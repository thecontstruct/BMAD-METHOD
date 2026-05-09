---
title: bmad.lock Schema Reference
description: JSON schema for _bmad/_config/bmad.lock — top-level fields, per-entry fields, and the invariants the compiler enforces.
---

Reference for the `bmad.lock` provenance file the compiler emits after each successful compile. The lockfile records what was compiled, where every fragment and variable resolved from, and what hashes correspond to each artifact. `bmad upgrade` reads the lockfile to detect drift between your installed customizations and upstream changes.

:::note[Format]

JSON, not YAML. The Python compiler is stdlib-only and `pyyaml` is banned. JSON is a strict subset of YAML so downstream tools that parse YAML can read it. Emitted with `json.dumps(sort_keys=True, indent=2)` for byte-stable diffs.

:::

## File location

```text
<install-dir>/_bmad/_config/bmad.lock
```

Always under `_bmad/_config/`. One lockfile per install. The compiler regenerates it on every successful compile that targets that install dir.

## Top-level fields

```json
{
  "bmad_version": "1.0.0",
  "compiled_at": "1.0.0",
  "version": 1,
  "entries": [...]
}
```

| Field          | Type    | Description                                                                                                  |
| -------------- | ------- | ------------------------------------------------------------------------------------------------------------ |
| `version`      | integer | Lockfile schema version. Currently `1`. Type-strict — bool, float, string, list, dict, and negative ints rejected. |
| `bmad_version` | string  | Deterministic sentinel; not a wall-clock value.                                                              |
| `compiled_at`  | string  | Also a deterministic sentinel for byte-stable output.                                                        |
| `entries`      | array   | One entry per compiled skill, sorted alphabetically by `skill`.                                              |

:::caution[Strict version field]

Story 5.5b enforces type strictness on `version`. Pre-5.5b accepted `version: 1.9` via `int()` truncation — silent data corruption. Post-5.5b rejects non-integer types with `LockfileVersionMismatchError`. To recover from a malformed lockfile, re-run `bmad install`.

:::

## Per-entry fields

Each entry records the provenance of one compiled skill:

```json
{
  "skill": "bmad-customize",
  "compiled_hash": "<sha256>",
  "source_hash": "<sha256>",
  "variant": null,
  "fragments": [...],
  "glob_inputs": [...],
  "variables": [...]
}
```

| Field           | Type           | Description                                                                                            |
| --------------- | -------------- | ------------------------------------------------------------------------------------------------------ |
| `skill`         | string         | Canonical skill name (`module/skill` or short).                                                        |
| `compiled_hash` | sha256 string  | Hash of the compiled `SKILL.md`. Validated by `validate:compile` against published artifacts.          |
| `source_hash`   | sha256 string  | Hash of the source template (`<skill>.template.md`).                                                   |
| `variant`       | string \| null | Selected IDE variant (`cursor`, `claudecode`, etc.) or `null` for the base template.                   |
| `fragments`     | array          | Every prose fragment the resolver visited. See below.                                                  |
| `glob_inputs`   | array          | TOML `file:` glob expansions resolved at compile time. Empty for skills without glob inputs.           |
| `variables`     | array          | Every TOML-resolved variable used by the template (e.g., `{{self.name}}`). See below.                  |

## fragments[] entries

```json
{
  "path": "core-skills/bmad-customize/fragments/preflight.md",
  "hash": "<sha256>",
  "resolved_from": "base"
}
```

| Field           | Type          | Description                                                                                                                       |
| --------------- | ------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `path`          | string        | Repo-relative POSIX path to the fragment as resolved.                                                                             |
| `hash`          | sha256 string | Hash of the fragment content.                                                                                                     |
| `resolved_from` | string        | Resolution tier: `base`, `variant`, `user-module-fragment`, `user-override`, or `user-full-skill`.                                |
| `override_path` | string        | Path of the override file. Present only when `resolved_from` is `user-module-fragment` or `user-override`.                        |
| `base_hash`     | sha256 string \| null | Hash of the base-tier fragment. Present only on override-tier entries; `null` when the override has no upstream base.    |
| `lineage`       | array         | Story 5.3 carry-forward of pre-upgrade hash transitions. Empty `[]` on fresh build. Present only on override-tier entries.        |

`resolved_from` tells you which tier supplied the fragment. `user-*` values mean a custom override won the resolution; `base` and `variant` mean a shipped fragment was used. The `lineage` array is how `bmad upgrade` distinguishes "user changed their override" from "upstream changed under the override".

## variables[] entries

```json
{
  "name": "self.name",
  "source": "toml",
  "source_path": "core-skills/bmad-customize/customize.toml",
  "toml_layer": "defaults",
  "value_hash": "<sha256>"
}
```

| Field         | Type          | Description                                                                                          |
| ------------- | ------------- | ---------------------------------------------------------------------------------------------------- |
| `name`        | string        | Variable name as written in the template (`self.name`, `self.description`, etc.).                    |
| `source`      | string        | Resolution source: `toml`, `bmad-config`, `runtime`.                                                 |
| `source_path` | string        | Repo-relative path to the file that supplied the value.                                              |
| `toml_layer`  | string        | TOML layer that won merge: `defaults`, `team`, or `user`. Present only when `source` is `toml`.      |
| `value_hash`  | sha256 string | Hash of the resolved value.                                                                          |
| `lineage`     | array         | Story 5.3 carry-forward of pre-upgrade value transitions. Empty `[]` on fresh build. Present only on user-layer TOML variables. |

## glob_inputs[] entries

Story 4.4 introduced TOML `file:` arrays — fields whose values resolve to file globs at compile time. Each expanded glob records:

```json
{
  "toml_key": "fragments_glob",
  "pattern": "fragments/*.md",
  "resolved_pattern": "core-skills/<skill>/fragments/*.md",
  "matches": [
    { "path": "core-skills/<skill>/fragments/preflight.md", "hash": "<sha256>" }
  ]
}
```

| Field              | Type            | Description                                                                                  |
| ------------------ | --------------- | -------------------------------------------------------------------------------------------- |
| `toml_key`         | string          | TOML key that contained the `file:` array.                                                   |
| `pattern`          | string          | Glob pattern as authored.                                                                    |
| `resolved_pattern` | string \| null  | Pattern after path normalization. `null` if the lookup is deferred.                          |
| `match_set_hash`   | sha256 string   | Aggregate hash over the sorted match set. Lets `bmad upgrade` detect set-level drift quickly without diffing each match. |
| `matches`          | array           | Every matched file with its hash. Sorted by `path` for deterministic output.                 |

## Invariants the compiler enforces

| Invariant                                                                          | Why                                                                  |
| ---------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `version` is a non-negative integer                                                | Prevent silent truncation (`1.9 → 1`) or bool coercion (`True → 1`). |
| `entries[]` sorted alphabetically by `skill`                                       | Deterministic output for byte-stable diffs.                          |
| `fragments[]` and `variables[]` hashes are sha256                                  | Cryptographically robust drift detection.                            |
| Top-level emit uses `json.dumps(sort_keys=True, indent=2)`                         | Byte-stable across platforms and Python versions.                    |
| File reads happen via `bmad_compile.io`, never raw `open()` or `pathlib`           | Library layering: `lockfile` is Layer 7 and may only call downward (e.g., `io` at Layer 2). See `src/scripts/bmad_compile/LAYERING.md`. |

:::caution[Lineage and upgrade]

The lockfile is what `bmad upgrade` reads to detect drift between your overrides and upstream changes. Story 1.5 covers provenance contract; Story 6.6 covers drift triage UX. Don't hand-edit `bmad.lock` — re-run the compiler instead.

:::

## Worked example

After compiling `bmad-customize` against the bundled install:

```json
{
  "bmad_version": "1.0.0",
  "compiled_at": "1.0.0",
  "version": 1,
  "entries": [
    {
      "skill": "bmad-customize",
      "compiled_hash": "51afdaac...",
      "source_hash": "e92fcf45...",
      "variant": null,
      "fragments": [
        {
          "path": "core-skills/bmad-customize/fragments/preflight.md",
          "hash": "4fb6ef54...",
          "resolved_from": "base"
        },
        {
          "path": "core-skills/bmad-customize/fragments/when-this-skill-cant-help.md",
          "hash": "9d9302a2...",
          "resolved_from": "base"
        }
      ],
      "glob_inputs": [],
      "variables": [
        {
          "name": "self.description",
          "source": "toml",
          "source_path": "core-skills/bmad-customize/customize.toml",
          "toml_layer": "defaults",
          "value_hash": "061a1c38..."
        },
        {
          "name": "self.name",
          "source": "toml",
          "source_path": "core-skills/bmad-customize/customize.toml",
          "toml_layer": "defaults",
          "value_hash": "54f85ec7..."
        }
      ]
    }
  ]
}
```

Hashes truncated for display. The actual file emits full sha256 strings.

## Common questions

### What if my lockfile is corrupted?

`read_lockfile_version` returns `0` for malformed JSON or non-dict top levels, allowing overwrite. Re-run `bmad install` to regenerate cleanly.

### Why not YAML?

The Python compiler is stdlib-only and `pyyaml` is banned (see `src/scripts/bmad_compile/LAYERING.md` Layer 7). JSON is a strict subset of YAML so YAML readers handle it.

### Is the lockfile machine-readable?

Yes — sorted keys, deterministic indent, sha256 hashes. Diff it with standard JSON tooling. Story 5.5b made the format byte-stable across Python versions.

## Next steps

- [Author migration guide](./author-migration-guide.md) — how the compiler builds the entries the lockfile records
- [Explain vocabulary](./explain-vocabulary.md) — `--explain` exposes the same provenance as inline XML
- [Quickstart](./quickstart.md) — see the lockfile update during the round-trip
