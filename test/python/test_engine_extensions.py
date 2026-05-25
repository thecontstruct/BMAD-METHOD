"""Story 10.25 + 10.26: FR-3 multi-artifact emit + lockfile v3 tests.

Tests:
- AC-1b: _extract_artifacts_from_frontmatter — regression guard
- AC-5: path traversal / absolute path / unknown kind rejection
- AC-6: integration tests (basic emit + lockfile records)
- Lockfile v2→v3 migration
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Add src/scripts to sys.path so component_runner.py's absolute imports resolve.
# Pattern established by test_epic8_story85.py.
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_SCRIPTS = str(_PROJECT_ROOT / "src" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from bmad_compile import engine, errors, io, lockfile, resolver
from bmad_compile.component_runner import MockComponentRunner
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


if __name__ == "__main__":
    unittest.main()
