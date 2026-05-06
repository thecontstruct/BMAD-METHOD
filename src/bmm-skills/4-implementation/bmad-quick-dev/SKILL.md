---
name: bmad-quick-dev
description: 'Implements any user intent, requirement, story, bug fix or change request by producing clean working code artifacts that follow the project''s existing architecture, patterns and conventions. Use when the user wants to build, fix, tweak, refactor, add or modify any code, component or feature.'
---

Run this from the project root (the directory containing `_bmad/`):

PYTHONPATH=_bmad/scripts python3 -m bmad_compile.lazy_compile bmad-quick-dev 2>&1

Then follow the workflow it prints to stdout.

If the command exits non-zero, halt immediately and report the full error output to the user — do not proceed with stale or cached content.
