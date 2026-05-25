# Activation Transcript — bmad-sprint-planning (Story 10.14)

## Summary

**Signed-off deviations: 3 (D1, D2, D4)**

D3 (greeting single-brace) does not apply — original Step 5 already used `{user_name}`.

## Deviation Table

| Deviation | Source line | Compiled line | Verdict |
|-----------|-------------|---------------|---------|
| D1: Conventions example dropped | `- Bare paths (e.g. \`checklist.md\`) resolve from the skill root.` | `- Bare paths resolve from the skill root.` | Signed off — conventions.md fragment omits per-skill examples by design |
| D2: Config keys expanded | Step 4 lists 5 keys + 2 behavioral directives | Step 4 lists 8 keys + 4 behavioral directives (canonical workflow-activation.md config-load block) | Signed off — canonical superset; additive, non-breaking |
| D4: Handlebars normalization (8×) | `{{epic_count}}`, `{{story_count}}`, `{{in_progress_count}}`, `{{done_count}}` (×2 each) | `{epic_count}`, `{story_count}`, `{in_progress_count}`, `{done_count}` | Signed off — BMAD runtime syntax; LLM interprets identically. Established Epic 10 pattern. |

## Additional Notes

**Char-set:** unicode-passthrough (24 non-ASCII codepoints).

**Compiled golden:** `test/fixtures/migration-goldens/bmad-sprint-planning/SKILL.md` — 304 lines, SHA `7a5f1a58`, LF-only.

**Audit note:** Transcript authored retroactively (Story 10.14 committed `b087fd73`). Deviation data sourced from story spec Dev Note §3. — bc consolidated-audit 2026-05-25.
