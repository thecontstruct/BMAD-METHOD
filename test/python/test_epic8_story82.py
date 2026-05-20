"""Tests for Story 8.2 — Component Parser."""

from __future__ import annotations

import dataclasses
import unittest

from src.scripts.bmad_compile import errors, parser


class TestComponentNameToPath(unittest.TestCase):
    def test_a_date_banner(self):
        assert parser.component_name_to_path("DateBanner") == "components/date_banner.py"

    def test_b_xml_parser(self):
        # Consecutive uppercase letters: no underscores between them
        assert parser.component_name_to_path("XMLParser") == "components/xmlparser.py"

    def test_c_my_xml_parser(self):
        assert parser.component_name_to_path("MyXMLParser") == "components/my_xmlparser.py"


class TestComponentInvocationParse(unittest.TestCase):
    def test_d_simple_tag(self):
        nodes = parser.parse("<Foo />", "t.md")
        ci = [n for n in nodes if isinstance(n, parser.ComponentInvocation)]
        self.assertEqual(len(ci), 1)
        self.assertEqual(ci[0].name, "Foo")
        self.assertEqual(ci[0].props, ())
        self.assertEqual(ci[0].line, 1)
        self.assertEqual(ci[0].col, 1)

    def test_e_spurious_prop_guard(self):
        # bar value contains `=` and `{` — must not produce a spurious `x` prop
        nodes = parser.parse('<Foo bar="x={3}" />', "t.md")
        ci = [n for n in nodes if isinstance(n, parser.ComponentInvocation)]
        self.assertEqual(len(ci), 1)
        self.assertEqual(ci[0].props, (("bar", "x={3}"),))

    def test_f_string_prop(self):
        nodes = parser.parse('<Foo bar="hello" />', "t.md")
        ci = [n for n in nodes if isinstance(n, parser.ComponentInvocation)]
        self.assertEqual(ci[0].props, (("bar", "hello"),))

    def test_g_int_prop(self):
        nodes = parser.parse("<Foo count={42} />", "t.md")
        ci = [n for n in nodes if isinstance(n, parser.ComponentInvocation)]
        self.assertEqual(ci[0].props, (("count", 42),))
        self.assertIsInstance(ci[0].props[0][1], int)

    def test_h_bool_prop(self):
        nodes = parser.parse("<Foo enabled={true} />", "t.md")
        ci = [n for n in nodes if isinstance(n, parser.ComponentInvocation)]
        self.assertEqual(ci[0].props, (("enabled", True),))
        self.assertIsInstance(ci[0].props[0][1], bool)

    def test_i_duplicate_prop_raises(self):
        with self.assertRaises(errors.UnknownDirectiveError):
            parser.parse('<Foo a="1" a="2" />', "t.md")


class TestFenceTracking(unittest.TestCase):
    def test_j_tag_inside_backtick_fence(self):
        source = "```\n<Foo />\n```\n"
        nodes = parser.parse(source, "t.md")
        ci = [n for n in nodes if isinstance(n, parser.ComponentInvocation)]
        self.assertEqual(ci, [], "tag inside backtick fence must not produce ComponentInvocation")

    def test_k_tag_inside_tilde_fence(self):
        source = "~~~\n<Foo />\n~~~\n"
        nodes = parser.parse(source, "t.md")
        ci = [n for n in nodes if isinstance(n, parser.ComponentInvocation)]
        self.assertEqual(ci, [], "tag inside tilde fence must not produce ComponentInvocation")

    def test_tag_after_fence_is_recognized(self):
        source = "```\n<Foo />\n```\n<Bar />\n"
        nodes = parser.parse(source, "t.md")
        ci = [n for n in nodes if isinstance(n, parser.ComponentInvocation)]
        self.assertEqual(len(ci), 1)
        self.assertEqual(ci[0].name, "Bar")


class TestFrontmatterSkip(unittest.TestCase):
    def test_l_tag_inside_frontmatter(self):
        source = "---\n<Foo />\n---\nsome text\n"
        nodes = parser.parse(source, "t.md")
        ci = [n for n in nodes if isinstance(n, parser.ComponentInvocation)]
        self.assertEqual(ci, [], "tag inside TOML frontmatter must not produce ComponentInvocation")

    def test_tag_after_frontmatter_is_recognized(self):
        source = "---\ntitle: test\n---\n<Bar />\n"
        nodes = parser.parse(source, "t.md")
        ci = [n for n in nodes if isinstance(n, parser.ComponentInvocation)]
        self.assertEqual(len(ci), 1)
        self.assertEqual(ci[0].name, "Bar")

    def test_no_frontmatter_unaffected(self):
        nodes = parser.parse("<Foo />", "t.md")
        ci = [n for n in nodes if isinstance(n, parser.ComponentInvocation)]
        self.assertEqual(len(ci), 1)


class TestMultilineTag(unittest.TestCase):
    def test_m_multiline_tag_raises(self):
        # `<` followed by uppercase then lowercase triggers inline malformed-tag detection
        with self.assertRaises(errors.UnknownDirectiveError):
            parser.parse("<Foo\n  bar='x' />", "t.md")


class TestAstNodeUnion(unittest.TestCase):
    def test_n_astnode_contains_component_invocation(self):
        import typing
        args = typing.get_args(parser.AstNode)
        self.assertIn(parser.ComponentInvocation, args)

    def test_o_component_invocation_is_frozen(self):
        ci = parser.ComponentInvocation(name="Foo", props=(), line=1, col=1)
        with self.assertRaises((dataclasses.FrozenInstanceError, TypeError)):
            ci.name = "Bar"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
