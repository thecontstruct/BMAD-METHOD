/**
 * Story 10.58 — `_copySharedComponentsRoot` install-time copy semantics.
 *
 * Group D from spec test taxonomy:
 *   D-1: copies .py files from src/_shared/components/ to <bmadDir>/_shared/components/
 *   D-2: copies non-blocklisted data files (.json, .csv, .yaml)
 *   D-3: skips blocklisted (.DS_Store, .gitignore, *.pyc, __pycache__/)
 *   D-4: skips *.md files (prevents README.md double-install)
 *   D-5: empty src/_shared/components/ → no dest dir created
 *   D-6: absent src/_shared/components/ → no-op (pre-existing repos still install cleanly)
 *   D-7: _copySharedRoot still filters fragments to *.md only (regression guard for DN-4 = A)
 *
 * Usage: node test/test-shared-components-copy.js
 */

'use strict';

const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');

const { Installer } = require('../tools/installer/core/installer');

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
  return fs.mkdtemp(path.join(os.tmpdir(), 'bmad-shared-comp-'));
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

/**
 * Build a fake repo with src/_shared/components/ populated per the given map.
 * Returns the srcDir path (the repo root containing src/_shared/components).
 */
async function makeFakeRepoWithSharedComponents(files) {
  const repo = await makeTmpDir();
  const compDir = path.join(repo, 'src', '_shared', 'components');
  await fs.mkdir(compDir, { recursive: true });
  for (const [relPath, content] of Object.entries(files)) {
    const target = path.join(compDir, relPath);
    await fs.mkdir(path.dirname(target), { recursive: true });
    if (Buffer.isBuffer(content)) {
      await fs.writeFile(target, content);
    } else {
      await fs.writeFile(target, content);
    }
  }
  return repo;
}

async function main() {
  // -------------------------------------------------------------------------
  // D-1: .py files copied to <bmadDir>/_shared/components/
  // -------------------------------------------------------------------------
  await runTest('D-1: .py files copied byte-identical to <bmadDir>/_shared/components/', async () => {
    const srcRepo = await makeFakeRepoWithSharedComponents({
      'todays_date.py': 'RENDER_MODE = "jit"\n',
      'artifact_path.py': 'RENDER_MODE = "jit"\nRENDER_ERROR_FALLBACK = ""\n',
    });
    const bmadDir = await makeTmpDir();
    try {
      const installer = new Installer();
      await installer._copySharedComponentsRoot({ srcDir: srcRepo, bmadDir });

      const dest1 = path.join(bmadDir, '_shared', 'components', 'todays_date.py');
      const dest2 = path.join(bmadDir, '_shared', 'components', 'artifact_path.py');
      assert(await pathExists(dest1), 'D-1: todays_date.py exists at dest');
      assert(await pathExists(dest2), 'D-1: artifact_path.py exists at dest');

      const srcHash = await sha256OfFile(path.join(srcRepo, 'src', '_shared', 'components', 'todays_date.py'));
      const destHash = await sha256OfFile(dest1);
      assert(srcHash === destHash, 'D-1: byte-identical SHA-256', `src=${srcHash} dest=${destHash}`);

      const trackedKey = dest1.replaceAll('\\', '/');
      assert(
        installer.installedFiles.has(trackedKey),
        'D-1: dest path tracked in installedFiles (POSIX-normalized)',
        `installedFiles: ${[...installer.installedFiles].slice(0, 5).join(', ')}`,
      );
    } finally {
      await fs.rm(srcRepo, { recursive: true, force: true });
      await fs.rm(bmadDir, { recursive: true, force: true });
    }
  });

  // -------------------------------------------------------------------------
  // D-2: non-blocklisted data files (.json, .csv, .yaml) copied
  // -------------------------------------------------------------------------
  await runTest('D-2: non-blocklisted data files (.json, .csv, .yaml) copied', async () => {
    const srcRepo = await makeFakeRepoWithSharedComponents({
      'comp.py': 'RENDER_MODE = "jit"\n',
      'data.json': '{"k": "v"}',
      'matrix.csv': 'c1,c2\n1,2\n',
      'cfg.yaml': 'key: val\n',
    });
    const bmadDir = await makeTmpDir();
    try {
      const installer = new Installer();
      await installer._copySharedComponentsRoot({ srcDir: srcRepo, bmadDir });

      for (const name of ['data.json', 'matrix.csv', 'cfg.yaml', 'comp.py']) {
        assert(await pathExists(path.join(bmadDir, '_shared', 'components', name)), `D-2: ${name} copied to dest`);
      }
    } finally {
      await fs.rm(srcRepo, { recursive: true, force: true });
      await fs.rm(bmadDir, { recursive: true, force: true });
    }
  });

  // -------------------------------------------------------------------------
  // D-3: blocklisted entries (.DS_Store, .gitignore, *.pyc, __pycache__/) skipped
  // -------------------------------------------------------------------------
  await runTest('D-3: blocklisted .DS_Store / .gitignore / *.pyc / __pycache__/ skipped', async () => {
    const srcRepo = await makeFakeRepoWithSharedComponents({
      'comp.py': 'RENDER_MODE = "jit"\n',
      '.DS_Store': Buffer.from([0]),
      '.gitignore': '*.pyc\n',
      'stale.pyc': Buffer.from([0, 1, 2]),
    });
    // __pycache__/ is a directory; create it explicitly.
    const cacheDir = path.join(srcRepo, 'src', '_shared', 'components', '__pycache__');
    await fs.mkdir(cacheDir);
    await fs.writeFile(path.join(cacheDir, 'mod.cpython-313.pyc'), Buffer.from([0]));

    const bmadDir = await makeTmpDir();
    try {
      const installer = new Installer();
      await installer._copySharedComponentsRoot({ srcDir: srcRepo, bmadDir });

      const dest = path.join(bmadDir, '_shared', 'components');
      for (const blocked of ['.DS_Store', '.gitignore', 'stale.pyc', '__pycache__']) {
        assert(
          !(await pathExists(path.join(dest, blocked))),
          `D-3: ${blocked} NOT present at dest`,
          `unexpected: ${path.join(dest, blocked)}`,
        );
      }
      assert(await pathExists(path.join(dest, 'comp.py')), 'D-3: legitimate .py still copied');
    } finally {
      await fs.rm(srcRepo, { recursive: true, force: true });
      await fs.rm(bmadDir, { recursive: true, force: true });
    }
  });

  // -------------------------------------------------------------------------
  // D-4: *.md skipped (README.md guard)
  // -------------------------------------------------------------------------
  await runTest('D-4: README.md and other *.md files skipped', async () => {
    const srcRepo = await makeFakeRepoWithSharedComponents({
      'comp.py': 'RENDER_MODE = "jit"\n',
      'README.md': '# Author guidance\n',
      'NOTES.md': 'design notes\n',
    });
    const bmadDir = await makeTmpDir();
    try {
      const installer = new Installer();
      await installer._copySharedComponentsRoot({ srcDir: srcRepo, bmadDir });

      const dest = path.join(bmadDir, '_shared', 'components');
      assert(!(await pathExists(path.join(dest, 'README.md'))), 'D-4: README.md NOT installed');
      assert(!(await pathExists(path.join(dest, 'NOTES.md'))), 'D-4: NOTES.md NOT installed');
      assert(await pathExists(path.join(dest, 'comp.py')), 'D-4: comp.py sibling still installed');
    } finally {
      await fs.rm(srcRepo, { recursive: true, force: true });
      await fs.rm(bmadDir, { recursive: true, force: true });
    }
  });

  // -------------------------------------------------------------------------
  // D-5: empty src/_shared/components/ → no dest dir created
  // -------------------------------------------------------------------------
  await runTest('D-5: empty src/_shared/components/ → no dest dir created', async () => {
    const srcRepo = await makeTmpDir();
    await fs.mkdir(path.join(srcRepo, 'src', '_shared', 'components'), { recursive: true });
    const bmadDir = await makeTmpDir();
    try {
      const installer = new Installer();
      await installer._copySharedComponentsRoot({ srcDir: srcRepo, bmadDir });

      const dest = path.join(bmadDir, '_shared', 'components');
      assert(!(await pathExists(dest)), 'D-5: no dest dir created for empty source');
    } finally {
      await fs.rm(srcRepo, { recursive: true, force: true });
      await fs.rm(bmadDir, { recursive: true, force: true });
    }
  });

  // -------------------------------------------------------------------------
  // D-6: absent src/_shared/components/ → no-op
  // -------------------------------------------------------------------------
  await runTest('D-6: absent src/_shared/components/ → silent no-op', async () => {
    const srcRepo = await makeTmpDir();
    // Only create src/ — no _shared/components/ at all.
    await fs.mkdir(path.join(srcRepo, 'src'), { recursive: true });
    const bmadDir = await makeTmpDir();
    try {
      const installer = new Installer();
      // Must not throw.
      await installer._copySharedComponentsRoot({ srcDir: srcRepo, bmadDir });
      const dest = path.join(bmadDir, '_shared', 'components');
      assert(!(await pathExists(dest)), 'D-6: no dest dir created when source absent');
    } finally {
      await fs.rm(srcRepo, { recursive: true, force: true });
      await fs.rm(bmadDir, { recursive: true, force: true });
    }
  });

  // -------------------------------------------------------------------------
  // D-7: _copySharedRoot still filters fragments to *.md only (regression guard)
  // -------------------------------------------------------------------------
  await runTest('D-7: _copySharedRoot still filters to *.md (DN-4 fragment regression)', async () => {
    const srcRepo = await makeTmpDir();
    const fragDir = path.join(srcRepo, 'src', '_shared', 'fragments');
    await fs.mkdir(fragDir, { recursive: true });
    await fs.writeFile(path.join(fragDir, 'frag.md'), '# fragment body\n');
    await fs.writeFile(path.join(fragDir, 'not_md.txt'), 'should be skipped');
    await fs.writeFile(path.join(fragDir, 'binary.bin'), Buffer.from([0, 1, 2]));

    const bmadDir = await makeTmpDir();
    try {
      const installer = new Installer();
      await installer._copySharedRoot({ srcDir: srcRepo, bmadDir });

      const fragDest = path.join(bmadDir, '_shared', 'fragments');
      assert(await pathExists(path.join(fragDest, 'frag.md')), 'D-7: .md copied');
      assert(!(await pathExists(path.join(fragDest, 'not_md.txt'))), 'D-7: .txt NOT copied');
      assert(!(await pathExists(path.join(fragDest, 'binary.bin'))), 'D-7: .bin NOT copied');
    } finally {
      await fs.rm(srcRepo, { recursive: true, force: true });
      await fs.rm(bmadDir, { recursive: true, force: true });
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
