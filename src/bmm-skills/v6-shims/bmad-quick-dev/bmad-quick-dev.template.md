---
name: bmad-quick-dev
description: "Deprecated: forwards to bmad-build. Do not use unless invoked by name."
---

# Deprecated Build Alias

On activation, check for legacy `bmad-quick-dev` customization files. If none exist, state that `bmad-quick-dev` is deprecated and redirect exactly once to `bmad-build` with the original input. If legacy customization files exist, offer to migrate them to the corresponding `bmad-build` names only with explicit approval; never overwrite a new-name customization file. After a successful migration, redirect exactly once to `bmad-build`.
