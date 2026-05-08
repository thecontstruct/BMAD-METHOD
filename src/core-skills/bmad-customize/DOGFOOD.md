# bmad-customize Dogfood Release Gate

Release gate procedure for verifying `bmad-customize` self-upgrade behavior before each BMAD release.

**Coordination Owner:** **Phil M** — inaugural dogfood owner (Story 6.7 PR). Named owner assignment process formalized in Story 7.5. Owner must be a core maintainer with commit rights.

**Reference fixture:** `test/fixtures/customize-mocks/dry-run-bmad-customize-self.json` (simulates a bmad-customize self-upgrade dry-run with one drifted prose fragment and one drifted TOML default).

---

## Release Gate Procedure

**Given** `bmad-customize` has shipped at a prior BMAD version (N-1) as template source with at least one user-authored override applied to itself (e.g., its own `customize.toml` `icon` field overridden, and one prose fragment in its `fragments/` tree overridden)

**When** the release of BMAD version N is being prepared

**Then** the release owner executes the following procedure and records the outcome in the release PR:

1. Check out a clean environment with BMAD N-1 installed, including the `bmad-customize` self-overrides described above
2. Upgrade to the candidate build of BMAD N via `bmad upgrade --dry-run`
3. Assert the dry-run correctly classifies each `bmad-customize` self-override against upstream changes (no silent classification, every override either "unchanged / still applies" or "drift / needs triage")
4. If drift is reported, invoke `bmad-customize` (running under the N-1 build) with drift-triage intent against its own self-overrides, reconcile each drift entry per the Story 6.6 UX, and assert `bmad upgrade` succeeds after triage
5. Assert the upgraded `bmad-customize` at version N retains its own user overrides (the ones preserved through triage) and behaves correctly in a smoke-test scenario (discovery, plane routing, draft + accept, post-accept `--diff`)
6. Assert `bmad.lock` records the version N transition lineage for each self-override

---

## Pass Criteria

All of the following must hold for the release to proceed:

- Every self-override is either preserved verbatim or intentionally reconciled by the release owner; no silent loss.
- Upgrade completes to exit 0 after triage (or directly, if no drift).
- Post-upgrade smoke-test passes.
- Release owner signs off in the release PR description with the recorded outcome of steps 1–6.

## Fail Criteria

Any one of the following blocks release:

- A self-override is silently lost at any step.
- The dry-run misclassifies a drift entry (false negative or false positive verified against the known self-override set).
- Post-upgrade smoke-test fails.
- The procedure cannot be executed (e.g., `bmad-customize` at N-1 cannot be used to triage itself because of a compiler regression introduced in N).
