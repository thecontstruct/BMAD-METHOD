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
      install_dir: str,
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
                    NOT via --skill (compile.py rejects --skill + --diff);
                    combined with --install-dir for compile.py:745-747 invariant
  install_dir:      path to the bmad install directory; passed as compile.py
                    --install-dir; required by compile.py:745-747
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

Production callers derive compile_py and install_dir via:
  # dev-tree path; installed-package derivation deferred until packaging story
  compile_py = Path(__file__).resolve().parent.parent / "compile.py"
  install_dir = str(Path(__file__).resolve().parent.parent.parent)
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
    install_dir: str,
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
      4. Validate compile_py exists and skill_id is non-empty (Story 7.11
         AC-4 / L641). These guards run AFTER the write+emit so the file is
         already on disk if the user accepted it; they prevent the --diff
         subprocess from being spawned on bad inputs.
      5. Resolve _run at call time (so unittest.mock.patch("subprocess.run", ...)
         intercepts the call without callers passing run_fn).
      6. Invoke compile.py with positional skill_canonical + --install-dir + --diff.
      7. Emit propose_diff_review carrying the raw stdout as diff_text.

    On subprocess.CalledProcessError from the --diff invocation, diff_failed is
    emitted before re-raising BmadSubprocessError; propose_diff_review is NOT
    emitted. Other subprocess exceptions (FileNotFoundError, TimeoutExpired, OSError)
    propagate uncaught with NO diff_failed event. Recovery (e.g. calling
    revert_override) is the LLM shell's responsibility.

    Story 7.11 AC-4 (L631): write_text is wrapped in a try/except over the
    PermissionError / OSError / IsADirectoryError / NotADirectoryError set so
    filesystem failures (read-only target, target is a directory, etc.) yield
    a typed BmadSubprocessError rather than a raw OS exception. FileNotFoundError
    is not separately enumerated — and `OSError` would subsume it via class
    hierarchy in any case (Python 3 makes FileNotFoundError an OSError subclass).
    The "no mask" guarantee is therefore TEMPORAL, not exception-set-based:
    `mkdir(parents=True, exist_ok=True)` runs immediately above, so by the time
    write_text executes the parent directory exists and a FileNotFoundError
    from write_text cannot indicate the parent-missing case the mkdir-wrap
    classifies (only a TOCTOU race where the parent is deleted between the two
    statements could surface FileNotFoundError here).

    Story 7.11 AC-5 (L637, OQ-C=B): write_override_complete signals that
    write_text returned without error — NOT that bytes are on stable storage.
    The OS may buffer; fsync is NOT called. If the process crashes after
    write_text but before the shell observes write_override_complete, the file
    may be on disk without the shell knowing. Performance tradeoff; consistent
    with 6.7b's writes (no fsync).

    If emit_fn raises on the write_override_complete event, write_text has already
    succeeded — the file is on disk. The caller holds target_file a-priori and is
    responsible for calling revert_override(target_file, pre_write_content, emit_fn)
    in its exception handler to clean up. If emit_fn raises on the diff_failed event,
    CalledProcessError context is lost and BmadSubprocessError is not raised — the
    caller's exception handler sees the emit_fn exception (same shell responsibility).
    """
    target_path = Path(target_file)
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
    except (FileExistsError, NotADirectoryError, FileNotFoundError) as exc:
        raise BmadSubprocessError(
            f"write_override: parent path is not a usable directory: {target_path.parent}"
        ) from exc
    # Story 7.11 AC-4 (L631): wrap write_text filesystem errors in
    # BmadSubprocessError. FileNotFoundError is intentionally absent (mkdir-wrap
    # above handles the parent-missing case).
    try:
        target_path.write_text(accepted_content, encoding="utf-8")
    except (PermissionError, OSError, IsADirectoryError, NotADirectoryError) as exc:
        raise BmadSubprocessError(
            f"write_override: failed to write {target_file}: {exc}"
        ) from exc

    emit_fn({
        "action": "write_override_complete",
        "plane": plane,
        "target_file": target_file,
    })

    # Story 7.11 AC-4 (L641): pre-validate compile_py + skill_id BEFORE the
    # --diff subprocess. Placed AFTER write+emit so the user-accepted content
    # is on disk first; these guards only protect the --diff invocation.
    if not compile_py.exists():
        raise BmadSubprocessError(
            f"write_override: compile.py not found at {compile_py}"
        )
    if not skill_id or not skill_id.strip():
        raise BmadSubprocessError(
            "write_override: skill_id must be a non-empty string"
        )

    _run: Callable[..., subprocess.CompletedProcess[str]] = (
        run_fn if run_fn is not None else subprocess.run
    )
    # dev-tree path; installed-package derivation deferred until packaging story
    # NOTE: --diff uses positional skill_canonical arg (NOT --skill; see compile.py line 694).
    try:
        result = _run(
            [sys.executable, str(compile_py), skill_id, "--install-dir", install_dir, "--diff"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        emit_fn({
            "action": "diff_failed",
            "skill_id": skill_id,
            "returncode": exc.returncode,
            "stderr_excerpt": str(exc.stderr or "")[:500],
        })
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
            Raises BmadSubprocessError (without emitting revert_complete)
            if the target path is a directory — unlink() would fail
            platform-inconsistently; the directory is left intact.
      str:  the file pre-existed; restore its content via write_text.
            revert_complete is emitted with deleted=False.
            If target_path is a symlink, it is removed first so
            write_text creates a regular file at target_path rather
            than writing through to the symlink destination.

    Story 7.11 AC-5 (L633): pre_write_content must have been read from disk
    using UTF-8 encoding to round-trip correctly. revert_override re-writes
    via write_text(..., encoding="utf-8"); passing content decoded with a
    different encoding (e.g., latin-1, cp1252) is a caller error and may
    corrupt the restored file. Capture the original bytes via
    `Path.read_text(encoding="utf-8")` (or read_bytes + .decode("utf-8"))
    before the override write.
    """
    target_path = Path(target_file)
    if pre_write_content is None:
        if target_path.exists():
            if target_path.is_dir():
                raise BmadSubprocessError(
                    f"revert_override: target_file is a directory, not a file: {target_file}"
                )
            target_path.unlink()
        emit_fn({
            "action": "revert_complete",
            "target_file": target_file,
            "deleted": True,
        })
    else:
        if target_path.is_symlink():
            target_path.unlink()
        target_path.write_text(pre_write_content, encoding="utf-8")
        emit_fn({
            "action": "revert_complete",
            "target_file": target_file,
            "deleted": False,
        })
