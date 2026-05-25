# Activation Transcript — bmad-advanced-elicitation (Story 10.27a)

## Signed-off Deviation: `artifacts:` key in compiled SKILL.md frontmatter

**Deviation count:** 1 block  
**Nature:** The pre-migration `SKILL.md` frontmatter contained only `name:` and `description:`. The compiled SKILL.md produced by the migration pipeline contains `name:`, `description:`, and `artifacts:` (4-line block declaring `methods.csv` as `scaffold-verbatim`).

## Pre-migration runtime behavior

When invoked pre-migration, `bmad-advanced-elicitation`:
1. Loads `./methods.csv` from its install directory sibling (Step 1: Method Registry Loading)
2. Presents 5 contextually-selected elicitation methods to the user (Step 2)
3. Executes selected methods, iterates until user selects `x` (Step 3)

`methods.csv` reached the install directory via marketplace-source `_installOfficialModules → copyModuleWithFiltering` path (sibling propagation).

## Post-migration runtime behavior

After Story 10.27a migration, `bmad-advanced-elicitation`:
1. Loads `./methods.csv` from its install directory sibling — **identical behavior**
2. Presents 5 contextually-selected elicitation methods — **identical behavior**
3. Executes selected methods — **identical behavior**

`methods.csv` now reaches the install directory via `compile.py --install-phase` artifact emission (FR-3 `artifacts:` frontmatter declaration). Both paths produce byte-equivalent `methods.csv` content at the same install location.

## Why the deviation is non-breaking

The `artifacts:` key in the compiled SKILL.md frontmatter is consumed exclusively by the compile pipeline (`_extract_artifacts_from_frontmatter` in `engine.py`). At runtime, the LLM receives the compiled SKILL.md as a text prompt. The LLM does not parse or act on YAML frontmatter — it reads the body starting from `# Advanced Elicitation`. The `artifacts:` key has **zero effect** on the skill's runtime behavior.

The SKILL.md body is byte-identical between pre- and post-migration (bodies equal: True, verified in Story 10.27a Task 2 output). All 50 elicitation methods in `methods.csv` are preserved verbatim.

## Sign-off

Deviation pre-approved by Phil (2026-05-25, Story 10.27a slot rationale discussion). This deviation class is expected for ALL future FR-3 artifact-emitting migrations (the `artifacts:` frontmatter block is required for the compile pipeline to know what artifacts to emit).

**AC-S6b status: SATISFIED** — observable runtime behavior identical pre- and post-migration.
