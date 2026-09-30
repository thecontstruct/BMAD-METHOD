# Ticket-tree impact and handoff

Use this reference only after the shared ticket runtime resolves an active tree. It is a read-only impact analysis route; `bmad-correct-course` writes its Sprint Change Proposal but does not mutate ticket-tree records.

## Resolve affected work

1. Run `uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} status`. Record the active initiative, the returned rows, their `status` and `state`, and any `blocks` or prerequisite information relevant to the change.
2. Match the user's named ticket reference, epic folder, slug, or described scope against those rows. If more than one row fits, show the candidates and ask the user which work is affected. Do not infer a ticket identity from a similar title alone.
3. Resolve every selected row through `uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} find <ref>`. Read the returned entry, `epic_file`, `story_file` when present, and `plan` when it exists. Include prerequisites and dependents in the impact analysis.
4. Use the ticket row's state as evidence, not as permission to rewrite history. Planned or backlog work can be rescoped, resequenced, split, added, or dropped. For `in-progress`, blocked, built, done, or dropped work, preserve the record and propose follow-on work unless the user explicitly asks the ticketing workflow to change its status or record.

## Write the proposal

For every ticket-tree proposal, record the ticket ref, epic folder, current state, source evidence, proposed operation, before/after effect, prerequisites or dependents affected, and the reason. Use only these operations:

- add a ticket or epic;
- rescope a planned ticket;
- resequence tickets;
- update prerequisites;
- split a planned ticket;
- drop a ticket with its reason and dependent remediation.

Keep artifact edits distinct from ticket-tree operations. A PRD, architecture, UX, or spec change may justify a ticket operation, but neither change is applied by Correct Course.

## Handoff

After the user approves the Sprint Change Proposal, send the ticket operations list to `bmad-preview-ticketing`. That workflow validates and applies the tree changes, including any user-approved status action. Never run `tickets.py pull` or `tickets.py mark`, edit `tickets.toml`, edit ticket files, or edit plans from Correct Course. The ticket runtime is shared at `{project-root}/_bmad/method/scripts/tickets.py`; never use a copy inside the ticketing skill directory.

## Legacy fallback

Use the legacy epics-and-stories route only when `tickets.py status` cannot resolve an active tree. Do not load or update sprint status as a second source after a ticket tree resolves.
