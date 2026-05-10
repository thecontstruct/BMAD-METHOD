"""Story 6.4: Drafting handler tests — propose_draft events and no-disk-write
contract.

Covers AC-1 (propose_draft emitted for TOML and prose planes), AC-2 (no
filesystem mutations during handler execution + structural lockfile check),
AC-3 (multiple iterations, all stateless, no writes), AC-4 (revision_feedback
echoed in event, no staging files).
"""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

# Add test/ to path for harness.* imports
_TEST_DIR = Path(__file__).resolve().parent.parent
if str(_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_TEST_DIR))

# Add src/scripts to path for bmad_customize.* imports
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from bmad_customize._errors import BmadSubprocessError
from bmad_customize.drafting import draft_content
from harness.mock_compiler import MockCompiler
from harness.skill_test_runner import run_handler_with_mock

_FIXTURES_ROOT = _TEST_DIR / "fixtures" / "customize-mocks"
_COMPILE_PY = _SCRIPTS_DIR / "compile.py"

_GUARD_MSG = (
    "MockCompiler.calls is empty after skill invocation -- "
    "run_handler_with_mock seam wiring broken."
)


# ---------------------------------------------------------------------------
# AC-1: TOML plane propose_draft
# ---------------------------------------------------------------------------


class TestDraftTOML(unittest.TestCase):
    """draft_content with explain-icon-clean.json: TOML propose_draft."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--explain --json", "explain-icon-clean.json")

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(
            draft_content,
            self.mock,
            intent="change the icon from 📋 to 🎯",
            plane="toml",
            field_path="icon",
            fragment_name=None,
            target_file="_bmad/custom/skill-a.user.toml",
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )

    def test_propose_draft_emitted(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["action"], "propose_draft")
        self.assertNotIn("revision_feedback", events[-1])

    def test_plane_is_toml(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["plane"], "toml")

    def test_field_path_in_event(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["field_path"], "icon")

    def test_target_file_is_user_toml(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["target_file"], "_bmad/custom/skill-a.user.toml")

    def test_current_value_in_event(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["current_value"], "📋")

    def test_requires_confirmation_true(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertIs(events[-1]["requires_confirmation"], True)

    def test_no_disk_write_on_toml_draft(self) -> None:
        with patch("pathlib.Path.write_text") as mock_write:
            self._run()
            mock_write.assert_not_called()


# ---------------------------------------------------------------------------
# AC-1: Prose plane propose_draft
# ---------------------------------------------------------------------------


class TestDraftProse(unittest.TestCase):
    """draft_content with explain-prose-menu-handler.json: prose propose_draft."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--explain --json", "explain-prose-menu-handler.json")

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(
            draft_content,
            self.mock,
            intent="rewrite the menu handler to be more concise",
            plane="prose",
            field_path=None,
            fragment_name="menu-handler",
            target_file="_bmad/custom/fragments/mock-module/skill-a/menu-handler.template.md",
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )

    def test_propose_draft_emitted(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["action"], "propose_draft")

    def test_plane_is_prose(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["plane"], "prose")

    def test_fragment_name_in_event(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["fragment_name"], "menu-handler")

    def test_target_file_in_event(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(
            events[-1]["target_file"],
            "_bmad/custom/fragments/mock-module/skill-a/menu-handler.template.md",
        )

    def test_requires_confirmation_true(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertIs(events[-1]["requires_confirmation"], True)


# ---------------------------------------------------------------------------
# AC-2: No-disk-write contract + structural lock-file assertion
# ---------------------------------------------------------------------------


class TestNoDiskWriteContract(unittest.TestCase):
    """Behavioral and structural verification that draft_content never writes."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--explain --json", "explain-icon-clean.json")
        self.mock_prose = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock_prose.register("--explain --json", "explain-prose-menu-handler.json")

    def _run_toml(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(
            draft_content,
            self.mock,
            intent="change the icon from 📋 to 🎯",
            plane="toml",
            field_path="icon",
            fragment_name=None,
            target_file="_bmad/custom/skill-a.user.toml",
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )

    def _run_prose(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(
            draft_content,
            self.mock_prose,
            intent="rewrite the menu handler to be more concise",
            plane="prose",
            field_path=None,
            fragment_name="menu-handler",
            target_file="_bmad/custom/fragments/mock-module/skill-a/menu-handler.template.md",
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )

    def test_no_write_text_on_toml_draft(self) -> None:
        with patch("pathlib.Path.write_text") as mock_write:
            self._run_toml()
            mock_write.assert_not_called()

    def test_no_write_bytes_on_toml_draft(self) -> None:
        with patch("pathlib.Path.write_bytes") as mock_write:
            self._run_toml()
            mock_write.assert_not_called()

    def test_no_write_text_on_prose_draft(self) -> None:
        with patch("pathlib.Path.write_text") as mock_write:
            self._run_prose()
            mock_write.assert_not_called()

    def test_bmad_lock_not_referenced(self) -> None:
        import inspect

        import bmad_customize.drafting as mod
        src = inspect.getsource(mod)
        self.assertNotIn("lockfile", src.lower())
        self.assertNotIn("bmad.lock", src)


# ---------------------------------------------------------------------------
# AC-3: Iteration — multiple draft calls, no shared state, no writes
# ---------------------------------------------------------------------------


class TestDraftIteration(unittest.TestCase):
    """Multiple drafting iterations: each call independent, no writes."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--explain --json", "explain-icon-clean.json")

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(
            draft_content,
            self.mock,
            intent="change icon to 🎯",
            plane="toml",
            field_path="icon",
            fragment_name=None,
            target_file="_bmad/custom/skill-a.user.toml",
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )

    def test_first_iteration_propose_draft(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["action"], "propose_draft")

    def test_second_iteration_propose_draft(self) -> None:
        fresh_mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        fresh_mock.register("--explain --json", "explain-icon-clean.json")
        events = run_handler_with_mock(
            draft_content,
            fresh_mock,
            intent="change icon to 🌟",
            plane="toml",
            field_path="icon",
            fragment_name=None,
            target_file="_bmad/custom/skill-a.user.toml",
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )
        self.assertGreater(len(fresh_mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["action"], "propose_draft")

    def test_no_disk_write_on_any_iteration(self) -> None:
        with patch("pathlib.Path.write_text") as mock_write:
            self._run()
            self._run()
            mock_write.assert_not_called()


# ---------------------------------------------------------------------------
# AC-4: Revision feedback echoed; no staging files on revision
# ---------------------------------------------------------------------------


class TestDraftRevision(unittest.TestCase):
    """draft_content with revision_feedback: key echoed, still no writes."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--explain --json", "explain-icon-clean.json")

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(
            draft_content,
            self.mock,
            intent="change the icon from 📋 to 🎯",
            plane="toml",
            field_path="icon",
            fragment_name=None,
            target_file="_bmad/custom/skill-a.user.toml",
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
            revision_feedback="actually use a lightning bolt emoji instead",
        )

    def test_revision_feedback_in_event(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(
            events[-1]["revision_feedback"],
            "actually use a lightning bolt emoji instead",
        )

    def test_propose_draft_on_revision(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["action"], "propose_draft")

    def test_no_disk_write_on_revision(self) -> None:
        with patch("pathlib.Path.write_text") as mock_write:
            self._run()
            mock_write.assert_not_called()


# ---------------------------------------------------------------------------
# Story 7.11 AC-2: draft_content subprocess input validation (L607/L611/L613)
# ---------------------------------------------------------------------------


class TestDraftContentInputValidation(unittest.TestCase):
    """draft_content raises BmadSubprocessError on missing compile_py or sys.executable."""

    def _call(
        self,
        compile_py: Path | None = None,
        run_fn: Any | None = None,
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        kwargs: dict[str, Any] = {}
        if run_fn is not None:
            kwargs["run_fn"] = run_fn
        draft_content(
            intent="icon",
            plane="toml",
            field_path="icon",
            fragment_name=None,
            target_file="skill-a.user.toml",
            skill_id="mock/skill-a",
            install_dir=".",
            compile_py=compile_py if compile_py is not None else _COMPILE_PY,
            emit_fn=events.append,
            **kwargs,
        )
        return events

    def test_missing_compile_py_raises_before_subprocess(self) -> None:
        missing = Path("/nonexistent/path/compile.py")
        with self.assertRaises(BmadSubprocessError) as cm:
            self._call(compile_py=missing)
        self.assertIn("not found", str(cm.exception).lower())

    def test_missing_compile_py_raises_bmad_not_file_not_found(self) -> None:
        # Must NOT propagate raw FileNotFoundError; must wrap in BmadSubprocessError.
        missing = Path("/nonexistent/path/compile.py")
        try:
            self._call(compile_py=missing)
        except BmadSubprocessError:
            pass  # expected
        except FileNotFoundError:
            self.fail("FileNotFoundError must be wrapped in BmadSubprocessError")

    def test_sys_executable_validation_raises_on_nonexistent(self) -> None:
        # Patch sys.executable IN the drafting module so the existence check
        # sees the nonexistent path. compile_py exists; only sys.executable fails.
        # Patch the attribute (not the whole sys module) for surgical isolation.
        with patch("bmad_customize.drafting.sys.executable", "/nonexistent/python"):
            with self.assertRaises(BmadSubprocessError) as cm:
                self._call()
        self.assertIn("executable", str(cm.exception).lower())


# ---------------------------------------------------------------------------
# Story 7.11 AC-3: draft_content caller-contract enforcement (L622/L624/L626)
# ---------------------------------------------------------------------------


class TestDraftContentContractEnforcement(unittest.TestCase):
    """draft_content raises on malformed toml_fields, multi-segment field_path,
    and empty-string revision_feedback (OQ-B=A, OQ-D=A)."""

    @staticmethod
    def _run_fn_with_fields(toml_fields: list[Any]) -> Any:
        import json as _json
        payload = {"toml_fields": toml_fields, "fragments": []}

        def _run_fn(args: list[str], *a: Any, **kw: Any) -> "subprocess.CompletedProcess[str]":
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout=_json.dumps(payload), stderr=""
            )
        return _run_fn

    def test_non_dict_toml_field_raises(self) -> None:
        events: list[dict[str, Any]] = []
        run_fn = self._run_fn_with_fields(["icon", "logo"])  # strings, not dicts
        with self.assertRaises(BmadSubprocessError) as cm:
            draft_content(
                intent="icon",
                plane="toml",
                field_path="icon",
                fragment_name=None,
                target_file="x.toml",
                skill_id="mock/skill-a",
                install_dir=".",
                compile_py=_COMPILE_PY,
                emit_fn=events.append,
                run_fn=run_fn,
            )
        self.assertIn("not a dict", str(cm.exception).lower())

    def test_non_dict_raises_not_attribute_error(self) -> None:
        events: list[dict[str, Any]] = []
        run_fn = self._run_fn_with_fields([None, 42])
        try:
            draft_content(
                intent="icon",
                plane="toml",
                field_path="icon",
                fragment_name=None,
                target_file="x.toml",
                skill_id="mock/skill-a",
                install_dir=".",
                compile_py=_COMPILE_PY,
                emit_fn=events.append,
                run_fn=run_fn,
            )
        except BmadSubprocessError:
            pass
        except AttributeError:
            self.fail("AttributeError must be wrapped in BmadSubprocessError")

    def test_multi_segment_field_path_raises(self) -> None:
        events: list[dict[str, Any]] = []
        run_fn = self._run_fn_with_fields([{"path": "commands.icon", "current_value": "x"}])
        with self.assertRaises(BmadSubprocessError) as cm:
            draft_content(
                intent="icon",
                plane="toml",
                field_path="commands.menu.icon",  # multi-segment
                fragment_name=None,
                target_file="x.toml",
                skill_id="mock/skill-a",
                install_dir=".",
                compile_py=_COMPILE_PY,
                emit_fn=events.append,
                run_fn=run_fn,
            )
        self.assertIn("multi-segment", str(cm.exception).lower())

    def test_empty_revision_feedback_raises(self) -> None:
        mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        mock.register("--explain --json", "explain-icon-clean.json")
        with self.assertRaises(BmadSubprocessError) as cm:
            run_handler_with_mock(
                draft_content,
                mock,
                intent="icon",
                plane="toml",
                field_path="icon",
                fragment_name=None,
                target_file="x.toml",
                skill_id="mock/skill-a",
                install_dir=".",
                compile_py=_COMPILE_PY,
                revision_feedback="",  # empty string — invalid per OQ-D=A
            )
        self.assertIn("revision_feedback", str(cm.exception))


# ---------------------------------------------------------------------------
# Story 7.11 AC-6: draft_content TOML field-not-found graceful degradation (L615)
# ---------------------------------------------------------------------------


class TestDraftTOMLFieldNotFound(unittest.TestCase):
    """TOML field-not-found: propose_draft emitted without current_value
    (graceful degradation, not a raise)."""

    def test_field_not_found_emits_propose_draft(self) -> None:
        # explain-icon-clean.json has only "agent.icon"; request a nonexistent
        # field so the loop terminates without setting current_value.
        mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        mock.register("--explain --json", "explain-icon-clean.json")
        events = run_handler_with_mock(
            draft_content,
            mock,
            intent="icon",
            plane="toml",
            field_path="nonexistent_field_xyz",
            fragment_name=None,
            target_file="x.toml",
            skill_id="mock/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )
        propose = next((e for e in events if e.get("action") == "propose_draft"), None)
        self.assertIsNotNone(propose, "propose_draft must be emitted even when field not found")

    def test_field_not_found_no_current_value(self) -> None:
        mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        mock.register("--explain --json", "explain-icon-clean.json")
        events = run_handler_with_mock(
            draft_content,
            mock,
            intent="icon",
            plane="toml",
            field_path="nonexistent_field_xyz",
            fragment_name=None,
            target_file="x.toml",
            skill_id="mock/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )
        propose = next(e for e in events if e.get("action") == "propose_draft")
        self.assertNotIn(
            "current_value", propose,
            "current_value must be absent when field_path is not found",
        )


if __name__ == "__main__":
    unittest.main()
