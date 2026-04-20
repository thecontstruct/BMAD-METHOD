---
stepsCompleted:
  - step-01-init
  - step-02-discovery
  - step-02b-vision
  - step-02c-executive-summary
  - step-03-success
  - step-04-journeys
  - step-05-domain
  - step-06-innovation
  - step-07-project-type
  - step-08-scoping
  - step-09-functional
  - step-10-nonfunctional
  - step-11-polish
  - step-12-complete
completedAt: '2026-04-17'
inputDocuments:
  - /home/user/bmad-opensource-teamspace/proposals/bmad-skill-compiler-proposal-v3.md
  - /home/user/bmad-opensource-teamspace/proposals/research-prompt-compilation-landscape.md
workflowType: 'prd'
documentCounts:
  briefCount: 0
  researchCount: 1
  brainstormingCount: 0
  projectDocsCount: 0
  proposalCount: 1
projectMode: greenfield-from-proposal
scope: minimum-viable-rollout
classification:
  projectType: developer_tool
  domain: general
  complexity: medium
  projectContext: greenfield-subsystem-in-brownfield
  primaryUsers:
    - bmad-core-maintainers
    - bmad-module-authors
    - end-users-customizing-skills
  targetEnvironments:
    - claude-code
    - cursor
  migrationConstraint: preserve-verbatim-install-for-unmigrated-skills
vision:
  statement: >-
    Authored Markdown skills stay the edge format; a deterministic compiler sits
    beneath them so fragments assemble predictably, user overrides survive
    upgrades, and drift is auditable via a lockfile.
  differentiator: >-
    First integrated system combining fragment composition, compile-time
    assembly, upgrade-safe user overrides, multi-IDE variants, and drift
    visibility. No existing tool (DSPy, Prompt Flow, Cursor rules, CrewAI)
    covers this set.
  coreInsight: >-
    Prompts are source code and need a build pipeline. Anything that can be
    assembled deterministically should not be delegated to the model at
    runtime.
  problemReframe: >-
    The real failure mode is erosion of trust in BMad itself: users fork on
    upgrade or lose edits, maintainers fear cross-file refactors. The compiler
    restores confidence on both sides.
  northStarMetrics:
    primary: zero-customization-loss-across-one-full-upgrade-cycle
    secondary: percent-skills-using-shared-fragments
    tertiary: user-override-adoption-rate
  antiGoals:
    - no-python-render-functions-in-v1
    - no-jit-invoke-time-assembly-in-v1
    - no-artifact-aware-collectors-in-v1
    - no-llm-assisted-compilation-in-v1
  delightMoment: >-
    User runs `bmad upgrade`; overrides survive cleanly OR `bmad-customize`
    walks the user through each version's change-set and plans the upgrade
    path against their overrides (impact preview, drift flags, guided
    reconciliation) before the upgrade is applied.
---

# Product Requirements Document - Compiled Skills (BMAD)

**Author:** Root
**Date:** 2026-04-17

## Executive Summary

BMAD Compiled Skills introduces a deterministic build pipeline beneath BMAD's authored Markdown skills. Skill sources (`*.template.md`) are assembled from shared fragments at install time, compile-time variables are resolved, IDE-specific variants are selected, and user overrides are layered on top — producing plain Markdown at the edge that IDEs and models consume unchanged.

Today, shared prompt blocks are duplicated across dozens of skills, any wording change requires cross-file grep-and-edit, and users who customize a skill face two bad options: edit the installed file and lose changes on upgrade, or fork the whole repo and diverge. The minimum-viable rollout delivers Levels 0–2 only — static Markdown, compile-time interpolation, and fragment composition — plus `bmad-customize` for guided overrides and `bmad.lock` for drift detection. Python render functions, invoke-time assembly, artifact-aware collectors, and LLM-assisted compilation are explicit non-goals for v1.

Primary users are BMAD core maintainers, third-party module authors, and end users who want upgrade-safe customization of installed skills. Target environments for the MVP are Claude Code and Cursor, with the existing "copy skill directory verbatim" install path preserved for any skill not yet migrated to template source.

The north-star outcome is zero loss of user customizations across a full upgrade cycle, with supporting metrics on fragment adoption across core skills and user override uptake.

### What Makes This Special

No existing tool combines fragment composition, compile-time assembly, upgrade-safe user overrides, multi-IDE variants, and drift visibility in one integrated system. DSPy learns prompts but does not compose them; Microsoft Prompt Flow orchestrates but lacks user override semantics; Cursor rules append but have no override safety or drift detection; CrewAI concatenates role strings. Each covers a slice; none solve customization durability across upgrades.

The core insight is that prompts are source code and need a build pipeline, not string concatenation. Anything that can be assembled deterministically should not be delegated to the model at runtime. The compiler exists to make the existing BMAD artifact model (initiative store, story front matter, `epic.md`, governance) easier to express and consume, not to replace it.

The delight moment is upgrade time: the user runs `bmad upgrade`, their customizations survive cleanly, and `bmad-customize` walks them through each version's change-set — showing impact previews against their overrides, flagging drift, and planning a reconciliation path before the upgrade is applied. The system turns "will my edits survive?" from an open anxiety into an audited workflow.

## Project Classification

- **Project Type:** Developer tool (compiler + CLI + lockfile + fragment library within the `bmad-method` npm package)
- **Domain:** General / prompt-engineering infrastructure — no regulated-domain constraints
- **Complexity:** Medium — include resolution, variant selection, override layering, and hash-based lockfile are real engineering; the MVP scope (Levels 0–2) excludes the higher-complexity Levels 3–6
- **Project Context:** Greenfield subsystem inside a brownfield codebase — coexists with the current verbatim-copy install path during migration

## Success Criteria

### User Success

- **Maintainers:** A shared prompt change requires editing one fragment file, not N skill files. Rebuild propagates the change; no cross-file grep required. Validation surfaces the affected compiled outputs before merge.
- **Module authors:** A new module can ship `*.template.md` source, reuse core fragments, and install cleanly alongside verbatim-copy modules. Authoring ergonomics match core authors — no extra tooling burden.
- **End users customizing skills:** Running `bmad-customize` discovers every fragment that contributes to a given skill, scaffolds an override in the correct location pre-populated with the active content, recompiles the affected skill(s), and shows a compiled-Markdown diff before the change is treated as done. Running `bmad upgrade` preserves every override that still applies, and `bmad-customize` presents the per-version change-set with impact preview, drift flags, and a guided reconciliation path for any override that no longer applies cleanly.

### Business Success

- **Adoption of shared fragments.** ≥ 50 % of core skills with identifiable duplicate prompt blocks migrated to `<<include>>` fragments within the first two minor releases post-launch.
- **User override uptake.** ≥ 25 % of active BMAD installs (measured via opt-in telemetry or self-report in the Discord community survey) have at least one user-authored override within 90 days of release.
- **Zero silent-loss upgrade cycle.** Across one complete release cycle (at least one minor version bump that touches shared fragments), the number of *silent* lost-customization incidents is zero. A surfaced conflict (reconcile-halt, drift-flag, merge-prompt) is not a loss. Measurement combines issue tracker / Discord reports with a post-upgrade opt-in prompt ("did all your overrides apply cleanly?") emitted by the installer so actual outcomes, not just reported ones, are counted.
- **Dogfood release gate.** Before release, `bmad-customize` skill (which is itself authored as template source per FR39) has survived at least one internal upgrade cycle with its own override reconciled. Own-cooking failure blocks release.
- **Module-author adoption.** At least two third-party modules ship template-source distribution (Model 2 or Model 3) within six months of release.

### Technical Success

- **Deterministic compilation.** Given identical source + overrides + config, compilation is byte-for-byte reproducible. Hash of compiled output is stable across runs and platforms.
- **Install contract preserved.** Any skill not yet migrated to template source continues to install exactly as it does today (verbatim copy). The compiler is opt-in per skill; mixed installs are first-class.
- **Override resolution order enforced.** User overrides always win over variant fragments, which always win over base fragments. Full-skill replacement is supported as an escape hatch. Resolution order is observable via `bmad compile --explain` and recorded in `bmad.lock`.
- **Drift visibility.** Every compile produces a `bmad.lock` entry recording source templates used, fragments resolved, variants selected, overrides applied, and output hash. A `bmad upgrade` dry-run surfaces drift (upstream-changed fragments with user overrides) before the upgrade applies.
- **IDE variant support.** Claude Code and Cursor variants are selectable via file naming (`*.cursor.template.md`) with a working universal fallback. No runtime conditional logic in compiled output.
- **Validation coverage.** `npm run validate:skills` passes on every compiled skill; lockfile drift surfaces as a CI-visible failure, not a silent warning.

### Measurable Outcomes

| Outcome | Target | Source |
|---|---|---|
| Silent customization-loss incidents per release cycle | 0 | Issue tracker, Discord, post-upgrade opt-in prompt |
| Dogfood release gate: `bmad-customize` skill survives own upgrade cycle | pass | Internal dogfood log, release checklist |
| Core skills with shared fragments | ≥ 50 % of duplicate-heavy skills | Repo audit |
| Users with ≥ 1 override | ≥ 25 % of active installs | Opt-in telemetry / survey |
| Third-party modules shipping template source | ≥ 2 | Module registry |
| Compiled output hash stability | 100 % across identical inputs | CI check |
| Verbatim-install compatibility for unmigrated skills | 100 % | CI regression suite |

## Product Scope (Summary)

The v1 delivers Appendix C steps 1–4 of the v3 proposal, scoped to Levels 0–2 only: fragment extraction, template-source compile pipeline, user overrides (plus `bmad-customize` skill for guided authoring), and `bmad.lock` drift detection. Target environments are Claude Code and Cursor; the install command remains `npx bmad-method install ...` with the verbatim-copy path preserved for unmigrated skills.

Full MVP feature set, phased roadmap, and risk-mitigation strategy are defined in [Project Scoping & Phased Development](#project-scoping--phased-development) below. That section is the binding scope definition; this summary exists only to orient readers arriving from the Executive Summary.

## User Journeys

### Journey 1 — Maya, Core Maintainer: Refactor a Shared Prompt Block

**Opening.** Maya maintains the BMAD core skills. A reviewer flags that the "activation rules" prose in `bmad-agent-pm` contradicts the same block in `bmad-agent-architect`. Maya audits: the block is copy-pasted across seven skills with three subtly different wordings. Refactoring means seven file edits and seven PR hunks she cannot easily diff.

**Rising action.** Maya runs `bmad compile bmad-agent-pm --explain --tree` and sees the skill is currently a monolithic `SKILL.md` with no fragments declared. She converts the shared block to `fragments/activation-rules.template.md`, updates seven `*.template.md` sources to reference it via `<<include>>`, and runs `npm run test:refs`. The validator reports every compiled skill that depends on the fragment.

**Climax.** Maya edits the one fragment file. `npm run validate:skills` recompiles all dependents and diffs the compiled output against `bmad.lock`. Seven compiled `SKILL.md` files change; all seven diffs show the single intended edit. CI is green.

**Resolution.** The PR touches one fragment plus seven one-line includes. Reviewers read the fragment once and trust the propagation. Maya's next cross-skill prose change is a one-file edit, not a grep-and-fix sweep.

**Requirements revealed.** Fragment extraction + `<<include>>` resolution; dependency tracking for validation and diff; lockfile-backed compiled-output diff; CI hook that fails on drift between lockfile and recompile.

### Journey 2 — Diego, End User: Override One Fragment, Survive Upgrade

**Opening.** Diego runs a boutique consultancy and uses BMAD for client work. The default PM skill's "menu handler" block is slightly too terse for his clients, who prefer more explicit next-step prompts. He has burned customizations twice on prior BMAD versions by editing installed `SKILL.md` files.

**Rising action.** He invokes `bmad-customize` skill for `bmad-agent-pm` in his IDE chat and describes what he wants to change in plain language. The skill discovers every contributing fragment (by calling `bmad compile --explain --json` under the hood), identifies the menu-handler fragment as the target, previews its current content, and scaffolds an override file at `.bmad-overrides/bmm/fragments/menu-handler.template.md` pre-populated with the active text. Diego edits the override (or lets the skill draft the edit and reviews it), and the skill calls `bmad compile bmad-agent-pm --diff` to render the unified diff of the final compiled `SKILL.md` before Diego commits.

**Climax.** A week later BMAD 6.4 ships. `bmad upgrade --dry-run` reports: "menu-handler.template.md unchanged upstream; your override still applies cleanly. 3 other fragments changed in core; your overrides are not affected." Diego runs `bmad upgrade`. His override survives verbatim.

**Resolution.** Diego stops worrying about upgrade risk. Customization becomes something he does casually, not defensively.

**Requirements revealed.** Override-resolution order (user > variant > base); override root convention; `bmad-customize` discover/scaffold/preview/recompile/diff flow; `bmad upgrade --dry-run` impact preview; `bmad.lock` tracking per-fragment resolution.

### Journey 3 — Diego (Edge Case): Upgrade With Drift, Guided Reconciliation

**Opening.** Three months later, BMAD 6.5 ships and substantially rewrites the menu-handler fragment Diego overrides.

**Rising action.** `bmad upgrade --dry-run` reports: "menu-handler.template.md: upstream content changed significantly (diff attached). Your override diverges from the new base. Reconciliation needed." Diego runs `bmad upgrade --reconcile`, which walks him through a side-by-side view: upstream old → upstream new → his current override. The tool shows which passages upstream changed, which of his edits are additive (safe to keep), and which conflict with upstream intent. (The `bmad-customize` skill can be invoked mid-reconcile to reason about complex merges in plain language.)

**Climax.** Diego chooses per passage: keep his override, adopt upstream, or merge. The tool writes a reconciled override, recompiles, and runs validation. `bmad.lock` records both the old and new base hashes so the decision is auditable.

**Resolution.** No silent loss. No silent merge conflict in a compiled output at runtime. Diego's override is either intentionally preserved or intentionally rewritten, with a record of why.

**Requirements revealed.** Upgrade drift detection per fragment; upstream-base diff surface; three-way reconciliation UX; audit trail in `bmad.lock` for override lineage across versions.

### Journey 4 — Priya, Third-Party Module Author: Ship Template Source

**Opening.** Priya authors a domain-specific BMAD module (`bmad-module-legaltech`). She wants to reuse the same "persona-guard" fragment that core uses, without copy-pasting it into every agent skill in her module.

**Rising action.** Her module declares a dependency on `@bmad/core-fragments`. Her `*.template.md` sources include `<<include path="core/persona-guard.template.md">>`. At install time, the compiler resolves both core fragments and her module-local fragments. She ships Model 2 (template source); users who run an older BMAD installer without compiler support get a precompiled fallback (Model 3) she publishes alongside.

**Climax.** A user installs both core BMAD and her legaltech module. The installer produces compiled `SKILL.md` files that share the core persona-guard content. The user later overrides persona-guard for their install; Priya's module respects the override because resolution runs through the same pipeline as core.

**Resolution.** Priya's module has the same customization surface as core. Users customize once; it applies everywhere.

**Requirements revealed.** Cross-module fragment reference with explicit core-fragment namespace; distribution-model declaration (precompiled / template source / both); installer support for Model 3 fallback; module boundary enforcement (core cannot be silently overridden by a module install).

### Journey Requirements Summary

Capabilities revealed across journeys:

| Capability | Journeys |
|---|---|
| Fragment authoring + `<<include>>` resolution | 1, 2, 4 |
| `*.template.md` → `SKILL.md` compile pipeline | 1, 2, 4 |
| Dependency tracking for validation and recompile | 1 |
| User override root with upgrade-safe resolution order | 2, 3 |
| `bmad-customize`: discover / scaffold / preview / recompile / diff | 2, 3 |
| `bmad upgrade --dry-run` with per-fragment impact preview | 2, 3 |
| Three-way reconciliation UX for drifted overrides | 3 |
| `bmad.lock` recording sources, resolutions, overrides, output hashes | 1, 2, 3 |
| CI hooks: drift failure, lockfile integrity | 1 |
| Cross-module fragment reference + module boundary enforcement | 4 |
| Distribution models for modules (precompiled / source / both) | 4 |
| IDE variant selection (Claude Code, Cursor) via file naming | all (implicit) |

## Domain-Specific Requirements

Not applicable. This is a developer-tooling / prompt-engineering-infrastructure project with no regulated-domain constraints (no healthcare, fintech, govtech, aerospace, etc.). Technical constraints (determinism, lockfile integrity, override resolution order, trust model for future Python-backed fragments) are captured under Technical Success and will be expanded in Non-Functional Requirements.

## Innovation & Novel Patterns

### Detected Innovation Areas

- **First integrated compile-capable skill pipeline.** The research (`research-prompt-compilation-landscape.md`) confirms no existing project combines fragment composition, build-time compilation, upgrade-safe user override semantics, multi-IDE adaptation, and drift detection in one system. DSPy optimizes, Prompt Flow orchestrates, Cursor rules append, CrewAI concatenates — none cover the full set. BMAD Compiled Skills fills this gap.
- **Prompt-engineering lockfile (`bmad.lock`).** Treating a compile pipeline's output as a signed, reproducible artifact — with recorded source templates, resolved fragments, selected variants, applied overrides, and output hashes — is standard in traditional software build tooling but absent in the prompt-composition space. This is a direct transplant of a proven pattern into a new medium.
- **Three-way reconciliation for user overrides across upgrades.** `bmad upgrade --reconcile` shows upstream-old → upstream-new → user-override and lets the user resolve per passage; `bmad-customize` skill can be invoked mid-reconcile for natural-language reasoning about complex merges. No surveyed project (Cursor rules, Cline custom instructions, Prompt Flow variants) offers override reconciliation at this granularity. Closest analog is `git merge --tool`, repurposed for authored prompt content rather than source code.
- **Intentionally restricted authoring surface.** The v1 syntax is four constructs: Markdown passthrough, `<<include path="...">>`, `{{var}}`, `{var}`. Surveyed systems either use full Jinja (Prompt Flow), full Python (DSPy), or no composition at all (CrewAI). A deliberately minimal surface is itself a design choice — it keeps the mental model trivial for solo authors while leaving room for advanced layers (Levels 3–6) behind explicit opt-in.
- **User-wins resolution order as a first-class contract.** Many systems treat user customization as a string append or config override. Here it is a documented merge-order (base → variant → user-fragment → user-module-fragment → user-full-skill) enforced by the compiler and recorded in the lockfile. The user always wins, and the system can prove it did.

### Market Context & Competitive Landscape

Competitor coverage per the research matrix:

| System | Composition | Compile | User Override | Multi-IDE | Drift Detection |
|---|---|---|---|---|---|
| Microsoft Prompt Flow | YAML DAG | Jinja | — | Partial | — |
| DSPy | — | Learned | — | Yes | — |
| Cursor Rules | File append | — | Basic | — | — |
| Cline | Context | JIT | Basic | — | — |
| CrewAI | Role string | — | — | — | — |
| Dust.tt | Visual | Server | — | — | — |
| Marvin | Type-based | Implicit | — | Yes | — |
| **BMAD Compiled Skills (v1)** | **MDX-lite fragments** | **Build-time** | **Full with override root** | **CC + Cursor** | **`bmad.lock`** |

BMAD is the first system in the surveyed landscape to check all five columns simultaneously.

### Validation Approach

- **Internal canary.** Migrate 3–5 high-duplication core skills to `*.template.md` + fragments before general release. Measure: (a) single-fragment edit propagation time vs. current grep-and-edit, (b) CI recompile + lockfile diff stability across 10 consecutive commits.
- **Closed beta cohort.** Recruit 10–20 BMAD power users (Discord community, consultancies) for a pre-release with `bmad-customize` enabled. Measure: override creation rate, reported upgrade-safety incidents, survey on reconciliation UX.
- **Upgrade simulation.** Ship 6.3.x → 6.4.x through two deliberate fragment changes — one bug-fix (non-conflicting) and one rewrite (drift-inducing) — and verify `bmad upgrade --dry-run` correctly classifies each against overrides.
- **Module-author dogfooding.** Port one existing community module to Model 2 (template source) with help from the core team. Measure author time-to-integration and surface any missing primitives before the API is frozen.

### Risk Mitigation

- **Fallback path preserved.** The verbatim-copy install path is a required, tested code path, not a deprecation target. If the compiler ships with unknown-unknowns, every skill not yet migrated is unaffected and the blast radius is scoped.
- **Explicit anti-goals prevent scope creep.** Python render functions (Level 3), JIT / invoke-time assembly (Level 4), artifact-aware collectors, and LLM-assisted compilation (Level 6) are documented as out-of-scope for v1. Review gate: any proposed v1 feature that introduces one of these patterns is rejected.
- **Trust model defined for future advanced layers.** When Level 3 (Python) is introduced, it is gated behind `compiler: { trust_mode: full }` in config. The gate is both a security boundary and a statement of intent — advanced is advanced, not the default.
- **Syntax surface is frozen for v1.** Four constructs. No conditionals, no loops, no custom tags. This makes the compiler fully specifiable, the output fully auditable, and bug classes small. Any syntax proposal is a post-v1 conversation.
- **Drift surfaces early, not at runtime.** Drift is detected at `bmad upgrade` time, not at skill-invocation time. A broken prompt at runtime is a user-trust incident; a flagged drift at upgrade time is a workflow step. The lockfile makes this difference possible.

## Developer Tool Specific Requirements

### Project-Type Overview

BMAD Compiled Skills ships as a subsystem of the `bmad-method` npm package (currently v6.3.0). It adds a compile pipeline to the existing installer without changing the install command or breaking the verbatim-copy path for unmigrated skills. The public surface is four artifacts: a template syntax for skill authors, a CLI command set for users, a config block for installs, and a lockfile for audits.

### Technical Architecture Considerations

- **Runtime.** Node.js ≥ 20 (matches existing `bmad-method` engine requirement). No Python for v1 — Python is deferred to Level 3 (computed fragments) behind `trust_mode: full`.
- **Dependencies.** Reuse existing `bmad-method` dependencies (`commander`, `fs-extra`, `glob`, `js-yaml`, `xml2js`, `semver`). Introduce no new runtime deps in v1; if a Markdown parser is needed beyond the existing `@kayvan/markdown-tree-parser`, evaluate for minimal surface.
- **Packaging.** All compiler code lives under `tools/installer/compiler/` in the `bmad-method` repo. The compiler is invoked by every CLI subcommand (`install`, `upgrade`, `compile`) and is not exposed as a separate package in v1.
- **Two-layer design.** Mechanical operations (install, upgrade, drift detection, per-skill recompile, provenance rendering) live in the CLI and are fully deterministic. Intent-to-change reasoning (interpret a user's customization request, pick the right override target, draft the edit) lives in `bmad-customize` skill, which calls CLI primitives under the hood. This keeps safety-critical paths deterministic while using LLM reasoning only where human intent is fuzzy.
- **Single-engine plumbing, layered porcelain.** All CLI subcommands route to the same `compile()` engine with different input sets. The `bmad-customize` skill is a consumer of that engine via `bmad compile`, not a parallel path.
- **Execution model.** Static compilation only for v1. Compile runs at install time, at explicit `bmad compile <skill>` time, and at `bmad upgrade` time. No invoke-time assembly (explicit anti-goal).
- **Output contract.** Compiled output is plain Markdown (`SKILL.md` or workflow-step `.md`). IDEs and models see no compiler artifacts at runtime. The `--explain` output is diagnostic only and is never installed.

### Language & Environment Support

| Axis | v1 Support | Notes |
|---|---|---|
| Node.js runtime | ≥ 20.0.0 | Matches current `bmad-method` engine |
| Python | Not used at runtime in v1 | Deferred to Level 3; documented as post-v1 |
| IDE — Claude Code | Full (universal fragments + `.claudecode.template.md` variants if needed) | Primary target |
| IDE — Cursor | Full (`.cursor.template.md` variants) | Co-primary target |
| IDE — others (VS Code, JetBrains, Gemini CLI) | Deferred | Growth scope; add as demand proven |
| OS | macOS, Linux, Windows (same matrix as `bmad-method` today) | No OS-specific compiler behavior |

### Installation Methods

- **Existing path unchanged.** `npx bmad-method install` continues to work. The installer detects whether a skill directory has `*.template.md` source and branches:
  - Template present → compile, apply overrides, write `SKILL.md` to install location.
  - Template absent → copy skill directory verbatim (existing behavior).
- **Smart `install` default.** On an existing install, `bmad install` detects prior state (via `bmad.lock`) and auto-routes to `bmad upgrade --dry-run` followed by an interactive confirmation, rather than silently reinstalling over user overrides. This preserves one-command muscle memory while making upgrade paths safe by default.
- **Non-interactive install** (`--yes`) remains supported. Compiler defaults: no overrides applied, universal variant, config-default vars.
- **Explicit subcommands.** `bmad upgrade` and `bmad compile` exist as dedicated subcommands for discoverability. `upgrade` can also be reached indirectly by running `bmad install` on an existing install. All subcommands share `--directory`, `--modules`, `--tools`, `--override-root`, and `--yes`.
- **Customization is a skill, not a subcommand.** `bmad-customize` ships as a first-class BMAD skill (one of the MVP-migrated reference skills). Users invoke it from their IDE chat with natural-language intent; the skill calls `bmad compile` primitives for the mechanical work.

### Public API Surface

**Template syntax (authoring API, frozen for v1):**

| Construct | Purpose | Example |
|---|---|---|
| Markdown passthrough | Plain content | Any non-construct text |
| `<<include path="..." [local-props]>>` | Inline another template or fragment | `<<include path="fragments/persona.template.md" help-skill="bmad-help">>` |
| `{{var_name}}` | Compile-time variable | `{{agent_display_name}}` |
| `{var_name}` | Runtime placeholder, passed through verbatim | `{user_name}` |

**CLI surface (subcommands of `bmad` / `bmad-method`) — mechanical layer, deterministic:**

| Command | Purpose |
|---|---|
| `bmad install` | Fresh install, or re-install. On an existing install, auto-routes to `upgrade --dry-run` + confirm. |
| `bmad upgrade [--dry-run] [--reconcile]` | Recompile against new core templates; `--dry-run` previews impact against user overrides; `--reconcile` launches three-way merge for drifted overrides. Reconciliation is only reachable via this flag in v1; it is not a top-level subcommand. |
| `bmad compile <skill>` | Recompile a single skill from its template source plus applied overrides. Writes the compiled `SKILL.md` to the install location. |
| `bmad compile <skill> --diff` | Emit a unified diff of the newly compiled output against the currently installed file, without writing. |
| `bmad compile <skill> --explain [--tree \| --json]` | Annotated provenance view (see `--explain` Output below). Default format is Markdown with inline XML provenance tags; `--tree` renders the fragment dependency tree only; `--json` emits a machine-readable structure for editor tooling and `bmad-customize` skill. |

`bmad compile` is the mechanical primitive; it does no reasoning about user intent. It is callable directly by power users, by CI, and by `bmad-customize` skill.

Shared flags across subcommands: `--directory <path>`, `--modules <ids>`, `--tools <ids>`, `--override-root <path>`, `--yes`, `--debug`.

**Skill surface — reasoning layer:**

| Skill | Purpose |
|---|---|
| `bmad-customize` | Interpret a user's natural-language customization intent, discover the right override target (fragment / variable / full-skill replacement), draft the override content, call `bmad compile --diff` to show impact, and negotiate acceptance with the user. Called from IDE chat, not from a terminal. Built on top of `bmad compile --explain --json` for discovery and `bmad compile --diff` for preview. The skill itself is written as a template and compiled by the same pipeline it helps users customize. |

**`--explain` Output (provenance view).**

Goal: render the final compiled Markdown with inline XML tags that attribute every non-literal chunk to its source. Output is diagnostic — stdout by default, never installed.

Tag vocabulary (v1):

| Tag | Purpose | Required Attributes | Optional Attributes |
|---|---|---|---|
| `<Include>` | Fragment inclusion boundary | `src`, `resolved-from` (`base` / `variant` / `user-override` / `user-module-fragment` / `user-full-skill`), `hash` | `base-hash`, `override-hash`, `override-path` (when `resolved-from` is an override), `variant` (when `resolved-from=variant`) |
| `<Variable>` | `{{var}}` interpolation | `name`, `source`, `resolved-at` (always `compile-time` for `{{var}}` in v1) | `source-path` (file that supplied the value) |

`<Variable source="…">` enumerates where the value came from. Permitted values in v1:

| `source` value | Meaning |
|---|---|
| `install-flag` | Value was set via a CLI flag to `bmad install` / `bmad upgrade` / `bmad compile` at the current invocation (e.g., `--user-name`). **Highest precedence.** |
| `user-config` | Value came from a user-authored config file under the override root (`<override_root>/[<module>/[<workflow-path>/]]config.yaml`). Most-specific path wins within this tier. |
| `module-config` | Value came from the active module's `config.yaml` (e.g., `_bmad/bmm/config.yaml`), from keys above the `# Core Configuration Values` marker. Also used in v1 for workflow-scoped `<module>/<workflow-path>/config.yaml` values (disambiguated via `source-path`); a dedicated `workflow-config` enum value is reserved for a future major version. |
| `bmad-config` | Value came from BMAD core config (`_bmad/core/config.yaml`), or from keys below the `# Core Configuration Values` marker inside a module's `config.yaml`. |
| `env` | **Reserved — not emitted in v1.** Retained in the enum for forward compatibility; v1 compiler never reads `process.env` for variable resolution and never emits this source value. |
| `derived` | Computed at compile time from an enumerated allowlist (install-absolute paths, BMAD/module versions, current-module/skill/variant identifiers, resolved `directories:` entries from `module.yaml`). No timestamps, no ambient state. |

**Precedence order (v1, highest to lowest):** `install-flag` > `user-config` > `module-config` > `bmad-config` > `derived`. `env` is reserved and never participates in v1 resolution. A variable's `source` reflects the first tier in which the name appears during the precedence walk.

Runtime placeholders (`{var_name}`) are **not** tagged in `--explain` output; they pass through unchanged so the output still previews what the model will actually receive.

Example `--explain` output:

```xml
<!-- bmad-agent-pm.SKILL.md — `bmad compile bmad-agent-pm --explain` -->

# Agent PM

## Identity

<Include src="fragments/persona-guard.template.md" resolved-from="base" hash="a3f9b21c…">
You are a product-focused PM facilitator...
</Include>

Welcome <Variable name="user_name" source="user-config" source-path=".bmad-overrides/config.yaml" resolved-at="compile-time">Root</Variable>.

<Include src="fragments/menu-handler.template.md" resolved-from="user-override" base-hash="b21c4d…" override-hash="e4d1a0…" override-path=".bmad-overrides/bmm/fragments/menu-handler.template.md">
[user-customized menu handler text]
</Include>

Runtime token that the model will resolve: {user_context}
```

`--tree` renders the same provenance metadata as an indented dependency tree (no content). `--json` serializes every `<Include>` / `<Variable>` as a structured object, preserving order, for use by editor plugins, LSP-style integrations, or future drift-visualization tools.

**Config surface (module `config.yaml`, additive):**

```yaml
compiler:
  enabled: true              # opt-in per module; false keeps verbatim-copy behavior
  override_root: .bmad-overrides  # where user overrides live (gitignored by convention)
  trust_mode: safe           # "safe" = Levels 0-2 only (default); "full" reserved for Level 3+ post-v1
```

**Lockfile (`bmad.lock`, schema v1):**

```yaml
version: 1
compiled_at: <release-pinned sentinel, NOT wall-clock>   # deterministic per release; see Reliability NFR-R1
bmad_version: 6.3.0
entries:
  - skill: bmad-agent-pm
    source: _bmad/bmm/skills/bmad-agent-pm/SKILL.template.md
    source_hash: <sha256>
    fragments:
      - path: fragments/persona-guard.template.md
        resolved_from: base
        hash: <sha256>
      - path: fragments/menu-handler.template.md
        resolved_from: user-override
        base_hash: <sha256>                 # current upstream base
        previous_base_hash: <sha256?>       # upstream base from prior compile; enables rollback forward-compat
        override_hash: <sha256>
        override_path: .bmad-overrides/bmm/fragments/menu-handler.template.md
        lineage:                            # audit trail of override/base history across upgrades
          - bmad_version: 6.3.0
            base_hash: <sha256>
            override_hash: <sha256>
          - bmad_version: 6.4.0
            base_hash: <sha256>
            override_hash: <sha256>
    variables:
      - name: user_name
        source: user-config
        source_path: .bmad-overrides/config.yaml
        declared_by: core                   # which module's module.yaml declared this variable
        template_from: core/module.yaml     # when a result-template was applied during resolution; omitted when none
        value_hash: <sha256>                # hash of resolved value, not plaintext (NFR-S1)
    variant: claude-code                    # or cursor / universal
    compiled_hash: <sha256>                 # hash of emitted SKILL.md
```

**Lockfile schema v1 field notes:**

- `compiled_at` is pinned to a release sentinel (e.g., the BMAD version tag), not wall-clock time, to satisfy NFR-R1 byte-for-byte reproducibility. Implementations that write wall-clock timestamps are non-conformant.
- `previous_base_hash` and `lineage` are additive forward-compat fields for a future `bmad upgrade --rollback` (out of v1 scope per PRD §Post-MVP). v1 writers populate them; v1 readers ignore lineage beyond the current compile.
- `declared_by` names the module whose `module.yaml` originally declared the variable (not necessarily the module whose `config.yaml` supplied the value; that is `source` + `source_path`).
- `template_from` names the `module.yaml` path whose `result:` template was applied to produce the resolved value (e.g., `output_folder` has `result: "{project-root}/{value}"` in `core/module.yaml`). Absent when no template was applied.
- Additive new fields (`previous_base_hash`, `lineage`, `declared_by`, `template_from`) are tolerated by any conformant v1 reader; unknown fields MUST be round-tripped unchanged by mechanical rewriters to preserve compatibility.

### Code Examples (Reference Skills)

The MVP ships with 3–5 core skills migrated to template source as canonical examples. Candidate set (final selection at implementation time):

- `bmad-agent-pm` — demonstrates persona fragment, menu-handler fragment, activation-rules fragment
- `bmad-agent-architect` — shares activation-rules fragment with pm; demonstrates reuse
- `bmad-create-prd` — demonstrates workflow-step-adjacent use (without Section 14 scope)
- `bmad-help` — demonstrates `{{var_name}}` interpolation for configured help-skill name
- `bmad-customize` — the customization skill itself, built as template source on top of the compiler it uses (dogfood example)

Each migrated skill ships a side-by-side snapshot: the old `SKILL.md`, the new `*.template.md` + fragments, the `bmad.lock` entry, and an `--explain` rendering.

### Migration Guide (Author-Facing)

Per Section 16.1 of the v3 proposal, migration is incremental:

1. **Identify duplication.** Run `bmad compile <skill> --explain --tree` on existing monolithic skills to visualize structure (initially, the tree is flat — that is the signal for where to extract).
2. **Extract fragments.** Move shared blocks to `fragments/<name>.template.md`. Replace call sites with `<<include path="...">>`.
3. **Keep contract.** Compiled output must match the original `SKILL.md` byte-for-byte initially. Use `npm run validate:skills` to confirm.
4. **Iterate.** Add variants (`*.cursor.template.md`) and compile-time vars (`{{var}}`) as discovered need arises.
5. **Publish.** Existing distribution unchanged — the npm package now ships both templates and a compiled fallback (Model 3) during the migration window.

Skipping the migration is a first-class choice: a module that prefers to ship pure Markdown (Model 1) continues to work without any compiler involvement.

### Implementation Considerations

- **CI integration.** A new `npm run validate:compile` target recompiles all templated skills and compares against `bmad.lock`. Any divergence fails CI.
- **Deterministic output across platforms.** No timestamps, no random IDs, no ordering dependent on filesystem enumeration. Fragment resolution order is specified (user > variant > base; alphabetical within tier).
- **Error messages target authors first.** Missing fragment path, unresolved `{{var}}`, cyclic include — each produces a message that names the template file and line, plus the `source` that was expected for a variable (from the `source` provenance rules above) when an interpolation fails.
- **No visual-design or store-compliance sections.** Not applicable to a developer-tool + npm-distributed library.

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP Approach: Problem-solving MVP.** The v1 exists to fix two concrete, measured pains — shared-prompt duplication for maintainers and upgrade-unsafe customization for users — on a small, high-signal subset of core skills. It is not an experience MVP (no new end-user UX beyond `bmad-customize` skill) and not a platform MVP (no ecosystem primitives that only pay off with mass adoption).

**Validated-learning target.** Across one full minor release cycle, demonstrate: (a) zero reported lost-customization incidents on migrated skills, (b) a single-fragment edit propagating to all dependent skills via one file change, (c) at least one third-party module author successfully porting to template source with documented time-to-integration.

**Resource shape.** One or two engineers plus a documentation contributor for roughly 6–10 weeks to ship the compile engine, CLI wiring, lockfile, `customize` wizard, 3–5 skill migrations, and author/user documentation. No dedicated product-design resource required — the UX surface is a CLI plus a small interactive prompt flow.

### MVP Feature Set (Phase 1)

**Core user journeys supported (from Journeys section):**

1. Maya the Core Maintainer — extract a shared fragment and propagate a one-file edit to all dependents.
2. Diego the End User — create a fragment override via `bmad-customize` skill, preview the diff, upgrade cleanly.
3. Diego (edge case) — drift reconciliation at upgrade time (minimum: drift is flagged and the user is halted for manual reconciliation; three-way merge UX is in-scope if capacity permits — see "Resource Risks" below).
4. Priya the Module Author — ship Model 2 (template source) with core-fragment references.

**Must-have capabilities:**

- Template compile pipeline: `*.template.md` → compiled `SKILL.md`; four syntax constructs only (Markdown passthrough, `<<include>>`, `{{var}}`, `{var}`).
- Fragment resolution with explicit precedence: user-override > user-module-fragment > variant > base.
- IDE variant selection via file naming: `*.cursor.template.md`, `*.claudecode.template.md` (if needed); universal fallback required.
- Single CLI binary with three mechanical subcommands: `bmad install`, `bmad upgrade [--dry-run] [--reconcile]`, `bmad compile <skill> [--diff] [--explain [--tree|--json]]`. All deterministic; no LLM reasoning.
- Smart `install` default: on an existing install, auto-routes to `upgrade --dry-run` + confirm.
- `bmad-customize` ships as a first-class BMAD skill (reasoning layer) that calls `bmad compile` primitives; not a CLI subcommand. Included among the 3–5 migrated reference skills (dogfood).
- Override root convention and resolution order documented and enforced by the compiler.
- `bmad.lock` schema v1 with source templates, resolved fragments, variables (name + source + value_hash), variant, and compiled output hash.
- `bmad upgrade --dry-run` impact preview: lists changed fragments, maps them to affected compiled skills, flags user overrides that diverge.
- `bmad compile <skill> --explain` with three formats (`md` default, `--tree`, `--json`).
- CI validation target (`npm run validate:compile`) that fails on lockfile drift.
- 3–5 canonical migrated core skills ship with the MVP as reference patterns (including `bmad-customize` itself).
- Backward-compatibility: verbatim-copy install path preserved for every skill not yet migrated.

**Must-have documentation:**

- Author-facing migration guide.
- User-facing `bmad-customize` skill walkthrough.
- `bmad.lock` schema reference.
- `--explain` tag vocabulary (for author / editor-tool consumers).

### Post-MVP Features

**Phase 2 — Growth (post-v1, near-term):**

- Full three-way merge UX for drifted overrides (if not shipped in v1 due to capacity).
- Workflow-step files participate in the same template/fragment/override pipeline (Section 14 of proposal).
- IDE variants beyond Claude Code and Cursor: VS Code extensions, JetBrains plugin context, Gemini CLI — added as demand is proven.
- Template linter, cross-module drift reports, fragment-usage registry for module authors.
- `bmad-customize` editor integrations (LSP-style) consuming `bmad compile --explain --json` output.
- Opt-in telemetry for override-adoption metrics (subject to privacy review).

**Phase 3 — Expansion (vision):**

- Level 3: computed fragments via Python render functions, gated behind `trust_mode: full`.
- Level 4: invoke-time assembly (JIT) for orchestrated flows and parent-child prompt assembly.
- Level 4 also: artifact-aware collectors (`InitiativeStoreCollector`, `GovernanceCollector`, etc.), additive and opt-in.
- Level 5: cross-skill references with explicit dependency rules and cycle detection.
- Level 6: LLM-assisted compilation for bounded, cached context summarization.
- Subagent orchestration layer built on deterministic child-prompt assembly.

### Risk Mitigation Strategy

**Technical risks.**

- *Syntax surface lock-in.* Four constructs in v1. Any proposed fifth construct is a post-v1 conversation and requires a major-version bump. Mitigation: explicit syntax-freeze documentation and a test suite asserting unknown directives emit a compile-time error rather than being silently ignored.
- *Cross-platform determinism.* Path separators, line endings, filesystem enumeration order. Mitigation: normalize paths to POSIX internally, pin line endings on emit, alphabetical ordering where enumeration matters, validation matrix includes macOS / Linux / Windows.
- *Override-resolution complexity.* Five-tier precedence (`user-full > user-module-fragment > user-override > variant > base`) has surface area for bugs. Mitigation: dedicated test suite covering every pair of adjacent tiers; every `bmad.lock` entry records `resolved_from` so resolution is observable.
- *Install-time performance regression.* Compile must not noticeably slow installs. Mitigation: hash-based skip — skills whose inputs match the prior lockfile entry are not recompiled; benchmark target of ≤ 10 % overhead vs. verbatim-copy on the BMAD reference install.

**Market / adoption risks.**

- *Insufficient migrated skill set.* If only 1–2 skills are migrated, the demo surface is too small to prove value. Mitigation: ship 3–5 migrated reference skills, chosen for high visible duplication, before general availability.
- *End users do not discover `bmad-customize`.* Mitigation: `bmad install --help` calls out the skill explicitly; post-install message mentions it with an example invocation; the first migrated skill's `SKILL.md` references it as the canonical way to tune behavior.
- *Module authors do not adopt templates.* Mitigation: Model 1 (precompiled) stays fully supported; no forced migration. Active outreach to one or two module authors for dogfood migration with core-team assistance.

**Resource risks.**

- *Three-way reconciliation UX scope.* Full guided merge is the most expensive single feature. Mitigation: v1 ships with a hard halt on drift (lockfile flags the divergence, user is told exactly which override conflicts and directed to edit it manually before re-running upgrade). Fully guided reconciliation is an explicit Phase 2 target if engineering bandwidth is constrained. This fallback still preserves the north-star metric (zero silent loss) even without the interactive UX.
- *Documentation debt.* A compiler that is under-documented is a net negative even if it ships correctly. Mitigation: docs are a ship gate, not a follow-up task — migration guide, `bmad-customize` skill walkthrough, and `--explain` vocabulary must be present in the release PR.
- *Scope creep into Level 3+ features.* Mitigation: anti-goals (no Python render, no JIT, no collectors, no LLM-assist) are documented here and will be treated as review-gate rejections for any v1 PR that introduces them.

## Functional Requirements

### Template Authoring

- FR1: Skill Author can write a skill source file with the suffix `*.template.md` sibling to the installed `SKILL.md`.
- FR2: Skill Author can include another template file by path using `<<include path="...">>`.
- FR3: Skill Author can pass local props to an included fragment via additional attributes on the `<<include>>` directive.
- FR4: Skill Author can declare a compile-time variable with `{{var_name}}` that will be resolved by the compiler before the skill is written to the install location.
- FR5: Skill Author can leave a runtime placeholder with `{var_name}` that passes through to the compiled output verbatim, for the model to resolve.
- FR6: Skill Author can author IDE-variant fragments using dotted suffixes (e.g., `persona-guard.cursor.template.md`) that are selected based on the target IDE at compile time, with a universal variant always available as a fallback.
- FR7: Skill Author receives a compile-time error (not a silent pass-through) for any unknown directive, unresolved `{{var}}`, missing include path, or cyclic include, with a message that identifies the template file and line.

### Fragment Composition & Resolution

- FR8: Installer can resolve `<<include path="...">>` recursively, combining fragments into a single compiled Markdown output.
- FR9: Installer can resolve `{{var_name}}` against a layered configuration (see Override Management) and emit the value into compiled output.
- FR10: Installer enforces a documented fragment-resolution precedence: `user-full-skill` > `user-module-fragment` > `user-override` > `variant` > `base`.
- FR11: Installer can detect and reject cyclic include chains at compile time.
- FR12: Installer produces byte-for-byte reproducible output given identical source, overrides, configuration, and target IDE.

### User Override Management

- FR13: End User can create an override for any individual fragment by placing a file at the documented override root (default: `.bmad-overrides/<module>/fragments/<name>.template.md`).
- FR14: End User can override a full skill by placing a complete `SKILL.md` (or `*.template.md`) at the corresponding path under the override root.
- FR15: End User can override a compile-time variable value by setting it in a user configuration file referenced by the override root.
- FR16: Installer applies overrides according to the precedence defined in FR10 and records the resolution outcome in the lockfile.
- FR17: Module Author cannot silently override a core fragment at install time; only the End User can register overrides of core behavior.

### Installation & Upgrade

- FR18: End User can run `bmad install` to perform a fresh install or a re-install into a target directory.
- FR19: `bmad install` detects an existing install (via presence of `bmad.lock`) and auto-routes to `bmad upgrade --dry-run` followed by an interactive confirmation, rather than silently reinstalling.
- FR20: Installer preserves the verbatim-copy install path for any skill directory that has no `*.template.md` source, guaranteeing backward compatibility for unmigrated skills.
- FR21: End User can run `bmad upgrade --dry-run` to preview the impact of a version bump — changed fragments, affected compiled skills, user overrides that diverge — without modifying files.
- FR22: End User can run `bmad upgrade` to apply a version bump after reviewing the dry-run output; the command halts if any user override diverges from the new base and no reconciliation has been resolved.
- FR23: End User can run `bmad upgrade --reconcile` (Phase 1 capacity permitting) to launch a three-way merge workflow that resolves each divergence per passage. Reconciliation is reachable only via this flag; there is no standalone `reconcile` subcommand in v1.
- FR24: All install/upgrade subcommands accept `--directory`, `--modules`, `--tools`, `--override-root`, `--yes`, and `--debug` flags.

### Compile Primitives (CLI Mechanical Layer)

- FR25: Power User or CI can run `bmad compile <skill>` to recompile a single skill from its template source plus applied overrides, writing compiled `SKILL.md` to the install location.
- FR26: Power User or CI can run `bmad compile <skill> --diff` to emit a unified diff of the newly compiled output against the currently installed file without writing changes. Output format: unified diff (standard `diff -u` layout), ANSI-colorized when stdout is a TTY, plain when piped or redirected, so the same command composes with `less`, `cat`, log scrapers, and CI annotations.
- FR27: Power User, CI, or `bmad-customize` skill can run `bmad compile <skill> --explain` to produce an annotated provenance view; default format is Markdown with inline XML tags (`<Include>`, `<Variable>`).
- FR28: `--explain` accepts `--tree` to render only the fragment dependency tree without content.
- FR29: `--explain` accepts `--json` to emit a machine-readable structured representation of fragments and variables for editor tooling and for consumption by `bmad-customize` skill.
- FR30: `<Include>` tags emitted by `--explain` carry attributes for `src`, `resolved-from` (one of `base`, `variant`, `user-override`, `user-module-fragment`, `user-full-skill`), `hash`, and, when applicable, `base-hash`, `override-hash`, `override-path`, `variant`.
- FR31: `<Variable>` tags emitted by `--explain` carry attributes for `name`, `source` (one of `user-config`, `module-config`, `bmad-config`, `install-flag`, `env`, `derived`), `resolved-at`, and optionally `source-path`.
- FR32: Runtime placeholders (`{var_name}`) are emitted unchanged by `--explain` so the output previews what the model will actually receive.
- FR33: `bmad compile` performs no LLM reasoning; given identical inputs it produces identical outputs and is safe to run in CI and scripts.

### Customization Skill (Reasoning Layer)

- FR34: End User can invoke `bmad-customize` skill from an IDE chat (Claude Code or Cursor) with a natural-language customization intent (e.g., "make the PM agent's menu include a [Q] Question option").
- FR35: The `bmad-customize` skill discovers candidate override targets by calling `bmad compile --explain --json` on the affected skill(s) and reasoning over the returned fragment and variable structure.
- FR36: The `bmad-customize` skill identifies whether the user's intent maps to a fragment override, a variable override, or a full-skill replacement, and negotiates the chosen target with the user before writing any files.
- FR37: The `bmad-customize` skill drafts override content conversationally in the IDE chat session, starting from the active content for the target fragment / variable / full skill and incorporating the user's expressed intent. The draft is shown to the user as text inside the conversation. No file is written under the configured override root during drafting (see FR54).
- FR38: After the user accepts a draft and the skill writes the override file to its final path under the override root, the skill invokes `bmad compile <skill> --diff` to surface the compiled-`SKILL.md`-level impact as a final verification step. The during-draft preview shown to the user inside chat is rendered conversationally by the skill itself, not produced by a `bmad compile --diff` call.
- FR39: The `bmad-customize` skill is itself authored as `SKILL.template.md` + fragments and compiled by the same pipeline it helps users customize (dogfood reference).
- FR54 (**ratified from PRD §Open Questions #1**): No override content is written to any path under `<override_root>` during the drafting phase of a `bmad-customize` session. Drafts exist only as conversational text inside the chat session. The override root is modified strictly on explicit user acceptance, and only at the final override path (never to a staging subdirectory). This contract applies to all draft states: proposed, revised, and abandoned.

### Drift Detection & Lockfile

- FR40: Installer writes a `bmad.lock` file on every compile that records, per skill: source template path and hash, every resolved fragment with its `resolved_from` tier and hash, every compile-time variable with `source` / `source_path` / `value_hash`, the selected IDE variant, and the compiled output hash.
- FR41: `bmad upgrade --dry-run` reports per-fragment drift by comparing new base hashes against lockfile `base_hash` values and flags any fragment where a user override was applied and the upstream base has changed.
- FR42: `bmad.lock` records both the old and new base hashes for an overridden fragment after a successful reconcile, producing an audit trail of override lineage across versions.
- FR43: Lockfile stores only a `value_hash` for variable values (never plaintext), so configured secrets cannot leak via committed lockfiles.

### IDE Variant Support

- FR44: Installer can select a Claude Code variant for any fragment that provides one (via `*.claudecode.template.md` naming) and otherwise falls back to the universal variant.
- FR45: Installer can select a Cursor variant for any fragment that provides one (via `*.cursor.template.md` naming) and otherwise falls back to the universal variant.
- FR46: Installer records the selected variant for each skill in `bmad.lock`.

### Module Distribution

- FR47: Module Author can ship a module in Model 1 (precompiled Markdown only), Model 2 (template source only), or Model 3 (source plus precompiled fallback); the installer accepts all three without user-visible differences in the install command.
- FR48: Module Author can reference core fragments from module skill templates using an explicit namespace (e.g., `<<include path="core/persona-guard.template.md">>`) without copy-pasting core content.

### Validation & CI Integration

- FR49: CI can run `npm run validate:compile` to recompile all templated skills and compare against `bmad.lock`; any divergence fails the build.
- FR50: CI can run `npm run validate:skills` to assert every compiled skill passes schema validation after compilation.
- FR51: Installer exits non-zero with a user-facing error when any FR7 error condition occurs during a compile.
- FR52: CI runs an end-to-end integration test covering the full customization lifecycle: fresh `bmad install` → `bmad-customize` skill scaffolds a fragment override → `bmad compile --diff` accepted → `bmad upgrade --dry-run` shows drift after a simulated upstream fragment change → `bmad upgrade` halts → manual override edit resolves the drift → `bmad upgrade` succeeds → `bmad.lock` records the lineage (old base hash, new base hash, override hash). Pipeline failure of any step fails the build.
- FR53: CI matrix includes a Model 3 (template source + precompiled fallback) distribution test: install a module in a compiler-present environment and in a compiler-absent environment, assert both produce equivalent installed skill output.
- FR55 (**companion to FR54**): CI runs a test that exercises an abandoned `bmad-customize` session — fresh `bmad install` → `bmad-customize` skill opens a drafting session → the session is abandoned before acceptance → assert no new files exist under `<override_root>` and `bmad.lock` is byte-identical to its pre-session state. Pipeline failure fails the build.

## Non-Functional Requirements

### Performance

- **NFR-P1 · Install-time overhead.** `bmad install` on the BMAD reference install completes in ≤ 110 % of the current (pre-compiler) install time on the same machine. Measured on a cold install with all core skills migrated. Compiler has a hash-based skip path for unchanged skills so re-installs and CI runs amortize to ≤ 5 % overhead.
- **NFR-P2 · Per-skill recompile.** `bmad compile <skill>` completes in ≤ 500 ms wall-clock on a mid-2021 laptop for a skill with up to 10 fragments. `bmad compile <skill> --diff` adds ≤ 100 ms on top.
- **NFR-P3 · Dry-run responsiveness.** `bmad upgrade --dry-run` on a full install with ≤ 50 migrated skills completes in ≤ 3 seconds. Output is streamed so the first drift item appears within 500 ms.
- **NFR-P4 · `bmad-customize` interactive latency.** Each step of `bmad-customize` skill (discovery, draft, preview-diff) returns within the IDE's expected skill-turn budget; no discovery path requires more than two `bmad compile --explain --json` invocations per user turn.

### Security

- **NFR-S1 · No plaintext secrets in lockfile.** `bmad.lock` stores only `value_hash` (SHA-256) for compile-time variable values. No variable source path, environment-variable name, or raw value is recoverable from a committed lockfile.
- **NFR-S2 · Override root containment.** The compiler reads overrides only from the configured `override_root`. Paths that escape the override root (`..`, symlinks pointing outside) are rejected with a compile-time error.
- **NFR-S3 · Module boundary enforcement.** Third-party modules installed via `bmad install --modules <ids>` cannot register overrides of core fragments. Any module-declared fragment that would shadow a core fragment produces a namespace collision error at install time.
- **NFR-S4 · Trust gate for Level 3+.** Python-backed computed fragments (post-v1) require `compiler.trust_mode: full` in the module config. In v1, any attempt to register a Python render function is rejected at install time regardless of other flags.
- **NFR-S5 · No network access during compile.** The v1 compiler performs zero network I/O. All inputs are on local disk. This is both a security property (no exfil path) and a determinism property (no remote state).
- **NFR-S6 · Supply-chain hygiene.** `bmad-method` introduces no new runtime dependencies in v1. Any future dependency addition requires an explicit review note in the release PR.

### Reliability & Determinism

- **NFR-R1 · Byte-for-byte reproducibility.** Given identical source, overrides, configuration, and IDE target, repeated `bmad compile <skill>` runs produce byte-for-byte identical output across macOS, Linux, and Windows. Enforced by a CI job that compiles on all three platforms and diffs the outputs.
- **NFR-R2 · Deterministic resolution order.** Fragment resolution is stable across runs: precedence tier first (per FR10), then alphabetical by path within tier. Filesystem enumeration order does not affect output.
- **NFR-R3 · Line-ending normalization.** Compiled output uses LF line endings on all platforms. Template sources may contain CRLF; the compiler normalizes at read time.
- **NFR-R4 · Compile errors are terminal, not silent.** Any of the error conditions in FR7 produces a non-zero exit, a user-facing error message, and no partial write to the install location.
- **NFR-R5 · Lockfile integrity.** If `bmad.lock` is present but malformed, the CLI refuses to proceed and instructs the user to run `bmad install` fresh. It does not attempt silent recovery. **If user overrides are present on disk at the time of a malformed-lockfile recovery, the CLI prompts the user before any destructive action; it never silently deletes or overwrites user overrides even when lockfile state is unreadable.**

### Compatibility

- **NFR-C1 · Node.js runtime.** Runs on Node.js ≥ 20.0.0, matching the existing `bmad-method` engine constraint. No polyfills for older Node versions.
- **NFR-C2 · OS matrix.** Officially supported: macOS (Intel + Apple Silicon), Linux (x86_64 + ARM64), Windows 10/11. CI covers all six OS/arch combinations.
- **NFR-C3 · IDE matrix.** Officially supported for v1: Claude Code, Cursor. Universal-variant fallback works for any IDE that consumes `SKILL.md` (no Claude-Code- or Cursor-specific assumptions leak into the universal path).
- **NFR-C4 · Backward compatibility for unmigrated skills.** A skill directory with no `*.template.md` source installs exactly as it does today — byte-for-byte identical install output, identical file permissions, identical install time — guaranteed by a CI regression suite that compares install output against a pre-compiler baseline.
- **NFR-C5 · Forward compatibility for lockfile.** `bmad.lock` schema declares `version: 1`. A future compiler reading a v1 lockfile must either handle it or fail with a clear "upgrade your BMAD install" message. Never silently read a newer version as if it were v1.

### Observability

- **NFR-O1 · Lockfile as audit trail.** Every compile writes or updates `bmad.lock`. The lockfile is the single source of truth for "what was installed, why, and from where." A user answering "which fragments are in my install?" never needs to read source files — the lockfile alone suffices.
- **NFR-O2 · `--explain` provides full provenance.** For any compiled skill, `bmad compile <skill> --explain` renders every non-literal chunk with its origin. There are no silent interpolations or silent fragment merges.
- **NFR-O3 · Error messages name file and line.** Every compile-time error references the template file and, where applicable, the line number of the offending directive or variable. Generic "compile failed" messages are a regression.
- **NFR-O4 · Dry-run outputs are diffable and scriptable.** `bmad upgrade --dry-run` output is structured (plain-text default, `--json` alternate) so it can be fed into scripts, CI dashboards, or change-approval workflows.
- **NFR-O5 · `--debug` flag for contributor diagnostics.** All subcommands accept `--debug`, which emits the resolution trace (fragments considered, variants rejected, overrides applied) to stderr without changing stdout output.

### Maintainability

- **NFR-M1 · Syntax surface frozen for v1.** Four authoring constructs, as defined in Template Authoring. Adding a fifth construct requires a major-version bump of `bmad-method`. Enforced by a test that asserts any unknown directive produces a compile-time error.
- **NFR-M2 · Test coverage for resolution tiers.** The compile engine has unit tests covering every adjacent pair of resolution tiers (base↔variant, variant↔user-override, user-override↔user-module-fragment, user-module-fragment↔user-full-skill) and a matrix test exercising all five tiers in combination.
- **NFR-M3 · Documentation is a ship gate.** Author migration guide, `bmad-customize` skill walkthrough, `bmad.lock` schema reference, `--explain` tag vocabulary (plus formal schema appendix, see Appendix A), and a **5-minute quickstart** ("I installed BMAD, I want to customize one thing") aimed at day-one end users must all be present and reviewed in the release PR. Missing docs block the release.
- **NFR-M4 · Reference skills stay in sync.** The 3–5 migrated canonical skills are treated as contract tests for the compiler. CI recompiles each and diffs against a checked-in baseline so any compiler regression surfaces immediately.
- **NFR-M5 · Error-message vocabulary is stable.** Specific error types (`UNKNOWN_DIRECTIVE`, `UNRESOLVED_VARIABLE`, `MISSING_FRAGMENT`, `CYCLIC_INCLUDE`, `OVERRIDE_OUTSIDE_ROOT`, `LOCKFILE_VERSION_MISMATCH`) are part of the public contract and do not change names or semantics within v1.

**Explicitly not documented:** scalability (local tool, no server load), accessibility (no direct UI surface beyond IDE-provided chat), integration with external systems (no external APIs beyond IDE target platforms).

## Appendix A: `--explain` Tag Schema

Formal schema for the XML tags emitted by `bmad compile <skill> --explain` (default Markdown format). Intended for consumption by third-party editor tooling, future LSP integrations, and the `--json` renderer.

### `<Include>` — Fragment Inclusion Boundary

Emitted around every chunk of compiled output that originated from a fragment include (whether direct `<<include>>` or transitively resolved).

| Attribute | Required | Type / Enum | Meaning |
|---|---|---|---|
| `src` | yes | string (path) | Template path of the fragment as written in the `<<include>>` directive |
| `resolved-from` | yes | `base` \| `variant` \| `user-override` \| `user-module-fragment` \| `user-full-skill` | Which tier of the resolution order produced the content (per FR10) |
| `hash` | yes | string (SHA-256, lowercase hex) | Content hash of the fragment content that was inlined |
| `variant` | conditional | string | IDE variant selected (e.g., `cursor`, `claudecode`). Required iff `resolved-from=variant`; absent otherwise |
| `base-hash` | conditional | string (SHA-256) | Hash of the base-tier fragment that was overridden. Required iff `resolved-from` is `user-override`, `user-module-fragment`, or `user-full-skill`; absent otherwise |
| `override-hash` | conditional | string (SHA-256) | Hash of the override content that was selected. Required iff `resolved-from` is one of the user-* values; absent otherwise |
| `override-path` | conditional | string (path) | Filesystem path to the override file. Required iff `resolved-from` is one of the user-* values; absent otherwise |

### `<Variable>` — Compile-Time Interpolation

Emitted around every `{{var_name}}` interpolation in the compiled output.

| Attribute | Required | Type / Enum | Meaning |
|---|---|---|---|
| `name` | yes | string | Variable name (the text inside `{{...}}`) |
| `source` | yes | `install-flag` \| `user-config` \| `module-config` \| `bmad-config` \| `env` \| `derived` | Which precedence tier supplied the value (see source-value table above for precedence order; `env` is reserved, not emitted in v1) |
| `resolved-at` | yes | `compile-time` | Always `compile-time` in v1. (Reserved for future runtime-resolution variants; `{var_name}` runtime placeholders are never tagged.) |
| `source-path` | optional | string (path) | Filesystem path of the file that supplied the value. Present for `user-config`, `module-config`, `bmad-config` sources; absent for `install-flag`. For `derived` sources, a symbolic path of the form `derived://<name>` is emitted so consumers can disambiguate without leaking secrets or ambient state. |
| `declared-by` | optional | string (module ID) | Module whose `module.yaml` originally declared this variable (e.g., `core`, `bmm`, `<custom>`). Distinguishes declaration from value source — a value resolved from `module-config` may originate from a variable declared by `core` via the `# Variables from Core Config inserted:` inheritance convention. |
| `template-from` | optional | string (path) | `module.yaml` file whose `result:` template was applied during resolution (e.g., `core/module.yaml` for `output_folder`'s `{project-root}/{value}` template). Absent when no template expansion occurred. |

### JSON Rendering Equivalence (`--json`)

The `--json` renderer emits an ordered array mixing literal-text nodes, `<Include>` nodes, and `<Variable>` nodes, each tagged with its attributes from the tables above. Element order matches the order of appearance in compiled Markdown output. Literal text is represented as `{ "type": "text", "content": "..." }`.

Example schema fragment:

```json
{
  "type": "include",
  "src": "fragments/persona-guard.template.md",
  "resolved-from": "base",
  "hash": "a3f9b21c...",
  "children": [ /* nested nodes, same shape, in order */ ]
}
```

### Stability

Tag names, attribute names, and **required** enum values defined in this appendix are frozen for v1. The stability rules, in order of restrictiveness:

- **Breaking (major bump required):** renaming an attribute; removing an attribute; changing an attribute's type; removing a `<Tag>`; adding a new value to the `resolved-from` or `source` enums beyond what this appendix lists (per NFR-M5 error-vocabulary stability, applied analogously to provenance vocabulary). The `env` source value may be activated in a future minor release without a bump because it is already listed in v1 (merely `reserved — not emitted`), so emitting it does not widen the enum.
- **Additive (no bump required):** adding a new **optional** attribute to an existing tag; adding a new **optional** field to a lockfile entry; adding a new **optional** `<Tag>` to the vocabulary where the absence of the tag is always a valid interpretation. Consumers MUST tolerate unknown optional attributes and fields (ignore them gracefully; round-trip them unchanged if they rewrite).

Consumers may safely pin to the v1 schema for required attributes and the set of v1-listed enum values.

## Open Questions for Architecture

Issues raised during PRD review that required resolution at architecture or implementation time. Not blockers for PRD acceptance; each is answered below before the affected FR is built. **Both items are now RESOLVED** via the architecture document at `proposals/bmad-skill-compiler-architecture.md`; resolutions are summarized inline for PRD self-containment.

- **Staging semantics for override scaffolds (FR37 ↔ FR38) — RESOLVED (see architecture §Core Architectural Decisions → Decision 8).**
  The `bmad-customize` skill is a Markdown prompt executed by an LLM in IDE chat — not compiled code — so override drafts happen *conversationally* in chat context, not on disk. No file is written under `<override_root>` until the user explicitly accepts the proposed change. The engine does not need a `--with-override-stdin` flag and there is no staging directory.
  - **FR37 clarification:** "Scaffolds override file(s)" is reframed as a **chat-time draft** — the skill presents the active content and the proposed edit as text inside the conversation for the user to review. The committed override root is untouched during drafting.
  - **FR38 clarification:** `bmad compile --diff` is called **after** the user accepts and the file is written, to surface the compiled-`SKILL.md`-level impact as final verification. The during-draft "preview" the user sees is a conversational before/after rendered by the skill itself, not a compile invocation.
  - **Ratified new contract (see FR54 below):** No override file is written under `<override_root>` until the user accepts. The only authoritative location for an override is its final path; staging is strictly a runtime concept of the skill, never a filesystem artifact.
  - **Integration test FR52** already exercises the accept path; a companion case verifies that a rejected / abandoned drafting session leaves the committed override root untouched.

- **`bmad upgrade --rollback` — RESOLVED forward-compat (see architecture §Core Architectural Decisions → Decision 4).**
  Rollback remains out of v1 scope. The v1 lockfile schema is extended with `previous_base_hash` (prior upstream base for an overridden fragment) and `lineage` (append-only array of `{bmad_version, base_hash, override_hash}` entries per fragment) so a future `bmad upgrade --rollback` can reconstruct pre-upgrade state without requiring parallel lockfile snapshots or a separate delta chain. v1 writers populate these fields; v1 readers treat them as optional. Neither field changes the wire format of the existing v1 schema (both are additive optional fields; see Appendix A Stability section).
