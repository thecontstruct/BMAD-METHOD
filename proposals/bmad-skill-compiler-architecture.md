---
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
| (a) Hand-rolled regex + line tracker | Zero deps, fully specifiable, ~200 LOC, grammar is frozen and small (4 constructs) | Must build line-tracking manually; error-recovery by hand |
| (b) `@kayvan/markdown-tree-parser@1.6` (existing dep) | Already in the tree; proper AST | Parser is general-purpose Markdown, not template-aware; `<<include>>` / `{{var}}` aren't directives it understands |
| (c) New PEG / parser-combinator dep | Clean grammar file | Violates NFR-S6 (no new deps) |

**Decision:** **(a) Hand-rolled tokenizer + AST builder.** Grammar is frozen at four constructs; a regex + line-column tracker is sufficient and keeps the implementation fully auditable. `@kayvan/markdown-tree-parser` is held in reserve for rendering `--explain` output (inline XML tags in emitted Markdown) where a proper tree walker helps.

**Implications:**

- AST node types: `Text`, `Include { src, props, line, col }`, `VarCompile { name, line, col }`, `VarRuntime { name, line, col }`.
- Unknown directive syntax (anything matching `<<...>>` or `{{...}}` not in the four constructs) raises `UNKNOWN_DIRECTIVE` at parse time — never silently passed through (FR7).
- Parser output is deterministic and pure; no I/O during parse.

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

### Decision 3 — Variable Resolver & Precedence

**Problem.** Resolve `{{var}}` against the complete set of config sources bmad reads or generates, attribute every resolution to its origin for `--explain` output (FR31, Appendix A), emit only value hashes to the lockfile (FR43, NFR-S1), and preserve byte-for-byte reproducibility (NFR-R1).

**Investigation: every config surface bmad currently creates or reads:**

| File / source | Role | Compiler treatment |
|---|---|---|
| `_bmad/core/config.yaml` | Core values: `user_name`, `communication_language`, `document_output_language`, `output_folder` | `bmad-config` tier |
| `_bmad/<module>/config.yaml` (e.g., `bmm`) | Module-specific values + duplicated copy of core values below a `# Core Configuration Values` comment marker (installer.js:819–862) | `module-config` tier for keys above marker; keys below are attributed to `bmad-config` to preserve provenance |
| `<module>/<workflow-path>/config.yaml` (e.g., `bmm/workflows/orchestrate-story/config.yaml`) | Workflow- or skill-scoped config; installer copies verbatim (`official-modules.js:472–475`). None in core/bmm today; bmb-created modules and Phase 2 workflow-step compilation produce them. | New semantic tier, surfaced as `module-config` in v1 `--explain` (disambiguated via `source-path`); dedicated `workflow-config` enum value is reserved for v2 |
| `_bmad/_config/manifest.yaml` | Install metadata (versions, dates, modules, IDEs) | Not a value source; used only to populate derived-tier values (`module_version`, `bmad_version`) |
| `_bmad/_config/{files-manifest,skill-manifest,agent-manifest,bmad-help}.csv`, `_bmad/<module>/module-help.csv` | Registries and help catalogs | Not value sources |
| **`<override_root>/[<module>/[<workflow-path>/]]config.yaml`** *(new)* | User's persistent variable overrides; most-specific path wins within the tier | `user-config` tier |
| CLI flags at this invocation | One-shot overrides (`bmad install --user-name=X`, `bmad compile --var-NAME=VALUE`, etc.) | `install-flag` tier |
| `process.env` | Reserved for future use | `env` tier — **not emitted or read in v1**; PRD Appendix A retains the enum value; compiler never touches `process.env` for variable resolution |
| Computed at compile time (allowlisted) | Install paths, version sentinels, current-invocation identifiers, `module.yaml` `directories:` resolved | `derived` tier |
| `src/<module>/module.yaml` | **Schema source** (not a value source): declares prompts, defaults, `result:` templates, `single-select` options, `directories:` list, and inherited-variables comment | Drives `declared-by` attribution, value-template expansion, derived-directory computation |

**Precedence (highest → lowest), v1:**

1. **`install-flag`** — CLI flags at the current `install` / `upgrade` / `compile` invocation. Explicit user intent at the moment of execution outranks everything persisted.
2. **`user-config`** — `<override_root>/[<module>/[<workflow-path>/]]config.yaml`. Most-specific path wins within this tier (e.g., module-scoped override beats root-scoped).
3. **`module-config`** — `<module>/config.yaml`, keys above the `# Core Configuration Values` marker. In v1 also used for workflow-scoped `<module>/<workflow-path>/config.yaml` values, with `source-path` disambiguating which file supplied the value.
4. **`bmad-config`** — `core/config.yaml`, and keys below the core-marker in module configs.
5. **`derived`** — computed allowlist (see table below).

**`env` is dropped from the active v1 tier list.** Process state breaks determinism (NFR-R1) and NFR-S5's "no ambient state" spirit. Reserved in the Appendix A enum only; the compiler never reads `process.env` and never emits `source="env"`.

**Provenance correctness — handling the installer's core-spread:**

The installer duplicates core values into each module's `config.yaml` for runtime convenience (installer.js:819–862). If the compiler naively read module-config first, every core value would be wrongly attributed to `module-config`. Mitigation:

- The compiler's module-config parser splits the YAML by the `# Core Configuration Values` comment marker. Keys above → `module-config` candidates; keys below → discarded (authoritative core value comes from `_bmad/core/config.yaml` and attributes to `bmad-config`).
- A module that legitimately overrides a core key for its own scope authors it *above* the marker, making the override module-scoped by convention. This is a compiler-recognized convention documented in the module-author migration guide.

**Derived values: what, where from, when computed:**

Computed **once per compile invocation** at compile-engine init (immediately after `InstallPaths.create()`, before any template parse). Frozen into `VariableScope` and never re-computed during the run. Same install state → same derived values across runs (NFR-R1).

Source inputs:
- `paths` object from `InstallPaths.create()` (`tools/installer/core/install-paths.js:7`): `srcDir`, `version`, `projectRoot`, `bmadDir`, `configDir`, `coreDir`, `isUpdate`.
- `_bmad/_config/manifest.yaml` — installation/module version blocks (no timestamps consumed).
- Compile invocation parameters: `currentModule`, `currentSkill`, `currentVariant`.

**Initial v1 derived allowlist** (enumerated, no arbitrary computation):

| Variable | Value | Computed from |
|---|---|---|
| `install_root` | Absolute POSIX path to `_bmad` | `paths.bmadDir` |
| `project_root` | Absolute POSIX path to project root | `paths.projectRoot` |
| `module_root` | Absolute POSIX path to current module directory | `paths.moduleDir(currentModule)` |
| `bmad_version` | BMAD semver | `paths.version` (from `package.json`) |
| `module_version` | Installed module's semver | `manifest.yaml` entry for `currentModule` |
| `current_module` | Module ID being compiled | Compile invocation parameter |
| `current_skill` | Skill ID being compiled | Compile invocation parameter |
| `current_variant` | Selected IDE variant or `universal` | Variant selector output (Decision 7) |
| `installed_modules` | Comma-joined sorted list of installed module IDs | Manifest module entries, sorted alphabetically |

**Explicitly NOT derived in v1:** wall-clock timestamps, `os.*`, `os.userInfo()`, hostname, arbitrary filesystem enumeration, random IDs, UUIDs. Hashes appear only in the lockfile, never in compiled output.

**`module.yaml` role (schema metadata, not a value source):**

The compiler reads each installed module's `module.yaml` once at engine init, building:

- Per-module **declared-variables set** (keys with `prompt:` / `default:` blocks) — enables `declared-by` attribution.
- Per-module **inherited-variables set** (parsed from the `# Variables from Core Config inserted:` comment block) — same declaration convention, declared-by still attributes to the originating module (e.g., `core`).
- Per-module **value-template map** (the `result: "{project-root}/{value}"` shape) — applied during resolution so `output_folder` emits `<project-root>/_bmad-output` everywhere it's referenced; produces the `template-from` attribute on `<Variable>` tags.
- Per-module **directories list** (resolved against the `VariableScope`) — populates `derived` entries for variables like `planning_artifacts`, `implementation_artifacts`, `project_knowledge`.

**Implications:**

- `VariableScope.resolve(name) → { value, source, source_path?, declared_by?, template_from? }`. Engine never re-reads the filesystem during resolution; scope is pre-materialized and frozen.
- Unknown variable raises `UNRESOLVED_VARIABLE` with a "tried tiers: install-flag (no), user-config (no), module-config (no), bmad-config (no), derived (not allowlisted)" remediation hint (NFR-O3).
- `--explain` output and lockfile entries carry `declared-by` / `declared_by` and `template-from` / `template_from` per the PRD amendment.
- Lockfile records `value_hash: sha256(value)` — never plaintext (NFR-S1, FR43).
- For `derived`, lockfile and `--explain` use a symbolic `source-path` of the form `derived://<name>` so consumers can disambiguate without leaking state.
- Workflow-scoped `<module>/<workflow-path>/config.yaml` values are resolved and attributed to `module-config` in v1 output; the dedicated `workflow-config` enum value activates in a future major version.

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

### Decision 5 — CLI Surface & Engine Sharing

**Problem.** All three subcommands (`install`, `upgrade`, `compile`) route to the same `compile()` engine with different input sets (PRD §Technical Architecture Considerations — "Single-engine plumbing, layered porcelain").

**Decision:** **One engine module, three command adapters.**

- Engine lives at `tools/installer/compiler/engine.js`, exporting `compile(skillInputs) → { compiledMarkdown, lockEntry, explain }`.
- Adapters in `tools/installer/commands/`:
  - `install.js` — existing; augmented to call the engine on migrated skills, verbatim-copy on unmigrated.
  - `upgrade.js` — new; wraps engine with `--dry-run`, `--reconcile`, and drift calculator.
  - `compile.js` — new; direct engine invocation for power users / CI / `bmad-customize`.
- Engine is deterministic and stateless (aside from its per-invocation fragment cache).
- `bmad` is the primary binary name (already the shorter of the two in `package.json`); `bmad-method` remains as alias.

**Implications:**

- `bmad-customize` skill calls `bmad compile <skill> --explain --json` and `bmad compile <skill> --diff` via the IDE's shell tool — no direct engine import (Decision 15).
- Every adapter shares flags `--directory`, `--modules`, `--tools`, `--override-root`, `--yes`, `--debug` (FR24).

---

### Decision 6 — Installer Integration Seam

**Problem.** Wire the compiler into `installer._installAndConfigure()` without breaking the verbatim-copy path (NFR-C4).

**Decision:** **Post-copy, pre-manifest hook.** The compiler runs *after* `OfficialModules.install()` has copied raw module files into the install location, and *before* `ManifestGenerator.generateManifests()` scans `SKILL.md`. For each migrated skill directory (detected by presence of `*.template.md`), the compiler:

1. Loads templates + fragments from the copied files.
2. Resolves includes, variants, variables, overrides.
3. Writes compiled `SKILL.md` to the install location, replacing any placeholder.
4. Emits a `bmad.lock` entry.

For non-migrated skills (no `*.template.md`), the copied files are left untouched. `ManifestGenerator.generateManifests()` then runs unchanged on a directory tree that looks uniform to it — preserves the validate-skills contract for both paths.

**Implications:**

- The `installedFiles` callback that `_installAndConfigure()` already maintains (installer.js:584) is updated by the compiler to include only *final* compiled outputs, not the intermediate templates (which are not installed).
- Templates are deleted from the install location after compile — they're build-time artifacts, not runtime (NFR-O2 implies only compiled output is visible at runtime).
- `quickUpdate()` (installer.js:1145) runs the compiler in "recompile-only" mode: no re-copy, just re-resolve against possibly-updated configs.

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

### Decision 8 — `bmad-customize` Skill Override-Authoring Flow (PRD Open Question #1, RESOLVED)

**Problem.** `bmad-customize` is a Markdown skill executed by an LLM in IDE chat, not compiled code. It can't "pipe to stdin" or "atomic-rename a staging file" as mechanical operations — it operates conversationally.

**Flow (v1):**

1. **Discovery (calls CLI).** Skill invokes `bmad compile <skill> --explain --json` via the IDE's shell tool. Receives structured provenance: every fragment, every variable, their resolution tiers and current values.
2. **Intent mapping (chat-only).** LLM reasons over the JSON to identify which fragment / variable / full-skill the user's natural-language request maps to. Negotiates ambiguity with the user in chat (FR36).
3. **Active content presentation (chat-only).** LLM presents the active fragment content to the user as a Markdown code block in the conversation — pulled from the explain JSON (enhanced, see engine adjustment below) or via an IDE read-tool on the resolved fragment path.
4. **Draft override (chat-only, iterative).** LLM proposes the edit as text in chat. User reviews, asks for adjustments, refines. **No disk writes during this phase.** The "preview" the user sees during drafting is a conversational before/after rendered by the LLM, not a compile-output diff.
5. **User acceptance.** User signals acceptance. LLM uses its file-write tool to write the override file at `<override_root>/<module>/fragments/<name>.template.md` (or the equivalent for a variable / full-skill override).
6. **Post-write verification (calls CLI).** LLM invokes `bmad compile <skill> --diff` against the currently-installed `SKILL.md`. CLI computes the diff between the installed file and the recompiled output (which now picks up the just-written override). LLM surfaces this final compiled-output diff to the user as confirmation.
7. **Final compile.** Either implicit (next `bmad install` / `bmad upgrade`) or explicit (`bmad compile <skill>`) to write the new compiled `SKILL.md` to its install location.

**PRD FR37 / FR38 semantics reframed (via PRD amendment):**

- **FR37** — "scaffolds override file(s)" is now a **chat-time draft** rendered as content in the conversation. No filesystem artifact during drafting.
- **FR38** — `bmad compile --diff` is a **post-write verification step**, not a pre-write preview.

**Ratified FR54** (added via PRD amendment): *No override content is written to any path under `<override_root>` during the drafting phase of a `bmad-customize` session. The override root is modified strictly on explicit user acceptance, and only at the final override path (never to a staging subdirectory).*

**Ratified FR55** (added via PRD amendment): *CI runs a test that exercises an abandoned `bmad-customize` session and asserts no new files under `<override_root>` and `bmad.lock` is byte-identical to its pre-session state.*

**Engine adjustment (single, small):**

- `bmad compile <skill> --explain --json` **includes the resolved active content** of every fragment by default. This lets the skill present the active text without a separate file read. No separate flag needed.
- No `--with-override-stdin` flag. No staging directory. The committed override root is the only place an override ever exists.

**Implications:**

- PRD §Open Questions item 1 is resolved without a new filesystem convention and without changing the 5-tier fragment precedence contract (FR10).
- Skill is responsible for graceful "I changed my mind" handling — user can edit or delete the written override file, and a recompile picks up the change.
- Engine remains pure: takes filesystem state, produces compiled output and lockfile entry. No special "preview" mode.

---

### Decision 9 — Lockfile Forward-Compat for Rollback (PRD Open Question #2, RESOLVED)

Resolved inside **Decision 4**: `previous_base_hash` and `lineage` fields on fragment entries. v1 writers populate them; v1 does not implement rollback. Future major version can add `bmad upgrade --rollback` that reads the lineage trail to reconstruct pre-upgrade state from the lockfile alone. Additive and documented via the PRD amendment.

---

### Decision 10 — Determinism Enforcement Strategy (the I/O Sandbox)

**Problem.** NFR-R1 demands byte-identical output across macOS/Linux/Windows. Common sources of drift: path separators, line endings, filesystem enumeration order, clocks, hash hexcase.

**Decision:** **All compiler I/O goes through `tools/installer/compiler/io.js`** which:

- Normalizes paths to POSIX internally (`path.posix.normalize`).
- Reads files as UTF-8, converts CRLF → LF on ingest.
- Writes files with LF line endings and no BOM.
- Sorts directory listings alphabetically (by POSIX path, case-sensitive).
- Rejects filesystem escapes: any path that resolves outside its declared root (e.g., override-root, install-root) raises `OVERRIDE_OUTSIDE_ROOT` or equivalent — also rejects symlinks that cross roots.
- Uses SHA-256 with lowercase hex (`toString('hex')` guarantees lowercase; spec-pinned in docs).

The engine never calls `fs.*` directly — always via the sandbox. Lint rule: `no-restricted-imports` bans `fs` and `fs-extra` from `tools/installer/compiler/**` except `io.js` itself.

**Implications:**

- NFR-S2 (override containment) is enforced at this layer, not scattered throughout the engine.
- CI runs a three-OS determinism check (NFR-R1) that compiles the reference skill set on macOS + Linux + Windows and diffs outputs byte-for-byte.

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

### Decision 15 — `bmad-customize` Skill Contract with the Compiler

**Decision:** The skill's only inputs from the compiler are:

1. `bmad compile <skill> --explain --json` → structured provenance with resolved fragment content (for discovery / intent mapping / active-content presentation).
2. `bmad compile <skill> --diff` → unified diff (for post-write verification).

The skill never imports the engine, never reads the lockfile directly, and never writes to disk except to persist an accepted override. This is a hard architectural boundary — the mechanical / reasoning split (PRD §Two-layer design).

**Implications:**

- Any future capability the skill needs must first appear as a CLI flag on `bmad compile`, not as a new skill-to-engine import path.
- The skill is authored as `*.template.md` + fragments (FR39) and compiled by the same engine — the dogfood loop is enforced by CI (every release recompiles the skill; any regression fails the build).

---

### Decision Impact Analysis

**Implementation sequence:**

1. Decision 1 (parser) + Decision 10 (I/O sandbox) + Decision 11 (error classes) — foundation; no dependencies.
2. Decision 2 (fragment resolver) + Decision 3 (variable resolver) — built on 1 + 10 + 11.
3. Decision 7 (variant selection) — wraps 2.
4. Decision 4 (lockfile) — consumes 2 + 3 output.
5. Decision 5 (CLI adapters) + Decision 6 (installer seam) — integration.
6. Decision 15 (`bmad-customize` contract) + Decision 13 (distribution model) + Decision 14 (module boundary) — cross-cutting, enforced through 2 + 6.
7. Decision 8 (`bmad-customize` flow) — requires engine's `--explain --json --with-content` output (enhancement inside Decision 15).
8. Decision 12 (cache) — optimization; deferrable to end of v1.

**Cross-component dependencies:**

- The I/O sandbox (Decision 10) is a singleton — every other component imports from it; a regression here breaks determinism for all.
- The lockfile writer (Decision 4) has read+write access; every other component is write-only on the lockfile, via an append-only API.
- The CLI adapter pattern (Decision 5) assumes the engine is idempotent; Decision 12 (caching) preserves idempotence — skip path must be observationally indistinguishable from a full recompile.
- Variable resolver (Decision 3) is the most inter-connected: consumes `InstallPaths` output, manifest, `module.yaml` schema, all config tiers, and the `VariableScope`. A change here ripples through `<Variable>` tag emission, lockfile variable entries, and all derived-value consumers.
