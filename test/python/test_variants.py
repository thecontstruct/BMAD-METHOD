"""Unit tests for bmad_compile.variants — IDE-variant selection."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from src.scripts.bmad_compile.io import PurePosixPath
from src.scripts.bmad_compile.variants import KNOWN_IDES, _is_universal, select_variant


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


class TestVariantsExtended(unittest.TestCase):
    """Story 1.4 — additional variant coverage."""

    def test_select_variant_empty_string_treated_as_no_ide(self) -> None:
        cands = _paths("foo.cursor.template.md", "foo.template.md")
        # "" is not in KNOWN_IDES → falls through to universal
        selected = select_variant(cands, "")
        self.assertIsNotNone(selected)
        self.assertEqual(selected.name, "foo.template.md")

    def test_is_universal_rejects_ide_suffixed(self) -> None:
        self.assertFalse(_is_universal("foo.cursor.template.md"))
        self.assertFalse(_is_universal("foo.claudecode.template.md"))

    def test_is_universal_accepts_plain_suffix(self) -> None:
        self.assertTrue(_is_universal("foo.template.md"))
        self.assertTrue(_is_universal("bar-skill.template.md"))

    def test_is_universal_rejects_unknown_ide_token(self) -> None:
        # Pure universal — no IDE token slot.
        self.assertTrue(_is_universal("skill1.template.md"))
        # Known IDE variant — already covered by test_is_universal_rejects_ide_suffixed,
        # re-asserted here for completeness against the new regex.
        self.assertFalse(_is_universal("skill1.cursor.template.md"))
        # Unknown IDE-shape token — the regression-pinning case.
        # Pre-fix: returns True (treated as universal — bug). Post-fix: returns False.
        self.assertFalse(_is_universal("skill1.vscode.template.md"))
        # No `.template.md` suffix — returns False under both old and new logic.
        self.assertFalse(_is_universal("skill1.md"))

    def test_known_ides_constant(self) -> None:
        self.assertEqual(KNOWN_IDES, ("cursor", "claudecode"))

    def test_layering_variants_no_forbidden_imports(self) -> None:
        src_path = (
            Path(__file__).parent.parent.parent
            / "src" / "scripts" / "bmad_compile" / "variants.py"
        )
        tree = ast.parse(src_path.read_text(encoding="utf-8"))
        # Collect sibling module names (not imported symbol names).
        # `from .io import PurePosixPath` → module "io"
        # `from . import errors` → module "errors" (from alias.name when node.module is None)
        actual_modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level and node.level > 0:
                if node.module:
                    # e.g. `from .io import PurePosixPath` → module="io"
                    actual_modules.add(node.module.split(".")[0])
                else:
                    # e.g. `from . import errors` → alias.name="errors"
                    for alias in node.names:
                        actual_modules.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("bmad_compile"):
                # absolute: `from bmad_compile.resolver import ...`
                parts = node.module.split(".")
                if len(parts) > 1:
                    actual_modules.add(parts[1])
            elif isinstance(node, ast.Import):
                # absolute: `import bmad_compile.resolver`
                for alias in node.names:
                    if alias.name.startswith("bmad_compile."):
                        actual_modules.add(alias.name.split(".", 2)[1])
        # variants.py must NOT import resolver, toml_merge, parser, or engine
        forbidden = {"resolver", "toml_merge", "parser", "engine"}
        self.assertEqual(actual_modules & forbidden, set())
        # Must be a subset of allowed internal imports
        self.assertLessEqual(actual_modules, {"errors", "io"})


if __name__ == "__main__":
    unittest.main()
