# bmad_compile — Library Layering (ADR)

The compiler is organized as a strict ten-layer library with a one-way import
rule: **a module may import only from strictly lower layers.** The layering
test (`test/python/test_layering.py`) enforces this with `ast`; CI fails on
upward imports. This is the same architectural decision recorded in
`BMAD-METHOD/proposals/bmad-skill-compiler-architecture.md` under
"Python Library Layering & Import Discipline".

| # | Module | Depends on |
|---|-------------------|-------------------|
| 1 | `errors`          | (nothing)         |
| 2 | `io`              | errors            |
| 3 | `parser`          | errors            |
| 4 | `toml_merge`      | errors, io        |
| 5 | `variants`        | errors, io        |
| 6 | `resolver`        | errors, io, parser, toml_merge, variants |
| 7 | `lockfile`        | errors, io, resolver                    |
| 8 | `explain`         | errors, io, parser, resolver, lockfile  |
| 9 | `engine`          | layers 1-8                              |
| 10 | `lazy_compile`   | layers 1-9                              |

## Why

1. **Purity by construction.** `parser` can't accidentally read files because
   `io` is below it — the layer above `io` that could route through it
   (`resolver`) is also above `parser`. A raw-I/O call in `parser.py` would
   require an upward import, which the layering test rejects.
2. **Determinism is a boundary, not a discipline.** All non-determinism
   (filesystem, hash, time) is confined to `io`. Modules above `io` receive
   inputs through that boundary and become pure functions of those inputs.
3. **Swappable parts.** A frontend change to `parser` cannot ripple into
   `engine` without passing through `resolver`, so blast radius stays local.

## Enforcement

- **`test/python/test_layering.py`** — parses each `bmad_compile/*.py` module
  with `ast`, walks `Import`/`ImportFrom` nodes, and asserts every
  `bmad_compile.*` import targets a layer `<=` the importing module's layer.
  Modules not yet created in the current story are skipped (`if not exists`).

- **`test/python/test_io_boundary.py`** — greps non-`io.py` modules for raw
  I/O tokens (`pathlib`, `hashlib`, `time.`, `os.listdir`, `os.scandir`,
  `glob`, bare `open(`). Lines annotated `# pragma: allow-raw-io` are
  exempted (only inside `io.py`, which the grep skips entirely). See
  architecture B-01 risk.

Both tests run under `python3 -m unittest discover -s test/python -t .` and
take <100ms — no reason to gate them behind a slow suite.

## Adding a new module

1. Decide its layer based on what it needs to import — never on what it
   "feels like". If you want `parser` to call `io`, the answer is: either
   push the I/O call up to the caller, or mediate through a helper the
   parser receives as an argument.
2. Update the table above.
3. Update `LAYERS` constant in `test_layering.py` if you're inserting a new
   layer (rare — the existing ten cover the full architecture per the ADR).
