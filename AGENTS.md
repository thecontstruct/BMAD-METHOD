# BMAD-METHOD

Open source framework for structured, agent-assisted software delivery.

## Rules

- Use Conventional Commits for every commit.
- Before pushing, run `npm ci && npm run quality` on `HEAD` in the exact checkout you are about to push.
  `quality` mirrors the checks in `.github/workflows/quality.yaml`.

- Skill validation rules are in `tools/skill-validator.md`.
- Deterministic skill checks run via `npm run validate:skills` (included in `quality`).

## Python environment for validators and tests

The fork's validator scripts and Python tests shell out to Python scripts in `src/scripts/`. Stories 10.27+ require **Python ≥ 3.11**. The fork detects `uv` automatically and falls through to `uv run --python 3.13 --with pyyaml python3 <args>` when no qualifying interpreter is on PATH, so `npm run quality` works on a fresh clone as long as `uv` is installed.

Install `uv` (`brew install uv` / `curl -LsSf https://astral.sh/uv/install.sh | sh`) if `npm run validate:compile` shows `ImportError: cannot import name 'StrEnum'`. Full setup, troubleshooting, and the rationale are in [docs/how-to/python-environment.md](./docs/how-to/python-environment.md).

## Compiler-fork workflow

- This checkout is the compiler fork's **source tree**, not an installed BMAD
  project. Do not invoke an externally installed BMAD skill or expect
  `_bmad/scripts/render_skill.py` to exist here.
- For source-tree compilation and migration work, use
  `src/scripts/compile.py` and the `src/scripts/bmad_compile/` package. The
  installer copies those into an installed project's `_bmad/scripts/` tree;
  that runtime layout is not a prerequisite for editing this repository.
- Before porting upstream skill work, identify the fork's canonical source
  (template, fragment, component, or compiler code), carry the behavior into
  that source rather than copying an upstream generated artifact, and run the
  relevant compiler validation. Preserve unrelated in-progress work in a dirty
  tree.
