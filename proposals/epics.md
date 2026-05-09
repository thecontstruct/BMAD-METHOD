---
stepsCompleted: [step-01-validate-prerequisites, step-02-design-epics, step-03-create-stories, step-04-final-validation]
inputDocuments:
  - BMAD-METHOD/proposals/bmad-skill-compiler-prd.md
  - BMAD-METHOD/proposals/bmad-skill-compiler-architecture.md
---

# BMAD Compiled Skills - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for BMAD Compiled Skills, decomposing the requirements from the PRD and Architecture into implementable stories. No UX design document exists — the product is a CLI + template-authoring system with no UI surface.

## FR Numbering Cross-Reference (PRD ↔ Epics)

**This document uses a sequential FR1–FR59 scheme.** The PRD uses FR1–FR58 plus the amendment-inserted FR13a. Both schemes cover the same 59 requirements with identical semantic content. When citing FRs in tickets, commits, PR descriptions, or error messages (e.g., `PRECEDENCE_UNDEFINED`), use the **epics scheme (FR1–FR59)** — this document is the authoritative numbering for implementation. Use the table below to look up PRD references.

| Range | PRD scheme | Epics scheme | Relationship |
|---|---|---|---|
| FR1–FR13 | FR1–FR13 | FR1–FR13 | Identical |
| TOML structured override | FR13a | FR14 | PRD v1.2 amendment insertion → promoted to full number in epics |
| FR14–FR58 (PRD) | FR14–FR58 | FR15–FR59 | Shifted by +1 |

**Lookup examples:**
- PRD "FR39 (dogfood)" → Epics FR40.
- PRD "FR54 (no-disk-write contract)" → Epics FR55.
- Epics "FR59 (lazy compile-on-entry)" → PRD FR58.

## Requirements Inventory

### Functional Requirements

**Template Authoring (FR1–7)**

FR1: Skill Author can write a skill source file with the suffix `*.template.md` sibling to the installed `SKILL.md`.
FR2: Skill Author can include another template file by path using `<<include path="...">>`.
FR3: Skill Author can pass local props to an included fragment via additional attributes on the `<<include>>` directive.
FR4: Skill Author can declare a compile-time variable with `{{var_name}}` that will be resolved by the compiler before the skill is written to the install location.
FR5: Skill Author can leave a runtime placeholder with `{var_name}` that passes through to the compiled output verbatim, for the model to resolve.
FR6: Skill Author can author IDE-variant fragments using dotted suffixes (e.g., `persona-guard.cursor.template.md`) that are selected based on the target IDE at compile time, with a universal variant always available as a fallback.
FR7: Skill Author receives a compile-time error (not a silent pass-through) for any unknown directive, unresolved `{{var}}`, missing include path, or cyclic include, with a message that identifies the template file and line.

**Fragment Composition & Resolution (FR8–12)**

FR8: Installer can resolve `<<include path="...">>` recursively, combining fragments into a single compiled Markdown output.
FR9: Installer can resolve `{{var_name}}` against a layered configuration and emit the value into compiled output.
FR10: Installer enforces a documented fragment-resolution precedence: `user-full-skill` > `user-module-fragment` > `user-override` > `variant` > `base`.
FR11: Installer can detect and reject cyclic include chains at compile time.
FR12: Installer produces byte-for-byte reproducible output given identical source, overrides, configuration, and target IDE.

**Override Management (FR13–18)**

FR13: End User can create a prose fragment override by placing a file under `_bmad/custom/fragments/<module>/<skill>/<name>.template.md`. Compiler applies it per FR10 precedence.
FR14: End User can create a TOML structured override for any field of a skill's `customize.toml` via sparse `_bmad/custom/<skill>.user.toml` (personal, gitignored) or `_bmad/custom/<skill>.toml` (team, committable); compiler merges defaults → team → user at compile time.
FR15: End User can override a full skill by placing a complete `SKILL.md` (or `*.template.md`) at the corresponding path under the override root. Full-skill replacement is an escape hatch.
FR16: End User can override a YAML compile-time variable value by setting it in a user configuration file under the override root — the `user-config` tier of the non-`self.` cascade.
FR17: Compiler applies overrides according to the two parallel precedence cascades (one for `self.*` TOML-sourced names, one for non-`self.` YAML-sourced names) and records the resolution outcome in `bmad.lock` for every variable and every fragment.
FR18: Module Author cannot silently override a core fragment or a core-declared TOML field at install time; only the End User can register overrides of core behavior. Namespace collisions are rejected at install time.

**Installation & Upgrade (FR19–25)**

FR19: End User can run `bmad install` to perform a fresh install or a re-install into a target directory.
FR20: `bmad install` detects an existing install (via presence of `bmad.lock`) and auto-routes to `bmad upgrade --dry-run` followed by interactive confirmation.
FR21: Installer preserves the verbatim-copy install path for any skill directory that has no `*.template.md` source (backward compatibility for unmigrated skills).
FR22: End User can run `bmad upgrade --dry-run` to preview impact across every tracked input: prose fragments, TOML defaults, TOML orphans, new TOML defaults, glob match-sets, variable provenance; `--json` emits structured report consumable by `bmad-customize`.
FR23: End User can run `bmad upgrade` to apply a version bump; command halts with non-zero exit if drift detected and `--yes` not passed, pointing user to `bmad-customize`.
FR24: Drift triage in v1 happens through the `bmad-customize` skill (FR57), not a standalone CLI subcommand. Prose drift → three-way merge UX; TOML drift → field-level review; glob drift → informational unless intersecting overridden field.
FR25: All install/upgrade subcommands accept `--directory`, `--modules`, `--tools`, `--override-root`, `--yes`, `--debug`. `--lock-timeout-seconds <N>` (default 300s) tunes advisory-lock timeout.

**Compile Primitives (FR26–34)**

FR26: Power User or CI can run `bmad compile <skill>` to recompile a single skill from its template source plus applied overrides, writing compiled `SKILL.md` to the install location.
FR27: `bmad compile <skill> --diff` emits a unified diff of newly compiled output against the currently installed file without writing changes. ANSI-colorized on TTY, plain when piped.
FR28: `bmad compile <skill> --explain` produces annotated provenance view; default format is Markdown with inline XML tags (`<Include>`, `<Variable>`).
FR29: `--explain --tree` renders only the fragment dependency tree without content.
FR30: `--explain --json` emits machine-readable structured representation for editor tooling and `bmad-customize`.
FR31: `<Include>` tags carry attributes for `src`, `resolved-from` (one of `base`, `variant`, `user-override`, `user-module-fragment`, `user-full-skill`), `hash`, and when applicable `base-hash`, `override-hash`, `override-path`, `variant`.
FR32: `<Variable>` tags carry attributes for `name`, `source` (one of `install-flag`, `user-config`, `module-config`, `bmad-config`, `toml`, `derived`), `resolved-at`, and optionally `source-path`, `toml-layer`, `contributing-paths`, `base-source-path`, `declared-by`, `template-from`. `<TomlGlobExpansion>` tags wrap `file:`-prefixed TOML-array expansions.
FR33: Runtime placeholders (`{var_name}`) emitted unchanged by `--explain` so output previews what the model will actually receive.
FR34: `bmad compile` performs no LLM reasoning; given identical inputs it produces identical outputs and is safe for CI.

**Customization Skill (FR35–40, FR55, FR57)**

FR35: End User can invoke `bmad-customize` skill from an IDE chat (Claude Code or Cursor) with a natural-language customization intent.
FR36: The `bmad-customize` skill discovers the full customization surface by calling `bmad compile --explain --json`, returning: structured TOML fields + defaults + currently-resolved values + per-field provenance, prose fragments with resolved-from tier + active content, and variables with tier + source-path + declared-by provenance.
FR37: The `bmad-customize` skill identifies which plane (TOML structured field / prose fragment / YAML variable / full-skill replacement) the intent maps to, and negotiates the target with the user before writing. Ambiguous intent → asks first.
FR38: The `bmad-customize` skill drafts override content conversationally in chat, starting from active content and incorporating intent. Draft shown to user as text inside conversation. No file is written during drafting.
FR39: After user accepts a draft, the skill writes to the correct file (per FR37 routing) and invokes `bmad compile <skill> --diff` to surface compiled-SKILL.md impact as final verification.
FR40: The `bmad-customize` skill is itself authored as `SKILL.template.md` + fragments + `customize.toml` and compiled by the same pipeline (dogfood reference).
FR55: No override content is written to any path under `_bmad/custom/` during drafting. Drafts exist only as conversational text. Override root modified strictly on explicit user acceptance, only at final override path (never staging subdirectory). Contract applies to all draft states and all planes.
FR57: When invoked with drift-triage intent (explicitly or automatically per FR58), `bmad-customize` consumes `bmad upgrade --dry-run --json` and walks user through each drift entry. Per-entry UX: prose drift → three-way merge (keep/adopt/author-merged); TOML default-value drift → keep/adopt/rewrite; TOML orphan → notify + offer remove; TOML new-default → informational; glob-input drift → informational. Writes follow FR55. Post-accept, re-run `bmad upgrade`.

**Drift Detection & Lockfile (FR41–44)**

FR41: Compiler writes `_bmad/_config/bmad.lock` on every compile, recording per skill: source template hash, every resolved fragment with `resolved_from` tier + hashes + lineage, TOML customization block (defaults_hash, per-layer override hashes, per-field `overridden_paths` entries), every variable with source + path + layer + contributing-paths + declared-by + template-from + value_hash, every glob input with pattern + resolved_pattern + source + match_set + match_set_hash, the selected IDE variant, and the compiled output hash.
FR42: `bmad upgrade --dry-run` reports drift across every tracked input category: prose fragment drift, TOML default-value drift, TOML orphan drift, TOML new-default awareness, glob-input drift, variable provenance drift. `--json` emits structured report.
FR43: `bmad.lock` maintains append-only `lineage` array per overridden fragment and per TOML-overridden field, capturing `{bmad_version, base_hash, override_hash}` at each upgrade for forward-compat `bmad upgrade --rollback` (v1 doesn't implement rollback).
FR44: Lockfile stores only `value_hash` for variable values (never plaintext), and only hashes (not contents) for globbed files.

**IDE Variants (FR45–47)**

FR45: Installer can select a Claude Code variant for any fragment via `*.claudecode.template.md` naming; otherwise falls back to universal.
FR46: Installer can select a Cursor variant for any fragment via `*.cursor.template.md` naming; otherwise falls back to universal.
FR47: Installer records the selected variant for each skill in `bmad.lock`.

**Module Distribution (FR48–49)**

FR48: Module Author can ship a module in Model 1 (precompiled Markdown only), Model 2 (template source only), or Model 3 (source + precompiled fallback); installer accepts all three without user-visible differences.
FR49: Module Author can reference core fragments from module skill templates via explicit namespace (e.g., `<<include path="core/persona-guard.template.md">>`).

**Validation & CI (FR50–54, FR56, FR58–59)**

FR50: CI can run `npm run validate:compile` to recompile all templated skills and compare against `bmad.lock`; any divergence fails the build.
FR51: CI can run `npm run validate:skills` to assert every compiled skill passes schema validation after compilation.
FR52: Installer exits non-zero with user-facing error when any FR7 error condition occurs during a compile.
FR53: CI runs end-to-end integration test covering full customization lifecycle: fresh `bmad install` → `bmad-customize` scaffolds override → `bmad compile --diff` accepted → `bmad upgrade --dry-run` shows drift after upstream change → `bmad upgrade` halts → manual override edit resolves drift → `bmad upgrade` succeeds → `bmad.lock` records lineage. Pipeline failure fails build.
FR54: CI matrix includes Model 3 (source + precompiled fallback) distribution test: install module in compiler-present and compiler-absent environments; assert equivalent output.
FR56: CI runs abandoned-session test: fresh install → `bmad-customize` opens drafting session → session abandoned before acceptance → assert no new files under `_bmad/custom/` and `bmad.lock` byte-identical to pre-session state. Pipeline failure fails build.
FR58: `bmad upgrade` exits non-zero with clear message pointing to `bmad-customize` when drift detected and `--yes` not passed. Message format: "Drift detected in N skills (M prose fragments, P TOML fields, Q glob inputs). Invoke 'bmad-customize' skill in your IDE chat..." `--yes` is escape hatch for scripted CI.
FR59: At skill entry, cache-coherence guard (installed by SKILL.md shim) hashes every tracked input against corresponding `bmad.lock` entry. If any hash differs — or glob match-set changed, or tracked file missing — guard invokes same compile engine as build-time `bmad compile <skill>`. Guard performs no template rendering of its own; pure conditional-recompile wrapper. All hashes match → on-disk SKILL.md served unchanged (fast path).

### NonFunctional Requirements

**Performance**

NFR-P1: Install-time overhead ≤ 110% of pre-compiler install time on reference install; re-installs amortize to ≤ 5% overhead with hash-based skip.
NFR-P2: Per-skill recompile (`bmad compile <skill>`) completes in ≤ 500 ms wall-clock on mid-2021 laptop for skill with up to 10 fragments, 3 TOML layers, ≤ 20 file-glob matches totalling ≤ 500 KB (including ~50ms Python startup).
NFR-P3: Dry-run responsiveness (`bmad upgrade --dry-run`) on full install with ≤ 50 migrated skills completes in ≤ 3 seconds with streamed output (first drift item within 500 ms).
NFR-P4: `bmad-customize` interactive latency — each step returns within IDE skill-turn budget; no discovery path requires > 2 `bmad compile --explain --json` invocations per user turn; drift-triage sessions invoke `bmad upgrade --dry-run --json` at most once per session.
NFR-P5: Lazy compile-on-entry cache-coherence guard fast path (all hashes match) completes in ≤ 50 ms on mid-2021 laptop for skill with ≤ 20 tracked inputs; slow path within NFR-P2's 500 ms envelope.

**Security**

NFR-S1: No plaintext secrets in lockfile — stores only `value_hash` (SHA-256) for variable values and only hashes (not contents) for globbed files.
NFR-S2: Override root and glob containment — reads overrides only from configured `override_root` (default `_bmad/custom/`); paths escaping root via `..` or symlinks rejected with compile-time error; `file:` glob patterns must resolve inside `{project-root}`.
NFR-S3: Module boundary enforcement — third-party modules cannot register overrides of core fragments or core-declared TOML fields; namespace collisions rejected at install time.
NFR-S4: Trust gate for advanced layers — future non-stdlib Python extensions require `compiler.trust_mode: full`; v1 uses only Python stdlib.
NFR-S5: No network access during compile — v1 engine performs zero network I/O.
NFR-S6: Supply-chain hygiene — introduces no new runtime dependencies beyond Python 3.11+ stdlib; Node deps unchanged.

**Reliability & Determinism**

NFR-R1: Byte-for-byte reproducibility across macOS, Linux, Windows given identical inputs.
NFR-R2: Deterministic resolution order — precedence tier first (per FR10), then alphabetical by POSIX path within tier; TOML merge deterministic per documented rules; glob expansion sorts matches alphabetically.
NFR-R3: Line-ending normalization — compiled output uses LF on all platforms; compiler normalizes at read time.
NFR-R4: Compile errors are terminal, not silent — any error produces non-zero exit, user-facing message, no partial write; lazy-compile guard propagates errors.
NFR-R5: Lockfile integrity and lazy-compile coherence — malformed `bmad.lock` → CLI refuses to proceed and instructs user to run `bmad install` fresh; user-overrides-present → prompt before destructive action.

**Compatibility**

NFR-C1: Runs on Node.js ≥ 20.0.0 and Python ≥ 3.11.0; both already required by upstream.
NFR-C2: Officially supported OSes: macOS (Intel + Apple Silicon), Linux (x86_64 + ARM64), Windows 10/11; CI Linux runs every PR, all six OS/arch combos on merge-to-main, nightly, release-tag.
NFR-C3: Officially supported IDEs: Claude Code, Cursor; universal fallback works for any IDE consuming `SKILL.md`.
NFR-C4: Unmigrated skills install byte-for-byte identically to pre-compiler behavior (same output, permissions, install time).
NFR-C5: Lockfile schema declares `version: 1`; readers must handle or fail clearly; never silently read newer version as v1; unknown additive fields round-tripped unchanged.

**Observability**

NFR-O1: Lockfile as audit trail — every compile writes or updates `bmad.lock`; single source of truth for "what was installed, why, and from where."
NFR-O2: `--explain` provides full provenance — every non-literal chunk rendered with its origin; no silent interpolations or merges.
NFR-O3: Error messages name file and line — every compile-time error references template file and line number of offending directive.
NFR-O4: Dry-run outputs are diffable and scriptable — `bmad upgrade --dry-run` output is structured (plain-text default, `--json` alternate).
NFR-O5: `--debug` flag emits resolution trace (fragments considered, variants rejected, overrides applied) to stderr only.

**Maintainability**

NFR-M1: Syntax surface frozen for v1 — four authoring constructs; adding fifth requires major-version bump; enforced by test asserting any unknown directive produces compile-time error.
NFR-M2: Test coverage for resolution tiers — unit tests cover every adjacent pair of fragment tiers and every adjacent pair of variable tiers in both namespaces; TOML merge has own test matrix; glob-input drift has contract tests.
NFR-M3: Documentation is a ship gate — author migration guide, `bmad-customize` walkthrough, `bmad.lock` schema reference, `--explain` tag vocabulary, 5-minute quickstart must be present and reviewed in release PR.
NFR-M4: Reference skills stay in sync — 3–5 migrated canonical skills treated as contract tests; CI recompiles each and diffs against checked-in baseline.
NFR-M5: Error-message vocabulary stable — `UNKNOWN_DIRECTIVE`, `UNRESOLVED_VARIABLE`, `MISSING_FRAGMENT`, `CYCLIC_INCLUDE`, `OVERRIDE_OUTSIDE_ROOT`, `LOCKFILE_VERSION_MISMATCH`, `PRECEDENCE_UNDEFINED` are public contract; names and semantics frozen within v1.

### Additional Requirements

**Bootstrap / First Story (Architecture-Prescribed)**

- First implementation story is template parser + smoke-test compile of one reference skill (likely `bmad-help` — smallest surface, single `{{var}}` interpolation), producing byte-identical output to current `bmad-help/SKILL.md` to prove the "keep contract" step.
- Foundation implementation sequence: Decision 1 (parser), Decision 10 (I/O sandbox — `io.py`), Decision 11 (error classes — `errors.py`), Decision 17 (shared library skeleton — `toml_merge.py`).
- Migrated skill set (3–5 canonical reference skills) must be chosen for high visible duplication before general release (candidates: `bmad-agent-pm`, `bmad-agent-architect`, `bmad-help`, `bmad-customize`).

**Infrastructure / Deployment**

- Python compile library lives at `src/scripts/bmad_compile/` with 10 modules: `parser.py`, `resolver.py`, `toml_merge.py`, `variants.py`, `io.py`, `errors.py`, `lockfile.py`, `explain.py`, `engine.py`, `lazy_compile.py`.
- Build-time entry point: `src/scripts/compile.py` invoked as `python3 src/scripts/compile.py --skill <id> [flags]`.
- Node CLI adapters live at `tools/installer/commands/{install,upgrade,compile}.js` with shared subprocess helper `tools/installer/compiler/invoke-python.js`.
- Batch-mode compilation: `python3 compile.py --batch <skills.json>` collapses cold-start overhead to single interpreter load for N skills.
- Lazy-compile entry point: `python3 -m bmad_compile.lazy_compile <skill>` invoked by SKILL.md shim at skill entry.
- New validation target `npm run validate:compile` recompiles all templated skills and diffs against `bmad.lock`; CI gate.
- Hard check at installer start: `python3 --version ≥ 3.11`; abort install with clear message if absent or outdated.

**External Dependencies (Upstream — Informational)**

> All external upstream dependencies are reported as **already merged** per the architecture doc — verify at sprint kickoff as a sanity check.
- Upstream PR #2284 (TOML customization system) — merged.
- Upstream PR #2285 (central `config.toml`, `bmad-skill-manifest.yaml` removal, commit 4405b817) — merged.
- Upstream PR #2287 (17 bmm-skills switched to `customize.toml` + `workflow.md` deletion, commit ffdd9bc6) — merged.
- Upstream `a6d075bd` (fs-native.js replacing fs-extra) — merged.
- Upstream `b0d70766` (SKILL.md stdout-dispatch shim) — merged.
- Upstream `bf30b697` (at-skill-entry renderer) — refactored to call `lazy_compile.py` instead.
- Upstream `8fb22b1a` (`_bmad/custom/` provisioning) — merged.
- Upstream `resolve_customization.py` and `resolve_config.py` to be refactored in coordination to import from shared `bmad_compile.toml_merge`.

**Integration**

- Compiler hook into `installer._installAndConfigure()` between `OfficialModules.install()` (copies module files) and `ManifestGenerator.generateManifests()` (scans `SKILL.md`).
- Node installer invokes `python3 src/scripts/compile.py --install-phase --install-dir <bmadDir> [--skill <id>]` for each migrated skill after file copy.
- Per-migrated-skill: Node passes only paths/IDs to Python; Python reads inputs from disk via `bmad_compile/io.py`.
- Installer detects migration via presence of `*.template.md` in copied install-location tree; non-migrated skills follow verbatim-copy path unchanged.
- Python compiler returns structured JSON to Node; Node merges into existing `installedFiles` set callback for manifest generator.
- Templates (`*.template.md`) deleted from install location post-compile; `customize.toml` preserved (lazy-compile guard needs it).
- Upstream `resolve_customization.py` (per-skill TOML merge) and `resolve_config.py` (four-layer central TOML merge) refactored to consume shared `bmad_compile.toml_merge`.
- SKILL.md shim updated to invoke `lazy_compile.py` instead of upstream's runtime renderer; `{var}` substitution behavior removed (migrate to `{{var}}` / `{{self.*}}`).

**Data Migration / Setup**

- `bmad.lock` schema v1 written at `_bmad/_config/bmad.lock` on every compile (build-time or lazy).
- Four-layer central TOML structure (PR #2285): `_bmad/config.toml`, `_bmad/config.user.toml`, `_bmad/custom/config.toml`, `_bmad/custom/config.user.toml`.
- Override root `_bmad/custom/` provisioned at install time with git-ignore stub for `*.user.toml` and `fragments/**/*.user.*`.
- Migration of `{var}` → `{{var}}` / `{{self.*}}` in migrated-agent set must be coordinated with refactor PR.

**API Versioning**

- Lockfile schema v1 with `version` field; future breaking changes require version bump; additive optional fields do not.
- `--explain` JSON output has `schema_version: 1` at document root; renaming/removing fields requires major bump.
- `upgrade --dry-run --json` follows same policy.
- Unknown additive fields in v1 lockfile round-tripped unchanged by mechanical rewriters (forward compatibility).

**Security Implementation**

- All compile-time filesystem + hashing + time I/O routed through `bmad_compile/io.py` — sole determinism and filesystem boundary.
- Override root containment: rejects paths escaping `_bmad/custom/` via `..` or symlinks; error `OVERRIDE_OUTSIDE_ROOT`.
- Glob containment: `file:` patterns resolve only within `{project-root}`; symlinked matches pointing outside rejected at read time.
- Module boundary: modules cannot shadow core fragments or core-declared TOML fields; collisions rejected at install time.
- `trust_mode: safe` (default) uses only stdlib; `trust_mode: full` gated for future non-stdlib extensions.
- `tomllib` (stdlib) for TOML parsing — no arbitrary code execution path; no schema-driven extension loader in v1.

**Monitoring & Logging**

- `--debug` flag on any subcommand emits resolution trace to stderr only (never stdout).
- `--explain` default format: Markdown with inline XML provenance tags (`<Include>`, `<Variable>`, `<TomlGlobExpansion>`, `<TomlGlobMatch>`).
- Python outputs structured JSON to stdout (compile results, `--diff`, `--explain --json`); stderr carries diagnostics, progress, errors.

**Coordination / Release Gates**

- Refactoring `resolve_customization.py` and `resolve_config.py` to import from `bmad_compile.toml_merge` is a coordinated upstream change; PR must land both at once to avoid divergent TOML merge implementations.
- Lazy-compile guard integration requires coordination with SKILL.md shim owner to update shim to invoke `lazy_compile.py` instead of runtime renderer.
- `bmad-customize` skill is authored as `*.template.md` + fragments (dogfood loop); compiler must not have regressions before skill ships (release gate).
- Module distribution detection (Model 1/2/3) requires coordination with module authors; one third-party dogfood migration with core team before general release.

### UX Design Requirements

_Not applicable — no UI surface. The product is a CLI + template-authoring system. IDE-chat interactions with `bmad-customize` are captured in FR35–40, FR55, FR57._

### FR Coverage Map

FR1: Epic 1 — Template authoring syntax (`*.template.md`)
FR2: Epic 1 — `<<include>>` directive
FR3: Epic 1 — Include props
FR4: Epic 1 — `{{var}}` compile-time variable
FR5: Epic 1 — `{var}` runtime passthrough
FR6: Epic 1 — IDE-variant authoring suffixes
FR7: Epic 1 — Compile-time errors with file+line
FR8: Epic 1 — Recursive include resolution
FR9: Epic 1 — Variable interpolation against layered config
FR10: Epic 1 — Fragment precedence cascade
FR11: Epic 1 — Cyclic-include detection
FR12: Epic 1 — Byte-reproducible output
FR13: Epic 3 — Prose fragment override
FR14: Epic 3 — TOML structured override
FR15: Epic 3 — Full-skill override escape hatch
FR16: Epic 3 — YAML variable override
FR17: Epic 3 — Two parallel precedence cascades recorded in lockfile
FR18: Epic 3 — Module-boundary enforcement (no silent core shadowing)
FR19: Epic 2 — `bmad install` fresh/reinstall
FR20: Epic 5 — Install auto-routes to upgrade when existing install detected
FR21: Epic 2 — Verbatim-copy path for unmigrated skills
FR22: Epic 5 — `bmad upgrade --dry-run` with `--json`
FR23: Epic 5 — `bmad upgrade` halt-on-drift
FR24: Epic 5 — Drift triage via `bmad-customize` (primitive side)
FR25: Epic 5 — Shared install/upgrade flags
FR26: Epic 4 — `bmad compile <skill>`
FR27: Epic 4 — `--diff` unified diff
FR28: Epic 4 — `--explain` Markdown+XML
FR29: Epic 4 — `--explain --tree`
FR30: Epic 4 — `--explain --json`
FR31: Epic 4 — `<Include>` tag attributes
FR32: Epic 4 — `<Variable>` tag attributes + `<TomlGlobExpansion>`
FR33: Epic 4 — `{var}` passthrough in `--explain`
FR34: Epic 4 — Deterministic `bmad compile` (no LLM)
FR35: Epic 6 — Invoke `bmad-customize` from IDE chat
FR36: Epic 6 — Discovery via `--explain --json`
FR37: Epic 6 — Plane routing + negotiation
FR38: Epic 6 — Conversational drafting (no disk write)
FR39: Epic 6 — Post-accept write + `--diff` verification
FR40: Epic 6 — `bmad-customize` dogfood (authored as template)
FR41: Epic 1 — `bmad.lock` per-skill entry schema v1
FR42: Epic 5 — Drift report across all tracked categories
FR43: Epic 5 — Append-only lineage (rollback forward-compat)
FR44: Epic 1 — Lockfile stores only value hashes (no plaintext secrets)
FR45: Epic 1 — Claude Code variant selection
FR46: Epic 1 — Cursor variant selection
FR47: Epic 1 — Variant recorded in lockfile
FR48: Epic 7 — Module distribution Models 1/2/3 (Story 7.6)
FR49: Epic 7 — Core-fragment namespace reference (Story 7.6)
FR50: Epic 7 — `npm run validate:compile` + `validate:skills`
FR51: Epic 7 — `npm run validate:skills`
FR52: Epic 2 — Installer exits non-zero on FR7 errors
FR53: Epic 7 — E2E customization lifecycle test
FR54: Epic 7 — Model 3 distribution CI matrix test
FR55: Epic 6 — No-disk-write-until-accept contract
FR56: Epic 7 — Abandoned-session CI test
FR57: Epic 6 — Drift triage UX (prose three-way merge + TOML field-level)
FR58: Epic 5 — Halt-on-drift message + `--yes` escape hatch
FR59: Epic 5 — Lazy-compile-on-entry cache-coherence guard

**NFR Coverage (cross-cutting, attached to primary-owning epic):**

Performance: NFR-P1 (Epic 1), NFR-P2 (Epic 4), NFR-P3 (Epic 5), NFR-P4 (Epic 6), NFR-P5 (Epic 5)
Security: NFR-S1 (Epic 1), NFR-S2 (Epic 3), NFR-S3 (Epic 3), NFR-S4 (Epic 1), NFR-S5 (Epic 1), NFR-S6 (Epic 1)
Reliability: NFR-R1 (Epic 2), NFR-R2 (Epic 1), NFR-R3 (Epic 1), NFR-R4 (Epic 1), NFR-R5 (Epic 5)
Compatibility: NFR-C1 (Epic 2), NFR-C2 (Epic 2), NFR-C3 (Epic 1 variants), NFR-C4 (Epic 2 verbatim path), NFR-C5 (Epic 1 lockfile version gate)
Observability: NFR-O1 (Epic 1), NFR-O2 (Epic 4), NFR-O3 (Epic 1), NFR-O4 (Epic 5), NFR-O5 (Epic 5)
Maintainability: NFR-M1 (Epic 1), NFR-M2 (Epic 7), NFR-M3 (Epic 7 docs gate), NFR-M4 (Epic 7 reference skills), NFR-M5 (Epic 1 error vocabulary)

## Epic List

### Epic 1: Compile Pipeline & Authoring Syntax

Skill authors (Maya) can write `*.template.md` sources with fragments, compile-time variables, runtime placeholders, and IDE variants, and invoke `bmad compile` locally against a directory to produce a compiled `SKILL.md` with a full-provenance lockfile. No installer integration yet — this epic delivers the compile engine as a library + CLI.

**User outcome:** Authors can iterate on templates locally with a working compiler. Authoring syntax is frozen. Error taxonomy is complete and actionable.

**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR9, FR10, FR11, FR12, FR41, FR44, FR45, FR46, FR47

**Primary NFRs:** NFR-S1, NFR-S4, NFR-S5, NFR-S6, NFR-R2, NFR-R3, NFR-R4, NFR-C3, NFR-C5, NFR-O1, NFR-O3, NFR-M1, NFR-M5, NFR-P1

**Implementation notes:** Arch-prescribed bootstrap: `errors.py` → `io.py` → `parser.py` → minimal `engine.py` → first golden fixture → `bmad compile` CLI smoke test. `io.py` is the SOLE filesystem/hash/time boundary, enforced by AST-layering test. Frozen 7-code error vocabulary with file+line+caret+remediation hints. Lockfile schema v1 with forward-compat additive-field round-trip. Variant selection (`variants.py`) ships alongside parser so Claude Code + Cursor variants compile from day 1.

### Epic 2: Install Integration & First Migrated Skill

Maintainers and end users get a `bmad install` that invokes the Python compiler between file-copy and manifest generation for migrated skills, and preserves the verbatim-copy path for unmigrated skills. `bmad-help` migrates as the first production skill with a byte-identical-output "keep contract" CI guarantee. Cross-OS determinism is enforced.

**User outcome:** Installs produce compiled output automatically. Unmigrated skills are byte-identical to pre-compiler behavior. The first real production skill ships as template source.

**FRs covered:** FR19, FR21, FR52

**Primary NFRs:** NFR-R1, NFR-C1, NFR-C2, NFR-C4

**Implementation notes:** Node adapter `install.js` hooks between `OfficialModules.install()` and `ManifestGenerator.generateManifests()`. `invoke-python.js` subprocess helper. Python 3.11+ hard check with actionable error message. Cross-OS CI matrix (macOS Intel + Apple Silicon, Linux x86_64 + ARM64, Windows 10/11) on merge/nightly/release; Linux-only on PR for speed.

### Epic 3: User Overrides Across Three Planes

End users (Diego, manual path) can override any prose fragment, TOML structured field, or YAML variable by placing files under `_bmad/custom/`. Compiler merges according to documented precedence cascades. Module-boundary enforcement blocks silent core-fragment shadowing. Override-root and glob containment reject path-escape attempts.

**User outcome:** Customization via manual file edits works across all three planes. Re-install picks up overrides automatically. Third-party modules cannot stealth-shadow core behavior.

**FRs covered:** FR13, FR14, FR15, FR16, FR17, FR18

**Primary NFRs:** NFR-S2, NFR-S3

**Implementation notes:** `resolver.py` implements two parallel cascades — 5-tier YAML non-`self.*` and 8-tier TOML `self.*` (PR #2285 central TOML integrated). `toml_merge.py` shared library refactors upstream's `resolve_customization.py` + `resolve_config.py` to import from one source; lands as one coordinated PR. Path-escape and symlink-escape rejection in `io.py`. Full-skill escape hatch emits stderr warning about bypassing fragment-level upgrade safety.

### Epic 4: Compile Inspection Primitives (`bmad compile`)

Power users, authors, and tooling (including the future `bmad-customize` skill) can run `bmad compile <skill>` to recompile, `--diff` to preview changes without writing, `--explain` to render annotated provenance (Markdown / tree / JSON), and inspect every non-literal chunk's origin.

**User outcome:** Full observability of compile results. Diff-before-write workflow. Machine-readable provenance for editor tooling and downstream skills.

**FRs covered:** FR26, FR27, FR28, FR29, FR30, FR31, FR32, FR33, FR34

**Primary NFRs:** NFR-P2, NFR-O2

**Implementation notes:** `compile.js` Node adapter + `explain.py` formatter (Markdown/tree/JSON). `<Include>`, `<Variable>`, `<TomlGlobExpansion>`, `<TomlGlobMatch>` tag vocabulary. Runtime `{var}` passes through `--explain` so output previews the model's view. Deterministic by construction — no LLM, identical inputs = identical outputs.

### Epic 5: Upgrade, Drift & Lazy-Compile

End users (Diego, upgrade path) run `bmad upgrade --dry-run` to preview drift across six tracked-input categories, `bmad upgrade` halts non-zero when drift is detected (unless `--yes`), and SKILL.md is guaranteed fresh at skill entry via a lazy-compile cache-coherence guard. Install auto-routes to upgrade when an existing `bmad.lock` is present. Lineage is append-only for forward-compat rollback.

**User outcome:** Safe upgrades. No silent lost customizations. Fresh-at-entry guarantee means edits take effect immediately.

**FRs covered:** FR20, FR22, FR23, FR24, FR25, FR42, FR43, FR58, FR59

**Primary NFRs:** NFR-P3, NFR-P5, NFR-R5, NFR-O4, NFR-O5

**Implementation notes:** `upgrade.js` Node adapter. `lazy_compile.py` with advisory file-locks (`fcntl.flock` / `msvcrt.locking`). Lineage append in `lockfile.py`. SKILL.md shim (upstream commit `b0d70766`) updated to invoke `lazy_compile.py` instead of runtime renderer; `{var}` runtime substitution removed in favor of compile-time `{{var}}` / `{{self.*}}`. Batch-mode compilation for install-time perf (single Python cold-start for N skills). Three-way-merge-UX spike (2-day timebox) scheduled here before Epic 6 scope-locks.

### Epic 6: Interactive `bmad-customize` Skill

End users (Diego, ergonomic path) customize skills and triage upgrade drift through natural-language IDE chat — no manual disk edits, no silent losses. Skill dogfoods the compiler by being authored as `SKILL.template.md` + fragments + `customize.toml`.

**User outcome:** Conversational customization with plane routing, no-disk-write-until-accept contract, post-accept `--diff` verification, and guided drift triage (prose three-way merge, TOML field-level review, informational glob/new-default awareness).

**FRs covered:** FR35, FR36, FR37, FR38, FR39, FR40, FR55, FR57

**Primary NFRs:** NFR-P4

**Implementation notes:** `bmad-customize` authored as template source (dogfood); same compiler builds it. Discovery via `bmad compile --explain --json`; verification via `bmad compile --diff`. Drift triage consumes `bmad upgrade --dry-run --json`. Interactive latency budget: ≤ 2 `--explain --json` invocations per turn, ≤ 1 `--dry-run --json` per triage session. Three-way merge UX scope (v1 vs Phase 2) decided by Epic 5's spike.

### Epic 7: Validation, CI, Release Gates & Module Distribution

Every release passes automated quality gates — no regressions, no silent losses, all five required docs present. Dogfood-gate owner signs off that `bmad-customize` survives its own upgrade. Ship-gate success metric is either instrumented (telemetry-lite proxy) or explicitly downgraded to Phase 2 measurement. Module distribution models (1/2/3) ship with installer detection and third-party dogfood migration is a soft-gate at release.

**User outcome:** Users trust releases. Release-ready quality bar is observable and enforceable. Third-party module authors (Priya) can ship in any distribution model.

**FRs covered:** FR48, FR49, FR50, FR51, FR53, FR54, FR56

**Primary NFRs:** NFR-M2, NFR-M3, NFR-M4

**Implementation notes:** `npm run validate:compile` (recompile-all + lockfile diff) and `npm run validate:skills` (schema check) as PR gates. E2E customization lifecycle integration test (9-step flow). Model 3 distribution matrix (compiler-present vs compiler-absent). Abandoned-session test (enforces FR55). Docs gate: author migration guide, `bmad-customize` walkthrough, `bmad.lock` schema, `--explain` vocabulary, 5-minute quickstart — **Paige (Technical Writer)** is the designated reviewer. Dogfood-gate owner named in release PR. "25% override adoption" metric resolved (scope telemetry-lite proxy OR downgrade to Phase 2 measurement). Distribution detection (Models 1/2/3) in `install.js`. Third-party dogfood migration is **soft gate** — preferred complete before v1 release, but ship-blocking status waived; missing dogfood flagged in release notes as known gap.

---

**Delivery order:** Epic 1 → Epic 2 → Epic 3 → Epic 4 → Epic 5 → Epic 6 → Epic 7. After Epic 2, Epic 4 (inspection) and Epic 3 (overrides) can interleave. Epic 7 threads through from early on — distribution detection (7.6) ships alongside Epic 2's install hook; CI gates (7.1–7.4) added as each upstream capability ships; docs gate (7.5) locks before release; third-party dogfood (7.7) is soft gate preferred but not blocking.

---

## Epic 1: Compile Pipeline & Authoring Syntax

Skill authors can write `*.template.md` sources with fragments, compile-time variables, runtime placeholders, and IDE variants, and invoke `bmad compile` locally against a directory to produce a compiled `SKILL.md` with a full-provenance lockfile.

### Story 1.1: Bootstrap — Errors, I/O Boundary, Parser, Minimal Engine, CLI Smoke Test

As a compile-pipeline developer,
I want the foundational modules (`errors.py`, `io.py`, `parser.py`, a minimal `engine.py`), a golden-file fixture, and a `bmad compile` CLI smoke test,
So that subsequent stories build on a frozen error vocabulary, a single filesystem/hash/time boundary, and a verified end-to-end invocation path.

**Acceptance Criteria:**

**Given** a fresh checkout with no `src/scripts/bmad_compile/` package
**When** this story is complete
**Then** `errors.py` defines seven `CompilerError` subclasses keyed to codes `UNKNOWN_DIRECTIVE`, `UNRESOLVED_VARIABLE`, `MISSING_FRAGMENT`, `CYCLIC_INCLUDE`, `OVERRIDE_OUTSIDE_ROOT`, `LOCKFILE_VERSION_MISMATCH`, `PRECEDENCE_UNDEFINED`
**And** every error formats as `<CODE>: <relative-path>:<line>:<col>: <description>` with a caret span and a remediation hint
**And** an AST-layering test (CI-gated) rejects any upward import between modules in `bmad_compile/`

**Given** any read, hash, stat, or time call issued by the compiler
**When** the call is made
**Then** it is routed through `io.py` (verified by grep-test: no `pathlib`, `hashlib`, `time`, `os.path` imports outside `io.py`)
**And** paths normalize to POSIX, line endings normalize to LF at read time, SHA-256 hashes are computed in binary mode, directory listings sort alphabetically by POSIX path

**Given** a `*.template.md` source with only Markdown passthrough content
**When** `parser.py` tokenizes it
**Then** the AST is a single passthrough node whose content is byte-identical to input

**Given** a source containing the literal directive `<<foo>>`
**When** `parser.py` tokenizes it
**Then** a `CompilerError` with code `UNKNOWN_DIRECTIVE` is raised, formatted with file + line + col of the offending token

**Given** a fixture at `test/fixtures/bootstrap/minimal/` containing `input.template.md` and `expected.md`
**When** I run `python3 src/scripts/compile.py --skill test/fixtures/bootstrap/minimal --install-dir <tmp>`
**Then** `<tmp>/minimal/SKILL.md` is byte-identical to `expected.md`
**And** exit code is 0
**And** re-running against the same `--install-dir` is idempotent (overwrites cleanly, no stale artifacts)

**Given** the minimal `compile.py` shim
**When** invoked
**Then** it accepts exactly two flags via `argparse` — `--skill` (path, required) and `--install-dir` (path, required)
**And** it has no subcommands, no `--verbose`, no config loading, no plugin discovery
**And** it calls `io.read_template(args.skill)` → `parser.parse(...)` → writes single artifact + lockfile entry to `args.install_dir`
**And** it exits 0 on success, exits 1 on `FileNotFoundError`
**And** total implementation is ≤ 50 lines of Python (full CLI surface deferred to Epic 4)

> _Note: unknown-directive negative-path testing previously co-located here has moved to Story 1.4 (full error taxonomy)._

### Story 1.2: Fragment Resolution with Cycle Detection and Precedence Cascade

As a skill author,
I want `<<include path="...">>` to resolve recursively with deterministic precedence and cycle rejection,
So that I can compose skills from shared fragments without risk of infinite loops or surprising resolution order.

**Acceptance Criteria:**

**Given** a template containing `<<include path="fragments/a.template.md">>` and a fragment that includes `fragments/b.template.md`
**When** `resolver.py` resolves the template
**Then** the output has both fragments inlined in order and the resolver's dependency tree records the two-level include chain

**Given** a template that includes a fragment which in turn includes the template itself
**When** resolution is attempted
**Then** a `CompilerError` of code `CYCLIC_INCLUDE` is raised with the full cycle chain in the message (e.g., `a.template.md → b.template.md → a.template.md`)

**Given** the same fragment name exists at `user-full-skill`, `user-module-fragment`, `user-override`, `variant`, and `base` tiers
**When** the resolver chooses one
**Then** the `user-full-skill` version wins and `resolved_from` records `user-full-skill`
**And** removing the `user-full-skill` source causes `user-module-fragment` to win, and so on down the precedence ladder

**Given** two fragments at the same tier with different POSIX paths
**When** the resolver iterates the tier
**Then** the alphabetically-first POSIX path wins (verified by unit test fixture)

**Given** an `<<include>>` directive with additional attributes (e.g., `<<include path="..." heading-level="2">>`)
**When** parser tokenizes and resolver expands
**Then** the attributes are passed to the included fragment as local props available for variable interpolation within the fragment's scope only (not globally)

### Story 1.3: Compile-Time Variable Interpolation and Runtime Passthrough

As a skill author,
I want `{{var_name}}` resolved at compile time from layered config and `{var_name}` emitted verbatim for the model,
So that provenance is auditable and runtime placeholders survive the pipeline unchanged.

**Acceptance Criteria:**

**Given** a template containing `{{user_name}}` and a config where `user_name: Shado`
**When** `resolver.py` resolves variables
**Then** the compiled output contains `Shado` in place of `{{user_name}}`
**And** the resolver records `<Variable name="user_name" source="bmad-config" source_path="_bmad/core/config.yaml" value_hash="<sha256>">` in the provenance trace

**Given** a template containing `{var_name}` (single braces)
**When** the compiler runs
**Then** the literal string `{var_name}` passes through to compiled output unchanged

**Given** a template containing `{{unknown_var}}` with no matching config value
**When** the compiler runs
**Then** a `CompilerError` of code `UNRESOLVED_VARIABLE` is raised with file + line + caret pointing to the unresolved token
**And** the remediation hint lists available variable names in scope

**Given** a template containing `{{self.toml_field}}` and a `customize.toml` with that field defined
**When** the compiler runs
**Then** the value resolves from the TOML `self.*` namespace cascade, not the YAML non-`self.*` cascade
**And** provenance records `toml_layer` (one of `defaults`, `team`, `user`, `central-*`)

**Given** a template containing both `{{compile_var}}` and `{runtime_var}`
**When** the compiler emits compiled output
**Then** `{{compile_var}}` is replaced with its resolved value AND `{runtime_var}` is emitted unchanged so the model sees it at invocation

### Story 1.4: IDE Variant Selection and Full Error Taxonomy

As a skill author,
I want to ship IDE-specific fragments via dotted suffixes with a universal fallback always available, and I want every compile-time error to surface with file + line + caret + remediation hint,
So that Claude Code and Cursor users get IDE-appropriate content and I can fix problems without opening documentation.

**Acceptance Criteria:**

**Given** a fragment at `fragments/persona-guard.cursor.template.md`, a fragment at `fragments/persona-guard.claudecode.template.md`, and a universal fragment at `fragments/persona-guard.template.md`
**When** the compiler targets Claude Code
**Then** the `.claudecode.template.md` variant wins
**And** targeting Cursor selects the `.cursor.template.md` variant
**And** targeting any other IDE selects the universal fallback

**Given** only the universal fragment exists (no IDE variants)
**When** the compiler targets any IDE
**Then** the universal fragment compiles successfully with `<Include variant="universal">` in provenance

**Given** any compile-time error condition (unresolved variable, missing include, cyclic include, override outside root, lockfile version mismatch, undefined precedence)
**When** the error is raised
**Then** stderr contains the exact error code and a message formatted as `<CODE>: <path>:<line>:<col>: <description>` followed by a caret span and a one-line remediation hint
**And** the remediation hint is actionable without opening docs (e.g., `Did you mean 'user_name'? Available: user_name, module_root, installed_modules.`)

**Given** a fragment reference to `fragments/does-not-exist.template.md`
**When** the compiler runs
**Then** a `CompilerError` of code `MISSING_FRAGMENT` is raised with the non-existent path plus the list of candidate paths checked (one per precedence tier)

**Given** a fixture at `test/fixtures/bootstrap/unknown-directive/` containing a template with `<<foo>>`
**When** I run `python3 src/scripts/compile.py --skill test/fixtures/bootstrap/unknown-directive --install-dir <tmp>`
**Then** exit code is non-zero
**And** stderr contains `UNKNOWN_DIRECTIVE` with file + line + col of the offending token
**And** no partial writes exist in `<tmp>`

### Story 1.5: Lockfile v1 Writer with Provenance Tags

As a user,
I want the compiler to emit `_bmad/_config/bmad.lock` on every compile with per-skill source hash, fragment provenance, variable provenance, variant, glob inputs, and compiled-output hash,
So that there is a single audit trail for what was installed and why.

**Acceptance Criteria:**

**Given** a successful compile of a migrated skill
**When** the compiler finishes
**Then** `_bmad/_config/bmad.lock` contains a `version: 1` field and a per-skill entry with: `source_hash`, `fragments[]` (each with `path`, `resolved_from`, `hash`, optional `base_hash`, `override_hash`, `override_path`, `variant`, `lineage[]`), `variables[]` (each with `name`, `source`, optional `source_path`, `toml_layer`, `contributing_paths`, `declared_by`, `template_from`, required `value_hash`), `glob_inputs[]` (each with `pattern`, `resolved_pattern`, `match_set[]`, `match_set_hash`), `variant`, `compiled_hash`
**And** keys within each map are sorted alphabetically for deterministic output

**Given** a config value with plaintext secret content
**When** the lockfile records its variable entry
**Then** only `value_hash` (SHA-256) is written, never the plaintext value
**And** a grep of `bmad.lock` for known secret patterns finds nothing

**Given** a compile run and an identical re-compile run with unchanged inputs
**When** both runs complete
**Then** both lockfiles are byte-identical

**Given** a lockfile with `version: 2` and a v1 reader
**When** the reader opens the file
**Then** a `CompilerError` of code `LOCKFILE_VERSION_MISMATCH` is raised with a message directing the user to upgrade the compiler

**Given** a v1 lockfile containing unknown additive fields (from a future-compiler test fixture)
**When** the v1 compiler rewrites the lockfile after a recompile
**Then** the unknown additive fields are preserved unchanged (round-trip test asserts)

---

## Epic 2: Install Integration & First Migrated Skill

Maintainers and end users get a `bmad install` that invokes the Python compiler for migrated skills, preserves the verbatim-copy path for unmigrated skills, migrates `bmad-help` as the first production reference with byte-identical-output CI guarantee, and enforces cross-OS determinism.

### Story 2.1: Node Installer Hook, `invoke-python.js` Helper, Python 3.11 Hard Check

As a user running `bmad install`,
I want the installer to compile migrated skills via the Python compiler between file-copy and manifest generation, with a clear abort if Python 3.11+ is not available,
So that installs either succeed cleanly with compiled output or fail with an actionable error.

**Acceptance Criteria:**

**Given** a system with Python 3.10 or Python missing entirely
**When** `bmad install` runs
**Then** the installer detects Python < 3.11 (or absent), exits non-zero, and prints a message naming the detected version (or "not found") plus installation instructions
**And** no files are written to the install location

**Given** a system with Python 3.11+ and a module containing at least one migrated skill (`*.template.md` present)
**When** `bmad install` runs
**Then** the installer copies module files, invokes `python3 src/scripts/compile.py --install-phase --install-dir <path>` via `tools/installer/compiler/invoke-python.js`, receives structured JSON, and merges compiled outputs into the `installedFiles` set before manifest generation

**Given** a module containing only non-migrated skills (no `*.template.md`)
**When** `bmad install` runs
**Then** the installer follows the verbatim-copy path unchanged (no Python invocation for those skills)
**And** installed output is byte-identical to pre-compiler behavior (regression fixture in CI asserts)

**Given** a compile-time error during install (e.g., `UNRESOLVED_VARIABLE` in a migrated skill)
**When** the installer catches the Python subprocess failure
**Then** it exits non-zero, surfaces the Python-originated error (code + path + line + hint) to stdout, and leaves no partial writes in the install location

### Story 2.2: `bmad-help` as First Migrated Reference Skill (Keep-Contract)

As a skill maintainer,
I want `bmad-help` migrated to `SKILL.template.md` and CI diffing compiled output against the current `bmad-help/SKILL.md`,
So that the compiler is proven to preserve behavior for a real production skill before migrating additional skills.

**Acceptance Criteria:**

**Given** the current `bmad-help/SKILL.md` checked into the repo as baseline
**When** `bmad-help` is rewritten as `SKILL.template.md` (with any fragments factored out) and compiled by the pipeline
**Then** the compiled `SKILL.md` is byte-identical to the baseline (verified by `diff`)

**Given** the migrated `bmad-help` and a CI job running `bmad compile bmad-help --diff`
**When** the job runs on every PR
**Then** a non-empty diff fails the build
**And** the job runs on all three supported OSes to catch platform drift early

**Given** the baseline needs to intentionally change (e.g., content update)
**When** the maintainer edits fragments and updates the committed baseline
**Then** `bmad compile bmad-help --diff` against the new baseline is empty and `bmad.lock` reflects the new compiled hash

### Story 2.3: Cross-OS Determinism CI Matrix

As a maintainer,
I want CI to recompile the migrated skill set on macOS + Linux + Windows and assert byte-identical output,
So that platform-specific bugs (path separators, line endings, clock use) surface on PR rather than in production.

**Acceptance Criteria:**

**Given** a merge-to-main or release-tag commit
**When** CI runs
**Then** the compile job executes on `ubuntu-latest`, `macos-latest` (Intel and Apple Silicon runners), and `windows-latest`
**And** each job recompiles every migrated skill and asserts the compiled output hash is identical across all runners (consolidated diff step)

**Given** a PR commit (non-merge)
**When** CI runs
**Then** only `ubuntu-latest` runs the full matrix for speed; macOS + Windows run nightly and on merge-to-main

**Given** a CI run that produces non-identical output on one OS
**When** the consolidated diff step executes
**Then** the build fails with a report naming the divergent runner and the specific skill(s) whose hashes differ

---

## Epic 3: User Overrides Across Three Planes

End users can override prose fragments, TOML structured fields, and YAML variables under `_bmad/custom/`. Compiler merges according to documented precedence cascades. Module-boundary enforcement blocks silent core-fragment shadowing. Override-root and glob containment reject path-escape attempts.

### Story 3.1: Prose Fragment Overrides

As an end user,
I want to override any prose fragment by dropping a file under `_bmad/custom/fragments/<module>/<skill>/<name>.template.md`,
So that I can customize skill content without forking the upstream repo.

**Acceptance Criteria:**

**Given** a core skill with fragment `fragments/persona-guard.template.md` and no user override
**When** the compiler runs
**Then** the compiled output uses the core fragment and `<Include resolved-from="base">` is recorded

**Given** the same skill and a user override at `_bmad/custom/fragments/<module>/<skill>/persona-guard.template.md`
**When** the compiler runs
**Then** the compiled output uses the override content and `<Include resolved-from="user-override" override_path="_bmad/custom/...">` is recorded
**And** the override's hash is stored in the lockfile alongside the base hash

**Given** a full-skill override at `_bmad/custom/fragments/<module>/<skill>/SKILL.template.md`
**When** the compiler runs
**Then** the full-skill override wins over any per-fragment override per the precedence ladder (`user-full-skill > user-module-fragment > user-override > variant > base`)

**Given** an override file with identical content to the base
**When** the compiler runs
**Then** the override is still applied (precedence tier wins regardless of content equality) and `resolved_from` reflects the override tier

### Story 3.2: TOML Structured Overrides and Shared `toml_merge.py`

As an end user,
I want to override any `customize.toml` field via `_bmad/custom/<skill>.toml` (team) or `_bmad/custom/<skill>.user.toml` (personal, gitignored),
So that I can tune structured behavior without editing upstream files.

**Coordination Owner:** _TBD — assigned during Sprint 0._ This story includes a cross-cutting refactor of upstream's `resolve_customization.py` and `resolve_config.py` to import from the shared `bmad_compile.toml_merge` module. The refactor must land atomically in a single PR. The named owner is responsible for scheduling the landing window, coordinating with upstream maintainers, and arbitrating parity-test failures between the old and new implementations.

**Acceptance Criteria:**

**Given** a skill with `customize.toml` containing `icon = "📋"` and no user override
**When** the compiler runs
**Then** `{{self.icon}}` in the skill template resolves to `📋` with provenance `toml_layer: defaults`

**Given** the same skill and `_bmad/custom/<skill>.user.toml` containing `icon = "🎯"`
**When** the compiler runs
**Then** `{{self.icon}}` resolves to `🎯` with provenance `toml_layer: user`
**And** the lockfile records both the defaults hash and the user layer hash for the `icon` field

**Given** `customize.toml` with array-of-tables (`[[activation_phrases]]` entries keyed by `id`) and a user override adding a new entry and modifying an existing one
**When** `toml_merge.py` merges layers
**Then** scalars override, tables deep-merge, and arrays-of-tables merge by the documented key (`id` or `code`)
**And** test fixtures cover each case

**Given** upstream's `resolve_customization.py` and `resolve_config.py` were previously independent implementations
**When** this story ships
**Then** both upstream modules import from `bmad_compile.toml_merge`, their existing test suites still pass (parity), and a single PR lands both refactors atomically

**Given** the 8-tier TOML cascade (user → team → defaults → central-custom-user → central-custom-team → central-base-user → central-base-team + CLI flag)
**When** a value is resolved
**Then** the topmost tier containing the value wins and `contributing_paths[]` is recorded when multiple layers merge (e.g., deep-merged tables)

### Story 3.3: YAML Variable Overrides (non-`self.*` Cascade)

As an end user,
I want to override any compile-time YAML variable by setting it in `_bmad/custom/config.yaml` or a per-module override,
So that I can customize module-wide values without touching core config.

**Acceptance Criteria:**

**Given** `_bmad/core/config.yaml` with `user_name: Shado` and no user override
**When** the compiler runs
**Then** `{{user_name}}` resolves to `Shado` with provenance `source: bmad-config`, `source_path: _bmad/core/config.yaml`

**Given** the same core value and `_bmad/custom/config.yaml` containing `user_name: Override`
**When** the compiler runs
**Then** `{{user_name}}` resolves to `Override` with provenance `source: user-config`, `source_path: _bmad/custom/config.yaml`

**Given** a module-scoped value at `<module>/config.yaml` (above the core-marker comment)
**When** the compiler runs
**Then** it takes precedence over `bmad-config` but is overridden by `user-config` (5-tier cascade: `install-flag > user-config > module-config > bmad-config > derived`)

**Given** a CLI invocation with `--set user_name=Flag`
**When** the compiler runs
**Then** the `install-flag` tier wins and `source: install-flag` is recorded

### Story 3.4: Full-Skill Escape Hatch and Module-Boundary Enforcement

As a platform maintainer,
I want third-party modules unable to silently shadow core fragments or core-declared TOML fields, and I want end users to have a clearly-marked full-skill override escape hatch,
So that core behavior is protected while end users retain ultimate customization power.

**Acceptance Criteria:**

**Given** a third-party module declaring a fragment at `core/persona-guard.template.md` (attempting to shadow core)
**When** the installer runs
**Then** a `CompilerError` of code `PRECEDENCE_UNDEFINED` is raised at install time with a message explaining the module boundary
**And** no files are written

**Given** the same module namespaced correctly (e.g., `<module-name>/persona-guard.template.md`) and a core fragment at `core/persona-guard.template.md`
**When** the installer runs
**Then** both fragments install without conflict and resolve independently

**Given** an end user places `_bmad/custom/fragments/<module>/<skill>/SKILL.template.md` (full-skill replacement)
**When** the compiler runs
**Then** the replacement is applied with `resolved_from: user-full-skill`
**And** a warning is emitted to stderr noting that full-skill replacement bypasses fragment-level upgrade safety

### Story 3.5: Override-Root Containment and Glob Security

As a platform maintainer,
I want override paths and glob inputs rejected if they escape the project root via `..` or symlinks,
So that no override mechanism can exfiltrate content from outside the project.

**Acceptance Criteria:**

**Given** a user override at `_bmad/custom/../../etc/passwd` (path-escape attempt)
**When** the compiler reads the override set
**Then** a `CompilerError` of code `OVERRIDE_OUTSIDE_ROOT` is raised before any read occurs, naming the offending path

**Given** a symlink inside `_bmad/custom/` pointing to `/etc/passwd`
**When** the compiler follows the symlink during override resolution
**Then** the read is rejected with `OVERRIDE_OUTSIDE_ROOT` (resolved target is outside project root)

**Given** a `file:` TOML glob pattern `file:../../**/*.md`
**When** the compiler expands the glob
**Then** expansion is rejected with an error (glob must resolve inside `{project-root}`)

**Given** a glob pattern matching a symlink inside the project pointing outside
**When** expansion happens
**Then** matches whose resolved target escapes the project root are filtered out

---

## Epic 4: Compile Inspection Primitives (`bmad compile`)

Power users, authors, and tooling (including the future `bmad-customize` skill) can recompile, preview changes via `--diff`, and inspect full provenance via `--explain` (Markdown / tree / JSON).

### Story 4.1: `bmad compile <skill>` and `--diff`

As a power user or author,
I want to recompile a single skill from its template source and overrides, and to emit a unified diff against the currently-installed output without writing changes,
So that I can preview the impact of edits before committing them.

**Acceptance Criteria:**

**Given** a migrated skill with a local override that differs from installed content
**When** I run `bmad compile <skill>`
**Then** the compiled `SKILL.md` is written to the install location and `bmad.lock` is updated
**And** exit code is 0 on success, non-zero on any `CompilerError`

**Given** the same skill
**When** I run `bmad compile <skill> --diff`
**Then** a unified diff is emitted to stdout showing differences between currently-installed `SKILL.md` and freshly-compiled output
**And** no file writes occur (verified by `bmad.lock` and install-location byte-identical before/after)
**And** output is ANSI-colorized when stdout is a TTY, plain when piped

**Given** an unchanged skill (no edits since last compile)
**When** I run `bmad compile <skill> --diff`
**Then** the diff is empty and exit code is 0

**Given** a skill with no user overrides at all (pristine install state)
**When** I run `bmad compile <skill> --diff`
**Then** the diff is empty and exit code is 0 (empty-diff is success semantics, not silent failure)
**And** stderr is silent (no "no overrides found" warning — pristine state is normal)

**Given** `bmad compile` run without LLM access
**When** the command completes
**Then** identical inputs produce identical outputs (twice-run test asserts byte-equal stdout and lockfile entries)

### Story 4.2: `--explain` Markdown Output with `<Include>` and `<Variable>` Tags

As a power user or author,
I want `bmad compile <skill> --explain` to render a Markdown-with-inline-XML provenance view,
So that I can audit which fragment, tier, and variable source contributed each chunk of the compiled skill.

**Acceptance Criteria:**

**Given** a migrated skill
**When** I run `bmad compile <skill> --explain`
**Then** stdout contains compiled content interleaved with `<Include>` tags wrapping each fragment's content
**And** each `<Include>` tag has attributes `src`, `resolved-from`, `hash` and, when applicable, `base-hash`, `override-hash`, `override-path`, `variant`

**Given** a template containing compile-time variables
**When** `--explain` runs
**Then** each resolved value is surrounded by a `<Variable>` tag with `name`, `source`, `resolved-at`, and (when applicable) `source-path`, `toml-layer`, `contributing-paths`, `base-source-path`, `declared-by`, `template-from`

**Given** a template containing runtime `{var_name}` placeholders
**When** `--explain` runs
**Then** `{var_name}` passes through unchanged so the output previews what the model will receive

**Given** a fragment resolved from a user override
**When** `--explain` output is inspected
**Then** `<Include>` has `resolved-from="user-override"`, `override-path` pointing to `_bmad/custom/...`, and both `hash` (override) and `base-hash` (upstream) populated

### Story 4.3: `--explain --tree` and `--explain --json`

As a power user, tooling author, or the `bmad-customize` skill,
I want tree-only and JSON output modes for `--explain`,
So that I can render fragment dependency graphs or programmatically consume provenance.

**Acceptance Criteria:**

**Given** a skill with a multi-level include chain
**When** I run `bmad compile <skill> --explain --tree`
**Then** stdout contains only the fragment-dependency tree (no content bodies), indented by depth, each line showing fragment path and `resolved-from` tier

**Given** the same skill
**When** I run `bmad compile <skill> --explain --json`
**Then** stdout is valid JSON with a `schema_version: 1` root field and contains arrays `fragments[]` and `variables[]` with the same attributes as the XML tags
**And** `toml_fields[]` is populated with each field's path, default, current value, and per-layer hashes (for `bmad-customize` discovery)

**Given** `--explain --json` output
**When** piped to `jq '.fragments[] | select(.resolved_from == "user-override")'`
**Then** the result is a well-formed subset of fragments resolved from user overrides only

**Given** an additive schema field lands in a future v2
**When** a v1 consumer reads v2 output
**Then** it can still parse `schema_version`, `fragments[]`, and `variables[]` without crashing (additive-field tolerance)

**Given** Epic 4 is complete (end of epic)
**When** the `--explain --json` schema is checked in
**Then** a schema fixture at `src/scripts/bmad_compile/schemas/explain-v1.json` is frozen as a CI contract
**And** any change to field names or semantics requires updating `schema_version` and Epic 6 mock fixtures in the same PR
**And** this schema is Epic 6's sole source of truth for mock-contract construction (Story 6.1 depends on it)

### Story 4.4: `<TomlGlobExpansion>` Tags and Variable-Source Traceability

As an author customizing skills that use `file:`-prefixed TOML array values,
I want `--explain` to wrap glob expansions in `<TomlGlobExpansion>` tags with per-match detail,
So that I can trace which files contributed to a compiled variable's content.

**Acceptance Criteria:**

**Given** a `customize.toml` field `persistent_facts = "file:docs/context/*.md"` with three matching files
**When** `bmad compile <skill> --explain` runs
**Then** output contains `<TomlGlobExpansion pattern="file:docs/context/*.md" resolved_pattern="<abs-path>">` wrapping three `<TomlGlobMatch path="docs/context/a.md" hash="<sha256>">` children (alphabetically sorted)

**Given** the glob matches change between compiles (file added/removed/edited)
**When** re-compiling
**Then** `match_set_hash` in the lockfile changes and `--explain` shows the new match set

**Given** a variable resolved across multiple TOML tiers (merged table)
**When** `--explain` runs
**Then** `<Variable contributing-paths="layer1,layer2,layer3" toml-layer="merged">` records each contributing layer path

---

## Epic 5: Upgrade, Drift & Lazy-Compile

End users run `bmad upgrade --dry-run` to preview drift across six tracked-input categories, `bmad upgrade` halts non-zero on drift unless `--yes`, and SKILL.md is always fresh at skill-entry via a lazy-compile cache-coherence guard.

### Story 5.1: `bmad upgrade --dry-run` with Drift Categories

As an end user,
I want to preview the impact of a version bump across every tracked input before applying it,
So that I see exactly what will change and what overrides I'll need to reconcile.

**Acceptance Criteria:**

**Given** an installed project with a `bmad.lock` and upstream updates (prose fragment changes, TOML default changes, orphaned overrides, new defaults, glob changes, variable-provenance shifts)
**When** I run `bmad upgrade --dry-run`
**Then** stdout reports each of the six drift categories with per-skill count and per-item detail (old/new/user values for TOML; old/new hashes for prose; added/removed matches for globs)

**Given** the same conditions
**When** I run `bmad upgrade --dry-run --json`
**Then** stdout is valid JSON with `schema_version: 1`, per-skill drift entries keyed by category, per-entry fields consumable by `bmad-customize` (old-hash, new-hash, user-override-hash, paths, tier)

**Given** an upgrade with no drift (all tracked inputs match lockfile)
**When** `--dry-run` runs
**Then** stdout reports "No drift detected" (human) or empty categories (JSON) and exit code is 0

**Given** 50 migrated skills with drift in 3 categories
**When** `--dry-run` runs
**Then** total execution time is ≤ 3 seconds wall-clock on mid-2021 laptop
**And** the first drift item is streamed to stdout within 500ms (not buffered until completion)

**Given** Story 5.1 is complete
**When** the `--dry-run --json` schema is checked in
**Then** a schema fixture at `src/scripts/bmad_compile/schemas/dry-run-v1.json` is frozen as a CI contract
**And** any change to field names or semantics requires updating `schema_version` and Epic 6 mock fixtures in the same PR
**And** this schema is Epic 6's sole source of truth for drift-triage mock-contract construction (Story 6.1 depends on it)

### Story 5.2: `bmad upgrade` Halt-on-Drift, `--yes` Escape, Install Auto-Routing

As an end user,
I want `bmad upgrade` to halt non-zero when drift is detected (unless `--yes`), and I want `bmad install` to auto-route to `bmad upgrade --dry-run` when an install already exists,
So that upgrades never silently overwrite my customizations and re-installs surface drift by default.

**Acceptance Criteria:**

**Given** an install with drift in at least one tracked input
**When** I run `bmad upgrade` without `--yes`
**Then** exit code is 3, no files are modified, and stderr prints: `Drift detected in N skills (M prose fragments, P TOML fields, Q glob inputs). Invoke 'bmad-customize' skill in your IDE chat to review and resolve, then re-run 'bmad upgrade'. Use 'bmad upgrade --yes' to ignore drift and proceed (not recommended).`

**Given** the same install with drift
**When** I run `bmad upgrade --yes`
**Then** the upgrade proceeds, user-override-containing files are preserved, and new upstream content is written for non-overridden fragments/TOML fields
**And** lineage is appended to `bmad.lock` recording the base-hash transition

**Given** an install with no drift
**When** I run `bmad upgrade`
**Then** the upgrade proceeds without prompt and exit is 0

**Given** a project directory containing `_bmad/_config/bmad.lock` (existing install)
**When** I run `bmad install`
**Then** the installer auto-routes to `bmad upgrade --dry-run`, presents the drift report, and prompts for confirmation before proceeding (unless `--yes` passed, which proceeds as upgrade)

**Given** a project with no `bmad.lock` (fresh install)
**When** I run `bmad install`
**Then** no auto-routing; the installer performs a fresh install

### Story 5.3: Append-Only Lineage for Rollback Forward-Compat

As a platform maintainer,
I want `bmad.lock` to maintain an append-only lineage per overridden fragment and TOML field at each upgrade,
So that a future `bmad upgrade --rollback` can reconstruct pre-upgrade state (v1 doesn't implement rollback but records the data).

**Acceptance Criteria:**

**Given** a user-overridden fragment and an initial compile
**When** the lockfile is written
**Then** the fragment's `lineage[]` is empty (no history yet)

**Given** an upgrade that changes the base fragment's upstream hash
**When** `bmad upgrade` runs successfully
**Then** the fragment's `lineage[]` appends an entry `{bmad_version: <old>, base_hash: <old>, override_hash: <snapshot>}` recording pre-upgrade state
**And** subsequent upgrades continue to append — no entries are ever removed

**Given** a TOML field with a user override and an upgrade changing the default
**When** the upgrade runs
**Then** the field's `lineage[]` appends `{bmad_version: <old>, base_value_hash: <old>, override_value_hash: <current>}`

**Given** a lockfile with large lineage (e.g., 10 upgrades)
**When** the compiler reads and rewrites the lockfile
**Then** all lineage entries are preserved (not pruned)
**And** deterministic-output guarantee holds (lineage entry ordering is stable)

**Given** a rollback-foundation contract test (forward-compat for future `bmad upgrade --rollback`)
**When** the test runs after a multi-upgrade sequence
**Then** it reconstructs each intermediate state purely from `lineage[]` entries and asserts each reconstruction matches the pre-upgrade lockfile snapshot byte-identically
**And** any missing or corrupted lineage entry causes the reconstruction to fail (catches lineage-write bugs before rollback ships in a future release)

### Story 5.4: Lazy-Compile Cache-Coherence Guard — Hash Dispatch, Glob Drift, Error Propagation

As an IDE user,
I want SKILL.md guaranteed fresh at skill-entry with a fast path for unchanged skills, glob match-set drift detection, and missing-input errors propagated (not silenced),
So that edits to templates or overrides take effect immediately and staleness/corruption is never hidden.

**Acceptance Criteria:**

**Given** a skill with all tracked inputs unchanged since last compile
**When** the SKILL.md shim invokes `python3 -m bmad_compile.lazy_compile <skill>`
**Then** the guard re-hashes inputs, matches all against lockfile, and emits existing SKILL.md content to stdout
**And** total time is ≤ 50ms wall-clock on mid-2021 laptop with ≤ 20 tracked inputs (fast path)

**Given** one tracked input whose hash differs from lockfile
**When** the guard runs
**Then** it invokes the same compile engine as build-time `bmad compile <skill>`, writes fresh SKILL.md + updated lockfile entry, and emits fresh content to stdout
**And** total time is ≤ 500ms (slow path)

**Given** a tracked glob input whose match-set has changed (file added/removed/edited)
**When** the guard runs
**Then** it detects the match-set change (via `match_set_hash` diff), recompiles, and updates the lockfile entry

**Given** a tracked input file is missing at skill entry (deleted, moved, or stale lockfile entry)
**When** the guard runs
**Then** the recompile attempt surfaces a `MISSING_FRAGMENT` (or equivalent) error with file + line
**And** the shim propagates the error to the IDE (no silent fallback to stale content)

### Story 5.5: Lazy-Compile Concurrency — Advisory File-Locks and Timeout

> **[Split decision 2026-05-05 per Epic 4 retro §6 / Phil approval]:** Story 5.5 splits into 5.5a (concurrency primitives) + 5.5b (toml_merge + lockfile hardening accumulator). Story 5.5b absorbs the ~28 accumulated deferred entries (toml_merge AoT shallow-copy, BOM handling, mixed code/id silent concat, layer-falsy-drop, live override-dict references, in-root case-insensitive cycle keying, lockfile version-field strictness, non-dict `entries[]`, RMW concurrency TOCTOU, `_variant_candidate` TOCTOU, `_build_skill_entry` defensive guards, `_render_explain_tree` depth-tracker test hardening, etc. — see `_bmad-output/implementation-artifacts/deferred-work.md` Epic 4 close-out audit §PULL for the full list); 5.5a focuses on concurrency primitives (advisory locks via `fcntl.flock` POSIX / `msvcrt.locking` Windows, `--lock-timeout-seconds`, SIGKILL stale-lock recovery, cross-OS file-lock CI fixture). Surface-area heuristic per `_bmad/custom/bmad-create-story.toml`: 5.5a ≈ 5 markers, Sonnet-viable; 5.5b ≈ 7 markers, Opus territory (multi-file refactor + AoT semantics + BOM handling + version-field strictness + lineage forward-compat). 5.5b serves as Epic 5's "epic-closer" cleanup story per the Epic 1 §3.3 / Story 1.8 pattern. **AC reorganization happens at Story 5.5x spec authoring time, not now** — the AC list below remains the canonical Story 5.5 surface (which 5.5a inherits) until the spec-authoring pass formally splits it.

As an IDE user running two invocations of the same skill simultaneously (e.g., two tool calls referencing the same skill in one turn),
I want the lazy-compile guard to serialize concurrent compilations cross-platform,
So that no duplicate-compile races, no corrupted lockfile writes, and no hung invocations occur.

**Acceptance Criteria:**

**Given** two concurrent invocations of the lazy-compile guard for the same skill
**When** both run simultaneously
**Then** an advisory file-lock on `<skill-dir>/.compiling.lock` serializes them — POSIX uses `fcntl.flock`, Windows uses `msvcrt.locking`
**And** the second invocation waits up to `--lock-timeout-seconds` (default 300s), then re-reads the freshly-compiled SKILL.md and emits it without a second compile

**Given** a lock holder crashes mid-compile (stale lock file left behind)
**When** a new invocation acquires the lock
**Then** it detects the stale state (lockfile unchanged, `.compiling.lock` orphaned), takes the lock, and re-runs full compile
**And** a test fixture simulates this via `SIGKILL` mid-compile and asserts the next invocation recovers cleanly

**Given** the `--lock-timeout-seconds` elapses before the lock is released
**When** the waiting invocation times out
**Then** it exits non-zero with a clear message ("Timed out waiting for concurrent compile; see logs for lock holder PID")
**And** the invocation does NOT silently fall back to stale content

**Given** concurrent invocations across both POSIX and Windows CI runners
**When** the lock test fixture runs
**Then** both platforms complete within expected semantics (file-lock test fixture is required in the Windows + Linux CI matrix)

### Story 5.6: SKILL.md Shim Integration and Batch-Mode Compilation

As a performance-conscious user,
I want the SKILL.md shim updated to invoke `lazy_compile.py` instead of upstream's runtime renderer, and I want install-time compiles to use batch mode,
So that skill entry is fast and fresh installs don't pay N × 200ms interpreter startup.

**Coordination Owner:** _TBD — assigned during Sprint 0._ The SKILL.md shim change has skill-entry-wide blast radius: a broken shim fails every skill at entry simultaneously across every install. The named owner is responsible for (1) scheduling the landing window with the SKILL.md shim upstream owner, (2) defining a staged-rollout plan if the deployment model supports it (e.g., shim behind a feature flag for the first release), and (3) owning the roll-forward / roll-back procedure documented below.

**Roll-forward / roll-back plan:**
- **Pre-merge:** Full cross-OS CI on all 6 OS/arch combinations (macOS Intel + Apple Silicon, Linux x86_64 + ARM64, Windows 10/11) must pass, not the PR-default Linux-only subset. Integration test (Story 7.2) must pass against the candidate shim.
- **Post-merge guardrail:** For the first release after landing, the SKILL.md shim preserves a fallback code path that re-invokes the previous runtime renderer if `lazy_compile.py` exits non-zero from a known recoverable error taxonomy (`MISSING_FRAGMENT`, `LOCKFILE_VERSION_MISMATCH`). Fallback emits a stderr warning so regressions are visible without breaking user sessions. Fallback is removed in the following minor release once the shim is proven in the wild.
- **Roll-back trigger:** If ≥ 3 independent user reports of shim-originated skill-entry failure land within 7 days of release, the release owner reverts the shim commit and pins the runtime renderer back in a patch release. Decision authority rests with the Coordination Owner.

**Acceptance Criteria:**

**Given** the upstream SKILL.md shim (commit `b0d70766`) previously invoking a runtime renderer
**When** this story ships
**Then** the shim invokes `python3 -m bmad_compile.lazy_compile <skill>` instead
**And** upstream `{var}` runtime substitution behavior is removed (migration coordinated with Epic 2's first-skill story — `{var}` → `{{var}}` / `{{self.*}}`)

**Given** an install with N migrated skills
**When** `bmad install` invokes the compiler
**Then** the Node adapter calls `python3 src/scripts/compile.py --batch <skills.json>` once (single interpreter cold-start) and receives newline-delimited JSON for each skill
**And** total install-time overhead is ≤ 10% vs pre-compiler baseline (hash-based skip + batch mode combined)

**Given** a re-install with no source changes
**When** `bmad install` runs
**Then** hash-based skip activates: each skill's canonical input hash matches the lockfile, no recompile runs, and lockfile + installed SKILL.md remain byte-identical
**And** total re-install overhead is ≤ 5% vs pre-compiler baseline

---

## Epic 6: Interactive `bmad-customize` Skill

End users customize skills and triage upgrade drift through natural-language IDE chat — no manual disk edits, no silent losses. Skill dogfoods the compiler by being authored as `SKILL.template.md` + fragments + `customize.toml`. Testing uses compiler-primitive mocks at the JSON-schema boundary — bmad-customize logic is verified against frozen `--explain --json` / `--dry-run --json` schemas (not against a hand-authored stand-in skill), breaking the dogfood circular dependency.

### Story 6.1: Compiler-Primitive Mock Contract for Epic 6 Testing

As a `bmad-customize` skill developer,
I want a versioned mock contract for the compiler primitives (`--explain --json` and `--dry-run --json`) with fixtures covering every scenario the skill handles,
So that Stories 6.2–6.6 can test bmad-customize logic against the schema boundary rather than a stand-in skill, avoiding a circular dogfood dependency and keeping test assertions independent of LLM-phrasing drift.

**Acceptance Criteria:**

**Given** Story 4.3 has frozen the `--explain --json` schema at `src/scripts/bmad_compile/schemas/explain-v1.json` and Story 5.1 has frozen `--dry-run --json` schema at `schemas/dry-run-v1.json`
**When** Story 6.1 is complete
**Then** `test/fixtures/epic6/mocks/` contains synthesized-response fixtures for every scenario Stories 6.2–6.6 assert against, minimally:
  - `explain-pristine.json` (no overrides)
  - `explain-with-prose-override.json`
  - `explain-with-toml-override.json`
  - `explain-ambiguous-intent.json` (multiple candidate fields)
  - `dry-run-no-drift.json`
  - `dry-run-prose-drift.json`
  - `dry-run-toml-default-drift.json`
  - `dry-run-toml-orphan.json`
  - `dry-run-toml-new-default.json`
  - `dry-run-glob-drift.json`
**And** each fixture validates against the frozen schema (CI gate asserts)

**Given** the mock compiler test harness
**When** Stories 6.2–6.6 run
**Then** a `MockCompiler` class in `test/harness/mock_compiler.py` intercepts all `bmad compile --explain --json` and `bmad upgrade --dry-run --json` invocations from the skill under test and returns a named fixture
**And** stories assert structured intent objects emitted by the skill (not prose strings) — e.g., `assert event == {action: "request_disambiguation", candidates: [...]}`

**Given** a schema update to `--explain --json` or `--dry-run --json` in a later story or post-GA PR
**When** the schema changes
**Then** CI requires matching updates to Epic 6 mock fixtures in the same PR (enforced by a contract test that validates every mock against the current schema)

**Given** Story 6.7 (dogfood) runs
**When** the dogfood test executes
**Then** it bypasses the mock compiler and invokes the actual compiler, serving as the integration test against the real primitives — the mock seam is for 6.2–6.6 only

### Story 6.2: Invoke from IDE Chat and Discovery via `--explain --json`

As an end user in an IDE chat (Claude Code or Cursor),
I want to invoke `bmad-customize` with a natural-language customization intent and have it discover the target skill's full customization surface,
So that I can begin customizing without reading the skill's internal structure.

**Acceptance Criteria (assertions are on structured intent objects emitted by the skill, not on prose phrasing — LLM prose is UX polish, not contract):**

**Given** a simulated IDE-chat invocation with intent "make this agent's greeting more formal" against mock fixture `explain-pristine.json`
**When** the skill processes the intent
**Then** the skill emits structured event `{action: "discover", skill_id: "<resolved>", source: "--explain --json"}` before any prose response
**And** the `MockCompiler` records exactly one `--explain --json` call with the resolved skill-id

**Given** the mock returns a valid `--explain --json` payload
**When** the skill parses it
**Then** the skill emits structured event `{action: "report_surface", toml_fields: N, prose_fragments: M, variables: K}` with counts matching the fixture's contents

**Given** ambiguous intent (mock fixture `explain-ambiguous-intent.json` with multiple icon-like fields)
**When** the skill processes the intent
**Then** the skill emits `{action: "request_disambiguation", candidates: [...]}` and waits for user input before any further action

**Given** a user turn involving customization discovery
**When** the skill completes the turn
**Then** the `MockCompiler` records ≤ 2 `--explain --json` invocations (NFR-P4 perf budget asserted as call-count)

### Story 6.3: Plane Routing and Intent Negotiation

As an end user,
I want the skill to identify which customization plane (TOML / prose / YAML / full-skill) my intent maps to and negotiate the target with me before any write,
So that my customization lands at the right layer and I understand what's changing.

**Acceptance Criteria (structured-intent assertions against mocked discovery payloads):**

**Given** an intent mapping cleanly to a TOML field (mock fixture `explain-pristine.json` + intent "change the icon from 📋 to 🎯")
**When** the skill analyzes intent
**Then** the skill emits `{action: "propose_route", plane: "toml", field_path: "icon", target_file: "_bmad/custom/<skill>.user.toml", requires_confirmation: true}`
**And** does not emit any write action until a `{event: "user_confirmation", confirmed: true}` is received

**Given** an intent mapping to prose ("rewrite the menu handler to be more concise")
**When** the skill analyzes intent
**Then** the skill emits `{action: "propose_route", plane: "prose", fragment_name: "menu-handler", target_file: "_bmad/custom/fragments/<module>/<skill>/menu-handler.template.md", requires_confirmation: true}`

**Given** an intent that could map to multiple planes (mock payload with both TOML `greeting_template` field and prose `fragments/activation.template.md`)
**When** the skill detects ambiguity
**Then** the skill emits `{action: "request_plane_disambiguation", candidates: [{plane: "toml", field_path: "..."}, {plane: "prose", fragment_name: "..."}]}` and waits

**Given** an intent requesting full-skill replacement
**When** the skill detects it
**Then** the skill emits `{action: "warn_full_skill", bypass_warning: "full-skill replacement bypasses fragment-level upgrade safety", requires_confirmation: true, requires_second_confirmation: true}`
**And** does not route to `_bmad/custom/fragments/<module>/<skill>/SKILL.template.md` until both confirmations are received

### Story 6.4: Conversational Drafting and No-Disk-Write-Until-Accept

As an end user,
I want `bmad-customize` to draft override content conversationally in chat without writing to disk until I accept,
So that I can iterate freely without polluting my project tree or lockfile with abandoned attempts.

**Acceptance Criteria:**

**Given** a drafting session in progress
**When** the skill proposes a draft (prose, TOML, or YAML)
**Then** the draft is displayed as text inside the chat conversation only
**And** no file is created or modified under `_bmad/custom/`

**Given** a drafting session that is abandoned (user closes chat, rejects draft, says "never mind")
**When** the session ends
**Then** no files exist under `_bmad/custom/` that didn't exist before, and `bmad.lock` is byte-identical to its pre-session state

**Given** multiple drafting iterations (user says "make it shorter", skill revises, user says "actually try something else")
**When** each iteration runs
**Then** no file writes occur; all drafts live in conversation context only

**Given** a user partially-approves a draft and wants to tweak further
**When** the user requests a revision
**Then** the skill revises in chat without creating staging files or temporary overrides

### Story 6.5: Post-Accept Write and `--diff` Verification

As an end user,
I want the skill to write my accepted override to the correct file and show me a `bmad compile --diff` so I can verify the compiled-SKILL.md-level impact,
So that I see exactly what the LLM will receive after my change.

**Acceptance Criteria:**

**Given** a draft the user has explicitly accepted
**When** the skill writes the override
**Then** it writes to the exact file path determined by plane routing (e.g., `_bmad/custom/<skill>.user.toml` for TOML, `_bmad/custom/fragments/<module>/<skill>/<name>.template.md` for prose)
**And** writes only the fields/content that differ from defaults (sparse override), never full copies unless full-skill replacement

**Given** an override just written
**When** the skill invokes `bmad compile <skill> --diff`
**Then** the unified-diff output is shown in chat, comparing pre-override compiled SKILL.md to post-override compiled SKILL.md
**And** the user can confirm the diff matches their intent or ask for a revision

**Given** the user rejects the diff (says "that's not what I wanted")
**When** the skill responds
**Then** the skill offers to revise; on user confirmation, the skill reverts the override (removes or resets the file), re-drafts in chat, and re-writes only on acceptance

### Story 6.6: Drift Triage UX

As an end user whose upgrade halted due to drift,
I want `bmad-customize` to walk me through each drift entry with plane-appropriate UX,
So that I can reconcile drift without manual file archaeology.

**Acceptance Criteria:**

**Given** a halted `bmad upgrade` and drift detected in a prose fragment I've overridden (upstream-old / upstream-new / my-override all differ)
**When** I invoke `bmad-customize` with drift-triage intent
**Then** the skill calls `bmad upgrade --dry-run --json`, reads the prose-drift entry, and presents upstream-old / upstream-new / my-override side-by-side
**And** offers three actions: keep (retain my override), adopt (discard my override, use upstream-new), author-merged (skill drafts a merged override in chat for my approval)

**Given** drift in a TOML default-value I've overridden
**When** the skill processes the drift entry
**Then** it presents: field path, old-default, new-default, my override value, and offers: keep / adopt-new-default / rewrite-override

**Given** a TOML orphan drift (my override applies to a field removed upstream)
**When** the skill processes it
**Then** it notifies me the field no longer exists and offers to remove my now-orphaned override

**Given** TOML new-default awareness drift (upstream added a field with a default)
**When** the skill processes it
**Then** it notifies me of the new field and default; no action required unless I want to override

**Given** glob-input drift (a `file:` pattern's match-set changed)
**When** the skill processes it
**Then** it shows added/removed matches and content changes informationally; no action unless the user-overrides a TOML field whose value depends on the glob

**Given** drift triage complete and all entries resolved
**When** the skill finishes
**Then** it instructs the user to re-run `bmad upgrade` (which should now pass without halt)
**And** all writes during triage follow the no-disk-write-until-accept contract (FR55)

### Story 6.7: Dogfood — `bmad-customize` Authored as Template Source

As a platform maintainer,
I want `bmad-customize` itself authored as `SKILL.template.md` + fragments + `customize.toml` and compiled by the same pipeline it helps users customize,
So that the skill is a living reference implementation that exercises both compile planes and surfaces compiler regressions before release.

**Acceptance Criteria:**

**Given** the `bmad-customize` skill authored as template source
**When** the compiler builds it
**Then** the compiled output is a fully functional IDE-chat skill
**And** the skill references core fragments via `<<include path="core/...">>` and uses `{{self.*}}` for TOML-driven configuration

**Given** a user customizes `bmad-customize` itself (e.g., overrides its tone)
**When** `bmad-customize` runs with the customization applied
**Then** the customization takes effect (skill behavior reflects override)
**And** this dogfoods both the TOML plane and the prose plane

**Given** a CI step at release time
**When** the dogfood gate runs
**Then** `bmad-customize` is invoked via its own interactive test harness (drives discovery, drafts in chat-simulation, verifies no disk writes until accept, exercises drift triage against a fixture drift set)
**And** the release fails if any `bmad-customize` scenario fails

**Dogfood Release Gate Procedure (FR40 / PRD FR39 — own-cooking cycle):**

**Given** `bmad-customize` has shipped at a prior BMAD version (N-1) as template source with at least one user-authored override applied to itself (e.g., its own `customize.toml` `icon` field overridden, and one prose fragment in its `fragments/` tree overridden)
**When** the release of BMAD version N is being prepared
**Then** the release owner executes the following procedure and records the outcome in the release PR:

  1. Check out a clean environment with BMAD N-1 installed, including the `bmad-customize` self-overrides described above
  2. Upgrade to the candidate build of BMAD N via `bmad upgrade --dry-run`
  3. Assert the dry-run correctly classifies each `bmad-customize` self-override against upstream changes (no silent classification, every override either "unchanged / still applies" or "drift / needs triage")
  4. If drift is reported, invoke `bmad-customize` (running under the N-1 build) with drift-triage intent against its own self-overrides, reconcile each drift entry per the Story 6.6 UX, and assert `bmad upgrade` succeeds after triage
  5. Assert the upgraded `bmad-customize` at version N retains its own user overrides (the ones preserved through triage) and behaves correctly in a smoke-test scenario (discovery, plane routing, draft + accept, post-accept `--diff`)
  6. Assert `bmad.lock` records the version N transition lineage for each self-override

**Pass criteria (all must hold):**
  - Every self-override is either preserved verbatim or intentionally reconciled by the release owner; no silent loss.
  - Upgrade completes to exit 0 after triage (or directly, if no drift).
  - Post-upgrade smoke-test passes.
  - Release owner signs off in the release PR description with the recorded outcome of steps 1–6.

**Fail criteria (any one blocks release):**
  - A self-override is silently lost at any step.
  - The dry-run misclassifies a drift entry (false negative or false positive verified against the known self-override set).
  - Post-upgrade smoke-test fails.
  - The procedure cannot be executed (e.g., `bmad-customize` at N-1 cannot be used to triage itself because of a compiler regression introduced in N).

**Ownership:** The dogfood-gate procedure has a **named owner (person, not team)** on every release PR, assigned per Story 7.5. Owner must be a core maintainer with commit rights, not rotating — continuity matters across consecutive releases for reproducible sign-off.

---

## Epic 7: Validation, CI, Release Gates & Module Distribution

Every release passes automated quality gates — no regressions, no silent losses, all five required docs present. Dogfood-gate owner signs off that `bmad-customize` survives its own upgrade. Ship-gate success metric is either instrumented or explicitly downgraded. Module distribution models (1/2/3) are installer-detected. Third-party dogfood migration is preferred but ship-blocking status waived (soft gate).

### Story 7.1: `npm run validate:compile` and `npm run validate:skills`

As a CI pipeline,
I want two validation commands — one that recompiles all migrated skills and diffs against `bmad.lock`, and one that asserts every compiled skill passes schema validation,
So that any compiler regression or schema violation fails the build on PR.

**Acceptance Criteria:**

**Given** an unchanged repo state
**When** `npm run validate:compile` runs
**Then** it recompiles every migrated skill in-place, compares each compiled output's hash against `bmad.lock`, and exits 0 if all match

**Given** a code change that causes one or more skills to produce different output
**When** `npm run validate:compile` runs
**Then** it exits non-zero with a per-skill report showing which hashes diverged
**And** the CI job surfaces this report in the PR UI

**Given** every compiled `SKILL.md`
**When** `npm run validate:skills` runs
**Then** each compiled skill is parsed against the SKILL.md schema (frontmatter fields, required sections, etc.) and exits 0 only if all pass

**Given** a PR that regresses schema (e.g., missing required frontmatter)
**When** `npm run validate:skills` runs
**Then** it exits non-zero and reports the offending skill + field

### Story 7.2: End-to-End Customization Lifecycle Integration Test

As a CI pipeline,
I want an end-to-end integration test that exercises the full customization lifecycle — fresh install, interactive override, verify, upstream change, dry-run drift, halt, manual resolution, successful upgrade, lineage recorded,
So that regressions in any lifecycle step fail the build.

**Acceptance Criteria:**

**Given** a CI-provisioned test project
**When** the E2E test runs
**Then** it executes the following sequence and asserts expected state at each step:
  1. Fresh `bmad install` succeeds; `bmad.lock` written; compiled `SKILL.md` at expected path
  2. `bmad-customize` simulated session scaffolds a prose-fragment override under `_bmad/custom/`; override file exists after acceptance
  3. `bmad compile <skill> --diff` confirms the user-facing diff matches the override's expected impact
  4. Simulated upstream fragment change applied
  5. `bmad upgrade --dry-run` reports drift in the affected fragment category
  6. `bmad upgrade` halts with exit code 3 and the user-facing drift message
  7. Simulated manual override edit resolves drift
  8. `bmad upgrade` succeeds with exit 0
  9. `bmad.lock` shows a non-empty `lineage[]` entry for the overridden fragment

**Given** any of the 9 steps failing
**When** the test reports
**Then** the specific failing step is named and the test exits non-zero

### Story 7.3: Model 3 Distribution Matrix Test

As a CI pipeline,
I want a test that installs a Model 3 module in both compiler-present and compiler-absent environments and asserts equivalent installed output,
So that Model 3 fallback is proven to produce byte-equivalent behavior regardless of Python availability.

**Acceptance Criteria:**

**Given** a Model 3 test-fixture module (template source + precompiled fallback)
**When** the test installs it in a compiler-present environment (Python 3.11+)
**Then** compilation from source runs and installed SKILL.md matches expected output

**Given** the same module
**When** the test installs it in a compiler-absent environment (simulated via `--no-python` flag or containerized runtime with Python removed)
**Then** the precompiled fallback installs verbatim
**And** installed SKILL.md is byte-identical to the compiler-present installed output

**Given** a divergence between compile-from-source output and precompiled-fallback output
**When** the test detects it
**Then** the test fails with a per-file hash comparison report

### Story 7.4: Abandoned `bmad-customize` Session Test

As a CI pipeline,
I want a test that opens and abandons a `bmad-customize` session and asserts no files have been written under `_bmad/custom/` and `bmad.lock` is byte-identical to the pre-session state,
So that the no-disk-write-until-accept contract (FR55) is enforced.

**Acceptance Criteria:**

**Given** a fresh install
**When** the test captures the pre-session state (directory listing + `bmad.lock` hash)
**Then** it opens a simulated `bmad-customize` session, drafts content in conversation, and abandons before acceptance

**Given** the session is abandoned
**When** the test captures the post-session state
**Then** the directory listing under `_bmad/custom/` is identical to pre-session
**And** `bmad.lock` hash is byte-identical to pre-session

**Given** any file under `_bmad/custom/` was created or modified during the abandoned session
**When** the test detects the violation
**Then** the test fails and names the offending path

### Story 7.5: Docs Gate, Dogfood-Gate Owner, Success-Metric Resolution

As a release manager,
I want the five required documentation artifacts present and reviewed, a named owner for the `bmad-customize` dogfood gate, and a resolution to the "25% override adoption" success metric,
So that release-blocking items are closed before the release PR merges.

**Acceptance Criteria:**

**Given** a release PR
**When** the release-gate check runs
**Then** it verifies the presence of:
  1. Author migration guide (`docs/compile/author-migration-guide.md` or equivalent)
  2. `bmad-customize` walkthrough (`docs/compile/bmad-customize-walkthrough.md`)
  3. `bmad.lock` schema reference (`docs/compile/bmad-lock-schema.md`)
  4. `--explain` tag vocabulary reference (`docs/compile/explain-vocabulary.md`)
  5. 5-minute quickstart (`docs/compile/quickstart.md`)

> **Resolution (2026-05-09, course-correct):** Paige hard-gate clause removed from AC-1.
> OQ-B (CODEOWNERS for `docs/compile/*`) reverted; Paige approval is not in v1 scope.
> The 5-docs presence check stands as the sole AC-1 deliverable.

**Given** the dogfood gate
**When** release readiness is assessed
**Then** a named owner (person, not team) is responsible for running the `bmad-customize`-survives-own-upgrade test before release and signing off in the release PR

**Given** the PRD's "25% of installs have ≥ 1 override within 90 days" success metric
**When** this story is complete
**Then** the criterion is **explicitly downgraded to a Phase 2 post-release measurement** (rationale: v1 is a Problem-solving MVP, not an experience MVP; no telemetry infrastructure is in-scope; privacy posture per NFR-S1/NFR-S5 favors no-telemetry default)
**And** the replacement ship-gate-observable metric for v1 is: **"`bmad-customize` skill is invoked end-to-end without error in the dogfood test run defined by Story 6.7"** — measurable per DOGFOOD.md procedure (manual release gate, 6-step human-operator sign-off), no network/telemetry required
**And** a Phase 2 backlog item is filed to revisit the 25% metric with either (a) an opt-in post-upgrade installer prompt, or (b) a Discord community survey conducted ≥ 90 days post-GA
**And** this resolution may be overridden by the release manager before Story 7.5 is picked up if telemetry-lite is re-scoped into v1; the override must be recorded in the release PR description

> **Resolution (2026-05-09):** 25% metric downgraded to Phase 2 per Story 7.5 AC-3. v1
> ship-gate metric: "bmad-customize invoked end-to-end without error in Story 6.7 dogfood
> test." Phase 2 follow-up: deferred-work.md (workspace-level entry).

**Given** any **hard-gate** release item is unresolved (docs present, dogfood owner signed off, metric resolved)
**When** the release PR is created
**Then** CI blocks merge until all hard gates pass and named owners have signed off

**Given** the **soft-gate** release item — third-party dogfood migration (Story 7.7) — is incomplete
**When** the release PR is created
**Then** CI does NOT block merge
**And** the release notes include a "Known gaps" entry referencing the incomplete third-party migration and target milestone for follow-up

### Story 7.6: Module Distribution Model Detection (Models 1/2/3)

As a user installing any third-party module,
I want the installer to detect whether the module ships Model 1 (precompiled), Model 2 (template source), or Model 3 (source + precompiled fallback) and install it correctly without user-visible differences,
So that I can install any module uniformly regardless of authoring choice.

**Acceptance Criteria:**

**Given** a module containing only precompiled `SKILL.md` files (no `*.template.md`)
**When** the installer runs
**Then** it detects Model 1 and uses the verbatim-copy path
**And** installed output is byte-identical to source

**Given** a module containing `*.template.md` files (no precompiled `SKILL.md`)
**When** the installer runs
**Then** it detects Model 2, invokes the compiler, and produces compiled `SKILL.md` at install location
**And** behavior is indistinguishable to the user from a Model 1 install

**Given** a module containing both `*.template.md` and precompiled `SKILL.md`
**When** the installer runs on a compiler-present system (Python 3.11+)
**Then** it detects Model 3, compiles from source (preferring source over fallback), and produces compiled output

**Given** the same Model 3 module
**When** the installer runs on a compiler-absent system (no Python 3.11)
**Then** it falls back to the precompiled `SKILL.md` and installs verbatim
**And** installed output matches between compiler-present and compiler-absent environments (Story 7.3 CI matrix enforces the contract)

**Given** a third-party module skill template with `<<include path="core/persona-guard.template.md">>`
**When** the compiler resolves the include
**Then** the core fragment at `src/<core-module>/fragments/persona-guard.template.md` is inlined
**And** the lockfile records the resolved path spanning the module boundary

**Given** a third-party module attempting `<<include path="other-third-party-module/private-fragment.template.md">>`
**When** the compiler resolves
**Then** a `CompilerError` of code `PRECEDENCE_UNDEFINED` is raised (cross-third-party includes not allowed)
**And** explicit namespacing is permitted only for `core/` and the author's own module namespace

### Story 7.7: Third-Party Module Dogfood Migration (Soft Gate)

As a platform maintainer,
I want one real-world third-party module migrated to Model 2 (template source) in coordination with a community contributor,
So that the distribution path is proven on real code before it's relied on by the ecosystem.

**Acceptance Criteria:**

**Given** a candidate third-party module identified in coordination with the core team (e.g., a community-contributed module or similar)
**When** the migration is attempted
**Then** the module lands as Model 2 template source with CI validating byte-equivalent installed output across compiler-present and compiler-absent environments
**And** migration documentation captures any gotchas encountered as guidance for future third-party authors

**Given** the release PR is being prepared
**When** this story is incomplete (no third-party module migrated yet)
**Then** release is NOT blocked
**And** the release notes include a "Known gaps" section noting: "Third-party module dogfood migration pending — planned for follow-up release"
**And** the open status is tracked in the project's post-release backlog

**Given** this story is complete before release
**When** the release PR is prepared
**Then** release notes highlight the successful third-party migration as a confidence signal
