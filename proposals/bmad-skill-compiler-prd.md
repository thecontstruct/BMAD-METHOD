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
amendedAt: '2026-04-20'
amendmentNotes: >-
  v1.1 — Course-corrected to absorb upstream's TOML customization system
  (PR #2284) and related changes (fs-native I/O, _bmad/custom/ provisioning,
  at-skill-entry Python renderer). Major changes: Python 3.11+ is the baseline
  runtime (NFR-S6 lifted), override root is `_bmad/custom/`, TOML values flow
  into the unified variable resolver as `self.*`, runtime renderer becomes a
  lazy-compile-on-entry cache-coherence guard (no runtime template rendering
  remains), `file:` glob expansions tracked as first-class compile inputs,
  `bmad-customize` skill triages TOML drift alongside prose drift.
inputDocuments:
  - proposals/bmad-skill-compiler-proposal.md
  - proposals/research-prompt-compilation-landscape.md
  - proposals/bmad-skill-compiler-architecture.md
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
    - no-invoke-time-content-assembly-in-v1
    - no-llm-in-the-compile-engine-in-v1
    - no-artifact-aware-collectors-in-v1
    - no-llm-assisted-compilation-in-v1
    - no-cross-module-shadowing-of-core-fragments
    - no-runtime-template-rendering-v1-uses-lazy-compile-on-entry-instead
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

BMAD Compiled Skills introduces a deterministic build pipeline beneath BMAD's authored Markdown skills. Skill sources (`*.template.md`) are assembled from shared fragments at install time, compile-time variables are resolved (including values from the TOML customization layer), IDE-specific variants are selected, user prose and variable overrides are layered on top, and `file:` globs are expanded against project content — producing plain Markdown at the edge that IDEs and models consume unchanged.

Today, shared prompt blocks are still duplicated across dozens of skills and any wording change still requires cross-file grep-and-edit. BMAD's recent TOML customization system (shipped upstream in v6.x) solves *structured* customization — menus, principles, activation steps, personas — via a 3-layer resolver at skill entry. What it does not solve is **prose deduplication across skills, compile-time variable interpolation into Markdown bodies, IDE-variant selection, and compile-level drift auditing**. This is the compiler's remaining territory. The v1 delivers a Python compile engine (`src/scripts/bmad_compile/`) that does all four, plus a lockfile (`bmad.lock`) that extends the customization system's provenance story to file-hash granularity, plus a `bmad-customize` skill that triages drift in natural language when upgrades change upstream defaults or prose fragments.

Primary users are BMAD core maintainers (who want to stop grep-and-editing duplicate prose), third-party module authors (who want to ship prose fragments alongside TOML defaults), and end users who want upgrade-safe customization of both structured (TOML) and prose (Markdown body) content. Target environments for the MVP are Claude Code and Cursor, with the existing "copy skill directory verbatim" install path preserved for any skill not yet migrated to template source.

The compiler runs at install/upgrade and at skill entry — at skill entry as a **lazy compile-on-entry** cache-coherence guard that hashes tracked inputs (fragments, configs, `customize.toml`, user TOML overrides, globbed files) against the lockfile and transparently recompiles if any drifted. No runtime template rendering remains: every value the LLM sees was resolved at compile time. The "edit and go" UX of editing a `*.user.toml` or a project-context file survives because the cache guard catches the drift and recompiles before the LLM reads.

The north-star outcome is zero loss of user customizations across a full upgrade cycle, with supporting metrics on fragment adoption across core skills and user override uptake.

### What Makes This Special

No existing tool, including the upstream TOML customization system, combines fragment composition, compile-time assembly covering structured AND prose layers, upgrade-safe user overrides (for both layers), multi-IDE variants, and drift visibility in one integrated system with per-skill provenance to the file-hash level. DSPy learns prompts but does not compose them; Microsoft Prompt Flow orchestrates but lacks user override semantics; Cursor rules append but have no override safety or drift detection; CrewAI concatenates role strings; upstream's own TOML customization covers structured fields only and has no drift detection or audit trail. Each covers a slice; none solve durable maintainer-and-user customization across upgrades for both structured and prose layers.

The core insight is that prompts are source code and need a build pipeline, not string concatenation. Anything that can be assembled deterministically should not be delegated to the model at runtime. The compiler exists to complete the existing BMAD customization story, not replace it — it takes the TOML resolver's output and weaves it together with prose fragments, variables, and variant selection into a single auditable artifact per skill.

The delight moment is upgrade time: the user runs `bmad upgrade`, their customizations survive cleanly across both planes, and when upstream changes intersect with user overrides the `bmad-customize` skill walks them through each change in natural language — whether it's a modified prose fragment (three-way merge UX) or a changed TOML default whose value they override (semantic-drift triage) — showing impact previews and planning a reconciliation path before the upgrade is applied. The system turns "will my edits survive?" from an open anxiety into an audited workflow spanning both layers.

## Project Classification

- **Project Type:** Developer tool (compile engine + CLI adapters + lockfile + fragment library) shipping as a Python library under `src/scripts/bmad_compile/` within the `bmad-method` npm package, invoked by the existing Node installer
- **Domain:** General / prompt-engineering infrastructure — no regulated-domain constraints
- **Complexity:** Medium — fragment resolution, variant selection, two-plane (TOML + prose) layering, hash-based lockfile, lazy-compile cache coherence, and `file:` glob tracking are real engineering; the MVP scope excludes the higher-complexity JIT / LLM-assisted / artifact-collector levels
- **Project Context:** Greenfield subsystem inside a brownfield codebase that already ships an upstream TOML customization system — compiler coexists with both the verbatim-copy install path and the TOML resolver, sharing a single Python library with the latter

## Success Criteria

### User Success

- **Maintainers:** A shared prompt-prose change requires editing one fragment file, not N skill files. Rebuild propagates the change; no cross-file grep required. Validation surfaces the affected compiled outputs before merge. TOML customization defaults remain the author's existing surface for structured fields; the compiler does not displace them.
- **Module authors:** A new module can ship `*.template.md` source alongside `customize.toml` defaults, reuse core fragments, reference TOML values from templates via `{{self.*}}`, and install cleanly alongside verbatim-copy modules. Authoring ergonomics match core authors — no extra tooling burden beyond knowing which plane (TOML for structured / template for prose) a change belongs on.
- **End users customizing skills:** Running `bmad-customize` reads the full customization surface of a target skill (structured TOML fields + prose fragments + compile-time variables), identifies which plane a natural-language request maps to, drafts the edit conversationally in chat without touching disk, writes to the correct file on the user's acceptance, and runs verification. Running `bmad upgrade` preserves every override that still applies — `customize.toml` default changes flow through the TOML merge automatically, prose changes flow through the compiler — and when any override intersects a changed upstream default or fragment, `bmad-customize` presents the per-change triage in natural language (three-way merge for prose; semantic-drift review for TOML) before the upgrade is treated as complete.

### Business Success

- **Adoption of shared fragments.** ≥ 50 % of core skills with identifiable duplicate prompt blocks migrated to `<<include>>` fragments within the first two minor releases post-launch.
- **User override uptake.** ≥ 25 % of active BMAD installs (measured via opt-in telemetry or self-report in the Discord community survey) have at least one user-authored override within 90 days of release.
- **Zero silent-loss upgrade cycle.** Across one complete release cycle (at least one minor version bump that touches shared fragments), the number of *silent* lost-customization incidents is zero. A surfaced conflict (reconcile-halt, drift-flag, merge-prompt) is not a loss. Measurement combines issue tracker / Discord reports with a post-upgrade opt-in prompt ("did all your overrides apply cleanly?") emitted by the installer so actual outcomes, not just reported ones, are counted.
- **Dogfood release gate.** Before release, `bmad-customize` skill (which is itself authored as template source per FR39) has survived at least one internal upgrade cycle with its own override reconciled. Own-cooking failure blocks release.
- **Module-author adoption.** At least two third-party modules ship template-source distribution (Model 2 or Model 3) within six months of release.

### Technical Success

- **Deterministic compilation.** Given identical source + overrides + config + TOML layer state + globbed file content, compilation is byte-for-byte reproducible. Hash of compiled output is stable across runs and platforms.
- **Install contract preserved.** Any skill not yet migrated to template source continues to install exactly as it does today (verbatim copy). The compiler is opt-in per skill; mixed installs are first-class.
- **Override resolution order enforced.** For prose fragments: user overrides always win over variant fragments, which always win over base fragments (full-skill replacement supported as escape hatch). For variables: `install-flag > user-config > module-config > bmad-config > derived` for YAML-sourced names, and user TOML layer > team TOML layer > defaults TOML layer for `self.*` TOML-sourced names. Resolution order is observable via `bmad compile --explain` and recorded in `bmad.lock`.
- **Lazy compile-on-entry coherence.** At skill entry, the installed SKILL.md is guaranteed to be up-to-date relative to every tracked input (fragments, configs, TOML layers, globbed files). If any input drifted since the last compile, the compile engine is transparently re-invoked for that skill before the LLM reads. No runtime template rendering remains.
- **Drift visibility.** Every compile produces a `bmad.lock` entry recording source templates, fragments resolved, variants selected, overrides applied (prose + TOML), globbed file match-sets and hashes, and compiled output hash. `bmad upgrade --dry-run` surfaces drift across all tracked inputs before the upgrade applies.
- **IDE variant support.** Claude Code and Cursor variants are selectable via file naming (`*.cursor.template.md`) with a working universal fallback. No runtime conditional logic in compiled output.
- **Validation coverage.** `npm run validate:skills` passes on every compiled skill; lockfile drift surfaces as a CI-visible failure, not a silent warning.
- **Shared library discipline.** TOML merge semantics, path normalization, hash computation, and variable precedence are implemented once in `src/scripts/bmad_compile/` and consumed by both the build-time compile entry point and the skill-entry cache-coherence guard (which absorbs/replaces the upstream at-skill-entry renderer's internals).

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

The v1 delivers: fragment extraction + `<<include>>` composition, template-source compile pipeline (Python), compile-time variable interpolation across YAML configs AND merged TOML customization (`self.*` namespace), prose/variable overrides under `_bmad/custom/`, IDE variant selection, `bmad.lock` with per-input hashes, `file:` glob tracking, lazy-compile-on-entry cache coherence that absorbs the upstream at-skill-entry renderer, and the `bmad-customize` skill covering structured TOML + prose + variable authoring and drift triage. Target environments are Claude Code and Cursor; the install command remains `npx bmad-method install ...` with the verbatim-copy path preserved for unmigrated skills. The upstream TOML customization system ships unchanged in behavior; its merge code is refactored into the shared library.

Full MVP feature set, phased roadmap, and risk-mitigation strategy are defined in [Project Scoping & Phased Development](#project-scoping--phased-development) below. That section is the binding scope definition; this summary exists only to orient readers arriving from the Executive Summary.

## User Journeys

### Journey 1 — Maya, Core Maintainer: Refactor a Shared Prompt Block

**Opening.** Maya maintains the BMAD core skills. A reviewer flags that the "activation rules" prose in `bmad-agent-pm` contradicts the same block in `bmad-agent-architect`. Maya audits: the block is copy-pasted across seven skills with three subtly different wordings. Refactoring means seven file edits and seven PR hunks she cannot easily diff.

**Rising action.** Maya runs `bmad compile bmad-agent-pm --explain --tree` and sees the skill is currently a monolithic `SKILL.md` with no fragments declared. She converts the shared block to `fragments/activation-rules.template.md`, updates seven `*.template.md` sources to reference it via `<<include>>`, and runs `npm run test:refs`. The validator reports every compiled skill that depends on the fragment.

**Climax.** Maya edits the one fragment file. `npm run validate:skills` recompiles all dependents and diffs the compiled output against `bmad.lock`. Seven compiled `SKILL.md` files change; all seven diffs show the single intended edit. CI is green.

**Resolution.** The PR touches one fragment plus seven one-line includes. Reviewers read the fragment once and trust the propagation. Maya's next cross-skill prose change is a one-file edit, not a grep-and-fix sweep.

**Requirements revealed.** Fragment extraction + `<<include>>` resolution; dependency tracking for validation and diff; lockfile-backed compiled-output diff; CI hook that fails on drift between lockfile and recompile.

### Journey 2 — Diego, End User: Customize Across Both Planes, Survive Upgrade

**Opening.** Diego runs a boutique consultancy and uses BMAD for client work. He wants two things: first, change the PM agent's `icon` and extend `principles` with a company-specific rule (structured-metadata change); second, rewrite the "menu handler" prose to be more verbose for his clients (prose change). He has burned customizations twice on prior BMAD versions by editing installed `SKILL.md` files directly.

**Rising action.** He invokes `bmad-customize` skill for `bmad-agent-pm` in his IDE chat and describes both changes in plain language. The skill reads the skill's full customization surface by calling `bmad compile bmad-agent-pm --explain --json` — which returns structured TOML fields (`agent.icon`, `agent.principles`, etc.), prose fragments in use, and compile-time variables — and recognizes that the icon/principles intent maps to the TOML plane and the menu-handler intent maps to the prose plane. It drafts both edits conversationally in chat: the TOML edit as content targeted at `_bmad/custom/bmad-agent-pm.user.toml`, the prose edit as content targeted at `_bmad/custom/fragments/bmm/bmad-agent-pm/menu-handler.template.md`. Diego reviews both drafts in the conversation, refines the menu-handler wording, and accepts. The skill writes both files. It then invokes `bmad compile bmad-agent-pm --diff` for post-write verification: the compiled `SKILL.md` now shows the new icon inlined (from the merged TOML resolution at compile), the appended principle, and the new menu-handler prose — all in one deterministic artifact.

**Climax.** A week later BMAD 6.4 ships. `bmad upgrade --dry-run` reports: "menu-handler.template.md unchanged upstream; your prose override still applies. customize.toml defaults unchanged for fields you override. 3 other fragments changed; your overrides are not affected." Diego runs `bmad upgrade`. Both customizations survive.

**Resolution.** Diego stops worrying about upgrade risk on either plane. Customization becomes something he does casually, not defensively.

**Requirements revealed.** Two-plane override roots (TOML + prose) under a single convention `_bmad/custom/`; `bmad-customize` discovers full surface via `bmad compile --explain --json` and routes intent to the right plane; chat-time draft, write-on-accept, post-write `--diff` verification; `bmad upgrade --dry-run` covers TOML defaults and prose fragments together; lockfile tracks both planes.

### Journey 3 — Diego (Edge Case): Upgrade With Drift, Guided Triage

**Opening.** Three months later, BMAD 6.5 ships and (a) substantially rewrites the menu-handler fragment Diego overrides, and (b) changes the default value of `agent.principles[2]` in `customize.toml` — a principle Diego also overrides in his user TOML.

**Rising action.** `bmad upgrade` halts with non-zero exit: "Drift detected. Invoke the `bmad-customize` skill in your IDE chat to review and resolve." Diego invokes the skill. It calls `bmad upgrade --dry-run --json` to get the full drift report and reasons about each drift entry in natural language.

- For the prose fragment: skill presents upstream-old / upstream-new / Diego's override side-by-side, explains which passages upstream changed, asks whether to keep, adopt upstream, or author a merged override. Diego chooses merge; skill drafts a merged override in chat, Diego refines, skill writes on accept.
- For the TOML field: skill explains that `agent.principles[2]` default changed from "..." to "..." upstream; Diego's override kept the old sentiment. Given the new default, does Diego want to keep his override, adopt the new default, or rewrite? Diego decides to adopt the new default; skill removes the `principles[2]` override from `bmad-agent-pm.user.toml` (leaving the other principles intact).

After all drift entries are resolved, the skill instructs Diego to re-run `bmad upgrade`. He does. Upgrade proceeds. Lockfile records the new state with full lineage (old base hashes, new base hashes, override decisions) for future audit.

**Climax.** No silent loss on either plane. No silent conflict at skill entry. Diego's overrides are each intentionally preserved, intentionally rewritten, or intentionally adopted-upstream, with a record of why.

**Resolution.** Cross-plane drift becomes a routine workflow step, not a crisis.

**Requirements revealed.** Upgrade drift detection per tracked input (prose fragments, TOML defaults, globbed files, variable sources); halt-on-drift that points users to the triage skill; `bmad upgrade --dry-run --json` as the machine-readable drift interface; three-way UX for prose drift; semantic-drift triage for TOML via the same `bmad-customize` skill; audit trail in `bmad.lock` for override lineage across versions and across planes.

### Journey 4 — Priya, Third-Party Module Author: Ship Template Source

**Opening.** Priya authors a domain-specific BMAD module (`bmad-module-legaltech`). She wants to reuse the same "persona-guard" prose fragment that core uses (without copy-pasting it into every agent skill in her module), and she wants to ship `customize.toml` defaults so her module's agents are TOML-customizable alongside core.

**Rising action.** Her module ships both: per-skill `*.template.md` sources with `<<include path="core/persona-guard.template.md">>` references to the core fragment, and per-skill `customize.toml` files declaring her module-specific structured defaults. Her module's `module.yaml` declares variable schema for her module-config. She ships Model 2 (template source + TOML defaults); she optionally publishes a Model 3 precompiled fallback for pre-compiler-era installers.

**Climax.** A user installs both core BMAD and her legaltech module. The compiler produces compiled `SKILL.md` files that share the core persona-guard content; the TOML resolver layers in her module's defaults alongside core's. The user overrides one of her TOML fields via `_bmad/custom/bmad-legaltech-contract-reviewer.user.toml` and one prose fragment via `_bmad/custom/fragments/legaltech/.../clause-wording.template.md`; both apply on the next `bmad upgrade` or skill-entry lazy-compile. Priya's module respects both overrides because resolution runs through the same pipeline and library as core.

**Resolution.** Priya's module has the same two-plane customization surface as core. Users customize once; it applies everywhere. Module authors do not reimplement either plane.

**Requirements revealed.** Cross-module fragment reference with explicit core-fragment namespace; per-skill `customize.toml` as the structured-default surface for module authors; distribution-model declaration (precompiled / template source / both); installer support for Model 3 fallback; module boundary enforcement on both planes (core cannot be silently overridden by a module install; a module-declared TOML field cannot shadow a core-declared one at install time).

### Journey Requirements Summary

Capabilities revealed across journeys:

| Capability | Journeys |
|---|---|
| Fragment authoring + `<<include>>` resolution | 1, 2, 4 |
| `*.template.md` → `SKILL.md` compile pipeline (Python) | 1, 2, 4 |
| Dependency tracking for validation and recompile | 1 |
| Shared override root `_bmad/custom/` covering TOML (user/team layers) and prose (fragment overrides) | 2, 3 |
| TOML value access from templates via `{{self.*}}` namespace | 2, 4 |
| `bmad-customize`: full surface discovery + intent routing to correct plane + chat-time draft + write-on-accept + post-write `--diff` verification | 2, 3 |
| `bmad upgrade --dry-run --json` covering prose, TOML, and glob-input drift | 2, 3 |
| Halt-on-drift with pointer to `bmad-customize` skill | 3 |
| Three-way reconciliation UX for prose drift; semantic-drift triage for TOML drift | 3 |
| `bmad.lock` recording prose resolutions, TOML layers, glob inputs, variable provenance, output hashes, lineage | 1, 2, 3 |
| Lazy compile-on-entry cache coherence (no runtime template rendering) | all (implicit) |
| CI hooks: drift failure, lockfile integrity | 1 |
| Cross-module fragment reference + module boundary enforcement on both planes | 4 |
| Per-skill `customize.toml` for structured defaults + module-author distribution | 4 |
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
- **Explicit anti-goals prevent scope creep.** Invoke-time *content assembly* (Level 4 — subagent prompt composition, JIT fragment selection based on conversation state), artifact-aware collectors, and LLM-assisted compilation (Level 6) are documented as out-of-scope for v1. Review gate: any proposed v1 feature that introduces one of these patterns is rejected. Lazy compile-on-entry for cache coherence is NOT Level 4; it re-runs the same deterministic compile with no invoke-time reasoning.
- **Trust model defined for future advanced layers.** When non-stdlib Python extensions or computed fragments with custom render functions are introduced, they gate behind `compiler: { trust_mode: full }` in config. The gate is both a security boundary and a statement of intent — advanced is advanced, not the default. v1's use of stdlib Python (tomllib, pathlib, hashlib, etc.) is in the safe/default `trust_mode`.
- **Syntax surface is frozen for v1.** Four constructs. No conditionals, no loops, no custom tags. This makes the compiler fully specifiable, the output fully auditable, and bug classes small. Any syntax proposal is a post-v1 conversation.
- **Drift surfaces at upgrade time and is triaged, not at skill-invocation time.** `bmad upgrade` halts with a clear pointer to `bmad-customize` for triage if any tracked input drifted relative to user overrides. A broken prompt at runtime is a user-trust incident; a flagged drift at upgrade time is a supported workflow step. The lockfile + skill-led triage make this difference possible.

## Developer Tool Specific Requirements

### Project-Type Overview

BMAD Compiled Skills ships as a subsystem of the `bmad-method` npm package (currently v6.3.0). It adds a Python compile pipeline to the existing Node installer without changing the install command or breaking the verbatim-copy path for unmigrated skills. The public surface is four artifacts: a template syntax for skill authors, a CLI command set for users, a config block for installs, and a lockfile for audits. Internally the compile engine is a Python library (`src/scripts/bmad_compile/`) that is also consumed by the skill-entry lazy-compile guard and by the existing TOML customization resolver (both refactored to import from it).

### Technical Architecture Considerations

- **Runtime.** Node.js ≥ 20 for the installer and CLI adapters (matches existing `bmad-method` engine requirement). **Python ≥ 3.11** for the compile engine and shared library — already required by upstream's TOML customization system (stdlib `tomllib` for TOML, stdlib `pathlib` for determinism, stdlib `hashlib` for content hashing). Users who install BMAD already have Python ≥ 3.11 as a prerequisite.
- **Dependencies.** No new runtime dependencies introduced by this v1. Node side reuses `commander`, `fs-native.js` wrapper over `node:fs/promises` (replaced `fs-extra` upstream in `a6d075bd`), `glob`, `js-yaml`, `xml2js`, `semver`, `@clack/prompts`, `chalk`, `picocolors`. Python side uses only the standard library: `tomllib`, `pathlib`, `hashlib`, `glob`, `json`, `re`, `sys`, `argparse`. Appendix A / lockfile are YAML on the Node side (parsing via `js-yaml`) and YAML on the Python side (via a hand-rolled minimal emitter — determinism-controlled subset, no new deps).
- **Packaging.** Python compile library lives at `src/scripts/bmad_compile/`. Build-time entry point is `src/scripts/compile.py`. Node CLI adapters live at `tools/installer/commands/{install,upgrade,compile}.js` and shell out to the Python entry point. `src/scripts/resolve_customization.py` (the existing TOML resolver) is refactored to import from `bmad_compile.toml_merge`. The upstream at-skill-entry Python runner is refactored to import from `bmad_compile.lazy_compile` (see below). No separate npm or pip package in v1; everything ships inside the `bmad-method` repo.
- **Two-layer design.** Mechanical operations (install, upgrade, drift detection, per-skill recompile, provenance rendering, lockfile emission) live in the CLI adapters + Python library and are fully deterministic. Intent-to-change reasoning (interpret a user's customization request, pick the right override target across TOML/prose/var planes, draft the edit, triage drift) lives in the `bmad-customize` skill, which consumes the CLI's `--explain --json` and `--diff` and `upgrade --dry-run --json` outputs. Safety-critical paths deterministic; LLM reasoning only where human intent is fuzzy.
- **Single-engine plumbing, shared library porcelain.** Node CLI adapters route to a single Python entry point (`compile.py`). The skill-entry lazy-compile guard (`lazy_compile.py`, absorbing what `bf30b697`'s renderer did) consumes the same shared library. The TOML customization resolver (formerly standalone `resolve_customization.py`) consumes the same shared library. One source of truth for TOML merge, variable precedence, path normalization, hash computation, error taxonomy.
- **Execution model.** Compile runs at install time, at explicit `bmad compile <skill>` time, at `bmad upgrade` time, and **lazily at skill entry** as a cache-coherence guard — if any tracked input has drifted relative to the lockfile, the compile is transparently re-invoked for that skill before the LLM reads. There is no runtime template rendering; the lazy-compile guard either serves the on-disk `SKILL.md` unchanged (fast path) or re-runs the same deterministic build-time compile (slow path, bounded by NFR-P2).
- **Output contract.** Compiled output is plain Markdown (`SKILL.md` or workflow-step `.md`). IDEs and models see no compiler artifacts — the `SKILL.md` on disk is the final, fully-resolved artifact. The `--explain` output is diagnostic only and is never installed.

### Language & Environment Support

| Axis | v1 Support | Notes |
|---|---|---|
| Node.js runtime | ≥ 20.0.0 | Installer + CLI adapters (existing) |
| Python runtime | ≥ 3.11.0 | Compile engine, lazy-compile guard, TOML resolver (all share `bmad_compile/` library). Already required by upstream v6.x. Stdlib only. |
| IDE — Claude Code | Full (universal fragments + `.claudecode.template.md` variants if needed) | Primary target |
| IDE — Cursor | Full (`.cursor.template.md` variants) | Co-primary target |
| IDE — others (VS Code, JetBrains, Gemini CLI) | Deferred | Growth scope; add as demand proven |
| OS | macOS, Linux, Windows (same matrix as `bmad-method` today) | No OS-specific compiler behavior; Python stdlib provides cross-OS primitives (`pathlib.PurePosixPath`, deterministic `hashlib.sha256` hex) |

### Installation Methods

- **Existing path unchanged.** `npx bmad-method install` continues to work. The installer detects whether a skill directory has `*.template.md` source and branches:
  - Template present → Node installer shells out to `python3 src/scripts/compile.py --skill ...`, which parses the template, resolves fragments + variables (YAML chain + TOML layers merged via shared library), selects the IDE variant, expands `file:` globs, writes `SKILL.md` + `bmad.lock` entry.
  - Template absent → copy skill directory verbatim (existing behavior).
- **Override root is `_bmad/custom/`.** Provisioned at install time (already done upstream in `8fb22b1a`). Subpaths:
  - `_bmad/custom/<skill>.toml` — TOML team layer (committed convention).
  - `_bmad/custom/<skill>.user.toml` — TOML user layer (gitignored).
  - `_bmad/custom/config.yaml`, `_bmad/custom/<module>/config.yaml`, `_bmad/custom/<module>/<workflow-path>/config.yaml` — YAML variable user-config layers.
  - `_bmad/custom/fragments/<module>/<skill>/<name>.template.md` — prose fragment overrides (new).
  - `_bmad/custom/.gitignore` (upstream-seeded) keeps `*.user.toml` + `fragments/**/*.user.*` out of commits.
- **Smart `install` default.** On an existing install, `bmad install` detects prior state (via `bmad.lock`) and auto-routes to `bmad upgrade --dry-run` followed by an interactive confirmation, rather than silently reinstalling over user overrides.
- **Non-interactive install** (`--yes`) remains supported. Compiler defaults: no overrides applied, universal variant, config-default vars.
- **Explicit subcommands.** `bmad upgrade` and `bmad compile` exist as dedicated subcommands for discoverability. `upgrade` can also be reached indirectly by running `bmad install` on an existing install. All subcommands share `--directory`, `--modules`, `--tools`, `--override-root`, and `--yes`.
- **Customization is a skill, not a subcommand.** `bmad-customize` ships as a first-class BMAD skill (one of the MVP-migrated reference skills). Users invoke it from their IDE chat with natural-language intent; the skill calls `bmad compile --explain --json` for discovery, `bmad compile --diff` for verification, and `bmad upgrade --dry-run --json` for drift triage. All three inputs come from the same deterministic compile engine.
- **Lazy compile on skill entry.** The SKILL.md shim installed by upstream (`b0d70766`) invokes `python3 -m bmad_compile.lazy_compile <skill>` at skill entry. The guard hashes tracked inputs, compares against lockfile, and either emits the on-disk SKILL.md unchanged or invokes the same compile path as `bmad compile <skill>` before emitting. Outcome is identical to a build-time compile; only the trigger differs.

### Public API Surface

**Template syntax (authoring API, frozen for v1):**

| Construct | Purpose | Example |
|---|---|---|
| Markdown passthrough | Plain content | Any non-construct text |
| `<<include path="..." [local-props]>>` | Inline another template or fragment | `<<include path="fragments/persona.template.md" help-skill="bmad-help">>` |
| `{{var_name}}` | Compile-time variable resolved against YAML config chain | `{{agent_display_name}}`, `{{user_name}}`, `{{output_folder}}` |
| `{{self.<toml.path>}}` | Compile-time variable resolved against the merged TOML layer stack for this skill (defaults → team → user) | `{{self.agent.icon}}`, `{{self.agent.role}}`, `{{self.agent.persistent_facts}}` |
| `{var_name}` | LLM-resolved placeholder, emitted verbatim by the compiler and never rewritten by any tooling thereafter | `{user_context}`, `{conversation_state}` |

**Note on `{var_name}` semantics.** `{var_name}` is a contract with the model — the compiler writes it unchanged, the lazy-compile guard does not substitute it, and the LLM sees the literal. This is different from upstream's prior "runtime renderer substitutes `{var}` from config" behavior; any existing `{var}` usages that depended on Python substitution migrate to `{{var}}` (compile-time) in the same PR that lands the compiler.

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
| `bmad-customize` | Interpret a user's natural-language customization intent, discover the full customization surface of the target skill (TOML structured fields + prose fragments + compile-time variables), route the intent to the correct plane (TOML user layer / prose fragment override / YAML variable override / full-skill replacement), draft the edit conversationally in chat, write to disk on user acceptance, and run `bmad compile --diff` for post-write verification. When invoked after a drift-halted `bmad upgrade`, consumes `bmad upgrade --dry-run --json` to triage each drift entry: three-way merge UX for prose fragments, semantic-drift review for TOML fields, orphan notification for removed upstream fields, new-default awareness for added upstream fields. Built on `bmad compile --explain --json`, `bmad compile --diff`, and `bmad upgrade --dry-run --json` — never imports the engine directly. Itself authored as `SKILL.template.md` + fragments + `customize.toml`; compiled by the same pipeline it helps users customize. |

**`--explain` Output (provenance view).**

Goal: render the final compiled Markdown with inline XML tags that attribute every non-literal chunk to its source. Output is diagnostic — stdout by default, never installed.

Tag vocabulary (v1):

| Tag | Purpose | Required Attributes | Optional Attributes |
|---|---|---|---|
| `<Include>` | Fragment inclusion boundary | `src`, `resolved-from` (`base` / `variant` / `user-override` / `user-module-fragment` / `user-full-skill`), `hash` | `base-hash`, `override-hash`, `override-path` (when `resolved-from` is an override), `variant` (when `resolved-from=variant`), `lineage` (JSON-encoded array of prior {version, base-hash, override-hash} entries) |
| `<Variable>` | `{{var}}` or `{{self.*}}` interpolation | `name`, `source`, `resolved-at` (always `compile-time` for v1) | `source-path`, `toml-layer` (required when `source=toml`; one of `defaults`/`team`/`user`/`merged`), `contributing-paths` (used when `toml-layer=merged`, JSON-encoded list of contributing file paths), `declared-by` (module ID that originally declared the variable), `template-from` (`module.yaml` whose `result:` template was applied), `base-source-path` (the defaults file when the value came from an override layer) |
| `<TomlGlobExpansion>` | Boundary around content inlined from a `file:`-prefixed TOML array entry expanded via filesystem glob | `pattern` (the literal glob pattern, with `{project-root}`-style vars substituted), `source` (`toml`), `toml-layer`, `source-path` (the TOML file that contained the pattern), `toml-field` (dotted path into the merged TOML, e.g. `agent.persistent_facts`), `match-count` | — |
| `<TomlGlobMatch>` | Inner tag for each filesystem match inside a `<TomlGlobExpansion>` | `path` (POSIX-normalized absolute or project-relative), `hash` (SHA-256 lowercase hex of content) | — |

`<Variable source="…">` enumerates where the value came from. Permitted values in v1:

| `source` value | Meaning | Namespace |
|---|---|---|
| `install-flag` | Value was set via a CLI flag at the current `bmad install` / `bmad upgrade` / `bmad compile` / `bmad-customize`-triggered invocation (e.g., `--user-name`). **Highest precedence within its namespace.** | any |
| `user-config` | YAML config file under the override root (`_bmad/custom/[<module>/[<workflow-path>/]]config.yaml`). Most-specific path wins within the tier. | non-`self.` |
| `module-config` | The active module's `config.yaml` (e.g., `_bmad/bmm/config.yaml`), from keys above the `# Core Configuration Values` marker. Also used in v1 for workflow-scoped `<module>/<workflow-path>/config.yaml` values (disambiguated via `source-path`); a dedicated `workflow-config` enum value is reserved for a future major version. | non-`self.` |
| `bmad-config` | BMAD core config (`_bmad/core/config.yaml`), or keys below the `# Core Configuration Values` marker inside a module's `config.yaml`. | non-`self.` |
| `toml` | Value came from the merged TOML layer stack for the current skill (`customize.toml` defaults + `_bmad/custom/<skill>.toml` team + `_bmad/custom/<skill>.user.toml` user). The `toml-layer` attribute indicates which layer supplied the value. | `self.*` |
| `env` | **Reserved — not emitted in v1.** v1 compiler never reads `process.env`. | — |
| `derived` | Computed at compile time from an enumerated allowlist: `install_root`, `project_root`, `module_root`, `bmad_version`, `module_version`, `current_module`, `current_skill`, `current_variant`, `installed_modules`. No timestamps, no ambient state. | any |

**Two parallel precedence cascades (v1):**

- **`self.*` cascade (TOML-sourced):** `install-flag` > `toml/user` > `toml/team` > `toml/defaults` → error.
- **Non-`self.` cascade (YAML-sourced):** `install-flag` > `user-config` > `module-config` > `bmad-config` > `derived` → error.

The two namespaces are lexically distinct (`self.` prefix vs. not) so names never collide across cascades. A variable's `source` reflects the first tier in which the name appears during its namespace's precedence walk.

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
  override_root: _bmad/custom   # where user overrides live; provisioned by installer, gitignored patterns seeded
  trust_mode: safe           # "safe" = v1 stdlib-only Python (default); "full" reserved for computed fragments / non-stdlib extensions post-v1
```

**Lockfile (`bmad.lock`, schema v1):**

```yaml
version: 1
compiled_at: <release-pinned sentinel, NOT wall-clock>   # deterministic per release; see Reliability NFR-R1
bmad_version: 6.3.0
entries:
  - skill: bmad-agent-pm
    source: src/bmm-skills/2-plan-workflows/bmad-agent-pm/SKILL.template.md
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
        override_path: _bmad/custom/fragments/bmm/bmad-agent-pm/menu-handler.template.md
        lineage:                            # audit trail of override/base history across upgrades
          - bmad_version: 6.3.0
            base_hash: <sha256>
            override_hash: <sha256>
          - bmad_version: 6.4.0
            base_hash: <sha256>
            override_hash: <sha256>
    toml_customization:
      defaults_path: src/bmm-skills/2-plan-workflows/bmad-agent-pm/customize.toml
      defaults_hash: <sha256>               # hash of customize.toml as shipped
      team_override_path: _bmad/custom/bmad-agent-pm.toml
      team_override_hash: <sha256?>         # present iff file exists
      user_override_path: _bmad/custom/bmad-agent-pm.user.toml
      user_override_hash: <sha256?>         # present iff file exists
      overridden_paths:                     # dotted paths into the merged TOML where user/team supplied values
        - path: agent.menu_items[code=BP].prompt
          tier: user                        # or "team"
          base_value_hash: <sha256>         # hash of the default value at time of last compile
          override_value_hash: <sha256>
          lineage:
            - bmad_version: 6.3.0
              base_value_hash: <sha256>
    variables:
      - name: user_name
        source: user-config
        source_path: _bmad/custom/config.yaml
        declared_by: core                   # which module's module.yaml declared this variable
        template_from: core/module.yaml     # when a result-template was applied during resolution; omitted when none
        value_hash: <sha256>                # hash of resolved value, not plaintext (NFR-S1)
      - name: self.agent.icon
        source: toml
        toml_layer: defaults
        source_path: src/bmm-skills/2-plan-workflows/bmad-agent-pm/customize.toml
        declared_by: bmm
        value_hash: <sha256>
      - name: self.agent.persistent_facts   # array value produced by structural merge across layers
        source: toml
        toml_layer: merged
        contributing_paths:
          - src/bmm-skills/2-plan-workflows/bmad-agent-pm/customize.toml
          - _bmad/custom/bmad-agent-pm.user.toml
        declared_by: bmm
        value_hash: <sha256>
    glob_inputs:
      - pattern: "{project-root}/**/project-context.md"
        resolved_pattern: "/home/user/my-app/**/project-context.md"   # after derived-var substitution
        source: toml
        toml_layer: defaults
        source_path: src/bmm-skills/2-plan-workflows/bmad-agent-pm/customize.toml
        toml_field: agent.persistent_facts
        match_set:                                                     # deterministic alphabetical order
          - path: /home/user/my-app/docs/project-context.md
            hash: <sha256>
          - path: /home/user/my-app/services/api/project-context.md
            hash: <sha256>
        match_set_hash: <sha256 of sorted match_set>
    variant: claude-code                    # or cursor / universal
    compiled_hash: <sha256>                 # hash of emitted SKILL.md
```

**Lockfile schema v1 field notes:**

- `compiled_at` is pinned to a release sentinel (e.g., the BMAD version tag), not wall-clock time, to satisfy NFR-R1 byte-for-byte reproducibility. Implementations that write wall-clock timestamps are non-conformant.
- `toml_customization` records the defaults + team + user TOML file hashes plus structured-path-level overrides for drift detection at field granularity. `overridden_paths[].tier` is one of `team`/`user`; base_value_hash is the default at time of compile; override_value_hash is the user/team-supplied value.
- `glob_inputs` records every `file:` glob expansion the compiler performed. `match_set_hash` is the fast-comparator for the lazy-compile guard at skill entry (hash the sorted list of path+hash pairs).
- `previous_base_hash` and `lineage` are forward-compat fields for a future `bmad upgrade --rollback` (out of v1 scope). v1 writers populate them; v1 readers ignore beyond current compile.
- `declared_by` names the module whose `module.yaml` originally declared the variable (not necessarily the module whose `config.yaml` supplied the value; that is `source` + `source_path`).
- `template_from` names the `module.yaml` path whose `result:` template was applied to produce the resolved value (e.g., `output_folder` has `result: "{project-root}/{value}"` in `core/module.yaml`). Absent when no template was applied.
- For `source: toml` variables, `toml_layer` is required (`defaults`/`team`/`user`/`merged`); `contributing_paths` is required when `toml_layer=merged`; `source_path` is omitted when `toml_layer=merged`.
- Unknown fields MUST be round-tripped unchanged by mechanical rewriters to preserve compatibility with future lockfile additions.

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

- FR13: End User can create a **prose fragment override** by placing a file under the shared override root `_bmad/custom/fragments/<module>/<skill>/<name>.template.md`. Compiler applies it according to FR10's precedence order (`user-full-skill > user-module-fragment > user-override > variant > base`).
- FR13a: End User can create a **TOML structured override** for any field of a skill's `customize.toml` by placing a sparse `_bmad/custom/<skill>.user.toml` (personal, gitignored) or `_bmad/custom/<skill>.toml` (team, committable). Compiler merges defaults → team → user at compile time per the structural rules documented by upstream (scalars: override wins; tables: deep merge; arrays-of-tables with shared identifier key: merge-by-key; other arrays: append). Resolved value is accessible from templates as `{{self.<dotted.path>}}`.
- FR14: End User can override a full skill by placing a complete `SKILL.md` (or `*.template.md`) at the corresponding path under the override root. Full-skill replacement is an escape hatch; routine customization should use FR13 (prose) or FR13a (TOML) instead.
- FR15: End User can override a **YAML compile-time variable value** by setting it in a user configuration file under the override root (`_bmad/custom/config.yaml`, `_bmad/custom/<module>/config.yaml`, etc.) — the `user-config` tier of the non-`self.` precedence cascade.
- FR16: Compiler applies overrides according to the two parallel precedence cascades documented in §Public API Surface (one for `self.*` TOML-sourced names, one for non-`self.` YAML-sourced names) and records the resolution outcome in `bmad.lock` for every variable and every fragment.
- FR17: Module Author cannot silently override a core fragment or a core-declared TOML field at install time; only the End User can register overrides of core behavior. Namespace collisions are rejected at install time (NFR-S3).

### Installation & Upgrade

- FR18: End User can run `bmad install` to perform a fresh install or a re-install into a target directory.
- FR19: `bmad install` detects an existing install (via presence of `bmad.lock`) and auto-routes to `bmad upgrade --dry-run` followed by an interactive confirmation, rather than silently reinstalling.
- FR20: Installer preserves the verbatim-copy install path for any skill directory that has no `*.template.md` source, guaranteeing backward compatibility for unmigrated skills.
- FR21: End User can run `bmad upgrade --dry-run` to preview the impact of a version bump across every tracked input: prose fragments that changed upstream, `customize.toml` defaults that changed at fields the user overrides, TOML overrides on fields that were removed upstream (orphans), newly-added upstream TOML defaults, globbed-file match-set changes, and variable provenance changes. `--json` emits the same data as a structured report consumable by `bmad-customize`.
- FR22: End User can run `bmad upgrade` to apply a version bump after reviewing the dry-run output; the command halts with a non-zero exit if any drift is detected and `--yes` was not passed, pointing the user to `bmad-customize` for triage (FR57).
- FR23: Prose fragment drift is triaged via a three-way merge UX (upstream-old → upstream-new → user-override) that `bmad-customize` walks the user through (FR56). TOML semantic drift is triaged via a field-level review UX — same skill, same session, different per-entry presentation. There is no standalone `reconcile` subcommand in v1; `bmad-customize` is the supported triage path.
- FR24: All install/upgrade subcommands accept `--directory`, `--modules`, `--tools`, `--override-root`, `--yes`, and `--debug` flags.

### Compile Primitives (CLI Mechanical Layer)

- FR25: Power User or CI can run `bmad compile <skill>` to recompile a single skill from its template source plus applied overrides, writing compiled `SKILL.md` to the install location.
- FR26: Power User or CI can run `bmad compile <skill> --diff` to emit a unified diff of the newly compiled output against the currently installed file without writing changes. Output format: unified diff (standard `diff -u` layout), ANSI-colorized when stdout is a TTY, plain when piped or redirected, so the same command composes with `less`, `cat`, log scrapers, and CI annotations.
- FR27: Power User, CI, or `bmad-customize` skill can run `bmad compile <skill> --explain` to produce an annotated provenance view; default format is Markdown with inline XML tags (`<Include>`, `<Variable>`).
- FR28: `--explain` accepts `--tree` to render only the fragment dependency tree without content.
- FR29: `--explain` accepts `--json` to emit a machine-readable structured representation of fragments and variables for editor tooling and for consumption by `bmad-customize` skill.
- FR30: `<Include>` tags emitted by `--explain` carry attributes for `src`, `resolved-from` (one of `base`, `variant`, `user-override`, `user-module-fragment`, `user-full-skill`), `hash`, and, when applicable, `base-hash`, `override-hash`, `override-path`, `variant`.
- FR31: `<Variable>` tags emitted by `--explain` carry attributes for `name`, `source` (one of `install-flag`, `user-config`, `module-config`, `bmad-config`, `toml`, `env` [reserved-not-emitted-in-v1], `derived`), `resolved-at`, and optionally `source-path`, `toml-layer` (required when `source=toml`), `contributing-paths` (required when `toml-layer=merged`), `base-source-path`, `declared-by`, `template-from`. Additionally, `<TomlGlobExpansion>` tags wrap `file:`-prefixed TOML-array expansions, with nested `<TomlGlobMatch>` tags per matched file (see Appendix A).
- FR32: Runtime placeholders (`{var_name}`) are emitted unchanged by `--explain` so the output previews what the model will actually receive.
- FR33: `bmad compile` performs no LLM reasoning; given identical inputs it produces identical outputs and is safe to run in CI and scripts.

### Customization Skill (Reasoning Layer)

- FR34: End User can invoke `bmad-customize` skill from an IDE chat (Claude Code or Cursor) with a natural-language customization intent (e.g., "make the PM agent's menu include a [Q] Question option" or "add an org-wide compliance rule to every agent's principles").
- FR35: The `bmad-customize` skill discovers the full customization surface of the target skill(s) by calling `bmad compile --explain --json`, which returns: structured TOML fields with defaults + currently-resolved values + per-field provenance, prose fragments with their current resolved-from tier and active content, and compile-time variables (both `{{self.*}}` TOML-sourced and non-`self.` YAML-sourced) with their tier + source-path + declared-by provenance.
- FR36: The `bmad-customize` skill identifies which plane (TOML structured field / prose fragment / YAML variable / full-skill replacement escape hatch) the user's intent maps to, and negotiates the chosen target with the user before writing any files. If the intent is ambiguous (multiple plausible targets), the skill asks before proceeding.
- FR37: The `bmad-customize` skill drafts override content conversationally in the IDE chat session, starting from the active content (from the `--explain --json` output) and incorporating the user's expressed intent. The draft is shown to the user as text inside the conversation. No file is written under the configured override root during drafting (see FR54).
- FR38: After the user accepts a draft, the skill writes the override to the correct file (per FR36's plane routing) and invokes `bmad compile <skill> --diff` to surface the compiled-`SKILL.md`-level impact (which reflects the full merge across both planes) as a final verification step. The during-draft preview shown to the user inside chat is rendered conversationally by the skill itself, not produced by a `bmad compile --diff` call.
- FR39: The `bmad-customize` skill is itself authored as `SKILL.template.md` + fragments + `customize.toml` and compiled by the same pipeline it helps users customize (dogfood reference across both planes).
- FR54 (**ratified from PRD §Open Questions #1**): No override content is written to any path under `_bmad/custom/` during the drafting phase of a `bmad-customize` session. Drafts exist only as conversational text inside the chat session. The override root is modified strictly on explicit user acceptance, and only at the final override path (never to a staging subdirectory). This contract applies to all draft states: proposed, revised, and abandoned, and to all planes (TOML / prose / YAML / full-skill).

### Drift Detection & Lockfile

- FR40: Compiler writes `_bmad/_config/bmad.lock` on every compile (build-time invocation or lazy-compile-on-entry recompile) that records, per skill: source template path + hash, every resolved fragment with `resolved_from` tier + hashes + lineage, TOML customization block (`defaults_hash`, per-layer override file hashes if present, per-field `overridden_paths` entries with tier + base-value-hash + override-value-hash + lineage), every compile-time variable with `source` + `source_path?` + `toml_layer?` + `contributing_paths?` + `declared_by?` + `template_from?` + `value_hash`, every glob input with `pattern` + `resolved_pattern` + `source` + `source_path` + `toml_field` + `match_set[]` + `match_set_hash`, the selected IDE variant, and the compiled output hash.
- FR41: `bmad upgrade --dry-run` reports drift across every tracked input category:
  - **Prose fragment drift** — upstream base hash changed for a fragment the user overrides.
  - **TOML default-value drift** — upstream changed `customize.toml` default for a field the user overrides; per-field diff (old value, new value, user value).
  - **TOML orphan drift** — user overrides a field that no longer exists upstream (field removed in new version).
  - **TOML new-default awareness** — upstream added a new field with a default; reported informational, no action required.
  - **Glob-input drift** — the glob match-set changed (files added/removed matching pattern) or any match's content hash changed.
  - **Variable provenance drift** — a variable now resolves from a different tier than last compile (e.g., user added a user-config entry that shadows a module-config value).

  Output is human-readable by default; `--json` emits the structured report consumable by `bmad-customize` (FR56).
- FR42: `bmad.lock` maintains an append-only `lineage` array per overridden fragment and per TOML-overridden field, capturing `{bmad_version, base_hash, override_hash}` or `{bmad_version, base_value_hash, override_value_hash}` at each upgrade so a future `bmad upgrade --rollback` can reconstruct pre-upgrade state (forward-compat, v1 doesn't implement rollback).
- FR43: Lockfile stores only `value_hash` for variable values (never plaintext), and only hashes (not contents) for globbed files. Configured secrets cannot leak via committed lockfiles (NFR-S1).

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
- FR55 (**companion to FR54**): CI runs a test that exercises an abandoned `bmad-customize` session — fresh `bmad install` → `bmad-customize` skill opens a drafting session → the session is abandoned before acceptance → assert no new files exist under `_bmad/custom/` and `bmad.lock` is byte-identical to its pre-session state. Pipeline failure fails the build.
- FR56 (**drift triage**): When invoked with drift-triage intent (either explicitly by the user or automatically in response to a halted `bmad upgrade` per FR57), the `bmad-customize` skill consumes `bmad upgrade --dry-run --json` and walks the user through each drift entry in natural language. Per-entry triage UX:
  - **Prose fragment drift** — present upstream-old, upstream-new, and user-override side-by-side; offer keep / adopt-upstream / author-merged-override.
  - **TOML default-value drift** — present the field path, old-default, new-default, user's override value; offer keep / adopt-new-default / rewrite-override.
  - **TOML orphan** — notify that user's override no longer applies (field removed upstream); offer remove-override.
  - **TOML new-default awareness** — notify about the added field and its default; no action required by default.
  - **Glob-input drift** — show added/removed matches and any content changes; typically informational since globs auto-incorporate matches, unless the drift combines with a user override at the field level.

  Writes follow FR54 (no persist until acceptance). Post-acceptance, skill instructs user to re-run `bmad upgrade`.
- FR57 (**halt-on-drift**): `bmad upgrade` exits non-zero with a clear message pointing to `bmad-customize` when drift is detected across any tracked input AND `--yes` was not passed. Message format: `"Drift detected in N skills (M prose fragments, P TOML fields, Q glob inputs). Invoke the 'bmad-customize' skill in your IDE chat to review and resolve, then re-run 'bmad upgrade'. Use 'bmad upgrade --yes' to ignore drift and proceed (not recommended)."` The `--yes` override exists as an escape hatch for scripted CI / container-build contexts where the author has already reviewed drift.
- FR58 (**lazy compile-on-entry**): At skill entry, a cache-coherence guard (installed by the SKILL.md shim) hashes every tracked input (source template, all fragments, all config files, `customize.toml` + user/team TOML layers, every glob input's match-set and per-match content) against the corresponding `bmad.lock` entry for that skill. If any hash differs — or if a glob's match-set has changed, or if a tracked file no longer exists — the guard invokes the same compile engine as a build-time `bmad compile <skill>` to bring the installed SKILL.md up to date before the LLM reads. The guard performs no template rendering of its own; it is purely a conditional-recompile wrapper. If all hashes match, the on-disk SKILL.md is served unchanged (fast path).

## Non-Functional Requirements

### Performance

- **NFR-P1 · Install-time overhead.** `bmad install` on the BMAD reference install completes in ≤ 110 % of the current (pre-compiler) install time on the same machine. Measured on a cold install with all core skills migrated. Compiler has a hash-based skip path for unchanged skills so re-installs and CI runs amortize to ≤ 5 % overhead.
- **NFR-P2 · Per-skill recompile.** `bmad compile <skill>` completes in ≤ 500 ms wall-clock on a mid-2021 laptop for a skill with up to 10 fragments, 3 TOML layers, and ≤ 20 file-glob matches totalling ≤ 500 KB. `bmad compile <skill> --diff` adds ≤ 100 ms on top. Python process startup is included in the budget (a ~50ms floor on cold invocations).
- **NFR-P3 · Dry-run responsiveness.** `bmad upgrade --dry-run` on a full install with ≤ 50 migrated skills completes in ≤ 3 seconds. Output is streamed so the first drift item appears within 500 ms.
- **NFR-P4 · `bmad-customize` interactive latency.** Each step of `bmad-customize` skill (discovery, draft, preview-diff, drift triage) returns within the IDE's expected skill-turn budget; no discovery path requires more than two `bmad compile --explain --json` invocations per user turn. Drift-triage sessions invoke `bmad upgrade --dry-run --json` at most once per session (not per entry).
- **NFR-P5 · Lazy compile-on-entry budget.** At skill entry, the cache-coherence guard's fast path (all hashes match) completes in ≤ 50 ms wall-clock on a mid-2021 laptop for a skill with up to 20 tracked inputs (including glob matches). The slow path (recompile needed) completes within NFR-P2's ≤ 500 ms envelope. Guidance for authors: glob patterns should target narrow directories (avoid `{project-root}/**/*` shapes); CI linter warns on overly-broad patterns.

### Security

- **NFR-S1 · No plaintext secrets in lockfile.** `bmad.lock` stores only `value_hash` (SHA-256) for compile-time variable values, and only hashes (not contents) for globbed files. No variable source path, environment-variable name, or raw value is recoverable from a committed lockfile.
- **NFR-S2 · Override root and glob containment.** The compiler reads overrides only from the configured `override_root` (default `_bmad/custom/`). Paths that escape the override root (`..`, symlinks pointing outside) are rejected with a compile-time error. `file:` glob patterns must resolve inside `{project-root}`; globs that match files outside the project root are rejected at expansion time.
- **NFR-S3 · Module boundary enforcement.** Third-party modules installed via `bmad install --modules <ids>` cannot register overrides of core fragments or core-declared TOML fields. Any module-declared fragment, TOML field (under the same namespaced path), or variable name that would shadow a core declaration produces a namespace collision error at install time.
- **NFR-S4 · Trust gate for advanced layers.** Future non-stdlib Python extensions and computed fragments with custom render functions require `compiler.trust_mode: full` in the module config. v1's compile engine uses only Python standard library (`tomllib`, `pathlib`, `hashlib`, `glob`, `json`, `re`, `argparse`) and is in the default safe `trust_mode`. Any attempt to register a custom render function or load a third-party Python module is rejected at install time unless `trust_mode: full` is explicitly set.
- **NFR-S5 · No network access during compile.** The v1 compile engine performs zero network I/O. All inputs are on local disk. This is both a security property (no exfil path) and a determinism property (no remote state).
- **NFR-S6 · Supply-chain hygiene.** `bmad-method` introduces no new runtime dependencies in v1 beyond the Python 3.11+ stdlib (already required by upstream). The Node side retains its existing deps unchanged; `fs-extra` is not re-introduced (replaced by `fs-native.js` per upstream `a6d075bd`). Any future dependency addition requires an explicit review note in the release PR.

### Reliability & Determinism

- **NFR-R1 · Byte-for-byte reproducibility.** Given identical source, overrides (prose + TOML), configuration, IDE target, and globbed file contents, repeated `bmad compile <skill>` runs produce byte-for-byte identical output across macOS, Linux, and Windows — whether invoked at build time or via lazy compile-on-entry. Enforced by a CI job that compiles on all three platforms and diffs the outputs. Python side uses `pathlib.PurePosixPath` for internal path normalization and `hashlib.sha256(...).hexdigest()` (stable lowercase hex) for all hashing.
- **NFR-R2 · Deterministic resolution order.** Fragment resolution is stable across runs: precedence tier first (per FR10), then alphabetical by POSIX path within tier. TOML merge is deterministic per the documented structural rules. Glob expansion sorts matches alphabetically by POSIX path. Filesystem enumeration order does not affect output.
- **NFR-R3 · Line-ending normalization.** Compiled output uses LF line endings on all platforms. Template sources, config files, TOML layers, and globbed files may contain CRLF; the compiler normalizes at read time.
- **NFR-R4 · Compile errors are terminal, not silent.** Any of the error conditions in FR7 (plus `OVERRIDE_OUTSIDE_ROOT`, `LOCKFILE_VERSION_MISMATCH`, and TOML-parse errors) produces a non-zero exit, a user-facing error message, and no partial write to the install location. The lazy-compile-on-entry guard propagates errors to the shim; the shim surfaces them to the LLM instead of serving a stale SKILL.md.
- **NFR-R5 · Lockfile integrity and lazy-compile coherence.** If `bmad.lock` is present but malformed, the CLI refuses to proceed and instructs the user to run `bmad install` fresh. It does not attempt silent recovery. **If user overrides are present on disk at the time of a malformed-lockfile recovery, the CLI prompts the user before any destructive action; it never silently deletes or overwrites user overrides even when lockfile state is unreadable.** The lazy-compile-on-entry guard acquires an advisory file-lock during recompile to prevent concurrent recompiles from racing on the same skill; loser waits on the winner's output.

### Compatibility

- **NFR-C1 · Node.js and Python runtimes.** Runs on Node.js ≥ 20.0.0 (installer, CLI adapters) and Python ≥ 3.11.0 (compile engine, lazy-compile guard, TOML resolver) — both already required by upstream. No polyfills for older versions. Users are informed at install time if either runtime is missing or outdated.
- **NFR-C2 · OS matrix.** Officially supported: macOS (Intel + Apple Silicon), Linux (x86_64 + ARM64), Windows 10/11. CI covers all six OS/arch combinations for both Node and Python paths.
- **NFR-C3 · IDE matrix.** Officially supported for v1: Claude Code, Cursor. Universal-variant fallback works for any IDE that consumes `SKILL.md` (no Claude-Code- or Cursor-specific assumptions leak into the universal path).
- **NFR-C4 · Backward compatibility for unmigrated skills.** A skill directory with no `*.template.md` source installs exactly as it does today — byte-for-byte identical install output, identical file permissions, identical install time — guaranteed by a CI regression suite that compares install output against a pre-compiler baseline. Skills that have `customize.toml` but no `*.template.md` continue to use upstream's unmodified TOML customization path; only skills that opt in to template source exercise the compiler.
- **NFR-C5 · Forward compatibility for lockfile.** `bmad.lock` schema declares `version: 1`. A future compiler reading a v1 lockfile must either handle it or fail with a clear "upgrade your BMAD install" message. Never silently read a newer version as if it were v1. Unknown additive fields in a v1 lockfile (per §Appendix A Stability) MUST be round-tripped unchanged.

### Observability

- **NFR-O1 · Lockfile as audit trail.** Every compile writes or updates `bmad.lock`. The lockfile is the single source of truth for "what was installed, why, and from where." A user answering "which fragments are in my install?" never needs to read source files — the lockfile alone suffices.
- **NFR-O2 · `--explain` provides full provenance.** For any compiled skill, `bmad compile <skill> --explain` renders every non-literal chunk with its origin. There are no silent interpolations or silent fragment merges.
- **NFR-O3 · Error messages name file and line.** Every compile-time error references the template file and, where applicable, the line number of the offending directive or variable. Generic "compile failed" messages are a regression.
- **NFR-O4 · Dry-run outputs are diffable and scriptable.** `bmad upgrade --dry-run` output is structured (plain-text default, `--json` alternate) so it can be fed into scripts, CI dashboards, or change-approval workflows.
- **NFR-O5 · `--debug` flag for contributor diagnostics.** All subcommands accept `--debug`, which emits the resolution trace (fragments considered, variants rejected, overrides applied) to stderr without changing stdout output.

### Maintainability

- **NFR-M1 · Syntax surface frozen for v1.** Four authoring constructs, as defined in Template Authoring. Adding a fifth construct requires a major-version bump of `bmad-method`. Enforced by a test that asserts any unknown directive produces a compile-time error.
- **NFR-M2 · Test coverage for resolution tiers.** The compile engine has unit tests covering every adjacent pair of fragment resolution tiers (base↔variant, variant↔user-override, user-override↔user-module-fragment, user-module-fragment↔user-full-skill), every adjacent pair of variable resolution tiers in both namespaces (`self.*` cascade: `install-flag↔toml/user`, `toml/user↔toml/team`, `toml/team↔toml/defaults`; non-`self.` cascade: `install-flag↔user-config`, `user-config↔module-config`, `module-config↔bmad-config`, `bmad-config↔derived`), and a matrix test exercising all tiers in combination. TOML merge semantics have their own test matrix against upstream's documented structural rules. Glob-input drift detection has contract tests for add/remove/modify cases.
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

Emitted around every `{{var_name}}` or `{{self.<toml.path>}}` interpolation in the compiled output.

| Attribute | Required | Type / Enum | Meaning |
|---|---|---|---|
| `name` | yes | string | Variable name (the text inside `{{...}}`). For TOML-sourced values, a dotted path rooted at `self.` (e.g., `self.agent.icon`). |
| `source` | yes | `install-flag` \| `user-config` \| `module-config` \| `bmad-config` \| `toml` \| `env` \| `derived` | Which precedence tier supplied the value (see source-value table in the main doc for per-namespace precedence order). `env` is reserved, not emitted in v1. |
| `resolved-at` | yes | `compile-time` | Always `compile-time` in v1. (Reserved for future runtime-resolution variants; `{var_name}` LLM placeholders are never tagged.) |
| `source-path` | optional | string (path) | Filesystem path of the file that supplied the value. Present for `user-config`, `module-config`, `bmad-config`, `toml` (when `toml-layer` is not `merged`) sources; absent for `install-flag`. For `derived` sources, a symbolic path of the form `derived://<name>` is emitted so consumers can disambiguate without leaking secrets or ambient state. |
| `toml-layer` | conditional | `defaults` \| `team` \| `user` \| `merged` | Which TOML layer produced the value. Required iff `source=toml`; absent otherwise. `merged` indicates structural merge (array append or deep table merge) across multiple layers; in that case `source-path` is omitted and `contributing-paths` is used. |
| `contributing-paths` | conditional | JSON-encoded string array | Ordered list of TOML files that contributed to a `toml-layer=merged` value. Required iff `source=toml` and `toml-layer=merged`. |
| `base-source-path` | optional | string (path) | The defaults-layer file path when the value came from an override layer (`toml-layer` ∈ `{team, user}`). Useful for `bmad-customize` to compare user's value against defaults. |
| `declared-by` | optional | string (module ID) | Module whose `module.yaml` originally declared this variable (e.g., `core`, `bmm`, `<custom>`). For TOML-sourced `self.*` variables, the module of the `customize.toml` defaults file. |
| `template-from` | optional | string (path) | `module.yaml` file whose `result:` template was applied during resolution (e.g., `core/module.yaml` for `output_folder`'s `{project-root}/{value}` template). Absent when no template expansion occurred. |

### `<TomlGlobExpansion>` and `<TomlGlobMatch>` — File-Glob Expansion

Emitted around content inlined from a `file:`-prefixed entry in a merged TOML array (typically `agent.persistent_facts` or similar). The outer tag describes the glob itself; each inner `<TomlGlobMatch>` wraps the content of one matching file.

| Attribute (`<TomlGlobExpansion>`) | Required | Type / Enum | Meaning |
|---|---|---|---|
| `pattern` | yes | string | The glob pattern after `{project-root}`-style derived-var substitution (still a glob, not yet expanded to matches). |
| `source` | yes | `toml` | Always `toml` in v1. |
| `toml-layer` | yes | `defaults` \| `team` \| `user` | Which TOML layer's array entry produced the pattern. (`merged` is not used here — if multiple layers each contribute `file:` entries, they are emitted as multiple `<TomlGlobExpansion>` tags, one per contributing layer.) |
| `source-path` | yes | string (path) | The TOML file that contained the `file:` pattern entry. |
| `toml-field` | yes | string (dotted path) | Where in the merged TOML the array lives (e.g., `agent.persistent_facts`). |
| `match-count` | yes | integer | Number of filesystem matches (determines how many `<TomlGlobMatch>` children follow). |

| Attribute (`<TomlGlobMatch>`) | Required | Type / Enum | Meaning |
|---|---|---|---|
| `path` | yes | string (path) | POSIX-normalized path of the matched file. Typically expressed project-relative when the match is inside the project root. |
| `hash` | yes | string (SHA-256, lowercase hex) | Content hash of the matched file as inlined. |

### JSON Rendering Equivalence (`--json`)

The `--json` renderer emits an ordered array mixing literal-text nodes, `<Include>` nodes, `<Variable>` nodes, and `<TomlGlobExpansion>` nodes (each with nested `<TomlGlobMatch>` children), each tagged with its attributes from the tables above. Element order matches the order of appearance in compiled Markdown output. Literal text is represented as `{ "type": "text", "content": "..." }`. TOML glob expansions are represented as:

```json
{
  "type": "toml-glob-expansion",
  "pattern": "{project-root}/**/project-context.md",
  "source": "toml",
  "toml-layer": "defaults",
  "source-path": "src/bmm-skills/.../customize.toml",
  "toml-field": "agent.persistent_facts",
  "match-count": 2,
  "matches": [
    { "type": "toml-glob-match", "path": "/home/user/my-app/docs/project-context.md", "hash": "...", "content": "..." },
    { "type": "toml-glob-match", "path": "/home/user/my-app/services/api/project-context.md", "hash": "...", "content": "..." }
  ]
}
```

Example fragment node:

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

Tag names, attribute names, and enum values defined in this appendix are frozen for v1. The stability rules, in order of restrictiveness:

- **Breaking (major bump required) — after v1 ships:** renaming an attribute; removing an attribute; changing an attribute's type; removing a `<Tag>`; adding a new value to the `resolved-from` or `source` enums. The `env` source value may be activated in a future minor release without a bump because it is already listed in v1 (merely `reserved — not emitted`), so emitting it does not widen the enum.
- **Additive (no bump required) — even after v1 ships:** adding a new **optional** attribute to an existing tag; adding a new **optional** field to a lockfile entry; adding a new **optional** `<Tag>` to the vocabulary where the absence of the tag is always a valid interpretation. Consumers MUST tolerate unknown optional attributes and fields (ignore them gracefully; round-trip them unchanged if they rewrite).

Pre-ship note: until v1 is released to users, this schema may still change freely. The stability rules above govern post-release evolution. Consumers should not pin to pre-release drafts.

## Open Questions for Architecture

Issues raised during PRD review that required resolution at architecture or implementation time. Not blockers for PRD acceptance; each is answered below before the affected FR is built. **All items are now RESOLVED** via the architecture document at `proposals/bmad-skill-compiler-architecture.md`; resolutions are summarized inline for PRD self-containment.

- **Staging semantics for override scaffolds (FR37 ↔ FR38) — RESOLVED (see architecture §Core Architectural Decisions → Decision 8).**
  The `bmad-customize` skill is a Markdown prompt executed by an LLM in IDE chat — not compiled code — so override drafts happen *conversationally* in chat context, not on disk. No file is written under `<override_root>` until the user explicitly accepts the proposed change. The engine does not need a `--with-override-stdin` flag and there is no staging directory.
  - **FR37 clarification:** "Scaffolds override file(s)" is reframed as a **chat-time draft** — the skill presents the active content and the proposed edit as text inside the conversation for the user to review. The committed override root is untouched during drafting.
  - **FR38 clarification:** `bmad compile --diff` is called **after** the user accepts and the file is written, to surface the compiled-`SKILL.md`-level impact as final verification. The during-draft "preview" the user sees is a conversational before/after rendered by the skill itself, not a compile invocation.
  - **Ratified new contract (see FR54 below):** No override file is written under `<override_root>` until the user accepts. The only authoritative location for an override is its final path; staging is strictly a runtime concept of the skill, never a filesystem artifact.
  - **Integration test FR52** already exercises the accept path; a companion case verifies that a rejected / abandoned drafting session leaves the committed override root untouched.

- **`bmad upgrade --rollback` — RESOLVED forward-compat (see architecture §Core Architectural Decisions → Decision 4).**
  Rollback remains out of v1 scope. The v1 lockfile schema is extended with `previous_base_hash` (prior upstream base for an overridden fragment) and `lineage` (append-only array of `{bmad_version, base_hash, override_hash}` entries per fragment) so a future `bmad upgrade --rollback` can reconstruct pre-upgrade state without requiring parallel lockfile snapshots or a separate delta chain. v1 writers populate these fields; v1 readers treat them as optional. Neither field changes the wire format of the existing v1 schema (both are additive optional fields; see Appendix A Stability section).

- **TOML customization coexistence — RESOLVED (see architecture §Core Architectural Decisions → Decisions 3, 16, 17, 18).**
  Upstream's TOML customization system (`customize.toml` + `_bmad/custom/<skill>.{toml,user.toml}`) is absorbed into the compiler's unified surface rather than treated as a parallel plane:
  - TOML values are first-class variables in the compiler's resolver, accessible as `{{self.<toml.path>}}` in templates, resolved against the merged TOML layer stack (user → team → defaults) at compile time with full provenance recorded in the lockfile and `--explain`.
  - The TOML resolver (`src/scripts/resolve_customization.py`) and the at-skill-entry renderer (`bf30b697`) are refactored to import from a shared Python library (`src/scripts/bmad_compile/`) so merge semantics, path normalization, error vocabulary, and variable precedence are implemented once.
  - The at-skill-entry Python runner becomes a **lazy compile-on-entry** cache-coherence guard: it hashes tracked inputs against the lockfile and transparently re-invokes the compile engine if any drifted, replacing runtime template rendering with build-time rendering that is refreshed on demand.
  - `file:` glob expansions inside TOML arrays are tracked as first-class compile inputs in `bmad.lock` (pattern + match-set + per-match hashes); the lazy-compile guard re-evaluates globs as part of its staleness check so "edit a project-context file and the next skill entry reflects it" works via the same mechanism.
  - Drift detection extends to cover TOML semantic drift (user overrides a TOML field whose default changed), orphaned overrides, and new upstream defaults, alongside prose fragment drift. All drift is triaged by the `bmad-customize` skill consuming `bmad upgrade --dry-run --json`.
