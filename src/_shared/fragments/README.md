# `_shared/fragments/` naming convention

Fragments live in `src/_shared/fragments/` and are included via:
```
<<include path="_shared/fragments/<name>.template.md" [key="value" ...]>>
```

## `.md` vs `.template.md`

| Suffix | Variant support | Parameter support | Use when |
|--------|----------------|-------------------|----------|
| `.md` | No | No | Static boilerplate with no IDE-specific text and no `{{placeholders}}` |
| `.template.md` | Yes | Yes | Text that varies by IDE target and/or accepts `{{param}}` substitutions |

### `.md` (plain)

Copied verbatim at resolve time. The resolver never probes for `.<ide>.md` siblings.
Example: `config-load.md`, `conventions.md`.

### `.template.md` (template)

The resolver applies Tier-4 variant selection: when `--tools claudecode` is in effect,
`foo.template.md` is superseded by `foo.claudecode.template.md` if it exists.
`{{param_name}}` placeholders are substituted with values from the `<<include>>` directive.
Example: `sub-agent-activation.template.md` (and its `.claudecode.` / `.cursor.` siblings).

## Adding a new fragment

1. Start with `.md` unless you need IDE variants or params.
2. If you need IDE variants: create the universal `.template.md` first, then add
   `.<ide>.template.md` siblings only for IDEs that need different text.
3. Parameters use `{{double_braces}}` in the fragment and `key="value"` on the include directive.
   Attribute values may not span lines or contain `"` characters.
