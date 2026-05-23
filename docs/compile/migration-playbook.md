# Migration Playbook

Canonical 10-step migration playbook for Epic 10. Authored by Story 10.1 (R0 spike). Refined empirically by Story 10.7 after Batch 1 closes.

Use this checklist when migrating a hand-authored `SKILL.md` onto the compile pipeline. Each step is a binary done/not-done gate enabled by a concrete invocation.

The order is **load-bearing** per Arch §9: source-encoding MUST precede golden capture, or BOM/CRLF bytes leak into the golden.

---

## §1 — Source-encoding normalization (FIRST)

**Why it matters:** R-1 + R-8 mitigation. Mixed BOM / CRLF / Windows-1252 bytes will silently poison both the golden and the cross-consumer diff. Normalize once at pre-flight, never re-do mid-migration.

**Done when:** the script emits "BOM: absent", "CRLF: absent (LF-only)", and a Unicode codepoint census for every `.md` file under the skill dir. Non-UTF-8 input MUST hard-fail (exit code 2).

```bash
python3 src/scripts/migration_normalize.py --skill src/<module>/<skill>
```

If output reports BOM or CRLF, the file is rewritten in-place (idempotent on already-normalized source). Re-run is a no-op.

---

## §2 — Character-set canonicalization decision

**Why it matters:** R-8 — Unicode em-dashes (U+2014), en-dashes (U+2013), and right arrows (U+2192) appear inconsistently across consumers. The first consumer of a fragment family makes the family decision; all subsequent consumers honor it. Mixed Unicode + ASCII in the same fragment family forces per-consumer sign-off churn.

**Done when:** the story Dev Notes contains a §"Character-set decisions" section naming the family decision (`unicode-preserving` or `ascii-canonicalized`) with rationale, and the fragment family is documented as bound to that decision.

```text
Decision (per Arch §13):
  - unicode-preserving (default) if any consumer in the family contains Unicode in
    the extracted block — preserves bytes verbatim.
  - ascii-canonicalized if EVERY consumer is ASCII-only AND the family is small
    enough to absorb a one-time normalization pass.
```

`migration_normalize.py --canonicalize-ascii <dir>` applies U+2013→`-`, U+2014→`--`, U+2192→`->` when the family decision is `ascii-canonicalized`. OFF by default.

---

## §3 — Pre-flight golden capture (from normalized source)

**Why it matters:** FR-12 byte-equivalence target. The golden is the contract the migrated template must reproduce. Captured AFTER §1 normalization so BOM/CRLF bytes don't leak in.

**Done when:** the golden exists at `test/fixtures/migration-goldens/<skill>/SKILL.md` with LF-only bytes (`xxd | grep -c '0d0a'` returns 0), and the directory-scope `.gitattributes` rule `* text eol=lf` is in effect.

```bash
python3 src/scripts/migration_normalize.py --golden-mode \
  src/<module>/<skill>/SKILL.md \
  test/fixtures/migration-goldens/<skill>/SKILL.md

xxd test/fixtures/migration-goldens/<skill>/SKILL.md | grep -c '0d0a'   # → 0
git check-attr eol -- test/fixtures/migration-goldens/<skill>/SKILL.md  # → eol: lf
```

The golden may have a different SHA than the pre-flight source if §1 stripped BOM/CRLF; record the new SHA in story Dev Notes §"Golden capture".

---

## §4 — Classification lookup

**Why it matters:** FR-1 — different skill classes require different sub-sections of this playbook. Simple skills (one SKILL.md, no subdirs) take the fast path; multi-file skills need extra steps for `steps/` / `templates/` directory handling; runtime-scaffold skills need FR-3 `artifacts:` frontmatter declarations.

**Done when:** the manifest at `_bmad-output/epic-10-discovery/manifest.yaml` confirms the skill's classification.

```bash
python3 -c "
import yaml
m = yaml.safe_load(open('_bmad-output/epic-10-discovery/manifest.yaml'))
e = next((x for x in m if x['name'] == '<skill>'), None)
print(e['classification'], e['line_count'], e['subdirectories'])
"
```

If the classification is `migration-candidate-runtime-scaffold`, jump to the FR-3 sub-playbook (Story 10.25+). If `migration-candidate-multi-file`, follow steps/templates dir conventions from Arch §7.

---

## §5 — Fragment extraction

**Why it matters:** Arch §6 — the top-6 dedup blocks (`conventions`, `persistent-facts`, `resolver-fallback`, `config-load`, `workflow-activation`, `agent-activation`) are extracted to `src/_shared/fragments/`. First consumer per fragment family AUTHORS the fragment; subsequent consumers REFERENCE it.

**Done when:** each shared block in the skill is either (a) authored as a new fragment with single-trailing-newline discipline AND charset HTML-comment header AND parameter HTML-comment header, OR (b) referenced via `<<include path="_shared/fragments/<name>.md" [param="value"]*>>`.

```bash
# Author new fragment (with HTML headers per Arch §6):
cat > src/_shared/fragments/<name>.md <<'EOF'
<!-- charset: unicode-preserving -->
<!-- params: <param_name> ("<value>"|"<value>") -->
<fragment body with {{param_name}} placeholders>
EOF

# Verify single trailing newline:
tail -c 2 src/_shared/fragments/<name>.md | xxd
# Expected: ...0a (single \n) — NOT 0a0a (double) and NOT just ascii (zero)
```

**Engine caveat:** the engine emits fragment bytes VERBATIM including HTML-comment headers. If pre-migration consumer bytes don't have these headers, byte-equivalence fails. Spike-time discovery: ship fragments WITHOUT HTML headers OR document headers as an intentional byte deviation in the exception list (kind enum doesn't fit — surface in retro).

**Cross-consumer diff (mandatory):** before authoring a fragment that ≥3 consumers will share, diff against each candidate's equivalent block. Variance ≥1 line of semantic content signals SPLIT or DEMOTE per AC-FRAG-4 protocol (spike author's judgment).

---

## §6 — Component extraction

**Why it matters:** Epic 10 N/A — components are Python-level logic (date probes, git introspection). Reserved per ARC-OQ-1 for future skills that need Python-level fragments. Skip for all Epic 10 migrations.

**Done when:** N/A — confirm the skill has no Python-level logic that would require a `.py` component. If it does, the skill is ineligible for Epic 10 (escalate to a separate engine-extension story).

```bash
# Quick check: does the skill have any `components/*.py` files OR
# any `<ComponentName />` self-closing tags in its SKILL.md?
ls src/<module>/<skill>/components/ 2>/dev/null
grep -E '<[A-Z][A-Za-z]*\s+[^>]*\s*/>' src/<module>/<skill>/SKILL.md || echo "no components"
```

---

## §7 — Template authoring + frontmatter quote-style decision

**Why it matters:** Arch §13 — the template's frontmatter is emitted bytes-verbatim by the engine (no YAML parser). Quote-style preservation is automatic byte passthrough. The migration's template replaces the deleted `SKILL.md` and consumes the fragments authored in §5.

**Done when:** `src/<module>/<skill>/<skill>.template.md` exists with `<<include>>` directives at the byte offsets of the pre-migration block boundaries, and the source `SKILL.md` is DELETED in the same commit.

```bash
# Verify includes are positioned correctly:
grep -c '<<include path="_shared/fragments/' src/<module>/<skill>/<skill>.template.md

# Delete the source SKILL.md (compile output replaces it):
git rm src/<module>/<skill>/SKILL.md
```

**Include placement rule:** the `<<include>>` directive line is followed IMMEDIATELY by the next content line (no blank line between include and following content) — the fragment provides its own trailing newline. Adding a blank line after the include yields a double-newline → 2 blank lines between fragment and next heading.

---

## §8 — Byte-equivalence verification

**Why it matters:** FR-10 — the load-bearing measurement that the migration preserves the user-facing bytes. SHA-256 of compiled output MUST match golden.

**Done when:** `compile_skill` produces output byte-identical to the golden, OR the deviation count ≤3 with each deviation signed off as whitespace-only in `test/python/migration_equivalence_exceptions.json`.

```bash
# Run the parametric harness:
python3 -m pytest test/python/test_migration_equivalence.py -k <skill> -v

# Manual SHA assertion if needed:
sha256sum \
  test/fixtures/migration-goldens/<skill>/SKILL.md \
  src/_bmad/<module>/<skill>/SKILL.md
# Both SHAs MUST match.
```

If the SHA mismatch is content (not whitespace), STOP — the spike-fail criterion has fired (or, for non-spike migrations, the source bytes don't match the migrated form). Investigate and fix; do NOT add a content-kind exception.

---

## §9 — Lockfile regeneration

**Why it matters:** FR-14 — the lockfile records every fragment consumed by the skill, the source tier each was resolved from, and the SHA-256 of each. Without an up-to-date lockfile, `bmad upgrade` drift detection can't fire correctly.

**Done when:** `_bmad/_config/bmad.lock`'s `entries: []` contains an entry for the skill with `fragments: []` listing each consumed fragment via `_shared/fragments/<name>.md` paths and matching SHA-256 hashes.

```bash
python3 src/scripts/compile.py <skill> --install-dir src/_bmad

# Verify lockfile entry:
python3 -c "
import json, pathlib
lf = json.loads(pathlib.Path('src/_bmad/_config/bmad.lock').read_text())
e = next(x for x in lf['entries'] if x['skill'] == '<skill>')
for f in e.get('fragments', []):
    if f['path'].startswith('_shared/fragments/'):
        print(f['path'], f['hash'])
"
```

---

## §10 — Override survey + sign-off

**Why it matters:** FR-13 — every existing customize override against the migrated skill MUST be validated against the post-migration template surface. Keys absorbed into shared fragments require a deprecation notice per Arch §15.5.

**Done when:** every `_bmad/custom/*.toml` and `_bmad/custom/fragments/*` reference to the migrated skill has been classified as (a) still-honored (no action needed), or (b) absorbed-into-fragment (emit deprecation entry into the lockfile's `deprecations: []` field — Story 10.26+).

```bash
# Find existing user overrides for the skill:
grep -l <skill> _bmad/custom/*.toml 2>/dev/null
grep -rl <skill> _bmad/custom/fragments/ 2>/dev/null

# Parse the skill's customize.toml to enumerate keys:
python3 -c "
import tomllib
with open('src/<module>/<skill>/customize.toml', 'rb') as f:
    d = tomllib.load(f)
def walk(prefix, obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            kk = f'{prefix}.{k}' if prefix else k
            if isinstance(v, dict): walk(kk, v)
            else: print(kk)
walk('', d)
"
```

For each surfaced key, verify against the migrated template's surface. If the key is absorbed into a fragment param, queue a deprecation entry for the lockfile v3 schema (Story 10.26).

---

## Spike-discovered gaps (for Story 10.7 refinement)

- **Engine HTML-comment passthrough.** Arch §6 prescribes HTML-comment headers on fragments; the engine emits them verbatim into compiled output. Pre-migration source bytes have no such headers → byte-equivalence breaks. Spike-time resolution: ship fragments WITHOUT HTML headers (matches existing `bmad-customize/fragments/*` convention). Surfaced for Story 10.7 / Arch §6 retro.
- **Pre-migration `{{name}}` runtime-placeholder syntax.** Pre-migration `bmad-correct-course/SKILL.md` had `{{change_trigger}}` etc. (double-brace) inside `<workflow>` step content. Parser treats `{{name}}` as VarCompile → UnresolvedVariableError. Spike-time resolution: normalize `{{name}}` → `{name}` (VarRuntime passthrough) in both template AND golden. Document the normalization. Future migrated skills with this pattern apply the same normalization.
- **`<<include>>` trailing-newline budget.** The directive line consumes its own trailing `\n` as part of the next Text node. Author template with NO blank line between `<<include>>` and the following content line; the fragment provides its own trailing newline.

These gaps are surfaced to Story 10.7 (playbook refinement) for empirical refinement after Batch 1 closes.
