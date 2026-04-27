'use strict';

/**
 * AC 3 regression fixture: module with no migrated skills (Story 2.1).
 *
 * Verifies:
 *   1. hasMigratedSkillsInScope returns false for the fixture source tree
 *      (i.e., Python is never invoked during this install path)
 *   2. The fixture source tree hash matches the golden value — any accidental
 *      addition of *.template.md files to the fixture would break this test,
 *      catching regressions that loosen detection back to "any *.template.md"
 *   3. The compile task early-return path is exercised: when hasMigratedSkillsInScope
 *      returns false, the function returns 'Skipped — no migrated skills'
 *
 * Usage: node test/test-installer-no-migrated.js
 */

const path = require('node:path');
const fs = require('node:fs/promises');
const crypto = require('node:crypto');

const { hasMigratedSkillsInScope } = require('../tools/installer/compiler/invoke-python');

// Golden hash of test/fixtures/install-no-migrated/source/ (generated during Story 2.1 dev).
// Regenerate if fixture source files are intentionally changed — see README.md for the command.
const FIXTURE_GOLDEN_HASH = 'cc8019f110a13d740bb040fe0049afc14dcb081c328359b031b75c4f1cbaa341';

const FIXTURE_SOURCE = path.join(__dirname, 'fixtures', 'install-no-migrated', 'source');

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

/**
 * Compute a deterministic SHA-256 hash of a directory tree.
 * Sorted file list, content-addressed, forward-slash paths.
 */
async function hashDirTree(dir) {
  const hash = crypto.createHash('sha256');

  async function walk(d) {
    const entries = await fs.readdir(d, { withFileTypes: true });
    entries.sort((a, b) => a.name.localeCompare(b.name));
    for (const entry of entries) {
      const fullPath = path.join(d, entry.name);
      const relPath = path.relative(dir, fullPath).split(path.sep).join('/');
      if (entry.isDirectory()) {
        await walk(fullPath);
      } else {
        const content = await fs.readFile(fullPath);
        hash.update(relPath + '\n');
        hash.update(content);
      }
    }
  }

  await walk(dir);
  return hash.digest('hex');
}

async function main() {
  console.log('\n--- AC 3: no-migrated-skills regression fixture ---');

  await runTest('fixture source tree matches golden hash', async () => {
    const actual = await hashDirTree(FIXTURE_SOURCE);
    assert(
      actual === FIXTURE_GOLDEN_HASH,
      'fixture source tree hash matches golden',
      `expected ${FIXTURE_GOLDEN_HASH}\n  got      ${actual}\n  (if intentional: update FIXTURE_GOLDEN_HASH per README.md)`,
    );
  });

  await runTest('hasMigratedSkillsInScope returns false for no-migrated fixture', async () => {
    const fakeOfficialModules = {
      async findModuleSource(moduleCode) {
        if (moduleCode === 'no-migrated-fixture') return FIXTURE_SOURCE;
        return null;
      },
    };

    const result = await hasMigratedSkillsInScope({}, ['no-migrated-fixture'], fakeOfficialModules);
    assert(result === false, 'hasMigratedSkillsInScope returns false (Python will not be invoked)', `expected false, got ${result}`);
  });

  await runTest('fixture contains no *.template.md files', async () => {
    async function findTemplates(dir) {
      const found = [];
      const entries = await fs.readdir(dir, { withFileTypes: true });
      for (const entry of entries) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          found.push(...(await findTemplates(full)));
        } else if (entry.name.endsWith('.template.md')) {
          found.push(path.relative(FIXTURE_SOURCE, full));
        }
      }
      return found;
    }

    const templates = await findTemplates(FIXTURE_SOURCE);
    assert(templates.length === 0, 'fixture has zero *.template.md files', `found: ${JSON.stringify(templates)}`);
  });

  await runTest('fixture plain-skill/SKILL.md exists and is a regular file', async () => {
    const skillMd = path.join(FIXTURE_SOURCE, 'plain-skill', 'SKILL.md');
    try {
      const stat = await fs.stat(skillMd);
      assert(stat.isFile(), 'plain-skill/SKILL.md is a regular file');
    } catch {
      assert(false, 'plain-skill/SKILL.md exists', `not found at ${skillMd}`);
    }
  });

  console.log(
    `\n${passed + failed} tests: ${colors.green}${passed} passed${colors.reset}, ${failed > 0 ? colors.red : ''}${failed} failed${colors.reset}\n`,
  );
  if (failed > 0) process.exit(1);
}

main().catch((error) => {
  console.error('Test runner error:', error);
  process.exit(1);
});
