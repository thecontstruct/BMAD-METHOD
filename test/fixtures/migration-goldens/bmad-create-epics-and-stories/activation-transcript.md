# Activation Transcript — bmad-create-epics-and-stories (Story 10.31)

## Signed-off Deviation: `artifacts:` key in compiled SKILL.md frontmatter

**Deviation count:** 1 block  
**Nature:** The pre-migration `SKILL.md` frontmatter contained only `name:` and `description:`. The compiled SKILL.md contains `name:`, `description:`, and `artifacts:` (15-line block declaring 5 scaffold-verbatim artifacts: 1 in `templates/` + 4 in `steps/`).

## Why the deviation is non-breaking

Identical to Story 10.27a / 10.28 / 10.29 / 10.30 precedent: `artifacts:` key consumed exclusively by the compile pipeline. LLM reads body starting from `# Create Epics and Stories`. SKILL.md body is byte-identical (bodies equal: True).

## Fragment analysis

- **conventions.md**: MISMATCH — bullet 1 has `(e.g. \`steps/step-01-validate-prerequisites.md\`)` → verbatim.
- **resolver-fallback.md** (skill_kind="workflow"): EXACT MATCH → `<<include>>`.
- **persistent-facts.md**: EXACT MATCH → `<<include>>`.
- **config-load.md**: MISMATCH — 5-bullet skill-specific list → verbatim.
- **workflow-activation.md**: N/A (config-load differs).

Non-ASCII in verbatim body: emojis (🛑📖🚫💾🎯⏸️📋) in `## WORKFLOW ARCHITECTURE` section — unicode-passthrough, no rewrite needed.

Result: **migration-candidate-multi-file** with `resolver-fallback, persistent-facts` fragments. Bodies equal: True.

## Sign-off

Pre-approved by Story 10.27a precedent class (Phil sign-off 2026-05-25).

**AC-S6b status: SATISFIED**
