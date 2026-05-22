---
name: bmad-reference-components
description: 'Reference skill demonstrating conditional-rendering components (TodaysDate, IdeNotes, ProjectContext). Not for end-user install — reference and test purposes only.'
---

# BMAD Reference Components

This skill demonstrates the conditional-rendering component pattern introduced in Epic 9.
Components are Python functions; conditional logic lives in `render()`, not in template tags.

## Session Context

**Date:** <TodaysDate />

<ProjectContext />

## IDE Guidance

<IdeNotes />

---

*This skill exists as a living reference. Components live in `components/` and compile or
resolve JIT based on their `RENDER_MODE` declaration.*
