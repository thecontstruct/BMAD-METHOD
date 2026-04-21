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

  v1.2 (2026-04-20) — Aligned with upstream PR #2285 (central
  config.toml + bmad-skill-manifest.yaml removal, commit 4405b817)
  and PR #2287 (17 bmm-skills moved to customize.toml with
  workflow.md deletions, commit ffdd9bc6). Decision 3 resolver gains
  a fourth input surface: the four-layer central TOML
  (`_bmad/config.toml`, `_bmad/config.user.toml`,
  `_bmad/custom/config.toml`, `_bmad/custom/config.user.toml`)
  emitted by the installer and merged by `resolve_config.py`;
  agent-roster fields (`code`, `name`, `title`, `icon`,
  `description`) now originate in each module's `module.yaml`
  `agents:` block and flow into the `self.agent.*` namespace via
  those layers. Install tree diagram updated to show the central
  config files. Areas-for-Future-Enhancement wording on workflow-
  step compilation clarified to distinguish step-Markdown
  compilation (future) from workflow metadata (already owned by
  upstream `customize.toml`, out of v1 compiler scope).
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'complete'
completedAt: '2026-04-20'
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
- **Frozen error vocabulary:** `UNKNOWN_DIRECTIVE`, `UNRESOLVED_VARIABLE`, `MISSING_FRAGMENT`, `CYCLIC_INCLUDE`, `OVERRIDE_OUTSIDE_ROOT`, `LOCKFILE_VERSION_MISMATCH`, `PRECEDENCE_UNDEFINED` (NFR-M5).

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
- Frozen error vocabulary (NFR-M5): `UNKNOWN_DIRECTIVE`, `UNRESOLVED_VARIABLE`, `MISSING_FRAGMENT`, `CYCLIC_INCLUDE`, `OVERRIDE_OUTSIDE_ROOT`, `LOCKFILE_VERSION_MISMATCH`, `PRECEDENCE_UNDEFINED`.
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
| `_bmad/config.toml` | **Central TOML, base-team layer** (installer-emitted per PR #2285, commit 4405b817): team install answers + agent roster | `toml` source, `toml-layer: central-base-team`. Roster fields exposed as `self.agent.*` |
| `_bmad/config.user.toml` | **Central TOML, base-user layer** (installer-emitted, gitignored): user install answers | `toml` source, `toml-layer: central-base-user` |
| `_bmad/custom/config.toml` | **Central TOML, custom-team layer** (installer-stubbed, committed): team-scope overrides of central fields | `toml` source, `toml-layer: central-custom-team` |
| `_bmad/custom/config.user.toml` | **Central TOML, custom-user layer** (installer-stubbed, gitignored): personal overrides of central fields | `toml` source, `toml-layer: central-custom-user` |
| `_bmad/_config/manifest.yaml` | Install metadata (versions, modules, IDEs) | Not a value source; used only to populate derived-tier values |
| `_bmad/_config/{files-manifest,skill-manifest,bmad-help}.csv`, `_bmad/<module>/module-help.csv` | Registries and help catalogs | Not value sources. `agent-manifest.csv` was removed in PR #2285 — agent roster now derived from `module.yaml` + central TOML merge |
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
2. **`toml/user`** — `_bmad/custom/<skill>.user.toml` (per-skill user layer).
3. **`toml/team`** — `_bmad/custom/<skill>.toml` (per-skill team layer).
4. **`toml/defaults`** — `<skill>/customize.toml` (per-skill defaults).
5. **`toml/central-custom-user`** — `_bmad/custom/config.user.toml` (central user overrides, PR #2285).
6. **`toml/central-custom-team`** — `_bmad/custom/config.toml` (central team overrides, PR #2285).
7. **`toml/central-base-user`** — `_bmad/config.user.toml` (central base user answers, PR #2285).
8. **`toml/central-base-team`** — `_bmad/config.toml` (central base team answers + agent roster, PR #2285).

Per-skill TOML layers (tiers 2–4) are lexically scoped to the skill being compiled; the central TOML layers (tiers 5–8) are process-global and contribute the agent-roster surface (`self.agent.*`) plus any install-answer values that module.yaml schemas promote into templates. Tiers 5–8 match the four-layer merge order that upstream's `resolve_config.py` implements (base-team → base-user → custom-team → custom-user); the compiler's resolver produces the same merged view and records `toml-layer` provenance per leaf so `--explain` output can trace any value back to the originating file.

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

**Central TOML role (process-global agent roster + install answers, `self.*` source):**

The resolver additionally loads the four central TOML files once per engine init (not per skill) and merges them via `bmad_compile.toml_merge` in upstream's `resolve_config.py` order: `_bmad/config.toml` (base-team) → `_bmad/config.user.toml` (base-user) → `_bmad/custom/config.toml` (custom-team) → `_bmad/custom/config.user.toml` (custom-user). The merged central view is unioned into the per-skill `self.*` name table: central leaves occupy lower precedence than the per-skill stack (per the 8-tier cascade above), so a skill's `customize.toml` default can shadow a central base value if both declare the same path, and per-skill team/user overrides continue to win over everything central. Agent-roster fields (`self.agent.code`, `self.agent.name`, `self.agent.title`, `self.agent.icon`, `self.agent.description`) are declared schema-first in each module's `module.yaml` `agents:` block (PR #2285 relocated these from the now-removed `bmad-skill-manifest.yaml`); their values are whatever the merged central TOML produces, with the module.yaml declaration supplying defaults and `declared-by` attribution.

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
- `PrecedenceUndefinedError` → `PRECEDENCE_UNDEFINED` (cross-plane customization interaction not covered by §Cross-Plane Precedence Matrix)

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
6. **Hash-based skip (MANDATORY, not optional):** Decision 12 (compile caching). NFR-P1's ≤5% overhead for unchanged-skill re-installs is achievable only with the skip path. Ships alongside the lockfile because the skip path uses the lockfile as its cache-coherence source of truth, and the lazy-compile guard (Decision 16) depends on the same hash-match logic.
7. **CLI + installer integration:** Decision 5 (Python engine + Node adapters), Decision 6 (installer hook), Decision 13 (distribution-model detection), Decision 14 (module boundary).
8. **Lazy compile:** Decision 16 + refactor SKILL.md shim to use `lazy_compile.py`.
9. **Skill integration:** Decision 15 (widened contract), Decision 8 (skill flow + drift triage).

**Cross-component dependencies:**

- `bmad_compile.io` (Decision 10) is a singleton imported by every other module. A regression here breaks determinism everywhere.
- `bmad_compile.toml_merge` (Decision 17) is consumed by both the compile engine and the refactored `resolve_customization.py`. Upstream's existing TOML merge tests guard behavior.
- `lockfile.py` (Decision 4) is the append-only API shared by build-time compile (Decision 5) and lazy-compile guard (Decision 16). Both read the schema; only build-time compile writes.
- CLI adapters (Decision 5) assume engine idempotence. Decision 12 (caching) preserves idempotence — skip path must be observationally indistinguishable from a full recompile.
- `resolver.py` (Decision 3) is the most inter-connected — it consumes install-paths, manifest, module.yaml schemas, all config tiers, TOML layer stack. Changes ripple through `<Variable>` emission, lockfile variable entries, and derived-value consumers.
- `lazy_compile.py` (Decision 16) has zero independent rendering logic — it's a thin orchestrator over `engine.compile_one()`. Every correctness property of build-time compile applies to lazy compile by construction.

## Implementation Patterns & Consistency Rules

### Pattern Categories Defined

This is a compile pipeline + CLI tool with a Python library, Node CLI adapters, and a cross-process boundary between them. The canonical web-app conflict categories (DB tables, REST endpoints, frontend state) do not apply. Ten conflict surfaces for multiple AI agents implementing this codebase:

1. Cross-language process boundary (Node ↔ Python).
2. Python library layering and import discipline.
3. Determinism — enforced as a **boundary**, not a checklist (see §Determinism).
4. Error message format + remediation-hint quality bar.
5. Lockfile YAML serialization + schema evolution.
6. Test organization — unit / integration / golden-file / three-OS determinism.
7. Logging channels — stdout vs stderr.
8. Naming conventions per language and per artifact type.
9. File layout conventions.
10. Contract surfaces — CLI output shape stability, lockfile as a public artifact, cache filesystem location, customization-precedence matrix, security envelope.

Plus two cross-cutting concerns that interact with most categories:

- **Concurrency & file-locking** — governs the lazy-compile guard and any multi-process scenarios.
- **Customization precedence matrix** — governs what happens when TOML, prose, and YAML planes disagree.

### Cross-Language Process Boundary (Node ↔ Python)

**Invocation patterns (Node side):**

- Always `child_process.spawn`; never `exec`. Capture stdout + stderr separately; wait for exit.
- Command shape always prefixed with `python3 src/scripts/compile.py`. Hard-check at installer start that `python3 --version ≥ 3.11`; abort install with a clear message if absent. Do not fall back to `python` (could be 2.x).
- Arguments encode paths and IDs only — never file contents. Python reads inputs from disk via its own `bmad_compile.io` sandbox.
- Python cwd is set to project root by Node via spawn options; Python never uses `os.chdir`.

**Two invocation modes — per-skill and batch:**

- **Per-skill** — `python3 compile.py <subcommand> --skill <id> [flags]`. Used by: `bmad compile <skill>`, the lazy-compile-on-entry guard, `bmad-customize` skill via `--explain --json` and `--diff`.
- **Batch** — `python3 compile.py --batch <skills.json> [flags]`. Used by `bmad install` and `bmad upgrade` to compile all migrated skills in one Python invocation, collapsing ~200 ms × N interpreter cold-start overhead to 1 × N ≈ 10 s budget-impact regardless of skill count. Python pays import cost once, iterates the list, emits one JSON stream of per-skill results to stdout. Engine stays stateless per-skill internally; batch is a thin driver in `compile.py`.

**Python→Node stdout contract:**

- `--explain` default (Markdown with inline XML): plain text, one contiguous document.
- `--explain --json` / `--explain --tree`: JSON or tree-formatted text.
- `--diff`: unified diff; ANSI-colorized when `sys.stdout.isatty()`, plain when piped.
- `bmad upgrade --dry-run --json`: structured drift report (single JSON document).
- Compile engine writes to disk (SKILL.md, bmad.lock); Node learns outcome via structured JSON summary on stdout describing per-skill results.
- Batch mode: emits one JSON document per skill, newline-delimited, so Node can stream-parse.

**Python→Node stderr contract:**

- Progress messages, `--debug` resolution traces, warnings, errors → stderr only.
- stdout never contains diagnostic text. `| jq` / `| less` / `| cat` always Just Works.

**Exit codes:**

- 0: success.
- 1: compile error (frozen error codes, NFR-M5).
- 2: lockfile integrity error.
- 3: drift detected (halt-on-drift per FR57).
- Non-zero exit ALWAYS accompanies a structured error on stderr.

**Unstable-output prohibition:** no wall-clock time, developer-machine absolute paths, or hash-dependent process state in machine-readable stdout or in on-disk artifacts. Error messages on stderr MAY include install-absolute paths (user sees them directly).

**One shared Node subprocess helper:** `tools/installer/compiler/invoke-python.js` wraps `spawn`, captures stdout + stderr, optional JSON parsing with safe try/catch. All Node-side compiler calls go through it; raw `spawn` elsewhere is banned by lint.

### Python Library Layering & Import Discipline

**Layering (innermost → outermost):**

1. `errors.py` — no internal imports.
2. `io.py` — imports `errors` only. The **sole** determinism and filesystem boundary (see §Determinism).
3. `parser.py` — pure: imports `errors`, no `io`.
4. `toml_merge.py` — pure: imports `errors`, `tomllib`. No `io`.
5. `variants.py` — imports `errors`, `io`.
6. `resolver.py` — imports `errors`, `io`, `toml_merge`.
7. `lockfile.py` — imports `errors`, `io`.
8. `explain.py` — pure: imports `errors`. No `io`.
9. `engine.py` — imports everything above.
10. `lazy_compile.py` — imports `engine`, `lockfile`, `io`, `errors`.

**Rules (never import upward):** `parser.py` may not import `engine.py`; `io.py` may not import `resolver.py`; etc.

**Enforcement: AST-walking import test.** `test/python/test_layering.py` parses each `bmad_compile/*.py` module's `import` statements via `ast` and asserts imports only point at modules at or below the importing module's layer. ~30 lines of stdlib-only test code. Runs in CI; never lies; faster than a lint rule. Plus:

- `mypy --strict` on `bmad_compile/` catches dataclass-boundary violations and `None` unwraps.
- One architectural decision record in `src/scripts/bmad_compile/LAYERING.md` naming the layers and the rule.

**Allowed-imports allowlist for sandbox boundary:**

- `open()`, `pathlib.Path.read_*`, `pathlib.Path.write_*`, `hashlib`, `glob`, `os.walk`, `os.listdir`, `os.scandir` — allowed ONLY in `io.py`.
- `tomllib` — allowed ONLY in `toml_merge.py`.
- `datetime`, `time.time`, `time.monotonic` — allowed ONLY in `io.py` (release-sentinel formatting only). The engine has no direct access to wall-clock time.
- `yaml` / `pyyaml` — banned anywhere (stdlib only; lockfile uses a hand-rolled emitter in `io.py`).
- Enforcement: each forbidden-elsewhere line allowed in `io.py` requires `# pragma: allow-raw-io` comment; PRs adding this pragma outside `io.py` are blocked by review.

**Dataclasses over dicts at internal boundaries.** Explicit `to_dict()` / `from_dict()` at serialization boundaries. Type hints mandatory; `from __future__ import annotations` at the top of every module. `mypy --strict` as CI gate.

**Why not publish as separate packages?** Considered and rejected. Package boundaries give import-graph enforcement for free but tax refactor speed during the DSL-stabilization period. Revisit if `bmad_compile` ever ships standalone from `bmad-method`. Not now. Rule of Three.

### Determinism — a Boundary, Not a Checklist

**All non-determinism in the compile path lives inside `bmad_compile/io.py`.**

- Only `io.py` may read files, write files, enumerate directories, compute hashes, or format timestamps.
- Only `io.py` may import `datetime`, `time.*`, `hashlib`, `pathlib`, `os.listdir`, `os.scandir`, `glob`.
- Only `io.py` holds the hand-rolled stable YAML emitter for lockfile output.
- Only `io.py` converts between native paths and the internal POSIX representation.

The rules you'd otherwise enumerate (LF on write, UTF-8 no BOM, alphabetical directory sort, SHA-256 lowercase hex binary-mode hashing, `compiled_at` as release sentinel not wall-clock) become **implementation details of `io.py`**, not discipline for every module to follow.

**Contract:** every module outside `io.py` is pure over inputs it received through the sandbox. Reviewers audit `io.py`; everything else is type-checked to depend only on what `io.py` returns.

**Enforcement as one grep in CI:**

```
grep -r 'datetime\|time\.\|hashlib\|os\.listdir\|os\.scandir\|glob\|open(' \
     src/scripts/bmad_compile/ \
     --include='*.py' \
     --exclude=io.py
# exit 0 if empty — fail CI if non-empty
```

Plus the layering test (§Python Library Layering) which already forbids upward imports.

NFR-R1 byte-for-byte reproducibility across macOS / Linux / Windows is enforced by a three-OS determinism job — see §Test Organization for scheduling.

### Error Message Format + Remediation Hint Quality Bar

**Format** (stderr, one shape for every compile error):

```
<ERROR_CODE>: <relative-path>:<line>:<col>: <short description>
  <line_before>| <source context>
  <line_number>| <source line with offending token>
            | <spaces>^^^^^^^^ <caret span under the token>
  <line_after>| <source context>
    hint: <remediation — see quality bar below>
    [chain (cyclic includes only):
       <path1>
       → <path2>
       → <path1>]
    [see: bmad docs errors#<CODE>]
```

**Source-snippet rules:**

- Two lines of context around the offending line when available (truncate gracefully at file bounds).
- Caret span points at the offending token, not just column 1. Minimum one `^`; full span for multi-char tokens.
- **Column semantics (frozen):** `col` is the 1-based column of the **first character of the offending token**. For `{{output_folder}}` at col 15, that's the `{` of the opening `{{`. Editors can jump directly; documentation spells this out so no future change breaks tooling.
- `<ERROR_CODE>` is a short sluggified form of the enum (`UNRESOLVED_VARIABLE`, not `BMAD-E0042`); numeric prefixes rejected as bloat.
- `[see: bmad docs errors#<CODE>]` appended to every error pointing at the "When Compile Fails" ship-gate doc (see below).

**Remediation-hint quality bar.** Every error carries a hint. A hint **passes** if a new user, reading only the hint, can type the fix without opening docs. Examples:

| Code | Bad hint | Good hint |
|---|---|---|
| `UNRESOLVED_VARIABLE` | `define the missing variable` | `add 'output_folder: docs/' to _bmad/custom/config.yaml (user layer) or _bmad/core/config.yaml (core layer), or remove {{output_folder}} from line 42` |
| `MISSING_FRAGMENT` | `fragment not found` | `create _bmad/custom/fragments/bmm/bmad-agent-pm/persona-intro.template.md, or change <<include path="..."> on line 12 to an existing fragment (see _bmad/bmm/fragments/ for upstream options)` |
| `CYCLIC_INCLUDE` | `remove the cycle` | `break the cycle by removing one <<include>> directive in the chain above; the most recently added include is usually the safest edge to cut` |
| `OVERRIDE_OUTSIDE_ROOT` | `invalid override path` | `override path '../../etc/passwd' is outside _bmad/custom/ — move the file under _bmad/custom/ and retry, or remove the symlink if one resolves outside` |
| `UNKNOWN_DIRECTIVE` | `unknown directive` | `directive '<<incude>>' on line 7 is not recognized — did you mean '<<include>>'? Valid directives: <<include>>, {{var}}, {{self.<toml.path>}}, {var}` |
| `LOCKFILE_VERSION_MISMATCH` | `lockfile version mismatch` | `bmad.lock declares version N but this bmad-method (version M) reads up to version K. Run 'bmad upgrade' to regenerate; your overrides in _bmad/custom/ will be preserved` |

**Fix-it suggestions:** use Levenshtein-based "did you mean" for closed-set errors (`UNKNOWN_DIRECTIVE`). Skip for open-set (`UNRESOLVED_VARIABLE` — too many false suggestions).

**Hint craft is iterative; codes are frozen.** New error codes require a PRD NFR-M5 amendment. Hint wording changes are PR-level without ceremony — they're a craft, not a contract. A checked-in test asserts the hint-format shape (starts with `hint:`, non-empty, names a concrete file or syntax), not the wording.

**`--debug`** appends Python traceback under the error on stderr prefixed with `[debug]`. Never changes stdout.

### Ship-Gate Documentation

One doc must exist the day the compiler ships, titled **"When Compile Fails"**, covering:

1. The error format, with one annotated example walking through every field.
2. All frozen error codes — one-line description, minimal example output, the fix. Each code linkable by anchor (`#UNRESOLVED_VARIABLE`) so hints can `see: bmad docs errors#<CODE>`.
3. How to read the `[chain: ...]` block.
4. What `--debug` adds, when to use it.
5. Where to file a bug if the hint is useless.

Other docs (directive reference, customization guide, lockfile spec) may ship a week later. This page is non-negotiable — it's where every error message eventually points a confused user.

Augment NFR-M3's ship-gate list with: "When Compile Fails" page + directive reference + `bmad-customize` walkthrough + lockfile schema reference + 5-minute quickstart.

### Lockfile YAML — Serialization and Schema Evolution

**Serialization determinism:** hand-rolled minimal stable YAML emitter in `io.py`; 2-space indent, LF line endings, alphabetized mapping keys at every level; lists preserve compiler-emitted order; no floats; hashes are hex; unknown fields round-tripped unchanged.

**Schema evolution policy:**

- **Minor additions (backward-compatible):** adding a new optional field to an existing entry type. v1 readers ignore the field; round-trip it unchanged. No version bump. Example: a future version adds `last_validated_at` to lockfile entries.
- **Major changes (backward-incompatible):** renaming a field, removing a field, changing a field's type, adding a new required field, changing semantics of an existing field. Requires bumping `version:` in the lockfile schema (v1 → v2) AND emitting a clear `LOCKFILE_VERSION_MISMATCH` for readers that don't handle the new version.
- **Migration path for major changes:** v1 compiler reading v2 lockfile → error. v2 compiler reading v1 lockfile → auto-upgrade on write (reads v1, writes v2, records the upgrade in lineage). Never silently read v2 as v1.
- **Contract for downstream consumers** (`bmad-customize`, third-party tooling parsing lockfile): MUST tolerate unknown fields. SHOULD round-trip unknown fields on write. MAY pin to a `version:` and refuse to parse newer versions with a clear error.

The lockfile is a public artifact consumed by tooling (the `bmad-customize` skill, CI dashboards, potential future `bmad upgrade --rollback`). Its schema is part of the tool's public API the moment v1 ships.

### Concurrency & File-Locking

**Scenarios that can race:**

1. Two IDE windows invoke the lazy-compile guard for the same skill simultaneously.
2. A CI job racing a developer's on-save recompile.
3. Two modules in a parallel `bmad install` both writing to `bmad.lock`.

**Rules:**

- **Lazy-compile guard (Decision 16):** acquires an advisory file-lock via `fcntl.flock` (POSIX) / `msvcrt.locking` (Windows) on a sibling `.compiling.lock` file for the skill's install directory before recompile. Loser waits; when it acquires the lock, it re-reads the lockfile entry, typically finds the recompile already happened → emits the now-fresh `SKILL.md` → releases. Fast path for the loser: ~50 ms overhead.
- **`bmad.lock` writes during batch/install:** serialize through a lock on `_bmad/_config/.bmad.lock.write` (separate from `bmad.lock` itself). Batch mode acquires once, writes all entries, releases. Concurrent installs in the same project are unsupported (acquire fails → error).
- **Lock-stale detection:** a lock file older than 5 minutes is treated as stale (orphan process). Log a warning, reclaim, proceed. Tuning knob via `--lock-timeout-seconds` for CI environments with slow compiles.
- **Readers:** reading the lockfile or the on-disk `SKILL.md` requires no lock; the lazy-compile guard's atomic writes (temp-file + rename) ensure readers never see partial state.

**Enforcement:** integration test in `test/python/integration/test_concurrent_compile.py` spawns two guard invocations for the same skill and asserts one recompiles, the other waits-and-reads. Three-OS CI.

### Cross-Plane Customization Precedence Matrix

When the three customization planes (TOML structured fields, prose fragments, YAML compile-time variables) touch the same logical setting, the compiler must resolve deterministically.

| Scenario | Example | Resolution |
|---|---|---|
| TOML field + YAML var reference same name | `agent.icon` in `customize.toml` + `{{self.agent.icon}}` in template — no conflict, same plane | Expected: TOML defaults → team → user, single-plane cascade |
| TOML field + prose fragment reference same concept | `customize.toml` has `agent.role = "..."` AND a fragment uses the role text directly | **No conflict detected by compiler** (different artifacts). Author convention: prefer TOML for structured settings, reference it from prose via `{{self.agent.role}}`. |
| Prose fragment override + TOML user override both apply | User has both `_bmad/custom/fragments/.../menu.template.md` AND `_bmad/custom/bmad-agent-pm.user.toml` with `agent.menu` rewrites | **Both apply.** They operate on different rendering paths — fragment replaces the prose `<<include>>` boundary; TOML is injected into `{{self.agent.menu}}` interpolations. If a template happens to render both the fragment AND the TOML-sourced value in the same compiled region, both appear. Not a compiler concern; author-side smell. |
| YAML `{{var}}` and TOML `{{self.var}}` both defined | User sets `{{output_folder}}` in YAML and `{{self.agent.output_folder}}` in TOML | **No conflict** — different names (namespace prefix `self.`). Two separate variables with their own provenance. |
| TOML orphan override + upstream adds new default at same path | User overrides `agent.principles[2]` with custom text; upstream later adds a DIFFERENT `agent.principles[2]` default | User's override wins (TOML merge rules). Flagged by `bmad upgrade --dry-run` as semantic drift → `bmad-customize` triage. |
| `file:` glob expansion + direct fragment include with overlapping content | Both a `<<include>>` fragment and a `file:` glob pull in the same markdown file | **Both are inlined, independently.** File appears twice in compiled output. Author-side smell; compiler does not deduplicate — it reports two distinct `<TomlGlobMatch>` / `<Include>` entries in `--explain`. |
| Full-skill replacement + any other override | User has `_bmad/custom/fragments/<module>/<skill>/SKILL.template.md` AND a TOML user override | **Full-skill replacement wins** for the prose/structure; TOML user override still layers into `{{self.*}}` references *inside* the replacement template. Documented behavior: full-skill is a *template* replacement, not a value-resolution override — TOML continues to layer. |

**Enforcement:** one golden-file test per matrix row in `test/fixtures/compile/cross-plane/`. Three-OS determinism matrix.

**Missing-resolution detection:** if the compiler encounters a scenario not covered by this matrix — a new plane interaction introduced by a future feature — it errors with `PRECEDENCE_UNDEFINED` (frozen error code per NFR-M5) pointing at this matrix as the docs anchor. Better to block with a clear error than silently pick.

### Test Organization

**Python unit:** `test/python/test_<module>.py`, stdlib `unittest` (no pytest — NFR-S6). Table-driven cases via `self.subTest()` for parametrization. Use `self.assertEqual` on dicts/lists (produces unified diffs); ban bare `assert` in tests via lint.

**Python integration:** `test/python/integration/` — exercise `compile.py` and `lazy_compile.py` end-to-end via `subprocess.run`.

**Golden-file tests:** `test/fixtures/compile/<scenario>/` with:

- `input/` — skill source.
- `expected/` — expected `SKILL.md`, `bmad.lock`, `--explain` output.
- `run.sh` — harness.

**`--update-golden` regeneration flag.** `python3 src/scripts/compile.py --update-golden <scenario>` rewrites `expected/` in place; PR shows the diff for review. **AC for Story 1:** without this, fixture maintenance will be abandoned within a month.

**Minimal scenarios per behavior, not per skill.** `variable-resolution/`, `toml-layering/`, `glob-expansion/`, `frontmatter-stripping/`, `cross-plane/<matrix-row>/`, `cyclic-include/`, `variant-selection/`. ~8–15 total, not 50+.

**Node integration:** extend `test/test-installation-components.js` with `test-compile-integration.js`.

**E2E lifecycle test** (FR52, FR55): drives the full customization + upgrade lifecycle.

**Determinism CI matrix — scheduled, not per-PR.** Linux runs on every PR; macOS + Windows run on merges to main, nightly, and release tags. Saves ~6 min × every PR. Rationale: path-separator and line-ending bugs surface in nightly within a day; per-PR matrix is cost-for-insurance that NFR-R1 already guarantees via the `io.py` boundary. Trade: one day of blind to a macOS/Windows regression. Acceptable given the `io.py` determinism boundary makes regressions rare.

### Logging Channels & User-Facing Output

| Channel | Purpose |
|---|---|
| Python stdout | Compile engine's structured output only (compiled SKILL.md content for lazy compile; `--explain`/`--diff`/`--json` results). Never progress, never warnings. |
| Python stderr | Progress lines (`[compile] resolving fragments for bmad-agent-pm...`), warnings, errors, `--debug` traces. |
| Node stdout | User-facing interactive output (install progress, smart-install confirmation prompts). Pipes to the terminal; never machine-parseable. |
| Node stderr | Errors surfaced from Python + Node's own errors. Single formatter. |
| Log files | None in v1. `bmad.lock` is the audit trail; no separate log file. |

**`--debug` behavior:**

- Enabled via `--debug` on any CLI subcommand.
- Python: emits `[debug] <detail>` lines to stderr. One line per fragment considered, per variant rejected, per glob match.
- Node: emits its own `[debug] <detail>` lines to stderr at the adapter level.
- Never goes to stdout. Never changes stdout content. Scripts using `--json` are unaffected by `--debug`.

### Naming Conventions

| Artifact | Convention | Examples |
|---|---|---|
| Python module name | `snake_case.py` | `toml_merge.py`, `lazy_compile.py` |
| Python class name | `PascalCase` | `CompilerError`, `VariableScope`, `TomlGlobExpansion` |
| Python function / variable | `snake_case` | `resolve_name`, `current_skill` |
| Python constant | `UPPER_SNAKE` | `DEFAULT_OVERRIDE_ROOT`, `ERROR_CODES` |
| Node file name | `kebab-case.js` | `invoke-python.js`, `upgrade-command.js` |
| Node function / variable | `camelCase` | `invokePython`, `parseJsonSafely` |
| Node class name | `PascalCase` | `InstallPaths`, `ManifestGenerator` (matches upstream) |
| CLI subcommand | `lowercase` | `install`, `upgrade`, `compile` |
| CLI flag | `--kebab-case` | `--override-root`, `--dry-run`, `--explain` |
| Error code (enum value) | `UPPER_SNAKE` | `UNKNOWN_DIRECTIVE`, `OVERRIDE_OUTSIDE_ROOT` |
| Lockfile YAML key | `snake_case` | `source_hash`, `toml_layer`, `match_set_hash` |
| `--explain` XML attribute | `kebab-case` | `resolved-from`, `toml-layer`, `base-source-path` |
| Template syntax variable name | `snake_case` (YAML) or `dotted.path` (TOML) | `{{user_name}}`, `{{self.agent.icon}}` |
| Fragment file name | `kebab-case.template.md` | `persona-guard.template.md`, `menu-handler.cursor.template.md` |
| Skill directory | `bmad-<role>-<suffix>` | `bmad-agent-pm`, `bmad-create-prd` (matches upstream) |

### File Layout Conventions

**Source tree (`src/`):**

```
src/
  scripts/
    bmad_compile/         # shared Python library (Decision 17)
      __init__.py
      parser.py
      resolver.py
      toml_merge.py
      variants.py
      io.py
      errors.py
      lockfile.py
      explain.py
      engine.py
      lazy_compile.py
    compile.py            # build-time entry point (invoked by Node adapters)
    resolve_customization.py  # refactored thin shim over bmad_compile.toml_merge
  core-skills/
    <skill>/              # existing + migrated
      SKILL.template.md   # NEW — optional, for migrated skills
      SKILL.md            # existing OR generated from template
      customize.toml      # existing (upstream-shipped)
      fragments/          # NEW — prose fragments for this skill
        <name>.template.md
        <name>.cursor.template.md
      ...
  bmm-skills/
    <phase>/<skill>/      # same layout as core-skills
    module.yaml
```

**Install tree (`_bmad/`):**

```
_bmad/
  config.toml             # NEW (PR #2285) — central base-team: install answers + agent roster
  config.user.toml        # NEW (PR #2285) — central base-user: user install answers (gitignored)
  _config/
    manifest.yaml         # existing
    files-manifest.csv    # existing (unchanged by compiler)
    skill-manifest.csv    # existing
    bmad-help.csv         # existing
    bmad.lock             # NEW — compiler output
    # agent-manifest.csv removed in PR #2285; roster derives from module.yaml + central TOML
  scripts/                # upstream-provisioned (8fb22b1a)
    resolve_customization.py
    resolve_config.py     # central TOML merger (PR #2285)
    bmad_compile/         # copied from src/scripts/
    compile.py
    lazy_compile.py
  custom/                 # upstream-provisioned override root
    .gitignore            # seeded with `*.user.toml` + `fragments/**/*.user.*`
    config.toml           # NEW (PR #2285) — central custom-team overrides (committed stub)
    config.user.toml      # NEW (PR #2285) — central custom-user overrides (gitignored stub)
    <skill>.toml          # team TOML overrides (optional, per-skill)
    <skill>.user.toml     # user TOML overrides (optional, gitignored, per-skill)
    config.yaml           # user YAML variable overrides (optional)
    <module>/config.yaml  # per-module overrides (optional)
    fragments/            # NEW — prose fragment overrides
      <module>/<skill>/<name>.template.md
  core/
    config.yaml
    module-help.csv
  <module>/
    config.yaml
    module-help.csv
    <skill>/
      SKILL.md            # compiled output for migrated skills
      customize.toml      # preserved (lazy-compile needs it)
      .compiling.lock     # advisory file-lock sentinel (see §Concurrency)
      # (templates NOT present; deleted post-compile)
      # fragments/ NOT present; resolved inline into SKILL.md
```

**What's committed vs ignored vs regenerated:**

| Path | Commit? | Notes |
|---|---|---|
| `src/**/*.template.md` | Yes | Skill source |
| `src/**/fragments/**` | Yes | Fragment source |
| `src/**/customize.toml` | Yes | TOML defaults source |
| `src/scripts/bmad_compile/**` | Yes | Shared library source |
| `_bmad/**/SKILL.md` | No (in user project) | Regenerated by installer / lazy-compile |
| `_bmad/_config/bmad.lock` | Yes (recommended for user project) | Audit trail; drift-detect baseline |
| `_bmad/**/.compiling.lock` | No | Advisory lock sentinel; transient |
| `_bmad/custom/<skill>.toml` | Yes | Team TOML overrides (per-skill) |
| `_bmad/custom/<skill>.user.toml` | No (gitignored by convention) | Personal overrides (per-skill) |
| `_bmad/config.toml` | Yes | Central base-team: install answers + agent roster (installer-emitted, PR #2285) |
| `_bmad/config.user.toml` | No (gitignored by convention) | Central base-user: user install answers |
| `_bmad/custom/config.toml` | Yes | Central custom-team: team overrides of central fields |
| `_bmad/custom/config.user.toml` | No (gitignored by convention) | Central custom-user: personal overrides of central fields |
| `_bmad/custom/fragments/**/*.template.md` | Yes | Team prose overrides |
| `_bmad/custom/fragments/**/*.user.template.md` | No (gitignored) | Personal prose overrides |

### Contract Surfaces (tenth category)

Not all rules protect internals; these rules protect the compiler's external consumers.

**CLI output stability contract:**

- `--explain --json` shape is the same JSON schema for the lifetime of v1 of the lockfile. Adding a new optional field: OK. Renaming or removing a field: major version bump of the JSON schema (embedded as `"schema_version": 1` at document root).
- `upgrade --dry-run --json` follows the same policy.
- Node CLI wrappers pass JSON through unmodified; never reshape, never filter.

**Lockfile as a public artifact:**

- Third-party tooling (the `bmad-customize` skill, CI dashboards, future rollback tooling) may parse `bmad.lock`. Schema evolution follows §Lockfile YAML — Serialization and Schema Evolution.
- Checked-in reference documentation (lockfile schema spec) describes every field with type, semantics, and optionality; updated in the same PR as any schema change.

**Cache filesystem location:**

- Compiled outputs live at `<install-root>/_bmad/<module>/<skill>/SKILL.md` — per-project, same as existing install tree. **Not** in a user-global cache (no `~/.cache/bmad` or `%LOCALAPPDATA%\bmad`).
- Rationale: deterministic builds require the compile cache to be pinned to the install state; a user-global cache confuses per-project overrides and breaks NFR-R1 across workstations.
- Advisory locks (§Concurrency) co-locate with the cache at `<install-root>/_bmad/<module>/<skill>/.compiling.lock`.

**Security envelope (baseline for v1):**

- `file:` glob expansions resolve only within `{project-root}`. Escapes rejected with `OVERRIDE_OUTSIDE_ROOT` at expansion time. Symlinked matches pointing outside project-root also rejected.
- `customize.toml` parsing is stdlib `tomllib` — no arbitrary code execution path, no schema-driven extension loader in v1. Future Python-backed extensions gate behind `trust_mode: full` (NFR-S4).
- Override root is user-writable, committable/gitignored per convention; compiler does not enforce ACLs beyond containment.
- **CI operator consideration:** compiles are hermetic (no network; no env reads; no user-global state). Sandbox-friendly.

**Stakeholder voices this section represents:**

- CI operators: non-interactive compiles produce machine-readable output; exit codes are categorized; logs go to stderr in structured form; no TTY assumed.
- Downstream consumers: lockfile and `--explain --json` shapes have declared stability contracts.
- Security reviewers: containment rules documented; trust gate for future extensions specified; no arbitrary code paths at compile time.
- Third-party skill authors: TOML/fragment/YAML conventions apply to their skills too; documented in the author-facing migration guide.

### Enforcement Guidelines

**All AI Agents implementing this codebase MUST:**

- Route all compile-time filesystem + hashing + time I/O through `bmad_compile.io` (Python).
- Route all Node-side I/O through `fs-native.js` (upstream `a6d075bd`).
- Raise typed `CompilerError` subclasses; **never *swallow* `Exception`** — catch-and-reraise as typed at I/O boundaries is required, but generic `except Exception: log()` is banned.
- Write compile outputs (SKILL.md, bmad.lock) only through `bmad_compile.io` / `bmad_compile.lockfile`.
- Never introduce a new runtime dependency (Python: stdlib only; Node: existing deps only).
- Keep stdout machine-parseable in `--json` modes; diagnostics on stderr.
- Add a golden-file test for any new compile behavior.
- Preserve unknown lockfile fields on round-trip.
- Adhere to frozen error vocabulary; new error codes require PRD amendment; hint wording does not.
- When a new plane interaction is added, update the §Cross-Plane Customization Precedence Matrix and add a golden-file test per new row.

**Pattern Enforcement via CI:**

- `test_layering.py` — AST-checks module import graph.
- `grep` determinism check — no forbidden imports outside `io.py`.
- `mypy --strict` on `bmad_compile/`.
- Golden-file diff (Linux on PR; macOS + Windows on main + nightly + release).
- `npm run validate:compile` (FR49) on every PR.
- Concurrent-compile integration test.
- JSON-schema-stability test: compare `--explain --json` output against a checked-in snapshot shape.

### Anti-Patterns (Teaching Style for the Subtle Ones)

Prohibitions paired with their positive inverse where the distinction is non-obvious.

**Catching generic `Exception`.**

```python
# don't — swallows the typed-error contract
try:
    resolve_variable(name)
except Exception:
    log("failed")

# do — let typed errors propagate; the outermost entry point formats them
try:
    resolve_variable(name)
except UnresolvedVariableError as e:
    raise  # no-op; catches in compile.py top-level emit the standard format

# also do — at I/O boundaries where you can't help catching broad exceptions
try:
    data = json.loads(lockfile_contents)
except json.JSONDecodeError as e:
    raise LockfileVersionMismatchError(path=lockfile_path, cause=e) from e
```

The pattern: typed errors for known failure modes; catch-and-reraise-as-typed at boundaries; never swallow.

**Wall-clock timestamps in compiled output.**

```python
# don't — breaks NFR-R1 byte-for-byte reproducibility
compiled_header = f"# Compiled at {datetime.now().isoformat()}"

# do — use the release sentinel, read through io.py
compiled_header = f"# Compiled from bmad-method {io.release_sentinel()}"
```

**Re-reading input files during resolution.**

```python
# don't — causes the resolver to see filesystem state that differs from
# the state recorded in the lockfile if a file changes mid-compile
def resolve_var(name):
    config = yaml.safe_load(open(CORE_CONFIG))  # re-reads every call
    return config[name]

# do — pre-materialize the VariableScope once at engine init; resolver queries frozen data
scope = VariableScope.build_once(paths, manifest, configs_already_read)
def resolve_var(name):
    return scope.resolve(name)  # no I/O
```

**Implicit TOML merge outside `toml_merge.py`.** Two implementations drift. Always import from `bmad_compile.toml_merge`.

**Hand-writing lockfile entries.** Always go through `lockfile.py` writer; ad-hoc emission breaks the stable-ordering contract.

**Writing outside the sandbox.** Blatant prohibition — banned by grep, layering test, and lint.

**Progress messages on stdout.** Blatant prohibition — breaks every machine-parseable consumer. Use stderr.

**Cross-plane shortcuts in `bmad-customize`.** The skill never writes to a TOML override and a prose override in the same non-atomic sequence; each is independently acceptance-gated per FR54.

## Project Structure & Boundaries

### Complete Project Directory Structure

The compiler's physical layout across both the source repo and the installed tree is specified in §File Layout Conventions (Implementation Patterns). This section cross-references that layout with component boundaries, integration points, and a complete FR-to-file mapping.

**Consolidated tree — what lives where:**

```
bmad-method/                             # repo root (existing)
├── package.json                          # existing; Node ≥20, existing deps only
├── CHANGELOG.md                          # existing
├── proposals/
│   ├── bmad-skill-compiler-prd.md       # THIS PROPOSAL
│   ├── bmad-skill-compiler-architecture.md
│   ├── bmad-skill-compiler-proposal.md  # original v3
│   └── research-prompt-compilation-landscape.md
│
├── src/
│   ├── core-skills/
│   │   ├── module.yaml                   # existing
│   │   └── <skill>/
│   │       ├── SKILL.md                  # existing or compiler-generated
│   │       ├── SKILL.template.md         # NEW — optional source
│   │       ├── customize.toml            # existing (upstream)
│   │       └── fragments/                # NEW — per-skill prose fragments
│   │           └── <name>.template.md
│   ├── bmm-skills/
│   │   ├── module.yaml                   # existing
│   │   └── <phase>/<skill>/              # same layout as core-skills
│   └── scripts/                          # UPSTREAM-PROVISIONED (8fb22b1a)
│       ├── resolve_customization.py      # refactored: thin shim over bmad_compile.toml_merge
│       └── bmad_compile/                 # NEW — shared Python library (Decision 17)
│           ├── __init__.py
│           ├── errors.py                 # layer 1 — no internal imports
│           ├── io.py                     # layer 2 — determinism sandbox; ONLY here for fs/hash/time
│           ├── parser.py                 # layer 3 — pure template AST
│           ├── toml_merge.py             # layer 4 — TOML layer merge; imported by resolver + resolve_customization
│           ├── variants.py               # layer 5 — IDE variant selection
│           ├── resolver.py               # layer 6 — variable resolver (two-namespace cascade)
│           ├── lockfile.py               # layer 7 — stable YAML emitter + reader
│           ├── explain.py                # layer 8 — --explain Markdown/XML/JSON renderer
│           ├── engine.py                 # layer 9 — top-level build-time orchestrator
│           ├── lazy_compile.py           # layer 10 — skill-entry cache-coherence guard
│           └── LAYERING.md               # ADR documenting the layer rule
│       └── compile.py                    # NEW — build-time entry point invoked by Node
│
├── tools/
│   ├── installer/                        # existing
│   │   ├── bmad-cli.js                   # existing; CLI entry
│   │   ├── commands/
│   │   │   ├── install.js                # existing — augmented to invoke Python compiler
│   │   │   ├── upgrade.js                # NEW — `bmad upgrade [--dry-run] [--json] [--yes]`
│   │   │   ├── compile.js                # NEW — `bmad compile <skill> [...]`
│   │   │   ├── status.js                 # existing
│   │   │   └── uninstall.js              # existing
│   │   ├── core/                         # existing
│   │   │   ├── installer.js              # existing — hook point for compile at line ~584
│   │   │   ├── manifest.js               # existing
│   │   │   ├── manifest-generator.js     # existing
│   │   │   ├── config.js                 # existing
│   │   │   ├── install-paths.js          # existing — extended with customDir, scriptsDir
│   │   │   └── existing-install.js       # existing
│   │   ├── compiler/                     # NEW — Node adapter layer
│   │   │   └── invoke-python.js          # NEW — shared subprocess helper
│   │   ├── fs-native.js                  # upstream (a6d075bd) — replaced fs-extra
│   │   ├── file-ops.js                   # existing
│   │   ├── ide/                          # existing
│   │   ├── modules/                      # existing
│   │   └── ...
│   ├── validate-skills.js                # existing — unchanged
│   ├── validate-file-refs.js             # existing — unchanged
│   └── validate-compile.js               # NEW — npm run validate:compile target
│
└── test/
    ├── test-installation-components.js   # existing; extended
    ├── test-compile-integration.js       # NEW — Node-side integration tests for compile adapter
    ├── python/                           # NEW — Python test tree
    │   ├── _helpers.py                   # shared test fixtures/factories
    │   ├── test_errors.py
    │   ├── test_io.py                    # I/O sandbox; NFR-R1 determinism primitives
    │   ├── test_parser.py
    │   ├── test_toml_merge.py            # covers the upstream merge-rule test cases
    │   ├── test_variants.py
    │   ├── test_resolver.py              # two-namespace cascade; derived allowlist
    │   ├── test_lockfile.py              # YAML emitter stability; round-trip unknown fields
    │   ├── test_explain.py
    │   ├── test_layering.py              # AST-walking import check
    │   └── integration/
    │       ├── test_end_to_end.py
    │       ├── test_concurrent_compile.py
    │       └── test_lazy_compile_guard.py
    └── fixtures/
        └── compile/                      # NEW — golden-file scenarios
            ├── variable-resolution/
            │   ├── input/
            │   └── expected/
            ├── toml-layering/
            ├── glob-expansion/
            ├── frontmatter-stripping/
            ├── cross-plane/<matrix-row>/
            ├── cyclic-include/
            └── variant-selection/
```

**Install tree (`_bmad/` under user project):** see §File Layout Conventions (Implementation Patterns) for the post-install layout. Key new files introduced at install: `_bmad/_config/bmad.lock`, `_bmad/scripts/bmad_compile/` (copied from source), `_bmad/custom/fragments/` (user-populated, seeded gitignore).

### Architectural Boundaries

**Process boundary (Node ↔ Python):**

```
┌─────────────────────────────────────────────────────────────────────┐
│  Node process — tools/installer/                                    │
│                                                                     │
│  bmad-cli.js                                                        │
│     ↓                                                               │
│  commands/{install,upgrade,compile}.js                              │
│     ↓                                                               │
│  compiler/invoke-python.js  ──── spawn ───┐                         │
│                                            │                        │
│  ← parsed JSON on stdout, exit code ─────┐ │                        │
│                                          │ │                        │
└──────────────────────────────────────────│─│────────────────────────┘
                                           │ │
                                           ▼ │
┌─────────────────────────────────────────────────────────────────────┐
│  Python process — src/scripts/compile.py                            │
│                                                                     │
│  argparse → dispatch (--install-phase / --batch / --compile / ...)  │
│     ↓                                                               │
│  bmad_compile.engine                                                │
│     ↓                                                               │
│  parser → resolver → variants → lockfile → explain                  │
│     ↑                                                               │
│  bmad_compile.io  (SOLE determinism + filesystem boundary)          │
│     ↕                                                               │
│  Disk: _bmad/<module>/<skill>/SKILL.md, _bmad/_config/bmad.lock     │
└─────────────────────────────────────────────────────────────────────┘
```

- Contract: Node passes argv + paths, never file contents. Python owns all compile-time disk I/O.
- Transport: stdout for machine-parseable results (JSON / diff / Markdown-XML); stderr for diagnostics; exit code signals success/error class (see §Logging Channels).

**Library layer boundary (inside Python):**

```
                     ┌─────────────────────┐
                     │  lazy_compile.py    │  (layer 10 — skill entry)
                     └──────────┬──────────┘
                                │
                     ┌──────────▼──────────┐
                     │     engine.py       │  (layer 9 — orchestrator)
                     └┬──┬──┬──┬──┬──┬──┬──┘
                      │  │  │  │  │  │  │
       ┌──────────────┘  │  │  │  │  │  └──────────────┐
       │                 │  │  │  │  │                 │
┌──────▼─────┐  ┌────────▼─┐│  │  │  │  ┌──────────────▼┐
│ lockfile.py│  │ resolver │┘  │  │  │  │   explain.py   │
│  (layer 7) │  │  .py     │   │  │  │  │   (layer 8)    │
└─────┬──────┘  │(layer 6) │   │  │  │  └────────────────┘
      │         └──┬────┬──┘   │  │  │
      │            │    │      │  │  │
      │            │ ┌──▼──────▼──▼──▼──┐
      │            │ │   variants.py    │
      │            │ │   (layer 5)      │
      │            │ └────┬─────────────┘
      │            │      │
      │    ┌───────▼──┐   │
      │    │toml_merge│   │
      │    │.py (L4)  │   │
      │    └────┬─────┘   │
      │         │         │
      │   ┌─────▼─────┐   │
      │   │ parser.py │   │   (layer 3 — pure)
      │   └───────────┘   │
      │                   │
      └──────┐     ┌──────┘
             ▼     ▼
         ┌─────────────┐
         │    io.py    │  (layer 2 — sole boundary for fs/hash/time)
         └──────┬──────┘
                │
         ┌──────▼──────┐
         │  errors.py  │  (layer 1 — no internal imports)
         └─────────────┘
```

- `resolve_customization.py` (upstream thin shim) imports from `toml_merge.py` at layer 4 — same entry point as `resolver.py`, different consumer.
- `engine.py` and `lazy_compile.py` are the only modules importing across all lower layers. No module may import upward.
- Reviewer rule: audit changes to `io.py` carefully; everything else is pure over frozen inputs.

**Plane boundary (TOML / prose / YAML customization):**

```
               AUTHORING                COMPILE-TIME                RUNTIME (skill entry)
               ─────────                ────────────                ──────────────────────
TOML plane     customize.toml  ─────→   toml_merge.merge_layers   ─→ self.* vars in SKILL.md
               + <skill>.toml                                        (lazy-compile guard
               + <skill>.user.toml                                   refreshes on drift)

Prose plane    *.template.md    ─────→  parser → <<include>>       → inlined prose in SKILL.md
               + fragments/             resolver (5-tier precedence)
               + _bmad/custom/
                 fragments/

YAML plane     core/config.yaml ─────→  resolver (4-tier + derived) → {{var}} values in SKILL.md
               + <module>/config.yaml
               + _bmad/custom/
                 config.yaml
```

- Planes do not interact at compile time beyond what the §Cross-Plane Customization Precedence Matrix spells out.
- Each plane's resolution tier is documented in its respective Decision; this diagram is a guide, not a spec.
- The `bmad-customize` skill is the only consumer that reasons across all three planes — via the unified `--explain --json` view.

### Requirements → File Mapping (FR traceability)

Every FR in the PRD maps to a specific file or subsystem. This table is the definitive traceability artifact; CI can assert it by grep-checking that each FR number appears in at least one source comment or test name.

| FR / NFR | Primary file(s) | Test coverage |
|---|---|---|
| FR1–7 (template authoring) | `src/scripts/bmad_compile/parser.py` | `test/python/test_parser.py`, `test/fixtures/compile/variable-resolution/` |
| FR8 (recursive `<<include>>`) | `src/scripts/bmad_compile/resolver.py` | `test/python/test_resolver.py` |
| FR9 (`{{var}}` resolution) | `src/scripts/bmad_compile/resolver.py` | `test/python/test_resolver.py`, `test/fixtures/compile/variable-resolution/` |
| FR10 (fragment precedence) | `src/scripts/bmad_compile/resolver.py` + `engine.py` | `test/python/test_resolver.py` (one test per adjacent-tier pair) |
| FR11 (cycle detection) | `src/scripts/bmad_compile/resolver.py` | `test/python/test_resolver.py`, `test/fixtures/compile/cyclic-include/` |
| FR12 (byte-reproducibility) | `src/scripts/bmad_compile/io.py` + `engine.py` | Three-OS determinism CI job |
| FR13 (prose fragment override) | `src/scripts/bmad_compile/resolver.py` — override-root walk | `test/python/test_resolver.py`, `test/fixtures/compile/cross-plane/` |
| FR13a (TOML structured override) | `src/scripts/bmad_compile/toml_merge.py` | `test/python/test_toml_merge.py` |
| FR14 (full-skill replacement) | `src/scripts/bmad_compile/engine.py` — full-skill tier | `test/fixtures/compile/cross-plane/full-skill-replacement/` |
| FR15 (YAML var override) | `src/scripts/bmad_compile/resolver.py` — user-config tier | `test/python/test_resolver.py` |
| FR16 (precedence + lockfile) | `resolver.py` + `lockfile.py` | `test/python/test_lockfile.py` |
| FR17 (module boundary) | `src/scripts/bmad_compile/resolver.py` + `engine.py` — namespace collision check | `test/python/test_resolver.py` |
| FR18 (`bmad install`) | `tools/installer/commands/install.js` (existing, extended) | `test/test-installation-components.js` |
| FR19 (smart-install auto-routes to upgrade) | `tools/installer/commands/install.js` | `test/test-installation-components.js` |
| FR20 (verbatim-copy fallback) | `tools/installer/core/installer.js` — unchanged branch | Existing regression suite |
| FR21 (`upgrade --dry-run`) | `tools/installer/commands/upgrade.js` + `bmad_compile/engine.py` — drift calculator | `test/test-compile-integration.js` |
| FR22 (`upgrade` halts on drift) | `tools/installer/commands/upgrade.js` | Integration test |
| FR23 (reconcile triage via `bmad-customize`) | Skill-side (no compiler code); engine emits `--dry-run --json` | E2E test (FR52) |
| FR24 (shared flags) | `tools/installer/commands/{install,upgrade,compile}.js` | CLI-arg test |
| FR25 (`bmad compile <skill>`) | `tools/installer/commands/compile.js` → `src/scripts/compile.py --skill` | `test-compile-integration.js` |
| FR26 (`compile --diff`) | `src/scripts/compile.py` + `bmad_compile/explain.py` — diff mode | `test/python/test_explain.py`, integration test |
| FR27–29 (`--explain` formats) | `src/scripts/bmad_compile/explain.py` | `test/python/test_explain.py` |
| FR30 (`<Include>` tag attrs) | `src/scripts/bmad_compile/explain.py` | `test/python/test_explain.py` |
| FR31 (`<Variable>` tag attrs + `toml` source) | `src/scripts/bmad_compile/explain.py` | `test/python/test_explain.py` |
| FR32 (runtime `{var}` emitted unchanged) | `src/scripts/bmad_compile/parser.py` + `engine.py` | `test/python/test_parser.py` |
| FR33 (no LLM; deterministic) | `src/scripts/bmad_compile/engine.py` — no network, no LLM calls | NFR-S5 CI check |
| FR34–38 (`bmad-customize` skill flow) | `src/core-skills/bmad-customize/` (skill-side) + engine's `--explain --json` | E2E test (FR52) |
| FR39 (`bmad-customize` dogfooded) | Skill authored as template source | CI — recompile during release |
| FR40 (lockfile content) | `src/scripts/bmad_compile/lockfile.py` | `test/python/test_lockfile.py` |
| FR41 (`--dry-run` drift categories) | `tools/installer/commands/upgrade.js` + `bmad_compile/engine.py` + `lockfile.py` | Integration test + golden fixtures |
| FR42 (lockfile lineage) | `src/scripts/bmad_compile/lockfile.py` | `test/python/test_lockfile.py` |
| FR43 (value hashes, no plaintext) | `src/scripts/bmad_compile/lockfile.py` + `resolver.py` | `test/python/test_lockfile.py` |
| FR44–46 (IDE variants) | `src/scripts/bmad_compile/variants.py` | `test/python/test_variants.py`, `test/fixtures/compile/variant-selection/` |
| FR47 (distribution models 1/2/3) | `tools/installer/core/installer.js` + `modules/official-modules.js` | `test-compile-integration.js` |
| FR48 (cross-module fragment ref) | `src/scripts/bmad_compile/resolver.py` — namespace resolution | `test/python/test_resolver.py` |
| FR49 (`npm run validate:compile`) | `tools/validate-compile.js` — recompile + lockfile-diff | CI gate on every PR |
| FR50 (`validate:skills`) | `tools/validate-skills.js` — existing, unchanged | Existing CI gate |
| FR51 (non-zero exit on error) | `src/scripts/compile.py` + `tools/installer/commands/compile.js` | Integration test |
| FR52 (E2E customization lifecycle) | `test/test-compile-integration.js` — lifecycle test | CI gate |
| FR53 (Model-3 matrix) | `test/test-compile-integration.js` — compiler-present vs compiler-absent install | CI matrix |
| FR54 (no persist until accept) | `src/core-skills/bmad-customize/` (skill-side contract) | FR55 test |
| FR55 (abandoned-session CI) | `test/test-compile-integration.js` — abandoned-customize case | CI gate |
| FR56 (drift triage via skill) | Skill-side (consumes `--dry-run --json`) | E2E test |
| FR57 (halt-on-drift) | `tools/installer/commands/upgrade.js` | Integration test |
| FR58 (lazy compile on entry) | `src/scripts/bmad_compile/lazy_compile.py` + SKILL.md shim integration | `test/python/integration/test_lazy_compile_guard.py` |
| NFR-P1–P5 (performance budgets) | — (spans all modules) | Benchmark job (not per-PR; nightly) |
| NFR-S1–S6 (security) | `bmad_compile/io.py` (S2), `lockfile.py` (S1), `engine.py` (S3, S5) | Security-focused unit tests |
| NFR-R1 (byte-reproducibility) | `bmad_compile/io.py` | Three-OS determinism CI (nightly) |
| NFR-R2–R4 (determinism details) | `bmad_compile/io.py` | `test/python/test_io.py` |
| NFR-R5 (lockfile integrity + concurrency) | `lockfile.py` + `lazy_compile.py` | `test_concurrent_compile.py` |
| NFR-C1–C5 (compat) | — (environment + existing codepaths) | Install-matrix CI |
| NFR-O1–O5 (observability) | `lockfile.py` (audit), `explain.py` (provenance), `errors.py` (file+line) | Snapshot tests |
| NFR-M1–M5 (maintainability) | — (process concerns) | Layering test, `mypy --strict`, golden-file regression, docs-as-ship-gate |

**CI assertion:** a grep-walker in `test_fr_traceability.py` checks every FR number in the PRD appears in at least one source-comment header (`# FR41 — ...`) or test-name prefix (`test_fr42_...`). Missing FRs fail CI.

### Integration Points

**Compile-time integration (install / upgrade / explicit `bmad compile`):**

```
User → `npx bmad-method install`
    ↓
Node installer (tools/installer/bmad-cli.js)
    ↓
Node orchestrates: prompts user, writes module configs, copies module files
    ↓
Node shells out (once, batch mode): `python3 src/scripts/compile.py --batch skills.json`
    ↓
Python engine compiles every migrated skill:
    ↓
    ├─ parser.py: *.template.md → AST
    ├─ toml_merge.py: customize.toml + team + user → merged TOML
    ├─ resolver.py: resolves {{var}} / {{self.*}} / <<include>> / variant selection
    ├─ explain.py: optionally renders --explain output
    ├─ lockfile.py: writes per-skill entry to _bmad/_config/bmad.lock
    └─ io.py: atomic write of SKILL.md to install location
    ↓
Python returns per-skill JSON results to Node on stdout (newline-delimited)
    ↓
Node aggregates, runs manifest-generator, finishes install
```

**Skill-entry integration (lazy compile-on-entry):**

```
LLM invokes skill (Claude Code / Cursor)
    ↓
IDE reads _bmad/<module>/<skill>/SKILL.md — which is upstream's stdout-dispatch shim (b0d70766)
    ↓
Shim invokes: `python3 _bmad/scripts/lazy_compile.py <skill>`
    ↓
lazy_compile.py reads _bmad/_config/bmad.lock entry for <skill>
    ↓
Hashes every tracked input (fragments, configs, TOML layers, glob matches)
    ↓
    ├─ All hashes match → emit existing SKILL.md to stdout (fast path, ~50ms)
    └─ Any mismatch → acquire .compiling.lock → invoke engine.compile_one(skill) → update SKILL.md + lockfile → emit new SKILL.md (slow path, ~500ms)
    ↓
Shim passes SKILL.md content to LLM
```

**`bmad-customize` skill integration (chat-time authoring):**

```
User (in IDE chat): "change the PM agent's icon and add a company principle"
    ↓
Skill (LLM) invokes: `bmad compile bmad-agent-pm --explain --json`
    ↓
Node CLI → Python compile → --explain --json rendered by explain.py → stdout
    ↓
Skill parses: sees TOML fields + prose fragments + variables
    ↓
Skill maps intent to planes: icon → TOML, new principle → TOML
    ↓
Skill drafts override content in chat, iterates with user
    ↓
User accepts
    ↓
Skill writes: _bmad/custom/bmad-agent-pm.user.toml (no intermediate file touch before accept — FR54)
    ↓
Skill invokes: `bmad compile bmad-agent-pm --diff`
    ↓
Shows user the compiled-SKILL.md-level impact as verification
```

**`bmad upgrade` drift-triage integration:**

```
User: `bmad upgrade`
    ↓
Node → Python compile engine in dry-run mode
    ↓
Engine compares new source hashes against lockfile → detects drift per FR41's categories
    ↓
    ├─ No drift + --yes implied → proceed with upgrade
    ├─ No drift, no --yes → prompt user, proceed on confirm
    └─ Drift detected + no --yes → HALT with exit code 3; message: "Drift detected... invoke `bmad-customize` in your IDE chat to review"
    ↓ (user invokes bmad-customize with triage intent)
Skill: `bmad upgrade --dry-run --json`
    ↓
Skill walks each drift entry in chat, per FR56's per-type UX
    ↓
User decides: keep / adopt / rewrite / remove
    ↓
Skill persists decisions to _bmad/custom/ files (one per plane)
    ↓
User re-runs `bmad upgrade` → no drift → upgrade proceeds
```

### Data Flow — What Information Crosses Which Boundary

**Install time:**

1. User CLI flags + interactive prompts → Node `config.js` → Node `bmad.lock` entries written via Python on stdout.
2. Source files (`*.template.md`, fragments, `customize.toml`, `config.yaml`) → Python reads via `io.py` → compiled `SKILL.md` + `bmad.lock` entries written by Python.
3. Python → Node: JSON summary on stdout (per-skill success/failure, compiled hashes, drift flags if upgrade mode).
4. Node → user: aggregated human-readable progress on stdout; errors on stderr.

**Skill entry time:**

1. IDE → SKILL.md shim → `python3 lazy_compile.py <skill>`.
2. Python `lazy_compile.py` reads `bmad.lock` entry + all tracked inputs → emits SKILL.md content to stdout (possibly after recompile).
3. Shim → IDE → LLM reads content as the skill.

**Nothing crosses the network at compile time.** No telemetry in v1. No external service calls. NFR-S5 enforced by the absence of any `http`, `urllib`, `requests`, `socket` imports in `bmad_compile/*` (lint check).

### File Organization Rationale

**Why Python lives at `src/scripts/` not `tools/installer/compiler/`:**

- The upstream TOML resolver (`resolve_customization.py`) already lives at `src/scripts/`; the `bmad_compile/` library goes next to it for physical proximity and because both are Python.
- `tools/installer/` remains Node-only; `tools/installer/compiler/` contains ONLY Node adapter code (`invoke-python.js`).
- This keeps the language boundary obvious at the directory level: Node in `tools/`, Python in `src/scripts/`.

**Why `_bmad/scripts/` in the install tree mirrors `src/scripts/`:**

- The installer already copies `src/scripts/` → `_bmad/scripts/` per upstream `8fb22b1a`. Lazy-compile-on-entry depends on Python being available at `_bmad/scripts/bmad_compile/`, so the compiler slots into the existing provisioning path.
- No new install-path logic; we extend existing machinery.

**Why tests are split (`test/python/` and `test/test-*.js`):**

- Python tests use stdlib `unittest` directly with no crossover into Node's test harness.
- Node integration tests use the existing harness and shell out to Python when they need to exercise cross-language scenarios.
- The split mirrors the source split: one runtime per test tree.

**Why fixtures live under `test/fixtures/compile/` and not per-module:**

- Golden-file scenarios are testing compile *behaviors* (TOML layering, glob expansion, cyclic include), not module semantics. A single `fixtures/compile/` tree makes it easy to find a representative example of any behavior.
- ~8–15 scenarios total (per Implementation Patterns §Test Organization) — not 50+ per-skill golden files.

## Architecture Validation Results

### Coherence Validation ✅

**Decision compatibility:**

- Python 3.11+ baseline is declared in §Developer Tool / Runtime (PRD), NFR-C1, Decision 5, Decision 17, and Implementation Patterns. Consistent across the doc.
- `fs-native.js` (Node I/O) and `bmad_compile/io.py` (Python I/O) are deliberately separate sandboxes; both are named consistently wherever I/O is discussed.
- Override root `_bmad/custom/` appears in: PRD §Installation Methods, PRD config surface, lockfile schema, Decision 8, §File Layout Conventions, §FR-to-file mapping. No stale `.bmad-overrides/` references remain.
- Four-construct template syntax + `{{self.*}}` TOML access is consistent across: PRD §Template syntax, Appendix A `<Variable>` schema, Decision 1 parser, Decision 3 resolver.
- Lockfile schema fields (`toml_customization`, `glob_inputs`, `lineage`, `previous_base_hash`, `declared_by`, `template_from`) appear consistently in: PRD §Public API / Lockfile, Appendix A example, Decision 4, §File Layout Conventions, §FR-to-file mapping.
- Error vocabulary (frozen 6 codes) is consistent: NFR-M5 (PRD) = Decision 11 (arch) = Implementation Patterns error-format table = Anti-Patterns examples.
- Fragment precedence (5-tier `user-full-skill > user-module-fragment > user-override > variant > base`) is consistent: FR10, Decision 2, Decision 10's containment scope, §Cross-Plane Precedence Matrix.
- Variable precedence (two-namespace cascade) is consistent: PRD §Public API precedence note, Appendix A table, Decision 3 restated cascade.

**Pattern consistency:**

- Naming conventions from Implementation Patterns align with: Python module names under `bmad_compile/`, Node file names under `tools/installer/`, CLI flag names in PRD §Public API.
- Determinism enforcement (I/O sandbox + grep-check + layering test) aligns with NFR-R1, Decision 10, NFR-M2 test coverage, §Test Organization.
- CI gates in Implementation Patterns (`mypy --strict`, layering test, golden-file, `validate:compile`) align with FR49, FR50, NFR-M4.

**Structure alignment:**

- The process boundary diagram, library-layer diagram, and plane-boundary diagram in Project Structure are each supported by corresponding Decisions (5, 17/10, 3/8/18).
- FR-to-file mapping covers every FR and NFR; no requirement lacks a named file or subsystem.
- Integration-point diagrams match Decision 6 (installer seam), Decision 8 (bmad-customize flow), Decision 16 (lazy compile), Decision 5 (drift triage via halted upgrade).

### Requirements Coverage Validation ✅

**Functional Requirements coverage (FR1–FR58):**

Every FR appears in the FR-to-file mapping table with a primary file and test coverage assignment. Cross-checked:

- Template authoring (FR1–7): parser, error messages — ✅.
- Fragment composition (FR8–12): resolver, engine, io — ✅.
- User override management (FR13–17, including new FR13a): resolver, toml_merge, override-root walk — ✅.
- Installation & upgrade (FR18–24): Node commands, Python engine drift calculator — ✅.
- Compile primitives (FR25–33): Python entry point, explain renderer — ✅.
- Customization skill (FR34–39, FR54): skill-side + engine's `--explain --json` and `--diff` — ✅.
- Drift detection & lockfile (FR40–43, FR55–57): lockfile writer, upgrade command, halt-on-drift logic — ✅.
- IDE variants (FR44–46): variants module — ✅.
- Module distribution (FR47–48): installer core, resolver namespace — ✅.
- Validation & CI (FR49–53): `tools/validate-compile.js`, integration tests — ✅.
- Lazy compile-on-entry (FR58): `lazy_compile.py` + SKILL.md shim — ✅.

**Non-Functional Requirements coverage:**

- **Performance (NFR-P1–P5):** addressed by Decision 12 (hash-based skip), Decision 5 batch mode, lazy-compile fast path; tested via nightly benchmark CI (new job).
- **Security (NFR-S1–S6):** NFR-S1 via `lockfile.py` value-hash-only rule; NFR-S2 via `io.py` containment; NFR-S3 via resolver namespace-collision check; NFR-S4 via trust-mode gate; NFR-S5 via zero network I/O contract (enforced by absence of `http`/`urllib`/`socket` imports); NFR-S6 via "stdlib only + no new Node deps."
- **Reliability (NFR-R1–R5):** NFR-R1 via `io.py` boundary + three-OS CI; NFR-R2–R4 via io.py implementation details; NFR-R5 via advisory locks + lockfile integrity refusal.
- **Compatibility (NFR-C1–C5):** NFR-C1 dual-runtime check; NFR-C2 OS matrix in CI; NFR-C3 IDE variant support; NFR-C4 verbatim-copy fallback regression suite; NFR-C5 lockfile version+additive-field policy.
- **Observability (NFR-O1–O5):** NFR-O1 via lockfile audit trail; NFR-O2 via `--explain`; NFR-O3 via error format with caret + see-link; NFR-O4 via `--dry-run --json`; NFR-O5 via `--debug` stderr channel.
- **Maintainability (NFR-M1–M5):** NFR-M1 frozen syntax + unknown-directive test; NFR-M2 adjacent-tier resolution tests; NFR-M3 docs-as-ship-gate; NFR-M4 golden-file contract tests; NFR-M5 frozen error enum.

**All PRD requirements are architecturally supported.** No FR or NFR lacks a design decision or implementation target.

### Implementation Readiness Validation ✅

**Decision completeness:** 18 Decisions document every critical + important architectural choice. Decision Impact Analysis names build-order dependencies. All Decisions specify implications and trade-offs.

**Structure completeness:** Project Structure names every file that will be created/modified, plus integration points, data flow, and file-organization rationale.

**Pattern completeness:** Implementation Patterns enumerate 10 conflict categories + 2 cross-cutting concerns (concurrency, cross-plane precedence) with explicit rules and examples. Anti-Patterns paired with positive inverses where subtle.

**AI-agent implementation guidance:** every agent starting a work item has:

- PRD FR + NFR to satisfy.
- FR-to-file mapping naming exact source file(s).
- Decision(s) providing design rationale.
- Implementation Patterns rules for coding discipline.
- Test coverage target (unit file, golden-file scenario, integration test).

### Gap Analysis Results

Six minor drifts were identified during validation. **All six have since been resolved in a follow-up cleanup pass** — either by applying an edit to the PRD/arch doc, or by explicitly validating as intentional. Status summary:

**Resolved (previously medium):**

1. **NFR-C2 vs Implementation Patterns CI matrix cadence** — RESOLVED. PRD NFR-C2 updated to match the pattern's cadence: Linux on every PR; all six OS/arch combinations on merge-to-`main`, nightly, and release-tag builds.

2. **Decision 12 (compile caching) deferrability** — RESOLVED. Decision Impact Analysis (step 4 + step 7 handoff) re-lists Decision 12 as mandatory Phase-6 work (ships with the lockfile; lazy-compile's fast path depends on it), not as a deferrable end-of-v1 optimization.

3. **`PRECEDENCE_UNDEFINED` error code** — RESOLVED. Added to PRD NFR-M5's frozen error vocabulary proactively (paired with the §Cross-Plane Precedence Matrix). Error-class hierarchy in Decision 11 updated. No more "TBD when first needed" language.

**Resolved (previously low):**

4. **`--lock-timeout-seconds` flag** — RESOLVED. Added to PRD FR24 as an advanced flag (default 300s) tuning the advisory-lock timeout for CI operators running slow compile environments.

5. **`--update-golden` flag** — NO ACTION (intentional). Test-infrastructure convenience; not a user-facing PRD FR. Documented in Implementation Patterns §Test Organization only.

6. **FR23's "Phase 1 capacity permitting" language** — RESOLVED. PRD FR23 updated to reflect that v1 ships drift triage via the `bmad-customize` skill (no separate CLI subcommand); stale phasing language removed.

**Not gaps (validated as intentional):**

- Lockfile commit recommendation is advisory, not required. Intentional.
- Layering test (`test_layering.py`) is internal quality tooling, not a PRD FR. Intentional — internal enforcement only.
- `invoke-python.js` shared Node helper is an implementation detail, not a PRD FR. Intentional.
- `bmad-help` skill mentioned as candidate migration target in PRD Code Examples; not called out in §File Layout. Intentional — migration set final at implementation time.

### Validation Issues Addressed

- **Party-Mode findings from step 5** (Winston, Amelia, Paige, Mary) were fully incorporated into Implementation Patterns: determinism boundary, batch mode, layering test, concurrency, lockfile schema evolution, cross-plane precedence matrix, error format with caret, `--update-golden` flag, ship-gate docs, contract-surfaces category.
- **PRD Open Questions** (staging semantics, rollback forward-compat, TOML coexistence) are marked RESOLVED in the PRD, with pointers to Decisions 4, 8, 16, 17, 18.
- **Medium drifts identified above** are flagged for a PRD follow-up PR but do not block implementation.

### Architecture Completeness Checklist

**✅ Requirements Analysis (Step 2)**

- [x] Project context analyzed (developer-tool subsystem, brownfield coexistence, two-plane customization)
- [x] Scale and complexity assessed (medium; 18 decisions; ~10 Python modules + ~3 Node adapters)
- [x] Technical constraints identified (Node ≥20, Python ≥3.11, stdlib-only, existing deps only)
- [x] Cross-cutting concerns mapped (determinism, security envelope, backward compat, observability, two-layer split, dogfood loop)

**✅ Architectural Decisions (Step 4)**

- [x] 18 Decisions documented (Decisions 1–15 plus course-correct Decisions 16, 17, 18)
- [x] Technology stack fully specified (Python 3.11 stdlib + Node 20 + existing deps)
- [x] Integration patterns defined (Node↔Python subprocess, library layering, lazy compile, drift triage)
- [x] Performance considerations addressed (hash-based skip, batch mode, lazy-compile fast path)

**✅ Implementation Patterns (Step 5)**

- [x] Naming conventions established (Python snake_case, Node kebab-case, CLI kebab flags, error codes UPPER_SNAKE)
- [x] Structure patterns defined (10 conflict categories + 2 cross-cutting; library layering + sandbox boundary)
- [x] Communication patterns specified (stdout/stderr contracts, JSON schema stability, exit codes)
- [x] Process patterns documented (error format + hint quality bar, concurrency locks, cross-plane precedence matrix, ship-gate docs)

**✅ Project Structure (Step 6)**

- [x] Complete directory structure defined (source tree + install tree, consolidated)
- [x] Component boundaries established (process, library layers, customization planes)
- [x] Integration points mapped (compile-time, skill-entry, bmad-customize authoring, upgrade drift-triage, data flow)
- [x] Requirements-to-structure mapping complete (every FR + NFR → file + test)

### Architecture Readiness Assessment

**Overall Status:** READY FOR IMPLEMENTATION

**Confidence Level:** High.

**Key Strengths:**

- Deterministic compilation contract pinned at a single module boundary (`bmad_compile/io.py`) rather than as cross-cutting discipline — strongest NFR-R1 guarantee possible.
- Course-correct absorption of upstream TOML customization preserves user UX while eliminating parallel-plane complexity via the shared library (Decision 17) and lazy-compile guard (Decision 16).
- Cross-plane precedence matrix closes the predicted day-one bug class (Mary's finding); enforced by per-row golden-file tests.
- Every FR and NFR has a named file, a named test, and a documented decision rationale.
- Error UX (frozen codes, caret spans, hint quality bar, ship-gate "When Compile Fails" doc) serves all three audiences (skill authors, end users, contributors).

**Areas for Future Enhancement (post-v1):**

- Richer TOML semantic-drift UX beyond the v1 dry-run notification (Phase 2).
- Workflow-step Markdown compilation — step body files themselves (e.g., `steps/step-01-init.md`) become compilable inputs, activating the reserved `workflow-config` tier and source enum value for step-scoped YAML variables. **Scope boundary:** this is step *body* compilation only; workflow *metadata* (activation_steps_prepend/append, persistent_facts, on_complete) is already owned by upstream's `customize.toml` system — PR #2287 migrated 17 bmm-skills onto it and deleted their `workflow.md` files — and remains outside compiler v1 scope with no absorption planned.
- `bmad upgrade --rollback` — schema already supports via `lineage` field; implementation is future work.
- Cross-skill references with cycle detection (Level 5 per PRD §Post-MVP).
- Python render-function extensions gated by `trust_mode: full` (Level 3).
- LLM-assisted compilation with bounded context summarization (Level 6).
- IDE variant expansion beyond Claude Code + Cursor (VS Code, JetBrains, Gemini CLI).

### Implementation Handoff

**AI Agent Guidelines:**

- Follow all architectural Decisions as documented; annotate source files with the Decision numbers they implement (`# Decision 3: variable resolver ...`).
- Use Implementation Patterns rules consistently across all components; grep and layering tests enforce.
- Respect the three boundaries — process (Node↔Python), library (10 Python layers), plane (TOML/prose/YAML).
- Emit typed `CompilerError` subclasses per NFR-M5 frozen vocabulary; never swallow `Exception`.
- Refer to this document for all architectural questions; PRD for requirement rationale.

**First Implementation Story:** Bootstrap the shared library + smallest end-to-end compile.

1. Create `src/scripts/bmad_compile/` skeleton with `errors.py`, `io.py` (minimal read/write + hash + path normalization), and `LAYERING.md`.
2. Add `test/python/test_layering.py` AST-walking import checker; CI-gate it from day one.
3. Implement `parser.py` + `test/python/test_parser.py` for the four constructs including `{{self.*}}`.
4. Implement minimal `engine.py` that compiles a single hand-written fixture `bmad-help` skill (one `{{var}}` reference, no fragments, universal variant) to byte-identical output as the existing installed `SKILL.md`.
5. Add the first golden-file fixture `test/fixtures/compile/smoke/` exercising (4).
6. Wire `tools/installer/commands/compile.js` → `invoke-python.js` → `python3 src/scripts/compile.py --skill bmad-help`; add `test/test-compile-integration.js` smoke case.

This story proves the cross-language seam, the library-layering enforcement, the I/O determinism boundary, and the golden-file pattern — the foundation every subsequent story builds on.

**Downstream work order (per Decision Impact Analysis):**

1. Foundation: parser, io, errors, layering test.
2. Core resolution: fragment resolver, variable resolver (two-namespace cascade), `toml_merge` (refactor from `resolve_customization.py`).
3. Variant selection.
4. Glob inputs.
5. Lockfile (full schema with `toml_customization`, `glob_inputs`, `lineage`).
6. Hash-based skip (mandatory, not optional) — ships with the lockfile since the skip path reads the lockfile's hashes as its cache-coherence source.
7. CLI + installer integration; distribution-model detection; module boundary.
8. Lazy compile-on-entry; SKILL.md shim refactor.
9. Skill integration (`bmad-customize`) + drift-triage flow.
