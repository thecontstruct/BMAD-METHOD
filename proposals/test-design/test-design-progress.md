---
workflowStatus: 'in-progress'
totalSteps: 5
stepsCompleted: ['step-01-detect-mode', 'step-02-load-context', 'step-03-risk-and-testability', 'step-04-coverage-plan']
lastStep: 'step-04-coverage-plan'
nextStep: '{skill-root}/steps-c/step-05-generate-output.md'
lastSaved: '2026-04-22'
inputDocuments:
  - BMAD-METHOD/proposals/bmad-skill-compiler-prd.md
  - BMAD-METHOD/proposals/bmad-skill-compiler-architecture.md
  - BMAD-METHOD/proposals/epics.md
  - .claude/skills/bmad-testarch-test-design/resources/knowledge/risk-governance.md
  - .claude/skills/bmad-testarch-test-design/resources/knowledge/test-levels-framework.md
  - .claude/skills/bmad-testarch-test-design/resources/knowledge/test-quality.md
  - .claude/skills/bmad-testarch-test-design/resources/knowledge/adr-quality-readiness-checklist.md
---

# Test Design Progress — System-Level

## Step 01 — Detect Mode & Prerequisites

**Mode:** System-Level
**Rationale:** User explicit intent ("high level system first"); PRD + ADR present; epics present but system-level preferred when both exist.

### Inputs located

- **PRD:** `BMAD-METHOD/proposals/bmad-skill-compiler-prd.md` — has §Functional Requirements and §Non-Functional Requirements.
- **Architecture/ADR:** `BMAD-METHOD/proposals/bmad-skill-compiler-architecture.md` — 18 decisions, explicit cross-cutting concerns section, 10 pattern categories, boundaries, validation results.
- **Epics (context only):** `BMAD-METHOD/proposals/epics.md` — 7 epics, ~30 stories.

### Scope recalibration

User's initial generic scope ("auth, observability, data integrity, NFRs that span epics") does not match project type. This is a compile pipeline / CLI tool (Node+Python), not a web app. Cross-cutting concerns per architecture doc:

- Determinism / byte-for-byte reproducibility (NFR-R1)
- I/O boundary sandbox (Decision 10)
- Error taxonomy consistency (Decision 11)
- Cross-language process boundary (Node ↔ Python)
- Lockfile integrity, drift detection, rollback forward-compat
- Concurrency & file-locking
- Module boundary enforcement
- Glob security / override-root containment
- Cache coherence (lazy compile-on-entry)
- Observability — logging channels + user-facing output

These become the anchors for risk assessment.

## Step 02 — Load Context & Knowledge Base

### Stack detection

- **Detected stack:** `backend` (Node CLI tool + planned Python engine subpackage)
- `package.json` present; no `pyproject.toml` yet (implementation phase will create it)
- No browser, no HTTP API, no UI — playwright-utils and browser-automation features are N/A

### Config flags resolved

| Flag | Value | Applied? |
|---|---|---|
| `tea_use_playwright_utils` | true | **No** — no browser/API surface to test |
| `tea_use_pactjs_utils` | false | No |
| `tea_pact_mcp` | none | No |
| `tea_browser_automation` | auto | Skipped — no UI to explore |
| `test_stack_type` | auto → backend | — |
| `test_artifacts` | `skills/test-artifacts` | — |

### Knowledge fragments loaded (core, system-level required set)

1. `adr-quality-readiness-checklist.md` — 8 categories / 29 criteria
2. `test-levels-framework.md` — unit / integration / E2E selection rules
3. `risk-governance.md` — P×I scoring, gate decision rules
4. `test-quality.md` — Definition of Done

Extended/specialized fragments skipped (not relevant for a non-service CLI tool).

### Existing test footprint

- `BMAD-METHOD/test/*.js` — 4 Node integration-style tests (installer components, rehype plugins, workflow path regex, file-refs csv)
- `BMAD-METHOD/src/core-skills/bmad-distillator/scripts/tests/` — pytest
- `BMAD-METHOD/src/core-skills/bmad-customize/scripts/tests/` — pytest
- No shared fixture library, no CI test matrix wired for this subproject yet.

### NFR Checklist reframe (IMPORTANT for gate math)

The 29-criteria checklist is written for services. This project is a compile-time CLI + library. Categories will be reinterpreted laterally; criteria that truly don't apply are flagged **N/A** and excluded from the denominator (honest gate math vs. artificial failure):

| Category | Reframe for compile pipeline |
|---|---|
| 1. Testability & Automation | Engine runs isolated from Node installer; seedable I/O sandbox; CLI headless |
| 2. Test Data Strategy | Fixture skills (synthetic), no prod data, temp-dir cleanup |
| 3. Scalability & Availability | **Partial** — throughput (batch compile), no availability/SLA |
| 4. Disaster Recovery | **Mostly N/A** — no state, but *lockfile rollback* maps here |
| 5. Security | **Critical** — override-root containment, glob security, no credential handling |
| 6. Monitorability | Logging channels, `--explain` output, error taxonomy |
| 7. QoS & QoE | Latency: compile <500ms; friendly error messages w/ remediation hints |
| 8. Deployability | Lazy-compile cache coherence, cross-OS determinism, Python 3.11 hard check |

## Step 03 — Testability & Risk Assessment

### Testability Assessment Summary ✅ (what's already strong)

The architecture document is unusually friendly to testing — most concerns are already designed for:

- **Determinism boundary confined to `io.py` (Decision 10).** One file = audit surface for cross-OS drift. Python-linter ban on raw file ops elsewhere (documented).
- **Lockfile = single source of truth (NFR-O1).** Perfect observability anchor — every compile writes provenance. Test assertions read lockfile, not source files.
- **`--explain --json` provenance surface (NFR-O2, FR27–31, Appendix A).** Machine-readable XML/JSON with frozen tag vocabulary. Golden goldmine for assertions.
- **Frozen error taxonomy (NFR-M5, Decision 11).** Seven error codes; tests assert `code`, not brittle messages.
- **Golden-file test harness planned with `--update-golden`** (architecture §Test Organization). Proven pattern for deterministic engines; regeneration mechanism prevents fixture rot.
- **Pre-named test scenarios (architecture §Test Organization):** variable-resolution, toml-layering, glob-expansion, frontmatter-stripping, cross-plane, cyclic-include, variant-selection. ~8–15 golden scenarios target — the right scope.
- **CI matrix scheduled, not universal** — Linux every PR; macOS+Windows on merge/nightly. Explicitly costed against `io.py` boundary guarantees.
- **Dedicated test stories in epics:** FR52 (E2E lifecycle), FR55 (abandoned-session), Story 2.3 (3-OS determinism matrix), Story 6.1 (compiler-primitive mock contract for skill).
- **Controllability via seeding:** architecture allows fixture skills + synthetic project roots. No external services to mock.
- **Frozen CLI surface** = stable integration seam. Tests don't rebase every release.

### 🚨 Testability Concerns (actionable)

| # | Concern | Why it matters | Action |
|---|---|---|---|
| T-01 | **`io.py` linter ban is "documented" but enforcement unclear** | NFR-R1 determinism depends on zero raw `open()`/`pathlib` calls outside `io.py`. Architecture says *"repo Python linter config bans raw file operations"* — but no specific rule or CI gate cited. | Story 1.1 DoD must include: implementing the lint rule (e.g., Ruff custom rule or grep-based pre-commit hook), wiring it into `npm run lint`/`quality` gate. Without this, R-01 is unmitigated. |
| T-02 | **No explicit perf-budget CI harness for NFR-P2 / NFR-P5** | 500ms per-skill + 50ms lazy-path fast-path are *committed NFRs*. "Mid-2021 laptop" is a human ref, not CI. Perf regressions won't surface until a user complains. | Add a perf-smoke job: a reference skill + generated-synthetic fragments repo, `time` measurement with a generous CI-adjusted budget (e.g., 1.5× the wall-clock NFR to absorb CI noise). Threshold breach = warning; 3× = fail. |
| T-03 | **3-OS concurrency semantics are non-obvious (Windows `msvcrt.locking` ≠ POSIX `flock`)** | Decision 16 + §Concurrency locks on `.compiling.lock`. Advisory semantics differ between OSes. Stale-lock detection at 5 min. | Dedicated race-test `test_concurrent_compile.py` mentioned in architecture — confirm it runs on all 3 OSes in the merge-to-main matrix (not just Linux). Add an assertion for stale-lock reclaim. |
| T-04 | **Cross-language boundary lacks a focused contract test** | Node invokes Python; errors propagate via exit code + stderr. NFR-O3 requires file/line in user-facing errors. Easy to regress if Node swallows stderr, or Python writes errors to stdout. | New integration test: inject each of the 7 error codes via a malformed template fixture, invoke via Node CLI, assert stderr contains file + line + code, stdout empty, exit non-zero. One test, high coverage. |
| T-05 | **Lockfile forward-compat claim ("unknown additive fields round-tripped")** | NFR-C5 + Appendix A stability rules. Critical for v2-forward evolution. No test named in architecture. | Golden-file test: hand-craft a lockfile with `version: 1` + a fake `future_field: "x"`, run a compile, assert `future_field: "x"` preserved unchanged. |
| T-06 | **Symlink / Windows-junction escape testing is adversarial** | NFR-S2 override-root + glob containment. Architecture says "symlinks pointing outside roots are rejected" via `Path.resolve(strict=True)` + ancestor check. Windows junctions and NFS/SMB mounts are historical edge cases. | Security test suite with symlink/junction escape fixtures — must run on 3 OSes (not Linux-only). Windows fixtures generated at test-time via `mklink /J`. |
| T-07 | **Drift category combinatorics under-covered by "~8–15 scenarios"** | FR41 lists 6 drift categories × (positive, negative, plane-intersection) = 30+ cases. Architecture's scenario count targets ~8–15 total. Missed drift = silent user-override loss (violates north-star metric). | Dedicated drift scenario suite — one golden per category minimum + one cross-category case (e.g., glob-input drift intersecting a TOML override). Treat as a separate scenario family from compile-correctness goldens. |
| T-08 | **`bmad-customize` skill ↔ compiler boundary (Decision 15) is architectural but LLM-consumer** | Skill is Markdown executed by an LLM. Decision 15 says skill's ONLY inputs are 3 CLI commands. Hard to enforce at test-time because the "importer" is a natural-language prompt. | Story 6.1's "compiler-primitive mock contract" covers tests against a mock. Add a lint: if any new file under the skill directory references `bmad_compile` Python module or `bmad.lock` path, fail. |
| T-09 | **Backward-compat regression (NFR-C4) depends on a pre-compiler baseline that doesn't exist in this repo yet** | "Byte-for-byte identical" install for unmigrated skills — needs a checked-in baseline of current install output to diff against. | Story 2.1 / 2.2 DoD: generate baseline (`tar` of current `_bmad/` install for a reference config) and commit it; CI diffs new install against baseline. Without this, R-17 has no measurement. |
| T-10 | **The `customize.toml` + fragment + YAML cross-plane matrix** (architecture §Cross-Plane Customization Precedence Matrix) | Each matrix row is a specific scenario requiring a golden. `PRECEDENCE_UNDEFINED` is the fallback for unmatched scenarios — but the matrix entries themselves need passing tests. | Architecture already commits to "one golden per matrix row in `test/fixtures/compile/cross-plane/`" — confirm this is story-scoped. |

### Architecturally Significant Requirements (ASRs)

**ACTIONABLE** (require specific test coverage / gate before ship):

| ASR | Source | Why ACTIONABLE |
|---|---|---|
| Byte-for-byte determinism across macOS / Linux / Windows | NFR-R1 | Single-largest risk surface. Needs 3-OS CI + io.py-boundary lint (T-01). |
| Lazy-compile fast-path ≤50ms; slow-path ≤500ms | NFR-P5, NFR-P2 | No perf gate yet (T-02). |
| Lazy-compile concurrency correctness | Decision 16 + §Concurrency | Advisory locks, 3-OS semantics, stale-lock recovery (T-03). |
| Override-root + glob containment (no escape) | NFR-S2, Decision 10 | Security property; adversarial tests needed (T-06). |
| Lockfile schema forward-compat (v1 additive fields round-trip) | NFR-C5, Appendix A Stability | Unknown-field survival test (T-05). |
| Frozen error taxonomy with file/line in every message | NFR-M5, NFR-O3, Decision 11 | Cross-language propagation test (T-04). |
| E2E customization lifecycle | FR52 | Named in epic backlog (Story 7.2). |
| Abandoned-session cleanliness (no disk writes until accept) | FR54, FR55 | Named in epic backlog (Story 7.4). |
| Backward-compat for unmigrated skills (byte-identical install) | NFR-C4 | Requires committed baseline (T-09). |
| Drift detection across 6 categories + cross-category | FR41, FR58 | Under-scoped scenario count (T-07). |
| Dogfood loop: `bmad-customize` compiles clean on every release | FR39 | Gate in release CI. |
| Cross-plane precedence matrix (one golden per row) | Architecture §Cross-Plane Matrix | Row-enumerated in docs; test enumeration must match (T-10). |
| `bmad-customize` skill ↔ compiler boundary (3 CLI primitives only) | Decision 15 | Needs lint (T-08) + mock contract (Story 6.1). |

**FYI** (inherent / architectural, low independent test action):

| ASR | Why FYI |
|---|---|
| Node ≥20, Python ≥3.11 (NFR-C1) | Hard startup check; single version-mismatch fixture covers it. |
| No network access during compile (NFR-S5) | CI default-deny + a single "resolve with net blocked" smoke test. |
| No new runtime deps (NFR-S6) | `package.json` diff review gate; not a runtime test. |
| Four-construct syntax frozen (NFR-M1) | Single "unknown directive → UNKNOWN_DIRECTIVE" test; syntax changes require major bump. |
| Frozen explain tag vocabulary (Appendix A) | Golden `--explain` output compares against committed fixture; vocabulary drift = golden diff. |
| Reference skills as contract tests (NFR-M4) | Implemented by CI recompile + baseline diff; not a separate test family. |
| `--debug` on all subcommands (NFR-O5) | Trivially asserted via presence of `[debug]` lines in stderr. |

### Risk Assessment Matrix

Scoring: P (1–3) × I (1–3) = score (1–9). Score ≥6 = HIGH (requires mitigation plan). Score = 9 = CRITICAL (blocker).
Categories: TECH (technical debt/architecture fragility), SEC (security), PERF (performance), DATA (lockfile/override-state integrity), BUS (business/product), OPS (operational/deployability).

| ID | Category | Risk | P | I | Score | Level | Owner | Mitigation |
|---|---|---|---|---|---|---|---|---|
| **R-01** | TECH | Cross-OS determinism drift — a direct `open()`/`pathlib` call bypassing `io.py` leaks path/newline/ordering differences into compiled output | 2 | 3 | **6** | HIGH | Engine lead | (1) Implement & enforce Python linter rule banning raw I/O outside `io.py` (T-01). (2) 3-OS determinism test matrix (Story 2.3). (3) Nightly catches merge-window regressions within 24h — accepted trade. |
| **R-02** | DATA | Lockfile corruption triggers silent recovery → wrong content served to LLM | 1 | 3 | 3 | LOW | Engine lead | NFR-R5 explicitly forbids silent recovery. Unit test: malformed lockfile → non-zero exit + user-facing instruction. |
| **R-03** | DATA | Malformed-lockfile recovery deletes a user override | 1 | 3 | 3 | LOW | Engine lead | NFR-R5: prompt before destruction. Integration test: stage malformed lockfile + user override present → assert interactive prompt, no silent deletion. |
| **R-04** | SEC | Override-root escape via symlink, Windows junction, or `..` path — attacker-controlled or user-error content injection / exfil | 2 | 3 | **6** | HIGH | Security / engine lead | (1) `io.py` ancestor-containment check via `Path.resolve(strict=True)`. (2) Adversarial test suite on 3 OSes (T-06) including Windows junctions via `mklink /J`. (3) Glob containment enforced at expansion time per NFR-S2. |
| **R-05** | SEC | Third-party module shadows core fragment at install time (NFR-S3 violation) | 1 | 2 | 2 | LOW | Installer lead | Install-time namespace-collision check. Test: install fixture module declaring a core-path fragment → install fails with clear error. |
| **R-06** | SEC | Plaintext variable value or glob-file content leaks into committed lockfile | 1 | 3 | 3 | LOW | Engine lead | NFR-S1 mandates `value_hash` only. Unit test: compile with a `{{var}}` containing "secret" → assert "secret" absent from lockfile YAML, `value_hash` present. |
| **R-07** | PERF | Per-skill recompile exceeds NFR-P2 500ms budget (CI or user-reported) | 2 | 2 | 4 | MEDIUM | Engine lead | Perf-smoke CI job (T-02) with 1.5× generous CI-adjusted budget; warn at 1.5×, fail at 3×. |
| **R-08** | PERF | Lazy-compile fast path exceeds NFR-P5 50ms — every LLM turn pays the cost | 2 | 2 | 4 | MEDIUM | Engine lead | Author guidance on glob narrowness (documented in NFR-P5). CI linter warns on overly-broad glob patterns (stated in NFR-P5). Perf-smoke job includes fast-path measurement. |
| **R-09** | TECH | Lazy-compile guards race on parallel IDE invocations; winner-writes-loser-reads contract broken → wrong bytes to LLM | 2 | 3 | **6** | HIGH | Engine lead | (1) Advisory lock on `.compiling.lock` (Decision 16). (2) Atomic temp-file+rename writes (§Concurrency). (3) 3-OS race test (`test_concurrent_compile.py`) with parallel `subprocess.run` invocations. (4) Stale-lock reclaim test at 5-min threshold (T-03). |
| **R-10** | TECH | Cross-language boundary swallows Python errors — user sees "compile failed" without file/line (NFR-O3 regression) | 2 | 2 | 4 | MEDIUM | CLI adapter lead | Contract test per error code: fixture triggers code → Node CLI stderr contains file+line+code (T-04). |
| **R-11** | TECH | Hash-skip false-positive (Decision 12) — an untracked input changes but skip engages → stale compiled output | 2 | 3 | **6** | HIGH | Engine lead | (1) Input-hash composition reviewed (source + fragments + vars + variant + glob-match-set + per-match-content). (2) Regression test per tracked-input class: mutate each, assert skip does NOT engage. (3) `--debug` emits skip/no-skip rationale for audit. |
| **R-12** | DATA | Drift dry-run false-negative — upstream change is real drift but not flagged → user upgrades, override silently lost | 2 | 3 | **6** | HIGH | Engine lead + QA | (1) Dedicated drift scenario suite, 6 categories × (positive + negative + cross-category) (T-07). (2) FR52 E2E test simulates the full loop. (3) Violates north-star metric "zero silent loss" — critical dogfood guard. |
| **R-13** | DATA | Drift dry-run false-positive — flags non-drift, annoys users, weakens trust | 2 | 1 | 2 | LOW | Engine lead | Absorbed by same scenario suite as R-12. |
| **R-14** | OPS | Lockfile v1 schema forward-compat broken — unknown fields dropped on write | 1 | 2 | 2 | LOW | Engine lead | T-05: unknown-field round-trip test. |
| **R-15** | OPS | Abandoned `bmad-customize` session pollutes `_bmad/custom/` (FR54 violation) | 1 | 2 | 2 | LOW | Skill lead | FR55 CI test already planned. |
| **R-16** | BUS | Dogfood loop breaks — compiler refactor makes `bmad-customize` skill fail to compile → ship gate blocks release | 2 | 3 | **6** | HIGH | Release gate | (1) Every CI run recompiles the skill (NFR-M4 contract). (2) Skill-compile diff against committed baseline. (3) Named as "Business Success dogfood release gate" in PRD. |
| **R-17** | TECH | NFR-C4 regression — unmigrated skill install bytes differ from pre-compiler baseline | 2 | 3 | **6** | HIGH | Installer lead | (1) Commit pre-compiler baseline tar (T-09). (2) CI diff gate on every PR. (3) Story 2.2 "keep contract" DoD. |
| **R-18** | TECH | `bmad-customize` skill violates Decision 15 boundary — future contributor adds helper script that imports compiler engine | 2 | 2 | 4 | MEDIUM | Architecture reviewer | Lint rule: no references to `bmad_compile` module or `bmad.lock` path from skill directory (T-08). |
| **R-19** | PERF | Glob-input expansion slow on large repos (`{project-root}/**/*` type patterns) | 2 | 2 | 4 | MEDIUM | Engine lead | NFR-P5 documents author guidance + CI linter warning on broad patterns. Perf-smoke with a large synthetic-repo fixture. |
| **R-20** | TECH | Error message regression — a new error class ships without file/line (NFR-O3) | 1 | 2 | 2 | LOW | Engine lead | Per-code contract test (T-04). |

### Risk Summary

- **Critical (score=9):** 0 — no single P=3 × I=3 blocker. The architecture's determinism-boundary + frozen-vocabulary discipline defuses most catastrophic scenarios.
- **High (score 6–8):** 7 — R-01, R-04, R-09, R-11, R-12, R-16, R-17.
- **Medium (score 4–5):** 5 — R-07, R-08, R-10, R-18, R-19.
- **Low (score ≤3):** 8 — R-02, R-03, R-05, R-06, R-13, R-14, R-15, R-20.

**Category distribution:** TECH dominates (7 risks, 5 high/medium — expected for a new compile pipeline). DATA next (5 risks, 2 high — lockfile+drift is the north-star surface). SEC (3 risks, 1 high — containment is the live wire). PERF (3 risks, all medium — real but quantifiable). BUS (1 high — dogfood discipline). OPS (2 risks, both low — forward-compat and hygiene).

**Themes across the 7 HIGH risks:**

1. **Determinism + cache coherence** (R-01, R-09, R-11) — three expressions of the same underlying concern: did the engine see the world correctly? Mitigated via io.py-boundary enforcement + 3-OS race tests + hash-composition review.
2. **Drift semantics** (R-12) — the single most consumer-facing risk. Directly threatens the PRD's "zero silent override loss" north-star metric.
3. **Backward compatibility** (R-17) — every refactor of the installer risks regressing the verbatim-copy path. Requires a committed baseline.
4. **Security containment** (R-04) — path/symlink/glob escape. 3-OS adversarial tests non-negotiable.
5. **Dogfood discipline** (R-16) — release gate, not just a test.

No scores warrant waiver. R-01, R-04, R-09, R-11, R-12, R-16, R-17 all have clear mitigation paths already aligned with planned stories — the test-design work in step 4 will prioritize tests against these seven.

## Step 04 — Coverage Plan & Execution Strategy

### Test Level Terminology (mapped to this project)

The generic "unit / integration / E2E" maps non-obviously for a compile pipeline. Definitions used below:

| Level | What it means here | Location | Framework |
|---|---|---|---|
| **Unit** | Single-module Python test, no subprocess, no filesystem beyond `tmp_path` | `test/python/test_<module>.py` | stdlib `unittest` + `self.subTest()` (NFR-S6 — no pytest) |
| **Golden** | Fixture-driven compile test: input skill → expected SKILL.md + lockfile + --explain. One behavior per fixture. | `test/fixtures/compile/<scenario>/` + `run.sh` + `--update-golden` regeneration | stdlib harness |
| **Python integration** | `subprocess.run` exercising `compile.py` / `lazy_compile.py` as black box | `test/python/integration/` | stdlib |
| **Node integration** | Node CLI → Python subprocess boundary test | `test/test-compile-integration.js` (new) + existing `test-installation-components.js` | jest + hand-rolled harness |
| **E2E lifecycle** | Full `install → customize → upgrade` journey (FR52) | existing harness + scripted fixtures | hand-rolled |
| **3-OS determinism** | Same compile on macOS + Linux + Windows, byte-diff outputs | CI matrix, nightly + merge | GitHub Actions matrix |
| **Perf smoke** | Wall-clock budget measurement (NFR-P2, NFR-P5) | `test/python/perf/` | stdlib `time.perf_counter` |
| **Security adversarial** | Escape attempts (symlinks, junctions, `..` paths) | `test/python/security/` | stdlib + OS-specific fixtures |

"E2E for UI" doesn't exist — no UI. "API tests" don't exist — no HTTP API. Everything is CLI + filesystem.

### Coverage Matrix

One row per scenario. `Traces` links to the risk(s) and/or FR/NFR/Decision it covers. `Level` uses the terminology above. Priority follows `test-priorities-matrix.md` adjusted for risk score (scores ≥6 → at least P0/P1; score 9 → P0).

#### P0 — Must test (blockers / revenue-critical-equivalent)

For this project, "revenue-critical equivalent" = things that silently corrupt user state, violate security containment, or break the north-star metric "zero silent override loss."

| # | Scenario | Level | Traces |
|---|---|---|---|
| P0-01 | `io.py` normalizes paths to POSIX, converts CRLF→LF, sorts dir listings alphabetically, rejects path escapes | Unit | NFR-R1, NFR-R2, NFR-R3, Decision 10, R-01 |
| P0-02 | Linter rule fails CI if any file under `src/scripts/bmad_compile/` (except `io.py`) imports `open`, `pathlib.Path.open`, `os.listdir`, `os.scandir` | Node integration (lint gate) | Decision 10, T-01, R-01 |
| P0-03 | 3-OS determinism: compile reference skill on macOS + Linux + Windows, assert byte-identical output across all three | 3-OS determinism (CI matrix) | NFR-R1, NFR-C2, Story 2.3, R-01 |
| P0-04 | Override-root containment: override file path containing `..`, symlink pointing outside `_bmad/custom/`, and symlink chain to outside → each raises `OverrideOutsideRootError` | Security adversarial (3-OS) | NFR-S2, Decision 10, R-04, T-06 |
| P0-05 | Glob containment: `file:` TOML-array pattern that would match outside `{project-root}` → rejected at expansion with clear error | Security adversarial (3-OS) | NFR-S2, FR31/Appendix A, R-04 |
| P0-06 | Windows junction escape: `mklink /J` pointing outside project root → rejected | Security adversarial (Windows-only) | NFR-S2, R-04, T-06 |
| P0-07 | Parallel lazy-compile guard invocations for same skill: one recompiles, the other waits on `.compiling.lock` and reads fresh bytes | Python integration (3-OS) | Decision 16, NFR-R5 §Concurrency, R-09, T-03 |
| P0-08 | Stale `.compiling.lock` (>5 min old) is reclaimed; compile proceeds with warning | Python integration | §Concurrency, R-09 |
| P0-09 | Hash-skip fires iff every tracked input hash matches. Mutate each input class (source, fragment, variable value, variant, glob-match-set, per-match content) and assert skip does NOT engage | Python integration (parametrized) | Decision 12, R-11 |
| P0-10 | `--debug` emits skip/no-skip rationale | Python integration | Decision 12, R-11 |
| P0-11 | Drift dry-run across 6 categories — one positive + one negative fixture per category (prose, TOML default, TOML orphan, TOML new-default, glob-input, variable-provenance) = 12 fixtures | Golden | FR41, R-12, T-07 |
| P0-12 | Drift cross-category: glob-input drift at a path intersecting a TOML user override → flagged, not silently dropped | Golden | FR41, R-12, T-07 |
| P0-13 | E2E lifecycle (FR52): install → customize draft → accept → compile --diff → simulated upstream change → upgrade --dry-run shows drift → upgrade halts → manual resolve → upgrade succeeds → lockfile records lineage | E2E lifecycle | FR52, R-12, R-16 |
| P0-14 | Dogfood gate: every CI run recompiles `bmad-customize` skill, diffs against committed baseline; any regression fails the build | Node integration (release gate) | FR39, NFR-M4, R-16 |
| P0-15 | Backward compat (NFR-C4): install a fixture module with no `*.template.md` → install output byte-identical to committed pre-compiler baseline | Node integration | NFR-C4, Story 2.2, R-17, T-09 |
| P0-16 | Full 7-code error taxonomy: fixture per code, invoked via Node CLI, stderr contains `file:line:code + remediation hint`, stdout empty, exit non-zero, no partial writes | Node integration | NFR-M5, NFR-O3, NFR-R4, Decision 11, R-10, T-04 |
| P0-17 | Lockfile integrity: malformed lockfile → non-zero exit with clear remediation, no silent recovery, no destruction of user overrides (prompt first) | Python integration | NFR-R5, R-02, R-03 |
| P0-18 | Secret-leak guard: compile with `{{var}}` resolving to `SECRET_VALUE` → assert `SECRET_VALUE` absent from lockfile, `value_hash` present | Unit (lockfile.py) | NFR-S1, R-06 |

Count: **18 P0 scenarios.** Every P0 traces to at least one HIGH risk or a frozen contract NFR.

#### P1 — Should test (core paths + medium risk)

| # | Scenario | Level | Traces |
|---|---|---|---|
| P1-01 | Template parser: each of 4 constructs (literal, `<<include>>`, `{{var}}`, `{var}`) tokenized correctly; unknown directive → `UNKNOWN_DIRECTIVE` with file+line | Unit (parser.py) | FR1–7, NFR-M1, Decision 1 |
| P1-02 | Fragment resolution precedence: 5-tier cascade (user-full-skill > user-module-fragment > user-override > variant > base); one fixture per adjacent pair + one matrix fixture | Golden | FR10, NFR-M2, Decision 2 |
| P1-03 | Cyclic include detection: A→B→A → `CYCLIC_INCLUDE` with chain; three-hop cycle → detected | Unit (resolver.py) | FR11, Decision 2 |
| P1-04 | Variable resolver 8-tier `self.*` cascade + non-`self.` cascade: fixture per adjacent pair + combined matrix (NFR-M2 requirement) | Golden | FR16, NFR-M2, Decision 3 |
| P1-05 | TOML layer merge: scalars, deep-merge tables, merge-by-key arrays, append arrays; fixture matrix against upstream's documented rules | Unit (toml_merge.py) + Golden | FR13a, NFR-M2 |
| P1-06 | IDE variant selection: Claude Code picks `*.claudecode.template.md`; Cursor picks `*.cursor.template.md`; unknown IDE falls back to universal | Golden | FR6, FR44–46, Decision 7 |
| P1-07 | Cross-plane precedence matrix: one golden per documented row in Architecture §Cross-Plane Customization Precedence Matrix (7 rows) | Golden | NFR-M5, T-10 |
| P1-08 | `PRECEDENCE_UNDEFINED` raised when a plane interaction not covered by the matrix occurs; error message points at matrix docs anchor | Unit + Golden | NFR-M5, Decision 11 |
| P1-09 | `--explain` output: every `<Include>` has required attributes; every `<Variable>` has required attributes; every `<TomlGlobExpansion>` + `<TomlGlobMatch>` pair matches Appendix A schema; order matches compiled Markdown order | Golden | FR27–31, Appendix A, NFR-O2 |
| P1-10 | `--explain --json` equivalence: JSON representation semantically equals Markdown/XML output, with the same ordering | Golden | FR29, Appendix A |
| P1-11 | `--explain --tree`: fragment dependency tree only, no content | Golden | FR28 |
| P1-12 | `bmad compile <skill> --diff`: unified diff format, ANSI when TTY, plain when piped; +100ms budget | Node integration + perf smoke | FR26 |
| P1-13 | Lockfile schema fidelity: one compile, read back via `bmad.lock` reader, every FR40-listed field present with correct shape (source, fragments, TOML, variables, globs, variant, compiled_hash) | Python integration | FR40, FR43 |
| P1-14 | Lockfile forward-compat: hand-crafted lockfile with `version: 1` + unknown field `future_field: "x"` → compile preserves unknown field on write | Unit (lockfile.py) | NFR-C5, Appendix A Stability, R-14, T-05 |
| P1-15 | Abandoned `bmad-customize` session (FR55): start draft → abandon before accept → assert no files written under `_bmad/custom/`, `bmad.lock` byte-identical to pre-session state | Node integration (E2E harness) | FR54, FR55, R-15, Story 7.4 |
| P1-16 | Module boundary: third-party module declaring a core-path fragment at install time → `NAMESPACE_COLLISION` (NFR-S3 error) | Node integration | FR17, FR47, NFR-S3, Decision 14, R-05 |
| P1-17 | Cross-module include: `<<include path="core/persona-guard.template.md">>` from a non-core skill resolves to core module's fragment | Golden | FR48, Decision 14 |
| P1-18 | Compile-engine partial-write prevention: inject a failure mid-compile → no partial files written to install location | Python integration | NFR-R4, Decision 11 |
| P1-19 | Halt-on-drift (FR57): `bmad upgrade` with drift but without `--yes` → exit non-zero with `bmad-customize` pointer in message | Node integration | FR22, FR57 |
| P1-20 | `--yes` escape: `bmad upgrade --yes` proceeds despite drift | Node integration | FR22, FR57 |
| P1-21 | `--debug` on every subcommand: emits `[debug]` lines to stderr, never stdout, never changes stdout content | Node integration | NFR-O5 |
| P1-22 | Skill↔compiler boundary lint: any file under `src/.../bmad-customize/` referencing `bmad_compile` module, `bmad.lock` path, or Python imports → lint failure | Node integration (lint gate) | Decision 15, R-18, T-08 |
| P1-23 | Distribution model detection: Model 1 (verbatim copy), Model 2 (templates only), Model 3 (templates + precompiled fallback). CI matrix tests each (Story 7.3) | Node integration | FR47, FR53, Decision 13 |
| P1-24 | Runtime placeholder passthrough: `{var_name}` appears verbatim in compiled output (not substituted) | Golden | FR5, FR32, Decision 16 |

Count: **24 P1 scenarios.**

#### P2 — Nice to test (secondary / low-medium risk / coverage fill)

| # | Scenario | Level | Traces |
|---|---|---|---|
| P2-01 | Per-skill compile perf budget (NFR-P2 ≤500ms): fixture skill with 10 fragments + 3 TOML layers + 20 glob matches @ 500KB, timed with 1.5× CI-adjusted budget | Perf smoke | NFR-P2, R-07, T-02 |
| P2-02 | Lazy-compile fast-path (NFR-P5 ≤50ms): all hashes match, measure wall-clock with 1.5× CI-adjusted budget | Perf smoke | NFR-P5, R-08, T-02 |
| P2-03 | Install-time overhead (NFR-P1 ≤110%): before/after compiler integration, measure full install time | Perf smoke (release gate, nightly) | NFR-P1 |
| P2-04 | Glob expansion on synthetic large repo (10k files): flag overly-broad patterns, assert CI linter warns | Perf smoke + Node integration | NFR-P5, R-19 |
| P2-05 | `bmad upgrade --dry-run` streams first drift item within 500ms (NFR-P3) | Perf smoke | NFR-P3 |
| P2-06 | Python runtime version check: `python3 --version < 3.11` → install fails with clear message at install-time check | Node integration | NFR-C1, Story 2.1 |
| P2-07 | Node runtime version check: `node --version < 20` → install fails with clear message | Node integration | NFR-C1 |
| P2-08 | No network during compile (NFR-S5): compile with network default-denied → succeeds | Python integration (CI net-deny env) | NFR-S5 |
| P2-09 | No new runtime deps (NFR-S6): `package.json` diff gate on release PR; `pyproject.toml` absent or stdlib-only | Node integration (release gate) | NFR-S6 |
| P2-10 | `--explain` unknown optional attributes round-trip: consumer-side tolerance for additive attributes | Unit (explain.py) | Appendix A Stability |
| P2-11 | Trust-gate rejection (NFR-S4): attempt to load a custom Python render function without `trust_mode: full` → install-time rejection | Node integration | NFR-S4 |
| P2-12 | Lockfile rollback forward-compat: `lineage` array appended on every upgrade, `previous_base_hash` field populated, round-tripped unchanged by v1 | Python integration | FR42, NFR-C5, Decision 9 |
| P2-13 | `bmad upgrade --dry-run --json` output is valid JSON consumable by `bmad-customize` mock (Story 6.1) | Python integration | FR21, FR56, Decision 15 |
| P2-14 | Config file layering (workflow-scoped config.yaml copied verbatim) | Golden | Architecture §Technical Constraints |
| P2-15 | `--lock-timeout-seconds` flag tunes advisory-lock timeout as documented (FR24) | Python integration | FR24 |
| P2-16 | Error message quality: assert each of 7 error codes includes a remediation hint per "Error Message Format" spec | Unit (errors.py) | Architecture §Error Message Format, R-20 |
| P2-17 | Empty-skill edge cases: skill with no fragments, no variables, no globs → compiles to bare literal content with valid lockfile entry | Golden | Smoke |

Count: **17 P2 scenarios.**

#### P3 — Test if time permits

| # | Scenario | Level | Traces |
|---|---|---|---|
| P3-01 | Chaos-ish: corrupt a random byte in `bmad.lock` → fail-safe behavior (non-zero exit, clear message) | Python integration | Robustness |
| P3-02 | Windows path-case collision (two files differing only in case on case-insensitive FS) → deterministic ordering | 3-OS determinism | NFR-R1 edge case |
| P3-03 | Unicode path names in globs → preserved through compile | Golden | Robustness |
| P3-04 | Very-large TOML layer (>1MB) → parses within budget | Perf smoke | Boundary |
| P3-05 | `--help` output completeness smoke (every flag documented) | Node integration | UX polish |

Count: **5 P3 scenarios.**

#### Coverage summary

| Priority | Count | Covers |
|---|---|---|
| P0 | 18 | All 7 HIGH risks; security containment; determinism boundary; dogfood gate; backward-compat baseline; error-taxonomy contract |
| P1 | 24 | All ACTIONABLE ASRs; all FRs with direct user-visible behavior; cross-plane matrix (7 rows); frozen Appendix A schema |
| P2 | 17 | NFRs with measurable budgets (perf, runtime versions); supply-chain; trust gate; secondary edge cases |
| P3 | 5 | Robustness / polish |
| **Total** | **64** | |

Anti-pattern guard applied: no scenario is duplicated across levels where a lower level suffices. Example: path normalization is tested at Unit (`io.py`), not re-exercised at Golden or Integration. Example: precedence rules are tested at Unit (resolver) + Golden (one fixture per adjacent pair) — Integration does not re-derive the cascade.

### Execution Strategy

| Tier | Contents | Frequency | Budget |
|---|---|---|---|
| **PR (fast)** | All Unit + all Golden + all Python integration (non-perf, non-3-OS) + Node integration (lint gates + boundary tests) | Every PR, Linux-x64 only | ≤10 min |
| **PR (full)** | Above + 3-OS determinism subset (2 fixture skills, all 3 OSes) | Every PR where `tools/installer/compiler/**` or `src/scripts/bmad_compile/**` changes | ≤20 min |
| **Merge-to-main** | Full PR suite + complete 3-OS determinism matrix + security adversarial (Windows junctions) + perf smoke | On every merge | ≤30 min |
| **Nightly** | Full E2E lifecycle (FR52) + Model 3 distribution matrix (FR53) + release-gate perf (NFR-P1 install-time overhead measured against historical baseline) | Daily 02:00 UTC | ≤60 min |
| **Release tag** | Nightly suite + dogfood gate + backward-compat baseline diff + `bmad-customize` skill recompile-diff | Per release PR | ≤90 min |

**Rationale for the PR "fast" vs "full" split:** architecture §Test Organization explicitly schedules macOS + Windows for merge-to-main rather than per-PR, costing a day's blind-to-regression in exchange for ~6 min × every PR. Keeping that trade. The "full" PR tier triggers only when compiler code is touched — balances signal with cost.

**Flakiness policy** (per `test-quality.md`): any test that fails twice in a 7-day rolling window is quarantined; quarantine expires after fix or after 14 days (whichever first). No opt-in retries. Flakiness is treated as a P1 bug, not a CI annoyance.

### Resource Estimates

Effort ranges for test authorship (not execution). Assumes one engineer moderately familiar with the compile engine; halve for a TEA-dedicated engineer.

| Priority | Scenarios | Effort (hours) |
|---|---|---|
| P0 | 18 | **60–100h** — security adversarial + 3-OS CI plumbing drives upper bound |
| P1 | 24 | **50–90h** — cross-plane matrix + Appendix A schema fixtures are the long poles |
| P2 | 17 | **20–40h** — perf-smoke harness is the main investment |
| P3 | 5 | **5–15h** — opportunistic |
| **Total** | **64** | **135–245 hours** |

Timeline if distributed across Epics 1–7 per story DoDs (recommended — avoid "test at the end" anti-pattern):

- Epic 1 (compile pipeline core): ~35–55h — parser, resolver, io.py, errors, lockfile, variants, golden harness
- Epic 2 (install integration): ~20–35h — Node-Python boundary, backward-compat baseline, 3-OS CI
- Epic 3 (overrides): ~15–30h — cross-plane, TOML layers, module boundary
- Epic 4 (compile primitives): ~20–35h — `--explain` schema, `--diff`, `--json`, tree
- Epic 5 (upgrade/drift/lazy): ~25–45h — drift 6-category suite, lazy race tests, concurrency
- Epic 6 (customize skill): ~10–20h — mock contract, boundary lint
- Epic 7 (validation/CI/release): ~10–25h — dogfood gate, distribution matrix, E2E lifecycle

Spread matches the epic scope; no single epic concentrates >25% of test effort.

### Quality Gates

Release-blocking thresholds:

| Gate | Threshold |
|---|---|
| P0 pass rate | **100%** — every scenario green |
| P1 pass rate | **≥95%** — ≤1 failure allowed with documented waiver + owner + expiry |
| P2 pass rate | **≥80%** — CONCERNS if below, not blocker |
| P3 pass rate | Best-effort; trends tracked |
| HIGH-risk mitigations | **All 7 HIGH risks (R-01, R-04, R-09, R-11, R-12, R-16, R-17) must be MITIGATED before release.** Not waivable in v1. |
| 3-OS determinism matrix | **100% byte-equal** on macOS / Linux / Windows for reference skills |
| Dogfood gate | **`bmad-customize` skill recompile matches baseline, byte-for-byte** |
| Backward-compat gate | **Unmigrated-skill install output byte-matches pre-compiler baseline** (NFR-C4) |
| Flakiness budget | ≤2% test-failure-rate over trailing 30 CI runs per test; any test over budget is quarantined |
| Perf thresholds | NFR-P2, NFR-P5 measured with 1.5× CI-adjusted ceiling; warn at 1.5× real budget, fail at 3× |

Coverage target: **≥80% statement coverage on `bmad_compile/*.py`**, with the `io.py` module held to **≥95%** (it's the determinism boundary — every branch matters). Branch coverage tracked but not gated in v1.

**Gate decision framework** (applied during trace/gate workflow later):

- **PASS** — all P0 green, P1 ≥95%, all HIGH mitigations complete, all matrix gates green
- **CONCERNS** — P1 at 90–95% with owners+deadlines, or P2 <80%, or one HIGH risk mitigation pending a documented plan
- **FAIL** — any P0 failure, any HIGH risk unmitigated without waiver, any determinism/dogfood/backward-compat gate red
- **WAIVED** — only for P2/P3 with explicit approver + reason + expiry; no P0 or P1 waivers

## Step 05 — Generate Outputs & Completion

### Execution Mode Resolved

- `tea_execution_mode: auto` (from config)
- Runtime capability: single-agent session (no subagent/agent-team probe needed)
- **Resolved mode: `sequential`**

### Output Files Generated

| File | Purpose | Status |
|---|---|---|
| `skills/test-artifacts/test-design-architecture.md` | Architect-facing concerns, risks, testability gaps (WHAT / WHY) | ✅ Created |
| `skills/test-artifacts/test-design-qa.md` | QA execution recipe, 64 scenarios, execution tiers (HOW) | ✅ Created |
| `skills/test-artifacts/test-design/bmad-skill-compiler-handoff.md` | BMAD integration handoff with per-story test guidance | ✅ Created |
| `skills/test-artifacts/test-design-progress.md` | Full 5-step workflow trace (this file) | ✅ Updated |

### Validation Notes

Checklist compliance:

- ✅ System-level mode two-document pattern (architecture + QA) + handoff
- ✅ Architecture doc focused on concerns/risks (WHAT/WHY); no test scripts, no test level strategy (lives in QA doc), no quality gate criteria (QA doc), no tool selection (QA doc)
- ✅ QA doc has Dependencies near top, Risk Assessment, Entry/Exit Criteria, Coverage Plan (P0–P3 with criteria-only headings), Execution Strategy (PR/Nightly/Weekly tiers), QA Effort Estimate (interval ranges), Interworking & Regression, Appendix A code examples, Appendix B KB refs
- ✅ Handoff doc populated with TEA Artifacts Inventory, Epic + Story-level guidance, risk-to-story mapping, BMAD workflow sequence, phase transition gates
- ✅ Consistent Risk IDs (R-01 … R-20) across all three documents
- ✅ Effort estimates use interval ranges (no false precision)
- ✅ P0/P1/P2/P3 sections describe priority, not execution timing
- ✅ High-risk mitigation plans documented with Owner + Timeline + Verification

Intentional deviations from checklist (flagged):

- **QA doc "Code example" uses Python `unittest`, not playwright-utils.** Checklist specifies playwright-utils example when `tea_use_playwright_utils` is true. Config says true, but project has no browser / HTTP API surface to test — playwright-utils would produce wrong content. Substituted an equivalent `unittest` pattern demonstrating the same principles (subTest parametrization, tmp_path cleanup, explicit assertions). This is the correct call for the project type but deviates from the checklist letter.
- **No "Tooling & Access" beyond baseline GitHub Actions / Python 3.11 / stdlib.** Project ships zero new runtime deps (NFR-S6); no k6, no Pact, no Playwright. Tooling section kept minimal.

### Workflow Complete

Next recommended actions (per skill `bmad-help` guidance):

1. **User review:** walk through the three generated documents, especially the 🚨 BLOCKERS in `test-design-architecture.md` and the Story→Test mapping table in the handoff.
2. **Architecture Review meeting:** validate B-01 / B-02 / B-03 have named story-DoD owners before Sprint 1 starts.
3. **Possible next TEA workflows:** `AT` (ATDD) per epic starting with Epic 1 or 5 (P0-heaviest); or `TF` (test framework) if the golden-file harness needs more detailed scaffolding.
