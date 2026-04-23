---
title: 'TEA Test Design → BMAD Handoff Document'
version: '1.0'
workflowType: 'testarch-test-design-handoff'
inputDocuments:
  - BMAD-METHOD/proposals/bmad-skill-compiler-prd.md
  - BMAD-METHOD/proposals/bmad-skill-compiler-architecture.md
  - BMAD-METHOD/proposals/epics.md
sourceWorkflow: 'testarch-test-design'
generatedBy: 'TEA Master Test Architect (Murat)'
generatedAt: '2026-04-22'
projectName: 'BMAD Compiled Skills'
---

# TEA → BMAD Integration Handoff

## Purpose

Bridges TEA's system-level test design outputs with BMAD's implementation workflow. Provides structured guidance so that quality requirements, risk assessments, and test strategies flow into per-story DoDs across Epics 1–7. **Epics already exist in `BMAD-METHOD/proposals/epics.md`** — this handoff provides per-epic / per-story test guidance layered on top, not an epic regeneration.

## TEA Artifacts Inventory

| Artifact | Path | BMAD Integration Point |
|---|---|---|
| Test Design — Architecture view | `skills/test-artifacts/test-design-architecture.md` | Epic quality requirements, pre-implementation blockers (B-01/B-02/B-03) |
| Test Design — QA view | `skills/test-artifacts/test-design-qa.md` | Story acceptance criteria, test scenarios (64), execution strategy |
| Test Design Progress | `skills/test-artifacts/test-design-progress.md` | Full workflow trace (5-step process output) |
| Risk Register | (embedded in test-design-architecture.md) | Epic risk classification, story priority escalation |
| Coverage Strategy | (embedded in test-design-qa.md) | Story test requirements per epic |

## Epic-Level Integration Guidance

### Risk References — P0/P1 Risks Per Epic

The 7 HIGH risks map to epics as follows. Each epic's DoD should include explicit coverage for the risk(s) below.

| Epic | High Risks Addressed | Implementation Notes |
|---|---|---|
| **Epic 1 — Compile Pipeline & Authoring Syntax** | R-01, R-11 | B-01 (io.py linter) MUST land in Story 1.1 DoD. Hash composition (Decision 12) MUST be reviewed in Story 1.5 with R-11 mitigation attached. |
| **Epic 2 — Install Integration & First Migrated Skill** | R-01, R-17 | B-02 (pre-compiler baseline) MUST land in Story 2.2 DoD. 3-OS determinism matrix MUST be wired in Story 2.3. |
| **Epic 3 — User Overrides Across Three Planes** | R-04 | Security adversarial suite (symlink / junction / `..`) MUST land alongside override-root code paths. Story 3.4 & 3.5 DoDs. |
| **Epic 4 — Compile Inspection Primitives** | (no high risks; R-18 monitoring only) | Appendix A schema fixtures are the heavy lift here; consumer-tolerance tests for unknown optional attributes. |
| **Epic 5 — Upgrade, Drift & Lazy-Compile** | R-09, R-12, R-08 (medium) | B-03 (perf-smoke harness) MUST land in Story 5.1. Drift scenario family MUST be separate from compile-correctness budget. |
| **Epic 6 — Interactive `bmad-customize` Skill** | R-16, R-18 (medium) | Skill-boundary lint MUST land alongside Story 6.1 mock contract. Dogfood baseline captured at first successful compile. |
| **Epic 7 — Validation, CI, Release Gates** | R-16, R-17 (release gates) | Dogfood gate + backward-compat gate MUST be release-blocking. FR52 E2E lifecycle test owned here. |

### Quality Gates Per Epic

| Epic | Epic-Completion Gate |
|---|---|
| Epic 1 | B-01 in place; all P0 unit/golden tests for parser, resolver, io.py green on Linux; hash-composition review documented |
| Epic 2 | B-02 baseline committed; P0-15 backward-compat gate green; 3-OS determinism matrix (P0-03) green on reference skill set |
| Epic 3 | Full security adversarial suite (P0-04, P0-05, P0-06) green on 3 OSes; NFR-S3 module-boundary test (P1-16) green |
| Epic 4 | Appendix A schema goldens (P1-09, P1-10, P1-11) green; `compile --diff` contract (P1-12) green |
| Epic 5 | B-03 perf harness online; drift scenario family (P0-11, P0-12) 100% green; lazy-compile race test (P0-07, P0-08) green on 3 OSes |
| Epic 6 | Skill-boundary lint (P1-22) in place; Story 6.1 mock contract green; dogfood baseline captured |
| Epic 7 | FR52 E2E lifecycle (P0-13) green; release-gate dogfood diff (P0-14) and backward-compat gate (P0-15) both wired as release-blocking |

## Story-Level Integration Guidance

### P0 Test Scenarios → Story Acceptance Criteria

Every story below should include the listed P0 test(s) as explicit acceptance criteria in its DoD. Test IDs reference the coverage matrix in `test-design-qa.md`.

| Story | P0 Acceptance Criteria | TEA Test IDs |
|---|---|---|
| **Story 1.1** Bootstrap | io.py normalizes paths, converts CRLF→LF, rejects escapes; linter rule CI-enforced; secret-leak guard | P0-01, P0-02, P0-18 |
| **Story 1.2** Fragment Resolution + Cycle Detection | (P1) precedence golden per adjacent pair; cyclic include detected | P1-02, P1-03 |
| **Story 1.3** Variable Interpolation + Passthrough | (P1) 8-tier cascade golden; runtime passthrough preserved | P1-04, P1-24 |
| **Story 1.4** IDE Variant + Error Taxonomy | Error taxonomy per-code contract via Node CLI | P0-16 |
| **Story 1.5** Lockfile v1 Writer | Hash-skip mutation test per input class; `--debug` emits rationale; (P1) lockfile schema fidelity + forward-compat | P0-09, P0-10, P1-13, P1-14 |
| **Story 2.1** Node Installer Hook | (P1) `compile --diff` contract | P1-12 |
| **Story 2.2** `bmad-help` Reference Skill | Backward-compat byte-match against baseline | P0-15 |
| **Story 2.3** 3-OS Determinism CI Matrix | 3-OS byte-identical compile of reference set | P0-03 |
| **Story 3.1–3.3** Overrides | (P1) cross-plane matrix goldens (7 rows) | P1-05, P1-07, P1-08 |
| **Story 3.4** Full-Skill Escape Hatch | Full-skill replacement wins for prose, TOML continues layering (matrix row) | P1-07 (relevant row) |
| **Story 3.5** Override-Root Containment + Glob Security | Override escape adversarial (3 OSes incl. Windows junction) | P0-04, P0-05, P0-06 |
| **Story 4.2** `--explain` with XML tags | Appendix A `<Include>` / `<Variable>` schema goldens | P1-09 |
| **Story 4.3** `--explain --tree` and `--json` | JSON equivalence + tree-only | P1-10, P1-11 |
| **Story 5.1** `bmad upgrade --dry-run` | Dry-run streams first drift <500ms; halt-on-drift exit | P2-05, P1-19, P1-20 |
| **Story 5.2** Halt-on-Drift + Auto-Routing | (P1) `--yes` escape works | P1-20 |
| **Story 5.4** Lazy-Compile Cache Coherence | Hash-dispatch correctness; glob-drift detection | P0-09, P0-10 |
| **Story 5.5** Lazy-Compile Concurrency | Parallel guard race + stale-lock reclaim on 3 OSes | P0-07, P0-08 |
| **Story 6.1** Compiler-Primitive Mock Contract | Mock contract + skill-boundary lint | P1-22 |
| **Story 6.4** Conversational Drafting (no-write-until-accept) | FR54 contract upheld — drafting produces no files | (covered by P1-15 at epic close) |
| **Story 6.5** Post-Accept Write + `--diff` Verification | Accept flow writes to correct path; `--diff` surfaces impact | (integration via Story 7.2) |
| **Story 7.2** E2E Customization Lifecycle Integration | FR52 full loop | P0-13 |
| **Story 7.3** Model 3 Distribution Matrix | All 3 models install equivalently | P1-23 |
| **Story 7.4** Abandoned Session Test | FR55 — no pollution, lockfile byte-identical | P1-15 |
| **Story 7.5** Docs + Dogfood Gate | Dogfood recompile-diff as release gate | P0-14 |
| **Story 7.6–7.7** Module Distribution + Dogfood | Third-party module migration smoke | P1-23 (extended) |

### Data-TestId Requirements

N/A — this is a CLI / compile-pipeline project. No UI elements. Testability hooks come from:

- **CLI flags:** `--explain`, `--json`, `--debug`, `--diff` are the programmatic observation surface.
- **Lockfile fields:** `bmad.lock` is the primary assertion target.
- **Error codes:** 7-member frozen enum (`UNKNOWN_DIRECTIVE`, `UNRESOLVED_VARIABLE`, `MISSING_FRAGMENT`, `CYCLIC_INCLUDE`, `OVERRIDE_OUTSIDE_ROOT`, `LOCKFILE_VERSION_MISMATCH`, `PRECEDENCE_UNDEFINED`) — tests assert code, not message.

## Risk-to-Story Mapping

| Risk ID | Category | P×I | Recommended Story/Epic | Test Level |
|---|---|---|---|---|
| R-01 | TECH | 2×3=6 | Story 1.1 (io.py) + Story 2.3 (3-OS CI) | Unit + 3-OS determinism |
| R-02 | DATA | 1×3=3 | Story 1.5 (lockfile writer) | Python integration |
| R-03 | DATA | 1×3=3 | Story 1.5 (lockfile writer) + Story 3.5 (override containment) | Python integration |
| R-04 | SEC | 2×3=6 | Story 3.5 (override containment + glob security) | Security adversarial (3-OS) |
| R-05 | SEC | 1×2=2 | Story 3.4 (module boundary) | Node integration |
| R-06 | SEC | 1×3=3 | Story 1.5 (lockfile writer) | Unit |
| R-07 | PERF | 2×2=4 | Story 5.1 (dry-run perf) + perf harness | Perf smoke |
| R-08 | PERF | 2×2=4 | Story 5.4 (lazy-compile fast-path) | Perf smoke |
| R-09 | TECH | 2×3=6 | Story 5.5 (concurrency + advisory locks) | Python integration (3-OS) |
| R-10 | TECH | 2×2=4 | Story 1.4 (error taxonomy) + Story 2.1 (Node adapter) | Node integration |
| R-11 | TECH | 2×3=6 | Story 1.5 (hash composition) + Story 5.4 (lazy compose) | Python integration (parametrized) |
| R-12 | DATA | 2×3=6 | Story 5.1 (dry-run) + Story 5.2 (halt-on-drift) + Story 7.2 (E2E) | Golden (drift family) + E2E |
| R-13 | DATA | 2×1=2 | absorbed in Story 5.1 | Golden |
| R-14 | OPS | 1×2=2 | Story 1.5 (lockfile writer) | Unit |
| R-15 | OPS | 1×2=2 | Story 7.4 (abandoned session) | Node integration |
| R-16 | BUS | 2×3=6 | Story 6.7 (dogfood) + Story 7.5 (release gate) | Release-gate CI |
| R-17 | TECH | 2×3=6 | Story 2.2 (`bmad-help` reference skill + baseline) | Node integration |
| R-18 | TECH | 2×2=4 | Story 6.1 (mock contract + boundary lint) | Node integration (lint) |
| R-19 | PERF | 2×2=4 | Story 5.4 (lazy compose) + perf harness | Perf smoke |
| R-20 | TECH | 1×2=2 | Story 1.4 (error taxonomy) | Unit |

## Recommended BMAD → TEA Workflow Sequence

1. **TEA Test Design** (`TD`) — **DONE** (this handoff)
2. **BMAD Implementation Readiness Check** — recommended before sprint planning; validates PRD/architecture/epics alignment and B-01/B-02/B-03 are story-assigned
3. **TEA ATDD** (`AT`) per epic — optional; recommended for Epic 1, 3, 5 where P0 density is highest
4. **BMAD Dev Story Execution** — per-story test DoD from this handoff's Story-Level table
5. **TEA Test Automate** (`TA`) per feature — expand from P0/P1 scaffolds into full automation
6. **TEA Trace** (`TR`) — per-epic coverage validation + quality gate decision
7. **TEA NFR Assessment** (`NR`) — at release gate, validates NFR-P*, NFR-S*, NFR-R*, NFR-C* claims

## Phase Transition Quality Gates

| From Phase | To Phase | Gate Criteria |
|---|---|---|
| Test Design | Sprint Planning | All 7 HIGH risks have mitigation owner + timeline; B-01, B-02, B-03 assigned to specific story DoDs |
| Sprint Planning | Implementation | P0 scenarios visible in story DoDs (via table above); B-blockers scheduled in Epic 1 or 2 |
| Implementation | Test Automation | All acceptance tests per story table passing; no P0 unaddressed |
| Test Automation | Release | Trace matrix shows ≥80% coverage of P0/P1 requirements; all HIGH-risk mitigations MITIGATED; 3-OS determinism green; dogfood + backward-compat gates green |

## Notes for BMAD Product Team

- **Scope recalibration flagged during test design:** user's initial generic cross-cutting scope ("auth, observability, data integrity") does not match project type. Real cross-cutters for this compile-pipeline project are documented in `test-design-architecture.md` §Executive Summary. Adjust any stakeholder-facing test-strategy communications accordingly.
- **Drift coverage budget:** architecture's generic "~8–15 goldens" target is under-scoped for R-12 (north-star-metric protection). Recommending drift goldens as a separate scenario family. Requires budget signoff during implementation planning.
- **Windows CI runner dev-mode:** R-04 mitigation depends on Windows junction capability. If runner-cost prevents dev-mode, TEA's security adversarial suite degrades from blocking to informational; security reviewer must perform manual penetration check to compensate.
- **Release-gate status:** dogfood (R-16) and backward-compat (R-17) gates are BOTH required for v1 release. Together they make compiler correctness *observable* rather than *asserted*.
