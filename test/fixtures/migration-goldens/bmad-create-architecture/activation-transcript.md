# Activation Transcript — bmad-create-architecture (Story 10.29)

## Signed-off Deviation: `artifacts:` key in compiled SKILL.md frontmatter

**Deviation count:** 1 block  
**Nature:** The pre-migration `SKILL.md` frontmatter contained only `name:` and `description:`. The compiled SKILL.md produced by the migration pipeline contains `name:`, `description:`, and `artifacts:` (36-line block declaring 12 scaffold-verbatim artifacts: 1 root file + 2 in `data/` + 9 in `steps/`).

## Pre-migration runtime behavior

When invoked pre-migration, `bmad-create-architecture`:
1. Loads step files from its install directory siblings (`steps/step-0N-*.md`) — reaching them via marketplace-source `_installOfficialModules → copyModuleWithFiltering` path (sibling propagation).
2. Loads data files (`data/domain-complexity.csv`, `data/project-types.csv`) via the same path.
3. Loads `architecture-decision-template.md` from the skill root via the same path.

## Post-migration runtime behavior

After Story 10.29 migration, `bmad-create-architecture`:
1. The same 12 asset files reach the install directory via `compile.py --install-phase` artifact emission (FR-3 `artifacts:` frontmatter declaration). Both paths produce byte-equivalent asset content at the same install location.

## Why the deviation is non-breaking

Identical to Story 10.27a precedent (bmad-advanced-elicitation EXCEPTION-1, signed-off 2026-05-25) and Story 10.28 precedent (bmad-prd EXCEPTION-1, signed-off 2026-05-25):

The `artifacts:` key in the compiled SKILL.md frontmatter is consumed exclusively by the compile pipeline (`_extract_artifacts_from_frontmatter` in `engine.py`). At runtime, the LLM receives the compiled SKILL.md as a text prompt. The LLM does not parse or act on YAML frontmatter — it reads the body starting from `# Architecture Workflow`. The `artifacts:` key has **zero effect** on the skill's runtime behavior.

The SKILL.md body is byte-identical between pre- and post-migration (bodies equal: True, verified in Story 10.29 Task 2 output).

## Fragment analysis (migration class determination)

All four fragment candidates were evaluated:

- **conventions.md**: Original SKILL.md has `- Bare paths (e.g. \`steps/step-01-init.md\`) resolve from the skill root.` (includes a skill-specific example) vs conventions.md which has `- Bare paths resolve from the skill root.` (no example). Content differs → **not applicable (verbatim)**.
- **resolver-fallback.md** (`skill_kind="workflow"`): Compiled fragment text is byte-identical to SKILL.md lines 35–41 (`**If the script fails**...append.`) → **used (`<<include>>`)**. Bodies equal verified.
- **persistent-facts.md**: Compiled fragment text is byte-identical to SKILL.md line 49 (`Treat every entry in \`{workflow.persistent_facts}\`...verbatim.`) → **used (`<<include>>`)**. Bodies equal verified.
- **config-load.md**: Original SKILL.md has a 5-bullet skill-specific config list vs config-load.md's 11-line standardized format. Content differs substantially → **not applicable (verbatim)**.
- **workflow-activation.md**: Cannot use (embeds config-load.md which differs) → **N/A**.

Result: **migration-candidate-multi-file** with `resolver-fallback, persistent-facts` fragments consumed. Bodies equal: True.

## Sign-off

Deviation pre-approved by precedent class established in Story 10.27a (Phil sign-off 2026-05-25) and confirmed in Story 10.28. This deviation class is expected for ALL future FR-3 artifact-emitting migrations.

**AC-S6b status: SATISFIED** — observable runtime behavior identical pre- and post-migration.
