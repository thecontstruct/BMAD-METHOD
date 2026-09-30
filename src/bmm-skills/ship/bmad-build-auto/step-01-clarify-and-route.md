---
plan_file: '' # set at runtime once a route resolves it
ticket_args: '' # the folder/ref arguments resolved by tickets.py find
followup_pass: '' # set for a built or done plan re-dispatched for review
---

# Step 1: Clarify and Route

## RULES

- Treat the invocation as workflow input, not a substitute for planning.
- **EARLY EXIT** means stop this step and read the named next step.
- Ticket-tree reads and writes use only `uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root}`. Never read or mutate ticket files directly, and never run `pull`.

## Intent check

A prompt explicitly naming a ticket (ref, ticket file, or title) resolves through `uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} find <folder> <ref>`. On failure HALT `blocked` with `ticket not resolved`. Save the resolved folder/ref as `{ticket_args}`, then follow **Ticket resolution**.

An explicit existing plan routes by frontmatter status: `draft` → `./step-02-plan.md`; `ready-for-dev`/`in-progress` → `./step-03-implement.md`; `in-review` → `./step-04-review.md`; `blocked` HALTs without overwriting its reason; `built`/`done` reset `review_loop_iteration`, set `{followup_pass}` true, and route to `./step-04-review.md`.

Without a named ticket, the invocation is freeform intent. If it is unclear, HALT `blocked` with `unclear intent`. Never advance to another ticket in this run.

### Ticket resolution

Use find's description, verify, references, notes, unknown fields, epic file and named References, and optional story file as the complete ticket input. Do not use tracker status for build routing.

- If `find.plan` exists, treat it as an explicit plan and route by status above.
- Otherwise set `{plan_file}` to `find.plan`; its `ticket` frontmatter must be `find.id`, or the stem of `find.story_file` when no id exists — never its ref. Continue to instructions and skip freeform file naming.

## INSTRUCTIONS

1. For ticket work, retain the resolved entry and its files as context. For continuity, read sibling plans whose `ticket` matches a plain-number item from `find.after`; carry forward Code Map, Design Notes, Implementation Notes, Plan Change Log, and Tasks & Acceptance. For freeform work, selectively load planning and implementation artifacts.
2. Resolve intent from evidence; unresolved material choices HALT `blocked` as `intent gap`.
3. Require a clean working tree and a fitting branch; ticket branches fit their epic.
4. Carry a `multiple-goals` warning forward rather than splitting.
5. For freeform work only, create `{implementation_artifacts}/plan-<slug>.md`, resuming a draft match or suffixing an existing completed name.

## NEXT

Read fully and follow: `./step-02-plan.md`.
