"""Story 6.7b: Robustness atomic-fix bundle tests.

Covers:
  AC-1 — CalledProcessError wrapping (discover_surface, route_intent, drift_triage)
  AC-2 — JSONDecodeError + non-dict payload guards
  AC-3 — propose_variable_provenance_shift event + total_provenance_shifts
  AC-4 — drift_triage_complete try/finally invariant

AC-5 (A1 marker cleanup) and AC-6 (UTF-8 + null coercion) are verified by code
inspection and mypy --strict; no behavioral branching warrants dedicated tests
for those ACs (per spec Dev Notes).
"""
from __future__ import annotations

import json
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
from bmad_customize.drafting import draft_content
from bmad_customize.drift import drift_triage
from bmad_customize.routing import route_intent
from harness.mock_compiler import MockCompiler
from harness.skill_test_runner import run_handler_with_mock

_FIXTURES_ROOT = _TEST_DIR / "fixtures" / "customize-mocks"
_COMPILE_PY = _SCRIPTS_DIR / "compile.py"
_UPGRADE_PY = _SCRIPTS_DIR / "upgrade.py"


def _cpe_run_fn(*_a: Any, **_kw: Any) -> subprocess.CompletedProcess[str]:
    raise subprocess.CalledProcessError(
        returncode=1, cmd=[], stderr="compile failed"
    )


def _stdout_run_fn(stdout: str) -> Any:
    def _inner(*_a: Any, **_kw: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout)
    return _inner


# ---------------------------------------------------------------------------
# AC-1: CalledProcessError wrapping
# ---------------------------------------------------------------------------


class TestCalledProcessError(unittest.TestCase):
    """Each handler raises BmadSubprocessError on subprocess.CalledProcessError;
    no events are emitted before the raise.
    """

    def test_discover_surface_cpe(self) -> None:
        events: list[dict[str, Any]] = []
        with self.assertRaises(BmadSubprocessError):
            discover_surface(
                intent="x",
                skill_id="mock/skill-a",
                compile_py=_COMPILE_PY,
                emit_fn=events.append,
                run_fn=_cpe_run_fn,
            )
        self.assertEqual(events, [])

    def test_route_intent_cpe(self) -> None:
        events: list[dict[str, Any]] = []
        with self.assertRaises(BmadSubprocessError):
            route_intent(
                intent="change icon",
                skill_id="mock/skill-a",
                compile_py=_COMPILE_PY,
                emit_fn=events.append,
                run_fn=_cpe_run_fn,
            )
        self.assertEqual(events, [])

    def test_drift_triage_cpe(self) -> None:
        events: list[dict[str, Any]] = []
        with self.assertRaises(BmadSubprocessError):
            drift_triage(
                upgrade_py=_UPGRADE_PY,
                emit_fn=events.append,
                run_fn=_cpe_run_fn,
            )
        # CalledProcessError fires pre-start, before the try/finally block
        # (per spec Task 4.1) → drift_triage_complete MUST NOT be emitted.
        self.assertEqual(events, [])


# ---------------------------------------------------------------------------
# AC-2: JSONDecodeError wrapping
# ---------------------------------------------------------------------------


class TestJsonDecodeError(unittest.TestCase):
    """Each handler raises BmadSubprocessError on invalid JSON stdout."""

    def test_discover_surface_jde(self) -> None:
        events: list[dict[str, Any]] = []
        with self.assertRaises(BmadSubprocessError):
            discover_surface(
                intent="x",
                skill_id="mock/skill-a",
                compile_py=_COMPILE_PY,
                emit_fn=events.append,
                run_fn=_stdout_run_fn("<not-json>"),
            )
        self.assertEqual(events, [])

    def test_route_intent_jde(self) -> None:
        events: list[dict[str, Any]] = []
        with self.assertRaises(BmadSubprocessError):
            route_intent(
                intent="change icon",
                skill_id="mock/skill-a",
                compile_py=_COMPILE_PY,
                emit_fn=events.append,
                run_fn=_stdout_run_fn("<not-json>"),
            )
        self.assertEqual(events, [])

    def test_drift_triage_jde(self) -> None:
        events: list[dict[str, Any]] = []
        with self.assertRaises(BmadSubprocessError):
            drift_triage(
                upgrade_py=_UPGRADE_PY,
                emit_fn=events.append,
                run_fn=_stdout_run_fn("<not-json>"),
            )
        self.assertEqual(events, [])


# ---------------------------------------------------------------------------
# AC-2: Non-dict payload guard (JSON null / array / scalar at top level)
# ---------------------------------------------------------------------------


class TestNullPayload(unittest.TestCase):
    """Each handler raises BmadSubprocessError when stdout is JSON 'null'."""

    def test_discover_surface_null(self) -> None:
        events: list[dict[str, Any]] = []
        with self.assertRaises(BmadSubprocessError):
            discover_surface(
                intent="x",
                skill_id="mock/skill-a",
                compile_py=_COMPILE_PY,
                emit_fn=events.append,
                run_fn=_stdout_run_fn("null"),
            )
        self.assertEqual(events, [])

    def test_route_intent_null(self) -> None:
        events: list[dict[str, Any]] = []
        with self.assertRaises(BmadSubprocessError):
            route_intent(
                intent="change icon",
                skill_id="mock/skill-a",
                compile_py=_COMPILE_PY,
                emit_fn=events.append,
                run_fn=_stdout_run_fn("null"),
            )
        self.assertEqual(events, [])

    def test_draft_content_null(self) -> None:
        events: list[dict[str, Any]] = []
        with self.assertRaises(BmadSubprocessError):
            draft_content(
                intent="x",
                plane="toml",
                field_path="icon",
                fragment_name=None,
                target_file="_bmad/custom/skill-a.user.toml",
                skill_id="mock/skill-a",
                compile_py=_COMPILE_PY,
                emit_fn=events.append,
                run_fn=_stdout_run_fn("null"),
            )
        self.assertEqual(events, [])


# ---------------------------------------------------------------------------
# AC-3: variable_provenance_shifts event
# ---------------------------------------------------------------------------


class TestVariableProvenanceShift(unittest.TestCase):
    """drift_triage emits propose_variable_provenance_shift with required fields
    and drift_triage_start carries total_provenance_shifts.
    """

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--dry-run --json", "dry-run-provenance-shift.json")

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(drift_triage, self.mock, upgrade_py=_UPGRADE_PY)

    def test_shift_emitted(self) -> None:
        events = self._run()
        actions = [e["action"] for e in events]
        self.assertIn("propose_variable_provenance_shift", actions)

    def test_shift_payload_fields(self) -> None:
        events = self._run()
        shifts = [e for e in events if e["action"] == "propose_variable_provenance_shift"]
        self.assertEqual(len(shifts), 1)
        evt = shifts[0]
        self.assertEqual(evt["skill"], "mock-module/skill-a")
        self.assertEqual(evt["name"], "icon")
        self.assertEqual(evt["old_source"], "toml-default")
        self.assertEqual(evt["new_source"], "user-toml")
        self.assertNotIn("requires_confirmation", evt)

    def test_start_total_provenance_shifts(self) -> None:
        events = self._run()
        self.assertEqual(events[0]["action"], "drift_triage_start")
        self.assertGreaterEqual(events[0]["total_provenance_shifts"], 1)

    def test_complete_emits_after_shifts(self) -> None:
        events = self._run()
        self.assertEqual(events[-1]["action"], "drift_triage_complete")


# ---------------------------------------------------------------------------
# AC-4: drift_triage_complete try/finally guard
# ---------------------------------------------------------------------------


class TestDriftTriageComplete(unittest.TestCase):
    """drift_triage_complete is the final event whether iteration succeeds or
    raises mid-loop (post-start failures only; pre-start failures are tested
    in TestCalledProcessError / TestJsonDecodeError / TestNullPayload).
    """

    def test_complete_emits_on_midloop_exception(self) -> None:
        # Malformed: prose_fragment_changes entry is missing the required "path"
        # key, which triggers KeyError at the change["path"] access inside the
        # iteration loop. The KeyError fires BEFORE any per-entry emit, so the
        # only events that should appear are drift_triage_start (pre-loop) and
        # drift_triage_complete (re-emitted by the finally block before the
        # exception re-raises).
        malformed = {
            "schema_version": 1,
            "drift": [
                {
                    "skill": "x",
                    "prose_fragment_changes": [{}],
                    "toml_default_changes": [],
                    "orphaned_overrides": [],
                    "new_defaults": [],
                    "glob_changes": [],
                    "variable_provenance_shifts": [],
                }
            ],
            "summary": {
                "total_skills_with_drift": 1,
                "prose_fragment_changes": 1,
                "toml_default_changes": 0,
                "orphaned_overrides": 0,
                "new_defaults": 0,
                "glob_changes": 0,
                "variable_provenance_shifts": 0,
            },
        }
        events: list[dict[str, Any]] = []
        with self.assertRaises(KeyError):
            drift_triage(
                upgrade_py=_UPGRADE_PY,
                emit_fn=events.append,
                run_fn=_stdout_run_fn(json.dumps(malformed)),
            )
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["action"], "drift_triage_start")
        self.assertEqual(events[-1]["action"], "drift_triage_complete")

    def test_complete_emits_on_no_drift(self) -> None:
        mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        mock.register("--dry-run --json", "dry-run-no-drift.json")
        events = run_handler_with_mock(
            drift_triage, mock, upgrade_py=_UPGRADE_PY,
        )
        self.assertEqual(events[-1]["action"], "drift_triage_complete")


if __name__ == "__main__":
    unittest.main()
