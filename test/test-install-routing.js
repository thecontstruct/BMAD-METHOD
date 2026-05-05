'use strict';

/**
 * Unit tests for install.js AC 4/5 routing logic (via invoke-python.js boundary).
 *
 * Covers:
 *   (a) lockfile present triggers dry-run: runUpgradeDryRun returns drift report with drift > 0
 *   (b) no drift falls through: runUpgradeDryRun returns report with total_skills_with_drift === 0
 *   (c) runUpgradeYes succeeds when upgrade.py exits 0 (no lockfile skips routing path)
 *
 * Tests invoke runUpgradeDryRun and runUpgradeYes directly via the exported functions using
 * a real tmpdir with a fake upgrade.py script (same pattern as test-invoke-python.js).
 *
 * Usage: node test/test-install-routing.js
 */

const path = require('node:path');
const fs = require('node:fs/promises');
const os = require('node:os');

const { runUpgradeDryRun, runUpgradeYes } = require('../tools/installer/compiler/invoke-python');

const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  red: '\x1b[31m',
  dim: '\x1b[2m',
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
  return fs.mkdtemp(path.join(os.tmpdir(), 'install-routing-test-'));
}

async function _writeFile(filePath, content) {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, content, 'utf8');
}

async function main() {
  // ---------------------------------------------------------------------------
  // (a) lockfile present triggers dry-run
  // ---------------------------------------------------------------------------

  console.log('\n--- lockfile present triggers dry-run ---');

  await runTest('runUpgradeDryRun returns drift report when upgrade.py emits JSON with drift', async () => {
    const tmpDir = await _makeTempDir();
    try {
      const upgradePy = path.join(tmpDir, 'upgrade.py');
      const driftReport = {
        schema_version: 1,
        drift: [
          {
            skill: 'bmad-customize',
            prose_fragment_changes: [{ path: 'fragment.md', old_hash: 'aaa', new_hash: 'bbb', user_override_hash: null, tier: 'base' }],
            toml_default_changes: [],
            orphaned_overrides: [],
            new_defaults: [],
            glob_changes: [],
            variable_provenance_shifts: [],
          },
        ],
        summary: {
          total_skills_with_drift: 1,
          prose_fragment_changes: 1,
          toml_default_changes: 0,
          orphaned_overrides: 0,
          new_defaults: 0,
          glob_changes: 0,
          variable_provenance_shifts: 0,
        },
      };
      const reportJson = path.join(tmpDir, 'drift.json');
      await _writeFile(reportJson, JSON.stringify(driftReport));
      await _writeFile(
        upgradePy,
        `import sys\nwith open(${JSON.stringify(reportJson)}) as f:\n    print(f.read())\nsys.exit(0)\n`,
      );

      const report = await runUpgradeDryRun({ upgradePy, projectRoot: tmpDir });

      assert(typeof report === 'object' && report !== null, 'returns an object');
      assert(report.schema_version === 1, 'schema_version is 1');
      assert(Array.isArray(report.drift), 'drift is an array');
      assert(report.summary.total_skills_with_drift === 1, 'total_skills_with_drift is 1', `got: ${report.summary.total_skills_with_drift}`);
      assert(report.summary.prose_fragment_changes === 1, 'prose_fragment_changes is 1');
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  // ---------------------------------------------------------------------------
  // (b) no drift falls through
  // ---------------------------------------------------------------------------

  console.log('\n--- no drift falls through ---');

  await runTest('runUpgradeDryRun returns zero-drift report when upgrade.py emits no drift', async () => {
    const tmpDir = await _makeTempDir();
    try {
      const upgradePy = path.join(tmpDir, 'upgrade.py');
      const zeroDriftReport = {
        schema_version: 1,
        drift: [],
        summary: {
          total_skills_with_drift: 0,
          prose_fragment_changes: 0,
          toml_default_changes: 0,
          orphaned_overrides: 0,
          new_defaults: 0,
          glob_changes: 0,
          variable_provenance_shifts: 0,
        },
      };
      const reportJson = path.join(tmpDir, 'drift.json');
      await _writeFile(reportJson, JSON.stringify(zeroDriftReport));
      await _writeFile(
        upgradePy,
        `import sys\nwith open(${JSON.stringify(reportJson)}) as f:\n    print(f.read())\nsys.exit(0)\n`,
      );

      const report = await runUpgradeDryRun({ upgradePy, projectRoot: tmpDir });

      assert(report.summary.total_skills_with_drift === 0, 'total_skills_with_drift is 0 (no routing triggered)', `got: ${report.summary.total_skills_with_drift}`);
      assert(Array.isArray(report.drift) && report.drift.length === 0, 'drift list is empty');
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  await runTest('runUpgradeDryRun throws when upgrade.py exits 1', async () => {
    const tmpDir = await _makeTempDir();
    try {
      const upgradePy = path.join(tmpDir, 'upgrade.py');
      await _writeFile(upgradePy, 'import sys\nprint("Error: no lockfile", file=sys.stderr)\nsys.exit(1)\n');

      let threw = false;
      let errMsg = '';
      try {
        await runUpgradeDryRun({ upgradePy, projectRoot: tmpDir });
      } catch (error) {
        threw = true;
        errMsg = error.message;
      }

      assert(threw, 'runUpgradeDryRun throws when upgrade.py exits 1');
      assert(errMsg.toLowerCase().includes('dry-run failed') || errMsg.includes('upgrade.py'), 'error message is descriptive', `got: ${errMsg}`);
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  // ---------------------------------------------------------------------------
  // (c) runUpgradeYes succeeds (no lockfile skips routing — upgrade.py --yes path)
  // ---------------------------------------------------------------------------

  console.log('\n--- runUpgradeYes succeeds when upgrade.py exits 0 ---');

  await runTest('runUpgradeYes resolves without error when upgrade.py exits 0', async () => {
    const tmpDir = await _makeTempDir();
    try {
      const upgradePy = path.join(tmpDir, 'upgrade.py');
      await _writeFile(upgradePy, 'import sys\nprint("Upgrade complete.")\nsys.exit(0)\n');

      let threw = false;
      try {
        await runUpgradeYes({ upgradePy, projectRoot: tmpDir });
      } catch {
        threw = true;
      }

      assert(!threw, 'runUpgradeYes resolves cleanly on exit 0');
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  await runTest('runUpgradeYes throws when upgrade.py exits non-zero', async () => {
    const tmpDir = await _makeTempDir();
    try {
      const upgradePy = path.join(tmpDir, 'upgrade.py');
      await _writeFile(upgradePy, 'import sys\nprint("compile failure", file=sys.stderr)\nsys.exit(1)\n');

      let threw = false;
      let errMsg = '';
      try {
        await runUpgradeYes({ upgradePy, projectRoot: tmpDir });
      } catch (error) {
        threw = true;
        errMsg = error.message;
      }

      assert(threw, 'runUpgradeYes throws on non-zero exit');
      assert(errMsg.includes('exit 1') || errMsg.toLowerCase().includes('failed'), 'error message indicates failure', `got: ${errMsg}`);
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
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
