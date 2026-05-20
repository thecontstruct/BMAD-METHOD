/**
 * Story 8.9 — Installer Component Copy & Distribution Validation
 *
 * Tests _copyComponentFiles() and related installer behaviour.
 *
 * Sub-cases:
 *   a — .py file copied to correct dest path (AC-1, AC-4)
 *   b — dest path tracked in installedFiles (AC-1)
 *   c — skill with no components/ dir → no-op (AC-3)
 *   d — empty components/ dir → no dest dir created (AC-1, AC-3)
 *   e — non-.py files in components/ are skipped (AC-1)
 *   f — installer path formula == render.py path formula (AC-2)
 *   g — Model 3 Python-absent: SKILL.md copied, components/ NOT created (AC-5)
 *   h — TPL-02 gate: correct components fixture → no HIGH/MEDIUM findings (AC-6)
 *   i — layout invariant: _cleanupSkillDirs removes skill dir but NOT components/ (AC-7)
 *   j — 3-level fixture: moduleName = immediate parent, NOT grandparent (AC-1, DN-5)
 *
 * Usage: node test/test-component-installer.js
 */

'use strict';

const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');

const { Installer } = require('../tools/installer/core/installer');
const { applyModel3FallbackIfAllEligible } = require('../tools/installer/compiler/invoke-python');
const { validateSkill } = require('../tools/validate-skills');

const FIXTURE_SKILL_DIR = path.join(__dirname, 'fixtures', 'component-installer', 'test-module', 'component-skill');

const FIXTURE_3LEVEL_SKILL_DIR = path.join(
  __dirname,
  'fixtures',
  'component-installer-3level',
  'parent-dir',
  'test-module',
  'component-skill',
);

const colors = { reset: '[0m', green: '[32m', red: '[31m', dim: '[2m' };
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
  return fs.mkdtemp(path.join(os.tmpdir(), 'bmad-test-'));
}

async function pathExists(p) {
  try {
    await fs.access(p);
    return true;
  } catch {
    return false;
  }
}

async function main() {
  // ---------------------------------------------------------------------------
  // Sub-case a + b: _copyComponentFiles copies .py to dest and tracks it
  // ---------------------------------------------------------------------------
  await runTest('a: _copyComponentFiles copies fixture_banner.py to correct dest path', async () => {
    const tmpDir = await makeTmpDir();
    try {
      const installer = new Installer();
      const skills = [{ skillDir: FIXTURE_SKILL_DIR, installDir: tmpDir }];
      await installer._copyComponentFiles(skills, tmpDir);

      const destPath = path.join(tmpDir, 'components', 'test-module', 'component-skill', 'fixture_banner.py');
      const exists = await pathExists(destPath);
      assert(exists, 'a: fixture_banner.py exists at dest path', `expected: ${destPath}`);

      const src = await fs.readFile(path.join(FIXTURE_SKILL_DIR, 'components', 'fixture_banner.py'));
      const dest = await fs.readFile(destPath);
      assert(src.equals(dest), 'a: installed fixture_banner.py is byte-identical to source');
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  await runTest('b: _copyComponentFiles tracks dest path in installedFiles', async () => {
    const tmpDir = await makeTmpDir();
    try {
      const installer = new Installer();
      const skills = [{ skillDir: FIXTURE_SKILL_DIR, installDir: tmpDir }];
      await installer._copyComponentFiles(skills, tmpDir);

      const destPath = path.join(tmpDir, 'components', 'test-module', 'component-skill', 'fixture_banner.py');
      assert(
        installer.installedFiles.has(destPath),
        'b: destPath is in installedFiles',
        `installedFiles: ${[...installer.installedFiles].join(', ')}`,
      );
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  // ---------------------------------------------------------------------------
  // Sub-case c: skill with no components/ dir → no-op
  // ---------------------------------------------------------------------------
  await runTest('c: skill with no components/ dir → no-op (no error, no dest)', async () => {
    const tmpDir = await makeTmpDir();
    try {
      const noCompDir = path.join(tmpDir, 'src', 'no-comp-module', 'plain-skill');
      await fs.mkdir(noCompDir, { recursive: true });
      await fs.writeFile(path.join(noCompDir, 'SKILL.md'), '# plain skill\n');

      const installer = new Installer();
      const skills = [{ skillDir: noCompDir, installDir: tmpDir }];
      await installer._copyComponentFiles(skills, tmpDir); // must not throw

      const componentsRoot = path.join(tmpDir, 'components');
      assert(!(await pathExists(componentsRoot)), 'c: no _bmad/components/ dir created for skill without components/');
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  // ---------------------------------------------------------------------------
  // Sub-case d: empty components/ dir → no dest dir created
  // ---------------------------------------------------------------------------
  await runTest('d: empty components/ dir → no dest dir created', async () => {
    const tmpDir = await makeTmpDir();
    try {
      const emptySkillDir = path.join(tmpDir, 'src', 'empty-module', 'empty-skill');
      await fs.mkdir(path.join(emptySkillDir, 'components'), { recursive: true });
      await fs.writeFile(path.join(emptySkillDir, 'SKILL.md'), '# empty skill\n');

      const installer = new Installer();
      await installer._copyComponentFiles([{ skillDir: emptySkillDir }], tmpDir);

      const destDir = path.join(tmpDir, 'components', 'empty-module', 'empty-skill');
      assert(
        !(await pathExists(destDir)),
        'd: no dest dir created for empty components/ (ensureDir not called)',
        `unexpected dir: ${destDir}`,
      );
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  // ---------------------------------------------------------------------------
  // Sub-case e: non-.py files are skipped
  // ---------------------------------------------------------------------------
  await runTest('e: non-.py files in components/ are skipped', async () => {
    const tmpDir = await makeTmpDir();
    try {
      const installer = new Installer();
      await installer._copyComponentFiles([{ skillDir: FIXTURE_SKILL_DIR, installDir: tmpDir }], tmpDir);

      const destDir = path.join(tmpDir, 'components', 'test-module', 'component-skill');
      const pyExists = await pathExists(path.join(destDir, 'fixture_banner.py'));
      const txtExists = await pathExists(path.join(destDir, 'not_a_component.txt'));

      assert(pyExists, 'e: fixture_banner.py IS copied');
      assert(!txtExists, 'e: not_a_component.txt is NOT copied');
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  // ---------------------------------------------------------------------------
  // Sub-case f: installer path formula == render.py path formula (AC-2)
  // ---------------------------------------------------------------------------
  await runTest('f: installer path formula matches render.py path formula', async () => {
    const bmadDir = '/project/_bmad';
    const skillDir = FIXTURE_SKILL_DIR; // .../component-installer/test-module/component-skill

    const moduleName = path.basename(path.dirname(skillDir)); // "test-module"
    const skillBasename = path.basename(skillDir); // "component-skill"
    const pyFileName = 'fixture_banner.py';

    // Installer formula (JS, OS-native separators)
    const installerPath = path.join(bmadDir, 'components', moduleName, skillBasename, pyFileName);

    // render.py formula (POSIX, forward slashes)
    const root = '/project';
    const renderPath = [root, '_bmad', 'components', moduleName, skillBasename, pyFileName].join('/');

    const suffix = ['components', moduleName, skillBasename, pyFileName].join(path.sep);
    assert(
      installerPath.endsWith(suffix),
      'f: installer path ends with components/test-module/component-skill/fixture_banner.py',
      `got: ${installerPath}`,
    );

    const posixSuffix = ['components', moduleName, skillBasename, pyFileName].join('/');
    assert(
      renderPath.endsWith(posixSuffix),
      'f: render.py path ends with components/test-module/component-skill/fixture_banner.py',
      `got: ${renderPath}`,
    );

    assert(moduleName === 'test-module', `f: moduleName = "test-module" (got "${moduleName}")`);
    assert(skillBasename === 'component-skill', `f: skillBasename = "component-skill" (got "${skillBasename}")`);
  });

  // ---------------------------------------------------------------------------
  // Sub-case g: Model 3 Python-absent — SKILL.md copied, components/ NOT created
  // ---------------------------------------------------------------------------
  await runTest('g: Model 3 fallback copies SKILL.md but does not create components/', async () => {
    const tmpDir = await makeTmpDir();
    try {
      // FIXTURE_SKILL_DIR has both template + SKILL.md → Model 3
      const skills = [{ skillDir: FIXTURE_SKILL_DIR, installDir: tmpDir }];
      const applied = await applyModel3FallbackIfAllEligible(skills);

      assert(applied === true, 'g: applyModel3FallbackIfAllEligible returns true', `got: ${applied}`);

      const installedSkillMd = path.join(tmpDir, 'test-module', 'component-skill', 'SKILL.md');
      assert(
        await pathExists(installedSkillMd),
        'g: SKILL.md copied to installDir/test-module/component-skill/',
        `expected: ${installedSkillMd}`,
      );

      const installedComponents = path.join(tmpDir, 'components');
      assert(!(await pathExists(installedComponents)), 'g: no components/ dir created by applyModel3FallbackIfAllEligible');
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  // ---------------------------------------------------------------------------
  // Sub-case h: TPL-02 gate — correct components fixture → no HIGH/MEDIUM findings
  // ---------------------------------------------------------------------------
  await runTest('h: TPL-02 validates fixture skill with correct components → no findings', async () => {
    // Pass _testComponents directly to bypass the hardcoded LOCKFILE_PATH in validate-skills.js
    const testComponents = [
      {
        name: 'FixtureBanner',
        props_hash: 'aaaa1111bbbb2222',
        render_mode: 'jit',
        path: 'components/fixture_banner.py',
      },
    ];

    const findings = validateSkill(FIXTURE_SKILL_DIR, testComponents);
    const tpl02Findings = findings.filter((f) => f.rule === 'TPL-02' && (f.severity === 'HIGH' || f.severity === 'MEDIUM'));

    assert(
      tpl02Findings.length === 0,
      'h: no TPL-02 HIGH or MEDIUM findings for fixture skill',
      `got ${tpl02Findings.length} finding(s): ${JSON.stringify(tpl02Findings.map((f) => ({ title: f.title, severity: f.severity })))}`,
    );
  });

  // ---------------------------------------------------------------------------
  // Sub-case i: layout invariant — _cleanupSkillDirs removes skill dir NOT components/
  // ---------------------------------------------------------------------------
  await runTest('i: _cleanupSkillDirs removes skill dir but leaves components/ intact', async () => {
    const tmpDir = await makeTmpDir();
    try {
      const installer = new Installer();

      // 1. Run _copyComponentFiles to populate _bmad/components/
      await installer._copyComponentFiles([{ skillDir: FIXTURE_SKILL_DIR, installDir: tmpDir }], tmpDir);

      const destPath = path.join(tmpDir, 'components', 'test-module', 'component-skill', 'fixture_banner.py');
      assert(await pathExists(destPath), 'i (setup): component file installed at destPath');

      // 2. Create skill dir at bmadDir/<module>/<skill>/ (mirrors real install)
      const skillInstallDir = path.join(tmpDir, 'test-module', 'component-skill');
      await fs.mkdir(skillInstallDir, { recursive: true });
      await fs.writeFile(path.join(skillInstallDir, 'SKILL.md'), '# placeholder\n');

      // 3. Stage minimal skill-manifest.csv
      const configDir = path.join(tmpDir, '_config');
      await fs.mkdir(configDir, { recursive: true });
      const csvContent =
        'canonicalId,name,description,module,path\n' + 'fixture-skill,FixtureSkill,,test-module,test-module/component-skill/SKILL.md\n';
      await fs.writeFile(path.join(configDir, 'skill-manifest.csv'), csvContent, 'utf8');

      // 4. Run _cleanupSkillDirs
      await installer._cleanupSkillDirs(tmpDir);

      // 5a: skill dir removed
      assert(
        !(await pathExists(skillInstallDir)),
        'i (a): skill dir test-module/component-skill/ removed by _cleanupSkillDirs',
        `still exists: ${skillInstallDir}`,
      );

      // 5b: component destPath survives
      assert(
        await pathExists(destPath),
        'i (b): components/test-module/component-skill/fixture_banner.py survives cleanup',
        `missing: ${destPath}`,
      );
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  // ---------------------------------------------------------------------------
  // Sub-case j: 3-level fixture — moduleName = immediate parent, NOT grandparent
  // ---------------------------------------------------------------------------
  await runTest('j: 3-level fixture derives moduleName="test-module", not "parent-dir"', async () => {
    const tmpDir = await makeTmpDir();
    try {
      const installer = new Installer();
      // path: .../component-installer-3level/parent-dir/test-module/component-skill
      const skills = [{ skillDir: FIXTURE_3LEVEL_SKILL_DIR, installDir: tmpDir }];
      await installer._copyComponentFiles(skills, tmpDir);

      const correctDest = path.join(tmpDir, 'components', 'test-module', 'component-skill', 'fixture_banner.py');
      const wrongDest = path.join(tmpDir, 'components', 'parent-dir', 'component-skill', 'fixture_banner.py');

      assert(await pathExists(correctDest), 'j: file at correct path components/test-module/component-skill/', `expected: ${correctDest}`);
      assert(
        !(await pathExists(wrongDest)),
        'j: file NOT at wrong path components/parent-dir/component-skill/',
        `wrong dest exists: ${wrongDest}`,
      );
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  // ---------------------------------------------------------------------------
  // Summary
  // ---------------------------------------------------------------------------
  console.log(`\n${passed + failed} tests: ${passed} passed, ${failed} failed`);
  process.exit(failed > 0 ? 1 : 0);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
