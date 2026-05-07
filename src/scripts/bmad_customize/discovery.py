"""Discovery handler for bmad-customize: discovers skill customization surface
via --explain --json.

Emits structured events via the emit_fn callback. Stories 6.3-6.6 extend this
module's docstring with additional event schemas as they add handler functions.

Event schemas emitted by this module:
  discover:
    {"action": "discover", "skill_id": str, "source": str}
    First event emitted on every discovery call (before any branching).
  report_surface:
    {"action": "report_surface", "toml_fields": int, "prose_fragments": int,
     "variables": int}
    Emitted on non-ambiguous discovery path only.
  request_disambiguation:
    {"action": "request_disambiguation", "candidates": list[dict]}
    Emitted when ambiguous intent is detected; handler returns immediately after
    (no further events follow — execution suspends pending user input).
  propose_route:
    {"action": "propose_route", "plane": str, "field_path": str (TOML plane only),
     "fragment_name": str (prose plane only), "target_file": str,
     "requires_confirmation": bool}
    Emitted by routing.py when intent maps cleanly to one plane. Either
    field_path (TOML) or fragment_name (prose) is present, never both.
  request_plane_disambiguation:
    {"action": "request_plane_disambiguation",
     "candidates": list[{"plane": str, "field_path"?: str, "fragment_name"?: str,
                         "target_file"?: str}]}
    Emitted by routing.py when intent matches both TOML and prose candidates,
    or when no candidate is found. Each candidate includes "plane".
  warn_full_skill:
    {"action": "warn_full_skill", "bypass_warning": str,
     "requires_confirmation": bool, "requires_second_confirmation": bool}
    Emitted by routing.py when intent requests full-skill replacement.
    No compiler call precedes this event (pre-compile path).
  propose_draft:
    {"action": "propose_draft", "plane": str, "field_path": str (TOML only),
     "fragment_name": str (prose only), "target_file": str,
     "current_value": str (TOML only — present when field found in explain payload),
     "intent": str, "revision_feedback": str (present on revision iterations only),
     "requires_confirmation": bool}
    Emitted by drafting.py when the handler fetches current surface content and
    proposes a draft for LLM-shell rendering. No filesystem writes occur. Either
    field_path (TOML) or fragment_name (prose) is present, never both.
    current_value is absent when the matching TOML field is not found (graceful
    degradation). revision_feedback is absent on first iteration.
  write_override_complete:
    {"action": "write_override_complete", "plane": str, "target_file": str}
    Emitted by writer.py immediately after the override file is written to disk
    and before the --diff subprocess call. Signals the LLM shell that the write
    succeeded.
  propose_diff_review:
    {"action": "propose_diff_review", "diff_text": str, "target_file": str,
     "requires_confirmation": bool}
    Emitted by writer.py after capturing --diff output. diff_text is the raw
    unified-diff string (may be empty if no change detected). requires_confirmation
    is always True. Signals the LLM shell to render the diff for user review.
  revert_complete:
    {"action": "revert_complete", "target_file": str, "deleted": bool}
    Emitted by writer.py::revert_override after reverting the override.
    deleted=True when the file was newly created and has been deleted;
    deleted=False when the file pre-existed and its content has been restored.

Interface (discover_surface — see also routing.py, drafting.py, writer.py for handler events):
  discover_surface(
      intent: str,
      skill_id: str,
      compile_py: Path,
      emit_fn: Callable[[dict[str, Any]], None],
      run_fn: Optional[Callable[..., subprocess.CompletedProcess[str]]] = None,
      # None → resolved at call time; default behaviour is subprocess.run
  ) -> None

  intent:      natural-language customization intent (accepted for API stability;
               unused in Story 6.2 -- do not branch on its value)
  skill_id:    resolved skill identifier (e.g. "mock-module/skill-a")
  compile_py:  path to compile.py; ignored by run_fn in tests
  emit_fn:     event collector callback
  run_fn:      resolved to subprocess.run at call time when None; pass explicit callable for DI

Production callers derive compile_py via:
  # A1 (Story 6.2): dev-tree path assumption; Story 6.7 must generalize to
  # installed/packaged path.
  compile_py = Path(__file__).resolve().parent.parent / "compile.py"
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional

_ICON_SUBSTRINGS: tuple[str, ...] = ("icon", "glyph", "emoji", "logo")


def discover_surface(
    intent: str,
    skill_id: str,
    compile_py: Path,
    emit_fn: Callable[[dict[str, Any]], None],
    run_fn: Optional[Callable[..., "subprocess.CompletedProcess[str]"]] = None,
) -> None:
    """Discover customization surface of skill_id via --explain --json.

    Ordered steps (mandatory sequence per Story 6.2 Task 3.3):
      1. Invoke compiler via run_fn.
      2. Parse JSON stdout.
      3. Emit discover event unconditionally as first event.
      4. Detect ambiguity; if ambiguous, emit request_disambiguation and return.
      5. Otherwise emit report_surface.

    run_fn defaults to None so that subprocess.run is resolved dynamically at
    call time (not captured at module import time). This lets
    unittest.mock.patch("subprocess.run", ...) intercept the call correctly in
    skill_test_runner.run_handler_with_mock without callers passing run_fn.
    Pass an explicit run_fn for explicit dependency injection only.
    """
    # (1) Invoke the compiler; resolve run_fn at call time so global patch works
    _run: Callable[..., subprocess.CompletedProcess[str]] = (
        run_fn if run_fn is not None else subprocess.run
    )
    result = _run(
        [sys.executable, str(compile_py), "--skill", skill_id, "--explain", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    # (2) Parse JSON output
    payload: dict[str, Any] = json.loads(result.stdout)
    # (3) Emit discover event unconditionally as the first event
    emit_fn({"action": "discover", "skill_id": skill_id, "source": "--explain --json"})
    # (4) Detect ambiguity: toml condition AND fragment condition must both hold
    toml_fields: list[dict[str, Any]] = payload.get("toml_fields", [])
    fragments: list[dict[str, Any]] = payload.get("fragments", [])
    toml_icon_count = sum(
        1 for f in toml_fields
        if any(sub in f.get("path", "") for sub in _ICON_SUBSTRINGS)
    )
    frag_icon_match = any(
        sub in frag.get("src", "")
        for frag in fragments
        for sub in _ICON_SUBSTRINGS
    )
    if toml_icon_count >= 2 and frag_icon_match:
        candidates: list[dict[str, Any]] = [
            {"path": f["path"]}
            for f in toml_fields
            if any(sub in f.get("path", "") for sub in _ICON_SUBSTRINGS)
        ] + [
            {"src": frag["src"]}
            for frag in fragments
            if any(sub in frag.get("src", "") for sub in _ICON_SUBSTRINGS)
        ]
        emit_fn({"action": "request_disambiguation", "candidates": candidates})
        return
    # (5) Report surface: emit counts from parsed payload
    emit_fn({
        "action": "report_surface",
        "toml_fields": len(toml_fields),
        "prose_fragments": len(fragments),
        "variables": len(payload.get("variables", [])),
    })
