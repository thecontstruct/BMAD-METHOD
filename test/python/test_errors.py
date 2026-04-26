"""Unit tests for bmad_compile.errors — format shape + code immutability."""

from __future__ import annotations

import unittest

from src.scripts.bmad_compile import errors
from src.scripts.bmad_compile.errors import (
    ERROR_CODES,
    CompilerError,
    CyclicIncludeError,
    LockfileVersionMismatchError,
    MissingFragmentError,
    OverrideOutsideRootError,
    PrecedenceUndefinedError,
    UnknownDirectiveError,
    UnresolvedVariableError,
)


class TestErrorCodes(unittest.TestCase):
    def test_exactly_seven_frozen_codes(self) -> None:
        expected = {
            "UNKNOWN_DIRECTIVE",
            "UNRESOLVED_VARIABLE",
            "MISSING_FRAGMENT",
            "CYCLIC_INCLUDE",
            "OVERRIDE_OUTSIDE_ROOT",
            "LOCKFILE_VERSION_MISMATCH",
            "PRECEDENCE_UNDEFINED",
        }
        self.assertEqual(ERROR_CODES, expected)

    def test_error_codes_is_frozen(self) -> None:
        self.assertIsInstance(ERROR_CODES, frozenset)


class TestSubclassCodeImmutability(unittest.TestCase):
    """Each subclass carries a hard-coded code that matches its role."""

    CASES: list[tuple[type[CompilerError], str]] = [
        (UnknownDirectiveError, "UNKNOWN_DIRECTIVE"),
        (UnresolvedVariableError, "UNRESOLVED_VARIABLE"),
        (MissingFragmentError, "MISSING_FRAGMENT"),
        (CyclicIncludeError, "CYCLIC_INCLUDE"),
        (OverrideOutsideRootError, "OVERRIDE_OUTSIDE_ROOT"),
        (LockfileVersionMismatchError, "LOCKFILE_VERSION_MISMATCH"),
        (PrecedenceUndefinedError, "PRECEDENCE_UNDEFINED"),
    ]

    def test_each_subclass_exposes_its_code(self) -> None:
        for cls, expected_code in self.CASES:
            with self.subTest(cls=cls.__name__):
                err = cls("irrelevant", file="f.md", line=1, col=1)
                self.assertEqual(err.code, expected_code)

    def test_code_is_read_only_per_instance(self) -> None:
        for cls, _ in self.CASES:
            with self.subTest(cls=cls.__name__):
                err = cls("x", file="f.md", line=1, col=1)
                with self.assertRaises(AttributeError):
                    err.code = "HIJACKED"  # type: ignore[misc]


class TestFormatShape(unittest.TestCase):
    SOURCE = "line 1\n<<foo>> on line 2\nline 3\n"

    def _render(self) -> str:
        err = UnknownDirectiveError(
            "unknown directive '<<foo>>'",
            file="foo.template.md",
            line=2,
            col=1,
            token="<<foo>>",
            hint="directive '<<foo>>' on line 2 is not recognized",
        )
        return err.format(source=self.SOURCE)

    def test_header_starts_with_code(self) -> None:
        rendered = self._render()
        self.assertTrue(rendered.startswith("UNKNOWN_DIRECTIVE:"))

    def test_header_carries_path_line_col(self) -> None:
        rendered = self._render()
        self.assertIn("foo.template.md:2:1:", rendered)

    def test_has_hint(self) -> None:
        rendered = self._render()
        self.assertIn("hint:", rendered)

    def test_has_caret_span_of_at_least_one_caret(self) -> None:
        rendered = self._render()
        caret_lines = [ln for ln in rendered.split("\n") if "^" in ln]
        self.assertGreaterEqual(len(caret_lines), 1)
        self.assertGreaterEqual(caret_lines[0].count("^"), 1)

    def test_see_anchor_present(self) -> None:
        rendered = self._render()
        self.assertIn("[see: bmad docs errors#UNKNOWN_DIRECTIVE]", rendered)

    def test_two_line_context_window(self) -> None:
        rendered = self._render()
        self.assertIn("line 1", rendered)
        self.assertIn("<<foo>> on line 2", rendered)
        self.assertIn("line 3", rendered)

    def test_context_truncates_at_start(self) -> None:
        err = UnknownDirectiveError(
            "bad", file="a.md", line=1, col=1, token="<<x>>", hint="h"
        )
        rendered = err.format(source="<<x>> only line\n")
        self.assertTrue(rendered.startswith("UNKNOWN_DIRECTIVE:"))
        # No line 0 should render
        self.assertNotIn("  0|", rendered)

    def test_context_truncates_at_end(self) -> None:
        src = "a\nb\n"
        err = UnknownDirectiveError("bad", file="f.md", line=2, col=1, token="b", hint="h")
        rendered = err.format(source=src)
        # Line 3 doesn't exist
        self.assertNotIn("  3|", rendered)


class TestCyclicChainRendering(unittest.TestCase):
    def test_chain_line_only_for_cyclic(self) -> None:
        err = CyclicIncludeError(
            "cycle",
            file="a.md",
            line=1,
            col=1,
            chain=["a.md", "b.md", "a.md"],
            hint="break cycle",
        )
        rendered = err.format(source="x\n")
        self.assertIn("[chain: a.md -> b.md -> a.md]", rendered)

    def test_chain_line_absent_for_other_errors(self) -> None:
        # `chain` is only on CyclicIncludeError; other error types never
        # render a `[chain: ...]` block regardless of their content.
        err = UnknownDirectiveError(
            "bad", file="a.md", line=1, col=1, token="<<x>>", hint="h"
        )
        rendered = err.format(source="<<x>>\n")
        self.assertNotIn("[chain:", rendered)


class TestSubclassesListed(unittest.TestCase):
    def test_seven_subclasses_exported(self) -> None:
        self.assertEqual(len(errors.SUBCLASSES), 7)
        for cls in errors.SUBCLASSES:
            with self.subTest(cls=cls.__name__):
                self.assertTrue(issubclass(cls, CompilerError))
        self.assertEqual(
            set(errors.SUBCLASSES),
            {
                errors.UnknownDirectiveError,
                errors.UnresolvedVariableError,
                errors.MissingFragmentError,
                errors.CyclicIncludeError,
                errors.OverrideOutsideRootError,
                errors.LockfileVersionMismatchError,
                errors.PrecedenceUndefinedError,
            },
        )


if __name__ == "__main__":
    unittest.main()
