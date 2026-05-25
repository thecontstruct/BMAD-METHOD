# Activation Transcript — bmad-agent-architect (Story 10.20)

## Summary

**Signed-off deviations: 1 (D1)**

D2 does not apply — agent skills use Step 5 (inline agent config format in agent-activation.md, not canonical config-load.md workflow format).
D3 does not apply — original Step 6 already used `{user_name}` (via agent-activation.md).
D4 does not apply — 0 `{{...}}` instances in source.

## Deviation Table

| Deviation | Source line | Compiled line | Verdict |
|-----------|-------------|---------------|---------|
| D1: Conventions example dropped | `- Bare paths (e.g. \`references/guide.md\`) resolve from the skill root.` | `- Bare paths resolve from the skill root.` | Signed off — conventions.md fragment omits per-skill examples by design |

## Additional Notes

**Char-set:** unicode-passthrough (10 non-ASCII codepoints — 8× U+2014 em-dash, 2× U+2192 rightward-arrow).

**Template:** 19 lines (no trailing newline on last include line, consistent with bmad-agent-analyst template). Compiled golden: 74 lines, LF-only.

**TOML schema changes (compiler compatibility — same pattern as Story 10.19):**
- `principles`: converted from TOML array to scalar string (join). Affects all 5 remaining Batch 3 agent skills (10.20–10.24); each story applies the same fix to its own customize.toml.
- `agent.menu`: converted from `[[agent.menu]]` array-of-tables to `[agent.menu.CODE]` subtable format. Same compatibility requirement.

**Commit note:** Story 10.20 committed independently (not bundled). customize.toml included in commit (TOML schema change required for compilation).

**Audit note:** Transcript authored at dev time. — bc 2026-05-25.
