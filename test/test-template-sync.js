/**
 * Sprint-status template sync check.
 *
 * The sprint-status template is a cross-skill contract: bmad-sprint-planning
 * owns the source of truth, while bmad-retrospective tests a vendored copy.
 * This check prevents the copies from drifting.
 */

const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');
const source = path.join(root, 'src/bmm-skills/plan/bmad-sprint-planning/sprint-status-template.yaml');
const fixture = path.join(root, 'src/bmm-skills/ship/bmad-retrospective/scripts/tests/fixtures/sprint-status-template.yaml');

const sourceText = fs.readFileSync(source, 'utf8');
const fixtureText = fs.readFileSync(fixture, 'utf8');

if (sourceText !== fixtureText) {
  console.error('FAIL: sprint-status template fixture is out of sync.');
  console.error(`  source:  ${path.relative(root, source)}`);
  console.error(`  fixture: ${path.relative(root, fixture)}`);
  console.error('Copy the source over the fixture to resolve.');
  process.exit(1);
}

console.log('ok: sprint-status template fixture matches the source template');
