---
title: --explain Vocabulary Reference
description: Tags emitted by compile.py --explain — purpose, attributes, and example output for every provenance element.
---

Reference for the inline XML tags `compile.py --explain` emits. Each tag carries the provenance of one resolved artifact — fragment, variable, or glob expansion — so you can trace exactly where each piece of compiled output came from.

:::note[Invocation]

```bash
python3 src/scripts/compile.py <skill> --explain --install-dir <path>
```

`--explain` is read-only; it never writes files. Combine with `--tree` for a fragment-only dependency tree, or `--json` for structured output.

:::

:::tip[Authority]

This page documents the actual tags `bmad_compile/engine.py` emits. The Story 7.5 spec listed earlier names (`TomlField`, `ProseFragmentInclude`, `VariableRef`, `VariablePassthrough`, `TomlDefaultValue`); those names did not survive into the implementation. Use the four tags below — they are what you will see in real `--explain` output.

:::

## Output shape

The whole compile output is wrapped in a root `<Include>` representing the entry-point template. Inside, the resolver emits more `<Include>` tags for each included fragment, `<Variable>` tags for resolved template variables, and `<TomlGlobExpansion>` blocks (each containing one or more `<TomlGlobMatch>` rows) for any TOML `file:` array.

Outside those tags, the document is the same Markdown the compiler would write to `SKILL.md`. The XML adds provenance without disrupting the prose.

## `<Include>` — fragment include

Wraps the root template plus every fragment the resolver visited via `<<include path="...">>`. Story 4.2 introduced the tag; Stories 4.2/4.3/4.4 grew its attributes.

**Attributes:**

| Attribute       | Description                                                                                                  |
| --------------- | ------------------------------------------------------------------------------------------------------------ |
| `src`           | Repo-relative POSIX path to the resolved fragment.                                                           |
| `resolved-from` | Resolution tier: `base`, `variant`, `user-module-fragment`, `user-override`, or `user-full-skill`.            |
| `hash`          | sha256 of the resolved fragment content.                                                                     |
| `base-hash`     | sha256 of the base-tier fragment when an override won. Lets a reader compare override vs base.               |
| `override-hash` | sha256 of the override-tier fragment. Present only when `resolved-from` is `user-module-fragment` or `user-override`. |
| `override-path` | Repo-relative path to the override file. Present only on override-tier fragments.                            |
| `variant`       | IDE variant name (e.g., `cursor`, `claudecode`). Present only when `resolved-from` is `variant`.              |

**Example:**

```xml
<Include src="bmad-help/bmad-help.template.md"
         resolved-from="base"
         hash="cd7096b2ff55b2b87e12d6b9c4c9ea13dfca78c49299a09327c97107f9531da8">
...fragment content...
</Include>
```

When a user override wins resolution, `resolved-from="user-override"` and `base-hash` carries the shipped fragment's hash for comparison. See `src/scripts/bmad_compile/resolver.py` for the full resolution priority order.

## `<Variable>` — TOML or config-resolved variable

Wraps each `{{name}}` substitution the template requested. Story 4.2 introduced the tag; fold-ins added the layer attributes.

**Attributes:**

| Attribute            | Description                                                                                       |
| -------------------- | ------------------------------------------------------------------------------------------------- |
| `name`               | Variable name as written in the template (`self.name`, `self.description`, etc.).                 |
| `source`             | Resolution source: `toml`, `bmad-config`, or `runtime`.                                           |
| `source-path`        | Repo-relative path to the file that supplied the value.                                           |
| `resolved-at`        | Static `compile-time` for now. Reserved so future runtime variables can be distinguished.         |
| `toml-layer`         | TOML layer that won merge: `defaults`, `team`, or `user`. Present only when `source="toml"`.       |
| `contributing-paths` | Semicolon-separated list of every layer's source path. Present only when more than one layer contributed. |

**Example:**

```xml
<Variable name="self.name"
          source="toml"
          source-path="core-skills/bmad-customize/customize.toml"
          toml-layer="defaults"
          resolved-at="compile-time">bmad-customize</Variable>
```

Inner text is the resolved value, with `<` and `&` XML-escaped so a value containing `</Variable>` cannot close the tag prematurely (Story 4.2 R1 P1 hardening).

:::caution[Attribute naming]
Attribute names mix underscored and hyphenated styles in the engine output. `<Include>` and `<Variable>` use hyphens (`resolved-from`, `source-path`, `toml-layer`). `<TomlGlobExpansion>` mixes both — `pattern` and `resolved_pattern` are underscored, `toml-layer` and `contributing-paths` are hyphenated. The tables below match what `bmad_compile/engine.py` actually emits.
:::

## `<TomlGlobExpansion>` — file: glob expansion

Wraps each TOML `file:` array the resolver expanded. Story 4.4 introduced the tag. One `<TomlGlobExpansion>` block per glob, sorted by `toml_key` for deterministic output.

**Attributes:**

| Attribute            | Description                                                                                                   |
| -------------------- | ------------------------------------------------------------------------------------------------------------- |
| `pattern`            | Glob pattern as authored in `customize.toml`.                                                                 |
| `resolved_pattern`   | Pattern after path normalization. `(deferred)` when the resolver could not resolve at this layer.             |
| `toml-layer`         | Layer that contributed the glob: `defaults`, `team`, or `user`.                                               |
| `contributing-paths` | Semicolon-separated source paths. Present only when more than one layer contributed.                          |

The expansion block always appears just before the root template's closing `</Include>` so the XML stays single-rooted (downstream parsers and `xmllint` rely on this).

**Example:**

```xml
<TomlGlobExpansion pattern="fragments/*.md"
                   resolved_pattern="core-skills/my-skill/fragments/*.md"
                   toml-layer="defaults">
  <TomlGlobMatch path="core-skills/my-skill/fragments/preflight.md"
                 hash="4fb6ef54..." />
  <TomlGlobMatch path="core-skills/my-skill/fragments/principles.md"
                 hash="91aa30c8..." />
</TomlGlobExpansion>
```

## `<TomlGlobMatch>` — single matched file

Always nested inside `<TomlGlobExpansion>`. One `<TomlGlobMatch>` per matched file. Self-closing. Sorted by `path` for deterministic output.

**Attributes:**

| Attribute | Description                                            |
| --------- | ------------------------------------------------------ |
| `path`    | Repo-relative POSIX path to the matched file.          |
| `hash`    | sha256 of the matched file's content.                  |

**Example:**

```xml
<TomlGlobMatch path="core-skills/my-skill/fragments/preflight.md"
               hash="4fb6ef54b17fcee29b55529c6be5f4ced92790f1325f642e99ba5ec876ac0d50" />
```

## Variants of the explain output

Three flags shape what `--explain` emits:

| Flag        | Output                                                                                                         |
| ----------- | -------------------------------------------------------------------------------------------------------------- |
| `--explain` | Markdown body with inline `<Include>` / `<Variable>` / glob tags. The default.                                 |
| `--tree`    | Fragment-only dependency tree, indented by depth, no content. Useful for spotting deeply nested includes.      |
| `--json`    | Structured JSON provenance. Equivalent information without XML wrappers; good for tooling and tests.           |

`--tree` and `--json` only have effect with `--explain`. Standalone they error.

## Reading the output

The first `<Include>` is always the root template. Walk inward to see every fragment that was inlined. `<Variable>` appears at the position the substitution happened in the source. `<TomlGlobExpansion>` blocks appear at the end so the document stays single-rooted.

When a variable resolves through multiple layers, `contributing-paths` shows the chain from `defaults` through `team` to `user`. The `toml-layer` attribute names the layer that won.

## Common questions

### Can I parse `--explain` output as XML?

Yes. The compiler escapes `<`, `&`, and quotes in attribute values and inner text so the document is single-rooted, well-formed XML. Use `xmllint` or any standards-compliant parser.

### Why are tag names different from the spec?

The Story 7.5 spec listed aspirational tag names (`TomlField`, `ProseFragmentInclude`, `VariableRef`, etc.). Stories 4.2 and 4.4 shipped the four tags above instead. The spec was not updated; this reference documents what's emitted.

### Is the explain output deterministic?

Yes. Hashes are sha256, glob matches sort by `path`, glob expansions sort by `toml_key`, and the wrapper uses `json.dumps(sort_keys=True)` semantics where applicable.

## Next steps

- [Quickstart](./quickstart.md) — see `--explain` in the round-trip
- [bmad.lock schema](./bmad-lock-schema.md) — same provenance, different format
- [Author migration guide](./author-migration-guide.md) — what each tag corresponds to in source
