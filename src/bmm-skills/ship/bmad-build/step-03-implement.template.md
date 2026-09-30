---
---

# Step 3: Implement

## RULES

- YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`
- No push. No remote ops.
- Sequential execution only.
- Content inside `<frozen-after-approval>` in `{plan_file}` is read-only. Do not modify.

## PRECONDITION

Verify `{plan_file}` resolves to a non-empty path and the file exists on disk. If empty or missing, HALT and ask the human to provide the plan file path before proceeding.

## INSTRUCTIONS

### Baseline

Capture `baseline_commit` (current HEAD, or `NO_VCS` if version control is unavailable) into `{plan_file}` frontmatter before making any changes. If the frontmatter already contains `baseline_commit` (resumed run), preserve the existing value — never overwrite it.

### Implement

Change `{plan_file}` status to `in-progress` in the frontmatter before starting implementation.

When `{plan_file}` came from the ticket tree, its frontmatter is the only Build lifecycle write; do not update sprint status or a ticket file.

If `{plan_file}` has a non-empty `context:` list in its frontmatter, load those files before implementation begins. When handing to a subagent, include them in the subagent prompt so it has access to the referenced context.

<<include path="_shared/fragments/sub-agent-activation.template.md" spawn_action="Hand `{plan_file}` to a subagent/task and let it implement. If the platform allows, keep the subagent available for re-engagement after it returns — step-04 may send it review fixes." fallback_action="implement directly.">>

**Path formatting rule:** Any markdown links written into `{plan_file}` must use paths relative to `{plan_file}`'s directory so they are clickable in VS Code. Any file paths displayed in terminal/conversation output must use CWD-relative format with `:line` notation (e.g., `src/path/file.ts:42`) for terminal clickability. No leading `/` in either case.

### Tasks & Acceptance Verification

Before leaving this step, verify every task in the `## Tasks & Acceptance` section of `{plan_file}` is complete and every acceptance criterion is satisfied. Mark each finished task `[x]`. If any task is not done or any acceptance criterion is not satisfied, finish the missing work before proceeding.

### Matrix Test Audit

If `{plan_file}`'s `<frozen-after-approval>` block contains an I/O & Edge-Case Matrix, verify every matrix row is covered by at least one test that verifies its expected behavior, and that each covering test ran and passed in the verification output. A covering test that exists but did not run — unregistered, filtered out, skipped, or disabled — counts as missing. If a test disagrees with the matrix, never edit the expectation to match the code: fix the code, or if the matrix row itself is ambiguous, HALT and ask the human. Fix any other audit failure before proceeding.

## NEXT

Read fully and follow `./step-04-review.md`
