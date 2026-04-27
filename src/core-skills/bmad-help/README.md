# bmad-help skill — dual-file layout and keep-contract

This directory contains two files that work together as the keep-contract for the
bmad-help reference skill:

| File | Role |
| --- | --- |
| `bmad-help.template.md` | **Template** — the source the compile pipeline reads |
| `SKILL.md` | **Frozen baseline** — the expected compile output that CI checks against |

## What the keep-contract means

`SKILL.md` must always equal the output of `engine.compile_skill` run against
`bmad-help.template.md`. CI enforces this: if the two diverge, `npm run test:python`
fails with a byte-diff assertion. This makes `bmad-help` the **first reference skill**
that proves the compile pipeline preserves byte-for-byte output for a real production skill.

Because bmad-help has zero `{{var}}` interpolations and zero `<<include>>` fragments,
the keep-contract is pure passthrough — any divergence is unambiguously a
compile-pipeline bug.

## Updating bmad-help content

Never edit `SKILL.md` directly. Instead:

1. Edit `bmad-help.template.md` (the template — source of truth).
2. Run the regeneration helper from the repo root:
   ```
   python3 BMAD-METHOD/tools/regenerate-bmad-help-baseline.py
   ```
3. The helper compiles the updated template and overwrites `SKILL.md` with the
   fresh compiled bytes.
4. Commit **both** the template change and the regenerated baseline in the same PR.
5. CI (`npm run test:python`) verifies the keep-contract holds against the new baseline.

Helper source: [`tools/regenerate-bmad-help-baseline.py`](../../../tools/regenerate-bmad-help-baseline.py)

## Future work

Story 4.1 will add a `bmad compile <skill> --diff` CLI subcommand that makes this
regeneration flow ergonomic at the user-facing CLI layer, replacing the one-off
helper script.

## References

- Helper script: [`tools/regenerate-bmad-help-baseline.py`](../../../tools/regenerate-bmad-help-baseline.py)
- Story 2.2 (`bmad-help` as first migrated reference skill, keep-contract) and the verify-story / code-review process notes are maintainer-only artifacts in the BMAD authoring workspace — not bundled with this package.
