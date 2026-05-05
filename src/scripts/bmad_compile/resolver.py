"""Layer 6 — fragment-resolution engine.

Story 1.3 additions:
- `ResolvedValue` dataclass: provenance record for a resolved variable value.
- `VariableScope`: pre-materialized variable lookup table built once per
  `compile_skill()` call. Two parallel cascades:
    non-self.*: local_scope props > bmad-config YAML (_bmad/core/config.yaml)
    self.*:     toml/user > toml/team > toml/defaults (per-skill customize.toml)
- `_parse_flat_yaml()`: custom flat key-value YAML parser (no pyyaml).
- `ResolveContext.var_scope` field (optional; None is valid for legacy tests).
- `_walk_nodes()` now resolves `VarCompile` nodes inline (respecting
  per-fragment local_scope) and passes `VarRuntime` nodes through unchanged.

Expands `<<include path="...">>` directives in an AST into an inline node
stream via DFS, enforcing:

- **5-tier precedence cascade** (Story 1.2 AC 3): tier-1 (`user-full-skill`)
  is observed only for the root template via `ResolveContext.root_resolved_from`;
  tiers 2–5 (`user-module-fragment`, `user-override`, `variant`, `base`) are
  probed for each nested include in order.
- **Cycle rejection with full chain** (AC 2): a DFS visited-stack of
  `(resolved_path, authored_src)` detects cycles. On a repeat, the `chain`
  attribute on `CyclicIncludeError` lists the authored paths in order, with
  the closing repeat appended so the cycle reads left-to-right.
- **Alphabetical tiebreak within a tier** (AC 4): inherited from
  `io.list_dir_sorted`, which sorts entries by filename (basename),
  case-sensitively.
- **Include-directive attributes become local props** (AC 5): authored
  attributes other than `path` propagate down the tree via
  `ResolveContext.local_scope`. Child props shadow parent props on key
  collision. Sibling includes do not see each other's props.
- **Per-compile fragment cache** (AC 10): the engine allocates a fresh
  `CompileCache` per `compile_skill()` call; siblings that include the same
  fragment share one read+parse. No cross-compile caching.
- **Module-boundary path semantics** (AC 7): `core/<...>` and
  `<moduleId>/<...>` route via `context.module_roots`; bare paths
  (`fragments/...`, `./...`) route to `context.skill_dir`.

Chain strings in `CyclicIncludeError.chain` are the **authored** include
paths — skill-root-relative by construction when authors follow the
`fragments/...` convention. This matches the architecture example's
`[chain: fragments/a.template.md -> fragments/b.template.md -> fragments/a.template.md]`
shape and lets an author map each edge back to a specific `<<include>>`
line they can edit.

Pathlib boundary: imports `PurePosixPath` via the `io.py` re-export.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Any, Union

from . import errors, io, parser, toml_merge, variants
from .io import PurePosixPath

# Story 4.4 R1 P2: a "runtime variable reference" inside a `file:` glob
# pattern is a `{name}` placeholder — a paired pair of braces with content
# between them. Plain `{` or `}` characters in a filename (legal on Linux)
# must NOT cause the glob to be deferred, so we require BOTH delimiters
# with non-empty content between them. Regex matches `{`, then one-or-more
# non-`}` chars, then `}`.
_RUNTIME_VAR_RE = re.compile(r"\{[^}]+\}")

# Tier names — frozen for v1.
_TIER_USER_FULL_SKILL = "user-full-skill"
_TIER_USER_MODULE_FRAGMENT = "user-module-fragment"
_TIER_USER_OVERRIDE = "user-override"
_TIER_VARIANT = "variant"
_TIER_BASE = "base"

# Tiers probed for nested includes, in cascade order. Tier 1
# (`user-full-skill`) is never in this list — it only fires for the root
# template, and the engine communicates that via `root_resolved_from`.
_NESTED_TIERS: tuple[str, ...] = (
    _TIER_USER_MODULE_FRAGMENT,
    _TIER_USER_OVERRIDE,
    _TIER_VARIANT,
    _TIER_BASE,
)

# Single source of truth lives in `variants.py`; aliased here for readability
# at the call sites that still reference `_TEMPLATE_SUFFIX` locally.
_TEMPLATE_SUFFIX = variants.TEMPLATE_SUFFIX


@dataclass(frozen=True)
class ResolvedValue:
    """Provenance record for a resolved variable value."""
    value: str
    source: str          # "bmad-config" | "toml" | "local-scope" | etc.
    source_path: str | None = None        # absolute filesystem path (TOML: winning-layer file; YAML: config file path; lockfile.py normalizes to relative on write)
    toml_layer: str | None = None         # "defaults" | "team" | "user"
    contributing_paths: list[str] | None = None
    value_hash: str | None = None         # SHA-256 hex of value.encode()


@dataclass(frozen=True)
class GlobMatch:
    """Story 4.4: one file matched by a `file:`-prefixed TOML array glob.  # pragma: allow-raw-io

    `path` is scenario-root-relative POSIX (matches the lockfile fragment-path
    convention). `hash` is the SHA-256 hex of the file's RAW bytes — no
    CRLF→LF normalization, so that the lockfile's `match_set_hash` actually
    detects byte-level edits to glob inputs (cache coherence is the whole  # pragma: allow-raw-io
    reason this entry exists).
    """
    path: str
    hash: str


@dataclass(frozen=True)
class GlobExpansion:
    """Story 4.4: provenance record for one `file:`-prefixed TOML array key.

    Stored on `VariableScope._glob_expansions` after `build()` runs. Read by  # pragma: allow-raw-io
    `engine._render_explain` (markdown), `engine._render_explain_json`
    (additive `glob_expansions[]` field), and `lockfile._build_skill_entry`  # pragma: allow-raw-io
    (lockfile `glob_inputs[]` array — cache-coherence sentinel).  # pragma: allow-raw-io

    `pattern` stores the raw authored value(s) as a single string. For
    multi-pattern keys (same key contributed by >1 TOML layer after
    `merge_layers` concatenation) it is a `", "`-joined list — chosen so the
    JSON schema can keep `pattern` as `{"type": "string"}`.

    `resolved_pattern` is the absolute POSIX glob path of `pattern[0]`  # pragma: allow-raw-io
    (the first contributed pattern) anchored under `scenario_root`. It is
    `None` when ANY pattern in the merged list contains a runtime variable
    reference (`{...}`) — the v1 simplification: such keys are entirely
    deferred to runtime. `match_set_hash` is `None` in that case AND when
    the glob expanded to zero files; consumers should treat both as  # pragma: allow-raw-io
    "no compile-time content to track".
    """
    toml_key: str
    pattern: str
    resolved_pattern: str | None
    matches: tuple[GlobMatch, ...]
    match_set_hash: str | None
    toml_layer: str  # "defaults" | "team" | "user" | "merged"
    contributing_source_paths: tuple[str, ...]


def _normalize_rel(path: str, root: str) -> str:
    """Story 4.4: scenario-root-relative POSIX string; absolute fallback.

    Resolver-local copy of the same convention used by `lockfile._normalize_path`.
    Resolver cannot import from `lockfile` (lockfile imports resolver), so the
    helper is duplicated here.

    R1 P3: textual `relative_to` is case- and symlink-sensitive. On a
    case-insensitive filesystem (macOS, Windows) or when the caller passes
    an unresolved root (with case- or symlink-different segments) against
    a resolved match, the relative_to walk fails and we fall through to
    the absolute POSIX path — which then leaks an environment-specific
    string into the lockfile / explain output and breaks twice-run
    determinism across machines. Resolve both sides through the
    filesystem first so canonicalization (case, symlinks) matches.
    """
    posix = io.to_posix(path)
    root_posix = io.to_posix(root)
    try:
        return str(posix.relative_to(root_posix))
    except ValueError:
        # Fall back to OS-resolved comparison on a textual mismatch — handles
        # case-insensitive filesystems and symlink-prefix divergences.
        try:
            from pathlib import Path as _P  # local import: io.py wraps Path  # pragma: allow-raw-io
            r_resolved = _P(path).resolve()  # pragma: allow-raw-io
            root_resolved = _P(root).resolve()  # pragma: allow-raw-io
            return str(io.to_posix(r_resolved).relative_to(io.to_posix(root_resolved)))
        except (ValueError, OSError):
            return str(posix)


def _parse_flat_yaml(content: str) -> dict[str, str]:
    """Parse a flat YAML config file (key: value pairs only).

    Rules:
      - Lines starting with `#` after stripping → skip (comments).
      - Lines with no `:` → skip.
      - Lines with leading whitespace → skip (nested YAML not supported).
      - Key: everything before the first `:`, stripped.
      - Value: everything after the first `:`, stripped.
      - Surrounding single or double quotes on the entire value are stripped.
      - Empty value after stripping → key set to empty string (not omitted).
      - Empty key after stripping → skip.

    Story 1.3 reads the full file. Module-config tier parsing (the
    `# Core Configuration Values` marker) is deferred to Story 2.x.

    A leading UTF-8 BOM (`\\ufeff`) is stripped before parsing — common when
    YAML is authored on Windows. Without this, the first key would be stored
    as `\\ufeffkey` and silently fail every `{{key}}` lookup.
    """
    if content.startswith("\ufeff"):
        content = content[1:]
    result: dict[str, str] = {}
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line[0:1] == " " or line[0:1] == "\t":
            continue  # indented → nested YAML, skip
        if ":" not in line:
            continue
        key, _, raw_value = line.partition(":")
        key = key.strip()
        if not key:
            continue
        val = raw_value.strip()
        # Strip surrounding matching quotes — only when len >= 2 to avoid
        # treating a lone quote character as its own delimiter.
        if len(val) >= 2 and (
            (val.startswith('"') and val.endswith('"')) or
            (val.startswith("'") and val.endswith("'"))
        ):
            val = val[1:-1]
        result[key] = val
    return result


def _parse_flat_yaml_with_marker(content: str) -> tuple[dict[str, str], dict[str, str]]:
    """Parse a flat YAML config file, splitting on the core-marker comment.

    Splits on the first line whose `.strip()` equals `# Core Configuration Values`.
    Lines before the marker → `above_marker`; lines after → `below_marker`.
    Both halves are parsed with the same rules as `_parse_flat_yaml`.

    Marker absent → all keys go into `above_marker`; `below_marker` is `{}`.
    """
    if content.startswith("\ufeff"):
        content = content[1:]
    above_lines: list[str] = []
    below_lines: list[str] = []
    seen_marker = False
    for line in content.splitlines():
        if not seen_marker and line.strip() == "# Core Configuration Values":
            seen_marker = True
            continue
        (below_lines if seen_marker else above_lines).append(line)

    def _parse(lines: list[str]) -> dict[str, str]:
        result: dict[str, str] = {}
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if line[0:1] == " " or line[0:1] == "\t":
                continue
            if ":" not in line:
                continue
            key, _, raw_value = line.partition(":")
            key = key.strip()
            if not key:
                continue
            val = raw_value.strip()
            if len(val) >= 2 and (
                (val.startswith('"') and val.endswith('"')) or
                (val.startswith("'") and val.endswith("'"))
            ):
                val = val[1:-1]
            result[key] = val
        return result

    return _parse(above_lines), _parse(below_lines)


def _flatten_toml(
    d: dict[str, Any],
    prefix: str,
    layer_name: str,
    priority_map: dict[str, str],
    result: dict[str, ResolvedValue],
    layer_paths: dict[str, str] | None = None,  # layer_name → absolute_path
    list_priority_map: dict[str, str] | None = None,  # Story 4.2: array-error file attribution
    glob_sink: list[tuple[str, list[Any], str, str | None]] | None = None,  # Story 4.4  # pragma: allow-raw-io
) -> None:
    """Recursively flatten a merged TOML dict into `self.<dotted.path>` entries.

    Story 4.4: `glob_sink` is the opt-in escape hatch for ``file:``-prefixed  # pragma: allow-raw-io
    array values (`persistent_facts = ["file:docs/*.md"]`). When supplied
    and the list is non-empty AND every item is a `file:`-prefixed string,
    append `(full_key, list(v), winning_layer, layer_path)` to `glob_sink`  # pragma: allow-raw-io
    and continue. When `glob_sink` is `None` OR the list is empty OR any  # pragma: allow-raw-io
    item lacks the `file:` prefix, the historical
    `UnknownDirectiveError("...resolves to a TOML array...")` raise still
    fires — preserving AC 8 (mixed lists, empty lists, non-`file:` lists
    all still raise).
    """
    _paths = layer_paths or {}
    _list_priority = list_priority_map or {}
    for k, v in d.items():
        dotted = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            # Story 4.4: forward `glob_sink` so `file:` arrays nested under
            # TOML table sections (e.g. `[workflow] persistent_facts = [...]`)
            # are intercepted too. Without this forward, the latent-bug fix
            # for skills like `bmad-create-story` (which puts persistent_facts
            # under `[workflow]`) silently fails.
            _flatten_toml(
                v, dotted, layer_name, priority_map, result, _paths,
                list_priority_map, glob_sink=glob_sink,  # pragma: allow-raw-io
            )
        elif isinstance(v, list):
            full_key = f"self.{dotted}"
            # Story 4.2 fold-in 2: list-valued keys are intentionally absent
            # from `priority_map` (which records scalar provenance only), so
            # consult `list_priority_map` first to preserve array-error file
            # attribution.
            winning_layer = (
                _list_priority.get(full_key)
                or priority_map.get(full_key, layer_name)
            )
            # Story 4.4: `file:`-prefixed array → glob expansion route.
            # The `v and` guard intentionally short-circuits on empty lists
            # (AC 8: `persistent_facts = []` MUST raise — `file:` semantics
            # require at least one item). Do not drop this guard.
            if (
                glob_sink is not None  # pragma: allow-raw-io
                and v
                and all(isinstance(item, str) and item.startswith("file:") for item in v)
            ):
                glob_sink.append(  # pragma: allow-raw-io
                    (full_key, list(v), winning_layer, _paths.get(winning_layer))
                )
                continue
            # tomllib does not expose per-value source positions; line=1,col=1 is a
            # deterministic locator pointing at the file head — the dotted path in
            # the message names the offending key.
            raise errors.UnknownDirectiveError(
                f"self.* variable '{dotted}' resolves to a TOML array, not a scalar",
                file=_paths.get(winning_layer) or None,
                line=1,
                col=1,
                hint=(
                    f"self.* variable path '{dotted}' resolves to a TOML array, "
                    "not a scalar — use a more specific dotted path"
                ),
            )
        else:
            full_key = f"self.{dotted}"
            # Booleans must serialize as lowercase "true"/"false" to match
            # TOML/JSON/YAML conventions; Python's str(False) gives "False".
            str_val = str(v).lower() if isinstance(v, bool) else str(v)
            winning_layer = priority_map.get(full_key, layer_name)
            result[full_key] = ResolvedValue(
                value=str_val,
                source="toml",
                source_path=_paths.get(winning_layer) or None,
                toml_layer=winning_layer,
                value_hash=io.hash_text(str_val),
            )


def _build_priority_map(
    toml_layers: list[tuple[str, dict[str, Any]]],
) -> tuple[dict[str, str], dict[str, str]]:
    """Scan layers from highest to lowest priority to record which layer wins each path.

    Story 4.2 fold-in 2: returns `(scalar_priority_map, list_priority_map)`.
    Scalar paths and list paths are tracked separately so a list-valued entry
    in a higher-priority tier cannot misattribute a scalar value that wins from
    a lower tier (the cross-shape misattribution bug). The list map preserves
    array-error file attribution that callers depend on.
    """
    priority_map: dict[str, str] = {}
    list_priority_map: dict[str, str] = {}

    def _scan(d: dict[str, Any], prefix: str, layer_name: str) -> None:
        for k, v in d.items():
            dotted = f"{prefix}.{k}" if prefix else k
            full_key = f"self.{dotted}"
            if isinstance(v, dict):
                _scan(v, dotted, layer_name)
            elif isinstance(v, list):
                if full_key not in list_priority_map:
                    list_priority_map[full_key] = layer_name
            else:
                if full_key not in priority_map:
                    priority_map[full_key] = layer_name

    # Scan from highest priority (last in list) to lowest.
    for layer_name, layer_dict in reversed(toml_layers):
        _scan(layer_dict, "", layer_name)
    return priority_map, list_priority_map


class VariableScope:
    """Pre-materialized variable lookup table for one compile_skill() call.

    Build once at engine init via VariableScope.build(); pass the frozen
    instance into ResolveContext. Never reads the filesystem during resolve().
    Decision 3 — two parallel cascades (YAML non-self.* and TOML self.*).

    Story 1.3 supports:
      Non-self.*: bmad-config (core/config.yaml simple YAML)
      self.*:     toml/defaults, toml/team, toml/user (per-skill TOML stack)

    Note: hyphenated include prop names (e.g. heading-level) are NOT accessible
    as {{heading_level}} compile-time variables — verbatim match only.
    """

    def __init__(
        self,
        table: dict[str, ResolvedValue],
        glob_expansions: list[GlobExpansion] | None = None,  # pragma: allow-raw-io
    ) -> None:
        self._table = table
        # Story 4.4: defensive `list(...)` so the caller can't mutate the
        # internal list after the scope is built. Empty list (no glob
        # inputs) is the common case and fully valid.
        self._glob_expansions: list[GlobExpansion] = list(glob_expansions or [])  # pragma: allow-raw-io

    @classmethod
    def build(
        cls,
        *,
        yaml_config_path: str | None = None,
        module_yaml_paths: list[str] | None = None,
        user_yaml_path: str | None = None,
        install_flags: dict[str, str] | None = None,
        toml_layers: list[tuple[str, dict[str, Any]]] | None = None,
        toml_layer_paths: list[str] | None = None,
        scenario_root: str | None = None,
    ) -> "VariableScope":
        """Build a VariableScope from config sources.

        yaml_config_path: path to a flat YAML config file (bmad-config tier).
                          None = no YAML config.
        module_yaml_paths: ordered list of module-config paths (above-marker keys
                          win over bmad-config). None = no module-config.
        user_yaml_path: path to user-config (_bmad/custom/config.yaml). Wins over
                          module-config. None = no user-config.
        install_flags: CLI --set KEY=VALUE overrides. Wins over all YAML tiers.
                          None = no install flags.
        toml_layers: ordered list of (layer_name, parsed_dict) from lowest to
                    highest priority: [("defaults", ...), ("team", ...), ("user", ...)].
                    None = no TOML config.
        toml_layer_paths: parallel list of file paths for toml_layers (same order).
                          None = no path attribution on TOML errors.
        """
        table: dict[str, ResolvedValue] = {}
        # Story 4.4: collected once the TOML cascade has flattened the
        # `file:`-prefixed arrays it intercepted. Stays empty for skills
        # without any glob inputs (the common case) — `cls(table, glob_
        # expansions=[])` is the equivalent of the pre-Story-4.4 return.
        glob_expansions: list[GlobExpansion] = []  # pragma: allow-raw-io

        # Non-self.* cascade: 4-tier last-write-wins
        # bmad-config < module-config < user-config < install-flag
        if yaml_config_path is not None:
            content = io.read_template(yaml_config_path)
            parsed = _parse_flat_yaml(content)
            for name, val in parsed.items():
                table[name] = ResolvedValue(
                    value=val,
                    source="bmad-config",
                    source_path=yaml_config_path,
                    value_hash=io.hash_text(val),
                )

        if module_yaml_paths:
            for path in module_yaml_paths:
                content = io.read_template(path)
                above_marker, _below = _parse_flat_yaml_with_marker(content)
                for name, val in above_marker.items():
                    table[name] = ResolvedValue(
                        value=val,
                        source="module-config",
                        source_path=path,
                        value_hash=io.hash_text(val),
                    )

        if user_yaml_path is not None:
            content = io.read_template(user_yaml_path)
            parsed = _parse_flat_yaml(content)
            for name, val in parsed.items():
                table[name] = ResolvedValue(
                    value=val,
                    source="user-config",
                    source_path=user_yaml_path,
                    value_hash=io.hash_text(val),
                )

        if install_flags:
            for name, val in install_flags.items():
                table[name] = ResolvedValue(
                    value=val,
                    source="install-flag",
                    source_path=None,
                    value_hash=io.hash_text(val),
                )

        # self.* cascade: TOML layers merged, then flattened.
        if toml_layers:
            # Story 4.2 fold-in 4: parallel-list contract.
            # engine.py constructs matched-length toml_layers/toml_layer_paths;
            # mismatch indicates a buggy caller, so fail fast rather than let
            # zip() silently truncate (closes deferred-work.md line 138).
            if toml_layer_paths is not None and len(toml_layers) != len(toml_layer_paths):
                raise ValueError(
                    f"toml_layers and toml_layer_paths must have equal length; "
                    f"got {len(toml_layers)} layers and {len(toml_layer_paths)} paths"
                )
            priority_map, list_priority_map = _build_priority_map(toml_layers)
            merged = toml_merge.merge_layers(*[d for _, d in toml_layers])
            _layer_paths: dict[str, str] = {}
            if toml_layer_paths:
                for (ln, _), lp in zip(toml_layers, toml_layer_paths):
                    _layer_paths[ln] = lp
            # Story 4.4: collect `file:`-prefixed arrays into a sink instead
            # of raising on them. Non-`file:` arrays still raise (AC 8).
            _glob_sink: list[tuple[str, list[Any], str, str | None]] = []  # pragma: allow-raw-io
            _flatten_toml(
                merged, "", "", priority_map, table, _layer_paths or None,
                list_priority_map=list_priority_map or None,
                glob_sink=_glob_sink,  # pragma: allow-raw-io
            )

            # Story 4.2 fold-in 1: populate contributing_paths for any
            # self.* scalar key that appears in MORE THAN ONE TOML layer.
            # Single-source keys keep contributing_paths=None (no schema
            # change). Closes deferred-work.md line 85.
            if toml_layer_paths:
                _key_to_paths: dict[str, list[str]] = {}

                def _collect(
                    d: dict[str, Any], prefix: str, path: str
                ) -> None:
                    for k, v in d.items():
                        dotted = f"{prefix}.{k}" if prefix else k
                        if isinstance(v, dict):
                            _collect(v, dotted, path)
                        elif isinstance(v, list):
                            # mirrors _flatten_toml + _build_priority_map list-skip
                            continue
                        else:
                            full_key = f"self.{dotted}"
                            _key_to_paths.setdefault(full_key, []).append(path)

                for (_ln, layer_dict), layer_path in zip(toml_layers, toml_layer_paths):
                    _collect(layer_dict, "", layer_path)

                for full_key, paths in _key_to_paths.items():
                    if full_key in table and len(paths) > 1:
                        rv = table[full_key]
                        table[full_key] = replace(rv, contributing_paths=sorted(paths))

            # Story 4.4: process the `file:` arrays collected by `_flatten_toml`
            # into `GlobExpansion` records on the returned `VariableScope`.
            #
            # Per-key layer provenance: walk every layer dict looking for the
            # same `file:`-prefix arrays and record (layer_name, layer_path)
            # for each contribution. This mirrors the Story 4.2 contributing
            # _paths post-pass pattern but tracks the lists `_flatten_toml`
            # skipped instead of the scalars it kept.
            #
            # If `scenario_root` is None (resolver-level test caller without
            # an engine), glob expansion is skipped entirely — the
            # `GlobExpansion` records still get created, but with
            # `matches=()` and `match_set_hash=None`. This keeps build()
            # callable from unit tests that don't have a filesystem.
            if _glob_sink:  # pragma: allow-raw-io
                _glob_layer_paths: dict[str, list[str]] = {}  # pragma: allow-raw-io
                _glob_layer_names: dict[str, list[str]] = {}  # pragma: allow-raw-io
                if toml_layer_paths is not None:

                    def _scan_lists(
                        d: dict[str, Any], prefix: str, lp: str, ln: str,
                    ) -> None:
                        for k, v in d.items():
                            dotted = f"{prefix}.{k}" if prefix else k
                            full_key = f"self.{dotted}"
                            if isinstance(v, dict):
                                _scan_lists(v, dotted, lp, ln)
                            elif (
                                isinstance(v, list)
                                and v
                                and all(
                                    isinstance(item, str) and item.startswith("file:")
                                    for item in v
                                )
                            ):
                                _glob_layer_paths.setdefault(full_key, []).append(lp)  # pragma: allow-raw-io
                                _glob_layer_names.setdefault(full_key, []).append(ln)  # pragma: allow-raw-io

                    for (_ln, _layer_dict), _lp in zip(toml_layers, toml_layer_paths):
                        _scan_lists(_layer_dict, "", _lp, _ln)

                for full_key, pattern_list, winning_layer, _winning_path in _glob_sink:  # pragma: allow-raw-io
                    contributing_paths_list = _glob_layer_paths.get(full_key, [])  # pragma: allow-raw-io
                    contributing_names = _glob_layer_names.get(full_key, [])  # pragma: allow-raw-io
                    toml_layer = (
                        "merged" if len(contributing_names) > 1
                        else (contributing_names[0] if contributing_names else winning_layer)
                    )
                    pattern_field = (
                        ", ".join(pattern_list) if len(pattern_list) > 1
                        else pattern_list[0]
                    )
                    contributing_sorted = tuple(sorted(contributing_paths_list))

                    # v1 simplification: if ANY pattern in the merged list
                    # contains `{...}`, the entire key is treated as
                    # runtime-deferred. Prevents partial expansions where
                    # some patterns resolve and others don't.
                    # R1 P2: regex match of `\{[^}]+\}` (paired braces with
                    # content), not bare `{` substring — a literal brace in
                    # a filename (legal on Linux) was being misclassified as
                    # a runtime-var reference and the entire glob deferred.
                    has_runtime_var = any(_RUNTIME_VAR_RE.search(p[5:]) for p in pattern_list)
                    if has_runtime_var or scenario_root is None:
                        glob_expansions.append(GlobExpansion(  # pragma: allow-raw-io
                            toml_key=full_key,
                            pattern=pattern_field,
                            resolved_pattern=None,
                            matches=(),
                            match_set_hash=None,
                            toml_layer=toml_layer,
                            contributing_source_paths=contributing_sorted,
                        ))
                        continue

                    all_matches: list[GlobMatch] = []
                    for raw_pattern in pattern_list:
                        stripped = raw_pattern[5:]  # strip "file:" prefix
                        # AC 6: containment is enforced inside io.glob_expand;
                        # OverrideOutsideRootError MUST propagate to the
                        # caller — do NOT wrap in try/except here.
                        match_paths = io.glob_expand(stripped, scenario_root)  # pragma: allow-raw-io
                        for mp in match_paths:
                            content_bytes = io.read_bytes(str(mp))
                            content_hash = io.sha256_hex(content_bytes)
                            rel = _normalize_rel(str(mp), scenario_root)
                            all_matches.append(GlobMatch(path=rel, hash=content_hash))

                    # R1 P4: dedupe by path before sorting + hashing. Without
                    # this, a merged pattern list like
                    # `["file:a.md", "file:a.md"]` (or two patterns whose
                    # globs both match `a.md`) would emit two GlobMatch
                    # entries for the same path, double-counting in
                    # `match_set_hash` and breaking the cache-coherence
                    # contract: the same effective match set must produce
                    # the same hash regardless of pattern duplication.
                    _seen_paths: set[str] = set()
                    deduped: list[GlobMatch] = []
                    for _gm in all_matches:
                        if _gm.path not in _seen_paths:
                            _seen_paths.add(_gm.path)
                            deduped.append(_gm)
                    all_matches = deduped
                    all_matches.sort(key=lambda m: m.path)

                    msh: str | None
                    if all_matches:
                        hash_parts = [f"{m.path}:{m.hash}" for m in all_matches]
                        msh = io.sha256_hex("\n".join(hash_parts).encode("utf-8"))
                    else:
                        msh = None

                    stripped0 = pattern_list[0][5:]
                    resolved_pattern = str(io.to_posix(scenario_root) / stripped0)

                    glob_expansions.append(GlobExpansion(  # pragma: allow-raw-io
                        toml_key=full_key,
                        pattern=pattern_field,
                        resolved_pattern=resolved_pattern,
                        matches=tuple(all_matches),
                        match_set_hash=msh,
                        toml_layer=toml_layer,
                        contributing_source_paths=contributing_sorted,
                    ))

        return cls(table, glob_expansions=glob_expansions)  # pragma: allow-raw-io

    def resolve(self, name: str) -> ResolvedValue:
        """Look up `name` in the pre-materialized table.

        Raises UnresolvedVariableError if not found.
        Does NOT check local_scope — the resolver handles that first.
        """
        if name in self._table:
            return self._table[name]
        all_names = self.available_names()
        if name.startswith("self."):
            hint_names = [n for n in all_names if n.startswith("self.")]
            hint = (
                f"variable '{name}' is not defined. "
                f"Available self.* keys: {hint_names}. "
                "Define it in customize.toml per architecture Decision 3."
            )
        else:
            hint_names = [n for n in all_names if not n.startswith("self.")]
            hint = (
                f"variable '{name}' is not defined. "
                f"Available: {hint_names}. "
                "Add it to _bmad/core/config.yaml (bmad-config) or "
                "customize.toml (self.* TOML) per architecture Decision 3."
            )
        raise errors.UnresolvedVariableError(
            "unresolved variable '{{" + name + "}}'",
            hint=hint,
        )

    def available_names(self) -> list[str]:
        """Return sorted list of resolvable names, for error hints."""
        return sorted(self._table.keys())


@dataclass(frozen=True)
class ResolveContext:
    skill_dir: PurePosixPath
    module_roots: dict[str, PurePosixPath]
    current_module: str
    scenario_root: PurePosixPath  # Story 3.5: project root for containment checks
    override_root: PurePosixPath | None = None
    target_ide: str | None = None
    # Include-directive props merged into this scope as the DFS descends.
    # Child keys shadow parent keys on collision. Recorded on every
    # descendant `ResolvedFragment.local_props` transitively (Story 1.3
    # will consume this during `{{var}}` resolution).
    local_scope: tuple[tuple[str, str], ...] = ()
    # The tier that produced the ROOT template the engine passed into
    # `resolve()`. Engine sets this to `"user-full-skill"` when it swapped
    # the root for the override at
    # `<override_root>/fragments/<current_module>/<skill>/SKILL.template.md`;
    # otherwise `"base"`.
    root_resolved_from: str = _TIER_BASE
    # Pre-materialized variable scope. None is valid for legacy tests that
    # have no {{var}} tokens; the resolver only raises when a VarCompile node
    # is actually encountered with var_scope=None.
    var_scope: VariableScope | None = None
    # Story 4.2: explain mode toggles two behaviors in `_walk_nodes`:
    #   1) Inject `FragmentBoundary` sentinels around each fragment's
    #      contribution so `_render_explain` can wrap it in `<Include>`.
    #   2) Replace `parser.Text` emission for `VarCompile` resolution with
    #      `ExplainVar` carrying the full `ResolvedValue` provenance.
    # Default False preserves all existing behavior — `compile_skill` never
    # sets it, only `explain_skill` does.
    explain_mode: bool = False
    # Story 4.2 fold-in 5: tier-5 (base) candidate path for the ROOT template
    # when `root_resolved_from == "user-full-skill"`. Engine sets this; the
    # resolver only forwards it to `dep_tree[0].base_path`. None for the
    # `base` root (no override) and for non-explain compiles.
    root_base_path: PurePosixPath | None = None


@dataclass
class CompileCache:
    """Per-compile, mutable. Engine allocates fresh per `compile_skill()`."""

    fragments: dict[tuple[PurePosixPath, str], list[parser.AstNode]] = field(
        default_factory=dict
    )
    # Keyed identically to `fragments`; holds raw source text so error
    # rendering (caret block) inside a fragment can point at the right
    # source line without re-reading.
    sources: dict[tuple[PurePosixPath, str], str] = field(default_factory=dict)

    def put(
        self,
        key: tuple[PurePosixPath, str],
        ast_nodes: list[parser.AstNode],
        source: str,
    ) -> None:
        """Store a parsed fragment and its source text together."""
        self.fragments[key] = ast_nodes
        self.sources[key] = source

    def get_source(self, key: tuple[PurePosixPath, str]) -> str:
        return self.sources[key]

    def __contains__(self, key: object) -> bool:
        return key in self.fragments


@dataclass(frozen=True)
class ResolvedFragment:
    src: str
    resolved_path: PurePosixPath
    resolved_from: str
    local_props: tuple[tuple[str, str], ...]
    # The scope visible to this fragment's body — local_props merged on top of
    # the parent's scope (child keys shadow parent keys). Recorded for
    # observability; Story 1.3 variable resolution will consume this.
    merged_scope: tuple[tuple[str, str], ...]
    nodes: list[parser.AstNode]
    # Tier-5 (base) candidate path, populated only when an override tier
    # (`user-module-fragment` or `user-override`) wins AND the base file
    # exists on disk. None for non-override tiers and for override wins where
    # no upstream base exists. Story 3.1: enables lockfile.py to compute
    # `base_hash` without re-probing tier 5 itself.
    base_path: PurePosixPath | None = None


@dataclass(frozen=True)
class FragmentBoundary:
    """Story 4.2: explain-mode sentinel injected around each fragment's
    contribution in the flat node stream. `is_start=True` is emitted
    before a fragment's child nodes, `is_start=False` after — so a linear
    walker can emit `<Include>` / `</Include>` wrappers without a tree
    reconstruction pass. Never produced when `explain_mode=False`."""
    fragment: ResolvedFragment
    is_start: bool


@dataclass(frozen=True)
class ExplainVar:
    """Story 4.2: explain-mode replacement for the resolved-text `parser.Text`
    that `_walk_nodes` would otherwise emit for a `VarCompile` node. Carries
    the full `ResolvedValue` provenance so `_render_explain` can synthesize
    a `<Variable>` tag with `source`, `source-path`, `toml-layer`,
    `contributing-paths`, etc. Never produced when `explain_mode=False`."""
    name: str
    value: str
    rv: ResolvedValue
    line: int
    col: int


# Story 4.2: union for explain-mode flat node streams. Non-explain compiles
# return `list[parser.AstNode]`; explain compiles return `list[ExplainNode]`.
ExplainNode = Union[parser.AstNode, FragmentBoundary, ExplainVar]


@dataclass
class _StackFrame:
    resolved_path: PurePosixPath
    authored_src: str


def _merge_scope(
    parent_scope: tuple[tuple[str, str], ...],
    include_props: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    """Merge with child (include) wins on key collision."""
    merged = dict(parent_scope)
    for name, value in include_props:
        merged[name] = value
    return tuple(sorted(merged.items()))


def _parse_include_src(
    src: str,
    current_module: str,
    module_roots: dict[str, PurePosixPath],
) -> tuple[str, PurePosixPath, str, bool]:
    """Split authored include src into routing components.

    Returns ``(effective_module, relative_subpath, leaf, had_module_prefix)``:
    - `effective_module` — the module whose root anchors the base tier.
    - `relative_subpath` — path beneath the module root (or the skill
      directory for bare paths), **with `..` segments preserved** so a
      future containment check can inspect escape intent.
    - `leaf` — the last component of `relative_subpath`, used for
      override namespacing at tiers 2 and 3.
    - `had_module_prefix` — True if the authored src started with a
      known module id (controls whether the base tier anchors at
      `module_roots[effective_module]` or at `skill_dir`).
    """
    # Story 4.4 fold-in (deferred-work :321): the `file:` URL scheme is
    # reserved for the Story 4.4 `<TomlGlobExpansion>` mechanism (TOML
    # array values like `persistent_facts = ["file:docs/*.md"]`). It is
    # NEVER valid as an `<<include path="...">>` attribute. Reject early —
    # before any filesystem probe — so a malicious or mis-authored
    # template like `<<include path="file:///etc/passwd">>` cannot reach
    # any I/O primitive at all.
    # R1 P1: case-insensitive — `FILE:`, `File:` must also reject. URL
    # schemes are case-insensitive per RFC 3986; matching only lowercase
    # would let `<<include path="FILE:/etc/passwd">>` slip past the guard.
    if src[:5].lower() == "file:":
        raise errors.UnknownDirectiveError(
            f"include path '{src}' uses reserved 'file:' scheme",
            file=None, line=None, col=None,
            hint=(
                "'file:' prefix is reserved for TOML array glob expansion "  # pragma: allow-raw-io
                "(customize.toml persistent_facts values); it cannot be used "
                "in <<include>> path attributes"
            ),
        )

    # `./` prefix is the author's explicit force-skill-local escape hatch.
    # PurePosixPath normalizes `./` away, so we must check the raw string
    # before the conversion to catch `./core/foo.template.md` and route it
    # to the current skill's tree rather than the `core` module root.
    if src.startswith("./"):
        pp = PurePosixPath(src)
        leaf = pp.name
        return current_module, pp, leaf, False

    pp = PurePosixPath(src)
    parts = pp.parts
    if parts and parts[0] in module_roots:
        effective_module = parts[0]
        if len(parts) > 1:
            relative_subpath = PurePosixPath(*parts[1:])
        else:
            relative_subpath = PurePosixPath(".")
        had_module_prefix = True
    else:
        effective_module = current_module
        relative_subpath = pp
        had_module_prefix = False
    leaf = relative_subpath.name
    return effective_module, relative_subpath, leaf, had_module_prefix


def _base_candidate(
    context: ResolveContext,
    effective_module: str,
    relative_subpath: PurePosixPath,
    had_module_prefix: bool,
) -> PurePosixPath | None:
    """The tier-5 base path. Also the anchor for tier-4 variant search.

    Returns `None` only when `effective_module` has no entry in
    `module_roots` (should not happen for bare paths because
    `current_module` must be present, but guarded nonetheless).
    """
    if had_module_prefix:
        root = context.module_roots.get(effective_module)
        if root is None:
            return None
        path = root / relative_subpath
    else:
        path = context.skill_dir / relative_subpath
    # Story 3.5: Reject ../ traversal that escapes scenario_root.
    return io.ensure_within_root(path, context.scenario_root)


def _variant_candidate(
    context: ResolveContext,
    base_candidate: PurePosixPath | None,
    leaf: str,
) -> PurePosixPath | None:
    """Tier-4 probe: IDE-suffixed siblings of the base candidate's name."""
    if base_candidate is None:
        return None
    if not leaf.endswith(_TEMPLATE_SUFFIX):
        return None
    parent = base_candidate.parent
    if not io.is_dir(str(parent)):
        return None
    stem = leaf[: -len(_TEMPLATE_SUFFIX)]
    entries = io.list_dir_sorted(str(parent))
    matches: list[PurePosixPath] = []
    for entry in entries:
        for ide in variants.KNOWN_IDES:
            if entry.name == f"{stem}.{ide}{_TEMPLATE_SUFFIX}":
                # Tier-4 `is_file` discipline (mirrors tiers 2/3/5 from R4
                # and engine tier 1 from R5): a directory whose name happens
                # to match `<stem>.<ide>.template.md` would otherwise win
                # the variant probe and crash later in `read_template` with
                # a raw `IsADirectoryError` outside the `CompilerError`
                # taxonomy.
                if io.is_file(str(entry)):
                    try:
                        safe_entry = io.ensure_within_root(entry, context.scenario_root)
                    except errors.OverrideOutsideRootError:
                        continue
                    matches.append(safe_entry)
                break
    return variants.select_variant(matches, context.target_ide)


def _lookup_tier(
    tier: str,
    context: ResolveContext,
    effective_module: str,
    relative_subpath: PurePosixPath,
    leaf: str,
    had_module_prefix: bool,
) -> PurePosixPath | None:
    skill_basename = context.skill_dir.name
    if tier == _TIER_USER_MODULE_FRAGMENT:
        if context.override_root is None:
            return None
        path = (
            context.override_root
            / "fragments"
            / effective_module
            / skill_basename
            / leaf
        )
        _safe = io.ensure_within_root(path, context.scenario_root)
        return _safe if io.is_file(str(_safe)) else None
    if tier == _TIER_USER_OVERRIDE:
        if context.override_root is None:
            return None
        path = context.override_root / "fragments" / leaf
        _safe = io.ensure_within_root(path, context.scenario_root)
        return _safe if io.is_file(str(_safe)) else None
    if tier == _TIER_BASE:
        base = _base_candidate(
            context, effective_module, relative_subpath, had_module_prefix
        )
        if base is None:
            return None
        return base if io.is_file(str(base)) else None
    if tier == _TIER_VARIANT:
        base = _base_candidate(
            context, effective_module, relative_subpath, had_module_prefix
        )
        return _variant_candidate(context, base, leaf)
    # `user-full-skill` never appears in the nested-tier loop.
    return None


def _relative_file(
    resolved_path: PurePosixPath, context: ResolveContext
) -> str:
    """Relative POSIX path for use in error messages.

    Preference: skill-root-relative; fall back to module-root-relative;
    final fallback: the full resolved path as a string.
    """
    try:
        return str(resolved_path.relative_to(context.skill_dir))
    except ValueError:
        pass
    for root in context.module_roots.values():
        try:
            return str(resolved_path.relative_to(root))
        except ValueError:
            continue
    if context.override_root is not None:
        try:
            return str(resolved_path.relative_to(context.override_root))
        except ValueError:
            pass
    return str(resolved_path)


def _missing_fragment_hint(
    src: str,
    context: ResolveContext,
    effective_module: str,
    relative_subpath: PurePosixPath,
    leaf: str,
    had_module_prefix: bool,
    include_line: int,
) -> str:
    """Per architecture hint quality bar: name a concrete `.template.md`
    path the author can create, plus the change-the-include alternative."""
    skill_basename = context.skill_dir.name
    if context.override_root is not None:
        create_path = (
            context.override_root
            / "fragments"
            / effective_module
            / skill_basename
            / leaf
        )
    else:
        base = _base_candidate(
            context, effective_module, relative_subpath, had_module_prefix
        )
        create_path = base if base is not None else context.skill_dir / leaf
    return (
        f"create {create_path}, or change <<include path=\"...\">> on line "
        f"{include_line} to an existing fragment (see "
        f"{effective_module}/fragments/ for options)"
    )


_MAX_INCLUDE_DEPTH = 200


def _make_include_token(node: parser.Include) -> str:
    """Reconstruct the full directive text including authored props."""
    if node.raw_token:
        return node.raw_token
    # Legacy fallback: reconstruct from sorted props (pre-Story 1.4 Include nodes with raw_token="")
    parts = [f'<<include path="{node.src}"']
    for name, value in sorted(node.props):
        parts.append(f' {name}="{value}"')
    parts.append(">>")
    return "".join(parts)


def _walk_nodes(
    nodes: list[parser.AstNode],
    context: ResolveContext,
    cache: CompileCache,
    visited_stack: list[_StackFrame],
    dep_tree: list[Any],
    enclosing_file: str,
    enclosing_source: str | None,
    depth: int = 0,
) -> list[Any]:
    """DFS pre-order node walk. Includes get expanded in place.

    Return type is `list[Any]` because explain-mode walks emit
    `FragmentBoundary` and `ExplainVar` sentinels alongside the standard
    `parser.AstNode` items (see `ExplainNode` union). Non-explain compiles
    still produce only `parser.AstNode` items, so `_render` continues to
    work unchanged.
    """
    if depth >= _MAX_INCLUDE_DEPTH:
        raise errors.CyclicIncludeError(
            f"include depth reached the {_MAX_INCLUDE_DEPTH}-level cap — "
            "check for a very deep or unbounded include chain",
            file=enclosing_file,
            chain=[f.authored_src for f in visited_stack],
            hint=(
                f"reduce nesting depth below {_MAX_INCLUDE_DEPTH} levels; "
                "if this is a legitimate deep chain, contact the maintainer"
            ),
        )

    flat: list[Any] = []
    for node in nodes:
        # --- VarCompile: resolve inline at the correct lexical scope. ---
        if isinstance(node, parser.VarCompile):
            name = node.name
            resolved_text: str | None = None
            resolved_rv: ResolvedValue | None = None  # populated when var_scope wins

            # For non-self.* names, check local_scope (include props) first.
            if not name.startswith("self."):
                for prop_name, prop_value in context.local_scope:
                    if prop_name == name:
                        resolved_text = prop_value
                        break

            if resolved_text is None:
                if context.var_scope is None:
                    raise errors.UnresolvedVariableError(
                        "unresolved variable '{{" + name + "}}'",
                        file=enclosing_file,
                        line=node.line,
                        col=node.col,
                        token=f"{{{{{name}}}}}",
                        hint=(
                            "no VariableScope configured — "
                            "pass a VariableScope to engine.compile_skill()"
                        ),
                        source=enclosing_source,
                    )
                try:
                    rv = context.var_scope.resolve(name)
                except errors.UnresolvedVariableError as exc:
                    raise errors.UnresolvedVariableError(
                        exc.desc,
                        file=enclosing_file,
                        line=node.line,
                        col=node.col,
                        token=f"{{{{{name}}}}}",
                        hint=exc.hint,
                        source=enclosing_source,
                    ) from None
                resolved_text = rv.value
                resolved_rv = rv

            # By construction `resolved_text` is set by this point: either a
            # local_scope match (props are always strings) or `rv.value` from
            # `var_scope.resolve()` (always str), or the function has raised
            # `UnresolvedVariableError` above. The assert narrows the type
            # for mypy (R1 P3) and serves as a tripwire if a future code
            # path forgets to set it.
            assert resolved_text is not None
            if context.explain_mode:
                # Story 4.2: explain mode emits ExplainVar carrying the full
                # ResolvedValue (or a synthetic one for local-scope wins).
                explain_rv = resolved_rv if resolved_rv is not None else ResolvedValue(
                    value=resolved_text,
                    source="local-scope",
                )
                flat.append(ExplainVar(
                    name=name,
                    value=resolved_text,
                    rv=explain_rv,
                    line=node.line,
                    col=node.col,
                ))
            else:
                flat.append(parser.Text(content=resolved_text, line=node.line, col=node.col))
            continue

        # --- VarRuntime: pass through unchanged; _render() emits {name}. ---
        if isinstance(node, parser.VarRuntime):
            flat.append(node)
            continue

        if not isinstance(node, parser.Include):
            flat.append(node)
            continue

        effective_module, relative_subpath, leaf, had_prefix = _parse_include_src(
            node.src, context.current_module, context.module_roots
        )

        resolved_path: PurePosixPath | None = None
        tier_won: str | None = None
        for tier in _NESTED_TIERS:
            candidate = _lookup_tier(
                tier, context, effective_module, relative_subpath, leaf, had_prefix
            )
            if candidate is not None:
                resolved_path = candidate
                tier_won = tier
                break

        if resolved_path is None or tier_won is None:
            token = _make_include_token(node)
            raise errors.MissingFragmentError(
                "fragment not found",
                file=enclosing_file,
                line=node.line,
                col=node.col,
                token=token,
                hint=_missing_fragment_hint(
                    node.src,
                    context,
                    effective_module,
                    relative_subpath,
                    leaf,
                    had_prefix,
                    node.line,
                ),
                source=enclosing_source,
            )

        # Cycle detection via resolved_path identity on the DFS stack.
        for frame in visited_stack:
            if frame.resolved_path == resolved_path:
                chain = [f.authored_src for f in visited_stack] + [node.src]
                token = _make_include_token(node)
                raise errors.CyclicIncludeError(
                    "cyclic include detected",
                    file=enclosing_file,
                    line=node.line,
                    col=node.col,
                    token=token,
                    chain=chain,
                    hint=(
                        "break the cycle by removing one <<include>> directive "
                        "in the chain above; the most recently added include "
                        "is usually the safest edge to cut"
                    ),
                    source=enclosing_source,
                )

        cache_key = (resolved_path, tier_won)
        if cache_key not in cache:
            fragment_src = io.read_template(str(resolved_path))
            rel_path = _relative_file(resolved_path, context)
            cache.put(cache_key, parser.parse(fragment_src, rel_path), fragment_src)
        fragment_ast = cache.fragments[cache_key]
        fragment_src = cache.get_source(cache_key)

        child_scope = _merge_scope(context.local_scope, node.props)
        child_context = replace(context, local_scope=child_scope)

        visited_stack.append(
            _StackFrame(resolved_path=resolved_path, authored_src=node.src)
        )
        placeholder_idx = len(dep_tree)
        dep_tree.append(None)
        child_flat = _walk_nodes(
            fragment_ast,
            child_context,
            cache,
            visited_stack,
            dep_tree,
            enclosing_file=_relative_file(resolved_path, context),
            enclosing_source=fragment_src,
            depth=depth + 1,
        )
        visited_stack.pop()

        base_path_for_frag: PurePosixPath | None = None
        if tier_won in (_TIER_USER_MODULE_FRAGMENT, _TIER_USER_OVERRIDE):
            base_candidate = _base_candidate(
                context, effective_module, relative_subpath, had_prefix
            )
            if base_candidate is not None and io.is_file(str(base_candidate)):
                base_path_for_frag = base_candidate

        resolved = ResolvedFragment(
            src=node.src,
            resolved_path=resolved_path,
            resolved_from=tier_won,
            local_props=node.props,
            merged_scope=child_scope,
            nodes=child_flat,
            base_path=base_path_for_frag,
        )
        dep_tree[placeholder_idx] = resolved
        if context.explain_mode:
            # Story 4.2: bracket the fragment's contribution with
            # FragmentBoundary sentinels so _render_explain can emit the
            # corresponding <Include>...</Include> wrapper inline.
            flat.append(FragmentBoundary(fragment=resolved, is_start=True))
            flat.extend(child_flat)
            flat.append(FragmentBoundary(fragment=resolved, is_start=False))
        else:
            flat.extend(child_flat)
    return flat


def resolve(
    ast: list[parser.AstNode],
    context: ResolveContext,
    cache: CompileCache,
    *,
    root_src: str = "",
    root_path: PurePosixPath | None = None,
    root_source: str | None = None,
) -> tuple[list[parser.AstNode], list[ResolvedFragment]]:
    """Expand an AST's includes into an inline node stream.

    Returns `(flat_nodes, dep_tree)`:
    - `flat_nodes` — the input AST with every `Include` replaced in place by
      its recursively-resolved child nodes. Story 1.2 renders this as text
      (still only `Text` nodes after inlining); Story 1.3 will add
      `{{var}}` resolution atop the same walk.
    - `dep_tree` — a flat `list[ResolvedFragment]` in DFS pre-order. The
      first entry is always the root, carrying
      `resolved_from = context.root_resolved_from`. Siblings that include
      the same fragment show up as separate entries (the cache suppresses
      re-read/re-parse, not dep-tree duplication).

    `root_src` / `root_path` / `root_source` exist so the root's
    `ResolvedFragment` and any error raised at the root level can carry
    meaningful file + source context. Engine populates them from the CLI
    arguments; resolver tests can omit them (then `resolved_path` on the
    root entry defaults to the skill directory).
    """
    dep_tree: list[Any] = []
    visited_stack: list[_StackFrame] = []

    root_rel_file = (
        _relative_file(root_path, context) if root_path is not None else root_src
    )
    placeholder_idx = len(dep_tree)
    dep_tree.append(None)
    flat = _walk_nodes(
        ast,
        context,
        cache,
        visited_stack,
        dep_tree,
        enclosing_file=root_rel_file or context.skill_dir.name,
        enclosing_source=root_source,
    )

    root_entry = ResolvedFragment(
        src=root_src,
        resolved_path=(
            root_path if root_path is not None else context.skill_dir
        ),
        resolved_from=context.root_resolved_from,
        local_props=context.local_scope,
        merged_scope=context.local_scope,
        nodes=flat,
        # Story 4.2 fold-in 5: when the engine probed and found a
        # `user-full-skill` override, it sets `context.root_base_path` to the
        # tier-5 base template path so `_render_explain` can hash-and-attribute
        # the upstream base via `<Include base-hash="...">` on the root.
        # `None` for `base` roots (no override) and for non-explain compiles.
        base_path=context.root_base_path,
    )
    dep_tree[placeholder_idx] = root_entry
    return flat, dep_tree
