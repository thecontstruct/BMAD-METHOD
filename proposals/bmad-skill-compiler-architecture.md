---
revisionNotes: >-
  v1.1 (2026-04-20) — Course-corrected after absorbing upstream's TOML
  customization system (PR #2284, bf30b697 at-skill-entry renderer,
  a6d075bd fs-native, 8fb22b1a _bmad/custom/ provisioning). Decisions
  3, 5, 6, 8, 10, 13, 15 revised in place. New decisions 16 (lazy
  compile-on-entry), 17 (shared Python library absorbs upstream
  renderer + resolver), 18 (glob inputs tracked as first-class
  compile inputs) appended. Python 3.11+ is the baseline runtime;
  compile engine lives at `src/scripts/bmad_compile/`. Override root
  renamed `_bmad/custom/` throughout.
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - proposals/bmad-skill-compiler-prd.md
  - proposals/bmad-skill-compiler-proposal.md
  - proposals/research-prompt-compilation-landscape.md
  - tools/installer/bmad-cli.js
  - tools/installer/commands/install.js
  - tools/installer/core/installer.js
  - tools/installer/core/manifest.js
  - tools/installer/core/manifest-generator.js
  - tools/installer/core/config.js
  - tools/installer/core/install-paths.js
  - tools/installer/core/existing-install.js
  - tools/installer/file-ops.js
  - tools/installer/ide/manager.js
  - tools/installer/modules/official-modules.js
  - tools/installer/modules/plugin-resolver.js
  - tools/validate-skills.js
  - tools/validate-file-refs.js
  - test/test-installation-components.js
  - src/core-skills/module.yaml
  - src/bmm-skills/module.yaml
workflowType: 'architecture'
project_name: 'BMAD Compiled Skills'
user_name: 'Root'
date: '2026-04-18'
---

# Architecture Decision Document — BMAD Compiled Skills

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements (53 total, 10 categories):**

| Category | FRs | Architectural Implication |
|---|---|---|
| Template Authoring | FR1–7 | Parser for 4 constructs (Markdown, `<<include>>`, `{{var}}`, `{var}`); error taxonomy with file+line reporting |
| Fragment Composition | FR8–12 | Recursive include resolver; cyclic-include detector; byte-for-byte determinism contract |
| User Override Management | FR13–17 | Override-root convention; 5-tier precedence engine; module-boundary enforcement |
| Installation & Upgrade | FR18–24 | Hook compiler into `installer._installAndConfigure()`; smart-install auto-routes to upgrade; verbatim fallback branch |
| Compile Primitives (CLI) | FR25–33 | `bmad compile` as shared engine entrypoint with `--diff`, `--explain`, `--tree`, `--json` adapters |
| Customization Skill | FR34–39 | `bmad-customize` skill consumes `--explain --json` and `--diff`; itself authored as template (dogfood loop) |
| Drift Detection & Lockfile | FR40–43 | `bmad.lock` schema v1 with source/fragment/variable/variant/output hashes; `value_hash` only (no plaintext) |
| IDE Variant Support | FR44–46 | File-naming-based variant (`*.cursor.template.md`, `*.claudecode.template.md`) with universal fallback |
| Module Distribution | FR47–48 | Three distribution models (precompiled / template source / both); cross-module fragment namespace |
| Validation & CI | FR49–53 | `npm run validate:compile` recompiles + diffs lockfile; E2E lifecycle test; Model-3 matrix test |

**Non-Functional Requirements (30 total, 6 categories):**

- **Performance (NFR-P1–4):** ≤10% install overhead; hash-based skip amortizes to ≤5%; per-skill compile ≤500ms; dry-run ≤3s with streamed output.
- **Security (NFR-S1–6):** No plaintext secrets (hash-only in lockfile); override-root containment (reject `..`, out-of-root symlinks); module boundary (modules can't shadow core); `trust_mode: safe` gate for future Python; zero network I/O at compile time; zero new runtime deps.
- **Reliability & Determinism (NFR-R1–5):** Byte-for-byte reproducible across macOS/Linux/Windows; stable resolution order (tier → alphabetical); LF normalization on emit; terminal errors (non-zero exit, no partial writes); lockfile-integrity refusal (no silent recovery; prompt before destructive action when user overrides exist).
- **Compatibility (NFR-C1–5):** Node ≥20; six OS/arch combos in CI; Claude Code + Cursor officially; unmigrated skills byte-identical to pre-compiler baseline; lockfile `version: 1` with fail-loud on unknown versions.
- **Observability (NFR-O1–5):** Lockfile as audit trail; `--explain` full provenance; file+line error messages; dry-run diffable + `--json`; `--debug` to stderr without polluting stdout.
- **Maintainability (NFR-M1–5):** Syntax frozen (4 constructs, breaking change = major bump); test matrix for every adjacent-tier pair of resolution; docs as ship gate; reference skills as contract tests; frozen error-vocabulary names.

**Scale & Complexity:**

- Primary domain: developer-tool subsystem (Node CLI + compile pipeline + lockfile + skill).
- Complexity level: **medium** (per PRD classification) — include resolution, variant selection, override layering, hash lockfile are non-trivial; Level 3+ features deliberately excluded.
- Context: **greenfield subsystem in brownfield** — coexists with verbatim-copy path; compiler is opt-in per module.
- Estimated architectural components: ~8 (template parser, include resolver, variant selector, override layerer, variable resolver, lockfile writer, explain renderer, drift detector) + 3 CLI adapters (`install`/`upgrade`/`compile`) + 1 skill (`bmad-customize`).

### Technical Constraints & Dependencies

- **Runtime:** Node.js ≥ 20.0.0 only (NFR-C1). No Python at runtime in v1 (deferred to Level 3 behind `trust_mode: full`).
- **Dependencies:** Reuse-only. Existing set: `commander`, `fs-extra`, `glob`, `js-yaml`, `xml2js`, `semver`, `@kayvan/markdown-tree-parser`, `chalk`, `picocolors`. No new runtime deps without a release-PR review note (NFR-S6).
- **Packaging:** All compiler code under `tools/installer/compiler/` — not a separate npm package.
- **Install contract:** `npx bmad-method install` must remain the front door. Smart-install routes to upgrade on existing installs. Verbatim-copy branch preserved for unmigrated skills (NFR-C4, regression-suited).
- **Integration seam:** Compiler runs inside `installer._installAndConfigure()` — between `OfficialModules.install()` (copies module files) and `ManifestGenerator.generateManifests()` (scans `SKILL.md`). The installer already emits a `files-manifest.csv` (schema `type,name,module,path,hash`) that the lockfile can extend or supersede.
- **No existing templating:** `validate-file-refs.js:19` explicitly defers `{{mustache}}` as non-goal. Variables are injected only via `generateModuleConfigs()` writing `_bmad/{module}/config.yaml` today.
- **No existing fragment/override mechanism:** But hash-drift infrastructure exists — `detectCustomFiles()` (installer.js:670) compares SHA-256 against `files-manifest.csv` and writes `.bak` on upgrade. That pattern seeds the lockfile-drift approach.
- **Workflow-scoped config.yaml files exist today.** `official-modules.js:472–475` treats module-root `config.yaml` as regenerated (stripped on copy) but **workflow-level `config.yaml` files are copied verbatim**. None ship in core/bmm today, but bmb-created modules and any Phase 2 workflow-step compilation will produce them. The variable resolver accommodates this (see Core Architectural Decisions → Decision 3).
- **`module.yaml` as schema source.** Each module ships `src/<module>/module.yaml` declaring its variable schema: prompts, defaults, `result:` value templates, optional `single-select` options, and a `directories:` list of paths to create. Also explicitly tracks inherited core variables via a `# Variables from Core Config inserted:` comment. The compiler consumes this for `declared-by` attribution, value-template expansion, and derived-directory resolution.
- **Frozen syntax surface:** Four constructs only for v1 (FR1–6); unknown directives must error, not silently pass (FR7, NFR-M1).
- **Frozen error vocabulary:** `UNKNOWN_DIRECTIVE`, `UNRESOLVED_VARIABLE`, `MISSING_FRAGMENT`, `CYCLIC_INCLUDE`, `OVERRIDE_OUTSIDE_ROOT`, `LOCKFILE_VERSION_MISMATCH` (NFR-M5).

### Cross-Cutting Concerns Identified

1. **Determinism is pervasive.** Path normalization (POSIX internal), LF line endings on emit, alphabetical ordering within tier, no clocks or random IDs in output, hash-based skip. Every new code path must uphold this or it leaks into the lockfile as a spurious drift.
2. **Security envelope at every boundary.** Override-root containment, module-boundary enforcement, no network I/O, no plaintext secrets in lockfile, trust-gate for future Python. All I/O is through a thin sandboxed layer, not ad-hoc `fs` calls.
3. **Backward compatibility as first-class branch.** The verbatim-copy path is not a deprecation target; it is a tested, permanent alternative. Any refactor of the installer must preserve unmigrated-skill behavior byte-for-byte (NFR-C4).
4. **Observability threaded through every operation.** Every compile writes a lockfile entry; every interpolation/include is attributable via `--explain`. No silent interpolations, no silent merges.
5. **Two-layer API split.** Mechanical deterministic surface (CLI: `install`/`upgrade`/`compile`) vs. reasoning surface (skill: `bmad-customize`). The skill consumes `compile --explain --json` and `compile --diff` as its only primitives. Never the reverse.
6. **Error ergonomics for authors.** Every compile-time error must name the template file and line (NFR-O3). Error types are frozen vocabulary (NFR-M5). Generic "compile failed" messages are a regression.
7. **Lockfile as the single source of truth.** "What was installed, why, from where" — reproducibility, drift detection, override lineage, audit trail all flow through `bmad.lock`. Schema must be forward-compatible (NFR-C5).
8. **Dogfood loop.** `bmad-customize` skill is itself authored as template source (FR39). The compiler compiles its own consumer — any regression in the compiler breaks the skill's build, which is a ship gate (Business Success dogfood release gate).

### Open Architectural Questions (inherited from PRD §Open Questions)

> **Status:** Both open questions are **RESOLVED** in §Core Architectural Decisions (step 4) and via a corresponding PRD amendment. Summaries below; see the decisions for full rationale.

1. **Override scaffold staging (FR37 ↔ FR38) — RESOLVED.** Resolved in **Decision 8**. The `bmad-customize` skill is a Markdown prompt executed by an LLM in IDE chat, not compiled code. Override drafts happen conversationally in chat context; no file is written under `<override_root>` until the user explicitly accepts. The engine needs no `--with-override-stdin` flag and no staging directory. FR37's "scaffold" is reframed as a chat-time draft; FR38's `compile --diff` becomes a post-write verification (not a pre-write preview). A corresponding new FR ratifies the "no persist until accept" contract.

2. **Upgrade rollback forward-compat — RESOLVED.** Resolved in **Decision 4**. The `bmad.lock` schema v1 carries a `lineage` array on fragment entries (prior `base_hash` values across upgrades) and a `previous_base_hash` field. v1 does not implement `bmad upgrade --rollback`, but the schema is additive and does not foreclose a future implementation. v1 readers ignore unknown fields; v2 can read the lineage trail to reconstruct pre-upgrade state.

## Starter Template Evaluation

### Primary Technology Domain

**Developer-tool subsystem inside an existing Node.js CLI codebase.** The compiler is not a new project; it's a capability added to `bmad-method` v6.3.0, which already ships a full installer, module loader, IDE wiring, manifest generator, and validation suite.

### Starter Options Considered

This workflow step normally surveys new-project starters (Next.js, NestJS, etc.). None apply here. Considered and rejected:

| Option | Why rejected |
|---|---|
| New monorepo (Turborepo / Nx) | Compiler is intentionally bundled inside `bmad-method`, not distributed separately (PRD §Developer Tool Specific Requirements / Packaging). |
| Standalone npm package (`@bmad/compiler`) | Explicit PRD constraint: "All compiler code lives under `tools/installer/compiler/` in the `bmad-method` repo. The compiler is invoked by every CLI subcommand and is not exposed as a separate package in v1." |
| New CLI framework (`oclif`, etc.) | NFR-S6 forbids new runtime deps; existing `commander@14` is already the CLI framework. |
| New language runtime (Rust / Go for speed) | NFR-C1 pins Node ≥ 20; Python is explicitly deferred to Level 3 behind `trust_mode: full`. |

### Selected Starter: existing `bmad-method` repository

**Rationale for Selection:**

- The compiler must hook into `installer._installAndConfigure()` between `OfficialModules.install()` and `ManifestGenerator.generateManifests()`. That seam only exists inside this repo.
- The installer's existing machinery (path resolution, file-ops with hash comparison, IDE manager, manifest writer, quick-update flow) solves at least half the compiler's plumbing for free.
- Zero-new-runtime-deps constraint (NFR-S6) means the compiler inherits the existing dependency set and Node engine requirement.
- Reference skills and CI targets (`npm run validate:skills`, `test:install`) are already wired; the compiler extends rather than replaces them.

**Initialization Command:**

```bash
# No project init. Development happens on a feature branch of the existing repo:
git checkout -b feature/compiled-skills
mkdir -p tools/installer/compiler
# Scaffold the new subdirectory layout (finalized in step 6).
```

**Architectural Decisions Inherited from the "Starter":**

- **Language & Runtime:** JavaScript (CommonJS), Node.js ≥ 20.0.0. `package.json` `"engines": { "node": ">=20.0.0" }` already enforced. No TypeScript in the repo today.
- **CLI framework:** `commander@14` drives `bmad-cli.js`; new subcommands (`upgrade`, `compile`) register via the existing `tools/installer/commands/` pattern.
- **File I/O:** `fs-extra@11` for atomic writes and recursive ops; `glob@11` for pattern matching; existing `file-ops.js` primitives (`copyDirectory`, `syncDirectory`, `getFileHash`) reused as the I/O sandbox layer.
- **YAML / XML:** `js-yaml@4` for configs and lockfile; `xml2js@0.6` available for any XML emitted by `--explain` (though a lightweight string builder is more likely, given the tag vocabulary is frozen and small).
- **Markdown parsing:** `@kayvan/markdown-tree-parser@1.6` available. Template parsing for the 4-construct syntax is likely a hand-rolled regex/state-machine given how restricted the grammar is; the existing parser is kept in reserve if needed for `--explain` rendering.
- **Terminal UX:** `@clack/prompts@1` for interactive confirmation (already used by smart-install); `chalk@4` / `picocolors@1` for TTY coloring (unified-diff output in `compile --diff` uses `picocolors` since ANSI is the v1 format contract).
- **Styling:** N/A (CLI, no UI).
- **Testing framework:** The repo ships `jest@30` (dev dep) and a hand-rolled `test/test-installation-components.js` harness. Compiler tests add to both: jest for unit-level parser/resolver tests, the existing harness for install/upgrade integration tests. The E2E lifecycle test (FR52) lives in the existing harness.
- **Linting / formatting:** `eslint@9` with `eslint-plugin-n`, `eslint-plugin-unicorn`, `eslint-plugin-yml`; `prettier@3`; `markdownlint-cli2`. Compiler code inherits these configs unchanged.
- **Validation / CI:** `npm run validate:skills`, `npm run validate:refs`, `npm run test:install`, `npm run lint`, `npm run lint:md`, `npm run format:check`. Compiler adds one new target: `npm run validate:compile` (FR49) — recompile all templated skills, diff against `bmad.lock`, non-zero on divergence. Wired into the existing `npm run quality` gate.
- **Project structure:** Installer code lives under `tools/installer/{core,commands,modules,ide}/`; compiler slots in as `tools/installer/compiler/` (sibling of `core/`). Skill source moves from `src/{core,bmm}-skills/` today (monolithic `SKILL.md`) to gain optional `*.template.md` + `fragments/` siblings in migrated skills. File structure finalized in step 6.

**Note:** No initialization story needed. First implementation story is the template parser plus a smoke-test compile of one reference skill (likely `bmad-help` — smallest surface, single `{{var}}` interpolation), producing byte-identical output to the current `bmad-help/SKILL.md` to prove the "keep contract" step of the Migration Guide.

## Core Architectural Decisions

### Decision Priority Analysis

**Already decided (locked by PRD / starter — do not revisit):**

- Node ≥ 20, no new runtime deps (NFR-C1, NFR-S6).
- Four-construct syntax frozen: Markdown passthrough, `<<include>>`, `{{var}}`, `{var}` (FR1–6, NFR-M1).
- Fragment resolution precedence: `user-full-skill > user-module-fragment > user-override > variant > base` (FR10).
- Code location: `tools/installer/compiler/` (PRD §Packaging).
- Frozen error vocabulary (NFR-M5): `UNKNOWN_DIRECTIVE`, `UNRESOLVED_VARIABLE`, `MISSING_FRAGMENT`, `CYCLIC_INCLUDE`, `OVERRIDE_OUTSIDE_ROOT`, `LOCKFILE_VERSION_MISMATCH`.
- `bmad.lock` schema v1 shape (FR40, Appendix A, PRD amendment adds `previous_base_hash` / `lineage` / `declared_by` / `template_from` as additive optional fields).
- `--explain` tag vocabulary (Appendix A, frozen; PRD amendment adds `declared-by` / `template-from` as additive optional `<Variable>` attributes).
- `bmad-customize` authoring contract: no persist under `<override_root>` until user accept (FR54, ratified via PRD amendment).

**Critical decisions (block implementation — decided below):**

1. Template parser implementation strategy
2. Fragment resolution engine (walk order, cycle detection)
3. Variable resolver layering & precedence enforcement
4. Lockfile format, path, and relationship to `files-manifest.csv`
5. CLI surface & engine sharing (`install` / `upgrade` / `compile`)
6. Installer integration seam (exact hook point and data flow)
7. IDE variant selection algorithm
8. `bmad-customize` skill override-authoring flow (PRD Open Question #1)
9. Lockfile forward-compat for rollback (PRD Open Question #2)
10. Determinism enforcement strategy (the I/O sandbox)

**Important decisions (shape architecture significantly):**

11. Error class hierarchy & reporting
12. Compile caching (hash-based skip)
13. Distribution-model detection (Model 1 / 2 / 3)
14. Module boundary enforcement
15. `bmad-customize` skill's contract with the compiler

**Deferred (post-v1, explicit anti-goals):**

- Python render functions (Level 3, behind `trust_mode: full`).
- JIT / invoke-time assembly (Level 4).
- Artifact-aware collectors (Level 4).
- LLM-assisted compilation (Level 6).
- Cross-skill references with cycle detection (Level 5).

---

### Decision 1 — Template Parser Implementation

**Problem.** Parse `*.template.md` into an AST the resolver can walk, with file+line reporting for every error class (NFR-O3).

**Options:**

| Option | Pros | Cons |
|---|---|---|
| (a) Hand-rolled Python regex + line tracker | Zero deps (stdlib `re`), fully specifiable, ~200 LOC, grammar is frozen and small (4 constructs including `{{self.*}}`) | Must build line-tracking manually; error-recovery by hand |
| (b) Python third-party parsing lib (`lark`, `parsimonious`, etc.) | Clean grammar file | Violates NFR-S6 (stdlib only) |
| (c) JS parser in the Node layer, pass AST to Python | Could use `@kayvan/markdown-tree-parser` | Cross-process AST marshalling; two languages handling determinism |

**Decision:** **(a) Hand-rolled Python tokenizer + AST builder, stdlib only.** Grammar is frozen at four constructs; a stdlib `re`-based tokenizer with a line-column tracker is sufficient and keeps the implementation fully auditable. The parser lives at `src/scripts/bmad_compile/parser.py`.

**Implications:**

- AST node types (Python dataclasses): `Text`, `Include(src, props, line, col)`, `VarCompile(name, line, col)` where `name` carries the full dotted path (including any `self.` prefix for TOML-sourced), `VarRuntime(name, line, col)`.
- Unknown directive syntax (anything matching `<<...>>` or `{{...}}` not in the four constructs) raises `UnknownDirectiveError` at parse time — never silently passed through (FR7).
- Parser is pure: AST out, no I/O. Deterministic.

---

### Decision 2 — Fragment Resolution Engine

**Problem.** Recursively resolve `<<include>>` chains with cycle detection, stable ordering, and 5-tier precedence (FR10, FR11).

**Options:**

| Option | Pros | Cons |
|---|---|---|
| (a) Depth-first walk with visited-set per compile | Simple, natural for nested includes | Must track resolution path for cycle-error messages |
| (b) Topo-sort first, then inline | Enables parallel resolution; clean cycle detection | Overkill for the sizes involved; harder to localize errors |
| (c) Lazy / memoized resolve | Avoids re-reading shared fragments | Memo cache is another invalidation surface |

**Decision:** **(a) Depth-first walk with a per-compile visited set,** plus a per-compile fragment-content cache keyed by `(resolved-path, tier)` to amortize shared-fragment reads inside one skill's compile. Cycle detection records the include chain so the error message names every step of the loop (`A → B → C → A`). Resolution order within a tier is alphabetical by path (NFR-R2); tiers are walked in precedence order.

**Implications:**

- Resolver signature: `resolve(templateAST, context) → compiledNodes[]`, where `context` carries the tier lookup tables and visited-set.
- Per-compile cache invalidates on every new compile; no cross-compile caching in v1 (keeps determinism auditable).
- Cycle error message: lists the full include chain with file paths, not just the two endpoints.

---

### Decision 3 — Variable Resolver & Precedence (two-namespace cascade, YAML + TOML)

**Problem.** Resolve `{{var}}` against the complete set of config sources bmad reads or generates (YAML *and* TOML), attribute every resolution to its origin for `--explain` output (FR31, Appendix A), emit only value hashes to the lockfile (FR43, NFR-S1), and preserve byte-for-byte reproducibility (NFR-R1).

**Investigation: every config surface bmad currently creates or reads:**

| File / source | Role | Compiler treatment |
|---|---|---|
| `_bmad/core/config.yaml` | Core YAML values: `user_name`, `communication_language`, `document_output_language`, `output_folder` | `bmad-config` tier |
| `_bmad/<module>/config.yaml` (e.g., `bmm`) | Module-specific values + duplicated copy of core values below a `# Core Configuration Values` comment marker (installer.js:819–862) | `module-config` tier for keys above marker; keys below are attributed to `bmad-config` |
| `<module>/<workflow-path>/config.yaml` | Workflow- or skill-scoped YAML config; installer copies verbatim (`official-modules.js:472–475`). None in core/bmm today; bmb-created modules and Phase 2 produce them | Attributed to `module-config` in v1 `--explain` (disambiguated via `source-path`); dedicated `workflow-config` enum value reserved for v2 |
| `<skill>/customize.toml` | TOML defaults for a skill's structured customization (declared per-field `prompt`, `default`, `result` etc.) | `toml` source, `toml-layer: defaults`. Values accessed via `{{self.<dotted.path>}}` |
| `_bmad/custom/<skill>.toml` | TOML team override layer (committable convention) | `toml` source, `toml-layer: team` |
| `_bmad/custom/<skill>.user.toml` | TOML user override layer (gitignored convention) | `toml` source, `toml-layer: user` |
| `_bmad/_config/manifest.yaml` | Install metadata (versions, modules, IDEs) | Not a value source; used only to populate derived-tier values |
| `_bmad/_config/{files-manifest,skill-manifest,agent-manifest,bmad-help}.csv`, `_bmad/<module>/module-help.csv` | Registries and help catalogs | Not value sources |
| **`_bmad/custom/[<module>/[<workflow-path>/]]config.yaml`** | User's persistent YAML variable overrides; most-specific path wins within the tier | `user-config` tier |
| CLI flags at this invocation | One-shot overrides (`bmad install --user-name=X`, `bmad compile --var-NAME=VALUE`, etc.) | `install-flag` tier (applies to both namespaces) |
| `process.env` | Reserved for future use | `env` — **not emitted or read in v1** |
| Computed at compile time (allowlisted) | Install paths, version sentinels, current-invocation identifiers, `module.yaml` `directories:` resolved | `derived` tier |
| `src/<module>/module.yaml` | **Schema source** (not a value source): declares prompts, defaults, `result:` templates, `single-select` options, `directories:` list, inherited-variables comment | Drives `declared-by` attribution, value-template expansion, derived-directory computation |

**Two parallel precedence cascades (v1):**

The `self.*` namespace is lexically distinct from non-`self.` names, so the two cascades never collide. Each `{{name}}` reference resolves in exactly one cascade based on whether its dotted path starts with `self.`.

**Non-`self.` cascade (YAML-sourced, highest → lowest):**

1. **`install-flag`** — CLI flags at the current invocation.
2. **`user-config`** — `_bmad/custom/[<module>/[<workflow-path>/]]config.yaml`; most-specific path wins.
3. **`module-config`** — `<module>/config.yaml` (keys above core-marker), plus workflow-scoped YAML files.
4. **`bmad-config`** — `core/config.yaml`, and keys below the core-marker in module configs.
5. **`derived`** — computed allowlist.

**`self.*` cascade (TOML-sourced, highest → lowest):**

1. **`install-flag`** — CLI flags that specifically target TOML paths (e.g., a hypothetical `--self-agent-icon=X`); same tier as YAML install-flag.
2. **`toml/user`** — `_bmad/custom/<skill>.user.toml`.
3. **`toml/team`** — `_bmad/custom/<skill>.toml`.
4. **`toml/defaults`** — `<skill>/customize.toml`.

TOML merge within the `self.*` cascade uses upstream's structural rules (scalars: override wins; tables: deep merge; arrays-of-tables with shared `code`/`id`: merge-by-key; other arrays: append). When an array value is produced by structural merge across multiple layers, the resolver attributes the composite value to `toml-layer: merged` and emits `contributing-paths` listing every contributing file.

**`env` is dropped from both v1 cascades.** Process state breaks determinism (NFR-R1) and NFR-S5. Reserved in the enum only.

**Provenance correctness — handling the installer's core-spread:**

The installer duplicates core values into each module's `config.yaml` for runtime convenience. The compiler's YAML module-config parser splits on the `# Core Configuration Values` comment marker: keys above → `module-config` candidates; keys below → discarded (authoritative core value comes from `core/config.yaml` and attributes to `bmad-config`). A module that legitimately overrides a core key authors it above the marker.

**Derived values — computed once at engine init, frozen into scope, never re-computed during the run:**

| Variable | Value | Computed from |
|---|---|---|
| `install_root` | POSIX path to `_bmad` | install-paths |
| `project_root` | POSIX path to project root | install-paths |
| `module_root` | POSIX path to current module directory | `install_root / currentModule` |
| `bmad_version` | BMAD semver | `package.json` |
| `module_version` | Installed module's semver | `manifest.yaml` |
| `current_module` | Module ID being compiled | invocation parameter |
| `current_skill` | Skill ID being compiled | invocation parameter |
| `current_variant` | Selected IDE variant or `universal` | Variant selector output |
| `installed_modules` | Comma-joined sorted list of module IDs | manifest entries, alphabetical |

**Explicitly NOT derived in v1:** wall-clock timestamps, `os.*`, hostname, arbitrary filesystem enumeration, random IDs. Hashes appear only in the lockfile, never in compiled output.

**`module.yaml` role (schema metadata):**

The compiler reads each installed module's `module.yaml` once at engine init, building per-module:
- **declared-variables set** (keys with `prompt:`/`default:`) → enables `declared-by`.
- **inherited-variables set** (parsed from `# Variables from Core Config inserted:` comment).
- **value-template map** (`result:` shapes) → applied during resolution, produces `template-from` attribution.
- **directories list** → populates `derived` entries.

**TOML customize.toml role (per-skill structured defaults, `self.*` source):**

At compile init for a given skill, the resolver loads the skill's TOML layer stack in order: `customize.toml` (defaults) → `_bmad/custom/<skill>.toml` (team) if exists → `_bmad/custom/<skill>.user.toml` (user) if exists. Each layer is parsed by stdlib `tomllib`. Layers are merged via the shared `bmad_compile.toml_merge` library (same code consumed by upstream's `resolve_customization.py` — see Decision 17). The merged result is flattened into a `self.*` name table with per-leaf provenance (which layer contributed; for merged arrays, which layers contributed and the `contributing-paths` list). Each `{{self.<dotted.path>}}` reference resolves by dotted-path lookup into this table.

**Implications:**

- `VariableScope.resolve(name) → ResolvedValue` where `ResolvedValue` carries `value, source, source_path?, toml_layer?, contributing_paths?, base_source_path?, declared_by?, template_from?`. Engine never re-reads the filesystem during resolution; scope is pre-materialized and frozen.
- Unknown variable raises `UnresolvedVariableError` with a cascade-specific "tried tiers" remediation hint.
- Lockfile records `value_hash: sha256(value)` — never plaintext (NFR-S1, FR43). For `source: toml`, additional fields (`toml_layer`, `contributing_paths?`) are recorded.
- For `derived`, lockfile and `--explain` use a symbolic `source-path` of `derived://<name>`.
- Workflow-scoped YAML files are resolved and attributed to `module-config` in v1 with `source-path` disambiguation.

---

### Decision 4 — Lockfile Format, Path, Relationship to `files-manifest.csv`

**Problem.** `bmad.lock` must be the audit trail for compile operations, survive upgrades, support rollback forward-compat, and not duplicate `files-manifest.csv` which already records per-file hashes.

**Options:**

| Option | Pros | Cons |
|---|---|---|
| (a) Extend `files-manifest.csv` with compile columns | Single manifest; minimal churn | CSV can't represent nested structure (fragments-per-skill, variables-per-skill); no YAML ergonomics |
| (b) Separate `bmad.lock` (YAML) at `_bmad/_config/bmad.lock`; `files-manifest.csv` unchanged | Clean separation of install-level vs. compile-level audit; YAML matches PRD schema v1; CSV stays generic | Two artifacts to keep in sync |
| (c) Single JSON lockfile | Machine-readable; no YAML ambiguity | PRD schema is YAML; existing configs are YAML |

**Decision:** **(b) Separate `bmad.lock` (YAML) at `_bmad/_config/bmad.lock`.** `files-manifest.csv` retains its role as the install-level hash registry (input to `detectCustomFiles()` and upgrade `.bak` decisions) and is unchanged. The lockfile is strictly compile-audit; skills that are verbatim-copied (not compiled) have no lockfile entry. Compiler is the sole writer.

**Forward-compat for rollback (PRD Open Question #2):** The v1 lockfile carries a `previous_base_hash` field (upstream base hash from the prior compile) and a `lineage` array (append-only history of `{bmad_version, base_hash, override_hash}` per overridden fragment). v1 does not implement rollback; v1 writers populate both fields unconditionally. This enables a future `bmad upgrade --rollback` to reconstruct pre-upgrade state from the lockfile alone — no parallel snapshots, no delta chain. Both fields are additive optional; v1 readers tolerate them gracefully (PRD amendment Appendix A Stability section codifies the rule).

**Schema v1 reference:** See PRD §Public API Surface → Lockfile and PRD Appendix A. Schema includes: `version`, `compiled_at` (release-pinned sentinel, not wall-clock, per NFR-R1), `bmad_version`, `entries[]` per skill with `source_hash`, `fragments[]` (`resolved_from`, `hash`, `base_hash`, `previous_base_hash`, `override_hash`, `override_path`, `lineage`), `variables[]` (`source`, `source_path`, `declared_by`, `template_from`, `value_hash`), `variant`, `compiled_hash`.

**Implications:**

- `compiled_at` is pinned to the BMAD release semver (or a deterministic sentinel), not `new Date()` — otherwise CI runs would drift byte-for-byte.
- Lockfile is YAML-serialized via `js-yaml` with stable key ordering and LF line endings.
- Malformed lockfile halts the CLI with `LOCKFILE_VERSION_MISMATCH` and instructs `bmad install` fresh; when user overrides exist on disk, prompt first (NFR-R5).

---

### Decision 5 — CLI Surface, Python Engine, Node Adapters

**Problem.** All three subcommands (`install`, `upgrade`, `compile`) route to the same compile engine with different input sets (PRD §Technical Architecture Considerations — "Single-engine plumbing, layered porcelain"). The engine is now in Python (Option A from the course-correct); Node hosts the CLI and installer.

**Decision:** **One Python engine module, one build-time entry point, Node CLI adapters that shell out.**

- Shared library: `src/scripts/bmad_compile/` (Python package, stdlib only). Modules: `parser.py`, `resolver.py`, `toml_merge.py`, `variants.py`, `io.py`, `errors.py`, `lockfile.py`, `explain.py`, `lazy_compile.py`.
- Build-time entry: `src/scripts/compile.py`. Invoked as `python3 src/scripts/compile.py --skill <id> --install-dir <path> [--dry-run] [--diff] [--explain] [--tree|--json] [--with-content] ...`. Emits JSON to stdout (compile result, `--diff`, `--explain --json`) or plain text (`--diff` TTY mode, `--explain` default). Non-zero exit on error; error detail on stderr.
- Runtime entry: `src/scripts/lazy_compile.py` (invoked by the SKILL.md shim at skill entry — see Decision 16).
- Upstream TOML resolver (`src/scripts/resolve_customization.py`) is refactored to import from `bmad_compile.toml_merge` (Decision 17).
- Node adapters in `tools/installer/commands/`:
  - `install.js` — existing; the module-install callback invokes `python3 src/scripts/compile.py --install-phase ...` for each migrated skill after `OfficialModules.install()` copies files.
  - `upgrade.js` — new; wraps engine invocation with `--dry-run` + drift-calculator output aggregation; emits `--json` for `bmad-customize` triage.
  - `compile.js` — new; direct `python3 compile.py` passthrough with arg forwarding.
- Node is responsible for argv parsing, user prompts (`@clack/prompts`), TTY coloring, orchestration. Python owns all template parsing, fragment resolution, variable resolution, TOML merge, lockfile I/O, `--explain` rendering. File I/O for compile inputs/outputs is done by Python via its own sandbox (`bmad_compile/io.py`).
- `bmad` remains the primary binary name (already the shorter of two in `package.json`); `bmad-method` remains alias.

**Process-boundary contract:**

- Node passes arguments only (paths, skill IDs, flags) — not file contents.
- Python reads inputs from disk, writes outputs to disk (compiled SKILL.md, bmad.lock), emits structured JSON to stdout for ephemeral outputs (`--diff`, `--explain --json`, `upgrade --dry-run --json`).
- Node parses Python's stdout for adapter-level decisions (e.g., "exit non-zero because drift detected"); propagates Python's exit code and stderr to the user.
- No long-lived Python subprocess; each invocation is cold-start (stdlib-only, so ~50ms overhead — within NFR-P2 budget).

**Implications:**

- `bmad-customize` skill calls `bmad compile <skill> --explain --json` and `bmad compile <skill> --diff` and `bmad upgrade --dry-run --json` via the IDE's shell tool — Node CLI on top, Python engine underneath, no direct engine import (Decision 15).
- Every adapter shares flags `--directory`, `--modules`, `--tools`, `--override-root`, `--yes`, `--debug` (FR24). `--override-root` defaults to `_bmad/custom/`.
- Error taxonomy (Decision 11) is implemented in Python; Node adapters propagate. Frozen error codes (NFR-M5) remain the public contract regardless of which runtime raises them.

---

### Decision 6 — Installer Integration Seam (Node shells to Python)

**Problem.** Wire the Python compile engine into `installer._installAndConfigure()` without breaking the verbatim-copy path (NFR-C4).

**Decision:** **Post-copy, pre-manifest Node→Python shell-out.** The Node installer runs `OfficialModules.install()` as today to copy raw module files into the install location, then before `ManifestGenerator.generateManifests()` scans `SKILL.md`, the Node adapter spawns `python3 src/scripts/compile.py --install-phase --install-dir <bmadDir> [--skill <id>]` which:

1. Enumerates migrated skills (detected by presence of `*.template.md` in the copied-to-install-location tree).
2. Per migrated skill: loads templates + fragments + `customize.toml` stack + YAML configs, resolves via the shared library, writes compiled `SKILL.md` to the install location, emits the lockfile entry.
3. Returns structured JSON to stdout summarizing per-skill outcomes; Node parses and passes to the existing `installedFiles` set callback.

For non-migrated skills (no `*.template.md`), the copied files are left untouched. `ManifestGenerator.generateManifests()` then runs unchanged on a directory tree that looks uniform to it — preserves the validate-skills contract.

**SKILL.md shim integration:** For skills the compiler owns, the "SKILL.md" at the install location is NOT the compiled output directly — it is (a) the compiled content or (b) upstream's stdout-dispatch shim (`b0d70766`) that invokes `lazy_compile.py` at skill entry. The compiler writes the compiled output to a canonical location the shim reads from (e.g., `<skill-dir>/SKILL.md.compiled`) and keeps the shim's `SKILL.md` stub in place; the shim either emits the compiled file directly (fast path) or invokes `lazy_compile.py` if staleness is suspected. See Decision 16 for the full lazy-compile contract.

Alternatively, if coordination with the shim proves fragile, the compiler writes directly to `SKILL.md` (no shim for compiled skills) and the lazy-compile guard is wired as a separate pre-read hook the IDE invokes. Implementation detail; the PRD's externally-visible contract (SKILL.md is always fresh at skill entry) is what matters. Chosen approach is finalized during implementation of this integration story.

**Implications:**

- The `installedFiles` callback that `_installAndConfigure()` already maintains (installer.js:584) is updated from Python-side JSON output; Node merges compiled outputs into the set that the manifest generator later scans.
- Templates (`*.template.md`) are deleted from the install location after compile — they're build-time artifacts (NFR-O2 implies only compiled output is visible at runtime). `customize.toml` is NOT deleted — the lazy-compile guard needs it and the TOML resolver pattern requires its presence.
- `quickUpdate()` (installer.js:1145) runs the compiler in "recompile-only" mode: no re-copy, just `python3 compile.py --recompile-all` against possibly-updated configs.
- `fs-native.js` (upstream-introduced in `a6d075bd`) replaces `fs-extra` for all Node-side I/O touching installed files. Python side uses its own stdlib I/O through `bmad_compile/io.py`.

---

### Decision 7 — IDE Variant Selection Algorithm

**Problem.** Select `*.cursor.template.md` vs `*.claudecode.template.md` vs universal `*.template.md` based on the `--tools` flag, with universal fallback guaranteed (FR44–46).

**Decision:** **Filename-suffix-parsed variant selection with deterministic fallback.**

1. Parse filename: `name[.<variant>].template.md` where `<variant>` ∈ `{cursor, claudecode}` (enumerated, not open-ended — matches PRD supported IDEs for v1; new variants require a major bump of the variant enum).
2. For target IDE `<T>`: prefer `name.<T>.template.md`; else `name.template.md` (universal); else error (`MISSING_FRAGMENT`).
3. Multiple IDEs in `--tools`: compile once per IDE; lockfile records `variant: <T>` per skill; compiled outputs live in per-IDE directories (matching current IDE manager behavior).
4. Unknown variant suffix on a filename: `UNKNOWN_DIRECTIVE` (treat unrecognized dotted suffix as unknown vocabulary).

**Implications:**

- Variant enum is extended only by PRs that bump the platform-codes enum in `tools/installer/ide/platform-codes.yaml`; compiler reads the IDE list from that existing registry, not a hard-coded constant.
- Explain output shows `<Include ... resolved-from="variant" variant="cursor">` only when a variant was actually selected; universal inclusions render as `resolved-from="base"`.

---

### Decision 8 — `bmad-customize` Skill Flow Across Three Planes + Drift Triage

**Problem.** `bmad-customize` is a Markdown skill executed by an LLM in IDE chat. It operates conversationally. Course-correct extended its scope to cover three customization planes (TOML structured fields, prose fragments, YAML variables) + drift triage.

**Authoring flow (v1, per-plane routing):**

1. **Discovery (calls CLI).** Skill invokes `bmad compile <skill> --explain --json` via the IDE's shell tool. Returns the full customization surface: structured TOML fields with defaults + currently-resolved values + per-field provenance; prose fragments with resolved-from tier + active content; compile-time variables (`{{self.*}}` TOML-sourced and non-`self.` YAML-sourced) with source + source-path + declared-by.
2. **Intent mapping (chat-only).** LLM reasons over the JSON to identify which plane the user's request maps to:
   - Metadata/icon/principle/step/menu → TOML plane → target file `_bmad/custom/<skill>.user.toml` (or `<skill>.toml` if team scope)
   - Prose wording of instructions, greetings, explanations → prose plane → target file `_bmad/custom/fragments/<module>/<skill>/<name>.template.md`
   - Variable-value change (e.g., `output_folder`) → YAML plane → target file `_bmad/custom/config.yaml` (or `<module>/config.yaml`)
   - Full-skill rewrite → full-skill plane → target file `_bmad/custom/fragments/<module>/<skill>/SKILL.template.md`
3. **Active-content presentation (chat-only).** LLM shows the user the current value (from explain JSON).
4. **Draft (chat-only, iterative).** LLM drafts the edit as text in chat. User reviews/refines. **No disk writes during this phase** (FR54).
5. **User acceptance.** LLM uses its file-write tool to write the override file at the plane-appropriate path.
6. **Post-write verification (calls CLI).** LLM invokes `bmad compile <skill> --diff` (shows compiled-SKILL.md-level impact across both planes, since the compiler merges TOML values into `{{self.*}}` references at compile time and applies prose overrides too).
7. **Final compile.** Implicit on next `bmad install`/`upgrade`, or explicit `bmad compile <skill>`, or lazy at next skill entry.

**Drift-triage flow (new, post-course-correct — FR56):**

1. User runs `bmad upgrade`; CLI detects drift (prose / TOML / glob / variable-provenance) and halts with non-zero exit (FR57), pointing user to `bmad-customize`.
2. User invokes `bmad-customize` with drift-triage intent.
3. Skill calls `bmad upgrade --dry-run --json`; receives structured per-entry drift report.
4. For each drift entry, skill applies per-type UX in chat:
   - **Prose fragment drift** → three-way side-by-side (upstream-old / upstream-new / user-override); keep / adopt-upstream / author-merged-override.
   - **TOML default-value drift** → field-path + old-default / new-default / user-value; keep / adopt-new-default / rewrite-override.
   - **TOML orphan** → "field removed upstream; override no longer applies"; remove-override offered.
   - **TOML new-default awareness** → informational; no action required.
   - **Glob-input drift** → show added/removed matches and content changes; informational unless intersecting a field-level override.
5. For each decision, skill writes the appropriate file (FR54 contract preserved).
6. After all entries are triaged, skill instructs user to re-run `bmad upgrade`.

**Engine adjustments (two, small):**

- `bmad compile <skill> --explain --json` includes resolved active content of every fragment by default (for step 3 above without a separate file read).
- `bmad upgrade --dry-run --json` emits structured per-entry drift report (for the triage flow).
- No `--with-override-stdin` flag. No staging directory. `_bmad/custom/` is the only place any override ever exists.

**Implications:**

- PRD §Open Questions item 1 resolved without a new filesystem convention. FR54/FR55 ratified.
- Skill handles "I changed my mind" by editing or deleting the written file; next recompile picks up the change.
- Engine remains pure: takes filesystem state, produces compiled output + lockfile. No special preview mode.
- Triage is a new skill-mode, not a new CLI path. The only CLI addition is `upgrade --dry-run --json`.

---

### Decision 9 — Lockfile Forward-Compat for Rollback (PRD Open Question #2, RESOLVED)

Resolved inside **Decision 4**: `previous_base_hash` and `lineage` fields on fragment entries. v1 writers populate them; v1 does not implement rollback. Future major version can add `bmad upgrade --rollback` that reads the lineage trail to reconstruct pre-upgrade state from the lockfile alone. Additive and documented via the PRD amendment.

---

### Decision 10 — Determinism Enforcement Strategy (the I/O Sandbox)

**Problem.** NFR-R1 demands byte-identical output across macOS/Linux/Windows. Common sources of drift: path separators, line endings, filesystem enumeration order, clocks, hash hexcase.

**Decision:** **All Python compile-engine I/O goes through `src/scripts/bmad_compile/io.py`** which:

- Normalizes paths to POSIX internally (`pathlib.PurePosixPath`).
- Reads files with explicit `encoding='utf-8'`, converts CRLF → LF on ingest.
- Writes files with LF line endings (`newline='\n'`) and no BOM.
- Sorts directory listings alphabetically by POSIX path (case-sensitive) — never relies on `os.listdir` / `pathlib.Path.iterdir` native order.
- Rejects filesystem escapes: any path that resolves outside its declared root (override-root `_bmad/custom/`, install-root `_bmad/`, project-root for glob expansion) raises `OverrideOutsideRootError`. Symlinks that cross roots are rejected via `Path.resolve(strict=True)` + ancestor containment check.
- Uses `hashlib.sha256(...).hexdigest()` — stdlib guarantees lowercase hex. Files are hashed in binary mode so platform newline conversion never affects hashes.

The Python engine never calls `open` or `pathlib` I/O directly outside `io.py`; repo Python linter config bans raw file operations elsewhere in `bmad_compile/`.

The Node side uses `fs-native.js` (upstream-introduced in `a6d075bd`) for installer coordination, manifest scanning, `.bak` handling, and network fetches. Compile-time I/O (Python `io.py`) and installer-time I/O (Node `fs-native.js`) are deliberately separate sandboxes — they enforce different contracts (Python's for determinism; Node's for atomic multi-module install without graceful-fs monkey-patching).

**Implications:**

- NFR-S2 (override root containment + glob containment) is enforced at `io.py`, not scattered throughout the engine.
- CI runs a three-OS determinism check (NFR-R1) that compiles the reference skill set on macOS + Linux + Windows and diffs outputs byte-for-byte. Both runtimes (Python 3.11 + Node 20) are tested on each OS.
- `fs-extra` is NOT reintroduced on the Node side (replaced upstream in `a6d075bd`); the compiler subsystem does not regress that fix.

---

### Decision 11 — Error Class Hierarchy

**Decision:** One `CompilerError` base class with `code` (frozen enum), `file`, `line`, `col`, and `chain?` (for cycles) fields. Subclasses for each code:

- `UnknownDirectiveError` → `UNKNOWN_DIRECTIVE`
- `UnresolvedVariableError` → `UNRESOLVED_VARIABLE`
- `MissingFragmentError` → `MISSING_FRAGMENT`
- `CyclicIncludeError` → `CYCLIC_INCLUDE`
- `OverrideOutsideRootError` → `OVERRIDE_OUTSIDE_ROOT`
- `LockfileVersionMismatchError` → `LOCKFILE_VERSION_MISMATCH`

All errors format via a shared renderer that emits the file + line + code + remediation hint. CLI converts to non-zero exit (FR51). No partial writes on any error (NFR-R4) — engine stages output in memory and commits only on success.

---

### Decision 12 — Compile Caching (Hash-Based Skip)

**Decision:** The engine computes a canonical input hash per skill from `(source_hash, [fragment_hash...], [variable_hash...], variant)`. If the lockfile's `compiled_hash` for that skill matches *and* no input hash has changed, the compile is skipped for that skill and the existing compiled output + lockfile entry are retained. This amortizes re-installs and CI runs to ≤ 5 % overhead (NFR-P1).

Skip path is observable via `--debug`; the lockfile timestamp / `compiled_at` is not updated when skipped (keeps the audit trail stable).

---

### Decision 13 — Distribution-Model Detection

**Decision:** The installer inspects each module at copy time:

- Module contains `*.template.md` files → Model 2 or Model 3 candidate. If compiler is present → compile. If a `precompiled/` shadow directory exists and compiler is absent → Model 3 fallback (use precompiled). If compiler absent *and* no fallback → hard error (module author must ship one).
- Module contains only `SKILL.md` (no templates) → Model 1 (verbatim copy).

Detection is per-module, not per-skill, to keep module boundaries clean. FR53 covers the CI matrix.

---

### Decision 14 — Module Boundary Enforcement

**Decision:** Cross-module fragment includes use an explicit namespace: `<<include path="core/persona-guard.template.md">>` means *core* module's fragment, not a relative path. The include resolver:

1. Resolves `core/…` against the core module's fragment tree (lives under `_bmad/core/fragments/` at install; under `src/core-skills/fragments/` in the source repo).
2. Resolves `<moduleId>/…` against that module's fragments.
3. Bare relative paths (`fragments/…`, `./…`) resolve within the current skill's own module.
4. A module declaring a fragment at the same namespaced path as core raises a namespace-collision error at install time (NFR-S3), *not* a shadowing of core. Modules cannot shadow core; only the end user can (via override root).

---

### Decision 15 — `bmad-customize` Skill Contract with the Compiler (widened)

**Decision:** The skill's only inputs from the compiler are:

1. **`bmad compile <skill> --explain --json`** → structured provenance with resolved fragment content AND structured TOML field defaults + current values + per-field layer attribution AND variable values with source / declared-by / template-from. This is the discovery / intent-mapping / active-content primitive.
2. **`bmad compile <skill> --diff`** → unified diff (for post-write verification after the skill persists an accepted override on any plane).
3. **`bmad upgrade --dry-run --json`** (new) → structured per-entry drift report covering prose fragments, TOML defaults, TOML orphans, TOML new-defaults, glob-input changes, and variable-provenance shifts. This is the drift-triage primitive.

The skill never imports the compile engine, never reads `bmad.lock` directly, and never writes to disk except to persist an accepted override (on one of the three planes). This is a hard architectural boundary — the mechanical / reasoning split (PRD §Two-layer design).

**Implications:**

- Any future capability the skill needs must first appear as a CLI flag on `bmad compile` or `bmad upgrade`, not as a new skill-to-engine import path.
- The skill is authored as `*.template.md` + fragments + `customize.toml` (FR39) and compiled by the same engine — the dogfood loop is enforced by CI (every release recompiles the skill across both planes; any regression fails the build).
- The skill is responsible for per-plane routing of user intent (Decision 8) but does NOT need to understand the merge semantics of either plane — both `--explain --json` (for currently-resolved values) and `--dry-run --json` (for drift) present already-computed state.

---

### Decision 16 — Lazy Compile-on-Entry as Cache-Coherence Guard

**Problem.** Users edit TOML overrides (`_bmad/custom/<skill>.user.toml`) and project-context files (matched by `file:` globs in `persistent_facts`) at any time and expect changes to take effect on the next skill invocation without running a manual `bmad compile`. Upstream shipped a runtime Python template renderer (`bf30b697`) to serve that UX. If the compiler bakes all values at install time, the user loses "edit and go" — unacceptable.

**Decision: replace the runtime renderer with a cache-coherence guard that lazily recompiles on input drift.**

At skill entry, the SKILL.md shim (upstream `b0d70766`'s stdout-dispatch mechanism) invokes `python3 -m bmad_compile.lazy_compile <skill>`. The guard:

1. Reads the skill's `bmad.lock` entry for the tracked-input hash manifest.
2. For each tracked input, computes the current hash:
   - Source template + all included fragments → hash each file.
   - YAML config files (core, module, workflow-scoped, user-config) → hash each.
   - TOML layer files (`customize.toml`, team, user) → hash each.
   - Each `glob_inputs[]` entry → re-evaluate glob against current filesystem, produce sorted match list, compute `match_set_hash` of `{path, content_hash}` pairs; compare against lockfile's `match_set_hash` as fast early-out; on fast-match, hash each current match's content for content-drift check.
3. If every tracked input hash matches the lockfile → emit `SKILL.md` bytes unchanged to stdout (fast path, target ≤50 ms per NFR-P5).
4. If any mismatch → invoke the same compile engine that `bmad compile <skill>` would invoke, write new `SKILL.md` + new lockfile entry, emit the new bytes (slow path, target ≤500 ms per NFR-P2).

**What the guard is NOT:**

- Not a template renderer. No substitution, no TOML merge, no `{var}` resolution happens inside the guard. Those happen only when the compile engine runs.
- Not invoke-time content assembly (Level 4). Level 4 is forbidden (explicit anti-goal). The guard is mechanical cache coherence — it re-runs the same deterministic compile that would have run at install time.

**Concurrency:**

At skill entry the IDE may invoke the guard for multiple skills simultaneously, or a single skill concurrently on fast keystrokes. The guard acquires an advisory file-lock (`flock` POSIX / `LockFileEx` Windows) on a sibling `.compiling.lock` file for the skill's install directory during recompile. If locked, a concurrent invocation waits on the winner and re-reads the newly-written `SKILL.md` rather than recompiling.

**What replaces upstream's renderer:**

- `bf30b697`'s runtime renderer → replaced by `lazy_compile.py`.
- `{var}` substitution behavior — **removed.** `{var}` now means "emitted unchanged; LLM is the sole consumer." Any upstream template relying on Python-side `{var}` substitution migrates to `{{var}}` or `{{self.*}}` in the same PR as the compiler lands.
- `resolve_customization.py` (TOML resolver invoked at skill entry) — **subsumed.** The guard's recompile runs the TOML merge via the shared library (Decision 17); there is no separate TOML resolution at skill entry.

**Behavioral contract:**

- `SKILL.md` on disk is the exact bytes the LLM will read.
- `SKILL.md` is up to date relative to every tracked input at the moment the LLM reads.
- There is no runtime substitution; what you see at `--explain` is what the LLM sees (minus the diagnostic XML tags).

**Implications:**

- Lockfile integrity is critical. A stale/malformed lockfile either falsely misses a drift (wrong content shown to LLM) or falsely triggers unnecessary recompiles (perf regression). NFR-R5 already covers refusing to proceed on malformed lockfile.
- CI must exercise the lazy path: a test that installs, edits a TOML user override, invokes the shim, asserts the emitted SKILL.md reflects the edit without any explicit `bmad compile` call.
- NFR-P5 (≤50 ms fast path) is a new budget specifically for the guard.

---

### Decision 17 — Shared Python Library Absorbs Upstream Renderer + Resolver

**Problem.** Upstream ships two Python components today: `resolve_customization.py` (TOML merge at skill entry) and the runtime template renderer (`bf30b697`, `{var}` substitution at skill entry). The compiler needs the same TOML merge logic at build time. Two implementations of TOML merge = bug factory.

**Decision: one Python library, multiple entry points.**

**Library layout (`src/scripts/bmad_compile/`):**

```
bmad_compile/
    __init__.py
    parser.py         # template tokenizer + AST builder (Decision 1)
    resolver.py       # variable resolver (Decision 3) — two cascades
    toml_merge.py     # TOML layer merge (upstream's structural rules, shared)
    variants.py       # IDE variant selection (Decision 7)
    io.py             # deterministic I/O sandbox (Decision 10)
    errors.py         # CompilerError hierarchy (Decision 11)
    lockfile.py       # lockfile reader + writer + hash builder (Decision 4)
    explain.py        # --explain renderer (Markdown/XML, tree, JSON)
    lazy_compile.py   # skill-entry cache-coherence guard (Decision 16)
    engine.py         # top-level orchestrator (build-time compile)
```

**Entry points:**

```
src/scripts/
    compile.py        # build-time entry; invoked by Node CLI adapters (install / upgrade / compile)
                      # uses: engine, parser, resolver, toml_merge, variants, io, errors, lockfile, explain
    resolve_customization.py  # refactored — thin shim over bmad_compile.toml_merge
                              # signature + stdout behavior unchanged for backward compat with upstream consumers
```

**Relationship to upstream code:**

1. **`resolve_customization.py`** (existing, from `bd1c0053`/`0dbfae67`): refactored. Its merge logic is extracted into `bmad_compile.toml_merge.merge_layers(defaults, team, user) → merged`. The shim retains its CLI interface and stdout contract (returns merged TOML) so any existing consumer scripts or skill-entry invocations keep working. Same test suite upstream has for the resolver is ported / adapted.

2. **`bf30b697`'s runtime renderer** (quick-dev at-skill-entry template substitution): replaced by `lazy_compile.py`. The SKILL.md shim (`b0d70766`) that currently invokes the renderer is updated to invoke `lazy_compile.py` instead. Templates that depend on `{var}` Python substitution at skill entry are migrated to `{{var}}` / `{{self.*}}` as part of the compiler-rollout PR (the migrated set is the same 6 agents upstream migrated to TOML — a coordinated change).

**Shared state between the compile engine and the lazy-compile guard:**

- Same `lockfile.py` code (reader/writer).
- Same `resolver.py` (variable resolution for both cascades).
- Same `toml_merge.py` (identical merge output for same inputs).
- Same `io.py` (determinism sandbox).
- Different `__main__` logic: `engine.py` does full compile (parse, resolve, merge, write, lockfile); `lazy_compile.py` does hash-check + conditional `engine.compile_one(skill_id)`.

**What this is NOT:**

- Not a new FR — the upstream-shipped capabilities (TOML merge, runtime rendering) are consolidated in implementation, not scope-expanded.
- Not a takeover of runtime rendering as a compiler concern — `lazy_compile.py` is cache coherence, not rendering.
- Not a breaking change to upstream's external contract — `resolve_customization.py` keeps its CLI surface for any out-of-tree consumer.

**Migration sequencing:**

1. Land the shared library with `parser/resolver/toml_merge/io/errors/lockfile/explain/engine`.
2. Refactor `resolve_customization.py` to import from `bmad_compile.toml_merge` (behavior-preserving; validated against upstream's existing tests).
3. Land `compile.py` and the Node CLI adapters (`install`/`upgrade`/`compile`).
4. Land `lazy_compile.py` and update the SKILL.md shim to use it instead of the runtime renderer.
5. Migrate `{var}` → `{{var}}`/`{{self.*}}` usages in the migrated-agent set; delete the runtime renderer code from upstream.

**Implications:**

- One source of truth for TOML merge, variable precedence, path normalization, hash computation, error vocabulary.
- Upstream maintainers are stakeholders for this refactor; the PR that lands the compiler touches their code and needs their review. Coordinate via GitHub discussion before implementation.
- Regression risk during refactor is contained to TOML merge (widely covered by upstream tests) + runtime-renderer contract (narrower surface, tested by existing skill entry-point tests).

---

### Decision 18 — Glob Inputs Tracked as First-Class Compile Inputs

**Problem.** `customize.toml` fields like `persistent_facts` accept entries prefixed with `file:` that must glob against the filesystem and inline the matching file contents into the skill. The matched files can change independently of any bmad command (user edits project-context.md; user adds new matching file). Lazy compile-on-entry (Decision 16) must detect these changes to stay coherent.

**Decision: compile-time glob expansion + lockfile-tracked match set + guard-time re-evaluation.**

**At compile time:**

1. For each `file:`-prefixed entry in a merged TOML array (after layer merge), substitute `{project-root}`-style derived variables in the pattern.
2. Glob deterministically against the filesystem; sort matches alphabetically by POSIX path.
3. Read each matched file through the I/O sandbox (UTF-8, CRLF→LF normalization).
4. Inline matched content at the TOML field's render location in the compiled output, wrapped in `<TomlGlobExpansion>` + `<TomlGlobMatch>` tags when `--explain` is active (plain content when emitting real `SKILL.md`).
5. Record a `glob_inputs[]` entry in the lockfile with: `pattern` (pre-substitution), `resolved_pattern` (post-substitution), `source: toml`, `toml_layer`, `source_path` (the TOML file that contained the pattern), `toml_field` (dotted path into merged TOML), `match_set[]` (sorted list of `{path, hash}`), `match_set_hash` (hash of the sorted list for fast comparison).

**At skill entry (lazy-compile guard — Decision 16):**

1. For each `glob_inputs[]` entry in the lockfile:
   - Re-substitute derived vars in the pattern (same `project_root` as install state → same pattern).
   - Re-glob against the current filesystem.
   - Sort matches alphabetically.
   - Compute `match_set_hash` of the current matches (path + content hash).
   - Compare against lockfile's `match_set_hash`. If mismatch → staleness detected → recompile.
2. If `match_set_hash` matches → fast path.

**Two-stage comparison optimization:**

- Stage 1: `match_set_hash` is a single hash over `[(path_1, hash_1), (path_2, hash_2), …]`. If this matches, the entire match set is unchanged — neither the set of matched files nor any individual file's content. Fast out.
- Stage 2: only needed when authoring `--debug` output or when `match_set_hash` changes — walk the per-match list to identify which matches were added/removed/modified. Used by `bmad upgrade --dry-run --json` (FR41) for drift reporting.

**Authoring guidance (documented):**

- Prefer narrow globs (`{project-root}/docs/*.md`, `{project-root}/standards/*.md`) over broad (`{project-root}/**/*`).
- CI linter warns on `**`-heavy patterns that could match >100 files.
- Author-facing migration guide documents the pattern conventions.

**Containment:**

- Patterns that resolve outside `{project-root}` are rejected at compile with `OverrideOutsideRootError` (symmetric with override-root containment per NFR-S2).
- Symlinked matches that point outside `{project-root}` are rejected at read time.

**Performance bound:**

- Glob re-evaluation + hashing of ≤20 matches totalling ≤500 KB: <20 ms on a warm FS, within NFR-P5's 50 ms fast-path budget.
- Degenerate globs (10,000+ matches in a monorepo `**/*.md`) exceed budget; author-side guidance is the mitigation, CI linter the enforcement.

**Provenance:**

- `--explain` emits `<TomlGlobExpansion pattern="..." toml-layer="..." source-path="..." toml-field="..." match-count="N">` wrapping `<TomlGlobMatch path="..." hash="...">` per file, with file content inlined inside each match tag (Appendix A).
- `--json` emits the same as a structured node (see Appendix A).

**Drift detection and triage (ties to FR41 / FR56):**

- `bmad upgrade --dry-run --json` reports glob-input drift as a dedicated entry type when match_set_hash differs. Per-drift payload: pattern, old match-set, new match-set (with per-file add/remove/modify classification).
- `bmad-customize` triage UX for glob-input drift is typically informational (globs auto-incorporate new matches); flagged for action only when a user override layers on top of the relevant TOML field.

**Implications:**

- Lockfile grows with globbed files, proportional to match count. Narrow globs are cheap; wide globs are expensive.
- Edge case: file deleted between compile and skill entry → re-glob sees smaller set → mismatch → recompile (recompile handles the gone-file naturally).
- Edge case: file added between compile and skill entry → re-glob sees larger set → mismatch → recompile → new file content incorporated.
- Edge case: file content changed, name unchanged → per-match hash differs → mismatch → recompile.
- All three edge cases covered by the same mechanism: re-glob + re-hash on guard invocation.

---

### Decision Impact Analysis

**Implementation sequence (revised):**

1. **Foundation:** Decision 1 (parser), Decision 10 (I/O sandbox), Decision 11 (error classes), Decision 17 (shared library skeleton).
2. **Core resolution:** Decision 2 (fragment resolver), Decision 3 (variable resolver with two cascades), `bmad_compile.toml_merge` (refactored from `resolve_customization.py`).
3. **Variant selection:** Decision 7.
4. **Globs:** Decision 18 (glob expansion + lockfile tracking).
5. **Lockfile:** Decision 4 (full schema incl. toml_customization, glob_inputs, lineage).
6. **CLI + installer integration:** Decision 5 (Python engine + Node adapters), Decision 6 (installer hook), Decision 13 (distribution-model detection), Decision 14 (module boundary).
7. **Lazy compile:** Decision 16 + refactor SKILL.md shim to use `lazy_compile.py`.
8. **Skill integration:** Decision 15 (widened contract), Decision 8 (skill flow + drift triage).
9. **Optimizations:** Decision 12 (hash-based skip at build time).

**Cross-component dependencies:**

- `bmad_compile.io` (Decision 10) is a singleton imported by every other module. A regression here breaks determinism everywhere.
- `bmad_compile.toml_merge` (Decision 17) is consumed by both the compile engine and the refactored `resolve_customization.py`. Upstream's existing TOML merge tests guard behavior.
- `lockfile.py` (Decision 4) is the append-only API shared by build-time compile (Decision 5) and lazy-compile guard (Decision 16). Both read the schema; only build-time compile writes.
- CLI adapters (Decision 5) assume engine idempotence. Decision 12 (caching) preserves idempotence — skip path must be observationally indistinguishable from a full recompile.
- `resolver.py` (Decision 3) is the most inter-connected — it consumes install-paths, manifest, module.yaml schemas, all config tiers, TOML layer stack. Changes ripple through `<Variable>` emission, lockfile variable entries, and derived-value consumers.
- `lazy_compile.py` (Decision 16) has zero independent rendering logic — it's a thin orchestrator over `engine.compile_one()`. Every correctness property of build-time compile applies to lazy compile by construction.
