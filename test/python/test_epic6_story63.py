"""Story 6.3: Routing handler tests — plane routing and intent negotiation.

Covers AC-1 (TOML route), AC-2 (prose route), AC-3 (multi-plane
disambiguation), AC-4 (full-skill warning, no compile call).
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
from bmad_customize.routing import _match_prose, route_intent
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


# ---------------------------------------------------------------------------
# AC-1 (7.9): _match_prose empty-name wildcard guard
# ---------------------------------------------------------------------------


class TestMatchProseEmptyName(unittest.TestCase):
    """_match_prose must skip fragments whose normalized name is empty."""

    def test_empty_name_not_matched(self) -> None:
        # "fragments/.template.md" → name="" → must NOT wildcard-match any intent
        frags = [{"src": "fragments/.template.md"}]
        result = _match_prose(frags, ["icon", "change", "update"], "mock-module/skill-a")
        self.assertEqual(result, [])

    def test_normal_fragment_still_matches_after_guard(self) -> None:
        # Regression: valid fragment still resolves after empty-name guard is added
        frags = [{"src": "fragments/preflight.template.md"}]
        result = _match_prose(frags, ["preflight"], "mock-module/skill-a")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["fragment_name"], "preflight")

    def test_mixed_fragments_empty_skipped(self) -> None:
        # Both a degenerate and a valid fragment present: only valid one matches
        frags = [
            {"src": "fragments/.template.md"},
            {"src": "fragments/preflight.template.md"},
        ]
        result = _match_prose(frags, ["preflight"], "mock-module/skill-a")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["fragment_name"], "preflight")

    def test_dot_only_name_not_matched(self) -> None:
        # R1-ECH-1: ".template.md" (no "fragments/" prefix) → name="." after suffix strip
        # "." passes bare `if not name:` but must be caught by extended guard
        frags = [{"src": ".template.md"}]
        result = _match_prose(frags, ["icon", "change", "update"], "mock-module/skill-a")
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# AC-2 (7.9): _match_prose slash-in-name path-separator guard (OQ-A=A)
# ---------------------------------------------------------------------------


class TestMatchProseSlashInName(unittest.TestCase):
    """_match_prose must strip nested-path slashes from fragment names."""

    def test_nested_fragment_name_is_basename_only(self) -> None:
        frags = [{"src": "fragments/sub/nested.template.md"}]
        result = _match_prose(frags, ["nested"], "mock-module/skill-a")
        self.assertEqual(len(result), 1)
        self.assertNotIn("/", result[0]["fragment_name"])
        self.assertEqual(result[0]["fragment_name"], "nested")

    def test_nested_fragment_target_file_no_nested_path(self) -> None:
        frags = [{"src": "fragments/sub/nested.template.md"}]
        result = _match_prose(frags, ["nested"], "mock-module/skill-a")
        self.assertEqual(len(result), 1)
        # R2-ECH-R2-3: basename of target_file must equal "nested.template.md" exactly
        self.assertEqual(result[0]["target_file"].rsplit("/", 1)[-1], "nested.template.md")

    def test_non_nested_fragment_unaffected(self) -> None:
        # Regression: flat fragment path unchanged by basename extraction
        frags = [{"src": "fragments/preflight.template.md"}]
        result = _match_prose(frags, ["preflight"], "mock-module/skill-a")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["fragment_name"], "preflight")

    def test_nested_dot_template_not_matched(self) -> None:
        # R1-ECH-2: "fragments/sub/.template.md" → after suffix strip → "sub/" → basename → ""
        # Must NOT wildcard-match (proves guard fires after basename extraction)
        frags = [{"src": "fragments/sub/.template.md"}]
        result = _match_prose(frags, ["icon", "change", "update"], "mock-module/skill-a")
        self.assertEqual(result, [])

    def test_collision_raises_error_with_both_srcs(self) -> None:
        # DN-7.9-2=B: two fragments with same basename from different subdirs → raise
        frags = [
            {"src": "fragments/sub-a/widget.template.md"},
            {"src": "fragments/sub-b/widget.template.md"},
        ]
        with self.assertRaises(BmadSubprocessError) as ctx:
            _match_prose(frags, ["widget"], "mock-module/skill-a")
        msg = str(ctx.exception)
        self.assertIn("widget", msg)
        self.assertIn("fragments/sub-a/widget.template.md", msg)
        self.assertIn("fragments/sub-b/widget.template.md", msg)


# ---------------------------------------------------------------------------
# Story 7.11 AC-1: route_intent schema_version forward-compat guard (L590)
# ---------------------------------------------------------------------------


class TestRouteIntentSchemaVersion(unittest.TestCase):
    """schema_version guard in route_intent (OQ-A=A).

    Uses an intent that does NOT match _FULL_SKILL_PHRASES so route_intent
    proceeds past step (1) and invokes the compiler — exercising the guard.
    """

    @staticmethod
    def _run_with_version(schema_version: int | None) -> list[dict[str, Any]]:
        import json as _json
        payload: dict[str, Any] = {"toml_fields": [], "fragments": []}
        if schema_version is not None:
            payload["schema_version"] = schema_version

        def _run_fn(args: list[str], *a: Any, **kw: Any) -> "subprocess.CompletedProcess[str]":
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout=_json.dumps(payload), stderr=""
            )
        events: list[dict[str, Any]] = []
        route_intent(
            intent="change icon",
            skill_id="mock/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
            emit_fn=events.append,
            run_fn=_run_fn,
        )
        return events

    def test_schema_version_absent_passes(self) -> None:
        # Must not raise; routing emits a request_plane_disambiguation with empty
        # candidates because no fields/fragments are present in payload.
        self._run_with_version(None)

    def test_schema_version_1_passes(self) -> None:
        self._run_with_version(1)

    def test_schema_version_2_raises(self) -> None:
        with self.assertRaises(BmadSubprocessError) as cm:
            self._run_with_version(2)
        self.assertIn("schema_version", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
