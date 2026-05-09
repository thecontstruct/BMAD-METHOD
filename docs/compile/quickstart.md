---
title: Compile Quickstart
description: Five-minute walkthrough — compile a skill, inspect its output, author one override, see the override applied.
---

A five-minute round trip from a fresh install through your first override. Confirms the compiler, customization surface, and lockfile work end-to-end.

:::note[Prerequisites]

- BMad installed in your project (see [How to Install BMad](../how-to/install-bmad.md))
- Python 3.11+ on your `PATH` (stdlib only — no `pip install`, no virtualenv)
- A skill installed under `_bmad/` you can experiment against (every install ships `bmad-help`)

:::

:::tip[Quick Path]
Compile a skill, override a TOML scalar in `_bmad/custom/`, recompile with `--diff`, see your change in the unified diff. No file you didn't author gets touched.
:::

## Step 1: Compile a skill

Run the compiler against an installed skill. The default install layout puts skills under `_bmad/<module>/` and writes the compiled `SKILL.md` next to the source template.

From the root of a project where `bmad install` has previously run (so `_bmad/` exists as a direct child):

```bash
python3 path/to/bmad-method/src/scripts/compile.py bmad-help --install-dir .
```

The positional argument is the canonical skill name (`module/skill` or just `skill` if unambiguous). `--install-dir` must point to the directory that contains `_bmad/` — that is, an installed bmad-method project root, not the bmad-method source repo itself. The repo's `src/_bmad/` tree is engine source layout used during development, not a complete install root with a populated `bmad.lock`.

On success the compiler exits 0 and updates two files:

- `_bmad/<module>/bmad-help/SKILL.md` — compiled output
- `_bmad/_config/bmad.lock` — provenance record (see [bmad.lock schema](./bmad-lock-schema.md))

## Step 2: Inspect what compiled

Use `--explain` to see provenance for every fragment, variable, and glob expansion. `--explain` is read-only; it never writes files.

```bash
python3 src/scripts/compile.py bmad-help --explain --install-dir .
```

Output is Markdown with inline XML provenance attributes. Each `<Include>` tag carries the fragment path, its sha256 hash, and where the resolver found it (`base`, `user-override`, etc.). See [the explain vocabulary](./explain-vocabulary.md) for every tag.

For a fragment-only dependency tree, add `--tree`. For machine-readable output, add `--json`.

## Step 3: Author one override

Pick a customizable skill — every workflow skill ships a `customize.toml` describing its override surface. Use `bmad-customize` from your IDE chat for guided authoring (see [the walkthrough](./bmad-customize-walkthrough.md)), or hand-author a sparse override file.

For a hand-authored example, create `_bmad/custom/bmad-create-prd.toml`:

```toml
[workflow]
activation_steps_prepend = [
  "Read the team's PRD style guide at _bmad/team-context/prd-style.md before starting.",
]
```

Only the fields you're changing. Never copy the whole `customize.toml`.

## Step 4: Recompile with --diff

Dry-run mode emits a unified diff to stdout without writing files:

```bash
python3 src/scripts/compile.py bmad-create-prd --diff --install-dir .
```

The diff shows the override merged into the skill's compiled output. Append-array fields like `activation_steps_prepend` show as added lines in the relevant section.

If the diff is empty, the override either matched the existing default or didn't reach the right surface. Re-read the target's `customize.toml` to confirm field names.

## Step 5: Apply

Drop `--diff` to write the change:

```bash
python3 src/scripts/compile.py bmad-create-prd --install-dir .
```

The compiler updates `bmad.lock` with the override's hash and source path. Subsequent `bmad upgrade` runs detect drift between your override and upstream changes per the lockfile lineage.

## What you've accomplished

- Compiled a skill from source and inspected its provenance.
- Authored a sparse override under `_bmad/custom/` without modifying installed files.
- Verified the override merged correctly via dry-run before applying.

## Next steps

- [Author migration guide](./author-migration-guide.md) — for skill authors moving to the template-source pattern
- [bmad-customize walkthrough](./bmad-customize-walkthrough.md) — guided override authoring from IDE chat
- [How to Customize BMad](../how-to/customize-bmad.md) — full reference for every override surface

## Common questions

### Does `--diff` ever write files?

No. Both `--diff` and `--explain` are strict dry-runs.

### What if compile fails with a hash mismatch?

The compiled output diverged from `bmad.lock`. Re-run `bmad install` to regenerate the lockfile. Story 5.5b strict-mode validates the lockfile `version` field.

### Is the compiler stdlib-only?

Yes. `compile.py` and `bmad_compile/` import only Python 3.11+ stdlib (no `pyyaml`, no `requests`). The CI matrix in Story 7.3 confirms compiler-present and compiler-absent installs produce byte-identical output.
