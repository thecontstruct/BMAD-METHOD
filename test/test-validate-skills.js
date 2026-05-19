'use strict';

/**
 * TPL-01 lint rule tests for tools/validate-skills.js
 * Usage: node test/test-validate-skills.js
 */

const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');

const { validateSkill } = require('../tools/validate-skills');

const colors = {
  reset: '[0m',
  green: '[32m',
  red: '[31m',
  cyan: '[36m',
};

let passed = 0;
let failed = 0;

function record(name, ok, detail) {
  if (ok) {
    passed++;
    console.log(`  ${colors.green}✓${colors.reset} ${name}`);
  } else {
    failed++;
    console.log(`  ${colors.red}✗${colors.reset} ${name}`);
    if (detail) console.log(`      ${detail.split('\n').join('\n      ')}`);
  }
}

const SKILL_MD = `---
name: bmad-test-fixture
description: Use when testing TPL-01. Use if you need to validate the lint rule.
---

Body content here.
`;

function makeFixture(fixtureFileName, fixtureContent) {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'tpl01-test-'));
  const skillDir = path.join(tmpRoot, 'bmad-test-fixture');
  fs.mkdirSync(skillDir);
  fs.writeFileSync(path.join(skillDir, 'SKILL.md'), SKILL_MD);
  fs.writeFileSync(path.join(skillDir, fixtureFileName), fixtureContent);
  return { tmpRoot, skillDir };
}

// Case 1 — {{.word}} in template.md → TPL-01 HIGH
function test_compile_time_sub_in_template_fires() {
  const { tmpRoot, skillDir } = makeFixture('template.md', 'Line one.\n{{.command}} is forbidden.\nLine three.');
  try {
    const findings = validateSkill(skillDir).filter((f) => f.rule === 'TPL-01');
    record('Case 1: findings.length === 1', findings.length === 1, `got ${findings.length}`);
    record(
      'Case 1: severity HIGH',
      findings.length > 0 && findings[0].severity === 'HIGH',
      findings[0] ? `got ${findings[0].severity}` : 'no finding',
    );
    record('Case 1: line === 2', findings.length > 0 && findings[0].line === 2, findings[0] ? `got ${findings[0].line}` : 'no finding');
    record(
      'Case 1: file === template.md',
      findings.length > 0 && findings[0].file === 'template.md',
      findings[0] ? `got ${findings[0].file}` : 'no finding',
    );
    record(
      'Case 1: detail includes {{.command}}',
      findings.length > 0 && findings[0].detail.includes('{{.command}}'),
      findings[0] ? `detail: ${findings[0].detail}` : 'no finding',
    );
  } finally {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
}

// Case 2 — clean template.md → no TPL-01
function test_clean_template_no_finding() {
  const { tmpRoot, skillDir } = makeFixture('template.md', 'Line one.\n{self.description} is fine.\n{{user_name}} also fine.\nLine four.');
  try {
    const findings = validateSkill(skillDir).filter((f) => f.rule === 'TPL-01');
    record('Case 2: clean template.md → no TPL-01', findings.length === 0, `got ${findings.length} finding(s)`);
  } finally {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
}

// Case 3 — {{self.X}} in template.md → no TPL-01 (sigil-safe)
function test_self_sigil_no_finding() {
  const { tmpRoot, skillDir } = makeFixture('template.md', '{{self.description}} is our runtime sigil.\n{{self.name}} is also safe.');
  try {
    const findings = validateSkill(skillDir).filter((f) => f.rule === 'TPL-01');
    record('Case 3: {{self.X}} → no TPL-01', findings.length === 0, `got ${findings.length} finding(s)`);
  } finally {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
}

// Case 4 — {{.var}} in non-template .md → no TPL-01
function test_non_template_no_finding() {
  const { tmpRoot, skillDir } = makeFixture('workflow.md', '{{.command}} appears here.');
  try {
    const findings = validateSkill(skillDir).filter((f) => f.rule === 'TPL-01');
    record('Case 4: {{.var}} in non-template file → no TPL-01', findings.length === 0, `got ${findings.length} finding(s)`);
  } finally {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
}

// Case 5 — multiple violations across lines → one finding per violation line
function test_multiple_violations() {
  const { tmpRoot, skillDir } = makeFixture('template.md', '{{.foo}} is bad.\nBetween.\n{{.bar}} also bad.');
  try {
    const findings = validateSkill(skillDir).filter((f) => f.rule === 'TPL-01');
    record('Case 5: two violations → 2 findings', findings.length === 2, `got ${findings.length}`);
    record(
      'Case 5: first finding line === 1',
      findings.length > 0 && findings[0].line === 1,
      findings[0] ? `got ${findings[0].line}` : 'no finding',
    );
    record(
      'Case 5: second finding line === 3',
      findings.length > 1 && findings[1].line === 3,
      findings[1] ? `got ${findings[1].line}` : 'no finding',
    );
  } finally {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
}

// ─────────────────────────────────────────────────────────────────────────
// Runner
// ─────────────────────────────────────────────────────────────────────────

console.log(`${colors.cyan}test-validate-skills.js (TPL-01)${colors.reset}\n`);

test_compile_time_sub_in_template_fires();
test_clean_template_no_finding();
test_self_sigil_no_finding();
test_non_template_no_finding();
test_multiple_violations();

console.log('');
console.log(`${colors.cyan}========================================${colors.reset}`);
console.log(`Test Results:`);
console.log(`  Passed: ${colors.green}${passed}${colors.reset}`);
console.log(`  Failed: ${colors.red}${failed}${colors.reset}`);
console.log(`${colors.cyan}========================================${colors.reset}\n`);

process.exit(failed > 0 ? 1 : 0);
