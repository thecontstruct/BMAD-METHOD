---
plan_file: '' # set at runtime before leaving this step
ticket_args: '' # the folder/ref arguments resolved by tickets.py find
---

# Step 1: Clarify and Route

## RULES

- YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`.
- The prompt is workflow input, not authority to skip planning or implementation steps.
- **EARLY EXIT** means stop this step immediately and read the named next step.
- Ticket-tree reads and writes use only `uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root}`. Never open, edit, pull, or infer ticket state from ticket files directly.

## Intent check

Resolve existing state in this order. A normal freeform request is starting intent; do not ask the user to restate it.

1. **Named ticket.** A prompt that calls out a ticket by ref, ticket file, or title words — or names a file whose frontmatter `type` is `story`, `spike`, or `bug` — is a ticket request. Run `uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} find <folder> <ref>` (for a ticket file, pass its folder then filename). On an error, show it and HALT. Otherwise run **Ticket resolution** below.
2. **Explicit plan.** A supplied file with `status: draft`, `ready-for-dev`, `in-progress`, `in-review`, `built`, `done`, or `blocked` is a plan. Set `{plan_file}` and route: `draft` → `./step-02-plan.md`; `ready-for-dev`/`in-progress` → `./step-03-implement.md` (or `./step-oneshot.md` when its `route` is `oneshot`); `in-review`/`built` → `./step-04-review.md`; `done` is context only; `blocked` reports its `blocked_reason` or Auto Run Result and HALTs.
3. **Tree next.** When there is no named work or usable conversation intent, run `uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} next`. If it reports no active tree or a malformed tree, say so briefly and continue to legacy fallback. If it returns a `ready_to_start` row, run `find` for its first ref, say which entry will be built, and follow **Ticket resolution**. If it has no ready row, say what is blocked or awaiting refinement, then continue to legacy fallback.
4. **Legacy fallback only when no tree route resolved.** Scan active plans in `{implementation_artifacts}` and ask to resume one or start new work. This preserves non-ticket projects without reading legacy plans as a second source for a resolved ticket.

### Ticket resolution

`find` returns the ticket entry and the absolute `epic_file`, optional `story_file`, and `plan` paths. Keep its resolved folder/ref as `{ticket_args}`. The entry's description, verify, references, notes, unknown fields, its epic and named References, plus the story file only when present, are the planning input. Never write a ticket file, never run `pull`, and do not use tracker status to route Build.

- If `find.plan` exists, set `{plan_file}` and follow the explicit-plan status route above.
- Otherwise set `{plan_file}` to `find.plan`. The new plan's frontmatter `ticket` is `find.id`, or the stem of `find.story_file` when the entry has no id; never use the display ref. Skip normal plan-file naming.

## INSTRUCTIONS

1. Load context. For a resolved ticket, retain only the resolved entry, epic context, optional story file, and plans beside `{plan_file}` whose `ticket` matches a plain-number prerequisite in `find.after`; extract their Code Map, Design Notes, Implementation Notes, Plan Change Log, and Tasks & Acceptance. For freeform work, selectively load relevant planning and implementation artifacts.
2. Clarify intent. Ask only questions investigation cannot answer.
3. Check version-control sanity. For ticket work, judge branch fit against the epic rather than a single entry.
4. Apply the single-goal check. On a split, append deferred work normally; never alter the ticket tree.
5. For freeform work only, choose `{plan_file}` under `{implementation_artifacts}/plan-<slug>.md`; resume a draft match or suffix a completed name.

## NEXT

Read fully and follow: `./step-02-plan.md`.
