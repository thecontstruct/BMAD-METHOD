/**
 * Story 10.0 — `_copySharedRoot` and Model 2 install-time JIT routing.
 *
 * Sub-cases:
 *   A — absent src/_shared/ → silent no-op, no dest dir created (AC-6, AC-13A)
 *   B — markdown source → bytes byte-identical, installedFiles tracked (AC-7, AC-13B)
 *   C — mixed source → .md copied, non-.md silently skipped (AC-8, AC-13C)
 *   D — nested subdirs → recursive copy works at arbitrary depth (AC-7, AC-13D)
 *   E — Model 2 end-to-end: fixture install → Python install-phase compile resolves
 *       _shared/... include and lockfile records the path (AC-14)
 *
 * Usage: node test/test-shared-root-copy.js
 */

'use strict';

const fs = require('node:fs/promises');
const fsSync = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

const { Installer } = require('../tools/installer/core/installer');

const FIXTURE_DIR = path.join(__dirname, 'fixtures', 'install-shared-routing');
const REPO_ROOT = path.join(__dirname, '..');

const colors = { reset: '[0m', green: '[32m', red: '[31m', dim: '[2m' };
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

async function makeTmpDir() {
  return fs.mkdtemp(path.join(os.tmpdir(), 'bmad-shared-routing-'));
}

async function pathExists(p) {
  try {
    await fs.access(p);
    return true;
  } catch {
    return false;
  }
}

async function sha256OfFile(p) {
  const buf = await fs.readFile(p);
  return crypto.createHash('sha256').update(buf).digest('hex');
}

async function copyDirRecursive(src, dest) {
  await fs.mkdir(dest, { recursive: true });
  const entries = await fs.readdir(src, { withFileTypes: true });
  for (const entry of entries) {
    const srcPath = path.join(src, entry.name);
    const destPath = path.join(dest, entry.name);
    if (entry.isDirectory()) {
      await copyDirRecursive(srcPath, destPath);
    } else if (entry.isFile()) {
      await fs.copyFile(srcPath, destPath);
    }
  }
}

async function main() {
  // -------------------------------------------------------------------------
  // Sub-case A — absent src/_shared/ → silent no-op
  // -------------------------------------------------------------------------
  await runTest('A: absent src/_shared/ → silent no-op, no dest dir created', async () => {
    const tmpDir = await makeTmpDir();
    try {
      const emptyFakeRepo = await makeTmpDir();
      try {
        await fs.mkdir(path.join(emptyFakeRepo, 'src'), { recursive: true });
        const bmadDir = path.join(tmpDir, '_bmad');
        await fs.mkdir(bmadDir, { recursive: true });

        const installer = new Installer();
        await installer._copySharedRoot({ srcDir: emptyFakeRepo, bmadDir });

        const dest = path.join(bmadDir, '_shared');
        assert(!(await pathExists(dest)), 'A: <bmadDir>/_shared/ NOT created when src/_shared/ absent', `unexpected: ${dest}`);
      } finally {
        await fs.rm(emptyFakeRepo, { recursive: true, force: true });
      }
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  // -------------------------------------------------------------------------
  // Sub-case B — markdown source copied byte-identical + tracked
  // -------------------------------------------------------------------------
  await runTest('B: .md source copied byte-identical and tracked in installedFiles', async () => {
    const tmpDir = await makeTmpDir();
    try {
      const bmadDir = path.join(tmpDir, '_bmad');
      await fs.mkdir(bmadDir, { recursive: true });

      const installer = new Installer();
      await installer._copySharedRoot({ srcDir: FIXTURE_DIR, bmadDir });

      const srcFragment = path.join(FIXTURE_DIR, 'src', '_shared', 'fragments', 'test_routing.md');
      const destFragment = path.join(bmadDir, '_shared', 'fragments', 'test_routing.md');

      assert(await pathExists(destFragment), 'B: dest fragment exists', `expected: ${destFragment}`);

      const srcHash = await sha256OfFile(srcFragment);
      const destHash = await sha256OfFile(destFragment);
      assert(srcHash === destHash, 'B: SHA-256 byte-identical', `src=${srcHash} dest=${destHash}`);

      const trackedKey = destFragment.replaceAll('\\', '/');
      assert(
        installer.installedFiles.has(trackedKey),
        'B: dest path tracked in installedFiles (POSIX-normalized)',
        `installedFiles: ${[...installer.installedFiles].join(', ')}`,
      );
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  // -------------------------------------------------------------------------
  // Sub-case C — non-.md entries silently skipped
  // -------------------------------------------------------------------------
  await runTest('C: non-.md entries in src/_shared/ silently skipped', async () => {
    const tmpDir = await makeTmpDir();
    try {
      const bmadDir = path.join(tmpDir, '_bmad');
      await fs.mkdir(bmadDir, { recursive: true });

      const installer = new Installer();
      await installer._copySharedRoot({ srcDir: FIXTURE_DIR, bmadDir });

      const nonMdDest = path.join(bmadDir, '_shared', 'non_md_stray.txt');
      assert(!(await pathExists(nonMdDest)), 'C: non-.md file NOT copied to dest', `unexpected: ${nonMdDest}`);

      const mdDest = path.join(bmadDir, '_shared', 'fragments', 'test_routing.md');
      assert(await pathExists(mdDest), 'C: .md sibling still copied');
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  // -------------------------------------------------------------------------
  // Sub-case D — nested subdirs handled recursively
  // -------------------------------------------------------------------------
  await runTest('D: nested directories copied recursively', async () => {
    const tmpDir = await makeTmpDir();
    const fakeRepo = await makeTmpDir();
    try {
      const nestedSrc = path.join(fakeRepo, 'src', '_shared', 'foo', 'bar');
      await fs.mkdir(nestedSrc, { recursive: true });
      await fs.writeFile(path.join(nestedSrc, 'baz.md'), 'deep nested\n');

      const bmadDir = path.join(tmpDir, '_bmad');
      await fs.mkdir(bmadDir, { recursive: true });

      const installer = new Installer();
      await installer._copySharedRoot({ srcDir: fakeRepo, bmadDir });

      const nestedDest = path.join(bmadDir, '_shared', 'foo', 'bar', 'baz.md');
      assert(await pathExists(nestedDest), 'D: nested dest path exists', `expected: ${nestedDest}`);

      const content = await fs.readFile(nestedDest, 'utf8');
      assert(content === 'deep nested\n', 'D: nested file content preserved');
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
      await fs.rm(fakeRepo, { recursive: true, force: true });
    }
  });

  // -------------------------------------------------------------------------
  // Sub-case E — Model 2 install-time JIT routing (end-to-end)
  // -------------------------------------------------------------------------
  await runTest('E: Model 2 e2e — _copySharedRoot + Python install-phase resolves _shared/...', async () => {
    const tmpDir = await makeTmpDir();
    try {
      // Step 1: copy the consumer skill tree into the install dir.
      await copyDirRecursive(path.join(FIXTURE_DIR, 'bmm'), path.join(tmpDir, 'bmm'));
      await fs.mkdir(path.join(tmpDir, '_config'), { recursive: true });

      // Step 2: _copySharedRoot materializes <tmp>/_shared/ from the fixture.
      const installer = new Installer();
      await installer._copySharedRoot({ srcDir: FIXTURE_DIR, bmadDir: tmpDir });

      assert(
        await pathExists(path.join(tmpDir, '_shared', 'fragments', 'test_routing.md')),
        'E: <tmp>/_shared/fragments/test_routing.md materialized',
      );

      // Step 3: spawn python compile.py --install-phase against the tmp install dir.
      const compileScript = path.join(REPO_ROOT, 'src', 'scripts', 'compile.py');
      const { resolvePythonInterpreter, resolvePythonInvocation } = require('../tools/python-env');
      const pyInterp = resolvePythonInterpreter();
      const pyInv = resolvePythonInvocation({
        interpreter: pyInterp,
        scriptArgs: [compileScript, '--install-phase', '--install-dir', tmpDir],
        withDeps: ['pyyaml'],
      });
      const result = spawnSync(pyInv.cmd, pyInv.args, {
        encoding: 'utf8',
        cwd: REPO_ROOT,
      });

      assert(result.status === 0, 'E: python compile.py exit 0', `exit=${result.status} stderr=${result.stderr} stdout=${result.stdout}`);

      // Step 4: assert compiled SKILL.md contains the fragment bytes.
      const skillMd = path.join(tmpDir, 'bmm', 'shared-routing-fixture', 'SKILL.md');
      assert(await pathExists(skillMd), 'E: compiled SKILL.md exists', `expected: ${skillMd}`);
      const compiled = await fs.readFile(skillMd, 'utf8');
      assert(compiled.includes('shared fragment body'), 'E: compiled SKILL.md contains fragment body', `got: ${JSON.stringify(compiled)}`);

      // Step 5: lockfile records the _shared/... path POSIX-normalized.
      const lockPath = path.join(tmpDir, '_config', 'bmad.lock');
      assert(await pathExists(lockPath), 'E: lockfile produced', `expected: ${lockPath}`);
      const lockfile = JSON.parse(await fs.readFile(lockPath, 'utf8'));
      const skillEntry = (lockfile.entries || []).find((e) => e.skill === 'shared-routing-fixture');
      assert(skillEntry !== undefined, 'E: lockfile has skill entry', `entries: ${JSON.stringify(lockfile.entries)}`);
      const fragments = (skillEntry && skillEntry.fragments) || [];
      const sharedFrag = fragments.find((f) => f.path === '_shared/fragments/test_routing.md');
      assert(
        sharedFrag !== undefined,
        'E: lockfile fragment path POSIX-normalized to _shared/fragments/test_routing.md',
        `fragments: ${JSON.stringify(fragments)}`,
      );
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  // -------------------------------------------------------------------------
  // Summary
  // -------------------------------------------------------------------------
  console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed`);
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
