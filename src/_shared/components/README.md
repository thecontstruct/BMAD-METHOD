# `_shared/components/` — Shared render-time primitives

This directory hosts Python component files (`*.py`) that are shared
across multiple skills. Authored to solve the cross-skill component
duplication problem identified by Architecture ARC-OQ-1 / OOS-Arch-4
and shipped under Story 10.58.

This README is **author guidance only** — it is excluded from the install
target by the `_copySharedComponentsRoot` blocklist (`*.md`).

## Resolution order

When a skill references a component (`<MyComp />`), the engine probes
two roots in order:

1. **Per-skill** — `<skill_dir>/components/<snake>.py` (the canonical
   per-skill home).
2. **Shared fallback** — `<install_root>/_shared/components/<snake>.py`
   (this directory, when probe #1 misses).

Per-skill probe wins; intentional shadowing is permitted. A skill that
wants to override a shared primitive can drop a same-named file in its
own `components/`.

## DN-8 criteria — when to lift a component here

A component qualifies for `_shared/components/` lift only if all of:

1. Referenced by ≥2 inter-skill consumers (≥2 distinct skills).
2. Byte-identical OR semantically identical across copies.
3. Absent from any SHA-pinned skill, OR pinned-keeps-local with the
   lifted copy serving unpinned consumers only.
4. A render-time primitive (component-tag-invoked via `<Foo />`).
5. Stable surface — same `render(ctx, **props)` signature, same
   `RENDER_MODE`, same `RENDER_ERROR_FALLBACK` semantics.
6. Genuinely cross-cutting — its name does not require referencing
   one skill's domain.

Failing any criterion → keep the component per-skill.

## Cache and lockfile behavior

- Cache key includes both `_data_files_hash` (per-skill) and
  `_shared_data_files_hash` (this directory). Non-`.py` files dropped
  here invalidate every consumer's compile cache.
- Lockfile v4 records `_shared/components/<snake>.py` verbatim in each
  consuming component's `path:` field when the shared fallback wins
  (vs. `components/<snake>.py` for per-skill wins).

## Currently shipped components

- `todays_date.py` — lifted byte-identical from
  `bmad-quick-dev/components/` + `bmad-reference-components/components/`.
  Pinned copies stay in place until DN-FOLLOWUP-G (post-pin-lift cleanup).
- `artifact_path.py` — JIT component encoding BMAD-domain path-derivation
  logic (story spec paths, sprint-status keys, epic keys, retro filenames,
  planning-artifact globs). Consumer adoption tracked as DN-FOLLOWUP-I.

## Limits

- Flat directory only — no subdirectories (DN-FOLLOWUP-E).
- Per-component data-file declaration not yet supported — skill-level
  over-invalidation is acceptable for now (DN-FOLLOWUP-B).
