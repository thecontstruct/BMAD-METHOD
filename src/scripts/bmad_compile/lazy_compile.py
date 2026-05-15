"""Lazy-compile cache-coherence guard for SKILL.md at skill-entry.

Invoked as:
    python -m bmad_compile.lazy_compile <skill> --project-root <path> [--tools <ide>]

Algorithm:
1. Read bmad.lock; find the lockfile entry for <skill>.
2. If no entry, no lockfile, or SKILL.md missing: trigger slow path.
3. Re-hash all tracked inputs (prose fragments, glob match-sets, TOML-layer
   variables) and compare against stored hashes.
4. All match (fast path): emit existing SKILL.md to stdout, exit 0.
5. Any mismatch (slow path): call engine.compile_skill(), emit fresh SKILL.md
   to stdout, exit 0.
6. CompilerError: write formatted error to stderr, exit 1.

Tracked input categories (v1):
- Prose fragments: fragments[].hash
- Glob match-sets: glob_inputs[].match_set_hash
- TOML-layer variables: variables[].value_hash where source == "toml"
- YAML config variables: OUT OF SCOPE for v1. Changes to core/config.yaml or
  custom/config.yaml are NOT detected by this guard; a manual
  'bmad compile <skill>' or 'bmad upgrade' is needed. (Story 5.5b)

compiled_hash NOT verified (OQ-2): the guard's contract is "inputs unchanged
→ output is correct by construction." A manually edited SKILL.md is emitted
as-is on the fast path; 'bmad compile <skill>' restores it.

Concurrency (Story 5.5a): advisory file-lock on <skill-dir>/.compiling.lock
serializes concurrent slow-path invocations for the same skill. POSIX uses
fcntl.flock; Windows uses msvcrt.locking. --lock-timeout-seconds (default 300s)
controls the wait limit. After acquiring the lock, the guard re-reads the lockfile
into fresh_entry and re-runs _needs_recompile: if a parallel compile completed while
waiting, the guard emits the fresh SKILL.md without recompiling.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path  # pragma: allow-raw-io
from typing import Any

from . import engine, errors, io
from .io import PurePosixPath

# Directories at scenario-root depth-1 that are never module dirs.
# Mirrors engine._MODULE_DIR_SKIP and compile.py's _SKIP_AT_DEPTH_1.
_MODULE_DIR_SKIP: frozenset[str] = frozenset(
    {"_config", "custom", "scripts", "memory", "_memory"}
)

# Override tiers the guard checks for on-disk absence.
# Note: drift.py defines _OVERRIDE_TIERS = frozenset({"user-module-fragment",
# "user-override"}) which intentionally excludes "user-full-skill" — drift.py
# only tracks prose-fragment drift for those two tiers. The guard needs all
# three: a missing user-full-skill file means the engine would fall back to
# base-tier compilation on the slow path, so its absence must trigger recompile.
_GUARD_OVERRIDE_TIERS: frozenset[str] = frozenset(
    {"user-module-fragment", "user-override", "user-full-skill"}
)


# ---------------------------------------------------------------------------
# Lockfile helpers
# ---------------------------------------------------------------------------

def _find_lockfile_entry(lockfile_path: Path, skill: str) -> dict[str, Any] | None:
    """Return the lockfile entry dict for skill, or None if absent/unreadable."""
    if not io.is_file(str(lockfile_path)):
        return None
    try:
        data = json.loads(io.read_template(str(lockfile_path)))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    for entry in data.get("entries") or []:
        if isinstance(entry, dict) and entry.get("skill") == skill:
            return entry
    return None


# ---------------------------------------------------------------------------
# Module / path reconstruction
# ---------------------------------------------------------------------------

def _infer_module(entry: dict[str, Any] | None) -> str | None:
    """Infer module name from base/variant fragment paths in the lockfile entry.

    Returns None when entry is None or no qualifying fragment exists.
    """
    if entry is None:
        return None
    for frag in entry.get("fragments") or []:
        if not isinstance(frag, dict):
            continue
        if frag.get("resolved_from") in ("base", "variant"):
            parts = PurePosixPath(frag.get("path", "")).parts
            if len(parts) >= 2:
                return parts[0]
    return None


def _scan_for_module(scenario_root: Path, skill: str) -> str:
    """Scan scenario_root for exactly one module directory containing <skill>.

    Raises RuntimeError on zero or more than one match.
    """
    found: list[str] = []
    for posix_entry in io.list_dir_sorted(str(scenario_root)):
        name = posix_entry.name
        if name in _MODULE_DIR_SKIP:
            continue
        if not io.is_dir(str(scenario_root / name)):
            continue
        if io.is_dir(str(scenario_root / name / skill)):
            found.append(name)
    if len(found) == 1:
        return found[0]
    if not found:
        raise RuntimeError(
            f"Cannot locate skill {skill!r} under {scenario_root}: "
            "no module directory contains it. Is this a valid bmad project?"
        )
    raise RuntimeError(
        f"Ambiguous: skill {skill!r} found in multiple modules "
        f"under {scenario_root}: {found}"
    )


def _reconstruct_paths(
    entry: dict[str, Any] | None,
    scenario_root: Path,
    skill: str,
) -> tuple[Path, Path]:
    """Return (skill_dir, install_dir).

    install_dir is always scenario_root. skill_dir is derived from the lockfile
    entry (fast) or a filesystem scan (when entry is None or has no base frags).
    """
    module = _infer_module(entry)
    if module is None:
        module = _scan_for_module(scenario_root, skill)
    return scenario_root / module / skill, scenario_root


def _reconstruct_skill_md_path(
    entry: dict[str, Any] | None,
    scenario_root: Path,
    skill: str,
    skill_dir: Path | None = None,
) -> Path | None:
    """Return the absolute path to SKILL.md, or None if inference fails."""
    if skill_dir is not None:
        return skill_dir / "SKILL.md"
    try:
        sd, _ = _reconstruct_paths(entry, scenario_root, skill)
        return sd / "SKILL.md"
    except RuntimeError:
        return None


# ---------------------------------------------------------------------------
# Hash-dispatch: does the skill need recompilation?
# ---------------------------------------------------------------------------

def _needs_recompile(entry: dict[str, Any], scenario_root: Path) -> bool:
    """Return True if any tracked input hash differs from the lockfile stored hash."""
    from .drift import (
        _detect_prose_fragment_drift,
        _detect_glob_drift,  # pragma: allow-raw-io
        _detect_toml_variable_drift,
    )
    # Override-tier fragments absent from disk: _detect_prose_fragment_drift
    # (drift.py:202) silently skips them — it only reports missing BASE fragments.
    # For the guard, a missing override file means the engine would use the base
    # version on recompile, so the rendered output would differ → slow path.
    for _frag in (entry.get("fragments") or []):
        if not isinstance(_frag, dict):
            continue
        if _frag.get("resolved_from") in _GUARD_OVERRIDE_TIERS:
            _parts = PurePosixPath(_frag.get("path", "")).parts
            _abs = str(scenario_root.joinpath(*_parts)) if _parts else ""
            if _abs and not io.is_file(_abs):
                return True
    if _detect_prose_fragment_drift(entry, scenario_root):
        return True
    if _detect_glob_drift(entry, scenario_root):  # pragma: allow-raw-io
        return True
    toml_changes, _, _ = _detect_toml_variable_drift(entry, scenario_root)
    return bool(toml_changes)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="lazy-compile cache-coherence guard",
    )
    parser.add_argument("skill", help="skill basename (e.g. bmad-help)")
    parser.add_argument(
        "--project-root",
        default=str(Path.cwd()),  # pragma: allow-raw-io
        help="project root directory (default: current working directory)",
    )
    parser.add_argument(
        "--tools",
        default=None,
        help="target IDE for variant compilation (e.g. cursor, windsurf)",
    )
    parser.add_argument(
        "--lock-timeout-seconds",
        type=float,
        default=300.0,
        help="advisory lock wait timeout in seconds (default: 300)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Parse args, dispatch fast or slow path, return exit code."""
    args = _parse_args(argv)
    project_root = Path(args.project_root).resolve()
    lockfile_path = project_root / "_bmad" / "_config" / "bmad.lock"
    scenario_root = project_root / "_bmad"

    if args.lock_timeout_seconds < 0:
        sys.stderr.write(
            f"MISSING_FRAGMENT: ?:?:?: "
            f"Invalid lock timeout: timeout_seconds must be >= 0, "
            f"got {args.lock_timeout_seconds}\n"
        )
        return 1

    entry = _find_lockfile_entry(lockfile_path, args.skill)
    skill_md_path = _reconstruct_skill_md_path(entry, scenario_root, args.skill)

    needs_recompile = (
        entry is None
        or skill_md_path is None
        or not io.is_file(str(skill_md_path))
        or _needs_recompile(entry, scenario_root)
    )

    if not needs_recompile:
        # Fast path: all hashes match and SKILL.md exists on disk.
        sys.stdout.write(io.read_template(str(skill_md_path)))
        return 0

    # Slow path: acquire advisory lock before recompile.
    try:
        skill_dir, install_dir = _reconstruct_paths(entry, scenario_root, args.skill)
    except RuntimeError as exc:
        sys.stderr.write(f"MISSING_FRAGMENT: {scenario_root}:?:?: {exc}\n")
        return 1

    if not io.is_dir(str(skill_dir)):
        sys.stderr.write(
            f"MISSING_FRAGMENT: {skill_dir}:?:?: "
            f"Skill directory missing: {skill_dir}\n"
        )
        return 1

    lock_path = str(skill_dir / ".compiling.lock")
    lock_fd: int | None = None
    try:
        lock_fd = io.acquire_lock(lock_path, args.lock_timeout_seconds)
    except io.LockTimeoutError:
        sys.stderr.write(
            f"Compile lock timeout for skill {args.skill!r} after "
            f"{args.lock_timeout_seconds:.0f}s; another process may be compiling\n"
        )
        return 1
    except OSError as exc:
        # Non-retriable lock error (e.g., EACCES permission denied on .compiling.lock,
        # ENOSPC disk full). Exit cleanly rather than propagating a traceback.
        sys.stderr.write(
            f"MISSING_FRAGMENT: {lock_path}:?:?: "
            f"Cannot acquire compile lock: {exc}\n"
        )
        return 1

    try:
        # Re-read lockfile after acquiring lock — a parallel compile may have
        # updated it while we waited. Use fresh_entry (not `entry`) to avoid
        # shadowing the outer variable that was used for _reconstruct_paths above.
        fresh_entry = _find_lockfile_entry(lockfile_path, args.skill)
        # AC-3: Re-validate paths from post-lock lockfile state.
        try:
            _post_lock_skill_dir, _ = _reconstruct_paths(
                fresh_entry, scenario_root, args.skill
            )
        except RuntimeError:
            _post_lock_skill_dir = None  # skill disappeared from disk
        if _post_lock_skill_dir != skill_dir:
            sys.stderr.write(
                f"MISSING_FRAGMENT: {lock_path}:?:?: "
                f"Skill structure changed during lock acquisition: "
                f"pre-lock path {skill_dir}, post-lock path {_post_lock_skill_dir}\n"
            )
            return 1
        # skill_dir is already known from above; pass it directly to avoid a
        # redundant _reconstruct_paths call.
        fresh_skill_md_path = _reconstruct_skill_md_path(
            fresh_entry, scenario_root, args.skill, skill_dir=skill_dir
        )
        needs_recompile_now = (
            fresh_entry is None
            or fresh_skill_md_path is None
            or not io.is_file(str(fresh_skill_md_path))
            or _needs_recompile(fresh_entry, scenario_root)
        )
        if not needs_recompile_now:
            # Parallel compile completed — emit without recompiling.
            sys.stdout.write(io.read_template(str(fresh_skill_md_path)))
            return 0

        # Still needs compile (first holder, or previous holder was killed mid-compile).
        try:
            engine.compile_skill(
                skill_dir,
                install_dir,
                args.tools or None,
                lockfile_root=install_dir,
                # override_root MUST be explicit. Without it, engine._compile_core()
                # derives candidate_override_root = scenario_root / "_bmad" / "custom"
                # where scenario_root = skill_posix.parent.parent. For the guard's
                # skill_dir (<project_root>/_bmad/<module>/<skill>), parent.parent is
                # <project_root>/_bmad, so the engine probes
                # <project_root>/_bmad/_bmad/custom (doubled _bmad) — a path that
                # does not exist — causing override_root=None and silently disabling
                # all user overrides on the slow path.
                override_root=install_dir / "custom",
            )
        except errors.CompilerError as exc:
            sys.stderr.write(exc.format() + "\n")
            return 1

        # Re-read freshly written SKILL.md from the canonical engine output path.
        # Guard against the (unlikely) case where engine succeeded but SKILL.md is
        # absent (e.g., module-inference mismatch between guard and engine).
        fresh_skill_md = skill_dir / "SKILL.md"
        try:
            sys.stdout.write(io.read_template(str(fresh_skill_md)))
        except OSError as exc:
            sys.stderr.write(
                f"MISSING_FRAGMENT: {fresh_skill_md}:?:?: "
                f"SKILL.md not found after compile: {exc}\n"
            )
            return 1
        return 0
    finally:
        if lock_fd is not None:
            io.release_lock(lock_fd)


if __name__ == "__main__":
    sys.exit(main())
