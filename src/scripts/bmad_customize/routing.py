"""Routing handler for bmad-customize: maps natural-language intent to a
customization plane (TOML / prose / full-skill) and emits a routing proposal
or a disambiguation request.

Stateless per call: emits a proposal event and returns. Events with
requires_confirmation=True signal to the LLM shell that it must wait for user
confirmation before any write. Actual writing is Story 6.5's responsibility.

Full-skill detection is intent-based: if the intent contains a recognized
full-skill-replacement phrase, the handler emits warn_full_skill and returns
WITHOUT calling the compiler. For all other intents, the handler calls
--explain --json once to get the surface, then routes based on keyword
matching.

Event schemas: see discovery.py module docstring for the canonical registry
of action schemas (propose_route, request_plane_disambiguation,
warn_full_skill are declared there alongside discover/report_surface/
request_disambiguation).

Interface:
  route_intent(
      intent: str,
      skill_id: str,
      install_dir: str,
      compile_py: Path,
      emit_fn: Callable[[dict[str, Any]], None],
      run_fn: Optional[Callable[..., subprocess.CompletedProcess[str]]] = None,
      # None → resolved at call time; default behaviour is subprocess.run
  ) -> None

  intent:       natural-language customization intent (matched against
                _FULL_SKILL_PHRASES first; tokenized and matched against
                surface fields/fragments otherwise)
  skill_id:     resolved skill identifier (e.g. "mock-module/skill-a"); used to
                derive target_file paths and as compile.py positional
                <skill_canonical> argument
  install_dir:  path to the BMAD install directory (root containing _bmad/);
                passed as --install-dir to compile.py; accepted for API
                consistency with discover_surface but NEVER dereferenced on
                the full-skill pre-compile path (same as compile_py below)
  compile_py:   path to compile.py; accepted for API consistency with
                discover_surface but NEVER dereferenced on the full-skill
                pre-compile path (handler emits warn_full_skill and returns
                before any run_fn call when _is_full_skill_intent is true)
  emit_fn:      event collector callback
  run_fn:       resolved to subprocess.run at call time when None; pass an
                explicit callable for explicit dependency injection only

Production callers derive compile_py and install_dir via:
  # dev-tree paths; installed-package derivation deferred until packaging story
  compile_py = Path(__file__).resolve().parent.parent / "compile.py"
  install_dir = str(Path(__file__).resolve().parent.parent.parent)  # repo/install root containing _bmad/
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from ._errors import BmadSubprocessError

_FULL_SKILL_PHRASES: tuple[str, ...] = (
    "entire skill",
    "whole skill",
    "full skill",
    "full-skill",
    "replace skill",
    "rewrite skill",
    "replace the entire",
    "rewrite the entire",
    "from scratch",
)


def _is_full_skill_intent(intent: str) -> bool:
    """Return True if intent contains a recognized full-skill-replacement phrase."""
    lower = intent.lower()
    return any(phrase in lower for phrase in _FULL_SKILL_PHRASES)


def _extract_tokens(intent: str) -> list[str]:
    """Lowercase, split on non-alphanumeric, filter short tokens (len < 4)."""
    parts = re.split(r"[\W_]+", intent.lower())
    seen: set[str] = set()
    result: list[str] = []
    for t in parts:
        if len(t) >= 4 and t not in seen:
            seen.add(t)
            result.append(t)
    return result


def _match_toml(
    toml_fields: list[dict[str, Any]],
    tokens: list[str],
    skill_id: str,
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    skill_name = skill_id.split("/")[-1]
    for field in toml_fields:
        path = field.get("path", "")
        segments = re.split(r"[._]", path)
        if any(tok in seg for tok in tokens for seg in segments):
            field_path = path.split(".")[-1] if "." in path else path
            matched.append({
                "plane": "toml",
                "field_path": field_path,
                "target_file": f"_bmad/custom/{skill_name}.user.toml",
            })
    return matched


def _match_prose(
    fragments: list[dict[str, Any]],
    tokens: list[str],
    skill_id: str,
) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for frag in fragments:
        src = frag.get("src", "")
        name = src
        if name.startswith("fragments/"):
            name = name[len("fragments/"):]
        if name.endswith(".template.md"):
            name = name[: -len(".template.md")]
        name_tokens = re.split(r"[-_]", name)
        if any(tok in nt or nt in tok for tok in tokens for nt in name_tokens):
            matched.append({
                "plane": "prose",
                "fragment_name": name,
                "target_file": f"_bmad/custom/fragments/{skill_id}/{name}.template.md",
            })
    return matched


def route_intent(
    intent: str,
    skill_id: str,
    install_dir: str,
    compile_py: Path,
    emit_fn: Callable[[dict[str, Any]], None],
    run_fn: Optional[Callable[..., "subprocess.CompletedProcess[str]"]] = None,
) -> None:
    """Route a natural-language intent to a customization plane.

    Ordered steps:
      1. Full-skill check (pre-compile): if intent matches _FULL_SKILL_PHRASES,
         emit warn_full_skill and return without calling run_fn.
      2. Otherwise, invoke compiler via run_fn for --explain --json.
      3. Parse JSON; tokenize intent; match against toml_fields and fragments.
      4. Decide route: both planes match → request_plane_disambiguation;
         only one plane → propose_route; neither → request_plane_disambiguation
         with empty candidates.

    run_fn defaults to None so subprocess.run is resolved at call time (not
    captured at module import time), letting unittest.mock.patch intercept the
    call without callers passing run_fn.
    """
    # (1) Full-skill check BEFORE any compile call.
    if _is_full_skill_intent(intent):
        emit_fn({
            "action": "warn_full_skill",
            "bypass_warning": "full-skill replacement bypasses fragment-level upgrade safety",
            "requires_confirmation": True,
            "requires_second_confirmation": True,
        })
        return
    # (2) Invoke compiler; resolve run_fn at call time so global patch works.
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
            f"route_intent: bmad compile failed (rc={exc.returncode}): {exc.stderr}"
        ) from exc
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise BmadSubprocessError(
            f"route_intent: invalid JSON from compile.py: {result.stdout[:200]!r}"
        ) from exc
    if not isinstance(raw, dict):
        raise BmadSubprocessError(
            f"route_intent: expected JSON object, got {type(raw).__name__}"
        )
    payload: dict[str, Any] = raw
    # (3) Tokenize intent and match against surface
    tokens = _extract_tokens(intent)
    toml_fields: list[dict[str, Any]] = payload.get("toml_fields") or []
    fragments: list[dict[str, Any]] = payload.get("fragments") or []
    toml_candidates = _match_toml(toml_fields, tokens, skill_id)
    prose_candidates = _match_prose(fragments, tokens, skill_id)
    # (4) Routing decision
    if toml_candidates and prose_candidates:
        emit_fn({
            "action": "request_plane_disambiguation",
            "candidates": toml_candidates + prose_candidates,
        })
        return
    if toml_candidates:
        first = toml_candidates[0]
        emit_fn({
            "action": "propose_route",
            "plane": "toml",
            "field_path": first["field_path"],
            "target_file": first["target_file"],
            "requires_confirmation": True,
        })
        return
    if prose_candidates:
        first = prose_candidates[0]
        emit_fn({
            "action": "propose_route",
            "plane": "prose",
            "fragment_name": first["fragment_name"],
            "target_file": first["target_file"],
            "requires_confirmation": True,
        })
        return
    emit_fn({"action": "request_plane_disambiguation", "candidates": []})
