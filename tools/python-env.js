/**
 * tools/python-env.js — Python interpreter resolution for BMAD-METHOD validators
 *
 * The fork's Stories 10.27+ require Python ≥ 3.11 (e.g. `from enum import StrEnum`).
 * On a fresh clone there's no guarantee that `python3` on PATH meets that bar
 * (macOS ships 3.9, many Linux distros ship 3.10). This helper lets the JS-side
 * tools (`validate-compile.js`, `invoke-python.js`, smoke tests, etc.) spawn
 * a qualifying interpreter without each caller having to know about it.
 *
 * Resolution order:
 *   1. `python3` / `python` on PATH at ≥ 3.11 — return the absolute path
 *   2. `.venv/bin/python3` (or `.venv\Scripts\python.exe` on Windows) at ≥ 3.11
 *   3. `uv run --python 3.13 --with pyyaml python3` — return that wrapper
 *   4. If `uv` is also missing, throw with a remediation message
 *
 * Usage:
 *
 *   const { resolvePythonInvocation } = require('./tools/python-env.js');
 *   const { cmd, args, prefix } = resolvePythonInvocation({ withDeps: ['pyyaml'] });
 *   // cmd is 'python3' (or 'uv'), args includes any `--with X` and the script path
 *   // prefix is an extra prefix arg list for spawn() (for uv, args shift into the spawn)
 *
 *   // Simple spawn form (preferred):
 *   const { spawnArgs } = resolvePythonInvocation({ withDeps: ['pyyaml'] });
 *   spawnSync(spawnArgs[0], spawnArgs.slice(1).concat(['path/to/script.py']), { ... });
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const MIN_PYTHON = { major: 3, minor: 11 };
const REPO_ROOT = path.resolve(__dirname, '..');

/**
 * Parse `python3 --version` output ("Python 3.13.14") into {major, minor, patch}.
 * @param {string} output
 * @returns {{major: number, minor: number, patch: number, raw: string} | null}
 */
function parsePythonVersion(output) {
  if (!output) return null;
  const match = output.match(/Python\s+(\d+)\.(\d+)(?:\.(\d+))?/i);
  if (!match) return null;
  return {
    major: Number(match[1]),
    minor: Number(match[2]),
    patch: Number(match[3] || 0),
    raw: `${match[1]}.${match[2]}.${match[3] || 0}`,
  };
}

/**
 * Detect whether the named binary qualifies as Python ≥ 3.11.
 * @param {string} bin
 * @returns {{version: object, path: string} | null}
 */
function probePython(bin) {
  let result;
  try {
    result = spawnSync(bin, ['--version'], {
      encoding: 'utf8',
      timeout: 5000,
      windowsHide: true,
    });
  } catch {
    return null;
  }
  if (!result || result.error || result.status !== 0) return null;
  const version = parsePythonVersion(`${result.stdout || ''}\n${result.stderr || ''}`);
  if (!version) return null;
  if (version.major < MIN_PYTHON.major || (version.major === MIN_PYTHON.major && version.minor < MIN_PYTHON.minor)) {
    return null;
  }
  // Resolve to absolute path so spawn() doesn't pick up a different shim.
  const which = spawnSync('which', [bin], { encoding: 'utf8' }).stdout?.trim();
  return { version, path: which || bin };
}

/**
 * Detect `uv` on PATH.
 * @returns {{version: {raw: string}} | null}
 */
function probeUv() {
  let result;
  try {
    result = spawnSync('uv', ['--version'], {
      encoding: 'utf8',
      timeout: 5000,
      windowsHide: true,
    });
  } catch {
    return null;
  }
  if (!result || result.error || result.status !== 0) return null;
  const match = `${result.stdout || ''}\n${result.stderr || ''}`.match(/uv\s+(\d+\.\d+(?:\.\d+)?)/i);
  if (!match) return null;
  return { version: { raw: match[1] } };
}

/**
 * Resolve the spawnable Python invocation.
 *
 * Returns `{ kind, binary, version, uv }` where:
 *   - kind: 'python' (direct interpreter) or 'uv' (must run via `uv run`)
 *   - binary: the absolute path to `python3` (or 'uv' when kind==='uv')
 *   - version: parsed {major, minor, patch, raw} for diagnostics
 *   - uv: present only when kind==='uv' (for diagnostics)
 *
 * Throws with a remediation message if no qualifying interpreter is available.
 *
 * @returns {{kind: 'python'|'uv', binary: string, version: object, uv?: object}}
 */
function resolvePythonInterpreter() {
  const candidates = [process.platform === 'win32' ? 'python' : 'python3', process.platform === 'win32' ? 'python3' : 'python'];

  // 1 + 2: direct + project-local venv
  for (const bin of candidates) {
    const probed = probePython(bin);
    if (probed) return { kind: 'python', binary: probed.path, version: probed.version };
  }

  const venvPython =
    process.platform === 'win32' ? path.join(REPO_ROOT, '.venv', 'Scripts', 'python.exe') : path.join(REPO_ROOT, '.venv', 'bin', 'python3');
  if (fs.existsSync(venvPython)) {
    const probed = probePython(venvPython);
    if (probed) return { kind: 'python', binary: probed.path, version: probed.version };
  }

  // 3: uv fallback
  const uv = probeUv();
  if (uv) {
    return { kind: 'uv', binary: 'uv', version: { major: 3, minor: 13, patch: 0, raw: 'via uv' }, uv: uv.version };
  }

  // 4: no path — throw with remediation
  const err = new Error(
    'No Python ≥ 3.11 available, and `uv` is not on PATH.\n' +
      'BMAD-METHOD validators (validate:compile, test:validate-compile, test_migration_equivalence)\n' +
      'require Python 3.11+ since Stories 10.27+. Install `uv` so the build pipeline can\n' +
      'provision a 3.11+ interpreter on demand:\n' +
      '  macOS/Linux:  curl -LsSf https://astral.sh/uv/install.sh | sh\n' +
      '  Windows:      powershell -c "irm https://astral.sh/uv/install.ps1 | iex"\n' +
      '  Homebrew:     brew install uv\n' +
      '  Docs:         https://docs.astral.sh/uv/getting-started/installation/\n' +
      'See docs/how-to/python-environment.md for full setup.',
  );
  err.code = 'PYTHON_ENV_UNAVAILABLE';
  throw err;
}

/**
 * Build the full spawn arg list for a Python script invocation.
 *
 * @param {{interpreter?: object, withDeps?: string[], scriptArgs?: string[]}} opts
 * @returns {{cmd: string, args: string[]}}
 *   - cmd: the binary to spawn (python3 absolute path, or 'uv')
 *   - args: array of args, ending with the script-relative args
 *
 * Example:
 *   resolvePythonInvocation({ withDeps: ['pyyaml'], scriptArgs: ['script.py', '--foo'] })
 *   → { cmd: '/usr/bin/python3', args: ['script.py', '--foo'] }                          // direct
 *   → { cmd: 'uv', args: ['run', '--python', '3.13', '--with', 'pyyaml', 'python3', 'script.py', '--foo'] }  // uv
 */
function resolvePythonInvocation(opts = {}) {
  const interpreter = opts.interpreter || resolvePythonInterpreter();
  const scriptArgs = opts.scriptArgs || [];
  const withDeps = opts.withDeps || [];

  if (interpreter.kind === 'python') {
    return { cmd: interpreter.binary, args: [...scriptArgs] };
  }

  // uv form: uv run [--python 3.13] [--with X ...] python3 <scriptArgs>
  const args = ['run'];
  // Pin the interpreter version so contributors get reproducible behavior.
  args.push('--python', '3.13');
  for (const dep of withDeps) {
    args.push('--with', dep);
  }
  args.push('python3', ...scriptArgs);
  return { cmd: interpreter.binary, args };
}

module.exports = {
  parsePythonVersion,
  probePython,
  probeUv,
  resolvePythonInterpreter,
  resolvePythonInvocation,
  MIN_PYTHON,
  REPO_ROOT,
};
