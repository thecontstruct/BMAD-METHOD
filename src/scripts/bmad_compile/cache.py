"""Compile-mode component output cache (Story 10.52 — ARC-OQ-3)."""
from __future__ import annotations

import json
import os
import sys

from bmad_compile import io as _io

CACHE_VERSION = "1"


class ComponentCache:
    """Hash-keyed disk cache for compile-mode component rendered output.

    Cache key: hash(source_hash:props_hash:ctx_hash:CACHE_VERSION)
    where each sub-hash is the sha256 hex digest of its respective input.

    Cache files live at <cache_root>/<key>.txt (UTF-8, LF-normalized).
    Any I/O failure is non-fatal: get() returns None (miss), put() logs warning.
    """

    def __init__(self, cache_root: str) -> None:
        self._root = cache_root

    def _cache_path(self, key: str) -> str:
        return os.path.join(self._root, f"{key}.txt")  # pragma: allow-raw-io

    def _make_key(self, source_text: str, props: dict, ctx_dict: dict) -> str:
        source_hash = _io.hash_text(source_text)
        props_hash = _io.hash_text(
            json.dumps(props, sort_keys=True, separators=(",", ":"))
        )
        # Include config, skill_id, skill_source_root — all non-constant ctx fields.
        # render_mode is always "compile" — excluded. ctx.git is intentionally
        # excluded: git state changes should not bust component output caches (DN-1).
        ctx_subset = {
            k: ctx_dict[k]
            for k in ("config", "skill_id", "skill_source_root")
            if k in ctx_dict
        }
        ctx_hash = _io.hash_text(
            json.dumps(ctx_subset, sort_keys=True, separators=(",", ":"))
        )
        # Story 10.57: include data files hash so changes to non-.py assets in
        # components/ invalidate the cache. Empty string when absent (standalone
        # per-skill compiles where lockfile_root=None skip cache anyway).
        data_files_hash = ctx_dict.get("_data_files_hash", "")
        combined = f"{source_hash}:{props_hash}:{ctx_hash}:{data_files_hash}:{CACHE_VERSION}"
        return _io.hash_text(combined)

    def get(self, source_text: str, props: dict, ctx_dict: dict) -> str | None:
        """Return cached output string if key matches, else None (miss).

        Any I/O or decode failure returns None without raising.
        """
        try:
            path = self._cache_path(self._make_key(source_text, props, ctx_dict))
            if _io.is_file(path):
                return _io.read_template(path)
        except Exception:
            pass
        return None

    def put(self, source_text: str, props: dict, ctx_dict: dict, output: str) -> None:
        """Write output to cache. Any failure logs a warning; never raises."""
        try:
            path = self._cache_path(self._make_key(source_text, props, ctx_dict))
            _io.write_text(path, output)
        except Exception as exc:
            sys.stderr.write(  # pragma: allow-raw-io
                f"warning: component cache write failed: {exc}\n"
            )
