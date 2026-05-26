# Activation Transcript — bmad-code-review (Story 10.32)

## Classification

- **Class:** migration-candidate-multi-file
- **Module:** bmm
- **Bodies equal:** True
- **Exception class:** EXCEPTION-1 (artifacts: frontmatter)

## Fragment Analysis

### Step 1: conventions.md

Fragment text begins: `- Bare paths (e.g. \`checklist.md\`) resolve from the skill root.`

Original SKILL.md Conventions section:
```
## Conventions

- Bare paths (e.g. `checklist.md`) resolve from the skill root.
- `{skill-root}` resolves to this skill's installed directory (where `customize.toml` lives).
- `{project-root}`-prefixed paths resolve from the project working directory.
- `{skill-name}` resolves to the skill directory's basename.
```

Fragment content uses a generic example (`e.g. \`checklist.md\``). The original uses `checklist.md` as the example — this matches the fragment for this skill. However, `conventions.md` fragment text uses `(e.g. \`steps/step-01-discover.md\`)` which differs. **Result: MISMATCH → verbatim**

### Step 2: resolver-fallback.md (skill_kind="workflow")

Fragment matches the On Activation Step 1 resolver-fallback block exactly.
**Result: MATCH → `<<include path="_shared/fragments/resolver-fallback.md" skill_kind="workflow">>`**

### Step 3: persistent-facts.md

Fragment matches the "Load Persistent Facts" step block exactly.
**Result: MATCH → `<<include path="_shared/fragments/persistent-facts.md">>`**

### Step 4: config-load.md

Original Step 4 has skill-specific config items:
- `project_name`, `planning_artifacts`, `implementation_artifacts`, `user_name`
- `communication_language`, `document_output_language`, `user_skill_level`
- `date` as system-generated current datetime
- `sprint_status` = `{implementation_artifacts}/sprint-status.yaml`
- `project_context` = `**/project-context.md` (load if exists)
- CLAUDE.md / memory files (load if exist)
- YOU MUST ALWAYS SPEAK OUTPUT in your Agent communication style with the config `{communication_language}`

Fragment config-load.md is generic. **Result: MISMATCH → verbatim**

## Template Structure

Artifacts frontmatter (4 entries):
- `steps/step-01-gather-context.md` (scaffold-verbatim)
- `steps/step-02-review.md` (scaffold-verbatim)
- `steps/step-03-triage.md` (scaffold-verbatim)
- `steps/step-04-present.md` (scaffold-verbatim)

Includes used:
- `<<include path="_shared/fragments/resolver-fallback.md" skill_kind="workflow">>`
- `<<include path="_shared/fragments/persistent-facts.md">>`

## EXCEPTION-1 Note

Original SKILL.md had `name:` + `description:` frontmatter only. Compiled SKILL.md has `artifacts:` block added. Bodies equal: True — deviation is frontmatter-only, non-breaking (LLM reads body only).

## Deviations

- **D-EXCEPTION-1:** `artifacts:` frontmatter key present in compiled SKILL.md (same class as 10.27a/10.28/10.30/10.33/10.34). Non-breaking. Signed-off.

## Char-set

unicode-passthrough (no non-ASCII chars in this skill's body)

## Golden SHA

SHA-256[:16]: `01a91957a634dc6a`  
Size: 4380 bytes
