# Proposal: Compiled Skills — A Prompt Composition Pipeline for BMAD

**Author:** Phil M
**Date:** 2026-04-10
**Status:** Draft — for review by BMAD maintainers
**Roadmap alignment:** Workflow Customization, Adaptive Skills, Centralized Skills

---

## 1. Problem

### 1.1 Maintainer pain

BMAD skills are hand-authored Markdown files. Shared prompt patterns are duplicated verbatim across many files rather than composed from a single source. A survey of the current `src/` tree shows:

| Repeated block                                                                              |      Occurrences      |
| ------------------------------------------------------------------------------------------- | :--------------------: |
| "On Activation → load config → resolve `{user_name}`, `{communication_language}`, …" |    9 SKILL.md files    |
| "You must fully embody this persona…"                                                      | 6 agent SKILL.md files |
| "STOP and WAIT for user input" menu guard                                                   | 6 agent SKILL.md files |
| "CRITICAL Handling: invoke the corresponding skill…"                                       | 6 agent SKILL.md files |
| "Remind the user they can invoke `bmad-help`…"                                           | 6 agent SKILL.md files |

Any change to shared wording (config path, behavioral guardrail, help reminder) requires editing every file manually. This is brittle, error-prone, and blocks confident refactoring.

### 1.2 User pain

Users who want to customize prompt behavior today have two bad options:

1. **Edit installed SKILL.md files directly** — changes are overwritten on the next `npx bmad install` or update.
2. **Fork the entire BMAD repo** — heavy, loses upstream updates, diverges quickly.

The existing `detectCustomFiles` / hash-based backup system preserves user-created files during updates, but there is no mechanism for users to **override specific prompt fragments** and have those overrides survive upgrades while still receiving upstream improvements to the rest of the skill.

### 1.3 Platform variance

The roadmap lists "Adaptive Skills" — skills optimized for different models and IDEs. Today there is no way to express conditional content (e.g. "include this guardrail only for Cursor" or "use this phrasing for Claude models"). Every variant would require a separate copy-pasted file.

---

## 2. Proposed solution: Compiled Skills

Replace the current **"copy skill directory verbatim"** install step with a **compile step** that assembles final Markdown from composable sources, user overrides, and a context object describing the target environment.

### 2.1 Authoring format: MDX

Skills would be authored in **MDX** (Markdown + JSX), compiled at install time (and optionally via `--watch` during development) into plain Markdown that IDEs and models consume.

**Why MDX:**

- Familiar syntax for anyone who writes Markdown.
- JSX components provide clean composition (`<OnActivation />`, `<PersonaGuard />`, `<MenuHandler />`).
- Conditional rendering via props (`{props.ide === "cursor" && <CursorSpecificBlock />}`).
- TypeScript support for component contracts.
- Established ecosystem (unified/remark/rehype).
- Aligns with the existing use of MDX in the BMAD docs site.

**What changes for authors:**

```
Before (current — hand-duplicated Markdown):
  src/bmm-skills/bmad-agent-pm/SKILL.md     ← full file, copy-pasted blocks
  src/bmm-skills/bmad-agent-architect/SKILL.md ← same blocks, different persona

After (proposed — composed MDX):
  src/fragments/on-activation-bmm.mdx        ← single source
  src/fragments/persona-guard.mdx             ← single source
  src/fragments/menu-handler.mdx              ← single source
  src/bmm-skills/bmad-agent-pm/SKILL.mdx     ← imports fragments, passes props
  src/bmm-skills/bmad-agent-architect/SKILL.mdx ← imports same fragments, different props
```

**Example SKILL.mdx (simplified, restricted-compatible):**

```mdx
---
name: bmad-agent-pm
description: Product manager for PRD creation and requirements discovery.
---

# John

## Overview

This skill provides a Product Manager who drives PRD creation through
user interviews, requirements discovery, and stakeholder alignment.

## Identity

Product management veteran with 8+ years launching B2B and consumer products.

<Include fragment="persona-guard" />

## On Activation

<Include fragment="on-activation-bmm" configPath="bmm" />

<Include fragment="menu-handler" helpSkill="bmad-help" />
```

No `import` statements — the compiler resolves `<Include>` references from the fragment library at compile time. This is safe to process for any content source (first-party, community, or user override).

**Compiled output** (what gets installed as `SKILL.md`): identical to today's hand-written files — plain Markdown, no JSX, no imports.

### 2.2 Context object

The compiler receives a context describing the target:

```typescript
interface CompileContext {
  ide: string;          // "cursor" | "claude-code" | "gemini" | ...
  model?: string;       // "opus" | "sonnet" | "gpt-4" | ...
  moduleConfig: Record<string, string>; // resolved config.yaml values
  overrideRoot?: string; // path to user override directory
}
```

Fragments can branch on context using the restricted component set:

```mdx
<If ide="cursor">
  <Include fragment="cursor-specific-guidance" />
</If>

<Switch on="model">
  <Case value="opus">Use detailed chain-of-thought reasoning.</Case>
  <Case value="sonnet">Be concise and action-oriented.</Case>
</Switch>
```

No raw JS expressions — conditionals use declarative components that the compiler evaluates safely.

### 2.3 User overrides

Users place override files in a designated directory that **shadows** the fragment tree:

```
Default location:    {project}/_bmad/_prompt-overrides/
Custom location:     --prompt-root <path>  or  BMAD_PROMPT_ROOT env var
```

**Resolution order** (last wins):

1. **BMAD canonical fragment** (shipped with the framework)
2. **User override fragment** (same filename in the override root)
3. **Full skill replacement** (user places a complete `SKILL.mdx` that replaces the entire skill body — escape hatch)

Override files are **excluded** from the installer's "modified file" detection — they are never treated as accidental edits to shipped content.

### 2.4 Compile step integration

The compile step slots into the existing installer between config resolution and IDE copy:

```
Current flow:
  resolve config → copy skill dirs verbatim → copy to IDE targets

Proposed flow:
  resolve config → compile MDX → emit SKILL.md into _bmad → copy to IDE targets
```

| Command                              | Behavior                                                                                  |
| ------------------------------------ | ----------------------------------------------------------------------------------------- |
| `npx bmad install`                 | Full compile + install (default). Prints drift report if overrides exist after an upgrade. |
| `npx bmad install --watch`         | Watch mode: recompile on fragment/override/config changes                                 |
| `npx bmad compile`                 | Compile only (no IDE copy) — useful for CI/testing                                       |
| `npx bmad compile --explain`       | Print which fragments and overrides produced each output                                  |
| `npx bmad compile --diff <target>` | Show upstream vs override diff for a specific fragment or file                            |

Every compile writes a **compile manifest** (`_bmad/_config/compile-manifest.yaml`) that records which files were overridden, their content hashes, and the upstream version they were compiled against. On the next compile after a BMAD upgrade or module update, the compiler compares hashes to detect **drift** — upstream content changes, orphaned overrides targeting removed files, and workflow step list changes. The drift report is printed to stdout and written to `_bmad/_config/compile-drift-report.md` for consumption by the `bmad-customize` skill. See Section 9 for the full drift detection design.

### 2.5 Validation

- `validate-skills.js` runs on **compiled output** (the contract with IDEs/models is unchanged).
- A new **fragment validator** checks MDX sources for: valid imports, no orphaned fragments, component prop types.
- CI runs `npm run compile && npm run validate:skills` to catch regressions.
- The compile manifest enables **drift validation** as a CI check: `npm run compile` exits non-zero if any override is orphaned (targeting a file that no longer exists upstream).
- **Token budget warnings**: The compiler knows the target model (from `CompileContext`). After emitting a compiled skill, it counts tokens and warns if the output exceeds the target model's context window budget (configurable threshold, e.g. 80% of max context). This catches bloated overrides or overly-inlined context before they cause silent truncation at runtime.

---

## 3. Trust model

### Why restricted-by-default is the only viable starting point

Community modules and the marketplace skill pack ecosystem already exist. Any content from those sources flows through the same install pipeline as first-party BMAD skills. This means `npx bmad install` can execute content authored by **unknown third parties**. If the compiler allows arbitrary JS in `.mdx` files, installing a community module becomes equivalent to running an untrusted `postinstall` script — except users have no expectation of that risk when they think they're installing "prompt files."

Bolting on restrictions after shipping a full-JS compiler would be a breaking change for any community module that adopted the unrestricted surface. **The restriction boundary must exist from day one.**

### Default mode: Restricted MDX (safe for all content)

All content — first-party BMAD fragments, third-party modules, user overrides — compiles through the **restricted MDX pipeline** by default.

**What's allowed:**

- All standard Markdown syntax.
- **Allowlisted components only**, injected by the compiler (not imported by the author):

| Component                 | Purpose                                         | Example                                                      |
| ------------------------- | ----------------------------------------------- | ------------------------------------------------------------ |
| `<If>` / `<Unless>`   | Conditional rendering based on context          | `<If ide="cursor">…</If>`                                 |
| `<Var>`                 | Emit a config variable as literal text          | `<Var name="user_name" />`                                 |
| `<Include>`             | Pull in a named fragment                        | `<Include fragment="persona-guard" />`                     |
| `<Fragment>`            | Define a named, overridable block               | `<Fragment id="greeting">…</Fragment>`                    |
| `<Switch>` / `<Case>` | Multi-branch context selection                  | `<Switch on="ide"><Case value="cursor">…</Case></Switch>` |
| `<ForEach>`             | Iterate over a context list (e.g. capabilities) | `<ForEach items={capabilities}>…</ForEach>`               |

- **No `import` statements.** Components are provided by the compiler environment, not by user code.
- **No arbitrary `{expressions}`.** Only component props and `<Var />` accessors. Raw `{…}` blocks that are not component attributes are rejected at compile time with a clear error message.
- **No inline JS, no `export`, no dynamic evaluation.**

**What this means in practice:**

The restricted surface is **Markdown + a small DSL expressed as JSX tags**. Authors write what looks like HTML-in-Markdown (which they're already familiar with from MDX docs and the BMAD docs site). The compiler validates that only allowlisted tags are used before any processing runs.

**Implementation:** A custom recma (post-MDX AST) plugin walks the tree after parsing and **rejects any node** that is not plain Markdown or an allowlisted component. This runs before evaluation, so no user code ever executes. Failed validation produces a clear error: `"Component <Foo> is not in the allowlist. Only <If>, <Unless>, <Var>, <Include>, <Fragment>, <Switch>, <Case>, <ForEach> are permitted."`

### Full MDX mode (escape hatch for power users)

Restricted mode is the **safe default**, but full MDX is a **first-class supported mode** — not a reluctant concession. Some users and teams genuinely need the full surface: custom component libraries, programmatic generation, TypeScript-driven conditional logic, or rapid prototyping of new components before proposing them for the restricted allowlist. The escape hatch exists because the framework should empower people who know what they're doing, not gatekeep them.

**Three ways to opt in** (all explicit, no accidental activation):

```yaml
# 1. Project-level config (persistent, affects all compiles in this project)
# In _bmad/core/config.yaml
compiler:
  trust_mode: full       # default: "restricted"
```

```bash
# 2. Per-invocation flag (temporary, for testing or one-off builds)
npx bmad compile --trust full

# 3. Environment variable (useful for CI or dev environments)
BMAD_COMPILER_TRUST=full npx bmad install
```

**What this unlocks:** Arbitrary imports, custom components, JS expressions, TypeScript — the complete MDX surface. Authors can define and use their own components beyond the allowlist, import utility libraries, and write arbitrary rendering logic.

**What it means for security:** All `.mdx` content (including community modules) can execute arbitrary code during compilation. This is the same trust boundary as `npm install` with postinstall scripts. Users should only enable this when they trust every module source in their install.

**When to use:**

- Org-internal setups where all module sources are code-reviewed.
- Solo developers who want maximum flexibility for their own projects.
- Development and testing of new restricted-mode components before proposing them for the allowlist.
- Enterprise teams with their own component libraries deployed via private module registries.

**Guard rails (even in full mode):**

- `npx bmad install` prints a one-line notice when `trust_mode: full` is active so the user is never unaware.
- The `bmad-customize` skill (Section 7) defaults to scaffolding restricted-compatible overrides regardless of mode. When creating content that uses full-mode features, it flags this clearly: "This override uses imports/expressions that require `trust_mode: full`. It won't compile for users in restricted mode."
- `npx bmad compile --explain` shows which files used full-mode features, so teams can audit what would break if they switched back to restricted.

### Expanding the allowlist over time

The restricted component set is not frozen. New components can be added when real customization needs emerge:

1. Someone identifies a pattern that can't be expressed with the current set.
2. A new component is proposed (as a PR or issue) with its semantics and safety properties.
3. The component is implemented in the compiler, added to the allowlist, and documented.
4. All existing restricted-mode content continues to work (the allowlist only grows).

This is the same model as adding new HTML elements to a spec — additive, non-breaking, community-driven.

---

## 4. Migration path

### Phase 1: Restricted compiler + fragments + workflow customization (non-breaking)

- Add `tools/compiler/` with MDX pipeline **and** the restricted-mode recma plugin (allowlist enforcement from day one).
- Define the initial allowlisted component set: `<If>`, `<Unless>`, `<Var>`, `<Include>`, `<Fragment>`, `<Switch>`, `<Case>`, `<ForEach>`. No workflow-specific components — workflows use the same primitives as everything else.
- Add `src/fragments/` with extracted shared blocks (on-activation, persona-guard, menu-handler, step-mandatory-rules, step-context-boundaries, workflow-architecture-rules, etc.).
- Convert a **small set of agent skills and their workflows** (e.g. 3 agents + 2 workflows with step files) to `.mdx` source using only restricted components, emitting identical `.md` output.
- Validate compiled output matches current hand-written files byte-for-byte.
- Wire `npm run compile && npm run validate:skills` into `npm run quality`.
- Add `--trust full` opt-in for internal development.

### Phase 2: Full conversion + user overrides

- Convert all remaining skills, workflows, and step files to `.mdx` source.
- Remove hand-written duplicated blocks from source.
- Implement full override resolution (`_prompt-overrides/` shadow tree) for fragments, skills, step files, and workflow sequences.
- Ship the `bmad-customize` companion skill in BMB (Section 7) with workflow customization support.
- Document the override system, restricted component API, and workflow customization patterns for users.
- Add `--watch` mode.

### Phase 3: Adaptive skills + third-party compiler support

- Add IDE/model context to the `CompileContext`.
- Author platform-specific fragments using `<If>` / `<Switch>`.
- Validate that each (IDE × model) variant passes `validate-skills`.
- Support `compile: true` in third-party `module.yaml` (Section 8).
- Version the fragment API; publish stability contract for community module authors.

### Phase 4: Ecosystem maturation

- Expand the allowlisted component set based on real community requests.
- Add `--explain` build tracing for debugging compiled output.
- Autoresearch-style optimization harness (Section 5) for CI-driven fragment tuning.
- Evaluate whether `trust_mode: full` should support a per-module granularity (e.g. trust first-party, restrict community).

---

## 5. Autonomous prompt optimization (autoresearch-style loops)

The compiled skills architecture enables a powerful workflow borrowed from [Karpathy&#39;s autoresearch](https://github.com/karpathy/autoresearch): **automated, iterative optimization of individual prompt fragments** using an agent-driven experiment loop.

### How it maps

In autoresearch, an AI agent modifies `train.py` (the experiment), trains for a fixed budget, measures a metric, and keeps or discards the change — while `program.md` (the instructions) stays fixed. The same pattern applies to compiled skills:

| autoresearch                                    | skill compiler                                                                  |
| ----------------------------------------------- | ------------------------------------------------------------------------------- |
| `train.py` — the single file the agent edits | One fragment `.mdx` — the piece being optimized                              |
| `program.md` — fixed agent instructions      | The rest of the skill tree — held constant                                     |
| 5-min train run →`val_bpb` metric            | Compile → run skill against eval task → score output quality                  |
| Keep/discard based on metric delta              | Keep/discard fragment variant based on quality score                            |
| Experiments are isolated and comparable         | Fragment changes are isolated; all dependent skills recompile deterministically |

### Why compilation makes this practical

Without a compile step, optimizing a shared block (e.g. the "On Activation" sequence) means editing 9 separate files per iteration and hoping they stay consistent. **With compilation:**

1. **The agent edits one `.mdx` fragment** — the unit of experimentation is a single file.
2. **Watch mode recompiles all dependent skills** — incremental, sub-second, no manual coordination.
3. **An eval harness scores the compiled output** — run the skill against a benchmark task, measure adherence to acceptance criteria, response quality, or any domain-specific metric. **[Promptfoo](https://github.com/promptfoo/promptfoo)** is a natural fit here: it's an open-source prompt testing framework designed to evaluate prompt outputs against assertions. The compiler emits the prompt; Promptfoo runs it against test cases; the agent reads the score.
4. **Keep or revert** — the agent decides based on the score and proceeds to the next experiment.

This gives you **independent optimization of orthogonal concerns**: one loop tunes the persona guard phrasing, another tunes the activation sequence, another tunes model-specific guardrails — all running in parallel without interfering, because each targets a different fragment.

A further evolution: **[DSPy](https://github.com/stanfordnlp/dspy)** (Stanford NLP) treats prompts as *learnable parameters* — it optimizes prompt phrasing via examples and feedback loops, automatically generating model-specific variants. DSPy's learned optimization and BMAD's authored composition are complementary, not competing. A future integration could use DSPy to optimize individual compiled fragments: the author provides the structure and intent via MDX, DSPy tunes the specific wording for each target model within that structure.

### What this unlocks on the roadmap

- **Adaptive Skills** becomes testable: compile the same skill tree with `{ide: "cursor"}` vs `{ide: "claude-code"}`, run the same eval suite, compare scores. The agent can search for platform-specific phrasing that measurably improves output quality.
- **Community contributions** become evaluable: a submitted fragment override can be scored against the baseline before merging.
- **Regression detection**: CI runs the eval suite on every PR that touches fragments; quality regressions surface before merge.

Without compilation, none of this is practical — you'd be copy-pasting changes across files, manually verifying consistency, and hoping the eval setup matches what's actually installed.

---

## 6. Concrete duplication that Phase 1 eliminates

These blocks become **single-source fragments** in Phase 1:

### `on-activation-bmm.mdx` — used by 9 skills

```markdown
1. Load config from `{project-root}/_bmad/bmm/config.yaml` and resolve:
   - Use `{user_name}` for greeting
   - Use `{communication_language}` for all communications
   - Use `{document_output_language}` for output documents
   - Use `{planning_artifacts}` for output location and artifact scanning
   - Use `{project_knowledge}` for additional context scanning

2. **Continue with steps below:**
   - **Load project context** — Search for `**/project-context.md`. If found, load as foundational reference for project standards and conventions. If not found, continue without it.
   - **Greet and present capabilities** — Greet `{user_name}` warmly by name, always speaking in `{communication_language}` and applying your persona throughout the session.
```

### `persona-guard.mdx` — used by 6 agent skills

```markdown
You must fully embody this persona so the user gets the best experience and help they need, therefore its important to remember you must not break character until the users dismisses this persona.

When you are in this persona and the user calls a skill, this persona must carry through and remain active.
```

### `menu-handler.mdx` — used by 6 agent skills

```markdown
3. Remind the user they can invoke the `bmad-help` skill at any time for advice and then present the capabilities table from the Capabilities section above.

   **STOP and WAIT for user input** — Do NOT execute menu items automatically. Accept number, menu code, or fuzzy command match.

**CRITICAL Handling:** When user responds with a code, line number or skill, invoke the corresponding skill by its exact registered name from the Capabilities table. DO NOT invent capabilities on the fly.
```

---

## 7. Companion skill: `bmad-customize` (BMB module addition)

The customize skill belongs in **BMad Builder (BMB)** alongside the existing builder trifecta (`bmad-agent-builder`, `bmad-workflow-builder`, `bmad-module-builder`). Those three skills **create** BMAD content; this one **tailors installed content**. Same audience, same toolbox — the four together cover the full authoring lifecycle: build agents, build workflows, package modules, customize the result.

It ships as part of the BMB module and is available to any project with BMB installed. The skill follows BMB's existing patterns: loads config from `_bmad/config.yaml` and `config.user.yaml`, supports `--headless` / `-H`, and routes by intent.

### Trigger phrases

- "I want to customize a skill"
- "help me override a prompt fragment"
- "customize bmad"
- "create a prompt override"

### What it does

#### Discovery mode (default)

The skill starts by helping the user understand what's customizable:

1. **Scan the installed skill tree** — list all compiled skills and their fragment dependencies.
2. **Show the fragment catalog** — present each shared fragment with a one-line summary (e.g. "`on-activation-bmm` — config loading and greeting sequence, used by 9 skills").
3. **Preview a fragment** — show the current compiled output of any fragment so the user sees exactly what they're overriding.
4. **Show downstream impact** — for a selected fragment, list every skill that includes it ("changing this will affect: bmad-agent-pm, bmad-agent-architect, bmad-agent-dev, …").

#### Create override

Once the user picks a target:

1. **Scaffold the override file** — create the file at the correct path in the override directory (`_bmad/_prompt-overrides/` or user-configured location), pre-populated with the current canonical content as a starting point.
2. **Guide edits** — the user modifies the override in their editor. The skill explains which components and variables are available, warns about `{expression}` vs literal brace syntax, and flags any content that would break compilation.
3. **Compile and diff** — trigger a compile and show a diff of every affected skill's output (before override vs after override).
4. **Validate** — run `validate-skills` on all affected compiled output and surface any errors introduced by the override.

#### Full skill replacement (escape hatch)

If fragment-level overrides aren't sufficient:

1. **Copy the full skill `.mdx` source** into the override directory.
2. **Warn clearly** — "This skill is now fully detached from upstream fragments. You won't receive upstream improvements to this skill unless you manually merge them."
3. **Tag the override** with the BMAD version it was forked from (in frontmatter metadata) so future updates can surface "upstream changed since your fork" warnings.

#### Manage existing overrides

- **List** — show all active overrides with their type (fragment vs full skill) and which BMAD version they were created against.
- **Diff upstream** — for any override, show what changed in the canonical source since the override was created. Flag overrides that may need attention after an upgrade.
- **Remove** — delete an override and recompile to revert to canonical behavior.
- **Validate all** — run the full compile + validate pipeline across all overrides and report health.

### Example session

```
User: customize bmad

Skill: Here's your installed fragment catalog:

  Fragment                  Used by         Description
  ─────────────────────────────────────────────────────────────────────
  on-activation-bmm         9 skills        Config loading and greeting sequence
  on-activation-core        3 skills        Core module activation (no doc output)
  persona-guard             6 agent skills  Character persistence instruction
  menu-handler              6 agent skills  Capability menu and input guard
  stop-wait                 4 skills        Pause-for-input instruction

  What would you like to do?
  1. Preview a fragment
  2. Create a new override
  3. Replace a full skill
  4. Manage existing overrides

User: 2 — I want to override persona-guard

Skill: persona-guard is used by 6 skills:
  bmad-agent-analyst, bmad-agent-architect, bmad-agent-dev,
  bmad-agent-pm, bmad-agent-tech-writer, bmad-agent-ux-designer

  Current content:
  ┌──────────────────────────────────────────────────────────────────┐
  │ You must fully embody this persona so the user gets the best    │
  │ experience and help they need, therefore its important to       │
  │ remember you must not break character until the users dismisses │
  │ this persona.                                                   │
  │                                                                 │
  │ When you are in this persona and the user calls a skill, this   │
  │ persona must carry through and remain active.                   │
  └──────────────────────────────────────────────────────────────────┘

  I'll create an override file at:
    _bmad/_prompt-overrides/fragments/persona-guard.mdx

  The file will contain the current canonical content as your starting point.
  Edit it however you like, then tell me when you're ready to compile and validate.

User: [edits the file]

User: ready

Skill: Compiling... done. 6 skills affected. Diff:

  bmad-agent-pm/SKILL.md:
  - You must fully embody this persona so the user gets the best
  + Stay in character as John throughout this session and any skill
  + invocations. Do not break persona unless the user explicitly
  + requests it.
  [same change in 5 other files]

  Running validate-skills... ✓ All 6 skills pass validation.

  Your override is active. Run `npx bmad compile` any time to recompile,
  or use `--watch` for live updates.
```

### Why this matters

- **Lowers the barrier** — users don't need to understand the compiler internals, MDX syntax, or directory conventions. The skill handles scaffolding, paths, and validation.
- **Prevents mistakes** — validates overrides before they can break installed skills, shows downstream impact before committing.
- **Discoverability** — the fragment catalog makes the composition model visible. Users learn what's shared and how skills are assembled.
- **Upgrade safety** — version-tagging overrides and diffing against upstream means users know when their customizations need attention after a BMAD update.

---

## 8. Third-party modules

### Current state

Third-party modules today are Git repos (or local paths) containing `SKILL.md` directories, optionally described by `marketplace.json` and `module.yaml`. The installer clones the repo, discovers skills, and copies them verbatim into `_bmad`. There is no compilation step — what the author wrote is exactly what gets installed.

### The core question

With a compiled skills architecture, third-party module authors face a choice: **ship source (`.mdx`) or ship pre-compiled (`.md`)?** The answer depends on what they want to support and how much of BMAD's compiler infrastructure they adopt.

### Three distribution models

#### Model 1: Ship pre-compiled `.md` (works today, no compiler needed)

```
third-party-module/
  skills/
    my-skill/
      SKILL.md          ← hand-written or pre-compiled by the author
      workflow.md
  module.yaml
  marketplace.json
```

**How it works:** Identical to today. The installer copies the skill verbatim. The BMAD compiler is not involved.

**User overrides:** Users **can still override** these skills via `_prompt-overrides/` — the override system works at install time on any `.md` content, regardless of whether the source was `.mdx` or hand-written. The user creates a full-skill replacement override (not fragment-level, since there are no fragments to shadow).

**Who it's for:** Authors who don't want a BMAD compiler dependency. Simple modules with few skills that don't need platform variants.

**Tradeoff:** No fragment reuse, no conditional platform content, no access to BMAD's shared components. But zero onboarding cost — it's how everything works today.

#### Model 2: Ship `.mdx` source + use BMAD's compiler (recommended)

```
third-party-module/
  src/
    skills/
      my-skill/
        SKILL.mdx       ← uses BMAD fragments + own fragments
    fragments/
      my-custom-block.mdx
  module.yaml
  marketplace.json
```

**How it works:** The module declares in `module.yaml` that it ships MDX source:

```yaml
code: my-module
name: "My Module"
compile: true               # signals the installer to compile, not copy
compiler_version: ">=1.0"   # minimum BMAD compiler version required
```

At install time, the BMAD compiler:

1. Resolves the module's `.mdx` files.
2. Makes BMAD's core fragment library available as imports (e.g. `<OnActivation />`, `<PersonaGuard />`).
3. Passes the same `CompileContext` (IDE, model, config) as for first-party skills.
4. Emits compiled `.md` into `_bmad/{module-name}/`.

**User overrides:** Full fragment-level overrides work. If the module uses `<OnActivation />`, the user's override of `on-activation-bmm.mdx` applies to this module's skills too. Module-specific fragments are also overridable via `_prompt-overrides/{module-name}/fragments/`.

**Who it's for:** Authors who want to leverage BMAD's composition model, ship adaptive skills across platforms, and give users granular customization.

**Tradeoff:** Module authors take a dependency on BMAD's compiler and fragment API. The fragment API needs a stability contract (see open questions).

#### Model 3: Ship both source and pre-compiled (maximum compatibility)

```
third-party-module/
  src/
    skills/
      my-skill/
        SKILL.mdx
  dist/
    skills/
      my-skill/
        SKILL.md         ← pre-compiled default
  module.yaml
  marketplace.json
```

**How it works:** `module.yaml` declares:

```yaml
compile: true
fallback_dist: dist/       # use if compiler unavailable or version mismatch
```

- If the user's BMAD install has a compatible compiler → compile from `src/` (full fragment/override support).
- If no compiler (older BMAD version, or user opted out) → copy from `dist/` (same as Model 1).

**Who it's for:** Module authors who want wide compatibility but still want to offer the compiled experience to users who have it.

**Tradeoff:** Authors maintain two outputs (or automate `dist/` generation in their own CI). But this is a solved pattern — it's the same as shipping both ESM and CJS in npm packages.

### Do third-party authors need to compile for every target combination?

**No.** Compilation happens at **install time on the user's machine**, not at publish time. The module ships `.mdx` source; the user's BMAD compiler combines it with the user's `CompileContext` (which IDE, which model, which config). This is the same model as a React component library: you ship JSX, the consumer's bundler compiles it for their target.

This means:

- A module author writes `{props.ide === "cursor" && <CursorBlock />}` **once**.
- Every user gets the right output for **their** IDE at install time.
- The author does **not** need to produce and publish `dist/cursor/`, `dist/claude-code/`, `dist/gemini/` etc.

The only exception is **Model 3's fallback `dist/`**, which is a single pre-compiled default for users without the compiler. Authors pick one reasonable default (or omit it and require the compiler).

### Can users customize third-party modules the same way?

**Yes, identically.** The override resolution chain extends naturally:

```
Resolution order (last wins):
  1. BMAD core fragment         (e.g. on-activation-bmm.mdx)
  2. User override of core      (e.g. _prompt-overrides/fragments/on-activation-bmm.mdx)
  3. Module-specific fragment   (e.g. my-module/fragments/my-custom-block.mdx)
  4. User override of module    (e.g. _prompt-overrides/my-module/fragments/my-custom-block.mdx)
  5. Full skill replacement     (e.g. _prompt-overrides/my-module/skills/my-skill/SKILL.mdx)
```

The `bmad-customize` skill (Section 7) works the same way for third-party modules: it shows the module's fragment catalog, scaffolds overrides in the right subdirectory, compiles, diffs, and validates.

### Fragment API stability

If third-party modules import BMAD core fragments, those fragments become a **public API**. Breaking changes (renaming a fragment, changing its props) break third-party modules. This requires:

- **Versioned fragment API** — fragments declare a version; modules declare minimum required version.
- **Deprecation cycle** — old fragment names kept as aliases for at least one major version.
- **CI check** — the BMAD repo's own CI validates that no published fragment's props changed in a breaking way.

This is the same discipline as any library API, just applied to prompt components.

### Impact on `marketplace.json` and `PluginResolver`

Minimal changes:

- `marketplace.json` schema gains an optional `compile: true` field per plugin.
- `PluginResolver` checks for `compile` in `module.yaml`; if true, routes to the compiler instead of verbatim copy.
- `CustomModuleManager.resolveSource` passes the module's `src/` tree to the compiler when `compile: true`.
- `detectCustomFiles` excludes `_prompt-overrides/{module-name}/` from "accidental edit" detection, same as for core overrides.

---

## 9. Workflow customization

### Why workflows must be customizable from day one

Workflows are where BMAD's real value lives — the step-by-step sequences that guide agents through complex tasks like creating architecture, writing stories, or running code reviews. If users can customize SKILL.md (the skill shell) but not the workflow (the actual behavior), the compiler solves the **easy** problem and ignores the **hard** one.

Real customization needs are workflow-level: "add a security review step to code review," "skip the web research step in create-story for air-gapped environments," "inject our compliance checklist after architecture validation," "replace the brainstorming technique selection with our org's standard process."

### Current workflow structure

BMAD workflows use two patterns, both of which the compiler must handle:

**Pattern A: Step-file architecture** (16 workflows, 55 step files)

```
bmad-code-review/
  workflow.md              ← sequence definition + initialization
  steps/
    step-01-gather-context.md
    step-02-review.md
    step-03-triage.md
    step-04-present.md
```

`workflow.md` defines the sequence and rules; each `step-XX-name.md` is self-contained with its own rules, instructions, and context boundaries. Steps are loaded sequentially at runtime.

**Pattern B: Inline workflow XML** (6 workflows, all in `4-implementation/`)

```
bmad-create-story/
  workflow.md              ← contains <step n="1">…</step> elements inline
```

All steps are defined as `<step>` elements within a single `<workflow>` block. Same sequential execution, different file layout. Used by: `bmad-create-story`, `bmad-dev-story`, `bmad-correct-course`, `bmad-retrospective`, `bmad-sprint-planning`, `bmad-sprint-status`.

Note: Git history shows these are **two coexisting patterns**, not a legacy format being phased out. The step-file architecture was introduced as a deliberate feature (`feat: implement granular step-file workflow architecture`), while the inline XML workflows have not been migrated and there are no issues or PRs suggesting migration is planned.

### How customization works (no special operations needed)

Workflows are just files. The **same override primitives** that work for SKILL.md and fragments work for workflows — no dedicated workflow mutation components required.

| Customization need | How it's done |
|---|---|
| **Add steps to a sequence** | Override `workflow.md` (or the `<Fragment>` containing the sequence) — add your step entries |
| **Remove steps** | Override `workflow.md` — omit the step entries you don't want |
| **Reorder steps** | Override `workflow.md` — change the order |
| **Replace a step's content** | Override the step file directly (e.g. `_prompt-overrides/bmm/bmad-code-review/steps/step-02-review.mdx`) |
| **Modify part of a step** | Override a fragment used within that step (e.g. override `step-mandatory-rules`) |
| **Add content to a step** | Override the step file with your version that includes the extra content |

This is **one mental model** ("override the file") rather than six special operations. The tradeoff is that a workflow.md override is a full replacement — if upstream adds a new step, the user's override doesn't automatically get it. That's where the **compile manifest** comes in.

### Step-level fragment composition

Individual steps benefit from fragment composition. The repeated patterns across step files:

| Repeated block | Occurrences across step files |
|---|:---:|
| "MANDATORY EXECUTION RULES" header | Most step-01 files |
| "CONTEXT BOUNDARIES" section | Most step files |
| "YOU MUST ALWAYS SPEAK OUTPUT in … `{communication_language}`" | Nearly all step files |
| "NEVER load multiple step files simultaneously" | All step-file workflows |
| Step processing rules block | All step-file workflow.md files |

These become fragments:

```mdx
<!-- steps/step-01-gather-context.mdx -->

# Step 1: Gather Context

<Include fragment="step-mandatory-rules" />
<Include fragment="step-context-boundaries" />

## Instructions

...step-specific content...
```

Users can override `step-mandatory-rules` globally (affects all workflows) or per-skill (affects only one workflow's steps).

### Override resolution for workflows

The resolution chain extends naturally to cover workflow components:

```
Resolution order (last wins):
  1. BMAD core fragment             (e.g. step-mandatory-rules.mdx)
  2. User override of core fragment (e.g. _prompt-overrides/fragments/step-mandatory-rules.mdx)
  3. Skill-specific workflow/step   (e.g. bmad-code-review/steps/step-02-review.mdx)
  4. User override of workflow/step (e.g. _prompt-overrides/bmm/bmad-code-review/steps/step-02-review.mdx)
  5. Full workflow replacement       (e.g. _prompt-overrides/bmm/bmad-code-review/workflow.mdx)
```

### Compile manifest and upgrade drift detection

Since workflow overrides are full-file replacements, the compiler must detect when upstream changes make an override stale or orphaned. This is handled by the **compile manifest** — a record of every compile run that tracks what was overridden and what it was compiled against.

**What the compiler records** (written to `_bmad/_config/compile-manifest.yaml` on every compile):

```yaml
bmad_version: "6.4.0"
compiled_at: "2026-04-10T14:32:00Z"
compiler_version: "1.0.0"
trust_mode: restricted

overrides:
  - source: "_prompt-overrides/fragments/persona-guard.mdx"
    type: fragment
    targets:
      - bmad-agent-pm/SKILL.md
      - bmad-agent-architect/SKILL.md
      - bmad-agent-dev/SKILL.md
      # ...4 more
    upstream_hash: "a3f8c1..."        # hash of canonical persona-guard.mdx at compile time
    override_hash: "7b2e4d..."        # hash of user's override file

  - source: "_prompt-overrides/bmm/bmad-code-review/workflow.mdx"
    type: workflow
    targets:
      - bmad-code-review/workflow.md
    upstream_hash: "e9d1f2..."
    upstream_steps:                    # snapshot of the upstream step list at compile time
      - step-01-gather-context
      - step-02-review
      - step-03-triage
      - step-04-present
    override_hash: "c4a7b3..."

  - source: "_prompt-overrides/bmm/bmad-code-review/steps/step-02-review.mdx"
    type: step
    targets:
      - bmad-code-review/steps/step-02-review.md
    upstream_hash: "f1c3a8..."
    override_hash: "d9e2b1..."
```

**What the compiler checks on the next compile** (after a BMAD upgrade or module update):

1. **Upstream hash changed** → The canonical source that this override shadows has been modified upstream. The compiler flags it:
   `"⚠ persona-guard: upstream changed since your override was created (v6.4.0 → v6.5.0). Review your override against the new canonical version."`

2. **Upstream file removed** → The file being overridden no longer exists in the source tree. The override is orphaned:
   `"✗ step-02-review: this file no longer exists in upstream bmad-code-review. Your override has no effect. Remove it or update the target."`

3. **Upstream steps changed** (workflow overrides) → For workflow.md overrides, the compiler compares the upstream step list against the snapshot. If upstream added `step-02b-security` or removed `step-03-triage`:
   `"⚠ bmad-code-review/workflow: upstream added step-02b-security since your override was created. Your override does not include this step. Review and update."`

4. **Override file unchanged, upstream unchanged** → Clean. No warnings.

**Output format:** The compiler produces a **drift report** (JSON and human-readable) that can be:
- Printed to stdout during `npx bmad compile` or `npx bmad install`
- Written to a file (`_bmad/_config/compile-drift-report.md`)
- Fed directly into the `bmad-customize` skill for guided resolution

**Example drift report:**

```
BMAD Compile Drift Report — upgrade from v6.4.0 to v6.5.0
══════════════════════════════════════════════════════════

⚠ UPSTREAM CHANGED (2 overrides affected)
  persona-guard.mdx
    Override: _prompt-overrides/fragments/persona-guard.mdx
    Affects: 6 skills
    Action: Review your override against the new canonical version.
            Run: npx bmad compile --diff persona-guard

  bmad-code-review/workflow.mdx
    Override: _prompt-overrides/bmm/bmad-code-review/workflow.mdx
    Affects: workflow sequence
    Upstream added: step-02b-security-scan
    Action: Your workflow override is missing the new step.
            Run: bmad-customize → Manage → Diff upstream

✗ ORPHANED (1 override has no effect)
  bmad-old-skill/SKILL.mdx
    Override: _prompt-overrides/bmm/bmad-old-skill/SKILL.mdx
    Reason: bmad-old-skill was removed in v6.5.0
    Action: Delete the override or migrate to the replacement skill.

✓ CLEAN (3 overrides unchanged)
  on-activation-bmm.mdx — upstream unchanged
  step-mandatory-rules.mdx — upstream unchanged
  bmad-code-review/steps/step-02-review.mdx — upstream unchanged
```

The `bmad-customize` skill (Section 7) consumes this report in its **Manage** mode, walking the user through each drift item: showing the upstream diff, suggesting resolutions, and recompiling after fixes.

### Impact on phasing

Workflow customization ships in **Phase 1** because:

1. The step-file convention (55 step files across 22 workflows) is where the most duplication and the most customization demand exists.
2. Deferring workflows means building a fragment system that doesn't cover the content users most want to change — undermining adoption.
3. No new restricted components are needed — workflows use the same `<Include>`, `<Fragment>`, `<If>` primitives as everything else.
4. The compile manifest and drift detection are simple to implement (hash comparison + list diff) and critical for upgrade safety regardless of whether the override is a skill, fragment, or workflow.

---

## 10. Open questions

1. **BMAD placeholder syntax** — `{user_name}` collides with MDX expression syntax. Options: (a) preprocess BMAD vars before MDX compile, (b) use a `<Var name="..." />` component, (c) use `\{user_name\}` escapes. Recommendation: **(b)** for authored source, compiled output still emits `{user_name}` as literal text.
2. **Inline vs step-file workflow parity** — both workflow patterns (step-file and inline XML) need override support. Should the compiler normalize them to one internal representation before applying overrides, or handle them as separate paths? Recommendation: separate paths initially (they have different enough semantics), with a possible future unification pass.
3. **Source of truth in git** — should compiled `.md` files be checked in (easy diffing, works without build step) or `.gitignore`d (pure generated artifacts)? Recommendation: **check in compiled output** during migration (proves correctness), move to generated-only once CI is solid.
4. **`--watch` scope** — should watch mode recompile all skills or only changed ones? Recommendation: incremental by default (dependency graph from imports), `--all` flag for full rebuild.
5. **Fragment API versioning** — when third-party modules depend on core fragments, what's the stability contract? Recommendation: semver on the fragment library as a whole (not per-fragment), with a deprecation alias mechanism for renamed fragments. Breaking changes only in major BMAD versions.
6. **Third-party compiler requirement** — should `compile: true` modules fail loudly when installed on an older BMAD without the compiler, or silently fall back to `dist/`? Recommendation: warn + fall back if `fallback_dist` exists; error if no fallback and no compiler.

---

## 11. Future direction: Just-in-time compilation

### The vision

If the compiler is fast enough (sub-second for a single skill), the architecture can evolve beyond static pre-compiled files. Instead of:

1. Install time: compile all `.mdx` → `.md` with config values as `{placeholders}`
2. Runtime: LLM reads `SKILL.md`, reads `config.yaml`, mentally substitutes `{user_name}` → "Phil", loads `project-context.md`, resolves paths, etc. across multiple turns

You get:

1. Runtime: skill is invoked → compiler runs → **fully resolved prompt** is emitted with all values baked in, state assembled, context inlined — **one artifact, zero runtime resolution**

The installed skill becomes a **thin execution wrapper** — a shell script or tool call that invokes the compiler with the current context and pipes the result to the model. The LLM never sees `{user_name}` or `{communication_language}` as placeholders. It never reads `config.yaml`. It never searches for `**/project-context.md`. All of that is resolved **before the prompt reaches the model**.

### What changes

| Concern | Static compilation (current proposal) | JIT compilation (future) |
|---|---|---|
| When compilation runs | Install time (once) | Every skill invocation |
| Config values | Placeholders in output, resolved by LLM | Baked into the prompt as literals |
| Project context | LLM told to "search for and load if found" | Compiler finds it, inlines relevant sections |
| Multi-file state | LLM reads config.yaml, sprint-status.yaml, prior story, etc. | Compiler assembles a single context blob |
| Workflow state | LLM tracks progress via frontmatter | Compiler reads frontmatter, emits only the current step with accumulated state |
| Token cost | LLM spends tokens parsing config, resolving paths, loading files | Zero overhead — the prompt is already resolved |
| Reliability | Depends on LLM correctly interpreting placeholder conventions | Deterministic — compiler output is what the model sees |

### What a JIT-compiled skill invocation looks like

```bash
# Today: LLM reads SKILL.md, then spends turns loading config, finding files, resolving state
# Future: one call, fully resolved

$ npx bmad invoke bmad-agent-pm

# Compiler runs (~200ms):
#   1. Reads SKILL.mdx + all fragments
#   2. Reads _bmad/config.yaml + config.user.yaml → resolves all variables
#   3. Finds project-context.md → inlines it
#   4. Checks override directory → applies user overrides
#   5. Evaluates <If ide="cursor"> → includes/excludes conditional blocks
#   6. Emits a single fully-resolved prompt string

# Output piped to model as system prompt or skill context:
#   "# John
#    ## Overview
#    ...
#    ## On Activation
#    1. Config loaded. Project: Acme App. User: Phil. Language: English.
#    2. Project context:
#       [inlined project-context.md content]
#    3. Your capabilities: [table]
#    ..."
```

The model receives a **complete, self-contained prompt** with no instructions to "load config" or "search for files." It can start working immediately.

### Why this matters beyond convenience

- **Eliminates an entire class of LLM failure modes.** Today, models regularly misread config paths, fail to find `project-context.md`, skip config loading, or apply wrong variable values. These are instructions the LLM can get wrong. JIT compilation removes the instructions entirely — the values are already there.

- **Reduces token cost.** The "On Activation" sequence in every agent skill exists solely to tell the LLM how to bootstrap itself. With JIT, that bootstrapping is done by the compiler. The prompt is shorter and the model starts productive work sooner.

- **Enables stateful workflows without LLM state tracking.** The compiler can read a workflow's frontmatter (`stepsCompleted: [1, 2, 3]`), determine the current step, inline only that step's content with all accumulated context, and emit a prompt that says "you are on step 4, here's what happened in steps 1-3, here's your task." No more "read the frontmatter and figure out where you left off."

- **Makes watch mode truly interactive.** Change a config value or override a fragment → compiler re-emits the prompt → model sees the change immediately on the next invocation. No reinstall, no "reload config."

### Prerequisites from this proposal

JIT compilation is **not a separate architecture** — it's the same compiler running at a different time. Everything in this proposal (fragments, restricted MDX, overrides, compile manifest, drift detection) applies identically. The only additions are:

1. **`npx bmad invoke <skill>`** command that runs the compiler and outputs the resolved prompt.
2. **Context collectors** — small plugins that gather runtime state (current git branch, sprint status, prior story output) and inject it into the `CompileContext`.
3. **IDE integration** — skill trigger in Cursor/Claude that calls `bmad invoke` instead of reading the static file. This depends on IDE support for tool-backed skill loading (some IDEs support this now, others will).

### JIT-compiled subagents

The most impactful application of JIT compilation is **subagent context assembly**. Today, when a parent agent spawns a subagent — party mode spawning individual persona agents, create-story spawning research subagents, or any workflow delegating to a specialist — the parent LLM **manually constructs the subagent's context**. It reads manifest data, summarizes conversation history, forwards config values, and assembles it all into a prompt string. That's LLM-mediated string assembly, which means it can be incomplete, hallucinated, or inconsistent between invocations.

With JIT, the parent doesn't build the subagent's prompt at all. It makes a compiler call:

```bash
npx bmad invoke bmad-agent-architect \
  --context '{"topic":"API design","prior_discussion":"...summary..."}'
```

The **compiler** builds the complete subagent prompt — persona, communication style, principles, config values, project context, relevant prior state — deterministically. The parent only passes the **task-specific payload** (what to discuss, what other agents said). Everything structural is the compiler's job.

**Concrete problems this solves in the current codebase:**

- **Party mode** reads `agent-manifest.csv` and manually constructs persona prompts from manifest fields (`displayName`, `communicationStyle`, `principles`, `identity`). With JIT, it invokes each agent's skill through the compiler — the full persona with all config, project context, and behavioral rules is baked in. The parent only passes the discussion topic and what other agents said this round.

- **Create-story's parallel research** tells subagents to "analyze architecture" or "research latest tech" with manually assembled context from prior steps. JIT compiles each subagent's prompt with the exact story context, config values, and relevant artifact content already resolved — no risk of the parent forgetting to pass a critical piece of context.

- **Workflow step handoffs** — when a step-file workflow loads the next step, the LLM must carry forward state from prior steps (reading frontmatter, recalling decisions, tracking what's been completed). JIT compiles each step with the **accumulated state from prior steps already inlined**. Step 4's prompt includes a compiler-assembled summary of steps 1-3, so the model doesn't need to "remember" or re-read anything.

**The general principle:** Anything that currently relies on **one LLM call correctly setting up context for the next LLM call** becomes a compiler responsibility instead. The compiler is deterministic; the LLM isn't. Every handoff that the compiler handles is one fewer opportunity for context to degrade across the chain.

### Why not start here

JIT compilation is a **superset** of static compilation. Static is the right Phase 1 because:

- It works with **every IDE today** (they all read `.md` files; not all support tool-backed skill loading).
- It's **debuggable** — you can read the compiled `.md` file and see exactly what the model will get.
- It **doesn't require runtime infrastructure** — no daemon, no invoke command, no context collectors.
- It **proves the compiler** — same MDX pipeline, same fragments, same overrides. JIT is just "run it later."

When IDE support matures and the compiler is proven, JIT becomes a natural evolution, not a rewrite.

---

## 12. Prior art and landscape

A deep research survey of existing projects (full report: [`research-prompt-compilation-landscape.md`](research-prompt-compilation-landscape.md)) found that **no existing project combines** composable fragments, a build pipeline, user override safety, multi-model adaptation, and multi-agent assembly. The landscape is fragmented:

| Project | What it does well | What it lacks |
|---|---|---|
| **DSPy** (Stanford) | Learned prompt optimization, multi-model adaptation | No authored composition, no user overrides, no fragments |
| **Microsoft Prompt Flow** | DAG orchestration, Jinja templating, variable substitution | No fragment composition, no override system, no multi-model variants |
| **Promptfoo** | Prompt testing and evaluation | Doesn't compose prompts — only tests them |
| **Cursor rules** | User customization via `.cursor/rules` | File append only, no merge safety, no drift detection, single agent |
| **Cline** | JIT prompt assembly from context | Basic `custom_instructions` override, no fragment system |
| **CrewAI / AutoGen / LangChain** | Multi-agent orchestration | String concatenation for prompts, no composition pipeline |
| **Dust.tt** | Visual prompt composition | Closed-source, UI-first, no programmatic override system |

The component-based composition pattern (MDX-like) is identified across multiple sources as the highest-potential approach, but has **zero production implementations**. The BMAD proposal would be the first.

---

## 13. Alternatives considered

| Alternative                      | Why not (for now)                                                                                                                                                             |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Handlebars / Nunjucks**  | Simpler, but lacks component composition and TypeScript. Would work for variable substitution but doesn't scale to conditional platform blocks or shared component libraries. |
| **YAML + fragment IDs**    | Maximum safety, minimum flexibility. Good for "slot these blocks in order" but awkward for conditional content or nested composition.                                         |
| **LangChain / ADK**        | Runtime agent orchestration frameworks, not static document compilers. Wrong layer — these consume compiled skills, they don't produce them.                                 |
| **DSPy**                         | Complementary, not a replacement. DSPy *optimizes* prompt wording through learning; BMAD *composes* prompts through authoring. A future integration could use DSPy to tune compiled fragments. |
| **No change (status quo)** | Workable today but increasingly painful as skill count grows, platform targets multiply, and community customization demand increases.                                        |
