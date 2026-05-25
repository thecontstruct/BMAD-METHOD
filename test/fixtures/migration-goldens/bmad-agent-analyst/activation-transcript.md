# Activation Transcript — bmad-agent-analyst (Story 10.19)

## Summary

**Signed-off deviations: 1 (D1 only)**

D2 (config-key canonicalization), D3 (greeting single-brace), and D4 (Handlebars normalization) do not apply to this skill.

## Deviation Table

| Deviation | Source line | Compiled line | Verdict |
|-----------|-------------|---------------|---------|
| D1: Conventions example dropped | `- Bare paths (e.g. \`references/guide.md\`) resolve from the skill root.` | `- Bare paths resolve from the skill root.` | Signed off — conventions.md fragment omits the example by design (consistent with all other migrated skills) |

## Additional Notes

**customize.toml schema change (compile-time constraint):**
The source `customize.toml` was restructured from TOML array-of-tables (`[[agent.menu]]`) and plain string array (`principles = [...]`) to compiler-compatible format (`[agent.menu.CODE]` sub-tables and scalar `principles`). This was required because `VariableScope.build()` rejects non-empty, non-`file:`-prefixed TOML arrays — a constraint not anticipated in the original spec (which stated "customize.toml is runtime-referenced only"). Runtime behavior is preserved: `resolve_customization.py` outputs the same structured data; the LLM reads `{agent.principles}` and `{agent.menu}` as runtime references. This change applies to the source SKILL.md only and does not affect compiled output byte-equivalence.

**Template no-trailing-newline:**
The template file (`bmad-agent-analyst.template.md`) ends without a trailing newline (`>>`), which prevents the include-directive-line's `\n` from adding a spurious blank line after the fragment content. This is an artifact of the template mechanics: each `<<include...>>\n` line contributes a Text `\n` node after expansion. Ending the template file at `>>` ensures the compiled SKILL.md ends exactly where `agent-activation.md`'s trailing `\n` ends — matching the original source.
