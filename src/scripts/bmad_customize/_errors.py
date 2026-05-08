"""Shared exception types for bmad-customize handlers.

Lives in its own module so that all five handler files (discovery.py, routing.py,
drafting.py, writer.py, drift.py) can import it without creating circular imports.
"""
from __future__ import annotations


class BmadSubprocessError(RuntimeError):
    """Raised when a bmad-customize handler's subprocess call fails or returns
    unparsable output. Wraps the underlying CalledProcessError or
    JSONDecodeError so callers see a single typed exception type instead of
    raw subprocess/json errors leaking through the emit-event contract.
    """
