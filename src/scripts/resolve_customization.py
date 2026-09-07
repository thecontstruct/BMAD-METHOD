#!/usr/bin/env python3
"""
Resolve customization for a BMad skill using three-layer TOML merge.

Reads customization from three layers (highest priority first):
  1. {project-root}/_bmad/custom/{name}.user.toml  (personal, gitignored)
  2. {project-root}/_bmad/custom/{name}.toml        (team/org, committed)
  3. {skill-root}/customize.toml                    (skill defaults)

Skill name is derived from the basename of the skill directory.

Outputs merged JSON to stdout. Errors go to stderr.

Uses only the Python stdlib (`tomllib`) — no third-party dependencies.
BMad is standardizing on `uv run` to invoke scripts (uv provisions a suitable
interpreter for you); a plain `python3` on PATH still works during the
transition. Either runner needs Python 3.11+ for `tomllib`.

  uv run resolve_customization.py --skill /abs/path/to/skill-dir
  uv run resolve_customization.py --skill ... --key agent
  uv run resolve_customization.py --skill ... --key agent.menu

Merge rules (purely structural — no field-name special-casing):
  - Scalars (string, int, bool, float): override wins
  - Tables: deep merge (recursively apply these rules)
  - Arrays of tables where every item shares the *same* identifier
    field (every item has `code`, or every item has `id`):
    merge by that key (matching keys replace, new keys append)
  - All other arrays — including arrays where only some items have
    `code` or `id`, or where items mix the two keys:
    append (base items followed by override items)

No removal mechanism — overrides cannot delete base items. To suppress
a default, fork the skill or override the item by code with a no-op
description/prompt.
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
        "Install a newer Python or run the resolution manually per the\n"
        "fallback instructions in the skill's SKILL.md.\n"
    )
    sys.exit(3)

from bmad_compile.toml_merge import merge_layers


_MISSING = object()


def find_project_root(start: Path) -> Path | None:
    """Nearest ancestor holding `_bmad/`, falling back to the nearest `.git`."""
    git_root: Path | None = None
    current = start.resolve()
    while True:
        if (current / "_bmad").is_dir():
            return current
        if git_root is None and (current / ".git").exists():
            git_root = current
        parent = current.parent
        if parent == current:
            return git_root
        current = parent


def script_project_root() -> Path | None:
    """Return the project root implied by an installed resolver path."""
    parents = Path(__file__).resolve().parents
    if len(parents) >= 3 and parents[0].name == "scripts" and parents[1].name == "_bmad":
        return parents[2]
    return None


def candidate_project_roots(skill_dir: Path) -> list[Path]:
    """Return plausible project roots, ordered by the trustworthy context."""
    ordered: list[Path] = []
    for root in (
        find_project_root(skill_dir),
        find_project_root(Path.cwd()),
        script_project_root(),
    ):
        if root is not None and root not in ordered:
            ordered.append(root)
    return ordered


def has_override(root: Path, skill_name: str) -> bool:
    custom_dir = root / "_bmad" / "custom"
    return any(
        (custom_dir / name).is_file()
        for name in (f"{skill_name}.toml", f"{skill_name}.user.toml")
    )


def warn_on_masked_override(chosen: Path, rejected: list[Path], skill_name: str) -> None:
    if has_override(chosen, skill_name):
        return
    for root in rejected:
        if has_override(root, skill_name):
            sys.stderr.write(
                f"note: resolved project root {chosen} has no customization for "
                f"`{skill_name}`, but {root} does. Using {chosen}; pass "
                f"--project-root to select the other explicitly.\n"
            )
            return


def load_toml(file_path: Path, required: bool = False) -> dict[str, Any]:
    if not file_path.exists():
        if required:
            sys.stderr.write(f"error: required customization file not found: {file_path}\n")
            sys.exit(1)
        return {}
    try:
        with file_path.open("rb") as f:
            parsed = tomllib.load(f)
        if not isinstance(parsed, dict):
            if required:
                sys.stderr.write(f"error: {file_path} did not parse to a table\n")
                sys.exit(1)
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


def write_json_stdout(output: Any) -> None:
    """Write JSON as UTF-8 so Windows cp1252/cp932 stdout can carry emoji icons."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")
    sys.stdout.write(json.dumps(output, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve customization for a BMad skill using three-layer TOML merge.",
        add_help=True,
    )
    parser.add_argument(
        "--skill", "-s", required=True,
        help="Absolute path to the skill directory (must contain customize.toml)",
    )
    parser.add_argument(
        "--key", "-k", action="append", default=[],
        help="Dotted field path to resolve (repeatable). Omit for full dump.",
    )
    parser.add_argument(
        "--project-root",
        help="Project root whose _bmad/custom overrides apply.",
    )
    args = parser.parse_args()

    skill_dir = Path(args.skill).resolve()
    skill_name = skill_dir.name
    defaults_path = skill_dir / "customize.toml"

    defaults = load_toml(defaults_path, required=True)

    if args.project_root:
        project_root = Path(args.project_root).resolve()
    else:
        candidates = candidate_project_roots(skill_dir)
        project_root = candidates[0] if candidates else None
        if project_root is not None:
            warn_on_masked_override(project_root, candidates[1:], skill_name)

    team: dict[str, Any] = {}
    user: dict[str, Any] = {}
    if project_root:
        custom_dir = project_root / "_bmad" / "custom"
        team = load_toml(custom_dir / f"{skill_name}.toml")
        user = load_toml(custom_dir / f"{skill_name}.user.toml")

    merged = merge_layers(defaults, team, user)

    output: dict[str, Any]
    if args.key:
        output = {}
        for key in args.key:
            value = extract_key(merged, key)
            if value is not _MISSING:
                output[key] = value
    else:
        output = merged

    write_json_stdout(output)


if __name__ == "__main__":
    main()
