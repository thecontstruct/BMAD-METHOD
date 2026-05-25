# Activation Transcript — bmad-retrospective (Story 10.15)

## Summary

**Signed-off deviations: 2 (D2, D4)**

D1 (conventions example) does not apply — original conventions block was already canonical (no per-skill example).
D3 (greeting single-brace) does not apply — original Step 5 already used `{user_name}`.

## Deviation Table

| Deviation | Source line | Compiled line | Verdict |
|-----------|-------------|---------------|---------|
| D2: Config keys expanded | Step 4 lists 5 keys + 1 behavioral directive | Step 4 lists 8 keys + 4 behavioral directives (canonical workflow-activation.md config-load block) | Signed off — canonical superset; additive, non-breaking |
| D4: Handlebars normalization (299×) | Extensive `{{var_name}}`, `{{#if ...}}`, `{{/if}}`, `{{#each ...}}`, `{{/each}}`, `{{@index}}`, etc. throughout party-mode dialogue, workflow steps, and facilitation sections | All converted to single-brace `{var_name}`, `{#if ...}`, `{/if}`, `{#each ...}`, `{/each}`, `{@index}`, etc. | Signed off — compile engine rejects `{{...}}` Handlebars syntax; single-brace is BMAD runtime convention; LLM interprets identically. Largest D4 count in Batch 2 cohort (299 instances) due to retrospective's party-mode dialogue format. |

## Additional Notes

**Char-set:** unicode-passthrough (1,159 non-ASCII codepoints — highest in cohort; party-mode dialogue contains extensive emoji and typographic characters).

**Template size:** 1,472 lines (largest in Batch 2). Compiled golden: 1,518 lines.

**D4 count note:** Story 10.15 commit message stated "410×" — the Dev Note §3 figure of 299 instances is used here as the more precise count captured during dev execution.

**Compiled golden:** `test/fixtures/migration-goldens/bmad-retrospective/SKILL.md` — 1,518 lines, SHA `b4210c4d`, LF-only.

**Audit note:** Transcript authored retroactively (Story 10.15 committed `3b85053d`). Deviation data sourced from story spec Dev Note §3. — bc consolidated-audit 2026-05-25.
