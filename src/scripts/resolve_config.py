#!/usr/bin/env python3
"""
Resolve BMad's central config using four-layer TOML merge.

Reads from four layers (highest priority last):
  1. {project-root}/_bmad/config.toml              (installer-owned team)
  2. {project-root}/_bmad/config.user.toml         (installer-owned user)
  3. {project-root}/_bmad/custom/config.toml       (human-authored team, committed)
  4. {project-root}/_bmad/custom/config.user.toml  (human-authored user, gitignored)

Outputs merged JSON to stdout. Errors go to stderr.

Requires Python 3.11+ (uses stdlib `tomllib`). No `uv`, no `pip install`,
no virtualenv — plain `python3` is sufficient.

  python3 resolve_config.py --project-root /abs/path/to/project
  python3 resolve_config.py --project-root ... --key core
  python3 resolve_config.py --project-root ... --key agents

Merge rules (same as resolve_customization.py):
  - Scalars: override wins
  - Tables: deep merge
  - Arrays of tables where every item shares `code` or `id`: merge by that key
  - All other arrays: append
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    sys.stderr.write(
        "error: Python 3.11+ is required (stdlib `tomllib` not found).\n"
    )
    sys.exit(3)

from bmad_compile.toml_merge import merge_layers


_MISSING = object()


def load_toml(file_path: Path, required: bool = False) -> dict[str, Any]:
    if not file_path.exists():
        if required:
            sys.stderr.write(f"error: required config file not found: {file_path}\n")
            sys.exit(1)
        return {}
    try:
        with file_path.open("rb") as f:
            parsed = tomllib.load(f)
        if not isinstance(parsed, dict):
            return {}
        return parsed
    except tomllib.TOMLDecodeError as error:
        level = "error" if required else "warning"
        sys.stderr.write(f"{level}: failed to parse {file_path}: {error}\n")
        if required:
            sys.exit(1)
        return {}
    except OSError as error:
        level = "error" if required else "warning"
        sys.stderr.write(f"{level}: failed to read {file_path}: {error}\n")
        if required:
            sys.exit(1)
        return {}


def extract_key(data: dict[str, Any], dotted_key: str) -> Any:
    parts = dotted_key.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return _MISSING
    return current


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve BMad central config using four-layer TOML merge.",
    )
    parser.add_argument(
        "--project-root", "-p", required=True,
        help="Absolute path to the project root (contains _bmad/)",
    )
    parser.add_argument(
        "--key", "-k", action="append", default=[],
        help="Dotted field path to resolve (repeatable). Omit for full dump.",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    bmad_dir = project_root / "_bmad"

    base_team = load_toml(bmad_dir / "config.toml", required=True)
    base_user = load_toml(bmad_dir / "config.user.toml")
    custom_team = load_toml(bmad_dir / "custom" / "config.toml")
    custom_user = load_toml(bmad_dir / "custom" / "config.user.toml")

    merged = merge_layers(base_team, base_user, custom_team, custom_user)

    output: dict[str, Any]
    if args.key:
        output = {}
        for key in args.key:
            value = extract_key(merged, key)
            if value is not _MISSING:
                output[key] = value
    else:
        output = merged

    sys.stdout.write(json.dumps(output, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
