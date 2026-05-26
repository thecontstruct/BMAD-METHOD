# Activation Transcript — bmad-product-brief (Story 10.39)

## Classification

- **Class:** migration-candidate-multi-file (fragment-empty subclass)
- **Module:** bmm
- **Bodies equal:** True
- **Exception class:** EXCEPTION-1 (artifacts: frontmatter)

## Fragment Analysis

### Step 1: resolver-fallback.md check

Original On Activation Step 1 uses condensed format: "On failure, read `{skill-root}/customize.toml` directly and use defaults." — much shorter than the full resolver-fallback TOML merge instructions. **Result: MISMATCH → verbatim**

### Step 3: persistent-facts.md check

Original Step 3: "Treat every entry in `{workflow.persistent_facts}` as foundational context **for the rest of the run**..."
Fragment: "Treat every entry in `{workflow.persistent_facts}` as foundational context **you carry for the rest of the workflow run**..."
Wording differs. **Result: MISMATCH → verbatim**

**Overall: fragment-empty migration — pure verbatim body**

Note: On Activation uses a numbered list (1-7) rather than the standard Step 1/2/3 heading format. Custom format; no fragments apply.

## Template Structure

Artifacts frontmatter (1 entry):
- `assets/brief-template.md` (scaffold-verbatim)

No includes used (fragment-empty).

Notable body content: complex coaching/create/update/validate workflow; extensive runtime vars (`{workflow.brief_template}`, `{workflow.doc_standards}`, `{workflow.external_handoffs}`, `{workflow.on_complete}`, `{workflow.external_sources}`, `{doc_workspace}`, `{workflow.brief_output_path}`, `{workflow.run_folder_pattern}`); no D4 normalization needed (original SKILL.md uses single-brace `{X}` throughout).

## EXCEPTION-1 Note

Original SKILL.md had `name:` + `description:` frontmatter only. Compiled SKILL.md has `artifacts:` block added. Bodies equal: True — deviation is frontmatter-only, non-breaking (LLM reads body only).

## Deviations

- **D-EXCEPTION-1:** `artifacts:` frontmatter key present in compiled SKILL.md. Non-breaking. Signed-off.

## Char-set

unicode-passthrough (em-dashes U+2014 and `⛔`... wait — no special chars in product-brief. Actually reviewing: no `⛔`, no em-dash. ASCII-only body.)

## Golden SHA

SHA-256[:16]: `fec7f119ec2a64d8`  
Size: 10613 bytes
