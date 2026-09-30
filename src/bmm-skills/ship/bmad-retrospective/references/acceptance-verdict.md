# Ticket-tree Acceptance Verdict

Use the ticket inventory as evidence, not as a command to mutate it.

- `pending_tickets` is authoritative for this selected epic: rows from `tickets.py status <epic_folder>` whose `status` is not `built` and whose `state` is neither `done` nor `dropped`.
- Any non-empty `{pending_tickets}` forces the machine verdict to `rejected`. In an interactive run the human can override it, but the report records the unfinished refs, original verdict, decision, and reason. In headless mode it cannot be overridden.
- With no pending tickets, choose `accepted` only when every epic Done-when criterion has implementation and verification evidence and no blocking finding remains. Choose `accepted-with-open-items` when criteria are met but evidence-backed non-blocking action items remain. Choose `rejected` when a criterion is not met or a blocking finding remains.
- If the ticket-tree status check was unavailable, do not infer accepted or rejected from missing rows. Record the unavailable check and weigh only the criteria and findings that were actually inspected.
