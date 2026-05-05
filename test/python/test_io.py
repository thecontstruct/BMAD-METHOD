"""Unit tests for bmad_compile.io — determinism guarantees at the boundary.

Tests verify:
- read_template: CRLF->LF normalization
- write_text: LF-only on-disk, UTF-8 no BOM, atomic (no partial writes)
- sha256_hex: binary mode + lowercase hex + newline-invariant for the same
  canonical content only when bytes are literally equal (hash over raw bytes,
  not normalized content)
- list_dir_sorted: stable basename ordering, case-sensitive
- ensure_within_root: raises on path escape
- TestLockPrimitives: acquire_lock / release_lock cross-platform primitives
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from src.scripts.bmad_compile import io as bio
from src.scripts.bmad_compile.errors import OverrideOutsideRootError

# Path to the src/scripts/ directory (contains the bmad_compile package).
# Used by subprocess helpers to insert into sys.path for dynamic imports.
_IO_SRC_PATH = Path(__file__).resolve().parent.parent.parent / "src" / "scripts"


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
            self.assertEqual(entries, ["B.md", "a.md", "c.md", "d.md"])

    def test_stable_across_calls(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            for name in ["c.md", "a.md", "b.md"]:
                (Path(d) / name).write_text("x", encoding="utf-8")
            first = bio.list_dir_sorted(d)
            second = bio.list_dir_sorted(d)
            self.assertEqual(first, second)


class TestListFilesSorted(unittest.TestCase):
    def test_returns_only_files_not_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.md").write_text("x", encoding="utf-8")
            (Path(d) / "b.md").write_text("x", encoding="utf-8")
            (Path(d) / "c").mkdir()
            result = bio.list_files_sorted(d)
            expected = [bio.to_posix(Path(d) / "a.md"), bio.to_posix(Path(d) / "b.md")]
            self.assertEqual(result, expected)

    def test_empty_dir_returns_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(bio.list_files_sorted(d), [])

    def test_missing_path_raises_file_not_found(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = str(Path(tmp) / "does_not_exist")
            with self.assertRaises(FileNotFoundError):
                bio.list_files_sorted(missing)

    def test_broken_symlink_is_silently_dropped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.symlink("nonexistent_target", os.path.join(tmp, "broken.md"))
            except OSError:
                self.skipTest("symlinks require elevated privileges on this platform")
            result = bio.list_files_sorted(tmp)
            self.assertEqual(result, [])


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


class TestLockPrimitives(unittest.TestCase):
    """Advisory file-lock primitives: acquire_lock / release_lock (Story 5.5a)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.lock_path = os.path.join(self._tmp.name, "test.lock")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _hold_lock_subprocess(self, lock_path_str: str) -> subprocess.Popen[bytes]:
        """Start a child process that acquires the lock and signals when ready.

        Uses subprocess so that fcntl.flock per-process semantics produce
        real contention (same-process flock re-grants on POSIX).
        """
        helper = textwrap.dedent(f"""
            import sys, time
            sys.path.insert(0, {str(_IO_SRC_PATH)!r})
            from bmad_compile import io as bmad_io
            fd = bmad_io.acquire_lock({lock_path_str!r}, 60)
            sys.stdout.write("LOCKED\\n")
            sys.stdout.flush()
            time.sleep(60)
        """)
        p = subprocess.Popen(
            [sys.executable, "-c", helper],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        line = p.stdout.readline()  # type: ignore[union-attr]
        if not line:
            p.wait()
            err = p.stderr.read().decode(errors="replace")  # type: ignore[union-attr]
            raise RuntimeError(f"Lock helper subprocess failed: {err!r}")
        assert line.strip() == b"LOCKED"
        return p

    def test_acquire_and_release(self) -> None:
        """Acquire, release, then re-acquire — proves lock is fully released."""
        fd = bio.acquire_lock(self.lock_path, timeout_seconds=5)
        self.assertIsInstance(fd, int)
        bio.release_lock(fd)
        # Should be acquirable again immediately after release.
        fd2 = bio.acquire_lock(self.lock_path, timeout_seconds=5)
        bio.release_lock(fd2)

    def test_timeout_raises_lock_timeout_error(self) -> None:
        """LockTimeoutError raised when a subprocess holds the lock."""
        p = self._hold_lock_subprocess(self.lock_path)
        try:
            with self.assertRaises(bio.LockTimeoutError):
                bio.acquire_lock(self.lock_path, timeout_seconds=0.5)
        finally:
            p.kill()
            p.wait()

    @unittest.skipIf(sys.platform == "win32", "POSIX-only: fcntl.flock")
    def test_posix_uses_fcntl(self) -> None:
        """POSIX: lock held by subprocess blocks same-file flock from test process."""
        import fcntl
        p = self._hold_lock_subprocess(self.lock_path)
        try:
            fd2 = os.open(self.lock_path, os.O_RDWR)
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(fd2, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(fd2)
        finally:
            p.kill()
            p.wait()

    @unittest.skipUnless(sys.platform == "win32", "Windows-only: msvcrt.locking")
    def test_windows_uses_msvcrt(self) -> None:
        """Windows: lock held by subprocess blocks same-file locking from test process."""
        import msvcrt
        p = self._hold_lock_subprocess(self.lock_path)
        try:
            # acquire_lock creates the file via O_CREAT; open after the helper runs.
            fd2 = os.open(self.lock_path, os.O_RDWR)
            try:
                os.lseek(fd2, 0, os.SEEK_SET)
                with self.assertRaises(PermissionError):
                    msvcrt.locking(fd2, msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
            finally:
                os.close(fd2)
        finally:
            p.kill()
            p.wait()


if __name__ == "__main__":
    unittest.main()
