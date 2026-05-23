"""Cross-platform source-encoding normalizer for Epic 10 migrations.

Authored for Story 10.1 (R0 spike — `bmad-correct-course` migration). Used by
every per-skill migration story henceforth. See `docs/compile/migration-playbook.md`
for the canonical step sequencing.

CLI surface (frozen contract — Batch 1+ stories ride on this):

    migration_normalize.py --skill <skill-dir>
        Pre-flight: report BOM/CRLF/non-ASCII status; normalize in-place
        if source had BOM or CRLF; hard-fail (exit 2) on non-UTF-8.

    migration_normalize.py --golden-mode <src> <dst>
        LF-only re-write for golden capture. Hard-fail (exit 2) on
        non-UTF-8. Idempotent on already-LF source.

    migration_normalize.py --canonicalize-ascii <skill-dir>
        Opt-in ASCII canonicalization (U+2013 -> "-", U+2014 -> "--",
        U+2192 -> "->"). OFF by default.

    migration_normalize.py --validate-manifest <path> [--schema <path>]
        JSON Schema validation of the discovery manifest. Exit non-zero
        on invalidity.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path


EXIT_OK = 0
EXIT_USAGE = 1
EXIT_BAD_INPUT = 2


def _decode_utf8_or_die(path: Path, raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as e:
        sys.stderr.write(
            f"migration_normalize: {path}: not valid UTF-8 at byte offset {e.start}\n"
        )
        sys.exit(EXIT_BAD_INPUT)


def _strip_leading_bom(text: str) -> tuple[str, bool]:
    """Strip a SINGLE leading U+FEFF (byte-0 BOM). Preserve body-embedded U+FEFF."""
    if text.startswith("﻿"):
        return text[1:], True
    return text, False


def _normalize_line_endings(text: str) -> tuple[str, bool]:
    """Convert CRLF and lone CR to LF. Return (text, changed)."""
    if "\r" not in text:
        return text, False
    return text.replace("\r\n", "\n").replace("\r", "\n"), True


def _non_ascii_census(text: str) -> list[tuple[int, int, str, str]]:
    """Return list of (line, col, codepoint-hex, glyph) for each non-ASCII char."""
    out: list[tuple[int, int, str, str]] = []
    for lineno, line in enumerate(text.split("\n"), start=1):
        for col, ch in enumerate(line, start=1):
            if ord(ch) > 0x7F:
                out.append((lineno, col, f"U+{ord(ch):04X}", ch))
    return out


def _iter_text_files(skill_dir: Path):
    """Yield .md files under the skill directory."""
    for p in sorted(skill_dir.rglob("*.md")):
        if p.is_file():
            yield p


def cmd_skill(skill_dir: Path) -> int:
    if not skill_dir.is_dir():
        sys.stderr.write(f"migration_normalize: --skill: not a directory: {skill_dir}\n")
        return EXIT_USAGE

    files = list(_iter_text_files(skill_dir))
    if not files:
        sys.stderr.write(f"migration_normalize: --skill: no .md files under {skill_dir}\n")
        return EXIT_USAGE

    print(f"# migration_normalize --skill {skill_dir}")
    for path in files:
        raw = path.read_bytes()
        text = _decode_utf8_or_die(path, raw)
        text, had_bom = _strip_leading_bom(text)
        text, had_crlf = _normalize_line_endings(text)
        census = _non_ascii_census(text)
        rewrite = had_bom or had_crlf
        if rewrite:
            path.write_bytes(text.encode("utf-8"))
        print(f"## {path.relative_to(skill_dir)}")
        print(f"  BOM:    {'STRIPPED' if had_bom else 'absent'}")
        print(f"  CRLF:   {'NORMALIZED-TO-LF' if had_crlf else 'absent (LF-only)'}")
        print(f"  Non-ASCII chars: {len(census)}")
        for lineno, col, cp, glyph in census:
            print(f"    line {lineno} col {col}: {cp} ({glyph})")
        if rewrite:
            print("  Rewrite: YES (in-place)")
        else:
            print("  Rewrite: NO (already normalized)")
    return EXIT_OK


def cmd_golden_mode(src: Path, dst: Path) -> int:
    if not src.is_file():
        sys.stderr.write(f"migration_normalize: --golden-mode: source not a file: {src}\n")
        return EXIT_USAGE
    raw = src.read_bytes()
    text = _decode_utf8_or_die(src, raw)
    text, _ = _strip_leading_bom(text)
    text, _ = _normalize_line_endings(text)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(text.encode("utf-8"))
    print(f"migration_normalize: golden written: {dst} ({len(text.encode('utf-8'))} bytes LF-only)")
    return EXIT_OK


_ASCII_MAP = {
    "–": "-",   # en dash
    "—": "--",  # em dash
    "→": "->",  # rightwards arrow
}


def cmd_canonicalize_ascii(skill_dir: Path) -> int:
    if not skill_dir.is_dir():
        sys.stderr.write(f"migration_normalize: --canonicalize-ascii: not a directory: {skill_dir}\n")
        return EXIT_USAGE
    for path in _iter_text_files(skill_dir):
        raw = path.read_bytes()
        text = _decode_utf8_or_die(path, raw)
        for k, v in _ASCII_MAP.items():
            text = text.replace(k, v)
        path.write_bytes(text.encode("utf-8"))
        print(f"  canonicalized: {path}")
    return EXIT_OK


def cmd_validate_manifest(manifest_path: Path, schema_path: Path | None) -> int:
    try:
        import jsonschema  # type: ignore
        import yaml  # type: ignore
    except ImportError as e:
        sys.stderr.write(f"migration_normalize: --validate-manifest requires PyYAML and jsonschema: {e}\n")
        return EXIT_USAGE

    if not manifest_path.is_file():
        sys.stderr.write(f"migration_normalize: --validate-manifest: not a file: {manifest_path}\n")
        return EXIT_USAGE
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    if schema_path is None:
        # Default: sibling manifest.schema.json
        schema_path = manifest_path.with_name("manifest.schema.json")
    if not schema_path.is_file():
        sys.stderr.write(f"migration_normalize: --validate-manifest: schema not found: {schema_path}\n")
        return EXIT_USAGE
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    try:
        jsonschema.validate(manifest, schema)
    except jsonschema.ValidationError as e:
        sys.stderr.write(f"migration_normalize: manifest validation FAILED: {e.message}\n")
        sys.stderr.write(f"  at path: {list(e.absolute_path)}\n")
        return EXIT_BAD_INPUT
    print(f"migration_normalize: manifest validated against schema (OK): {manifest_path}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="migration_normalize",
        description="Epic 10 migration source-encoding normalizer + manifest validator.",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--skill", metavar="DIR", help="Pre-flight normalize skill dir (in-place).")
    g.add_argument("--golden-mode", nargs=2, metavar=("SRC", "DST"),
                   help="LF-only re-write for golden capture.")
    g.add_argument("--canonicalize-ascii", metavar="DIR",
                   help="Opt-in: replace en/em-dash + right arrow with ASCII equivalents.")
    g.add_argument("--validate-manifest", metavar="PATH",
                   help="Validate manifest YAML against JSON Schema.")
    p.add_argument("--schema", metavar="PATH",
                   help="Optional schema path for --validate-manifest (default: sibling manifest.schema.json).")
    args = p.parse_args(argv)

    if args.skill:
        return cmd_skill(Path(args.skill))
    if args.golden_mode:
        return cmd_golden_mode(Path(args.golden_mode[0]), Path(args.golden_mode[1]))
    if args.canonicalize_ascii:
        return cmd_canonicalize_ascii(Path(args.canonicalize_ascii))
    if args.validate_manifest:
        return cmd_validate_manifest(
            Path(args.validate_manifest),
            Path(args.schema) if args.schema else None,
        )
    return EXIT_USAGE  # unreachable due to required=True


if __name__ == "__main__":
    sys.exit(main())
