/** Site URL resolver regression tests. */
import assert from 'node:assert/strict';
import { getSiteUrl } from '../website/src/lib/site-url.mjs';

const originalSiteUrl = process.env.SITE_URL;
const originalRepository = process.env.GITHUB_REPOSITORY;
const tests = [];
const test = (name, run) => tests.push({ name, run });

function setEnvironment(siteUrl, repository) {
  if (siteUrl === undefined) delete process.env.SITE_URL;
  else process.env.SITE_URL = siteUrl;
  if (repository === undefined) delete process.env.GITHUB_REPOSITORY;
  else process.env.GITHUB_REPOSITORY = repository;
}

test('normalizes trailing slashes from a site override', () => {
  setEnvironment('https://example.github.io/team/repo///', undefined);
  assert.equal(getSiteUrl(), 'https://example.github.io/team/repo');
});
test('prefers a normalized SITE_URL over GitHub fallback', () => {
  setEnvironment('https://docs.example/', 'ignored/repository');
  assert.equal(getSiteUrl(), 'https://docs.example');
});
test('uses the GitHub Pages fallback when SITE_URL is empty', () => {
  setEnvironment('', 'owner/repository');
  assert.equal(getSiteUrl(), 'https://owner.github.io/repository');
});
test('rejects malformed repository fallback', () => {
  setEnvironment('', 'malformed');
  assert.throws(() => getSiteUrl(), /Invalid GITHUB_REPOSITORY format/);
});

let failures = 0;
try {
  for (const { name, run } of tests) {
    try {
      run();
      console.log(`✓ ${name}`);
    } catch (error) {
      failures++;
      console.error(`✗ ${name}: ${error.message}`);
    }
  }
} finally {
  setEnvironment(originalSiteUrl, originalRepository);
}
if (failures) process.exit(1);
