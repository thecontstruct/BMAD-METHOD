"""Drift-triage handler for bmad-customize: walks the dry-run drift report
from upgrade.py and emits one event per drift entry for the LLM shell to
process conversationally.

Single public function: drift_triage(upgrade_py, emit_fn, run_fn=None).

The handler invokes upgrade.py --dry-run --json (NOT compile.py), parses the
dry-run-v1.json payload, and dispatches over five drift types. Three are
actionable (propose_prose_drift, propose_toml_default_drift,
propose_toml_orphan — all carry requires_confirmation=True); two are
informational (propose_toml_new_default, propose_glob_drift — no
requires_confirmation field). drift_triage_start opens the sequence carrying
summary counts; drift_triage_complete closes it.

drift_triage does NOT take skill_id and does NOT pass --skill to upgrade.py
— it triages all skills in the lockfile by iterating the dry-run payload's
drift array.

FR55 compliance: drift_triage is a pure scan-and-emit function. It performs
exactly one subprocess call (upgrade.py --dry-run --json) and writes nothing
to disk. All disk writes happen exclusively through writer.py (Story 6.5),
invoked only after the LLM shell receives user acceptance of a drift
resolution.

Event schemas: see discovery.py module docstring for the canonical registry
of action schemas (drift_triage_start, propose_prose_drift,
propose_toml_default_drift, propose_toml_orphan, propose_toml_new_default,
propose_glob_drift, drift_triage_complete are declared there alongside the
prior-handler schemas).

Interface:
  drift_triage(
      upgrade_py: Path,
      emit_fn: Callable[[dict[str, Any]], None],
      run_fn: Optional[Callable[..., subprocess.CompletedProcess[str]]] = None,
      # None → resolved at call time; default behaviour is subprocess.run
  ) -> None

  upgrade_py: path to upgrade.py; passed to subprocess.run as argv[1]. NOTE
              this is upgrade.py, NOT compile.py. The handler invokes
              `upgrade.py --dry-run --json` with no --skill flag, which
              triages all skills in the lockfile in a single call.
  emit_fn:    event collector callback. drift_triage_start is always the
              first event emitted; drift_triage_complete is always the last.
              Per-entry events are emitted in payload order, grouped by
              drift type within each entry.
  run_fn:     resolved to subprocess.run at call time when None; pass an
              explicit callable for explicit dependency injection only.

Production callers derive upgrade_py via:
  # A1 (Story 6.2): same dev-tree path assumption as discovery.py;
  # see deferred-work.md Story 6.7 entry.
  upgrade_py = Path(__file__).resolve().parent.parent / "upgrade.py"
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional


def drift_triage(
    upgrade_py: Path,
    emit_fn: Callable[[dict[str, Any]], None],
    run_fn: Optional[Callable[..., "subprocess.CompletedProcess[str]"]] = None,
) -> None:
    """Walk the dry-run drift report and emit one event per drift entry.

    Ordered steps:
      1. Resolve _run at call time (so unittest.mock.patch("subprocess.run", ...)
         intercepts the call without callers passing run_fn).
      2. Invoke upgrade.py --dry-run --json (NO --skill flag — triages all
         skills in the lockfile).
      3. Parse JSON; reject schema_version != 1.
      4. Emit drift_triage_start with summary counts.
      5. Iterate payload["drift"]; per entry, emit one event per
         drift-type sub-array entry (prose / toml-default / orphan /
         new-default / glob).
      6. Emit drift_triage_complete.

    Invariants:
      - Exactly one subprocess call per invocation.
      - drift_triage_start is the first event; drift_triage_complete is the
        last.
      - No filesystem writes occur on any code path (FR55).
      - Informational events (propose_toml_new_default, propose_glob_drift)
        do NOT carry requires_confirmation; actionable events do (always True).
    """
    _run: Callable[..., subprocess.CompletedProcess[str]] = (
        run_fn if run_fn is not None else subprocess.run
    )
    # A1 (Story 6.2): same dev-tree path assumption; see deferred-work.md Story 6.7 entry.
    result = _run(
        [sys.executable, str(upgrade_py), "--dry-run", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    payload: dict[str, Any] = json.loads(result.stdout)
    sv = payload.get("schema_version")
    if sv != 1:
        raise ValueError(f"Unsupported dry-run schema version: {sv!r}")

    summary: dict[str, Any] = payload.get("summary", {})
    emit_fn({
        "action": "drift_triage_start",
        "total_prose_changes": summary.get("prose_fragment_changes", 0),
        "total_toml_changes": summary.get("toml_default_changes", 0),
        "total_orphans": summary.get("orphaned_overrides", 0),
        "total_new_defaults": summary.get("new_defaults", 0),
        "total_glob_changes": summary.get("glob_changes", 0),
    })

    for entry in payload.get("drift", []):
        skill: str = entry.get("skill", "")

        for change in entry.get("prose_fragment_changes", []):
            emit_fn({
                "action": "propose_prose_drift",
                "skill": skill,
                "path": change["path"],
                "tier": change["tier"],
                "old_hash": change["old_hash"],
                "new_hash": change["new_hash"],
                "user_override_hash": change.get("user_override_hash"),
                "requires_confirmation": True,
            })

        for change in entry.get("toml_default_changes", []):
            emit_fn({
                "action": "propose_toml_default_drift",
                "skill": skill,
                "key": change["key"],
                "old_hash": change["old_hash"],
                "new_value": change["new_value"],
                "user_override_value": change.get("user_override_value"),
                "requires_confirmation": True,
            })

        for change in entry.get("orphaned_overrides", []):
            emit_fn({
                "action": "propose_toml_orphan",
                "skill": skill,
                "path": change["path"],
                "reason": change["reason"],
                "override_hash": change["override_hash"],
                "requires_confirmation": True,
            })

        for change in entry.get("new_defaults", []):
            emit_fn({
                "action": "propose_toml_new_default",
                "skill": skill,
                "key": change["key"],
                "new_value": change["new_value"],
                "source": change["source"],
            })

        for change in entry.get("glob_changes", []):
            emit_fn({
                "action": "propose_glob_drift",
                "skill": skill,
                "pattern": change["pattern"],
                "toml_key": change["toml_key"],
                "added_matches": change["added_matches"],
                "removed_matches": change["removed_matches"],
            })

        # variable_provenance_shifts: intentionally not iterated — no event schema
        # defined in Story 6.6. Do not add handling; deferred to a later story.

    emit_fn({"action": "drift_triage_complete"})
