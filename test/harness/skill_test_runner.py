"""Subprocess-seam test runner for Epic 6 bmad-customize handler tests.

Patches subprocess.run globally for the duration of a handler call, routing
calls through MockCompiler.intercept() to return fixture JSON.

Public API: run_handler_with_mock
Stories 6.2-6.6 use this module; Story 6.7 bypasses it (real subprocess calls).
"""
from __future__ import annotations

import subprocess
from typing import Any, Callable
from unittest.mock import patch

from .mock_compiler import MockCompiler


def _make_side_effect(
    mock_compiler: MockCompiler,
) -> Callable[..., subprocess.CompletedProcess[str]]:
    def side_effect(
        args: list[str], *_a: Any, **_kw: Any
    ) -> subprocess.CompletedProcess[str]:
        joined = " ".join(str(a) for a in args)
        stdout = mock_compiler.intercept(joined)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout)

    return side_effect


def run_handler_with_mock(
    handler_fn: Callable[..., None],
    mock_compiler: MockCompiler,
    *args: Any,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Run handler_fn under subprocess.run patch backed by mock_compiler.

    Creates an emit_fn collector and injects it as a keyword argument to
    handler_fn. Patches subprocess.run for the duration of the call so that
    any subprocess.run([compile.py, ...]) inside the handler hits mock_compiler.

    CONSTRAINT: callers MUST NOT pass run_fn explicitly — the global patch
    intercepts subprocess.run at call time; an explicit run_fn bypasses it and
    breaks seam isolation. This applies to all test classes in Stories 6.2–6.6.

    Returns the list of events emitted by handler_fn via its emit_fn argument.
    """
    events: list[dict[str, Any]] = []
    with patch("subprocess.run", side_effect=_make_side_effect(mock_compiler)):
        handler_fn(*args, emit_fn=events.append, **kwargs)
    return events
