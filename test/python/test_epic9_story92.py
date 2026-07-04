"""Story 9.2 tests: reference conditional-rendering components + quick-dev migration.

Tests run via ComponentRunner.run_jit() against the actual component source files.
This mirrors Story 9.1's test approach: real files, no mocks except where isolation
is needed (TestProjectContextComponent sub-case h mocks subprocess.run).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BMAD_ROOT = Path(__file__).resolve().parent.parent.parent
REF_COMPS = BMAD_ROOT / "src" / "core-skills" / "bmad-reference-components" / "components"
SHARED_COMPS = BMAD_ROOT / "src" / "_shared" / "components"
QD_COMPS = BMAD_ROOT / "src" / "bmm-skills" / "4-implementation" / "bmad-quick-dev" / "components"
# Post-DN-FOLLOWUP-II (2026-07-03): bmad-quick-dev's local todays_date.py
# was lifted to _shared/components/. The local copy is gone; consumers
# resolve via the shared fallback.
SHARED_COMPS = BMAD_ROOT / "src" / "_shared" / "components"

_SCRIPTS = str(BMAD_ROOT / "src" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from bmad_compile.component_runner import ComponentRunner

_CTX_FULL = {
    "config": {"core": {"project_name": "test-project", "ide": "cursor", "user_name": "Tester"}},
    "skill_id": "core/bmad-reference-components",
    "skill_source_root": str(REF_COMPS.parent),
    "render_mode": "jit",
}

_CTX_EMPTY = {
    "config": {},
    "skill_id": "core/bmad-reference-components",
    "skill_source_root": str(REF_COMPS.parent),
    "render_mode": "compile",
}


class TestTodaysDateComponent(unittest.TestCase):

    def _run(self, props=None, ctx=None):
        runner = ComponentRunner()
        return runner.run_jit(
            str(REF_COMPS / "todays_date.py"),
            ctx or _CTX_EMPTY,
            props or {},
            component_name="TodaysDate",
        )

    def test_a_default_fmt_iso_date(self):
        """Default format returns YYYY-MM-DD."""
        import re, datetime
        result = self._run()
        self.assertRegex(result, r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(result, datetime.date.today().isoformat())

    def test_b_custom_fmt_month_year(self):
        """Custom fmt returns month + year."""
        import datetime
        result = self._run(props={"fmt": "%B %Y"})
        expected = datetime.date.today().strftime("%B %Y")
        self.assertEqual(result, expected)

    def test_c_empty_config_no_exception(self):
        """Missing config keys do not cause an exception."""
        result = self._run(ctx=_CTX_EMPTY)
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)


class TestIdeNotesComponent(unittest.TestCase):

    def _run(self, ide_value=None):
        config = {"core": {"ide": ide_value}} if ide_value else {}
        ctx = {**_CTX_EMPTY, "config": config, "render_mode": "compile"}
        runner = ComponentRunner()
        return runner.run_jit(
            str(SHARED_COMPS / "ide_notes.py"),
            ctx, {},
            component_name="IdeNotes",
        )

    def test_d_cursor_ide(self):
        """cursor ide returns Cursor-specific guidance."""
        result = self._run("cursor")
        self.assertIn("Cursor", result)
        self.assertIn("⌘K", result)

    def test_e_claude_code_ide(self):
        """claude-code ide returns Claude Code-specific guidance."""
        result = self._run("claude-code")
        self.assertIn("Claude Code", result)
        self.assertIn("--continue", result)

    def test_f_generic_fallback_no_ide_key(self):
        """Missing ide key returns generic guidance."""
        result = self._run()  # no ide value → config = {}
        self.assertIn("IDE", result)
        self.assertIn("chat panel", result)

    def test_l_claudecode_alias(self):
        """'claudecode' (no hyphen) is an accepted alias for 'claude-code'."""
        result = self._run("claudecode")
        self.assertIn("Claude Code", result)
        self.assertIn("--continue", result)

    def test_m_vscode_ide(self):
        """vscode ide returns VS Code-specific guidance."""
        result = self._run("vscode")
        self.assertIn("VS Code", result)
        self.assertIn("Copilot", result)


class TestProjectContextComponent(unittest.TestCase):

    def _run(self, ctx=None):
        runner = ComponentRunner()
        return runner.run_jit(
            str(SHARED_COMPS / "project_context.py"),
            ctx or _CTX_FULL,
            {},
            component_name="ProjectContext",
        )

    def test_g_config_and_git(self):
        """With project_name in config, result starts with 'Project: test-project'.

        Branch is included if git is available in the test environment; absent otherwise.
        Both forms are acceptable — assert the common prefix only.
        Note: if running in a detached HEAD state, git returns "HEAD" as branch name,
        which is still a valid non-empty branch string and the test passes.
        """
        result = self._run()
        self.assertIn("Project: test-project", result)
        # Accept "Project: test-project | Branch: <x>" OR "Project: test-project"
        self.assertTrue(
            result.startswith("Project: test-project"),
            f"Expected prefix 'Project: test-project', got: {result!r}",
        )

    def test_h_git_subprocess_fail_graceful(self):
        """If subprocess.run raises FileNotFoundError, returns project name only."""
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            result = self._run()
        self.assertEqual(result, "Project: test-project")

    def test_i_missing_project_name_fallback(self):
        """Missing project_name → 'unknown' default."""
        ctx = {**_CTX_EMPTY, "config": {}, "render_mode": "jit"}
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = self._run(ctx=ctx)
        self.assertIn("Project: unknown", result)


class TestQuickDevMigration(unittest.TestCase):

    def test_j_todays_date_renders_via_run_jit(self):
        """TodaysDate at the shared-components path returns today's ISO date via run_jit.

        Post-DN-FOLLOWUP-II: bmad-quick-dev's local todays_date.py was lifted to
        _shared/components/todays_date.py. The render still happens via run_jit
        with the shared path as the resolved source.
        """
        import datetime
        runner = ComponentRunner()
        result = runner.run_jit(
            str(SHARED_COMPS / "todays_date.py"),
            _CTX_EMPTY,
            {},
            component_name="TodaysDate",
        )
        self.assertEqual(result, datetime.date.today().isoformat())

    def test_k_todays_date_copies_byte_identical(self):
        """todays_date.py is content-identical between the reference and shared copies.

        Post-DN-FOLLOWUP-II: the bmad-quick-dev local copy was lifted to shared;
        only bmad-reference-components' local copy remains. Until its own
        SHA-pin-lift lands, the two remaining copies must stay byte-identical.

        Uses read_text(encoding='utf-8') rather than read_bytes() to normalise line
        endings (CRLF vs LF) on Windows, so the comparison is platform-safe.
        """
        import hashlib
        ref_text = (REF_COMPS / "todays_date.py").read_text(encoding="utf-8")
        shared_text = (SHARED_COMPS / "todays_date.py").read_text(encoding="utf-8")
        ref_hash = hashlib.sha256(ref_text.encode("utf-8")).hexdigest()
        shared_hash = hashlib.sha256(shared_text.encode("utf-8")).hexdigest()
        self.assertEqual(
            ref_hash, shared_hash,
            "todays_date.py diverged between reference and shared copies. "
            "Keep them in sync or complete the next SHA-pin-lift.",
        )


class TestResearchReportHeaderComponent(unittest.TestCase):

    def test_n_renders_full_scaffold(self):
        """ResearchReportHeader returns the 30-line research document scaffold verbatim."""
        runner = ComponentRunner()
        result = runner.run_jit(
            str(REF_COMPS / "research_report_header.py"),
            _CTX_EMPTY,
            {},
            component_name="ResearchReportHeader",
        )
        self.assertIn("stepsCompleted:", result)
        self.assertIn("workflowType: 'research'", result)
        self.assertIn("# Research Report:", result)
        self.assertIn("## Research Overview", result)
        self.assertIn("Content will be appended sequentially", result)
        # verify it's a compile-mode component
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_rr", str(REF_COMPS / "research_report_header.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(mod.RENDER_MODE, "compile")


if __name__ == "__main__":
    unittest.main()
