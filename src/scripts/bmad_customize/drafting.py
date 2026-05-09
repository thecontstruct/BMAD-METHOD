"""Drafting handler for bmad-customize: fetches current surface content for
the routed target and emits a propose_draft event for LLM-shell rendering.

Stateless per call: invokes --explain --json on every call to retrieve the
current surface, builds a propose_draft event payload, and emits exactly one
event before returning. No filesystem writes occur — the no-write contract
holds for every iteration. Actual file writes are Story 6.5's responsibility.

Event schemas: see discovery.py module docstring for the canonical registry
of action schemas (propose_draft is declared there alongside discover/
report_surface/request_disambiguation/propose_route/
request_plane_disambiguation/warn_full_skill).

Interface:
  draft_content(
      intent: str,
      plane: str,
      field_path: Optional[str],     # TOML plane only; None for prose
      fragment_name: Optional[str],  # prose plane only; None for TOML
      target_file: str,
      skill_id: str,
      install_dir: str,
      compile_py: Path,
      emit_fn: Callable[[dict[str, Any]], None],
      run_fn: Optional[Callable[..., subprocess.CompletedProcess[str]]] = None,
      revision_feedback: Optional[str] = None,
  ) -> None

  intent:            natural-language customization intent (echoed in event for
                     LLM-shell context)
  plane:             "toml" or "prose" (selects which optional keys are added)
  field_path:        TOML field path (e.g. "icon"); None on prose plane
  fragment_name:     prose fragment name (e.g. "menu-handler"); None on TOML plane
  target_file:       caller-provided override file path (set by routing handler;
                     not re-derived here)
  skill_id:          resolved skill identifier; used as compile.py positional
                     <skill_canonical> argument
  install_dir:       path to the BMAD install directory (root containing _bmad/);
                     passed as --install-dir to compile.py
  compile_py:        path to compile.py; used on ALL paths (draft_content always
                     calls --explain --json to fetch current surface state,
                     unlike route_intent which skips it on the full-skill path)
  emit_fn:           event collector callback
  run_fn:            resolved to subprocess.run at call time when None; pass
                     explicit callable for explicit dependency injection only
  revision_feedback: when provided, echoed into the event under the same key;
                     when None, the key is omitted from the event entirely

Production callers derive compile_py and install_dir via:
  # dev-tree paths; installed-package derivation deferred until packaging story
  compile_py = Path(__file__).resolve().parent.parent / "compile.py"
  install_dir = str(Path(__file__).resolve().parent.parent.parent)  # repo/install root containing _bmad/
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from ._errors import BmadSubprocessError


def draft_content(
    intent: str,
    plane: str,
    field_path: Optional[str],
    fragment_name: Optional[str],
    target_file: str,
    skill_id: str,
    install_dir: str,
    compile_py: Path,
    emit_fn: Callable[[dict[str, Any]], None],
    run_fn: Optional[Callable[..., "subprocess.CompletedProcess[str]"]] = None,
    revision_feedback: Optional[str] = None,
) -> None:
    """Fetch the current surface state and emit a propose_draft event.

    Ordered steps:
      1. Invoke compiler via run_fn for --explain --json.
      2. Build base event payload with action, plane, target_file, intent,
         requires_confirmation.
      3. TOML plane: add field_path and (if matching field found) current_value.
      4. Prose plane: add fragment_name. current_content is not added — the
         explain payload carries hash+src but not raw fragment text (OQ-2).
      5. If revision_feedback is provided, echo it into the event.
      6. Emit exactly one propose_draft event and return.

    No filesystem writes occur on any code path. run_fn defaults to None so
    subprocess.run is resolved at call time, letting unittest.mock.patch
    intercept the call without callers passing run_fn.
    """
    _run: Callable[..., subprocess.CompletedProcess[str]] = (
        run_fn if run_fn is not None else subprocess.run
    )
    # dev-tree path; installed-package derivation deferred until packaging story
    cmd = [sys.executable, str(compile_py), skill_id, "--install-dir", install_dir, "--explain", "--json"]
    try:
        result = _run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise BmadSubprocessError(
            f"draft_content: bmad compile failed (rc={exc.returncode}): {exc.stderr}"
        ) from exc
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BmadSubprocessError(
            f"draft_content: invalid JSON from compile.py: {result.stdout[:200]!r}"
        ) from exc
    if not isinstance(raw, dict):
        raise BmadSubprocessError(
            f"draft_content: expected JSON object, got {type(raw).__name__}"
        )
    payload: dict[str, Any] = raw

    event: dict[str, Any] = {
        "action": "propose_draft",
        "plane": plane,
        "target_file": target_file,
        "intent": intent,
        "requires_confirmation": True,
    }

    if plane == "toml" and field_path is not None:
        event["field_path"] = field_path
        for field in payload.get("toml_fields") or []:
            path = field.get("path", "")
            last_seg = path.split(".")[-1] if "." in path else path
            if last_seg == field_path:
                val = field.get("current_value")
                if val is not None:
                    event["current_value"] = val
                break
    elif plane == "prose" and fragment_name is not None:
        event["fragment_name"] = fragment_name

    if revision_feedback is not None:
        event["revision_feedback"] = revision_feedback

    emit_fn(event)
