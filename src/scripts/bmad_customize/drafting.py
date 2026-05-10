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
      1. Pre-validate compile_py and sys.executable exist on disk (Story 7.11
         AC-2, L607/L611/L613). These guards turn a raw FileNotFoundError into
         a typed BmadSubprocessError before the subprocess is launched.
      2. Validate caller contracts on revision_feedback and (later) field_path
         and toml_fields entries (Story 7.11 AC-3, L622/L624/L626).
      3. Invoke compiler via run_fn for --explain --json.
      4. Build base event payload with action, plane, target_file, intent,
         requires_confirmation.
      5. TOML plane: add field_path and (if matching field found) current_value.
      6. Prose plane: add fragment_name. current_content is not added — the
         explain payload carries hash+src but not raw fragment text (OQ-2).
      7. If revision_feedback is provided, echo it into the event.
      8. Emit exactly one propose_draft event and return.

    No filesystem writes occur on any code path. run_fn defaults to None so
    subprocess.run is resolved at call time, letting unittest.mock.patch
    intercept the call without callers passing run_fn.

    Story 7.11 AC-2 (L613): the compile_py and sys.executable guards only
    confirm the paths resolve to existing files on disk. They do NOT confirm
    sys.executable is the right Python version or the active venv's
    interpreter — that is caller responsibility (e.g., shim/venv resolution
    is upstream of this handler).
    """
    # Story 7.11 AC-2 (L607/L611): validate compile_py exists before spawning.
    if not compile_py.exists():
        raise BmadSubprocessError(
            f"draft_content: compile.py not found at {compile_py}"
        )
    # Story 7.11 AC-2 (L613): validate sys.executable resolves to an existing file.
    if not Path(sys.executable).exists():
        raise BmadSubprocessError(
            f"draft_content: Python executable not found at {sys.executable}"
        )
    # Story 7.11 AC-3 (L626, OQ-D=A): empty / whitespace-only revision_feedback
    # is semantically invalid. None means absent (no echo); a non-empty string
    # is a real revision iteration.
    if revision_feedback is not None and not revision_feedback.strip():
        raise BmadSubprocessError(
            "draft_content: revision_feedback must be non-empty string or None"
        )
    # Story 7.11 AC-3 (L624, OQ-B=A): routing.py emits single-segment field_path
    # values via `path.split(".")[-1]`. A multi-segment value here means a caller
    # contract violation; surface it before silent last-segment matching.
    if plane == "toml" and field_path is not None and "." in field_path:
        raise BmadSubprocessError(
            f"draft_content: multi-segment field_path {field_path!r} not supported; "
            f"routing.py must emit single-segment paths only"
        )
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
            # Story 7.11 AC-3 (L622): caller contract guard on entry shape.
            # Raises before AttributeError on the field.get(...) call below.
            if not isinstance(field, dict):
                raise BmadSubprocessError(
                    f"draft_content: toml_fields entry is not a dict: {field!r}"
                )
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
