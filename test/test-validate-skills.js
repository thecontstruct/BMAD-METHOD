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
// TPL-02 helpers
// ─────────────────────────────────────────────────────────────────────────

function makeComponentFixture(skillMdBody, fixtureFiles = {}) {
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'tpl02-test-'));
  const skillDir = path.join(tmpRoot, 'bmad-test-fixture');
  fs.mkdirSync(skillDir);
  const fullSkillMd = SKILL_MD.trimEnd() + '\n\n' + skillMdBody + '\n';
  fs.writeFileSync(path.join(skillDir, 'SKILL.md'), fullSkillMd);
  for (const [relPath, content] of Object.entries(fixtureFiles)) {
    const absPath = path.join(skillDir, relPath);
    fs.mkdirSync(path.dirname(absPath), { recursive: true });
    fs.writeFileSync(absPath, content);
  }
  return { tmpRoot, skillDir };
}

function makeCompEntry(overrides = {}) {
  return {
    name: 'DateBanner',
    path: 'components/date_banner.py',
    source_hash: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    render_mode: 'compile',
    props: {},
    props_hash: '1234567890abcdef',
    compiled_hash: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
    sentinel_format_version: null,
    ...overrides,
  };
}

// ─────────────────────────────────────────────────────────────────────────
// TPL-02 test cases
// ─────────────────────────────────────────────────────────────────────────

// Case 6 — compile-only skill with stale JIT sentinel → TPL-02 HIGH
function test_tpl02_compile_only_with_jit_sentinel() {
  const { tmpRoot, skillDir } = makeComponentFixture('<!-- BMAD-JIT:DateBanner:1234567890abcdef -->', {
    'components/date_banner.py': 'RENDER_MODE = "compile"\ndef render(ctx, **props):\n    return ""\n',
  });
  const components = [makeCompEntry({ render_mode: 'compile' })];
  try {
    const findings = validateSkill(skillDir, components).filter((f) => f.rule === 'TPL-02');
    record('Case 6: compile-only with JIT sentinel → 1 HIGH TPL-02', findings.length > 0, `got ${findings.length}`);
    record(
      'Case 6: finding severity HIGH',
      findings.some((f) => f.severity === 'HIGH' && f.title === 'Compile-only skill contains JIT sentinel'),
      JSON.stringify(findings.map((f) => f.title)),
    );
  } finally {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
}

// Case 7 — malformed sentinel → TPL-02 HIGH
function test_tpl02_malformed_sentinel() {
  const { tmpRoot, skillDir } = makeComponentFixture('<!-- BMAD-JIT:badformat -->');
  const components = [makeCompEntry({ render_mode: 'jit', sentinel_format_version: 1, compiled_hash: null })];
  try {
    const findings = validateSkill(skillDir, components).filter((f) => f.rule === 'TPL-02');
    record(
      'Case 7: malformed sentinel → 1 HIGH TPL-02',
      findings.some((f) => f.severity === 'HIGH' && f.title === 'Malformed JIT sentinel in SKILL.md'),
      JSON.stringify(findings.map((f) => f.title)),
    );
  } finally {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
}

// Case 8 — sentinel with no lockfile entry → TPL-02 MEDIUM
function test_tpl02_sentinel_lockfile_mismatch() {
  const { tmpRoot, skillDir } = makeComponentFixture('<!-- BMAD-JIT:DateBanner:bbbbbbbbbbbbbbbb -->');
  const components = [
    makeCompEntry({ render_mode: 'jit', props_hash: 'aaaaaaaaaaaaaaaa', compiled_hash: null, sentinel_format_version: 1 }),
  ];
  try {
    const findings = validateSkill(skillDir, components).filter((f) => f.rule === 'TPL-02');
    record(
      'Case 8: sentinel hash mismatch → MEDIUM TPL-02',
      findings.some((f) => f.severity === 'MEDIUM' && f.title === 'JIT sentinel has no matching lockfile entry'),
      JSON.stringify(findings.map((f) => `${f.severity}:${f.title}`)),
    );
  } finally {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
}

// Case 9 — component missing def render( → TPL-02 HIGH
function test_tpl02_missing_def_render() {
  const { tmpRoot, skillDir } = makeComponentFixture('Body content.', {
    'components/date_banner.py': 'RENDER_MODE = "compile"\n# no render function\n',
  });
  const components = [makeCompEntry({ render_mode: 'compile' })];
  try {
    const findings = validateSkill(skillDir, components).filter((f) => f.rule === 'TPL-02');
    record(
      'Case 9: missing def render( → HIGH TPL-02',
      findings.some((f) => f.severity === 'HIGH' && f.title === 'Component missing def render( function'),
      JSON.stringify(findings.map((f) => `${f.severity}:${f.title}`)),
    );
  } finally {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
}

// Case 10 — JIT component missing RENDER_ERROR_FALLBACK → TPL-02 HIGH
function test_tpl02_missing_render_error_fallback() {
  const { tmpRoot, skillDir } = makeComponentFixture('Body content.', {
    'components/sprint_banner.py': 'RENDER_MODE = "jit"\ndef render(ctx, **props):\n    return "hello"\n',
  });
  const components = [
    makeCompEntry({
      name: 'SprintBanner',
      path: 'components/sprint_banner.py',
      render_mode: 'jit',
      compiled_hash: null,
      sentinel_format_version: 1,
    }),
  ];
  try {
    const findings = validateSkill(skillDir, components).filter((f) => f.rule === 'TPL-02');
    record(
      'Case 10: missing RENDER_ERROR_FALLBACK → HIGH TPL-02',
      findings.some((f) => f.severity === 'HIGH' && f.title === 'JIT component missing RENDER_ERROR_FALLBACK'),
      JSON.stringify(findings.map((f) => `${f.severity}:${f.title}`)),
    );
  } finally {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
}

// Case 11 — components: [] → no TPL-02 findings (AC-1 skip)
function test_tpl02_empty_components_skip() {
  const { tmpRoot, skillDir } = makeComponentFixture('<!-- BMAD-JIT:Whatever:1234567890abcdef -->');
  const components = [];
  try {
    const findings = validateSkill(skillDir, components).filter((f) => f.rule === 'TPL-02');
    record('Case 11: components: [] → no TPL-02 findings', findings.length === 0, `got ${findings.length}`);
  } finally {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
}

// ─────────────────────────────────────────────────────────────────────────
// Runner
// ─────────────────────────────────────────────────────────────────────────

console.log(`${colors.cyan}test-validate-skills.js (TPL-01 + TPL-02)${colors.reset}\n`);

test_compile_time_sub_in_template_fires();
test_clean_template_no_finding();
test_self_sigil_no_finding();
test_non_template_no_finding();
test_multiple_violations();

console.log(`\n${colors.cyan}--- TPL-02 cases ---${colors.reset}`);
test_tpl02_compile_only_with_jit_sentinel();
test_tpl02_malformed_sentinel();
test_tpl02_sentinel_lockfile_mismatch();
test_tpl02_missing_def_render();
test_tpl02_missing_render_error_fallback();
test_tpl02_empty_components_skip();

console.log(`\n${colors.cyan}--- SKILL-06 deprecation exemption cases (upstream c9813c68) ---${colors.reset}`);

const SKILL06_FIXTURES_DIR = path.join(__dirname, 'fixtures/validate-skills');

function hasSkill06TriggerFinding(skillName) {
  const findings = validateSkill(path.join(SKILL06_FIXTURES_DIR, skillName));
  return findings.some((f) => f.rule === 'SKILL-06' && /trigger phrase/i.test(f.detail));
}

record(
  'SKILL-06: deprecated skill is exempt from trigger-phrase requirement',
  hasSkill06TriggerFinding('deprecated-shim') === false,
  'Expected no SKILL-06 trigger finding for a DEPRECATED skill',
);
record(
  'SKILL-06: active skill missing trigger phrase is still flagged',
  hasSkill06TriggerFinding('missing-trigger') === true,
  'Expected a SKILL-06 trigger finding for a non-deprecated skill without "Use when"',
);
record(
  'SKILL-06: active skill with "Use when" trigger is not flagged',
  hasSkill06TriggerFinding('with-trigger') === false,
  'Expected no SKILL-06 trigger finding when description contains "Use when"',
);

console.log('');
console.log(`${colors.cyan}========================================${colors.reset}`);
console.log(`Test Results:`);
console.log(`  Passed: ${colors.green}${passed}${colors.reset}`);
console.log(`  Failed: ${colors.red}${failed}${colors.reset}`);
console.log(`${colors.cyan}========================================${colors.reset}\n`);

process.exit(failed > 0 ? 1 : 0);
