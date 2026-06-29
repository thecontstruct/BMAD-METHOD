---
title: 'Python Environment for Validators and Tests'
description: How the BMAD-METHOD build pipeline resolves a Python 3.11+ interpreter for validators and tests, and what to install to make `npm run quality` work
sidebar:
  order: 13
---

The fork's validator and test scripts (`npm run validate:compile`, `npm run test:validate-compile`, `test/python/test_migration_equivalence.py`, and others) shell out to Python scripts in `src/scripts/`. Stories 10.27+ in the fork introduced Python 3.11+ syntax (`from enum import StrEnum`), so the fork's Python surface requires **CPython ≥ 3.11**.

:::note[Prerequisites]

- A working `npm` and `node` (see [How to Install BMad](./install-bmad.md))
- Either `uv` on PATH, or a `python3` ≥ 3.11 on PATH

:::

## Why `uv`

[`uv`](https://docs.astral.sh/uv/) is becoming the de facto standard for running BMAD's Python scripts. The fork's installer detects `uv` and recommends it via [`tools/installer/core/uv-check.js`](https://github.com/bmad-code-org/BMAD-METHOD/blob/main/tools/installer/core/uv-check.js). The reason is simple: `uv run` provisions an interpreter and resolves dependencies on demand, so contributors don't have to manage a venv by hand.

When the build pipeline can't find a `python3` ≥ 3.11 on PATH, it falls through to `uv run --python 3.13 --with pyyaml python3 <args>`. This keeps validation working on a fresh clone without manual setup, as long as `uv` is installed.

## Install `uv`

Pick one:

- **Ask your agent**: "install and set up uv for me"
- **macOS/Linux**: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Windows (PowerShell)**: `irm https://astral.sh/uv/install.ps1 | iex`
- **Homebrew**: `brew install uv`
- **Docs**: <https://docs.astral.sh/uv/getting-started/installation/>

`uv --version` should print `uv 0.x.y` once installed.

## What happens during `npm run quality`

The quality gate invokes `npm run validate:compile`, which spawns `compile.py` once per skill. Each spawn goes through [`tools/python-env.js`](https://github.com/bmad-code-org/BMAD-METHOD/blob/main/tools/python-env.js), which:

1. Probes for a `python3` ≥ 3.11 on PATH first (cheapest path — works inside any pre-existing venv)
2. Falls back to `uv run --python 3.13 --with pyyaml python3 <args>` if no qualifying interpreter is found
3. Reuses the existing `uv-check.js` detection so the message stays consistent with the installer

The result: `npm run quality` works on any machine with `uv` installed, without any manual venv creation. Contributors who prefer a hand-managed venv can still set `PATH` to point at their own `python3` ≥ 3.11 and the helper will use it directly.

## Running the Python test suite

`test/python/test_migration_equivalence.py` (and other `test/python/test_*.py` files) require `pytest` and `pyyaml` as runtime deps. These are listed in `pyproject.toml` under `[tool.uv]` (auto-installed on `uv run`) or can be installed manually into your venv:

```sh
uv pip install pytest pyyaml
```

`uv run` resolves both automatically on first invocation — no manual install needed if you go through the helper.

## The `.venv` directory

The fork has Stories 10.27+ code that uses Python 3.11+ syntax. If you previously ran `uv run` in the fork root (or `uv venv .venv`), you'll have a `.venv/` directory. This is gitignored (added in the same prep commit that added `tools/python-env.js`).

If you prefer to **commit** your resolved dependencies for reproducibility, leave `uv.lock` tracked — `uv` will pick it up on the next `uv run`. The fork ships `uv.lock` committed by default.

## Troubleshooting

:::caution[Symptom: `validate:compile` shows 27 of 27 fail with `ImportError: cannot import name 'StrEnum'`]

You're on system `python3` < 3.11. Either install `uv` (recommended) or upgrade your local Python. The `StrEnum` import landed in Stories 10.27+ and is a hard requirement.

:::

:::caution[Symptom: `pytest: ModuleNotFoundError` running `test_migration_equivalence.py`]

You're invoking `python3 -m pytest` outside the `uv run` chain. Run via `uv run --with pytest python3 -m pytest test/python/test_migration_equivalence.py` instead, or `uv pip install pytest pyyaml` once into your venv.

:::

:::caution[Symptom: `uv: command not found`]

`uv` isn't installed (or isn't on PATH for the shell that runs `npm run quality`). See the install instructions above.

:::