/** Ticket-tree consumer contract for Correct Course. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const failures = [];
const test = (name, condition) => {
  if (condition) console.log(`✓ ${name}`);
  else {
    console.error(`✗ ${name}`);
    failures.push(name);
  }
};

const skill = 'src/bmm-skills/plan/bmad-correct-course';
const template = read(`${skill}/bmad-correct-course.template.md`);
const reference = read(`${skill}/references/ticket-tree.md`);
const checklist = read(`${skill}/checklist.md`);

test(
  'Correct Course resolves ticket trees through the shared runtime first',
  template.includes('uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} status') &&
    template.includes('references/ticket-tree.md') &&
    reference.includes('uv run {project-root}/_bmad/method/scripts/tickets.py') &&
    !template.includes('python3 {project-root}/_bmad/method/scripts/tickets.py') &&
    !reference.includes('python3 {project-root}/_bmad/method/scripts/tickets.py'),
);
test(
  'Correct Course resolves each affected ticket before proposing changes',
  template.includes('tickets.py --project-root {project-root} find <ref>') && reference.includes('find <ref>'),
);
test(
  'Correct Course retains a legacy fallback without dual-reading ticket state',
  template.includes('legacy epics-and-stories fallback') &&
    reference.includes('only when `tickets.py status` cannot resolve an active tree') &&
    reference.includes('Do not load or update sprint status as a second source'),
);
test(
  'Correct Course routes approved operations to ticketing without mutating the tree',
  template.includes('route it to `bmad-preview-ticketing`') &&
    reference.includes('Never run `tickets.py pull` or `tickets.py mark`') &&
    reference.includes('edit `tickets.toml`'),
);
test(
  'Correct Course no longer updates sprint status from its checklist',
  !checklist.includes('Update sprint-status.yaml') && checklist.includes('hand the approved operations list to `bmad-preview-ticketing`'),
);

if (failures.length) process.exit(1);
