#!/usr/bin/env python3
"""bmad compile — CLI shim.

Per-skill mode flags: --skill (path), --install-dir (path), --tools (target IDE).
Install-phase mode: --install-phase --install-dir (path).
No subcommands, no --verbose, no config loading, no plugin discovery.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from bmad_compile import engine, variants
from bmad_compile.errors import CompilerError


def _emit(obj: dict) -> None:
    """Write a JSON event to stdout (sort_keys=True) and flush."""
    print(json.dumps(obj, sort_keys=True), flush=True)


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
            module = dirpath.parent.name
            _full_skill_override = (
                install_dir / "custom" / "fragments" / module / dir_name / "SKILL.template.md"
            )
            if _full_skill_override.is_file():
                _emit({
                    "schema_version": 1,
                    "kind": "warning",
                    "skill": f"{module}/{dir_name}",
                    "message": (
                        f"warning: full-skill override at '{_full_skill_override}' "
                        "bypasses fragment-level upgrade safety; this skill will not "
                        "receive fragment-level upgrades from the base module"
                    ),
                })
            try:
                engine.compile_skill(
                    dirpath,
                    install_dir,
                    target_ide=None,
                    lockfile_root=install_dir,
                    override_root=install_dir / "custom",
                )
                skill_md = install_dir / module / dir_name / "SKILL.md"
                _emit({
                    "schema_version": 1,
                    "kind": "skill",
                    "skill": f"{module}/{dir_name}",
                    "status": "ok",
                    "written": [str(skill_md)],
                    "lockfile_updated": True,
                })
                compiled += 1
            except CompilerError as exc:
                errors += 1
                _emit({
                    "schema_version": 1,
                    "kind": "error",
                    "skill": f"{dirpath.parent.name}/{dir_name}",
                    "status": "error",
                    "code": exc.code,
                    "file": exc.file,
                    "line": exc.line,
                    "col": exc.col,
                    "message": exc.desc,
                    "hint": exc.hint,
                })
            except Exception as exc:  # noqa: BLE001
                # Unexpected exception (not a CompilerError): emit a structured error
                # event so the NDJSON contract is preserved and the batch continues.
                errors += 1
                _emit({
                    "schema_version": 1,
                    "kind": "error",
                    "skill": f"{dirpath.parent.name}/{dir_name}",
                    "status": "error",
                    "code": "INTERNAL_ERROR",
                    "file": str(dirpath),
                    "line": None,
                    "col": None,
                    "message": f"{type(exc).__name__}: {exc}",
                    "hint": None,
                })
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="bmad compile", description="Compile a BMAD skill."
    )
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--skill", default=None, help="Skill source directory (per-skill mode).")
    mode.add_argument("--install-phase", action="store_true", help="Batch-compile all migrated skills under --install-dir.")
    ap.add_argument("--install-dir", required=True, help="Output directory (per-skill) or install root (install-phase).")
    ap.add_argument("--tools", default=None, help="Target IDE for variant selection (e.g. cursor, claudecode).")
    ap.add_argument(
        "--set", dest="var_overrides", action="append", metavar="KEY=VALUE",
        default=[],
        help="Override a compile-time variable (repeatable). Format: KEY=VALUE.",
    )
    args = ap.parse_args(argv)

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

    install_path = Path(args.install_dir).resolve()

    if args.install_phase:
        if not install_path.is_dir():
            sys.stderr.write(f"invalid --install-dir: must be an existing directory for --install-phase: {install_path}\n")
            return 1
        return _run_install_phase(install_path)

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

    try:
        engine.compile_skill(
            skill_path, install_path, target_ide=target_ide,
            install_flags=install_flags or None,
        )
    except CompilerError as e:
        sys.stderr.write(e.format() + "\n")
        return 2
    except FileNotFoundError as e:
        sys.stderr.write(f"file not found: {e}\n")
        return 1
    except (UnicodeDecodeError, PermissionError, IsADirectoryError, OSError) as e:
        sys.stderr.write(f"read error: {type(e).__name__}: {e}\n")
        return 1
    except RuntimeError as e:
        sys.stderr.write(f"internal error: {e}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
