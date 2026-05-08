/**
 * validate-compile — recompile every migrated skill, diff against bmad.lock, run schema validation.
 *
 * For each entry in src/_bmad/_config/bmad.lock:
 *   1. Reconstruct the skill source directory from fragments[0].path (Dev Note §1).
 *   2. Compile via `compile.py --skill <src> --install-dir <tmp>`.
 *   3. SHA-256 the compiled SKILL.md bytes; compare against entry.compiled_hash.
 *   4. Run validateSkill() from validate-skills.js on the compiled output (Story 7.1 OQ-3 Option A).
 * Exit 0 iff every skill matched on hash AND passed schema. Exit 1 on any divergence or schema failure.
 *
 * Lock-file regeneration (when a template change is intentional):
 *   python3 src/scripts/compile.py --skill src/core-skills/<skill> --install-dir src/_bmad
 * (npm run bmad:install does NOT update src/_bmad/_config/bmad.lock — it writes to <projectRoot>/_bmad/.)
 *
 * Usage:
 *   node tools/validate-compile.js
 *   node tools/validate-compile.js --strict   (alias — default behavior; reserved for parity with validate:skills)
 *   node tools/validate-compile.js --json
 */

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

const { validateSkill } = require('./validate-skills');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const LOCK_PATH = path.join(PROJECT_ROOT, 'src', '_bmad', '_config', 'bmad.lock');
const COMPILE_PY = path.join(PROJECT_ROOT, 'src', 'scripts', 'compile.py');
const SRC_PREFIX = 'src';

const args = process.argv.slice(2);
const JSON_OUTPUT = args.includes('--json');

function escapeAnnotation(str) {
  return String(str).replaceAll('%', '%25').replaceAll('\r', '%0D').replaceAll('\n', '%0A');
}

function reconstructSkillSrcDir(entry) {
  const fragments = entry.fragments;
  if (!Array.isArray(fragments) || fragments.length === 0) {
    throw new Error(`bmad.lock entry for skill "${entry.skill}" has no fragments[]; cannot reconstruct source directory.`);
  }
  const fragPath = fragments[0].path;
  if (typeof fragPath !== 'string' || fragPath === '') {
    throw new Error(`bmad.lock entry for skill "${entry.skill}" has empty fragments[0].path.`);
  }
  const segments = fragPath.split('/');
  // DN-R2-2 (Phil Option B 2026-05-08): defensive assertion — bmad.lock fragments[i].path
  // is documented as src-relative (e.g. "core-skills/foo/fragments/x.md"). A leading "src"
  // segment is a lockfile-corruption signal that would otherwise produce a path-doubled
  // resolution (`<root>/src/src/...`) which the BH-3 traversal check still passes.
  if (segments[0] === 'src') {
    throw new Error(
      `bmad.lock entry for skill "${entry.skill}": fragments[0].path "${fragPath}" must be src-relative (no leading "src" segment).`,
    );
  }
  // Find the FIRST segment exactly equal to "fragments" (per Dev Note §1 — avoids
  // false-matching a hypothetical skill named "fragments-helper").
  const fragIdx = segments.indexOf('fragments');
  if (fragIdx === -1) {
    throw new Error(`bmad.lock entry for skill "${entry.skill}": fragment path "${fragPath}" does not contain a "fragments" segment.`);
  }
  if (fragIdx === 0) {
    // ECH-3: distinguish "no fragments segment" from "no skill-name prefix before fragments".
    throw new Error(
      `bmad.lock entry for skill "${entry.skill}": fragment path "${fragPath}" has no skill-name segment before the "fragments" marker (expected: <module>/<skill>/fragments/<file>).`,
    );
  }
  const resolved = path.join(PROJECT_ROOT, SRC_PREFIX, ...segments.slice(0, fragIdx));
  // BH-3: defense-in-depth against tampered bmad.lock with `..` segments. Reject any
  // path that escapes <PROJECT_ROOT>/src/.
  const srcRoot = path.join(PROJECT_ROOT, SRC_PREFIX);
  if (resolved !== srcRoot && !resolved.startsWith(srcRoot + path.sep)) {
    throw new Error(`bmad.lock entry for skill "${entry.skill}": fragment path "${fragPath}" escapes src/ (resolved to "${resolved}").`);
  }
  return resolved;
}

function sha256OfFile(filePath) {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function runCompile(skillSrcDir, tmpDir) {
  const pythonBin = process.platform === 'win32' ? 'python' : 'python3';
  // BH-1: 30s timeout — a hung compile.py should fail fast rather than burning the CI runner timeout.
  const result = spawnSync(pythonBin, [COMPILE_PY, '--skill', skillSrcDir, '--install-dir', tmpDir], {
    encoding: 'utf8',
    timeout: 30_000,
  });
  return result;
}

function validateOne(entry) {
  const skill = entry.skill;
  const skillSrcDir = reconstructSkillSrcDir(entry);
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'bmad-validate-'));

  try {
    const compileResult = runCompile(skillSrcDir, tmpDir);
    // BH-2/ECH-2: surface spawn-failure (ENOENT, EACCES, ETIMEDOUT) before status check.
    // When the process never ran or was killed mid-flight, status is null and stderr is empty;
    // without this branch the operator sees a confusing "(no output)" instead of the real cause.
    if (compileResult.error) {
      const errCode = compileResult.error.code || 'spawn-error';
      return {
        skill,
        skillSrcDir,
        status: 'compile-error',
        expected: entry.compiled_hash,
        actual: null,
        compileStderr: `${errCode}: ${compileResult.error.message}`,
        compileStdout: '',
        schemaFindings: [],
      };
    }
    if (compileResult.status !== 0) {
      return {
        skill,
        skillSrcDir,
        status: 'compile-error',
        expected: entry.compiled_hash,
        actual: null,
        compileStderr: (compileResult.stderr || '').trim(),
        compileStdout: (compileResult.stdout || '').trim(),
        schemaFindings: [],
      };
    }

    // Per-skill mode (no lockfile_root): engine writes to <install_dir>/<basename>/SKILL.md.
    // The basename is the skill source dir's last segment.
    const skillBasename = path.basename(skillSrcDir);
    const compiledSkillDir = path.join(tmpDir, skillBasename);
    const compiledSkillMd = path.join(compiledSkillDir, 'SKILL.md');
    if (!fs.existsSync(compiledSkillMd)) {
      return {
        skill,
        skillSrcDir,
        status: 'output-missing',
        expected: entry.compiled_hash,
        actual: null,
        compileStderr: (compileResult.stderr || '').trim(),
        compileStdout: (compileResult.stdout || '').trim(),
        schemaFindings: [],
      };
    }

    const actual = sha256OfFile(compiledSkillMd);
    const hashMatch = actual === entry.compiled_hash;

    // OQ-3 Option A: schema-validate the compiled output regardless of hash result.
    const schemaFindings = validateSkill(compiledSkillDir);
    // DN-R1-1=A (Phil 2026-05-08): only CRITICAL and HIGH block the build. MEDIUM and LOW
    // are informational, mirroring the `validate:skills --strict` contract.
    const schemaFailures = schemaFindings.filter((f) => f.severity === 'CRITICAL' || f.severity === 'HIGH');

    let status;
    if (!hashMatch && schemaFailures.length > 0) {
      status = 'hash-and-schema-fail';
    } else if (!hashMatch) {
      status = 'hash-mismatch';
    } else if (schemaFailures.length > 0) {
      status = 'schema-fail';
    } else {
      status = 'pass';
    }

    return {
      skill,
      skillSrcDir,
      status,
      expected: entry.compiled_hash,
      actual,
      schemaFindings: schemaFailures,
    };
  } finally {
    // BH-4/ECH-4: don't let cleanup failures (Windows file locks, etc.) clobber the
    // validation result. force:true was previously suppressing real I/O errors AND a raw
    // throw inside finally would propagate out of validateOne, replacing the computed record.
    try {
      fs.rmSync(tmpDir, { recursive: true });
    } catch (cleanupError) {
      process.stderr.write(`warn: could not remove tmp dir ${tmpDir}: ${cleanupError.message}\n`);
    }
  }
}

function emitAnnotation(record) {
  if (!process.env.GITHUB_ACTIONS) return;
  const skill = record.skill;
  // Annotate against the template file when possible — that's the source of truth a developer edits.
  // record.skillSrcDir is absolute and already rooted under <PROJECT_ROOT>/src, so a single
  // path.relative() yields the repo-root-relative path; do not re-prepend "src/".
  // ECH-5: normalize backslashes on win32 BEFORE joining the template name — GitHub silently
  // drops annotations whose file= attribute contains backslashes.
  const skillRel = record.skillSrcDir ? path.relative(PROJECT_ROOT, record.skillSrcDir).split(path.sep).join('/') : 'src';
  const file = `${skillRel}/${path.basename(skillRel)}.template.md`;
  if (record.status === 'hash-mismatch' || record.status === 'hash-and-schema-fail') {
    const msg = `COMPILE_HASH_MISMATCH skill=${skill} expected=${record.expected} actual=${record.actual}`;
    console.log(`::error file=${file},line=1::${escapeAnnotation(msg)}`);
  }
  if (record.status === 'compile-error') {
    const msg = `COMPILE_ERROR skill=${skill}: ${record.compileStderr || record.compileStdout || '(no output)'}`;
    console.log(`::error file=${file},line=1::${escapeAnnotation(msg)}`);
  }
  if (record.status === 'output-missing') {
    const msg = `COMPILE_OUTPUT_MISSING skill=${skill}: compile.py exited 0 but SKILL.md was not produced`;
    console.log(`::error file=${file},line=1::${escapeAnnotation(msg)}`);
  }
  for (const f of record.schemaFindings) {
    const msg = `SCHEMA_FAIL skill=${skill} ${f.rule}: ${f.detail}`;
    console.log(`::error file=${file},line=1::${escapeAnnotation(msg)}`);
  }
}

function reportHuman(records) {
  const failures = records.filter((r) => r.status !== 'pass');
  console.log('');
  console.log(`validate-compile — ${records.length} skill(s) processed`);
  console.log('');

  for (const r of records) {
    if (r.status === 'pass') {
      console.log(`PASS  ${r.skill}  ${r.actual}`);
      continue;
    }
    console.log(`FAIL  ${r.skill}  [${r.status}]`);
    if (r.status === 'hash-mismatch' || r.status === 'hash-and-schema-fail') {
      console.log(`      expected: ${r.expected}`);
      console.log(`      actual:   ${r.actual}`);
    }
    if (r.status === 'compile-error') {
      console.log(`      compile.py exit non-zero`);
      if (r.compileStderr) console.log(`      stderr: ${r.compileStderr.split('\n').slice(0, 5).join('\n              ')}`);
    }
    if (r.status === 'output-missing') {
      console.log(`      compile.py exited 0 but produced no SKILL.md at expected path`);
    }
    for (const f of r.schemaFindings) {
      console.log(`      [${f.severity}] ${f.rule}: ${f.detail}`);
    }
  }

  console.log('');
  if (failures.length === 0) {
    console.log('All compile hashes match and compiled SKILL.md outputs pass schema.');
  } else {
    console.log(`${failures.length} of ${records.length} skill(s) failed validate-compile.`);
  }
}

function reportJson(records, exitCode) {
  // Relativize skillSrcDir for portability across machines.
  const portable = records.map((r) => ({
    ...r,
    skillSrcDir: r.skillSrcDir ? path.relative(PROJECT_ROOT, r.skillSrcDir).split(path.sep).join('/') : null,
  }));
  console.log(JSON.stringify({ exit_code: exitCode, skills: portable }, null, 2));
}

function main() {
  if (!fs.existsSync(LOCK_PATH)) {
    const msg = `bmad.lock not found at ${path.relative(PROJECT_ROOT, LOCK_PATH)}`;
    if (JSON_OUTPUT) {
      console.log(JSON.stringify({ exit_code: 1, error: msg, skills: [] }, null, 2));
    } else {
      console.error(msg);
    }
    process.exit(1);
  }

  let lock;
  try {
    // ECH-1: strip a UTF-8 BOM if present — common on Windows-edited files; otherwise
    // JSON.parse rejects with a cryptic "Unexpected token" error.
    // DN-R2-5 (Phil Option A 2026-05-08): bmad.lock contract is UTF-8. The Python compiler
    // emits via `json.dumps(..., sort_keys=True, indent=2)` + UTF-8 file write; a UTF-16 BOM
    // would only appear if the file was hand-edited with a non-default encoding — out of
    // scope for this validator. UTF-16 BOM detection deferred (R2-BH-6).
    const raw = fs.readFileSync(LOCK_PATH, 'utf8').replace(/^\uFEFF/, '');
    lock = JSON.parse(raw);
  } catch (error) {
    console.error(`Failed to parse bmad.lock: ${error.message}`);
    process.exit(1);
  }

  const entries = Array.isArray(lock.entries) ? lock.entries : [];
  if (entries.length === 0) {
    if (JSON_OUTPUT) {
      console.log(JSON.stringify({ exit_code: 0, skills: [] }, null, 2));
    } else {
      console.log('validate-compile — bmad.lock has zero entries; nothing to verify.');
    }
    process.exit(0);
  }

  const records = [];
  for (const entry of entries) {
    let record;
    try {
      record = validateOne(entry);
    } catch (error) {
      record = {
        skill: entry.skill || '<unknown>',
        skillSrcDir: null,
        status: 'internal-error',
        expected: entry.compiled_hash || null,
        actual: null,
        error: error.message,
        schemaFindings: [],
      };
    }
    records.push(record);
    emitAnnotation(record);
  }

  const failed = records.some((r) => r.status !== 'pass');
  const exitCode = failed ? 1 : 0;

  if (JSON_OUTPUT) {
    reportJson(records, exitCode);
  } else {
    reportHuman(records);
  }
  process.exit(exitCode);
}

if (require.main === module) {
  main();
}

module.exports = { reconstructSkillSrcDir, sha256OfFile, validateOne };
