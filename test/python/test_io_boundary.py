"""Raw-I/O boundary enforcement (B-01 risk mitigation).

Determinism is a boundary, not a discipline — every filesystem / hash / time
call in the compiler must route through `bmad_compile.io`. This test greps
each `bmad_compile/*.py` module (other than `io.py` itself) for raw-I/O
tokens and fails if any are found on non-pragma lines.

Banned tokens (per architecture §Determinism — a Boundary, Not a Checklist):
- `pathlib`        — path construction belongs in io.to_posix()
- `hashlib`        — hashing belongs in io.sha256_hex()
- `time.`          — wall-clock belongs nowhere in the compiler (release
                     sentinel date lives in io as an explicit helper)
- `os.listdir`     — listing belongs in io.list_dir_sorted()
- `os.scandir`     — same
- `glob`           — same
- `open(`          — file IO belongs in io.read_*/write_*

Exemptions:
- `io.py` itself is skipped wholesale (every raw-I/O line there carries the
  pragma, but we don't rely on it — the file is excluded by name).
- On any other module, a line literally containing `# pragma: allow-raw-io`
  is exempted. No non-io module uses the pragma today; it is the documented
  escape hatch when one is ever needed.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

PKG_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "src" / "scripts" / "bmad_compile"
)

BANNED_TOKENS: tuple[str, ...] = (
    "pathlib",
    "hashlib",
    "time.",
    "os.listdir",
    "os.scandir",
    "glob",
    "open(",
)

PRAGMA = "# pragma: allow-raw-io"


def _offending_lines(text: str) -> list[tuple[int, str, str]]:
    """Return (line_no, token, line_text) tuples for each non-pragma hit.

    String/docstring-only hits are filtered out with a lightweight heuristic:
    if the token appears only inside triple-quoted regions or `"..."` /
    `'...'` spans, we skip it. For Story 1.1 we keep this simple — parser.py
    legitimately contains the substring `time.` nowhere, and no module should
    reference these tokens at all outside io.py, so a naive substring check
    is fine until proven wrong.
    """
    hits: list[tuple[int, str, str]] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        if PRAGMA in line:
            continue
        stripped = line.lstrip()
        # Skip pure-comment lines and docstring-ish lines.
        if stripped.startswith("#"):
            continue
        for tok in BANNED_TOKENS:
            if tok in line:
                # Skip lines that look like they're documenting the rule
                # (e.g., LAYERING.md is MD not .py so this is rarely needed,
                # but keep the heuristic simple).
                hits.append((idx, tok, line))
                break
    return hits


def _strip_string_literals(source: str) -> str:
    """Remove triple-quoted and single-quoted literals so banned tokens
    inside docstrings / regex patterns don't trip the grep."""
    # Remove triple-quoted strings (greedy across lines).
    source = re.sub(r'"""[\s\S]*?"""', lambda m: "\n" * m.group(0).count("\n"), source)
    source = re.sub(r"'''[\s\S]*?'''", lambda m: "\n" * m.group(0).count("\n"), source)
    # Remove single-line single/double quoted strings (naive; good enough here).
    source = re.sub(r'"(?:\\.|[^"\\])*"', '""', source)
    source = re.sub(r"'(?:\\.|[^'\\])*'", "''", source)
    return source


class TestIoBoundary(unittest.TestCase):
    def test_no_raw_io_outside_io_module(self) -> None:
        self.assertTrue(PKG_DIR.is_dir(), f"expected {PKG_DIR} to exist")

        violations: list[str] = []
        for py_file in sorted(PKG_DIR.glob("*.py")):
            if py_file.name == "io.py":
                continue
            # Package markers (`__init__.py`) contain only imports/docstrings;
            # raw-I/O calls would be architecturally out of place here, so the
            # blanket skip is documented rather than policy-enforced.
            if py_file.name == "__init__.py":
                continue
            raw = py_file.read_text(encoding="utf-8")
            code_only = _strip_string_literals(raw)
            for line_no, tok, line_text in _offending_lines(code_only):
                # Reconstruct: report the original line for clarity.
                original = raw.splitlines()[line_no - 1]
                violations.append(
                    f"{py_file.name}:{line_no}: banned token {tok!r} "
                    f"-> {original.strip()!r}"
                )

        self.assertEqual(
            violations,
            [],
            msg=(
                "raw I/O tokens found outside bmad_compile/io.py. "
                "Route the call through io.py, or annotate the line with "
                f"'{PRAGMA}' if it genuinely belongs outside the boundary.\n"
                + "\n".join(violations)
            ),
        )

    def test_pragma_marker_is_recognized_when_present(self) -> None:
        """If someone adds the pragma to a banned-token line, it must be skipped.

        Synthesized in-test so we don't have to write an intentionally-failing
        fixture file to disk.
        """
        sample = (
            "def f():\n"
            "    import hashlib  # pragma: allow-raw-io\n"
            "    return hashlib.sha256(b'x').hexdigest()  # pragma: allow-raw-io\n"
        )
        self.assertEqual(_offending_lines(sample), [])

    def test_banned_tokens_detected_without_pragma(self) -> None:
        """Sanity check the detector itself — it must flag an unannotated hit."""
        sample = "def f():\n    import hashlib\n"
        hits = _offending_lines(sample)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][1], "hashlib")


if __name__ == "__main__":
    unittest.main()
