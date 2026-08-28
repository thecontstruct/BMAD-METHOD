'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const buildDir = path.join(root, 'src/bmm-skills/ship/bmad-build');
const customize = fs.readFileSync(path.join(buildDir, 'customize.toml'), 'utf8');
const route = fs.readFileSync(path.join(buildDir, 'step-01-clarify-and-route.template.md'), 'utf8');
const plan = fs.readFileSync(path.join(buildDir, 'step-02-plan.template.md'), 'utf8');
const spec = fs.readFileSync(path.join(buildDir, 'spec-template.md'), 'utf8');
const present = fs.readFileSync(path.join(buildDir, 'step-05-present.template.md'), 'utf8');
const oneshot = fs.readFileSync(path.join(buildDir, 'step-oneshot.template.md'), 'utf8');

const checks = [
  ['customize exposes open_spec', /open_spec\s*=\s*"""[\s\S]*\{project-root\}[\s\S]*\{spec_file\}/.test(customize)],
  ['present route delegates editor behavior to open_spec', present.includes('{workflow.open_spec}') && !present.includes('code -r')],
  ['one-shot route delegates editor behavior to open_spec', oneshot.includes('{workflow.open_spec}') && !oneshot.includes('code -r')],
  [
    'folder-plus-id dispatch keeps story specs beside stories.yaml',
    route.includes("spec_folder: ''") &&
      route.includes("story_id: ''") &&
      route.includes('{spec_folder}/stories.yaml') &&
      route.includes('{spec_folder}/stories/{story_id}-*.md') &&
      route.includes('keep the colocated `{spec_file}` selected above'),
  ],
  [
    'routing happens after investigation, not during clarification',
    !route.includes('zero blast radius') &&
      route.includes('Do not conduct an intent interview here') &&
      plan.includes('Investigate the codebase') &&
      plan.includes('If there are no intent gaps, nothing irreversible, and the change is small'),
  ],
  [
    'light in-session route has an escalation path',
    spec.includes("route: '' # in-session | dispatch") &&
      spec.includes('## Open Questions') &&
      spec.includes('## Implementation Notes') &&
      oneshot.includes('**Escalation ramp.**') &&
      oneshot.includes("set `route: 'dispatch'` and `status: 'draft'`"),
  ],
];

let failed = 0;
for (const [label, ok] of checks) {
  console.log(`${ok ? '✓' : '✗'} ${label}`);
  if (!ok) failed++;
}

if (failed) process.exit(1);
