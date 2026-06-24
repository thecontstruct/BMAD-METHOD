/**
 * Deterministic Skill Validator
 *
 * Validates 12 deterministic rules across all skill directories.
 * Acts as a fast first-pass complement to the inference-based skill validator.
 *
 * What it checks:
 * - SKILL-01: SKILL.md exists
 * - SKILL-02: SKILL.md frontmatter has name
 * - SKILL-03: SKILL.md frontmatter has description
 * - SKILL-04: name format (lowercase, hyphens, no forbidden substrings)
 * - SKILL-05: name matches directory basename
 * - SKILL-06: description quality (length, "Use when"/"Use if")
 * - SKILL-07: SKILL.md has body content after frontmatter
 * - PATH-02: no installed_path variable
 * - STEP-01: step filename format
 * - STEP-06: step frontmatter has no name/description
 * - STEP-07: step count 2-10
 * - SEQ-02: no time estimates
 * - TPL-01: template files must not contain compile-time {{.var}} substitutions
 * - TPL-02: component lint — JIT sentinels, render function presence, RENDER_ERROR_FALLBACK form
 *
 * Usage:
 *   node tools/validate-skills.js                    # All skills, human-readable
 *   node tools/validate-skills.js path/to/skill-dir  # Single skill
 *   node tools/validate-skills.js --strict           # Exit 1 on HIGH+ findings
 *   node tools/validate-skills.js --json             # JSON output
 */

const fs = require('node:fs');
const path = require('node:path');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const SRC_DIR = path.join(PROJECT_ROOT, 'src');

// --- CLI Parsing ---

const args = process.argv.slice(2);
const STRICT = args.includes('--strict');
const JSON_OUTPUT = args.includes('--json');
const positionalArgs = args.filter((a) => !a.startsWith('--'));

// --- Constants ---

const NAME_REGEX = /^bmad-[a-z0-9]+(-[a-z0-9]+)*$/;
const STEP_FILENAME_REGEX = /^step-\d{2}[a-z]?-[a-z0-9-]+\.md$/;
const TIME_ESTIMATE_PATTERNS = [/takes?\s+\d+\s*min/i, /~\s*\d+\s*min/i, /estimated\s+time/i, /\bETA\b/];
const TEMPLATE_FILENAME_REGEX = /template/i;
const COMPILE_TIME_SUB_REGEX = /\{\{\.\w+\}\}/;

const LOCKFILE_PATH = path.join(PROJECT_ROOT, '_bmad', '_config', 'bmad.lock');
const JIT_SENTINEL_PREFIX = '<!-- BMAD-JIT:';
// Non-global: used for per-line well-formedness test in AC-3
const JIT_SENTINEL_FULL_RE = /<!--\s*BMAD-JIT:([A-Z][A-Za-z0-9]+):([0-9a-f]{16})\s*-->/;
// Global: used to extract all well-formed sentinels from SKILL.md for AC-4
const JIT_SENTINEL_FULL_RE_GLOBAL = /<!--\s*BMAD-JIT:([A-Z][A-Za-z0-9]+):([0-9a-f]{16})\s*-->/g;
const DEF_RENDER_RE = /def render\s*\(/;
const FALLBACK_MULTILINE_RE = /^RENDER_ERROR_FALLBACK\s*=\s*("""|''')/m;
const FALLBACK_SINGLE_LINE_RE = /^RENDER_ERROR_FALLBACK\s*=\s*["'].*["']/m;

const SEVERITY_ORDER = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };

// --- Output Escaping ---

function escapeAnnotation(str) {
  return str.replaceAll('%', '%25').replaceAll('\r', '%0D').replaceAll('\n', '%0A');
}

function escapeTableCell(str) {
  return String(str).replaceAll('|', String.raw`\|`);
}

// --- Frontmatter Parsing ---

/**
 * Parse YAML frontmatter from a markdown file.
 * Returns an object with key-value pairs, or null if no frontmatter.
 */
function parseFrontmatter(content) {
  const trimmed = content.trimStart();
  if (!trimmed.startsWith('---')) return null;

  let endIndex = trimmed.indexOf('\n---\n', 3);
  if (endIndex === -1) {
    // Handle file ending with \n---
    if (trimmed.endsWith('\n---')) {
      endIndex = trimmed.length - 4;
    } else {
      return null;
    }
  }

  const fmBlock = trimmed.slice(3, endIndex).trim();
  if (fmBlock === '') return {};

  const result = {};
  for (const line of fmBlock.split('\n')) {
    const colonIndex = line.indexOf(':');
    if (colonIndex === -1) continue;
    // Skip indented lines (nested YAML values)
    if (line[0] === ' ' || line[0] === '\t') continue;
    const key = line.slice(0, colonIndex).trim();
    let value = line.slice(colonIndex + 1).trim();
    // Strip surrounding quotes (single or double)
    if ((value.startsWith("'") && value.endsWith("'")) || (value.startsWith('"') && value.endsWith('"'))) {
      value = value.slice(1, -1);
    }
    result[key] = value;
  }

  return result;
}

/**
 * Parse YAML frontmatter, handling multiline values (description often spans lines).
 * Returns an object with key-value pairs, or null if no frontmatter.
 */
function parseFrontmatterMultiline(content) {
  const trimmed = content.trimStart();
  if (!trimmed.startsWith('---')) return null;

  let endIndex = trimmed.indexOf('\n---\n', 3);
  if (endIndex === -1) {
    // Handle file ending with \n---
    if (trimmed.endsWith('\n---')) {
      endIndex = trimmed.length - 4;
    } else {
      return null;
    }
  }

  const fmBlock = trimmed.slice(3, endIndex).trim();
  if (fmBlock === '') return {};

  const result = {};
  let currentKey = null;
  let currentValue = '';

  for (const line of fmBlock.split('\n')) {
    const colonIndex = line.indexOf(':');
    // New key-value pair: must start at column 0 (no leading whitespace) and have a colon
    if (colonIndex > 0 && line[0] !== ' ' && line[0] !== '\t') {
      // Save previous key
      if (currentKey !== null) {
        result[currentKey] = stripQuotes(currentValue.trim());
      }
      currentKey = line.slice(0, colonIndex).trim();
      currentValue = line.slice(colonIndex + 1);
    } else if (currentKey !== null) {
      // Skip YAML comment lines
      if (line.trimStart().startsWith('#')) continue;
      // Continuation of multiline value
      currentValue += '\n' + line;
    }
  }

  // Save last key
  if (currentKey !== null) {
    result[currentKey] = stripQuotes(currentValue.trim());
  }

  return result;
}

function stripQuotes(value) {
  if ((value.startsWith("'") && value.endsWith("'")) || (value.startsWith('"') && value.endsWith('"'))) {
    return value.slice(1, -1);
  }
  return value;
}

// --- Safe File Reading ---

/**
 * Read a file safely, returning null on error.
 * Pushes a warning finding if the file cannot be read.
 */
function safeReadFile(filePath, findings, relFile) {
  try {
    return fs.readFileSync(filePath, 'utf-8');
  } catch (error) {
    findings.push({
      rule: 'READ-ERR',
      title: 'File Read Error',
      severity: 'MEDIUM',
      file: relFile || path.basename(filePath),
      detail: `Cannot read file: ${error.message}`,
      fix: 'Check file permissions and ensure the file exists.',
    });
    return null;
  }
}

// --- Code Block Stripping ---

function stripCodeBlocks(content) {
  return content.replaceAll(/```[\s\S]*?```/g, (m) => m.replaceAll(/[^\n]/g, ''));
}

// --- Skill Discovery ---

function discoverSkillDirs(rootDirs) {
  const skillDirs = [];

  function walk(dir) {
    if (!fs.existsSync(dir)) return;
    const entries = fs.readdirSync(dir, { withFileTypes: true });

    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      if (entry.name === 'node_modules' || entry.name === '.git') continue;

      const fullPath = path.join(dir, entry.name);
      const skillMd = path.join(fullPath, 'SKILL.md');

      if (fs.existsSync(skillMd)) {
        skillDirs.push(fullPath);
      }

      // Keep walking into subdirectories to find nested skills
      walk(fullPath);
    }
  }

  for (const rootDir of rootDirs) {
    walk(rootDir);
  }

  return skillDirs.sort();
}

// --- File Collection ---

function collectSkillFiles(skillDir) {
  const files = [];

  function walk(dir) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.name === 'node_modules' || entry.name === '.git') continue;
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(fullPath);
      } else if (entry.isFile()) {
        files.push(fullPath);
      }
    }
  }

  walk(skillDir);
  return files;
}

// --- Lockfile Helper ---

/**
 * Read lockfile components[] for a named skill from the global lockfile.
 * Returns null if the lockfile is absent, v1, or has no entry for this skill.
 */
function readLockfileComponents(skillName) {
  if (!fs.existsSync(LOCKFILE_PATH)) return null;
  let data;
  try {
    data = JSON.parse(fs.readFileSync(LOCKFILE_PATH, 'utf-8'));
  } catch {
    return null;
  }
  if (!data || typeof data.version !== 'number' || data.version < 2) return null;
  const entry = (data.entries || []).find((e) => e.skill === skillName);
  if (!entry || !Array.isArray(entry.components)) return null;
  return entry.components;
}

// --- Rule Checks ---

function validateSkill(skillDir, _testComponents) {
  const findings = [];
  const dirName = path.basename(skillDir);
  const skillMdPath = path.join(skillDir, 'SKILL.md');
  const workflowMdPath = path.join(skillDir, 'workflow.md');
  const stepsDir = path.join(skillDir, 'steps');

  // Collect all files in the skill for PATH-02 and SEQ-02
  const allFiles = collectSkillFiles(skillDir);

  // --- SKILL-01: SKILL.md must exist ---
  if (!fs.existsSync(skillMdPath)) {
    findings.push({
      rule: 'SKILL-01',
      title: 'SKILL.md Must Exist',
      severity: 'CRITICAL',
      file: 'SKILL.md',
      detail: 'SKILL.md not found in skill directory.',
      fix: 'Create SKILL.md as the skill entrypoint.',
    });
    // Cannot check SKILL-02 through SKILL-07 without SKILL.md
    return findings;
  }

  const skillContent = safeReadFile(skillMdPath, findings, 'SKILL.md');
  if (skillContent === null) return findings;
  const skillFm = parseFrontmatterMultiline(skillContent);

  // --- SKILL-02: frontmatter has name ---
  if (!skillFm || !('name' in skillFm)) {
    findings.push({
      rule: 'SKILL-02',
      title: 'SKILL.md Must Have name in Frontmatter',
      severity: 'CRITICAL',
      file: 'SKILL.md',
      detail: 'Frontmatter is missing the `name` field.',
      fix: 'Add `name: <skill-name>` to the frontmatter.',
    });
  } else if (skillFm.name === '') {
    findings.push({
      rule: 'SKILL-02',
      title: 'SKILL.md Must Have name in Frontmatter',
      severity: 'CRITICAL',
      file: 'SKILL.md',
      detail: 'Frontmatter `name` field is empty.',
      fix: 'Set `name` to the skill directory name (kebab-case).',
    });
  }

  // --- SKILL-03: frontmatter has description ---
  if (!skillFm || !('description' in skillFm)) {
    findings.push({
      rule: 'SKILL-03',
      title: 'SKILL.md Must Have description in Frontmatter',
      severity: 'CRITICAL',
      file: 'SKILL.md',
      detail: 'Frontmatter is missing the `description` field.',
      fix: 'Add `description: <what it does and when to use it>` to the frontmatter.',
    });
  } else if (skillFm.description === '') {
    findings.push({
      rule: 'SKILL-03',
      title: 'SKILL.md Must Have description in Frontmatter',
      severity: 'CRITICAL',
      file: 'SKILL.md',
      detail: 'Frontmatter `description` field is empty.',
      fix: 'Add a description stating what the skill does and when to use it.',
    });
  }

  const name = skillFm && skillFm.name;
  const description = skillFm && skillFm.description;

  // Deprecated skills are thin compatibility shims that forward to a replacement.
  // They intentionally omit a "Use when" trigger so users are steered to the new
  // skill instead, so exempt them from the SKILL-06 trigger-phrase requirement.
  const isDeprecated = typeof description === 'string' && /^\s*deprecated\b/i.test(description);

  // --- SKILL-04: name format ---
  if (name && !NAME_REGEX.test(name)) {
    findings.push({
      rule: 'SKILL-04',
      title: 'name Format',
      severity: 'HIGH',
      file: 'SKILL.md',
      detail: `name "${name}" does not match pattern: ${NAME_REGEX}`,
      fix: 'Rename to comply with lowercase letters, numbers, and hyphens only (max 64 chars).',
    });
  }

  // --- SKILL-05: name matches directory ---
  if (name && name !== dirName) {
    findings.push({
      rule: 'SKILL-05',
      title: 'name Must Match Directory Name',
      severity: 'HIGH',
      file: 'SKILL.md',
      detail: `name "${name}" does not match directory name "${dirName}".`,
      fix: `Change name to "${dirName}" or rename the directory.`,
    });
  }

  // --- SKILL-06: description quality ---
  if (description) {
    if (description.length > 1024) {
      findings.push({
        rule: 'SKILL-06',
        title: 'description Quality',
        severity: 'MEDIUM',
        file: 'SKILL.md',
        detail: `description is ${description.length} characters (max 1024).`,
        fix: 'Shorten the description to 1024 characters or less.',
      });
    }

    if (!isDeprecated && !/use\s+when\b/i.test(description) && !/use\s+if\b/i.test(description)) {
      findings.push({
        rule: 'SKILL-06',
        title: 'description Quality',
        severity: 'MEDIUM',
        file: 'SKILL.md',
        detail: 'description does not contain "Use when" or "Use if" trigger phrase.',
        fix: 'Append a "Use when..." clause to explain when to invoke this skill.',
      });
    }
  }

  // --- SKILL-07: SKILL.md must have body content after frontmatter ---
  {
    const trimmed = skillContent.trimStart();
    let bodyStart = -1;
    if (trimmed.startsWith('---')) {
      let endIdx = trimmed.indexOf('\n---\n', 3);
      if (endIdx !== -1) {
        bodyStart = endIdx + 4;
      } else if (trimmed.endsWith('\n---')) {
        bodyStart = trimmed.length; // no body at all
      }
    } else {
      bodyStart = 0; // no frontmatter, entire file is body
    }
    const body = bodyStart >= 0 ? trimmed.slice(bodyStart).trim() : '';
    if (body === '') {
      findings.push({
        rule: 'SKILL-07',
        title: 'SKILL.md Must Have Body Content',
        severity: 'HIGH',
        file: 'SKILL.md',
        detail: 'SKILL.md has no content after frontmatter. L2 instructions are required.',
        fix: 'Add markdown body with skill instructions after the closing ---.',
      });
    }
  }

  // --- PATH-02: no installed_path ---
  for (const filePath of allFiles) {
    // Only check markdown and yaml files
    const ext = path.extname(filePath);
    if (!['.md', '.yaml', '.yml'].includes(ext)) continue;

    const relFile = path.relative(skillDir, filePath);
    const content = safeReadFile(filePath, findings, relFile);
    if (content === null) continue;

    // Check frontmatter for installed_path key
    const fm = parseFrontmatter(content);
    if (fm && 'installed_path' in fm) {
      findings.push({
        rule: 'PATH-02',
        title: 'No installed_path Variable',
        severity: 'HIGH',
        file: relFile,
        detail: 'Frontmatter contains `installed_path:` key.',
        fix: 'Remove `installed_path` from frontmatter. Use relative paths instead.',
      });
    }

    // Check content for any mention of installed_path (variable ref, prose, bare text)
    const stripped = stripCodeBlocks(content);
    const lines = stripped.split('\n');
    for (const [i, line] of lines.entries()) {
      if (/installed_path/i.test(line)) {
        findings.push({
          rule: 'PATH-02',
          title: 'No installed_path Variable',
          severity: 'HIGH',
          file: relFile,
          line: i + 1,
          detail: '`installed_path` reference found in content.',
          fix: 'Remove all installed_path usage. Use relative paths (`./path` or `../path`) instead.',
        });
      }
    }
  }

  // --- STEP-01: step filename format ---
  // --- STEP-06: step frontmatter no name/description ---
  // --- STEP-07: step count ---
  // Only check the literal steps/ directory (variant directories like steps-c, steps-v
  // use different naming conventions and are excluded per the rule specification)
  if (fs.existsSync(stepsDir) && fs.statSync(stepsDir).isDirectory()) {
    const stepDirName = 'steps';
    const stepFiles = fs.readdirSync(stepsDir).filter((f) => f.endsWith('.md'));

    // STEP-01: filename format
    for (const stepFile of stepFiles) {
      if (!STEP_FILENAME_REGEX.test(stepFile)) {
        findings.push({
          rule: 'STEP-01',
          title: 'Step File Naming',
          severity: 'MEDIUM',
          file: path.join(stepDirName, stepFile),
          detail: `Filename "${stepFile}" does not match pattern: ${STEP_FILENAME_REGEX}`,
          fix: 'Rename to step-NN-description.md (NN = zero-padded number, optional letter suffix).',
        });
      }
    }

    // STEP-06: step frontmatter has no name/description
    for (const stepFile of stepFiles) {
      const stepPath = path.join(stepsDir, stepFile);
      const stepContent = safeReadFile(stepPath, findings, path.join(stepDirName, stepFile));
      if (stepContent === null) continue;
      const stepFm = parseFrontmatter(stepContent);

      if (stepFm) {
        if ('name' in stepFm) {
          findings.push({
            rule: 'STEP-06',
            title: 'Step File Frontmatter: No name or description',
            severity: 'MEDIUM',
            file: path.join(stepDirName, stepFile),
            detail: 'Step file frontmatter contains `name:` — this is metadata noise.',
            fix: 'Remove `name:` from step file frontmatter.',
          });
        }
        if ('description' in stepFm) {
          findings.push({
            rule: 'STEP-06',
            title: 'Step File Frontmatter: No name or description',
            severity: 'MEDIUM',
            file: path.join(stepDirName, stepFile),
            detail: 'Step file frontmatter contains `description:` — this is metadata noise.',
            fix: 'Remove `description:` from step file frontmatter.',
          });
        }
      }
    }

    // STEP-07: step count 2-10
    const stepCount = stepFiles.filter((f) => f.startsWith('step-')).length;
    if (stepCount > 0 && (stepCount < 2 || stepCount > 10)) {
      const detail =
        stepCount < 2
          ? `Only ${stepCount} step file found — consider inlining into workflow.md.`
          : `${stepCount} step files found — more than 10 risks LLM context degradation.`;
      findings.push({
        rule: 'STEP-07',
        title: 'Step Count',
        severity: 'LOW',
        file: stepDirName + '/',
        detail,
        fix: stepCount > 10 ? 'Consider consolidating steps.' : 'Consider expanding or inlining.',
      });
    }
  }

  // --- SEQ-02: no time estimates ---
  for (const filePath of allFiles) {
    const ext = path.extname(filePath);
    if (!['.md', '.yaml', '.yml'].includes(ext)) continue;

    const relFile = path.relative(skillDir, filePath);
    const content = safeReadFile(filePath, findings, relFile);
    if (content === null) continue;
    const stripped = stripCodeBlocks(content);
    const lines = stripped.split('\n');

    for (const [i, line] of lines.entries()) {
      for (const pattern of TIME_ESTIMATE_PATTERNS) {
        if (pattern.test(line)) {
          findings.push({
            rule: 'SEQ-02',
            title: 'No Time Estimates',
            severity: 'LOW',
            file: relFile,
            line: i + 1,
            detail: `Time estimate pattern found: "${line.trim()}"`,
            fix: 'Remove time estimates — AI execution speed varies too much.',
          });
          break; // Only report once per line
        }
      }
    }
  }

  // --- TPL-01: template files must not contain compile-time {{.var}} substitutions ---
  // Template files seed durable, version-controlled artifacts (spec files) that
  // execute on other machines. Baking a {{.var}} at render time would freeze a
  // machine-local value into every downstream artifact.
  for (const filePath of allFiles) {
    if (path.extname(filePath) !== '.md') continue;
    const base = path.basename(filePath);
    if (!TEMPLATE_FILENAME_REGEX.test(base)) continue;

    const relFile = path.relative(skillDir, filePath);
    const content = safeReadFile(filePath, findings, relFile);
    if (content === null) continue;

    const lines = content.split('\n');
    for (const [i, line] of lines.entries()) {
      const match = line.match(COMPILE_TIME_SUB_REGEX);
      if (match) {
        findings.push({
          rule: 'TPL-01',
          title: 'Template files must not contain compile-time substitutions',
          severity: 'HIGH',
          file: relFile,
          line: i + 1,
          detail: `Template file contains compile-time substitution \`${match[0]}\` — this would be baked at render time and leak a machine-local value into every spec produced from the template.`,
          fix: 'Remove the `{{.var}}` reference. Use single-curly `{var}` if the value should be resolved at LLM runtime by the consumer of the generated spec.',
        });
      }
    }
  }

  // --- TPL-02: component lint for JIT sentinels, render function, RENDER_ERROR_FALLBACK ---
  // TPL-01 catches unresolved template markers; TPL-02 catches component-level issues.
  // Fires only for skills with a non-empty components[] in the v2 lockfile.
  const _tpl02Components = _testComponents ?? readLockfileComponents(name);

  if (_tpl02Components !== null && _tpl02Components.length > 0) {
    const components = _tpl02Components;

    // --- AC-2: compile-only skill must have no JIT sentinels ---
    const allCompileMode = components.every((c) => c.render_mode === 'compile');
    if (allCompileMode && skillContent.includes(JIT_SENTINEL_PREFIX)) {
      findings.push({
        rule: 'TPL-02',
        title: 'Compile-only skill contains JIT sentinel',
        severity: 'HIGH',
        file: 'SKILL.md',
        detail:
          'All components are render_mode "compile" but SKILL.md contains a JIT sentinel. ' +
          'Either a component mode changed without recompiling, or SKILL.md was corrupted.',
        fix: 'Recompile the skill, or change the component render_mode to "jit" if JIT was intended.',
      });
    }

    // --- AC-3: malformed JIT sentinels ---
    const skillMdLines = skillContent.split('\n');
    for (const [i, line] of skillMdLines.entries()) {
      if (line.includes(JIT_SENTINEL_PREFIX) && !JIT_SENTINEL_FULL_RE.test(line)) {
        findings.push({
          rule: 'TPL-02',
          title: 'Malformed JIT sentinel in SKILL.md',
          severity: 'HIGH',
          file: 'SKILL.md',
          line: i + 1,
          detail:
            `JIT sentinel prefix found on line ${i + 1} but does not match expected format ` +
            "'<!-- BMAD-JIT:ComponentName:16hexchars -->'. Recompile to regenerate well-formed sentinels.",
          fix: 'Recompile the skill to regenerate SKILL.md with properly formatted sentinels.',
        });
      }
    }

    // --- AC-4: sentinel–lockfile alignment ---
    for (const match of skillContent.matchAll(JIT_SENTINEL_FULL_RE_GLOBAL)) {
      const [fullMatch, sentinelName, sentinelHash] = match;
      const hasEntry = components.some((c) => c.name === sentinelName && c.props_hash === sentinelHash);
      if (!hasEntry) {
        findings.push({
          rule: 'TPL-02',
          title: 'JIT sentinel has no matching lockfile entry',
          severity: 'MEDIUM',
          file: 'SKILL.md',
          detail:
            `Sentinel '${fullMatch}' has no matching component entry in the lockfile ` +
            '(name + props_hash mismatch). SKILL.md and lockfile are out of sync.',
          fix: 'Recompile the skill to regenerate SKILL.md and lockfile together.',
        });
      }
    }

    // --- AC-5: missing def render( + AC-6: RENDER_ERROR_FALLBACK for JIT components ---
    for (const entry of components) {
      const compRelPath = entry.path;
      const compAbsPath = path.join(skillDir, compRelPath);
      let compSource = null;

      if (!fs.existsSync(compAbsPath)) {
        findings.push({
          rule: 'TPL-02',
          title: 'Component missing def render( function',
          severity: 'HIGH',
          file: compRelPath,
          detail: `Component file not found: ${compRelPath}. Cannot verify render function or RENDER_ERROR_FALLBACK.`,
          fix: 'Ensure the component file exists at the expected path relative to the skill directory.',
        });
        continue;
      }

      compSource = safeReadFile(compAbsPath, findings, compRelPath);
      if (compSource === null) continue;

      // AC-5: def render( check
      // TPL-02 render-check is a regex scan; lambda and callable-class render patterns are
      // not supported — use def render() syntax.
      if (!DEF_RENDER_RE.test(compSource)) {
        findings.push({
          rule: 'TPL-02',
          title: 'Component missing def render( function',
          severity: 'HIGH',
          file: compRelPath,
          detail:
            `Component file does not contain 'def render(' — the BMAD compile engine will ` + 'reject this component at compile time.',
          fix: 'Add a def render(ctx, **props) -> str: function to the component.',
        });
      }

      // AC-6: RENDER_ERROR_FALLBACK form check (JIT only)
      if (entry.render_mode === 'jit') {
        if (FALLBACK_MULTILINE_RE.test(compSource)) {
          findings.push({
            rule: 'TPL-02',
            title: 'JIT component RENDER_ERROR_FALLBACK is not a single-line string literal',
            severity: 'MEDIUM',
            file: compRelPath,
            detail:
              "RENDER_ERROR_FALLBACK uses a triple-quoted or multi-line string. The wrapper's " +
              'pre-import regex matches only single-line string literals — this component will ' +
              'silently fall back to the system default error slot at JIT time.',
            fix: "Change to a single-line string: RENDER_ERROR_FALLBACK = 'a safe error message'",
          });
        } else if (FALLBACK_SINGLE_LINE_RE.test(compSource)) {
          // single-line string literal present — OK, no finding
        } else {
          findings.push({
            rule: 'TPL-02',
            title: 'JIT component missing RENDER_ERROR_FALLBACK',
            severity: 'HIGH',
            file: compRelPath,
            detail:
              'JIT-mode component does not define RENDER_ERROR_FALLBACK = "..." at module level. ' +
              'This is required (FR-6.2 SHALL) for all JIT components to provide a safe error slot.',
            fix: "Add RENDER_ERROR_FALLBACK = 'a safe error message' at module level.",
          });
        }
      }
    }
  }

  return findings;
}

// --- Output Formatting ---

function formatHumanReadable(results) {
  const output = [];
  let totalFindings = 0;
  const severityCounts = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };

  output.push(
    `\nValidating skills in: ${SRC_DIR}`,
    `Mode: ${STRICT ? 'STRICT (exit 1 on HIGH+)' : 'WARNING (exit 0)'}${JSON_OUTPUT ? ' + JSON' : ''}\n`,
  );

  let totalSkills = 0;
  let skillsWithFindings = 0;

  for (const { skillDir, findings } of results) {
    totalSkills++;
    const relDir = path.relative(PROJECT_ROOT, skillDir);

    if (findings.length > 0) {
      skillsWithFindings++;
      output.push(`\n${relDir}`);

      for (const f of findings) {
        totalFindings++;
        severityCounts[f.severity]++;
        const location = f.line ? ` (line ${f.line})` : '';
        output.push(`  [${f.severity}] ${f.rule} — ${f.title}`, `    File: ${f.file}${location}`, `    ${f.detail}`);

        if (process.env.GITHUB_ACTIONS) {
          const absFile = path.join(skillDir, f.file);
          const ghFile = path.relative(PROJECT_ROOT, absFile);
          const line = f.line || 1;
          const level = f.severity === 'LOW' ? 'notice' : 'warning';
          console.log(`::${level} file=${ghFile},line=${line}::${escapeAnnotation(`${f.rule}: ${f.detail}`)}`);
        }
      }
    }
  }

  // Summary
  output.push(
    `\n${'─'.repeat(60)}`,
    `\nSummary:`,
    `   Skills scanned: ${totalSkills}`,
    `   Skills with findings: ${skillsWithFindings}`,
    `   Total findings: ${totalFindings}`,
  );

  if (totalFindings > 0) {
    output.push('', `   | Severity | Count |`, `   |----------|-------|`);
    for (const sev of ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']) {
      if (severityCounts[sev] > 0) {
        output.push(`   | ${sev.padEnd(8)} | ${String(severityCounts[sev]).padStart(5)} |`);
      }
    }
  }

  const hasHighPlus = severityCounts.CRITICAL > 0 || severityCounts.HIGH > 0;

  if (totalFindings === 0) {
    output.push(`\n   All skills passed validation!`);
  } else if (STRICT && hasHighPlus) {
    output.push(`\n   [STRICT MODE] HIGH+ findings found — exiting with failure.`);
  } else if (STRICT) {
    output.push(`\n   [STRICT MODE] Only MEDIUM/LOW findings — pass.`);
  } else {
    output.push(`\n   Run with --strict to treat HIGH+ findings as errors.`);
  }

  output.push('');

  // Write GitHub Actions step summary
  if (process.env.GITHUB_STEP_SUMMARY) {
    let summary = '## Skill Validation\n\n';
    if (totalFindings > 0) {
      summary += '| Skill | Rule | Severity | File | Detail |\n';
      summary += '|-------|------|----------|------|--------|\n';
      for (const { skillDir, findings } of results) {
        const relDir = path.relative(PROJECT_ROOT, skillDir);
        for (const f of findings) {
          summary += `| ${escapeTableCell(relDir)} | ${f.rule} | ${f.severity} | ${escapeTableCell(f.file)} | ${escapeTableCell(f.detail)} |\n`;
        }
      }
      summary += '\n';
    }
    summary += `**${totalSkills} skills scanned, ${totalFindings} findings**\n`;
    fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, summary);
  }

  return { output: output.join('\n'), hasHighPlus };
}

function formatJson(results) {
  const allFindings = [];
  for (const { skillDir, findings } of results) {
    const relDir = path.relative(PROJECT_ROOT, skillDir);
    for (const f of findings) {
      allFindings.push({
        skill: relDir,
        rule: f.rule,
        title: f.title,
        severity: f.severity,
        file: f.file,
        line: f.line || null,
        detail: f.detail,
        fix: f.fix,
      });
    }
  }

  // Sort by severity
  allFindings.sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]);

  const hasHighPlus = allFindings.some((f) => f.severity === 'CRITICAL' || f.severity === 'HIGH');

  return { output: JSON.stringify(allFindings, null, 2), hasHighPlus };
}

// --- Main ---

if (require.main === module) {
  // Determine which skills to validate
  let skillDirs;

  if (positionalArgs.length > 0) {
    // Single skill directory specified
    const target = path.resolve(positionalArgs[0]);
    if (!fs.existsSync(target) || !fs.statSync(target).isDirectory()) {
      console.error(`Error: "${positionalArgs[0]}" is not a valid directory.`);
      process.exit(2);
    }
    skillDirs = [target];
  } else {
    // Discover all skills
    skillDirs = discoverSkillDirs([SRC_DIR]);
  }

  if (skillDirs.length === 0) {
    console.error('No skill directories found.');
    process.exit(2);
  }

  // Validate each skill
  const results = [];
  for (const skillDir of skillDirs) {
    const findings = validateSkill(skillDir);
    results.push({ skillDir, findings });
  }

  // Format output
  const { output, hasHighPlus } = JSON_OUTPUT ? formatJson(results) : formatHumanReadable(results);
  console.log(output);

  // Exit code
  if (STRICT && hasHighPlus) {
    process.exit(1);
  }
}

// --- Exports (for testing) ---
module.exports = { parseFrontmatter, parseFrontmatterMultiline, validateSkill, discoverSkillDirs };
