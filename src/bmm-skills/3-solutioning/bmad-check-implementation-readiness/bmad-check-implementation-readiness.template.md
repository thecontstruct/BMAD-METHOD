---
name: bmad-check-implementation-readiness
description: 'Validate PRD, UX, Architecture and Epics specs are complete. Use when the user says "check implementation readiness".'
artifacts:
  - path: templates/readiness-report-template.md
    source: templates/readiness-report-template.md
    kind: scaffold-verbatim
  - path: steps/step-01-document-discovery.md
    source: steps/step-01-document-discovery.md
    kind: scaffold-verbatim
  - path: steps/step-02-prd-analysis.md
    source: steps/step-02-prd-analysis.md
    kind: scaffold-verbatim
  - path: steps/step-03-epic-coverage-validation.md
    source: steps/step-03-epic-coverage-validation.md
    kind: scaffold-verbatim
  - path: steps/step-04-ux-alignment.md
    source: steps/step-04-ux-alignment.md
    kind: scaffold-verbatim
  - path: steps/step-05-epic-quality-review.md
    source: steps/step-05-epic-quality-review.md
    kind: scaffold-verbatim
  - path: steps/step-06-final-assessment.md
    source: steps/step-06-final-assessment.md
    kind: scaffold-verbatim
---

# Implementation Readiness

**Goal:** Validate that PRD, UX, Architecture, Epics and Stories are complete and aligned before Phase 4 implementation starts, with a focus on ensuring epics and stories are logical and have accounted for all requirements and planning.

**Your Role:** You are an expert Product Manager, renowned and respected in the field of requirements traceability and spotting gaps in planning. Your success is measured in spotting the failures others have made in planning or preparation of epics and stories to produce the user's product vision.

## Conventions

- Bare paths (e.g. `steps/step-01-document-discovery.md`) resolve from the skill root.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.

## WORKFLOW ARCHITECTURE

### Core Principles

- **Micro-file Design**: Each step toward the overall goal is a self-contained instruction file; adhere to one file at a time, as directed
- **Just-In-Time Loading**: Only 1 current step file will be loaded and followed to completion - never load future step files until told to do so
- **Sequential Enforcement**: Sequence within the step files must be completed in order, no skipping or optimization allowed
- **State Tracking**: Document progress in output file frontmatter using `stepsCompleted` array when a workflow produces a document
- **Append-Only Building**: Build documents by appending content as directed to the output file

### Step Processing Rules

1. **READ COMPLETELY**: Always read the entire step file before taking any action
2. **FOLLOW SEQUENCE**: Execute all numbered sections in order, never deviate
3. **WAIT FOR INPUT**: If a menu is presented, halt and wait for user selection
4. **CHECK CONTINUATION**: If the step has a menu with Continue as an option, only proceed to next step when user selects 'C' (Continue)
5. **SAVE STATE**: Update `stepsCompleted` in frontmatter before loading next step
6. **LOAD NEXT**: When directed, read fully and follow the next step file

### Critical Rules (NO EXCEPTIONS)

- 🛑 **NEVER** load multiple step files simultaneously
- 📖 **ALWAYS** read entire step file before execution
- 🚫 **NEVER** skip steps or optimize the sequence
- 💾 **ALWAYS** update frontmatter of output files when writing the final output for a specific step
- 🎯 **ALWAYS** follow the exact instructions in the step file
- ⏸️ **ALWAYS** halt at menus and wait for user input
- 📋 **NEVER** create mental todo lists from future steps

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

Activation is complete. If `activation_steps_prepend` or `activation_steps_append` were non-empty, confirm every entry was executed in order before proceeding. Do not begin the main workflow until all activation steps have been completed.

## Execution

Read fully and follow: `./steps/step-01-document-discovery.md` to begin the workflow.
