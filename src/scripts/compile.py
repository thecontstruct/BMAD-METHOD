#!/usr/bin/env python3
"""bmad compile — minimal CLI shim (Story 1.1 scope).

Two flags only: --skill (path), --install-dir (path). No subcommands, no
--verbose, no config loading, no plugin discovery. Story 1.2+ extends the
pipeline; this shim stays thin.
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
    args = ap.parse_args(argv)
    skill_path = Path(args.skill)
    if not skill_path.exists():
        sys.stderr.write(f"file not found: --skill path does not exist: {skill_path}\n")
        return 1
    if not skill_path.is_dir():
        sys.stderr.write(f"invalid --skill: not a directory: {skill_path}\n")
        return 1
    install_path = Path(args.install_dir)
    if install_path.exists() and not install_path.is_dir():
        sys.stderr.write(f"invalid --install-dir: exists but is not a directory: {install_path}\n")
        return 1
    try:
        engine.compile_skill(skill_path, install_path)
    except CompilerError as e:
        sys.stderr.write(e.format() + "\n")
        return 2
    except FileNotFoundError as e:
        sys.stderr.write(f"file not found: {e}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
