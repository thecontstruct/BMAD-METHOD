'use strict';

/**
 * End-to-end smoke test for `bmad install` with Python batch compilation.
 *
 * Exercises the cross-tree batch compile path (engine.py + resolver.py) that
 * was broken by OVERRIDE_OUTSIDE_ROOT until commit 3786f12f. If this test
 * passes, the fix is verified.
 *
 * Spec: test/smoke/bmad-smoke.spec.md
 * Usage: node test/smoke/bmad-smoke.js
 */

const path = require('node:path');
const os = require('node:os');
const fs = require('node:fs');
const { spawnSync } = require('node:child_process');

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const CLI = path.join(REPO_ROOT, 'tools', 'installer', 'bmad-cli.js');
const PKG = require(path.join(REPO_ROOT, 'package.json'));

const colors = {
  reset: '[0m',
  green: '[32m',
  red: '[31m',
  yellow: '[33m',
  cyan: '[36m',
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
    if (errorMessage) {
      console.log(`  ${colors.dim}${errorMessage}${colors.reset}`);
    }
    failed++;
  }
}

function checkPython3() {
  const result = spawnSync('python3', ['--version'], { stdio: 'pipe' });
  if (result.status !== 0) {
    console.log(`${colors.yellow}SKIP: python3 not available — skipping smoke test${colors.reset}`);
    process.exit(0);
  }
}

function checkVersion() {
  console.log(`\n${colors.cyan}Version check${colors.reset}`);
  const result = spawnSync('node', [CLI, '--version'], { stdio: 'pipe', encoding: 'utf8' });
  const cliVersion = (result.stdout || '').trim().replace(/^v/, '');
  const pkgVersion = PKG.version;
  assert(result.status === 0, 'CLI --version exits 0', `exit code: ${result.status}`);
  assert(cliVersion === pkgVersion, `CLI version matches package.json (${pkgVersion})`, `got: ${JSON.stringify(cliVersion)}`);
}

function runInstall(tmpDir) {
  console.log(`\n${colors.cyan}Install check${colors.reset}`);
  console.log(`  ${colors.dim}Installing to ${tmpDir} ...${colors.reset}`);

  const result = spawnSync('node', [CLI, 'install', '--yes', '--directory', tmpDir, '--tools', 'claude-code', '--modules', 'bmm'], {
    stdio: 'pipe',
    encoding: 'utf8',
    timeout: 120_000,
    cwd: REPO_ROOT,
  });

  const stdout = result.stdout || '';
  const stderr = result.stderr || '';

  assert(result.status === 0, 'install exits 0', `exit code: ${result.status}\nstderr:\n${stderr.slice(0, 500)}`);
  assert(stdout.includes('BMAD is ready to use!'), 'stdout contains "BMAD is ready to use!"', `stdout tail: ${stdout.slice(-300)}`);
  assert(!stderr.includes('OVERRIDE_OUTSIDE_ROOT'), 'no OVERRIDE_OUTSIDE_ROOT in stderr', stderr.slice(0, 300));
  assert(!stderr.includes('BatchInstallError'), 'no BatchInstallError in stderr', stderr.slice(0, 300));
}

function checkDirectoryStructure(tmpDir) {
  console.log(`\n${colors.cyan}Directory structure${colors.reset}`);
  const expected = ['_bmad', '_bmad/scripts', '_bmad/bmm', '_bmad/_shared', '_bmad/_config', '.claude/skills'];
  for (const rel of expected) {
    const full = path.join(tmpDir, rel);
    assert(fs.existsSync(full) && fs.statSync(full).isDirectory(), `${rel}/ exists`);
  }
}

function checkSkillCount(tmpDir) {
  console.log(`\n${colors.cyan}Skill count (.claude/skills/)${colors.reset}`);
  const skillsDir = path.join(tmpDir, '.claude', 'skills');
  const entries = fs.readdirSync(skillsDir).filter((name) => {
    return fs.statSync(path.join(skillsDir, name)).isDirectory();
  });
  const count = entries.length;
  if (count !== 45) {
    console.log(`  ${colors.dim}Found ${count} skills: ${entries.sort().join(', ')}${colors.reset}`);
  }
  assert(count === 45, `exactly 45 skills installed (got ${count})`);
}

function checkKeySkills(tmpDir) {
  console.log(`\n${colors.cyan}Key skills present${colors.reset}`);
  const keySkills = ['bmad-create-story', 'bmad-code-review'];
  for (const skill of keySkills) {
    const skillMd = path.join(tmpDir, '.claude', 'skills', skill, 'SKILL.md');
    assert(fs.existsSync(skillMd), `${skill}/SKILL.md exists`);
  }
}

function checkSkillContent(tmpDir) {
  console.log(`\n${colors.cyan}SKILL.md content${colors.reset}`);
  const keySkills = ['bmad-create-story', 'bmad-code-review'];
  for (const skill of keySkills) {
    const skillMd = path.join(tmpDir, '.claude', 'skills', skill, 'SKILL.md');
    let content;
    try {
      content = fs.readFileSync(skillMd, 'utf8');
    } catch (error) {
      assert(false, `${skill}/SKILL.md readable`, `${error.message}`);
      continue;
    }
    const lines = content.split('\n');
    const hasFrontmatterOpen = lines[0] === '---';
    const hasFrontmatterClose = lines.slice(1).includes('---');
    assert(hasFrontmatterOpen, `${skill}/SKILL.md has opening frontmatter delimiter`);
    assert(hasFrontmatterClose, `${skill}/SKILL.md has closing frontmatter delimiter`);
    assert(content.length > 100, `${skill}/SKILL.md body > 100 bytes (got ${content.length})`);
  }
}

function checkManifest(tmpDir) {
  console.log(`\n${colors.cyan}Skill manifest${colors.reset}`);
  const manifestPath = path.join(tmpDir, '_bmad', '_config', 'skill-manifest.csv');
  assert(fs.existsSync(manifestPath), 'skill-manifest.csv exists');
  if (fs.existsSync(manifestPath)) {
    const lines = fs.readFileSync(manifestPath, 'utf8').split('\n').filter(Boolean);
    assert(lines.length >= 40, `skill-manifest.csv has >= 40 lines (got ${lines.length})`);
  }
}

async function main() {
  console.log(`${colors.cyan}═══════════════════════════════════════${colors.reset}`);
  console.log(`${colors.cyan}bmad install smoke test${colors.reset}`);
  console.log(`${colors.cyan}═══════════════════════════════════════${colors.reset}`);

  checkPython3();

  checkVersion();

  let tmpDir = null;
  let installFailed = false;

  try {
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'bmad-smoke-'));

    runInstall(tmpDir);
    installFailed = failed > 0;

    if (installFailed) {
      console.log(`\n${colors.yellow}Skipping filesystem checks because install failed${colors.reset}`);
    } else {
      checkDirectoryStructure(tmpDir);
      checkSkillCount(tmpDir);
      checkKeySkills(tmpDir);
      checkSkillContent(tmpDir);
      checkManifest(tmpDir);
    }
  } finally {
    if (tmpDir) {
      if (failed > 0) {
        console.log(`\n${colors.dim}Temp dir retained for inspection: ${tmpDir}${colors.reset}`);
      }
      try {
        fs.rmSync(tmpDir, { recursive: true, force: true });
      } catch (error) {
        console.log(`  ${colors.yellow}Warning: cleanup failed: ${error.message}${colors.reset}`);
      }
    }
  }

  console.log(`\n${colors.cyan}═══════════════════════════════════════${colors.reset}`);
  console.log(`${colors.green}Passed: ${passed}${colors.reset}  ${failed > 0 ? colors.red : colors.dim}Failed: ${failed}${colors.reset}`);
  console.log(`${colors.cyan}═══════════════════════════════════════${colors.reset}`);

  process.exit(failed > 0 ? 1 : 0);
}

main().catch((error) => {
  console.error(`${colors.red}Unexpected error: ${error.message}${colors.reset}`);
  process.exit(1);
});
