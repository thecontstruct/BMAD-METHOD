'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const gather = fs.readFileSync(path.join(root, 'src/bmm-skills/4-implementation/bmad-code-review/steps/step-01-gather-context.md'), 'utf8');
const lens = fs.readFileSync(path.join(root, 'src/core-skills/bmad-review/references/lens-verification-gap.md'), 'utf8');

const checks = [
  ['explicit no-spec requests skip the spec question', gather.includes('explicitly') && gather.includes('Do **not** ask for a spec')],
  ['unspecified context requires a user choice', gather.includes('ask the user to choose') && gather.includes('Continue without a spec')],
  ['test-only removals can be verification gaps', lens.includes('test-only change') && lens.includes('broken-verification gap')],
  ['verification lens stops at inference boundaries', lens.includes('stop at the inference boundary')],
];

let failed = 0;
for (const [label, ok] of checks) {
  console.log(`${ok ? '✓' : '✗'} ${label}`);
  if (!ok) failed++;
}
if (failed) process.exit(1);
