'use strict';

/**
 * Unit tests for tools/installer/compiler/invoke-python.js
 *
 * Covers:
 *   (a) checkPythonVersion: parses 3.11+, too-old, not-found paths
 *   (b) hasMigratedSkillsInScope: basename-match rule, false-positive regression,
 *       positive case, IDE-variant positive case
 *   (c) runInstallPhase: malformed JSON line surfaces actionable error;
 *       kind:error event throws with caret-format message
 *
 * Usage: node test/test-invoke-python.js
 */

const path = require('node:path');
const fs = require('node:fs/promises');
const os = require('node:os');

const { checkPythonVersion, hasMigratedSkillsInScope, runInstallPhase } = require('../tools/installer/compiler/invoke-python');

const colors = {
  reset: '[0m',
  green: '[32m',
  red: '[31m',
  dim: '[2m',
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

function _makeFakeOfficialModules(sourceMap) {
  return {
    async findModuleSource(moduleCode) {
      return sourceMap[moduleCode] ?? null;
    },
  };
}

async function _makeTempDir() {
  return fs.mkdtemp(path.join(os.tmpdir(), 'invoke-py-test-'));
}

async function _writeFile(filePath, content = '') {
  await fs.mkdir(path.dirname(filePath), { recursive: true });
  await fs.writeFile(filePath, content, 'utf8');
}

async function main() {
  // ---------------------------------------------------------------------------
  // (a) checkPythonVersion
  // ---------------------------------------------------------------------------

  console.log('\n--- checkPythonVersion ---');

  await runTest('returns an object with ok:boolean', async () => {
    const result = await checkPythonVersion();
    assert(typeof result.ok === 'boolean', 'ok is boolean');
    if (result.ok) {
      assert(typeof result.version === 'string', 'ok:true has version string');
      assert(/^\d+\.\d+\.\d+$/.test(result.version), 'version matches x.y.z');
    } else {
      assert(result.reason === 'not found' || result.reason === 'too old', 'failure has valid reason');
      assert(typeof result.detected === 'string', 'failure has detected string');
    }
  });

  // ---------------------------------------------------------------------------
  // (b) hasMigratedSkillsInScope — basename-match rule (R3-A1)
  // ---------------------------------------------------------------------------

  console.log('\n--- hasMigratedSkillsInScope ---');

  await runTest('false-positive regression: bmm workflow template shape returns false', async () => {
    // Fixture: dir bmad-technical-research/ contains research.template.md (NOT bmad-technical-research.template.md)
    const tmpDir = await _makeTempDir();
    try {
      await _writeFile(path.join(tmpDir, 'bmad-technical-research', 'research.template.md'), 'workflow template');
      const fakeModules = _makeFakeOfficialModules({ bmm: tmpDir });
      const result = await hasMigratedSkillsInScope({}, ['bmm'], fakeModules);
      assert(result === false, 'research.template.md does not match bmad-technical-research basename', `got ${result}`);
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  await runTest('positive case: foo/ containing foo.template.md returns true', async () => {
    const tmpDir = await _makeTempDir();
    try {
      await _writeFile(path.join(tmpDir, 'foo', 'foo.template.md'), 'skill content');
      const fakeModules = _makeFakeOfficialModules({ mymod: tmpDir });
      const result = await hasMigratedSkillsInScope({}, ['mymod'], fakeModules);
      assert(result === true, 'foo/foo.template.md detected as migrated skill');
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  await runTest('positive case: IDE-variant foo/foo.cursor.template.md returns true', async () => {
    const tmpDir = await _makeTempDir();
    try {
      await _writeFile(path.join(tmpDir, 'foo', 'foo.cursor.template.md'), 'cursor variant');
      const fakeModules = _makeFakeOfficialModules({ mymod: tmpDir });
      const result = await hasMigratedSkillsInScope({}, ['mymod'], fakeModules);
      assert(result === true, 'foo/foo.cursor.template.md detected');
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  await runTest('positive case: claudecode IDE variant detected', async () => {
    const tmpDir = await _makeTempDir();
    try {
      await _writeFile(path.join(tmpDir, 'bar', 'bar.claudecode.template.md'), 'claudecode variant');
      const fakeModules = _makeFakeOfficialModules({ mymod: tmpDir });
      const result = await hasMigratedSkillsInScope({}, ['mymod'], fakeModules);
      assert(result === true, 'bar/bar.claudecode.template.md detected');
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  await runTest('empty source tree returns false', async () => {
    const tmpDir = await _makeTempDir();
    try {
      const fakeModules = _makeFakeOfficialModules({ mymod: tmpDir });
      const result = await hasMigratedSkillsInScope({}, ['mymod'], fakeModules);
      assert(result === false, 'empty tree returns false');
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  await runTest('findModuleSource returning null skips module gracefully', async () => {
    const fakeModules = _makeFakeOfficialModules({});
    const result = await hasMigratedSkillsInScope({}, ['unknown-module'], fakeModules);
    assert(result === false, 'null sourcePath treated as no skills');
  });

  await runTest('nested skill dir detected at depth > 1', async () => {
    const tmpDir = await _makeTempDir();
    try {
      // Mirrors bmm structure: 1-analysis/research/bmad-help/
      const skillDir = path.join(tmpDir, '1-analysis', 'research', 'bmad-help');
      await _writeFile(path.join(skillDir, 'bmad-help.template.md'), 'help content');
      const fakeModules = _makeFakeOfficialModules({ bmm: tmpDir });
      const result = await hasMigratedSkillsInScope({}, ['bmm'], fakeModules);
      assert(result === true, 'skill nested at depth 3 detected');
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  await runTest('sibling non-matching template does not trigger detection', async () => {
    const tmpDir = await _makeTempDir();
    try {
      // Same dir as false-positive case but verifying no other file names trigger it
      await _writeFile(path.join(tmpDir, 'foo', 'SKILL.md'), 'compiled output');
      await _writeFile(path.join(tmpDir, 'foo', 'other.template.md'), 'other template');
      const fakeModules = _makeFakeOfficialModules({ mymod: tmpDir });
      const result = await hasMigratedSkillsInScope({}, ['mymod'], fakeModules);
      assert(result === false, 'other.template.md in foo/ does not match foo basename');
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  // ---------------------------------------------------------------------------
  // (c) runInstallPhase: error-path contract
  // ---------------------------------------------------------------------------

  console.log('\n--- runInstallPhase ---');

  await runTest('malformed JSON line from stdout surfaces actionable error', async () => {
    const tmpDir = await _makeTempDir();
    try {
      const installDir = path.join(tmpDir, '_bmad');
      const scriptsDir = path.join(installDir, 'scripts');
      await fs.mkdir(scriptsDir, { recursive: true });

      // Fake compile.py that emits a non-JSON line
      await _writeFile(path.join(scriptsDir, 'compile.py'), 'import sys\nprint("not json at all")\nsys.exit(0)\n');

      let threw = false;
      let errMsg = '';
      try {
        await runInstallPhase({ bmadDir: installDir, projectRoot: tmpDir });
      } catch (error) {
        threw = true;
        errMsg = error.message;
      }

      assert(threw, 'runInstallPhase throws on malformed JSON line');
      assert(errMsg.toLowerCase().includes('json'), 'error message mentions JSON', `got: ${errMsg}`);
      assert(errMsg.includes('not json'), 'error snippet present in message', `got: ${errMsg}`);
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  await runTest('kind:error event causes runInstallPhase to throw', async () => {
    const tmpDir = await _makeTempDir();
    try {
      const installDir = path.join(tmpDir, '_bmad');
      const scriptsDir = path.join(installDir, 'scripts');
      await fs.mkdir(scriptsDir, { recursive: true });

      const fakeScript = [
        'import sys, json',
        'print(json.dumps({"schema_version":1,"kind":"error","skill":"mod/s","status":"error","code":"UNRESOLVED_VARIABLE","file":"s.template.md","line":1,"col":1,"message":"undefined var","hint":"define it"}))',
        'print(json.dumps({"schema_version":1,"kind":"summary","compiled":0,"errors":1,"lockfile_path":"/fake/bmad.lock"}))',
        'sys.exit(1)',
      ].join('\n');
      await _writeFile(path.join(scriptsDir, 'compile.py'), fakeScript);

      let threw = false;
      let errMsg = '';
      try {
        await runInstallPhase({ bmadDir: installDir, projectRoot: tmpDir });
      } catch (error) {
        threw = true;
        errMsg = error.message;
      }

      assert(threw, 'runInstallPhase throws on kind:error event');
      assert(errMsg.includes('UNRESOLVED_VARIABLE'), 'error message includes error code', `got: ${errMsg}`);
      assert(errMsg.includes('undefined var'), 'error message includes error description', `got: ${errMsg}`);
    } finally {
      await fs.rm(tmpDir, { recursive: true, force: true });
    }
  });

  await runTest('caret format: kind:error with file/line/col/hint produces caret-style output', async () => {
    const tmpDir = await _makeTempDir();
    try {
      const installDir = path.join(tmpDir, '_bmad');
      const scriptsDir = path.join(installDir, 'scripts');
      await fs.mkdir(scriptsDir, { recursive: true });

      const fakeScript = [
        'import sys, json',
        'print(json.dumps({"schema_version":1,"kind":"error","skill":"mod/s","status":"error","code":"MISSING_FRAGMENT","file":"x/y.template.md","line":3,"col":5,"message":"fragment missing","hint":"create it"}))',
        'print(json.dumps({"schema_version":1,"kind":"summary","compiled":0,"errors":1,"lockfile_path":"/fake/bmad.lock"}))',
        'sys.exit(1)',
      ].join('\n');
      await _writeFile(path.join(scriptsDir, 'compile.py'), fakeScript);

      let errMsg = '';
      try {
        await runInstallPhase({ bmadDir: installDir, projectRoot: tmpDir });
      } catch (error) {
        errMsg = error.message;
      }

      assert(errMsg.includes('MISSING_FRAGMENT'), 'error code in caret output');
      assert(errMsg.includes('x/y.template.md'), 'file in caret output');
      assert(errMsg.includes(':3:'), 'line in caret output');
      assert(errMsg.includes(':5:') || errMsg.includes('3:5'), 'col in caret output', `got: ${errMsg}`);
      assert(errMsg.includes('create it'), 'hint in caret output');
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
