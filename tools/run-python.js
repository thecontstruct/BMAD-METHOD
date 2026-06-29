/**
 * tools/run-python.js — npm-script entry point for Python invocations
 *
 * Mirrors tools/python-env.js's resolution but emits a `spawn` (not `spawnSync`)
 * so the parent shell sees the child's stdout/stderr/exit code directly. This
 * lets `npm run test:python` / `npm run test:e2e` flow the test output up to
 * the operator instead of swallowing it inside a `spawnSync` return value.
 *
 * Resolution order (same as tools/python-env.js):
 *   1. `python3` / `python` on PATH at ≥ 3.11 — invoke directly
 *   2. `.venv/bin/python3` at ≥ 3.11
 *   3. `uv run --python 3.13 --with pyyaml --with pytest python3 ...`
 *   4. Throw with remediation if no qualifying interpreter is available
 *
 * Usage:
 *   node tools/run-python.js <script.py> [args...]
 *   node tools/run-python.js -m unittest discover -s test/python
 *
 * Test deps (`pyyaml`, `pytest`) are auto-injected via `uv run --with` when the
 * uv fallback path is used; they're no-ops when running a real interpreter
 * (the deps are expected to be installed in the venv/system site-packages).
 */
'use strict';

const { spawn } = require('node:child_process');
const { resolvePythonInterpreter, resolvePythonInvocation } = require('./python-env');

function main() {
  // Skip argv[0] (node) and argv[1] (this script).
  const scriptArgs = process.argv.slice(2);
  if (scriptArgs.length === 0) {
    console.error('usage: node tools/run-python.js <script.py|-m module> [args...]');
    process.exit(2);
  }

  const interpreter = resolvePythonInterpreter();
  const inv = resolvePythonInvocation({
    interpreter,
    scriptArgs,
    withDeps: ['pyyaml', 'pytest'],
  });

  const child = spawn(inv.cmd, inv.args, {
    stdio: 'inherit',
    env: process.env,
    cwd: process.cwd(),
  });

  child.on('error', (err) => {
    console.error(`run-python: failed to spawn ${inv.cmd}: ${err.message}`);
    process.exit(127);
  });
  child.on('close', (code, signal) => {
    if (signal) {
      // 128 + signal number for shells; npm scripts usually just propagate the
      // raw signal via the child process group.
      process.kill(process.pid, signal);
      return;
    }
    process.exit(code ?? 1);
  });
}

main();
