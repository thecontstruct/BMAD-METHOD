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

# Test Design for QA: BMAD Compiled Skills

**Purpose:** Test execution recipe. What to test, how to test it, what QA needs from other teams.

**Date:** 2026-04-22
**Author:** Murat (TEA) for Shado
**Status:** Draft
**Project:** BMAD Compiled Skills (`tools/installer/compiler/` + `src/scripts/bmad_compile/`)

**Related:** See Architecture doc (`test-design-architecture.md`) for testability concerns and architectural blockers.

---

## Executive Summary

**Scope:** Compile-pipeline testing — template parser, fragment resolution, variable resolver, lockfile, lazy compile-on-entry, drift detection, user-override planes, 3-OS determinism, security containment, perf budgets.

**Risk Summary:**

- Total Risks: 20 (7 high-priority score ≥6, 5 medium, 8 low)
- Critical categories: TECH dominates (determinism + cache coherence siblings); DATA next (lockfile/drift); SEC live-wire on containment

**Coverage Summary:**

- P0 tests: 18 (determinism boundary, security containment, drift, dogfood gate, backward-compat, error taxonomy)
- P1 tests: 24 (resolution cascades, lockfile schema, cross-plane matrix, Appendix A `--explain` schema, module boundary)
- P2 tests: 17 (perf budgets, runtime version checks, trust gate, supply chain)
- P3 tests: 5 (robustness / polish)
- **Total:** 64 scenarios. Effort **~135–245 hours** distributed across Epics 1–7 DoDs.

---

## Not in Scope

| Item | Reasoning | Mitigation |
|---|---|---|
| **LLM-side behavior (post-compile)** | Compiler's contract ends at `SKILL.md` bytes. LLM comprehension is out of scope. | Dogfood loop (R-16) validates the skill recompiles and functions in IDE chat as a smoke-level gate. |
| **npm registry supply-chain attack** | v1 ships zero new runtime deps (NFR-S6); risk addressed by review discipline, not runtime test. | `package.json` diff review gate on release PRs. |
| **Heavy concurrent-install scenarios** | `bmad install` is single-developer or CI-job; concurrent installs explicitly unsupported. | Decision 16 concurrency tests cover lazy-compile guard (the real parallel surface). |
| **External IDE API stability** | Claude Code / Cursor API surfaces are outside compiler scope; shim invokes Python and reads stdout only. | Universal-variant fallback per FR6 / FR44–45. |
| **Accessibility / UI / network testing** | No UI, no HTTP API, no network (NFR-S5). | Trivial network-deny smoke test (P2-08). |

**Note:** items reviewed and accepted as out-of-scope by TEA. Confirm with PM during Architecture Review.

---

## Dependencies & Test Blockers

**CRITICAL:** QA cannot proceed without these items from other teams.

### Backend/Architecture Dependencies (Pre-Implementation)

See Architecture doc "Quick Guide" for full mitigation plans.

1. **B-01: `io.py` raw-I/O linter rule** — Engine lead — Story 1.1 DoD
   - Without automated enforcement, R-01 (determinism drift) is unmeasurable at PR time.
   - Blocks: P0-02 (linter gate test).
2. **B-02: Pre-compiler install baseline tarball** — Installer lead — Story 2.2 DoD
   - Without a committed baseline, NFR-C4 backward-compat claim has no reference to diff against.
   - Blocks: P0-15 (backward-compat gate test).
3. **B-03: Perf-smoke CI harness** — Engine lead — Story 5.x DoD
   - Without it, NFR-P2 / NFR-P5 have no automated gate.
   - Blocks: P2-01, P2-02, P2-03, P2-05 (all perf scenarios).

### QA Infrastructure Setup (Pre-Implementation)

1. **Golden-file harness with `--update-golden`** — QA + Engine lead
   - `test/fixtures/compile/<scenario>/` layout: `input/` + `expected/` + `run.sh`.
   - `python3 src/scripts/compile.py --update-golden <scenario>` regenerates `expected/`; PR shows diff for review.
   - Without regeneration, fixture maintenance is abandoned within a month (per architecture §Test Organization).

2. **Drift scenario family (separate from compile-correctness goldens)** — QA
   - Under `test/fixtures/drift/` with one fixture per (category × positive/negative) plus cross-category.
   - See R-12 mitigation for minimum count.

3. **3-OS CI matrix** — DevOps + Engine lead
   - Linux on every PR; macOS + Windows on merge-to-main, nightly, and release tags.
   - Windows runner must support `mklink /J` (admin rights or developer mode).

4. **Security adversarial fixture builders** — QA
   - Test-time symlink creation (`os.symlink`); Windows-only test creates junction via `subprocess.run(['cmd', '/c', 'mklink', '/J', ...])`.
   - Cleanup discipline: `tmp_path` scoped, no leaked symlinks.

**Example factory pattern (Python stdlib `unittest`, matching architecture §Test Organization — no pytest per NFR-S6):**

```python
# test/python/test_io_boundary.py
import unittest
from pathlib import Path
import tempfile
import os
from bmad_compile.io import read_text, OverrideOutsideRootError

class TestIoBoundary(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bmad-test-")
        self.addCleanup(lambda: __import__('shutil').rmtree(self.tmp, ignore_errors=True))

    def test_override_root_escape_via_dotdot_rejected(self):
        with self.assertRaises(OverrideOutsideRootError):
            read_text(Path(self.tmp) / "custom" / ".." / ".." / "etc" / "passwd",
                      root=Path(self.tmp) / "custom")

    def test_symlink_escape_rejected(self):
        root = Path(self.tmp) / "custom"
        root.mkdir()
        target = Path(self.tmp) / "outside.txt"
        target.write_text("secret", encoding="utf-8")
        link = root / "leak.txt"
        os.symlink(target, link)
        with self.assertRaises(OverrideOutsideRootError):
            read_text(link, root=root)

    def test_crlf_normalized_to_lf_on_read(self):
        f = Path(self.tmp) / "input.md"
        f.write_bytes(b"line1\r\nline2\r\n")
        self.assertEqual(read_text(f, root=Path(self.tmp)), "line1\nline2\n")
```

---

## Risk Assessment

**Note:** full details in Architecture doc. QA-relevant summary below.

### High-Priority Risks (Score ≥6)

| Risk ID | Category | Description | Score | QA Test Coverage |
|---|---|---|---|---|
| **R-01** | TECH | Cross-OS determinism drift | **6** | P0-01 (io.py unit), P0-02 (linter gate), P0-03 (3-OS byte-diff) |
| **R-04** | SEC | Override-root / glob escape | **6** | P0-04, P0-05, P0-06 (adversarial suite, 3-OS incl. Windows junctions) |
| **R-09** | TECH | Lazy-compile guard race | **6** | P0-07, P0-08 (3-OS parallel race + stale-lock reclaim) |
| **R-11** | TECH | Hash-skip false-positive | **6** | P0-09 (parametrized per-input mutation), P0-10 (--debug trace) |
| **R-12** | DATA | Drift dry-run false-negative | **6** | P0-11 (6-category fixtures), P0-12 (cross-category), P0-13 (FR52 E2E) |
| **R-16** | BUS | Dogfood loop breaks | **6** | P0-14 (CI dogfood recompile-diff against baseline) |
| **R-17** | TECH | NFR-C4 backward-compat regression | **6** | P0-15 (install baseline byte-diff) |

### Medium/Low-Priority Risks

| Risk ID | Category | Description | Score | QA Test Coverage |
|---|---|---|---|---|
| R-07 | PERF | Per-skill compile exceeds 500ms | 4 | P2-01 (perf smoke, 1.5× CI budget) |
| R-08 | PERF | Lazy-compile fast-path exceeds 50ms | 4 | P2-02 (perf smoke) |
| R-10 | TECH | Node CLI swallows Python errors | 4 | P0-16 (per-error-code contract via Node CLI) |
| R-18 | TECH | Skill imports engine directly | 4 | P1-22 (directory-scoped lint gate) |
| R-19 | PERF | Glob slow on large repos | 4 | P2-04 (synthetic 10k-file repo) |
| R-02 | DATA | Malformed lockfile silent recovery | 3 | P0-17 (non-zero exit + clear remediation) |
| R-03 | DATA | Lockfile recovery destroys override | 3 | P0-17 (prompt-before-destruction) |
| R-06 | SEC | Plaintext secret in lockfile | 3 | P0-18 (value_hash-only unit) |
| R-05 | SEC | Module shadows core fragment | 2 | P1-16 (install-time collision) |
| R-13 | DATA | Drift false-positive | 2 | absorbed in P0-11 suite |
| R-14 | OPS | Lockfile forward-compat breaks | 2 | P1-14 (unknown-field round-trip) |
| R-15 | OPS | Abandoned session pollution | 2 | P1-15 (FR55) |
| R-20 | TECH | Error missing file/line | 2 | P0-16 |

---

## Entry Criteria

- [ ] All requirements and assumptions agreed by QA, Engineering, PM (via Architecture Review sign-off)
- [ ] B-01 (`io.py` linter rule) in place and CI-enforced
- [ ] B-02 (pre-compiler install baseline) committed
- [ ] B-03 (perf-smoke harness) scaffolded (can be green-fielded; thresholds tune-in later)
- [ ] 3-OS CI matrix configured with Linux per-PR, macOS+Windows on merge-to-main
- [ ] Golden-file harness with `--update-golden` flag implemented (Story 1.1 DoD)
- [ ] `test/fixtures/` directory structure agreed: `compile/`, `drift/`, `security/`, `perf/`

## Exit Criteria

- [ ] All P0 tests passing (100%)
- [ ] P1 pass rate ≥95%; any P1 failure has documented waiver + owner + expiry
- [ ] All 7 HIGH risks (R-01, R-04, R-09, R-11, R-12, R-16, R-17) MITIGATED — non-waivable
- [ ] 3-OS determinism gate green for reference skills (byte-equal)
- [ ] Dogfood gate green (`bmad-customize` skill recompile-diff vs baseline byte-match)
- [ ] Backward-compat gate green (unmigrated-skill install bytes match pre-compiler baseline)
- [ ] No open P0/P1 bugs
- [ ] Flakiness budget ≤2% test-failure-rate / trailing 30 CI runs per test
- [ ] `io.py` coverage ≥95%; overall `bmad_compile/*.py` coverage ≥80%

---

## Test Coverage Plan

**IMPORTANT:** P0/P1/P2/P3 = **priority and risk level** (what to focus on if time-constrained), NOT execution timing. See "Execution Strategy" for when tests run.

### P0 (Critical)

**Criteria:** Blocks core functionality + High risk (≥6) + No workaround + Violates a non-waivable NFR or north-star metric.

| Test ID | Requirement | Test Level | Risk Link | Notes |
|---|---|---|---|---|
| **P0-01** | `io.py` normalizes POSIX paths, converts CRLF→LF, sorts dir listings, rejects escapes | Unit | R-01 | Covers NFR-R1/R2/R3, Decision 10 |
| **P0-02** | Linter rule fails CI on raw `open`/`pathlib` outside `io.py` | Node integration (lint) | R-01 | Blocked by B-01 |
| **P0-03** | 3-OS byte-identical compile of reference skill (macOS/Linux/Windows) | 3-OS determinism | R-01 | Story 2.3 |
| **P0-04** | Override path via `..` or symlink outside root → `OverrideOutsideRootError` | Security adversarial (3-OS) | R-04 | NFR-S2 |
| **P0-05** | Glob pattern matching outside project root → rejected at expansion | Security adversarial (3-OS) | R-04 | NFR-S2 |
| **P0-06** | Windows junction (`mklink /J`) pointing outside project → rejected | Security adversarial (Windows) | R-04 | Admin/dev-mode CI runner |
| **P0-07** | Two parallel lazy-compile guards on same skill: one recompiles, other waits + reads fresh | Python integration (3-OS) | R-09 | Decision 16 |
| **P0-08** | Stale `.compiling.lock` (>5 min) reclaimed with warning | Python integration | R-09 | §Concurrency |
| **P0-09** | Hash-skip fires iff ALL tracked inputs unchanged — mutate each input class, assert no skip | Python integration (parametrized) | R-11 | Decision 12 |
| **P0-10** | `--debug` emits skip/no-skip rationale for audit | Python integration | R-11 | NFR-O5 |
| **P0-11** | Drift dry-run: 6 categories × (positive + negative) = 12 fixtures | Golden (drift family) | R-12 | FR41 |
| **P0-12** | Drift cross-category: glob-input intersecting TOML user override | Golden (drift family) | R-12 | FR41 |
| **P0-13** | E2E lifecycle: install → customize → accept → upstream change → upgrade --dry-run drift → upgrade halts → manual resolve → upgrade succeeds | E2E lifecycle | R-12, R-16 | FR52 |
| **P0-14** | Dogfood gate: CI recompile of `bmad-customize` skill diffs against committed baseline | Node integration (release gate) | R-16 | FR39, NFR-M4 |
| **P0-15** | Install a fixture module with no `*.template.md` → byte-match pre-compiler install baseline | Node integration | R-17 | NFR-C4, blocked by B-02 |
| **P0-16** | 7-code error taxonomy: fixture per code → Node CLI stderr contains `file:line:code + hint`, stdout empty, exit non-zero, no partial writes | Node integration | R-10, R-20 | NFR-M5, NFR-O3, NFR-R4 |
| **P0-17** | Malformed lockfile: non-zero exit + clear remediation + no silent destruction (prompt on user-override conflict) | Python integration | R-02, R-03 | NFR-R5 |
| **P0-18** | Compile with `{{var}}` resolving to `SECRET_VALUE` → `SECRET_VALUE` absent from lockfile; `value_hash` present | Unit | R-06 | NFR-S1 |

**Total P0:** 18 tests.

---

### P1 (High)

**Criteria:** Important features + frozen contract + common workflows. Workaround exists but breaking regresses core user value.

| Test ID | Requirement | Test Level | Risk Link | Notes |
|---|---|---|---|---|
| **P1-01** | Parser: 4 constructs (literal, `<<include>>`, `{{var}}`, `{var}`); unknown directive → `UNKNOWN_DIRECTIVE + file+line` | Unit | R-20 | FR1–7, Decision 1 |
| **P1-02** | Fragment precedence 5-tier: one fixture per adjacent pair + matrix | Golden | — | FR10, NFR-M2 |
| **P1-03** | Cyclic include detection (2-hop + 3-hop) with error chain | Unit | — | FR11 |
| **P1-04** | Variable 8-tier `self.*` + non-`self.` cascades: adjacent-pair + combined matrix | Golden | — | FR16, NFR-M2 |
| **P1-05** | TOML merge: scalars, deep-merge tables, merge-by-key arrays, append arrays | Unit + Golden | — | FR13a |
| **P1-06** | IDE variant selection: Claude Code / Cursor / universal fallback | Golden | — | FR6, FR44–46 |
| **P1-07** | Cross-plane precedence matrix: one golden per architecture §matrix row (7 rows) | Golden | — | Architecture §Cross-Plane Matrix |
| **P1-08** | `PRECEDENCE_UNDEFINED` raised on uncovered plane interaction; message points at matrix | Unit + Golden | — | NFR-M5 |
| **P1-09** | `--explain` schema: Appendix A-conformant `<Include>` / `<Variable>` / `<TomlGlobExpansion>` / `<TomlGlobMatch>` attributes | Golden | — | FR27–31 |
| **P1-10** | `--explain --json` semantically equals Markdown, ordering preserved | Golden | — | FR29 |
| **P1-11** | `--explain --tree` emits tree only, no content | Golden | — | FR28 |
| **P1-12** | `compile --diff`: unified diff, ANSI on TTY, plain on pipe; +100ms budget | Node integration + perf | — | FR26 |
| **P1-13** | Lockfile schema fidelity: every FR40 field present with correct shape | Python integration | — | FR40, FR43 |
| **P1-14** | Lockfile forward-compat: `version: 1` + unknown `future_field: "x"` round-tripped unchanged | Unit | R-14 | NFR-C5 |
| **P1-15** | Abandoned `bmad-customize` session: no files under `_bmad/custom/`, lockfile byte-identical | Node integration | R-15 | FR55 |
| **P1-16** | Third-party module declaring core-path fragment → NAMESPACE_COLLISION at install | Node integration | R-05 | NFR-S3 |
| **P1-17** | `<<include path="core/persona-guard.template.md">>` from non-core skill resolves to core's fragment | Golden | — | FR48 |
| **P1-18** | Compile failure mid-write → no partial files at install location | Python integration | — | NFR-R4 |
| **P1-19** | `bmad upgrade` with drift, no `--yes` → non-zero exit + `bmad-customize` pointer | Node integration | — | FR22, FR57 |
| **P1-20** | `bmad upgrade --yes` proceeds despite drift | Node integration | — | FR22 |
| **P1-21** | `--debug` on every subcommand: `[debug]` to stderr, never stdout | Node integration | — | NFR-O5 |
| **P1-22** | Skill↔compiler lint: any reference to `bmad_compile` or `bmad.lock` from skill dir → lint failure | Node integration (lint) | R-18 | Decision 15 |
| **P1-23** | Distribution Model 1 / 2 / 3 detection + install | Node integration | — | FR47, FR53, Story 7.3 |
| **P1-24** | Runtime placeholder `{var_name}` passthrough (not substituted) | Golden | — | FR5, FR32 |

**Total P1:** 24 tests.

---

### P2 (Medium)

**Criteria:** Secondary features + NFR measurement + edge cases + regression prevention.

| Test ID | Requirement | Test Level | Risk Link | Notes |
|---|---|---|---|---|
| **P2-01** | Per-skill compile ≤500ms (1.5× CI-adjusted ceiling; warn 1.5×, fail 3×) | Perf smoke | R-07 | NFR-P2, blocked by B-03 |
| **P2-02** | Lazy-compile fast-path ≤50ms (1.5× CI-adjusted) | Perf smoke | R-08 | NFR-P5 |
| **P2-03** | Install-time overhead ≤110% of baseline | Perf smoke (nightly) | — | NFR-P1 |
| **P2-04** | Glob on synthetic 10k-file repo: linter warns on overly-broad pattern | Perf + Node integration | R-19 | NFR-P5 guidance |
| **P2-05** | `bmad upgrade --dry-run` streams first drift within 500ms | Perf smoke | — | NFR-P3 |
| **P2-06** | Python <3.11 detected at install-time → clear error | Node integration | — | NFR-C1 |
| **P2-07** | Node <20 detected at install-time → clear error | Node integration | — | NFR-C1 |
| **P2-08** | Compile with network default-denied → succeeds | Python integration | — | NFR-S5 |
| **P2-09** | Release PR diff gate: no new runtime deps in `package.json` or `pyproject.toml` | Node integration | — | NFR-S6 |
| **P2-10** | `--explain` unknown optional attributes tolerated by consumers | Unit | — | Appendix A Stability |
| **P2-11** | Custom Python render function without `trust_mode: full` → install-time rejection | Node integration | — | NFR-S4 |
| **P2-12** | Lockfile `lineage` array appended per upgrade; `previous_base_hash` populated | Python integration | — | FR42, Decision 9 |
| **P2-13** | `bmad upgrade --dry-run --json` is valid JSON consumable by customize mock | Python integration | — | FR21, Story 6.1 |
| **P2-14** | Workflow-scoped `config.yaml` copied verbatim (existing behavior preserved) | Golden | — | Architecture §Technical Constraints |
| **P2-15** | `--lock-timeout-seconds` flag tunes advisory-lock timeout | Python integration | — | FR24 |
| **P2-16** | Each of 7 error codes includes a remediation hint | Unit | R-20 | Error Message Format |
| **P2-17** | Empty-skill smoke: no fragments, no vars, no globs → bare compile + valid lockfile | Golden | — | Boundary |

**Total P2:** 17 tests.

---

### P3 (Low)

**Criteria:** Robustness, exploratory, benchmarks.

| Test ID | Requirement | Test Level | Notes |
|---|---|---|---|
| **P3-01** | Random byte corruption in `bmad.lock` → fail-safe (non-zero + clear message) | Python integration | Chaos-lite |
| **P3-02** | Case-insensitive FS path collision → deterministic ordering | 3-OS determinism | Windows edge |
| **P3-03** | Unicode path names in globs preserved through compile | Golden | Robustness |
| **P3-04** | Very-large TOML layer (>1MB) parses within budget | Perf smoke | Boundary |
| **P3-05** | `--help` output completeness smoke | Node integration | UX polish |

**Total P3:** 5 tests.

---

## Execution Strategy

**Philosophy:** Run everything in PRs unless there's significant infrastructure overhead. Per-PR budget ≤10 min on Linux. 3-OS matrix runs on merge-to-main and nightly, accepting a ~24h blind window for macOS/Windows regressions (costed explicitly by architecture).

Organized by **tier**, not by priority:

### Every PR — Linux-x64 (~5–10 min)

- All **Unit** tests (Python stdlib `unittest`)
- All **Golden** tests (fixture-driven compile)
- All **Python integration** tests except perf and race (including P0-07/P0-08 race smoke on Linux only at PR; full 3-OS on merge)
- All **Node integration** tests (lint gates, boundary tests, CLI contract)
- Every P0 that doesn't require 3 OSes or Windows-only features
- Most P1s
- All P2 non-perf (runtime version checks, network-deny, trust gate)

### PR (conditional) — full 3-OS (~15–20 min)

Triggered when `tools/installer/compiler/**` or `src/scripts/bmad_compile/**` changes:

- 3-OS determinism subset: 2 reference skills byte-diffed across macOS + Linux + Windows
- Concurrency race test (P0-07/P0-08) on all 3 OSes
- Security adversarial suite on all 3 OSes (incl. Windows junction P0-06)

### Merge-to-main (~25–30 min)

Full PR suite + complete 3-OS determinism + full security adversarial + perf smoke:

- All P2 perf (P2-01, P2-02, P2-04, P2-05)
- Full `test/fixtures/compile/` + `test/fixtures/drift/` + `test/fixtures/security/` across 3 OSes
- Lint rules exercised (raw-I/O ban, skill-boundary ban)

### Nightly (~45–60 min)

- Full E2E lifecycle (FR52) — P0-13
- Model 1/2/3 distribution matrix (Story 7.3) — P1-23
- NFR-P1 install-time overhead measurement against historical baseline — P2-03
- P3 robustness tests (chaos, unicode, large TOML)

### Release tag (~75–90 min)

All of the above + release gates:

- Dogfood gate (P0-14)
- Backward-compat gate (P0-15)
- `package.json` / `pyproject.toml` diff review (P2-09)
- Full perf baseline comparison

**Flakiness policy:** any test failing twice in a 7-day rolling window is quarantined; quarantine expires after fix OR 14 days. No opt-in retries. Flakiness treated as a P1 bug, not a CI annoyance (per `test-quality.md`).

---

## QA Effort Estimate

Ranges for QA test authorship only (excludes Engineering time on instrumentation, baseline generation, or fixture infrastructure).

| Priority | Count | Effort Range | Notes |
|---|---|---|---|
| P0 | 18 | **~1.5–2.5 weeks** | Security adversarial + 3-OS CI plumbing are the long poles |
| P1 | 24 | **~1–2 weeks** | Cross-plane matrix (7 rows) + Appendix A schema fixtures dominate |
| P2 | 17 | **~0.5–1 week** | Perf-smoke harness is the main investment |
| P3 | 5 | **~1–3 days** | Opportunistic |
| **Total** | **64** | **~3.5–6 weeks** | **1 QA engineer, full-time** |

**Distribution recommendation:** spread test authorship across Epics 1–7 DoDs rather than a "test at the end" block. Rough per-epic effort:

- Epic 1 (compile pipeline core): ~0.75–1.5 weeks
- Epic 2 (install integration): ~0.5–1 week
- Epic 3 (overrides): ~0.5–0.75 weeks
- Epic 4 (compile primitives): ~0.5–1 week
- Epic 5 (upgrade/drift/lazy): ~0.75–1.25 weeks (drift suite is heaviest)
- Epic 6 (customize skill): ~0.25–0.5 weeks
- Epic 7 (validation/CI/release): ~0.25–0.75 weeks

**Assumptions:**

- Includes test design, implementation, debugging, CI integration
- Excludes ongoing maintenance (~10% buffer)
- Assumes golden-file harness + `--update-golden` flag in place from Story 1.1

**Dependencies from other teams:**

- See "Dependencies & Test Blockers" for B-01 / B-02 / B-03 that gate P0-02 / P0-15 / all perf scenarios.

---

## Implementation Planning Handoff

Work items that need scheduling (beyond normal story test DoDs).

| Work Item | Owner | Target Milestone | Dependencies/Notes |
|---|---|---|---|
| B-01: Implement `io.py` raw-I/O linter rule | Engine lead | Story 1.1 DoD | Grep-based pre-commit hook is simplest; avoids adding Ruff dep (NFR-S6) |
| B-02: Capture + commit pre-compiler install baseline | Installer lead | Story 2.2 DoD | Tarball of `_bmad/` from current `main` on reference config |
| B-03: Scaffold perf-smoke CI harness | Engine lead | Story 5.1 DoD | Reference skill + 10k-file synthetic-repo fixture |
| Create `test/fixtures/drift/` scenario family (separate budget) | QA + Engine lead | Epic 5 | 15+ fixtures; do not count against compile-correctness budget |
| 3-OS CI matrix with Windows `mklink /J` capability | DevOps | Story 2.3 DoD | Windows runner needs dev-mode or admin for junction creation |
| Release-gate dogfood diff for `bmad-customize` skill | Release manager | First release containing Epic 6 | Requires baseline from first successful compile |

---

## Tooling & Access

| Tool | Purpose | Access Required | Status |
|---|---|---|---|
| GitHub Actions Linux/macOS/Windows runners | 3-OS CI matrix | Standard GH workflow permissions + Windows dev-mode for junctions | Pending DevOps confirmation on Windows runner dev-mode |
| Python 3.11+ in CI | Compile engine runtime | `setup-python@v5` in workflow | Available |
| stdlib `unittest`, `hashlib`, `pathlib` | Python testing | stdlib, zero install | Available |
| `jest@30` | Node-side test runner | Already dev-dep in `BMAD-METHOD/package.json` | Available |
| Existing `test/test-installation-components.js` harness | Node integration | Already in repo | Available |

**Access requests needed:**

- [ ] Confirm Windows GH runner can create junctions (may need `actions/setup-windows-dev-mode` or elevated runner) — DevOps
- [ ] Confirm nightly CI schedule slot at 02:00 UTC — DevOps

---

## Interworking & Regression

| Component | Impact | Regression Scope | Validation Steps |
|---|---|---|---|
| **Existing `installer.js` smart-install** | Compiler hooks into `_installAndConfigure()` between `OfficialModules.install()` and `ManifestGenerator.generateManifests()` | Smart-install smoke must still route to `bmad upgrade --dry-run` on existing installs | `test/test-installation-components.js` extended with Model-1 unchanged-module smoke |
| **`files-manifest.csv` writer** | Lockfile is a superset; manifest logic preserved for unmigrated modules | Install output for unmigrated skills byte-identical | P0-15 backward-compat gate |
| **`resolve_customization.py` / `resolve_config.py`** | Refactored into shim over `bmad_compile.toml_merge` (Decision 17) | External consumers (bmad-party-mode, agent-roster) must continue to read stdout as before | Existing upstream test suite ported to shim; PR #2285 central-TOML flow unchanged |
| **Upstream runtime renderer (`bf30b697`)** | REMOVED, replaced by `lazy_compile.py` | Any upstream `{var}` template usage migrates to `{{var}}` or `{{self.*}}` in same PR | Golden fixture per migrated reference skill |
| **Existing `validate-skills` / `validate-refs` npm scripts** | Extended with new `validate:compile` target | Existing validations still pass | `npm run quality` green end-to-end |

**Regression test strategy:**

- Before each release, run full PR suite + merge-to-main suite + nightly suite on release candidate
- Explicit cross-check against upstream `bmad-method` `main` branch test baseline to catch accidental reversions
- Backward-compat gate (P0-15) is the strongest cross-team coordination point — any installer change threatens it

---

## Appendix A: Code Examples & Tagging

**Python `unittest` patterns** (NFR-S6 — no pytest):

```python
# test/python/test_toml_merge.py — parametrized via self.subTest()
import unittest
from bmad_compile.toml_merge import merge_layers

class TestTomlMerge(unittest.TestCase):
    cases = [
        ("scalar_override",
         [{"x": 1}, {"x": 2}],
         {"x": 2}),
        ("deep_merge_table",
         [{"agent": {"name": "base"}}, {"agent": {"icon": "🧪"}}],
         {"agent": {"name": "base", "icon": "🧪"}}),
        ("merge_by_key_array",
         [{"menu": [{"code": "TD", "desc": "old"}]},
          {"menu": [{"code": "TD", "desc": "new"}, {"code": "AT", "desc": "added"}]}],
         {"menu": [{"code": "TD", "desc": "new"}, {"code": "AT", "desc": "added"}]}),
        ("append_array",
         [{"tags": ["a"]}, {"tags": ["b"]}],
         {"tags": ["a", "b"]}),
    ]

    def test_merge_semantics(self):
        for name, layers, expected in self.cases:
            with self.subTest(name):
                self.assertEqual(merge_layers(*layers), expected)
```

**Golden-file fixture layout:**

```
test/fixtures/compile/
    variable-resolution/
        input/
            SKILL.template.md
            customize.toml
            fragments/persona.template.md
        expected/
            SKILL.md
            bmad.lock
            explain.md
        run.sh
```

**Run specific fixtures:**

```bash
# Run all compile goldens
python3 -m unittest test.python.test_goldens

# Regenerate one fixture's expected output after intentional change
python3 src/scripts/compile.py --update-golden variable-resolution

# Run 3-OS determinism check locally (requires Docker for cross-OS simulation, or CI matrix)
npm run test:determinism
```

**Node integration (jest) boundary test example:**

```javascript
// test/test-compile-boundary.js
const { execSync } = require('child_process');
const path = require('path');

describe('Python→Node error propagation', () => {
  test('UNKNOWN_DIRECTIVE surfaces with file+line via Node CLI', () => {
    const fixture = path.join(__dirname, 'fixtures/errors/unknown-directive');
    let stderr = '';
    let status = 0;
    try {
      execSync(`node bmad-cli.js compile ${fixture}`, { stdio: 'pipe' });
    } catch (e) {
      stderr = e.stderr.toString();
      status = e.status;
    }
    expect(status).not.toBe(0);
    expect(stderr).toMatch(/UNKNOWN_DIRECTIVE/);
    expect(stderr).toMatch(/SKILL\.template\.md:\d+/); // file:line
    expect(stderr).toMatch(/hint:/i); // remediation hint
  });
});
```

---

## Appendix B: Knowledge Base References

- **Risk Governance:** `risk-governance.md` — P×I scoring, gate decisions, mitigation workflow
- **Test Priorities Matrix:** `test-priorities-matrix.md` — P0–P3 criteria
- **Test Levels Framework:** `test-levels-framework.md` — unit / integration / E2E selection rules
- **Test Quality DoD:** `test-quality.md` — no hard waits, <300 lines, <1.5 min, self-cleaning
- **ADR Quality Readiness Checklist:** `adr-quality-readiness-checklist.md` — 8 categories, 29 criteria (reframed for non-service context)

---

**Generated by:** BMad TEA Agent (Murat)
**Workflow:** `bmad-testarch-test-design` (System-Level Mode)
**Version:** 4.0 (BMad v6)
