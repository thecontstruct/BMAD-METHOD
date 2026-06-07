# Dev Notes Template

Pre-dev checklist for story specs on this fork. Paste this block into the Dev Notes section of every new story spec. Fill in each item before dev starts.

See also: [migration-playbook.md](migration-playbook.md) — canonical migration steps §1–§14.

---

## Dev Notes — Story \<id\>

### Engine-Frozen Invariant

The 5 pinned SHA files must remain byte-identical unless the story explicitly lifts the freeze:

- `src/core-skills/bmad-help/SKILL.md`
- `tools/installer/compiler/invoke-python.js`
- `src/core-skills/bmad-quick-dev/` (all files)
- `src/core-skills/bmad-customize/bmad-customize.template.md`
- `src/core-skills/bmad-reference-components/` (all files)

- [ ] Does this story touch any pinned file? If yes, document which AC requires it and why.
- [ ] If none are touched: state "engine-frozen: held — scope exclusion" in the spec.
- [ ] Proof after dev: `python3 -m pytest test/python/test_bmad_help_keep_contract.py` → 3/3 PASS.

### Compile Path

- [ ] Does this story compile a skill? If yes, identify module path:
  - `core-skills/<name>` for skills under `src/core-skills/`
  - `bmm/<name>` for skills under `src/_bmad/bmm/`
- [ ] Temp dir structure mirrors module path (e.g., `$WIN_TMP/core-skills/bmad-name/`).
- [ ] All `/tmp/` paths resolved via `cygpath -w` before passing to Python (see playbook §11).

### File Extraction (Upstream Port Stories)

- [ ] No `>` redirection from PowerShell for any new file.
- [ ] All Git-extracted files use Python binary write (`subprocess.run(['git','show',...], capture_output=True).stdout`).
- [ ] BOM audit run before `git add`: Python `rglob` + `read_bytes()[:3] == b'\xef\xbb\xbf'` check (see playbook §12).
- [ ] CSV/JSON files confirmed BOM-free (`open(f,'rb').read(3).hex()` ≠ `efbbbf`).

### Lockfile Schema

- [ ] Any script reading `bmad.lock` uses `lf['entries']` — NOT `lf['skills']` (see playbook §14).
- [ ] Lockfile path: `src/_bmad/_config/bmad.lock` (gitignored; not `_bmad-output/`).
- [ ] If lockfile needs regeneration: `python3 src/scripts/compile.py <module> --install-dir src/_bmad`.

### Golden Files

- [ ] Will any goldens need updating? Which skills?
- [ ] Drift is intentional (upstream update / fragment update) — not a regression.
- [ ] Batch refresh: use the `cygpath -w + compile + cp` loop from playbook §8.y.
- [ ] After refresh: `python3 -m pytest test/python/test_migration_equivalence.py -v` → all PASS.

### ComponentRunner Audit (Python-Script Ports)

- [ ] Are there new `scripts/*.py` files? If yes, complete the §6.x checklist (playbook §6.x).
- [ ] All `.py` files: stdlib-only imports confirmed.
- [ ] No `<<component>>` wiring needed (runtime CLI tools ≠ ComponentRunner inputs).
- [ ] BOM check on all `.py` files: `open(f,'rb').read(3).hex()` ≠ `efbbbf`.

### Smoke Test Plan

| Suite | Expected baseline | Command |
|---|---|---|
| Python tests | 1074 pass, 11 skipped | `python3 -m pytest test/python/ -q` |
| validate:compile | 25/25 PASS | `npm run validate:compile` |
| Engine-frozen | 3/3 PASS | `python3 -m pytest test/python/test_bmad_help_keep_contract.py` |
| npm test | all PASS | `npm test` |

**Baselines are post-Story 10.48.** If the story intentionally changes these numbers, document the new baseline here.
