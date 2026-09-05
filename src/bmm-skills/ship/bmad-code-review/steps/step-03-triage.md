---
---

# Step 3: Triage

## RULES

- YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

## INSTRUCTIONS

1. **Normalize** findings from all layers into a unified list where each finding has:
   - `id` -- sequential integer
   - `source` -- the `id` of the layer that produced the finding (e.g., `blind-hunter`), or merged sources joined with `+` (e.g., `blind-hunter+edge-case-hunter`)
   - `title` -- one-line summary
   - `detail` -- full description
   - `location` -- file and line reference (if available)

2. **Render a verdict on each finding before grouping.** Once every layer has reported, verify each claim at its named location independently. Read past the diff hunk into callers, guards, and validation far enough to determine whether its claimed consequence actually occurs. A neighboring finding's outcome never settles this one.

   A gap finding from the verification-gap layer arrives pre-verified — that layer's evidence rules made it read the tests and run the searches it cites, and triage trusts the claim as filed. Skip verification, render the verdict from the filed evidence, and weigh its filed `disposition` when routing. That layer's `gap_shape: "other"` findings are verified like everything else.

3. **Assign severity** from that verified consequence for the artifact's main consumer (software user, document reader, etc).
   Disregard any severity assigned by a reviewing subagent. Review subagents operate under by-design information asymmetry and do not have enough context to set final severity for this workflow.
   - `low` -- none or cosmetic
   - `medium` -- tolerable
   - `high` -- intolerable

4. **Keep or dismiss.** Keep a finding only when verification confirms its claimed consequence. Dismiss noise, refuted claims, and claims that cannot be substantiated; the reason must dispose of that finding's own claim. Record every dismissal and its reason for the summary — never drop a finding silently.

5. **Group survivors by shared root cause.** Merge only findings with the same underlying defect, not merely the same location or fix. Preserve each member's verified consequence and the highest severity in the group.

6. **Route** each surviving group into exactly one triage bucket:
   - **decision_needed** -- There is an ambiguous choice that requires human input. The code cannot be correctly patched without knowing the user's intent. Only possible if `{review_mode}` = `"full"`.
   - **patch** -- Code issue that is fixable without human input. The correct fix is unambiguous.
   - **defer** -- Pre-existing issue not caused by the current change. Real but not actionable now.
   - **dismiss** -- Noise, false positive, or handled elsewhere.

   If `{review_mode}` = `"no-spec"` and a finding would otherwise be `decision_needed`, reclassify it as `patch` (if the fix is unambiguous) or `defer` (if not).

7. **Record** every dismissed finding and its reason in the summary; do not include it in the surviving groups.

8. If `{failed_layers}` is non-empty, report which layers failed before announcing results. If zero findings remain after dropping dismissed AND `{failed_layers}` is non-empty, warn the user that the review may be incomplete rather than announcing a clean review.

9. If zero findings remain after triage (all rejected or none raised): state "✅ Clean review — all layers passed." (Step 3 already warned if any review layers failed via `{failed_layers}`.)

## NEXT

Read fully and follow `./step-04-present.md`
