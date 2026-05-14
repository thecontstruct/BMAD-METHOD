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

import copy
import re
import tomllib
from typing import Any

from . import errors, io


def _is_valid_keyed_value(v: Any) -> bool:
    """Story 5.5b AC-10 (DN2): a TOML AoT keyed-merge value must be a hashable
    scalar string or integer. `bool` is rejected explicitly even though it's
    a subclass of int — `hash(True) == hash(1)` and `hash(False) == hash(0)`,
    which would silently merge a `code=True` row with a `code=1` row in
    `index_by_key`. See spec Dev Note 8 for full rationale.
    """
    if isinstance(v, bool):
        return False
    return isinstance(v, (str, int))


def _keyed_field(items: list[Any]) -> str | None:
    """Return 'code' or 'id' if every item in `items` is a dict sharing that
    field, otherwise None. Both base and override lists must pass this check."""
    if not items:
        return None
    for field in ("code", "id"):
        if all(isinstance(item, dict) and field in item for item in items):
            return field
    return None


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge two TOML dicts applying structural rules.

    Story 5.5b hardening (ACs 6, 7, 9, 10):
    - Override values are deep-copied when newly inserted so post-merge
      mutation of inputs cannot corrupt the merged result (AC-7 line 40).
    - AoT items are deep-copied, not shallow-copied via `dict(item)` (AC-6).
    - Non-dict items in an AoT raise `MIXED_AOT_SHAPE` (AC-6).
    - Within-layer duplicate keyed values raise `DUPLICATE_KEYED_ARRAY` (AC-6).
    - Mixed `code`/`id` key fields across layers raise `MIXED_KEY_FIELDS` (AC-9).
    - Unhashable or `bool` keyed values raise `UNHASHABLE_KEYED_VALUE` (AC-10).
    """
    result: dict[str, Any] = dict(base)
    for key, override_val in override.items():
        if key not in result:
            # AC-7: deep-copy on new-key insertion. Without this, mutating
            # the override layer dict post-merge corrupts the merged result.
            result[key] = copy.deepcopy(override_val)
            continue
        base_val = result[key]
        if isinstance(base_val, dict) and isinstance(override_val, dict):
            result[key] = _deep_merge(base_val, override_val)
        elif isinstance(base_val, list) and isinstance(override_val, list):
            # AC-9: detect mixed-key-field schema mismatch BEFORE building the
            # combined list. If both sides have a key field and they differ
            # (e.g. base uses `code`, override uses `id`), raise rather than
            # silently appending un-keyed.
            base_field = _keyed_field(base_val)
            override_field = _keyed_field(override_val)
            if (
                base_field is not None
                and override_field is not None
                and base_field != override_field
            ):
                # Subtype "MIXED_KEY_FIELDS" is encoded as a desc prefix
                # because errors.py is FROZEN per spec §7 — the
                # UnknownDirectiveError.__init__ does not accept a `code`
                # parameter; .code is a class-level constant returning
                # "UNKNOWN_DIRECTIVE". The subtype label preserves the
                # spec's intent (additive subtypes within the frozen
                # taxonomy) while tests assert via substring match on desc.
                raise errors.UnknownDirectiveError(
                    f"MIXED_KEY_FIELDS: array-of-tables uses different key "
                    f"fields across layers: base uses '{base_field}', "
                    f"override uses '{override_field}'; cannot merge",
                    file=None, line=None, col=None,
                    hint=(
                        "array-of-tables merge requires both layers to use the "
                        f"same key field; choose either '{base_field}' or "
                        f"'{override_field}' consistently across layers"
                    ),
                )

            # AC-6: mixed-shape detection — if ANY item in either layer is
            # a dict (suggesting the user intended an array-of-tables) but
            # NOT ALL items are dicts, raise MIXED_AOT_SHAPE. This catches
            # the "looks like AoT but malformed" case before falling back
            # to the plain-array append path.
            for layer_label, layer in (("base", base_val), ("override", override_val)):
                _has_dict = any(isinstance(it, dict) for it in layer)
                if _has_dict and not all(isinstance(it, dict) for it in layer):
                    _bad_idx = next(
                        i for i, it in enumerate(layer) if not isinstance(it, dict)
                    )
                    raise errors.UnknownDirectiveError(
                        f"MIXED_AOT_SHAPE: array-of-tables must contain only "
                        f"tables; got {type(layer[_bad_idx]).__name__} at "
                        f"index {_bad_idx}",
                        file=None, line=None, col=None,
                        hint=(
                            f"the {layer_label} layer's array-of-tables for "
                            "this key contains a non-table item; ensure every "
                            "item is a `[[name]]` table"
                        ),
                    )

            # Check keyed-array-of-tables condition on the combined item list.
            combined = base_val + override_val
            field = _keyed_field(combined)
            if field is not None:
                # AC-6: validate AoT shape + key-value hashability + within-layer
                # duplicate detection BEFORE building index_by_key.
                for layer_label, layer in (("base", base_val), ("override", override_val)):
                    for idx, item in enumerate(layer):
                        if not isinstance(item, dict):
                            raise errors.UnknownDirectiveError(
                                f"MIXED_AOT_SHAPE: array-of-tables must "
                                f"contain only tables; got "
                                f"{type(item).__name__} at index {idx}",
                                file=None, line=None, col=None,
                                hint=(
                                    f"the {layer_label} layer's array-of-tables "
                                    "for this key contains a non-table item; "
                                    "ensure every item is a `[[name]]` table"
                                ),
                            )
                        v = item.get(field)
                        if not _is_valid_keyed_value(v):
                            raise errors.UnknownDirectiveError(
                                f"UNHASHABLE_KEYED_VALUE: array-of-tables key "
                                f"'{field}' value must be a hashable scalar "
                                f"string or integer; got {type(v).__name__}",
                                file=None, line=None, col=None,
                                hint=(
                                    f"`{field}` must be a string or integer "
                                    "(not bool, list, dict, or null) so it can "
                                    "uniquely key the AoT merge"
                                ),
                            )

                # Full replacement by key — matches upstream _merge_by_key.
                index_by_key: dict[Any, int] = {}
                merged_list: list[Any] = []
                # AC-6: within-layer duplicate detection — `[{code="x"}, {code="x"}]`
                # in the same layer is a TOML authoring bug; raise instead of
                # silently keeping only the last entry via dict overwrite.
                _base_seen: set[Any] = set()
                for item in base_val:
                    k = item[field]
                    if k in _base_seen:
                        raise errors.UnknownDirectiveError(
                            f"DUPLICATE_KEYED_ARRAY: array-of-tables key "
                            f"{field}={k!r} appears 2+ times in same layer "
                            "(base)",
                            file=None, line=None, col=None,
                            hint=(
                                "each AoT entry must have a unique key value within "
                                "its layer; duplicates indicate a TOML authoring bug"
                            ),
                        )
                    _base_seen.add(k)
                    index_by_key[k] = len(merged_list)
                    # AC-6: deep-copy AoT items so nested dicts inside an entry
                    # are independent from the input layer dicts.
                    merged_list.append(copy.deepcopy(item))
                _override_seen: set[Any] = set()
                for item in override_val:
                    k = item[field]
                    if k in _override_seen:
                        raise errors.UnknownDirectiveError(
                            f"DUPLICATE_KEYED_ARRAY: array-of-tables key "
                            f"{field}={k!r} appears 2+ times in same layer "
                            "(override)",
                            file=None, line=None, col=None,
                            hint=(
                                "each AoT entry must have a unique key value within "
                                "its layer; duplicates indicate a TOML authoring bug"
                            ),
                        )
                    _override_seen.add(k)
                    if k in index_by_key:
                        # Full replacement: override item completely replaces
                        # base item — base fields NOT in override are dropped.
                        merged_list[index_by_key[k]] = copy.deepcopy(item)
                    else:
                        index_by_key[k] = len(merged_list)
                        merged_list.append(copy.deepcopy(item))
                result[key] = merged_list
            else:
                # Plain array: append. (Inputs are not deep-copied here because
                # the resulting list is a fresh concat; mutating an input's
                # list AFTER merge does not affect the result list. Mutating
                # an input list ITEM still leaks into the result, but TOML
                # plain-array items are scalars or independent dicts/lists per
                # the parser contract — accepted limitation; AC-6/AC-7 cover
                # the common AoT case.)
                result[key] = base_val + override_val
        else:
            # Scalar (or cross-type): override wins.
            result[key] = override_val
    return result


def merge_layers(*layers: dict[str, Any]) -> dict[str, Any]:
    """Merge zero or more TOML dicts, left=lowest priority, right=highest.

    Story 5.5b AC-7: non-dict layers raise `TypeError` rather than being
    silently dropped via the previous `if layer:` falsy check. Empty `{}`
    layers are valid and merge as no-ops; non-dicts are programmer errors
    and must surface.
    """
    result: dict[str, Any] = {}
    for idx, layer in enumerate(layers):
        if not isinstance(layer, dict):
            raise TypeError(
                f"merge_layers: layer {idx} must be a dict; "
                f"got {type(layer).__name__}"
            )
        # Empty dicts are valid layers (merge as no-op); non-empty merge
        # via _deep_merge as before.
        if layer:
            result = _deep_merge(result, layer)
    return result


def load_toml_file(path: str) -> dict[str, Any]:
    """Read and parse a TOML file. Returns {} if file does not exist.

    Raises UnknownDirectiveError (code UNKNOWN_DIRECTIVE) on TOML parse
    failure — the 7 error codes are frozen at Story 1.1; no new subclass.
    Uses io.read_bytes() to stay inside the io.py boundary.

    Story 5.5b AC-8:
    - UTF-8 BOM is silently stripped via `decode("utf-8-sig")` so files saved
      by Windows editors (Notepad, etc.) parse correctly.
    - TOCTOU: if `read_bytes` raises `FileNotFoundError` (file removed after
      `is_file` returned True), return `{}` rather than propagating — same
      result as if the file never existed. Both cases are "no layer to merge".
    """
    if not io.is_file(path):
        return {}
    try:
        content_bytes = io.read_bytes(path)
    except FileNotFoundError:
        # AC-8 TOCTOU recovery: file removed between is_file and read_bytes.
        return {}
    try:
        # AC-8: utf-8-sig strips one leading BOM. Story 7.13 AC-B: strip any
        # additional leading BOMs (some editors write multiple BOMs).
        text = content_bytes.decode("utf-8-sig")
        while text.startswith("﻿"):
            text = text[1:]
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        _msg = str(exc)
        _line_m = re.search(r'line (\d+)', _msg)
        _col_m = re.search(r'column (\d+)', _msg)
        _err_line = int(_line_m.group(1)) if _line_m else None
        _err_col = int(_col_m.group(1)) if _col_m else None
        raise errors.UnknownDirectiveError(
            f"TOML parse error in '{path}'",
            file=path,
            line=_err_line,
            col=_err_col,
            hint=f"TOML parse error in '{path}': {exc} — fix the TOML syntax and retry",
        ) from exc
