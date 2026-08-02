---
name: bmad-document-project
description: 'Document brownfield projects for AI context. Use when the user says "document this project" or "generate project docs"'
artifacts:
  - path: checklist.md
    source: checklist.md
    kind: scaffold-verbatim
  - path: documentation-requirements.csv
    source: documentation-requirements.csv
    kind: scaffold-verbatim
  - path: instructions.md
    source: instructions.md
    kind: scaffold-verbatim
  - path: templates/deep-dive-template.md
    source: templates/deep-dive-template.md
    kind: scaffold-verbatim
  - path: templates/index-template.md
    source: templates/index-template.md
    kind: scaffold-verbatim
  - path: templates/project-overview-template.md
    source: templates/project-overview-template.md
    kind: scaffold-verbatim
  - path: templates/project-scan-report-schema.json
    source: templates/project-scan-report-schema.json
    kind: scaffold-verbatim
  - path: templates/source-tree-template.md
    source: templates/source-tree-template.md
    kind: scaffold-verbatim
  - path: workflows/deep-dive-instructions.md
    source: workflows/deep-dive-instructions.md
    kind: scaffold-verbatim
  - path: workflows/deep-dive-workflow.md
    source: workflows/deep-dive-workflow.md
    kind: scaffold-verbatim
  - path: workflows/full-scan-instructions.md
    source: workflows/full-scan-instructions.md
    kind: scaffold-verbatim
  - path: workflows/full-scan-workflow.md
    source: workflows/full-scan-workflow.md
    kind: scaffold-verbatim
---

# Document Project Workflow

**Goal:** Document brownfield projects for AI context.

**Your Role:** Project documentation specialist.

## Conventions

- Bare paths (e.g. `instructions.md`) resolve from the skill root.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

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

Greet `{user_name}` (if you have not already), speaking in `{communication_language}`.

### Step 6: Execute Append Steps

Execute each entry in `{workflow.activation_steps_append}` in order.

Activation is complete. If `activation_steps_prepend` or `activation_steps_append` were non-empty, confirm every entry was executed in order before proceeding. Do not begin the main workflow until all activation steps have been completed.

## Execution

Read fully and follow: `./instructions.md`
