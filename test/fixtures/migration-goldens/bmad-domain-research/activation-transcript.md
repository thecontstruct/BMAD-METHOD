# Activation Transcript — bmad-domain-research (Story 10.40)

## Classification

- **Class:** migration-candidate-multi-file (runtime-scaffold subclass)
- **Module:** bmm
- **Bodies equal:** False (D4: 4× `{{X}}`→`{X}` Handlebars normalization)
- **Exception class:** EXCEPTION-1 (artifacts: frontmatter)

## Fragment Analysis

### Step 1: conventions.md

Original Conventions section uses `(e.g. \`domain-steps/step-01-init.md\`)` as bare-path example (skill-specific). Fragment uses different generic example. **Result: MISMATCH → verbatim**

### Step 2: resolver-fallback.md (skill_kind="workflow")

Original Step 1 On Activation block matches the resolver-fallback fragment exactly.
**Result: MATCH → `<<include path="_shared/fragments/resolver-fallback.md" skill_kind="workflow">>`**

### Step 3: persistent-facts.md

Original Step 3 "Load Persistent Facts" block matches the persistent-facts fragment exactly.
**Result: MATCH → `<<include path="_shared/fragments/persistent-facts.md">>`**

### Step 4: config-load.md

Skill-specific config items (planning_artifacts, project_knowledge). **Result: MISMATCH → verbatim**

## D4 Normalization

4 Handlebars `{{X}}` patterns normalized to runtime `{X}`:
1. `{{user_name}}` → `{user_name}` (QUICK TOPIC DISCOVERY greeting)
2. `{{research_topic}}` → `{research_topic}` (slug derivation note)
3. `{{research_topic_slug}}` → `{research_topic_slug}` (output file path)
4. `{{date}}` → `{date}` (output file path)

## Template Structure

Artifacts frontmatter (7 entries):
- `research.template.md` (scaffold-verbatim — runtime scaffold template)
- `domain-steps/step-01-init.md` through `domain-steps/step-06-research-synthesis.md` (6× scaffold-verbatim)

Includes used:
- `<<include path="_shared/fragments/resolver-fallback.md" skill_kind="workflow">>`
- `<<include path="_shared/fragments/persistent-facts.md">>`

## EXCEPTION-1 Note

Original SKILL.md had `name:` + `description:` frontmatter only. Compiled SKILL.md has `artifacts:` block added. Bodies equal: False due to D4 normalization (Handlebars → runtime placeholder). Content semantics unchanged. Non-breaking.

## Deviations

- **D-EXCEPTION-1:** `artifacts:` frontmatter key present in compiled SKILL.md. Non-breaking. Signed-off.
- **D4:** 4× `{{X}}`→`{X}` Handlebars normalization. Signed-off.

## Char-set

unicode-passthrough (⛔ U+26D4 in PREREQUISITE section, ✅ U+2705 in ROUTE section)

## Golden SHA

SHA-256[:16]: `4b27cbeb26cd95a9`  
Size: 5457 bytes
