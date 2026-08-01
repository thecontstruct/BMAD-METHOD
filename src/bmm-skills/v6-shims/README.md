# v6 Deprecation Shims

Skills in this folder are deprecated skills kept for backward compatibility with v6 skill IDs.
Some retain their full workflow, while others forward to the skill that replaced them, passing a
stated intent and pre-resolved customization fields so the target skips its own intent inference.

| Shim                      | Forwards to                        |
| ------------------------- | ---------------------------------- |
| `bmad-create-story`       | Retained in full                   |
| `bmad-dev-story`          | Retained in full                   |
| `bmad-market-research`    | `bmad-deep-recon` (market type)    |
| `bmad-domain-research`    | `bmad-deep-recon` (domain type)    |
| `bmad-technical-research` | `bmad-deep-recon` (technical type) |

Enterprise users may still depend on these IDs, so they ship by default. Removal rides the
v7 cut — never a 6.x minor.

The folder is grouping only: the installer discovers skills recursively and installs each
one under its own `name`, so nesting here does not change any installed path or skill ID.
A future install option will let users include or exclude this folder before it is removed
outright.

**Not yet grouped here:** this fork's PRD and architecture forwarders (`bmad-create-prd`,
`bmad-edit-prd`, `bmad-validate-prd`, `bmad-create-architecture`) still sit in their
original phase folders under `2-plan-workflows/` and `3-solutioning/`. Upstream moved them
here in #2608; that regrouping is a separate port. Since the folder is grouping only, their
IDs and installed paths are unaffected either way.
