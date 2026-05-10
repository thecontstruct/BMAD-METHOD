'use strict';

const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs/promises');
const os = require('node:os');
const crypto = require('node:crypto');

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
    proc.on('close', (code, signal) => resolve({ code, stdout, stderr, signal }));
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
function _formatError(event, source = '--install-phase') {
  if (!event) return `compile.py ${source} failed (no error event emitted)`;
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

/**
 * Recursively walk a module source tree, accumulating absolute paths of all
 * migrated-skill candidates per the basename-match rule (R3-A1).
 *
 * Unlike `_hasSkillsInTree` (which short-circuits on first match), this collects
 * EVERY matching skill — required by `enumerateMigratedSkills` for batch input.
 */
async function _collectSkillsInTree(dirPath, depth, maxDepth, results) {
  if (depth > maxDepth) return;
  let entries;
  try {
    entries = await fs.readdir(dirPath, { withFileTypes: true });
  } catch {
    return;
  }

  const fileNames = entries.filter((e) => e.isFile()).map((e) => e.name);
  const dirName = path.basename(dirPath);
  if (_isSkillDir(dirName, fileNames)) {
    results.push(String(dirPath));
    return; // do not recurse into a skill dir
  }

  for (const entry of entries) {
    if (entry.isDirectory()) {
      await _collectSkillsInTree(path.join(dirPath, entry.name), depth + 1, maxDepth, results);
    }
  }
}

/**
 * Enumerate every migrated skill across the selected modules' source trees,
 * returning batch-input rows of `{skillDir, installDir}`. For a single-root
 * install, every `installDir` is `paths.bmadDir`.
 *
 * Mirrors `hasMigratedSkillsInScope`'s discovery semantics, including the
 * `findModuleSource` network-error fallback (returns empty array AND keeps the
 * boolean preflight at installer.js:48 effective; the optimistic-empty path
 * means zero skills compile when the source isn't cloned, which is safe).
 *
 * @param {Object} paths - InstallPaths instance (uses paths.bmadDir)
 * @param {string[]} modules - array of module codes
 * @param {Object} officialModules - OfficialModules instance
 * @returns {Promise<Array<{skillDir: string, installDir: string}>>}
 */
async function enumerateMigratedSkills(paths, modules, officialModules) {
  const skills = [];
  for (const moduleCode of modules) {
    let sourcePath;
    try {
      sourcePath = await officialModules.findModuleSource(moduleCode);
    } catch (error) {
      // Network/clone error: log and skip this module (do NOT propagate). The
      // boolean preflight at installer.js:48 stays effective via its own try/catch.
      console.warn(`bmad: enumerateMigratedSkills could not resolve source for ${moduleCode}: ${error.message}`);
      continue;
    }
    if (!sourcePath) continue;

    const moduleSkills = [];
    await _collectSkillsInTree(sourcePath, 0, 6, moduleSkills);
    for (const skillDir of moduleSkills) {
      skills.push({ skillDir, installDir: paths.bmadDir });
    }
  }
  return skills;
}

/**
 * Error thrown by `runBatchInstall` when compilation fails after one or more
 * skills were successfully written. The `writtenFiles` property carries the
 * partial manifest of skill files written before the failure.
 *
 * Callers that only need "did it succeed?" continue to use try/catch unchanged.
 * Callers that need the partial manifest check:
 *   `err instanceof BatchInstallError && err.writtenFiles`
 */
class BatchInstallError extends Error {
  constructor(message, { writtenFiles = [] } = {}) {
    super(message);
    this.name = 'BatchInstallError';
    this.writtenFiles = writtenFiles;
  }
}

/**
 * Run `compile.py --batch <skills.json>` and parse the newline-delimited JSON stdout.
 *
 * Writes a temp `skills.json` describing every batch entry, spawns python3 once
 * (single interpreter cold-start), parses NDJSON output, returns the summary.
 * Cleans up the temp file in a `finally` block.
 *
 * @param {Object} opts
 * @param {Array<{skillDir: string, installDir: string}>} opts.skills
 * @param {string} opts.bmadDir   - Path to the installed _bmad directory (compile.py lives here)
 * @param {string} opts.projectRoot - cwd for the Python subprocess
 * @param {Function} [opts.message] - Progress callback, called with each skill name
 * @returns {Promise<{compiled: number, writtenFiles: string[], lockfilePath: string|null}>}
 * @throws {BatchInstallError} when a per-skill error event is emitted or exit code is non-zero.
 *   `err.writtenFiles` carries all skill paths written before the failure.
 */
async function runBatchInstall({ skills, bmadDir, projectRoot, message }) {
  const compilePy = path.join(bmadDir, 'scripts', 'compile.py');
  try {
    await fs.access(compilePy);
  } catch {
    throw new Error(`compile.py not found at: ${compilePy}`);
  }

  const tmpFile = path.join(os.tmpdir(), `bmad-batch-${crypto.randomUUID()}.json`);
  const payload = skills.map(({ skillDir, installDir }) => ({
    skill_dir: path.resolve(skillDir),
    install_dir: path.resolve(installDir),
  }));

  try {
    try {
      await fs.writeFile(tmpFile, JSON.stringify(payload), 'utf8');
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
      try {
        event = JSON.parse(line);
      } catch {
        const sigMsg = result.signal ? ` (process killed by signal ${result.signal})` : '';
        throw new Error(`compile.py --batch emitted non-JSON line${sigMsg}:\n  ${line.slice(0, 200)}\n\nstderr:\n${result.stderr}`);
      }
      events.push(event);
      // Skip the progress callback for hash-skipped events (compiled === false /
      // status === "skipped"); the user shouldn't see "Compiling X..." for a no-op.
      if (event.kind === 'skill' && event.compiled !== false && message && event.skill) {
        message(`Compiling ${event.skill}...`);
      }
      if (event.kind === 'error' && !firstError) firstError = event;
    }

    // Accumulate writtenFiles BEFORE the error check — events[] is already
    // complete at this point. This ensures the partial manifest is preserved
    // regardless of whether a subsequent error throws (AC-1 / L520).
    const writtenFiles = [];
    for (const event of events) {
      if (event.kind === 'skill' && Array.isArray(event.written)) {
        for (const f of event.written) writtenFiles.push(f);
      }
    }

    if (result.code !== 0 || firstError) {
      let msg = _formatError(firstError, '--batch');
      if (result.signal) msg += ` (process killed by signal ${result.signal})`;
      if (result.stderr.trim()) msg += `\n\nstderr:\n${result.stderr.trim()}`;
      throw new BatchInstallError(msg, { writtenFiles });
    }

    const summary = events.toReversed().find((e) => e.kind === 'summary');
    if (!summary) {
      let msg = 'compile.py --batch did not emit a summary event';
      if (result.stderr.trim()) msg += `\n\nstderr:\n${result.stderr.trim()}`;
      throw new BatchInstallError(msg, { writtenFiles });
    }

    // R2 F6: rare path — process exits 0 but a signal was received (Windows
    // signal semantics differ from POSIX; SIGINT/SIGTERM after summary-flush
    // can leave code === 0). The summary made it through so the run is
    // semantically successful, but the signal is worth surfacing.
    if (result.signal) {
      console.warn(`bmad: compile.py --batch received signal ${result.signal} (exit code 0; summary emitted)`);
    }

    return {
      compiled: summary.compiled,
      writtenFiles,
      lockfilePath: summary.lockfile_path ?? null,
    };
  } finally {
    await fs.unlink(tmpFile).catch((error) => {
      if (error.code !== 'ENOENT') {
        console.warn(`bmad: failed to clean up batch temp file ${tmpFile}: ${error.message}`);
      }
    });
  }
}

/**
 * Run `upgrade.py --dry-run --json` and return the parsed drift report object.
 *
 * @param {Object} opts
 * @param {string} opts.upgradePy   - Path to upgrade.py
 * @param {string} opts.projectRoot - Project root (cwd for the Python subprocess)
 * @returns {Promise<Object>} Parsed JSON drift report (schema_version, drift, summary)
 */
async function runUpgradeDryRun({ upgradePy, projectRoot }) {
  let result;
  try {
    result = await _spawnPython([upgradePy, '--dry-run', '--json', '--project-root', projectRoot], { cwd: projectRoot });
  } catch (error) {
    throw new Error(`Failed to spawn upgrade.py: ${error.message}`);
  }
  if (result.code === 1) {
    throw new Error(`upgrade.py --dry-run failed:\n${result.stderr}`);
  }
  // Exit code 0 always for --dry-run (no drift or drift found, both return 0).
  try {
    return JSON.parse(result.stdout);
  } catch {
    throw new Error(`upgrade.py --dry-run emitted non-JSON output:\n${result.stdout.slice(0, 200)}`);
  }
}

/**
 * Run `upgrade.py --yes` to force upgrade past drift.
 *
 * @param {Object} opts
 * @param {string} opts.upgradePy   - Path to upgrade.py
 * @param {string} opts.projectRoot - Project root (cwd for the Python subprocess)
 * @returns {Promise<void>}
 */
async function runUpgradeYes({ upgradePy, projectRoot }) {
  const result = await _spawnPython([upgradePy, '--yes', '--project-root', projectRoot], { cwd: projectRoot });
  if (result.code !== 0) {
    throw new Error(`upgrade.py --yes failed (exit ${result.code}):\n${result.stderr}`);
  }
}

/**
 * Detect the Model tier of a skill directory (Story 7.3 OQ-1=A).
 *
 * Model 3: BOTH `<basename>.template.md` (or `<basename>.<ide>.template.md`) AND `SKILL.md` present.
 * Model 2: `*.template.md` present, NO `SKILL.md`.
 * Model 1: NO `*.template.md` (precompiled-only or non-skill).
 *
 * @param {string} skillDirPath - Absolute path to the skill directory.
 * @returns {Promise<'model1' | 'model2' | 'model3'>}
 */
async function detectModelTier(skillDirPath) {
  let entries;
  try {
    entries = await fs.readdir(skillDirPath, { withFileTypes: true });
  } catch (error) {
    // ECH-1 (Phil R1 2026-05-08): only ENOENT (dir absent) is a legitimate model1 default.
    // EACCES / ENOTDIR / other errors indicate a real problem — surfacing them gives the
    // operator a useful diagnostic instead of a misleading "Python 3.11+ required" error
    // routed through applyModel3FallbackIfAllEligible's `return false` path.
    if (error && error.code === 'ENOENT') return 'model1';
    throw error;
  }
  const fileNames = entries.filter((e) => e.isFile()).map((e) => e.name);
  const dirName = path.basename(skillDirPath);
  const hasTemplate = _isSkillDir(dirName, fileNames);
  const hasSkillMd = fileNames.includes('SKILL.md');

  if (hasTemplate && hasSkillMd) return 'model3';
  if (hasTemplate) return 'model2';
  return 'model1';
}

/**
 * Copy a Model 3 precompiled `SKILL.md` from a skill source directory into the install
 * directory at the same path layout that `runBatchInstall` would produce.
 *
 * Path layout: `<installDir>/<moduleName>/<skillBasename>/SKILL.md` where
 * `moduleName = path.basename(path.dirname(skillDir))` — mirrors compile.py's batch-mode
 * scenario_root derivation (lockfile.py:206 — frag.path = _normalize_path(...)).
 *
 * Idempotency contract (BH-2 / ECH-4 documented per Phil 2026-05-08): `fs.copyFile` overwrites
 * the destination by default (no `COPYFILE_EXCL` flag); a partially-copied multi-skill batch
 * left behind by a prior failed `applyModel3FallbackIfAllEligible` is safely overwritten on
 * retry. Callers do NOT need a rollback path for partial failures — the next successful run
 * restores correct state.
 *
 * Security guards:
 *   - BH-1 (DN-R2-2=A): **lexical** containment check via `path.resolve` — asserts resolved
 *     `destDir` starts with `installDirAbs + path.sep`. Defends against tampered `..` segments
 *     in `moduleName` / `skillBasename`. Does NOT follow symlinks (`path.resolve` is purely
 *     lexical); operator is responsible for source-tree integrity if a symlinked installDir
 *     or pre-existing dangling symlink could be exploited. Realpath-based defense out of scope
 *     for Story 7.3.
 *   - ECH-7 (R2-BH-7 strengthened): reject empty / `.` / `path.sep` moduleName so degenerate
 *     skillDir inputs (`/`, `./test-skill`) fail loud rather than silently producing a wrong
 *     install path layout.
 *   - BH-3 / ECH-2 (R2-BH-3 broadened): wrap any `copyFile` error with skillBasename + error
 *     code context so TOCTOU races (ENOENT, EISDIR, EACCES, EBUSY) yield an actionable
 *     diagnostic identifying which skill failed.
 *
 * @param {string} skillDir - Source skill directory containing the precompiled SKILL.md.
 * @param {string} installDir - Destination install root.
 * @returns {Promise<void>}
 */
async function copyPrecompiledFallback(skillDir, installDir) {
  const sourceSkillMd = path.join(skillDir, 'SKILL.md');
  const moduleName = path.basename(path.dirname(skillDir));
  const skillBasename = path.basename(skillDir);
  // ECH-7 + R2-BH-7 (Phil R2 2026-05-08): reject empty / '.' / path-sep moduleName.
  // Catches degenerate inputs like `/` (basename → '') and `./test-skill` (basename of dirname → '.')
  // that would otherwise silently produce a wrong install path layout.
  if (!moduleName || moduleName === '.' || moduleName === path.sep) {
    throw new Error(
      `copyPrecompiledFallback: could not derive moduleName from skillDir path: ${skillDir} (got moduleName=${JSON.stringify(moduleName)})`,
    );
  }
  const installDirAbs = path.resolve(installDir);
  const destDir = path.resolve(path.join(installDirAbs, moduleName, skillBasename));
  // BH-1: containment check — reject any path that escapes installDir (tampered fragments[0]
  // or symlink-injected moduleName must not resolve outside the install root).
  if (destDir !== installDirAbs && !destDir.startsWith(installDirAbs + path.sep)) {
    throw new Error(`copyPrecompiledFallback: resolved destination "${destDir}" escapes installDir "${installDirAbs}"`);
  }
  const destSkillMd = path.join(destDir, 'SKILL.md');
  await fs.mkdir(destDir, { recursive: true });
  try {
    // BH-2 / ECH-4: fs.copyFile overwrites the destination by default — partial-batch retry is safe.
    await fs.copyFile(sourceSkillMd, destSkillMd);
  } catch (error) {
    // BH-3 / ECH-2 (R2-BH-3 broadened per Phil 2026-05-08): wrap ANY copyFile error with the
    // skill path + error code so TOCTOU races (ENOENT, EISDIR, EACCES, EBUSY, etc.) yield an
    // actionable diagnostic identifying which skill failed. The prior ENOENT-only wrap left
    // EISDIR/EACCES/EBUSY producing raw fs errors with no skill context.
    if (error && error.code) {
      throw new Error(
        `copyPrecompiledFallback: failed to copy SKILL.md (skill="${skillBasename}", source="${sourceSkillMd}", code=${error.code}): ${error.message}`,
      );
    }
    throw error;
  }
}

/**
 * Routing helper for Model 3 compiler-absent fallback (Story 7.3 OQ-1=A, DN-4=G3).
 *
 * If EVERY skill in the input list is Model 3 (precompiled SKILL.md available next to the
 * template), copy each precompiled SKILL.md verbatim to its install location. Returns true.
 *
 * If ANY skill is not Model 3, return false WITHOUT copying anything — the caller is
 * expected to throw the "Python 3.11+ required" error.
 *
 * Tested directly in `test/test-model3-distribution-matrix.js` (DN-4=G3 — no Installer.install
 * indirection; the helper is the routing edge under test).
 *
 * H1 scope (DN-5=H1): Story 7.3 minimal — installer.js callers should `return;` after a
 * successful applyModel3FallbackIfAllEligible to skip IDE setup, manifest generation, and
 * lockfile writes. Story 7.6 refines this to a flag-based continuation that completes the
 * full install flow.
 *
 * @param {Array<{skillDir: string, installDir: string}>} skills - skill batch input.
 * @returns {Promise<boolean>} true if all skills are Model 3 and fallback was applied.
 */
async function applyModel3FallbackIfAllEligible(skills) {
  // DN-R1-1=A (Phil R1 2026-05-08): empty-skills guard. The function name says "fallback
  // applied"; zero copies means it wasn't. Without this guard, an empty array (e.g. when
  // every module's findModuleSource throws and enumerateMigratedSkills returns []) loops
  // zero times in pass 1, returns vacuous true, and the installer.js caller `return`s with
  // a silent no-op install. Returning false here forces the caller to throw.
  if (skills.length === 0) return false;
  // R2-BH-4 (Phil R2 2026-05-08): parallelize tier detection. Each detectModelTier call is
  // an independent fs.readdir — sequential await is O(n) round-trips on a slow disk; Promise.all
  // collapses to a single tick of concurrent I/O. Order-independent; correctness identical.
  const tiers = await Promise.all(skills.map((s) => detectModelTier(s.skillDir)));
  if (tiers.some((tier) => tier !== 'model3')) return false;
  for (const { skillDir, installDir } of skills) {
    await copyPrecompiledFallback(skillDir, installDir);
  }
  return true;
}

module.exports = {
  checkPythonVersion,
  hasMigratedSkillsInScope,
  enumerateMigratedSkills,
  runInstallPhase,
  runBatchInstall,
  BatchInstallError,
  runUpgradeDryRun,
  runUpgradeYes,
  // Story 7.3 (Model 3 distribution matrix; OQ-1=A, DN-4=G3, DN-5=H1).
  detectModelTier,
  copyPrecompiledFallback,
  applyModel3FallbackIfAllEligible,
};
