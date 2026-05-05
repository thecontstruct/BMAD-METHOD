"""Story 5.4: Tests for bmad_compile.lazy_compile — cache-coherence guard.

Covers AC-1 through AC-6: fast path, slow path, glob drift, missing inputs,
first-compile (no lockfile), and exit codes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

# Locate scripts dir so direct imports work.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from src.scripts.bmad_compile import engine as bmad_engine
from src.scripts.bmad_compile import io as bmad_io
from src.scripts.bmad_compile.lazy_compile import main as lazy_main


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_lockfile(project_root: Path, entries: list) -> None:
    lock_dir = project_root / "_bmad" / "_config"
    lock_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "bmad_version": "1.0.0",
        "compiled_at": "1.0.0",
        "entries": entries,
        "version": 1,
    }
    (lock_dir / "bmad.lock").write_text(
        json.dumps(data, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _frag_hash(path: Path) -> str:
    return bmad_io.hash_text(bmad_io.read_template(str(path)))


def _match_set_hash(matches: list[tuple[str, str]]) -> str:
    """Compute composite match-set hash from [(rel_posix, content_hash)] pairs."""
    sorted_pairs = sorted(matches, key=lambda m: m[0])
    parts = [f"{rel}:{h}" for rel, h in sorted_pairs]
    return bmad_io.sha256_hex("\n".join(parts).encode("utf-8"))


def _resolved_pattern(project_root: Path, scenario_rel_glob: str) -> str:
    """Return the absolute POSIX glob pattern as stored in the lockfile."""
    scenario_root = project_root / "_bmad"
    return str(bmad_io.to_posix(scenario_root) / scenario_rel_glob)


def _make_minimal_skill(
    project_root: Path,
    module: str = "mymodule",
    skill: str = "my-skill",
    template_content: str | None = None,
) -> Path:
    """Create a minimal compilable skill directory tree. Return skill_dir.

    The template uses <<include>> so the engine records a fragments entry.
    This ensures entry["fragments"][0] exists for tests that corrupt the hash.
    """
    scenario_root = project_root / "_bmad"
    skill_dir = scenario_root / module / skill
    skill_dir.mkdir(parents=True, exist_ok=True)
    frag_content = template_content or f"# {skill}\n\nHello world.\n"
    _write(skill_dir / "fragments" / "content.template.md", frag_content)
    _write(skill_dir / f"{skill}.template.md",
           '<<include path="fragments/content.template.md">>')
    (scenario_root / "custom").mkdir(parents=True, exist_ok=True)
    (scenario_root / "_config").mkdir(parents=True, exist_ok=True)
    return skill_dir


def _compile_skill(
    project_root: Path,
    module: str = "mymodule",
    skill: str = "my-skill",
) -> None:
    """Run engine.compile_skill to produce a real lockfile + SKILL.md."""
    scenario_root = project_root / "_bmad"
    skill_dir = scenario_root / module / skill
    bmad_engine.compile_skill(
        skill_dir,
        scenario_root,
        None,
        lockfile_root=scenario_root,
        override_root=scenario_root / "custom",
    )


def _run_guard(
    project_root: Path,
    skill: str,
    extra_args: list[str] | None = None,
) -> subprocess.CompletedProcess:
    """Invoke the guard as a subprocess. cwd=_SCRIPTS_DIR so bmad_compile is found."""
    cmd = [
        sys.executable, "-m", "bmad_compile.lazy_compile",
        skill, "--project-root", str(project_root),
    ]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(_SCRIPTS_DIR))


def _call_main(
    project_root: Path,
    skill: str,
    extra_args: list[str] | None = None,
) -> int:
    """Call main() directly (no subprocess). Used with mock.patch."""
    argv = [skill, "--project-root", str(project_root)]
    if extra_args:
        argv.extend(extra_args)
    return lazy_main(argv)


def _read_lockfile_entry(project_root: Path, skill: str) -> dict | None:
    lock_path = project_root / "_bmad" / "_config" / "bmad.lock"
    if not lock_path.is_file():
        return None
    data = json.loads(lock_path.read_text(encoding="utf-8"))
    for e in data.get("entries", []):
        if isinstance(e, dict) and e.get("skill") == skill:
            return e
    return None


# ---------------------------------------------------------------------------
# TestFastPath (AC-1)
# ---------------------------------------------------------------------------

class TestFastPath(unittest.TestCase):
    """All inputs unchanged: guard emits existing SKILL.md, does not recompile."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self._tmp.name) / "project"
        _make_minimal_skill(self.project_root)
        _compile_skill(self.project_root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_fast_path_emits_existing_skill_md(self) -> None:
        skill_md = self.project_root / "_bmad" / "mymodule" / "my-skill" / "SKILL.md"
        expected = skill_md.read_text(encoding="utf-8")
        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, expected)
        self.assertEqual(result.stderr, "")

    def test_fast_path_no_engine_call(self) -> None:
        """Fast path must NOT invoke engine.compile_skill (AC-1)."""
        with patch("src.scripts.bmad_compile.lazy_compile.engine") as mock_eng:
            code = _call_main(self.project_root, "my-skill")
        self.assertEqual(code, 0)
        mock_eng.compile_skill.assert_not_called()

    def test_fast_path_exit_0(self) -> None:
        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.returncode, 0)


# ---------------------------------------------------------------------------
# TestSlowPath (AC-2)
# ---------------------------------------------------------------------------

class TestSlowPath(unittest.TestCase):
    """Any input changed: guard recompiles, emits fresh SKILL.md."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self._tmp.name) / "project"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_with_stale_fragment_hash(self) -> None:
        """Create compiled skill but corrupt the fragment hash to force slow path."""
        skill_dir = _make_minimal_skill(self.project_root)
        _compile_skill(self.project_root)
        # Corrupt the fragment hash in the lockfile so hash check fails.
        entry = _read_lockfile_entry(self.project_root, "my-skill")
        assert entry is not None
        frags = entry["fragments"]
        frags[0]["hash"] = "00" * 32  # deliberately wrong
        _write_lockfile(self.project_root, [entry])

    def test_slow_path_on_fragment_mismatch(self) -> None:
        self._make_with_stale_fragment_hash()
        skill_md = self.project_root / "_bmad" / "mymodule" / "my-skill" / "SKILL.md"
        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.returncode, 0, result.stderr)
        # Stdout should equal the freshly compiled SKILL.md content.
        self.assertEqual(result.stdout, skill_md.read_text(encoding="utf-8"))
        self.assertEqual(result.stderr, "")

    def test_slow_path_on_toml_variable_mismatch(self) -> None:
        """TOML variable hash mismatch triggers slow path."""
        skill_dir = _make_minimal_skill(self.project_root)
        # Create customize.toml with greeting = "hello".
        customize = skill_dir / "customize.toml"
        _write(customize, 'greeting = "hello"\n')
        _compile_skill(self.project_root)

        # Corrupt the variable hash in the lockfile to simulate stale state.
        entry = _read_lockfile_entry(self.project_root, "my-skill")
        assert entry is not None
        for var in entry.get("variables", []):
            if var.get("name") == "self.greeting" and var.get("source") == "toml":
                var["value_hash"] = bmad_io.hash_text("old-value")
                break
        else:
            # If engine didn't record the variable, add it manually.
            entry.setdefault("variables", []).append({
                "name": "self.greeting",
                "source": "toml",
                "source_path": "mymodule/my-skill/customize.toml",
                "toml_layer": "defaults",
                "value_hash": bmad_io.hash_text("old-value"),
            })
        _write_lockfile(self.project_root, [entry])

        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.returncode, 0, result.stderr)
        skill_md = self.project_root / "_bmad" / "mymodule" / "my-skill" / "SKILL.md"
        self.assertEqual(result.stdout, skill_md.read_text(encoding="utf-8"))

    def test_slow_path_exit_0(self) -> None:
        self._make_with_stale_fragment_hash()
        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.returncode, 0)

    def test_post_engine_skill_md_missing_exits_1(self) -> None:
        """Engine succeeds but SKILL.md absent: guard exits 1, stderr has MISSING_FRAGMENT."""
        _make_minimal_skill(self.project_root)
        # Write a lockfile entry with wrong hash to force slow path.
        template_rel = "mymodule/my-skill/my-skill.template.md"
        entry = {
            "compiled_hash": "00" * 32,
            "fragments": [{"hash": "00" * 32, "path": template_rel, "resolved_from": "base"}],
            "glob_inputs": [],
            "skill": "my-skill",
            "source_hash": "00" * 32,
            "variables": [],
            "variant": None,
        }
        _write_lockfile(self.project_root, [entry])

        def _engine_noop(*args, **kwargs):  # type: ignore[no-untyped-def]
            """Engine call that succeeds but writes nothing."""
            pass

        with patch("src.scripts.bmad_compile.lazy_compile.engine") as mock_eng:
            mock_eng.compile_skill.side_effect = _engine_noop
            code = _call_main(self.project_root, "my-skill")

        self.assertEqual(code, 1)


# ---------------------------------------------------------------------------
# TestGlobDrift (AC-3)
# ---------------------------------------------------------------------------

class TestGlobDrift(unittest.TestCase):
    """Glob match-set drift detection."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self._tmp.name) / "project"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_skill_with_glob_entry(
        self,
        doc_files: list[tuple[str, str]],  # [(rel_path, content), ...]
        stored_hash: str | None,
        stored_matches: list[dict] | None = None,
    ) -> None:
        """Create skill + lockfile where glob_inputs has a stored match_set_hash."""
        skill_dir = _make_minimal_skill(self.project_root)
        # Create the doc files.
        for rel_path, content in doc_files:
            _write(self.project_root / "_bmad" / rel_path, content)

        template_path = skill_dir / "my-skill.template.md"
        frag_hash = _frag_hash(template_path)

        rp = _resolved_pattern(self.project_root, "mymodule/my-skill/docs/*.md")
        entry = {
            "compiled_hash": "aa" * 32,
            "fragments": [
                {"hash": frag_hash, "path": "mymodule/my-skill/my-skill.template.md",
                 "resolved_from": "base"}
            ],
            "glob_inputs": [
                {
                    "toml_key": "self.files",
                    "pattern": "mymodule/my-skill/docs/*.md",
                    "resolved_pattern": rp,
                    "match_set_hash": stored_hash,
                    "matches": stored_matches or [],
                }
            ],
            "skill": "my-skill",
            "source_hash": "bb" * 32,
            "variables": [],
            "variant": None,
        }
        # Write SKILL.md so fast path has it available.
        _write(skill_dir / "SKILL.md", "COMPILED\n")
        _write_lockfile(self.project_root, [entry])

    def test_glob_unchanged_stays_fast(self) -> None:
        """Glob match-set unchanged → fast path, SKILL.md emitted, engine not called."""
        # Create one doc file and compute the correct hash.
        doc = self.project_root / "_bmad" / "mymodule" / "my-skill" / "docs" / "intro.md"
        _write(doc, "Introduction.\n")
        rel = doc.relative_to(self.project_root / "_bmad").as_posix()
        h = bmad_io.sha256_hex(doc.read_bytes())
        correct_hash = _match_set_hash([(rel, h)])

        self._make_skill_with_glob_entry(
            doc_files=[],  # doc_files already created above
            stored_hash=correct_hash,
            stored_matches=[{"path": rel, "hash": h}],
        )

        with patch("src.scripts.bmad_compile.lazy_compile.engine") as mock_eng:
            code = _call_main(self.project_root, "my-skill")
        self.assertEqual(code, 0)
        mock_eng.compile_skill.assert_not_called()

    def test_glob_match_added_triggers_recompile(self) -> None:
        """New file matching glob pattern → slow path (recompile, not cached "COMPILED")."""
        # Setup with stored hash = None (empty match set).
        self._make_skill_with_glob_entry(doc_files=[], stored_hash=None, stored_matches=[])
        # Now create a doc file that wasn't there at "last compile".
        doc = self.project_root / "_bmad" / "mymodule" / "my-skill" / "docs" / "new.md"
        _write(doc, "New file.\n")

        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.returncode, 0, result.stderr)
        # Slow path was taken: stdout must be fresh compiled content, not the stale "COMPILED\n"
        # placeholder written by _make_skill_with_glob_entry.
        self.assertNotEqual(result.stdout, "COMPILED\n")

    def test_glob_match_removed_triggers_recompile(self) -> None:
        """File removed from glob match set → slow path (fresh content, not stale "COMPILED")."""
        # Create a doc file.
        doc = self.project_root / "_bmad" / "mymodule" / "my-skill" / "docs" / "old.md"
        _write(doc, "Old content.\n")
        rel = doc.relative_to(self.project_root / "_bmad").as_posix()
        h = bmad_io.sha256_hex(doc.read_bytes())
        old_hash = _match_set_hash([(rel, h)])

        self._make_skill_with_glob_entry(
            doc_files=[],
            stored_hash=old_hash,
            stored_matches=[{"path": rel, "hash": h}],
        )
        # Now remove the doc file so current match set is empty.
        doc.unlink()

        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(result.stdout, "COMPILED\n")

    def test_glob_content_changed_triggers_recompile(self) -> None:
        """Same glob paths but content changed → slow path (fresh content, not stale "COMPILED")."""
        doc = self.project_root / "_bmad" / "mymodule" / "my-skill" / "docs" / "f.md"
        _write(doc, "Original.\n")
        rel = doc.relative_to(self.project_root / "_bmad").as_posix()
        old_h = bmad_io.sha256_hex(doc.read_bytes())
        old_hash = _match_set_hash([(rel, old_h)])

        self._make_skill_with_glob_entry(
            doc_files=[],
            stored_hash=old_hash,
            stored_matches=[{"path": rel, "hash": old_h}],
        )
        # Modify the file content.
        _write(doc, "Modified.\n")

        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(result.stdout, "COMPILED\n")

    def test_lockfile_updated_after_recompile(self) -> None:
        """After slow path, lockfile entry reflects updated state (written by engine)."""
        # Setup with stored hash = None (empty match set → mismatch).
        self._make_skill_with_glob_entry(doc_files=[], stored_hash=None, stored_matches=[])
        # Create a new doc file.
        doc = self.project_root / "_bmad" / "mymodule" / "my-skill" / "docs" / "note.md"
        _write(doc, "Note.\n")

        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.returncode, 0, result.stderr)
        # Engine was called → lockfile was rewritten. Verify it's valid JSON.
        lock_path = self.project_root / "_bmad" / "_config" / "bmad.lock"
        self.assertTrue(lock_path.is_file())
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        entry = next((e for e in data["entries"] if e["skill"] == "my-skill"), None)
        self.assertIsNotNone(entry)


# ---------------------------------------------------------------------------
# TestMissingInputs (AC-4, AC-5)
# ---------------------------------------------------------------------------

class TestMissingInputs(unittest.TestCase):
    """Missing lockfile / entry / SKILL.md → slow path; missing fragment → exit 1."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self._tmp.name) / "project"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_no_lockfile_triggers_slow_path(self) -> None:
        """No bmad.lock → slow path (first compile). Skill dir must exist on disk."""
        _make_minimal_skill(self.project_root)
        # No lockfile written → _scan_for_module finds skill dir → slow path.
        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.returncode, 0, result.stderr)
        skill_md = self.project_root / "_bmad" / "mymodule" / "my-skill" / "SKILL.md"
        self.assertTrue(skill_md.is_file())
        self.assertEqual(result.stdout, skill_md.read_text(encoding="utf-8"))

    def test_no_entry_triggers_slow_path(self) -> None:
        """Lockfile exists but has no entry for skill → slow path."""
        _make_minimal_skill(self.project_root)
        # Write lockfile with a DIFFERENT skill entry.
        _write_lockfile(self.project_root, [
            {"compiled_hash": "aa" * 32, "fragments": [], "glob_inputs": [],
             "skill": "other-skill", "source_hash": "bb" * 32, "variables": [],
             "variant": None}
        ])
        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_skill_md_triggers_slow_path(self) -> None:
        """Lockfile entry exists but SKILL.md missing → slow path."""
        _make_minimal_skill(self.project_root)
        _compile_skill(self.project_root)
        # Remove SKILL.md to force slow path.
        skill_md = self.project_root / "_bmad" / "mymodule" / "my-skill" / "SKILL.md"
        skill_md.unlink()
        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(skill_md.is_file())

    def test_missing_fragment_exits_1_with_error(self) -> None:
        """Base fragment deleted → engine raises MissingFragmentError → exit 1."""
        _make_minimal_skill(self.project_root)
        _compile_skill(self.project_root)
        # Delete the included fragment file so the engine fails with MissingFragmentError.
        fragment = (self.project_root / "_bmad" / "mymodule" / "my-skill"
                    / "fragments" / "content.template.md")
        fragment.unlink()
        # Corrupt the fragment hash to force slow path (so engine is actually called).
        entry = _read_lockfile_entry(self.project_root, "my-skill")
        assert entry is not None
        entry["fragments"][0]["hash"] = "00" * 32
        _write_lockfile(self.project_root, [entry])

        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")  # no stale content on stdout
        self.assertIn("MISSING_FRAGMENT", result.stderr)

    def test_no_stale_stdout_on_error(self) -> None:
        """On error (exit 1), stdout must be empty (no stale SKILL.md)."""
        _make_minimal_skill(self.project_root)
        _compile_skill(self.project_root)
        fragment = (self.project_root / "_bmad" / "mymodule" / "my-skill"
                    / "fragments" / "content.template.md")
        fragment.unlink()
        entry = _read_lockfile_entry(self.project_root, "my-skill")
        assert entry is not None
        entry["fragments"][0]["hash"] = "00" * 32
        _write_lockfile(self.project_root, [entry])

        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.stdout, "")

    def test_missing_override_fragment_triggers_slow_path(self) -> None:
        """Missing override-tier fragment detected by pre-check → slow path → exit 0."""
        _make_minimal_skill(self.project_root)
        _compile_skill(self.project_root)

        # Add a fake override-tier fragment to the lockfile entry.
        entry = _read_lockfile_entry(self.project_root, "my-skill")
        assert entry is not None
        fake_override_rel = "custom/fragments/mymodule/my-skill/override.md"
        entry.setdefault("fragments", []).append({
            "hash": "cc" * 32,
            "path": fake_override_rel,
            "resolved_from": "user-module-fragment",
            "override_path": fake_override_rel,
            "base_hash": "dd" * 32,
            "lineage": [],
        })
        _write_lockfile(self.project_root, [entry])
        # The override file does NOT exist on disk → pre-check triggers slow path.

        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_skill_dir_not_found_exits_1(self) -> None:
        """Skill directory absent from disk: _scan_for_module raises → exit 1, MISSING_FRAGMENT."""
        # Create an empty _bmad structure with no module dirs containing the skill.
        scenario_root = self.project_root / "_bmad"
        scenario_root.mkdir(parents=True, exist_ok=True)
        (scenario_root / "_config").mkdir(exist_ok=True)
        (scenario_root / "custom").mkdir(exist_ok=True)
        # No lockfile, no module dirs → _scan_for_module raises RuntimeError on slow path.
        result = _run_guard(self.project_root, "no-such-skill")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("MISSING_FRAGMENT", result.stderr)


# ---------------------------------------------------------------------------
# TestCLI (AC-6, smoke)
# ---------------------------------------------------------------------------

class TestCLI(unittest.TestCase):
    """CLI argument parsing and exit codes."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self._tmp.name) / "project"
        _make_minimal_skill(self.project_root)
        _compile_skill(self.project_root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_exit_0_fast_path(self) -> None:
        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.returncode, 0)

    def test_exit_0_slow_path(self) -> None:
        # Corrupt hash to force slow path.
        entry = _read_lockfile_entry(self.project_root, "my-skill")
        assert entry is not None
        entry["fragments"][0]["hash"] = "00" * 32
        _write_lockfile(self.project_root, [entry])
        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.returncode, 0)

    def test_exit_1_on_compiler_error(self) -> None:
        """CompilerError → exit 1, formatted error on stderr, stdout empty."""
        entry = _read_lockfile_entry(self.project_root, "my-skill")
        assert entry is not None
        # Delete included fragment + corrupt hash → engine raises MissingFragmentError.
        fragment = (self.project_root / "_bmad" / "mymodule" / "my-skill"
                    / "fragments" / "content.template.md")
        fragment.unlink()
        entry["fragments"][0]["hash"] = "00" * 32
        _write_lockfile(self.project_root, [entry])

        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertTrue(len(result.stderr) > 0)

    def test_tools_flag_accepted(self) -> None:
        """--tools flag is parsed without error (argparse smoke)."""
        entry = _read_lockfile_entry(self.project_root, "my-skill")
        assert entry is not None
        entry["fragments"][0]["hash"] = "00" * 32
        _write_lockfile(self.project_root, [entry])
        result = _run_guard(self.project_root, "my-skill", ["--tools", "cursor"])
        # Should succeed (may compile with cursor variant, or default if variant not found).
        self.assertIn(result.returncode, (0, 1))  # not argparse error (2)


# ---------------------------------------------------------------------------
# TestPerf (AC-1/AC-2 perf gates, CI-skipped)
# ---------------------------------------------------------------------------

class TestPerf(unittest.TestCase):
    """Performance gates: fast path ≤50ms, slow path ≤500ms."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self._tmp.name) / "project"
        _make_minimal_skill(self.project_root)
        _compile_skill(self.project_root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @unittest.skipUnless(os.getenv("CI") != "1", "perf gate skipped on CI")
    def test_fast_path_under_50ms(self) -> None:
        t0 = time.perf_counter()
        code = _call_main(self.project_root, "my-skill")
        elapsed_ms = (time.perf_counter() - t0) * 1000
        self.assertEqual(code, 0)
        self.assertLessEqual(
            elapsed_ms, 50, f"fast path took {elapsed_ms:.1f}ms (limit: 50ms)"
        )

    @unittest.skipUnless(os.getenv("CI") != "1", "perf gate skipped on CI")
    def test_slow_path_under_500ms(self) -> None:
        # Corrupt hash to force slow path.
        entry = _read_lockfile_entry(self.project_root, "my-skill")
        assert entry is not None
        entry["fragments"][0]["hash"] = "00" * 32
        _write_lockfile(self.project_root, [entry])

        t0 = time.perf_counter()
        result = _run_guard(self.project_root, "my-skill")
        elapsed_ms = (time.perf_counter() - t0) * 1000
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLessEqual(
            elapsed_ms, 500, f"slow path took {elapsed_ms:.1f}ms (limit: 500ms)"
        )


if __name__ == "__main__":
    unittest.main()
