#!/usr/bin/env python3
"""BMAD component subprocess entry point.

Invocation:  python3 component_wrapper.py /abs/path/to/component.py
Stdin:       UTF-8 JSON  {"ctx": {...}, "props": {...}}
Stdout:      UTF-8 JSON  {"ok": true, "output": "..."}
                      or {"ok": false, "error": "...", "render_error_fallback": null|"..."}
Exit codes:  0 = ok (check "ok" field)
             1 = component error (import failure, render() exception, bad return type)
             2 = protocol error (missing argv, bad stdin JSON, path-containment violation)

IMPORTANT: This script MUST NOT import from bmad_compile or any BMAD package.
It runs as an isolated subprocess where PYTHONPATH may not include the project.
"""
from __future__ import annotations

import importlib.util
import io
import json
import logging
import os
import re
import sys
import tokenize
import traceback
import types


# ---------------------------------------------------------------------------
# Helpers — defined at module level, called throughout
# ---------------------------------------------------------------------------

def _write_ok(output: str) -> None:
    sys.__stdout__.write(json.dumps({"ok": True, "output": output}))
    sys.__stdout__.flush()


def _write_err(msg: str, fallback: str | None = None) -> None:
    sys.__stdout__.write(
        json.dumps({"ok": False, "error": msg, "render_error_fallback": fallback})
    )
    sys.__stdout__.flush()


def _strip_string_and_comment_tokens(source: str) -> str:
    """Return source with STRING and COMMENT token text replaced by empty strings.

    Preserves line structure so MULTILINE ^ anchors remain valid on the result.
    On TokenError (unparseable source), returns source unchanged.
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except tokenize.TokenError:
        return source  # unparseable — regex may false-positive; import will fail later
    lines = source.splitlines(keepends=True)
    result = list(lines)
    for tok_type, _tok_str, (srow, scol), (erow, ecol), _ in reversed(tokens):
        if tok_type in (tokenize.STRING, tokenize.COMMENT):
            if srow == erow:
                result[srow - 1] = result[srow - 1][:scol] + result[srow - 1][ecol:]
            else:
                result[srow - 1] = result[srow - 1][:scol]
                for mid in range(srow, erow - 1):
                    result[mid] = "\n"
                result[erow - 1] = result[erow - 1][ecol:]
    return "".join(result)


_FALLBACK_RE = re.compile(
    r'^RENDER_ERROR_FALLBACK\s*=\s*["\'](.+)["\']',
    re.MULTILINE,
)
# Matches the assignment skeleton after strip (value is gone after strip; used as guard
# to detect module-level presence before extracting the value from raw source).
_FALLBACK_SKELETON_RE = re.compile(r'^RENDER_ERROR_FALLBACK\s*=\s*', re.MULTILINE)

# ---------------------------------------------------------------------------
# Step 1: Parse argv + stdin (before stdout redirect — protocol errors go here)
# ---------------------------------------------------------------------------

if len(sys.argv) < 2:
    _write_err("missing argv[1]: component path required")
    sys.exit(2)

component_path: str = sys.argv[1]

try:
    _raw_payload = sys.stdin.buffer.read()
    _payload = json.loads(_raw_payload)
except (json.JSONDecodeError, ValueError) as _e:
    _write_err(f"invalid stdin JSON: {_e}")
    sys.exit(2)

ctx_data: dict = _payload.get("ctx", {})
props: dict = _payload.get("props", {})

# ---------------------------------------------------------------------------
# Step 2: NFR-S3 path-containment check (before stdout redirect)
# ---------------------------------------------------------------------------

_resolved_component = os.path.realpath(component_path)
_skill_source_root = os.path.realpath(ctx_data.get("skill_source_root", ""))
if not _resolved_component.startswith(_skill_source_root + os.sep):
    _write_err(f"component path escapes skill_source_root: {component_path}")
    sys.exit(2)

# ---------------------------------------------------------------------------
# Step 3: Build ctx namespace
# ---------------------------------------------------------------------------

ctx = types.SimpleNamespace(**ctx_data)

# ---------------------------------------------------------------------------
# Step 4: Capture stdout + silence logging BEFORE any open() or import
# ---------------------------------------------------------------------------

sys.stdout = io.StringIO()
logging.root.addHandler(logging.NullHandler())
logging.root.setLevel(logging.CRITICAL)

# ---------------------------------------------------------------------------
# Step 5: Read RENDER_ERROR_FALLBACK via tokenize-strip BEFORE importlib
#         (Guarantees fallback is available even if import fails — FR-6.2)
# ---------------------------------------------------------------------------

_render_error_fallback: str | None = None
try:
    with open(component_path, encoding="utf-8") as _f:  # pragma: allow-raw-io
        _raw_src = _f.read()
    _stripped = _strip_string_and_comment_tokens(_raw_src)
    # Guard: verify module-level presence via skeleton on stripped source (prevents
    # false positives from docstrings — their content is erased by strip).
    # Then extract the actual value from raw source (strip removes string tokens).
    if _FALLBACK_SKELETON_RE.search(_stripped):
        _fb_match = _FALLBACK_RE.search(_raw_src)
        if _fb_match:
            _render_error_fallback = _fb_match.group(1)
except Exception as _e:
    sys.stdout = sys.__stdout__
    _write_err(f"cannot read component file: {_e}", fallback=_render_error_fallback)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Step 6: Import component via importlib
# ---------------------------------------------------------------------------

try:
    _spec = importlib.util.spec_from_file_location("_bmad_component", component_path)
    _module = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_module)
except Exception as _e:
    sys.stdout = sys.__stdout__
    _write_err(
        f"component import failed: {traceback.format_exc()}",
        fallback=_render_error_fallback,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Step 7: Call render() while stdout is still captured (suppresses print() noise),
#         then restore stdout and validate return type
# ---------------------------------------------------------------------------

try:
    result = _module.render(ctx, **props)
except Exception as _e:
    sys.stdout = sys.__stdout__
    _write_err(
        f"render() raised {type(_e).__name__}: {_e}\n{traceback.format_exc()}",
        fallback=_render_error_fallback,
    )
    sys.exit(1)

sys.stdout = sys.__stdout__

if not isinstance(result, str):
    _write_err(
        f"render() returned {type(result).__name__}, expected str",
        fallback=_render_error_fallback,  # see DN-1 for resolution
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# Step 8: Write success envelope
# ---------------------------------------------------------------------------

_write_ok(result)
sys.exit(0)
