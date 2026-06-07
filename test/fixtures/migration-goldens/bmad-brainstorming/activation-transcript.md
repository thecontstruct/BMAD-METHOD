# Activation Transcript — bmad-brainstorming (Story 10.48)

## Classification

- **Class:** upstream-redesign (feab3d5e — facilitation modes + memlog + composer)
- **Module:** core
- **Bodies equal:** N/A — complete structural redesign, not a migration
- **Exception class:** EXCEPTION-1 (artifacts: frontmatter)

## Fragment Analysis

No standard fragment blocks present. SKILL.md body is the full upstream SKILL.md
content from feab3d5e: ~100 lines covering Overview, Conventions, On Activation,
three facilitation stances (Facilitator / Creative Partner / Ideate for me),
memlog session memory, Run a Session, Choosing Techniques, Converging, Resuming,
and Wrap-Up sections. References loaded on demand via `references/` directory.

**Result: full-body verbatim (upstream body) — fragment-empty**

## Template Structure

Artifacts frontmatter (18 entries):
- `customize.toml` (scaffold-verbatim)
- `assets/brain-methods.csv` (scaffold-verbatim)
- `assets/brain-icons.json` (scaffold-verbatim)
- `assets/brain-selector.html` (scaffold-verbatim)
- `references/converge.md` (scaffold-verbatim)
- `references/finalize.md` (scaffold-verbatim)
- `references/headless.md` (scaffold-verbatim)
- `references/in-chat-techniques.md` (scaffold-verbatim)
- `references/mode-autonomous.md` (scaffold-verbatim)
- `references/mode-facilitator.md` (scaffold-verbatim)
- `references/mode-partner.md` (scaffold-verbatim)
- `references/resume.md` (scaffold-verbatim)
- `scripts/brain.py` (scaffold-verbatim)
- `scripts/memlog.py` (scaffold-verbatim)
- `scripts/tests/test_brain.py` (scaffold-verbatim)
- `scripts/tests/test_memlog.py` (scaffold-verbatim)
- `analysis/catalog-analysis.md` (scaffold-verbatim)
- `analysis/method-matrix.csv` (scaffold-verbatim)

No includes used (fragment-empty).

## Activation Behavior (Post-feab3d5e)

On activation the skill:
1. Resolves `customize.toml` via `resolve_customization.py --skill {skill-root} --key workflow`
2. Runs activation_steps_prepend entries (default: empty)
3. Loads config.yaml, resolves user_name / communication_language / output_folder / date
4. Globs `{workflow.output_dir}/*/.memlog.md`, reads each frontmatter, and offers to
   resume any session with status ≠ `complete` (§Resuming) or start fresh (§Run a Session)
5. Session proceeds in one of three stances: Facilitator / Creative Partner / Ideate for me
6. Memlog (`.memlog.md`) is maintained via `python3 {skill-root}/scripts/memlog.py`
7. Techniques served via `python3 {skill-root}/scripts/brain.py --file {workflow.brain_methods}`
   — never the full catalog into context; --all is deliberate escape hatch

Old step-01/step-02/step-03/step-04 micro-file architecture replaced by SKILL.md +
references/ on-demand loading pattern.

## EXCEPTION-1 Note

Upstream SKILL.md had `name:` + `description:` frontmatter only. Compiled SKILL.md
has `artifacts:` block added. Bodies equal: True (same EXCEPTION-1 class as prior
migrations). Non-breaking — LLM reads body only.

## Python Scripts Compatibility

- `scripts/brain.py` (740 lines): stdlib only (argparse, csv, hashlib, html, json,
  random, sys, pathlib). Python ≥ 3.10. DEFAULT_FILE resolves to assets/brain-methods.csv
  relative to script location — correct for our structure.
- `scripts/memlog.py` (202 lines): stdlib only (argparse, json, os, sys, datetime,
  pathlib). Python ≥ 3.10.
- NO third-party dependencies. NO ComponentRunner integration.

## Deviations

- **D-EXCEPTION-1:** `artifacts:` frontmatter key present in compiled SKILL.md.
  Non-breaking. Signed-off per established EXCEPTION-1 precedent.

## Engine-Frozen Statement (Story 10.48)

5 pinned SHA files (bmad-help/SKILL.md, invoke-python.js, bmad-quick-dev/*,
bmad-customize.template.md, bmad-reference-components/*) remain byte-identical.
Proof: test_bmad_help_keep_contract.py passes.

## Char-set

UTF-8 (upstream SKILL.md contains em-dash and similar non-ASCII characters)

## Golden SHA

SHA-256[:16]: `26753467eb086986`
Size: 11223 bytes
