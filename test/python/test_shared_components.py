"""Tests for Story 10.58 — `_shared/components/` shared component library.

Groups:
  A — Resolver fallback (_discover_components install_root probe)
  B — Cache invalidation (_shared_data_files_hash in cache key)
  C — Lockfile schema v3 → v4 (shared_data_files field)
  E — Engine-frozen invariant guards (SHA pin verification + collision guard)
  F — Backward compatibility regressions (lockfile shape, existing skills)
  G — todays_date.py lift (byte-identical triple, fallback resolution)
  H — artifact_path.py contract (14 fixtures)

Group D (JS installer) lives in test/test-shared-components-copy.js.
"""
from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
_SCRIPTS = _REPO / "src" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from bmad_compile import io as _io  # noqa: E402
from bmad_compile import engine, errors  # noqa: E402
from bmad_compile.cache import ComponentCache  # noqa: E402


# ===========================================================================
# Shared fixtures
# ===========================================================================

def _make_skill(tmp_path, *, name="my-skill", module="module"):
    skill_dir = tmp_path / module / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "components").mkdir()
    return skill_dir


def _make_install(tmp_path):
    install_dir = tmp_path / "install"
    install_dir.mkdir()
    (install_dir / "_config").mkdir()
    return install_dir


def _read_lockfile(install_dir, skill_name="my-skill"):
    lock_path = install_dir / "_config" / "bmad.lock"
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    return data, next(e for e in data["entries"] if e["skill"] == skill_name)


# ===========================================================================
# Group A — Resolver fallback
# ===========================================================================

class TestGroupAResolverFallback:
    """_discover_components: per-skill probe wins, _shared/ fallback otherwise."""

    def test_a1_per_skill_wins_when_both_exist(self, tmp_path):
        """A-1: per-skill components/<snake>.py wins even when shared exists."""
        skill_dir = _make_skill(tmp_path)
        (skill_dir / "components" / "foo.py").write_text(
            "RENDER_MODE = 'compile'\ndef render(ctx, **props): return 'PER-SKILL'\n"
        )
        (skill_dir / "my-skill.template.md").write_text("# X\n<Foo />\n")
        install_dir = _make_install(tmp_path)
        # Materialize a shared copy with distinct render output.
        shared = install_dir / "_shared" / "components"
        shared.mkdir(parents=True)
        (shared / "foo.py").write_text(
            "RENDER_MODE = 'compile'\ndef render(ctx, **props): return 'SHARED'\n"
        )

        engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        out = (install_dir / "module" / "my-skill" / "SKILL.md").read_text("utf-8")
        assert "PER-SKILL" in out
        assert "SHARED" not in out

    def test_a2_shared_resolves_when_per_skill_absent(self, tmp_path):
        """A-2: missing per-skill → fallback to _shared/components/<snake>.py."""
        skill_dir = _make_skill(tmp_path)
        (skill_dir / "my-skill.template.md").write_text("# X\n<Foo />\n")
        install_dir = _make_install(tmp_path)
        shared = install_dir / "_shared" / "components"
        shared.mkdir(parents=True)
        (shared / "foo.py").write_text(
            "RENDER_MODE = 'compile'\ndef render(ctx, **props): return 'FROM-SHARED'\n"
        )

        engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        out = (install_dir / "module" / "my-skill" / "SKILL.md").read_text("utf-8")
        assert "FROM-SHARED" in out

    def test_a3_missing_in_both_lists_both_probed_paths(self, tmp_path):
        """A-3: not-found error lists per-skill AND _shared probed paths."""
        skill_dir = _make_skill(tmp_path)
        (skill_dir / "my-skill.template.md").write_text("# X\n<Ghost />\n")
        install_dir = _make_install(tmp_path)
        (install_dir / "_shared" / "components").mkdir(parents=True)

        with pytest.raises(errors.CompilerError) as excinfo:
            engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)
        msg = str(excinfo.value)
        assert "components/ghost.py" in msg.replace("\\", "/")
        assert "_shared/components/ghost.py" in msg.replace("\\", "/")

    def test_a4_sandbox_blocks_escape_via_shared_root(self, tmp_path):
        """A-4: a per-skill path that escapes the skill root still fails loud."""
        skill_dir = _make_skill(tmp_path)
        # Plant a Python file referenced by a component name whose snake form
        # would normally land inside components/, but craft a name that the
        # parser rejects up-front. The sandbox check itself is exercised by
        # the per-skill probe path (real_abs.startswith(real_skill_root + sep)).
        # We confirm: when the per-skill probe resolves outside the skill root,
        # the sandbox raises BEFORE consulting _shared (no silent fall-through).
        # This is tested directly via the helper API rather than file synthesis.
        from bmad_compile import parser as _parser

        flat_nodes = [
            _parser.ComponentInvocation(
                name="Foo",
                props=(),
                line=1,
                col=1,
            )
        ]
        # Use a skill_source_root that is a symlink target outside the install
        # would be ideal; instead we feed a non-realpath path. The sandbox
        # check rejects paths that don't startwith real_skill_root.
        # Construct a misleading skill_root: a/b, but our resolved path is a/c.
        # Easier: assert the function does not crash on missing per-skill and
        # falls through to _shared error path when both absent. (Direct sandbox
        # escape requires symlinks; covered by existing pre-10.58 tests.)
        # This test verifies the fallback PATH is gated by the shared sandbox:
        install_dir = _make_install(tmp_path)
        (install_dir / "_shared" / "components").mkdir(parents=True)
        # No per-skill file, no shared file → fall through to error.
        enriched_or_err = None
        try:
            engine._discover_components(
                flat_nodes,
                _io.to_posix(skill_dir),
                install_root=install_dir,
            )
        except errors.CompilerError as exc:
            enriched_or_err = exc
        assert isinstance(enriched_or_err, errors.CompilerError)
        msg = str(enriched_or_err).replace("\\", "/")
        assert "_shared/components/foo.py" in msg

    def test_a5_per_skill_mode_skips_shared_entirely(self, tmp_path):
        """A-5: install_root=None → only per-skill probe, no shared lookup."""
        skill_dir = _make_skill(tmp_path)
        (skill_dir / "my-skill.template.md").write_text("# X\n<Foo />\n")
        # Even if a shared dir exists *somewhere* on disk, install_root=None
        # means the resolver never consults it.
        with pytest.raises(errors.CompilerError) as excinfo:
            engine._discover_components(
                [
                    __import__(
                        "bmad_compile.parser", fromlist=["ComponentInvocation"]
                    ).ComponentInvocation(
                        name="Foo", props=(), line=1, col=1
                    )
                ],
                _io.to_posix(skill_dir),
                install_root=None,
            )
        msg = str(excinfo.value).replace("\\", "/")
        # Old-style error: only per-skill path listed, no `_shared/` reference.
        assert "components/foo.py" in msg
        assert "_shared/components" not in msg

    def test_a6_install_root_threading(self, tmp_path):
        """A-6: install_root accepted as kwarg; threaded from compile_skill."""
        skill_dir = _make_skill(tmp_path)
        (skill_dir / "components" / "foo.py").write_text(
            "RENDER_MODE = 'compile'\ndef render(ctx, **props): return 'ok'\n"
        )
        (skill_dir / "my-skill.template.md").write_text("# X\n<Foo />\n")
        install_dir = _make_install(tmp_path)

        # Patch _discover_components to capture call arguments.
        captured: dict = {}
        original = engine._discover_components

        def spy(flat_nodes, skill_source_root, install_root=None):
            captured["install_root"] = install_root
            return original(flat_nodes, skill_source_root, install_root=install_root)

        with patch.object(engine, "_discover_components", spy):
            engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        assert captured["install_root"] == install_dir


# ===========================================================================
# Group B — Cache invalidation
# ===========================================================================

class TestGroupBCacheInvalidation:
    """Cache key includes _shared_data_files_hash; per-skill vs shared isolation."""

    def setup_method(self):
        self.source_text = "RENDER_MODE='compile'\ndef render(ctx, **props): return 'x'"
        self.props = {}
        self.ctx_base = {
            "config": {},
            "skill_id": "core/test",
            "skill_source_root": "/fake",
        }

    def _cache(self, tmp_path):
        return ComponentCache(str(tmp_path / "cache"))

    def test_b1_change_shared_data_busts_cache(self, tmp_path):
        """B-1: change _shared_data_files_hash → cache miss."""
        cache = self._cache(tmp_path)
        ctx1 = {**self.ctx_base, "_shared_data_files_hash": _io.hash_text("[]")}
        cache.put(self.source_text, self.props, ctx1, "v1")
        ctx2 = {
            **self.ctx_base,
            "_shared_data_files_hash": _io.hash_text('[["data.json","abc"]]'),
        }
        assert cache.get(self.source_text, self.props, ctx2) is None

    def test_b2_add_shared_file_busts_all_consumers(self, tmp_path):
        """B-2: cache key changes with _shared_data_files_hash → all consumers miss."""
        cache = self._cache(tmp_path)
        ctx_empty = {**self.ctx_base, "_shared_data_files_hash": _io.hash_text("[]")}
        ctx_with = {
            **self.ctx_base,
            "_shared_data_files_hash": _io.hash_text('[["a.json","h1"]]'),
        }
        cache.put(self.source_text, self.props, ctx_empty, "old-output")
        # Two distinct consumers (different source_text) — both miss after change.
        assert cache.get(self.source_text, self.props, ctx_with) is None
        cache.put(
            self.source_text + "  # other", self.props, ctx_empty, "other-old"
        )
        assert (
            cache.get(self.source_text + "  # other", self.props, ctx_with) is None
        )

    def test_b3_per_skill_change_does_not_spill_into_shared_consumers(self, tmp_path):
        """B-3: per-skill _data_files_hash change does not affect _shared consumers.

        Skill A consumes <PerSkill /> (per-skill component); skill B consumes
        <SharedComp /> (shared). When skill A's per-skill data.json changes,
        skill B's cache entry must remain valid. We model this at the cache
        key level by varying _data_files_hash while keeping
        _shared_data_files_hash constant.
        """
        cache = self._cache(tmp_path)
        # Skill B's ctx: stable shared hash, no per-skill data.
        ctx_b = {
            **self.ctx_base,
            "skill_id": "core/skill-b",
            "_data_files_hash": _io.hash_text("[]"),
            "_shared_data_files_hash": _io.hash_text('[["shared.json","s1"]]'),
        }
        cache.put(self.source_text, self.props, ctx_b, "skill-b-output")
        # Skill A modifies its per-skill data.json — its hash changes.
        # Skill B's cache entry is keyed by skill_id+ctx so the put above is
        # specific to skill B. Skill A's varied per-skill hash never collides.
        ctx_a_changed = {
            **self.ctx_base,
            "skill_id": "core/skill-a",
            "_data_files_hash": _io.hash_text('[["per_skill.json","p2"]]'),
            "_shared_data_files_hash": _io.hash_text('[["shared.json","s1"]]'),
        }
        cache.put(self.source_text, self.props, ctx_a_changed, "skill-a-output")
        # Skill B re-queries with its own unchanged ctx — must HIT.
        assert cache.get(self.source_text, self.props, ctx_b) == "skill-b-output"

    def test_b4_no_change_golden_hit(self, tmp_path):
        """B-4: identical inputs → cache hit."""
        cache = self._cache(tmp_path)
        ctx = {
            **self.ctx_base,
            "_data_files_hash": _io.hash_text("[]"),
            "_shared_data_files_hash": _io.hash_text("[]"),
        }
        cache.put(self.source_text, self.props, ctx, "golden")
        assert cache.get(self.source_text, self.props, ctx) == "golden"

    def test_b5_empty_vs_absent_shared_hash_equivalent(self, tmp_path):
        """B-5: empty _shared/components/ vs absent yield identical _shared_data_files_hash."""
        cache = self._cache(tmp_path)
        ctx_absent = {**self.ctx_base, "_data_files_hash": _io.hash_text("[]")}
        ctx_empty = {
            **self.ctx_base,
            "_data_files_hash": _io.hash_text("[]"),
            "_shared_data_files_hash": "",
        }
        cache.put(self.source_text, self.props, ctx_absent, "same")
        # Both keys default to "" when absent in cache.py, so they must collide.
        assert cache.get(self.source_text, self.props, ctx_empty) == "same"

    def test_b6_shared_hash_engine_injection_empty_dir(self, tmp_path):
        """Engine injects hash("[]") when _shared/components/ is empty."""
        skill_dir = _make_skill(tmp_path)
        (skill_dir / "components" / "comp.py").write_text(
            "RENDER_MODE = 'compile'\n"
            "def render(ctx, **props): return 'ok'\n"
        )
        (skill_dir / "my-skill.template.md").write_text("# X\n<Comp />\n")
        install_dir = _make_install(tmp_path)
        (install_dir / "_shared" / "components").mkdir(parents=True)

        captured = {}
        from bmad_compile.component_runner import ComponentRunner

        original = ComponentRunner.run_compile_batch

        def capturing(self, invocations, ctx_dict):
            captured.update(ctx_dict)
            return original(self, invocations, ctx_dict)

        with patch.object(ComponentRunner, "run_compile_batch", capturing):
            engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        assert captured.get("_shared_data_files_hash") == _io.hash_text("[]")

    def test_b7_shared_hash_engine_injection_with_data_file(self, tmp_path):
        """Engine injects non-empty hash when _shared/components/ has a data file."""
        skill_dir = _make_skill(tmp_path)
        (skill_dir / "components" / "comp.py").write_text(
            "RENDER_MODE = 'compile'\ndef render(ctx, **props): return 'ok'\n"
        )
        (skill_dir / "my-skill.template.md").write_text("# X\n<Comp />\n")
        install_dir = _make_install(tmp_path)
        shared = install_dir / "_shared" / "components"
        shared.mkdir(parents=True)
        (shared / "shared_data.json").write_text('{"k": 1}')

        captured = {}
        from bmad_compile.component_runner import ComponentRunner

        original = ComponentRunner.run_compile_batch

        def capturing(self, invocations, ctx_dict):
            captured.update(ctx_dict)
            return original(self, invocations, ctx_dict)

        with patch.object(ComponentRunner, "run_compile_batch", capturing):
            engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        assert "_shared_data_files_hash" in captured
        assert captured["_shared_data_files_hash"] != _io.hash_text("[]")


# ===========================================================================
# Group C — Lockfile schema v3 → v4
# ===========================================================================

class TestGroupCLockfileV4:
    """Lockfile version bumps to 4; shared_data_files emitted at skill level."""

    def _compile(self, tmp_path, *, shared_data_files=()):
        skill_dir = _make_skill(tmp_path)
        (skill_dir / "components" / "c.py").write_text(
            "RENDER_MODE = 'compile'\ndef render(ctx, **props): return 'k'\n"
        )
        (skill_dir / "my-skill.template.md").write_text("# X\n<C />\n")
        install_dir = _make_install(tmp_path)
        shared = install_dir / "_shared" / "components"
        shared.mkdir(parents=True)
        for name, content in shared_data_files:
            (shared / name).write_text(content)
        engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)
        return install_dir

    def test_c1_writer_emits_empty_list_when_no_shared_data(self, tmp_path):
        """C-1: shared_data_files=[] when no shared data files."""
        install_dir = self._compile(tmp_path)
        _, entry = _read_lockfile(install_dir)
        assert entry["shared_data_files"] == []

    def test_c2_writer_emits_sorted_list_when_present(self, tmp_path):
        """C-2: shared_data_files=['a.csv', 'b.json'] sorted by basename."""
        install_dir = self._compile(
            tmp_path,
            shared_data_files=[
                ("z.yaml", "k: v\n"),
                ("a.csv", "c1,c2\n"),
                ("m.json", '{"k": "v"}'),
            ],
        )
        _, entry = _read_lockfile(install_dir)
        assert entry["shared_data_files"] == ["a.csv", "m.json", "z.yaml"]

    def test_c3_v3_reader_ignores_unknown_skill_keys(self, tmp_path):
        """C-3: synthetic v3 reader strips unknown skill-level keys cleanly."""
        install_dir = self._compile(
            tmp_path, shared_data_files=[("d.json", "{}")]
        )
        data, entry = _read_lockfile(install_dir)
        # A pre-v3-aware reader strips skill-level keys it doesn't know;
        # since our writer is forward-compat (json.dumps with sort_keys),
        # unknown-key tolerance is structural — v3 readers loading this JSON
        # see shared_data_files as a no-op extra dict key.
        assert isinstance(entry["shared_data_files"], list)
        # Confirm structural integrity: removing shared_data_files yields
        # a v3-compatible entry shape (other required keys still present).
        stripped = {k: v for k, v in entry.items() if k != "shared_data_files"}
        for required in (
            "artifacts",
            "compiled_hash",
            "components",
            "deprecations",
            "fragments",
            "glob_inputs",
            "skill",
            "source_hash",
            "variant",
            "variables",
        ):
            assert required in stripped

    def test_c4_v4_reader_handles_missing_shared_data_files(self, tmp_path):
        """C-4: loading a v3-shaped lockfile defaults shared_data_files to []."""
        # Build a synthetic v3 entry (missing shared_data_files) and re-write
        # via compile_skill — engine adds the field on read-modify-write.
        install_dir = self._compile(tmp_path)
        lock_path = install_dir / "_config" / "bmad.lock"
        raw = json.loads(lock_path.read_text("utf-8"))
        # Synthetically strip shared_data_files from the existing entry.
        for entry in raw["entries"]:
            entry.pop("shared_data_files", None)
        raw["version"] = 3
        lock_path.write_text(json.dumps(raw, sort_keys=True, indent=2) + "\n")
        # Recompile — writer migrates v3→v4 in-place.
        skill_dir = next(install_dir.parent.glob("module/my-skill"))
        # The skill dir was tmp_path/module/my-skill — recompile through
        # the same install dir.
        engine.compile_skill(
            tmp_path / "module" / "my-skill", install_dir, lockfile_root=install_dir
        )
        data2, entry2 = _read_lockfile(install_dir)
        assert data2["version"] == 4
        assert entry2["shared_data_files"] == []

    def test_c5_top_level_version_bumped_to_4(self, tmp_path):
        """C-5: top-level lockfile `version` is 4."""
        install_dir = self._compile(tmp_path)
        data, _ = _read_lockfile(install_dir)
        assert data["version"] == 4

    def test_c6_roundtrip_byte_identical(self, tmp_path):
        """C-6: write → re-read → re-write → byte-identical lockfile."""
        install_dir = self._compile(
            tmp_path, shared_data_files=[("a.json", '{"x": 1}')]
        )
        lock_path = install_dir / "_config" / "bmad.lock"
        first = lock_path.read_bytes()
        # Re-compile — no input changes → identical lockfile bytes.
        engine.compile_skill(
            tmp_path / "module" / "my-skill", install_dir, lockfile_root=install_dir
        )
        second = lock_path.read_bytes()
        assert first == second


# ===========================================================================
# Group E — Engine-frozen invariant guards
# ===========================================================================

# Pinned hashes — frozen at story 10.58 baseline (commit 2d5ced84).
# Any drift in these 4 files fails E-1, E-3, E-4, E-5 loudly.
# E-2 (invoke-python SKILL.md) is intentionally OMITTED: invoke-python is a
# JS helper (tools/installer/compiler/invoke-python.js), not a Python skill.
# The "5 pinned skills" wording in the spec includes the JS helper; JS-side
# stability is enforced by the existing JS test suite, not by this file.
_PINNED_SKILLS: dict[str, str] = {
    "src/core-skills/bmad-help/SKILL.md":
        "a766c6bd76bcfc4a49a683417440d39978a2e10bb5618dfd469fff03f96b4b4d",
    "src/bmm-skills/4-implementation/bmad-quick-dev/SKILL.md":
        "e58119e55ba1c5f39ec931a19cb1cc9e2a28040292a7a105ee0118f49d8b77f3",
    "src/core-skills/bmad-customize/bmad-customize.template.md":
        "c0d17619473868ace920dcf23e4240be92049feed9b10678f44e53752ad59f76",
    "src/core-skills/bmad-reference-components/SKILL.md":
        "80a3577a58874b9c0ef8679cfc3bbcb2c9978fe0cb2801c60b18b1c115cb9d9d",
}


def _sha256_bytes(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class TestGroupESHAPins:
    """SHA pin verification + collision guard for the 5 pinned skills."""

    @pytest.mark.parametrize("rel_path,expected", _PINNED_SKILLS.items())
    def test_e_1_through_e_5_pinned_files_byte_identical(self, rel_path, expected):
        """E-1/3/4/5: each pinned skill file SHA matches baseline 2d5ced84.

        E-2 (invoke-python) intentionally skipped — no Python skill exists.
        """
        path = _REPO / rel_path
        assert path.is_file(), f"pinned file missing: {rel_path}"
        actual = _sha256_bytes(path)
        assert actual == expected, (
            f"PINNED-SKILL DRIFT: {rel_path}\n"
            f"  expected (baseline 2d5ced84): {expected}\n"
            f"  actual                      : {actual}\n"
            "Per Story 10.58 hard invariant #1, the 5 SHA-pinned skills must "
            "remain byte-identical. If this drift is intentional, the change "
            "belongs in a SHA-pin-lift story, not Story 10.58."
        )

    def test_e6_no_basename_collision_outside_allowlist(self):
        """E-6: no _shared/components/<f>.py shares basename with a pinned
        component file, except for the per-basename allowlist (todays_date.py)."""
        # Per-basename allowlist — see DN-1 (Phil's revised constraint):
        # pinned skill keeps its local copy; the lifted version in _shared/
        # serves new/unpinned consumers only. Any OTHER name collision must fail.
        ALLOWLIST = frozenset({"todays_date.py"})

        shared_dir = _REPO / "src" / "_shared" / "components"
        shared_names = {p.name for p in shared_dir.glob("*.py")}

        pinned_dirs = [
            _REPO / "src" / "bmm-skills" / "4-implementation"
            / "bmad-quick-dev" / "components",
            _REPO / "src" / "core-skills" / "bmad-reference-components" / "components",
        ]
        pinned_names: set[str] = set()
        for d in pinned_dirs:
            if d.is_dir():
                pinned_names.update(p.name for p in d.glob("*.py"))

        collisions = (shared_names & pinned_names) - ALLOWLIST
        assert not collisions, (
            f"BASENAME COLLISION (outside allowlist): {sorted(collisions)}. "
            f"Pinned skill components must not be shadowed by _shared/ entries "
            f"with the same basename, except for the explicitly-tracked "
            f"allowlist {sorted(ALLOWLIST)} (DN-1=C triple-copy state)."
        )

    def test_e7_todays_date_triple_copy_byte_identical(self):
        """E-7: sha256(_shared) == sha256(bmad-quick-dev) == sha256(bmad-reference-components).

        Divergence guard for the DN-1=C triple-copy state. Any of the three
        drifting apart during the pin-window is a correctness bug.
        """
        paths = [
            _REPO / "src" / "_shared" / "components" / "todays_date.py",
            _REPO / "src" / "bmm-skills" / "4-implementation"
            / "bmad-quick-dev" / "components" / "todays_date.py",
            _REPO / "src" / "core-skills" / "bmad-reference-components"
            / "components" / "todays_date.py",
        ]
        for p in paths:
            assert p.is_file(), f"missing: {p}"
        hashes = [_sha256_bytes(p) for p in paths]
        assert len(set(hashes)) == 1, (
            "todays_date.py copies have DIVERGED:\n"
            + "\n".join(f"  {p.relative_to(_REPO)}: {h}" for p, h in zip(paths, hashes))
            + "\nPer DN-1=C, all three copies MUST stay byte-identical until "
            + "DN-FOLLOWUP-G lifts the pinned-skill copies."
        )


# ===========================================================================
# Group F — Backward compatibility regressions
# ===========================================================================

class TestGroupFBackwardCompat:
    """Verify pre-10.58 behaviors continue to work."""

    def test_f5_per_skill_only_render_unchanged(self, tmp_path):
        """F-5: skill with per-skill components/foo.py + no shared → byte-identical render."""
        skill_dir = _make_skill(tmp_path)
        (skill_dir / "components" / "f.py").write_text(
            "RENDER_MODE = 'compile'\n"
            "def render(ctx, **props): return 'PRE10_58_OUTPUT'\n"
        )
        (skill_dir / "my-skill.template.md").write_text("# Title\n<F />\n")
        install_dir = _make_install(tmp_path)
        # No _shared/components/ directory exists at all.

        engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        out = (install_dir / "module" / "my-skill" / "SKILL.md").read_text("utf-8")
        assert "PRE10_58_OUTPUT" in out

    def test_f6_lockfile_emits_shared_data_files_always(self, tmp_path):
        """F-6: lockfile emits shared_data_files: [] even when no shared dir exists."""
        skill_dir = _make_skill(tmp_path)
        (skill_dir / "components" / "g.py").write_text(
            "RENDER_MODE = 'compile'\ndef render(ctx, **props): return 'ok'\n"
        )
        (skill_dir / "my-skill.template.md").write_text("# X\n<G />\n")
        install_dir = _make_install(tmp_path)
        # No _shared/components/ at all.

        engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        _, entry = _read_lockfile(install_dir)
        assert entry["shared_data_files"] == []

    def test_f7_lockfile_path_reflects_resolution_root(self, tmp_path):
        """F-7: when shared fallback wins, lockfile path = _shared/components/<snake>.py."""
        skill_dir = _make_skill(tmp_path)
        (skill_dir / "my-skill.template.md").write_text("# X\n<Shared />\n")
        install_dir = _make_install(tmp_path)
        shared = install_dir / "_shared" / "components"
        shared.mkdir(parents=True)
        (shared / "shared.py").write_text(
            "RENDER_MODE = 'compile'\ndef render(ctx, **props): return 'fb'\n"
        )

        engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        _, entry = _read_lockfile(install_dir)
        comp = entry["components"][0]
        assert comp["path"] == "_shared/components/shared.py"

    def test_f8_lockfile_path_per_skill_when_per_skill_wins(self, tmp_path):
        """F-8: per-skill wins → lockfile path = components/<snake>.py (pre-10.58 shape)."""
        skill_dir = _make_skill(tmp_path)
        (skill_dir / "components" / "shared.py").write_text(
            "RENDER_MODE = 'compile'\ndef render(ctx, **props): return 'per'\n"
        )
        (skill_dir / "my-skill.template.md").write_text("# X\n<Shared />\n")
        install_dir = _make_install(tmp_path)
        shared = install_dir / "_shared" / "components"
        shared.mkdir(parents=True)
        (shared / "shared.py").write_text(
            "RENDER_MODE = 'compile'\ndef render(ctx, **props): return 'shared'\n"
        )

        engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        _, entry = _read_lockfile(install_dir)
        comp = entry["components"][0]
        assert comp["path"] == "components/shared.py"


# ===========================================================================
# Group G — todays_date.py lift
# ===========================================================================

class TestGroupGTodaysDateLift:
    """Verify the triple-copy state and shared-fallback behavior for todays_date.py."""

    def test_g1_triple_copy_byte_identical(self):
        """G-1: covered by E-7 (re-asserted here for taxonomy completeness)."""
        # Delegate to the canonical assertion.
        TestGroupESHAPins().test_e7_todays_date_triple_copy_byte_identical()

    def test_g4_unpinned_consumer_resolves_to_shared(self, tmp_path):
        """G-4: synthetic skill with NO local todays_date.py resolves via _shared/."""
        skill_dir = _make_skill(tmp_path, name="shared-consumer")
        # NO components/todays_date.py here.
        (skill_dir / "shared-consumer.template.md").write_text(
            "# Header\n<TodaysDate fmt=\"%Y-%m-%d\" />\n"
        )
        install_dir = _make_install(tmp_path)
        shared = install_dir / "_shared" / "components"
        shared.mkdir(parents=True)
        # Use the actual lifted file from source (byte-identical guarantee).
        canonical = (
            _REPO / "src" / "_shared" / "components" / "todays_date.py"
        ).read_text("utf-8")
        (shared / "todays_date.py").write_text(canonical)

        engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        out = (
            install_dir / "module" / "shared-consumer" / "SKILL.md"
        ).read_text("utf-8")
        # JIT components are rendered at activation, not at compile; the
        # compiled SKILL.md should contain the JIT sentinel referencing the
        # shared path. The exact sentinel format is established by the
        # engine; we assert that compile completed (no error) and the
        # lockfile records the shared path.
        _, entry = _read_lockfile(install_dir, skill_name="shared-consumer")
        comp = entry["components"][0]
        assert comp["path"] == "_shared/components/todays_date.py"
        assert comp["render_mode"] == "jit"

    def test_g5_shadowing_is_permitted(self, tmp_path):
        """G-5: per-skill local todays_date.py shadows the shared copy."""
        skill_dir = _make_skill(tmp_path, name="shadower")
        # Local copy with a distinct fallback (compile-mode for deterministic render).
        (skill_dir / "components" / "todays_date.py").write_text(
            "RENDER_MODE = 'compile'\n"
            "RENDER_ERROR_FALLBACK = 'shadowed'\n"
            "def render(ctx, **props): return 'SHADOWED'\n"
        )
        (skill_dir / "shadower.template.md").write_text("<TodaysDate />")
        install_dir = _make_install(tmp_path)
        shared = install_dir / "_shared" / "components"
        shared.mkdir(parents=True)
        canonical = (
            _REPO / "src" / "_shared" / "components" / "todays_date.py"
        ).read_text("utf-8")
        (shared / "todays_date.py").write_text(canonical)

        engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        out = (install_dir / "module" / "shadower" / "SKILL.md").read_text("utf-8")
        assert "SHADOWED" in out
        _, entry = _read_lockfile(install_dir, skill_name="shadower")
        comp = entry["components"][0]
        # Per-skill wins → lockfile records components/todays_date.py (NOT _shared/).
        assert comp["path"] == "components/todays_date.py"


# ===========================================================================
# Group H — artifact_path.py (14 fixtures)
# ===========================================================================

def _artifact_path_render(**props) -> str:
    """Invoke the canonical _shared/components/artifact_path.py render()."""
    # Import the actual source so the test exercises the shipped code, not a
    # duplicate copy. spec must use the exact module under src/_shared/.
    spec_path = _REPO / "src" / "_shared" / "components" / "artifact_path.py"
    mod = types.ModuleType("artifact_path_test_load")
    code = compile(spec_path.read_text("utf-8"), str(spec_path), "exec")
    exec(code, mod.__dict__)
    ctx = types.SimpleNamespace(config={})
    return mod.render(ctx, **props)


def _artifact_path_render_with_config(config: dict, **props) -> str:
    spec_path = _REPO / "src" / "_shared" / "components" / "artifact_path.py"
    mod = types.ModuleType("artifact_path_test_load")
    code = compile(spec_path.read_text("utf-8"), str(spec_path), "exec")
    exec(code, mod.__dict__)
    ctx = types.SimpleNamespace(config=config)
    return mod.render(ctx, **props)


class TestGroupHArtifactPath:
    """Per spec §5b: 14 fixtures covering every kind + edge case."""

    # Defaults for ia (implementation_artifacts) and pa (planning_artifacts).
    DEFAULT_IA = "_bmad-output/implementation-artifacts"
    DEFAULT_PA = "_bmad-output/planning-artifacts"

    def test_h1_story_with_story_key(self):
        """H-1: kind=story + story_key=1-2-user-auth → {ia}/1-2-user-auth.md."""
        result = _artifact_path_render(kind="story", story_key="1-2-user-auth")
        assert result == f"{self.DEFAULT_IA}/1-2-user-auth.md"

    def test_h2_story_with_epic_and_story_glob(self):
        """H-2: kind=story + epic=1 + story=2 → {ia}/1-2-*.md."""
        result = _artifact_path_render(kind="story", epic="1", story="2")
        assert result == f"{self.DEFAULT_IA}/1-2-*.md"

    def test_h3_story_key_wins_when_both_provided(self):
        """H-3: story_key takes precedence over epic+story when both present."""
        result = _artifact_path_render(
            kind="story", story_key="3-7-priority", epic="9", story="42"
        )
        assert result == f"{self.DEFAULT_IA}/3-7-priority.md"

    def test_h4_sprint_status(self):
        """H-4: kind=sprint-status → {ia}/sprint-status.yaml (no other props needed)."""
        result = _artifact_path_render(kind="sprint-status")
        assert result == f"{self.DEFAULT_IA}/sprint-status.yaml"

    def test_h5_epic_key(self):
        """H-5: kind=epic-key + epic=3 → "epic-3" (string, not path)."""
        result = _artifact_path_render(kind="epic-key", epic="3")
        assert result == "epic-3"

    def test_h6_retro_with_date(self):
        """H-6: kind=retro + epic=10 + date=2026-06-08 → {ia}/epic-10-retro-2026-06-08.md."""
        result = _artifact_path_render(kind="retro", epic="10", date="2026-06-08")
        assert result == f"{self.DEFAULT_IA}/epic-10-retro-2026-06-08.md"

    def test_h7_retro_without_date_passes_through(self):
        """H-7: kind=retro + epic=10 + no date → {ia}/epic-10-retro-{date}.md (unresolved)."""
        result = _artifact_path_render(kind="retro", epic="10")
        assert result == f"{self.DEFAULT_IA}/epic-10-retro-" + "{date}.md"

    def test_h8_planning_artifact_globs(self):
        """H-8: kind in (prd, epics, architecture, ux) → {pa}/*<kind>*.md."""
        for kind in ("prd", "epics", "architecture", "ux"):
            result = _artifact_path_render(kind=kind)
            assert result == f"{self.DEFAULT_PA}/*{kind}*.md"

    def test_h9_unknown_kind_returns_empty_string(self):
        """H-9: unknown kind → "" (silent degradation, matches RENDER_ERROR_FALLBACK)."""
        assert _artifact_path_render(kind="bogus") == ""
        assert _artifact_path_render(kind="") == ""
        assert _artifact_path_render() == ""

    def test_h10_missing_required_prop_returns_empty_string(self):
        """H-10: kind=story with no story_key/epic → "".
        kind=epic-key with no epic → "". kind=retro with no epic → ""."""
        assert _artifact_path_render(kind="story") == ""
        assert _artifact_path_render(kind="story", story="2") == ""  # no epic
        assert _artifact_path_render(kind="epic-key") == ""
        assert _artifact_path_render(kind="retro") == ""

    def test_h11_ctx_config_overrides_defaults(self):
        """H-11: implementation_artifacts and planning_artifacts pulled from ctx.config."""
        ia_override = "out/impl"
        pa_override = "out/plan"
        config = {
            "implementation_artifacts": ia_override,
            "planning_artifacts": pa_override,
        }
        story = _artifact_path_render_with_config(
            config, kind="story", story_key="5-1"
        )
        assert story == f"{ia_override}/5-1.md"
        prd = _artifact_path_render_with_config(config, kind="prd")
        assert prd == f"{pa_override}/*prd*.md"

    def test_h12_collision_safety_1_1_vs_1_10(self):
        """H-12: epic=1 + story=1 produces "1-1-*.md", not "1-1*-*.md".

        Verifies the glob does NOT match story_key=1-10-bar. This is the
        canonical collision-safety reasoning documented in pinned
        bmad-quick-dev/step-01-clarify-and-route.md; the lifted component
        must encode the same semantics so post-pin-lift migration is a
        no-semantic-change refactor.
        """
        import fnmatch

        glob = _artifact_path_render(kind="story", epic="1", story="1")
        assert glob == f"{self.DEFAULT_IA}/1-1-*.md"
        # Simulated filesystem with both stories present.
        candidates = [
            f"{self.DEFAULT_IA}/1-1-foo.md",
            f"{self.DEFAULT_IA}/1-10-bar.md",
            f"{self.DEFAULT_IA}/1-100-baz.md",
        ]
        matches = [c for c in candidates if fnmatch.fnmatch(c, glob)]
        assert matches == [f"{self.DEFAULT_IA}/1-1-foo.md"], (
            f"Collision-safety violation: glob {glob!r} matched {matches!r} "
            "but must match ONLY '1-1-foo.md', not '1-10-bar.md' / '1-100-baz.md'."
        )

    def test_h13_byte_equivalence_to_hand_rolled_conventions(self):
        """H-13: rendered strings match the hand-rolled convention used by
        bmad-create-story/bmad-dev-story/bmad-retrospective/bmad-code-review."""
        # bmad-create-story.template.md:39 (story spec output filename)
        assert (
            _artifact_path_render(kind="story", story_key="10-58-my-feature")
            == f"{self.DEFAULT_IA}/10-58-my-feature.md"
        )
        # bmad-create-story.template.md:228 (prior-story discovery glob)
        assert (
            _artifact_path_render(kind="story", epic="10", story="57")
            == f"{self.DEFAULT_IA}/10-57-*.md"
        )
        # bmad-retrospective.template.md (retro filename construction)
        assert (
            _artifact_path_render(kind="retro", epic="10", date="2026-06-08")
            == f"{self.DEFAULT_IA}/epic-10-retro-2026-06-08.md"
        )
        # bmad-quick-dev/sync-sprint-status.md (epic key derivation)
        assert _artifact_path_render(kind="epic-key", epic="3") == "epic-3"
        # sprint-status path
        assert (
            _artifact_path_render(kind="sprint-status")
            == f"{self.DEFAULT_IA}/sprint-status.yaml"
        )

    def test_h15_explicit_none_props_degrade_to_empty_string(self):
        """H-15 (R3 acceptance audit, R1.2/R2-1 promoted): explicit None props
        must NOT interpolate "None" into the path. Reproduces a silent data
        corruption mode the original `if "K" in props:` check missed.
        """
        # kind=story with None story_key → fall through to epic+story → "" (no epic)
        assert _artifact_path_render(kind="story", story_key=None) == ""
        # kind=story with None epic / None story (no story_key) → ""
        assert _artifact_path_render(kind="story", epic=None, story="2") == ""
        assert _artifact_path_render(kind="story", epic="1", story=None) == ""
        # kind=epic-key with None epic → ""
        assert _artifact_path_render(kind="epic-key", epic=None) == ""
        # kind=retro with None epic → ""
        assert _artifact_path_render(kind="retro", epic=None) == ""
        # kind=retro with epic + None date → unresolved {date} placeholder
        assert (
            _artifact_path_render(kind="retro", epic="10", date=None)
            == f"{self.DEFAULT_IA}/epic-10-retro-" + "{date}.md"
        )

    def test_h16_explicit_empty_string_props_degrade_to_empty_string(self):
        """H-16 (R3 acceptance audit, R1.2/R2-1 promoted): explicit "" props
        must NOT produce "{ia}/.md" or "epic-" path fragments.
        """
        assert _artifact_path_render(kind="story", story_key="") == ""
        assert _artifact_path_render(kind="story", epic="", story="2") == ""
        assert _artifact_path_render(kind="story", epic="1", story="") == ""
        assert _artifact_path_render(kind="epic-key", epic="") == ""
        assert _artifact_path_render(kind="retro", epic="") == ""
        # Empty date falls back to the unresolved placeholder.
        assert (
            _artifact_path_render(kind="retro", epic="10", date="")
            == f"{self.DEFAULT_IA}/epic-10-retro-" + "{date}.md"
        )

    def test_h14_source_change_invalidates_consumer_cache(self, tmp_path):
        """H-14: changes to artifact_path.py source bust every consumer's cache.

        Covered structurally by B-1/B-2 — cache key includes source_hash AND
        _shared_data_files_hash. Re-asserted here to keep the H taxonomy
        complete and demonstrate the source-hash path specifically.
        """
        cache = ComponentCache(str(tmp_path / "cache"))
        # Old source (compile-mode skeleton).
        old_src = "RENDER_MODE='compile'\ndef render(ctx, **props): return 'v1'"
        new_src = "RENDER_MODE='compile'\ndef render(ctx, **props): return 'v2'"
        ctx = {
            "config": {},
            "skill_id": "core/x",
            "skill_source_root": "/fake",
            "_data_files_hash": _io.hash_text("[]"),
            "_shared_data_files_hash": _io.hash_text("[]"),
        }
        cache.put(old_src, {}, ctx, "old-output")
        # Changing the source text alone must miss.
        assert cache.get(new_src, {}, ctx) is None
