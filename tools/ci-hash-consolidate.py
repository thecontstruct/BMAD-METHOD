#!/usr/bin/env python3
"""ci-hash-consolidate.py — compare per-platform skill hashes and report divergence.

Arguments: --hashes-dir <path>

Exit codes:
  0 — all platforms agree on every skill hash
  1 — at least one hash diverges across platforms
  2 — configuration/file error (missing dir, bad JSON, empty dir)

Output format (PASS):
  PASS: all N skill(s) byte-identical across M platforms
  platform/arch   skill                  hash (first 12 chars)
  ...

Output format (FAIL):
  FAIL: K divergence(s) detected
  DIVERGENCE: <skill>
    Platform/Arch:   <hash12>   [✓|✗] (...)
  ...
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _platform_label(data: dict[str, Any]) -> str:
    return f"{data['runner_os']}/{data['runner_arch']}"


def _load_hashes(hashes_dir: Path) -> list[dict[str, Any]]:
    """Load all *.json files from hashes_dir. Exit 2 on any error."""
    json_files = sorted(hashes_dir.glob("*.json"))
    if not json_files:
        print(f"ERROR: no *.json files found in {hashes_dir}", file=sys.stderr)
        sys.exit(2)

    records: list[dict[str, Any]] = []
    for f in json_files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"ERROR: failed to read {f}: {exc}", file=sys.stderr)
            sys.exit(2)
        records.append(data)
    return records


def _compare(
    records: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, str]], list[str], str]:
    """Return (per_skill_platform_hashes, divergent_skills, ref_label).

    per_skill_platform_hashes: {skill_key: {platform_label: hash}}
    divergent_skills: skills where not all hashes agree
    ref_label: the platform used as the reference for divergence checks
    """
    assert records, "_compare requires at least one record (guaranteed by _load_hashes)"
    # Collect: skill → {platform_label → hash}
    skill_hashes: dict[str, dict[str, str]] = {}
    for rec in records:
        label = _platform_label(rec)
        for skill, h in rec.get("skills", {}).items():
            skill_hashes.setdefault(skill, {})[label] = h

    # Find reference: Linux platform, or first platform as fallback
    ref_label: str | None = None
    for rec in records:
        if rec.get("runner_os", "").lower() == "linux":
            ref_label = _platform_label(rec)
            break
    if ref_label is None:
        ref_label = _platform_label(records[0])

    divergent: list[str] = []
    for skill, platform_map in skill_hashes.items():
        ref_hash = platform_map.get(ref_label)
        if ref_hash is None:
            # Reference platform didn't compile this skill — still check uniformity
            hashes = set(platform_map.values())
            if len(hashes) > 1:
                divergent.append(skill)
        else:
            if any(h != ref_hash for h in platform_map.values()):
                divergent.append(skill)

    return skill_hashes, divergent, ref_label


def _print_pass(skill_hashes: dict[str, dict[str, str]], n_platforms: int) -> None:
    n_skills = len(skill_hashes)
    print(f"PASS: all {n_skills} skill(s) byte-identical across {n_platforms} platform(s)")
    # Table header
    print(f"\n{'Platform':<24}  {'Skill':<32}  Hash (first 12 chars)")
    print("-" * 74)
    for skill in sorted(skill_hashes):
        for platform, h in sorted(skill_hashes[skill].items()):
            print(f"{platform:<24}  {skill:<32}  {h[:12]}")


def _print_fail(
    skill_hashes: dict[str, dict[str, str]],
    divergent: list[str],
    ref_label: str,
) -> None:
    print(f"FAIL: {len(divergent)} divergence(s) detected")
    for skill in sorted(divergent):
        platform_map = skill_hashes[skill]
        ref_hash = platform_map.get(ref_label)
        print(f"\nDIVERGENCE: {skill}")
        for platform in sorted(platform_map):
            h = platform_map[platform]
            truncated = h[:12]
            if platform == ref_label:
                marker = "(reference)"
            elif ref_hash is not None and h == ref_hash:
                marker = f"✓ (matches {ref_label})"
            else:
                marker = f"✗ (differs from {ref_label})"
            print(f"  {platform:<24} {truncated}   {marker}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare per-platform skill hashes.")
    ap.add_argument("--hashes-dir", required=True, help="Directory containing *.json hash files.")
    args = ap.parse_args()

    hashes_dir = Path(args.hashes_dir)
    if not hashes_dir.is_dir():
        print(f"ERROR: --hashes-dir does not exist or is not a directory: {hashes_dir}", file=sys.stderr)
        sys.exit(2)

    records = _load_hashes(hashes_dir)

    skill_hashes, divergent, ref_label = _compare(records)

    if not divergent:
        _print_pass(skill_hashes, len(records))
        sys.exit(0)
    else:
        _print_fail(skill_hashes, divergent, ref_label)
        sys.exit(1)


if __name__ == "__main__":
    main()
