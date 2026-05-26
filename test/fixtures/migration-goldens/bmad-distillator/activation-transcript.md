# Activation Transcript — bmad-distillator (Story 10.36)

## Classification

- **Class:** migration-candidate-multi-file (fragment-empty subclass)
- **Module:** core
- **Bodies equal:** False (NORM-TN: trailing newline normalization)
- **Exception class:** EXCEPTION-1 (artifacts: frontmatter)

## Fragment Analysis

No standard On Activation pattern (micro-file architecture). SKILL.md uses a direct Stage-based workflow with custom "On Activation" section (Validate inputs → Route to Stage 1). The resolver-fallback and persistent-facts fragments have zero overlap with this content.

**Result: fragment-empty migration — pure verbatim body**

## Template Structure

Artifacts frontmatter (7 entries):
- `agents/distillate-compressor.md` (scaffold-verbatim)
- `agents/round-trip-reconstructor.md` (scaffold-verbatim)
- `resources/compression-rules.md` (scaffold-verbatim)
- `resources/distillate-format-reference.md` (scaffold-verbatim)
- `resources/splitting-strategy.md` (scaffold-verbatim)
- `scripts/analyze_sources.py` (scaffold-verbatim — Python script emitted verbatim)
- `scripts/tests/test_analyze_sources.py` (scaffold-verbatim)

No includes used (fragment-empty).

## EXCEPTION-1 Note

Original SKILL.md had `name:` + `description:` frontmatter only. Compiled SKILL.md has `artifacts:` block added. Bodies equal: False due to NORM-TN — original SKILL.md lacked a trailing newline (non-standard POSIX file); compiled output adds one. Content is otherwise byte-identical. Non-breaking.

## Deviations

- **D-EXCEPTION-1:** `artifacts:` frontmatter key present in compiled SKILL.md. Non-breaking. Signed-off.
- **D-NORM-TN:** Original SKILL.md lacked trailing newline; compiled output adds trailing `\n` per POSIX convention. Content unchanged. Signed-off.

## Char-set

ASCII-only

## Golden SHA

SHA-256[:16]: `a928b26078a83123`  
Size: 9767 bytes
