"""Layer 2 — determinism sandbox.

All filesystem/hash/time access in the compiler MUST flow through this module.
Every raw-I/O line is annotated with `# pragma: allow-raw-io`; the boundary
grep test in `test/python/test_io_boundary.py` excludes this file entirely
(and additionally ignores pragma-annotated lines elsewhere as a belt-and-suspenders
safety net).

Contract highlights:
- UTF-8 only, no BOM, LF line endings on write.
- Reads normalize CRLF -> LF so hash + parse are source-newline-invariant.
- SHA-256 is always computed in binary mode over raw bytes (lowercase hex).
- Directory listings are sorted alphabetically by filename (basename), case-sensitive.
- Writes are atomic (temp file + rename) so AC 10 — no partial writes on error —
  is enforceable.
- `glob_expand` (Story 4.4) is the canonical glob primitive. It (a) calls
  `ensure_within_root` on every match (containment, fold-in deferred-work:322),
  (b) re-resolves each path so the OS-canonical case wins on case-insensitive
  filesystems (fold-in :60), and (c) sorts with NFC-normalized keys so macOS
  decomposed (NFD) and Linux composed (NFC) filename encodings produce the
  same order (fold-in :47).
"""

from __future__ import annotations

import glob as _glob_module  # pragma: allow-raw-io
import hashlib  # pragma: allow-raw-io
import os  # pragma: allow-raw-io
import sys as _sys  # pragma: allow-raw-io
import tempfile  # pragma: allow-raw-io
import unicodedata as _unicodedata  # pragma: allow-raw-io
from pathlib import Path, PurePosixPath as PurePosixPath  # pragma: allow-raw-io
from typing import Union

from . import errors

# Re-export PurePosixPath so downstream layered modules (variants.py,
# resolver.py, ...) can stay inside the raw-I/O boundary with
# `from .io import PurePosixPath` — the grep that forbids `pathlib` in
# non-io modules never sees it in their source. The `from X import Y as Y`
# form (the `as PurePosixPath` alias in the import above) is the explicit-reexport
# idiom mypy recognizes under --no-implicit-reexport (enabled by --strict).

PathLike = Union[str, os.PathLike[str]]


def to_posix(path: PathLike) -> PurePosixPath:
    """Normalize an arbitrary path to a POSIX-style PurePosixPath."""
    return PurePosixPath(Path(str(path)).as_posix())  # pragma: allow-raw-io


def _fs(path: PathLike) -> Path:
    return Path(str(path))  # pragma: allow-raw-io


def read_bytes(path: PathLike) -> bytes:
    """Read raw bytes from disk."""
    with open(_fs(path), "rb") as f:  # pragma: allow-raw-io
        return f.read()


def read_template(path: PathLike) -> str:
    """Read a template source file as text.

    UTF-8 decode + CRLF->LF normalization (and lone CR->LF for legacy macs).
    """
    data = read_bytes(path)
    text = data.decode("utf-8")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def write_text(path: PathLike, content: str) -> None:
    """Atomic LF-only UTF-8 write. Creates parent directories as needed.

    Stages into a sibling temp file and os.replace()s on success. On failure,
    removes the temp file and the destination is untouched — this is how AC 10
    (no partial writes on error) is enforced at the boundary.

    Both mkdir and mkstemp are inside the try so cleanup is complete on any
    failure path; an orphaned fd is closed explicitly if fdopen never ran.
    """
    dest = _fs(path)
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    fd: int | None = None
    tmp: Path | None = None
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)  # pragma: allow-raw-io
        fd, tmp_str = tempfile.mkstemp(  # pragma: allow-raw-io
            dir=str(dest.parent), prefix=".tmp-bmad-", suffix=".write"
        )
        tmp = Path(tmp_str)  # pragma: allow-raw-io
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:  # pragma: allow-raw-io
            fd = None  # fdopen now owns the descriptor
            f.write(normalized)
        os.replace(tmp, dest)  # pragma: allow-raw-io
        tmp = None  # replace succeeded; nothing to clean up
    except BaseException:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)  # pragma: allow-raw-io
            except OSError:
                pass
        if fd is not None:
            try:
                os.close(fd)  # pragma: allow-raw-io
            except OSError:
                pass
        raise


def is_dir(path: PathLike) -> bool:
    """Return True if `path` exists and is a directory."""
    return _fs(path).is_dir()  # pragma: allow-raw-io


def is_file(path: PathLike) -> bool:
    """Return True if `path` exists and is a regular file.

    Tier-lookup probes in `resolver.py` use this (not `path_exists`) so
    an include whose authored path resolves to a directory (bare module
    name, `<<include path="fragments/subdir">>`, etc.) is rejected as a
    missing fragment rather than tripping a raw `IsADirectoryError` /
    `PermissionError` inside `read_template`.
    """
    return _fs(path).is_file()  # pragma: allow-raw-io


def path_exists(path: PathLike) -> bool:
    """Existence probe at the I/O boundary.

    Kept for callers that legitimately need "exists, file-or-dir" — e.g.
    the engine's skill-directory probe. Tier-lookup code in `resolver.py`
    uses `is_file` instead so directory targets don't slip through.
    """
    return _fs(path).exists()  # pragma: allow-raw-io


def list_dir_sorted(path: PathLike) -> list[PurePosixPath]:
    """List directory entries sorted alphabetically by filename (basename), case-sensitive.

    Stable across repeated calls.
    """
    base = _fs(path)
    entries = [to_posix(e) for e in base.iterdir()]  # pragma: allow-raw-io
    entries.sort(key=lambda e: e.name)
    return entries


def list_files_sorted(path: PathLike) -> list[PurePosixPath]:
    """Return only file entries from `list_dir_sorted(path)`, in the same order."""
    return [e for e in list_dir_sorted(path) if is_file(str(e))]


def glob_expand(pattern: str, root: PathLike) -> list[PurePosixPath]:
    """Story 4.4: expand a glob `pattern` relative to `root`; containment-check
    each match; return a deterministically sorted list of file paths.

    Semantics:
    - `pattern` is a glob string relative to `root` (e.g. ``"docs/**/*.md"``).
      Absolute patterns are intentionally not supported — the containment
      check would reject them anyway, and stripping the `file:` scheme prefix
      is the caller's responsibility.
    - Recursive `**` is enabled (mirrors the documented ``file:`` semantics).
    - Each match is re-resolved through the OS so the canonical case wins
      on case-insensitive filesystems (deferred-work fold-in :60). Without
      this, two compiles on macOS/Windows with different-case authoring of
      the same file would produce different hashes.
    - Each match is then run through `ensure_within_root` to enforce the
      Story 3.5 containment invariant (deferred-work fold-in :322). A
      symlink or `..` segment that escapes `root` raises
      `OverrideOutsideRootError`.
    - Directories matched by the pattern are silently dropped (`is_file`
      filter). The pattern `*.md` against a `dir.md/` directory returns
      no entries for that directory.
    - The final sort key is `unicodedata.normalize("NFC", str(path))`, so
      filenames authored on macOS (NFD) and Linux (NFC) sort the same way
      (deferred-work fold-in :47). Without this, twice-run determinism
      breaks across operating systems.
    """
    root_abs = _fs(root).resolve()  # pragma: allow-raw-io
    full_pattern = str(root_abs / pattern)
    raw_matches = _glob_module.glob(full_pattern, recursive=True)  # pragma: allow-raw-io
    result: list[PurePosixPath] = []
    for m in raw_matches:
        canonical = _fs(m).resolve()  # pragma: allow-raw-io
        posix = ensure_within_root(canonical, root)
        if is_file(str(posix)):
            result.append(posix)
    result.sort(key=lambda p: _unicodedata.normalize("NFC", str(p)))
    return result


def hash_text(text: str) -> str:
    """SHA-256 hex digest of a UTF-8 string. Used for value_hash in provenance."""
    return hashlib.sha256(text.encode()).hexdigest()  # pragma: allow-raw-io


def sha256_hex(data_or_path: Union[bytes, bytearray, memoryview, PathLike]) -> str:
    """SHA-256, binary mode, lowercase hex.

    Accepts raw bytes OR a path (which is read as bytes). Never normalizes
    newlines — the hash is of actual on-disk bytes so downstream cache-coherence
    guards can't be fooled by newline drift.
    """
    if isinstance(data_or_path, (bytes, bytearray, memoryview)):
        return hashlib.sha256(bytes(data_or_path)).hexdigest()  # pragma: allow-raw-io
    b = read_bytes(data_or_path)
    return hashlib.sha256(b).hexdigest()  # pragma: allow-raw-io


def ensure_within_root(path: PathLike, root: PathLike) -> PurePosixPath:
    """Resolve `path` and assert it lives under `root`.

    Raises `OverrideOutsideRootError` on escape. Returns the resolved path
    as a POSIX path. Used by override-resolution in Story 3.x; the primitive
    lives at the boundary now so there's one canonical check.
    """
    p_abs = _fs(path).resolve()  # pragma: allow-raw-io
    r_abs = _fs(root).resolve()  # pragma: allow-raw-io
    try:
        p_abs.relative_to(r_abs)
    except ValueError:
        raise errors.OverrideOutsideRootError(
            f"path '{path}' escapes root '{root}'",
            file=str(path),
            line=None,
            col=None,
            hint="override paths must resolve within the skill root",
        ) from None
    return to_posix(p_abs)


# ---------------------------------------------------------------------------
# Advisory file-lock primitives (Story 5.5a)
# ---------------------------------------------------------------------------

class LockTimeoutError(OSError):  # pragma: allow-raw-io
    """Raised by acquire_lock when the timeout elapses."""


def acquire_lock(lock_path: PathLike, timeout_seconds: float = 300.0) -> int:  # pragma: allow-raw-io
    """Acquire an exclusive advisory lock on lock_path.

    Creates the lock file if absent. Returns an OS file descriptor that must be
    passed to release_lock(). Raises LockTimeoutError if timeout_seconds elapses
    before the lock is acquired. Raises OSError on non-retriable errors (EACCES
    for a different reason, bad fd, disk error) after closing the fd.

    POSIX: fcntl.flock(LOCK_EX|LOCK_NB) with poll-loop; only BlockingIOError
      (errno EWOULDBLOCK) is retriable — all other OSErrors close fd and re-raise.
    Windows: msvcrt.locking(LK_NBLCK, 1) with poll-loop; only PermissionError
      (errno EACCES, the lock-contention errno) is retriable — all other OSErrors
      close fd and re-raise.

    Poll interval: 0.1s. File descriptor opened O_RDWR|O_CREAT mode 0o600.
    """
    import os as _os  # pragma: allow-raw-io
    import time as _time  # pragma: allow-raw-io
    path_str = str(_fs(lock_path))
    fd = _os.open(path_str, _os.O_RDWR | _os.O_CREAT, 0o600)  # pragma: allow-raw-io
    deadline = _time.monotonic() + timeout_seconds  # pragma: allow-raw-io
    try:
        if _sys.platform == "win32":  # pragma: allow-raw-io
            import msvcrt as _msvcrt  # pragma: allow-raw-io
            while True:  # pragma: allow-raw-io
                try:
                    _os.lseek(fd, 0, _os.SEEK_SET)  # pragma: allow-raw-io
                    _msvcrt.locking(fd, _msvcrt.LK_NBLCK, 1)  # pragma: allow-raw-io
                    return fd
                except PermissionError:
                    # PermissionError (errno EACCES=13) is the lock-contention error
                    if _time.monotonic() >= deadline:  # pragma: allow-raw-io
                        raise LockTimeoutError(
                            f"Lock timeout after {timeout_seconds}s on {path_str!r}"
                        )
                    _time.sleep(0.1)  # pragma: allow-raw-io
        else:
            import fcntl as _fcntl  # pragma: allow-raw-io
            while True:  # pragma: allow-raw-io
                try:
                    _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)  # type: ignore[attr-defined]  # pragma: allow-raw-io
                    return fd
                except BlockingIOError:
                    # BlockingIOError (errno EWOULDBLOCK) means lock is held elsewhere
                    if _time.monotonic() >= deadline:  # pragma: allow-raw-io
                        raise LockTimeoutError(
                            f"Lock timeout after {timeout_seconds}s on {path_str!r}"
                        )
                    _time.sleep(0.1)  # pragma: allow-raw-io
    except BaseException:
        # Close fd on any exception (timeout, non-retriable OSError, etc.)
        # so we never leak a file descriptor. Guard the close so a secondary
        # OSError does not replace the original exception being re-raised.
        try:
            _os.close(fd)  # pragma: allow-raw-io
        except OSError:
            pass
        raise


def release_lock(lock_fd: int) -> None:  # pragma: allow-raw-io
    """Release and close a lock file descriptor returned by acquire_lock.

    Swallows all OSErrors so a release failure in a finally block never masks
    the original exception from the try body.
    """
    import os as _os  # pragma: allow-raw-io
    if _sys.platform == "win32":  # pragma: allow-raw-io
        import msvcrt as _msvcrt  # pragma: allow-raw-io
        try:
            _os.lseek(lock_fd, 0, _os.SEEK_SET)  # pragma: allow-raw-io
            _msvcrt.locking(lock_fd, _msvcrt.LK_UNLCK, 1)  # pragma: allow-raw-io
        except OSError:
            pass
    else:
        import fcntl as _fcntl  # pragma: allow-raw-io
        try:
            _fcntl.flock(lock_fd, _fcntl.LOCK_UN)  # type: ignore[attr-defined]  # pragma: allow-raw-io
        except OSError:
            pass
    try:
        _os.close(lock_fd)  # pragma: allow-raw-io
    except OSError:
        pass
