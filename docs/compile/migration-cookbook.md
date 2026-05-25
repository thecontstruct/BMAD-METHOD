# Migration Cookbook

Companion to [migration-playbook.md](migration-playbook.md). Three worked examples applying the 10-step playbook to real and projected migrations.

**How to use:** find the example closest to your migration shape, then follow the playbook for the concrete commands. Navigate back from any playbook §-section to the example via the cross-reference tables below.

---

## Example 1 — Simple migration: `bmad-index-docs` (fragment-empty, Story 10.2)

**Skill:** `bmad-index-docs` | **Module:** `core-skills` | **Class:** `migration-candidate-simple` (fragment-empty subclass)
**Story:** 10.2 | **Commit:** `547c3363` | **Complexity:** S
**Diff stat:** 2 files changed, 66 insertions(+) — `bmad-index-docs.template.md` (NEW rename) + `test/fixtures/migration-goldens/bmad-index-docs/SKILL.md` (NEW)

This is the **degenerate case** — the simplest possible migration shape. `bmad-index-docs` has zero blocks matching the four spike fragments (`conventions`, `persistent-facts`, `resolver-fallback`, `config-load`). The produced template is byte-identical to the source `SKILL.md`. The compile pipeline runs end-to-end but the resolver short-circuits (parser produces a single `Text` node; no `Include` nodes to resolve).

### Pre-migration source excerpt

```markdown
---
name: bmad-index-docs
description: 'Generates or updates an index.md to reference all docs in the folder.
  Use if user requests to create or update an index of all files in a specific folder'
---

# Index Docs

**Goal:** Generate or update an index.md to reference all docs in a target folder.

## EXECUTION

### Step 1: Scan Directory

- List all files and subdirectories in the target location
```

*(66 lines total — full source at `test/fixtures/migration-goldens/bmad-index-docs/SKILL.md`.)*

### Playbook walkthrough (§1–§10)

**§1 — Source-encoding normalization**

```
python3 src/scripts/migration_normalize.py --skill src/core-skills/bmad-index-docs
```

Result: `BOM: absent` / `CRLF: absent (LF-only)` / `Non-ASCII chars: 0`. No rewrite needed.

**§2 — Character-set canonicalization decision**

Decision: `ascii-canonicalized`. Trigger: zero non-ASCII codepoints in the source (no em-dashes, arrows, or smart quotes). In Batch 1, `ascii-canonicalized` required ALL source bytes to be ASCII — the `unicode-passthrough` default applies when any non-ASCII byte is present (see §8.x in the playbook for Batch 1 charset data table).

**§3 — Pre-flight golden capture**

```
python3 src/scripts/migration_normalize.py --golden-mode \
  src/core-skills/bmad-index-docs/bmad-index-docs.template.md \
  test/fixtures/migration-goldens/bmad-index-docs/SKILL.md
```

Golden: `test/fixtures/migration-goldens/bmad-index-docs/SKILL.md` — 66 lines, LF-only bytes, `text: set eol: lf` via the directory-scope `.gitattributes` rule already present from Story 10.1.

**§4 — Classification lookup**

Manifest entry: `classification: migration-candidate-simple`, `line_count: 66`, `file_count: 1`, `subdirectories: []`, `customize_toml_keys: []`, `top_3_duplication_blocks: []`. Clean single-file skill; no sibling complications.

**§5 — Fragment extraction**

**N/A — fragment-empty migration.** Source inspection confirms zero blocks matching the four spike fragments:
- No `## Conventions` section
- No `workflow.persistent_facts` block
- No resolver-fallback dual-CLI block
- No `## Step N: Load Config` block

`grep -c '<<include' src/core-skills/bmad-index-docs/bmad-index-docs.template.md` → **0**

The template has zero `<<include>>` directives. This is the primary teaching point of Example 1: when a skill has no fragment-matching blocks, the template == source verbatim and the compiler acts as a trivial passthrough.

**§6 — Component extraction**

**N/A.** No `components/*.py` files; no `<ComponentName />` self-closing tags in the source.

**§7 — Template authoring**

Fragment-empty path (playbook §7.x):

```bash
cp src/core-skills/bmad-index-docs/SKILL.md \
   src/core-skills/bmad-index-docs/bmad-index-docs.template.md
git rm src/core-skills/bmad-index-docs/SKILL.md
```

The template is byte-identical to the deleted source. Zero `<<include>>` directives authored. No frontmatter changes. The git rename stat (`SKILL.md → bmad-index-docs.template.md`) shows 0 changes for this reason.

No VarRuntime normalization (§7.y) needed — the source has no `{{double-brace}}` placeholders.

**§8 — Byte-equivalence verification**

```
python3 -m pytest \
  "test/python/test_migration_equivalence.py::test_migration_equivalence[bmad-index-docs-golden]" \
  -v
```

Result: **1 passed, 0 deviations.** The parametric harness auto-discovered the new golden via `_iter_goldens()` — `test_migration_equivalence.py` was NOT modified (EPICS cross-cutting invariant held; harness is parametric over `test/fixtures/migration-goldens/*/SKILL.md`). `migration_equivalence_exceptions.json` entry for `bmad-index-docs`: absent (empty dict).

SHA-256 of compiled output matches golden exactly — the engine's `_compile_core → parser.parse → varcompile.compile → io.write_text` path is a trivial passthrough for a zero-include template.

**§9 — Lockfile regeneration**

```
python3 src/scripts/compile.py --skill src/core-skills/bmad-index-docs \
  --install-dir src/_bmad
```

Lockfile entry (v2 schema, current — v3 ships in Story 10.26):

```json
{
  "skill": "core/bmad-index-docs",
  "fragments": [],
  "components": [],
  "compiled_hash": "<sha256-matching-golden>",
  "source_hash": "<sha256-of-template>"
}
```

`fragments: []` is correct for a fragment-empty migration — `lockfile.py:197-198` iterates `dep_tree[1:]`, so the root template (`dep_tree[0]`) is excluded; with zero `<<include>>` directives, `dep_tree` has only the root, yielding an empty fragments array.

**§10 — Override survey + sign-off**

```bash
grep -l bmad-index-docs _bmad/custom/*.toml 2>/dev/null  # exit non-zero (no matches)
grep -rl bmad-index-docs _bmad/custom/fragments/ 2>/dev/null  # exit non-zero (no matches)
```

Override survey: empty. No pre-migration customizations to validate. No deprecation entries needed.

### Playbook cross-reference table

| Playbook § | What this example shows |
|---|---|
| §1 | Clean ASCII source — normalize is a no-op; stdout confirms 0 non-ASCII |
| §2 | `ascii-canonicalized` decision — trigger is zero non-ASCII bytes in source |
| §3 | Golden capture from template path (not deleted SKILL.md); golden = source bytes |
| §4 | `migration-candidate-simple`; all manifest fields confirm single-file shape |
| §5 | **Fragment-empty case** — zero `<<include>>` directives; `grep -c '<<include'` = 0 |
| §6 | N/A — no Python component logic |
| §7 | §7.x fast-path: `cp` + `git rm`; template == source; no directive authoring |
| §8 | Parametric harness auto-discovers golden; 0 deviations; exceptions dict empty |
| §9 | `fragments: []` in lockfile — correct outcome for zero-include dep_tree |
| §10 | Both survey greps exit non-zero; no deprecation entries |

---

## Example 2 — Multi-file migration preview: `bmad-prd` (⚠️ FORWARD-LOOKING, Batch 4)

> **⚠️ FORWARD-LOOKING.** This example is authored before Batch 4 opens (Sub-batch 4a engine extensions — Stories 10.25–10.27 — must ship first). It is grounded in Architecture §7 and the EPICS Batch 4 table. Verify against the actual Story 10.28 diff once it closes. The engine work required by this migration class (`artifacts:` frontmatter, lockfile v3) does not exist at Story 10.8 dispatch time.

**Projected target:** `bmad-prd` | **Module:** `bmm` | **Class:** `migration-candidate-multi-file`
**Story:** 10.28 | **Sub-batch 4b** | **Complexity:** M
**Expected subdirs:** `assets/`, `steps/` (2 subdirectories confirmed in EPICS Batch 4 table)
**Expected fragments:** `conventions`, `persistent-facts`, `resolver-fallback`, `config-load`, `workflow-activation`
**FR-3 `artifacts:` declared:** YES — `assets/*` templates emitted as scaffold-verbatim siblings

### What makes this a multi-file migration

`bmad-prd` has `assets/` and `steps/` subdirectories under its skill root (any subdirectory under a skill root triggers the `multi-file` classification per Arch §10, ARC-OQ-3 decision). The compiled install artifact is NOT just `SKILL.md` — it also includes the template files from `assets/` that the skill emits to the user's project as PRD scaffolds.

### Template frontmatter: the `artifacts:` array (FR-3)

Multi-file skills that emit user-facing scaffold files declare them in the template's YAML frontmatter using the `artifacts:` array mechanism (Arch §4.1, FR-3 — ships in Story 10.25):

```yaml
---
name: bmad-prd
description: '...'
artifacts:
  - path: assets/prd-template.md
    source: assets/prd-template.md
    kind: scaffold-verbatim
  - path: assets/prd-shim.md
    source: assets/prd-shim.md
    kind: scaffold-verbatim
---
```

Each artifact entry names the `path` (install-relative), the `source` (skill-dir-relative source file), and the `kind`:
- `scaffold-verbatim` — copied byte-for-byte; content not compiled
- `compiled` — run through the compile pipeline (for artifact templates that use `<<include>>`)

### Lockfile v3: the `artifacts` field (FR-4)

Lockfile v3 schema (Story 10.26) adds an `artifacts: []` array to each entry:

```json
{
  "skill": "bmm/bmad-prd",
  "fragments": ["_shared/fragments/conventions.md", "..."],
  "components": [],
  "compiled_hash": "...",
  "source_hash": "...",
  "artifacts": [
    { "path": "assets/prd-template.md", "kind": "scaffold-verbatim", "hash": "..." },
    { "path": "assets/prd-shim.md",     "kind": "scaffold-verbatim", "hash": "..." }
  ]
}
```

`ArtifactDrift` detection (FR-5, Story 10.27) compares the installed artifact hashes against the lockfile `artifacts[].hash` values on each `bmad upgrade` run — if a scaffold file is modified post-install, drift fires.

### `steps/` subdirectory handling

`steps/` files typically contain workflow step content referenced from the main `SKILL.md`. For Epic 10, `steps/` files are treated as either `scaffold-verbatim` artifacts (if they are emitted to the user's workspace) or as compile-time `<<include>>` fragments (if they feed into the compiled `SKILL.md` body). The Story 10.28 spec will determine which pattern applies for `bmad-prd`'s step files at migration time.

---

## Example 3 — Parameterized-activation extraction: `agent-activation.md` (⚠️ FORWARD-LOOKING, Batch 3)

> **⚠️ FORWARD-LOOKING.** This example is authored before Batch 3 opens (Story 10.19 extracts `agent-activation.md`; depends on Stories 10.0, 10.1, 10.7, 10.8). It is grounded in Architecture §6 and the EPICS Batch 3 table. Verify against the actual Story 10.19 diff once it closes.

**Extraction target:** `src/_shared/fragments/agent-activation.md`
**First extractor story:** 10.19 | **Extracting skill:** `bmad-agent-dev` (first Batch 3 story)
**Fragment parameters (Arch §6):** `agent_name`, `agent_role`, `agent_icon`, `agent_kind`
**Projected consumers:** 6 agent skills (Stories 10.19–10.24)
**Complexity:** M (Story 10.19 — extracts the fragment; 10.20–10.24 are S)

### The `<<include>>` directive with named parameters

For `bmad-agent-dev` (agent name: Amelia, Story 10.19), the template's activation block is replaced by:

```markdown
<<include path="_shared/fragments/agent-activation.md" agent_name="Amelia" agent_role="Senior Software Engineer" agent_icon="🧑‍💻" agent_kind="agent">>
```

This directive supplies the four parameters inline at the call site. Each Batch 3 skill uses the same `path=` value but different attribute values — only the identity data changes, not the fragment structure.

### Fragment placeholder shape

`src/_shared/fragments/agent-activation.md` (to be authored by Story 10.19) will use `{{param_name}}` double-brace syntax for the four parameters, since these are compile-time values resolved by the engine (not runtime workflow variables):

```markdown
# {{agent_name}}

*Role:* {{agent_role}}
*Icon:* {{agent_icon}}
*Kind:* {{agent_kind}}

[activation body shared across all agent skills]
```

At compile time, the engine's `VarCompile` resolution replaces `{{agent_name}}` → `"Amelia"` etc. — the compiled `SKILL.md` contains the resolved values verbatim, no placeholders.

### No new `customize.toml` keys (Arch §6 invariant)

The four `<<include>>` parameters (`agent_name`, `agent_role`, `agent_icon`, `agent_kind`) are author-controlled at include-directive time. They are intrinsic to the skill's identity and are NOT user-overridable, so they do NOT require new entries in `customize.toml`. This is the no-new-`customize.toml`-key invariant from Architecture §6.

**Exception:** if a skill already has `customize.toml.agent.icon` (a pre-existing user-overridable icon), the include line reads `agent_icon="{{self.agent.icon}}"` — the fragment receives the TOML-resolved value rather than a hardcoded literal. The invariant still holds: no new key is added to `customize.toml`; the existing key is referenced.

### Cross-consumer diff requirement (Arch §14)

Before Story 10.19 finalizes `agent-activation.md`, the author must diff the extracted block across ≥3 of the 6 projected consumer skills. If variance ≥1 line of semantic content is found, the fragment is split (parametric sub-families) or demoted (per AC-FRAG-4 protocol). At Batch 3 close, the fragment's reverse-index should list all 6 consumers.

---

*See [migration-playbook.md](migration-playbook.md) for the canonical 10-step procedure these examples apply.*
