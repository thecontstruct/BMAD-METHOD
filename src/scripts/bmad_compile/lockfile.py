"""Layer 7 — lockfile v1 writer.

Emits ``_bmad/_config/bmad.lock`` after each successful compile. The file
is JSON (not YAML) — ``json.dumps(sort_keys=True, indent=2)`` — because the
Python port is stdlib-only and ``pyyaml`` is banned. JSON is a strict subset
of YAML so downstream tools that parse YAML can read it.

Schema v1 example::

    {
      "bmad_version": "1.0.0",
      "compiled_at": "1.0.0",
      "entries": [
        {
          "compiled_hash": "<sha256>",
          "fragments": [
            {
              "hash": "<sha256>",
              "path": "fragments/header.template.md",
              "resolved_from": "base"
            }
          ],
          "glob_inputs": [],
          "skill": "my-skill",
          "source_hash": "<sha256>",
          "variant": null,
          "variables": [
            {
              "name": "user_name",
              "source": "bmad-config",
              "source_path": "_bmad/core/config.yaml",
              "value_hash": "<sha256>"
            }
          ]
        }
      ],
      "version": 1
    }

Allowed imports (layer 7): errors (1), io (2), resolver (6), stdlib json.
Must NOT import: pathlib, hashlib, time, os.listdir, os.scandir, glob, open.
All file I/O via io.is_file / io.read_template / io.write_text.
Path manipulation via PurePosixPath re-exported from io.
"""

from __future__ import annotations

import json
import sys  # pragma: allow-raw-io  (stderr write for AC-5 defensive warning)
from typing import Any

from . import errors, io, resolver
from .io import PurePosixPath

_VERSION = 1
_BMAD_VERSION = "1.0.0"  # deterministic sentinel — never wall-clock


def read_lockfile_version(path: str) -> int | None:
    """Return the ``version`` field of an existing lockfile, or ``None`` if absent.

    Returns ``0`` for malformed/unreadable content (treated as no-version,
    allowing overwrite). Any non-dict top level (list, scalar) also returns 0.

    Story 5.5b AC-3: type-strict on the `version` field. Pre-5.5b accepted
    `version: 1.9` via `int()` truncation \u2014 silent data corruption. Post-5.5b
    rejects floats, bools, strings, lists, dicts, and negative integers with
    `LockfileVersionMismatchError`. Migration: re-run `bmad install` to
    regenerate the lockfile. Missing `version` field still returns 0
    (graceful path preserved for fresh installs).
    """
    if not io.is_file(path):
        return None
    content = io.read_template(path)
    if content.startswith("\ufeff"):
        # Windows authors / editors may save bmad.lock with a UTF-8 BOM;
        # mirror _parse_flat_yaml which strips the BOM before json/yaml parse.
        content = content[1:]
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(data, dict):
        return 0
    if "version" not in data:
        return 0
    v: Any = data["version"]
    # bool is a subclass of int \u2014 check first to reject `True`/`False` as
    # non-integer (per AC-3 strictness). Same pattern as toml_merge AC-10.
    if isinstance(v, bool):
        raise errors.LockfileVersionMismatchError(
            f"version must be a non-negative integer; got bool: {v}",
            file=path,
            hint=(
                "lockfile `version` field must be a non-negative integer; "
                "bool is rejected to prevent silent True\u21921 / False\u21920 coercion. "
                "Re-run 'bmad install' to regenerate cleanly."
            ),
        )
    if not isinstance(v, int):
        raise errors.LockfileVersionMismatchError(
            f"version must be a non-negative integer; "
            f"got {type(v).__name__}: {v!r}",
            file=path,
            hint=(
                "lockfile `version` field must be a non-negative integer; "
                "non-integer numerics (e.g. 1.9), strings, lists, and dicts "
                "are rejected. Re-run 'bmad install' to regenerate cleanly."
            ),
        )
    if v < 0:
        raise errors.LockfileVersionMismatchError(
            "negative version is not valid",
            file=path,
            hint=(
                "lockfile `version` field must be a non-negative integer. "
                "Re-run 'bmad install' to regenerate cleanly."
            ),
        )
    return v


def _lockfile_lock_path(install_dir_or_lockfile_path: PurePosixPath) -> str:
    """Story 5.5b AC-2: sibling-of-lockfile path for the advisory lock.

    Accepts either an install_dir (canonical form: lock file lands at
    ``<install_dir>/_config/.bmad.lock.lock``) OR an already-resolved
    lockfile path (test-fixture form: lock file lands as a sibling at
    ``<dir>/.bmad.lock.lock``). Detection: if the path's basename is
    ``bmad.lock``, treat it as a lockfile path and use its parent as the
    sibling directory; otherwise treat the input as an install_dir.

    R1 P2 (defensive): if the path's basename is already
    ``.bmad.lock.lock`` (the lock file itself), raise ValueError —
    callers should never pass the lock file path as input. Without this
    guard, the function would treat ``<x>/.bmad.lock.lock`` as an
    install_dir and produce
    ``<x>/.bmad.lock.lock/_config/.bmad.lock.lock`` — a path that lives
    inside the lock file, recursing onto a non-existent subdirectory.
    Two processes — one passing the install_dir, the other passing the
    lock file path itself — would mutex at different paths and the
    serialization would silently fail.

    Same directory as ``bmad.lock`` so cross-filesystem ``os.replace``
    constraints don't apply. Hidden via leading dot. The ``.lock``
    suffix is the lock-on-lock convention (the file being locked is
    ``bmad.lock``).
    """
    posix = io.to_posix(install_dir_or_lockfile_path)
    if posix.name == ".bmad.lock.lock":
        # R1 P2: caller passed the lock file itself — programmer error.
        raise ValueError(
            f"_lockfile_lock_path: input is the lock file itself "
            f"({posix}); pass the install_dir or the lockfile (bmad.lock) "
            "path instead"
        )
    if posix.name == "bmad.lock":
        # Lockfile path was passed directly — sibling lock in same dir.
        return str(posix.parent / ".bmad.lock.lock")
    # Install-dir form — canonical _config/.bmad.lock.lock subpath.
    return str(posix / "_config" / ".bmad.lock.lock")


def _normalize_path(absolute_path: str, scenario_root: PurePosixPath) -> str:
    """Return scenario-root-relative POSIX string; fallback to absolute POSIX."""
    posix = io.to_posix(absolute_path)
    try:
        return str(posix.relative_to(scenario_root))
    except ValueError:
        return str(posix)


def _build_skill_entry(
    scenario_root: PurePosixPath,
    skill_basename: str,
    *,
    source_text: str,
    compiled_text: str,
    dep_tree: list[Any],
    var_scope: resolver.VariableScope,
    target_ide: str | None,
    cache: resolver.CompileCache,
) -> dict[str, Any]:
    source_hash = io.hash_text(source_text)
    compiled_hash = io.hash_text(compiled_text)

    fragments: list[dict[str, Any]] = []
    for _i, entry in enumerate(dep_tree[1:], start=1):
        if entry is None:
            continue
        # Story 5.5b AC-5: defensive guard. The resolver's contract guarantees
        # `dep_tree[i]: ResolvedFragment | None`, but a future regression
        # where a caller manually constructs a malformed dep_tree would
        # otherwise crash on the `frag.resolved_path` attribute access.
        # Skip + warn to stderr; matches the "kind:warning" defensive
        # posture used elsewhere in compile.py.
        if not isinstance(entry, resolver.ResolvedFragment):
            sys.stderr.write(  # pragma: allow-raw-io
                f"warning: non-ResolvedFragment in dep_tree at index {_i} "
                f"(got {type(entry).__name__}); skipping\n"
            )
            continue
        frag = entry
        frag_source = cache.get_source((frag.resolved_path, frag.resolved_from))
        frag_hash = io.hash_text(frag_source)
        frag_path = _normalize_path(str(frag.resolved_path), scenario_root)
        frag_entry: dict[str, Any] = {
            "hash": frag_hash,
            "path": frag_path,
            "resolved_from": frag.resolved_from,
        }
        # Story 3.1: when an override tier wins, record the override file
        # path explicitly and the base file's hash (or null when the
        # override has no upstream base — a brand-new fragment).
        if frag.resolved_from in ("user-module-fragment", "user-override"):
            frag_entry["override_path"] = frag_path
            if frag.base_path is not None:
                # read_template normalizes CRLF→LF, matching cache.get_source (also LF-normalized).
                base_text = io.read_template(str(frag.base_path))
                frag_entry["base_hash"] = io.hash_text(base_text)
            else:
                frag_entry["base_hash"] = None
            frag_entry["lineage"] = []  # Story 5.3: empty on fresh build; write_skill_entry() carries forward
        fragments.append(frag_entry)

    variables: list[dict[str, Any]] = []
    for name, rv in sorted(var_scope._table.items()):
        if rv.source == "local-scope":
            continue
        # Story 5.5b AC-5: ResolvedValue.value_hash is contractually set in
        # practice (resolver always populates it). A None value here indicates
        # a resolver bug and would otherwise serialize as `"value_hash": null`
        # in the lockfile JSON — surfacing only at downstream cache-coherence
        # check time. Fail fast with the offending variable named.
        if rv.value_hash is None:
            raise RuntimeError(
                f"internal: ResolvedValue.value_hash is None for variable "
                f"{name!r}"
            )
        var_entry: dict[str, Any] = {
            "name": name,
            "source": rv.source,
            "value_hash": rv.value_hash,
        }
        if rv.source_path is not None:
            var_entry["source_path"] = _normalize_path(rv.source_path, scenario_root)
        if rv.toml_layer is not None:
            var_entry["toml_layer"] = rv.toml_layer
        if rv.source == "toml" and rv.toml_layer == "user" and rv.base_value_hash is not None:
            # Story 5.3: record defaults-layer hash and initialize empty lineage.
            # write_skill_entry() carries forward lineage entries on subsequent compiles.
            var_entry["base_value_hash"] = rv.base_value_hash
            var_entry["lineage"] = []
        variables.append(var_entry)

    # Story 4.4: glob_inputs[] — one entry per `file:`-prefixed TOML array
    # key collected by VariableScope.build(). The `match_set_hash` is the
    # cache-coherence sentinel: it changes when a glob match-set member is
    # added, removed, or edited, so a downstream cache layer can skip an
    # input-stable recompile in O(1) without re-walking every match.
    glob_inputs: list[dict[str, Any]] = []  # pragma: allow-raw-io
    for ge in var_scope._glob_expansions:  # pragma: allow-raw-io
        glob_inputs.append({  # pragma: allow-raw-io
            "toml_key": ge.toml_key,
            "pattern": ge.pattern,
            "resolved_pattern": ge.resolved_pattern,
            "match_set_hash": ge.match_set_hash,
            "matches": [{"path": m.path, "hash": m.hash} for m in ge.matches],
        })

    return {
        "compiled_hash": compiled_hash,
        "fragments": fragments,
        "glob_inputs": glob_inputs,  # pragma: allow-raw-io
        "skill": skill_basename,
        "source_hash": source_hash,
        "variant": target_ide,
        "variables": variables,
    }


def write_skill_entry(
    lockfile_path: str,
    scenario_root: PurePosixPath,
    skill_basename: str,
    *,
    source_text: str,
    compiled_text: str,
    dep_tree: list[Any],
    var_scope: resolver.VariableScope,
    target_ide: str | None,
    cache: resolver.CompileCache,
    lock_timeout_seconds: float = 300.0,
) -> None:
    """Write (or update) the skill entry in the lockfile at ``lockfile_path``.

    Story 5.5b AC-2: serializes concurrent invocations via Story 5.5a's
    advisory lock primitives. The lock file is a sibling of
    ``lockfile_path`` (``<dir>/.bmad.lock.lock``); the RMW window
    (read → mutate ``entries[]`` → ``io.write_text``) holds the lock so
    two processes targeting the same lockfile cannot lose-write.
    ``lock_timeout_seconds`` defaults to 300s (matching
    ``lazy_compile.py``'s ``--lock-timeout-seconds`` default). On timeout,
    ``LockTimeoutError`` propagates without modifying the lockfile.
    """
    # Derive the lock-file path from the lockfile_path itself (sibling
    # in the same directory). _lockfile_lock_path detects the basename
    # form and chooses the right placement.
    _lockfile_posix = io.to_posix(lockfile_path)
    _lock_path = _lockfile_lock_path(_lockfile_posix)
    # Ensure the lockfile's parent dir exists so the lock fd can be
    # created. The lockfile itself may not exist yet (first compile),
    # but its directory must.
    _lock_dir = _lockfile_posix.parent
    if not io.is_dir(str(_lock_dir)):
        from pathlib import Path as _Path  # pragma: allow-raw-io
        _Path(str(_lock_dir)).mkdir(parents=True, exist_ok=True)  # pragma: allow-raw-io

    _lock_fd = io.acquire_lock(_lock_path, timeout_seconds=lock_timeout_seconds)
    try:
        _do_write_skill_entry(
            lockfile_path,
            scenario_root,
            skill_basename,
            source_text=source_text,
            compiled_text=compiled_text,
            dep_tree=dep_tree,
            var_scope=var_scope,
            target_ide=target_ide,
            cache=cache,
        )
    finally:
        # io.release_lock is documented no-throw (swallows OSError per
        # Story 5.5a), but defensive try/except OSError ensures an
        # exception inside the RMW body is not masked by a release-side
        # fault. AC-2: "if release_lock ever raises, wrap ... so the
        # in-flight write-window exception is not masked".
        try:
            io.release_lock(_lock_fd)
        except OSError:
            pass


def _do_write_skill_entry(
    lockfile_path: str,
    scenario_root: PurePosixPath,
    skill_basename: str,
    *,
    source_text: str,
    compiled_text: str,
    dep_tree: list[Any],
    var_scope: resolver.VariableScope,
    target_ide: str | None,
    cache: resolver.CompileCache,
) -> None:
    """Internal: the original RMW body, now called inside the AC-2 lock."""
    existing: dict[str, Any] = {}
    if io.is_file(lockfile_path):
        try:
            content = io.read_template(lockfile_path)
            if content.startswith("\ufeff"):
                content = content[1:]
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                existing = parsed
            # else: non-dict top level treated as malformed; leave existing = {}
        except (json.JSONDecodeError, ValueError, TypeError):
            existing = {}

    # Story 5.3: capture old bmad_version and build fragment/variable indices for
    # lineage carry-forward BEFORE _build_skill_entry() runs (line ~224 will
    # overwrite the top-level bmad_version with the current sentinel).
    old_bmad_version: str = existing.get("bmad_version", _BMAD_VERSION)
    old_frag_by_path: dict[str, dict[str, Any]] = {}
    old_var_by_name: dict[str, dict[str, Any]] = {}
    _ex_entries = existing.get("entries")
    for _oe in (_ex_entries if isinstance(_ex_entries, list) else []):
        if isinstance(_oe, dict) and _oe.get("skill") == skill_basename:
            _of_list = _oe.get("fragments")
            for _of in (_of_list if isinstance(_of_list, list) else []):
                if isinstance(_of, dict) and "path" in _of:
                    old_frag_by_path[_of["path"]] = _of
            _ov_list = _oe.get("variables")
            for _ov in (_ov_list if isinstance(_ov_list, list) else []):
                if isinstance(_ov, dict) and "name" in _ov:
                    old_var_by_name[_ov["name"]] = _ov
            break

    new_entry = _build_skill_entry(
        scenario_root,
        skill_basename,
        source_text=source_text,
        compiled_text=compiled_text,
        dep_tree=dep_tree,
        var_scope=var_scope,
        target_ide=target_ide,
        cache=cache,
    )

    # Story 5.3: carry forward lineage for override-tier fragments.
    for _frag in new_entry["fragments"]:
        if _frag.get("resolved_from") not in ("user-module-fragment", "user-override"):
            continue
        _old_frag = old_frag_by_path.get(_frag["path"])
        if _old_frag is None:
            continue  # first compile for this fragment — lineage: [] already set
        _raw_lin = _old_frag.get("lineage")
        _old_lin: list[dict[str, Any]] = _raw_lin if isinstance(_raw_lin, list) else []
        if _old_frag.get("base_hash") != _frag.get("base_hash"):
            # Upstream base changed — append lineage entry recording pre-upgrade state.
            _frag["lineage"] = _old_lin + [{
                "base_hash": _old_frag.get("base_hash"),
                "bmad_version": old_bmad_version,
                "override_hash": _old_frag.get("hash"),
            }]
        else:
            # No base change — carry old lineage forward unchanged.
            _frag["lineage"] = _old_lin

    # Story 5.3: carry forward lineage for user-layer TOML variables.
    for _var in new_entry["variables"]:
        if "lineage" not in _var:
            continue
        _old_var = old_var_by_name.get(_var["name"])
        if _old_var is None:
            continue  # first compile for this variable — lineage: [] already set
        _raw_var_lin = _old_var.get("lineage")
        _old_var_lin: list[dict[str, Any]] = _raw_var_lin if isinstance(_raw_var_lin, list) else []
        _old_bvh = _old_var.get("base_value_hash")
        if _old_bvh != _var.get("base_value_hash"):
            # Defaults layer changed — append lineage entry recording pre-upgrade state.
            _var["lineage"] = _old_var_lin + [{
                "base_value_hash": _old_bvh,
                "bmad_version": old_bmad_version,
                "override_value_hash": _old_var.get("value_hash"),
            }]
        else:
            # No defaults change — carry old lineage forward unchanged.
            _var["lineage"] = _old_var_lin

    raw_entries = existing.get("entries", [])
    # Defensive: a corrupted lockfile with entries=null/int/str dict-parses
    # successfully but would TypeError on list(...) (None) or silently
    # explode a string into a per-character list. Treat as fresh.
    raw_list: list[Any] = list(raw_entries) if isinstance(raw_entries, list) else []
    # Story 5.5b AC-4: silently drop non-dict items on write. The existing
    # `isinstance(entry, dict)` check below is preserved for skill matching,
    # but the post-write `entries[]` array is rebuilt from filtered entries
    # only — non-dict corruption (null, int, str, list at the entry level)
    # is opportunistically removed.
    entries: list[Any] = [e for e in raw_list if isinstance(e, dict)]
    updated = False
    for i, entry in enumerate(entries):
        if isinstance(entry, dict) and entry.get("skill") == skill_basename:
            entries[i] = new_entry
            updated = True
            break
    if not updated:
        entries.append(new_entry)

    output = dict(existing)   # copies unknown keys (forward-compat)
    output["version"] = _VERSION
    output["compiled_at"] = _BMAD_VERSION
    output["bmad_version"] = _BMAD_VERSION
    output["entries"] = entries

    serialized = json.dumps(output, sort_keys=True, indent=2) + "\n"
    io.write_text(lockfile_path, serialized)
