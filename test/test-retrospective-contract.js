'use strict';

const fs = require('node:fs');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../src/bmm-skills/ship/bmad-retrospective/bmad-retrospective.template.md'), 'utf8');

const checks = [
  ['requires evidence-backed findings', source.includes('A claim without evidence is not a finding')],
  ['supports unattended runs', source.includes('-H` / `--headless')],
  ['defines all acceptance verdicts', ['accepted`', 'accepted-with-open-items`', 'rejected`'].every((value) => source.includes(value))],
  ['does not alter implementation artifacts', source.includes('Do not modify project code, specs, stories, or tests')],
  ['supports spec-folder story epics without sprint status', source.includes('### Stories mode') && source.includes('stories.yaml')],
  [
    'stories-mode retro does not mutate the story contract',
    source.includes('do not create or edit sprint status, `SPEC.md`, `stories.yaml`, or any story artifact'),
  ],
];

let failed = 0;
for (const [label, ok] of checks) {
  console.log(`${ok ? '✓' : '✗'} ${label}`);
  if (!ok) failed++;
}
if (failed) process.exit(1);
