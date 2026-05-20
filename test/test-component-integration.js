/**
 * Story 8.5 integration test — compile_skill end-to-end with components.
 *
 * Fixture: test/fixtures/compile/component-integration/
 *   core/component-integration/component-integration.template.md
 *   core/component-integration/components/date_banner.py   (RENDER_MODE = "compile")
 *   core/component-integration/components/sprint_banner.py (RENDER_MODE = "jit")
 *
 * Asserts:
 *   (a) SKILL.md contains "[Compile Output]"
 *   (b) SKILL.md contains "<!-- BMAD-JIT:SprintBanner:" (with 16-hex suffix)
 *   (c) SKILL.md contains neither "<DateBanner" nor "<SprintBanner"
 *   (d) bmad.lock entry has "components" array of length 2
 *   (e) compile-mode entry has name=DateBanner, render_mode=compile, compiled_hash non-null
 *   (f) JIT-mode entry has name=SprintBanner, render_mode=jit, sentinel_format_version=1
 *   (g) Atomicity — when ComponentBatchError is injected, neither SKILL.md nor lockfile changes
 *
 * Usage: node test/test-component-integration.js
 */

'use strict';

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const colors = {
  reset: '\u001B[0m',
  green: '\u001B[32m',
  red: '\u001B[31m',
};

let passed = 0;
let failed = 0;
const failures = [];

function test(name, fn) {
  try {
    fn();
    passed++;
    console.log(`  ${colors.green}OK${colors.reset} ${name}`);
  } catch (error) {
    failed++;
    failures.push({ name, message: error.message });
    console.log(`  ${colors.red}FAIL${colors.reset} ${name}: ${error.message}`);
  }
}

function assert(cond, msg) {
  if (!cond) throw new Error(msg);
}

const ROOT = path.join(__dirname, '..');
const FIXTURE_SRC = path.join(__dirname, 'fixtures', 'compile', 'component-integration');
const PY = process.env.PYTHON || 'python';

function copyDirSync(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dst, entry.name);
    if (entry.isDirectory()) copyDirSync(s, d);
    else fs.copyFileSync(s, d);
  }
}

function runPython(script) {
  const result = spawnSync(PY, ['-c', script], {
    cwd: ROOT,
    encoding: 'utf-8',
  });
  return result;
}

// ── Test A: happy path (compile + JIT sentinel) ──────────────────────────────

const tmpA = fs.mkdtempSync(path.join(os.tmpdir(), 'bmad-component-it-'));
try {
  // Copy fixture into temp (so install_dir writes do not pollute the source tree)
  copyDirSync(FIXTURE_SRC, tmpA);

  const skillDir = path.join(tmpA, 'core', 'component-integration');
  const installDir = path.join(tmpA, 'install');
  const lockfilePath = path.join(tmpA, '_bmad', '_config', 'bmad.lock');
  fs.mkdirSync(installDir, { recursive: true });

  // Use forward slashes for the Python literal so backslashes on Windows do not break parsing
  const skillDirPosix = skillDir.replaceAll('\\', '/');
  const installDirPosix = installDir.replaceAll('\\', '/');

  const script = [
    'import sys',
    'sys.path.insert(0, "src/scripts")',
    'from bmad_compile.engine import compile_skill',
    `compile_skill(r"${skillDirPosix}", r"${installDirPosix}")`,
    'print("OK")',
  ].join('\n');

  const res = runPython(script);
  if (res.status === 0) {
    const skillMdPath = path.join(installDir, 'component-integration', 'SKILL.md');
    test('SKILL.md exists', () => assert(fs.existsSync(skillMdPath), `not found: ${skillMdPath}`));

    const skillMd = fs.readFileSync(skillMdPath, 'utf-8');

    test('(a) SKILL.md contains [Compile Output]', () => {
      assert(skillMd.includes('[Compile Output]'), `got: ${skillMd}`);
    });

    test('(b) SKILL.md contains BMAD-JIT:SprintBanner sentinel with 16-hex suffix', () => {
      const m = skillMd.match(/<!-- BMAD-JIT:SprintBanner:([0-9a-f]{16}) -->/);
      assert(m !== null, `no sentinel found in: ${skillMd}`);
    });

    test('(c) SKILL.md has no raw <DateBanner or <SprintBanner tags', () => {
      assert(!skillMd.includes('<DateBanner'), 'raw <DateBanner leaked');
      assert(!skillMd.includes('<SprintBanner'), 'raw <SprintBanner leaked');
    });

    test('lockfile exists', () => assert(fs.existsSync(lockfilePath), `not found: ${lockfilePath}`));

    const lockfile = JSON.parse(fs.readFileSync(lockfilePath, 'utf-8'));
    const entry = lockfile.entries.find((e) => e.skill === 'component-integration');
    test('lockfile entry exists', () => assert(entry !== undefined, 'no entry for skill'));

    test('(d) lockfile.components has length 2', () => {
      assert(Array.isArray(entry.components), 'components not array');
      assert(entry.components.length === 2, `got length ${entry.components.length}`);
    });

    const dateBanner = entry.components.find((c) => c.name === 'DateBanner');
    const sprintBanner = entry.components.find((c) => c.name === 'SprintBanner');

    test('(e) DateBanner entry has render_mode=compile + non-null compiled_hash', () => {
      assert(dateBanner !== undefined, 'no DateBanner entry');
      assert(dateBanner.render_mode === 'compile', `got: ${dateBanner.render_mode}`);
      assert(
        typeof dateBanner.compiled_hash === 'string' && dateBanner.compiled_hash.length > 0,
        `compiled_hash: ${dateBanner.compiled_hash}`,
      );
      assert(
        dateBanner.sentinel_format_version === null,
        `sentinel_format_version should be null for compile-mode; got ${dateBanner.sentinel_format_version}`,
      );
    });

    test('(f) SprintBanner entry has render_mode=jit + sentinel_format_version=1', () => {
      assert(sprintBanner !== undefined, 'no SprintBanner entry');
      assert(sprintBanner.render_mode === 'jit', `got: ${sprintBanner.render_mode}`);
      assert(
        sprintBanner.sentinel_format_version === 1,
        `sentinel_format_version should be 1; got ${sprintBanner.sentinel_format_version}`,
      );
      assert(sprintBanner.compiled_hash === null, `compiled_hash should be null for JIT; got ${sprintBanner.compiled_hash}`);
    });

    test('(g) TPL-01 — compiled SKILL.md has no unresolved {{var}} markers', () => {
      assert(!/\{\{[^}]+\}\}/.test(skillMd), 'unresolved {{var}} found');
    });
  } else {
    console.log(`Python stderr: ${res.stderr}`);
    console.log(`Python stdout: ${res.stdout}`);
    failed++;
    failures.push({ name: 'happy-path compile', message: `python exit ${res.status}` });
  }
} finally {
  fs.rmSync(tmpA, { recursive: true, force: true });
}

// ── Test B: atomicity — ComponentBatchError aborts without touching outputs ──

const tmpB = fs.mkdtempSync(path.join(os.tmpdir(), 'bmad-component-it-atomic-'));
try {
  copyDirSync(FIXTURE_SRC, tmpB);

  const skillDir = path.join(tmpB, 'core', 'component-integration');
  const installDir = path.join(tmpB, 'install');
  const lockfilePath = path.join(tmpB, '_bmad', '_config', 'bmad.lock');
  fs.mkdirSync(installDir, { recursive: true });

  const skillDirPosix = skillDir.replaceAll('\\', '/');
  const installDirPosix = installDir.replaceAll('\\', '/');
  const expectedSkillMd = path.join(installDir, 'component-integration', 'SKILL.md');

  // Inject MockComponentRunner that raises ComponentBatchError for token_index 1
  // (the DateBanner is the first compile-mode invocation; its index depends on
  // the parser, so we wire the mock to error on any token by passing a Mock that
  // always fails).
  const script = [
    'import sys',
    'sys.path.insert(0, "src/scripts")',
    'from bmad_compile.component_runner import MockComponentRunner',
    'from bmad_compile.errors import ComponentBatchError, ComponentError',
    'from bmad_compile.engine import compile_skill',
    '',
    'class AlwaysFails(MockComponentRunner):',
    '    def run_compile_batch(self, invocations, ctx_dict, timeout_seconds=10.0):',
    '        if not invocations:',
    '            return {}',
    '        raise ComponentBatchError(',
    '            "injected failure",',
    '            errors=[ComponentError("boom", component_name=inv.original.name) for inv in invocations],',
    '        )',
    '',
    'try:',
    `    compile_skill(r"${skillDirPosix}", r"${installDirPosix}", component_runner=AlwaysFails())`,
    '    print("UNEXPECTED_SUCCESS")',
    'except ComponentBatchError:',
    '    print("EXPECTED_FAILURE")',
  ].join('\n');

  const res = runPython(script);
  test('atomicity: compile raises ComponentBatchError', () => {
    assert(
      res.stdout.includes('EXPECTED_FAILURE'),
      `expected EXPECTED_FAILURE in stdout. stdout=${res.stdout == null ? '' : res.stdout} stderr=${res.stderr == null ? '' : res.stderr}`,
    );
  });

  test('atomicity: SKILL.md was NOT written', () => {
    assert(!fs.existsSync(expectedSkillMd), `SKILL.md should not exist at ${expectedSkillMd}`);
  });

  test('atomicity: lockfile was NOT created', () => {
    assert(!fs.existsSync(lockfilePath), `lockfile should not exist at ${lockfilePath}`);
  });
} finally {
  fs.rmSync(tmpB, { recursive: true, force: true });
}

// ── Summary ──────────────────────────────────────────────────────────────────

console.log(`\n${passed} passed, ${failed} failed`);
if (failed > 0) {
  for (const f of failures) console.log(`  - ${f.name}: ${f.message}`);
  process.exit(1);
}
