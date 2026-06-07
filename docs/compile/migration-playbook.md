# Migration Playbook

Canonical 10-step migration playbook for Epic 10. Authored by Story 10.1 (R0 spike). Refined empirically by Story 10.7 after Batch 1 closes.

See also:

- [migration-cookbook.md](migration-cookbook.md) — three worked examples applying these steps to real and projected migrations.
- [dev-notes-template.md](dev-notes-template.md) — pre-dev checklist for new stories on this fork.

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

> **⚠ ADVISORY — `top_3_duplication_blocks` is a heuristic (until Story 10.27 ships):** This field uses lexical similarity, not byte-equivalence-aware structural matching. Do **not** accept a fragment substitution based solely on this field — always empirically verify the candidate block against the spike fragment before treating it as a match.
>
> **Batch 1 over-claim example (Story 10.3):** `bmad-party-mode` listed `top_3_duplication_blocks: [config-load]`, but byte-inspection showed the actual block is a 2-key resolver (vs. the spike fragment's 8 resolution targets + 4 behavioral directives across 13 lines). Accepting the substitution would change observable behavior, violating NFR-4. The classifier fired on loose lexical matching ("file mentions config or load config"), not structural equivalence.
>
> Story 10.27 (FR-5 ArtifactDrift) will refine the classifier to require byte-equivalence between the candidate block and the corresponding spike fragment body. Until then, treat `top_3_duplication_blocks` as ADVISORY only.

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

**Engine caveat:** the engine emits fragment bytes VERBATIM including any HTML-comment headers. Ship fragments WITHOUT HTML-comment headers — this matches the existing `bmad-customize/fragments/*` convention and avoids byte-equivalence failures against pre-migration consumer bytes that have no such headers.

**Cross-consumer diff (mandatory):** before authoring a fragment that ≥3 consumers will share, diff against each candidate's equivalent block. Variance ≥1 line of semantic content signals SPLIT or DEMOTE per AC-FRAG-4 protocol (spike author's judgment).

### §5.x — Fragment corpus status at Batch 1 close

**Fragment families at Batch 1 close (2026-05-24):**

| Fragment family | File | Consumers at Batch 1 close |
|---|---|---|
| Conventions | `src/_shared/fragments/conventions.md` | 1 — Story 10.1 spike only |
| Persistent facts | `src/_shared/fragments/persistent-facts.md` | 1 — Story 10.1 spike only |
| Resolver fallback | `src/_shared/fragments/resolver-fallback.md` | 1 — Story 10.1 spike only |
| Config load | `src/_shared/fragments/config-load.md` | 1 — Story 10.1 spike only; DN-2 PENDING |

**Batch 1 cross-consumer diff result:** all 4 non-spike Batch 1 migrations (10.2–10.5) were fragment-empty — zero additional consumers added to any fragment family. The mandatory cross-consumer diff check above ("before authoring a fragment that ≥3 consumers will share") was not triggered in Batch 1.

**">50% corpus-wide" criterion (Arch §14): NOT YET FIRED.** At Batch 1 close, 0% of the ~37-skill migration corpus shares a fragment family beyond the spike. This criterion activates once enough Batch 2/3 skills share a fragment.

**`config-load.md` DN-2 verdict: STILL PENDING.** No Batch 1 skill exercised the config-load fragment (all 4 non-spike Batch 1 migrations were fragment-empty — zero `## Step N: Load Config` pattern matches). DN-2 defers to the first Batch 2+ skill whose source has a matching config-load block. At that point:
1. Verify the LOC savings (fragment body ≈ 13 lines; if the consumer block is byte-equivalent, the fragment is justified)
2. If justified: update `config-load.md`'s `<!-- params: ... -->` comment and record the verdict in this playbook
3. If no consumers by Batch 3 close: demote `config-load.md` to a reference-only file and remove it from the family listing above

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

### §6.x — ComponentRunner compatibility audit for Python scripts

**When this applies:** an upstream story being ported introduces new Python scripts (`scripts/*.py`) alongside the skill's SKILL.md (runtime CLI tools invoked via shell commands in SKILL.md).

**Rule:** Python scripts in a skill are scaffold-verbatim install artifacts. They are **not** ComponentRunner inputs. ComponentRunner is the compile-time `<<component>>` directive system for inlining Python-level logic into SKILL.md at build time. These are orthogonal.

**Signal:** if a Python file's first line is `#!/usr/bin/env python3` or it imports `argparse`, it is a CLI tool. If SKILL.md contains `python3 {skill-root}/scripts/...`, it is a runtime invocation. No ComponentRunner wiring needed.

**Audit checklist for any new Python script artifact:**

```bash
# 1. CLI tool check (no ComponentRunner analysis needed if true):
head -1 <script>.py  # #!/usr/bin/env python3
grep "^import argparse\|^from argparse" <script>.py

# 2. stdlib-only audit (no third-party deps allowed in scaffold-verbatim):
grep "^from\|^import" <script>.py | sort -u

# 3. No ComponentRunner wiring:
grep -c '<<component' <skill>.template.md   # → 0

# 4. BOM check before committing:
python3 -c "print(open('<script>.py','rb').read(3).hex())"  # must NOT be efbbbf

# 5. Check version floor (walrus operator requires Python 3.8+; match/case requires 3.10+):
python3 --version
```

**Empirical reference:** Story 10.48 — `brain.py` (740 lines) and `memlog.py` (202 lines) in `bmad-brainstorming` are standalone runtime CLI tools. All imports are stdlib. No ComponentRunner analysis was needed. *(10-48-brainstorming-port-retro.md L1)*

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

### §7.x — Fragment-empty migration

**When this applies:** the skill's source `SKILL.md` has zero blocks matching the spike fragments (`## Conventions`, `workflow.persistent_facts`, resolver-fallback dual-CLI block, `## Step N: Load Config`). No `<<include>>` directives will be authored. The template is a verbatim copy of the source `SKILL.md`.

**Mechanical steps (simplified from §5–§7):**

```bash
# 1. Copy source as template (no include directives added):
cp src/<module>/<skill>/SKILL.md src/<module>/<skill>/<skill>.template.md

# 2. Delete the source (compile output replaces it):
git rm src/<module>/<skill>/SKILL.md
```

No fragment authoring. No `<<include>>` directive insertion. Proceed directly to §3 (golden capture from the template) and §8 (byte-equivalence verification).

**Done when:** `src/<module>/<skill>/<skill>.template.md` exists and is byte-identical to the pre-migration source `SKILL.md` (zero `<<include>>` directives — no spike fragment blocks present in this skill); source `SKILL.md` is DELETED in the same commit.

**Harness note:** `test_migration_equivalence.py` auto-discovers fragment-empty goldens via `_iter_goldens()` — no changes to the test file are needed. AC-S6 byte-equivalence is trivially satisfied (the engine's `_compile_core → parser.parse` produces a single Text node; resolver short-circuits; output = input bytes). Batch 1 empirical confirmation: 4/4 fragment-empty migrations (10.2–10.5) passed with 0 deviations.

### §7.y — Pre-migration VarRuntime placeholder normalization

**When this applies:** the source `SKILL.md` contains `{{name}}` double-brace syntax inside `<workflow>` step content (e.g., `{{change_trigger}}`, `{{skill_name}}`). The engine's parser tokenizes `{{name}}` as a `VarCompile` node — at compile time, if the parameter is not declared in the template frontmatter, the engine raises `UnresolvedVariableError`.

**Resolution:** normalize `{{name}}` → `{name}` (single-brace) in the template BEFORE golden capture. Single-brace `{name}` is tokenized as `VarRuntime` — the engine passes it through verbatim to compiled output.

```bash
# Identify double-brace VarCompile placeholders in the source:
grep -oE '\{\{[^}]+\}\}' src/<module>/<skill>/SKILL.md

# Normalize in template (verify each {{name}} is a runtime workflow variable):
sed -i 's/{{/{/g; s/}}/}/g' src/<module>/<skill>/<skill>.template.md
```

Then **re-capture the golden** (§3) from the normalized template. Document the normalization in Dev Notes as a deliberate content change. This does NOT constitute a byte-equivalence exception-list entry — the normalized form IS the correct compiled output.

**Spike reference:** `bmad-correct-course/SKILL.md` had `{{change_trigger}}` etc. in `<workflow>` content. Story 10.1 normalized these to `{change_trigger}` in the template and golden before byte-equivalence verification.

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

### §8.x — Batch 1 empirical status (SM-7 budget)

**At Batch 1 close (Stories 10.0–10.5, 2026-05-24):**

| Metric | Value |
|---|---|
| Skills migrated | 5 (Story 10.0 spike + Stories 10.2–10.5 Batch 1) |
| Byte-equivalence deviations signed off | 0 |
| `migration_equivalence_exceptions.json` entries | 0 |
| SM-7 progress | 5 / ~37 total migration stories (13.5%) |
| SM-7 compliance | 5/5 = 100% byte-equivalent → ≥90% target met for migrated subset |

**Charset decisions (Batch 1 empirical data):**

| Story | Skill | Lines | Decision | Trigger |
|---|---|---|---|---|
| 10.2 | `bmad-index-docs` | 66 | `ascii-canonicalized` | ASCII-pure source (zero non-ASCII bytes) |
| 10.3 | `bmad-party-mode` | 128 | `unicode-passthrough` | 26 × U+2014 EM DASH |
| 10.4 | `bmad-review-adversarial-general` | 37 | `unicode-passthrough` | 5 × U+2014 EM DASH |
| 10.5 | `bmad-review-edge-case-hunter` | 67 | `unicode-passthrough` | 11 × U+2014 EM DASH |

**Trigger rule (empirically confirmed):** `ascii-canonicalized` requires ALL source bytes to be ASCII. Any U+2014 em-dash or other non-ASCII codepoint → `unicode-passthrough`.

**Quote-style decisions:** no Batch 1 quote-style decisions changed. All 4 non-spike Batch 1 migrations were fragment-empty (zero frontmatter quote-style authoring required). Fragment family quote-style decisions from Story 10.1 remain as-is.

**Fragment-family charset decisions (§2):** unchanged at Batch 1 close. All 4 families (`conventions.md`, `persistent-facts.md`, `resolver-fallback.md`, `config-load.md`) remain as authored at spike time — no Batch 1 consumer added or amended a family charset decision.

### §8.y — Golden drift: detection and batch refresh

**When this applies:** goldens in `test/fixtures/migration-goldens/` become stale when shared fragments are updated or when upstream template bodies change. Stale goldens do not block commits but fail CI test runs.

**Detection:**

```bash
python3 -m pytest test/python/test_migration_equivalence.py -v 2>&1 \
  | grep -E 'FAILED|ERROR'
```

Any `FAILED test_migration_equivalence.py::test_<skill>_matches_golden` means the compiled output drifted from the golden. An `ERROR` result means an infrastructure failure (missing import, file not found) — fix the infrastructure issue before deciding whether to refresh. Determine whether drift is intentional (upstream update → update golden) or regressive (template bug → fix template first).

**Batch refresh pattern (intentional drift only):**

**Prerequisite:** all skills in the list must be at a `compile.py`-discoverable location. For core-skills, `src/core-skills/<name>/` is the source. For bmm skills, `src/_bmad/bmm/<name>/` must exist (run the BMAD installer first if absent).

```bash
command -v cygpath >/dev/null 2>&1 || { echo "cygpath not found — run this loop in Git Bash"; exit 1; }
WIN_TMP=$(cygpath -w /tmp/golden-refresh)

for skill in bmad-my-skill bmad-other-skill; do
  # core-skills skills use core-skills/ module path; bmm skills use bmm/
  if [ -d "src/core-skills/$skill" ]; then
    MODULE="core-skills/$skill"
  else
    MODULE="bmm/$skill"
  fi
  mkdir -p "$WIN_TMP/$MODULE"
  python3 src/scripts/compile.py "$MODULE" --install-dir "$WIN_TMP" \
    || { echo "compile failed for $skill"; exit 1; }
  cp "$WIN_TMP/$MODULE/SKILL.md" "test/fixtures/migration-goldens/$skill/SKILL.md"
done

# Verify all pass:
python3 -m pytest test/python/test_migration_equivalence.py -v
```

**Rule:** only refresh goldens when the compiled output is intentionally changed (upstream body update, shared fragment update with Phil sign-off). If tests fail unexpectedly, investigate root cause before refreshing.

**Empirical reference:** Story 10.47 — 17 pre-existing stale goldens blocked the clean test run. Root cause was an activation-complete wording change propagated to 17 skills without golden updates. The batch-compile loop above resolved all 17 in one pass. *(10-47-upstream-sync-retro.md L4)*

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

**⚠ Pitfall — do NOT commit sibling assets alongside the template.** Unless a deliberate source-of-truth-shadow decision is recorded in the story spec (with rationale), commit ONLY `<skill>.template.md` (and the deleted source `SKILL.md`). Non-markdown sibling files placed in the migration tree (e.g., `checklist.md`, `customize.toml`) are bypassed at install time — the marketplace-source copy is canonical (see §10.5 below).

*Story 10.1 exception:* the R0 spike committed `checklist.md` + `customize.toml` at `src/bmm-skills/4-implementation/bmad-correct-course/`. Whether these are intentional source-of-truth shadows or dead code is deferred to Story 10.27a (FR-3 retroactive amendment opportunity). Until 10.27a resolves this, do not replicate the pattern in Batch 2+ stories without explicit spec-level rationale.

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

### §10.5 — Sibling-asset propagation

Migration compile emits **only** the compiled `SKILL.md`. Non-markdown sibling files at the skill root (CSVs, JSONs, TOML configs, checklists, etc.) do **not** propagate via the migration path. Instead, they reach the install destination via the marketplace-source `_installOfficialModules → copyModuleWithFiltering` path, which copies the entire pre-migration source tree.

**Pre-FR-3 (before Story 10.25 ships):** as a migration author, you need no special action for sibling assets. The marketplace path handles them automatically when the channel is reachable.

**Pre-FR-3 caveat:** for offline or disconnected installs, sibling assets sourced from the marketplace may be missing. See Story 10.43 investigation seed (sprint-status 2026-05-23) — this gap is not yet empirically verified or closed.

**Post-FR-3 (Story 10.25+):** prefer the `artifacts:` frontmatter mechanism in the skill template to make the migrated skill marketplace-independent. See Story 10.27a for the first FR-3 consumer (`bmad-advanced-elicitation`), which serves as the smoke test for the `artifacts:` mechanism.

---

## §11 — Windows / Git Bash path handling

**Why it matters:** Git Bash maps `/tmp/` to an MSYS2 virtual path that Python's `open()` cannot resolve as a native Windows path. Any shell compile step that passes a `/tmp/` path directly to Python will raise `FileNotFoundError` or produce a silently wrong path.

**The rule:** before passing any `/tmp/` path to Python, resolve to the Windows native form via `cygpath -w`.

```bash
# Pattern — always use this when a compile step touches /tmp/ on Windows:
WIN_PATH=$(cygpath -w /tmp/my-compile-dir)
mkdir -p "$WIN_PATH/core-skills/bmad-my-skill"
python3 src/scripts/compile.py core-skills/bmad-my-skill --install-dir "$WIN_PATH"
```

The temp dir structure must mirror the module path: if the module path is `core-skills/bmad-my-skill`, create `$WIN_PATH/core-skills/bmad-my-skill/` before invoking `compile.py`.

**Empirical reference:** Story 10.47 — compiling `bmad-party-mode` from a Git Bash `/tmp/pm-compile/` path raised `FileNotFoundError`. Fixed by resolving to the native Windows path via `cygpath -w`. *(10-47-upstream-sync-retro.md L1)*

---

## §12 — BOM-proof file extraction from Git

**Why it matters:** PowerShell 5.1's `>` redirection, `Out-File -Encoding UTF8`, and `Set-Content -Encoding UTF8` all write **UTF-8 WITH BOM** (`EF BB BF`). For `.py` files Python silently strips the BOM, but for CSV and JSON files the BOM is fatal:

- `csv.DictReader` with `encoding="utf-8"`: first column becomes `﻿category` (BOM prepended), causing `KeyError` on every row access.
- `json.load()`: raises `JSONDecodeError("Unexpected UTF-8 BOM")`.

**The rule:** never use `>` or PowerShell redirection to extract files from Git. Always use Python binary write.

```bash
# Option A — Python subprocess (preferred; works in PowerShell and Git Bash):
python3 -c "
import subprocess, pathlib
content = subprocess.run(
    ['git', 'show', '<SHA>:<path/to/file>'],
    capture_output=True
).stdout   # raw bytes — no BOM
pathlib.Path('dest/file').write_bytes(content)
"

# Option B — bash pipe (Git Bash only; bash > is stdout redirection, NOT
# PowerShell Out-File — it writes raw bytes and does NOT add BOM):
git show <SHA>:<path/to/file> | \
  python3 -c "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())" \
  > dest/file
```

**BOM audit before committing any new files:**

```python
import pathlib

for p in pathlib.Path('src/core-skills/bmad-my-skill').rglob('*'):
    if p.is_file():
        b = p.read_bytes()[:3]
        status = 'BOM' if b == b'\xef\xbb\xbf' else 'ok'
        print(status, p)
```

**Strip BOM in-place if already present:**

```python
import pathlib

for p in pathlib.Path('src/core-skills/bmad-my-skill').rglob('*'):
    if p.is_file():
        content = p.read_bytes()
        if content.startswith(b'\xef\xbb\xbf'):
            p.write_bytes(content[3:])
            print(f'stripped: {p}')
```

**Note on `.py` files:** Python 3 silently strips BOM from `.py` files at import — the `__pycache__` bytecode exists and the file executes without error. But strip BOM from `.py` files anyway: upstream expectation is BOM-free and the check is free.

**Empirical reference:** Story 10.48 — all 18 scaffold-verbatim files for `bmad-brainstorming` were extracted via PowerShell and had BOM. The BOM in `brain-methods.csv` caused `KeyError` on `r["category"]` in the skill's own test suite. Fixed in `a9bad9b8` via the in-place strip above. *(10-48-brainstorming-port-retro.md L3, L4)*

---

## §13 — Compile path reference by skill location

**Why it matters:** the module-path argument passed to `compile.py` and `validate-compile.js` differs by skill location. Using the wrong path produces a `ModuleNotFoundError` or silent no-op.

| Skill source location | Module path | Example |
|---|---|---|
| `src/core-skills/<name>/` | `core-skills/<name>` | `core-skills/bmad-party-mode` |
| `src/_bmad/bmm/<name>/` | `bmm/<name>` | `bmm/bmad-create-story` |

**Compile invocation examples:**

```bash
# core-skills skill (e.g., bmad-party-mode):
WIN_PATH=$(cygpath -w /tmp/pm-compile)
mkdir -p "$WIN_PATH/core-skills/bmad-party-mode"
python3 src/scripts/compile.py core-skills/bmad-party-mode \
  --install-dir "$WIN_PATH"

# bmm skill (e.g., bmad-create-story):
WIN_PATH=$(cygpath -w /tmp/cs-compile)
mkdir -p "$WIN_PATH/bmm/bmad-create-story"
python3 src/scripts/compile.py bmm/bmad-create-story \
  --install-dir "$WIN_PATH"
```

**Passthrough skills:** skills with no `<<include>>` fragments (e.g., `bmad-party-mode` post-fae70152) compile as passthrough: `compiled_hash == source_hash`. The golden is byte-identical to the template body. Verification is trivial — compare `sha256sum` of template with compiled output.

**Empirical reference:** Story 10.47 — initial compile of `bmad-party-mode` failed because the temp dir was structured as `bmm/bmad-party-mode/` instead of `core-skills/bmad-party-mode/`. Required trial-and-error to discover. *(10-47-upstream-sync-retro.md L3)*

---

## §14 — Lockfile (`bmad.lock`) schema reference

**Why it matters:** any script that reads `_config/bmad.lock` to extract hashes or verify skill entries MUST use the correct top-level key. The key is `"entries"` — **not** `"skills"`.

**Prerequisite:** generate the lockfile first if absent (`python3 src/scripts/compile.py <any-module> --install-dir src/_bmad`). The file is gitignored — do not rely on `git pull` to provide it.

**Top-level schema (v3, post-Story 10.26):**

```json
{
  "version": 3,
  "entries": [
    {
      "skill": "<module>/<skill>",
      "compiled_hash": "<sha256>",
      "source_hash": "<sha256>",
      "fragments": [
        { "path": "_shared/fragments/<name>.md", "hash": "<sha256>" }
      ],
      "artifacts": [
        { "path": "<relative/path/to/artifact>", "hash": "<sha256>" }
      ],
      "deprecations": []
    }
  ]
}
```

**Note (partial schema):** additional fields may be present in practice (`bmad_version`, `compiled_at`, per-entry `components`, per-fragment `resolved_from`) — these are not documented here and are subject to change.

**Extraction pattern:**

```python
import json, pathlib

lf = json.loads(
    pathlib.Path('src/_bmad/_config/bmad.lock').read_bytes()
    .decode('utf-8-sig')  # strips BOM if present on Windows
)
# Top-level key is "entries", NOT "skills":
entry = next(
    (e for e in lf['entries'] if e['skill'] == 'core-skills/bmad-party-mode'),
    None
)
if entry:
    print('compiled_hash:', entry['compiled_hash'])
```

**Lockfile path:** `src/_bmad/_config/bmad.lock` (install-phase path, gitignored). Do NOT conflate with `_bmad-output/` — that is the workspace artifact directory.

**Empirical reference:** Story 10.47 — initial Python extraction returned empty because the code searched `data['skills']`. Reading raw JSON via `repr()` revealed the correct key is `"entries"`. *(10-47-upstream-sync-retro.md L2)*
