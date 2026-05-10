"""Story 6.5: Writer handler tests — post-accept write, --diff verification,
and revert-on-rejection.

Covers AC-1 (override write to exact path with sparse content), AC-2
(--diff invocation and propose_diff_review event ordering), AC-3 (revert
on diff rejection: delete-when-new vs restore-when-pre-existing).
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

# Add test/ to path for harness.* imports
_TEST_DIR = Path(__file__).resolve().parent.parent
if str(_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_TEST_DIR))

# Add src/scripts to path for bmad_customize.* imports
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from bmad_customize._errors import BmadSubprocessError
from bmad_customize.writer import revert_override, write_override
from harness.mock_compiler import MockCompiler
from harness.skill_test_runner import run_handler_with_mock

_FIXTURES_ROOT = _TEST_DIR / "fixtures" / "customize-mocks"
_COMPILE_PY = _SCRIPTS_DIR / "compile.py"

_GUARD_MSG = (
    "MockCompiler.calls is empty after skill invocation -- "
    "run_handler_with_mock seam wiring broken."
)


# ---------------------------------------------------------------------------
# AC-1 / AC-2: TOML plane write + --diff
# ---------------------------------------------------------------------------


class TestWriteOverrideTOML(unittest.TestCase):
    """write_override on the TOML plane: file written + propose_diff_review."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--diff", "diff-icon-change.txt")
        self._tmp = tempfile.TemporaryDirectory()
        self._target = str(Path(self._tmp.name) / "_bmad/custom/skill-a.user.toml")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(
            write_override,
            self.mock,
            plane="toml",
            target_file=self._target,
            accepted_content='agent.icon = "🎯"\n',
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )

    def test_target_file_written(self) -> None:
        self._run()
        self.assertTrue(Path(self._target).exists())

    def test_file_content_matches_accepted(self) -> None:
        self._run()
        self.assertEqual(
            Path(self._target).read_text(encoding="utf-8"),
            'agent.icon = "🎯"\n',
        )

    def test_parent_dirs_created(self) -> None:
        self._run()
        self.assertTrue(Path(self._target).parent.exists())

    def test_write_override_complete_emitted(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[0]["action"], "write_override_complete")

    def test_propose_diff_review_emitted(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertIn("propose_diff_review", [e["action"] for e in events])

    def test_diff_text_matches_fixture(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(
            events[-1]["diff_text"],
            (_FIXTURES_ROOT / "diff-icon-change.txt").read_text(encoding="utf-8"),
        )

    def test_requires_confirmation_true(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertIs(events[-1]["requires_confirmation"], True)


# ---------------------------------------------------------------------------
# AC-1 / AC-2: Prose plane write + --diff
# ---------------------------------------------------------------------------


class TestWriteOverrideProse(unittest.TestCase):
    """write_override on the prose plane: nested fragment path + diff event."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--diff", "diff-prose-change.txt")
        self._tmp = tempfile.TemporaryDirectory()
        self._target = str(
            Path(self._tmp.name)
            / "_bmad/custom/fragments/mock-module/skill-a/menu-handler.template.md"
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(
            write_override,
            self.mock,
            plane="prose",
            target_file=self._target,
            accepted_content="Revised menu handler content.\n",
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )

    def test_target_file_written(self) -> None:
        self._run()
        self.assertTrue(Path(self._target).exists())

    def test_file_content_matches_accepted(self) -> None:
        self._run()
        self.assertEqual(
            Path(self._target).read_text(encoding="utf-8"),
            "Revised menu handler content.\n",
        )

    def test_write_override_complete_emitted(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[0]["action"], "write_override_complete")

    def test_propose_diff_review_emitted(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertIn("propose_diff_review", [e["action"] for e in events])

    def test_requires_confirmation_true(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertIs(events[-1]["requires_confirmation"], True)


# ---------------------------------------------------------------------------
# AC-3: Revert on diff rejection (pure filesystem; no MockCompiler)
# ---------------------------------------------------------------------------


class TestRevertOverride(unittest.TestCase):
    """revert_override deletes (when newly created) or restores (when pre-existing)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_file(self, content: str) -> str:
        p = Path(self._tmp.name) / "skill-a.user.toml"
        p.write_text(content, encoding="utf-8")
        return str(p)

    def test_revert_deletes_new_file(self) -> None:
        events: list[dict[str, Any]] = []
        target = self._make_file("old content\n")
        revert_override(target, pre_write_content=None, emit_fn=events.append)
        self.assertFalse(Path(target).exists())

    def test_revert_restores_existing_file(self) -> None:
        events: list[dict[str, Any]] = []
        target = self._make_file("old\n")
        Path(target).write_text("new\n", encoding="utf-8")
        revert_override(target, pre_write_content="old\n", emit_fn=events.append)
        self.assertEqual(Path(target).read_text(encoding="utf-8"), "old\n")

    def test_revert_complete_emitted_on_delete(self) -> None:
        events: list[dict[str, Any]] = []
        target = self._make_file("old content\n")
        revert_override(target, pre_write_content=None, emit_fn=events.append)
        self.assertEqual(events[-1]["action"], "revert_complete")
        self.assertIs(events[-1]["deleted"], True)

    def test_revert_complete_emitted_on_restore(self) -> None:
        events: list[dict[str, Any]] = []
        target = self._make_file("old\n")
        Path(target).write_text("new\n", encoding="utf-8")
        revert_override(target, pre_write_content="old\n", emit_fn=events.append)
        self.assertEqual(events[-1]["action"], "revert_complete")
        self.assertIs(events[-1]["deleted"], False)


# ---------------------------------------------------------------------------
# AC-2: --diff subprocess + event ordering contract
# ---------------------------------------------------------------------------


class TestDiffContract(unittest.TestCase):
    """Subprocess + event ordering: write before diff, exactly one --diff call."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--diff", "diff-icon-change.txt")
        self._tmp = tempfile.TemporaryDirectory()
        self._target = str(Path(self._tmp.name) / "_bmad/custom/skill-a.user.toml")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(
            write_override,
            self.mock,
            plane="toml",
            target_file=self._target,
            accepted_content='agent.icon = "🎯"\n',
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )

    def test_events_sequence_write_then_diff(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[0]["action"], "write_override_complete")
        self.assertEqual(events[1]["action"], "propose_diff_review")

    def test_exactly_one_mock_call_per_write(self) -> None:
        self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(len(self.mock.calls), 1)

    def test_diff_text_non_empty(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertTrue(events[-1]["diff_text"])

    def test_no_explain_call_in_write_handler(self) -> None:
        self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(self.mock.calls[0]["pattern"], "--diff")


# ---------------------------------------------------------------------------
# AC-1 (7.8): revert_override delete branch — directory at target path
# ---------------------------------------------------------------------------


class TestRevertDeleteBranchDirectory(unittest.TestCase):
    """revert_override delete branch refuses to unlink a directory."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_raises_on_directory_target(self) -> None:
        target = str(Path(self._tmp.name) / "a_dir")
        Path(target).mkdir()
        with self.assertRaises(BmadSubprocessError) as ctx:
            revert_override(target, pre_write_content=None, emit_fn=lambda _: None)
        self.assertIn(target, str(ctx.exception))

    def test_directory_not_removed_on_error(self) -> None:
        target = str(Path(self._tmp.name) / "a_dir")
        Path(target).mkdir()
        try:
            revert_override(target, pre_write_content=None, emit_fn=lambda _: None)
        except BmadSubprocessError:
            pass
        self.assertTrue(Path(target).is_dir())

    def test_no_event_emitted_on_error(self) -> None:
        target = str(Path(self._tmp.name) / "a_dir")
        Path(target).mkdir()
        events: list[dict[str, Any]] = []
        try:
            revert_override(target, pre_write_content=None, emit_fn=events.append)
        except BmadSubprocessError:
            pass
        self.assertEqual(events, [])


# ---------------------------------------------------------------------------
# AC-2 (7.8): revert_override restore branch — symlink at target path (OQ-A=A)
# ---------------------------------------------------------------------------


class TestRevertRestoreBranchSymlink(unittest.TestCase):
    """revert_override restore branch unlinks symlink before write_text (OQ-A=A)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_symlink(
        self, link_path: str, target_content: str = "symlink-target\n"
    ) -> tuple[str, Path]:
        real = Path(self._tmp.name) / "real_file.txt"
        real.write_text(target_content, encoding="utf-8")
        try:
            os.symlink(str(real), link_path)
        except OSError:
            self.skipTest("symlink creation not permitted on this platform")
        return link_path, real

    def test_symlink_replaced_with_regular_file(self) -> None:
        link, _ = self._make_symlink(str(Path(self._tmp.name) / "override.toml"))
        revert_override(link, pre_write_content="restored\n", emit_fn=lambda _: None)
        self.assertTrue(Path(link).is_file() and not Path(link).is_symlink())
        self.assertEqual(Path(link).read_text(encoding="utf-8"), "restored\n")

    def test_symlink_target_not_modified(self) -> None:
        link, real = self._make_symlink(
            str(Path(self._tmp.name) / "override.toml"), "original-target-content\n"
        )
        revert_override(link, pre_write_content="restored\n", emit_fn=lambda _: None)
        self.assertEqual(real.read_text(encoding="utf-8"), "original-target-content\n")

    def test_revert_complete_emitted_on_symlink_restore(self) -> None:
        link, _ = self._make_symlink(str(Path(self._tmp.name) / "override.toml"))
        events: list[dict[str, Any]] = []
        revert_override(link, pre_write_content="restored\n", emit_fn=events.append)
        self.assertEqual(events[-1]["action"], "revert_complete")
        self.assertIs(events[-1]["deleted"], False)


# ---------------------------------------------------------------------------
# AC-3 (7.8): write_override mkdir — parent path is a non-directory
# ---------------------------------------------------------------------------


class TestWriteOverrideMkdirConflict(unittest.TestCase):
    """write_override raises BmadSubprocessError when parent path is a non-directory."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_raises_when_parent_is_a_file(self) -> None:
        conflict = Path(self._tmp.name) / "not_a_dir"
        conflict.write_text("blocker\n", encoding="utf-8")
        target = str(conflict / "skill-a.user.toml")
        with self.assertRaises(BmadSubprocessError) as ctx:
            write_override(
                plane="toml",
                target_file=target,
                accepted_content='agent.icon = "🎯"\n',
                skill_id="mock-module/skill-a",
                install_dir=".",
                compile_py=_COMPILE_PY,
                emit_fn=lambda _: None,
            )
        self.assertIn(str(conflict), str(ctx.exception))

    def test_no_events_emitted_on_mkdir_error(self) -> None:
        conflict = Path(self._tmp.name) / "not_a_dir"
        conflict.write_text("blocker\n", encoding="utf-8")
        target = str(conflict / "skill-a.user.toml")
        events: list[dict[str, Any]] = []
        try:
            write_override(
                plane="toml",
                target_file=target,
                accepted_content='agent.icon = "🎯"\n',
                skill_id="mock-module/skill-a",
                install_dir=".",
                compile_py=_COMPILE_PY,
                emit_fn=events.append,
            )
        except BmadSubprocessError:
            pass
        self.assertEqual(events, [])


# ---------------------------------------------------------------------------
# AC-4 (7.8): write_override emit_fn-raise — revert_override reachable (OQ-B=A)
# ---------------------------------------------------------------------------


class TestWriteOverrideEmitFnRaise(unittest.TestCase):
    """revert_override remains reachable when emit_fn raises post-write (OQ-B=A)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _raising_emit(self, event: dict[str, Any]) -> None:
        raise RuntimeError("emit_fn intentionally raises")

    def test_file_on_disk_when_emit_fn_raises(self) -> None:
        target = str(Path(self._tmp.name) / "skill-a.user.toml")
        try:
            write_override(
                plane="toml",
                target_file=target,
                accepted_content='agent.icon = "🎯"\n',
                skill_id="mock-module/skill-a",
                install_dir=".",
                compile_py=_COMPILE_PY,
                emit_fn=self._raising_emit,
            )
        except RuntimeError:
            pass
        self.assertTrue(Path(target).exists())

    def test_revert_delete_reachable_from_shell_exception_handler(self) -> None:
        target = str(Path(self._tmp.name) / "skill-a.user.toml")
        events: list[dict[str, Any]] = []
        try:
            write_override(
                plane="toml",
                target_file=target,
                accepted_content='agent.icon = "🎯"\n',
                skill_id="mock-module/skill-a",
                install_dir=".",
                compile_py=_COMPILE_PY,
                emit_fn=self._raising_emit,
            )
        except RuntimeError:
            revert_override(target, pre_write_content=None, emit_fn=events.append)
        self.assertGreater(len(events), 0, "revert_override did not emit revert_complete")
        self.assertFalse(Path(target).exists())
        self.assertEqual(events[-1]["action"], "revert_complete")
        self.assertIs(events[-1]["deleted"], True)

    def test_revert_restore_reachable_from_shell_exception_handler(self) -> None:
        target = str(Path(self._tmp.name) / "skill-a.user.toml")
        Path(target).write_text("prior content\n", encoding="utf-8")
        events: list[dict[str, Any]] = []
        try:
            write_override(
                plane="toml",
                target_file=target,
                accepted_content='agent.icon = "🎯"\n',
                skill_id="mock-module/skill-a",
                install_dir=".",
                compile_py=_COMPILE_PY,
                emit_fn=self._raising_emit,
            )
        except RuntimeError:
            revert_override(target, pre_write_content="prior content\n", emit_fn=events.append)
        self.assertGreater(len(events), 0, "revert_override did not emit revert_complete")
        self.assertEqual(Path(target).read_text(encoding="utf-8"), "prior content\n")
        self.assertEqual(events[-1]["action"], "revert_complete")
        self.assertIs(events[-1]["deleted"], False)


# ---------------------------------------------------------------------------
# AC-3 (7.9): write_override --diff failure protocol event (OQ-B=A, OQ-C=A)
# ---------------------------------------------------------------------------


class TestWriteOverrideDiffFailed(unittest.TestCase):
    """write_override must emit diff_failed before raising when --diff subprocess fails."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _failing_run(
        self, args: list[str], *a: Any, **kw: Any
    ) -> "subprocess.CompletedProcess[str]":
        raise subprocess.CalledProcessError(
            returncode=1, cmd=args, stderr="mock compile --diff error"
        )

    def _failing_run_long_stderr(
        self, args: list[str], *a: Any, **kw: Any
    ) -> "subprocess.CompletedProcess[str]":
        raise subprocess.CalledProcessError(
            returncode=1, cmd=args, stderr="x" * 600
        )

    def _failing_run_no_stderr(
        self, args: list[str], *a: Any, **kw: Any
    ) -> "subprocess.CompletedProcess[str]":
        raise subprocess.CalledProcessError(returncode=2, cmd=args)

    def test_diff_failed_event_emitted(self) -> None:
        target = str(Path(self._tmp.name) / "skill-a.user.toml")
        events: list[dict[str, Any]] = []
        try:
            write_override(
                plane="toml",
                target_file=target,
                accepted_content='agent.icon = "🎯"\n',
                skill_id="mock-module/skill-a",
                install_dir=".",
                compile_py=_COMPILE_PY,
                emit_fn=events.append,
                run_fn=self._failing_run,
            )
        except BmadSubprocessError:
            pass
        # R1-AA-4: exactly one diff_failed per invocation
        diff_failed_events = [e for e in events if e["action"] == "diff_failed"]
        self.assertEqual(len(diff_failed_events), 1)

    def test_diff_failed_event_has_required_fields(self) -> None:
        target = str(Path(self._tmp.name) / "skill-a.user.toml")
        events: list[dict[str, Any]] = []
        try:
            write_override(
                plane="toml",
                target_file=target,
                accepted_content='agent.icon = "🎯"\n',
                skill_id="mock-module/skill-a",
                install_dir=".",
                compile_py=_COMPILE_PY,
                emit_fn=events.append,
                run_fn=self._failing_run,
            )
        except BmadSubprocessError:
            pass
        fail_evt = next(e for e in events if e.get("action") == "diff_failed")
        # R1-AA-5/ECH-3: verify field presence AND correct values
        self.assertEqual(fail_evt["skill_id"], "mock-module/skill-a")
        self.assertEqual(fail_evt["returncode"], 1)
        self.assertIn("mock compile --diff error", fail_evt["stderr_excerpt"])

    def test_write_override_complete_precedes_diff_failed(self) -> None:
        # Sequence contract: write_override_complete fires BEFORE diff_failed
        target = str(Path(self._tmp.name) / "skill-a.user.toml")
        events: list[dict[str, Any]] = []
        try:
            write_override(
                plane="toml",
                target_file=target,
                accepted_content='agent.icon = "🎯"\n',
                skill_id="mock-module/skill-a",
                install_dir=".",
                compile_py=_COMPILE_PY,
                emit_fn=events.append,
                run_fn=self._failing_run,
            )
        except BmadSubprocessError:
            pass
        actions = [e["action"] for e in events]
        self.assertIn("write_override_complete", actions)
        self.assertIn("diff_failed", actions)
        self.assertLess(
            actions.index("write_override_complete"),
            actions.index("diff_failed"),
        )
        # R2-BH-R2-2: propose_diff_review must NOT appear
        self.assertNotIn("propose_diff_review", actions)

    def test_file_written_before_diff_failed_emitted(self) -> None:
        # R1-L-3: file must be on disk (write_text succeeded before _run fired)
        target = str(Path(self._tmp.name) / "skill-a.user.toml")
        try:
            write_override(
                plane="toml",
                target_file=target,
                accepted_content='agent.icon = "🎯"\n',
                skill_id="mock-module/skill-a",
                install_dir=".",
                compile_py=_COMPILE_PY,
                emit_fn=lambda _: None,
                run_fn=self._failing_run,
            )
        except BmadSubprocessError:
            pass
        self.assertTrue(Path(target).exists())

    def test_stderr_excerpt_truncated_at_500(self) -> None:
        # M-1: stderr longer than 500 chars must be truncated to exactly 500
        target = str(Path(self._tmp.name) / "skill-a.user.toml")
        events: list[dict[str, Any]] = []
        try:
            write_override(
                plane="toml",
                target_file=target,
                accepted_content='agent.icon = "🎯"\n',
                skill_id="mock-module/skill-a",
                install_dir=".",
                compile_py=_COMPILE_PY,
                emit_fn=events.append,
                run_fn=self._failing_run_long_stderr,
            )
        except BmadSubprocessError:
            pass
        fail_evt = next(e for e in events if e.get("action") == "diff_failed")
        self.assertEqual(len(fail_evt["stderr_excerpt"]), 500)

    def test_stderr_none_produces_empty_string(self) -> None:
        # M-2: CalledProcessError with stderr=None must yield stderr_excerpt=""
        target = str(Path(self._tmp.name) / "skill-a.user.toml")
        events: list[dict[str, Any]] = []
        try:
            write_override(
                plane="toml",
                target_file=target,
                accepted_content='agent.icon = "🎯"\n',
                skill_id="mock-module/skill-a",
                install_dir=".",
                compile_py=_COMPILE_PY,
                emit_fn=events.append,
                run_fn=self._failing_run_no_stderr,
            )
        except BmadSubprocessError:
            pass
        fail_evt = next(e for e in events if e.get("action") == "diff_failed")
        self.assertEqual(fail_evt["stderr_excerpt"], "")


# ---------------------------------------------------------------------------
# AC-1 (7.10): check=True kwarg forwarded to _run (L668)
# ---------------------------------------------------------------------------


class TestWriteOverrideCheckTruePassed(unittest.TestCase):
    """write_override must forward check=True to the _run callable."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._check_kwarg_seen: bool = False

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _check_asserting_run(
        self, args: list[str], *a: Any, **kw: Any
    ) -> "subprocess.CompletedProcess[str]":
        self._check_kwarg_seen = kw.get("check") is True
        raise subprocess.CalledProcessError(
            returncode=1, cmd=args, stderr="check=True path verified"
        )

    def test_check_true_kwarg_forwarded_to_run(self) -> None:
        target = str(Path(self._tmp.name) / "skill-a.user.toml")
        try:
            write_override(
                plane="toml",
                target_file=target,
                accepted_content='agent.icon = "🎯"\n',
                skill_id="mock-module/skill-a",
                install_dir=".",
                compile_py=_COMPILE_PY,
                emit_fn=lambda _: None,
                run_fn=self._check_asserting_run,
            )
        except BmadSubprocessError:
            pass
        self.assertTrue(
            self._check_kwarg_seen,
            "write_override must forward check=True to _run; kwarg was absent or False",
        )

    def test_check_true_path_exercises_diff_failed_handler(self) -> None:
        # When check=True fires (non-zero returncode), diff_failed must be emitted
        target = str(Path(self._tmp.name) / "skill-a.user.toml")
        events: list[dict[str, Any]] = []
        try:
            write_override(
                plane="toml",
                target_file=target,
                accepted_content='agent.icon = "🎯"\n',
                skill_id="mock-module/skill-a",
                install_dir=".",
                compile_py=_COMPILE_PY,
                emit_fn=events.append,
                run_fn=self._check_asserting_run,
            )
        except BmadSubprocessError:
            pass
        self.assertEqual(
            sum(1 for e in events if e.get("action") == "diff_failed"), 1
        )


# ---------------------------------------------------------------------------
# AC-2 (7.10): filesystem state byte-identical to accepted_content at diff time (L670)
# ---------------------------------------------------------------------------


class TestWriteOverrideFilesystemStateAtDiff(unittest.TestCase):
    """Filesystem state is byte-identical to accepted_content at --diff invocation."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._target = str(Path(self._tmp.name) / "_bmad" / "custom" / "skill-a.user.toml")
        self._file_exists_at_diff: bool = False
        self._file_content_at_diff: str | None = None
        self._custom_files_at_diff: list[Path] = []

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _snapshot_run(
        self, args: list[str], *a: Any, **kw: Any
    ) -> "subprocess.CompletedProcess[str]":
        assert "--diff" in args, f"_snapshot_run called for unexpected command: {args}"
        target = Path(self._target)
        self._file_exists_at_diff = target.exists()
        if self._file_exists_at_diff:
            self._file_content_at_diff = target.read_text(encoding="utf-8")
        custom_dir = Path(self._tmp.name) / "_bmad" / "custom"
        self._custom_files_at_diff = [p for p in custom_dir.rglob("*") if p.is_file()]
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout="--- diff ---\n+++ change\n"
        )

    def _run_write(self) -> None:
        write_override(
            plane="toml",
            target_file=self._target,
            accepted_content='agent.icon = "🎯"\n',
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
            emit_fn=lambda _: None,
            run_fn=self._snapshot_run,
        )

    def test_target_file_exists_at_diff_invocation(self) -> None:
        self._run_write()
        self.assertTrue(
            self._file_exists_at_diff,
            "target_file must exist on disk when --diff _run is called",
        )

    def test_target_file_content_byte_identical_at_diff_invocation(self) -> None:
        self._run_write()
        self.assertEqual(self._file_content_at_diff, 'agent.icon = "🎯"\n')

    def test_no_extra_files_under_custom_at_diff_invocation(self) -> None:
        self._run_write()
        extra = [p for p in self._custom_files_at_diff if p != Path(self._target)]
        self.assertEqual(
            extra, [],
            f"write_override created unexpected files before --diff call: {extra}",
        )


# ---------------------------------------------------------------------------
# AC-3 (7.10): write_override creates parents; revert_override does not (L672)
# ---------------------------------------------------------------------------


class TestWriteOverrideMkdirAsymmetry(unittest.TestCase):
    """write_override creates parents; revert_override does not — intentional contract."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--diff", "diff-icon-change.txt")
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_write_override_creates_nested_parent_dirs(self) -> None:
        # Confirms parents=True behaviour: 3 levels deep, no pre-existing dirs
        target = str(Path(self._tmp.name) / "a" / "b" / "c" / "skill-a.user.toml")
        run_handler_with_mock(
            write_override,
            self.mock,
            plane="toml",
            target_file=target,
            accepted_content='agent.icon = "🎯"\n',
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )
        self.assertTrue((Path(self._tmp.name) / "a" / "b" / "c").is_dir())
        self.assertTrue(Path(target).exists())

    def test_revert_override_delete_noops_when_parent_missing(self) -> None:
        # revert_override delete branch: exists() guard silently no-ops on missing parent
        target = str(Path(self._tmp.name) / "missing_parent" / "skill-a.user.toml")
        events: list[dict[str, Any]] = []
        # No FileNotFoundError — exists() returns False → unlink skipped → revert_complete fires
        revert_override(target, pre_write_content=None, emit_fn=events.append)
        self.assertFalse(Path(target).parent.exists())
        self.assertEqual(len(events), 1)
        self.assertEqual(events[-1]["action"], "revert_complete")
        self.assertIs(events[-1]["deleted"], True)

    def test_revert_override_restore_raises_when_parent_missing(self) -> None:
        """Intentional contract: revert_override restore branch assumes the parent dir
        exists because write_override always creates it before the LLM shell invokes
        revert_override. Raw FileNotFoundError is correct behaviour (OQ-A=A, Phil 2026-05-09);
        no BmadSubprocessError wrap is needed or desired."""
        target = str(Path(self._tmp.name) / "missing_parent" / "skill-a.user.toml")
        with self.assertRaises(FileNotFoundError):
            revert_override(target, pre_write_content="prior content\n", emit_fn=lambda _: None)


if __name__ == "__main__":
    unittest.main()
