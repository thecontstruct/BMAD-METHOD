---
name: bmad-retrospective
description: 'Evidence-based epic retrospective — collect what the epic produced, verify findings against sources, and render an acceptance verdict. Use when the user says "run a retrospective" or "lets retro the epic [epic]". Supports -H/--headless.'
---

# Retrospective

Review a completed epic by reading the evidence it left: its epic and story records, the full diff, per-story commits, sprint status, and session logs when they exist. Every finding must cite a file, line, commit, or log. A claim without evidence is not a finding.

## RULES

- Communicate in `{communication_language}` and write artifacts in `{document_output_language}`.
- Do not modify project code, specs, stories, or tests. The retrospective may update sprint status only after the human accepts its action items and verdict. In stories mode, it writes only the retrospective document in the selected spec folder.
- Do not invent a root cause or a trend. Drop a pattern that is not demonstrated by the evidence.
- `-H` / `--headless` means do not ask questions: select the requested epic, use machine-verifiable evidence, write the report, and return the verdict.
- Party-mode discussion is opt-in. It discusses the evidence already gathered; it never replaces gathering or changes an evidence-backed finding without recording the source.

<<include path="_shared/fragments/conventions.md">>

## On Activation

Run: `python3 {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`

<<include path="_shared/fragments/resolver-fallback.md" skill_kind="workflow">>
<<include path="_shared/fragments/workflow-activation.md" config_path="{project-root}/_bmad/bmm/config.yaml" skill_kind="workflow">>

## Evidence Contract

Use these sources, skipping an unavailable source and recording that it was unavailable:

1. Sprint status: `<ArtifactPath kind="sprint-status" />`.
2. Epic and story planning records under `{planning_artifacts}`.
3. Build specs and legacy stories under `{implementation_artifacts}`.
4. The complete repository diff for the epic's commit range, including per-story commits when discoverable.
5. Relevant test/CI output, review findings, and session logs when present.

### Stories mode

A completed epic can also be a spec folder: `SPEC.md`, an ordered `stories.yaml`, and one `stories/<id>-*.md` artifact per story. A named spec folder selects this mode even when sprint status exists. A named epic number selects sprint mode. With neither, use sprint mode when `sprint-status.yaml` exists; otherwise search `{planning_artifacts}` and `{implementation_artifacts}` for spec folders. If more than one candidate exists, ask which folder to retro; headless mode stops and requires an explicit folder.

In stories mode, `stories.yaml` list order is authoritative. Resolve each entry to exactly one `stories/<id>-*.md` file and read its frontmatter status. `pending_stories` is every id whose status is not `done`; do not create, read, or update `sprint-status.yaml`. Use each completed story's `baseline_revision` (deprecated) or `baseline_commit` to gather per-story diff evidence. The end is the next story's baseline; for the last story, derive it from history and mark it inferred rather than recorded.

For each source, record its path or command, the scope inspected, and the evidence it contributed. Keep source references beside each finding rather than collecting unsupported conclusions at the end.

## Execution

### 1. Resolve the Epic

1. If the request names a spec folder, use stories mode and that folder. If it names an epic, use sprint mode and that epic.
2. Otherwise read sprint status and select the highest epic with completed stories and no completed retrospective; only when sprint status is unavailable, discover candidate spec folders as described above. In interactive mode ask the user to confirm.
3. In sprint mode, gather all story keys for the epic and classify them as done, review, in-progress, backlog, or missing. In stories mode, use `stories.yaml` order and each story artifact's frontmatter status.
4. If any story is not done, the machine verdict is `rejected`. In interactive mode, explain the incomplete inventory and ask whether to stop or produce a partial report. In headless mode, continue only to document the rejection and evidence.

### 2. Inventory Evidence

Create `{implementation_artifacts}/epic-{epic_number}-retro-{date}.md` in sprint mode, or `{spec_folder}/RETROSPECTIVE.md` in stories mode, with these initial sections:

```markdown
# Epic {epic_number} Retrospective

## Evidence Inventory

## Story Completion

## Aggregate Findings

## Spec Reconciliation

## Acceptance Verdict

## Action Items
```

For every story, locate its Build spec (`spec-{epic_number}-{story_number}-*.md`) or legacy story record; in stories mode use the resolved `{spec_folder}/stories/<id>-*.md` artifact. Extract acceptance criteria, verification evidence, review outcome, deferred work, and any explicit unresolved risk. For the epic, extract its stated goal and acceptance criteria from the epic record or `SPEC.md`. Record missing artifacts explicitly; never fill them in from memory.

### 3. Examine the Epic as a Whole

Construct the full diff across the epic's story commits. Where commit boundaries are unavailable, use the best supported baseline and state the limitation. Inspect the diff and repository for cross-story effects that isolated story reviews cannot see:

- duplicated helpers or divergent implementations of the same concern;
- architectural or API-contract drift;
- growing files/classes/modules and changed seams between stories;
- tests or deterministic checks weakened, removed, skipped, or no longer observing changed behavior;
- an acceptance criterion that has no implementation or verification evidence.

Use `bmad-review` only on this epic-wide diff and only for applicable lenses. Treat its output as leads: verify each lead against the evidence before including it in the retrospective.

### 4. Reconcile Specs and Acceptance

For each epic acceptance criterion, write one of:

- `met` — cite implementation and verification evidence;
- `not met` — cite the missing or contradictory evidence;
- `uncertain` — cite what was inspected and why it cannot establish the result.

For each Build spec or legacy story that diverges from the delivered code, record the divergence and source. Do not edit a spec during a retrospective. An uncertain interpretation remains an action item for a human, not an automatic reconciliation.

### 5. Determine the Verdict

Set the machine verdict:

- `accepted` when every story is done, every acceptance criterion is met, and no blocking finding remains;
- `accepted-with-open-items` when the epic is complete and criteria are met but evidence-backed non-blocking action items remain;
- `rejected` when a story is incomplete, an acceptance criterion is not met, or evidence establishes a blocking finding.

In interactive mode, present the evidence and proposed verdict. The human may override it, but record the override, reason, and original machine verdict. In headless mode do not override.

### 6. Action Items and Closeout

For every accepted finding, create an owned action item with a stable id (`retro-{epic_number}-{n}`), a precise next step, severity, owner when known, and a source reference. Do not create action items for speculation or rejected review noise.

After interactive approval (or immediately in headless mode), append the action items and verdict to sprint status in sprint mode. In stories mode, finalize `{spec_folder}/RETROSPECTIVE.md` and stop: do not create or edit sprint status, `SPEC.md`, `stories.yaml`, or any story artifact. Mark the epic retrospective complete only when the report was written. Do not mark a rejected epic accepted merely because a report exists.

### 7. Present

Present:

- the epic and evidence inventory inspected;
- story-completion summary;
- acceptance verdict and whether it was human-overridden;
- findings grouped by aggregate defect, spec reconciliation, and verification;
- action item ids and sources;
- missing or unavailable evidence.

Offer optional party-mode discussion over the written findings. Offer `bmad-build` for accepted fix-now action items and `bmad-sprint-planning` when the verdict or action items require replanning.

## On Complete

<<include path="_shared/fragments/on-complete.md">>
