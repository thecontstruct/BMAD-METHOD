# Spec: bmad install end-to-end smoke test

Status: done

Spec authored via: bmad-create-story skill workflow (dogfood 2026-05-29)
Skill location: C:\Users\shado\workspace\.claude\skills\bmad-create-story\

## Story

As a BMAD maintainer,
I want a CI-runnable smoke test for `bmad install` that exercises the Python-backed batch compilation pipeline end-to-end,
so that regressions in cross-tree skill compilation are caught automatically before they reach users.

## Acceptance Criteria

**AC-1 — npm script**
Given `package.json` exists in the repo root,
When Story lands,
Then `package.json` contains a `"test:smoke"` script entry that runs `node test/smoke/bmad-smoke.js`.

**AC-2 — Install exits 0**
Given a writable temp directory and `python3` available in PATH,
When the smoke test runs `bmad install --yes --directory <tmpdir> --tools claude-code --modules bmm`,
Then the process exits with code 0.
And no `OVERRIDE_OUTSIDE_ROOT` or `BatchInstallError` appears in stderr.

**AC-3 — Version string**
Given `bmad-cli.js` is invoked with `--version`,
When the smoke test runs,
Then stdout contains the version string from `package.json` (currently `6.8.0-bc.0`).

**AC-4 — Directory structure**
Given install exits 0,
When the smoke test checks the temp directory,
Then all of the following directories exist:
- `<tmpdir>/_bmad/`
- `<tmpdir>/_bmad/scripts/`
- `<tmpdir>/_bmad/bmm/`
- `<tmpdir>/_bmad/_shared/`
- `<tmpdir>/_bmad/_config/`
- `<tmpdir>/.claude/skills/`

**AC-5 — Claude-code skill count**
Given install exits 0,
When the smoke test counts subdirectories in `<tmpdir>/.claude/skills/`,
Then the count is exactly 45.

**AC-6 — Key skills present in .claude/skills**
Given install exits 0,
When the smoke test checks for installed skill directories,
Then `<tmpdir>/.claude/skills/bmad-create-story/SKILL.md` exists.
And `<tmpdir>/.claude/skills/bmad-code-review/SKILL.md` exists.

**AC-7 — SKILL.md content is valid**
Given `bmad-create-story/SKILL.md` and `bmad-code-review/SKILL.md` exist,
When the smoke test reads each file,
Then each file begins with `---` (YAML frontmatter opening delimiter).
And each file contains a second `---` (YAML frontmatter closing delimiter).
And each file body (after frontmatter) is non-empty (> 100 bytes total file size).

**AC-8 — Skill manifest generated**
Given install exits 0,
When the smoke test checks `<tmpdir>/_bmad/_config/skill-manifest.csv`,
Then the file exists.
And it contains at least 40 lines (header + 39 skill rows).

**AC-9 — Cleanup**
Given the smoke test completes (pass or fail),
When the test process exits,
Then the temp directory is removed in a finally block.
And if removal fails it is logged but does not affect exit code.
And on assertion failure the tmpdir path is printed so the developer can inspect it before cleanup.

**AC-10 — Python skip**
Given `python3` is not available in PATH,
When the smoke test runs,
Then it prints a skip message: `SKIP: python3 not available — skipping smoke test`.
And it exits with code 0 (not code 1).

## Tasks/Subtasks

- [x] Task 1: Create `test/smoke/bmad-smoke.js`
  - [x] 1.1 Scaffold test file — check python3 availability; skip+exit(0) if absent; declare `tmpDir` before try block; wire try/finally for cleanup
  - [x] 1.2 Implement version check — spawn `node tools/installer/bmad-cli.js --version`; strip leading `v` from stdout; compare against version from `package.json`
  - [x] 1.3 Implement install check — spawn install command, assert exit code 0; assert stdout contains `BMAD is ready to use!`; assert stderr does not contain `OVERRIDE_OUTSIDE_ROOT` or `BatchInstallError`
  - [x] 1.4 Implement directory structure check — assert all 6 expected dirs exist
  - [x] 1.5 Implement skill count check — count `.claude/skills/` subdirs; assert === 45; on mismatch print sorted dir list for diagnosis
  - [x] 1.6 Implement key skills check — assert SKILL.md for create-story and code-review
  - [x] 1.7 Implement SKILL.md content check — assert both `---` delimiters present; assert file size > 100 bytes; wrap reads in try-catch and report filename on error
  - [x] 1.8 Implement manifest check — assert `_bmad/_config/skill-manifest.csv` exists and has >= 40 lines
  - [x] 1.9 Implement cleanup in finally block — print tmpdir path before cleanup on any failure; remove dir; log if removal fails but do not re-throw
  - [x] 1.10 Wire all checks into `main()`, report totals, exit 1 on any failure

- [x] Task 2: Add `test:smoke` to package.json scripts

## Dev Notes

### CLI invocation
The test must invoke the CLI as `node tools/installer/bmad-cli.js` (not the global `bmad` shim) so the test works in CI without `npm link`. Use `node:child_process` `spawnSync` with `stdio: 'pipe'` to capture output.

```js
const CLI = path.resolve(__dirname, '../../tools/installer/bmad-cli.js');
const result = spawnSync('node', [CLI, 'install', '--yes', '--directory', tmpDir, '--tools', 'claude-code', '--modules', 'bmm'], {
  stdio: 'pipe',
  encoding: 'utf8',
  timeout: 120_000, // 2 min; batch compile can be slow on first run
});
```

### Python requirement
The smoke test specifically exercises the Python compilation path (Phase A bug fix target). If `python3` is unavailable the test should skip with a clear message rather than fail, since CI may not always have Python.

```js
const pyCheck = spawnSync('python3', ['--version'], { stdio: 'pipe' });
if (pyCheck.status !== 0) {
  console.log('SKIP: python3 not available — skipping smoke test');
  process.exit(0);
}
```

### Temp directory
Declare `tmpDir` before the try block so the finally block can always reference it:

```js
let tmpDir = null;
try {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'bmad-smoke-'));
  // ... assertions ...
} finally {
  if (tmpDir) {
    try { fs.rmSync(tmpDir, { recursive: true, force: true }); }
    catch (e) { console.log(`  Warning: cleanup failed: ${e.message}`); }
  }
}
```

### Version comparison
Strip any leading `v` from CLI output before comparing:
```js
const cliVersion = result.stdout.trim().replace(/^v/, '');
const pkgVersion = packageJson.version;
```

### Version source
Read version from `../../package.json` at test startup (don't hardcode it). The smoke test should work across version bumps.

### Existing test pattern
All tests in `test/` use a hand-rolled assert/color framework — no mocha/jest. Follow the exact same pattern as `test/test-installation-components.js`:
- `colors` object with ANSI codes
- `assert(condition, testName, errorMessage)` function
- `passed / failed` counters
- Final `process.exit(failed > 0 ? 1 : 0)` 

### OVERRIDE_OUTSIDE_ROOT regression guard
The root cause fixed in commit 3786f12f was that batch compilation used `scenario_root` (source tree) for security checks but needed `lockfile_root` (install tree). The smoke test exercises this path end-to-end. If AC-2 passes (exit 0, no OVERRIDE_OUTSIDE_ROOT in stderr), the fix is verified.

## Dev Agent Record

### Implementation Plan
Phase A: Fix engine.py + resolver.py cross-tree OVERRIDE_OUTSIDE_ROOT bugs (commit 3786f12f)
Phase B: Author this spec via bmad-create-story dogfood workflow; R1+R2+R3 inline
Phase C: Implement bmad-smoke.js + add test:smoke to package.json; verify 23/23 pass

### Debug Log
No issues. ESLint required `unicorn/prefer-includes` and `unicorn/no-negated-condition` fixes.
prettier-plugin-packagejson reordered `test:smoke` alphabetically in package.json.
Full npm test suite passed after fixes.

### Completion Notes
`npm run test:smoke` runs 23 assertions covering all 10 ACs. All pass.
OVERRIDE_OUTSIDE_ROOT regression guard (AC-2/AC-3) confirmed: the cross-tree
batch compilation path that was broken is now verified green end-to-end.

## File List

- `test/smoke/bmad-smoke.spec.md` (NEW — this file)
- `test/smoke/bmad-smoke.js` (NEW — smoke test implementation)
- `package.json` (MODIFY — add `test:smoke` script)

## Change Log

- 2026-05-29: Spec authored (dogfood Phase B); R1+R2+R3 complete; ready-for-dev

## Review Chain

**R1** (correctness + security): 7 findings — 3 STRUCK (reviewer misunderstood forced-core install and actual manifest size from real install), 1 STRUCK (noise, already covered), 1 PULLED→Low (AC-9 cleanup clarification), 1 PULLED (AC-7 frontmatter closing delimiter), 1 PULLED (AC-10 Python skip AC added).

**R2** (implementation completeness): 8 findings — 1 RETAGGED→Low (spawnSync timeout is correct, added doc note), 1 PULLED (tmpDir guard + finally structure), 1 PULLED (AC-5 diagnostic output), 1 KEPT (file read error handling, already in try-catch), 1 PULLED (Python skip semantics clarified in Dev Notes), 1 KEPT (compiled vs raw already clear), 1 PULLED (tmpdir retained on failure), 1 PULLED (version string normalization).

**R3** (defer-list walk 2026-05-29): 7 items STRUCK, 7 PULLED into spec, 2 KEPT for implementation guidance. Spec updated and ready for implementation.
