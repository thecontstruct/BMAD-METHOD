---
title: "TOML Merge Contract"
description: Authoritative contract for BMAD's TOML merge model — per-skill and
  central config stacks, merge semantics, error taxonomy, and security boundaries.
---

Authoritative reference for BMAD's TOML configuration merge model. This document
covers both callers of `bmad_compile/toml_merge.py`, all four merge rules, the full
error taxonomy, edge cases, security boundaries, and sigil semantics.

Epic 8 implementers: read this before building on the TOML config stack.

## Overview

`bmad_compile/toml_merge.py` is a shared merge engine with **two callers**:

1. **`engine.py`** — builds a **per-skill 3-layer stack** (defaults → team → user)
   for each `compile_skill()` call. Resolves `self.*` TOML variables for one skill
   at compile time.
2. **`src/scripts/resolve_config.py`** — builds a **central 4-layer stack** for the
   project's agent roster and install answers, resolved once per engine invocation.

The term "4-layer" in the story title refers to the central config stack in
`resolve_config.py`. The per-skill stack has 3 layers (defaults, team, user). Together
with the reserved install-flag tier, the full cascade is **8 tiers** per ADR
§Decision 17.

The merge engine applies the same four structural rules to both stacks. Both callers
pass their layers to `merge_layers(*layers)` — `toml_merge.py` does not know which
caller it is serving.

---

## Per-Skill Layer Stack

Implemented in `engine.py` lines 327–342. Resolved once per `compile_skill()` call.

| Layer name | File path | Priority |
|---|---|---|
| `defaults` | `{skill_dir}/customize.toml` | lowest |
| `team`     | `_bmad/custom/{skill_basename}.toml` | middle |
| `user`     | `_bmad/custom/{skill_basename}.user.toml` | highest |

**Priority order:** `defaults` < `team` < `user`. Higher-priority layer wins on
conflicts (see §Merge Semantics).

**Conditionality:** layers 2 (`team`) and 3 (`user`) are only loaded when the file
exists. A missing file is a no-op — equivalent to an empty `{}`. Layer 1 (`defaults`)
is also conditional on `customize.toml` existing in the skill directory.

`override_root` is resolved to `_bmad/custom/` relative to the project root. A
caller-supplied `override_root` is validated by `io.ensure_within_root()` (see
§Security).

The engine constructs the layer stack as a list of `(label, dict)` tuples — the label
(`"defaults"`, `"team"`, `"user"`) becomes the `toml-layer` provenance attribute in
`--explain` output (see `docs/compile/explain-vocabulary.md`).

---

## Central Config Layer Stack

Implemented in `src/scripts/resolve_config.py` lines 101–106. Resolved once per
engine invocation — the merged result is shared across all skills compiled in that run.

| Layer name | TOML-layer label | File path | Ownership | Priority |
|---|---|---|---|---|
| `base_team` | `central-base-team` | `_bmad/config.toml` | installer-owned, committed | lowest |
| `base_user` | `central-base-user` | `_bmad/config.user.toml` | installer-owned, gitignored | 2nd |
| `custom_team` | `central-custom-team` | `_bmad/custom/config.toml` | human-authored, committed | 3rd |
| `custom_user` | `central-custom-user` | `_bmad/custom/config.user.toml` | human-authored, gitignored | highest |

**Ownership:**
- `base_team` / `base_user` are written by `npm install`. `base_user` captures
  personal install answers and is gitignored.
- `custom_team` / `custom_user` are human-authored overrides. `custom_user` is
  gitignored (personal preferences).

**Required layer:** `base_team` (`_bmad/config.toml`) is required. `resolve_config.py`
calls `load_toml(..., required=True)` for it — if missing, writes an error to stderr
and exits with code 1. All other layers are optional; missing = `{}`.

**Central loader vs. per-skill loader:** `resolve_config.py` uses its own `load_toml()`
function — distinct from `toml_merge.load_toml_file()`. The central loader does not
strip UTF-8 BOM, does not perform TOCTOU recovery, and surfaces parse errors as stderr
warnings (or errors for required layers). See §Edge Cases for the full comparison.

**Upstream prototype comparison:** `upstream/feat/quick-dev-python-config` has its own
4-layer inline merge in `render.py` (lines 33–41) covering the same 4 central config
files. That implementation uses simplified semantics: scalars override, tables deep
merge, but **all arrays append** (no keyed AoT merge). The comment at render.py line 39
reads: "we don't need the full keyed-merge semantics of resolve_config.py". Our
`resolve_config.py` uses the full keyed-merge semantics via `bmad_compile.toml_merge`.

Implication for Epic 8: use `resolve_config.py` when building on the central config
stack, not `render.py`'s simplified merge, unless you are certain no keyed AoT values
are present in the central config files.

---

## 8-Tier ADR Cascade Mapping

ADR §Decision 17 (`proposals/bmad-skill-compiler-architecture.md`) defines an 8-tier
cascade. The current implementation realizes all 8 tiers:

| Tier | ADR label | Implementation | Stack |
|---|---|---|---|
| 1 | `install-flag` | Reserved for TOML-path CLI targeting (not yet shipped). The current `--set KEY=VALUE` flag in `compile.py:692` targets the YAML non-`self.*` cascade only. ADR §Decision 3 reserves an analogous TOML-targeting flag as future work. | — |
| 2 | `toml/defaults` | `defaults` layer: `{skill_dir}/customize.toml` | per-skill (`engine.py`) |
| 3 | `toml/team` | `team` layer: `_bmad/custom/{skill}.toml` | per-skill (`engine.py`) |
| 4 | `toml/user` | `user` layer: `_bmad/custom/{skill}.user.toml` | per-skill (`engine.py`) |
| 5 | `central-base-team` | `base_team`: `_bmad/config.toml` | central (`resolve_config.py`) |
| 6 | `central-base-user` | `base_user`: `_bmad/config.user.toml` | central (`resolve_config.py`) |
| 7 | `central-custom-team` | `custom_team`: `_bmad/custom/config.toml` | central (`resolve_config.py`) |
| 8 | `central-custom-user` | `custom_user`: `_bmad/custom/config.user.toml` | central (`resolve_config.py`) |

**Precedence principle — specific scope wins over general scope.** Per-skill TOML
layers (tiers 2–4) outrank the process-global central TOML layers (tiers 5–8) even
when the per-skill layer is a *shipped default* (tier 2) and the central layer is an
*explicit user override* (tier 8).

Example: a skill author declares `agent.icon = "📋"` in PM's `customize.toml` (tier 2).
Even if `_bmad/custom/config.user.toml` (tier 8) sets `agent.icon = "⚙️"`, the
per-skill default wins. The rationale: per-skill intent from the skill author is more
specific than a global preference.

This is the most surprising rule in the cascade. It is not a bug — it is an explicit
design decision documented in ADR §Decision 17 lines 322–326.

---

## Merge Semantics

The same four rules apply to both per-skill and central stacks. All merges are pairwise,
left-to-right (lowest priority first), accumulating into `result`.

### Rule 1 — Scalars: higher-priority layer wins

When a key maps to a scalar in both layers, the override wins with full replacement; no
blending occurs. This also applies to cross-type values (e.g., base has a string,
override has an int) — the override value wins silently. No error is raised for
cross-type scalar conflicts.

### Rule 2 — Tables (dicts): deep recursive merge

When a key maps to a dict in both layers, the result is a deep recursive merge of both
dicts. Keys present in both layers are resolved recursively (applying these same rules at
the nested level). Keys present in only one layer are preserved as-is. There is no depth
limit on recursion.

### Rule 3 — Keyed arrays-of-tables (AoT): merge by `code` or `id`

When a key maps to a list in both layers, and **every item in both layers** is a dict
sharing the same key field (`code` or `id`), the arrays are merged by that key:
- An override item whose key matches a base item **fully replaces** the entire base item.
  Fields in the base item that are NOT present in the override item are dropped — this is
  NOT a recursive deep-merge of the item's fields. The override item wins in full.
- An override item with no matching base key is appended to the result list.
- Base items with no override counterpart are preserved.

The all-or-nothing key detection rule: `_keyed_field()` uses `all()` — if **any** item
in **either** layer is missing the `code`/`id` field, the entire array falls through to
Rule 4 (plain-append), not keyed merge. A single non-keyed item in either layer silently
downgrades the merge to append.

### Rule 4 — All other arrays: plain append

Arrays that do not satisfy the keyed AoT condition (Rule 3) are concatenated: base items
first, override items appended. Non-dict arrays (e.g., `["a", "b"]`), uniformly non-keyed
dict arrays, and empty arrays all follow this rule.

---

## Error Taxonomy (AoT Violations)

`_deep_merge` raises `errors.UnknownDirectiveError` when AoT structural invariants are
violated. The subtype is encoded as a label prefix in the `desc` field (the
`errors.py` exception class is frozen per spec §7 — no new subclasses; tests assert
via substring match on `desc`).

| Subtype label | Trigger condition |
|---|---|
| `DUPLICATE_KEYED_ARRAY` | Same `code`/`id` value appears 2+ times within one layer (base or override). |
| `MIXED_AOT_SHAPE` | An array contains at least one dict item but not all items are dicts (within the same layer). A uniformly non-dict array does NOT trigger this — it falls through to plain-append (Rule 4). Only fires when keyed-mode is attempted but the shape is malformed. |
| `MIXED_KEY_FIELDS` | Base layer uses `code` as the key field; override layer uses `id` (or vice versa). Both sides have a recognized key field, but they differ. |
| `UNHASHABLE_KEYED_VALUE` | The `code`/`id` value for an AoT item is not a hashable scalar string or integer. `bool` is rejected explicitly even though it is a subclass of `int` — `hash(True) == hash(1)` would silently merge `code=True` with `code=1`. |

**Taxonomy scope:** These errors cover AoT structural violations during merge. Load-phase
exceptions propagate unchanged from `load_toml_file()` and are NOT remapped:
- `tomllib.TOMLDecodeError` → raised as `UnknownDirectiveError` with desc prefix
  `"TOML parse error in '{path}'"` (this is a load-phase error, distinct from the AoT
  merge-phase errors above).
- `UnicodeDecodeError` from UTF-16 input → propagates uncaught (known gap; see §Edge
  Cases).

---

## Edge Cases

| Edge case | Per-skill stack (`toml_merge.load_toml_file`) | Central stack (`resolve_config.load_toml`) |
|---|---|---|
| Missing layer file | Returns `{}` — treated as no-op; layer is omitted from stack. | Optional layers return `{}`. Required layer (`base_team`) writes to stderr and calls `sys.exit(1)`. |
| TOCTOU race (file removed between `is_file` and `read_bytes`) | Catches `FileNotFoundError` from `io.read_bytes`, returns `{}` — same result as never existed. (Story 5.5b AC-8.) | Not handled — `OSError` propagates as a stderr warning (or error for required layers). |
| UTF-8 BOM | `decode('utf-8-sig')` strips one leading BOM; a `while` loop then strips any additional leading BOM characters (Story 7.13 AC-B). Any number of leading UTF-8 BOMs are removed. | No BOM stripping. The file is opened in binary mode via `tomllib.load()` which handles standard UTF-8 but does not strip BOM. |
| UTF-16 BOM (known gap) | `UnicodeDecodeError` propagates uncaught — not handled. Only UTF-8 BOM is stripped. (Deferred: `deferred-work.md` DN-α-KEEP, Story 7.13 R2.) | Same uncaught `UnicodeDecodeError`, surfaced as stderr warning/error by the OSError handler. |
| Empty layer (`{}`) | Valid no-op — `merge_layers()` accepts it and merges without error. (Story 5.5b AC-7.) | Same — `merge_layers()` receives `{}` for missing optional layers. |
| Non-dict layer | `merge_layers()` raises `TypeError` with the layer index in the message. (Story 5.5b AC-7.) | Not expected — `load_toml()` returns `{}` if parsed result is not a dict. |
| Nested tables | Recursively deep-merged; no depth limit. | Same — both pass layers through `merge_layers()`. |
| AoT with 0 items | An empty list has no keyed field (`_keyed_field` returns `None` for empty input); treated as plain-array append (Rule 4). | Same. |
| All layers absent / all `{}` | `merge_layers()` called with empty or all-`{}` input; result is `{}`. | Same. |
| Cross-type value (same key, different types) | Override value wins silently — same as scalar override (Rule 1). No error raised. | Same. |
| TOML parse error | `UnknownDirectiveError` with desc prefix `"TOML parse error in '{path}'"`, including file, line, and column. | `tomllib.TOMLDecodeError` written to stderr as warning or error; optional layers return `{}`, required layer exits. |

**Loader distinction summary:** The per-skill stack's `toml_merge.load_toml_file()` and
the central stack's `resolve_config.load_toml()` are separate functions with different
error semantics. UTF-8 BOM stripping, TOCTOU recovery, and `UnknownDirectiveError`
taxonomy apply only to the per-skill stack. The central loader surfaces errors via
stderr rather than exceptions.

---

## Security and Trust Boundaries

### Per-Skill Layer Trust

| Layer | Trust level | Rationale |
|---|---|---|
| `defaults` | Trusted | Shipped with skill source; compiled into the installer artifact; controlled by the skill author. |
| `team` | Semi-trusted | Committed to version control; controlled by the team. Visible to all team members. |
| `user` | Untrusted (from engine perspective) | Gitignored; personal; MUST NOT influence compiled output shipped to other machines. Values are only visible in local `--explain` runs and are not embedded in the compiled `SKILL.md` artifact itself. |

### Central Layer Trust

| Layer | Trust level | Rationale |
|---|---|---|
| `base_team` | Installer-owned | Written by `npm install`; committed. |
| `base_user` | Installer-owned, personal | Written by `npm install`; gitignored — captures local install answers. |
| `custom_team` | Human-authored, committed | Team overrides; committed to version control. |
| `custom_user` | Human-authored, gitignored | Personal overrides; gitignored. |

### Override-Root Containment

`engine.py` enforces that a caller-supplied `override_root` resolves within the project
tree via `io.ensure_within_root(override_root, scenario_root)` (engine.py line 171).
A path-traversal attack via a caller-supplied `override_root` is blocked.

The default `_bmad/custom/` derivation (when no `override_root` is passed) is derived
directly from `scenario_root` (already validated upstream) by appending a fixed literal
subpath — there is no attacker-influenced component in the default derivation, so it is
intentionally exempt from re-validation. The check is applied at the only boundary where
untrusted input can enter the path.

### Central Config is Process-Global

`resolve_config.py` merges the 4 central files once per engine invocation. Its output is
shared across all skills compiled in that run. A malicious `_bmad/custom/config.user.toml`
could inject values into all skills in the same compile run. However, the per-skill layer
precedence principle (§8-Tier Cascade) means it cannot override paths the skill's own
`customize.toml` already declares — per-skill tier 4 outranks central tier 5.

---

## Sigil Handling

Two sigil namespaces exist in the BMAD pipeline. They are **mutually exclusive by design**:

### `{{self.X}}` — Compile-time sigil (v6.6.0 compiler)

Resolved at compile time by `engine.py` + `resolver.py`. The engine calls
`resolver.VariableScope.build()` with the merged per-skill TOML layer stack; the result
is a `VariableScope._table` mapping flattened dotted keys to their values. During
fragment resolution, `resolver.py` substitutes each `{{self.dotted.path}}` reference via
dotted-path lookup in that table.

`{{self.X}}` may appear in any file processed by the compiler — templates and fragments.

### `{{.X}}` — Upstream prototype sigil (render.py, JIT renderer)

Resolved at skill-entry time by `render.py` in `upstream/feat/quick-dev-python-config`,
using the simplified 4-layer central config merge. This sigil is rejected by the TPL-01
lint rule (Story 7.20) when found in template `.md` files.

Mixing `{{self.X}}` and `{{.X}}` in a template is a bug — they serve different pipelines
and are not interoperable.

### TPL-01 Enforcement Scope

The TPL-01 lint rule enforces that `{{.X}}` (upstream sigil) does not appear in `.md`
files whose basename matches `/template/i`. Non-template-named `.md` files are not
scanned — a `workflow.md` containing `{{.command}}` produces zero TPL-01 findings
(Story 7.20 AC-3 Case 4).

---

## Public API

Only `merge_layers` and `load_toml_file` are public. All other symbols (`_deep_merge`,
`_keyed_field`, `_is_valid_keyed_value`) are private.

### `merge_layers(*layers: dict[str, Any]) -> dict[str, Any]`

- `*layers`: zero or more dicts; left = lowest priority, right = highest priority.
- Returns a **new** merged dict. Does NOT mutate inputs — deep-copy guarantee per
  Story 5.5b AC-7.
- Raises `TypeError` (with layer index in message) if any layer is not a `dict`.
  Empty `{}` layers are valid no-ops.
- May raise `UnknownDirectiveError` (see §Error Taxonomy) if AoT merge invariants are
  violated: `DUPLICATE_KEYED_ARRAY`, `MIXED_AOT_SHAPE`, `MIXED_KEY_FIELDS`,
  `UNHASHABLE_KEYED_VALUE`.

### `load_toml_file(path: str) -> dict[str, Any]`

- Returns `{}` if the file does not exist.
- Returns `{}` on TOCTOU race (file removed between `is_file` and `read_bytes`).
- Strips UTF-8 BOM via `decode("utf-8-sig")` plus a `while` loop for multiple BOMs
  (Story 7.13 AC-B). UTF-16 BOM is **not handled** — raises uncaught `UnicodeDecodeError`
  (known gap, `deferred-work.md` DN-α-KEEP).
- Raises `UnknownDirectiveError` (desc prefix `"TOML parse error in '{path}'"`) on
  `tomllib.TOMLDecodeError`, including file path, line, and column.

`load_toml_file` is used by the per-skill stack only. The central config stack
(`resolve_config.py`) has its own `load_toml()` with different error semantics.

---

## Existing Test Coverage

`test/python/test_toml_merge.py` is the behavioral regression spec for `toml_merge.py`.
Do not add new tests for behavior already covered here — Story 5.5b and 3.2 provide
comprehensive coverage.

**Story 3.2 coverage (ACs 1–5):**
- 3-layer cascade priority (defaults < team < user)
- AoT merge-by-key (`code` and `id`)
- `contributing-paths` provenance in `--explain` output
- Per-skill override paths

**Story 5.5b coverage (ACs 6–10):**
- Deep-copy correctness — post-merge mutation of inputs does not corrupt the result
- TOCTOU recovery (AC-8)
- UTF-8 BOM strip (AC-8)
- Non-dict layer `TypeError` (AC-7)
- Empty `{}` layer no-op (AC-7)
- `DUPLICATE_KEYED_ARRAY` error (AC-6)
- `MIXED_AOT_SHAPE` error (AC-6)
- `MIXED_KEY_FIELDS` error (AC-9)
- `UNHASHABLE_KEYED_VALUE` error (AC-10)

---

## Cross-References

| Resource | Purpose |
|---|---|
| `src/scripts/bmad_compile/toml_merge.py` | Primary implementation — merge engine and TOML file loader |
| `src/scripts/resolve_config.py` | Central 4-layer config caller — reads the 4 central config files and calls `merge_layers` |
| `src/scripts/bmad_compile/engine.py` lines 327–342 | Per-skill layer stack construction loop |
| `src/scripts/bmad_compile/resolver.py` `VariableScope.build()` | Integrates merged per-skill TOML into the compile-time variable resolver |
| `proposals/bmad-skill-compiler-architecture.md` §Decision 17 | Architecture ADR — source of merge rules and 8-tier cascade design |
| `docs/compile/explain-vocabulary.md` | `toml-layer` / `contributing-paths` provenance attributes in `--explain` output |
| `docs/compile/bmad-customize-walkthrough.md` | User-facing guide for the per-skill override layers |
| Story 5.5b spec | Hardening accumulator — AoT edge cases, BOM, TOCTOU, deep-copy guarantee |
| Story 3.2 spec | Original TOML structured overrides implementation |
