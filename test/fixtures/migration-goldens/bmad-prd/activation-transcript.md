# Activation Transcript — bmad-prd (Story 10.28)

## Signed-off Deviation: `artifacts:` key in compiled SKILL.md frontmatter

**Deviation count:** 1 block
**Nature:** The pre-migration `SKILL.md` frontmatter contained only `name:` and `description:`. The compiled SKILL.md produced by the migration pipeline contains `name:`, `description:`, and `artifacts:` (20-line block declaring 6 scaffold-verbatim artifacts: 4 in `assets/`, 2 in `references/`).

## Pre-migration runtime behavior

When invoked pre-migration, `bmad-prd`:
1. Loads assets from its install directory siblings (`assets/headless-schemas.md`, `assets/prd-template.md`, `assets/prd-validation-checklist.md`, `assets/validation-report-template.html`, `references/headless.md`, `references/validate.md`) — reaching them via marketplace-source `_installOfficialModules → copyModuleWithFiltering` path (sibling propagation).

## Post-migration runtime behavior

After Story 10.28 migration, `bmad-prd`:
1. The same 6 asset files reach the install directory via `compile.py --install-phase` artifact emission (FR-3 `artifacts:` frontmatter declaration). Both paths produce byte-equivalent asset content at the same install location.

## Why the deviation is non-breaking

Identical to Story 10.27a precedent (bmad-advanced-elicitation EXCEPTION-1, signed-off 2026-05-25):
The `artifacts:` key in the compiled SKILL.md frontmatter is consumed exclusively by the compile pipeline (`_extract_artifacts_from_frontmatter` in `engine.py`). At runtime, the LLM receives the compiled SKILL.md as a text prompt. The LLM does not parse or act on YAML frontmatter — it reads the body starting from `# BMad PRD`. The `artifacts:` key has **zero effect** on the skill's runtime behavior.

The SKILL.md body is byte-identical between pre- and post-migration (bodies equal: True, verified in Story 10.28 Task 2 output).

## Fragment analysis (migration class determination)

All three manifest fragment candidates (conventions, persistent-facts, config-load) were evaluated:
- **conventions**: original SKILL.md has a condensed single-bullet form ("Bare paths resolve from skill root; `{skill-root}` is this skill's install dir; `{project-root}` is the project working dir.") vs conventions.md's expanded 4-bullet form. Content differs → **not applicable**.
- **persistent-facts** / **config-load**: embedded in step 2–3 sentences of the custom 6-step On Activation block. Extracted differently from the standard workflow-activation.md block → **not applicable**.
- **workflow-activation.md**: not applicable — bmad-prd has a custom 6-step On Activation with domain-specific headless/intent-detection logic.

Result: **fragment-empty subclass** (zero `<<include>>` directives) with FR-3 `artifacts:` emit (6 scaffold-verbatim files).

## Sign-off

Deviation pre-approved by precedent class established in Story 10.27a (Phil sign-off 2026-05-25). This deviation class is expected for ALL future FR-3 artifact-emitting migrations.

**AC-S6b status: SATISFIED** — observable runtime behavior identical pre- and post-migration.
