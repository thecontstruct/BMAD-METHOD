---
title: bmad-customize Walkthrough
description: End-to-end walkthrough of an interactive bmad-customize session — invocation, discovery, plane routing, draft, accept, post-accept diff, and drift triage.
---

What an interactive `bmad-customize` session looks like from start to finish, with the artifacts each step produces. Use this as the mental model before invoking the skill from your IDE chat.

:::note[Prerequisites]

- BMad installed in your project (see [How to Install BMad](../how-to/install-bmad.md))
- Python 3.11+ on your `PATH`
- At least one customizable skill installed under `_bmad/`

:::

:::tip[Quick Path]
Invoke `bmad-customize` from chat with a clear intent. The skill discovers customizable surfaces, routes you to the right one (agent vs workflow), drafts a sparse override, writes it to `_bmad/custom/`, and verifies the merge with `compile --diff`.
:::

## Invocation

Trigger from any IDE chat that hosts BMad:

> "Run `bmad-customize` to add a step before the PRD workflow that loads our team's PRD style guide."

The skill activates and loads `_bmad/config.toml` (and `_bmad/config.user.toml` if present) for your `user_name` and `communication_language` defaults. If your invocation already names a target skill plus a specific change, the skill jumps straight to surface routing.

## Step 1: Classify intent

The skill bins your request into one of four shapes:

- **Directed** — specific skill plus specific change. Goes straight to Step 3.
- **Exploratory** — "what can I customize?" Goes to discovery.
- **Audit / iterate** — review or change something already customized. Discovery leads with skills that already have overrides.
- **Cross-cutting** — could live on multiple surfaces. Routing walks the tradeoffs with you.

If the classification is wrong, correct it in chat. The skill re-routes without re-asking everything from scratch.

## Step 2: Discovery

For exploratory and audit intents, the skill runs:

```bash
python3 {skill-root}/scripts/list_customizable_skills.py --project-root .
```

`{skill-root}` resolves to wherever `bmad-customize` is installed in your project (typically `_bmad/core-skills/bmad-customize/`).

Output groups customizable skills into agents and workflows. Each entry surfaces:

- Skill name and short description
- `has_team_override` — true if `_bmad/custom/<skill>.toml` exists
- `has_user_override` — true if `_bmad/custom/<skill>.user.toml` exists

Use `--extra-root <path>` (repeatable) when skills live outside the default install root.

If discovery returns an empty list, the skill shows the directories it scanned and offers to retry with `--extra-root`.

## Step 3: Plane routing

The skill reads the target's `customize.toml` and identifies the override surface — top-level `[agent]` or `[workflow]`. If a team or user override already exists, the skill reads it first and summarizes what's already overridden before drafting changes.

Routing heuristic:

| Intent shape                         | Surface                                               |
| ------------------------------------ | ----------------------------------------------------- |
| Every workflow this agent runs       | Agent (e.g., `bmad-agent-pm.toml`)                    |
| One workflow only                    | Workflow (e.g., `bmad-create-prd.toml`)               |
| Several specific workflows           | Multiple workflow overrides, not an agent override    |
| Outside the exposed surface          | Skill says so plainly; offers approximations or tells you to use `bmad-builder` |

Cross-cutting intents walk both surfaces with you and let you pick.

## Step 4: Compose the draft

The skill translates plain English to TOML against the target's exposed fields. Drafts are sparse — only the fields you're changing, never the whole `customize.toml`.

Merge semantics the draft respects:

- **Scalars** (`icon`, `role`, `*_template`, `on_complete`) — override wins.
- **Append arrays** (`persistent_facts`, `activation_steps_prepend`/`append`, `principles`) — your entries append in order.
- **Keyed arrays of tables** (menu items with `code` or `id`) — matching keys replace, new keys append.

If your intent doesn't fit the exposed surface, the skill says so and offers `activation_steps_prepend` / `append` or `persistent_facts` as approximations, or recommends `bmad-builder` to author a custom skill.

## Step 5: Team or user placement

The skill places the override under `_bmad/custom/`:

- `<skill-name>.toml` — team, committed. Policies, org conventions, compliance.
- `<skill-name>.user.toml` — user, gitignored. Personal tone, private facts, shortcuts.

Default is by character (policy → team, personal → user); the skill confirms before writing.

## Step 6: Show, confirm, write, verify

Before writing, the skill shows the proposed override and the file path. After you confirm, it writes the file and runs verification:

```bash
python3 src/scripts/compile.py <skill-name> --diff --install-dir .
```

The dry-run diff shows exactly how your override merges into the compiled output. If the diff is empty, your override didn't reach a real surface — re-check field names against the target's `customize.toml`.

For a richer inspection, the skill can also run `--explain` to show every variable's `toml-layer` (`defaults`, `team`, or `user`) and `contributing-paths` when more than one layer contributed. See [the explain vocabulary](./explain-vocabulary.md).

## Step 7: Accept and post-accept compile

After the diff looks right, the skill commits the change by re-running the compiler without `--diff`:

```bash
python3 src/scripts/compile.py <skill-name> --install-dir .
```

This regenerates the installed `SKILL.md`, updates `_bmad/_config/bmad.lock` with the override's hash, and records the lineage so future `bmad upgrade` runs can detect drift.

## Drift triage

When `bmad upgrade` runs and your override no longer applies cleanly to the upstream skill, the upgrade reports drift. Re-invoke `bmad-customize` with drift-triage intent against the affected skill — the skill reads the drift report, walks each entry with you, and either reconciles (rewriting the override against new upstream) or marks the override as no-longer-applicable.

The dogfood release gate (`src/core-skills/bmad-customize/DOGFOOD.md`) exercises this flow on every release: `bmad-customize` must survive its own upgrade with at least one self-override preserved through triage.

## Reference fixture

The repo ships a recorded session fixture at:

```text
test/fixtures/customize-mocks/dry-run-bmad-customize-self.json
```

It simulates a `bmad-customize` self-upgrade dry-run with one drifted prose fragment and one drifted TOML default. Use it to see exact draft / diff payloads in tests or when authoring new fixtures.

## Common questions

### What if I want to customize something not exposed in customize.toml?

The skill tells you so plainly and offers `activation_steps_prepend` / `append` or `persistent_facts` as approximations. For deeper changes, use `bmad-builder` to author a custom skill that wraps or replaces the original.

### Can I run bmad-customize on a skill I'm authoring?

Yes — once your skill ships a `customize.toml` and uses the template-source pattern (see [author migration guide](./author-migration-guide.md)), it participates in the framework like any other.

### Where do my overrides go?

`_bmad/custom/<skill>.toml` (team, committed) or `_bmad/custom/<skill>.user.toml` (user, gitignored). The skill picks the default based on the character of the change and confirms before writing.

## Next steps

- [Quickstart](./quickstart.md) — the five-minute end-to-end loop
- [bmad.lock schema](./bmad-lock-schema.md) — what the compiler writes after each accept
- [Explain vocabulary](./explain-vocabulary.md) — provenance tags emitted by `--explain`
