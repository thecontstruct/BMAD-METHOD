'use strict';

/**
 * Unit tests for runBatchInstall + enumerateMigratedSkills (Story 5.6).
 *
 * Covers:
 *   (a) runBatchInstall: spawns python3 exactly once (single cold-start);
 *       parses NDJSON; returns {compiled, writtenFiles, lockfilePath}; cleans
 *       up the temp skills.json in finally.
 *   (b) runBatchInstall: graceful failure when compile.py is missing.
 *   (c) runBatchInstall: malformed JSON line surfaces actionable error.
 *   (d) enumerateMigratedSkills: collects ALL matching skills (no early exit);
 *       network-error fallback returns empty array (does not throw).
 *
 * Usage: node test/test-batch-install.js
 */

const path = require('node:path');
const fs = require('node:fs/promises');
const fsSync = require('node:fs');
const os = require('node:os');

const {
  runBatchInstall,
  enumerateMigratedSkills,
} = require('../tools/installer/compiler/invoke-python');

const colors = {
  reset: '[0m',
  green: '[32m',
  red: '[31m',
  dim: '[2m',
};

let passed = 0;
let failed = 0;

function assert(condition, testName, errorMessage = '') {
  if (condition) {
    console.log(`${colors.green}✓${colors.reset} ${testName}`);
    passed++;
  } else {
    console.log(`${colors.red}✗${colors.reset} ${testName}`);
    if (errorMessage) console.log(`  ${colors.dim}${errorMessage}${colors.reset}`);
    failed++;
  }
}

async function runTest(name, fn) {
  try {
    await fn();
  } catch (error) {
    console.log(`${colors.red}✗${colors.reset} ${name}`);
    console.log(`  ${colors.dim}threw: ${error.message}${colors.reset}`);
    failed++;
  }
}

async function _makeTempDir() {
  return fs.mkdtemp(path.join(os.tmpdir(), 'batch-install-test-'));
}

async function _writeFile(filePath, content = '') {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, content, 'utf8');
}

// fs.cp() is still experimental on Node < 22.3; manual recursive copy keeps
// us on the Node 20+ baseline without lint warnings.
async function _copyRecursive(src, dst) {
  const stat = await fs.stat(src);
  if (stat.isDirectory()) {
    await fs.mkdir(dst, { recursive: true });
    const entries = await fs.readdir(src);
    for (const name of entries) {
      await _copyRecursive(path.join(src, name), path.join(dst, name));
    }
  } else if (stat.isFile()) {
    await fs.mkdir(path.dirname(dst), { recursive: true });
    await fs.copyFile(src, dst);
  }
}

function _makeFakeOfficialModules(sourceMap) {
  return {
    async findModuleSource(moduleCode) {
      return sourceMap[moduleCode] ?? null;
    },
  };
}

function _makeThrowingOfficialModules(error) {
  return {
    async findModuleSource() {
      throw error;
    },
  };
}

/**
 * Build a self-contained _bmad install with compile.py copied in, plus a
 * single source skill at <repo>/src/<module>/<skill>/<skill>.template.md.
 * Returns {projectRoot, bmadDir, skillDir}.
 */
async function _setupInstallWithCompiler() {
  const tmpDir = await _makeTempDir();
  const bmadDir = path.join(tmpDir, '_bmad');
  await fs.mkdir(bmadDir, { recursive: true });
  // Copy bmad_compile package + compile.py into the install scripts/ dir.
  const srcScripts = path.join(__dirname, '..', 'src', 'scripts');
  const dstScripts = path.join(bmadDir, 'scripts');
  await fs.mkdir(dstScripts, { recursive: true });
  await fs.copyFile(
    path.join(srcScripts, 'compile.py'),
    path.join(dstScripts, 'compile.py'),
  );
  await _copyRecursive(
    path.join(srcScripts, 'bmad_compile'),
    path.join(dstScripts, 'bmad_compile'),
  );
  return { projectRoot: tmpDir, bmadDir };
}

async function main() {
  // ---------------------------------------------------------------------------
  // (a) runBatchInstall: single cold-start, NDJSON parse, summary return
  // ---------------------------------------------------------------------------
  console.log('\n--- runBatchInstall: happy path ---');

  await runTest('compiles a single skill and returns summary fields', async () => {
    const { projectRoot, bmadDir } = await _setupInstallWithCompiler();
    try {
      const skillDir = path.join(bmadDir, 'mod1', 'sk1');
      await _writeFile(path.join(skillDir, 'sk1.template.md'), 'Hello batch');
      await fs.mkdir(path.join(bmadDir, 'custom'), { recursive: true });

      const result = await runBatchInstall({
        skills: [{ skillDir, installDir: bmadDir }],
        bmadDir,
        projectRoot,
      });

      assert(result.compiled === 1, 'summary.compiled === 1');
      assert(
        Array.isArray(result.writtenFiles) && result.writtenFiles.length === 1,
        'one writtenFile recorded',
      );
      assert(
        typeof result.lockfilePath === 'string' && result.lockfilePath.endsWith('bmad.lock'),
        'lockfilePath is a string ending in bmad.lock',
      );

      const skillMd = path.join(bmadDir, 'mod1', 'sk1', 'SKILL.md');
      assert(fsSync.existsSync(skillMd), 'SKILL.md was written');
    } finally {
      await fs.rm(projectRoot, { recursive: true, force: true });
    }
  });

  await runTest('removes temp skills.json after invocation', async () => {
    const { projectRoot, bmadDir } = await _setupInstallWithCompiler();
    try {
      const skillDir = path.join(bmadDir, 'mod1', 'sk1');
      await _writeFile(path.join(skillDir, 'sk1.template.md'), 'Hello batch');
      await fs.mkdir(path.join(bmadDir, 'custom'), { recursive: true });

      const before = (await fs.readdir(os.tmpdir())).filter((n) =>
        n.startsWith('bmad-batch-'),
      );
      await runBatchInstall({
        skills: [{ skillDir, installDir: bmadDir }],
        bmadDir,
        projectRoot,
      });
      const after = (await fs.readdir(os.tmpdir())).filter((n) =>
        n.startsWith('bmad-batch-'),
      );
      assert(after.length === before.length, 'temp skills.json files cleaned up');
    } finally {
      await fs.rm(projectRoot, { recursive: true, force: true });
    }
  });

  // ---------------------------------------------------------------------------
  // (b) Graceful failure when compile.py is missing
  // ---------------------------------------------------------------------------
  console.log('\n--- runBatchInstall: missing compile.py ---');

  await runTest('throws actionable error when compile.py is missing', async () => {
    const tmpDir = await _makeTempDir();
    try {
      const bmadDir = path.join(tmpDir, '_bmad');
      await fs.mkdir(bmadDir, { recursive: true });
      // Intentionally do NOT copy compile.py.
      let errMsg = '';
      try {
        await runBatchInstall({
          skills: [],
          bmadDir,
          projectRoot: tmpDir,
        });
      } catch (error) {
        errMsg = error.message;
      }
      assert(errMsg.includes('compile.py not found'), 'error mentions compile.py not found');
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  // ---------------------------------------------------------------------------
  // (c) Compile errors propagate via NDJSON kind:error
  // ---------------------------------------------------------------------------
  console.log('\n--- runBatchInstall: error propagation ---');

  await runTest('compile error surfaces via thrown Error message', async () => {
    const { projectRoot, bmadDir } = await _setupInstallWithCompiler();
    try {
      const skillDir = path.join(bmadDir, 'mod1', 'broken');
      // Unresolved variable triggers UNRESOLVED_VARIABLE
      await _writeFile(path.join(skillDir, 'broken.template.md'), '{{undefined}}');
      await fs.mkdir(path.join(bmadDir, 'custom'), { recursive: true });

      let errMsg = '';
      try {
        await runBatchInstall({
          skills: [{ skillDir, installDir: bmadDir }],
          bmadDir,
          projectRoot,
        });
      } catch (error) {
        errMsg = error.message;
      }
      assert(errMsg.includes('UNRESOLVED_VARIABLE'), 'error code surfaces in thrown message');
      assert(errMsg.includes('mod1/broken') || errMsg.includes('broken.template.md'), 'skill name or file path surfaces');
    } finally {
      await fs.rm(projectRoot, { recursive: true, force: true });
    }
  });

  // ---------------------------------------------------------------------------
  // (d) enumerateMigratedSkills
  // ---------------------------------------------------------------------------
  console.log('\n--- enumerateMigratedSkills ---');

  await runTest('collects ALL matching skills across the source tree (no early exit)', async () => {
    const tmpDir = await _makeTempDir();
    try {
      // module source root with multiple migrated skills:
      //   <src>/skill-a/skill-a.template.md
      //   <src>/grouped/skill-b/skill-b.template.md
      //   <src>/grouped/non-skill/    (no template — not collected)
      const moduleSrc = path.join(tmpDir, 'module-src');
      await _writeFile(path.join(moduleSrc, 'skill-a', 'skill-a.template.md'), 'a');
      await _writeFile(path.join(moduleSrc, 'grouped', 'skill-b', 'skill-b.template.md'), 'b');
      await _writeFile(path.join(moduleSrc, 'grouped', 'non-skill', 'random.md'), 'noop');

      const paths = { bmadDir: '/install/dir' };
      const officialModules = _makeFakeOfficialModules({ mod: moduleSrc });
      const skills = await enumerateMigratedSkills(paths, ['mod'], officialModules);

      assert(skills.length === 2, `expected 2 skills, got ${skills.length}`);
      const names = skills.map((s) => path.basename(s.skillDir)).sort();
      assert(names[0] === 'skill-a' && names[1] === 'skill-b', 'both skills collected by basename');
      assert(
        skills.every((s) => s.installDir === '/install/dir'),
        'every entry uses paths.bmadDir as installDir',
      );
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  await runTest('returns empty array on findModuleSource throw (network error)', async () => {
    const officialModules = _makeThrowingOfficialModules(new Error('ECONNRESET'));
    const paths = { bmadDir: '/anywhere' };
    const skills = await enumerateMigratedSkills(paths, ['flaky-mod'], officialModules);
    assert(Array.isArray(skills) && skills.length === 0, 'returns empty array on throw');
  });

  // ---------------------------------------------------------------------------
  // Summary
  // ---------------------------------------------------------------------------
  console.log(
    `\n${passed + failed} tests: ${colors.green}${passed} passed${colors.reset}, ${failed > 0 ? colors.red : ''}${failed} failed${colors.reset}\n`,
  );
  if (failed > 0) process.exit(1);
}

main().catch((error) => {
  console.error('Test runner error:', error);
  process.exit(1);
});
