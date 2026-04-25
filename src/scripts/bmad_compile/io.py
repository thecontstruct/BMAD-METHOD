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
- Directory listings are sorted alphabetically by POSIX path string.
- Writes are atomic (temp file + rename) so AC 10 — no partial writes on error —
  is enforceable.
"""

from __future__ import annotations

import hashlib  # pragma: allow-raw-io
import os  # pragma: allow-raw-io
import tempfile  # pragma: allow-raw-io
from pathlib import Path, PurePosixPath  # pragma: allow-raw-io
from typing import Union

from . import errors

# Re-export PurePosixPath so downstream layered modules (variants.py,
# resolver.py, ...) can stay inside the raw-I/O boundary with
# `from .io import PurePosixPath` — the grep that forbids `pathlib` in
# non-io modules never sees it in their source. The self-assignment is
# intentional: it documents the export and survives tools that strip
# "unused" imports.
PurePosixPath = PurePosixPath  # pragma: allow-raw-io

PathLike = Union[str, os.PathLike]


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
    """List directory entries sorted alphabetically by POSIX path string.

    Case-sensitive sort. Stable across repeated calls.
    """
    base = _fs(path)
    entries = [to_posix(e) for e in base.iterdir()]  # pragma: allow-raw-io
    entries.sort(key=str)
    return entries


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
