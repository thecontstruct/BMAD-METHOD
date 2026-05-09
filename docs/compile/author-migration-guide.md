---
title: Author Migration Guide
description: Migrate a skill from raw SKILL.md authoring to the template-source pattern with customize.toml and prose fragments.
---

Walks skill authors through migrating from a hand-authored `SKILL.md` to the template-source pattern that v6's compiler resolves at install time. Covers template syntax, the `customize.toml` surface, prose-fragment includes, and the local compile loop.

:::note[Prerequisites]

- An existing skill with a hand-authored `SKILL.md`
- Python 3.11+ on your `PATH` (stdlib only)
- Familiarity with TOML

:::

:::tip[Quick Path]
Rename `SKILL.md` to `<skill-name>.template.md`, extract `name` and `description` into a sibling `customize.toml`, replace inline values with `{{self.name}}` / `{{self.description}}`, and keep going. The compiler emits the new `SKILL.md` from the template.
:::

## Why migrate

The template-source pattern decouples authored content from compiled output. Users override fields in `_bmad/custom/` without forking the skill, and `bmad upgrade` detects drift against your published source rather than against a generated artifact. Skills that ship as raw `SKILL.md` cannot be customized in this way.

Migration is a one-time refactor per skill. Once migrated, the skill participates in the customization framework, the lockfile, and `--explain` provenance.

## What changes

| Before                              | After                                                             |
| ----------------------------------- | ----------------------------------------------------------------- |
| `SKILL.md` hand-authored            | `<skill-name>.template.md` authored, `SKILL.md` compiler-generated |
| `name` / `description` inline       | `name` / `description` defaults in `customize.toml`               |
| Long prose blocks duplicated        | Reusable prose extracted to `fragments/*.md`                      |
| Variant skills hand-forked          | Single template plus IDE variants resolved at compile time        |

## Step 1: Rename the source

Rename your existing `SKILL.md` to `<skill-name>.template.md` in the same directory. The compiler picks up `<skill-name>.template.md` as the root for that skill.

```text
src/<module>/<skill-name>/
├── <skill-name>.template.md   ← rename from SKILL.md
└── (other files unchanged)
```

## Step 2: Author customize.toml

Create `customize.toml` next to the template. At minimum it carries `name` and `description` defaults plus the override surface (`[agent]` or `[workflow]`):

```toml
name = "my-skill"
description = "Short trigger description used by the agent dispatcher."

[workflow]
# Steps appended before the standard activation. Override appends.
activation_steps_prepend = []

# Steps appended after greet but before the workflow begins. Override appends.
activation_steps_append = []
```

Only expose fields you intend users to override. Anything not present in `customize.toml` is uncustomizable through the framework. See [How to Customize BMad](../how-to/customize-bmad.md) for the full schema and merge rules.

## Step 3: Replace inline values with template variables

In `<skill-name>.template.md`, swap the literal `name` and `description` values in the YAML frontmatter for `{{self.name}}` and `{{self.description}}`:

```markdown
---
name: {{self.name}}
description: {{self.description}}
---

# My Skill
```

The compiler reads `{{self.<field>}}` and resolves it against `customize.toml` defaults plus any override layer. Reference [the explain vocabulary](./explain-vocabulary.md) for every variable provenance attribute.

## Step 4: Extract reusable prose to fragments

Prose blocks shared across skills move to `fragments/<name>.md` and pull in via `<<include>>`:

```markdown
<<include path="fragments/preflight.md">>
```

Fragments resolve in this priority order: user override (`_bmad/custom/`), module-level fragment, base fragment shipped with the skill. Each level emits a `<Include>` tag in `--explain` output with the resolved path.

Use fragments only for prose that genuinely benefits from sharing. Inlining a unique block keeps the source flat and the lockfile shorter.

## Step 5: Compile and verify locally

Run the compiler against your skill from the repo root:

```bash
python3 src/scripts/compile.py <skill-name> --install-dir <path-to-test-install>
```

Expected behavior:

- `<install-dir>/<module>/<skill-name>/SKILL.md` is regenerated.
- `<install-dir>/_bmad/_config/bmad.lock` records the new entry.

Diff the compiled `SKILL.md` against your old hand-authored one. The two should be byte-identical except for fields the template now resolves (typically frontmatter only).

For a deeper inspection, run `--explain` to see every fragment, variable, and glob expansion the resolver visited:

```bash
python3 src/scripts/compile.py <skill-name> --explain --install-dir <path>
```

## Step 6: Update CI and validation

Two CI gates cover migrated skills:

- `validate:compile` — verifies your published `SKILL.md` matches what the compiler emits from the current source.
- `validate:skills` — frontmatter and structural rules.

Run both locally before opening a PR:

```bash
npm run validate:compile
npm run validate:skills
```

If `validate:compile` flags a hash mismatch, the published `SKILL.md` is stale. Re-run the compiler and commit the regenerated artifact alongside the template change.

## Common questions

### Do I commit the compiled SKILL.md?

Yes. The repo ships both source (`<skill-name>.template.md`) and compiled output (`SKILL.md`) so installs without Python at compile time still work. Story 7.6 covers the distribution-model detection.

### Can I keep some skills as Model 1 (precompiled-only)?

Yes. Skills without a `*.template.md` file install verbatim via the Model 1 path. Migrate when you want to expose customization, not before.

### What about IDE-variant files?

If your skill has IDE-specific variants, ship them as `<skill-name>.<ide>.template.md` next to the base. The compiler selects via `--tools <ide>`.

## Next steps

- [Quickstart](./quickstart.md) — the five-minute end-to-end loop
- [bmad-customize walkthrough](./bmad-customize-walkthrough.md) — what end-users will experience after migration
- [bmad.lock schema](./bmad-lock-schema.md) — provenance fields the compiler writes
