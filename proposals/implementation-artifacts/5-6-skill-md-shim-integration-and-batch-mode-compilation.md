# Story 5.6 — SKILL.md Shim Integration and Batch-Mode Compilation

<!-- ENGINE-FROZEN SCOPE LIFT: compile.py gains a new --batch <skills.json> mode.
     invoke-python.js updated to call --batch instead of --install-phase.
     bmad-quick-dev/SKILL.md replaced with a lazy_compile shim (≤15 lines).
     bmad-quick-dev/bmad-quick-dev.template.md created from current SKILL.md content.
     Zero changes to any bmad_compile/ module (engine.py, lazy_compile.py, io.py,
     drift.py, lockfile.py, resolver.py, errors.py, parser.py, toml_merge.py, variants.py).
     Zero changes to upgrade.py or cross-os-determinism.yaml. -->

<!-- STORY 5.5a DEPENDENCY: Story 5.5a ships lazy_compile.py with advisory file-locks.
     Confirm Story 5.5a is merged (status: done) before starting dev.
     Story 5.4 prerequisite: lazy_compile.py with hash-based cache coherence. -->

## Story

**As a** performance-conscious user,
**I want** the SKILL.md shim updated to invoke `lazy_compile.py` instead of upstream's runtime renderer, and install-time compiles to use batch mode,
**So that** skill entry is fast and fresh installs don't pay N × 200ms interpreter startup.

## Status

ready-for-dev

## Context

Stories 5.4 and 5.5a shipped `lazy_compile.py` with hash-based cache coherence and cross-platform advisory file locking. The bmad-quick-dev skill's `SKILL.md` currently contains the full ~111-line workflow with `{project-root}` and `{skill-root}` runtime tokens interpreted by the LLM at invocation time. Upstream commit `b0d70766` (on the main branch, not yet merged to this branch) replaced this with a 2-line shim that runs `render.py` and follows what it prints to stdout. Story 5.6 implements the analogous shim on this branch using `lazy_compile.py` instead of `render.py`. **Do NOT copy the shim from commit b0d70766 verbatim** — that shim calls `render.py`, which does not exist on this branch. This story's shim must call `lazy_compile.py`.

Current install pays N Python interpreter cold-starts — one per migrated skill via `--install-phase` walking the install tree. Batch mode (`--batch <skills.json>`) reduces this to 1 cold-start for N skills: the Node installer pre-enumerates which skills need compilation, writes a JSON file, and invokes `compile.py --batch` once.

**Coordination Owner: Phil** (per project assignment). The SKILL.md shim change has skill-entry-wide blast radius — a broken shim fails every skill activation simultaneously across every install. Phil is responsible for: (1) scheduling the landing window with the SKILL.md shim upstream owner, (2) defining a staged-rollout plan (e.g., shim behind a feature flag if deployment model supports it), (3) owning the roll-forward/roll-back procedure documented below.

**Roll-forward / roll-back plan (mandatory gates):**

- **Pre-merge gate:** Full cross-OS CI on all 6 OS/arch combinations (macOS Intel + Apple Silicon, Linux x86_64 + ARM64, Windows 10/11) must pass — not the PR-default Linux-only subset. Story 7.2 integration test must pass against the candidate shim.
- **Post-merge fallback (first release only):** The SKILL.md shim includes a natural-language fallback instruction: if `lazy_compile.py` exits non-zero, the LLM should halt and report the error output to the user rather than silently continuing with stale content. This fallback instruction is removed in the following minor release once the shim is proven in production.
- **Roll-back trigger:** If ≥ 3 independent user reports of shim-originated skill-entry failure land within 7 days of release, the Coordination Owner (Phil) reverts the shim commit and pins the previous behavior in a patch release.

---

## Acceptance Criteria

### AC-1 — SKILL.md shim invokes `lazy_compile.py`; `{var}` runtime substitution removed

**Given** the bmad-quick-dev `SKILL.md` currently contains the full ~111-line workflow with `{project-root}` / `{skill-root}` runtime tokens
**When** this story ships
**Then** `src/bmm-skills/4-implementation/bmad-quick-dev/SKILL.md` is a short shim (≤ 15 lines including YAML front matter):
  - The executable block: `PYTHONPATH=_bmad/scripts python3 -m bmad_compile.lazy_compile bmad-quick-dev 2>&1`
  - The following instruction tells the LLM to follow the workflow printed to stdout
  - A fallback instruction: if the command exits non-zero, halt and report the full error output to the user — do not continue with stale or cached content
**And** `{project-root}` / `{skill-root}` runtime substitution tokens are absent from the shim body (excluding YAML front matter `description`)
**And** `src/bmm-skills/4-implementation/bmad-quick-dev/bmad-quick-dev.template.md` exists and contains the migrated workflow content (current SKILL.md content, tokens migrated per Dev Note 4)
**And** a test asserts all of:
  - `SKILL.md` contains `lazy_compile` (exact string), is ≤ 15 lines
  - `SKILL.md` does NOT contain `{project-root}` or `{skill-root}` in the non-front-matter body
  - `bmad-quick-dev.template.md` exists and is non-empty

**Pre-merge gate (process):** Full cross-OS CI (6 platform combinations, see Context) must pass before merging — verified by Coordination Owner Phil, not by automated test.

### AC-2 — Node adapter uses `--batch <skills.json>`; single interpreter cold-start

**Given** an install with N migrated skills
**When** `bmad install` invokes the compiler
**Then** `invoke-python.js` writes a `skills.json` temp file (absolute paths) and calls `python3 compile.py --batch <skills.json>` exactly once (single interpreter cold-start) via the existing `_spawnPython` helper with an args array — never a shell string
**And** `skills.json` is a JSON array; each element has `skill_dir` (absolute path to skill source directory) and `install_dir` (absolute path to install root per-entry, supporting future multi-root installs)
**And** `compile.py --batch` emits NDJSON; the schema extends `--install-phase` with one difference: per-skill `kind: "skill"` events include a boolean `"compiled"` field (`true` = recompiled, `false` = hash-skipped); the summary event retains `"compiled": <int>` count and `"errors": <int>` for parity with `--install-phase`
**And** `invoke-python.js` parses the NDJSON output and cleans up the temp `skills.json` in a `finally` block
**And** the existing `runInstallPhase` call site(s) in `tools/installer/` are migrated to `runBatchInstall`
**And** a test verifies: `runBatchInstall` spawns python3 exactly once (one cold-start) and returns `{compiled, writtenFiles, lockfilePath}` matching the parsed summary event

**Advisory perf target (not a CI gate):** Total install-time overhead ideally ≤ 10% vs N sequential cold-starts (baseline: N calls to `python3 -c "pass"`). Measured in `TestBatchPerf` (excluded from default `pytest` run via `@pytest.mark.perf`).

### AC-3 — Hash-based skip on re-install; byte-identical skill output

**Given** a re-install with no source changes (all skill hashes match the lockfile at `_config/bmad.lock` inside `install_dir`)
**When** `bmad install` runs via `--batch`
**Then** no skill `kind: "skill"` event has `"compiled": true` on the second run (i.e., `summary.compiled === 0`)
**And** the installed `SKILL.md` files remain byte-identical to the previous install (same content bytes; lockfile entries are semantically identical — same hash, same skill list, same schema version — regardless of any timestamp fields)
**And** a test asserts: running `--batch` twice in a row with no source changes produces `summary.compiled === 0` and byte-identical SKILL.md on the second run

**Advisory perf target (not a CI gate):** Total re-install overhead ideally ≤ 5% vs N sequential cold-starts. Measured in `TestBatchPerf` (excluded from default `pytest` run).

### AC-4 — Roll-forward/roll-back gates codified (process gate — human review, no automated test)

**Given** the Coordination Owner is Phil and the pre-merge gate requires full cross-OS CI
**When** the PR is filed
**Then** the PR description must list:
  - The 6 OS/arch combinations required for CI sign-off
  - The roll-back trigger condition (≥ 3 user reports in 7 days)
  - Phil as Coordination Owner with decision authority for rollback
  - Story 7.2 integration test result (if Story 7.2 exists at merge time: must pass; otherwise omit and note it as a post-ship gate)

*This AC is a process gate verified by PR review, not by an automated test. Zero automated-test rows in the coverage map.*

---

## Dev Notes

### 1. Scope: files touched

**Files to modify:**
- `BMAD-METHOD/src/bmm-skills/4-implementation/bmad-quick-dev/SKILL.md` — replace with shim (≤ 15 lines)
- `BMAD-METHOD/src/scripts/compile.py` — add `--batch <skills.json>` to the `mode` mutually exclusive group; implement `_run_batch(batch_file: Path) -> int`
- `BMAD-METHOD/tools/installer/compiler/invoke-python.js` — add `runBatchInstall`; migrate call site(s)

**Files to create:**
- `BMAD-METHOD/src/bmm-skills/4-implementation/bmad-quick-dev/bmad-quick-dev.template.md` — migrated workflow (see Note 4)
- `BMAD-METHOD/test/python/test_compile_batch.py` — unit + perf tests for `--batch` mode
- `BMAD-METHOD/test/test-batch-install.js` — JS integration test for `runBatchInstall` (co-located with `test/test-invoke-python.js`, consistent with existing JS test convention)

**Files NOT to touch (frozen):** `io.py`, `lazy_compile.py`, `engine.py`, `drift.py`, `lockfile.py`, `resolver.py`, `errors.py`, `parser.py`, `toml_merge.py`, `variants.py`, `upgrade.py`, `cross-os-determinism.yaml`, `test_lazy_compile.py`, `test_lazy_compile_concurrency.py`, `test_io.py`.

### 2. Surface-area heuristic

Markers: (1) new `--batch` compile.py mode with JSON file input, (2) `{var}` → `{{var}}` template migration in bmad-quick-dev, (3) SKILL.md shim change (blast radius: every skill activation), (4) invoke-python.js adapter change (temp-file write + NDJSON parse), (5) temp-file lifecycle management in Node (must clean up in `finally`), (6) cross-OS CI gate requirement. Count: **6 markers**. Pattern-reuse discount: partial — NDJSON output reuses `--install-phase` schema extension. **Recommended dev model: Opus** per the 6-marker threshold.

### 3. Shim anatomy — current vs. target SKILL.md

**Current SKILL.md (~111 lines):** full workflow with YAML front matter + `{project-root}`, `{skill-root}`, `{skill-name}`, `{workflow.*}` runtime tokens.

**Target SKILL.md (≤ 15 lines):**

```
---
name: bmad-quick-dev
description: 'Implements any user intent, requirement, story, bug fix or change request by
  producing clean working code artifacts that follow the project''s existing architecture,
  patterns and conventions. Use when the user wants to build, fix, tweak, refactor, add
  or modify any code, component or feature.'
---

PYTHONPATH=_bmad/scripts python3 -m bmad_compile.lazy_compile bmad-quick-dev 2>&1

Then follow the workflow it prints to stdout.

If the command exits non-zero, halt immediately and report the full error output to the user — do not proceed with stale or cached content.
```

**Invocation form (ECH-8 resolved — Option A):** `PYTHONPATH=_bmad/scripts python3 -m bmad_compile.lazy_compile bmad-quick-dev 2>&1`

`lazy_compile.py` uses package-relative imports (`from . import engine, errors, io`) and CANNOT be run via direct path (`python3 /path/to/lazy_compile.py`). The `-m` form with `PYTHONPATH=_bmad/scripts` resolves the package from the well-known install dir. `2>&1` redirects stderr so the LLM captures error output. No wrapper file is created. `_bmad` is the hardcoded install dir name; shim executes from project root (standard cwd for skill invocation).

**Shell requirement:** `PYTHONPATH=VAR cmd` prefix syntax and `2>&1` redirection are POSIX shell (bash/sh/zsh). On Windows cmd.exe or PowerShell this syntax does not work. The shim assumes a POSIX-compatible shell — consistent with the existing project convention that all `bmad` CLI tooling uses bash. Users on Windows are expected to use Git Bash or WSL. Note also that `python3` may not exist on Windows stock installs (Python installs `python.exe`); the `python3` shebang convention is the existing project-wide assumption (all of compile.py, invoke-python.js, and upgrade.py already use `python3`).

**`bmad-quick-dev.template.md`:** verbatim current SKILL.md content, with `{var}` tokens migrated per Note 4. This is compiled by `engine.compile_skill()` at install time; `lazy_compile.py` emits the compiled output to stdout when the shim is run.

**Do NOT copy the shim from commit b0d70766 verbatim** — that shim calls `render.py`, not `lazy_compile.py`. The two are unrelated.

### 4. `{var}` → `{{var}}` migration in the template source

The current SKILL.md uses these runtime tokens (LLM substitutes them at invocation time):
- `{project-root}` — appears in paths like `{project-root}/_bmad/scripts/resolve_customization.py`
- `{skill-root}` — appears in paths like `{skill-root}/customize.toml`
- `{skill-name}` — the skill directory basename
- `{workflow.*}` — workflow configuration values from the resolved TOML

These tokens must remain as `{var}` in the **compiled output** so the LLM can substitute them at runtime.

**Token handling (R2 verified):** `tools/validate-skills.js` has no TPL-01 rule — the rule does not exist on this branch. `engine.py` emits `VarRuntime` tokens verbatim as `{name}` in compiled output, so single-brace `{var}` tokens in `.template.md` source survive compilation intact. **Conclusion: keep single-brace `{var}` in `bmad-quick-dev.template.md` — no migration needed.**

Confirm this by running `python3 src/scripts/compile.py --skill src/bmm-skills/4-implementation/bmad-quick-dev --install-dir _bmad` and verifying that `{project-root}` tokens appear verbatim in the output. Capture the result in the PR description.

The step files referenced in `bmad-quick-dev.template.md` (e.g., `./step-01-clarify-and-route.md`) are prose, not fragment `{{include}}` directives, so `engine.compile_skill` passes them through verbatim — the fixture for `test_compile_batch.py` does NOT need stub step files. Use a synthetic template with no include directives.

### 5. `--batch <skills.json>` contract in compile.py

**Argparse addition:** Add `mode.add_argument("--batch", default=None, metavar="SKILLS_JSON", help="JSON file listing skills to compile in batch.")` to the existing `mode` mutually exclusive group (line 327 in compile.py, after `--install-phase`). `--install-dir` is NOT required when `--batch` is used (each JSON entry carries its own `install_dir`); change `ap.add_argument("--install-dir", required=True, ...)` at line 330 to `required=False, default=None`.

**CRITICAL — early dispatch before line 418:** Line 418 unconditionally runs `install_path = Path(args.install_dir).resolve()`. With `--batch` and no `--install-dir`, `args.install_dir is None` → `TypeError`. The `--batch` dispatch MUST occur BEFORE line 418:

```python
# in main(), immediately after validation guards (after line 404):
if args.batch:
    return _run_batch(Path(args.batch))

# line 418 only reached for non-batch modes:
install_path = Path(args.install_dir).resolve()
```

Add validation guards: `--batch` cannot be combined with `--diff`, `--explain`, `--tree`, `--json`, `--set` (var-overrides), or positional skill argument. Explicitly guard `--set` with `--batch` since per-entry variable overrides are not supported in the batch JSON contract:

```python
if args.batch and args.var_overrides:
    sys.stderr.write("error: --set cannot be used with --batch (per-entry overrides not supported)\n")
    return 1
```

(mirror the `--install-phase` guard pattern at lines 368–404 for the other flags).

**Input file (`<skills.json>`) format:**
```json
[
  {
    "skill_dir": "/absolute/path/to/src/bmm-skills/4-implementation/bmad-quick-dev",
    "install_dir": "/absolute/path/to/_bmad"
  }
]
```

Each entry must have `skill_dir` and `install_dir` as strings. Validate on read: if either key is missing or not a string, emit a `kind: "error"` NDJSON event to stdout AND write to stderr, then exit 1. Validate that both paths are absolute (`Path(skill_dir).is_absolute()`); reject relative paths with an error event + stderr + exit 1. An empty array `[]` is valid — emit a summary with `compiled: 0` and `errors: 0`.

**`_run_batch(batch_file: Path) -> int` implementation:**
1. Read and parse `batch_file`; on `FileNotFoundError` or `json.JSONDecodeError`, emit a `kind: "error"` NDJSON event (not stderr-only) and exit 1. This preserves the NDJSON contract so the JS caller's parser does not fail with "no summary event."
2. Deduplicate entries by `(skill_dir, install_dir)` pair; emit a `kind: "warning"` event for each duplicate found.
3. For each (unique) entry:
   a. Resolve `skill_dir` and `install_dir` to `Path` objects.
   b. Compute `module = Path(skill_dir).parent.name`, `dir_name = Path(skill_dir).name`.
   c. **Hash-based skip check (AC-3):** Use `entry = _lc._find_lockfile_entry(lockfile_path, dir_name)`. If entry exists and `not _lc._needs_recompile(entry, Path(install_dir))`, emit and continue:
      `{"schema_version": 1, "kind": "skill", "skill": f"{module}/{dir_name}", "written": [], "compiled": false, "status": "skipped", "lockfile_updated": false}`
   d. Otherwise: check for the full-skill override at `install_dir / "custom" / "fragments" / module / dir_name / "SKILL.template.md"` (same check as `_run_install_phase`); emit a `kind: "warning"` if present. Then call `engine.compile_skill(...)` and emit:
      `{"schema_version": 1, "kind": "skill", "skill": f"{module}/{dir_name}", "written": [str(skill_md)], "compiled": true, "status": "ok", "lockfile_updated": true}`
   e. On `CompilerError`: emit a `kind: "error"` event. **Continue processing remaining skills** (do not abort the loop) — mirror `_run_install_phase`'s catch-and-continue semantics. Set an error flag.
   f. On other exceptions (`FileNotFoundError`, `OSError`, `RuntimeError`): emit a `kind: "error"` event, continue, set error flag.
4. Emit `kind: "summary"` with `compiled: <int>`, `errors: <int>`, and `lockfile_path` (use the last `install_dir / "_config" / "bmad.lock"` path seen, or `null` if none).
5. Return 0 on success, 1 if any error occurred.

**`_needs_recompile` import note:** `lockfile.find_skill_entry(...)` does NOT exist in `lockfile.py` (only `write_skill_entry`, `_build_skill_entry`, and `read_lockfile_version` exist). For the hash-skip check, use `lazy_compile._find_lockfile_entry` and `lazy_compile._needs_recompile` via direct import — compile.py already imports from the `bmad_compile` package, so coupling is minimal:

```python
from bmad_compile import lazy_compile as _lc
# ...inside _run_batch for each entry:
lockfile_path = Path(install_dir) / "_config" / "bmad.lock"
entry = _lc._find_lockfile_entry(lockfile_path, dir_name)  # returns dict or None
if entry is not None and not _lc._needs_recompile(entry, Path(install_dir)):
    # emit compiled=false skip event and continue
```

Note: the lockfile is JSON (`{"entries": [...]}` with each entry keyed by `"skill"` basename), NOT TOML. Do not use `tomllib` for lockfile reads. `_find_lockfile_entry` handles the JSON parsing and list lookup correctly.

**Reuse opportunity:** The per-skill compile-and-emit body in `_run_install_phase` (lines 73–137) is near-identical to what `_run_batch` needs. Extract a shared helper `_compile_one_skill(dirpath: Path, install_dir: Path) -> list[dict]` that returns a list of NDJSON event dicts (zero or more warning events followed by exactly one skill or error event). Callers inspect the last event's `kind` to determine success/error and increment counters accordingly. Call it from both `_run_install_phase` and `_run_batch`. After extracting, run `--install-phase` against the existing test suite to confirm behavior is unchanged.

`LockfileVersionMismatchError` is a subclass of `CompilerError`; `_run_batch` catches `CompilerError` generically (same as `_run_install_phase`). There is no distinct exit code 2 in `--batch` mode — `LockfileVersionMismatchError` is collapsed to exit 1, same as all other errors. This is intentional parity with `--install-phase`. The error event `code` field will contain `exc.code` (e.g., `"LOCKFILE_VERSION_MISMATCH"`) so JS callers can surface it if needed.

**Dedup warning shape (step 2):** `{"schema_version": 1, "kind": "warning", "skill": f"{module}/{dir_name}", "message": "duplicate batch entry skipped"}` — same structure as the full-skill override warning emitted in step 3d.

**NDJSON schema table (--batch vs --install-phase):**

| Field | `--install-phase` skill event | `--batch` skill event |
|---|---|---|
| `schema_version` | 1 | 1 |
| `kind` | `"skill"` | `"skill"` |
| `skill` | `"module/name"` | `"module/name"` |
| `written` | `[...]` | `[...]` |
| `compiled` | *(absent)* | `true` / `false` (new field) |
| `status` | `"ok"` | `"ok"` (same as install-phase) |
| `lockfile_updated` | `true` | `true` (same as install-phase) |

**D1 resolved:** Both modes emit identical `status` and `lockfile_updated` fields, enabling the shared `_compile_one_skill` helper. The `compiled` boolean is a deliberate additive extension in `--batch` mode. The JS caller reads only `summary.compiled` (not per-skill `compiled`), so this extension does not break `runInstallPhase` behavior. Hash-skipped events (`compiled: false`) emit `status: "skipped"` and `lockfile_updated: false` since nothing was written.

Summary event for `--batch` must include `"errors": <int>` for parity with `--install-phase` summary.

**`lockfile_path` in summary:** Use `str(last_install_dir / "_config" / "bmad.lock")` (note the `str()` wrapper — `Path` is not JSON-serializable). For an empty batch (no entries), emit `"lockfile_path": null`. This diverges from `_run_install_phase` (which always emits a string); the divergence is intentional since batch has no global `install_dir` to fall back on.

**`_needs_recompile` equivalence:** `install_dir` (the `_bmad` dir passed per entry) equals `scenario_root` as defined in `lazy_compile.py` line 228 (`scenario_root = project_root / "_bmad"`). Passing `Path(install_dir)` directly to `_lc._needs_recompile(entry, Path(install_dir))` is correct.

### 6. `invoke-python.js` update

Current `runInstallPhase` (line 159) spawns `python3 compile.py --install-phase --install-dir bmadDir`. Add `runBatchInstall` alongside it:

```javascript
/**
 * Run `compile.py --batch <skills.json>` and parse the newline-delimited JSON stdout.
 *
 * @param {Object} opts
 * @param {Array<{skillDir: string, installDir: string}>} opts.skills
 * @param {string} opts.bmadDir   - Path to the installed _bmad directory (compile.py lives here)
 * @param {string} opts.projectRoot - cwd for the Python subprocess
 * @param {Function} [opts.message] - Progress callback
 * @returns {Promise<{compiled: number, writtenFiles: string[], lockfilePath: string|null}>}
 */
async function runBatchInstall({ skills, bmadDir, projectRoot, message }) {
  const compilePy = path.join(bmadDir, 'scripts', 'compile.py');
  // compile.py lives in _bmad/scripts/ (same location as runInstallPhase assumption).
  // Verify it exists before spawning to produce a friendlier error.
  try { await fs.access(compilePy); } catch {
    throw new Error(`compile.py not found at: ${compilePy}`);
  }

  const tmpFile = path.join(os.tmpdir(), `bmad-batch-${crypto.randomUUID()}.json`);
  // _spawnPython uses an args array (not a shell string) — no backslash escaping on Windows.

  const payload = skills.map(({ skillDir, installDir }) => ({
    skill_dir: path.resolve(skillDir),
    install_dir: path.resolve(installDir),
  }));

  try {
    try {
      await fs.writeFile(tmpFile, JSON.stringify(payload));
    } catch (error) {
      throw new Error(`bmad install: failed to write batch input file: ${error.message}`);
    }

    let result;
    try {
      result = await _spawnPython([compilePy, '--batch', tmpFile], { cwd: projectRoot });
    } catch (error) {
      throw new Error(`Failed to spawn python3: ${error.message}`);
    }

    const lines = result.stdout.split('\n').filter((l) => l.trim() !== '');
    const events = [];
    let firstError = null;
    for (const line of lines) {
      let event;
      try { event = JSON.parse(line); } catch {
        const sigMsg = result.signal ? ` (process killed by signal ${result.signal})` : '';
        throw new Error(`compile.py --batch emitted non-JSON line${sigMsg}:\n  ${line.slice(0, 200)}\n\nstderr:\n${result.stderr}`);
      }
      events.push(event);
      if (event.kind === 'skill' && message) message(`Compiling ${event.skill}...`);
      if (event.kind === 'error' && !firstError) firstError = event;
    }

    if (result.code !== 0 || firstError) {
      let msg = _formatError(firstError, '--batch');
      if (result.stderr.trim()) msg += `\n\nstderr:\n${result.stderr.trim()}`;
      throw new Error(msg);
    }

    const summary = events.toReversed().find((e) => e.kind === 'summary');
    if (!summary) {
      let msg = 'compile.py --batch did not emit a summary event';
      if (result.stderr.trim()) msg += `\n\nstderr:\n${result.stderr.trim()}`;
      throw new Error(msg);
    }

    const writtenFiles = [];
    for (const event of events) {
      if (event.kind === 'skill' && Array.isArray(event.written)) {
        for (const f of event.written) writtenFiles.push(f);
      }
    }
    return { compiled: summary.compiled, writtenFiles, lockfilePath: summary.lockfile_path ?? null };
  } finally {
    await fs.unlink(tmpFile).catch(() => {});
  }
}
```

**Required new imports:** Add `const os = require('node:os');` and `const crypto = require('node:crypto');` at the top of `invoke-python.js`. Both require Node 15.6+ (`crypto.randomUUID`) — already satisfied by the `Array.prototype.toReversed` baseline (Node 20+).

**`_spawnPython` signal capture:** The current `_spawnPython` resolves with `{ code, stdout, stderr }` only — it does NOT capture the process termination signal. The `runBatchInstall` snippet above references `result.signal` in the SIGKILL-aware error path. Update `_spawnPython`'s `close` handler to also capture `signal`: `proc.on('close', (code, signal) => resolve({ code, stdout, stderr, signal }))`. This is backward-compatible (adds a new field; existing callers ignore it).

**Update `_formatError`:** Add a `source` parameter with default `'--install-phase'`: `function _formatError(event, source = '--install-phase')`. Update the null-case string to use `source`: `\`compile.py ${source} failed (no error event emitted)\``. The existing call in `runInstallPhase` (`_formatError(firstError)`) requires no change. `runBatchInstall` calls `_formatError(firstError, '--batch')`.

**`hasMigratedSkillsInScope` two-call-site note:** `installer.js` calls `hasMigratedSkillsInScope` at TWO locations: line 48 (Python version preflight — before module clone) and line 267 (compile gate). Only the line 267/271 pair migrates to `enumerateMigratedSkills` + `runBatchInstall`. Line 48 stays as-is (boolean gate; source dirs may not be cloned yet). Task 4.5's "migrate all call sites" means only the line 267/271 pair.

**Export:** Add `runBatchInstall` to `module.exports` on line 268. Keep `runInstallPhase` exported — `test/test-invoke-python.js` still imports it, so removal would break the test suite. If the test file is also migrated (optional), keep `runInstallPhase` exported anyway for backward compat.

### 7. Test patterns for `test_compile_batch.py`

```python
# Perf tests use @pytest.mark.perf and are excluded from the default run.
# Register the marker in pyproject.toml or pytest.ini:
#   markers = ["perf: performance advisory tests (excluded by default)"]
# Run default suite with: pytest -m "not perf"
# Run perf suite with:     pytest -m perf

class TestShimIntegrity:
    def test_shim_contains_lazy_compile(...)          # AC-1: SKILL.md has 'lazy_compile', ≤15 lines
    def test_shim_no_project_root_token(...)          # AC-1: SKILL.md does not contain '{project-root}'
    def test_shim_no_skill_root_token(...)            # AC-1: SKILL.md does not contain '{skill-root}'
    def test_template_file_exists_and_nonempty(...)   # AC-1: bmad-quick-dev.template.md exists

class TestBatchMode:
    def test_batch_single_skill_emits_skill_event_and_summary(...)
    def test_batch_multiple_skills_emits_multiple_events_in_order(...)
    def test_batch_error_skill_emits_error_event_and_continues(...)  # ECH-2: continue on error
    def test_batch_summary_compiled_count_matches_events(...)
    def test_batch_empty_array_emits_summary_zero_compiled(...)      # ECH-1: empty array
    def test_batch_nonexistent_json_file_emits_ndjson_error_exits_1(...)  # BH-14: NDJSON error
    def test_batch_malformed_json_emits_ndjson_error_exits_1(...)
    def test_batch_missing_skill_dir_key_exits_1(...)                # ECH-4: validation
    def test_batch_relative_path_exits_1(...)                        # ECH-4: absolute path required
    def test_batch_duplicate_entries_compile_once(...)               # ECH-10: dedup

class TestHashSkip:
    def test_batch_second_run_summary_compiled_zero(...)             # AC-3: no recompiles
    def test_batch_second_run_skill_md_byte_identical(...)
    def test_batch_second_run_lockfile_semantically_identical(...)   # AC-3: same hash entries

class TestBatchPerf:
    @pytest.mark.perf
    def test_batch_install_overhead_advisory(...)    # compare vs N cold-starts; wide margin
    @pytest.mark.perf
    def test_batch_reinstall_overhead_advisory(...)
```

Fixture approach: use `tmp_path` + a minimal synthetic skill fixture (just `<skill-name>.template.md` with no external fragment references — `customize.toml` is NOT required by `engine.compile_skill`; existing test fixtures in `test/python/test_lazy_compile.py` omit it). Do not use mocks for the engine in `TestHashSkip` — run the real engine against the fixture to keep hash-skip logic meaningful. Confirm the lockfile is written at `_config/bmad.lock` inside `install_dir` so the skip-check path resolves correctly.

**`compiled` field naming note:** In the NDJSON schema, per-skill events have `compiled: bool` (was this skill recompiled?) and the summary event has `compiled: int` (how many skills were recompiled?). These share a field name but different types. Future maintainers should be aware; consider renaming per-skill to `was_compiled` in a future schema version. For this story, the names match the spec as written.

---

## Tasks

### Task 1: Create `bmad-quick-dev.template.md` from current SKILL.md

- 1.1 Copy `BMAD-METHOD/src/bmm-skills/4-implementation/bmad-quick-dev/SKILL.md` to `bmad-quick-dev.template.md` in the same directory
- 1.2 Run `python3 src/scripts/compile.py --skill src/bmm-skills/4-implementation/bmad-quick-dev --install-dir _bmad` and confirm `{project-root}` tokens appear verbatim in the output (TPL-01 doesn't exist; single-brace `{var}` is already confirmed correct by R2)
- 1.3 No token migration needed — keep source as-is with single-brace `{var}`
- 1.4 Capture the compile output for PR description

### Task 2: Write SKILL.md shim

- 2.1 Verify `PYTHONPATH=_bmad/scripts python3 -m bmad_compile.lazy_compile bmad-quick-dev` resolves cleanly from the project root (run once manually from `BMAD-METHOD/` or a test project root to confirm no ImportError; exit code 0 expected when lockfile is current)
- 2.2 Write new `SKILL.md` (≤ 15 lines) per Dev Note 3 anatomy: YAML front matter → `PYTHONPATH=_bmad/scripts python3 -m bmad_compile.lazy_compile bmad-quick-dev 2>&1` → follow-stdout instruction → error-halt fallback
- 2.3 Verify shim contains `lazy_compile`, is ≤ 15 lines, has the error-halt fallback instruction, and does NOT contain `{project-root}` or `{skill-root}` outside YAML front matter

### Task 3: Add `--batch <skills.json>` mode to compile.py

- 3.1 Extract shared `_compile_one_skill(dirpath, install_dir) -> tuple[dict, list[dict]]` from `_run_install_phase`; run `--install-phase` test to confirm no regression before proceeding
- 3.2 Change `ap.add_argument("--install-dir", required=True, ...)` to `required=False, default=None`; add the `--batch` early-dispatch block BEFORE line 418's `Path(args.install_dir).resolve()` (see Dev Note 5 — this is mandatory to prevent TypeError); the `--install-phase` branch at line 420 already validates `install_path.is_dir()`, which implicitly requires it
- 3.3 Add `--batch` to the `mode` mutually exclusive group (after `--install-phase`); add all validation guards
- 3.4 Implement `_run_batch(batch_file: Path) -> int` per Dev Note 5 (read JSON, validate, dedup, hash-skip with `_config/bmad.lock` path, compile, continue-on-error, emit NDJSON)
- 3.5 Wire `--batch` dispatch in `main()` (analogous to `--install-phase` at line 420–424)

### Task 4: Update `invoke-python.js`

- 4.1 Add `const os = require('node:os');` and `const crypto = require('node:crypto');` imports
- 4.2a Update `_spawnPython`'s `close` handler to also capture `signal`: `proc.on('close', (code, signal) => resolve({ code, stdout, stderr, signal }))` (backward-compatible; existing callers ignore the new field)
- 4.2 Implement `runBatchInstall({skills, bmadDir, projectRoot, message})` per Dev Note 6 (includes `fs.access` preflight, friendly write-failure message, SIGKILL-aware error path)
- 4.3 Update `_formatError` to generalize the mode string (remove hardcoded `--install-phase` reference)
- 4.4 Export `runBatchInstall` from `module.exports`
- 4.5 **Migrate all call sites:** Run `grep -r 'runInstallPhase\|--install-phase' tools/installer/` and update every call site to use `runBatchInstall`. The `skills` array must be constructed from the enumerated migrated skills (Task 4.6). Verify grep returns zero results for `runInstallPhase` in production code (test files may retain it for backward-compat testing).
- 4.6 **Enumerate skills for batch:** Add `enumerateMigratedSkills(paths, modules, officialModules)` to `invoke-python.js` returning `Promise<Array<{skillDir: string, installDir: string}>>`. Key requirements:
  - `skillDir` = the matched skill source directory (full path, e.g., `.../src/bmm-skills/4-implementation/bmad-quick-dev`); `installDir` = `paths.bmadDir` (same for all entries in a single-root install).
  - Must collect ALL matching skills across the entire source tree — do NOT short-circuit on first match (unlike `_hasSkillsInTree` which returns `true` early). Write a separate `_collectSkillsInTree(dirPath, depth, maxDepth, results)` accumulator or refactor `_hasSkillsInTree` to fill an array.
  - Use `officialModules.findModuleSource(moduleCode)` to get the module source root, then walk it for skills — same pattern as `hasMigratedSkillsInScope`.
  - On `findModuleSource` throw (network error): return an empty array AND log a warning — do NOT propagate the throw, so the boolean preflight at line 48 still gates the Python version check separately. This mirrors `hasMigratedSkillsInScope`'s `return true` on throw (the boolean gate pessimistically assumes skills exist; the enumerator optimistically returns empty on error, which means zero skills are compiled, which is safe — the installer already checked Python version before reaching the compile step).

### Task 5: Write tests and verify

- 5.1 Write `test_compile_batch.py` covering `TestShimIntegrity`, `TestBatchMode`, `TestHashSkip`, `TestBatchPerf` (Dev Note 7); register `perf` pytest marker by adding the following section to `pyproject.toml` (the project has no `pytest.ini`; `pyproject.toml` already has `[tool.mypy]` but lacks `[tool.pytest.ini_options]`):
  ```toml
  [tool.pytest.ini_options]
  markers = ["perf: performance advisory tests (excluded by default)"]
  ```
  Without this, `@pytest.mark.perf` triggers `PytestUnknownMarkWarning` and `-m "not perf"` does not correctly exclude the tests.
- 5.2 Create `test/test-batch-install.js` (not in `tools/installer/compiler/` — follow existing convention: all JS tests live in `test/`, e.g., `test/test-invoke-python.js`); cover: single cold-start, NDJSON parse, graceful failure on non-existent compile.py
- 5.3 Run full Python test suite: `python3 -m pytest test/python/ -m "not perf" -x --tb=short` — must pass all prior tests
- 5.4 Run mypy: `mypy --strict src/scripts/compile.py src/scripts/bmad_compile/` — must be clean
- 5.5 Run npm test: `npm test` from `BMAD-METHOD/`
- 5.6 Verify test count delta: new tests should push total meaningfully higher than 479 (current after 5.5a)

### Task 6: Sprint tracking and docs

- 6.1 Mark this story `in-progress` in `sprint-status.yaml` when starting dev; `review` when complete
- 6.2 Confirm `**/.compiling.lock` is already in `.gitignore` (added in 5.5a)
- 6.3 Confirm temp batch JSON files (in `os.tmpdir()`) are not in the repo — no `.gitignore` change needed since they live outside the project root

---

## Open Questions

1. ~~**`{var}` migration mechanics:**~~ **RESOLVED (R2):** `tools/validate-skills.js` has NO TPL-01 rule. `engine.py` emits `VarRuntime` tokens verbatim. Single-brace `{var}` in `bmad-quick-dev.template.md` is correct — no migration needed. Confirm with a test compile per Dev Note 4.

2. ~~**`_needs_recompile` reuse vs inline:**~~ **RESOLVED (R1):** Use `lazy_compile._find_lockfile_entry` + `lazy_compile._needs_recompile` via direct import. The lockfile is JSON (not TOML), and the schema uses an `"entries"` list (not a `"skills"` dict) — inline re-implementation would need to replicate the same JSON+list logic, making `_find_lockfile_entry` the safer and simpler choice. compile.py already imports from the `bmad_compile` package so coupling is minimal.

3. ~~**Lockfile timestamp sensitivity:**~~ **RESOLVED (R1):** `bmad.lock` has NO wall-clock timestamp fields. `compiled_at` and `bmad_version` are both set to the deterministic sentinel `"1.0.0"`. Two identical compiles produce byte-identical lockfiles. `TestHashSkip` tests may assert byte-identical lockfile content (not just semantic equality).

4. ~~**`enumerateMigratedSkills` design:**~~ **RESOLVED (R1):** `enumerateMigratedSkills` belongs in `invoke-python.js` alongside `hasMigratedSkillsInScope` (same discovery logic, same inputs). For a single-root install, `installDir` is `paths.bmadDir` for every skill entry.

5. ~~**`bmad_compile` importability from arbitrary cwd:**~~ **RESOLVED (R1/ECH-8 — Option A):** `PYTHONPATH=_bmad/scripts python3 -m bmad_compile.lazy_compile bmad-quick-dev 2>&1`. No wrapper file. `_bmad` is the hardcoded install dir name; shim runs from project root. See Dev Note 3 for rationale.

---

## Coverage Impact

See `epic-5-coverage-map.md` — rows for Story 5.6 added at the bottom of that file.

---

## Senior Developer Review (AI)

### R1 — Accuracy pass (Sonnet, 2026-05-05)

**9 patches applied. 1 item DECISION-NEEDED (ECH-8).**

| ID | Severity | Finding |
|----|----------|---------|
| P1 | CRITICAL | Dev Note 5 inline lockfile example used `tomllib` — lockfile is JSON, not TOML. Fixed to use `json` via `lazy_compile._find_lockfile_entry`. |
| P2 | CRITICAL | Dev Note 5 inline lookup used `lf.get("skills",{}).get(dir_name)` — actual schema is `{"entries": [{...}]}` list. Fixed to use `_find_lockfile_entry`. |
| P3 | Resolution | OQ-2 resolved: direct import of `lazy_compile._find_lockfile_entry + _needs_recompile` preferred over inline (P1+P2 confirmed inline approach was wrong). |
| P4 | Resolution | OQ-3 resolved: lockfile has no wall-clock timestamp (`compiled_at = "1.0.0"` sentinel). TestHashSkip may assert byte-identical content. |
| P5 | Accuracy | Task 5.6: test count updated 470 → 479 (actual measured via `pytest --collect-only`). |
| P6 | Code bug | Dev Note 6 `runBatchInstall` snippet referenced `result.signal` but `_spawnPython` doesn't capture signal. Added Task 4.2a to fix `_spawnPython`; updated Dev Note 6. |
| P7 | Accuracy | Dev Note 5 `_run_install_phase` body line range: "~73–130" → "73–137" (verified). |
| P8 | Missing context | Dev Note 3: added explicit note that `lazy_compile.py` uses relative package imports and CANNOT be run as a direct script — informs ECH-8/OQ-5. |
| P9 | Resolution | OQ-4 resolved: `enumerateMigratedSkills` belongs in `invoke-python.js`; `installDir = paths.bmadDir` for all entries in single-root install. |
| ECH-8 | Resolved | OQ-5: **Option A chosen** — `PYTHONPATH=_bmad/scripts python3 -m bmad_compile.lazy_compile bmad-quick-dev 2>&1`. No wrapper file. Spec amended in AC-1, Dev Note 3, Task 2, and OQ-5. |

### R2 — Deep review (Opus, 3-agent fan-out, 2026-05-05)

**26 findings across 3 domains. 0 DECISION-NEEDED (both design questions resolved by principle). All 26 patches applied.**

| ID | Sev | Domain | Finding → Patch |
|----|-----|--------|----------------|
| R2-P1 | CRITICAL | compile.py | `--batch` dispatch MUST precede `Path(args.install_dir).resolve()` (line 418) — TypeError otherwise. Added early-return pattern before line 418 in Dev Note 5 and Task 3.2. |
| R2-P2 | CRITICAL | compile.py | `_compile_one_skill` return type `tuple[dict,list[dict]]` was unworkable given closure variables and error/success branching. Changed to `list[dict]` (events in order). |
| R2-P3 | CRITICAL | JS | `enumerateMigratedSkills` cannot reuse `_hasSkillsInTree`'s early-exit semantics — must collect ALL skills. Updated Task 4.6 with explicit walker requirement. |
| R2-P4 | CRITICAL | SKILL.md | "follow the instruction it prints to stdout" misdescribes full ~111-line workflow output. Fixed to "follow the workflow it prints to stdout". |
| R2-D1 | CRITICAL | schema | Schema asymmetry: `status`+`lockfile_updated` omitted in batch events contradicted shared helper goal. Resolved: batch includes both fields (`"status": "ok"/"skipped"`, `"lockfile_updated": true/false`). Updated NDJSON table and step 3c/3d emit blocks. |
| R2-P5 | HIGH | compile.py | `LockfileVersionMismatchError` — document deliberate collapse to exit 1 in batch (parity with `--install-phase`). |
| R2-P6 | HIGH | compile.py | `--set` with `--batch` undefined. D2 resolved: reject with guard error. Added explicit guard to Dev Note 5. |
| R2-P7 | HIGH | JS | Two `hasMigratedSkillsInScope` call sites — only installer.js:267 migrates; line 48 stays as boolean gate. Clarified in Dev Note 6. |
| R2-P8 | HIGH | JS | `findModuleSource` network-error fallback must be preserved in `enumerateMigratedSkills`. Updated Task 4.6. |
| R2-P9 | HIGH | JS | `_formatError` snippet called without mode arg — batch errors would say `--install-phase`. Fixed snippet to pass `'--batch'`; Task 4.3 updated. |
| R2-P10 | HIGH | JS | `skillDir` must be the matched skill source dir (not module root). Clarified in Task 4.6. |
| R2-P11 | HIGH | SKILL.md | Cross-OS PYTHONPATH + `python3` Windows assumptions not documented. Added POSIX shell + `python3` notes to Dev Note 3. |
| R2-P12 | HIGH | SKILL.md | Story 7.2 gate is aspirational (file doesn't exist). AC-1 + AC-4 updated to conditional. |
| R2-P13 | MEDIUM | compile.py | Dedup warning shape unspecified. Added example `{"kind": "warning", "message": "duplicate batch entry skipped"}`. |
| R2-P14 | MEDIUM | compile.py | `install_dir == scenario_root` equivalence not stated. Added clarifying comment. |
| R2-P15 | MEDIUM | compile.py | Empty-batch `lockfile_path: null` diverges from `_run_install_phase`. Documented in schema table. Added `str()` wrapper note. |
| R2-P16 | MEDIUM | compile.py | `pyproject.toml` has no `[tool.pytest.ini_options]`. Added concrete TOML snippet to Task 5.1. |
| R2-P17 | MEDIUM | SKILL.md | `enumerateMigratedSkills` resolution in OQ-4 understated — actual implementation complexity noted. Updated Task 4.6. |
| R2-P18 | MEDIUM | JS | `runInstallPhase` still imported by `test/test-invoke-python.js` — must keep exported. Updated Dev Note 6. |
| R2-P19 | LOW | SKILL.md | TPL-01 rule phantom — doesn't exist in `tools/validate-skills.js`. Simplified Dev Note 4, Task 1.2, OQ-1. |
| R2-P20 | LOW | SKILL.md | `bmad-quick-dev.template.md` step-file references are prose not includes — fixture needs no stub files. Clarified Dev Note 4. |
| R2-P21 | LOW | JS | `test-batch-install.js` location — should be `test/` not `tools/installer/compiler/`. Fixed Dev Note 1 and Task 5.2. |
| R2-P22 | LOW | schema | `compiled` field naming collision (int in summary, bool per-skill). Added maintainability note in Dev Note 7. |
| R2-P23 | LOW | JS | `engine.compile_skill` returns None (not a flag). Confirmed correct as written. |
| R2-P24 | LOW | compile.py | `customize.toml` not required by `engine.compile_skill`. Removed from Dev Note 7 fixture description. |
| R2-P25 | LOW | compile.py | `lockfile_path` needs `str()` wrapper for JSON serialization. Added note in schema table section. |

_Spec ready for development. No remaining DECISION-NEEDED items. R3 skipped (zero open decisions)._
