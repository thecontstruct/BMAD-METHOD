# Activation Transcript — bmad-investigate (Story 10.38)

## Classification

- **Class:** migration-candidate-multi-file (fragment-empty subclass)
- **Module:** bmm
- **Bodies equal:** True
- **Exception class:** EXCEPTION-1 (artifacts: frontmatter)

## Fragment Analysis

### Step 1: resolver-fallback.md check

Original Step 1 "Resolve the workflow block" uses:
`If the script fails, stop and surface the error.`

This is DIFFERENT from the resolver-fallback fragment which provides the full TOML fallback instructions (3-file merge description). **Result: MISMATCH → verbatim**

### Step 3: persistent-facts.md check

Original Step 3 "Load persistent facts" uses:
`Treat each entry in \`{workflow.persistent_facts}\` as foundational context. \`file:\` prefixes are paths or globs under \`{project-root}\` (load contents); other entries are facts verbatim.`

This is a condensed variant DIFFERENT from the persistent-facts fragment (which uses the longer "Treat every entry in..." wording with "you carry for the rest of the workflow run"). **Result: MISMATCH → verbatim**

### Overall fragment result

All fragment candidates mismatch. **Result: fragment-empty migration — pure verbatim body**

## Template Structure

Artifacts frontmatter (1 entry):
- `references/case-file-template.md` (scaffold-verbatim)

No includes used (fragment-empty). Step 7 ("Acknowledge and route") is unique to this skill — adds a routing step not present in standard 6-step activation.

## EXCEPTION-1 Note

Original SKILL.md had `name:` + `description:` frontmatter only. Compiled SKILL.md has `artifacts:` block added. Bodies equal: True — deviation is frontmatter-only, non-breaking (LLM reads body only).

## Deviations

- **D-EXCEPTION-1:** `artifacts:` frontmatter key present in compiled SKILL.md (same class as 10.27a/10.28/10.30/10.33/10.34). Non-breaking. Signed-off.

## Char-set

unicode-passthrough (em-dashes U+2014 throughout body)

## Golden SHA

SHA-256[:16]: `95f0ee704917ee55`  
Size: 11249 bytes
