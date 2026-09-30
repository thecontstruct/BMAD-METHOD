---
diff_file: '' # set at runtime: absolute path to the staged unified diff
claims_file: '' # set at runtime (path or empty)
plan_file: '' # set at runtime (path or empty; a ticket plan or legacy story/spec)
review_mode: '' # set at runtime: "full" or "no-plan"
ticket_args: '' # set at runtime: resolved ticket folder/ref arguments
story_key: '' # set only by legacy sprint-status routing
---

# Step 1: Gather Context

## RULES

- YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`.
- The prompt that triggered this workflow IS the intent — not a hint.
- Writing `{diff_file}` and `{claims_file}` is the only change this step may make. Otherwise it is read-only.
- Ticket-tree reads use only `uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root}`. Never open, edit, pull, or infer ticket state from ticket files directly.

## INSTRUCTIONS

1. **Find the review target.** The conversation context before this skill was triggered IS your starting point — not a blank slate. Check in this order — stop as soon as the review target is identified:

   **Tier 1 — Explicit argument or recent conversation.**
   Did the user provide a PR, commit SHA, branch, plan or story/spec file, or diff source in this message or the recent conversation?
   - PR reference → resolve to branch/commit via `gh pr view`. If resolution fails, ask for a SHA or branch.
   - Commit or branch → use directly.
   - Plan or story/spec file → set `{plan_file}` to the provided path. If its frontmatter has `baseline_revision` other than `NO_VCS`, use that as the diff baseline. For a legacy story/spec, also accept `baseline_commit`. A file without a usable baseline provides context only; continue the cascade to identify a diff source.
   - Also scan the argument for diff-mode keywords that narrow the scope: staged changes, uncommitted/working-tree changes, branch diff, commit range, or a provided diff/file list. Prefer the most specific match.

   **Tier 2 — Ticket tree.**
   Run `uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} status`. If it exits non-zero, say nothing about ticketing and continue to Tier 3. Otherwise offer every returned `tickets` row whose `state` is `review`, showing its `<ref>` and `<title>`, plus **Choose another target**, then HALT for the user's choice. If there are no review rows, or the user chooses another target, continue.

   For a selected row, run `uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} find <ref>`. On an error, show it and HALT. Set `{ticket_args}` to the resolved folder/ref arguments. `find.plan` is a computed path and may not exist yet (a tracker-backed ticket with no local plan). If it exists, set `{plan_file}` to it and treat that plan as the explicit context source. If it does not exist, leave `{plan_file}` empty and set `{review_mode}` = `"no-plan"` directly — do not ask the user for a plan. Either way, do not scan sprint status or legacy story records for this ticket.

   **Tier 3 — Legacy sprint tracking.**
   Only when no ticket target was resolved, look for a sprint-status file in `{implementation_artifacts}` or `{planning_artifacts}`. If found, scan for stories with status `review` and offer the existing one-or-many selection behavior. Set `{story_key}` only for that legacy selection; use its story context to determine the diff source.

   **Tier 4 — Current git state.**
   If version control is available and HEAD is not on the default branch, confirm whether to review this branch's changes against the default branch. If declined, continue.

   **Tier 5 — Ask.** Go to instruction 2.

   Never ask extra questions beyond this cascade. If a tier identified the target, skip remaining tiers and proceed to instruction 3.

2. HALT. Ask the user: **What do you want to review?** Present: uncommitted changes, staged changes only, branch diff (ask base), commit range, or provided diff/file list.

3. **Stage the selected diff once** in a unique system-temp file and set `{diff_file}` to its absolute path. Review layers receive this path, never the diff text.
   - A usable plan baseline diffs every tracked change from `baseline_revision` (or legacy `baseline_commit`) to `HEAD`, then appends each untracked file with `git diff --no-index /dev/null <path>`. Verify the baseline resolves first. `NO_VCS` is not a baseline: state that and use the selected source.
   - For staged changes run `git diff --cached`; for uncommitted changes run `git diff HEAD`; for a branch diff verify the base then run `git diff <base>...HEAD`; for a commit range verify it then run `git diff <range>`.
   - For a provided diff, validate it is non-empty unified diff text. For a file list, validate paths and include untracked files with `git diff --no-index`.
   - If the source does not resolve, HALT and ask for a valid source. If the staged diff is empty, HALT and say there is nothing to review. Read `{diff_file}` yourself wherever later steps need the diff.

4. **Stage the claims file.** For a plan baseline, branch diff, or commit range, write the covered commit messages verbatim (`git log <baseline>..HEAD` for a plan baseline) to another unique system-temp file and set `{claims_file}`. For other sources use the user or conversation narrative. If there is no narrative, set `{claims_file}` to `''`. Do not analyze or summarize it.

5. **Set the plan context.**
   - If `{review_mode}` is already `"no-plan"` from Tier 2's planless-ticket case, skip this step.
   - If the request explicitly says no plan, without a plan, or no-plan: set `{review_mode}` = `"no-plan"` and clear `{plan_file}`. Do not ask.
   - If `{plan_file}` is set: verify it exists and is readable, then set `{review_mode}` = `"full"`.
   - Otherwise ask the user to provide a plan or legacy story/spec path, or continue without one. Do not infer no-plan mode merely because no path was supplied.

6. If `{review_mode}` is `"full"` and `{plan_file}` frontmatter has a `context` list, load each referenced document and warn about missing docs.

7. If `wc -l {diff_file}` exceeds approximately 3000 lines, warn the user and offer to chunk by file group. If accepted, rebuild `{diff_file}` for the first group and list remaining groups for follow-up runs.

### CHECKPOINT

Present diff stats, `{review_mode}`, and loaded plan/context docs. HALT and wait for user confirmation.

## NEXT

Read fully and follow `./step-02-review.md`
