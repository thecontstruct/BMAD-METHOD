"""Test harness intercepting bmad compile/upgrade JSON invocations.
Stories 6.2-6.6 use this harness; Story 6.7 bypasses it and invokes the
real compiler -- see Story 6.7 spec for the integration-test pattern.
"""
from __future__ import annotations

import time
from pathlib import Path


class MockCompiler:
    """Test harness intercepting bmad compile/upgrade JSON invocations.
    Used by Stories 6.2-6.6 only. Story 6.7 bypasses this harness -- see AC-4.
    """

    def __init__(self, fixtures_root: Path) -> None:
        """fixtures_root points at test/fixtures/customize-mocks/."""
        self._fixtures_root = fixtures_root
        self._registry: list[tuple[str, str]] = []
        self._calls: list[dict[str, object]] = []

    def register(self, invocation_pattern: str, fixture_name: str) -> None:
        """Bind an invocation pattern (e.g., 'compile --explain --json --skill <id>')
        to a fixture filename (e.g., 'explain-pristine.json'). Multiple patterns
        may map to the same fixture. Patterns are matched as a literal-substring
        match against the joined argv (after argv[0] = 'bmad'). Last registration
        wins for collisions."""
        for i, (pat, _) in enumerate(self._registry):
            if pat == invocation_pattern:
                self._registry[i] = (invocation_pattern, fixture_name)
                return
        self._registry.append((invocation_pattern, fixture_name))

    def intercept(self, invocation_pattern: str) -> str:
        """Return the JSON contents of the registered fixture as a string.
        Raise KeyError with a directed message if no registered pattern
        matches. If a pattern is registered but its fixture file does not
        exist on disk, allow FileNotFoundError to propagate uncaught.
        Patterns are matched as literal substrings (no regex semantics).
        Reads the fixture from disk on each call (no cache).
        Each call is recorded in self.calls for assertion."""
        for pattern, fixture_name in reversed(self._registry):
            if pattern in invocation_pattern:
                fixture_path = self._fixtures_root / fixture_name
                content = fixture_path.read_text(encoding="utf-8")
                self._calls.append({
                    "pattern": pattern,
                    "fixture": fixture_name,
                    "timestamp_ns": time.monotonic_ns(),
                })
                return content
        raise KeyError(
            f"MockCompiler: no registered pattern matches {invocation_pattern!r}. "
            f"Registered patterns: {[p for p, _ in self._registry]}"
        )

    @property
    def calls(self) -> list[dict[str, object]]:
        """Read-only list of recorded calls. Each entry is
        {'pattern': str, 'fixture': str, 'timestamp_ns': int}.
        Story 6.2 AC-4 asserts <= 2 --explain --json invocations per turn."""
        return list(self._calls)

    def reset(self) -> None:
        """Clear self.calls. Registrations persist."""
        self._calls.clear()
