---
name: test-skill
description: CI fixture for Model 1 distribution detection (Story 7.6 AC-1). Module ships a precompiled SKILL.md only — no template — so it is installed verbatim without invoking the compiler.
tier: module
status: alpha
tags: []
---

# Test Skill

This is a minimal Model 1 fixture skill used by `test/test-model3-distribution-matrix.js`'s AC-1 (7.6) test to verify the verbatim-copy install path: a module with no `*.template.md` returns `'model1'` from `detectModelTier` and is excluded from `enumerateMigratedSkills`, so the compiler is never invoked.
