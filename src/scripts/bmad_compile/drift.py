"""Story 5.1: per-skill drift detection engine for `bmad upgrade --dry-run`.

Six drift categories: prose_fragment_changes, toml_default_changes,
orphaned_overrides (prose only, v1), new_defaults, glob_changes,
variable_provenance_shifts.

Does NOT import engine.py, resolver.py, or lockfile.py — lockfile JSON is
parsed by the caller and passed in as plain dicts. Only imports bmad_compile.io
and stdlib.

Fragment path convention (empirically verified): lockfile paths are
scenario-root-relative POSIX where scenario_root = <project_root>/_bmad/.
Reconstruction: Path(project_root) / "_bmad" / lockfile_fragment_path.

Override base path convention (user-module-fragment tier):
  lockfile path: custom/fragments/<module>/<skill>/<filename>
  inferred base: <module>/<skill>/fragments/<filename>
No base_path is stored in the lockfile — only base_hash — so we reconstruct
base path from the override path's component structure.
"""
from __future__ import annotations

import glob as _glob  # pragma: allow-raw-io
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath  # pragma: allow-raw-io
from typing import Any

from . import io

_OVERRIDE_TIERS = frozenset({"user-module-fragment", "user-override"})


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ProseFragmentChange:
    path: str
    old_hash: str
    new_hash: str | None  # None when base fragment deleted upstream
    user_override_hash: str | None
    tier: str  # "base" | "user-override" | "user-module-fragment"


@dataclass
class TomlDefaultChange:
    key: str
    old_hash: str
    new_value: str
    user_override_value: str | None


@dataclass
class OrphanedOverride:
    path: str
    override_hash: str
    reason: str  # "base_fragment_removed"


@dataclass
class NewDefault:
    key: str
    new_value: str
    source: str  # TOML layer that introduced it: "defaults" | "team" | "user"


@dataclass
class GlobChange:
    toml_key: str
    pattern: str
    old_match_set_hash: str | None
    new_match_set_hash: str | None
    added_matches: list[str]
    removed_matches: list[str]


@dataclass
class VariableProvenanceShift:
    name: str
    old_source: str
    new_source: str
    old_toml_layer: str | None
    new_toml_layer: str | None


@dataclass
class DriftReport:
    skill: str
    prose_fragment_changes: list[ProseFragmentChange] = field(default_factory=list)
    toml_default_changes: list[TomlDefaultChange] = field(default_factory=list)
    orphaned_overrides: list[OrphanedOverride] = field(default_factory=list)
    new_defaults: list[NewDefault] = field(default_factory=list)
    glob_changes: list[GlobChange] = field(default_factory=list)  # pragma: allow-raw-io
    variable_provenance_shifts: list[VariableProvenanceShift] = field(default_factory=list)

    def has_drift(self) -> bool:
        return any([
            self.prose_fragment_changes, self.toml_default_changes,
            self.orphaned_overrides, self.new_defaults,
            self.glob_changes, self.variable_provenance_shifts,  # pragma: allow-raw-io
        ])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _toml_str(v: Any) -> str:
    """Serialize a TOML scalar to string the same way resolver.py does."""
    return str(v).lower() if isinstance(v, bool) else str(v)


def _flatten_toml(d: dict[str, Any], prefix: str = "") -> list[tuple[str, str]]:
    """Recursively flatten a TOML dict into (dotted_key, str_value) pairs.

    Skips arrays (file: glob patterns handled by glob_inputs, other arrays
    unsupported). Applies the same bool-lowercasing as resolver.py:345.
    Keys are prefixed with "self." to match lockfile variable names.
    """
    result: list[tuple[str, str]] = []
    for k, v in d.items():
        dotted = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            result.extend(_flatten_toml(v, dotted))
        elif isinstance(v, list):
            pass  # arrays handled via glob_inputs or out of scope  # pragma: allow-raw-io
        else:
            result.append((f"self.{dotted}", _toml_str(v)))
    return result


def _load_toml_layers(
    skill_basename: str, scenario_root: Path, entry: dict[str, Any]
) -> list[tuple[str, dict[str, Any]]]:
    """Build the TOML layer stack for a skill (defaults → team → user order)."""
    layers: list[tuple[str, dict[str, Any]]] = []

    # Find customize.toml from the skill directory, inferred from base fragments.
    customize_toml: Path | None = None
    for frag in entry.get("fragments", []):
        if frag.get("resolved_from") == "base":
            parts = PurePosixPath(frag["path"]).parts
            if len(parts) >= 2:
                candidate = scenario_root / parts[0] / parts[1] / "customize.toml"
                if candidate.is_file():
                    customize_toml = candidate
                    break

    # Fall back to source_path from variables if fragment-based inference fails.
    if customize_toml is None:
        for var in entry.get("variables", []):
            sp = var.get("source_path", "")
            if sp and sp.endswith("customize.toml"):
                candidate = scenario_root / sp
                if candidate.is_file():
                    customize_toml = candidate
                    break

    if customize_toml is not None and customize_toml.is_file():
        layers.append(("defaults", tomllib.loads(customize_toml.read_text("utf-8"))))

    team_toml = scenario_root / "custom" / f"{skill_basename}.toml"
    if team_toml.is_file():
        layers.append(("team", tomllib.loads(team_toml.read_text("utf-8"))))

    user_toml = scenario_root / "custom" / f"{skill_basename}.user.toml"
    if user_toml.is_file():
        layers.append(("user", tomllib.loads(user_toml.read_text("utf-8"))))

    return layers


# ---------------------------------------------------------------------------
# Category detectors
# ---------------------------------------------------------------------------

def _detect_prose_fragment_drift(
    entry: dict[str, Any], scenario_root: Path
) -> list[ProseFragmentChange]:
    """Category 1: prose fragment content hash changes."""
    result: list[ProseFragmentChange] = []
    for frag in entry.get("fragments", []):
        frag_path: str = frag["path"]
        old_hash: str = frag["hash"]
        resolved_from: str = frag["resolved_from"]

        # Fragment path is scenario_root-relative POSIX — reconstruct absolute.
        abs_path = Path(scenario_root, *PurePosixPath(frag_path).parts)

        if abs_path.is_file():
            new_hash = io.hash_text(io.read_template(str(abs_path)))
            if new_hash != old_hash:
                result.append(ProseFragmentChange(
                    path=frag_path,
                    old_hash=old_hash,
                    new_hash=new_hash,
                    user_override_hash=frag.get("base_hash") if resolved_from in _OVERRIDE_TIERS else None,
                    tier=resolved_from,
                ))
        elif resolved_from == "base":
            # Base file deleted upstream — report as ProseFragmentChange with new_hash=None.
            # (Missing override files are not drift — the base still compiles cleanly.)
            result.append(ProseFragmentChange(
                path=frag_path,
                old_hash=old_hash,
                new_hash=None,
                user_override_hash=None,
                tier=resolved_from,
            ))

    result.sort(key=lambda c: c.path)
    return result


def _detect_glob_drift(  # pragma: allow-raw-io
    entry: dict[str, Any], scenario_root: Path
) -> list[GlobChange]:
    """Category 5: glob match-set changes (file added, removed, or edited)."""
    result: list[GlobChange] = []
    for gi in entry.get("glob_inputs", []):
        resolved_pattern: str | None = gi.get("resolved_pattern")
        if resolved_pattern is None:
            continue  # deferred (runtime-variable pattern)
        # Skip patterns that contain runtime variable placeholders {name}.
        if "{" in resolved_pattern:
            continue

        # Re-expand the glob using the stored absolute pattern.
        current_abs_matches = sorted(_glob.glob(resolved_pattern, recursive=True))  # pragma: allow-raw-io

        # Hash each match's binary content (Story 4.4 algorithm).
        current_rel_hashes: list[tuple[str, str]] = []
        for match_str in current_abs_matches:
            match_abs = Path(match_str)
            try:
                match_rel = match_abs.relative_to(scenario_root).as_posix()
            except ValueError:
                match_rel = match_abs.as_posix()
            content_hash = io.sha256_hex(match_abs.read_bytes())
            current_rel_hashes.append((match_rel, content_hash))

        # Compute composite hash (same algorithm as resolver.py:657-658).
        if current_rel_hashes:
            hash_parts = [f"{rel}:{h}" for rel, h in sorted(current_rel_hashes)]
            new_match_set_hash: str | None = io.sha256_hex(
                "\n".join(hash_parts).encode("utf-8")
            )
        else:
            new_match_set_hash = None

        old_match_set_hash: str | None = gi.get("match_set_hash")
        if new_match_set_hash == old_match_set_hash:
            continue

        old_paths = {m["path"] for m in gi.get("matches", [])}
        new_paths = {rel for rel, _ in current_rel_hashes}
        result.append(GlobChange(
            toml_key=gi["toml_key"],
            pattern=gi["pattern"],
            old_match_set_hash=old_match_set_hash,
            new_match_set_hash=new_match_set_hash,
            added_matches=sorted(new_paths - old_paths),
            removed_matches=sorted(old_paths - new_paths),
        ))

    result.sort(key=lambda c: c.toml_key)
    return result


def _detect_toml_variable_drift(
    entry: dict[str, Any], scenario_root: Path
) -> tuple[list[TomlDefaultChange], list[NewDefault], list[VariableProvenanceShift]]:
    """Categories 2, 4, 6: TOML default changes, new defaults, provenance shifts."""
    skill_basename: str = entry["skill"]
    layers = _load_toml_layers(skill_basename, scenario_root, entry)

    # Build current flat map: key → (str_value, layer_name).
    # Last-wins: later (higher-priority) layers overwrite earlier ones.
    current_flat: dict[str, tuple[str, str]] = {}
    for layer_name, layer_dict in layers:
        for key, str_val in _flatten_toml(layer_dict):
            current_flat[key] = (str_val, layer_name)

    lockfile_var_names: set[str] = set()
    toml_changes: list[TomlDefaultChange] = []
    new_defaults: list[NewDefault] = []
    provenance_shifts: list[VariableProvenanceShift] = []

    for var in entry.get("variables", []):
        src = var.get("source", "")
        if src == "local-scope":
            continue
        name: str = var["name"]
        lockfile_var_names.add(name)

        if src != "toml":
            continue  # only TOML-sourced variables have drift via TOML layers

        current = current_flat.get(name)
        if current is None:
            continue  # variable disappeared from TOML (different kind of drift, skip v1)

        current_value, current_layer = current
        current_hash = io.hash_text(current_value)
        old_hash: str = var["value_hash"]

        if current_hash != old_hash:
            toml_changes.append(TomlDefaultChange(
                key=name,
                old_hash=old_hash,
                new_value=current_value,
                user_override_value=None,
            ))

        # Provenance shift: source or toml_layer changed.
        old_toml_layer: str | None = var.get("toml_layer")  # optional in lockfile
        if old_toml_layer != current_layer:
            provenance_shifts.append(VariableProvenanceShift(
                name=name,
                old_source=src,
                new_source="toml",
                old_toml_layer=old_toml_layer,
                new_toml_layer=current_layer,
            ))

    # New defaults: TOML keys present now but not in lockfile variables.
    # Scan layers in priority order (defaults → team → user); first occurrence wins.
    new_default_map: dict[str, tuple[str, str]] = {}
    for layer_name, layer_dict in layers:
        for key, str_val in _flatten_toml(layer_dict):
            if key not in lockfile_var_names and key not in new_default_map:
                new_default_map[key] = (str_val, layer_name)

    for key, (val, layer_name) in new_default_map.items():
        new_defaults.append(NewDefault(key=key, new_value=val, source=layer_name))

    return (
        sorted(toml_changes, key=lambda c: c.key),
        sorted(new_defaults, key=lambda n: n.key),
        sorted(provenance_shifts, key=lambda p: p.name),
    )


def _detect_orphaned_overrides(
    entry: dict[str, Any], scenario_root: Path
) -> list[OrphanedOverride]:
    """Category 3: user prose-fragment overrides whose upstream base no longer exists.

    v1 scope: prose fragment overrides only (user-module-fragment tier).
    Orphaned TOML override files (_bmad/custom/<skill>.toml where the skill is
    no longer in the lockfile) are out of scope for v1.

    Base path reconstruction for user-module-fragment:
      override path (scenario-root-relative): custom/fragments/<module>/<skill>/<filename>
      inferred base path:                     <module>/<skill>/fragments/<filename>
    This follows the install-phase override-root convention (override_root = _bmad/custom/).
    """
    result: list[OrphanedOverride] = []
    for frag in entry.get("fragments", []):
        resolved_from: str = frag["resolved_from"]
        if resolved_from != "user-module-fragment":
            # Only handle user-module-fragment tier in v1; user-override base path
            # reconstruction requires different conventions not yet specified.
            continue

        base_hash = frag.get("base_hash")
        if base_hash is None:
            continue  # override was added without a base — not an orphan

        override_path: str = frag["path"]
        parts = PurePosixPath(override_path).parts
        # Expected: ('custom', 'fragments', '<module>', '<skill>', '<filename>')
        if len(parts) < 5 or parts[0] != "custom" or parts[1] != "fragments":
            continue  # unexpected path structure — skip

        # Reconstruct: custom/fragments/<module>/<skill>/<file> → <module>/<skill>/fragments/<file>
        module, skill_dir = parts[2], parts[3]
        rest = parts[4:]
        base_rel = str(PurePosixPath(module, skill_dir, "fragments", *rest))
        base_abs = Path(scenario_root, *PurePosixPath(base_rel).parts)

        if not base_abs.is_file():
            result.append(OrphanedOverride(
                path=override_path,
                override_hash=frag["hash"],
                reason="base_fragment_removed",
            ))

    result.sort(key=lambda o: o.path)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_drift(entry: dict[str, Any], project_root: str) -> DriftReport:
    """Run all four detection functions for one lockfile entry.

    No fast path in v1 — always runs all categories. source_hash in the
    lockfile is root-template-only and cannot be used as an all-inputs gate.
    """
    scenario_root = Path(project_root) / "_bmad"
    skill: str = entry["skill"]

    prose = _detect_prose_fragment_drift(entry, scenario_root)
    globs = _detect_glob_drift(entry, scenario_root)  # pragma: allow-raw-io
    toml_changes, new_defs, prov_shifts = _detect_toml_variable_drift(entry, scenario_root)
    orphans = _detect_orphaned_overrides(entry, scenario_root)

    return DriftReport(
        skill=skill,
        prose_fragment_changes=prose,
        toml_default_changes=toml_changes,
        orphaned_overrides=orphans,
        new_defaults=new_defs,
        glob_changes=globs,  # pragma: allow-raw-io
        variable_provenance_shifts=prov_shifts,
    )
