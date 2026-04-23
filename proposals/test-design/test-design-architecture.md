---
workflowStatus: 'completed'
totalSteps: 5
stepsCompleted: ['step-01-detect-mode', 'step-02-load-context', 'step-03-risk-and-testability', 'step-04-coverage-plan', 'step-05-generate-output']
lastStep: 'step-05-generate-output'
nextStep: ''
lastSaved: '2026-04-22'
workflowType: 'testarch-test-design'
inputDocuments:
  - BMAD-METHOD/proposals/bmad-skill-compiler-prd.md
  - BMAD-METHOD/proposals/bmad-skill-compiler-architecture.md
  - BMAD-METHOD/proposals/epics.md
---

# Test Design for Architecture: BMAD Compiled Skills

**Purpose:** Architectural concerns, testability gaps, and ASR requirements for review by the compiler Engineering team. Contract between TEA and Engineering on what must be in place before test development can proceed.

**Date:** 2026-04-22
**Author:** Murat (TEA) for Shado
**Status:** Architecture Review Pending
**Project:** BMAD Compiled Skills (`tools/installer/compiler/` + `src/scripts/bmad_compile/`)
**PRD Reference:** `BMAD-METHOD/proposals/bmad-skill-compiler-prd.md`
**ADR Reference:** `BMAD-METHOD/proposals/bmad-skill-compiler-architecture.md` (18 decisions)

---

## Executive Summary

**Scope:** Compile-pipeline for BMAD skills — template parser (Node+Python), 5-tier fragment resolution, 8-tier variable cascade, lockfile-as-audit-trail, lazy compile-on-entry guard, user override planes (prose / TOML / YAML / full-skill), drift triage via `bmad-customize` skill. 7 epics, ~30 stories.

**Business Context** (from PRD):

- **North-star metric:** zero silent loss of user overrides across upgrades.
- **Problem:** Today there's no way to customize a BMAD skill without forking it; upgrades overwrite customizations.
- **GA launch:** v1 scoped to 3–5 migrated reference skills + `bmad-customize` dogfood. No date in PRD.

**Architecture** (highlights from ADR):

- **Decision 10 — I/O sandbox:** all determinism-sensitive I/O through `src/scripts/bmad_compile/io.py`; linter ban on raw file ops elsewhere.
- **Decision 11 — Frozen error taxonomy:** 7 error codes, file+line+code+remediation-hint in every message.
- **Decision 16 — Lazy compile-on-entry:** cache-coherence guard replaces upstream's runtime renderer; advisory file-lock on `.compiling.lock`.
- **Decision 15 — Two-layer split:** mechanical (CLI) vs reasoning (`bmad-customize` skill). Skill's only inputs are 3 CLI commands. Hard architectural boundary.

**Expected Scale:** single-developer / CI job; no server load. Per-skill compile ≤500ms; lazy fast-path ≤50ms; install-time overhead ≤110% of pre-compiler baseline.

**Risk Summary:**

- **Total risks identified:** 20
- **High-priority (score ≥6):** 7 (R-01, R-04, R-09, R-11, R-12, R-16, R-17)
- **Critical (score = 9):** 0 — architecture's determinism-boundary + frozen-vocabulary discipline defuses catastrophic scenarios
- **Test effort:** 64 scenarios spread across Epics 1–7 (distributed via story DoDs)

---

## Quick Guide

### 🚨 BLOCKERS — Team Must Decide (Can't Proceed Without)

Pre-implementation critical path. These must land in Story 1.x / 2.x DoDs or downstream test design collapses.

1. **B-01: Linter rule banning raw I/O outside `io.py`.** Architecture states *"repo Python linter config bans raw file operations in `bmad_compile/`"* — no specific rule cited. Without automated enforcement, NFR-R1 (byte-for-byte determinism) depends on reviewer diligence. (recommended owner: Engine lead; Story 1.1 DoD)
2. **B-02: Committed pre-compiler baseline for NFR-C4 regression gate.** "Byte-for-byte identical install for unmigrated skills" is an explicit NFR, but no baseline artifact exists in the repo today. Without it, R-17 has no measurement and the backward-compat claim is unfalsifiable. (recommended owner: Installer lead; Story 2.2 DoD)
3. **B-03: Perf-budget CI harness for NFR-P2 / NFR-P5.** 500ms per-skill and 50ms lazy-fast-path are committed NFRs. "Mid-2021 laptop" is a human reference, not CI. No perf gate exists in the architecture document; regressions will surface only via user reports. (recommended owner: Engine lead; Story 5.x DoD — bundled with lazy-compile work)

**What we need from team:** Confirm each B-item has a named story + DoD owner before Sprint 1 starts. If engineering disagrees that any of these should block, document the rationale so we can rescore the underlying risk.

---

### ⚠️ HIGH PRIORITY — Team Should Validate (Recommendation Provided, Approval Needed)

Architectural judgment calls where TEA has a recommendation but engineering owns the final call.

1. **R-09: 3-OS concurrency race coverage.** Windows `msvcrt.locking` semantics differ from POSIX `flock`. Architecture plans `test_concurrent_compile.py` — TEA recommends this test runs on *all 3 OSes* in the merge-to-main matrix (not Linux-only). Implicit today in architecture §Test Organization but not explicit. (recommended approver: Engine lead)
2. **R-04: Adversarial security suite on Windows.** Override-root containment is NFR-S2. Windows junction points (`mklink /J`) are a known historical escape path that POSIX-only test matrices miss. TEA recommends the security adversarial suite include a Windows-only junction fixture. (recommended approver: Security reviewer)
3. **R-12: Drift category scenario scope.** Architecture §Test Organization targets "~8–15 total goldens" across all behaviors. FR41 defines 6 drift categories × (positive + negative + cross-category) ≈ 15+ cases just for drift. TEA recommends drift fixtures be a *separate* scenario family from compile-correctness goldens, with dedicated budget. (recommended approver: Engine lead)
4. **R-16: Dogfood gate enforcement in release CI.** FR39 makes `bmad-customize` skill compilable by the same compiler. NFR-M4 names reference skills as contract tests. TEA recommends the skill-compile-diff-against-baseline is an explicit *release-blocking* gate, not "nightly flakes acceptable". (recommended approver: Release manager)

**What we need from team:** Review, approve, or propose alternative.

---

### 📋 INFO ONLY — Solutions Provided (Review, No Decisions Needed)

1. **Test strategy:** 64 scenarios across 8 levels (Unit, Golden, Python integration, Node integration, E2E lifecycle, 3-OS determinism, Perf smoke, Security adversarial). Detailed in QA doc.
2. **Tooling:** stdlib `unittest` for Python (NFR-S6 bans pytest); jest for Node; golden-file harness with `--update-golden` regeneration. No new runtime deps.
3. **Execution tiers:** PR-fast → PR-full (on compiler changes) → merge-to-main → nightly → release. See QA doc §Execution Strategy.
4. **Coverage split:** 18 P0 / 24 P1 / 17 P2 / 5 P3 = 64 total.
5. **Quality gates:** P0=100%, P1≥95%, all 7 HIGH risks mitigated before release (non-waivable), 3-OS byte-equal, dogfood + backward-compat baselines byte-match.

**What we need from team:** Acknowledge; deep detail lives in the QA doc.

---

## For Architects and Devs — Open Topics 👷

### Risk Assessment

**Total risks identified:** 20 (7 high-priority score ≥6, 5 medium, 8 low).

#### High-Priority Risks (Score ≥6) — Immediate Attention

| Risk ID | Category | Description | P | I | Score | Mitigation | Owner | Timeline |
|---|---|---|---|---|---|---|---|---|
| **R-01** | TECH | Cross-OS determinism drift — raw `open()`/`pathlib` call outside `io.py` leaks path/newline/order differences into compiled output | 2 | 3 | **6** | Enforced linter rule (B-01) + 3-OS CI matrix + nightly macOS/Win | Engine lead | Before Epic 2 completes |
| **R-04** | SEC | Override-root / glob escape via symlink, Windows junction, or `..` path — content injection or exfil | 2 | 3 | **6** | `Path.resolve(strict=True)` + ancestor-containment in `io.py` + 3-OS adversarial suite incl. Windows junctions | Security reviewer + Engine lead | Before first security-relevant release |
| **R-09** | TECH | Lazy-compile guards race on parallel IDE invocations → wrong bytes to LLM | 2 | 3 | **6** | Advisory lock on `.compiling.lock` + atomic temp+rename + 3-OS race test + stale-lock reclaim | Engine lead | Epic 5 |
| **R-11** | TECH | Hash-skip false-positive — untracked input changes but skip engages → stale output served | 2 | 3 | **6** | Hash composition review + per-tracked-input mutation regression test + `--debug` rationale | Engine lead | Epic 1 |
| **R-12** | DATA | Drift dry-run false-negative → upgrade silently loses user override (violates north-star metric) | 2 | 3 | **6** | Dedicated drift scenario suite (6 categories × pos/neg/cross) + E2E lifecycle FR52 | Engine lead + TEA | Epic 5 |
| **R-16** | BUS | Dogfood loop breaks — compiler refactor makes `bmad-customize` skill uncompilable → release blocked | 2 | 3 | **6** | Every CI run recompiles skill against committed baseline; release-gate | Release manager | Every release |
| **R-17** | TECH | NFR-C4 regression — unmigrated-skill install bytes differ from pre-compiler baseline | 2 | 3 | **6** | Committed pre-compiler install tarball (B-02) + CI diff gate | Installer lead | Before Epic 2 completes |

#### Medium-Priority Risks (Score 3–5)

| Risk ID | Category | Description | P | I | Score | Mitigation | Owner |
|---|---|---|---|---|---|---|---|
| R-07 | PERF | Per-skill recompile exceeds NFR-P2 500ms budget | 2 | 2 | 4 | Perf-smoke CI job (B-03), 1.5× CI-adjusted budget | Engine lead |
| R-08 | PERF | Lazy-compile fast path exceeds NFR-P5 50ms — every LLM turn pays | 2 | 2 | 4 | Author guidance on narrow globs + CI linter warning + perf smoke | Engine lead |
| R-10 | TECH | Cross-language boundary swallows Python errors → "compile failed" without file/line (NFR-O3 regression) | 2 | 2 | 4 | Per-error-code contract test through Node CLI | CLI adapter lead |
| R-18 | TECH | `bmad-customize` skill violates Decision 15 boundary — future helper script imports engine directly | 2 | 2 | 4 | Directory-scoped lint rule: no `bmad_compile` imports or `bmad.lock` refs from skill dir | Architecture reviewer |
| R-19 | PERF | Glob expansion slow on large repos (`{project-root}/**/*` patterns) | 2 | 2 | 4 | Author guidance documented in NFR-P5 + CI linter warns on broad patterns | Engine lead |

#### Low-Priority Risks (Score 1–2)

| Risk ID | Category | Description | P | I | Score | Action |
|---|---|---|---|---|---|---|
| R-02 | DATA | Malformed-lockfile silent recovery | 1 | 3 | 3 | Monitor (test covers) |
| R-03 | DATA | Malformed-lockfile recovery destroys user override | 1 | 3 | 3 | Monitor (prompt-before-destruction test) |
| R-05 | SEC | Module shadows core fragment (NFR-S3) | 1 | 2 | 2 | Monitor (install-time collision test) |
| R-06 | SEC | Plaintext secret leaked to lockfile | 1 | 3 | 3 | Monitor (value-hash-only unit test) |
| R-13 | DATA | Drift false-positive — annoys users | 2 | 1 | 2 | Monitor (same suite as R-12) |
| R-14 | OPS | Lockfile v1 forward-compat breaks on unknown fields | 1 | 2 | 2 | Monitor (round-trip test) |
| R-15 | OPS | Abandoned `bmad-customize` session pollutes `_bmad/custom/` | 1 | 2 | 2 | Monitor (FR55 test) |
| R-20 | TECH | Error missing file/line (NFR-O3 regression) | 1 | 2 | 2 | Monitor (per-code contract test) |

#### Risk Category Legend

- **TECH**: Technical/architecture (determinism, integration, cache coherence)
- **SEC**: Security (containment, escape, secret handling)
- **PERF**: Performance (NFR-P2/P5 budgets, glob cost)
- **DATA**: Lockfile/override-state integrity (drift, corruption, destruction)
- **BUS**: Business/product (dogfood gate, release blockers)
- **OPS**: Deployability/forward-compat/hygiene

---

### Testability Concerns and Architectural Gaps

**🚨 ACTIONABLE CONCERNS — Architecture Team Must Address**

#### 1. Blockers to Fast Feedback (WHAT WE NEED FROM ARCHITECTURE)

| Concern | Impact on Testing | What Architecture Must Provide | Owner | Timeline |
|---|---|---|---|---|
| **`io.py` linter ban documented but not automated** | NFR-R1 depends on reviewer diligence; any raw `open()` merge leaks non-determinism into the lockfile as phantom drift | Automated lint rule (e.g., Ruff custom or grep pre-commit hook) wired into `npm run lint` / `quality` gate | Engine lead | Story 1.1 DoD |
| **Pre-compiler install baseline doesn't exist** | NFR-C4 backward-compat claim is unfalsifiable without a reference artifact to diff against | Committed tarball of current `_bmad/` install output for reference config + CI diff job | Installer lead | Story 2.2 DoD |
| **No perf-budget CI harness** | NFR-P2 (500ms) and NFR-P5 (50ms) are committed NFRs with no automated gate | Perf-smoke job with reference skill + large-repo synthetic fixture; warn at 1.5× real budget, fail at 3× | Engine lead | Story 5.x DoD |

#### 2. Architectural Improvements Needed (WHAT SHOULD BE CHANGED)

1. **Drift scenario budget needs separation from compile-correctness budget.**
   - **Current problem:** Architecture §Test Organization targets ~8–15 total golden scenarios. FR41's 6 drift categories × (positive/negative/cross-category) needs ~15+ cases alone.
   - **Required change:** Carve drift goldens into their own scenario family under `test/fixtures/drift/`; don't count them against the compile-correctness target.
   - **Impact if not fixed:** Drift coverage is the direct protection against the north-star-metric violation (silent override loss). Under-budgeting it is the highest-leverage mistake available in v1.
   - **Owner:** Engine lead + TEA
   - **Timeline:** Epic 5

2. **3-OS CI matrix should be explicit for concurrency tests.**
   - **Current problem:** Architecture §Concurrency mentions `test_concurrent_compile.py` but the 3-OS schedule in §Test Organization reads "Linux per-PR, macOS+Windows on merge/nightly" — applied to *all* tests generically.
   - **Required change:** Add per-OS concurrency test to the merge-to-main matrix explicitly; Windows `msvcrt.locking` is not a POSIX drop-in and advisory-lock semantics differ.
   - **Impact if not fixed:** R-09 (lazy-compile race) becomes un-measurable on Windows until a user complaint.
   - **Owner:** Engine lead
   - **Timeline:** Epic 5

3. **`bmad-customize` skill ↔ compiler boundary needs an architectural lint.**
   - **Current problem:** Decision 15 makes the skill's *only* compiler inputs 3 CLI commands. Skill is authored Markdown, read by an LLM — no import-time enforcement exists. A future helper script inside the skill dir could break the boundary silently.
   - **Required change:** Directory-scoped lint: any file under the skill's source directory referencing `bmad_compile` module path, `bmad.lock` path, or Python `import bmad_compile` → fail.
   - **Impact if not fixed:** Boundary erodes over time; test contract (Story 6.1 mock) becomes fiction.
   - **Owner:** Architecture reviewer
   - **Timeline:** Epic 6

---

### Testability Assessment Summary

**📊 CURRENT STATE — FYI**

#### What Works Well

- Determinism surface confined to one file (`io.py`) — smallest possible audit target.
- Lockfile-as-single-source-of-truth means every test assertion can read the lockfile, not source files — trivially stable anchor.
- `--explain --json` provenance + frozen Appendix A schema = machine-readable goldens that don't break on unrelated changes.
- Frozen error taxonomy (7 codes) means tests assert `code`, not brittle message strings.
- Golden-file harness with `--update-golden` regeneration is a proven sustainable pattern.
- Named test fixtures already planned: FR52 E2E lifecycle, FR55 abandoned-session, Story 2.3 3-OS determinism, Story 6.1 mock-contract, Story 7.3 Model 3 distribution.

#### Accepted Trade-offs (No Action Required)

- **Linux-only per-PR CI, macOS+Windows on merge/nightly.** Architecture costed this explicitly: up to 24h blind to cross-OS regressions, traded against ~6 min × every PR. Accepted given the `io.py` boundary is the only cross-OS drift surface.
- **No pytest (NFR-S6).** stdlib `unittest` with `self.subTest()` parametrization is verbose but dependency-free. Accepted as the supply-chain hygiene cost.
- **No runtime perf telemetry.** v1 has no production telemetry because there's no production — it's a local tool. Perf enforcement via CI perf smoke only.

---

### Risk Mitigation Plans (High-Priority Risks ≥6)

#### R-01: Cross-OS determinism drift (Score: 6) — HIGH

**Mitigation Strategy:**

1. Implement Python linter rule banning `open`, `pathlib.Path.open`, `os.listdir`, `os.scandir`, and direct `pathlib.Path(...).read_text()` imports outside `src/scripts/bmad_compile/io.py`. Candidate: Ruff custom rule or a grep-based pre-commit hook (simpler, zero new deps).
2. Wire the rule into `npm run lint` / `npm run quality` so CI fails on violation, not just review.
3. Add the 3-OS determinism job (Story 2.3) to merge-to-main and nightly CI; reference-skill set compiled on all 3, byte-diffed.
4. Re-run the boundary check quarterly as a health probe.

**Owner:** Engine lead
**Timeline:** B-01 by end of Epic 1; 3-OS CI by end of Epic 2
**Status:** Planned
**Verification:** attempt a raw `open()` call in any `bmad_compile/` module — CI fails. Byte-diff of reference compile on 3 OSes shows zero difference.

#### R-04: Override-root / glob escape (Score: 6) — HIGH

**Mitigation Strategy:**

1. `io.py` centralizes `Path.resolve(strict=True)` + ancestor-containment check for every path crossing the override-root / install-root / project-root boundaries.
2. Security adversarial test suite under `test/python/security/` with fixtures for: `..`-traversal, symlink-to-outside, symlink-chain, Windows junction (`mklink /J`) on Windows runner, NFS/SMB mount-point escape (Linux runner).
3. Each fixture asserts `OverrideOutsideRootError` raised and zero bytes written.
4. Security reviewer signs off before first release containing override-root code paths.

**Owner:** Security reviewer + Engine lead
**Timeline:** End of Epic 3
**Status:** Planned
**Verification:** adversarial suite green on all 3 OSes; manual penetration check by security reviewer against reference install.

#### R-09: Lazy-compile guard race (Score: 6) — HIGH

**Mitigation Strategy:**

1. Advisory file-lock on `.compiling.lock` (POSIX `fcntl.flock` / Windows `msvcrt.locking`) per Decision 16.
2. Atomic write: temp file + `os.replace` on success only. Readers never see partial state.
3. 3-OS race test: `test/python/integration/test_concurrent_compile.py` spawns two `subprocess.run` invocations of `lazy_compile.py` for the same skill; asserts exactly one recompile occurs, the other waits-and-reads fresh bytes.
4. Stale-lock reclaim test at the documented 5-min threshold.

**Owner:** Engine lead
**Timeline:** End of Epic 5
**Status:** Planned
**Verification:** race test green on macOS, Linux, Windows in merge-to-main matrix.

#### R-11: Hash-skip false-positive (Score: 6) — HIGH

**Mitigation Strategy:**

1. Review hash composition (source + fragments + variables + variant + glob match-set + per-match content) in design review; ensure no tracked input omitted from hash.
2. Parametrized regression test: for each tracked-input class, mutate one input and assert hash-skip does NOT engage.
3. `--debug` emits skip/no-skip rationale (listing which hash differs) for audit.

**Owner:** Engine lead
**Timeline:** End of Epic 1 (hash lands) + Epic 5 (lazy-compile composes with it)
**Status:** Planned
**Verification:** parametrized test passes; manual `--debug` trace inspection on reference skill.

#### R-12: Drift dry-run false-negative (Score: 6) — HIGH

**Mitigation Strategy:**

1. Dedicated drift scenario family under `test/fixtures/drift/` — budget independent of compile-correctness goldens.
2. Minimum coverage: 6 categories (prose, TOML default, TOML orphan, TOML new-default, glob-input, variable-provenance) × (positive + negative) = 12 fixtures, plus 3+ cross-category fixtures (e.g., glob-input drift intersecting TOML user override).
3. E2E lifecycle test (FR52) exercises the full loop: install → customize → accept → simulate upstream change → `upgrade --dry-run` shows drift → `upgrade` halts → manual resolve → re-run `upgrade` succeeds → lockfile records lineage.
4. Any drift-category miss is treated as a P0 bug (north-star-metric violation).

**Owner:** Engine lead + TEA
**Timeline:** End of Epic 5
**Status:** Planned
**Verification:** 15+ drift fixtures green + FR52 E2E green.

#### R-16: Dogfood loop breaks (Score: 6) — HIGH

**Mitigation Strategy:**

1. CI recompiles `bmad-customize` skill on every PR; diff against committed baseline.
2. Baseline regenerates only on explicit PR intent (requires reviewer sign-off) — not on routine compile changes.
3. Release-blocking gate: any unexpected diff fails the release PR.

**Owner:** Release manager
**Timeline:** Every release from Epic 6 onward
**Status:** Planned
**Verification:** inspect release PR; dogfood-diff gate visible in CI log.

#### R-17: NFR-C4 backward-compat regression (Score: 6) — HIGH

**Mitigation Strategy:**

1. Commit pre-compiler install tarball (`test/fixtures/baseline/pre-compiler-install.tar`) covering a reference module config with no `*.template.md` files.
2. CI install job produces current output, compares byte-for-byte to baseline.
3. Baseline regenerates only on an explicit intentional-divergence PR (approved by installer lead + release manager).

**Owner:** Installer lead
**Timeline:** Story 2.2 DoD
**Status:** Planned
**Verification:** CI install-baseline-diff job green on every PR.

---

### Assumptions and Dependencies

#### Assumptions

1. The `io.py` determinism boundary remains the single cross-OS drift surface. No new module under `bmad_compile/` introduces direct filesystem access.
2. Windows runner availability in CI (GitHub Actions `windows-latest`) remains stable for the merge-to-main matrix. If runner cost becomes prohibitive, Windows shifts to nightly-only (would downgrade R-09 detection window).
3. The reference skill set for 3-OS determinism testing is stable (not rotated every sprint). Churn in reference skills invalidates accumulated baselines.
4. `bmad-customize` skill's LLM-consumer-only design remains architectural law (no embedded Python helpers). Breaking this invalidates Decision 15's test strategy.

#### Dependencies

1. **`io.py` linter rule** — required before Story 1.1 is Done (B-01).
2. **Pre-compiler install baseline** — required before Story 2.2 is Done (B-02).
3. **Perf-smoke CI harness** — required before Story 5.x lazy-compile work is Done (B-03).
4. **Reference skill set committed** — required before 3-OS determinism CI can run (Story 2.3).
5. **`bmad-customize` skill compilable baseline** — required before release-gate dogfood diff can run (Epic 6 completion).

#### Risks to Plan

- **Risk:** Architecture §Test Organization targets "~8–15 goldens" and "3-OS on merge only" — if applied uniformly, drift coverage is under-scoped (see R-12 mitigation).
  - **Impact:** Silent override loss in production (north-star violation).
  - **Contingency:** TEA escalation — carve drift into a separate scenario family; if refused, score R-12 to P=3 and re-evaluate gate thresholds.
- **Risk:** Windows CI runner flakiness (historical — junction creation requires admin in some configurations).
  - **Impact:** R-04 adversarial tests become informational rather than blocking.
  - **Contingency:** document any skipped Windows scenarios in the gate decision; require manual penetration check by security reviewer in the interim.

---

**End of Architecture Document**

**Next Steps for Architecture Team:**

1. Review Quick Guide; confirm B-01 / B-02 / B-03 have named story DoDs.
2. Approve or propose alternatives for the 4 HIGH PRIORITY items.
3. Validate assumptions above; flag any that don't hold.
4. Provide feedback to TEA on the Architectural Improvements (drift budget separation, 3-OS concurrency, skill-boundary lint).

**Next Steps for QA Team:**

1. Wait for B-01 / B-02 / B-03 DoD confirmations before test implementation begins.
2. Refer to companion QA doc (`test-design-qa.md`) for test scenarios and execution strategy.
3. Begin test infrastructure setup (golden-file harness, `--update-golden` regeneration flag, Node-integration jest config for boundary tests).
