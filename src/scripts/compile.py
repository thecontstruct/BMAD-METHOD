#!/usr/bin/env python3
"""bmad compile — CLI shim.

Per-skill mode flags: --skill (path), --install-dir (path), --tools (target IDE).
Install-phase mode: --install-phase --install-dir (path).
No subcommands, no --verbose, no config loading, no plugin discovery.
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from bmad_compile import engine, lazy_compile as _lc, variants
from bmad_compile.errors import CompilerError, LockfileVersionMismatchError


_ANSI_GREEN = "\033[32m"
_ANSI_RED   = "\033[31m"
_ANSI_CYAN  = "\033[36m"
_ANSI_BOLD  = "\033[1m"
_ANSI_RESET = "\033[0m"


def _emit(obj: dict[str, Any]) -> None:
    """Write a JSON event to stdout (sort_keys=True) and flush."""
    print(json.dumps(obj, sort_keys=True), flush=True)


def _compile_one_skill(
    dirpath: Path,
    install_dir: Path,
    *,
    hash_skip: bool = False,
) -> list[dict[str, Any]]:
    """Compile a single skill source dir; return ordered NDJSON event dicts.

    Returns zero or more `kind:"warning"` events followed by exactly one
    `kind:"skill"` or `kind:"error"` event. Callers iterate the list to emit
    events in order and inspect the last event's `kind` to update counters.

    When `hash_skip=True` and a lockfile entry exists with all hashes matching
    current inputs, returns a single `kind:"skill"` event with `compiled=False`,
    `status="skipped"`, `lockfile_updated=False`, and `written=[]` — no engine
    invocation. Used by `--batch` mode for AC-3 hash-based skip on re-install.
    """
    events: list[dict[str, Any]] = []
    module = dirpath.parent.name
    dir_name = dirpath.name
    skill_id = f"{module}/{dir_name}"

    # AC-3 L530: guard against filesystem-root paths where dirpath.parent.name
    # is "" (e.g. Path("/skill_only").parent == Path("/")).
    if not module:
        return [{
            "schema_version": 1,
            "kind": "error",
            "skill": dir_name,
            "status": "error",
            "code": "BATCH_ENTRY_INVALID",
            "file": str(dirpath),
            "line": None,
            "col": None,
            "message": (
                f"_compile_one_skill: skill_dir has no parent module component "
                f"(filesystem-root path?): {dirpath}"
            ),
            "hint": None,
        }]

    # Hash-skip dispatch (AC-3, --batch only). install_dir == scenario_root for
    # both --install-phase and --batch (each batch entry's install_dir is the
    # _bmad install root, which is what lazy_compile.py treats as scenario_root).
    #
    # AC-3 L528: exception handler narrowed — expected TOCTOU filesystem events
    # (OSError, FileNotFoundError, PermissionError) silently recompile.
    # Programming errors (KeyError, AttributeError on malformed lockfile entries)
    # emit a kind:"warning" diagnostic before recompiling defensively.
    if hash_skip:
        lockfile_path = install_dir / "_config" / "bmad.lock"
        try:
            entry = _lc._find_lockfile_entry(lockfile_path, dir_name)
            should_skip = (
                entry is not None and not _lc._needs_recompile(entry, install_dir)
            )
        except (OSError, FileNotFoundError, PermissionError):
            # Expected TOCTOU: silently recompile.
            should_skip = False
        except Exception as exc:
            # Programming error (e.g. KeyError, AttributeError on structurally
            # malformed lockfile entry) — emit diagnostic then recompile.
            events.append({
                "schema_version": 1,
                "kind": "warning",
                "code": "HASH_SKIP_DIAGNOSTIC",
                "skill": skill_id,
                "message": (
                    f"lockfile entry for {skill_id!r} may be corrupt; "
                    f"recompiling defensively ({type(exc).__name__}: {exc})"
                ),
            })
            should_skip = False
        if should_skip:
            events.append({
                "schema_version": 1,
                "kind": "skill",
                "skill": skill_id,
                "status": "skipped",
                "written": [],
                "compiled": False,
                "lockfile_updated": False,
            })
            return events

    # Full-skill override warning (mirrors --install-phase, Story 3.4 pattern)
    _full_skill_override = (
        install_dir / "custom" / "fragments" / module / dir_name / "SKILL.template.md"
    )
    if _full_skill_override.is_file():
        events.append({
            "schema_version": 1,
            "kind": "warning",
            "skill": skill_id,
            "message": (
                f"warning: full-skill override at '{_full_skill_override}' "
                "bypasses fragment-level upgrade safety; this skill will not "
                "receive fragment-level upgrades from the base module"
            ),
        })

    # Story 5.5b AC-1: per-skill `TOML_EMPTY_ARRAY_SKIPPED` warning
    # collector. The engine appends one entry per empty TOML array
    # encountered during VariableScope.build(). NDJSON warning events
    # MUST be emitted BEFORE the per-skill kind:"skill"/"error" event so
    # consumers can correlate the warning with the skill it came from.
    # R1 P1: collect warnings BEFORE the engine call resolves outcome,
    # then emit via the deterministic order below regardless of which
    # exception path the engine took. Warnings precede the outcome
    # event in the events[] list.
    toml_warnings: list[dict[str, Any]] = []
    outcome_event: dict[str, Any] | None = None
    try:
        engine.compile_skill(
            dirpath,
            install_dir,
            target_ide=None,
            lockfile_root=install_dir,
            override_root=install_dir / "custom",
            toml_warning_sink=toml_warnings,
        )
        skill_md = install_dir / module / dir_name / "SKILL.md"
        outcome_event = {
            "schema_version": 1,
            "kind": "skill",
            "skill": skill_id,
            "status": "ok",
            "written": [str(skill_md)],
            "lockfile_updated": True,
        }
        if hash_skip:
            # --batch mode adds the per-skill `compiled` boolean (AC-3).
            outcome_event["compiled"] = True
    except CompilerError as exc:
        outcome_event = {
            "schema_version": 1,
            "kind": "error",
            "skill": skill_id,
            "status": "error",
            "code": exc.code,
            "file": exc.file,
            "line": exc.line,
            "col": exc.col,
            "message": exc.desc,
            "hint": exc.hint,
        }
    except Exception as exc:  # noqa: BLE001
        outcome_event = {
            "schema_version": 1,
            "kind": "error",
            "skill": skill_id,
            "status": "error",
            "code": "INTERNAL_ERROR",
            "file": str(dirpath),
            "line": None,
            "col": None,
            "message": f"{type(exc).__name__}: {exc}",
            "hint": None,
        }
    # R1 P1: warnings emit BEFORE the outcome event, regardless of whether
    # the engine succeeded or raised. Without this ordering, warnings
    # collected in `_flatten_toml` before a downstream resolver/render
    # error would be silently dropped.
    for w in toml_warnings:
        events.append({
            "schema_version": 1,
            "kind": "warning",
            "code": w.get("code", "TOML_EMPTY_ARRAY_SKIPPED"),
            "skill": skill_id,
            "key": w.get("key"),
            "path": w.get("path"),
        })
    if outcome_event is not None:
        events.append(outcome_event)
    return events


def _run_install_phase(install_dir: Path) -> int:
    """Walk install_dir for migrated skills, compile each, emit NDJSON events.

    Detection rule (R3-A1): a directory <dir>/ is a migrated-skill candidate
    iff it contains a file named exactly <dir>.template.md OR <dir>.<ide>.template.md
    for ide ∈ KNOWN_IDES. Workflow-output templates whose filename does NOT match
    the parent dir basename are silently skipped.

    Returns 0 on success, 1 if any skill produced a CompilerError.
    """
    compiled = 0
    errors = 0

    # Non-module dirs at depth 1 (direct children of install_dir): skip so
    # the walker never descends into _config/, custom/, scripts/, memory/, etc.
    _SKIP_AT_DEPTH_1 = frozenset({"_config", "custom", "scripts", "memory", "_memory"})

    def _walk(dirpath: Path, depth: int) -> None:
        nonlocal compiled, errors
        if depth > 6:
            return
        if depth == 1 and (dirpath.name in _SKIP_AT_DEPTH_1 or dirpath.name.startswith("_")):
            return
        try:
            entries = list(dirpath.iterdir())
        except OSError:
            return

        file_names = {e.name for e in entries if e.is_file()}
        dir_name = dirpath.name
        is_skill = (
            f"{dir_name}.template.md" in file_names
            or any(f"{dir_name}.{ide}.template.md" in file_names for ide in variants.KNOWN_IDES)
        )

        if is_skill:
            for ev in _compile_one_skill(dirpath, install_dir, hash_skip=False):
                _emit(ev)
                # ECH-3 (R1): defensive — only count "ok" skill events. With
                # hash_skip=False this is currently equivalent to `kind == "skill"`
                # (no skip events possible), but this guard prevents a future
                # regression that inadvertently passes hash_skip=True from
                # silently inflating the compiled count with skipped skills.
                if ev["kind"] == "skill" and ev.get("status") == "ok":
                    compiled += 1
                elif ev["kind"] == "error":
                    errors += 1
            return  # do not recurse into skill subdirs

        for entry in entries:
            if entry.is_dir():
                _walk(entry, depth + 1)

    _walk(install_dir, 0)

    lockfile_path = str(install_dir / "_config" / "bmad.lock")
    _emit({
        "schema_version": 1,
        "kind": "summary",
        "compiled": compiled,
        "errors": errors,
        "lockfile_path": lockfile_path,
    })

    return 0 if errors == 0 else 1


_KNOWN_BATCH_KEYS: frozenset[str] = frozenset({"skill_dir", "install_dir"})


def _run_batch(batch_file: Path) -> int:
    """Read JSON skill list from batch_file, compile each with hash-skip, emit NDJSON.

    Schema: batch_file contains a JSON array of objects with `skill_dir` and
    `install_dir` (both absolute path strings). Each entry produces zero or more
    warning events plus one skill or error event. Per-skill `compiled` boolean
    distinguishes recompiled (true) from hash-skipped (false). Summary uses an
    `int compiled` count for parity with `--install-phase`.

    Continues on per-skill error (matches `--install-phase` semantics). Returns
    0 on success, 1 if any error event was emitted (incl. JSON parse / validation).

    `LockfileVersionMismatchError` is a `CompilerError` subclass and collapses
    to exit 1 here (deliberate parity with `--install-phase`; the error event's
    `code` field carries `"LOCKFILE_VERSION_MISMATCH"` for JS callers).
    """
    try:
        raw = batch_file.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        _emit({
            "schema_version": 1,
            "kind": "error",
            "skill": None,
            "status": "error",
            "code": "BATCH_FILE_NOT_FOUND",
            "file": str(batch_file),
            "line": None,
            "col": None,
            "message": f"batch file not found: {exc}",
            "hint": None,
        })
        return 1
    except OSError as exc:
        _emit({
            "schema_version": 1,
            "kind": "error",
            "skill": None,
            "status": "error",
            "code": "BATCH_FILE_READ_ERROR",
            "file": str(batch_file),
            "line": None,
            "col": None,
            "message": f"failed to read batch file: {exc}",
            "hint": None,
        })
        return 1

    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as exc:
        _emit({
            "schema_version": 1,
            "kind": "error",
            "skill": None,
            "status": "error",
            "code": "BATCH_FILE_MALFORMED",
            "file": str(batch_file),
            "line": exc.lineno,
            "col": exc.colno,
            "message": f"batch file is not valid JSON: {exc.msg}",
            "hint": None,
        })
        return 1

    if not isinstance(entries, list):
        _emit({
            "schema_version": 1,
            "kind": "error",
            "skill": None,
            "status": "error",
            "code": "BATCH_FILE_MALFORMED",
            "file": str(batch_file),
            "line": None,
            "col": None,
            "message": "batch file root must be a JSON array",
            "hint": None,
        })
        return 1

    compiled_count = 0
    error_count = 0
    seen: set[tuple[str, str]] = set()
    last_install_dir: Path | None = None

    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            _emit({
                "schema_version": 1,
                "kind": "error",
                "skill": None,
                "status": "error",
                "code": "BATCH_ENTRY_INVALID",
                "file": str(batch_file),
                "line": None,
                "col": None,
                "message": f"entry {idx} is not a JSON object",
                "hint": None,
            })
            sys.stderr.write(
                f"error: batch entry {idx} is not a JSON object\n"
            )
            error_count += 1
            continue

        skill_dir_raw = entry.get("skill_dir")
        install_dir_raw = entry.get("install_dir")
        if not isinstance(skill_dir_raw, str) or not isinstance(install_dir_raw, str):
            _emit({
                "schema_version": 1,
                "kind": "error",
                "skill": None,
                "status": "error",
                "code": "BATCH_ENTRY_INVALID",
                "file": str(batch_file),
                "line": None,
                "col": None,
                "message": (
                    f"entry {idx} requires string fields 'skill_dir' and 'install_dir'"
                ),
                "hint": None,
            })
            sys.stderr.write(
                f"error: batch entry {idx} requires string 'skill_dir' and 'install_dir'\n"
            )
            error_count += 1
            continue

        skill_path = Path(skill_dir_raw)
        install_path = Path(install_dir_raw)
        if not skill_path.is_absolute() or not install_path.is_absolute():
            _emit({
                "schema_version": 1,
                "kind": "error",
                "skill": None,
                "status": "error",
                "code": "BATCH_ENTRY_INVALID",
                "file": str(batch_file),
                "line": None,
                "col": None,
                "message": (
                    f"entry {idx}: both 'skill_dir' and 'install_dir' must be absolute paths"
                ),
                "hint": None,
            })
            sys.stderr.write(
                f"error: batch entry {idx} requires absolute paths\n"
            )
            error_count += 1
            continue

        skill_path = skill_path.resolve()
        install_path = install_path.resolve()

        # AC-2 L526: verify install_dir exists as a directory before invoking
        # the engine. Produces a directed BATCH_ENTRY_INVALID rather than a
        # generic INTERNAL_ERROR from the engine on a missing directory.
        if not install_path.is_dir():
            _emit({
                "schema_version": 1,
                "kind": "error",
                "skill": None,
                "status": "error",
                "code": "BATCH_ENTRY_INVALID",
                "file": str(batch_file),
                "line": None,
                "col": None,
                "message": (
                    f"install_dir does not exist or is not a directory: {install_path}"
                ),
                "hint": None,
            })
            error_count += 1
            continue

        # AC-4 L532: warn on unknown batch entry keys (forward-compat tolerance).
        # Fires only for entries that passed all guards above — entries that
        # failed an earlier guard have already `continue`d without this warning.
        for k in sorted(set(entry.keys()) - _KNOWN_BATCH_KEYS):
            _emit({
                "schema_version": 1,
                "kind": "warning",
                "code": "UNKNOWN_BATCH_KEY",
                "skill": None,
                "message": f"unknown key {k!r} in batch entry {idx}; runtime did not honor it",
            })

        dedup_key = (str(skill_path), str(install_path))
        if dedup_key in seen:
            _emit({
                "schema_version": 1,
                "kind": "warning",
                "skill": f"{skill_path.parent.name}/{skill_path.name}",
                "message": "duplicate batch entry skipped",
            })
            continue
        seen.add(dedup_key)
        # Track install_dir of the last NON-DEDUP entry so the summary's
        # `lockfile_path` reflects an entry that was actually compiled (or at
        # least attempted) rather than a skipped duplicate (BH-6).
        last_install_dir = install_path

        for ev in _compile_one_skill(skill_path, install_path, hash_skip=True):
            _emit(ev)
            if ev["kind"] == "skill":
                if ev.get("compiled") is True:
                    compiled_count += 1
                # status=="skipped" with compiled=False: count toward neither compiled nor error.
            elif ev["kind"] == "error":
                error_count += 1

    summary: dict[str, Any] = {
        "schema_version": 1,
        "kind": "summary",
        "compiled": compiled_count,
        "errors": error_count,
        "lockfile_path": (
            str(last_install_dir / "_config" / "bmad.lock") if last_install_dir is not None else None
        ),
    }
    _emit(summary)

    return 0 if error_count == 0 else 1


def _colorize_diff(lines: list[str]) -> str:
    out = []
    for line in lines:
        if line.startswith(("+++", "---")):
            out.append(_ANSI_BOLD + line + _ANSI_RESET)
        elif line.startswith("+"):
            out.append(_ANSI_GREEN + line + _ANSI_RESET)
        elif line.startswith("-"):
            out.append(_ANSI_RED + line + _ANSI_RESET)
        elif line.startswith("@@"):
            out.append(_ANSI_CYAN + line + _ANSI_RESET)
        else:
            out.append(line)
    return "".join(out)


def _run_diff_mode(
    skill_path: Path,
    install_path: Path,
    target_ide: str | None,
    install_flags: dict[str, str],
) -> int:
    module_name = skill_path.parent.name
    skill_md_path = install_path / module_name / skill_path.name / "SKILL.md"
    lock_path = install_path / "_config" / "bmad.lock"

    # Save pre-compile state (bytes, not text — exact restore)
    old_skill = skill_md_path.read_bytes() if skill_md_path.is_file() else None
    old_lock = lock_path.read_bytes() if lock_path.is_file() else None

    new_skill_text: str | None = None
    try:
        engine.compile_skill(
            skill_path, install_path, target_ide=target_ide,
            lockfile_root=install_path,
            override_root=install_path / "custom",
            install_flags=install_flags or None,
        )
        new_skill_text = skill_md_path.read_text(encoding="utf-8")
    finally:
        # Restore — unconditional; runs on success, error, and KeyboardInterrupt
        if old_skill is not None:
            skill_md_path.write_bytes(old_skill)
        elif skill_md_path.is_file():
            skill_md_path.unlink()
        if old_lock is not None:
            lock_path.write_bytes(old_lock)
        elif lock_path.is_file():
            lock_path.unlink()

    # Invariant: if an exception was raised in the try block, it propagated
    # through the finally and this line is never reached. new_skill_text is set.
    assert new_skill_text is not None
    old_skill_text = old_skill.decode("utf-8") if old_skill is not None else ""
    old_lines = old_skill_text.splitlines(keepends=True)
    new_lines = new_skill_text.splitlines(keepends=True)
    skill_rel = f"{module_name}/{skill_path.name}/SKILL.md"
    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=skill_rel,
        tofile=skill_rel,
        tofiledate="(recompiled)",
    ))
    if diff:
        output = _colorize_diff(diff) if sys.stdout.isatty() else "".join(diff)
        sys.stdout.write(output)
    return 0


def _run_explain_mode(
    skill_path: Path,
    install_path: Path,
    target_ide: str | None,
    install_flags: dict[str, str],
    *,
    mode: str = "markdown",
) -> int:
    """Story 4.2/4.3: dry-run inspect mode. Compiles in memory only, writes
    nothing. `mode` selects the output renderer:
      "markdown" — Markdown+XML provenance view (Story 4.2)
      "tree"     — fragment dependency tree only (Story 4.3)
      "json"     — structured JSON output (Story 4.3)
    """
    flat_nodes, dep_tree, var_scope, cache, scenario_root, toml_layers_data = engine.explain_skill(
        skill_path, install_path,
        target_ide=target_ide,
        lockfile_root=install_path,
        override_root=install_path / "custom",
        install_flags=install_flags or None,
    )
    # This dispatch REPLACES the prior single call to engine._render_explain.
    # Do NOT add a second sys.stdout.write call — each branch below writes once.
    if mode == "tree":
        output = engine._render_explain_tree(flat_nodes, dep_tree, scenario_root)
    elif mode == "json":
        output = engine._render_explain_json(
            flat_nodes, dep_tree, var_scope, cache, scenario_root, toml_layers_data
        )
    else:  # "markdown" — Story 4.2 path
        output = engine._render_explain(flat_nodes, dep_tree, var_scope, cache, scenario_root)
    sys.stdout.write(output)
    return 0


# _RESOLVE_SKIP mirrors _SKIP_AT_DEPTH_1 in _run_install_phase and _MODULE_DIR_SKIP in engine.py
_RESOLVE_SKIP = frozenset({"_config", "custom", "scripts", "memory", "_memory"})


def _resolve_skill_canonical(canonical: str, install_dir: Path) -> "Path | None":
    # OQ-4: Reject backslash separators and path traversal components
    if "\\" in canonical:
        sys.stderr.write(f"error: invalid skill name (backslash not allowed): {canonical!r}\n")
        return None
    if "/" in canonical:
        if canonical.count("/") > 1:
            sys.stderr.write(f"error: invalid skill name (too many '/' separators): {canonical!r}\n")
            return None
        module, _, skill_name = canonical.partition("/")
        if not module or not skill_name or module in (".", "..") or skill_name in (".", ".."):
            sys.stderr.write(f"error: invalid skill name (path traversal not allowed): {canonical!r}\n")
            return None
        if module in _RESOLVE_SKIP or module.startswith("_"):
            sys.stderr.write(f"error: invalid skill name: module {module!r} is reserved\n")
            return None
        skill_path = install_dir / module / skill_name
        if not skill_path.is_dir():
            sys.stderr.write(
                f"error: skill not found: {canonical!r} — no directory at {skill_path}\n"
            )
            return None
        return skill_path
    else:
        if not canonical or canonical in (".", ".."):
            sys.stderr.write(f"error: invalid skill name: {canonical!r}\n")
            return None
        try:
            entries = list(install_dir.iterdir())
        except OSError as exc:
            sys.stderr.write(f"error: cannot read install directory: {exc}\n")
            return None
        matches = [
            entry / canonical
            for entry in entries
            if entry.is_dir()
            and not entry.name.startswith("_")
            and entry.name not in _RESOLVE_SKIP
            and (entry / canonical).is_dir()
        ]
        if len(matches) == 0:
            sys.stderr.write(
                f"error: skill not found: {canonical!r} — no match under {install_dir}\n"
            )
            return None
        if len(matches) > 1:
            sorted_matches = sorted(matches, key=lambda p: (p.parent.name, p.name))
            qualified = ", ".join(
                f"{p.parent.name}/{p.name}" for p in sorted_matches
            )
            sys.stderr.write(
                f"error: ambiguous skill name {canonical!r} — found in multiple modules: {qualified}\n"
                f"hint: use the qualified form, e.g. '{sorted_matches[0].parent.name}/{canonical}'\n"
            )
            return None
        return matches[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="bmad compile", description="Compile a BMAD skill."
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--skill", default=None, help="Skill source directory (per-skill mode).")
    mode.add_argument("--install-phase", action="store_true", help="Batch-compile all migrated skills under --install-dir.")
    mode.add_argument(
        "--batch", default=None, metavar="SKILLS_JSON",
        help="JSON file listing skills to compile in batch (single interpreter cold-start).",
    )
    ap.add_argument(
        "--install-dir", required=False, default=None,
        help="Output directory (per-skill) or install root (install-phase). Not required for --batch (each entry carries its own install_dir).",
    )
    ap.add_argument("--tools", default=None, help="Target IDE for variant selection (e.g. cursor, claudecode).")
    ap.add_argument(
        "--set", dest="var_overrides", action="append", metavar="KEY=VALUE",
        default=[],
        help="Override a compile-time variable (repeatable). Format: KEY=VALUE.",
    )
    ap.add_argument(
        "skill_canonical", nargs="?", default=None,
        help="Canonical skill name: 'module/skill' (qualified) or 'skill' (short, searched).",
    )
    ap.add_argument(
        "--diff", action="store_true",
        help="Dry-run mode: emit unified diff to stdout; no file writes.",
    )
    ap.add_argument(
        "--explain", action="store_true",
        help="Emit Markdown-with-inline-XML provenance view; no file writes.",
    )
    ap.add_argument(
        "--tree", action="store_true",
        help="With --explain: emit fragment dependency tree only (no content).",
    )
    ap.add_argument(
        "--json", action="store_true",
        help="With --explain: emit structured JSON provenance output.",
    )
    args = ap.parse_args(argv)
    # Normalize empty-string positional to None (argparse can produce '' for nargs="?")
    args.skill_canonical = args.skill_canonical or None

    # Validation guards
    if args.skill_canonical is not None and args.skill:
        sys.stderr.write("error: positional skill argument cannot be combined with --skill\n")
        return 1
    if args.skill_canonical is not None and args.install_phase:
        sys.stderr.write("error: positional skill argument cannot be combined with --install-phase\n")
        return 1
    if args.skill_canonical is not None and args.batch:
        sys.stderr.write("error: positional skill argument cannot be combined with --batch\n")
        return 1
    if args.batch and args.diff:
        sys.stderr.write("error: --batch cannot be combined with --diff\n")
        return 1
    if args.batch and args.explain:
        sys.stderr.write("error: --batch cannot be combined with --explain\n")
        return 1
    if args.batch and args.tree:
        sys.stderr.write("error: --batch cannot be combined with --tree\n")
        return 1
    if args.batch and args.json:
        sys.stderr.write("error: --batch cannot be combined with --json\n")
        return 1
    if args.batch and args.var_overrides:
        sys.stderr.write("error: --set cannot be used with --batch (per-entry overrides not supported)\n")
        return 1
    if args.diff and args.install_phase:
        sys.stderr.write("error: --diff cannot be used with --install-phase\n")
        return 1
    if args.diff and args.skill_canonical is None and not args.skill:
        sys.stderr.write("error: --diff requires a skill argument\n")
        return 1
    if args.diff and args.skill and args.skill_canonical is None:
        sys.stderr.write("error: --diff is not supported with --skill; use the positional <skill> argument instead\n")
        return 1
    # Story 4.2: --explain validation guards (mirror --diff structure)
    if args.explain and args.install_phase:
        sys.stderr.write("error: --explain cannot be used with --install-phase\n")
        return 1
    if args.explain and args.skill_canonical is None and not args.skill:
        sys.stderr.write("error: --explain requires a skill argument\n")
        return 1
    if args.explain and args.skill and args.skill_canonical is None:
        sys.stderr.write("error: --explain is not supported with --skill; use the positional <skill> argument instead\n")
        return 1
    if args.explain and args.diff:
        sys.stderr.write("error: --explain and --diff are mutually exclusive\n")
        return 1
    # Story 4.3: --tree and --json require --explain; they are mutually exclusive;
    # they cannot combine with --diff (belt-and-suspenders — --diff and --explain
    # are already mutually exclusive, so this fires only when --explain is absent).
    if args.tree and not args.explain:
        sys.stderr.write("error: --tree requires --explain\n")
        return 1
    if args.json and not args.explain:
        sys.stderr.write("error: --json requires --explain\n")
        return 1
    if args.tree and args.json:
        sys.stderr.write("error: --tree and --json are mutually exclusive\n")
        return 1
    if (args.tree or args.json) and args.diff:
        sys.stderr.write("error: --tree cannot be combined with --diff\n")
        return 1

    install_flags: dict[str, str] = {}
    for kv in (args.var_overrides or []):
        if "=" not in kv:
            sys.stderr.write(f"error: --set argument must be KEY=VALUE, got: {kv!r}\n")
            return 1
        k, _, v = kv.partition("=")
        k = k.strip()
        if not k:
            sys.stderr.write(f"error: --set KEY is empty in: {kv!r}\n")
            return 1
        install_flags[k] = v

    # --batch dispatch MUST occur BEFORE install_path resolution: --batch does
    # not require --install-dir (each JSON entry carries its own install_dir),
    # so reaching Path(args.install_dir).resolve() with args.install_dir=None
    # would raise TypeError (R2-P1).
    if args.batch:
        return _run_batch(Path(args.batch))

    if args.install_dir is None:
        sys.stderr.write("error: --install-dir is required (only --batch may omit it)\n")
        return 1

    install_path = Path(args.install_dir).resolve()

    if args.install_phase:
        if not install_path.is_dir():
            sys.stderr.write(f"invalid --install-dir: must be an existing directory for --install-phase: {install_path}\n")
            return 1
        return _run_install_phase(install_path)

    # Positional <skill> mode (AC 1, AC 2)
    if args.skill_canonical is not None:
        if not install_path.is_dir():
            sys.stderr.write(f"invalid --install-dir: must be an existing directory: {install_path}\n")
            return 1
        skill_path = _resolve_skill_canonical(args.skill_canonical, install_path)
        if skill_path is None:
            return 1
        target_ide = args.tools.lower().strip() if args.tools else None
        target_ide = target_ide or None  # "" → None
        # Full-skill override warning (mirrors per-skill mode pattern, Story 3.4)
        _module_name = skill_path.parent.name
        _fso = install_path / "custom" / "fragments" / _module_name / skill_path.name / "SKILL.template.md"
        if _fso.is_file():
            sys.stderr.write(
                f"warning: full-skill override at '{_fso}' "
                "bypasses fragment-level upgrade safety; this skill will not "
                "receive fragment-level upgrades from the base module\n"
            )
        if args.explain:
            _explain_mode = "tree" if args.tree else "json" if args.json else "markdown"
            try:
                return _run_explain_mode(skill_path, install_path, target_ide, install_flags, mode=_explain_mode)
            except CompilerError as e:
                sys.stderr.write(e.format() + "\n")
                return 2 if isinstance(e, LockfileVersionMismatchError) else 1
            except FileNotFoundError as e:
                sys.stderr.write(f"file not found: {e}\n")
                return 1
            except (UnicodeDecodeError, PermissionError, IsADirectoryError, OSError) as e:
                sys.stderr.write(f"read error: {type(e).__name__}: {e}\n")
                return 1
            except RuntimeError as e:
                sys.stderr.write(f"internal error: {e}\n")
                return 1
        if args.diff:
            try:
                return _run_diff_mode(skill_path, install_path, target_ide, install_flags)
            except CompilerError as e:
                sys.stderr.write(e.format() + "\n")
                return 2 if isinstance(e, LockfileVersionMismatchError) else 1
            except FileNotFoundError as e:
                sys.stderr.write(f"file not found: {e}\n")
                return 1
            except (UnicodeDecodeError, PermissionError, IsADirectoryError, OSError) as e:
                sys.stderr.write(f"read error: {type(e).__name__}: {e}\n")
                return 1
            except RuntimeError as e:
                sys.stderr.write(f"internal error: {e}\n")
                return 1
        # Normal compile via positional
        # Story 5.5b AC-1 + R1 P1: per-skill stderr warning emission. The
        # warning sink is populated by `_flatten_toml` during the build,
        # which runs BEFORE the resolver/render phases that may raise.
        # Emit via try/finally so diagnostics are preserved even when the
        # subsequent compile fails — without this, R1 flagged that the
        # warnings would be silently dropped on any CompilerError /
        # RuntimeError / OSError exit path.
        toml_warnings_pos: list[dict[str, Any]] = []
        try:
            try:
                engine.compile_skill(
                    skill_path, install_path, target_ide=target_ide,
                    lockfile_root=install_path,
                    override_root=install_path / "custom",
                    install_flags=install_flags or None,
                    toml_warning_sink=toml_warnings_pos,
                )
            except CompilerError as e:
                sys.stderr.write(e.format() + "\n")
                return 2 if isinstance(e, LockfileVersionMismatchError) else 1
            except FileNotFoundError as e:
                sys.stderr.write(f"file not found: {e}\n")
                return 1
            except (UnicodeDecodeError, PermissionError, IsADirectoryError, OSError) as e:
                sys.stderr.write(f"read error: {type(e).__name__}: {e}\n")
                return 1
            except (RuntimeError, ValueError) as e:
                # Story 5.5b R2 P1: catch ValueError too. R1 P2 added a
                # defensive `raise ValueError(...)` in `_lockfile_lock_path`
                # for the lock-file-as-input programmer-error case; without
                # this clause, the exception would escape main() as a raw
                # traceback rather than cleanly exit 1.
                sys.stderr.write(f"internal error: {e}\n")
                return 1
            return 0
        finally:
            for w in toml_warnings_pos:
                sys.stderr.write(
                    f"warning: {w.get('code', 'TOML_EMPTY_ARRAY_SKIPPED')}: "
                    f"empty array '{w.get('key')}' in {w.get('path')} "
                    "was skipped during compile (no scalar produced)\n"
                )

    # Per-skill mode (unchanged)
    if not args.skill:
        sys.stderr.write("error: --skill is required when not using --install-phase\n")
        return 1

    skill_path = Path(args.skill).resolve()
    if not skill_path.exists():
        sys.stderr.write(f"file not found: --skill path does not exist: {skill_path}\n")
        return 1
    if not skill_path.is_dir():
        sys.stderr.write(f"invalid --skill: not a directory: {skill_path}\n")
        return 1
    if skill_path.name in ("..", "."):
        sys.stderr.write(f"invalid --skill: resolved basename is '{skill_path.name}' — use an absolute path or a non-`..` relative path\n")
        return 1

    if install_path.exists() and not install_path.is_dir():
        sys.stderr.write(f"invalid --install-dir: exists but is not a directory: {install_path}\n")
        return 1
    if install_path.name in ("..", "."):
        sys.stderr.write(f"invalid --install-dir: resolved basename is '{install_path.name}' — use an absolute path or a non-`..` relative path\n")
        return 1

    target_ide = args.tools.lower().strip() if args.tools else None
    target_ide = target_ide or None  # "" → None

    # Per-skill mode: engine hardcodes current_module="core" (engine.py:128-130
    # for the lockfile_root=None branch; preserves Story 1.2 behavior). The
    # warning probe must mirror that — using `skill_path.parent.name` here
    # would fire on a non-effective path and miss the override the engine
    # actually picks up at fragments/core/<skill>/SKILL.template.md.
    _per_skill_override_root = skill_path.parent.parent / "_bmad" / "custom"
    _full_skill_override = (
        _per_skill_override_root / "fragments" / "core" / skill_path.name / "SKILL.template.md"
    )
    if _full_skill_override.is_file():
        sys.stderr.write(
            f"warning: full-skill override at '{_full_skill_override}' "
            "bypasses fragment-level upgrade safety; this skill will not "
            "receive fragment-level upgrades from the base module\n"
        )

    # Story 5.5b AC-1 + R1 P1: per-skill stderr warning emission for
    # --skill mode. Emit via try/finally so warnings collected before a
    # mid-build exception are still surfaced to the user.
    toml_warnings_skill: list[dict[str, Any]] = []
    try:
        try:
            engine.compile_skill(
                skill_path, install_path, target_ide=target_ide,
                install_flags=install_flags or None,
                toml_warning_sink=toml_warnings_skill,
            )
        except CompilerError as e:
            sys.stderr.write(e.format() + "\n")
            return 2 if isinstance(e, LockfileVersionMismatchError) else 1
        except FileNotFoundError as e:
            sys.stderr.write(f"file not found: {e}\n")
            return 1
        except (UnicodeDecodeError, PermissionError, IsADirectoryError, OSError) as e:
            sys.stderr.write(f"read error: {type(e).__name__}: {e}\n")
            return 1
        except (RuntimeError, ValueError) as e:
            # Story 5.5b R2 P1: see positional path for rationale (R1 P2
            # `_lockfile_lock_path` defensive raise).
            sys.stderr.write(f"internal error: {e}\n")
            return 1
        return 0
    finally:
        for w in toml_warnings_skill:
            sys.stderr.write(
                f"warning: {w.get('code', 'TOML_EMPTY_ARRAY_SKIPPED')}: "
                f"empty array '{w.get('key')}' in {w.get('path')} "
                "was skipped during compile (no scalar produced)\n"
            )


if __name__ == "__main__":
    raise SystemExit(main())
