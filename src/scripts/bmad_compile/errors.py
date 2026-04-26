"""Layer 1 — frozen error taxonomy and shared format renderer.

No internal imports; stdlib `enum` only.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, ClassVar


class ErrorCode(StrEnum):
    UNKNOWN_DIRECTIVE = "UNKNOWN_DIRECTIVE"
    UNRESOLVED_VARIABLE = "UNRESOLVED_VARIABLE"
    MISSING_FRAGMENT = "MISSING_FRAGMENT"
    CYCLIC_INCLUDE = "CYCLIC_INCLUDE"
    OVERRIDE_OUTSIDE_ROOT = "OVERRIDE_OUTSIDE_ROOT"
    LOCKFILE_VERSION_MISMATCH = "LOCKFILE_VERSION_MISMATCH"
    PRECEDENCE_UNDEFINED = "PRECEDENCE_UNDEFINED"


ERROR_CODES: frozenset[str] = frozenset(c.value for c in ErrorCode)


class CompilerError(Exception):
    """Base class for all compile-time errors.

    `CODE` is hard-coded per subclass and exposed immutably as `.code`.
    `format()` renders the public error-contract shape:

        <CODE>: <rel-path>:<line>:<col>: <desc>
          N-1| <context line>
          N  | <offending line>
             | ^^^^^^^
          N+1| <context line>
            hint: <remediation>
            [see: bmad docs errors#<CODE>]
    """

    CODE: ClassVar[str] = ""

    def __init__(
        self,
        desc: str,
        *,
        file: str | None = None,
        line: int | None = None,
        col: int | None = None,
        token: str | None = None,
        hint: str | None = None,
        source: str | None = None,
    ) -> None:
        super().__init__(desc)
        self.desc = desc
        self.file = file
        self.line = line
        self.col = col
        self.token = token
        self.hint = hint
        self.source = source

    @property
    def code(self) -> str:
        return type(self).CODE

    def format(self, source: str | None = None) -> str:
        src = source if source is not None else self.source
        file_s = self.file if self.file is not None else "<unknown>"
        line_s = str(self.line) if self.line is not None else "?"
        col_s = str(self.col) if self.col is not None else "?"
        header = f"{self.code}: {file_s}:{line_s}:{col_s}: {self.desc}"
        lines: list[str] = [header]

        # Render the context+caret block only when the error's line number
        # falls inside the source. Out-of-range lines (<=0 or past EOF) would
        # produce an empty context block with a misleading line header.
        if src is not None and self.line is not None:
            src_lines = src.splitlines()
            n = self.line
            if 1 <= n <= len(src_lines):
                start = max(1, n - 1)
                end = min(len(src_lines), n + 1)
                gutter_width = len(str(end))
                caret_span = max(1, len(self.token) if self.token else 1)
                caret_col = max(1, self.col if self.col is not None else 1)
                for i in range(start, end + 1):
                    content = src_lines[i - 1]
                    lines.append(f"  {str(i).rjust(gutter_width)}| {content}")
                    if i == n:
                        pad = " " * (caret_col - 1)
                        caret = "^" * caret_span
                        lines.append(f"  {' ' * gutter_width}| {pad}{caret}")

        chain = getattr(self, "chain", None)
        if chain:
            lines.append(f"    [chain: {' -> '.join(chain)}]")

        # AC 2: one-line `hint:` is part of the contract. Fall back to a
        # sentinel if hint is None / empty / whitespace-only so we never emit
        # a bare `hint:` with no remediation text. Multi-line hints collapse
        # to the first non-blank line.
        hint_lines = [ln for ln in (self.hint or "").splitlines() if ln.strip()]
        hint_one_line = hint_lines[0] if hint_lines else "(no hint available — see docs for this error code)"
        lines.append(f"    hint: {hint_one_line}")
        lines.append(f"    [see: bmad docs errors#{self.code}]")
        return "\n".join(lines)


class UnknownDirectiveError(CompilerError):
    CODE: ClassVar[str] = ErrorCode.UNKNOWN_DIRECTIVE.value


class UnresolvedVariableError(CompilerError):
    CODE: ClassVar[str] = ErrorCode.UNRESOLVED_VARIABLE.value


class MissingFragmentError(CompilerError):
    CODE: ClassVar[str] = ErrorCode.MISSING_FRAGMENT.value


class CyclicIncludeError(CompilerError):
    CODE: ClassVar[str] = ErrorCode.CYCLIC_INCLUDE.value

    def __init__(self, desc: str, *, chain: list[str] | None = None, **kwargs: Any) -> None:
        super().__init__(desc, **kwargs)
        self.chain = chain


class OverrideOutsideRootError(CompilerError):
    CODE: ClassVar[str] = ErrorCode.OVERRIDE_OUTSIDE_ROOT.value


class LockfileVersionMismatchError(CompilerError):
    CODE: ClassVar[str] = ErrorCode.LOCKFILE_VERSION_MISMATCH.value


class PrecedenceUndefinedError(CompilerError):
    CODE: ClassVar[str] = ErrorCode.PRECEDENCE_UNDEFINED.value


SUBCLASSES: tuple[type[CompilerError], ...] = (
    UnknownDirectiveError,
    UnresolvedVariableError,
    MissingFragmentError,
    CyclicIncludeError,
    OverrideOutsideRootError,
    LockfileVersionMismatchError,
    PrecedenceUndefinedError,
)
