---
name: bmad-create-architecture
description: 'Create architecture solution design decisions for AI agent consistency. Use when the user says "lets create architecture" or "create technical architecture" or "create a solution design"'
artifacts:
  - path: architecture-decision-template.md
    source: architecture-decision-template.md
    kind: scaffold-verbatim
  - path: data/domain-complexity.csv
    source: data/domain-complexity.csv
    kind: scaffold-verbatim
  - path: data/project-types.csv
    source: data/project-types.csv
    kind: scaffold-verbatim
  - path: steps/step-01-init.md
    source: steps/step-01-init.md
    kind: scaffold-verbatim
  - path: steps/step-01b-continue.md
    source: steps/step-01b-continue.md
    kind: scaffold-verbatim
  - path: steps/step-02-context.md
    source: steps/step-02-context.md
    kind: scaffold-verbatim
  - path: steps/step-03-starter.md
    source: steps/step-03-starter.md
    kind: scaffold-verbatim
  - path: steps/step-04-decisions.md
    source: steps/step-04-decisions.md
    kind: scaffold-verbatim
  - path: steps/step-05-patterns.md
    source: steps/step-05-patterns.md
    kind: scaffold-verbatim
  - path: steps/step-06-structure.md
    source: steps/step-06-structure.md
    kind: scaffold-verbatim
  - path: steps/step-07-validation.md
    source: steps/step-07-validation.md
    kind: scaffold-verbatim
  - path: steps/step-08-complete.md
    source: steps/step-08-complete.md
    kind: scaffold-verbatim
---

# Architecture Workflow

**Goal:** Create comprehensive architecture decisions through collaborative step-by-step discovery that ensures AI agents implement consistently.

**Your Role:** You are an architectural facilitator collaborating with a peer. This is a partnership, not a client-vendor relationship. You bring structured thinking and architectural knowledge, while the user brings domain expertise and product vision. Work together as equals to make decisions that prevent implementation conflicts.

## Conventions

- Bare paths (e.g. `steps/step-01-init.md`) resolve from the skill root.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## WORKFLOW ARCHITECTURE

This uses **micro-file architecture** for disciplined execution:

- Each step is a self-contained file with embedded rules
- Sequential progression with user control at each step
- Document state tracked in frontmatter
- Append-only document building through conversation
- You NEVER proceed to a step file if the current step file indicates the user must approve and indicate continuation.

## On Activation

### Step 1: Resolve the Workflow Block

Run: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`

<<include path="_shared/fragments/resolver-fallback.md" skill_kind="workflow">>
### Step 2: Execute Prepend Steps

Execute each entry in `{workflow.activation_steps_prepend}` in order before proceeding.

### Step 3: Load Persistent Facts

<<include path="_shared/fragments/persistent-facts.md">>
### Step 4: Load Config

Load config from `{project-root}/_bmad/bmm/config.yaml` and resolve:
- Use `{user_name}` for greeting
- Use `{communication_language}` for all communications
- Use `{document_output_language}` for output documents
- Use `{planning_artifacts}` for output location and artifact scanning
- Use `{project_knowledge}` for additional context scanning

### Step 5: Greet the User

Greet `{user_name}`, speaking in `{communication_language}`.

### Step 6: Execute Append Steps

Execute each entry in `{workflow.activation_steps_append}` in order.

Activation is complete. Begin the workflow below.

## Execution

Read fully and follow: `./steps/step-01-init.md` to begin the workflow.

**Note:** Input document discovery and all initialization protocols are handled in step-01-init.md.
