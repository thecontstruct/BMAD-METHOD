"""Story 5.2: `bmad upgrade` — halt-on-drift, `--yes` escape, and upgrade-proceeds.

Modes:
    --dry-run   Preview drift without writing any files (Story 5.1 behavior).
    (bare)      Halt at exit 3 if drift detected; call compile.py --install-phase
                and exit 0 if no drift.
    --yes       Force upgrade past drift; call compile.py --install-phase, exit 0.

Usage:
    python3 upgrade.py [--dry-run] [--yes] [--json] [--skill <name>] [--project-root <path>]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from bmad_compile.drift import (
    DriftReport,
    GlobChange,
    NewDefault,
    OrphanedOverride,
    ProseFragmentChange,
    TomlDefaultChange,
    VariableProvenanceShift,
    detect_drift,
)

# Lockfile path relative to project root.
# compile.py --install-phase uses --install-dir (_bmad/) as its anchor;
# upgrade.py uses --project-root (parent of _bmad/) so the constant is correct.
LOCKFILE_RELATIVE_PATH = "_bmad/_config/bmad.lock"

# Test-only override: set to a Path to redirect compile.py resolution in tests.
_COMPILE_PY_PATH: Path | None = None


def _get_compile_py() -> Path:
    return _COMPILE_PY_PATH if _COMPILE_PY_PATH is not None else Path(__file__).parent / "compile.py"


def _fmt_hash(h: str | None) -> str:
    """Truncate a hex hash to 12 chars + '...' for human readability."""
    if h is None:
        return "(none)"
    return h[:12] + "..."


def _format_human(report: DriftReport) -> str:
    """Format one skill's drift report as human-readable text."""
    lines: list[str] = []
    total = (
        len(report.prose_fragment_changes)
        + len(report.toml_default_changes)
        + len(report.orphaned_overrides)
        + len(report.new_defaults)
        + len(report.glob_changes)
        + len(report.variable_provenance_shifts)
    )
    lines.append(f"Skill: {report.skill} — {total} drift item(s)")

    for pfc in report.prose_fragment_changes:
        lines.append(f"  [prose_fragment_changes] {pfc.path}")
        lines.append(f"    old-hash: {_fmt_hash(pfc.old_hash)}")
        lines.append(f"    new-hash: {_fmt_hash(pfc.new_hash)}")
        if pfc.user_override_hash is not None:
            lines.append(f"    base-hash: {_fmt_hash(pfc.user_override_hash)}")

    for tdc in report.toml_default_changes:
        lines.append(f"  [toml_default_changes] {tdc.key}")
        lines.append(f"    old-hash: {_fmt_hash(tdc.old_hash)}")
        lines.append(f"    new-value: {tdc.new_value}")

    for oo in report.orphaned_overrides:
        lines.append(f"  [orphaned_overrides] {oo.path}")
        lines.append(f"    override-hash: {_fmt_hash(oo.override_hash)}")
        lines.append(f"    reason: {oo.reason}")

    for nd in report.new_defaults:
        lines.append(f"  [new_defaults] {nd.key}")
        lines.append(f"    new-value: {nd.new_value}")
        lines.append(f"    source: {nd.source}")

    for gc in report.glob_changes:
        lines.append(f"  [glob_changes] {gc.toml_key}")
        lines.append(f"    pattern: {gc.pattern}")
        lines.append(f"    old-hash: {_fmt_hash(gc.old_match_set_hash)}")
        lines.append(f"    new-hash: {_fmt_hash(gc.new_match_set_hash)}")
        added_str = ", ".join(gc.added_matches) if gc.added_matches else "(none)"
        removed_str = ", ".join(gc.removed_matches) if gc.removed_matches else "(none)"
        lines.append(f"    added: {added_str}")
        lines.append(f"    removed: {removed_str}")

    for vps in report.variable_provenance_shifts:
        lines.append(f"  [variable_provenance_shifts] {vps.name}")
        lines.append(f"    old-source: {vps.old_source} / {vps.old_toml_layer}")
        lines.append(f"    new-source: {vps.new_source} / {vps.new_toml_layer}")

    return "\n".join(lines)


def _print_footer(reports: list[DriftReport]) -> None:
    """Print the summary footer after all drift skills."""
    n_skills = len(reports)
    prose = sum(len(r.prose_fragment_changes) for r in reports)
    toml = sum(len(r.toml_default_changes) for r in reports)
    orphaned = sum(len(r.orphaned_overrides) for r in reports)
    new = sum(len(r.new_defaults) for r in reports)
    globs = sum(len(r.glob_changes) for r in reports)
    prov = sum(len(r.variable_provenance_shifts) for r in reports)
    print("---")
    print(
        f"Total: {n_skills} skill(s) with drift "
        f"({prose} prose, {toml} TOML, {orphaned} orphaned, "
        f"{new} new, {globs} glob, {prov} provenance)",
        flush=True,
    )


def _report_to_dict(report: DriftReport) -> dict[str, Any]:
    """Convert a DriftReport to its JSON-serializable dict form."""

    def prose_item(item: ProseFragmentChange) -> dict[str, Any]:
        return {
            "path": item.path,
            "old_hash": item.old_hash,
            "new_hash": item.new_hash,
            "user_override_hash": item.user_override_hash,
            "tier": item.tier,
        }

    def toml_item(item: TomlDefaultChange) -> dict[str, Any]:
        return {
            "key": item.key,
            "old_hash": item.old_hash,
            "new_value": item.new_value,
            "user_override_value": item.user_override_value,
        }

    def orphan_item(item: OrphanedOverride) -> dict[str, Any]:
        return {
            "path": item.path,
            "override_hash": item.override_hash,
            "reason": item.reason,
        }

    def new_item(item: NewDefault) -> dict[str, Any]:
        return {"key": item.key, "new_value": item.new_value, "source": item.source}

    def glob_item(item: GlobChange) -> dict[str, Any]:
        return {
            "toml_key": item.toml_key,
            "pattern": item.pattern,
            "old_match_set_hash": item.old_match_set_hash,
            "new_match_set_hash": item.new_match_set_hash,
            "added_matches": item.added_matches,
            "removed_matches": item.removed_matches,
        }

    def prov_item(item: VariableProvenanceShift) -> dict[str, Any]:
        return {
            "name": item.name,
            "old_source": item.old_source,
            "new_source": item.new_source,
            "old_toml_layer": item.old_toml_layer,
            "new_toml_layer": item.new_toml_layer,
        }

    return {
        "skill": report.skill,
        "prose_fragment_changes": [prose_item(i) for i in report.prose_fragment_changes],
        "toml_default_changes": [toml_item(i) for i in report.toml_default_changes],
        "orphaned_overrides": [orphan_item(i) for i in report.orphaned_overrides],
        "new_defaults": [new_item(i) for i in report.new_defaults],
        "glob_changes": [glob_item(i) for i in report.glob_changes],
        "variable_provenance_shifts": [prov_item(i) for i in report.variable_provenance_shifts],
    }


def _format_json(reports: list[DriftReport]) -> str:
    """Serialize all drift reports to a complete JSON document (buffered, emitted once).

    Precondition: all reports satisfy has_drift() == True (caller pre-filters).
    """
    drift_list = sorted(
        [_report_to_dict(r) for r in reports], key=lambda d: d["skill"]
    )
    summary: dict[str, Any] = {
        "total_skills_with_drift": len(reports),
        "prose_fragment_changes": sum(len(r.prose_fragment_changes) for r in reports),
        "toml_default_changes": sum(len(r.toml_default_changes) for r in reports),
        "orphaned_overrides": sum(len(r.orphaned_overrides) for r in reports),
        "new_defaults": sum(len(r.new_defaults) for r in reports),
        "glob_changes": sum(len(r.glob_changes) for r in reports),
        "variable_provenance_shifts": sum(len(r.variable_provenance_shifts) for r in reports),
    }
    result: dict[str, Any] = {
        "schema_version": 1,
        "drift": drift_list,
        "summary": summary,
    }
    return json.dumps(result, indent=2)


def _halt_on_drift_stderr(reports: list[DriftReport]) -> str:
    """Format the mandated AC 1 halt message with N/M/P/Q substitution."""
    n_skills = sum(1 for r in reports if r.has_drift())
    m_prose = sum(len(r.prose_fragment_changes) for r in reports)
    p_toml = sum(len(r.toml_default_changes) for r in reports)
    q_glob = sum(len(r.glob_changes) for r in reports)
    return (
        f"Drift detected in {n_skills} skills "
        f"({m_prose} prose fragments, {p_toml} TOML fields, {q_glob} glob inputs). "
        f"Invoke 'bmad-customize' skill in your IDE chat to review and resolve, "
        f"then re-run 'bmad upgrade'. "
        f"Use 'bmad upgrade --yes' to ignore drift and proceed (not recommended)."
    )


def _run_compile_install_phase(project_root: str) -> int:
    """Call compile.py --install-phase as a subprocess. Returns 0 on success, 1 on failure."""
    compile_py = _get_compile_py()
    bmad_dir = Path(project_root) / "_bmad"
    result = subprocess.run(
        [sys.executable, str(compile_py), "--install-phase", "--install-dir", str(bmad_dir)],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr, end="")
        return 1
    print("Upgrade complete.", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    # Exit code taxonomy for upgrade.py:
    #   0 — success (no drift, or upgrade completed via --yes / clean path)
    #   1 — error (missing lockfile, bad --skill arg, compile.py failure)
    #   3 — halt (drift detected without --yes; no files written)
    # Exit code 2 is reserved by POSIX convention (shell misuse).
    parser = argparse.ArgumentParser(
        description="bmad upgrade — drift detection and upgrade"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview drift without writing any files"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output JSON (requires --dry-run)"
    )
    parser.add_argument(
        "--yes", action="store_true", help="Proceed with upgrade even if drift is detected"
    )
    parser.add_argument("--skill", default=None, help="Limit analysis to one skill")
    parser.add_argument(
        "--project-root",
        default=os.getcwd(),
        help="Project root directory (default: CWD)",
    )
    args = parser.parse_args(argv)

    lock_path = Path(args.project_root) / LOCKFILE_RELATIVE_PATH
    if not lock_path.is_file():
        print(
            f"Error: no bmad.lock found at {lock_path}. Run 'bmad install' first.",
            file=sys.stderr,
        )
        return 1

    lockfile_data: dict[str, Any] = json.loads(lock_path.read_text(encoding="utf-8"))
    entries: list[dict[str, Any]] = lockfile_data.get("entries", [])

    if args.skill is not None:
        entries = [e for e in entries if e.get("skill") == args.skill]
        if not entries:
            print(
                f"Error: skill '{args.skill}' not found in lockfile.", file=sys.stderr
            )
            return 1

    if args.dry_run:
        # Story 5.1 path — unchanged.
        reports: list[DriftReport] = []
        for entry in entries:
            report = detect_drift(entry, args.project_root)
            if report.has_drift():
                if not args.json:
                    print(_format_human(report), flush=True)
                reports.append(report)

        if args.json:
            print(_format_json(reports), flush=True)
        elif not reports:
            print("No drift detected.", flush=True)
        else:
            _print_footer(reports)

        return 0

    # Non-dry-run path (Story 5.2): detect drift, halt or proceed.
    drift_reports: list[DriftReport] = []
    for entry in entries:
        report = detect_drift(entry, args.project_root)
        if report.has_drift():
            drift_reports.append(report)

    if drift_reports and not args.yes:
        print(_halt_on_drift_stderr(drift_reports), file=sys.stderr)
        return 3

    return _run_compile_install_phase(args.project_root)


if __name__ == "__main__":
    sys.exit(main())
