/**
 * Regression coverage for bmad-build-auto's deferred-finding contract.
 */

'use strict';

const fs = require('node:fs');
const path = require('node:path');
const yaml = require('yaml');

let total = 0;
let passed = 0;
const failures = [];

function test(name, fn) {
  total++;
  try {
    fn();
    passed++;
    console.log(`✓ ${name}`);
  } catch (error) {
    failures.push({ name, message: error.message });
    console.error(`✗ ${name}: ${error.message}`);
  }
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function read(relativePath) {
  return fs.readFileSync(path.join(__dirname, '..', relativePath), 'utf-8');
}

function parseFrontmatter(content, relativePath) {
  assert(content.startsWith('---\n'), `${relativePath} must start with a frontmatter delimiter`);
  const end = content.indexOf('\n---\n', 4);
  assert(end !== -1, `${relativePath} must close its frontmatter delimiter`);
  return yaml.parse(content.slice(4, end));
}

function dedent(content) {
  const lines = content.split('\n');
  const indents = lines.filter((line) => line.trim()).map((line) => line.match(/^ */)[0].length);
  const width = Math.min(...indents);
  return lines.map((line) => line.slice(width)).join('\n');
}

test('spec template exposes machine-readable deferred frontmatter', () => {
  const relativePath = 'src/bmm-skills/ship/bmad-build-auto/spec-template.md';
  const frontmatter = parseFrontmatter(read(relativePath), relativePath);
  assert(Array.isArray(frontmatter.deferred), 'spec-template.md frontmatter must declare deferred as a list');
  assert(frontmatter.deferred.length === 0, 'spec-template.md deferred list must start empty');
});

test('build-auto steps preserve their frontmatter boundaries', () => {
  const root = 'src/bmm-skills/ship/bmad-build-auto';
  const stepOnePath = `${root}/step-01-clarify-and-route.md`;
  const stepOneFrontmatter = parseFrontmatter(read(stepOnePath), stepOnePath);
  assert(stepOneFrontmatter.spec_file === '', 'step-01 must define spec_file in frontmatter');
  assert(stepOneFrontmatter.spec_folder === '', 'step-01 must define spec_folder in frontmatter');
  assert(stepOneFrontmatter.story_id === '', 'step-01 must define story_id in frontmatter');

  for (const filename of ['step-02-plan.md', 'step-04-review.md']) {
    const relativePath = `${root}/${filename}`;
    const content = read(relativePath);
    if (content.startsWith('---\n')) parseFrontmatter(content, relativePath);
  }
});

test('implementation handoff stays thin and spec-led', () => {
  const content = read('src/bmm-skills/ship/bmad-build-auto/customize.toml');
  assert(
    content.includes('Read {spec_file} fully and implement it — the spec is the sole source of truth.'),
    'handoff must make the spec the implementation source of truth',
  );
  assert(content.includes('Load every file listed in its frontmatter `context:` before you start.'), 'handoff must load declared context');
  assert(
    content.includes('report what you changed, how you verified it, and anything left incomplete or risky'),
    'handoff must request a concise completion report',
  );
  assert(!content.includes('Guardrails:'), 'handoff must not re-expand speculative guardrails');
  assert(
    !content.includes('Spec Change Log entries are binding constraints'),
    'handoff must not duplicate spec detail into dispatch instructions',
  );
});

test('review step safely records deferred findings only in the spec', () => {
  const content = read('src/bmm-skills/ship/bmad-build-auto/step-04-review.md');
  assert(content.includes('If the field is absent'), 'step-04-review.md must initialize deferred for legacy specs');
  assert(content.includes('never add a second `deferred:` key'), 'step-04-review.md must forbid duplicate deferred keys');
  assert(content.includes('parse the complete frontmatter as YAML'), 'step-04-review.md must validate the updated frontmatter');
  assert(!content.includes('deferred_work_file'), 'step-04-review.md must not mention a deferred-work ledger path');
  assert(!content.includes('deferred-work.md'), 'step-04-review.md must not mention the deferred-work ledger artifact');

  const example = content.match(/```yaml\n([\s\S]*?)\n[ \t]*```/);
  assert(example, 'step-04-review.md must include the deferred YAML example');
  const specialCharacters = dedent(example[1])
    .replace('<one sentence>', 'Parser fails: malformed # input')
    .replace('<why this is real>', 'Observed: value # remains data\n      Second evidence line');
  const parsed = yaml.parse(specialCharacters);
  assert(parsed.deferred[0].summary === 'Parser fails: malformed # input', 'summary example must preserve YAML-special characters');
  assert(
    parsed.deferred[0].evidence === 'Observed: value # remains data\nSecond evidence line',
    'evidence example must preserve YAML-special characters and line breaks',
  );
});

test('reference docs direct orchestrators to the spec deferred list', () => {
  const content = read('docs/reference/build-auto.md');
  assert(
    content.includes('Read deferred findings from the spec frontmatter `deferred:` list'),
    'docs/reference/build-auto.md must tell orchestrators where to read deferred findings',
  );
  assert(!content.includes('deferred-work.md'), 'docs/reference/build-auto.md must not describe a deferred-work ledger artifact');
});

console.log(`\n${passed}/${total} tests passed`);

if (failures.length > 0) {
  for (const failure of failures) console.error(`${failure.name}: ${failure.message}`);
  process.exit(1);
}
