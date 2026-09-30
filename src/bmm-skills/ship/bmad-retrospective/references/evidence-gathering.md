# Ticket-tree Evidence Gathering

Use this reference only after ticket-tree resolution selected an epic folder. Read the evidence through `tickets.py`; do not infer state from ticket files.

1. Run `uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} status <epic_folder>`. Its `tickets` rows, in returned order, are the epic inventory. For each row, run `uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} find <epic_folder> <ref>` and record the entry, `epic_file`, optional `story_file`, and `plan` path.
2. Record every row's `<ref>`, title, `status`, and `state`. A ticket is finished only when `status` is `built` or `state` is `done` or `dropped`; every other row belongs in `{pending_tickets}`. List `built` rows separately: their build completed, but they have not been called done.
3. Read the epic file and the parent initiative requirements it covers. Read each ticket entry's description, verify, covers, references, and notes. Read each plan when it exists: its frontmatter plus Code Review, Review Triage Log, Verification, Plan Change Log, and implementation notes. Record absent files as unavailable evidence.
4. For each plan with a usable `baseline_revision` (not missing and not `NO_VCS`), derive its diff from that baseline to the next plan baseline in history; the last range ends at `HEAD` and is marked inferred. When ranges overlap, count a commit or file change once in aggregate findings while retaining every ticket range as provenance. A plan with no usable baseline has no commit-range evidence; record that limitation.
5. Write the inventory, commands, scope, and missing evidence into the retrospective before analysis. A later finding must cite one of these sources.
