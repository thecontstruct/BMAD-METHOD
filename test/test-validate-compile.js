/**
 * tools/validate-compile.js integration tests.
 *
 * Each test invokes the script as a subprocess against the real repo. The
 * "hash mismatch", "missing bmad.lock", and "empty-lock" tests temporarily
 * mutate src/_bmad/_config/bmad.lock and restore it via try/finally so a test
 * failure does not leave the lock file in a corrupted state.
 *
 * R2-ECH-8 NOTE: the lockfile-mutation helpers (`withLockfileMutation`,
 * `withLockfileRemoved`) protect against synchronous throws (try/finally) and
 * SIGINT/SIGTERM (signal handlers that restore the original before exit). They
 * do NOT protect against an `uncaughtException` raised from a `Promise` the
 * test forgot to await — Node's default handler exits without unwinding
 * try/finally. **Mutator and fn() bodies must be synchronous.** If a future
 * test adds async work, register `process.on('uncaughtException')` and
 * `process.on('unhandledRejection')` alongside the existing signal handlers.
 *
 * Usage: node test/test-validate-compile.js
 */

'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const VALIDATE_SCRIPT = path.join(PROJECT_ROOT, 'tools', 'validate-compile.js');
const LOCK_PATH = path.join(PROJECT_ROOT, 'src', '_bmad', '_config', 'bmad.lock');

const colors = {
  reset: '[0m',
  green: '[32m',
  red: '[31m',
  cyan: '[36m',
};

let passed = 0;
let failed = 0;
const failures = [];

function record(name, ok, detail) {
  if (ok) {
    passed++;
    console.log(`  ${colors.green}✓${colors.reset} ${name}`);
  } else {
    failed++;
    failures.push({ name, detail });
    console.log(`  ${colors.red}✗${colors.reset} ${name}`);
    if (detail) console.log(`      ${detail.split('\n').join('\n      ')}`);
  }
}

function runValidate(extraArgs = []) {
  return spawnSync('node', [VALIDATE_SCRIPT, ...extraArgs], {
    cwd: PROJECT_ROOT,
    encoding: 'utf8',
  });
}

function withLockfileMutation(mutator, fn) {
  // BH-5: read-only checkout fallback — fail gracefully if bmad.lock is not writable.
  try {
    fs.accessSync(LOCK_PATH, fs.constants.W_OK);
  } catch {
    console.log('  (skipping mutation test: bmad.lock is not writable)');
    return;
  }
  const original = fs.readFileSync(LOCK_PATH, 'utf8');
  // ECH-7: SIGINT/SIGTERM safety — restore original before exit so an interrupted test
  // does not leave bmad.lock corrupted on disk for subsequent runs.
  let restored = false;
  const restoreOnSignal = () => {
    // R2-ECH-1: move process.exit() inside the `restored` guard so a SIGINT-during-cleanup
    // race doesn't fire process.exit twice (second exit is a no-op but the listener removal
    // in finally never runs; clean fix is one process.exit per signal-handler activation).
    if (!restored) {
      try {
        fs.writeFileSync(LOCK_PATH, original);
      } catch {
        /* best-effort signal-handler restore; nothing actionable on failure */
      }
      restored = true;
      process.exit(130);
    }
  };
  process.on('SIGINT', restoreOnSignal);
  process.on('SIGTERM', restoreOnSignal);
  try {
    mutator(original);
    fn();
  } finally {
    if (!restored) {
      fs.writeFileSync(LOCK_PATH, original);
      restored = true;
    }
    process.removeListener('SIGINT', restoreOnSignal);
    process.removeListener('SIGTERM', restoreOnSignal);
  }
}

function withLockfileRemoved(fn) {
  try {
    fs.accessSync(LOCK_PATH, fs.constants.W_OK);
  } catch {
    console.log('  (skipping missing-lock test: bmad.lock is not writable)');
    return;
  }
  const original = fs.readFileSync(LOCK_PATH);
  let restored = false;
  const restoreOnSignal = () => {
    // R2-ECH-1: move process.exit() inside the `restored` guard so a SIGINT-during-cleanup
    // race doesn't fire process.exit twice (second exit is a no-op but the listener removal
    // in finally never runs; clean fix is one process.exit per signal-handler activation).
    if (!restored) {
      try {
        fs.writeFileSync(LOCK_PATH, original);
      } catch {
        /* best-effort signal-handler restore; nothing actionable on failure */
      }
      restored = true;
      process.exit(130);
    }
  };
  process.on('SIGINT', restoreOnSignal);
  process.on('SIGTERM', restoreOnSignal);
  try {
    fs.unlinkSync(LOCK_PATH);
    fn();
  } finally {
    if (!restored) {
      fs.writeFileSync(LOCK_PATH, original);
      restored = true;
    }
    process.removeListener('SIGINT', restoreOnSignal);
    process.removeListener('SIGTERM', restoreOnSignal);
  }
}

// ─────────────────────────────────────────────────────────────────────────
// Tests
// ─────────────────────────────────────────────────────────────────────────

function test_validate_compile_exits_zero_unchanged() {
  const result = runValidate();
  record(
    'validate:compile exits 0 on unchanged repo',
    result.status === 0,
    `exit=${result.status}\nstdout:\n${result.stdout}\nstderr:\n${result.stderr}`,
  );
  record(
    'success message present in stdout',
    /All compile hashes match/.test(result.stdout),
    `stdout did not contain success message:\n${result.stdout}`,
  );
}

function test_validate_compile_exits_nonzero_on_hash_mismatch() {
  withLockfileMutation(
    (original) => {
      const lock = JSON.parse(original);
      lock.entries[0].compiled_hash = '0'.repeat(64);
      fs.writeFileSync(LOCK_PATH, JSON.stringify(lock, null, 2));
    },
    () => {
      const result = runValidate();
      record(
        'validate:compile exits 1 on hash mismatch',
        result.status === 1,
        `exit=${result.status}\nstdout:\n${result.stdout}\nstderr:\n${result.stderr}`,
      );
      record(
        'mismatch report mentions bmad-customize and both hashes',
        result.stdout.includes('bmad-customize') && result.stdout.includes('0'.repeat(64)) && /actual:\s+[\da-f]{64}/.test(result.stdout),
        `stdout did not include skill name + expected/actual hashes:\n${result.stdout}`,
      );
    },
  );
}

function test_validate_compile_json_output_structure() {
  const result = runValidate(['--json']);
  let parsed = null;
  let parseErr = null;
  try {
    parsed = JSON.parse(result.stdout);
  } catch (error) {
    parseErr = error.message;
  }
  record('--json output parses as JSON', parsed !== null, parseErr ? `parse error: ${parseErr}\nstdout:\n${result.stdout}` : null);
  if (parsed === null) return;
  record(
    'JSON output has top-level "exit_code" key',
    Object.prototype.hasOwnProperty.call(parsed, 'exit_code'),
    `keys: ${Object.keys(parsed).join(', ')}`,
  );
  record(
    'JSON output has top-level "skills" key',
    Object.prototype.hasOwnProperty.call(parsed, 'skills') && Array.isArray(parsed.skills),
    `keys: ${Object.keys(parsed).join(', ')}`,
  );
  record(
    'JSON output skills[0] has skill, status, expected, actual fields',
    parsed.skills.length > 0 &&
      'skill' in parsed.skills[0] &&
      'status' in parsed.skills[0] &&
      'expected' in parsed.skills[0] &&
      'actual' in parsed.skills[0],
    `skill[0] keys: ${parsed.skills[0] ? Object.keys(parsed.skills[0]).join(', ') : '<none>'}`,
  );
}

function test_validate_compile_fails_on_missing_bmad_lock() {
  withLockfileRemoved(() => {
    const result = runValidate();
    record(
      'validate:compile exits 1 when bmad.lock is missing',
      result.status === 1,
      `exit=${result.status}\nstdout:\n${result.stdout}\nstderr:\n${result.stderr}`,
    );
    const combined = result.stdout + result.stderr;
    record(
      'missing-lock error mentions bmad.lock and "not found"',
      combined.includes('bmad.lock') && /not found/i.test(combined),
      `combined output:\n${combined}`,
    );

    // ECH-8: also verify --json error shape for missing-lock so a regression in the
    // JSON branch wouldn't slip through unnoticed.
    const jsonResult = runValidate(['--json']);
    record(
      'validate:compile --json exits 1 when bmad.lock is missing',
      jsonResult.status === 1,
      `exit=${jsonResult.status}\nstdout:\n${jsonResult.stdout}\nstderr:\n${jsonResult.stderr}`,
    );
    let parsed = null;
    try {
      parsed = JSON.parse(jsonResult.stdout);
    } catch {
      /* parsed stays null; assertion below handles it */
    }
    record(
      '--json missing-lock output has exit_code:1 and error mentions bmad.lock',
      parsed !== null && parsed.exit_code === 1 && /bmad\.lock/.test(String(parsed.error || '')),
      `parsed: ${JSON.stringify(parsed)}`,
    );
  });
}

function test_validate_compile_exits_zero_on_empty_lock() {
  // DN-R1-4=A (Phil 2026-05-08): empty bmad.lock is vacuous-truth, exit 0. Spec AC-1
  // says "exits 0 if all match" — zero entries match trivially; this is a valid repo
  // state (e.g. pre-first-skill-migration), not a guard failure.
  withLockfileMutation(
    (original) => {
      const lock = JSON.parse(original);
      lock.entries = [];
      fs.writeFileSync(LOCK_PATH, JSON.stringify(lock, null, 2));
    },
    () => {
      const result = runValidate();
      record(
        'validate:compile exits 0 on empty bmad.lock (DN-R1-4=A vacuous-truth)',
        result.status === 0,
        `exit=${result.status}\nstdout:\n${result.stdout}\nstderr:\n${result.stderr}`,
      );
      record(
        'empty-lock message mentions zero entries / nothing to verify',
        /zero entries|nothing to verify/i.test(result.stdout),
        `stdout: ${result.stdout}`,
      );

      // --json branch: same vacuous-truth contract.
      const jsonResult = runValidate(['--json']);
      let parsed = null;
      try {
        parsed = JSON.parse(jsonResult.stdout);
      } catch {
        /* parsed stays null; assertion below handles it */
      }
      record(
        '--json empty-lock has exit_code:0 and skills:[]',
        jsonResult.status === 0 && parsed !== null && parsed.exit_code === 0 && Array.isArray(parsed.skills) && parsed.skills.length === 0,
        `exit=${jsonResult.status} parsed=${JSON.stringify(parsed)}`,
      );
    },
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Runner
// ─────────────────────────────────────────────────────────────────────────

function runTests() {
  console.log(`${colors.cyan}validate-compile.js tests${colors.reset}\n`);
  console.log(`  exits zero on unchanged repo:`);
  test_validate_compile_exits_zero_unchanged();
  console.log(`  exits zero on empty bmad.lock (DN-R1-4=A):`);
  test_validate_compile_exits_zero_on_empty_lock();
  console.log(`  exits non-zero on hash mismatch:`);
  test_validate_compile_exits_nonzero_on_hash_mismatch();
  console.log(`  --json output structure:`);
  test_validate_compile_json_output_structure();
  console.log(`  fails on missing bmad.lock:`);
  test_validate_compile_fails_on_missing_bmad_lock();

  console.log('');
  console.log(`${colors.cyan}========================================${colors.reset}`);
  console.log(`Test Results:`);
  console.log(`  Passed: ${colors.green}${passed}${colors.reset}`);
  console.log(`  Failed: ${colors.red}${failed}${colors.reset}`);
  console.log(`${colors.cyan}========================================${colors.reset}\n`);

  if (failed > 0) {
    process.exit(1);
  }
}

try {
  runTests();
} catch (error) {
  console.error(`${colors.red}Test runner failed:${colors.reset}`, error.message);
  console.error(error.stack);
  process.exit(1);
}
