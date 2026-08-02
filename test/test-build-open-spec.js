'use strict';

const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const buildDir = path.join(root, 'src/bmm-skills/ship/bmad-build');
const customize = fs.readFileSync(path.join(buildDir, 'customize.toml'), 'utf8');
const present = fs.readFileSync(path.join(buildDir, 'step-05-present.template.md'), 'utf8');
const oneshot = fs.readFileSync(path.join(buildDir, 'step-oneshot.template.md'), 'utf8');

const checks = [
  ['customize exposes open_spec', /open_spec\s*=\s*"""[\s\S]*\{project-root\}[\s\S]*\{spec_file\}/.test(customize)],
  ['present route delegates editor behavior to open_spec', present.includes('{workflow.open_spec}') && !present.includes('code -r')],
  ['one-shot route delegates editor behavior to open_spec', oneshot.includes('{workflow.open_spec}') && !oneshot.includes('code -r')],
];

let failed = 0;
for (const [label, ok] of checks) {
  console.log(`${ok ? '✓' : '✗'} ${label}`);
  if (!ok) failed++;
}

if (failed) process.exit(1);
