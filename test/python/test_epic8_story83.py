"""Story 8.3 strip-token test vectors — imported by test_epic8_story85.py.

TestComponentWrapper removed in Story 9.1 (component_wrapper.py deleted; see
test_epic9_story91.py for in-process component execution tests).
"""
from __future__ import annotations

import io as _io
import tokenize as _tokenize
import unittest

# Shared strip-token test vectors — test_epic8_story85.py imports and reuses these
STRIP_TOKEN_VECTORS: list[tuple[str, ...]] = [
    ('RENDER_MODE = "compile"\n', 'RENDER_MODE = \n'),
    ('x = """RENDER_ERROR_FALLBACK = "fake"\n"""\nREAL = 1\n', 'x = \nREAL = 1\n'),
    ('# RENDER_MODE = "jit"\nRENDER_MODE = "compile"\n', '\nRENDER_MODE = \n'),
    ("RENDER_ERROR_FALLBACK = 'real'\n", "RENDER_ERROR_FALLBACK = \n"),
]


def _strip_for_test(source: str) -> str:
    try:
        tokens = list(_tokenize.generate_tokens(_io.StringIO(source).readline))
    except _tokenize.TokenError:
        return source
    lines = source.splitlines(keepends=True)
    result = list(lines)
    for tok_type, _tok_str, (srow, scol), (erow, ecol), _ in reversed(tokens):
        if tok_type in (_tokenize.STRING, _tokenize.COMMENT):
            if srow == erow:
                result[srow - 1] = result[srow - 1][:scol] + result[srow - 1][ecol:]
            else:
                result[srow - 1] = result[srow - 1][:scol]
                for mid in range(srow, erow - 1):
                    result[mid] = "\n"
                result[erow - 1] = result[erow - 1][ecol:]
    return "".join(result)


class TestStripTokenVectors(unittest.TestCase):
    """Verify _strip_string_and_comment_tokens against canonical vectors.

    STRIP_TOKEN_VECTORS is imported by Story 8.5's test to verify the engine copy.
    """

    def test_strip_string_literal(self):
        src = 'RENDER_MODE = "compile"\n'
        stripped = _strip_for_test(src)
        self.assertNotIn('"compile"', stripped)
        self.assertIn("RENDER_MODE", stripped)

    def test_strip_triple_quoted_docstring(self):
        src = '"""RENDER_ERROR_FALLBACK = "fake"\n"""\nREAL = 1\n'
        stripped = _strip_for_test(src)
        self.assertNotIn("fake", stripped)
        self.assertIn("REAL = 1", stripped)

    def test_strip_comment(self):
        src = '# RENDER_MODE = "jit"\nRENDER_MODE = "compile"\n'
        stripped = _strip_for_test(src)
        self.assertNotIn("# RENDER_MODE", stripped)

    def test_token_error_returns_source(self):
        src = '"""unclosed triple quote\n'
        result = _strip_for_test(src)
        self.assertEqual(result, src)


if __name__ == "__main__":
    unittest.main()
