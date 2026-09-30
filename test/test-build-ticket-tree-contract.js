/** Ticket-tree consumer contract for the compiler-fork Build skills. */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const yaml = require('yaml');
const root = path.resolve(__dirname, '..');
const failures = [];
const read = (p) => fs.readFileSync(path.join(root, p), 'utf8');
const test = (name, condition) => {
  if (condition) console.log(`✓ ${name}`);
  else {
    console.error(`✗ ${name}`);
    failures.push(name);
  }
};
const frontmatter = (content) => yaml.parse(content.slice(4, content.indexOf('\n---\n', 4)));
for (const skill of ['bmad-build', 'bmad-build-auto']) {
  const prefix = `src/bmm-skills/ship/${skill}`;
  const rootTemplate = read(`${prefix}/${skill}.template.md`);
  const artifacts = frontmatter(rootTemplate).artifacts || [];
  test(
    `${skill} emits the plan template`,
    artifacts.some((a) => a.path === 'plan-template.md'),
  );
  const plan = read(`${prefix}/plan-template.md`);
  const planStep = read(`${prefix}/${skill === 'bmad-build' ? 'step-02-plan.template.md' : 'step-02-plan.md'}`);
  test(`${skill} plan carries ticket identity and built lifecycle`, plan.includes("ticket: ''") && plan.includes('built'));
  test(
    `${skill} writes resolved ticket identity from find output`,
    plan.includes('find.id') &&
      plan.includes('find.story_file') &&
      plan.includes('never find.ref') &&
      planStep.includes('set its `ticket` frontmatter from `find.id`') &&
      planStep.includes('the stem of `find.story_file`') &&
      planStep.includes('never use `find.ref`'),
  );
}
const buildRoute = read('src/bmm-skills/ship/bmad-build/step-01-clarify-and-route.template.md');
test(
  'Build resolves and starts ticket tree entries through uv-run shared tickets.py',
  buildRoute.includes('uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} find') &&
    buildRoute.includes('uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} next') &&
    !buildRoute.includes('python3 {project-root}/_bmad/method/scripts/tickets.py') &&
    buildRoute.includes('find.plan'),
);
test(
  'Build keeps legacy fallback conditional instead of dual-reading ticket state',
  buildRoute.includes('Legacy fallback only when no tree route resolved'),
);
const autoRoute = read('src/bmm-skills/ship/bmad-build-auto/step-01-clarify-and-route.md');
const autoRoot = read('src/bmm-skills/ship/bmad-build-auto/bmad-build-auto.template.md');
const autoReview = read('src/bmm-skills/ship/bmad-build-auto/step-04-review.md');
test(
  'Build Auto resolves tickets through uv-run shared tickets.py',
  autoRoute.includes('uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} find') &&
    !autoRoute.includes('python3 {project-root}/_bmad/method/scripts/tickets.py') &&
    autoRoot.includes('uv run {project-root}/_bmad/method/scripts/tickets.py --project-root {project-root} mark') &&
    autoRoute.includes('find.plan'),
);
test(
  'Build Auto blocks tickets through explicit runtime mark',
  autoRoot.includes('tickets.py --project-root {project-root} mark {ticket_args} blocked'),
);
test(
  'Build Auto finishes ticket plans at built, not done',
  autoReview.includes('status: built') &&
    autoReview.includes('HALT with status `built`') &&
    autoReview.includes('never advances itself to `done`'),
);
if (failures.length) process.exit(1);
