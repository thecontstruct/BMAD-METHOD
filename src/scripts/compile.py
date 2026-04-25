#!/usr/bin/env python3
"""bmad compile — CLI shim.

Flags: --skill (path), --install-dir (path), --tools (target IDE).
No subcommands, no --verbose, no config loading, no plugin discovery.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from bmad_compile import engine
from bmad_compile.errors import CompilerError


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="bmad compile", description="Compile a BMAD skill."
    )
    ap.add_argument("--skill", required=True, help="Skill source directory.")
    ap.add_argument("--install-dir", required=True, help="Output directory.")
    ap.add_argument("--tools", default=None, help="Target IDE for variant selection (e.g. cursor, claudecode).")
    args = ap.parse_args(argv)

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

    install_path = Path(args.install_dir).resolve()
    if install_path.exists() and not install_path.is_dir():
        sys.stderr.write(f"invalid --install-dir: exists but is not a directory: {install_path}\n")
        return 1
    if install_path.name in ("..", "."):
        sys.stderr.write(f"invalid --install-dir: resolved basename is '{install_path.name}' — use an absolute path or a non-`..` relative path\n")
        return 1

    target_ide = args.tools.lower().strip() if args.tools else None
    target_ide = target_ide or None  # "" → None

    try:
        engine.compile_skill(skill_path, install_path, target_ide=target_ide)
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
