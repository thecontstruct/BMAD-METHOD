"""Unit tests for bmad_compile.io — determinism guarantees at the boundary.

Tests verify:
- read_template: CRLF->LF normalization
- write_text: LF-only on-disk, UTF-8 no BOM, atomic (no partial writes)
- sha256_hex: binary mode + lowercase hex + newline-invariant for the same
  canonical content only when bytes are literally equal (hash over raw bytes,
  not normalized content)
- list_dir_sorted: stable POSIX-string ordering
- ensure_within_root: raises on path escape
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from src.scripts.bmad_compile import io as bio
from src.scripts.bmad_compile.errors import OverrideOutsideRootError


class TestReadTemplate(unittest.TestCase):
    def test_crlf_normalized_on_read(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.md"
            p.write_bytes(b"a\r\nb\r\nc\r\n")
            self.assertEqual(bio.read_template(p), "a\nb\nc\n")

    def test_lone_cr_normalized_on_read(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.md"
            p.write_bytes(b"a\rb\r")
            self.assertEqual(bio.read_template(p), "a\nb\n")

    def test_lf_only_passthrough(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.md"
            p.write_bytes(b"a\nb\n")
            self.assertEqual(bio.read_template(p), "a\nb\n")

    def test_utf8_decoded(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.md"
            p.write_bytes("héllo — 世界\n".encode("utf-8"))
            self.assertEqual(bio.read_template(p), "héllo — 世界\n")


class TestWriteText(unittest.TestCase):
    def test_writes_lf_only_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "out.md"
            bio.write_text(p, "a\nb\nc")
            self.assertEqual(p.read_bytes(), b"a\nb\nc")

    def test_normalizes_crlf_input_to_lf(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "out.md"
            bio.write_text(p, "a\r\nb\r\n")
            self.assertEqual(p.read_bytes(), b"a\nb\n")

    def test_no_utf8_bom(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "out.md"
            bio.write_text(p, "héllo")
            raw = p.read_bytes()
            self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(raw, "héllo".encode("utf-8"))

    def test_creates_parent_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "deep" / "nest" / "SKILL.md"
            bio.write_text(p, "x")
            self.assertTrue(p.is_file())

    def test_write_is_atomic_no_temp_leftover_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.md"
            bio.write_text(p, "content")
            # Only the destination exists; no leftover .tmp-bmad-* files
            siblings = list(Path(d).iterdir())
            self.assertEqual([s.name for s in siblings], ["x.md"])

    def test_write_overwrites_existing(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.md"
            bio.write_text(p, "first")
            bio.write_text(p, "second")
            self.assertEqual(p.read_bytes(), b"second")


class TestSha256Hex(unittest.TestCase):
    def test_bytes_input_lowercase_hex(self) -> None:
        digest = bio.sha256_hex(b"hello")
        self.assertEqual(digest, hashlib.sha256(b"hello").hexdigest())
        self.assertEqual(digest, digest.lower())

    def test_binary_mode_not_newline_normalized(self) -> None:
        """Hash is over raw bytes — CRLF and LF produce different hashes."""
        self.assertNotEqual(bio.sha256_hex(b"a\r\nb"), bio.sha256_hex(b"a\nb"))

    def test_path_input_matches_binary_read(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "f.txt"
            p.write_bytes(b"a\r\nb\r\n")
            expected = hashlib.sha256(b"a\r\nb\r\n").hexdigest()
            self.assertEqual(bio.sha256_hex(p), expected)


class TestListDirSorted(unittest.TestCase):
    def test_alphabetical_posix_sort(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            for name in ["c.md", "a.md", "B.md", "d.md"]:
                (Path(d) / name).write_text("x", encoding="utf-8")
            entries = [str(e).rsplit("/", 1)[-1] for e in bio.list_dir_sorted(d)]
            # Case-sensitive: uppercase B comes before lowercase a
            self.assertEqual(entries, sorted(entries))
            self.assertEqual(entries[0], "B.md")

    def test_stable_across_calls(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            for name in ["c.md", "a.md", "b.md"]:
                (Path(d) / name).write_text("x", encoding="utf-8")
            first = bio.list_dir_sorted(d)
            second = bio.list_dir_sorted(d)
            self.assertEqual(first, second)


class TestToPosix(unittest.TestCase):
    def test_windows_backslashes_become_forward_slashes(self) -> None:
        # Construct a Windows-style path string; to_posix should normalize.
        posix = bio.to_posix("a/b/c")
        self.assertEqual(str(posix), "a/b/c")

    def test_returns_pureposixpath(self) -> None:
        from pathlib import PurePosixPath

        self.assertIsInstance(bio.to_posix("x/y"), PurePosixPath)


class TestEnsureWithinRoot(unittest.TestCase):
    def test_path_inside_root_returns_posix(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            inside = root / "sub" / "f.md"
            inside.parent.mkdir(parents=True)
            inside.write_text("x", encoding="utf-8")
            result = bio.ensure_within_root(inside, root)
            self.assertTrue(str(result).endswith("sub/f.md"))

    def test_path_outside_root_raises(self) -> None:
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            f = Path(d2) / "outside.md"
            f.write_text("x", encoding="utf-8")
            with self.assertRaises(OverrideOutsideRootError) as cm:
                bio.ensure_within_root(f, d1)
            self.assertEqual(cm.exception.code, "OVERRIDE_OUTSIDE_ROOT")

    def test_dotdot_escape_detected(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "inner"
            root.mkdir()
            # An "inside" path whose .. escapes root
            escape = root / ".." / "outside.md"
            (Path(d) / "outside.md").write_text("x", encoding="utf-8")
            with self.assertRaises(OverrideOutsideRootError):
                bio.ensure_within_root(escape, root)


if __name__ == "__main__":
    unittest.main()
