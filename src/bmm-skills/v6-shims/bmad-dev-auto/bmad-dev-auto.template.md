---
name: bmad-dev-auto
description: "Deprecated: forwards to bmad-build-auto. Do not use unless invoked by name."
---

# Deprecated Build Auto Alias

On activation, check for legacy `bmad-dev-auto` customization files. If none exist, state that `bmad-dev-auto` is deprecated and redirect exactly once to `bmad-build-auto` with the original input. If legacy customization files exist, offer to migrate them to the corresponding `bmad-build-auto` names only with explicit approval; never overwrite a new-name customization file. After a successful migration, redirect exactly once to `bmad-build-auto`.
