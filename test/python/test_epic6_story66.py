"""Story 6.6: Drift-triage handler tests — five drift types over the
dry-run-v1.json schema, plus the start/complete contract.

Covers AC-1 (prose-fragment drift), AC-2 (TOML default-value drift), AC-3
(TOML orphan drift), AC-4 (TOML new-default informational), AC-5 (glob-input
informational), AC-6 (start/complete contract + FR55: exactly one
subprocess call, no disk writes).
"""
from __future__ import annotations

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

from bmad_customize.drift import drift_triage
from harness.mock_compiler import MockCompiler
from harness.skill_test_runner import run_handler_with_mock

_FIXTURES_ROOT = _TEST_DIR / "fixtures" / "customize-mocks"
_UPGRADE_PY = _SCRIPTS_DIR / "upgrade.py"

_GUARD_MSG = (
    "MockCompiler.calls is empty after skill invocation -- "
    "run_handler_with_mock seam wiring broken."
)


# ---------------------------------------------------------------------------
# AC-1: Prose-fragment drift (three-way UX, hash-only payload)
# ---------------------------------------------------------------------------


class TestProseDrift(unittest.TestCase):
    """drift_triage with prose-drift fixture: propose_prose_drift event."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--dry-run --json", "dry-run-prose-drift.json")

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(drift_triage, self.mock, upgrade_py=_UPGRADE_PY)

    def test_propose_prose_drift_emitted(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertIn("propose_prose_drift", [e["action"] for e in events])

    def test_prose_drift_path_and_tier(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[1]["path"], "fragments/intro.template.md")
        self.assertEqual(events[1]["tier"], "user-module-fragment")

    def test_prose_drift_hashes(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[1]["old_hash"], "a1b2c3d4e5f6789012345678abcdef01")
        self.assertEqual(events[1]["new_hash"], "b2c3d4e5f6789012345678abcdef0102")
        self.assertEqual(
            events[1]["user_override_hash"],
            "e5f6789012345678abcdef0102030405",
        )

    def test_prose_drift_requires_confirmation(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertIs(events[1]["requires_confirmation"], True)

    def test_exactly_one_mock_call_per_triage(self) -> None:
        self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(len(self.mock.calls), 1)


# ---------------------------------------------------------------------------
# AC-2: TOML default-value drift (field-level review)
# ---------------------------------------------------------------------------


class TestTomlDefaultDrift(unittest.TestCase):
    """drift_triage with toml-default-drift fixture: propose_toml_default_drift."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--dry-run --json", "dry-run-toml-default-drift.json")

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(drift_triage, self.mock, upgrade_py=_UPGRADE_PY)

    def test_propose_toml_default_drift_emitted(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertIn("propose_toml_default_drift", [e["action"] for e in events])

    def test_toml_default_drift_key(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[1]["key"], "agent.name")

    def test_toml_default_drift_values(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[1]["new_value"], "SkillA-v2")
        self.assertEqual(events[1]["user_override_value"], "MyCustomSkill")
        self.assertEqual(events[1]["old_hash"], "c3d4e5f6789012345678abcdef010203")

    def test_toml_default_drift_requires_confirmation(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertIs(events[1]["requires_confirmation"], True)

    def test_exactly_one_mock_call_per_triage(self) -> None:
        self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(len(self.mock.calls), 1)


# ---------------------------------------------------------------------------
# AC-3: TOML orphan drift (override applies to removed field)
# ---------------------------------------------------------------------------


class TestTomlOrphan(unittest.TestCase):
    """drift_triage with toml-orphan fixture: propose_toml_orphan event."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--dry-run --json", "dry-run-toml-orphan.json")

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(drift_triage, self.mock, upgrade_py=_UPGRADE_PY)

    def test_propose_toml_orphan_emitted(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertIn("propose_toml_orphan", [e["action"] for e in events])

    def test_toml_orphan_payload(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(
            events[1]["path"],
            "custom/fragments/mock-module/skill-a/intro.template.md",
        )
        self.assertEqual(events[1]["reason"], "base_fragment_removed")
        self.assertEqual(events[1]["override_hash"], "e5f6789012345678abcdef0102030405")

    def test_toml_orphan_requires_confirmation(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertIs(events[1]["requires_confirmation"], True)

    def test_exactly_one_mock_call_per_triage(self) -> None:
        self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(len(self.mock.calls), 1)


# ---------------------------------------------------------------------------
# AC-4: TOML new-default informational (no requires_confirmation)
# ---------------------------------------------------------------------------


class TestTomlNewDefault(unittest.TestCase):
    """drift_triage with toml-new-default fixture: propose_toml_new_default."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--dry-run --json", "dry-run-toml-new-default.json")

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(drift_triage, self.mock, upgrade_py=_UPGRADE_PY)

    def test_propose_toml_new_default_emitted(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertIn("propose_toml_new_default", [e["action"] for e in events])

    def test_toml_new_default_payload(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[1]["key"], "agent.temperature")
        self.assertEqual(events[1]["new_value"], "0.7")
        self.assertEqual(events[1]["source"], "defaults")

    def test_toml_new_default_no_confirmation_field(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertNotIn("requires_confirmation", events[1])

    def test_exactly_one_mock_call_per_triage(self) -> None:
        self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(len(self.mock.calls), 1)


# ---------------------------------------------------------------------------
# AC-5: Glob-input drift informational (no requires_confirmation)
# ---------------------------------------------------------------------------


class TestGlobDrift(unittest.TestCase):
    """drift_triage with glob-drift fixture: propose_glob_drift event."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--dry-run --json", "dry-run-glob-drift.json")

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(drift_triage, self.mock, upgrade_py=_UPGRADE_PY)

    def test_propose_glob_drift_emitted(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertIn("propose_glob_drift", [e["action"] for e in events])

    def test_glob_drift_pattern_and_key(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[1]["pattern"], "file:docs/*.md")
        self.assertEqual(events[1]["toml_key"], "self.context.docs")

    def test_glob_drift_match_sets(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[1]["added_matches"], ["docs/new-guide.md"])
        self.assertEqual(events[1]["removed_matches"], ["docs/old-guide.md"])

    def test_glob_drift_no_confirmation_field(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertNotIn("requires_confirmation", events[1])

    def test_exactly_one_mock_call_per_triage(self) -> None:
        self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(len(self.mock.calls), 1)


# ---------------------------------------------------------------------------
# AC-6: Triage start/complete contract + FR55 (exactly one subprocess call)
# ---------------------------------------------------------------------------


class TestDriftTriageContract(unittest.TestCase):
    """Subprocess + event-ordering contract for drift_triage."""

    def setUp(self) -> None:
        self.mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        self.mock.register("--dry-run --json", "dry-run-prose-drift.json")

    def _run(self) -> list[dict[str, Any]]:
        return run_handler_with_mock(drift_triage, self.mock, upgrade_py=_UPGRADE_PY)

    def test_exactly_one_mock_call_per_triage(self) -> None:
        self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(len(self.mock.calls), 1)

    def test_subprocess_call_is_dry_run_json(self) -> None:
        self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(self.mock.calls[0]["pattern"], "--dry-run --json")

    def test_drift_triage_start_is_first_event(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[0]["action"], "drift_triage_start")

    def test_drift_triage_complete_is_last_event(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[-1]["action"], "drift_triage_complete")

    def test_no_drift_emits_start_and_complete_only(self) -> None:
        no_drift_mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        no_drift_mock.register("--dry-run --json", "dry-run-no-drift.json")
        events = run_handler_with_mock(
            drift_triage, no_drift_mock, upgrade_py=_UPGRADE_PY,
        )
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["action"], "drift_triage_start")
        self.assertEqual(events[1]["action"], "drift_triage_complete")

    def test_drift_triage_start_count_fields(self) -> None:
        events = self._run()
        self.assertGreater(len(self.mock.calls), 0, _GUARD_MSG)
        self.assertEqual(events[0]["total_prose_changes"], 1)
        self.assertEqual(events[0]["total_toml_changes"], 0)
        self.assertEqual(events[0]["total_orphans"], 0)
        self.assertEqual(events[0]["total_new_defaults"], 0)
        self.assertEqual(events[0]["total_glob_changes"], 0)


# ---------------------------------------------------------------------------
# AC-5 + OQ-C (7.10): summary-vs-emit-count cross-validation (L702) + _UPGRADE_PY (L693)
# ---------------------------------------------------------------------------


class TestDriftTriageSummaryConsistency(unittest.TestCase):
    """drift_triage_start count fields must match actual emitted per-drift events."""

    def test_upgrade_py_path_exists(self) -> None:
        """_UPGRADE_PY must resolve to a real filesystem path — closes L693."""
        self.assertTrue(
            Path(_UPGRADE_PY).exists(),
            f"_UPGRADE_PY does not resolve to a real path: {_UPGRADE_PY}",
        )

    @staticmethod
    def _count_events(events: list[dict[str, Any]], action: str) -> int:
        return sum(1 for e in events if e.get("action") == action)

    def test_prose_drift_triage_start_matches_emitted_events(self) -> None:
        mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        mock.register("--dry-run --json", "dry-run-prose-drift.json")
        events = run_handler_with_mock(drift_triage, mock, upgrade_py=_UPGRADE_PY)
        start_evt = events[0]
        self.assertEqual(start_evt["action"], "drift_triage_start")
        self.assertEqual(
            start_evt["total_prose_changes"],
            self._count_events(events, "propose_prose_drift"),
        )

    def test_toml_default_drift_triage_start_matches_emitted_events(self) -> None:
        mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        mock.register("--dry-run --json", "dry-run-toml-default-drift.json")
        events = run_handler_with_mock(drift_triage, mock, upgrade_py=_UPGRADE_PY)
        start_evt = events[0]
        self.assertEqual(start_evt["action"], "drift_triage_start")
        self.assertEqual(
            start_evt["total_toml_changes"],
            self._count_events(events, "propose_toml_default_drift"),
        )

    def test_no_drift_all_counts_zero_in_triage_start(self) -> None:
        mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        mock.register("--dry-run --json", "dry-run-no-drift.json")
        events = run_handler_with_mock(drift_triage, mock, upgrade_py=_UPGRADE_PY)
        start_evt = events[0]
        self.assertEqual(start_evt["action"], "drift_triage_start")
        self.assertEqual(start_evt["total_prose_changes"], 0)
        self.assertEqual(start_evt["total_toml_changes"], 0)
        self.assertEqual(start_evt["total_orphans"], 0)
        self.assertEqual(start_evt["total_new_defaults"], 0)
        self.assertEqual(start_evt["total_glob_changes"], 0)
        self.assertEqual(start_evt["total_provenance_shifts"], 0)
        per_drift_actions = {
            "propose_prose_drift", "propose_toml_default_drift", "propose_toml_orphan",
            "propose_toml_new_default", "propose_glob_drift", "propose_variable_provenance_shift",
        }
        self.assertFalse(
            any(e["action"] in per_drift_actions for e in events),
            "no-drift fixture must not emit per-drift events",
        )

    def test_provenance_shift_triage_start_matches_emitted_events(self) -> None:
        mock = MockCompiler(fixtures_root=_FIXTURES_ROOT)
        mock.register("--dry-run --json", "dry-run-provenance-shift.json")
        events = run_handler_with_mock(drift_triage, mock, upgrade_py=_UPGRADE_PY)
        start_evt = events[0]
        self.assertEqual(start_evt["action"], "drift_triage_start")
        self.assertEqual(
            start_evt["total_provenance_shifts"],
            self._count_events(events, "propose_variable_provenance_shift"),
        )


if __name__ == "__main__":
    unittest.main()
