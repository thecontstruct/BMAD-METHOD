"""Story 6.5: Writer handler tests — post-accept write, --diff verification,
and revert-on-rejection.

Covers AC-1 (override write to exact path with sparse content), AC-2
(--diff invocation and propose_diff_review event ordering), AC-3 (revert
on diff rejection: delete-when-new vs restore-when-pre-existing).
"""
from __future__ import annotations

import os
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


if __name__ == "__main__":
    unittest.main()
