"""Story 5.1: Tests for `bmad upgrade --dry-run` (drift detection engine + CLI).

16 tests covering all six drift categories, human/JSON output, schema fixture
validation, no-write invariant, and subprocess integration (4.9–4.14).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath

# Locate scripts directory and add to path so imports work in isolation.
_SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "src" / "scripts"
)
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

_UPGRADE_PY = _SCRIPTS_DIR / "upgrade.py"
_SCHEMAS_DIR = _SCRIPTS_DIR / "bmad_compile" / "schemas"

from bmad_compile import io as bmad_io
from bmad_compile.drift import (
    GlobChange,
    NewDefault,
    OrphanedOverride,
    ProseFragmentChange,
    TomlDefaultChange,
    VariableProvenanceShift,
    detect_drift,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_lockfile(project_root: Path, entries: list) -> None:
    lock_dir = project_root / "_bmad" / "_config"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_data = {
        "bmad_version": "1.0.0",
        "compiled_at": "1.0.0",
        "entries": entries,
        "version": 1,
    }
    (lock_dir / "bmad.lock").write_text(
        json.dumps(lock_data, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _fragment_hash(project_root: Path, scenario_rel: str, content: str) -> str:
    """Write fragment file, return its hash (matches lockfile algorithm)."""
    abs_path = project_root / "_bmad" / scenario_rel
    _write(abs_path, content)
    return bmad_io.hash_text(bmad_io.read_template(str(abs_path)))


def _glob_content_hash(project_root: Path, scenario_rel: str, content: str) -> str:
    """Write a glob-matched file, return its binary hash (binary, not text)."""
    abs_path = project_root / "_bmad" / scenario_rel
    _write(abs_path, content)
    return bmad_io.sha256_hex(abs_path.read_bytes())


def _match_set_hash(matches: list[tuple[str, str]]) -> str:
    """Compute composite match-set hash from [(rel_path, content_hash)] pairs."""
    sorted_pairs = sorted(matches, key=lambda m: m[0])
    hash_parts = [f"{rel}:{h}" for rel, h in sorted_pairs]
    return bmad_io.sha256_hex("\n".join(hash_parts).encode("utf-8"))


def _resolved_pattern(project_root: Path, scenario_rel_glob: str) -> str:
    """Build the resolved_pattern value as stored in the lockfile."""
    scenario_root = project_root / "_bmad"
    return str(bmad_io.to_posix(scenario_root) / scenario_rel_glob)


def _make_base_entry(
    skill: str,
    frag_scenario_rel: str,
    frag_hash: str,
    *,
    source_path: str | None = None,
    variables: list | None = None,
    glob_inputs: list | None = None,
) -> dict:
    """Build a minimal lockfile entry for a base-tier skill."""
    entry: dict = {
        "compiled_hash": "aa" * 32,
        "fragments": [
            {
                "hash": frag_hash,
                "path": frag_scenario_rel,
                "resolved_from": "base",
            }
        ],
        "glob_inputs": glob_inputs or [],
        "skill": skill,
        "source_hash": "bb" * 32,
        "variant": None,
        "variables": variables or [],
    }
    return entry


def _run_upgrade(project_root: Path, *extra_args: str) -> tuple[int, str, str]:
    """Invoke upgrade.py as a subprocess, return (exit_code, stdout, stderr)."""
    result = subprocess.run(
        [
            sys.executable,
            str(_UPGRADE_PY),
            "--dry-run",
            "--project-root",
            str(project_root),
            *extra_args,
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDriftDetection(unittest.TestCase):
    """Unit tests for detect_drift() — call directly without subprocess."""

    # --- 4.1 ---

    def test_no_drift_clean_skill(self) -> None:
        """Fragment hash in lockfile matches file on disk → has_drift() == False."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            frag_rel = "core/skill1/fragments/intro.md"
            frag_hash = _fragment_hash(t, frag_rel, "Content A.\n")
            entry = _make_base_entry("skill1", frag_rel, frag_hash)
            _write_lockfile(t, [entry])

            report = detect_drift(entry, str(t))
            self.assertFalse(report.has_drift())
            self.assertEqual(report.skill, "skill1")

    # --- 4.2 ---

    def test_prose_fragment_changed(self) -> None:
        """Fragment content changed → one ProseFragmentChange with correct hashes."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            frag_rel = "core/skill1/fragments/intro.md"
            old_hash = bmad_io.hash_text("Old content.\n")
            # Write file with DIFFERENT content from what lockfile recorded.
            new_hash = _fragment_hash(t, frag_rel, "New content.\n")
            self.assertNotEqual(old_hash, new_hash)

            entry = _make_base_entry("skill1", frag_rel, old_hash)
            report = detect_drift(entry, str(t))

            self.assertTrue(report.has_drift())
            self.assertEqual(len(report.prose_fragment_changes), 1)
            change = report.prose_fragment_changes[0]
            self.assertIsInstance(change, ProseFragmentChange)
            self.assertEqual(change.path, frag_rel)
            self.assertEqual(change.old_hash, old_hash)
            self.assertEqual(change.new_hash, new_hash)
            self.assertEqual(change.tier, "base")

    # --- 4.3 ---

    def test_prose_fragment_missing_base(self) -> None:
        """Base fragment deleted upstream → ProseFragmentChange with new_hash=None."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            frag_rel = "core/skill1/fragments/missing.md"
            old_hash = bmad_io.hash_text("Was here.\n")
            # Do NOT create the file — it's "deleted upstream".
            entry = _make_base_entry("skill1", frag_rel, old_hash)
            report = detect_drift(entry, str(t))

            self.assertTrue(report.has_drift())
            self.assertEqual(len(report.prose_fragment_changes), 1)
            change = report.prose_fragment_changes[0]
            self.assertEqual(change.old_hash, old_hash)
            self.assertIsNone(change.new_hash)
            self.assertEqual(change.tier, "base")

    # --- 4.4 ---

    def test_glob_change_file_added(self) -> None:
        """New file added to glob directory → GlobChange with added_matches."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            scenario_root = t / "_bmad"

            # Initial state: one file matched.
            file1_rel = "docs/a.md"
            file1_hash = _glob_content_hash(t, file1_rel, "Alpha.\n")
            old_msh = _match_set_hash([(file1_rel, file1_hash)])

            resolved_pat = _resolved_pattern(t, "docs/*.md")
            glob_entry = {
                "toml_key": "self.context.docs",
                "pattern": "file:docs/*.md",
                "resolved_pattern": resolved_pat,
                "match_set_hash": old_msh,
                "matches": [{"path": file1_rel, "hash": file1_hash}],
            }

            # Add a second file AFTER lockfile was written.
            _glob_content_hash(t, "docs/b.md", "Beta.\n")

            entry = _make_base_entry(
                "skill1",
                "core/skill1/fragments/root.md",
                bmad_io.hash_text("Root.\n"),
                glob_inputs=[glob_entry],
            )
            _fragment_hash(t, "core/skill1/fragments/root.md", "Root.\n")

            report = detect_drift(entry, str(t))

            self.assertTrue(report.has_drift())
            self.assertEqual(len(report.glob_changes), 1)
            gc = report.glob_changes[0]
            self.assertIsInstance(gc, GlobChange)
            self.assertEqual(gc.toml_key, "self.context.docs")
            # b.md was added after lockfile was written → appears in added_matches.
            self.assertTrue(any("b.md" in m for m in gc.added_matches))
            self.assertEqual(gc.removed_matches, [])

    # --- 4.5 ---

    def test_glob_change_file_removed(self) -> None:
        """File removed from glob directory → GlobChange with removed_matches."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)

            # Initial state: two files matched.
            file1_rel = "docs/a.md"
            file2_rel = "docs/b.md"
            file1_hash = _glob_content_hash(t, file1_rel, "Alpha.\n")
            file2_hash = _glob_content_hash(t, file2_rel, "Beta.\n")
            old_msh = _match_set_hash([(file1_rel, file1_hash), (file2_rel, file2_hash)])

            resolved_pat = _resolved_pattern(t, "docs/*.md")
            glob_entry = {
                "toml_key": "self.context.docs",
                "pattern": "file:docs/*.md",
                "resolved_pattern": resolved_pat,
                "match_set_hash": old_msh,
                "matches": [
                    {"path": file1_rel, "hash": file1_hash},
                    {"path": file2_rel, "hash": file2_hash},
                ],
            }

            # Delete file2 AFTER lockfile was written.
            (t / "_bmad" / file2_rel).unlink()

            entry = _make_base_entry(
                "skill1",
                "core/skill1/fragments/root.md",
                bmad_io.hash_text("Root.\n"),
                glob_inputs=[glob_entry],
            )
            _fragment_hash(t, "core/skill1/fragments/root.md", "Root.\n")

            report = detect_drift(entry, str(t))

            self.assertTrue(report.has_drift())
            gc = report.glob_changes[0]
            self.assertTrue(any("b.md" in m for m in gc.removed_matches))
            self.assertEqual(gc.added_matches, [])

    # --- 4.6 ---

    def test_glob_no_change(self) -> None:
        """Glob files match lockfile exactly → no GlobChange."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            file1_rel = "docs/a.md"
            file1_hash = _glob_content_hash(t, file1_rel, "Alpha.\n")
            old_msh = _match_set_hash([(file1_rel, file1_hash)])

            resolved_pat = _resolved_pattern(t, "docs/*.md")
            glob_entry = {
                "toml_key": "self.context.docs",
                "pattern": "file:docs/*.md",
                "resolved_pattern": resolved_pat,
                "match_set_hash": old_msh,
                "matches": [{"path": file1_rel, "hash": file1_hash}],
            }
            entry = _make_base_entry(
                "skill1",
                "core/skill1/fragments/root.md",
                bmad_io.hash_text("Root.\n"),
                glob_inputs=[glob_entry],
            )
            _fragment_hash(t, "core/skill1/fragments/root.md", "Root.\n")

            report = detect_drift(entry, str(t))
            self.assertFalse(report.has_drift())

    # --- 4.7 ---

    def test_toml_default_changed(self) -> None:
        """TOML value changed → one TomlDefaultChange."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            frag_rel = "core/skill1/fragments/intro.md"
            frag_hash = _fragment_hash(t, frag_rel, "Content.\n")

            # Write TOML with "new_value" — but lockfile records hash of "old_value".
            toml_path = t / "_bmad" / "core" / "skill1" / "customize.toml"
            _write(toml_path, '[workflow]\nmodel = "new_value"\n')
            toml_rel = str(PurePosixPath("core/skill1/customize.toml"))

            old_hash = bmad_io.hash_text("old_value")
            entry = _make_base_entry(
                "skill1",
                frag_rel,
                frag_hash,
                source_path=toml_rel,
                variables=[
                    {
                        "name": "self.workflow.model",
                        "source": "toml",
                        "source_path": toml_rel,
                        "toml_layer": "defaults",
                        "value_hash": old_hash,
                    }
                ],
            )
            report = detect_drift(entry, str(t))

            self.assertTrue(report.has_drift())
            self.assertEqual(len(report.toml_default_changes), 1)
            tc = report.toml_default_changes[0]
            self.assertIsInstance(tc, TomlDefaultChange)
            self.assertEqual(tc.key, "self.workflow.model")
            self.assertEqual(tc.old_hash, old_hash)
            self.assertEqual(tc.new_value, "new_value")

    # --- 4.8 ---

    def test_new_default(self) -> None:
        """TOML has a key not in lockfile variables → NewDefault."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            frag_rel = "core/skill1/fragments/intro.md"
            frag_hash = _fragment_hash(t, frag_rel, "Content.\n")

            # Write TOML with a key that is NOT in lockfile variables.
            toml_path = t / "_bmad" / "core" / "skill1" / "customize.toml"
            _write(toml_path, '[workflow]\nbrand_new_key = "hello"\n')

            # Lockfile variables list is empty — key is "new".
            entry = _make_base_entry("skill1", frag_rel, frag_hash, variables=[])
            report = detect_drift(entry, str(t))

            self.assertTrue(report.has_drift())
            self.assertEqual(len(report.new_defaults), 1)
            nd = report.new_defaults[0]
            self.assertIsInstance(nd, NewDefault)
            self.assertEqual(nd.key, "self.workflow.brand_new_key")
            self.assertEqual(nd.new_value, "hello")
            self.assertEqual(nd.source, "defaults")

    # --- 4.8b ---

    def test_orphaned_override(self) -> None:
        """user-module-fragment override whose base no longer exists → OrphanedOverride."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            # Override at custom/fragments/core/skill1/guard.md — base would be
            # core/skill1/fragments/guard.md, which we deliberately do NOT create.
            override_rel = "custom/fragments/core/skill1/guard.md"
            override_hash = _fragment_hash(t, override_rel, "Override text.\n")
            # Provide base_hash so the engine knows there was a base.
            base_hash = bmad_io.hash_text("Original base.\n")

            # Also need a valid base fragment so the entry itself is well-formed.
            root_rel = "core/skill1/fragments/root.md"
            root_hash = _fragment_hash(t, root_rel, "Root.\n")

            entry = {
                "compiled_hash": "aa" * 32,
                "fragments": [
                    {"hash": root_hash, "path": root_rel, "resolved_from": "base"},
                    {
                        "hash": override_hash,
                        "path": override_rel,
                        "resolved_from": "user-module-fragment",
                        "base_hash": base_hash,
                    },
                ],
                "glob_inputs": [],
                "skill": "skill1",
                "source_hash": "bb" * 32,
                "variant": None,
                "variables": [],
            }
            report = detect_drift(entry, str(t))

            self.assertTrue(report.has_drift())
            self.assertEqual(len(report.orphaned_overrides), 1)
            oo = report.orphaned_overrides[0]
            self.assertIsInstance(oo, OrphanedOverride)
            self.assertEqual(oo.path, override_rel)
            self.assertEqual(oo.reason, "base_fragment_removed")

    # --- 4.8c ---

    def test_variable_provenance_shift(self) -> None:
        """TOML variable layer changed (defaults→team) → VariableProvenanceShift."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            frag_rel = "core/skill1/fragments/intro.md"
            frag_hash = _fragment_hash(t, frag_rel, "Content.\n")

            # Write team TOML with the variable (no customize.toml / defaults layer).
            current_value = "gpt-4"
            team_toml = t / "_bmad" / "custom" / "skill1.toml"
            _write(team_toml, f'[workflow]\nmodel = "{current_value}"\n')

            # Lockfile records: source=toml, layer=defaults, hash of same value.
            value_hash = bmad_io.hash_text(current_value)
            entry = _make_base_entry(
                "skill1",
                frag_rel,
                frag_hash,
                variables=[{
                    "name": "self.workflow.model",
                    "source": "toml",
                    "source_path": "core/skill1/customize.toml",
                    "toml_layer": "defaults",
                    "value_hash": value_hash,
                }],
            )
            report = detect_drift(entry, str(t))

            # Value unchanged → no toml_default_changes; layer changed → provenance shift.
            self.assertEqual(len(report.toml_default_changes), 0)
            self.assertTrue(report.has_drift())
            self.assertEqual(len(report.variable_provenance_shifts), 1)
            vps = report.variable_provenance_shifts[0]
            self.assertIsInstance(vps, VariableProvenanceShift)
            self.assertEqual(vps.name, "self.workflow.model")
            self.assertEqual(vps.old_toml_layer, "defaults")
            self.assertEqual(vps.new_toml_layer, "team")


class TestUpgradeCLI(unittest.TestCase):
    """Subprocess integration tests for upgrade.py."""

    # --- 4.9 ---

    def test_no_drift_message(self) -> None:
        """No drift → stdout is 'No drift detected.' and exit code 0."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            frag_rel = "core/skill1/fragments/intro.md"
            frag_hash = _fragment_hash(t, frag_rel, "Content.\n")
            entry = _make_base_entry("skill1", frag_rel, frag_hash)
            _write_lockfile(t, [entry])

            code, stdout, stderr = _run_upgrade(t)
            self.assertEqual(code, 0, f"stderr: {stderr}")
            self.assertEqual(stdout.strip(), "No drift detected.")

    # --- 4.10 ---

    def test_human_output_with_drift(self) -> None:
        """Prose fragment changed → stdout contains [prose_fragment_changes] and path."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            frag_rel = "core/skill1/fragments/intro.md"
            old_hash = bmad_io.hash_text("Old content.\n")
            # Write file with different content.
            _fragment_hash(t, frag_rel, "New content.\n")
            entry = _make_base_entry("skill1", frag_rel, old_hash)
            _write_lockfile(t, [entry])

            code, stdout, stderr = _run_upgrade(t)
            self.assertEqual(code, 0, f"stderr: {stderr}")
            self.assertIn("[prose_fragment_changes]", stdout)
            self.assertIn("intro.md", stdout)

    # --- 4.11 ---

    def test_json_output_with_drift(self) -> None:
        """--json flag: output is valid JSON with correct drift entry."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            frag_rel = "core/skill1/fragments/intro.md"
            old_hash = bmad_io.hash_text("Old content.\n")
            _fragment_hash(t, frag_rel, "New content.\n")
            entry = _make_base_entry("skill1", frag_rel, old_hash)
            _write_lockfile(t, [entry])

            code, stdout, stderr = _run_upgrade(t, "--json")
            self.assertEqual(code, 0, f"stderr: {stderr}")
            data = json.loads(stdout)
            self.assertEqual(data["schema_version"], 1)
            self.assertIsInstance(data["drift"], list)
            self.assertEqual(len(data["drift"]), 1)
            self.assertEqual(data["drift"][0]["skill"], "skill1")
            self.assertGreater(
                len(data["drift"][0]["prose_fragment_changes"]), 0
            )

    # --- 4.12 ---

    def test_json_validates_against_schema(self) -> None:
        """--json output must validate against the dry-run-v1.json schema fixture."""
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")

        schema_path = _SCHEMAS_DIR / "dry-run-v1.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            frag_rel = "core/skill1/fragments/intro.md"
            old_hash = bmad_io.hash_text("Old content.\n")
            _fragment_hash(t, frag_rel, "New content.\n")
            entry = _make_base_entry("skill1", frag_rel, old_hash)
            _write_lockfile(t, [entry])

            code, stdout, stderr = _run_upgrade(t, "--json")
            self.assertEqual(code, 0, f"stderr: {stderr}")
            data = json.loads(stdout)

            # Structural-only validation (same approach as TestExplainSchemaFixture).
            self.assertIsInstance(data["schema_version"], int)
            self.assertEqual(data["schema_version"], 1)
            self.assertIsInstance(data["drift"], list)
            self.assertIsInstance(data["summary"], dict)
            required_summary_keys = [
                "total_skills_with_drift",
                "prose_fragment_changes",
                "toml_default_changes",
                "orphaned_overrides",
                "new_defaults",
                "glob_changes",
                "variable_provenance_shifts",
            ]
            for k in required_summary_keys:
                self.assertIn(k, data["summary"])
            # Validate against schema if jsonschema is available.
            jsonschema.validate(data, schema)

    # --- 4.13 ---

    def test_schema_fixture_exists_and_valid_json(self) -> None:
        """dry-run-v1.json exists, parses as JSON, and schema_version is integer const."""
        schema_path = _SCHEMAS_DIR / "dry-run-v1.json"
        self.assertTrue(schema_path.exists(), f"Schema not found: {schema_path}")
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertIsInstance(schema, dict)
        self.assertIn("required", schema)
        required = schema["required"]
        for field in ("schema_version", "drift", "summary"):
            self.assertIn(field, required)
        # schema_version property must be integer const 1.
        sv_schema = schema["properties"]["schema_version"]
        self.assertEqual(sv_schema.get("type"), "integer")
        self.assertEqual(sv_schema.get("const"), 1)

    # --- 4.14 ---

    def test_dry_run_no_file_writes(self) -> None:
        """--dry-run must not write any files (read-only invariant)."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            frag_rel = "core/skill1/fragments/intro.md"
            old_hash = bmad_io.hash_text("Old.\n")
            _fragment_hash(t, frag_rel, "New.\n")
            entry = _make_base_entry("skill1", frag_rel, old_hash)
            _write_lockfile(t, [entry])

            # Snapshot all file mtimes before running.
            def _snapshot(root: Path) -> dict[str, float]:
                return {
                    str(p): p.stat().st_mtime
                    for p in root.rglob("*")
                    if p.is_file()
                }

            before = _snapshot(t)
            code, _, stderr = _run_upgrade(t)
            self.assertEqual(code, 0, f"stderr: {stderr}")
            after = _snapshot(t)

            # No new files and no modified files.
            self.assertEqual(set(before.keys()), set(after.keys()), "Files were added or removed")
            for path, mtime in before.items():
                self.assertEqual(after[path], mtime, f"File was modified: {path}")


if __name__ == "__main__":
    unittest.main()
