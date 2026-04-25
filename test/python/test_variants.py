"""Unit tests for bmad_compile.variants — IDE-variant selection."""

from __future__ import annotations

import unittest

from src.scripts.bmad_compile.io import PurePosixPath
from src.scripts.bmad_compile.variants import select_variant


def _paths(*names: str) -> list[PurePosixPath]:
    return [PurePosixPath("frag") / n for n in names]


class TestSelectVariant(unittest.TestCase):
    def test_universal_only_target_none(self) -> None:
        cands = _paths("foo.template.md")
        self.assertEqual(select_variant(cands, None), cands[0])

    def test_universal_only_target_cursor(self) -> None:
        cands = _paths("foo.template.md")
        self.assertEqual(select_variant(cands, "cursor"), cands[0])

    def test_cursor_variant_preferred_for_cursor_target(self) -> None:
        cands = _paths("foo.cursor.template.md", "foo.template.md")
        self.assertEqual(
            select_variant(cands, "cursor").name,
            "foo.cursor.template.md",
        )

    def test_claudecode_variant_preferred_for_claudecode_target(self) -> None:
        cands = _paths("foo.claudecode.template.md", "foo.template.md")
        self.assertEqual(
            select_variant(cands, "claudecode").name,
            "foo.claudecode.template.md",
        )

    def test_target_none_ignores_ide_variants(self) -> None:
        cands = _paths("foo.cursor.template.md")
        self.assertIsNone(select_variant(cands, None))

    def test_unknown_ide_target_falls_back_to_universal(self) -> None:
        cands = _paths(
            "foo.cursor.template.md",
            "foo.claudecode.template.md",
            "foo.template.md",
        )
        selected = select_variant(cands, "sublime")
        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "foo.template.md")

    def test_empty_candidates_returns_none(self) -> None:
        self.assertIsNone(select_variant([], None))
        self.assertIsNone(select_variant([], "cursor"))

    def test_cursor_variant_missing_falls_back_to_universal(self) -> None:
        cands = _paths("foo.claudecode.template.md", "foo.template.md")
        selected = select_variant(cands, "cursor")
        self.assertEqual(selected.name, "foo.template.md")


if __name__ == "__main__":
    unittest.main()
