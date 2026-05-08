"""Writer handler for bmad-customize: persists an accepted override to disk
and surfaces a unified-diff review event so the user can verify the
compiled-SKILL.md-level impact before confirming.

Two public functions:

  write_override
      Writes accepted_content verbatim to target_file (creating parent
      directories as needed), emits write_override_complete, then invokes
      compile.py <skill_id> --diff and emits propose_diff_review with the
      captured stdout. Order: write → emit → diff → emit. The file must
      exist on disk before --diff runs (otherwise the diff would show no
      change), and write_override_complete must precede the subprocess
      call so the shell observes the write even if --diff fails.

  revert_override
      Pure filesystem function with no subprocess calls. If
      pre_write_content is None, deletes the override (file was newly
      created); otherwise restores the prior content via write_text.
      Emits revert_complete with deleted=True/False accordingly.

The LLM shell is responsible for sparse-override formatting:
write_override does NOT compute sparsity, does NOT call --explain --json,
and does NOT parse TOML. It writes accepted_content verbatim. For TOML,
the shell passes a single dotted-key line (e.g. agent.icon = "🎯"\\n);
for prose, the shell passes the full fragment replacement text.

The --diff subprocess call uses the POSITIONAL skill_canonical argument
(NOT the --skill flag) because compile.py rejects the combination of
--skill with --diff. Output is plain-text unified diff — not JSON — so
the handler does not import json.

Event schemas: see discovery.py module docstring for the canonical
registry of action schemas (write_override_complete, propose_diff_review,
revert_complete are declared there alongside discover/report_surface/
request_disambiguation/propose_route/request_plane_disambiguation/
warn_full_skill/propose_draft).

Interface:
  write_override(
      plane: str,
      target_file: str,
      accepted_content: str,
      skill_id: str,
      compile_py: Path,
      emit_fn: Callable[[dict[str, Any]], None],
      run_fn: Optional[Callable[..., subprocess.CompletedProcess[str]]] = None,
      # None → resolved at call time; default behaviour is subprocess.run
  ) -> None

  plane:            "toml" or "prose" (echoed in write_override_complete)
  target_file:      filesystem path to write accepted_content to; parent
                    directories are created if missing
  accepted_content: verbatim string written to target_file. The LLM shell
                    is responsible for sparse formatting; write_override
                    does not transform or validate this content
  skill_id:         resolved skill identifier (e.g. "mock-module/skill-a");
                    passed as the POSITIONAL skill_canonical arg to --diff,
                    NOT via --skill (compile.py rejects --skill + --diff)
  compile_py:       path to compile.py; used in the --diff subprocess call
  emit_fn:          event collector callback
  run_fn:           resolved to subprocess.run at call time when None;
                    pass an explicit callable for explicit dependency
                    injection only

  revert_override(
      target_file: str,
      pre_write_content: Optional[str],
      emit_fn: Callable[[dict[str, Any]], None],
  ) -> None

  target_file:       filesystem path of the override to revert
  pre_write_content: None when the override was newly created (file is
                     deleted on revert); a string when the file pre-existed
                     (its content is restored on revert)
  emit_fn:           event collector callback

Production callers derive compile_py via:
  # dev-tree path; installed-package derivation deferred until packaging story
  compile_py = Path(__file__).resolve().parent.parent / "compile.py"
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from ._errors import BmadSubprocessError


def write_override(
    plane: str,
    target_file: str,
    accepted_content: str,
    skill_id: str,
    compile_py: Path,
    emit_fn: Callable[[dict[str, Any]], None],
    run_fn: Optional[Callable[..., "subprocess.CompletedProcess[str]"]] = None,
) -> None:
    """Write accepted_content to target_file, then capture --diff output.

    Ordered steps (non-negotiable):
      1. Create target_file's parent directories (mkdir -p).
      2. Write accepted_content verbatim with utf-8 encoding.
      3. Emit write_override_complete BEFORE the subprocess call so the
         shell observes the write even if --diff later fails.
      4. Resolve _run at call time (so unittest.mock.patch("subprocess.run", ...)
         intercepts the call without callers passing run_fn).
      5. Invoke compile.py with positional skill_canonical + --diff.
      6. Emit propose_diff_review carrying the raw stdout as diff_text.

    On subprocess.CalledProcessError or any subprocess failure, the
    exception propagates; propose_diff_review is NOT emitted. Recovery
    (e.g. calling revert_override) is the LLM shell's responsibility.
    """
    target_path = Path(target_file)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(accepted_content, encoding="utf-8")

    emit_fn({
        "action": "write_override_complete",
        "plane": plane,
        "target_file": target_file,
    })

    _run: Callable[..., subprocess.CompletedProcess[str]] = (
        run_fn if run_fn is not None else subprocess.run
    )
    # dev-tree path; installed-package derivation deferred until packaging story
    # NOTE: --diff uses positional skill_canonical arg (NOT --skill; see compile.py line 694).
    try:
        result = _run(
            [sys.executable, str(compile_py), skill_id, "--diff"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise BmadSubprocessError(
            f"write_override: bmad compile --diff failed (rc={exc.returncode}): {exc.stderr}"
        ) from exc
    diff_text = result.stdout

    emit_fn({
        "action": "propose_diff_review",
        "diff_text": diff_text,
        "target_file": target_file,
        "requires_confirmation": True,
    })


def revert_override(
    target_file: str,
    pre_write_content: Optional[str],
    emit_fn: Callable[[dict[str, Any]], None],
) -> None:
    """Revert an override: delete the file (if newly created) or restore
    its prior content. Pure filesystem operation — no subprocess calls.

    pre_write_content semantics:
      None: the override file was newly created; delete it. The
            existence guard before unlink() prevents a FileNotFoundError
            if the LLM shell has already deleted the file out-of-band;
            revert_complete is still emitted with deleted=True.
      str:  the file pre-existed; restore its content via write_text.
            revert_complete is emitted with deleted=False.
    """
    target_path = Path(target_file)
    if pre_write_content is None:
        if target_path.exists():
            target_path.unlink()
        emit_fn({
            "action": "revert_complete",
            "target_file": target_file,
            "deleted": True,
        })
    else:
        target_path.write_text(pre_write_content, encoding="utf-8")
        emit_fn({
            "action": "revert_complete",
            "target_file": target_file,
            "deleted": False,
        })
