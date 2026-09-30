/** Ticket-tree consumer contract for code review and retrospective. */
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
const review = read('src/bmm-skills/ship/bmad-code-review/steps/step-01-gather-context.md');
const present = read('src/bmm-skills/ship/bmad-code-review/steps/step-04-present.md');
test(
  'Code Review selects review tickets through the uv-run shared runtime',
  review.includes('uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} status') &&
    review.includes('uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} find <ref>') &&
    !review.includes('python3 {project-root}/_bmad/method/scripts/tickets.py') &&
    review.includes('state` is `review`'),
);
test(
  'Code Review uses a ticket plan baseline including untracked files',
  review.includes('baseline_revision') && review.includes('git diff --no-index /dev/null <path>') && review.includes('find.plan'),
);
test(
  'Code Review routes planless tracker tickets to no-plan mode instead of halting',
  review.includes('may not exist yet') &&
    review.includes('set `{review_mode}` = `"no-plan"` directly') &&
    review.includes("already `\"no-plan\"` from Tier 2's planless-ticket case"),
);
test(
  'Code Review does not mutate status for ticket cases',
  present.includes('Never run `tickets.py mark` or edit sprint status for a ticket review') &&
    present.includes('Skip this entire section when `{ticket_args}` is set'),
);
const retro = read('src/bmm-skills/ship/bmad-retrospective/bmad-retrospective.template.md');
const evidence = read('src/bmm-skills/ship/bmad-retrospective/references/evidence-gathering.md');
const verdict = read('src/bmm-skills/ship/bmad-retrospective/references/acceptance-verdict.md');
const document = read('src/bmm-skills/ship/bmad-retrospective/references/retro-document.md');
test(
  'Retrospective resolves ticket-tree epics through uv-run shared status evidence',
  retro.includes('uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} status') &&
    evidence.includes('uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} find <epic_folder> <ref>') &&
    !retro.includes('python3 {project-root}/_bmad/method/scripts/tickets.py') &&
    !evidence.includes('python3 {project-root}/_bmad/method/scripts/tickets.py'),
);
test(
  'Retrospective applies built done dropped completeness semantics',
  evidence.includes('`status` is `built` or `state` is `done` or `dropped`') &&
    verdict.includes('`built` and whose `state` is neither `done` nor `dropped`'),
);
test(
  'Retrospective writes only its ticket-tree artifact',
  document.includes('{epic_folder}/{epic_folder_basename}-retrospective.md') && document.includes('Do not run `tickets.py mark`'),
);
if (failures.length) process.exit(1);
