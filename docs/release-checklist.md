---
title: Release Checklist
description: Pre-release hard and soft gate checklist for bmad-method releases.
---

# Release Checklist

Copy this checklist into the release PR description before opening the PR.

## Hard Gates (CI blocks merge if any unchecked)

- [ ] `docs/compile/author-migration-guide.md` present (CI `docs-gate` job)
- [ ] `docs/compile/bmad-customize-walkthrough.md` present
- [ ] `docs/compile/bmad-lock-schema.md` present
- [ ] `docs/compile/explain-vocabulary.md` present
- [ ] `docs/compile/quickstart.md` present
- [ ] Dogfood gate: Phil M has executed the `src/core-skills/bmad-customize/DOGFOOD.md` procedure (steps 1–6) and recorded outcome below
- [ ] Success metric: 25% metric downgraded to Phase 2 (Story 7.5 AC-3 in `proposals/epics.md`)

## Soft Gates (does NOT block merge; include in release notes if incomplete)

- [ ] Story 7.7 (third-party module dogfood migration) complete
  - If incomplete, add to Known Gaps below

## Dogfood Sign-off (Phil M)

<!-- Copy outcome of DOGFOOD.md steps 1–6 here -->

## Known Gaps (for release notes)

<!-- List any soft-gate items that are incomplete. E.g.:
- Story 7.7 (third-party dogfood migration) incomplete; targeted for v6.7.0. -->
