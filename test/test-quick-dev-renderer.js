/**
 * Smoke test for bmad-quick-dev render.py (Story 7.22)
 *
 * Uses a minimal synthetic skill fixture (render.py + test-fixture.md) instead
 * of copying the full skill directory. Assertions:
 *   1. render.py exits 0 when config is well-formed
 *   2. test-fixture.md exists in the render output directory
 *   3. Custom override wins — rendered fixture contains "Japanese"
 *   4. sprint_status is an absolute POSIX path rooted at the temp project dir
 *   5. HALT guard fires when implementation_artifacts is absent
 *
 * Usage: node test/test-quick-dev-renderer.js
 * Exit codes: 0 = all tests pass, 1 = test failures
 */

'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

// ANSI color codes (same as other test files)
const colors = {
  reset: '[0m',
  green: '[32m',
  red: '[31m',
  cyan: '[36m',
};

let totalTests = 0;
let passedTests = 0;
const failures = [];

function test(name, fn) {
  totalTests++;
  try {
    fn();
    passedTests++;
    console.log(`  ${colors.green}✓${colors.reset} ${name}`);
  } catch (error) {
    console.log(`  ${colors.red}✗${colors.reset} ${name} ${colors.red}${error.message}${colors.reset}`);
    failures.push({ name, message: error.message });
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

// ── constants ────────────────────────────────────────────────────────────────

const RENDER_PY = path.join(__dirname, '..', 'src', 'bmm-skills', '4-implementation', 'bmad-quick-dev', 'render.py');

// ── helper: build a minimal fixture skill dir ────────────────────────────────

function makeSkillDir(base) {
  // render.py needs script_dir (its own containing dir) to have a name that
  // becomes skill_name; use 'bmad-quick-dev' so output lands under
  //   <root>/_bmad/render/bmad-quick-dev/
  const dir = path.join(base, 'bmad-quick-dev');
  fs.mkdirSync(dir, { recursive: true });
  fs.copyFileSync(RENDER_PY, path.join(dir, 'render.py'));
  return dir;
}

// ── Fixture A: happy path ────────────────────────────────────────────────────

let tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'bmad-renderer-test-'));
tmpDir = fs.realpathSync(tmpDir); // macOS: /var → /private/var symlink resolution
try {
  // _bmad/config.toml — base layer (includes implementation_artifacts)
  fs.mkdirSync(path.join(tmpDir, '_bmad'), { recursive: true });
  fs.writeFileSync(
    path.join(tmpDir, '_bmad', 'config.toml'),
    ['[core]', 'communication_language = "French"', '', '[modules.bmm]', 'implementation_artifacts = "{project-root}/impl"'].join('\n'),
    'utf-8',
  );

  // _bmad/custom/config.user.toml — layer 4 override (must win over layer 1)
  fs.mkdirSync(path.join(tmpDir, '_bmad', 'custom'), { recursive: true });
  fs.writeFileSync(
    path.join(tmpDir, '_bmad', 'custom', 'config.user.toml'),
    ['[core]', 'communication_language = "Japanese"'].join('\n'),
    'utf-8',
  );

  // minimal skill dir: render.py + synthetic fixture with {{.X}} placeholders
  const skillDst = makeSkillDir(tmpDir);
  fs.writeFileSync(path.join(skillDst, 'test-fixture.md'), 'Language: {{.communication_language}}\nStatus: {{.sprint_status}}\n', 'utf-8');

  const result = spawnSync('python3', [path.join(skillDst, 'render.py')], {
    cwd: skillDst,
    encoding: 'utf-8',
  });

  // Assertions 1–4
  test('render.py exits with code 0', () => {
    assert(result.status === 0, `exit ${result.status}\nstdout: ${result.stdout}\nstderr: ${result.stderr}`);
  });
  test('test-fixture.md exists in render output', () => {
    const rendered = path.join(tmpDir, '_bmad', 'render', 'bmad-quick-dev', 'test-fixture.md');
    assert(fs.existsSync(rendered), `not found at ${rendered}`);
  });
  test('custom override wins — rendered fixture contains "Japanese"', () => {
    const rendered = path.join(tmpDir, '_bmad', 'render', 'bmad-quick-dev', 'test-fixture.md');
    const content = fs.readFileSync(rendered, 'utf-8');
    assert(content.includes('Japanese'), `"Japanese" not found; content:\n${content.slice(0, 500)}`);
  });
  test('sprint_status is an absolute POSIX path rooted at temp project dir', () => {
    const rendered = path.join(tmpDir, '_bmad', 'render', 'bmad-quick-dev', 'test-fixture.md');
    const content = fs.readFileSync(rendered, 'utf-8');
    // normalize to forward slashes (render.py always outputs POSIX paths)
    const rootPosix = tmpDir.replaceAll('\\', '/');
    const expected = `${rootPosix}/impl/sprint-status.yaml`;
    assert(content.includes(expected), `Expected sprint_status="${expected}"\nContent:\n${content.slice(0, 500)}`);
  });
} finally {
  fs.rmSync(tmpDir, { recursive: true, force: true });
}

// ── Fixture B: HALT path (implementation_artifacts absent) ──────────────────

let haltDir = fs.mkdtempSync(path.join(os.tmpdir(), 'bmad-renderer-halt-'));
haltDir = fs.realpathSync(haltDir);
try {
  // config WITHOUT implementation_artifacts key
  fs.mkdirSync(path.join(haltDir, '_bmad'), { recursive: true });
  fs.writeFileSync(
    path.join(haltDir, '_bmad', 'config.toml'),
    [
      '[core]',
      'communication_language = "French"',
      // intentionally omitting [modules.bmm] implementation_artifacts
    ].join('\n'),
    'utf-8',
  );

  const skillDst2 = makeSkillDir(haltDir);
  fs.writeFileSync(path.join(skillDst2, 'test-fixture.md'), 'Language: {{.communication_language}}\n', 'utf-8');

  const haltResult = spawnSync('python3', [path.join(skillDst2, 'render.py')], {
    cwd: skillDst2,
    encoding: 'utf-8',
  });

  // Assertion 5 — verify HALT guard fires (not a Python traceback to stderr)
  test('HALT when implementation_artifacts is absent — exits non-zero, HALT on stdout', () => {
    assert(haltResult.status !== 0, `Expected non-zero exit, got ${haltResult.status}`);
    // Check for the specific key name, not just "HALT", to distinguish from
    // other HALT paths (e.g., find_project_root missing _bmad/)
    assert(
      haltResult.stdout.includes('implementation_artifacts'),
      `Expected "implementation_artifacts" in stdout.\n` + `stdout: ${haltResult.stdout}\nstderr: ${haltResult.stderr}`,
    );
  });
} finally {
  fs.rmSync(haltDir, { recursive: true, force: true });
}

// ── Fixture C: JIT happy path ────────────────────────────────────────────────

const SCRIPTS_DIR = path.join(__dirname, '..', 'src', 'scripts');
const JIT_FIXTURE_DIR = path.join(__dirname, 'fixtures', 'jit-renderer');

let jitDir = fs.mkdtempSync(path.join(os.tmpdir(), 'bmad-jit-test-'));
jitDir = fs.realpathSync(jitDir);
try {
  // config
  fs.mkdirSync(path.join(jitDir, '_bmad'), { recursive: true });
  fs.copyFileSync(path.join(JIT_FIXTURE_DIR, '_bmad', 'config.toml'), path.join(jitDir, '_bmad', 'config.toml'));

  // lockfile
  fs.mkdirSync(path.join(jitDir, '_bmad', '_config'), { recursive: true });
  fs.copyFileSync(path.join(JIT_FIXTURE_DIR, '_bmad', '_config', 'bmad.lock'), path.join(jitDir, '_bmad', '_config', 'bmad.lock'));

  // skill dir: render.py + SKILL.md
  const jitSkillDir = path.join(jitDir, '_bmad', 'test-module', 'test-skill');
  fs.mkdirSync(jitSkillDir, { recursive: true });
  fs.copyFileSync(RENDER_PY, path.join(jitSkillDir, 'render.py'));
  fs.copyFileSync(path.join(JIT_FIXTURE_DIR, '_bmad', 'test-module', 'test-skill', 'SKILL.md'), path.join(jitSkillDir, 'SKILL.md'));

  // component file
  const jitCompDir = path.join(jitDir, '_bmad', 'components', 'test-module', 'test-skill');
  fs.mkdirSync(jitCompDir, { recursive: true });
  fs.copyFileSync(
    path.join(JIT_FIXTURE_DIR, '_bmad', 'components', 'test-module', 'test-skill', 'fixture_banner.py'),
    path.join(jitCompDir, 'fixture_banner.py'),
  );

  const jitResult = spawnSync('python3', [path.join(jitSkillDir, 'render.py')], {
    cwd: jitSkillDir,
    env: { ...process.env, PYTHONPATH: SCRIPTS_DIR },
    encoding: 'utf-8',
  });

  test('JIT: render.py exits 0 with fixture SKILL.md', () => {
    assert(jitResult.status === 0, `exit ${jitResult.status}\nstdout: ${jitResult.stdout}\nstderr: ${jitResult.stderr}`);
  });
  test('JIT: _bmad/render/test-skill/SKILL.md exists', () => {
    const rendered = path.join(jitDir, '_bmad', 'render', 'test-skill', 'SKILL.md');
    assert(fs.existsSync(rendered), `not found at ${rendered}`);
  });
  test('JIT: rendered SKILL.md contains "[JIT RESOLVED]"', () => {
    const rendered = path.join(jitDir, '_bmad', 'render', 'test-skill', 'SKILL.md');
    const content = fs.readFileSync(rendered, 'utf-8');
    assert(content.includes('[JIT RESOLVED]'), `"[JIT RESOLVED]" not found; content:\n${content.slice(0, 500)}`);
  });
} finally {
  fs.rmSync(jitDir, { recursive: true, force: true });
}

// ── Fixture D: JIT lockfile absent ───────────────────────────────────────────

let jitNoLockDir = fs.mkdtempSync(path.join(os.tmpdir(), 'bmad-jit-nolock-'));
jitNoLockDir = fs.realpathSync(jitNoLockDir);
try {
  // config — no lockfile
  fs.mkdirSync(path.join(jitNoLockDir, '_bmad'), { recursive: true });
  fs.copyFileSync(path.join(JIT_FIXTURE_DIR, '_bmad', 'config.toml'), path.join(jitNoLockDir, '_bmad', 'config.toml'));

  const noLockSkillDir = path.join(jitNoLockDir, '_bmad', 'test-module', 'test-skill');
  fs.mkdirSync(noLockSkillDir, { recursive: true });
  fs.copyFileSync(RENDER_PY, path.join(noLockSkillDir, 'render.py'));
  fs.copyFileSync(path.join(JIT_FIXTURE_DIR, '_bmad', 'test-module', 'test-skill', 'SKILL.md'), path.join(noLockSkillDir, 'SKILL.md'));

  const noLockResult = spawnSync('python3', [path.join(noLockSkillDir, 'render.py')], {
    cwd: noLockSkillDir,
    env: { ...process.env, PYTHONPATH: SCRIPTS_DIR },
    encoding: 'utf-8',
  });

  test('JIT lockfile-absent: render.py exits 0', () => {
    assert(noLockResult.status === 0, `exit ${noLockResult.status}\nstdout: ${noLockResult.stdout}\nstderr: ${noLockResult.stderr}`);
  });
  test('JIT lockfile-absent: rendered SKILL.md contains error slot', () => {
    const rendered = path.join(jitNoLockDir, '_bmad', 'render', 'test-skill', 'SKILL.md');
    assert(fs.existsSync(rendered), `not found at ${rendered}`);
    const content = fs.readFileSync(rendered, 'utf-8');
    assert(content.includes('<!-- BMAD-ERROR:FixtureBanner -->'), `Error slot not found; content:\n${content.slice(0, 500)}`);
  });
} finally {
  fs.rmSync(jitNoLockDir, { recursive: true, force: true });
}

// ---------------------------------------------------------------------------
// Summary
// ---------------------------------------------------------------------------

console.log(`\n${colors.cyan}${'═'.repeat(55)}${colors.reset}`);
console.log(`${colors.cyan}Test Results:${colors.reset}`);
console.log(`  Total:  ${totalTests}`);
console.log(`  Passed: ${colors.green}${passedTests}${colors.reset}`);
console.log(`  Failed: ${passedTests === totalTests ? colors.green : colors.red}${totalTests - passedTests}${colors.reset}`);
console.log(`${colors.cyan}${'═'.repeat(55)}${colors.reset}\n`);

if (failures.length > 0) {
  console.log(`${colors.red}FAILED TESTS:${colors.reset}\n`);
  for (const failure of failures) {
    console.log(`${colors.red}✗${colors.reset} ${failure.name}`);
    console.log(`  ${failure.message}\n`);
  }
  process.exit(1);
}

console.log(`${colors.green}All tests passed!${colors.reset}\n`);
process.exit(0);
