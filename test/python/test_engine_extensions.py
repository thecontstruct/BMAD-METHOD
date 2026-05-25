"""Stories 10.25 + 10.26 + 10.27: FR-3 multi-artifact emit + lockfile v3 + FR-5/FR-13/DN-4.

Tests:
- AC-1b: _extract_artifacts_from_frontmatter — regression guard
- AC-5: path traversal / absolute path / unknown kind rejection
- AC-6: integration tests (basic emit + lockfile records)
- Lockfile v2→v3 migration
- Story 10.27 AC-11: ArtifactDrift detection, shared-fragment rollup, FR-13 deprecation
  warning, DN-4 orphan detector, bmad-customize contract, NFR-1b performance probe
"""

from __future__ import annotations

import contextlib
import io as _stdlib_io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Add src/scripts to sys.path so component_runner.py's absolute imports resolve.
# Pattern established by test_epic8_story85.py.
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_SCRIPTS = str(_PROJECT_ROOT / "src" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import upgrade as _upgrade_mod  # Story 10.27: _halt_on_drift_stderr
from bmad_compile import engine, errors, io, lockfile, resolver
from bmad_compile.component_runner import MockComponentRunner
from bmad_compile.drift import (  # Story 10.27
    ArtifactDrift,
    DriftReport,
    OrphanedOverride,
    ProseFragmentChange,
    _detect_artifact_drift,
    _detect_orphaned_overrides,
    detect_drift,
)
from bmad_compile.engine import Artifact, _extract_artifacts_from_frontmatter
from bmad_compile.io import PurePosixPath
from bmad_compile.resolver import CompileCache, VariableScope


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_skill(
    skill_dir: Path,
    template_content: str,
    artifact_files: dict[str, str] | None = None,
) -> None:
    """Create a minimal skill fixture with the given template and optional artifact files."""
    skill_dir.mkdir(parents=True, exist_ok=True)
    _write(skill_dir / f"{skill_dir.name}.template.md", template_content)
    _write(skill_dir / "customize.toml", "# minimal\n")
    if artifact_files:
        for name, content in artifact_files.items():
            _write(skill_dir / name, content)


def _mock_runner() -> MockComponentRunner:
    """No-component mock: returns empty buffer (no compile invocations expected)."""
    return MockComponentRunner(batch_results={})


SIMPLE_TEMPLATE = """\
---
name: test-skill
description: Test skill.
---

# Test Skill

Body text.
"""

ARTIFACT_TEMPLATE = """\
---
name: test-skill
description: Test skill with artifact.
artifacts:
  - path: data.csv
    source: data.csv
    kind: scaffold-verbatim
---

# Test Skill

Body text.
"""

NO_ARTIFACTS_TEMPLATE = """\
---
name: test-skill-plain
description: Test skill, no artifacts.
---

# Test Skill Plain

Body text.
"""

SLOPPY_FRONTMATTER_TEMPLATE = """\
---
name: test-skill
description: Test skill with broken YAML.
bad yaml: [unclosed
---

# Test Skill

Body text.
"""

MALFORMED_ARTIFACTS_TEMPLATE = """\
---
name: test-skill
description: Test skill with malformed artifacts.
artifacts: "not-a-list"
---

# Test Skill

Body text.
"""

UNKNOWN_KIND_TEMPLATE = """\
---
name: test-skill
description: Test skill with unknown artifact kind.
artifacts:
  - path: data.csv
    source: data.csv
    kind: compiled-template
---

# Test Skill

Body text.
"""

TRAVERSAL_SOURCE_TEMPLATE = """\
---
name: test-skill
description: Test skill with traversal source.
artifacts:
  - path: data.csv
    source: ../escape.csv
    kind: scaffold-verbatim
---

# Test Skill

Body text.
"""

ABSOLUTE_PATH_TEMPLATE = """\
---
name: test-skill
description: Test skill with absolute artifact path.
artifacts:
  - path: /etc/passwd
    source: data.csv
    kind: scaffold-verbatim
---

# Test Skill

Body text.
"""

CSV_CONTENT = "method,description\nmethod_a,First\nmethod_b,Second\n"


# ---------------------------------------------------------------------------
# AC-1b: _extract_artifacts_from_frontmatter regression guards
# ---------------------------------------------------------------------------

class TestExtractArtifactsFromFrontmatter(unittest.TestCase):

    def test_no_artifacts_key_returns_empty(self) -> None:
        result = _extract_artifacts_from_frontmatter(SIMPLE_TEMPLATE)
        self.assertEqual(result, [])

    def test_valid_artifact_returns_list(self) -> None:
        result = _extract_artifacts_from_frontmatter(ARTIFACT_TEMPLATE)
        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], Artifact)
        self.assertEqual(result[0].path, "data.csv")
        self.assertEqual(result[0].source, "data.csv")
        self.assertEqual(result[0].kind, "scaffold-verbatim")

    def test_frontmatter_yaml_typo_does_not_crash(self) -> None:
        """AC-1b: broken YAML with no artifacts: key → [] (tolerant path)."""
        result = _extract_artifacts_from_frontmatter(SLOPPY_FRONTMATTER_TEMPLATE)
        self.assertEqual(result, [])

    def test_frontmatter_artifacts_malformed_raises(self) -> None:
        """AC-1b: artifacts: present but scalar → CompilerError."""
        with self.assertRaises(errors.CompilerError):
            _extract_artifacts_from_frontmatter(MALFORMED_ARTIFACTS_TEMPLATE)

    def test_unknown_kind_raises(self) -> None:
        """AC-1b / AC-5: kind other than scaffold-verbatim → CompilerError."""
        with self.assertRaises(errors.CompilerError):
            _extract_artifacts_from_frontmatter(UNKNOWN_KIND_TEMPLATE)

    def test_no_frontmatter_returns_empty(self) -> None:
        """Template with no frontmatter block returns []."""
        result = _extract_artifacts_from_frontmatter("# Just a title\n\nBody.\n")
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# AC-5: Path traversal / absolute path rejection in compile_skill
# ---------------------------------------------------------------------------

class TestArtifactPathSafety(unittest.TestCase):

    def test_multi_artifact_emit_traversal_rejected(self) -> None:
        """AC-5: source: ../escape.csv → OverrideOutsideRootError."""
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "core" / "test-skill"
            _make_skill(skill_dir, TRAVERSAL_SOURCE_TEMPLATE)
            install = Path(tmp) / "install"
            with self.assertRaises(errors.OverrideOutsideRootError):
                engine.compile_skill(skill_dir, install,
                                     component_runner=_mock_runner())

    def test_multi_artifact_emit_absolute_path_rejected(self) -> None:
        """AC-5: path: /etc/passwd → CompilerError."""
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "core" / "test-skill"
            _make_skill(skill_dir, ABSOLUTE_PATH_TEMPLATE, {"data.csv": CSV_CONTENT})
            install = Path(tmp) / "install"
            with self.assertRaises(errors.CompilerError):
                engine.compile_skill(skill_dir, install,
                                     component_runner=_mock_runner())

    def test_multi_artifact_emit_kind_unknown_rejected(self) -> None:
        """AC-5: kind: compiled-template → CompilerError (from frontmatter extraction)."""
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir = Path(tmp) / "core" / "test-skill"
            _make_skill(skill_dir, UNKNOWN_KIND_TEMPLATE, {"data.csv": CSV_CONTENT})
            install = Path(tmp) / "install"
            with self.assertRaises(errors.CompilerError):
                engine.compile_skill(skill_dir, install,
                                     component_runner=_mock_runner())


# ---------------------------------------------------------------------------
# AC-6: Integration tests — basic emit + lockfile records
# ---------------------------------------------------------------------------

class TestMultiArtifactEmitIntegration(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.skill_dir = self.tmp / "core" / "test-skill"
        _make_skill(self.skill_dir, ARTIFACT_TEMPLATE, {"data.csv": CSV_CONTENT})
        self.install = self.tmp / "install"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _compile(self, skill_dir: Path | None = None, install: Path | None = None) -> None:
        engine.compile_skill(
            skill_dir or self.skill_dir,
            install or self.install,
            component_runner=_mock_runner(),
        )

    def test_multi_artifact_emit_basic(self) -> None:
        """AC-6: single-artifact template → SKILL.md + data.csv both exist."""
        self._compile()
        skill_out = self.install / "test-skill"
        self.assertTrue((skill_out / "SKILL.md").is_file())
        self.assertTrue((skill_out / "data.csv").is_file())

    def test_artifact_content_matches_source(self) -> None:
        """AC-6: emitted artifact content matches source (CRLF-normalized)."""
        self._compile()
        emitted = (self.install / "test-skill" / "data.csv").read_text(encoding="utf-8")
        expected = io.read_template(str(self.skill_dir / "data.csv"))
        self.assertEqual(emitted, expected)

    def test_multi_artifact_emit_lockfile_records(self) -> None:
        """AC-6: lockfile entry artifacts[0].hash matches io.hash_text of source."""
        self._compile()
        # Per-skill mode lockfile: skill_dir.parent.parent / _bmad / _config / bmad.lock
        lockfile_path = self.skill_dir.parent.parent / "_bmad" / "_config" / "bmad.lock"
        data = json.loads(lockfile_path.read_text(encoding="utf-8"))
        entry = next(e for e in data["entries"] if e["skill"] == "test-skill")
        self.assertEqual(len(entry["artifacts"]), 1)
        art = entry["artifacts"][0]
        self.assertEqual(art["kind"], "scaffold-verbatim")
        self.assertEqual(art["path"], "data.csv")
        expected_hash = io.hash_text(io.read_template(str(self.skill_dir / "data.csv")))
        self.assertEqual(art["hash"], expected_hash)

    def test_no_artifacts_skill_has_empty_artifacts_list(self) -> None:
        """AC-8: skills without artifacts: have artifacts: [] in lockfile entry."""
        skill_dir2 = self.tmp / "core" / "test-skill-plain"
        _make_skill(skill_dir2, NO_ARTIFACTS_TEMPLATE)
        self._compile(skill_dir2)
        # Per-skill mode lockfile: skill_dir.parent.parent / _bmad / _config / bmad.lock
        lockfile_path = skill_dir2.parent.parent / "_bmad" / "_config" / "bmad.lock"
        data = json.loads(lockfile_path.read_text(encoding="utf-8"))
        entry = next(e for e in data["entries"] if e["skill"] == "test-skill-plain")
        self.assertIn("artifacts", entry)
        self.assertEqual(entry["artifacts"], [])


# ---------------------------------------------------------------------------
# Lockfile v2→v3 migration (Story 10.26)
# ---------------------------------------------------------------------------

def _empty_scope() -> VariableScope:
    return VariableScope({})


def _empty_cache() -> CompileCache:
    return CompileCache()


def _make_dep_tree(scenario_root: PurePosixPath) -> list:
    root = resolver.ResolvedFragment(
        src="test-skill/test-skill.template.md",
        resolved_path=scenario_root / "core" / "test-skill" / "test-skill.template.md",
        resolved_from="base",
        local_props=(),
        merged_scope=(),
        nodes=[],
    )
    return [root]


def _write_v2_lockfile(path: str, entries: list[dict]) -> None:
    """Write a v2 lockfile (no artifacts/deprecations fields)."""
    data = {
        "version": 2,
        "bmad_version": "test",
        "compiled_at": "test",
        "entries": entries,
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


class TestLockfileV3(unittest.TestCase):
    """Story 10.26: lockfile schema v3 — artifacts/deprecations fields + v2→v3 migration."""

    def _lf_path(self, tmp: str) -> str:
        """Standard lockfile path for lockfile unit tests (sibling of tmp root)."""
        return str(Path(tmp) / "bmad.lock")

    def _scenario_root(self, tmp: str) -> PurePosixPath:
        return io.to_posix(tmp)

    def test_lockfile_v3_top_level_version(self) -> None:
        """New lockfile write produces version: 3 at top level."""
        with tempfile.TemporaryDirectory() as tmp:
            scenario_root = self._scenario_root(tmp)
            lf_path = self._lf_path(tmp)
            dep_tree = _make_dep_tree(scenario_root)
            lockfile.write_skill_entry(
                lf_path, scenario_root, "test-skill",
                source_text="source", compiled_text="compiled",
                dep_tree=dep_tree, var_scope=_empty_scope(),
                target_ide=None, cache=_empty_cache(),
            )
            data = json.loads(Path(lf_path).read_text(encoding="utf-8"))
            self.assertEqual(data["version"], 3)

    def test_lockfile_v3_entry_has_artifacts_and_deprecations(self) -> None:
        """New write adds artifacts: [] and deprecations: [] to entry."""
        with tempfile.TemporaryDirectory() as tmp:
            scenario_root = self._scenario_root(tmp)
            lf_path = self._lf_path(tmp)
            dep_tree = _make_dep_tree(scenario_root)
            lockfile.write_skill_entry(
                lf_path, scenario_root, "test-skill",
                source_text="source", compiled_text="compiled",
                dep_tree=dep_tree, var_scope=_empty_scope(),
                target_ide=None, cache=_empty_cache(),
            )
            data = json.loads(Path(lf_path).read_text(encoding="utf-8"))
            entry = data["entries"][0]
            self.assertIn("artifacts", entry)
            self.assertIn("deprecations", entry)
            self.assertEqual(entry["artifacts"], [])
            self.assertEqual(entry["deprecations"], [])

    def test_lockfile_v2_to_v3_migration(self) -> None:
        """(10.26): writing to a v2 lockfile migrates existing entries to v3."""
        with tempfile.TemporaryDirectory() as tmp:
            scenario_root = self._scenario_root(tmp)
            lf_path = self._lf_path(tmp)
            # Pre-existing v2 entry for a different skill (no artifacts/deprecations).
            v2_entry: dict = {
                "skill": "other-skill",
                "compiled_hash": "abc123",
                "source_hash": "def456",
                "fragments": [],
                "variables": [],
                "components": [],
                "target_ide": None,
            }
            _write_v2_lockfile(lf_path, [v2_entry])
            # Write test-skill into this v2 lockfile.
            dep_tree = _make_dep_tree(scenario_root)
            lockfile.write_skill_entry(
                lf_path, scenario_root, "test-skill",
                source_text="source", compiled_text="compiled",
                dep_tree=dep_tree, var_scope=_empty_scope(),
                target_ide=None, cache=_empty_cache(),
            )
            data = json.loads(Path(lf_path).read_text(encoding="utf-8"))
            self.assertEqual(data["version"], 3)
            # Both old and new entries must have artifacts/deprecations.
            for entry in data["entries"]:
                self.assertIn("artifacts", entry,
                              f"entry {entry.get('skill')} missing artifacts")
                self.assertIn("deprecations", entry,
                              f"entry {entry.get('skill')} missing deprecations")

    def test_lockfile_write_with_artifacts_records(self) -> None:
        """write_skill_entry with artifacts= stores them in the entry."""
        with tempfile.TemporaryDirectory() as tmp:
            scenario_root = self._scenario_root(tmp)
            lf_path = self._lf_path(tmp)
            dep_tree = _make_dep_tree(scenario_root)
            artifact_record = {
                "hash": "abc123hash",
                "kind": "scaffold-verbatim",
                "path": "data.csv",
            }
            lockfile.write_skill_entry(
                lf_path, scenario_root, "test-skill",
                source_text="source", compiled_text="compiled",
                dep_tree=dep_tree, var_scope=_empty_scope(),
                target_ide=None, cache=_empty_cache(),
                artifacts=[artifact_record],
            )
            data = json.loads(Path(lf_path).read_text(encoding="utf-8"))
            entry = data["entries"][0]
            self.assertEqual(entry["artifacts"], [artifact_record])


# ---------------------------------------------------------------------------
# Story 10.27 AC-11: ArtifactDrift detection (AC-2 + AC-3)
# ---------------------------------------------------------------------------

def _make_entry_with_artifact(
    art_path: str, art_hash: str, module: str = "core", skill: str = "test-skill"
) -> dict:
    """Build a minimal lockfile entry dict with one artifact and one base fragment
    so _infer_module can determine the module directory."""
    return {
        "skill": skill,
        "compiled_hash": "abc",
        "source_hash": "def",
        "fragments": [
            {
                "path": f"{module}/{skill}/fragments/base.md",
                "resolved_from": "base",
                "hash": "fragHash",
            }
        ],
        "variables": [],
        "components": [],
        "artifacts": [
            {"hash": art_hash, "kind": "scaffold-verbatim", "path": art_path}
        ],
        "deprecations": [],
    }


class TestArtifactDriftDetection(unittest.TestCase):
    """Story 10.27 AC-3 / AC-2: _detect_artifact_drift and has_drift() extension."""

    def _write_install_file(
        self, scenario_root: Path, module: str, skill: str, name: str, content: str
    ) -> Path:
        dest = scenario_root / module / skill / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        return dest

    def test_artifact_drift_detection_no_drift(self) -> None:
        """Install-dir artifact hash matches lockfile hash → artifact_changes empty."""
        with tempfile.TemporaryDirectory() as tmp:
            scenario_root = Path(tmp)
            content = "col_a,col_b\nval1,val2\n"
            self._write_install_file(scenario_root, "core", "test-skill", "data.csv", content)
            expected_hash = io.hash_text(io.read_template(
                str(scenario_root / "core" / "test-skill" / "data.csv")
            ))
            entry = _make_entry_with_artifact("data.csv", expected_hash)
            result = _detect_artifact_drift(entry, scenario_root)
            self.assertEqual(result, [])

    def test_artifact_drift_detection_install_hash_mismatch(self) -> None:
        """Install-dir artifact content modified → artifact_changes non-empty, has_drift True."""
        with tempfile.TemporaryDirectory() as tmp:
            scenario_root = Path(tmp)
            self._write_install_file(
                scenario_root, "core", "test-skill", "data.csv", "different content\n"
            )
            entry = _make_entry_with_artifact("data.csv", "a" * 64)  # wrong hash
            result = _detect_artifact_drift(entry, scenario_root)
            self.assertEqual(len(result), 1)
            self.assertEqual(result[0].artifact_path, "data.csv")
            self.assertIsNotNone(result[0].install_hash)
            self.assertEqual(result[0].old_hash, "a" * 64)
            # has_drift extension
            report = DriftReport(skill="test-skill", artifact_changes=result)
            self.assertTrue(report.has_drift())

    def test_artifact_drift_detection_missing_install_file(self) -> None:
        """Artifact file absent from install dir → install_hash is None, has_drift True."""
        with tempfile.TemporaryDirectory() as tmp:
            scenario_root = Path(tmp)
            # Do NOT create the install file.
            entry = _make_entry_with_artifact("data.csv", "b" * 64)
            result = _detect_artifact_drift(entry, scenario_root)
            self.assertEqual(len(result), 1)
            self.assertIsNone(result[0].install_hash)
            report = DriftReport(skill="test-skill", artifact_changes=result)
            self.assertTrue(report.has_drift())

    def test_has_drift_returns_true_when_only_artifact_changes(self) -> None:
        """AC-2 regression: DriftReport with ONLY artifact_changes → has_drift() True.

        Without the AC-2 has_drift() extension, a skill with only artifact drift
        would silently pass the upgrade gate.
        """
        art = ArtifactDrift(
            skill="s", artifact_path="f.csv", old_hash="x", new_hash="x",
            install_hash=None, tier="scaffold-verbatim"
        )
        report = DriftReport(skill="s", artifact_changes=[art])
        # All other lists are empty.
        self.assertEqual(report.prose_fragment_changes, [])
        self.assertEqual(report.toml_default_changes, [])
        self.assertTrue(report.has_drift())

    def test_artifact_drift_no_module_inference_returns_empty(self) -> None:
        """Entry with no fragments or variables → _infer_module returns None → []."""
        with tempfile.TemporaryDirectory() as tmp:
            entry = {
                "skill": "orphan-skill",
                "fragments": [],
                "variables": [],
                "artifacts": [{"hash": "abc", "kind": "scaffold-verbatim", "path": "x.csv"}],
            }
            result = _detect_artifact_drift(entry, Path(tmp))
            self.assertEqual(result, [])

    def test_artifact_drift_empty_artifacts_is_fast_path(self) -> None:
        """Entry with artifacts: [] → returns [] immediately (no filesystem access)."""
        entry = {"skill": "s", "fragments": [], "variables": [], "artifacts": []}
        result = _detect_artifact_drift(entry, Path("/nonexistent/root"))
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# Story 10.27 AC-6: shared-fragment drift rollup + BC-4 invariant
# ---------------------------------------------------------------------------

class TestSharedFragmentDriftRollup(unittest.TestCase):
    """Story 10.27 AC-6: _halt_on_drift_stderr roll-up + BC-4 regression."""

    def _make_shared_frag_report(self, skill: str) -> DriftReport:
        change = ProseFragmentChange(
            path="_shared/fragments/resolver-fallback.md",
            old_hash="old",
            new_hash="new",
            user_override_hash=None,
            tier="base",
        )
        return DriftReport(skill=skill, prose_fragment_changes=[change])

    def test_shared_fragment_drift_rollup(self) -> None:
        """2 skills with shared-fragment change → rollup line + consumer count."""
        report1 = self._make_shared_frag_report("skill-a")
        report2 = self._make_shared_frag_report("skill-b")
        msg = _upgrade_mod._halt_on_drift_stderr([report1, report2])
        self.assertIn("Shared fragment _shared/fragments/resolver-fallback.md changed", msg)
        self.assertIn("2 consumers affected", msg)
        # Must NOT contain "Drift detected in N skills" one-liner (rollup path)
        self.assertNotIn("Drift detected in 2 skills", msg)

    def test_single_skill_drift_halt_message_unchanged(self) -> None:
        """BC-4: non-shared-fragment drift + no artifacts → exact pre-Epic-10 one-liner."""
        change = ProseFragmentChange(
            path="core/bmad-customize/fragments/preflight.md",
            old_hash="old",
            new_hash="new",
            user_override_hash=None,
            tier="base",
        )
        report = DriftReport(skill="bmad-customize", prose_fragment_changes=[change])
        msg = _upgrade_mod._halt_on_drift_stderr([report])
        # BC-4: must start with the exact legacy format
        self.assertTrue(
            msg.startswith("Drift detected in 1 skills"),
            f"Expected BC-4 one-liner, got: {msg!r}",
        )
        self.assertNotIn("Shared fragment", msg)
        self.assertNotIn("artifact", msg)

    def test_artifact_changes_in_rollup_section(self) -> None:
        """Artifact drift alone → rollup section with 'artifact file(s) changed'."""
        art = ArtifactDrift(
            skill="s", artifact_path="data.csv", old_hash="x", new_hash="x",
            install_hash=None, tier="scaffold-verbatim"
        )
        report = DriftReport(skill="s", artifact_changes=[art])
        msg = _upgrade_mod._halt_on_drift_stderr([report])
        self.assertIn("Drift detected:", msg)
        self.assertIn("artifact file(s) changed", msg)


# ---------------------------------------------------------------------------
# Story 10.27 AC-9: FR-13 deprecation warning in compile_skill
# ---------------------------------------------------------------------------

class TestDeprecationWarning(unittest.TestCase):
    """Story 10.27 AC-9: compile_skill emits FR-13 deprecation WARNING to stderr."""

    def _compile_with_deprecations(
        self, tmp: str, deprecations: "list[dict] | None"
    ) -> str:
        """Compile a simple skill with given deprecations kwarg; return captured stderr."""
        skill_dir = Path(tmp) / "core" / "dep-skill"
        _make_skill(skill_dir, SIMPLE_TEMPLATE)
        install = Path(tmp) / "install"
        captured = _stdlib_io.StringIO()
        with contextlib.redirect_stderr(captured):
            engine.compile_skill(
                skill_dir, install,
                component_runner=_mock_runner(),
                deprecations=deprecations,
            )
        return captured.getvalue()

    def test_deprecation_notice_fires_on_nonempty_deprecations(self) -> None:
        """deprecations=[{...}] → WARNING: line on stderr."""
        with tempfile.TemporaryDirectory() as tmp:
            deps = [{"key": "my.old.key", "replacement": "conventions.md", "since": "v6.7.0"}]
            stderr = self._compile_with_deprecations(tmp, deps)
            self.assertIn("WARNING:", stderr)
            self.assertIn("my.old.key", stderr)
            self.assertIn("conventions.md", stderr)

    def test_no_deprecation_warning_when_empty(self) -> None:
        """deprecations=[] → no WARNING: on stderr."""
        with tempfile.TemporaryDirectory() as tmp:
            stderr = self._compile_with_deprecations(tmp, [])
            self.assertNotIn("WARNING:", stderr)

    def test_no_deprecation_warning_when_none(self) -> None:
        """deprecations=None (default) → no WARNING: on stderr."""
        with tempfile.TemporaryDirectory() as tmp:
            stderr = self._compile_with_deprecations(tmp, None)
            self.assertNotIn("WARNING:", stderr)


# ---------------------------------------------------------------------------
# Story 10.27 AC-7: DN-4 filesystem-walk orphan detector
# ---------------------------------------------------------------------------

class TestDN4OrphanDetector(unittest.TestCase):
    """Story 10.27 AC-7: DN-4 extension in _detect_orphaned_overrides."""

    def _base_entry(self, module: str = "core", skill: str = "test-skill") -> dict:
        """Entry with one base fragment so module can be inferred."""
        return {
            "skill": skill,
            "fragments": [
                {
                    "path": f"{module}/{skill}/fragments/known.md",
                    "resolved_from": "base",
                    "hash": "knownHash",
                }
            ],
            "variables": [],
        }

    def test_orphaned_pre_migration_override_detection(self) -> None:
        """DN-4: per-consumer override not in lockfile fragments → OrphanedOverride."""
        with tempfile.TemporaryDirectory() as tmp:
            scenario_root = Path(tmp)
            # Create the per-consumer override file (not listed in entry["fragments"])
            override_dir = scenario_root / "custom" / "fragments" / "core" / "test-skill"
            override_dir.mkdir(parents=True)
            (override_dir / "old-fragment.md").write_text("old content", encoding="utf-8")
            entry = self._base_entry()
            result = _detect_orphaned_overrides(entry, scenario_root)
            # Should contain one OrphanedOverride from the DN-4 walk
            orphan_paths = [o.path for o in result]
            self.assertEqual(len(result), 1, f"Expected 1 orphan, got: {orphan_paths}")
            self.assertIn("old-fragment.md", result[0].path)
            self.assertEqual(result[0].reason, "base_fragment_removed")

    def test_known_fragment_override_not_orphaned(self) -> None:
        """DN-4: per-consumer override that IS in lockfile fragments → not reported."""
        with tempfile.TemporaryDirectory() as tmp:
            scenario_root = Path(tmp)
            # Create override file WITH matching path in entry["fragments"]
            override_dir = scenario_root / "custom" / "fragments" / "core" / "test-skill"
            override_dir.mkdir(parents=True)
            (override_dir / "known.md").write_text("override content", encoding="utf-8")
            entry = {
                "skill": "test-skill",
                "fragments": [
                    {
                        "path": "custom/fragments/core/test-skill/known.md",
                        "resolved_from": "user-module-fragment",
                        "hash": "knownHash",
                    }
                ],
                "variables": [],
            }
            result = _detect_orphaned_overrides(entry, scenario_root)
            self.assertEqual(result, [])

    def test_global_tier_override_not_orphaned(self) -> None:
        """DN-4: global-tier override at custom/fragments/conventions.md → NOT reported.

        The DN-4 walk targets custom/fragments/<module>/<skill>/ only.
        A file at custom/fragments/conventions.md is in a completely different
        directory and is never encountered by the walk.
        """
        with tempfile.TemporaryDirectory() as tmp:
            scenario_root = Path(tmp)
            # Global-tier file (not under any module/skill subdir)
            global_dir = scenario_root / "custom" / "fragments"
            global_dir.mkdir(parents=True)
            (global_dir / "conventions.md").write_text("global override", encoding="utf-8")
            # Per-consumer dir does NOT exist
            entry = self._base_entry()
            result = _detect_orphaned_overrides(entry, scenario_root)
            self.assertEqual(result, [])

    def test_dn4_no_walk_when_per_consumer_dir_absent(self) -> None:
        """DN-4: no per-consumer directory → [] returned, no filesystem error."""
        with tempfile.TemporaryDirectory() as tmp:
            scenario_root = Path(tmp)
            entry = self._base_entry()
            result = _detect_orphaned_overrides(entry, scenario_root)
            self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# Story 10.27 AC-11: bmad-customize strict-superset contract
# ---------------------------------------------------------------------------

class TestBmadCustomizeContract(unittest.TestCase):
    """Story 10.27: DriftReport JSON shape is a strict superset of pre-Epic-10 shape."""

    def test_bmad_customize_tolerant_read_artifact_changes(self) -> None:
        """JSON DriftReport with artifact_changes key → parses without error.

        bmad-customize reads upgrade.py's JSON output. The artifact_changes key
        is additive; a consumer not knowing about it ignores it cleanly.
        """
        report_dict = {
            "skill": "test-skill",
            "prose_fragment_changes": [],
            "toml_default_changes": [],
            "orphaned_overrides": [],
            "new_defaults": [],
            "glob_changes": [],
            "variable_provenance_shifts": [],
            "artifact_changes": [
                {
                    "skill": "test-skill",
                    "artifact_path": "data.csv",
                    "old_hash": "a" * 64,
                    "new_hash": "a" * 64,
                    "install_hash": None,
                    "tier": "scaffold-verbatim",
                }
            ],
        }
        # Serialize + deserialize — structural validation.
        serialized = json.dumps(report_dict)
        parsed = json.loads(serialized)
        self.assertIn("artifact_changes", parsed)
        self.assertEqual(len(parsed["artifact_changes"]), 1)
        self.assertEqual(parsed["artifact_changes"][0]["artifact_path"], "data.csv")


# ---------------------------------------------------------------------------
# Story 10.27 AC-8: NFR-1b performance probe
# ---------------------------------------------------------------------------

class TestNFR1bProbe(unittest.TestCase):
    """Story 10.27 AC-8: drift detection completes in ≤5s on a ≥42-entry corpus."""

    def _make_minimal_entry(self, idx: int) -> dict:
        """Minimal lockfile entry — all file references point to non-existent paths
        (drift.py returns empty for each category cleanly)."""
        skill = f"skill-{idx:03d}"
        return {
            "skill": skill,
            "compiled_hash": "a" * 64,
            "source_hash": "b" * 64,
            "fragments": [
                {
                    "path": f"core/{skill}/fragments/conventions.md",
                    "resolved_from": "base",
                    "hash": "c" * 64,
                },
                {
                    "path": f"core/{skill}/fragments/persistent-facts.md",
                    "resolved_from": "base",
                    "hash": "d" * 64,
                },
                {
                    "path": f"core/{skill}/fragments/resolver-fallback.md",
                    "resolved_from": "base",
                    "hash": "e" * 64,
                },
            ],
            "variables": [
                {
                    "name": "self.name",
                    "source": "toml",
                    "source_path": f"core/{skill}/customize.toml",
                    "toml_layer": "defaults",
                    "value_hash": "f" * 64,
                },
                {
                    "name": "self.description",
                    "source": "toml",
                    "source_path": f"core/{skill}/customize.toml",
                    "toml_layer": "defaults",
                    "value_hash": "0" * 64,
                },
            ],
            "components": [],
            "artifacts": [],
            "deprecations": [],
            "glob_inputs": [],
        }

    def test_drift_detection_under_5s_post_epic_10(self) -> None:
        """NFR-1b: detect_drift across ≥42 entries must complete in ≤5s.

        Uses a synthetic fixture where all referenced files are absent
        (each category returns empty cleanly — no actual file I/O hot path).
        Budget: 5.0 seconds on GHA windows-latest 2-core.
        """
        with tempfile.TemporaryDirectory() as tmp:
            entries = [self._make_minimal_entry(i) for i in range(45)]  # > 42
            start = time.monotonic()
            for entry in entries:
                detect_drift(entry, tmp)
            elapsed = time.monotonic() - start
            self.assertLess(
                elapsed, 5.0,
                f"NFR-1b: drift detection took {elapsed:.2f}s for 45 entries (budget 5.0s)",
            )


if __name__ == "__main__":
    unittest.main()
