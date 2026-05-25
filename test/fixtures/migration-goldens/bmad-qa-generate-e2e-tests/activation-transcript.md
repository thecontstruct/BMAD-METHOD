# Activation Transcript — bmad-qa-generate-e2e-tests (Story 10.18)

## Summary

**Signed-off deviations: 2 (D1, D2)**

D3 (greeting single-brace) does not apply — original Step 5 already used `{user_name}`.
D4 (Handlebars normalization) does not apply — 0 `{{...}}` instances in source.

## Deviation Table

| Deviation | Source line | Compiled line | Verdict |
|-----------|-------------|---------------|---------|
| D1: Conventions example dropped | `- Bare paths (e.g. \`checklist.md\`) resolve from the skill root.` | `- Bare paths resolve from the skill root.` | Signed off — conventions.md fragment omits per-skill examples by design |
| D2: Config keys expanded | Step 4 lists 4 keys + 1 behavioral directive | Step 4 lists 8 keys + 4 behavioral directives (canonical workflow-activation.md config-load block) | Signed off — canonical superset; additive, non-breaking |

## Additional Notes

**Char-set:** unicode-passthrough.

**Template:** 137 lines (176 → 137 after fragment extraction). Compiled golden: SHA `5b0032aa`, LF-only.

**Commit note:** Stories 10.16, 10.17, 10.18 were committed atomically in `b4c57553`. Per-story SHA attribution is shared.

**Audit note:** Transcript authored retroactively (bundled commit `b4c57553`). Deviation data sourced from story spec Dev Note §3. — bc consolidated-audit 2026-05-25.
