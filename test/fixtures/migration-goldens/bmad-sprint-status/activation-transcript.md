# Activation Transcript — bmad-sprint-status (Story 10.13)

## Summary

**Signed-off deviations: 3 (D1, D2, D4)**

D3 (greeting single-brace) does not apply — original Step 5 already used `{user_name}`.

## Deviation Table

| Deviation | Source line | Compiled line | Verdict |
|-----------|-------------|---------------|---------|
| D1: Conventions example dropped | `- Bare paths (e.g. \`checklist.md\`) resolve from the skill root.` | `- Bare paths resolve from the skill root.` | Signed off — conventions.md fragment omits per-skill examples by design |
| D2: Config keys expanded | Step 4 lists 5 items + 1 behavioral directive | Step 4 lists 8 keys + 4 behavioral directives (canonical workflow-activation.md config-load block) | Signed off — canonical superset; additive, non-breaking |
| D4: Handlebars normalization (48×) | `{{mode}}`, `{{#each invalid_entries}}`, `{{/each}}`, `{{key}}`, `{{status}}`, `{{@index}}`, `{{count_backlog}}`, `{{#if risks}}`, `{{this}}`, etc. throughout Execution block | `{mode}`, `{#each invalid_entries}`, `{/each}`, `{key}`, `{status}`, `{@index}`, `{count_backlog}`, `{#if risks}`, `{this}`, etc. | Signed off — compile engine rejects `{{...}}` as UNKNOWN_DIRECTIVE; single-brace `{var}` is BMAD runtime syntax; LLM interprets identically at runtime. Established Epic 10 pattern (Story 10.1). |

## Additional Notes

**Char-set:** unicode-passthrough (18 non-ASCII codepoints).

**Compiled golden:** `test/fixtures/migration-goldens/bmad-sprint-status/SKILL.md` — 303 lines, SHA `92567e2c`, LF-only.

**Audit note:** Transcript authored retroactively (Story 10.13 committed `7100a874`). Deviation data sourced from story spec Dev Note §3. — bc consolidated-audit 2026-05-25.
