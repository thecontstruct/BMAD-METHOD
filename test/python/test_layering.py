"""AST-layering enforcement: no module may import from a strictly higher layer.

See `src/scripts/bmad_compile/LAYERING.md` for the ten-layer ordering and
motivation. This test parses each `bmad_compile/*.py` module with stdlib `ast`
and walks import nodes — no runtime imports are triggered, so the check is
deterministic and fast. Modules not yet created (later stories) are skipped.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

LAYERS: list[str] = [
    "errors",        # 1
    "io",            # 2
    "parser",        # 3
    "toml_merge",    # 4
    "variants",      # 5
    "resolver",      # 6
    "lockfile",      # 7
    "explain",       # 8
    "engine",        # 9
    "lazy_compile",  # 10
]

PKG_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "src" / "scripts" / "bmad_compile"
)


def _layer_index(module_name: str) -> int | None:
    try:
        return LAYERS.index(module_name)
    except ValueError:
        return None


def _internal_imports(tree: ast.Module) -> list[str]:
    """Return the set of sibling `bmad_compile.*` module names imported."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level > 0:
                # relative: `from . import foo` or `from .foo import x`
                if node.module:
                    names.append(node.module.split(".", 1)[0])
                else:
                    for alias in node.names:
                        names.append(alias.name.split(".", 1)[0])
            elif node.module and node.module.startswith("bmad_compile"):
                parts = node.module.split(".")
                if len(parts) > 1:
                    names.append(parts[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("bmad_compile."):
                    names.append(alias.name.split(".", 1)[1].split(".", 1)[0])
    return names


class TestLayering(unittest.TestCase):
    def test_package_dir_exists(self) -> None:
        self.assertTrue(PKG_DIR.is_dir(), f"expected {PKG_DIR} to exist")

    def test_no_upward_imports(self) -> None:
        self.assertTrue(PKG_DIR.is_dir())
        for module_path in sorted(PKG_DIR.glob("*.py")):
            module_name = module_path.stem
            if module_name == "__init__":
                continue
            importer_layer = _layer_index(module_name)
            if importer_layer is None:
                # Not in the formal layer list — probably a helper; skip.
                continue

            with self.subTest(module=module_name):
                tree = ast.parse(module_path.read_text(encoding="utf-8"))
                imports = _internal_imports(tree)
                for imported in imports:
                    imported_layer = _layer_index(imported)
                    if imported_layer is None:
                        continue  # not a layered module
                    # Skip modules that don't exist yet (later stories).
                    if not (PKG_DIR / f"{imported}.py").exists():
                        continue
                    self.assertLessEqual(
                        imported_layer,
                        importer_layer,
                        msg=(
                            f"{module_name} (layer {importer_layer + 1}) "
                            f"imports {imported} (layer {imported_layer + 1}) "
                            "— upward import forbidden"
                        ),
                    )

    def test_errors_has_no_internal_imports(self) -> None:
        """errors.py is layer 1 — nothing internal should be imported."""
        tree = ast.parse((PKG_DIR / "errors.py").read_text(encoding="utf-8"))
        self.assertEqual(_internal_imports(tree), [])

    def test_parser_imports_only_errors(self) -> None:
        """parser.py (layer 3) must import `errors` only — not `io`."""
        tree = ast.parse((PKG_DIR / "parser.py").read_text(encoding="utf-8"))
        self.assertEqual(set(_internal_imports(tree)), {"errors"})

    def test_io_imports_only_errors(self) -> None:
        """io.py (layer 2) depends on errors for the OverrideOutsideRootError."""
        tree = ast.parse((PKG_DIR / "io.py").read_text(encoding="utf-8"))
        self.assertEqual(set(_internal_imports(tree)), {"errors"})

    def test_engine_imports_from_lower_layers_only(self) -> None:
        tree = ast.parse((PKG_DIR / "engine.py").read_text(encoding="utf-8"))
        engine_layer = LAYERS.index("engine")
        for imported in set(_internal_imports(tree)):
            layer = _layer_index(imported)
            if layer is None:
                continue
            with self.subTest(imported=imported):
                self.assertLessEqual(layer, engine_layer)

    def test_resolver_imports_within_allowed_set(self) -> None:
        """LAYERING.md row 6: resolver may import errors, io, parser, toml_merge, variants."""
        resolver_path = PKG_DIR / "resolver.py"
        if not resolver_path.exists():
            self.skipTest("resolver.py not yet created")
        allowed = {"errors", "io", "parser", "toml_merge", "variants"}
        tree = ast.parse(resolver_path.read_text(encoding="utf-8"))
        actual = set(_internal_imports(tree))
        unknown = actual - allowed
        self.assertFalse(
            unknown,
            msg=f"resolver imports modules outside its allowed set: {unknown}",
        )


if __name__ == "__main__":
    unittest.main()
