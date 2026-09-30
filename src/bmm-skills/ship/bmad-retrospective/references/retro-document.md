# Ticket-tree Retrospective Document

The only ticket-tree write is `{epic_folder}/{epic_folder_basename}-retrospective.md` — for example, `epic-checkout/epic-checkout-retrospective.md`. It is the working artifact and may be resumed by re-reading it and reconciling it against current evidence.

Use frontmatter:

```yaml
---
epic: {epic_folder_basename}
verdict: accepted | accepted-with-open-items | rejected
---
```

Do not write `type` or `ticket` frontmatter fields: the ticket runtime can otherwise mistake the retrospective for a ticket or plan.

Include: Epic Summary; Assumptions (headless only); Evidence Inventory; Ticket Completion; Aggregate Findings; Spec and Requirement Reconciliation; Acceptance Verdict; Action Items; and Missing Evidence. Each action item has a stable `retro-{epic_slug}-{n}` id, owner when known, severity, next action, and source reference.

Finalize the document and stop. Do not edit an epic file, ticket file, plan, story file, tracker, or sprint-status file. Do not run `tickets.py mark`; ticketing closes an epic only after the user confirms its closure check.
