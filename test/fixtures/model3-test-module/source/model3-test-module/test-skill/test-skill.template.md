---
name: test-skill
description: CI fixture for Model 3 distribution matrix test (Story 7.3). Use when verifying compiler-present and compiler-absent install paths produce byte-identical SKILL.md.
tier: module
status: alpha
tags: []
---

# Test Skill

This is a minimal Model 3 fixture skill used by `test/test-model3-distribution-matrix.js` to verify the byte-identity contract between compile-from-source and precompiled-fallback install paths.

The skill is deliberately content-free — no fragment-include directives, no TOML substitutions, no cross-module references. The test only asserts on the SKILL.md hash, not on skill behavior.
