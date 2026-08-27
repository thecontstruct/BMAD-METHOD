'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const gather = fs.readFileSync(path.join(root, 'src/bmm-skills/ship/bmad-code-review/steps/step-01-gather-context.md'), 'utf8');
const lens = fs.readFileSync(path.join(root, 'src/core-skills/bmad-review/references/lens-verification-gap.md'), 'utf8');
const edgeLens = fs.readFileSync(path.join(root, 'src/core-skills/bmad-review/references/lens-edge-case-hunter.md'), 'utf8');
const review = fs.readFileSync(path.join(root, 'src/core-skills/bmad-review/bmad-review.template.md'), 'utf8');
const customize = fs.readFileSync(path.join(root, 'src/bmm-skills/ship/bmad-code-review/customize.toml'), 'utf8');
const triage = fs.readFileSync(path.join(root, 'src/bmm-skills/ship/bmad-code-review/steps/step-03-triage.md'), 'utf8');

const checks = [
  ['explicit no-spec requests skip the spec question', gather.includes('explicitly') && gather.includes('Do **not** ask for a spec')],
  ['unspecified context requires a user choice', gather.includes('ask the user to choose') && gather.includes('Continue without a spec')],
  ['test-only removals can be verification gaps', lens.includes('test-only change') && lens.includes('broken-verification gap')],
  ['verification lens stops at inference boundaries', lens.includes('stop at the inference boundary')],
  [
    'claims narrative is staged without exposing it to every layer',
    gather.includes('claims_file') && gather.includes('edge-case layer only'),
  ],
  [
    'edge-case lens falsifies claims after path tracing',
    edgeLens.includes('## Step 4: Claims check') && edgeLens.includes('must finish before the narrative'),
  ],
  ['claims remain isolated to the edge-case lens', review.includes('goes only to the edge-case lens')],
  [
    'code review has its default review layers',
    ['blind-hunter', 'edge-case-hunter', 'verification-gap', 'acceptance-auditor'].every((id) => customize.includes(`id = "${id}"`)),
  ],
  [
    'review layers receive a staged diff path rather than repeated diff text',
    gather.includes('diff_file') && customize.includes('{diff_file}') && !customize.includes('{diff_output}'),
  ],
  [
    'each review finding is verified before grouping or dismissal',
    triage.includes('before grouping') && triage.includes('never drop a finding silently'),
  ],
];

let failed = 0;
for (const [label, ok] of checks) {
  console.log(`${ok ? '✓' : '✗'} ${label}`);
  if (!ok) failed++;
}
if (failed) process.exit(1);
