---
name: bmad-create-ux-design
description: 'Plan UX patterns and design specifications. Use when the user says "lets create UX design" or "create UX specifications" or "help me plan the UX"'
artifacts:
  - path: ux-design-template.md
    source: ux-design-template.md
    kind: scaffold-verbatim
  - path: steps/step-01-init.md
    source: steps/step-01-init.md
    kind: scaffold-verbatim
  - path: steps/step-01b-continue.md
    source: steps/step-01b-continue.md
    kind: scaffold-verbatim
  - path: steps/step-02-discovery.md
    source: steps/step-02-discovery.md
    kind: scaffold-verbatim
  - path: steps/step-03-core-experience.md
    source: steps/step-03-core-experience.md
    kind: scaffold-verbatim
  - path: steps/step-04-emotional-response.md
    source: steps/step-04-emotional-response.md
    kind: scaffold-verbatim
  - path: steps/step-05-inspiration.md
    source: steps/step-05-inspiration.md
    kind: scaffold-verbatim
  - path: steps/step-06-design-system.md
    source: steps/step-06-design-system.md
    kind: scaffold-verbatim
  - path: steps/step-07-defining-experience.md
    source: steps/step-07-defining-experience.md
    kind: scaffold-verbatim
  - path: steps/step-08-visual-foundation.md
    source: steps/step-08-visual-foundation.md
    kind: scaffold-verbatim
  - path: steps/step-09-design-directions.md
    source: steps/step-09-design-directions.md
    kind: scaffold-verbatim
  - path: steps/step-10-user-journeys.md
    source: steps/step-10-user-journeys.md
    kind: scaffold-verbatim
  - path: steps/step-11-component-strategy.md
    source: steps/step-11-component-strategy.md
    kind: scaffold-verbatim
  - path: steps/step-12-ux-patterns.md
    source: steps/step-12-ux-patterns.md
    kind: scaffold-verbatim
  - path: steps/step-13-responsive-accessibility.md
    source: steps/step-13-responsive-accessibility.md
    kind: scaffold-verbatim
  - path: steps/step-14-complete.md
    source: steps/step-14-complete.md
    kind: scaffold-verbatim
---

# Create UX Design Workflow

**Goal:** Create comprehensive UX design specifications through collaborative visual exploration and informed decision-making where you act as a UX facilitator working with a product stakeholder.

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

## Paths

- `default_output_file` = `{planning_artifacts}/ux-design-specification.md`

## EXECUTION

- ✅ YOU MUST ALWAYS SPEAK OUTPUT In your Agent communication style with the config `{communication_language}`
- ✅ YOU MUST ALWAYS WRITE all artifact and document content in `{document_output_language}`
- Read fully and follow: `./steps/step-01-init.md` to begin the UX design workflow.
