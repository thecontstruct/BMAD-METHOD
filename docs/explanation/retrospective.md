---
title: "Retrospective"
description: Close out a finished epic by reading the evidence it left — the diff, commits, specs, and sprint status — rather than trusting memory.
sidebar:
  order: 15
---

Run `bmad-retrospective` when an epic is done. It reads the epic's actual outputs — Build specs, the full diff, per-story commits, sprint status, and available verification — then writes a review, owned action items, and an acceptance verdict.

## What it checks

- **Aggregate defects**: cross-story drift, duplicated helpers, growing modules, and changed seams no isolated story review could see.
- **Spec reconciliation**: where delivered code diverges from the epic or story contract.
- **Verification**: whether deterministic checks still protect changed behavior.
- **Acceptance**: each epic criterion is marked met, not met, or uncertain with supporting evidence.

Every reported finding includes a source reference. Unsupported patterns and invented root causes are excluded.

## What it produces

The retrospective creates an evidence inventory and report in implementation artifacts, plus an acceptance verdict:

- `accepted` — all stories and acceptance criteria are complete with no blocker.
- `accepted-with-open-items` — the epic is complete but has evidence-backed non-blocking follow-up work.
- `rejected` — a story is incomplete, a criterion is not met, or a blocking finding is established.

Interactive runs ask a human to confirm or override the verdict; headless (`-H` or `--headless`) runs record the machine verdict. In either mode, a report never silently converts a rejected epic into an accepted one.

## How to use it

Say "run a retrospective" or "retro epic 3." Ask for a team discussion only after the evidence report exists; party mode is optional and discusses the report rather than replacing it.

The retrospective does not edit code or specs. Accepted action items can be taken into `bmad-build`; rejected outcomes or larger follow-up work should return to planning.
