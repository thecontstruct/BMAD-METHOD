"""Tests for compile.py --install-phase mode (Story 2.1 AC 2/4, Task 3.8).

Exercises the `_run_install_phase` dispatcher end-to-end:
(a) one migrated skill emits kind:"skill" + kind:"summary" + writes SKILL.md + lockfile
(b) no migrated skills emits only kind:"summary" with compiled:0
(c) one migrated skill with an unresolved variable emits kind:"error" + kind:"summary" + exits 1
(d) JSON output is parseable line-by-line
(e) schema_version:1 is present on every emitted document
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_install_phase(install_dir: Path) -> tuple[int, list[dict], str]:
    """Invoke compile.py --install-phase and return (exit_code, events, stderr)."""
    compile_py = Path(__file__).resolve().parent.parent.parent / "src" / "scripts" / "compile.py"
    result = subprocess.run(
        [sys.executable, str(compile_py), "--install-phase", "--install-dir", str(install_dir)],
        capture_output=True,
        text=True,
    )
    events = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return result.returncode, events, result.stderr


class TestInstallPhaseHappyPath(unittest.TestCase):
    """(a) One migrated skill: emits kind:"skill" + kind:"summary", writes SKILL.md + lockfile."""

    def test_single_skill_emits_skill_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            skill_dir = install / "mymodule" / "my-skill"
            _write(skill_dir / "my-skill.template.md", "Hello from my-skill!")
            (install / "custom").mkdir(parents=True, exist_ok=True)

            code, events, _ = _run_install_phase(install)

            self.assertEqual(code, 0)
            skill_events = [e for e in events if e["kind"] == "skill"]
            summary_events = [e for e in events if e["kind"] == "summary"]
            self.assertEqual(len(skill_events), 1)
            self.assertEqual(len(summary_events), 1)

            skill_ev = skill_events[0]
            self.assertEqual(skill_ev["skill"], "mymodule/my-skill")
            self.assertEqual(skill_ev["status"], "ok")
            self.assertTrue(skill_ev["lockfile_updated"])

            summary_ev = summary_events[0]
            self.assertEqual(summary_ev["compiled"], 1)
            self.assertEqual(summary_ev["errors"], 0)

            # SKILL.md written at <install>/<module>/<skill>/SKILL.md
            skill_md = install / "mymodule" / "my-skill" / "SKILL.md"
            self.assertTrue(skill_md.is_file(), f"SKILL.md not found at {skill_md}")
            self.assertEqual(skill_md.read_text(encoding="utf-8"), "Hello from my-skill!")

            # lockfile written at <install>/_config/bmad.lock
            lockfile = install / "_config" / "bmad.lock"
            self.assertTrue(lockfile.is_file(), f"bmad.lock not found at {lockfile}")

    def test_skill_md_output_path_uses_module_segment(self) -> None:
        """SKILL.md output must be at <install>/<module>/<skill>/SKILL.md, not <install>/<skill>/SKILL.md."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            skill_dir = install / "core" / "my-core-skill"
            _write(skill_dir / "my-core-skill.template.md", "core content")
            (install / "custom").mkdir(parents=True, exist_ok=True)

            code, events, _ = _run_install_phase(install)

            self.assertEqual(code, 0)
            # Must land at install/core/my-core-skill/SKILL.md
            self.assertTrue((install / "core" / "my-core-skill" / "SKILL.md").is_file())
            # Must NOT be at install/my-core-skill/SKILL.md (old per-skill layout)
            self.assertFalse((install / "my-core-skill" / "SKILL.md").is_file())


class TestInstallPhaseNoSkills(unittest.TestCase):
    """(b) No migrated skills: emits only kind:"summary" with compiled:0."""

    def test_no_migrated_skills_emits_only_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            # A directory with a file NOT matching the basename rule
            research_dir = install / "bmm" / "bmad-technical-research"
            _write(research_dir / "research.template.md", "workflow output template")

            code, events, _ = _run_install_phase(install)

            self.assertEqual(code, 0)
            kinds = [e["kind"] for e in events]
            self.assertNotIn("skill", kinds)
            self.assertNotIn("error", kinds)
            self.assertIn("summary", kinds)
            summary = next(e for e in events if e["kind"] == "summary")
            self.assertEqual(summary["compiled"], 0)
            self.assertEqual(summary["errors"], 0)


class TestInstallPhaseErrorPath(unittest.TestCase):
    """(c) Migrated skill with unresolved variable: emits kind:"error" + kind:"summary", exits 1."""

    def test_unresolved_variable_emits_error_and_exits_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            skill_dir = install / "mod" / "broken-skill"
            # {{undefined_var}} will raise UnresolvedVariableError
            _write(skill_dir / "broken-skill.template.md", "{{undefined_var}}")
            (install / "custom").mkdir(parents=True, exist_ok=True)

            code, events, _ = _run_install_phase(install)

            self.assertEqual(code, 1)
            error_events = [e for e in events if e["kind"] == "error"]
            summary_events = [e for e in events if e["kind"] == "summary"]
            self.assertEqual(len(error_events), 1)
            self.assertEqual(len(summary_events), 1)

            err = error_events[0]
            self.assertEqual(err["code"], "UNRESOLVED_VARIABLE")
            self.assertEqual(err["skill"], "mod/broken-skill")
            self.assertEqual(err["status"], "error")

            summary = summary_events[0]
            self.assertEqual(summary["errors"], 1)
            self.assertEqual(summary["compiled"], 0)

    def test_error_does_not_abort_remaining_skills(self) -> None:
        """Failing skill must not abort compilation of subsequent skills."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            skill_a = install / "mod" / "skill-a"
            skill_b = install / "mod" / "skill-b"
            _write(skill_a / "skill-a.template.md", "{{undefined}}")
            _write(skill_b / "skill-b.template.md", "good content")
            (install / "custom").mkdir(parents=True, exist_ok=True)

            code, events, _ = _run_install_phase(install)

            self.assertEqual(code, 1)
            self.assertEqual(len([e for e in events if e["kind"] == "error"]), 1)
            self.assertEqual(len([e for e in events if e["kind"] == "skill"]), 1)
            summary = next(e for e in events if e["kind"] == "summary")
            self.assertEqual(summary["errors"], 1)
            self.assertEqual(summary["compiled"], 1)


class TestInstallPhaseJsonContract(unittest.TestCase):
    """(d) JSON output is parseable line-by-line. (e) schema_version:1 on every doc."""

    def test_every_event_has_schema_version_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            skill_dir = install / "mod" / "my-skill"
            _write(skill_dir / "my-skill.template.md", "hello")
            (install / "custom").mkdir(parents=True, exist_ok=True)

            code, events, _ = _run_install_phase(install)

            self.assertEqual(code, 0)
            self.assertGreater(len(events), 0)
            for ev in events:
                self.assertEqual(ev.get("schema_version"), 1, f"schema_version missing in event: {ev}")

    def test_output_is_parseable_line_by_line(self) -> None:
        """Each line of stdout must be a valid JSON document."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            skill_dir = install / "mod" / "my-skill"
            _write(skill_dir / "my-skill.template.md", "hello")
            (install / "custom").mkdir(parents=True, exist_ok=True)

            compile_py = Path(__file__).resolve().parent.parent.parent / "src" / "scripts" / "compile.py"
            result = subprocess.run(
                [sys.executable, str(compile_py), "--install-phase", "--install-dir", str(install)],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parsed = json.loads(line)  # raises ValueError if not valid JSON
                self.assertIsInstance(parsed, dict)

    def test_summary_is_always_last_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            skill_dir = install / "mod" / "my-skill"
            _write(skill_dir / "my-skill.template.md", "hello")
            (install / "custom").mkdir(parents=True, exist_ok=True)

            code, events, _ = _run_install_phase(install)

            self.assertEqual(code, 0)
            self.assertEqual(events[-1]["kind"], "summary")

    def test_sort_keys_stable_output(self) -> None:
        """JSON fields must be sorted (sort_keys=True contract)."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            skill_dir = install / "mod" / "my-skill"
            _write(skill_dir / "my-skill.template.md", "hello")
            (install / "custom").mkdir(parents=True, exist_ok=True)

            compile_py = Path(__file__).resolve().parent.parent.parent / "src" / "scripts" / "compile.py"
            result = subprocess.run(
                [sys.executable, str(compile_py), "--install-phase", "--install-dir", str(install)],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                keys = list(obj.keys())
                self.assertEqual(keys, sorted(keys), f"Keys not sorted in: {line}")

    def test_lockfile_path_in_summary_is_absolute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            skill_dir = install / "mod" / "my-skill"
            _write(skill_dir / "my-skill.template.md", "hello")
            (install / "custom").mkdir(parents=True, exist_ok=True)

            code, events, _ = _run_install_phase(install)

            self.assertEqual(code, 0)
            summary = next(e for e in events if e["kind"] == "summary")
            lp = summary["lockfile_path"]
            self.assertTrue(Path(lp).is_absolute(), f"lockfile_path not absolute: {lp}")
            self.assertTrue(lp.endswith("bmad.lock"))


if __name__ == "__main__":
    unittest.main()
