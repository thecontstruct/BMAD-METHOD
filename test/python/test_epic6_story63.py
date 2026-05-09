"""Story 6.3: Routing handler tests — plane routing and intent negotiation.

Covers AC-1 (TOML route), AC-2 (prose route), AC-3 (multi-plane
disambiguation), AC-4 (full-skill warning, no compile call).
"""

from __future__ import annotations

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

from bmad_customize.routing import route_intent
from harness.mock_compiler import MockCompiler
from harness.skill_test_runner import run_handler_with_mock

_FIXTURES_ROOT = _TEST_DIR / "fixtures" / "customize-mocks"
_COMPILE_PY = _SCRIPTS_DIR / "compile.py"

_GUARD_MSG = (
    "MockCompiler.calls is empty after skill invocation -- "
    "run_handler_with_mock seam wiring broken."
)


# ---------------------------------------------------------------------------
# AC-1: TOML route
# ---------------------------------------------------------------------------


class TestRouteTOML(unittest.TestCase):
    """route_intent with explain-icon-clean.json: propose_route toml."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--explain --json", "explain-icon-clean.json")

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(
            route_intent,
            self.mock,
            intent="change the icon from 📋 to 🎯",
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )

    def test_propose_route_emitted(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["action"], "propose_route")

    def test_plane_is_toml(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["plane"], "toml")

    def test_field_path_is_icon(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["field_path"], "icon")

    def test_target_file_is_user_toml(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["target_file"], "_bmad/custom/skill-a.user.toml")

    def test_requires_confirmation_true(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertIs(events[-1]["requires_confirmation"], True)

    def test_no_write_event_emitted(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertTrue(all(e["action"] != "write" for e in events))


# ---------------------------------------------------------------------------
# AC-2: Prose route
# ---------------------------------------------------------------------------


class TestRouteProse(unittest.TestCase):
    """route_intent with explain-prose-menu-handler.json: propose_route prose."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--explain --json", "explain-prose-menu-handler.json")

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(
            route_intent,
            self.mock,
            intent="rewrite the menu handler to be more concise",
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )

    def test_propose_route_emitted(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["action"], "propose_route")

    def test_plane_is_prose(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["plane"], "prose")

    def test_fragment_name_is_menu_handler(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["fragment_name"], "menu-handler")

    def test_target_file_contains_fragment_path(self) -> None:
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
# AC-3: Multi-plane disambiguation
# ---------------------------------------------------------------------------


class TestRoutePlaneDisambiguation(unittest.TestCase):
    """route_intent with explain-multi-plane-greeting.json: cross-plane disambig."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--explain --json", "explain-multi-plane-greeting.json")

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(
            route_intent,
            self.mock,
            intent="update the greeting and activation flow",
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )

    def test_plane_disambiguation_emitted(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertIn("request_plane_disambiguation", [e["action"] for e in events])

    def test_candidates_has_toml_entry(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertTrue(len(events) >= 1, "no events emitted")
        self.assertIn(
            "candidates", events[-1],
            f"last event has no 'candidates'; action={events[-1].get('action')}",
        )
        self.assertTrue(any(c["plane"] == "toml" for c in events[-1]["candidates"]))

    def test_candidates_has_prose_entry(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertTrue(len(events) >= 1, "no events emitted")
        self.assertIn(
            "candidates", events[-1],
            f"last event has no 'candidates'; action={events[-1].get('action')}",
        )
        self.assertTrue(any(c["plane"] == "prose" for c in events[-1]["candidates"]))

    def test_handler_suspends_after_disambiguation(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        actions = [e["action"] for e in events]
        self.assertIn(
            "request_plane_disambiguation", actions,
            f"request_plane_disambiguation not emitted; got: {actions}",
        )
        disambig_idx = actions.index("request_plane_disambiguation")
        self.assertEqual(disambig_idx, len(events) - 1)

    def test_propose_route_absent_after_disambiguation(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertTrue(all(e["action"] != "propose_route" for e in events))


# ---------------------------------------------------------------------------
# AC-4: Full-skill warning (no compile call, no MockCompiler)
# ---------------------------------------------------------------------------


class TestFullSkillWarning(unittest.TestCase):
    """route_intent with full-skill intent: warn_full_skill, no compile call.

    No MockCompiler / no run_handler_with_mock — handler returns before any
    compile call, so the mock seam is not exercised. Mock guard is intentionally
    absent (see Story 6.3 Dev Notes §8); test_no_compile_call_on_full_skill_path
    provides stronger evidence that subprocess.run is never called.
    """

    def _run(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        route_intent(
            intent="replace the entire skill with a new one",
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=Path("/nonexistent/compile.py"),
            emit_fn=events.append,
        )
        return events

    def test_warn_full_skill_emitted(self) -> None:
        events = self._run()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["action"], "warn_full_skill")

    def test_bypass_warning_is_nonempty_string(self) -> None:
        events = self._run()
        self.assertIsInstance(events[0]["bypass_warning"], str)
        self.assertTrue(events[0]["bypass_warning"])

    def test_requires_confirmation_true(self) -> None:
        events = self._run()
        self.assertIs(events[0]["requires_confirmation"], True)

    def test_requires_second_confirmation_true(self) -> None:
        events = self._run()
        self.assertIs(events[0]["requires_second_confirmation"], True)

    def test_no_write_event_emitted(self) -> None:
        events = self._run()
        self.assertTrue(all(e["action"] != "write" for e in events))

    def test_no_compile_call_on_full_skill_path(self) -> None:
        with patch("subprocess.run") as mock_run:
            self._run()
            mock_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
