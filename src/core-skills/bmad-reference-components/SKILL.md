---
name: bmad-reference-components
description: 'Reference skill demonstrating conditional-rendering components (TodaysDate, IdeNotes, ProjectContext). Not for end-user install — reference and test purposes only.'
---

# BMAD Reference Components

This skill demonstrates the conditional-rendering component pattern introduced in Epic 9.
Components are Python functions; conditional logic lives in `render()`, not in template tags.

## Session Context

**Date:** <!-- BMAD-JIT:TodaysDate:44136fa355b3678a -->

<!-- BMAD-JIT:ProjectContext:44136fa355b3678a -->

## IDE Guidance

**IDE:** Open your AI assistant's chat panel and describe your intent. Paste context from the spec or error message as needed.

---

*This skill exists as a living reference. Components live in `components/` and compile or
resolve JIT based on their `RENDER_MODE` declaration.*
