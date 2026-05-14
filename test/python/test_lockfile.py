"""Unit tests for bmad_compile.lockfile — lockfile v1 writer."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.scripts.bmad_compile import engine, errors, io, lockfile, resolver
from src.scripts.bmad_compile.io import PurePosixPath
from src.scripts.bmad_compile.resolver import (
    CompileCache,
    ResolvedFragment,
    ResolvedValue,
    VariableScope,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_scope() -> VariableScope:
    return VariableScope({})


def _empty_cache() -> CompileCache:
    return CompileCache()


def _make_dep_tree_root_only(scenario_root: PurePosixPath) -> list:
    """Minimal dep_tree: just a root entry, no fragments."""
    root = ResolvedFragment(
        src="skill1/skill1.template.md",
        resolved_path=scenario_root / "core" / "skill1" / "skill1.template.md",
        resolved_from="base",
        local_props=(),
        merged_scope=(),
        nodes=[],
    )
    return [root]


def _call_write(
    lockfile_path: str,
    scenario_root: PurePosixPath,
    *,
    skill_basename: str = "skill1",
    source_text: str = "source",
    compiled_text: str = "compiled",
    dep_tree: list | None = None,
    var_scope: VariableScope | None = None,
    target_ide: str | None = None,
    cache: CompileCache | None = None,
) -> None:
    if dep_tree is None:
        dep_tree = _make_dep_tree_root_only(scenario_root)
    if var_scope is None:
        var_scope = _empty_scope()
    if cache is None:
        cache = _empty_cache()
    lockfile.write_skill_entry(
        lockfile_path,
        scenario_root,
        skill_basename,
        source_text=source_text,
        compiled_text=compiled_text,
        dep_tree=dep_tree,
        var_scope=var_scope,
        target_ide=target_ide,
        cache=cache,
    )


# ---------------------------------------------------------------------------
# TestReadLockfileVersion
# ---------------------------------------------------------------------------

class TestReadLockfileVersion(unittest.TestCase):

    def test_returns_none_for_missing_file(self) -> None:
        self.assertIsNone(lockfile.read_lockfile_version("/nonexistent/bmad.lock"))

    def test_returns_version_for_valid_lockfile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lf = Path(tmp) / "bmad.lock"
            lf.write_text(json.dumps({"version": 1, "compiled_at": "1.0.0"}), encoding="utf-8")
            self.assertEqual(lockfile.read_lockfile_version(str(lf)), 1)

    def test_returns_0_for_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lf = Path(tmp) / "bmad.lock"
            lf.write_text("not json {{{{", encoding="utf-8")
            self.assertEqual(lockfile.read_lockfile_version(str(lf)), 0)

    def test_returns_0_for_non_dict_top_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lf = Path(tmp) / "bmad.lock"
            lf.write_text("[1, 2, 3]", encoding="utf-8")
            self.assertEqual(lockfile.read_lockfile_version(str(lf)), 0)

    def test_returns_future_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lf = Path(tmp) / "bmad.lock"
            lf.write_text(json.dumps({"version": 2}), encoding="utf-8")
            self.assertEqual(lockfile.read_lockfile_version(str(lf)), 2)

    def test_handles_utf8_bom_prefixed_lockfile(self) -> None:
        # Round 3 EC-2: Windows authors / editors may save bmad.lock with a
        # UTF-8 BOM. Without BOM stripping the file would parse as malformed
        # and the engine would silently overwrite a perfectly valid v1 lockfile.
        with tempfile.TemporaryDirectory() as tmp:
            lf = Path(tmp) / "bmad.lock"
            lf.write_bytes(b"\xef\xbb\xbf" + json.dumps({"version": 1}).encode("utf-8"))
            self.assertEqual(lockfile.read_lockfile_version(str(lf)), 1)


# ---------------------------------------------------------------------------
# TestWriteSkillEntry
# ---------------------------------------------------------------------------

class TestWriteSkillEntry(unittest.TestCase):

    def test_lockfile_created_on_first_compile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "_bmad" / "_config" / "bmad.lock")
            _call_write(lf, root)
            self.assertTrue(io.is_file(lf))
            data = json.loads(io.read_template(lf))
            self.assertIsInstance(data, dict)

    def test_schema_version_is_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root)
            data = json.loads(io.read_template(lf))
            self.assertEqual(data["version"], 1)

    def test_compiled_at_is_sentinel_not_datetime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root)
            data = json.loads(io.read_template(lf))
            self.assertEqual(data["compiled_at"], "1.0.0")
            # Must not look like a datetime string
            self.assertNotIn("T", data["compiled_at"])
            self.assertNotIn("-", data["compiled_at"])

    def test_keys_sorted_alphabetically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root)
            data = json.loads(io.read_template(lf))
            keys = list(data.keys())
            self.assertEqual(keys, sorted(keys))

    def test_source_hash_and_compiled_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root, source_text="hello", compiled_text="world")
            data = json.loads(io.read_template(lf))
            entry = data["entries"][0]
            self.assertEqual(entry["source_hash"], io.hash_text("hello"))
            self.assertEqual(entry["compiled_hash"], io.hash_text("world"))

    def test_secret_not_in_lockfile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = PurePosixPath(tmp_dir)
            # Write a real YAML config file with a secret value
            config_dir = Path(tmp_dir) / "_bmad" / "core"
            config_dir.mkdir(parents=True)
            config_path = config_dir / "config.yaml"
            config_path.write_text("user_name: SECRET_VALUE\n", encoding="utf-8")
            scope = VariableScope.build(yaml_config_path=str(config_path))
            lf = str(root / "bmad.lock")
            _call_write(lf, root, var_scope=scope)
            text = io.read_template(lf)
            self.assertNotIn("SECRET_VALUE", text)
            self.assertNotIn('"value":', text)

    def test_variable_source_path_is_relative(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = PurePosixPath(io.to_posix(tmp_dir))
            # Create the config file at _bmad/core/config.yaml
            config_dir = Path(tmp_dir) / "_bmad" / "core"
            config_dir.mkdir(parents=True)
            config_path = config_dir / "config.yaml"
            config_path.write_text("user_name: World\n", encoding="utf-8")
            scope = VariableScope.build(yaml_config_path=str(config_path))
            lf = str(root / "bmad.lock")
            _call_write(lf, root, var_scope=scope)
            data = json.loads(io.read_template(lf))
            variables = data["entries"][0]["variables"]
            var = next(v for v in variables if v["name"] == "user_name")
            self.assertEqual(var["source_path"], "_bmad/core/config.yaml")

    def test_toml_variable_source_path_and_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = PurePosixPath("/abs/scenario")
            scope = VariableScope.build(
                toml_layers=[("team", {"agent": {"name": "PM"}})],
                toml_layer_paths=["/abs/scenario/_bmad/custom/my-skill.toml"],
            )
            lf_path = Path(tmp_dir) / "bmad.lock"
            _call_write(str(lf_path), root, var_scope=scope)
            data = json.loads(lf_path.read_text(encoding="utf-8"))
            variables = data["entries"][0]["variables"]
            var = next(v for v in variables if v["name"] == "self.agent.name")
            self.assertEqual(var["source_path"], "_bmad/custom/my-skill.toml")
            self.assertEqual(var["toml_layer"], "team")

    def test_local_scope_vars_excluded(self) -> None:
        table = {
            "regular_var": ResolvedValue(
                value="val", source="bmad-config", value_hash=io.hash_text("val")
            ),
            "ephemeral": ResolvedValue(
                value="eph", source="local-scope", value_hash=io.hash_text("eph")
            ),
        }
        scope = VariableScope(table)
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root, var_scope=scope)
            data = json.loads(io.read_template(lf))
            names = [v["name"] for v in data["entries"][0]["variables"]]
            self.assertIn("regular_var", names)
            self.assertNotIn("ephemeral", names)

    def test_no_value_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = PurePosixPath(tmp_dir)
            config_dir = Path(tmp_dir) / "_bmad" / "core"
            config_dir.mkdir(parents=True)
            config_path = config_dir / "config.yaml"
            config_path.write_text("user_name: World\n", encoding="utf-8")
            scope = VariableScope.build(yaml_config_path=str(config_path))
            lf = str(root / "bmad.lock")
            _call_write(lf, root, var_scope=scope)
            text = io.read_template(lf)
            self.assertNotIn('"value":', text)

    def test_fragment_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            # Create the fragment file so we have a real path
            frag_dir = Path(tmp) / "core" / "skill1" / "fragments"
            frag_dir.mkdir(parents=True)
            frag_file = frag_dir / "header.template.md"
            frag_src = "# Header fragment"
            frag_file.write_text(frag_src, encoding="utf-8")

            frag_path = PurePosixPath(io.to_posix(frag_file))
            cache = CompileCache()
            cache.put((frag_path, "base"), [], frag_src)

            root_rf = ResolvedFragment(
                src="skill1/skill1.template.md",
                resolved_path=root / "core" / "skill1" / "skill1.template.md",
                resolved_from="base",
                local_props=(),
                merged_scope=(),
                nodes=[],
            )
            frag_rf = ResolvedFragment(
                src="fragments/header.template.md",
                resolved_path=frag_path,
                resolved_from="base",
                local_props=(),
                merged_scope=(),
                nodes=[],
            )
            dep_tree = [root_rf, frag_rf]

            lf = str(root / "bmad.lock")
            _call_write(lf, root, dep_tree=dep_tree, cache=cache)
            data = json.loads(io.read_template(lf))
            fragments = data["entries"][0]["fragments"]
            self.assertEqual(len(fragments), 1)
            self.assertEqual(fragments[0]["hash"], io.hash_text(frag_src))
            self.assertEqual(fragments[0]["resolved_from"], "base")
            # path must be root-relative
            self.assertFalse(fragments[0]["path"].startswith("/"))

    def test_glob_inputs_is_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root)
            data = json.loads(io.read_template(lf))
            self.assertEqual(data["entries"][0]["glob_inputs"], [])

    def test_variant_null_when_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root, target_ide=None)
            data = json.loads(io.read_template(lf))
            self.assertIsNone(data["entries"][0]["variant"])

    def test_variant_set_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root, target_ide="cursor")
            data = json.loads(io.read_template(lf))
            self.assertEqual(data["entries"][0]["variant"], "cursor")


# ---------------------------------------------------------------------------
# TestDeterminism
# ---------------------------------------------------------------------------

class TestDeterminism(unittest.TestCase):

    def test_byte_identical_on_two_writes(self) -> None:
        # AC 7: rewriting the same lockfile path with identical inputs must be
        # byte-identical — exercises the read-modify-write upsert path, not
        # just two independent fresh writes.
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            kwargs = dict(
                source_text="hello world",
                compiled_text="rendered output",
                target_ide=None,
            )
            _call_write(lf, root, **kwargs)
            b1 = Path(lf).read_bytes()
            _call_write(lf, root, **kwargs)
            b2 = Path(lf).read_bytes()
            self.assertEqual(b1, b2)


# ---------------------------------------------------------------------------
# TestForwardCompat
# ---------------------------------------------------------------------------

class TestForwardCompat(unittest.TestCase):

    def test_unknown_top_level_key_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            initial = {
                "version": 1,
                "compiled_at": "1.0.0",
                "bmad_version": "1.0.0",
                "entries": [],
                "future_key": "preserved_value",
            }
            Path(lf).write_text(json.dumps(initial), encoding="utf-8")
            _call_write(lf, root)
            data = json.loads(io.read_template(lf))
            self.assertEqual(data["future_key"], "preserved_value")

    def test_existing_skill_entry_updated_not_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root, skill_basename="skill1", source_text="v1")
            _call_write(lf, root, skill_basename="skill1", source_text="v2")
            data = json.loads(io.read_template(lf))
            skill_entries = [e for e in data["entries"] if e.get("skill") == "skill1"]
            self.assertEqual(len(skill_entries), 1)
            self.assertEqual(skill_entries[0]["source_hash"], io.hash_text("v2"))

    def test_other_skill_entry_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root, skill_basename="skill-a", source_text="aaa")
            _call_write(lf, root, skill_basename="skill-b", source_text="bbb")
            _call_write(lf, root, skill_basename="skill-a", source_text="aaa-v2")
            data = json.loads(io.read_template(lf))
            names = [e.get("skill") for e in data["entries"]]
            self.assertIn("skill-a", names)
            self.assertIn("skill-b", names)

    def test_corrupt_entries_field_does_not_crash(self) -> None:
        # Round 3 EC-1: a dict-shaped lockfile whose ``entries`` key is null,
        # an int, or a string would TypeError on list(...) (None) or silently
        # explode a string into per-character entries. Treat as fresh start.
        for bad in (None, 42, "abc"):
            with tempfile.TemporaryDirectory() as tmp:
                root = PurePosixPath(tmp)
                lf = str(root / "bmad.lock")
                Path(lf).write_text(
                    json.dumps({"version": 1, "entries": bad}), encoding="utf-8"
                )
                _call_write(lf, root)
                data = json.loads(io.read_template(lf))
                self.assertEqual(len(data["entries"]), 1)
                self.assertEqual(data["entries"][0]["skill"], "skill1")


# ---------------------------------------------------------------------------
# TestVersionMismatch
# ---------------------------------------------------------------------------

class TestVersionMismatch(unittest.TestCase):

    def test_version_mismatch_raises(self) -> None:
        """write a v2 lockfile into the fixture tree, compile should raise."""
        import pathlib
        repo_root = pathlib.Path(__file__).resolve().parents[2]
        fixture_scenario = (
            repo_root / "test" / "fixtures" / "compile" / "variable-resolution"
        )
        lockfile_path = fixture_scenario / "_bmad" / "_config" / "bmad.lock"
        try:
            lockfile_path.parent.mkdir(parents=True, exist_ok=True)
            lockfile_path.write_text(
                json.dumps({"version": 2, "compiled_at": "1.0.0",
                            "bmad_version": "1.0.0", "entries": []}),
                encoding="utf-8",
            )
            skill = fixture_scenario / "core" / "var-resolution-skill"
            with tempfile.TemporaryDirectory() as tmp_out:
                with self.assertRaises(errors.LockfileVersionMismatchError) as ctx:
                    engine.compile_skill(str(skill), tmp_out)
            self.assertEqual(ctx.exception.code, "LOCKFILE_VERSION_MISMATCH")
            self.assertIn("upgrade", ctx.exception.hint or "")
        finally:
            lockfile_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Helpers — override-tier fixture construction (Story 5.3 lineage tests)
# ---------------------------------------------------------------------------

def _make_override_fixture(
    tmp: Path,
    scenario_root: "PurePosixPath",
    base_content: str,
    override_content: str,
) -> "tuple[list, CompileCache, Path, Path]":
    """Create override-tier dep_tree + cache for lineage tests.

    Returns (dep_tree, cache, base_file_path, override_file_path).
    Caller may mutate base_file_path.write_text(...) to simulate an upstream upgrade.
    """
    base_dir = tmp / "core" / "skill1" / "fragments"
    base_dir.mkdir(parents=True, exist_ok=True)
    base_file = base_dir / "intro.template.md"
    base_file.write_text(base_content, encoding="utf-8")

    override_dir = tmp / "_bmad" / "custom" / "fragments" / "core" / "skill1"
    override_dir.mkdir(parents=True, exist_ok=True)
    override_file = override_dir / "intro.template.md"
    override_file.write_text(override_content, encoding="utf-8")

    base_path = io.to_posix(str(base_file))
    override_path = io.to_posix(str(override_file))

    cache = CompileCache()
    cache.put((override_path, "user-module-fragment"), [], override_content)

    root_rf = ResolvedFragment(
        src="skill1/skill1.template.md",
        resolved_path=scenario_root / "core" / "skill1" / "skill1.template.md",
        resolved_from="base",
        local_props=(),
        merged_scope=(),
        nodes=[],
    )
    override_rf = ResolvedFragment(
        src="fragments/intro.template.md",
        resolved_path=override_path,
        resolved_from="user-module-fragment",
        local_props=(),
        merged_scope=(),
        nodes=[],
        base_path=base_path,
    )

    return [root_rf, override_rf], cache, base_file, override_file


def _serialize_lockfile(data: dict) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _reconstruct(data: dict, n: int = 1) -> dict:
    """Rewind lockfile data by n compile generations.

    For each generation, walks fragments[*] and variables[*] in every skill
    entry. Only variables with toml_layer in ("user", "team") and non-empty
    lineage are rewound — dormant carry-forward entries (toml_layer "defaults"
    or absent) are skipped because they hold only audit history, not a
    restorable active-override state. toml_layer is not in lineage entries and
    is not restored (test scenarios must keep toml_layer stable across all
    compiles).
    """
    data = copy.deepcopy(data)
    for _ in range(n):
        for entry in data.get("entries", []):
            # Rewind fragments
            for frag in entry.get("fragments", []):
                lin = frag.get("lineage")
                if lin:
                    frag["base_hash"] = lin[-1]["base_hash"]
                    frag["hash"] = lin[-1]["override_hash"]
                    frag["lineage"] = lin[:-1]
            # Rewind variables
            for var in entry.get("variables", []):
                lin = var.get("lineage")
                if not lin:
                    continue  # untracked or empty — nothing to rewind
                if var.get("toml_layer") not in ("user", "team"):
                    continue  # dormant carry-forward entry — skip
                var["value_hash"] = lin[-1]["override_value_hash"]
                var["base_value_hash"] = lin[-1]["base_value_hash"]
                var["lineage"] = lin[:-1]
    return data


# ---------------------------------------------------------------------------
# TestLineageInitialCompile (Task 3: AC 1)
# ---------------------------------------------------------------------------

class TestLineageInitialCompile(unittest.TestCase):

    def test_initial_compile_lineage_empty(self) -> None:
        """AC 1: override-tier fragment has lineage=[] on first compile."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            dep_tree, cache, _, _ = _make_override_fixture(
                t, root, "base content v1", "override content"
            )
            _call_write(lf, root, dep_tree=dep_tree, cache=cache)
            data = json.loads(io.read_template(lf))
            frags = data["entries"][0]["fragments"]
            override_frags = [
                f for f in frags if f.get("resolved_from") == "user-module-fragment"
            ]
            self.assertEqual(len(override_frags), 1)
            self.assertIn("lineage", override_frags[0])
            self.assertEqual(override_frags[0]["lineage"], [])


# ---------------------------------------------------------------------------
# TestLineageFragmentUpgrade (Task 4: AC 2)
# ---------------------------------------------------------------------------

class TestLineageFragmentUpgrade(unittest.TestCase):

    def test_upgrade_appends_lineage_entry(self) -> None:
        """AC 2: upgrading upstream base appends one lineage entry with correct fields."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            override_content = "override content"
            dep_tree, cache, base_file, _ = _make_override_fixture(
                t, root, "base v1", override_content
            )
            base_hash_v1 = io.hash_text("base v1")
            override_hash = io.hash_text(override_content)

            # Initial compile.
            _call_write(lf, root, dep_tree=dep_tree, cache=cache)

            # Simulate upstream upgrade: change base file content.
            base_file.write_text("base v2", encoding="utf-8")

            # Second compile with updated base.
            _call_write(lf, root, dep_tree=dep_tree, cache=cache)

            data = json.loads(io.read_template(lf))
            frag = next(
                f for f in data["entries"][0]["fragments"]
                if f.get("resolved_from") == "user-module-fragment"
            )
            self.assertEqual(len(frag["lineage"]), 1)
            entry = frag["lineage"][0]
            self.assertEqual(entry["base_hash"], base_hash_v1)
            self.assertEqual(entry["bmad_version"], "1.0.0")
            self.assertEqual(entry["override_hash"], override_hash)
            self.assertEqual(frag["base_hash"], io.hash_text("base v2"))
            self.assertEqual(frag["hash"], override_hash)

    def test_upgrade_no_change_carries_lineage(self) -> None:
        """AC 2: no-op recompile does not add duplicate lineage entries."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            dep_tree, cache, base_file, _ = _make_override_fixture(
                t, root, "base v1", "override"
            )

            _call_write(lf, root, dep_tree=dep_tree, cache=cache)

            base_file.write_text("base v2", encoding="utf-8")
            _call_write(lf, root, dep_tree=dep_tree, cache=cache)

            # No-op recompile — base unchanged.
            _call_write(lf, root, dep_tree=dep_tree, cache=cache)

            data = json.loads(io.read_template(lf))
            frag = next(
                f for f in data["entries"][0]["fragments"]
                if f.get("resolved_from") == "user-module-fragment"
            )
            self.assertEqual(len(frag["lineage"]), 1)

    def test_multiple_upgrades_append_not_replace(self) -> None:
        """AC 2: three upgrades produce 3 lineage entries; oldest entry preserved."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            dep_tree, cache, base_file, _ = _make_override_fixture(
                t, root, "base v1", "override"
            )
            base_hash_v1 = io.hash_text("base v1")

            _call_write(lf, root, dep_tree=dep_tree, cache=cache)

            for version in ("base v2", "base v3", "base v4"):
                base_file.write_text(version, encoding="utf-8")
                _call_write(lf, root, dep_tree=dep_tree, cache=cache)

            data = json.loads(io.read_template(lf))
            frag = next(
                f for f in data["entries"][0]["fragments"]
                if f.get("resolved_from") == "user-module-fragment"
            )
            self.assertEqual(len(frag["lineage"]), 3)
            self.assertEqual(frag["lineage"][0]["base_hash"], base_hash_v1)

    def test_pre_5_3_lockfile_initializes_lineage(self) -> None:
        """Task 4.4: pre-5.3 lockfile (no lineage key) migrates on first 5.3 upgrade."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            dep_tree, cache, base_file, _ = _make_override_fixture(
                t, root, "base v1", "override"
            )
            base_hash_v1 = io.hash_text("base v1")
            override_hash = io.hash_text("override")

            # Write a current-format lockfile, then manually strip lineage keys
            # to simulate a pre-5.3 lockfile that has no lineage field.
            _call_write(lf, root, dep_tree=dep_tree, cache=cache)
            data = json.loads(io.read_template(lf))
            for e in data["entries"]:
                for f in e.get("fragments", []):
                    f.pop("lineage", None)
            Path(lf).write_text(json.dumps(data), encoding="utf-8")

            # Upgrade: base changes.
            base_file.write_text("base v2", encoding="utf-8")
            _call_write(lf, root, dep_tree=dep_tree, cache=cache)

            result = json.loads(io.read_template(lf))
            frag = next(
                f for f in result["entries"][0]["fragments"]
                if f.get("resolved_from") == "user-module-fragment"
            )
            self.assertEqual(len(frag["lineage"]), 1)
            self.assertEqual(frag["lineage"][0]["base_hash"], base_hash_v1)
            self.assertEqual(frag["lineage"][0]["override_hash"], override_hash)


# ---------------------------------------------------------------------------
# TestLineageTomlVariables (Task 5: AC 3)
# ---------------------------------------------------------------------------

class TestLineageTomlVariables(unittest.TestCase):

    def _make_toml_scope(self, defaults_val: str, user_val: str) -> VariableScope:
        return VariableScope.build(
            toml_layers=[
                ("defaults", {"agent": {"name": defaults_val}}),
                ("user", {"agent": {"name": user_val}}),
            ]
        )

    def test_toml_variable_lineage_initial_compile(self) -> None:
        """AC 3: user-layer variable has base_value_hash + lineage=[] on first compile."""
        scope = self._make_toml_scope("DefaultPM", "MyPM")
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            _call_write(lf, root, var_scope=scope)
            data = json.loads(io.read_template(lf))
            var = next(
                v for v in data["entries"][0]["variables"]
                if v["name"] == "self.agent.name"
            )
            self.assertIn("base_value_hash", var)
            self.assertEqual(var["base_value_hash"], io.hash_text("DefaultPM"))
            self.assertIn("lineage", var)
            self.assertEqual(var["lineage"], [])

    def test_toml_variable_lineage_appended(self) -> None:
        """AC 3: upgrading defaults value appends one variable lineage entry."""
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            scope_v1 = self._make_toml_scope("DefaultPM", "MyPM")
            old_bvh = io.hash_text("DefaultPM")
            old_override_hash = scope_v1._table["self.agent.name"].value_hash

            _call_write(lf, root, var_scope=scope_v1)

            scope_v2 = self._make_toml_scope("NewDefaultPM", "MyPM")
            _call_write(lf, root, var_scope=scope_v2)

            data = json.loads(io.read_template(lf))
            var = next(
                v for v in data["entries"][0]["variables"]
                if v["name"] == "self.agent.name"
            )
            self.assertEqual(len(var["lineage"]), 1)
            entry = var["lineage"][0]
            self.assertEqual(entry["base_value_hash"], old_bvh)
            self.assertEqual(entry["bmad_version"], "1.0.0")
            self.assertEqual(entry["override_value_hash"], old_override_hash)

    def test_toml_no_user_override_no_lineage(self) -> None:
        """AC 3: defaults-only variable must NOT have a lineage key."""
        scope = VariableScope.build(
            toml_layers=[("defaults", {"agent": {"name": "DefaultPM"}})]
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            _call_write(lf, root, var_scope=scope)
            data = json.loads(io.read_template(lf))
            var = next(
                v for v in data["entries"][0]["variables"]
                if v["name"] == "self.agent.name"
            )
            self.assertNotIn("lineage", var)
            self.assertNotIn("base_value_hash", var)

    def test_toml_variable_lineage_resolver_base_value_hash(self) -> None:
        """Task 0.3: ResolvedValue.base_value_hash populated by VariableScope.build()."""
        scope = self._make_toml_scope("DefaultPM", "MyPM")
        rv = scope._table["self.agent.name"]
        self.assertEqual(rv.value, "MyPM")
        self.assertEqual(rv.toml_layer, "user")
        self.assertIsNotNone(rv.base_value_hash)
        self.assertEqual(rv.base_value_hash, io.hash_text("DefaultPM"))

        # Defaults-only variable: base_value_hash must be None.
        scope_def = VariableScope.build(
            toml_layers=[("defaults", {"agent": {"name": "DefaultPM"}})]
        )
        rv_def = scope_def._table["self.agent.name"]
        self.assertEqual(rv_def.toml_layer, "defaults")
        self.assertIsNone(rv_def.base_value_hash)


# ---------------------------------------------------------------------------
# TestLineageLargeAndDeterministic (Task 6: AC 4)
# ---------------------------------------------------------------------------

class TestLineageLargeAndDeterministic(unittest.TestCase):

    def test_large_lineage_preserved(self) -> None:
        """AC 4: 10 pre-existing lineage entries preserved on no-op recompile."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            dep_tree, cache, base_file, _ = _make_override_fixture(
                t, root, "base current", "override"
            )
            base_hash_current = io.hash_text("base current")
            override_hash = io.hash_text("override")

            # Compile once to establish the correct lockfile path format.
            _call_write(lf, root, dep_tree=dep_tree, cache=cache)
            data = json.loads(io.read_template(lf))
            # Find the override fragment path as written by lockfile.
            frag_path = next(
                f["path"] for f in data["entries"][0]["fragments"]
                if f.get("resolved_from") == "user-module-fragment"
            )

            # Seed 10 pre-existing lineage entries into the lockfile.
            pre_lineage = [
                {"base_hash": f"hash_v{i}", "bmad_version": "1.0.0", "override_hash": override_hash}
                for i in range(10)
            ]
            for f in data["entries"][0]["fragments"]:
                if f.get("resolved_from") == "user-module-fragment":
                    f["lineage"] = pre_lineage
            Path(lf).write_text(json.dumps(data), encoding="utf-8")

            # No-op recompile (base unchanged).
            _call_write(lf, root, dep_tree=dep_tree, cache=cache)

            result = json.loads(io.read_template(lf))
            frag = next(
                f for f in result["entries"][0]["fragments"]
                if f.get("resolved_from") == "user-module-fragment"
            )
            self.assertEqual(len(frag["lineage"]), 10)
            self.assertEqual(frag["lineage"][0]["base_hash"], "hash_v0")
            self.assertEqual(frag["lineage"][9]["base_hash"], "hash_v9")

    def test_lineage_deterministic_ordering(self) -> None:
        """AC 4: chronological order — lineage[0] older base_hash than lineage[1]."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            dep_tree, cache, base_file, _ = _make_override_fixture(
                t, root, "base v1", "override"
            )
            bh1 = io.hash_text("base v1")

            _call_write(lf, root, dep_tree=dep_tree, cache=cache)

            base_file.write_text("base v2", encoding="utf-8")
            _call_write(lf, root, dep_tree=dep_tree, cache=cache)
            bh2 = io.hash_text("base v2")

            base_file.write_text("base v3", encoding="utf-8")
            _call_write(lf, root, dep_tree=dep_tree, cache=cache)

            data = json.loads(io.read_template(lf))
            frag = next(
                f for f in data["entries"][0]["fragments"]
                if f.get("resolved_from") == "user-module-fragment"
            )
            self.assertEqual(len(frag["lineage"]), 2)
            self.assertEqual(frag["lineage"][0]["base_hash"], bh1)
            self.assertEqual(frag["lineage"][1]["base_hash"], bh2)


# ---------------------------------------------------------------------------
# TestLineageReconstruction (Task 7: AC 5)
# ---------------------------------------------------------------------------

class TestLineageReconstruction(unittest.TestCase):

    def test_reconstruction_byte_identical(self) -> None:
        """AC 5: reconstruct_state_before_upgrade produces byte-identical snapshots."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            dep_tree, cache, base_file, _ = _make_override_fixture(
                t, root, "base v1", "override"
            )

            _call_write(lf, root, dep_tree=dep_tree, cache=cache)
            snapshot_0 = json.loads(io.read_template(lf))

            base_file.write_text("base v2", encoding="utf-8")
            _call_write(lf, root, dep_tree=dep_tree, cache=cache)
            snapshot_1 = json.loads(io.read_template(lf))

            base_file.write_text("base v3", encoding="utf-8")
            _call_write(lf, root, dep_tree=dep_tree, cache=cache)
            snapshot_2 = json.loads(io.read_template(lf))

            self.assertEqual(
                _serialize_lockfile(_reconstruct(snapshot_2, 1)),
                _serialize_lockfile(snapshot_1),
            )
            self.assertEqual(
                _serialize_lockfile(_reconstruct(snapshot_2, 2)),
                _serialize_lockfile(snapshot_0),
            )

    def test_tampered_lineage_fails_reconstruction(self) -> None:
        """AC 5: tampered override_hash in lineage yields different reconstruction output."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            dep_tree, cache, base_file, _ = _make_override_fixture(
                t, root, "base v1", "override"
            )

            _call_write(lf, root, dep_tree=dep_tree, cache=cache)
            snapshot_0 = json.loads(io.read_template(lf))

            base_file.write_text("base v2", encoding="utf-8")
            _call_write(lf, root, dep_tree=dep_tree, cache=cache)
            snapshot_1 = json.loads(io.read_template(lf))

            # Tamper: corrupt the override_hash in the single lineage entry.
            for f in snapshot_1["entries"][0]["fragments"]:
                if f.get("resolved_from") == "user-module-fragment":
                    f["lineage"][0]["override_hash"] = "tampered_value"

            reconstructed = _reconstruct(snapshot_1, 1)
            self.assertNotEqual(
                _serialize_lockfile(reconstructed),
                _serialize_lockfile(snapshot_0),
            )

    def test_toml_variable_lineage_history(self) -> None:
        """Task 7.3: after 2 defaults upgrades, variable lineage holds 2 entries."""
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")

            bvh_d1 = io.hash_text("DefaultPM")
            bvh_d2 = io.hash_text("NewDefaultPM")
            user_val_hash = io.hash_text("MyPM")

            scope_v1 = VariableScope.build(
                toml_layers=[
                    ("defaults", {"agent": {"name": "DefaultPM"}}),
                    ("user", {"agent": {"name": "MyPM"}}),
                ]
            )
            scope_v2 = VariableScope.build(
                toml_layers=[
                    ("defaults", {"agent": {"name": "NewDefaultPM"}}),
                    ("user", {"agent": {"name": "MyPM"}}),
                ]
            )
            scope_v3 = VariableScope.build(
                toml_layers=[
                    ("defaults", {"agent": {"name": "FinalDefaultPM"}}),
                    ("user", {"agent": {"name": "MyPM"}}),
                ]
            )

            _call_write(lf, root, var_scope=scope_v1)
            _call_write(lf, root, var_scope=scope_v2)
            _call_write(lf, root, var_scope=scope_v3)

            data = json.loads(io.read_template(lf))
            var = next(
                v for v in data["entries"][0]["variables"]
                if v["name"] == "self.agent.name"
            )
            self.assertEqual(len(var["lineage"]), 2)
            self.assertEqual(var["lineage"][0]["base_value_hash"], bvh_d1)
            self.assertEqual(var["lineage"][0]["override_value_hash"], user_val_hash)
            self.assertEqual(var["lineage"][1]["base_value_hash"], bvh_d2)
            self.assertEqual(var["lineage"][1]["override_value_hash"], user_val_hash)
            self.assertEqual(var["base_value_hash"], io.hash_text("FinalDefaultPM"))


# ---------------------------------------------------------------------------
# TestTeamLayerLineage (Task 6: Tests 1.1, 1.2)
# ---------------------------------------------------------------------------

class TestTeamLayerLineage(unittest.TestCase):

    def test_team_layer_variable_gets_lineage_initialized(self) -> None:
        """Test 1.1: team-layer variable gets base_value_hash + lineage: [] on first compile."""
        scope = VariableScope.build(
            toml_layers=[
                ("defaults", {"agent": {"name": "DefaultPM"}}),
                ("team", {"agent": {"name": "TeamPM"}}),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            _call_write(lf, root, var_scope=scope)
            data = json.loads(io.read_template(lf))
            var = next(v for v in data["entries"][0]["variables"] if v["name"] == "self.agent.name")
            self.assertIn("base_value_hash", var)
            self.assertEqual(var["base_value_hash"], io.hash_text("DefaultPM"))
            self.assertIn("lineage", var)
            self.assertEqual(var["lineage"], [])

    def test_team_layer_lineage_carry_forward_on_defaults_change(self) -> None:
        """Test 1.2: two compiles with different defaults hashes; lineage entry appended."""
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            scope_v1 = VariableScope.build(
                toml_layers=[
                    ("defaults", {"agent": {"name": "DefaultPM"}}),
                    ("team", {"agent": {"name": "TeamPM"}}),
                ]
            )
            old_bvh = io.hash_text("DefaultPM")
            old_override_hash = scope_v1._table["self.agent.name"].value_hash
            _call_write(lf, root, var_scope=scope_v1)

            scope_v2 = VariableScope.build(
                toml_layers=[
                    ("defaults", {"agent": {"name": "NewDefaultPM"}}),
                    ("team", {"agent": {"name": "TeamPM"}}),
                ]
            )
            _call_write(lf, root, var_scope=scope_v2)

            data = json.loads(io.read_template(lf))
            var = next(v for v in data["entries"][0]["variables"] if v["name"] == "self.agent.name")
            self.assertEqual(len(var["lineage"]), 1)
            entry = var["lineage"][0]
            self.assertEqual(entry["base_value_hash"], old_bvh)
            self.assertEqual(entry["bmad_version"], "1.0.0")
            self.assertEqual(entry["override_value_hash"], old_override_hash)


# ---------------------------------------------------------------------------
# TestDormantLineageCarryForward (Task 7: Tests 2.1–2.5)
# ---------------------------------------------------------------------------

class TestDormantLineageCarryForward(unittest.TestCase):

    def _user_scope(self, defaults_val: str, user_val: str) -> VariableScope:
        return VariableScope.build(
            toml_layers=[
                ("defaults", {"agent": {"name": defaults_val}}),
                ("user", {"agent": {"name": user_val}}),
            ]
        )

    def _defaults_scope(self, defaults_val: str) -> VariableScope:
        return VariableScope.build(
            toml_layers=[("defaults", {"agent": {"name": defaults_val}})]
        )

    def test_override_removal_preserves_dormant_lineage(self) -> None:
        """Test 2.1: user removes override; variable reverts to defaults-only; lineage still present."""
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            _call_write(lf, root, var_scope=self._user_scope("DefaultPM", "MyPM"))
            _call_write(lf, root, var_scope=self._defaults_scope("DefaultPM"))
            data = json.loads(io.read_template(lf))
            var = next(v for v in data["entries"][0]["variables"] if v["name"] == "self.agent.name")
            self.assertIn("lineage", var)
            self.assertEqual(var["lineage"], [])

    def test_dormant_lineage_survives_second_compile(self) -> None:
        """Test 2.2: two compiles after override removal; lineage still present after both."""
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            _call_write(lf, root, var_scope=self._user_scope("DefaultPM", "MyPM"))
            scope_def = self._defaults_scope("DefaultPM")
            _call_write(lf, root, var_scope=scope_def)
            _call_write(lf, root, var_scope=scope_def)
            data = json.loads(io.read_template(lf))
            var = next(v for v in data["entries"][0]["variables"] if v["name"] == "self.agent.name")
            self.assertIn("lineage", var)

    def test_override_removal_then_restore_correct_lineage(self) -> None:
        """Test 2.3: BH-R2-2 — defaults change, then remove override, then re-add; no {base_value_hash: null} entry."""
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            # Compile 1: user override with D1
            _call_write(lf, root, var_scope=self._user_scope("DefaultPM", "MyPM"))
            # Compile 2: defaults change to D2, override still present
            _call_write(lf, root, var_scope=self._user_scope("NewDefaultPM", "MyPM"))
            # Compile 3: override removed — dormant entry carries lineage + preserves base_value_hash
            _call_write(lf, root, var_scope=self._defaults_scope("NewDefaultPM"))
            # Compile 4: override restored — must NOT produce {base_value_hash: null}
            _call_write(lf, root, var_scope=self._user_scope("NewDefaultPM", "MyPM"))
            data = json.loads(io.read_template(lf))
            var = next(v for v in data["entries"][0]["variables"] if v["name"] == "self.agent.name")
            self.assertGreaterEqual(
                len(var.get("lineage", [])), 1,
                "lineage should have at least one entry from the defaults upgrade in compile 2",
            )
            for entry in var.get("lineage", []):
                self.assertIsNotNone(
                    entry.get("base_value_hash"),
                    "spurious {base_value_hash: null} entry found in lineage",
                )

    def test_variable_with_no_prior_lineage_not_affected(self) -> None:
        """Test 2.4: non-TOML variable (no prior lineage); no lineage key after second pass."""
        table = {
            "myvar": ResolvedValue(
                value="val", source="bmad-config", value_hash=io.hash_text("val")
            ),
        }
        scope = VariableScope(table)
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            _call_write(lf, root, var_scope=scope)
            _call_write(lf, root, var_scope=scope)
            data = json.loads(io.read_template(lf))
            var = next(v for v in data["entries"][0]["variables"] if v["name"] == "myvar")
            self.assertNotIn("lineage", var)

    def test_toml_to_non_toml_transition_preserves_dormant_lineage(self) -> None:
        """Test 2.5: variable was user-TOML (has lineage), source changes to non-TOML; dormant lineage carried forward."""
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            # Compile 1: user-TOML override
            _call_write(lf, root, var_scope=self._user_scope("DefaultPM", "MyPM"))
            # Compile 2: source switches to bmad-config (non-TOML)
            non_toml_scope = VariableScope({"self.agent.name": ResolvedValue(
                value="MyPM", source="bmad-config", value_hash=io.hash_text("MyPM")
            )})
            _call_write(lf, root, var_scope=non_toml_scope)
            data = json.loads(io.read_template(lf))
            var = next(v for v in data["entries"][0]["variables"] if v["name"] == "self.agent.name")
            self.assertIn("lineage", var)


# ---------------------------------------------------------------------------
# TestMigrationSuppression (Task 8: Tests 3.1–3.3)
# ---------------------------------------------------------------------------

class TestMigrationSuppression(unittest.TestCase):

    def _user_scope(self, defaults_val: str, user_val: str) -> VariableScope:
        return VariableScope.build(
            toml_layers=[
                ("defaults", {"agent": {"name": defaults_val}}),
                ("user", {"agent": {"name": user_val}}),
            ]
        )

    def _strip_lineage_fields(self, lf: str) -> None:
        """Strip base_value_hash + lineage from all variable entries (simulate pre-5.3 lockfile)."""
        data = json.loads(Path(lf).read_text(encoding="utf-8"))
        for e in data["entries"]:
            for v in e.get("variables", []):
                v.pop("base_value_hash", None)
                v.pop("lineage", None)
        Path(lf).write_text(json.dumps(data), encoding="utf-8")

    def test_pre_53_lockfile_no_base_value_hash_no_spurious_entry(self) -> None:
        """Test 3.1: first compile against pre-5.3 entry (no base_value_hash, no lineage); lineage: []."""
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            scope = self._user_scope("DefaultPM", "MyPM")
            _call_write(lf, root, var_scope=scope)
            self._strip_lineage_fields(lf)
            _call_write(lf, root, var_scope=scope)
            result = json.loads(io.read_template(lf))
            var = next(v for v in result["entries"][0]["variables"] if v["name"] == "self.agent.name")
            self.assertEqual(var["lineage"], [], "expected clean start, not spurious null entry")

    def test_pre_53_with_changed_defaults_gets_clean_start(self) -> None:
        """Test 3.2: pre-5.3 entry + changed defaults; lineage: [] (migration suppressed)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            _call_write(lf, root, var_scope=self._user_scope("DefaultPM", "MyPM"))
            self._strip_lineage_fields(lf)
            _call_write(lf, root, var_scope=self._user_scope("DifferentDefaultPM", "MyPM"))
            result = json.loads(io.read_template(lf))
            var = next(v for v in result["entries"][0]["variables"] if v["name"] == "self.agent.name")
            self.assertEqual(var["lineage"], [], "migration suppressed even when defaults changed")

    def test_guard_does_not_fire_when_old_lin_nonempty(self) -> None:
        """Test 3.3: _old_bvh is None but _old_var_lin non-empty; lineage entry IS appended."""
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            scope = self._user_scope("DefaultPM", "MyPM")
            _call_write(lf, root, var_scope=scope)
            # Manually set base_value_hash=absent but lineage=[{...}] non-empty
            data = json.loads(Path(lf).read_text(encoding="utf-8"))
            for e in data["entries"]:
                for v in e.get("variables", []):
                    if v["name"] == "self.agent.name":
                        v.pop("base_value_hash", None)
                        v["lineage"] = [{"base_value_hash": None, "bmad_version": "1.0.0", "override_value_hash": "abc"}]
            Path(lf).write_text(json.dumps(data), encoding="utf-8")
            # Recompile with changed defaults — bvh comparison fires
            _call_write(lf, root, var_scope=self._user_scope("DifferentDefaultPM", "MyPM"))
            result = json.loads(io.read_template(lf))
            var = next(v for v in result["entries"][0]["variables"] if v["name"] == "self.agent.name")
            # Guard did NOT fire — lineage entry appended (now 2 entries)
            self.assertEqual(len(var["lineage"]), 2)


# ---------------------------------------------------------------------------
# TestVariableLineageReconstruction (Task 9: Tests 4.1–4.4)
# ---------------------------------------------------------------------------

class TestVariableLineageReconstruction(unittest.TestCase):

    def _make_scope(self, defaults_val: str, user_val: str) -> VariableScope:
        return VariableScope.build(
            toml_layers=[
                ("defaults", {"agent": {"name": defaults_val}}),
                ("user", {"agent": {"name": user_val}}),
            ]
        )

    def test_reconstruct_variable_lineage_3_compile(self) -> None:
        """Test 4.1: 3 compiles with changing defaults; _reconstruct(data, n=1) restores to 2-compile state."""
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            scope1 = self._make_scope("D1", "U1")
            scope2 = self._make_scope("D2", "U1")
            scope3 = self._make_scope("D3", "U1")

            _call_write(lf, root, var_scope=scope1)
            snapshot1 = json.loads(io.read_template(lf))
            _call_write(lf, root, var_scope=scope2)
            snapshot2 = json.loads(io.read_template(lf))
            _call_write(lf, root, var_scope=scope3)
            snapshot3 = json.loads(io.read_template(lf))

            self.assertEqual(
                _serialize_lockfile(_reconstruct(snapshot3, 1)),
                _serialize_lockfile(snapshot2),
            )
            self.assertEqual(
                _serialize_lockfile(_reconstruct(snapshot3, 2)),
                _serialize_lockfile(snapshot1),
            )

    def test_reconstruct_skips_dormant_variables(self) -> None:
        """Test 4.2: dormant variable (toml_layer='defaults') with non-empty lineage is skipped by _reconstruct."""
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            # Compile 1: user override active — lineage: []
            _call_write(lf, root, var_scope=self._make_scope("D1", "U1"))
            # Compile 2: defaults change — lineage accumulates 1 entry while override is active
            _call_write(lf, root, var_scope=self._make_scope("D2", "U1"))
            # Compile 3: override removed — dormant with toml_layer="defaults" and non-empty lineage
            _call_write(lf, root, var_scope=VariableScope.build(
                toml_layers=[("defaults", {"agent": {"name": "D2"}})]
            ))
            data = json.loads(io.read_template(lf))
            original_var = next(
                v for v in data["entries"][0]["variables"] if v["name"] == "self.agent.name"
            )
            # Verify the dormant state: toml_layer="defaults" and non-empty lineage
            self.assertEqual(original_var.get("toml_layer"), "defaults")
            self.assertGreater(len(original_var.get("lineage", [])), 0)
            original_lineage = list(original_var.get("lineage", []))
            original_value_hash = original_var.get("value_hash")

            rewound = _reconstruct(data, 1)
            rvar = next(v for v in rewound["entries"][0]["variables"] if v["name"] == "self.agent.name")
            # _reconstruct skipped it via toml_layer guard — lineage and value_hash unchanged
            self.assertEqual(rvar.get("lineage"), original_lineage)
            self.assertEqual(rvar.get("value_hash"), original_value_hash)

    def test_reconstruct_skips_empty_lineage(self) -> None:
        """Test 4.3: variable with lineage: []; _reconstruct leaves it unmodified (no IndexError)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            _call_write(lf, root, var_scope=self._make_scope("DefaultPM", "MyPM"))
            data = json.loads(io.read_template(lf))
            var_before = next(v for v in data["entries"][0]["variables"] if v["name"] == "self.agent.name")
            self.assertEqual(var_before["lineage"], [])
            original_bvh = var_before["base_value_hash"]
            original_vh = var_before["value_hash"]

            # Must not raise IndexError
            rewound = _reconstruct(data, 1)
            rvar = next(v for v in rewound["entries"][0]["variables"] if v["name"] == "self.agent.name")
            self.assertEqual(rvar["base_value_hash"], original_bvh)
            self.assertEqual(rvar["value_hash"], original_vh)
            self.assertEqual(rvar["lineage"], [])

    def test_reconstruct_n2_rewinds_two_generations(self) -> None:
        """Test 4.4: 3 compiles; _reconstruct(data, n=2) restores to 1-compile state."""
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            lf = str(root / "bmad.lock")
            scope1 = self._make_scope("D1", "U1")
            scope2 = self._make_scope("D2", "U1")
            scope3 = self._make_scope("D3", "U1")

            _call_write(lf, root, var_scope=scope1)
            snapshot1 = json.loads(io.read_template(lf))
            _call_write(lf, root, var_scope=scope2)
            _call_write(lf, root, var_scope=scope3)
            snapshot3 = json.loads(io.read_template(lf))

            self.assertEqual(
                _serialize_lockfile(_reconstruct(snapshot3, 2)),
                _serialize_lockfile(snapshot1),
            )


if __name__ == "__main__":
    unittest.main()
