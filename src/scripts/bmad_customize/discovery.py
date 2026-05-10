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
  drift_triage_start:
    {"action": "drift_triage_start", "total_prose_changes": int,
     "total_toml_changes": int, "total_orphans": int,
     "total_new_defaults": int, "total_glob_changes": int,
     "total_provenance_shifts": int}
    Emitted by drift.py as the first event before processing any drift entry.
    Carries summary counts from the dry-run payload's summary block.
  propose_prose_drift:
    {"action": "propose_prose_drift", "skill": str, "path": str, "tier": str,
     "old_hash": str, "new_hash": str, "user_override_hash": str,
     "requires_confirmation": bool}
    Emitted by drift.py for each prose_fragment_changes entry. Carries hashes
    only (not actual content); the LLM shell fetches content for presentation.
    requires_confirmation is always True.
  propose_toml_default_drift:
    {"action": "propose_toml_default_drift", "skill": str, "key": str,
     "old_hash": str, "new_value": str, "user_override_value": str,
     "requires_confirmation": bool}
    Emitted by drift.py for each toml_default_changes entry. old_hash is the
    hash of the prior default (not the value string). requires_confirmation
    is always True.
  propose_toml_orphan:
    {"action": "propose_toml_orphan", "skill": str, "path": str,
     "reason": str, "override_hash": str, "requires_confirmation": bool}
    Emitted by drift.py for each orphaned_overrides entry. The LLM shell
    offers to remove the orphaned override via revert_override(pre_write_content=None).
    requires_confirmation is always True.
  propose_toml_new_default:
    {"action": "propose_toml_new_default", "skill": str, "key": str,
     "new_value": str, "source": str}
    Emitted by drift.py for each new_defaults entry. Informational only —
    no requires_confirmation field is emitted.
  propose_glob_drift:
    {"action": "propose_glob_drift", "skill": str, "pattern": str,
     "toml_key": str, "added_matches": list[str], "removed_matches": list[str]}
    Emitted by drift.py for each glob_changes entry. Informational only —
    no requires_confirmation field is emitted.
  propose_variable_provenance_shift:
    {"action": "propose_variable_provenance_shift", "skill": str,
     "name": str, "old_source": str, "new_source": str,
     "old_toml_layer": str | null, "new_toml_layer": str | null}
    Emitted by drift.py for each variable_provenance_shifts entry. Reports that
    a variable's compilation provenance changed between BMAD versions.
    Informational only — no requires_confirmation field (OQ-6=Option A).
  drift_triage_complete:
    {"action": "drift_triage_complete"}
    Emitted by drift.py after all drift entries have been processed. Signals
    the LLM shell to instruct the user to re-run bmad upgrade.

Interface (discover_surface — see also routing.py, drafting.py, writer.py, drift.py for handler events):
  discover_surface(
      intent: str,
      skill_id: str,
      install_dir: str,
      compile_py: Path,
      emit_fn: Callable[[dict[str, Any]], None],
      run_fn: Optional[Callable[..., subprocess.CompletedProcess[str]]] = None,
      # None → resolved at call time; default behaviour is subprocess.run
  ) -> None

  intent:       natural-language customization intent (accepted for API stability;
                unused in Story 6.2 -- do not branch on its value)
  skill_id:     resolved skill identifier (e.g. "mock-module/skill-a"); used as
                compile.py positional <skill_canonical> argument
  install_dir:  path to the BMAD install directory (root containing _bmad/);
                passed as --install-dir to compile.py; ignored by run_fn in tests
  compile_py:   path to compile.py; ignored by run_fn in tests
  emit_fn:      event collector callback
  run_fn:       resolved to subprocess.run at call time when None; pass explicit callable for DI

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

_ICON_SUBSTRINGS: tuple[str, ...] = ("icon", "glyph", "emoji", "logo")


def _has_icon_token(text: str) -> bool:
    """True iff any dot/hyphen/underscore/slash-delimited token in *text* is in _ICON_SUBSTRINGS.

    Story 7.11 AC-1 (L567): unanchored substring matching produced false positives
    on tokens that merely *contained* an icon substring (e.g., 'catalogo.title'
    contains 'logo'; 'unicode.encoding' contains 'icon'). Token-boundary matching
    splits on `.`, `-`, `_`, and `/` (the latter so fragment paths like
    'fragments/icon.template.md' tokenize to ['fragments', 'icon', 'template', 'md']
    and the icon hits) and requires exact equality against the set.
    """
    normalized = text.lower().replace("-", ".").replace("_", ".").replace("/", ".")
    tokens = normalized.split(".")
    return any(tok in _ICON_SUBSTRINGS for tok in tokens)


def discover_surface(
    intent: str,
    skill_id: str,
    install_dir: str,
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
            f"discover_surface: bmad compile failed (rc={exc.returncode}): {exc.stderr}"
        ) from exc
    # (2) Parse JSON output
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BmadSubprocessError(
            f"discover_surface: invalid JSON from compile.py: {result.stdout[:200]!r}"
        ) from exc
    if not isinstance(raw, dict):
        raise BmadSubprocessError(
            f"discover_surface: expected JSON object, got {type(raw).__name__}"
        )
    payload: dict[str, Any] = raw
    # Story 7.11 AC-1 (L590, OQ-A=A): forward-compat schema_version guard.
    # absent or == 1 passes through; any other value raises immediately.
    schema_version = payload.get("schema_version")
    if schema_version is not None and schema_version != 1:
        raise BmadSubprocessError(
            f"discover_surface: unsupported compiler schema_version={schema_version!r}; "
            f"expected 1 or absent"
        )
    # (3) Emit discover event unconditionally as the first event
    emit_fn({"action": "discover", "skill_id": skill_id, "source": "--explain --json"})
    # (4) Detect ambiguity: toml condition AND fragment condition must both hold
    toml_fields: list[dict[str, Any]] = payload.get("toml_fields", [])
    fragments: list[dict[str, Any]] = payload.get("fragments", [])
    # Story 7.11 AC-1 (L567): token-boundary matching via _has_icon_token avoids
    # false positives like 'catalogo.title' (substring 'logo') and 'unicode.encoding'
    # (substring 'icon'). True matches like 'agent.icon' / 'display.logo' still hit.
    toml_icon_count = sum(
        1 for f in toml_fields if _has_icon_token(f.get("path", ""))
    )
    frag_icon_match = any(
        _has_icon_token(frag.get("src", "")) for frag in fragments
    )
    if toml_icon_count >= 2 and frag_icon_match:
        candidates: list[dict[str, Any]] = [
            {"path": f["path"]}
            for f in toml_fields
            if _has_icon_token(f.get("path", ""))
        ] + [
            {"src": frag["src"]}
            for frag in fragments
            if _has_icon_token(frag.get("src", ""))
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
