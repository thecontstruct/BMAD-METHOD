---
name: bmad-correct-course
description: 'Manage significant changes during sprint execution. Identify impacted ticket-tree work and route approved changes through ticketing, with a legacy epics-and-stories fallback. Use when the user says "correct course" or "propose sprint change"'
artifacts:
  - path: customize.toml
    source: customize.toml
    kind: scaffold-verbatim
  - path: checklist.md
    source: checklist.md
    kind: scaffold-verbatim
  - path: references/ticket-tree.md
    source: references/ticket-tree.md
    kind: scaffold-verbatim
---

# Correct Course - Sprint Change Management Workflow

**Goal:** Manage significant changes during sprint execution by identifying their impact across the ticket tree and project artifacts, then producing a structured Sprint Change Proposal.

**Your Role:** You are a Developer navigating change management. Analyze the triggering issue, assess impact across the ticket tree when it is available, and across PRD, architecture, and UX artifacts. Produce an actionable Sprint Change Proposal that sends approved ticket changes to `bmad-preview-ticketing`.

<<include path="_shared/fragments/conventions.md">>
## On Activation

### Step 1: Resolve the Workflow Block

Run: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --project-root {project-root} --key workflow`

<<include path="_shared/fragments/resolver-fallback.md" skill_kind="workflow">>
<<include path="_shared/fragments/workflow-activation.md" config_path="{project-root}/_bmad/bmm/config.yaml" skill_kind="workflow">>
## Paths

- `default_output_file` = `{planning_artifacts}/sprint-change-proposal-{date}.md`

## Input Files

| Input | Path | Load Strategy |
|-------|------|---------------|
| Ticket tree | Shared method runtime: `uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} status` | TREE_FIRST |
| PRD | `{planning_artifacts}/*prd*.md` (whole) or `{planning_artifacts}/*prd*/*.md` (sharded) | FULL_LOAD |
| Architecture | `{planning_artifacts}/*architecture*.md` (whole) or `{planning_artifacts}/*architecture*/*.md` (sharded) | FULL_LOAD |
| UX Design | `{planning_artifacts}/*ux*.md` (whole) or `{planning_artifacts}/*ux*/*.md` (sharded) | FULL_LOAD |
| Spec | `{planning_artifacts}/*spec-*.md` (whole) | FULL_LOAD |
| Document Project | `{project_knowledge}/index.md` (sharded) | INDEX_GUIDED |

## Execution

### Document Discovery - Loading Project Artifacts

**Strategy**: Course correction needs broad project context to assess change impact accurately. Load all available planning artifacts.

**Ticket-tree discovery:** Run the shared runtime command in the Ticket tree row before legacy discovery. If it resolves an active tree, read `references/ticket-tree.md` and use ticket-tree mode for ticket and epic impact. If it exits non-zero or no active tree resolves, use the legacy epics-and-stories fallback below. Do not combine ticket-tree and legacy tracking state in one proposal.

**Discovery Process for FULL_LOAD documents (PRD, Architecture, UX Design, Spec):**

1. **Search for whole document first** - Look for files matching the whole-document pattern (e.g., `*prd*.md`, `*architecture*.md`, `*ux*.md`, `*spec-*.md`)
2. **Check for sharded version** - If whole document not found, look for a directory with `index.md` (e.g., `prd/index.md`)
3. **If sharded version found**:
   - Read `index.md` to understand the document structure
   - Read ALL section files listed in the index
   - Process the combined content as a single document
4. **Priority**: If both whole and sharded versions exist, use the whole document

**Discovery Process for INDEX_GUIDED documents (Document Project):**

1. **Search for index file** - Look for `{project_knowledge}/index.md`
2. **If found**: Read the index to understand available documentation sections
3. **Selectively load sections** based on relevance to the change being analyzed — do NOT load everything, only sections that relate to the impacted areas
4. **This document is optional** — skip if `{project_knowledge}` does not exist (greenfield projects)

**Fuzzy matching**: Be flexible with document names — users may use variations like `prd.md`, `bmm-prd.md`, `product-requirements.md`, etc.

**Missing documents**: Not all documents may exist. A PRD or a spec is essential; Architecture, UX Design, and Document Project are loaded if available. In legacy mode, epics and stories are also needed to assess work impact. HALT if neither a PRD nor a spec can be found.

<workflow>

<step n="1" goal="Initialize Change Navigation">
  <action>Confirm change trigger and gather user description of the issue</action>
  <action>Ask: "What specific issue or change has been identified that requires navigation?"</action>
  <action>Verify access to project documents:</action>
    - PRD (Product Requirements Document) or spec — required
    - Architecture documentation — optional, load if available
    - UI/UX specifications — optional, load if available
  <action>Resolve the ticket tree first:</action>
    - Run `uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} status`
    - If it resolves an active tree, use `references/ticket-tree.md` to identify the affected epic and ticket rows, then resolve each affected row with `tickets.py --project-root {project-root} find <ref>`
    - If it does not resolve a tree, ask the user to describe the epics and stories the change affects: what each covers and where it stands
    - Never read or update legacy sprint status while ticket-tree mode is active
  <action>Ask user for mode preference:</action>
    - **Incremental** (recommended): Refine each edit collaboratively
    - **Batch**: Present all changes at once for review
  <action>Store mode selection for use throughout workflow</action>

<action if="change trigger is unclear">HALT: "Cannot navigate change without clear understanding of the triggering issue. Please provide specific details about what needs to change and why."</action>

<action if="neither a PRD nor a spec is available">HALT: "Need access to a PRD or a spec to assess change impact. Please ensure one is accessible. Architecture and UI/UX will be used if available."</action>
</step>

<step n="2" goal="Execute Change Analysis Checklist">
  <action>Read fully and follow the systematic analysis from: checklist.md</action>
  <action>Work through each checklist section interactively with the user</action>
  <action>Record status for each checklist item:</action>
    - [x] Done - Item completed successfully
    - [N/A] Skip - Item not applicable to this change
    - [!] Action-needed - Item requires attention or follow-up
  <action>Maintain running notes of findings and impacts discovered</action>
  <action>Present checklist progress after each major section</action>

<action if="checklist cannot be completed">Identify blocking issues and work with user to resolve before continuing</action>
</step>

<step n="3" goal="Draft Specific Change Proposals">
<action>Based on checklist findings, create explicit edit proposals for each identified artifact</action>

<action>For ticket-tree changes:</action>

- Show old → new text format
- Include the ticket `ref`, its epic folder, and whether the ticket is planned, active, built, done, or dropped
- Provide rationale for each change
- State the ticketing operation needed: add, rescope, resequence, update prerequisites, drop, or split
- Preserve an existing ticket id. Do not rewrite active, built, done, or dropped work as a new plan; propose a separate ticket when the change must follow completed work.
- Do not edit ticket files, plans, `tickets.toml`, or ticket status in this workflow. The approved handoff goes through `bmad-preview-ticketing`.
- Example format:

  ```
  Ticket: [2.3] User Authentication
  Epic: epic-identity
  Operation: Rescope

  OLD:
  - User can log in with email/password

  NEW:
  - User can log in with email/password
  - User can enable 2FA via authenticator app

  Rationale: Security requirement identified during implementation
  ```

<action if="legacy epics-and-stories mode">For story changes, show the story ID and section being modified using the same old → new format. Do not create or update ticket-tree records in legacy mode.</action>

<action>For PRD modifications:</action>

- Specify exact sections to update
- Show current content and proposed changes
- Explain impact on MVP scope and requirements

<action>For Architecture changes:</action>

- Identify affected components, patterns, or technology choices
- Describe diagram updates needed
- Note any ripple effects on other components

<action>For UI/UX specification updates:</action>

- Reference specific screens or components
- Show wireframe or flow changes needed
- Connect changes to user experience impact

<check if="mode is Incremental">
  <action>Present each edit proposal individually</action>
  <action>HALT and give the user a choice:
  - **Approve** — accept this proposal
  - **Edit** — refine this proposal
  - **Skip** — drop this proposal
  </action>
  <action>If the user chooses **Approve**, keep the proposal. If they choose **Edit**, refine it with them. If they choose **Skip**, drop it. Continue to the next proposal.</action>
</check>

<action if="mode is Batch">Collect all edit proposals and present together at end of step</action>

</step>

<step n="4" goal="Generate Sprint Change Proposal">
<action>Compile comprehensive Sprint Change Proposal document with following sections:</action>

<action>Section 1: Issue Summary</action>

- Clear problem statement describing what triggered the change
- Context about when/how the issue was discovered
- Evidence or examples demonstrating the issue

<action>Section 2: Impact Analysis</action>

- Ticket-tree Impact: Which epic folders and ticket rows are affected, their current state, and which prerequisites or dependents change
- Legacy Impact: Which epics and stories are affected when no ticket tree is available
- Artifact Conflicts: PRD, Architecture, UI/UX documents needing updates
- Technical Impact: Code, infrastructure, or deployment implications

<action>Section 3: Recommended Approach</action>

- Present chosen path forward from checklist evaluation:
  - Direct Adjustment: Modify/add stories within existing plan
  - Potential Rollback: Revert completed work to simplify resolution
  - MVP Review: Reduce scope or modify goals
- Provide clear rationale for recommendation
- Include effort estimate, risk assessment, and timeline impact

<action>Section 4: Detailed Change Proposals</action>

- Include all refined edit proposals from Step 3
- Group by artifact type (Ticket tree or Stories, PRD, Architecture, UI/UX)
- Ensure each change includes before/after and justification

<action>Section 5: Implementation Handoff</action>

- Categorize change scope:
  - Minor: Direct implementation by Developer agent
  - Moderate: Backlog reorganization needed (PO/DEV)
  - Major: Fundamental replan required (PM/Architect)
- In ticket-tree mode, list each approved ticket operation and route it to `bmad-preview-ticketing`; include affected refs, epic folders, intended operation, rationale, and sequencing constraints. `bmad-correct-course` does not apply the ticket changes.
- Specify handoff recipients and their responsibilities
- Define success criteria for implementation

<action>Present complete Sprint Change Proposal to user</action>
<action>Write Sprint Change Proposal document to {default_output_file}</action>
<action>HALT and give the user a choice:
- **Continue** — proceed to approval
- **Edit** — revise the proposal first
</action>
<action>If the user chooses **Edit**, revise the proposal with them and write the updated document before continuing.</action>
</step>

<step n="5" goal="Finalize and Route for Implementation">
<action>Get explicit user approval for complete proposal</action>
<ask>Do you approve this Sprint Change Proposal for implementation? (yes/no/revise)</ask>

<check if="no or revise">
  <action>Gather specific feedback on what needs adjustment</action>
  <action>Return to appropriate step to address concerns</action>
  <goto step="3">If changes needed to edit proposals</goto>
  <goto step="4">If changes needed to overall proposal structure</goto>

</check>

<check if="yes the proposal is approved by the user">
  <action>Finalize Sprint Change Proposal document</action>
  <action>Determine change scope classification:</action>

- **Minor**: Can be implemented directly by Developer agent
- **Moderate**: Requires backlog reorganization and PO/DEV coordination
- **Major**: Needs fundamental replan with PM/Architect involvement

<action>Provide appropriate handoff based on scope:</action>

</check>

<check if="Minor scope">
  <action>Route to: Developer agent for direct implementation</action>
  <action>Deliverables: Finalized edit proposals and implementation tasks</action>
</check>

<check if="Moderate scope">
  <action>Route to: Product Owner / Developer agents and `bmad-preview-ticketing` for ticket-tree changes</action>
  <action>Deliverables: Sprint Change Proposal + backlog reorganization plan or ticketing operations list</action>
</check>

<check if="Major scope">
  <action>Route to: Product Manager / Solution Architect, then `bmad-preview-ticketing` for approved ticket-tree changes</action>
  <action>Deliverables: Complete Sprint Change Proposal + escalation notice + ticketing operations list</action>

<action>Confirm handoff completion and next steps with user</action>
<action>Document handoff in workflow execution log</action>
</check>

</step>

<step n="6" goal="Workflow Completion">
<action>Summarize workflow execution:</action>
  - Issue addressed: {change_trigger}
  - Change scope: {scope_classification}
  - Artifacts modified: {list_of_artifacts}
  - Routed to: {handoff_recipients}

<action>Confirm all deliverables produced:</action>

- Sprint Change Proposal document
- Specific edit proposals with before/after
- Implementation handoff plan

<action>Report workflow completion to user with personalized message: "Correct Course workflow complete, {user_name}!"</action>
<action>Remind user of success criteria and next steps for Developer agent</action>
<action><<include path="_shared/fragments/on-complete.md">></action>
</step>

</workflow>
