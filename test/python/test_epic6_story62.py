"""Story 6.2: Discovery handler tests -- invoke from IDE chat and discover
customization surface via --explain --json mock seam.

Covers AC-1 (discover event), AC-2 (surface counts), AC-3 (disambiguation),
AC-4 (NFR-P4 call budget).

Dev spec note: Story 6.2 Dev Note 5 lists stale fixture counts. Actual counts
from committed ffe4a4d5 (used as hard-coded regression anchors here):
  explain-pristine.json:        toml_fields=2, fragments=2, variables=1
  explain-ambiguous-intent.json: toml_fields=3, fragments=2, variables=1
"""

from __future__ import annotations

import subprocess
import sys
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
from bmad_customize.discovery import discover_surface
from harness.mock_compiler import MockCompiler
from harness.skill_test_runner import run_handler_with_mock

_FIXTURES_ROOT = _TEST_DIR / "fixtures" / "customize-mocks"
_COMPILE_PY = _SCRIPTS_DIR / "compile.py"

_GUARD_MSG = (
    "MockCompiler.calls is empty after skill invocation -- "
    "run_handler_with_mock seam wiring broken."
)


# ---------------------------------------------------------------------------
# AC-1 + AC-2: Pristine discovery path
# ---------------------------------------------------------------------------


class TestDiscoveryPristine(unittest.TestCase):
    """discover_surface with explain-pristine.json: discover event first, surface counts."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--explain --json", "explain-pristine.json")

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(
            discover_surface,
            self.mock,
            intent="make this agent's greeting more formal",
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )

    def test_discover_event_is_first(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertGreaterEqual(len(events), 1, "Handler emitted no events on pristine path")
        self.assertEqual(events[0]["action"], "discover")
        self.assertEqual(events[0]["source"], "--explain --json")
        self.assertIsInstance(events[0]["skill_id"], str)
        self.assertTrue(events[0]["skill_id"])

    def test_mock_records_exactly_one_explain_call(self) -> None:
        self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        explain_calls = [c for c in self.mock.calls if "--explain --json" in c["pattern"]]
        self.assertEqual(len(explain_calls), 1)

    def test_report_surface_counts_match_fixture(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertGreaterEqual(len(events), 2, "Handler emitted fewer than 2 events on pristine path")
        self.assertEqual(events[1]["action"], "report_surface")
        # Hard-coded from explain-pristine.json at ffe4a4d5:
        # toml_fields: 2 (agent.description, agent.name)
        # fragments:   2 (fragments/intro.template.md, fragments/guide.template.md)
        # variables:   1 (self.agent.name)
        self.assertEqual(events[1]["toml_fields"], 2)
        self.assertEqual(events[1]["prose_fragments"], 2)
        self.assertEqual(events[1]["variables"], 1)


# ---------------------------------------------------------------------------
# AC-3: Ambiguous intent -- disambiguation suspends execution
# ---------------------------------------------------------------------------


class TestDiscoveryAmbiguous(unittest.TestCase):
    """discover_surface with explain-ambiguous-intent.json: disambiguation path."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--explain --json", "explain-ambiguous-intent.json")

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(
            discover_surface,
            self.mock,
            intent="change the agent icon",
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )

    def test_disambiguation_event_emitted(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertTrue(
            len(events) >= 1,
            "Handler emitted no events for ambiguous fixture -- "
            "check MockCompiler registration and run_handler_with_mock wiring.",
        )
        self.assertEqual(events[-1]["action"], "request_disambiguation")

    def test_candidates_has_at_least_two_entries(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertTrue(
            len(events) >= 1,
            "Handler emitted no events for ambiguous fixture -- "
            "check MockCompiler registration and run_handler_with_mock wiring.",
        )
        self.assertGreaterEqual(len(events[-1]["candidates"]), 2)

    def test_handler_suspends_after_disambiguation(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertTrue(
            len(events) >= 1,
            "Handler emitted no events for ambiguous fixture -- "
            "check MockCompiler registration and run_handler_with_mock wiring.",
        )
        actions = [e["action"] for e in events]
        self.assertIn(
            "request_disambiguation", actions,
            f"request_disambiguation not emitted; got: {actions}",
        )
        disambig_idx = actions.index("request_disambiguation")
        self.assertEqual(disambig_idx, len(events) - 1)

    def test_report_surface_absent_after_disambiguation(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertTrue(
            len(events) >= 1,
            "Handler emitted no events for ambiguous fixture -- "
            "check MockCompiler registration and run_handler_with_mock wiring.",
        )
        self.assertTrue(all(e["action"] != "report_surface" for e in events))


# ---------------------------------------------------------------------------
# AC-4: NFR-P4 -- <= 2 --explain --json calls per discovery turn
# ---------------------------------------------------------------------------


class TestNFRP4Budget(unittest.TestCase):
    """Each method constructs its own fresh MockCompiler (no shared state)."""

    def test_explain_call_count_within_budget(self) -> None:
        mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        mock.register("--explain --json", "explain-pristine.json")
        run_handler_with_mock(
            discover_surface,
            mock,
            intent="make greeting more formal",
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )
        self.assertGreater(len(mock.calls), 0, _GUARD_MSG)
        explain_calls = [c for c in mock.calls if "--explain --json" in c["pattern"]]
        self.assertLessEqual(len(explain_calls), 2)

    def test_explain_call_count_within_budget_ambiguous(self) -> None:
        mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        mock.register("--explain --json", "explain-ambiguous-intent.json")
        run_handler_with_mock(
            discover_surface,
            mock,
            intent="change the icon",
            skill_id="mock-module/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
        )
        self.assertGreater(len(mock.calls), 0, _GUARD_MSG)
        explain_calls = [c for c in mock.calls if "--explain --json" in c["pattern"]]
        self.assertLessEqual(len(explain_calls), 2)


# ---------------------------------------------------------------------------
# Story 7.11 AC-1: icon token-boundary anchoring (L567)
# ---------------------------------------------------------------------------


class TestDiscoverSurfaceIconAnchoring(unittest.TestCase):
    """_has_icon_token: false positives eliminated; true matches preserved."""

    @staticmethod
    def _run_with_fields(
        toml_fields: list[dict[str, Any]],
        fragments: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Run discover_surface with run_fn injection returning controlled payload."""
        import json as _json
        payload = {
            "toml_fields": toml_fields,
            "fragments": fragments or [],
            "variables": [],
        }

        def _run_fn(args: list[str], *a: Any, **kw: Any) -> "subprocess.CompletedProcess[str]":
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout=_json.dumps(payload), stderr=""
            )
        events: list[dict[str, Any]] = []
        discover_surface(
            intent="icon",
            skill_id="mock/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
            emit_fn=events.append,
            run_fn=_run_fn,
        )
        return events

    def test_substring_false_positive_catalogo_not_disambiguated(self) -> None:
        # 'catalogo.title', 'prologo.text', 'epilogo.name' contain 'logo' as
        # substring but NOT as a delimited token — must not trigger disambiguation.
        fields = [
            {"path": "catalogo.title", "current_value": "foo"},
            {"path": "prologo.text", "current_value": "bar"},
            {"path": "epilogo.name", "current_value": "baz"},
        ]
        frags = [{"src": "fragments/prologue.template.md"}]
        events = self._run_with_fields(fields, frags)
        actions = [e["action"] for e in events]
        self.assertNotIn("request_disambiguation", actions)

    def test_true_match_agent_icon_triggers_disambiguation(self) -> None:
        # 'agent.icon' and 'display.logo' have icon/logo as proper tokens.
        fields = [
            {"path": "agent.icon", "current_value": "🎯"},
            {"path": "display.logo", "current_value": "🏆"},
        ]
        frags = [{"src": "fragments/icon.template.md"}]
        events = self._run_with_fields(fields, frags)
        actions = [e["action"] for e in events]
        self.assertIn("request_disambiguation", actions)

    def test_unicode_field_no_false_positive(self) -> None:
        # 'unicode.encoding' tokenizes to ['unicode', 'encoding']. Neither token
        # equals any entry in _ICON_SUBSTRINGS, so no disambiguation fires.
        # (Pre-fix unanchored substring matching would have been at risk on any
        # path that happened to contain 'icon'/'glyph'/'emoji'/'logo' as a
        # substring of a longer token; token-boundary matching eliminates that
        # whole class of false positive.)
        fields = [{"path": "unicode.encoding", "current_value": "utf-8"}]
        events = self._run_with_fields(fields, [])
        actions = [e["action"] for e in events]
        self.assertNotIn("request_disambiguation", actions)

    def test_emoji_field_as_token_matches(self) -> None:
        # 'branding.emoji' and 'header.emoji' have 'emoji' as exact tokens.
        fields = [
            {"path": "branding.emoji", "current_value": "✨"},
            {"path": "header.emoji", "current_value": "🌟"},
        ]
        frags = [{"src": "fragments/emoji.template.md"}]
        events = self._run_with_fields(fields, frags)
        actions = [e["action"] for e in events]
        self.assertIn("request_disambiguation", actions)


# ---------------------------------------------------------------------------
# Story 7.11 AC-1: discover_surface schema_version forward-compat guard (L590)
# ---------------------------------------------------------------------------


class TestDiscoverSurfaceSchemaVersion(unittest.TestCase):
    """schema_version guard in discover_surface (OQ-A=A)."""

    @staticmethod
    def _run_with_version(schema_version: int | None) -> list[dict[str, Any]]:
        import json as _json
        payload: dict[str, Any] = {"toml_fields": [], "fragments": [], "variables": []}
        if schema_version is not None:
            payload["schema_version"] = schema_version

        def _run_fn(args: list[str], *a: Any, **kw: Any) -> "subprocess.CompletedProcess[str]":
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout=_json.dumps(payload), stderr=""
            )
        events: list[dict[str, Any]] = []
        discover_surface(
            intent="icon",
            skill_id="mock/skill-a",
            install_dir=".",
            compile_py=_COMPILE_PY,
            emit_fn=events.append,
            run_fn=_run_fn,
        )
        return events

    def test_schema_version_absent_passes(self) -> None:
        events = self._run_with_version(None)
        self.assertEqual(events[0]["action"], "discover")

    def test_schema_version_1_passes(self) -> None:
        events = self._run_with_version(1)
        self.assertEqual(events[0]["action"], "discover")

    def test_schema_version_2_raises(self) -> None:
        with self.assertRaises(BmadSubprocessError) as cm:
            self._run_with_version(2)
        self.assertIn("schema_version", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
