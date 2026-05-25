# Activation Transcript — bmad-checkpoint-preview (Story 10.12)

## Summary

**Signed-off deviations: 3 (D1, D2, D3)**

D4 (Handlebars normalization) does not apply to this skill (0 `{{...}}` instances in source).

## Deviation Table

| Deviation | Source line | Compiled line | Verdict |
|-----------|-------------|---------------|---------|
| D1: Conventions example dropped | `- Bare paths (e.g. \`step-01-orientation.md\`) resolve from the skill root.` | `- Bare paths resolve from the skill root.` | Signed off — conventions.md fragment omits per-skill examples by design (consistent with all migrated skills) |
| D2: Config keys expanded | Step 4 lists 4 keys (`implementation_artifacts`, `planning_artifacts`, `communication_language`, `document_output_language`) | Step 4 lists 8 keys + 4 behavioral directives (canonical workflow-activation.md config-load block) | Signed off — canonical config-load.md is a superset of per-skill subsets; additional keys are additive and non-breaking |
| D3: Greeting adds user_name | `Greet the user, speaking in \`{communication_language}\`.` | `Greet \`{user_name}\`, speaking in \`{communication_language}\`.` | Signed off — canonical workflow-activation.md personalizes the greeting; `{user_name}` is resolved at runtime from config |

## Additional Notes

**Char-set:** unicode-passthrough (10 non-ASCII codepoints: em-dashes and arrows in workflow step descriptions).

**Compiled golden:** `test/fixtures/migration-goldens/bmad-checkpoint-preview/SKILL.md` — 75 lines, SHA `3d4edc9a`, LF-only.

**Audit note:** Transcript authored retroactively (Story 10.12 committed `a2552acb`). Deviation data sourced from story spec Dev Note §3. Methodology consistent with Story 10.19 pattern. — bc consolidated-audit 2026-05-25.
