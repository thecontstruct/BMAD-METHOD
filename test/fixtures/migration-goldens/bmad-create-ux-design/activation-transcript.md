# Activation Transcript — bmad-create-ux-design (Story 10.30)

## Signed-off Deviation: `artifacts:` key in compiled SKILL.md frontmatter

**Deviation count:** 1 block  
**Nature:** The pre-migration `SKILL.md` frontmatter contained only `name:` and `description:`. The compiled SKILL.md contains `name:`, `description:`, and `artifacts:` (48-line block declaring 16 scaffold-verbatim artifacts: 1 root file + 15 in `steps/`).

## Why the deviation is non-breaking

Identical to Story 10.27a / 10.28 / 10.29 precedent: the `artifacts:` key is consumed exclusively by the compile pipeline. The LLM reads the body starting from `# Create UX Design Workflow`. The SKILL.md body is byte-identical between pre- and post-migration (bodies equal: True).

## Fragment analysis

- **conventions.md**: MISMATCH — bullet 1 has skill-specific example `(e.g. \`steps/step-01-init.md\`)` → verbatim.
- **resolver-fallback.md** (skill_kind="workflow"): EXACT MATCH → `<<include>>`.
- **persistent-facts.md**: EXACT MATCH → `<<include>>`.
- **config-load.md**: MISMATCH — 5-bullet skill-specific list vs 11-line fragment → verbatim.
- **workflow-activation.md**: N/A (config-load differs).

Result: **migration-candidate-multi-file** with `resolver-fallback, persistent-facts` fragments. Bodies equal: True.

## Sign-off

Pre-approved by Story 10.27a precedent class (Phil sign-off 2026-05-25). Expected for all FR-3 artifact-emitting migrations.

**AC-S6b status: SATISFIED** — observable runtime behavior identical pre- and post-migration.
