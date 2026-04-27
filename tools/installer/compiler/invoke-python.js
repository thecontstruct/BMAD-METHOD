'use strict';

const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs/promises');

// Frozen for v1 — mirrors bmad_compile.variants.KNOWN_IDES
const KNOWN_IDES = ['cursor', 'claudecode'];

/**
 * Spawn python3 and collect stdout/stderr, resolving with { code, stdout, stderr }.
 */
function _spawnPython(args, options = {}) {
  return new Promise((resolve, reject) => {
    let stdout = '';
    let stderr = '';
    const proc = spawn('python3', args, {
      ...options,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    proc.on('error', (err) => reject(err));
    proc.stdout.on('data', (d) => {
      stdout += d;
    });
    proc.stderr.on('data', (d) => {
      stderr += d;
    });
    proc.on('close', (code) => resolve({ code, stdout, stderr }));
  });
}

/**
 * Check that python3 >= 3.11 is available on PATH.
 *
 * @returns {Promise<{ok: true, version: string} | {ok: false, reason: 'not found'|'too old', detected: string}>}
 */
async function checkPythonVersion() {
  let result;
  try {
    result = await _spawnPython(['--version']);
  } catch {
    return { ok: false, reason: 'not found', detected: 'python3 not on PATH' };
  }

  // python3 --version prints to stdout on 3.x (stderr on 2.x); capture both.
  // Search anywhere in output so pyenv/wrapper preamble lines don't block the match.
  // Patch component is optional — some custom builds emit only major.minor.
  const raw = (result.stdout + result.stderr).trim();
  const match = /Python\s+(\d+)\.(\d+)(?:\.(\d+))?/.exec(raw);
  if (!match) {
    return { ok: false, reason: 'not found', detected: 'python3 not on PATH' };
  }

  const major = parseInt(match[1], 10);
  const minor = parseInt(match[2], 10);
  const patch = match[3] ?? '0';
  const versionStr = `${major}.${minor}.${patch}`;

  if (major < 3 || (major === 3 && minor < 11)) {
    return { ok: false, reason: 'too old', detected: `Python ${versionStr}` };
  }

  return { ok: true, version: versionStr };
}

/**
 * Check if `dirName` directory is a migrated-skill candidate per the basename-match rule (R3-A1).
 * A dir <dir>/ matches iff it contains exactly <dir>.template.md OR <dir>.<ide>.template.md
 * for ide ∈ KNOWN_IDES.
 */
function _isSkillDir(dirName, fileNames) {
  if (fileNames.includes(`${dirName}.template.md`)) return true;
  for (const ide of KNOWN_IDES) {
    if (fileNames.includes(`${dirName}.${ide}.template.md`)) return true;
  }
  return false;
}

/**
 * Recursively walk a module source tree checking for migrated skills.
 * Cap at maxDepth levels from the source root.
 */
async function _hasSkillsInTree(dirPath, depth, maxDepth) {
  if (depth > maxDepth) return false;
  let entries;
  try {
    entries = await fs.readdir(dirPath, { withFileTypes: true });
  } catch {
    return false;
  }

  const fileNames = entries.filter((e) => e.isFile()).map((e) => e.name);
  const dirName = path.basename(dirPath);
  if (_isSkillDir(dirName, fileNames)) return true;

  for (const entry of entries) {
    if (entry.isDirectory()) {
      const found = await _hasSkillsInTree(path.join(dirPath, entry.name), depth + 1, maxDepth);
      if (found) return true;
    }
  }
  return false;
}

/**
 * Check whether any selected module's source tree contains migrated skills per the
 * basename-match detection rule (R3-A1).
 *
 * Uses `officialModules.findModuleSource(moduleCode)` — the actual module-source roots
 * (`src/bmm-skills/` for bmm, `src/core-skills/` for core) differ from the module code.
 *
 * @param {Object} paths - InstallPaths instance
 * @param {string[]} modules - array of module codes
 * @param {Object} officialModules - OfficialModules instance
 * @returns {Promise<boolean>}
 */
async function hasMigratedSkillsInScope(paths, modules, officialModules) {
  for (const moduleCode of modules) {
    let sourcePath;
    try {
      sourcePath = await officialModules.findModuleSource(moduleCode);
    } catch {
      // Network error on external clone — assume migrated skills exist so the
      // Python-version message wins over a confusing clone failure.
      return true;
    }
    if (!sourcePath) continue;

    const found = await _hasSkillsInTree(sourcePath, 0, 6);
    if (found) return true;
  }
  return false;
}

/**
 * Format a kind:"error" event in caret-friendly style mirroring errors.format().
 */
function _formatError(event) {
  if (!event) return 'compile.py --install-phase failed (no error event emitted)';
  const file = event.file ?? '<unknown>';
  const line = event.line == null ? '?' : event.line;
  const col = event.col == null ? '?' : event.col;
  const code = event.code ?? 'UNKNOWN';
  const msg = event.message ?? '(no message)';
  let out = `${code}: ${file}:${line}:${col}: ${msg}`;
  if (event.hint) out += `\n    hint: ${event.hint}`;
  return out;
}

/**
 * Run `compile.py --install-phase` and parse the newline-delimited JSON stdout.
 *
 * @param {Object} opts
 * @param {string} opts.bmadDir   - Path to the installed _bmad directory
 * @param {string} opts.projectRoot - Project root (cwd for the Python subprocess)
 * @param {Function} [opts.message] - Progress callback, called with each skill name
 * @returns {Promise<{compiled: number, writtenFiles: string[], lockfilePath: string|null}>}
 */
async function runInstallPhase({ bmadDir, projectRoot, message }) {
  const compilePy = path.join(bmadDir, 'scripts', 'compile.py');

  let result;
  try {
    result = await _spawnPython([compilePy, '--install-phase', '--install-dir', bmadDir], {
      cwd: projectRoot,
    });
  } catch (error) {
    throw new Error(`Failed to spawn python3: ${error.message}`);
  }

  const lines = result.stdout.split('\n').filter((l) => l.trim() !== '');
  const events = [];
  let firstError = null;

  for (const line of lines) {
    let event;
    try {
      event = JSON.parse(line);
    } catch {
      throw new Error(`compile.py --install-phase emitted non-JSON line:\n  ${line.slice(0, 200)}\n\nstderr:\n${result.stderr}`);
    }
    events.push(event);

    if (event.kind === 'skill' && message) {
      message(`Compiling ${event.skill}...`);
    }
    if (event.kind === 'error' && !firstError) {
      firstError = event;
    }
  }

  if (result.code !== 0 || firstError) {
    let msg = _formatError(firstError);
    if (result.stderr.trim()) {
      msg += `\n\nstderr:\n${result.stderr.trim()}`;
    }
    throw new Error(msg);
  }

  const summary = events.toReversed().find((e) => e.kind === 'summary');
  if (!summary) {
    let msg = 'compile.py --install-phase did not emit a summary event';
    if (result.stderr.trim()) msg += `\n\nstderr:\n${result.stderr.trim()}`;
    throw new Error(msg);
  }

  const writtenFiles = [];
  for (const event of events) {
    if (event.kind === 'skill' && Array.isArray(event.written)) {
      for (const f of event.written) writtenFiles.push(f);
    }
  }

  return {
    compiled: summary.compiled,
    writtenFiles,
    lockfilePath: summary.lockfile_path ?? null,
  };
}

module.exports = { checkPythonVersion, hasMigratedSkillsInScope, runInstallPhase };
