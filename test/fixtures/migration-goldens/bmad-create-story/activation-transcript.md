# Activation Transcript — bmad-create-story (Story 10.16)

## Summary

**Signed-off deviations: 3 (D1, D2, D4)**

D3 (greeting single-brace) does not apply — original Step 5 already used `{user_name}`.

## Deviation Table

| Deviation | Source line | Compiled line | Verdict |
|-----------|-------------|---------------|---------|
| D1: Conventions example dropped | `- Bare paths (e.g. \`discover-inputs.md\`) resolve from the skill root.` | `- Bare paths resolve from the skill root.` | Signed off — conventions.md fragment omits per-skill examples by design |
| D2: Config keys expanded | Step 4 lists 5 keys + 0 behavioral directives | Step 4 lists 8 keys + 4 behavioral directives (canonical workflow-activation.md config-load block) | Signed off — canonical superset; additive, non-breaking |
| D4: Handlebars normalization (34×) | `{{story_count}}`, `{{epic_title}}`, `{{#if ...}}`, `{{/if}}`, etc. throughout workflow instructions | `{story_count}`, `{epic_title}`, `{#if ...}`, `{/if}`, etc. | Signed off — BMAD runtime syntax; LLM interprets identically. Established Epic 10 pattern. |

## Additional Notes

**Char-set:** unicode-passthrough.

**Template:** 390 lines (429 → 390 after D4 normalization and fragment extraction). Compiled golden: SHA `d349169e`, LF-only.

**Commit note:** Stories 10.16, 10.17, 10.18 were committed atomically in `b4c57553`. Per-story SHA attribution is shared.

**Audit note:** Transcript authored retroactively (bundled commit `b4c57553`). Deviation data sourced from story spec Dev Note §3. — bc consolidated-audit 2026-05-25.
