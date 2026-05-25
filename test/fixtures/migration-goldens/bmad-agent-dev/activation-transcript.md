# Activation Transcript — bmad-agent-dev (Story 10.21)

## Summary
**Signed-off deviations: 1 (D1)**
D2 does not apply — agent skills use Step 5 (inline agent config format in agent-activation.md).
D3 does not apply — original Step 6 already used `{user_name}`.
D4 does not apply — 0 `{{...}}` instances in source.

## Deviation Table
| Deviation | Source line | Compiled line | Verdict |
|-----------|-------------|---------------|---------|
| D1: Conventions example dropped | `- Bare paths (e.g. \`references/guide.md\`) resolve from the skill root.` | `- Bare paths resolve from the skill root.` | Signed off — conventions.md fragment omits per-skill examples by design |

## Additional Notes
**Char-set:** unicode-passthrough (11 non-ASCII codepoints — 9× U+2014 em-dash, 2× U+2192 rightward-arrow).
**Template:** 19 lines (no trailing newline on last include line, consistent with bmad-agent-analyst template). Compiled golden: 74 lines, LF-only.
**TOML schema changes (compiler compatibility — same pattern as Stories 10.19–10.20):**
- `principles`: converted from TOML array to scalar string (join). Applied to this story's customize.toml.
- `agent.menu`: converted from `[[agent.menu]]` array-of-tables to `[agent.menu.CODE]` subtable format (8 items: DS, QD, QA, CR, SP, CS, ER, IN). Same compatibility requirement.
**Lockfile:** 3 fragments (conventions.md, resolver-fallback.md, agent-activation.md) confirmed from base layer.
**Override survey:** No overrides found in src/_bmad/custom/.
**Engine-frozen:** ZERO changes to src/scripts/bmad_compile/, compile.py, upgrade.py.
**validate-compile.js:** 19/19 PASS.
