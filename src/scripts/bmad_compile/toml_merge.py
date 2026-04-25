"""Layer 4 — TOML structural merge and file loading.

Implements upstream's structural merge rules (Decision 17):
  - scalars: later (higher-priority) layer wins
  - tables (dicts): deep merge
  - arrays-of-tables where every item has `code` or `id`: merge by that key;
    items in override that match by key replace base items (full replacement,
    NOT recursive deep-merge — matches upstream _merge_by_key semantic);
    new items appended
  - all other arrays: append

Also provides `load_toml_file()` for loading a TOML file from disk via io.
"""

from __future__ import annotations

import tomllib
from typing import Any

from . import errors, io


def _keyed_field(items: list) -> str | None:
    """Return 'code' or 'id' if every item in `items` is a dict sharing that
    field, otherwise None. Both base and override lists must pass this check."""
    if not items:
        return None
    for field in ("code", "id"):
        if all(isinstance(item, dict) and field in item for item in items):
            return field
    return None


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge two TOML dicts applying structural rules."""
    result: dict = dict(base)
    for key, override_val in override.items():
        if key not in result:
            result[key] = override_val
            continue
        base_val = result[key]
        if isinstance(base_val, dict) and isinstance(override_val, dict):
            result[key] = _deep_merge(base_val, override_val)
        elif isinstance(base_val, list) and isinstance(override_val, list):
            # Check keyed-array-of-tables condition on the combined item list.
            combined = base_val + override_val
            field = _keyed_field(combined)
            if field is not None:
                # Full replacement by key — matches upstream _merge_by_key.
                index_by_key: dict[Any, int] = {}
                merged_list: list = []
                for item in base_val:
                    k = item[field]
                    index_by_key[k] = len(merged_list)
                    merged_list.append(dict(item))
                for item in override_val:
                    k = item[field]
                    if k in index_by_key:
                        # Full replacement: override item completely replaces
                        # base item — base fields NOT in override are dropped.
                        merged_list[index_by_key[k]] = dict(item)
                    else:
                        index_by_key[k] = len(merged_list)
                        merged_list.append(dict(item))
                result[key] = merged_list
            else:
                # Plain array: append.
                result[key] = base_val + override_val
        else:
            # Scalar (or cross-type): override wins.
            result[key] = override_val
    return result


def merge_layers(*layers: dict) -> dict:
    """Merge zero or more TOML dicts, left=lowest priority, right=highest."""
    result: dict = {}
    for layer in layers:
        if layer:
            result = _deep_merge(result, layer)
    return result


def load_toml_file(path: str) -> dict:
    """Read and parse a TOML file. Returns {} if file does not exist.

    Raises UnknownDirectiveError (code UNKNOWN_DIRECTIVE) on TOML parse
    failure — the 7 error codes are frozen at Story 1.1; no new subclass.
    Uses io.read_bytes() to stay inside the io.py boundary.
    """
    if not io.is_file(path):
        return {}
    content_bytes = io.read_bytes(path)
    try:
        return tomllib.loads(content_bytes.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise errors.UnknownDirectiveError(
            f"TOML parse error in '{path}'",
            file=path,
            line=None,
            col=None,
            hint=f"TOML parse error in '{path}': {exc} — fix the TOML syntax and retry",
        ) from exc
