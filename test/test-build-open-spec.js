'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const buildDir = path.join(root, 'src/bmm-skills/ship/bmad-build');
const customize = fs.readFileSync(path.join(buildDir, 'customize.toml'), 'utf8');
const route = fs.readFileSync(path.join(buildDir, 'step-01-clarify-and-route.template.md'), 'utf8');
const present = fs.readFileSync(path.join(buildDir, 'step-05-present.template.md'), 'utf8');
const oneshot = fs.readFileSync(path.join(buildDir, 'step-oneshot.template.md'), 'utf8');

const checks = [
  ['customize exposes open_plan', /open_plan\s*=\s*"""[\s\S]*\{project-root\}[\s\S]*\{plan_file\}/.test(customize)],
  ['present route delegates editor behavior to open_plan', present.includes('{workflow.open_plan}') && !present.includes('code -r')],
  ['one-shot route delegates editor behavior to open_plan', oneshot.includes('{workflow.open_plan}') && !oneshot.includes('code -r')],
  [
    'ticket-tree routing resolves plans through the shared runtime',
    route.includes("ticket_args: ''") &&
      route.includes('tickets.py --project-root {project-root} find') &&
      route.includes('tickets.py --project-root {project-root} next') &&
      route.includes('find.plan'),
  ],
];

let failed = 0;
for (const [label, ok] of checks) {
  console.log(`${ok ? '✓' : '✗'} ${label}`);
  if (!ok) failed++;
}

if (failed) process.exit(1);
