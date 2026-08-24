---
deferred_work_file: '{implementation_artifacts}/deferred-work.md'
---

# Step One-Shot: Implement, Review, Present

## RULES

- YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`
- NEVER auto-push.
- All review subagents must run at the same model capability as the current session.
- Run subagents synchronously: launch them together as blocking calls awaited in this turn — never backgrounded or detached, never ending the turn to await results.

## INSTRUCTIONS

### Implement

Follow `./sync-sprint-status.md` with `{target_status}` = `in-progress`.

Implement the clarified intent directly.

### Review

The review layers for this route are `{workflow.oneshot_review_layers}`, resolved during activation.

Announce skipped layers first, then launch every active layer before handling any layer's result. Try running all active layers simultaneously. Skip every layer whose `instruction` is empty or missing, and every layer whose `when` condition (if present) does not hold. If no layers remain, HALT with status `blocked` and blocking condition `no active review layers`.

<<include path="_shared/fragments/sub-agent-activation.template.md" spawn_action="Launch each active layer's reviewer as a parallel subagent without conversation context." fallback_action="generate one review prompt file per layer in `{implementation_artifacts}` and HALT. Ask the human to run each in a separate session and paste back the findings.">>

Execute all remaining layers following each layer's `instruction` verbatim after substituting any runtime placeholders. Never handle a layer's result until every active layer has launched.

### Classify

Deduplicate all review findings, then route each finding in this order:

- **patch** — Patch every finding caused or exposed by this change that shows a defect that actually occurs, missing coverage for a specific case, or a broken gate or convention — not a state nothing reaches — and whose smallest fix is trivial, adds no public surface, and guards no state the finding did not demonstrate. Apply that smallest fix immediately.
- **HALT** — HALT on every finding caused or exposed by this change that shows the same evidence but whose smallest fix fails any of those conditions. Present it to the human for decision before proceeding.
- **defer** — Defer every other real finding, including pre-existing issues and improvement ideas. Append one new entry to `{deferred_work_file}` using this format. Do not modify existing entries or look for duplicates.
  ```markdown
  - source_spec: `{spec_file}`
    summary: <one sentence>
    evidence: <why this is real>
  ```
- **reject** — Reject only noise. Drop silently.

### Generate Spec Trace

Set `{title}` = a concise title derived from the clarified intent.

Write `{spec_file}` using `./spec-template.md`. Fill only these sections — delete all others:

1. **Frontmatter** — set `title: '{title}'`, `type`, `created`, `status: 'done'`. Add `route: 'one-shot'`.
2. **Title and Intent** — `# {title}` heading and `## Intent` with **Problem** and **Approach** lines. Reuse the summary you already generated for the terminal.
3. **Suggested Review Order** — append after Intent. Build using the same convention as `./step-05-present.md` § "Generate Suggested Review Order" (spec-file-relative links, concern-based ordering, ultra-concise framing).

Follow `./sync-sprint-status.md` with `{target_status}` = `review`.

### Commit

If version control is available and the tree is dirty, create a local commit with a conventional message derived from the intent. If VCS is unavailable, skip.

### Present

{workflow.open_spec}

Display a summary in conversation output, including:

- The commit hash (if one was created).
- List of files changed with one-line descriptions. Any file paths shown in conversation/terminal output must use CWD-relative format (no leading `/`) with `:line` notation (e.g., `src/path/file.ts:42`) for terminal clickability — this differs from spec-file links which use spec-file-relative paths.
- Review findings breakdown: patches applied, items deferred, items rejected. If all findings were rejected, say so.

Offer to push and/or create a pull request.

HALT and wait for human input.

Workflow complete.

## On Complete

<<include path="_shared/fragments/on-complete.md">>
