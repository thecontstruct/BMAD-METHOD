# Activation Transcript — bmad-document-project (Story 10.37)

## Classification

- **Class:** migration-candidate-multi-file
- **Module:** bmm
- **Bodies equal:** True
- **Exception class:** EXCEPTION-1 (artifacts: frontmatter)

## Fragment Analysis

### Step 1: conventions.md

Original Conventions section uses `(e.g. \`instructions.md\`)` as bare-path example (skill-specific). Fragment uses different generic example. **Result: MISMATCH → verbatim**

### Step 2: resolver-fallback.md (skill_kind="workflow")

Original Step 1 On Activation block matches the resolver-fallback fragment exactly (includes the full TOML fallback instructions with 3-file merge description).
**Result: MATCH → `<<include path="_shared/fragments/resolver-fallback.md" skill_kind="workflow">>`**

### Step 3: persistent-facts.md

Original Step 3 "Load Persistent Facts" block matches the persistent-facts fragment exactly.
**Result: MATCH → `<<include path="_shared/fragments/persistent-facts.md">>`**

### Step 4: config-load.md

Original Step 4 has skill-specific config items:
- `user_name`, `communication_language`, `document_output_language`
- `planning_artifacts`, `project_knowledge`

Fragment config-load.md is generic. **Result: MISMATCH → verbatim**

### Step 5: Greet — unique variant

Original Step 5: `Greet \`{user_name}\` (if you have not already), speaking in \`{communication_language}\`.`

This differs from all other skills which use `Greet \`{user_name}\`, speaking in \`{communication_language}\`.` (no "(if you have not already)" clause). **Verbatim (no fragment).**

## Template Structure

Artifacts frontmatter (12 entries):
- `checklist.md` (scaffold-verbatim)
- `documentation-requirements.csv` (scaffold-verbatim)
- `instructions.md` (scaffold-verbatim)
- `templates/deep-dive-template.md` (scaffold-verbatim)
- `templates/index-template.md` (scaffold-verbatim)
- `templates/project-overview-template.md` (scaffold-verbatim)
- `templates/project-scan-report-schema.json` (scaffold-verbatim)
- `templates/source-tree-template.md` (scaffold-verbatim)
- `workflows/deep-dive-instructions.md` (scaffold-verbatim)
- `workflows/deep-dive-workflow.md` (scaffold-verbatim)
- `workflows/full-scan-instructions.md` (scaffold-verbatim)
- `workflows/full-scan-workflow.md` (scaffold-verbatim)

Note: `customize.toml` is present in the skill directory but is NOT an artifact to emit (it is the customization config, not a scaffolded artifact).

Includes used:
- `<<include path="_shared/fragments/resolver-fallback.md" skill_kind="workflow">>`
- `<<include path="_shared/fragments/persistent-facts.md">>`

## EXCEPTION-1 Note

Original SKILL.md had `name:` + `description:` frontmatter only. Compiled SKILL.md has `artifacts:` block added. Bodies equal: True — deviation is frontmatter-only, non-breaking (LLM reads body only).

## Deviations

- **D-EXCEPTION-1:** `artifacts:` frontmatter key present in compiled SKILL.md (same class as 10.27a/10.28/10.30/10.33/10.34). Non-breaking. Signed-off.

## Char-set

ASCII-only

## Golden SHA

SHA-256[:16]: `1fd5f86a6dad0612`  
Size: 3835 bytes
