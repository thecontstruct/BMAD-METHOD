"""Unit tests for bmad_compile.parser — passthrough + unknown-directive + variable tokenization."""

from __future__ import annotations

import unittest

from src.scripts.bmad_compile import parser
from src.scripts.bmad_compile.errors import UnknownDirectiveError
from src.scripts.bmad_compile.parser import Include, Text, VarCompile, VarRuntime, parse


class TestPassthrough(unittest.TestCase):
    def test_plain_markdown_returns_single_text_node(self) -> None:
        src = "# Heading\n\nA paragraph.\n"
        nodes = parse(src, "plain.template.md")
        self.assertEqual(len(nodes), 1)
        self.assertIsInstance(nodes[0], Text)

    def test_content_is_byte_identical(self) -> None:
        src = "# H\n\nbody\n\n```\ncode\n```\n"
        nodes = parse(src, "x.md")
        self.assertEqual(nodes[0].content, src)

    def test_empty_input(self) -> None:
        nodes = parse("", "empty.md")
        self.assertEqual(nodes, [Text(content="", line=1, col=1)])

    def test_crlf_content_passes_through_at_parser_layer(self) -> None:
        """Parser is pure; it does not normalize newlines.

        Newline normalization is io.py's job (layer 2). By the time parser sees
        the string, it's already LF-only — but even if it weren't, parser would
        not touch it.
        """
        src = "a\r\nb\r\n"
        nodes = parse(src, "x.md")
        self.assertEqual(nodes[0].content, src)


class TestUnknownDirective(unittest.TestCase):
    def test_simple_foo_raises(self) -> None:
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse("<<foo>>", "t.md")
        err = cm.exception
        self.assertEqual(err.code, "UNKNOWN_DIRECTIVE")
        self.assertEqual(err.line, 1)
        self.assertEqual(err.col, 1)
        self.assertEqual(err.file, "t.md")
        self.assertEqual(err.token, "<<foo>>")

    def test_line_tracker_multi_line(self) -> None:
        src = "line 1\n<<foo>> on line 2\nline 3\n"
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse(src, "foo.template.md")
        err = cm.exception
        self.assertEqual(err.line, 2)
        self.assertEqual(err.col, 1)
        self.assertEqual(err.token, "<<foo>>")

    def test_col_is_offset_of_opening_angles(self) -> None:
        src = "hello <<bar>> world"
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse(src, "t.md")
        err = cm.exception
        self.assertEqual(err.line, 1)
        self.assertEqual(err.col, 7)  # 1-based col of first '<'

    def test_include_directive_still_unknown_this_story(self) -> None:
        """Story 1.1 does not handle `<<include ...>>` — it should raise.

        Story 1.2 will recognize `<<include>>`. Until then, every `<<...>>` is
        an unknown directive. The hint text can mention <<include>> even here;
        only the shape of the error is part of the frozen contract.
        """
        with self.assertRaises(UnknownDirectiveError):
            parse("<<include ./frag.md>>\n", "t.md")

    def test_first_directive_reported_when_multiple(self) -> None:
        src = "a\n<<first>>\n<<second>>\n"
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse(src, "t.md")
        err = cm.exception
        self.assertEqual(err.line, 2)
        self.assertEqual(err.token, "<<first>>")

    def test_error_formats_with_caret_under_token(self) -> None:
        src = "<<foo>>"
        try:
            parse(src, "t.md")
        except UnknownDirectiveError as e:
            rendered = e.format()
            self.assertIn("UNKNOWN_DIRECTIVE:", rendered)
            self.assertIn("t.md:1:1:", rendered)
            # token is 7 chars; caret span should be at least 7
            caret_lines = [ln for ln in rendered.split("\n") if "^" in ln]
            self.assertTrue(caret_lines)
            self.assertGreaterEqual(caret_lines[0].count("^"), 7)
            return
        self.fail("expected UnknownDirectiveError")


class TestIncludeTokenization(unittest.TestCase):
    """Story 1.2 AC 8: `<<include path="..." [name="val"]*>>` tokenization."""

    def test_parses_bare_include_path(self) -> None:
        nodes = parse('<<include path="fragments/a.template.md">>', "t.md")
        self.assertEqual(len(nodes), 1)
        self.assertEqual(
            nodes[0],
            Include(src="fragments/a.template.md", props=(), line=1, col=1,
                    raw_token='<<include path="fragments/a.template.md">>'),
        )

    def test_parses_include_with_one_attribute(self) -> None:
        nodes = parse(
            '<<include path="fragments/intro.template.md" heading-level="2">>',
            "t.md",
        )
        self.assertEqual(len(nodes), 1)
        self.assertIsInstance(nodes[0], Include)
        inc = nodes[0]
        self.assertEqual(inc.src, "fragments/intro.template.md")
        self.assertEqual(inc.props, (("heading-level", "2"),))

    def test_parses_include_with_multiple_attributes_sorted(self) -> None:
        # Authored order: z before a — resolved order must be alphabetical.
        nodes = parse(
            '<<include path="fragments/x.template.md" z="1" a="2">>', "t.md"
        )
        self.assertIsInstance(nodes[0], Include)
        self.assertEqual(nodes[0].props, (("a", "2"), ("z", "1")))

    def test_include_line_col_points_at_first_angle(self) -> None:
        src = "line 1\nline 2\n    <<include path=\"fragments/a.template.md\">>\n"
        nodes = parse(src, "t.md")
        includes = [n for n in nodes if isinstance(n, Include)]
        self.assertEqual(len(includes), 1)
        self.assertEqual(includes[0].line, 3)
        self.assertEqual(includes[0].col, 5)

    def test_text_between_includes_becomes_separate_text_nodes(self) -> None:
        src = 'text <<include path="a.template.md">> more'
        nodes = parse(src, "t.md")
        self.assertEqual(len(nodes), 3)
        self.assertIsInstance(nodes[0], Text)
        self.assertEqual(nodes[0].content, "text ")
        self.assertIsInstance(nodes[1], Include)
        self.assertEqual(nodes[1].src, "a.template.md")
        self.assertIsInstance(nodes[2], Text)
        self.assertEqual(nodes[2].content, " more")

    def test_adjacent_includes_have_no_empty_text_between(self) -> None:
        src = '<<include path="a.template.md">><<include path="b.template.md">>'
        nodes = parse(src, "t.md")
        self.assertEqual(len(nodes), 2)
        self.assertIsInstance(nodes[0], Include)
        self.assertIsInstance(nodes[1], Include)
        self.assertEqual(nodes[0].src, "a.template.md")
        self.assertEqual(nodes[1].src, "b.template.md")

    def test_story_12_text_passthrough_for_var_tokens_now_tokenizes(self) -> None:
        """Story 1.3 activates {{var}} / {var} tokenization (was deferred in 1.2).

        The old assertion — that the source parses to a single Text passthrough
        node — is replaced by the new expectation that each token is emitted as
        the correct AST node type.
        """
        src = "{{foo}} and {bar} and {{self.x.y}}"
        nodes = parse(src, "t.md")
        self.assertEqual(len(nodes), 5)
        self.assertIsInstance(nodes[0], VarCompile)
        self.assertEqual(nodes[0].name, "foo")
        self.assertIsInstance(nodes[1], Text)
        self.assertEqual(nodes[1].content, " and ")
        self.assertIsInstance(nodes[2], VarRuntime)
        self.assertEqual(nodes[2].name, "bar")
        self.assertIsInstance(nodes[3], Text)
        self.assertEqual(nodes[3].content, " and ")
        self.assertIsInstance(nodes[4], VarCompile)
        self.assertEqual(nodes[4].name, "self.x.y")

    def test_malformed_include_raises_unknown_directive_missing_path(self) -> None:
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse("<<include>>", "t.md")
        self.assertEqual(cm.exception.token, "<<include>>")

    def test_malformed_include_raises_unknown_directive_wrong_attr_name(self) -> None:
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse('<<include src="foo">>', "t.md")
        self.assertEqual(cm.exception.token, '<<include src="foo">>')

    def test_malformed_include_raises_unknown_directive_unbalanced_quote(self) -> None:
        with self.assertRaises(UnknownDirectiveError):
            parse('<<include path="foo>>\n', "t.md")

    def test_malformed_include_raises_unknown_directive_unknown_name(self) -> None:
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse("<<incude>>", "t.md")
        self.assertEqual(cm.exception.token, "<<incude>>")

    def test_malformed_include_raises_unknown_directive_newline_in_value(self) -> None:
        src = '<<include path="foo\nbar">>'
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse(src, "t.md")
        # Token truncates at newline — first line's `<<` tail is reported.
        self.assertTrue(cm.exception.token.startswith("<<include"))
        self.assertNotIn("\n", cm.exception.token)

    def test_embedded_escaped_quote_raises_unknown_directive(self) -> None:
        src = '<<include path="a\\"b">>'
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse(src, "t.md")
        self.assertTrue(
            "split the attribute" in (cm.exception.hint or "")
            or "remove the embedded quote" in (cm.exception.hint or ""),
            msg=f"unexpected hint: {cm.exception.hint!r}",
        )

    def test_premature_angle_bracket_in_value_is_not_a_silent_split(self) -> None:
        """Value with stray `<` / `>` must not yield a silent short-path Include."""
        src = '<<include path="a">x<b">>'
        try:
            nodes = parse(src, "t.md")
        except UnknownDirectiveError:
            return  # acceptable outcome
        # If no error raised, no Include with src="a" may have leaked.
        includes = [n for n in nodes if isinstance(n, Include)]
        for inc in includes:
            self.assertNotEqual(inc.src, "a")


class TestParserValidation(unittest.TestCase):
    """Review-patch coverage: edge cases discovered post-implementation."""

    def test_whitespace_only_path_raises(self) -> None:
        """P13: path=" " must raise rather than produce a space-leaf MISSING_FRAGMENT."""
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse('<<include path=" ">>', "t.md")
        self.assertIn("non-empty", cm.exception.hint or "")

    def test_path_with_embedded_gt_raises(self) -> None:
        """P14: `>>` inside a path value must not be silently accepted."""
        with self.assertRaises(UnknownDirectiveError):
            parse('<<include path="a>>b">>', "t.md")

    def test_duplicate_attribute_name_raises(self) -> None:
        """P3: duplicate extra attrs silently collapse after sort — detect and reject."""
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse('<<include path="f.template.md" x="1" x="2">>', "t.md")
        self.assertIn("duplicate", (cm.exception.hint or "").lower())

    def test_duplicate_path_attribute_raises(self) -> None:
        """P4: a second `path=` in extras must be rejected explicitly."""
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse('<<include path="f.template.md" path="g.template.md">>', "t.md")
        self.assertIn("duplicate", (cm.exception.hint or "").lower())

    def test_underscore_leading_attr_name_accepted(self) -> None:
        """P18: `_foo="v"` must not raise — underscore is a valid leading char."""
        nodes = parse('<<include path="f.template.md" _foo="v">>', "t.md")
        self.assertEqual(len(nodes), 1)
        self.assertIsInstance(nodes[0], Include)
        self.assertEqual(nodes[0].props, (("_foo", "v"),))

    def test_absolute_path_raises(self) -> None:
        """R4-P1: absolute POSIX paths bypass tier-cascade anchoring and would
        be read verbatim by the resolver. Reject at parse time."""
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse('<<include path="/etc/passwd">>', "t.md")
        self.assertIn("absolute", (cm.exception.hint or "").lower())

    def test_absolute_path_with_template_suffix_still_raises(self) -> None:
        """R4-P1: even well-formed absolute paths are rejected — no carve-outs."""
        with self.assertRaises(UnknownDirectiveError):
            parse('<<include path="/tmp/evil.template.md">>', "t.md")

    def test_null_byte_in_path_raises(self) -> None:
        """R7-P2: embedded `\\x00` in path values would slip through the
        regex char-class `[^"\\n>]+` and crash later in
        `pathlib.Path.is_file()` with raw `ValueError("embedded null
        byte")` outside the `CompilerError` taxonomy. Reject at parse."""
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse('<<include path="frag\x00s/a.template.md">>', "t.md")
        self.assertIn("control", (cm.exception.hint or "").lower())

    def test_other_c0_control_in_path_raises(self) -> None:
        """R7-P2: every C0 control (`\\x01`-`\\x1F`) and `\\x7F` are
        rejected — same containment rationale as null byte."""
        for ch in ("\x01", "\x07", "\x1f", "\x7f"):
            with self.subTest(ch=hex(ord(ch))):
                with self.assertRaises(UnknownDirectiveError):
                    parse(f'<<include path="frag{ch}s/a.template.md">>', "t.md")

    def test_tab_in_path_is_rejected(self) -> None:
        """R7-P2 follow-on: `\\t` is `\\x09`, a C0 control. Reject."""
        with self.assertRaises(UnknownDirectiveError):
            parse('<<include path="frag\ts/a.template.md">>', "t.md")

    def test_backslash_in_path_rejected(self) -> None:
        source = '<<include path="fragments\\a.template.md">>'
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse(source, "skill.template.md")
        self.assertIn("backslash", cm.exception.hint)
        self.assertIn("forward slashes", cm.exception.hint)


class TestVariableTokenization(unittest.TestCase):
    """Story 1.3 — {{var}} VarCompile and {var} VarRuntime tokenization."""

    def test_var_compile_simple(self) -> None:
        nodes = parse("{{user_name}}", "t.md")
        self.assertEqual(len(nodes), 1)
        self.assertIsInstance(nodes[0], VarCompile)
        self.assertEqual(nodes[0].name, "user_name")
        self.assertEqual(nodes[0].line, 1)
        self.assertEqual(nodes[0].col, 1)

    def test_var_compile_self_dotted(self) -> None:
        nodes = parse("{{self.agent.name}}", "t.md")
        self.assertEqual(len(nodes), 1)
        self.assertIsInstance(nodes[0], VarCompile)
        self.assertEqual(nodes[0].name, "self.agent.name")

    def test_var_compile_self_deep_dotted(self) -> None:
        nodes = parse("{{self.workflow.title}}", "t.md")
        self.assertEqual(len(nodes), 1)
        self.assertIsInstance(nodes[0], VarCompile)
        self.assertEqual(nodes[0].name, "self.workflow.title")

    def test_var_runtime_simple(self) -> None:
        nodes = parse("{runtime_var}", "t.md")
        self.assertEqual(len(nodes), 1)
        self.assertIsInstance(nodes[0], VarRuntime)
        self.assertEqual(nodes[0].name, "runtime_var")
        self.assertEqual(nodes[0].line, 1)
        self.assertEqual(nodes[0].col, 1)

    def test_var_compile_line_col(self) -> None:
        # {{user_name}} starts at line 3, col 5 (4 spaces of indent).
        src = "line1\nline2\n    {{user_name}}"
        nodes = parse(src, "t.md")
        var_nodes = [n for n in nodes if isinstance(n, VarCompile)]
        self.assertEqual(len(var_nodes), 1)
        self.assertEqual(var_nodes[0].line, 3)
        self.assertEqual(var_nodes[0].col, 5)

    def test_var_runtime_line_col(self) -> None:
        # {var} starts at line 2, col 3 (two spaces of indent).
        src = "x\n  {var}"
        nodes = parse(src, "t.md")
        var_nodes = [n for n in nodes if isinstance(n, VarRuntime)]
        self.assertEqual(len(var_nodes), 1)
        self.assertEqual(var_nodes[0].line, 2)
        self.assertEqual(var_nodes[0].col, 3)

    def test_mixed_compile_and_runtime(self) -> None:
        src = "Hello {{name}}! Your ref is {ref}."
        nodes = parse(src, "t.md")
        self.assertEqual(len(nodes), 5)
        self.assertIsInstance(nodes[0], Text)
        self.assertEqual(nodes[0].content, "Hello ")
        self.assertIsInstance(nodes[1], VarCompile)
        self.assertEqual(nodes[1].name, "name")
        self.assertIsInstance(nodes[2], Text)
        self.assertEqual(nodes[2].content, "! Your ref is ")
        self.assertIsInstance(nodes[3], VarRuntime)
        self.assertEqual(nodes[3].name, "ref")
        self.assertIsInstance(nodes[4], Text)
        self.assertEqual(nodes[4].content, ".")

    def test_triple_brace_compile_flanked(self) -> None:
        # {{{foo}}} → [Text("{"), VarCompile("foo"), Text("}")]
        nodes = parse("{{{foo}}}", "t.md")
        self.assertEqual(len(nodes), 3)
        self.assertIsInstance(nodes[0], Text)
        self.assertEqual(nodes[0].content, "{")
        self.assertIsInstance(nodes[1], VarCompile)
        self.assertEqual(nodes[1].name, "foo")
        self.assertIsInstance(nodes[2], Text)
        self.assertEqual(nodes[2].content, "}")

    def test_single_brace_not_followed_by_ident_is_text(self) -> None:
        for src in ("{ }", "{123}", "{}"):
            with self.subTest(src=src):
                nodes = parse(src, "t.md")
                # Must produce only Text nodes — no VarRuntime, no error.
                for n in nodes:
                    self.assertIsInstance(n, Text)
                full = "".join(n.content for n in nodes)
                self.assertEqual(full, src)

    def test_malformed_double_brace_leading_digit_raises(self) -> None:
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse("{{123var}}", "t.md")
        err = cm.exception
        self.assertEqual(err.code, "UNKNOWN_DIRECTIVE")
        self.assertEqual(err.line, 1)
        self.assertEqual(err.col, 1)

    def test_malformed_double_brace_empty_raises(self) -> None:
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse("{{}}", "t.md")
        self.assertEqual(cm.exception.code, "UNKNOWN_DIRECTIVE")

    def test_malformed_double_brace_trailing_dot_raises(self) -> None:
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse("{{self.}}", "t.md")
        self.assertEqual(cm.exception.code, "UNKNOWN_DIRECTIVE")

    def test_unterminated_double_brace_raises(self) -> None:
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse("{{unclosed", "t.md")
        self.assertEqual(cm.exception.code, "UNKNOWN_DIRECTIVE")

    def test_malformed_double_brace_hint_lists_four_constructs(self) -> None:
        """AC 4: hint must name the four valid constructs.

        R4 patch: prior tests asserted only the error code; a regression that
        dropped one of the four bullets would not be caught.
        """
        with self.assertRaises(UnknownDirectiveError) as cm:
            parse("{{123bad}}", "t.md")
        hint = cm.exception.hint or ""
        self.assertIn("<<include", hint)
        self.assertIn("{{var_name}}", hint)
        self.assertIn("{{self.", hint)
        self.assertIn("{var_name}", hint)

    def test_var_compile_and_include_in_same_source(self) -> None:
        src = '{{name}} <<include path="fragments/x.template.md">>'
        nodes = parse(src, "t.md")
        self.assertEqual(len(nodes), 3)
        self.assertIsInstance(nodes[0], VarCompile)
        self.assertEqual(nodes[0].name, "name")
        self.assertIsInstance(nodes[1], Text)
        self.assertEqual(nodes[1].content, " ")
        self.assertIsInstance(nodes[2], Include)
        self.assertEqual(nodes[2].src, "fragments/x.template.md")

    def test_existing_passthrough_suite_unchanged(self) -> None:
        """All existing parser behaviors from Stories 1.1 and 1.2 still hold."""
        # Plain text round-trips.
        src = "# Heading\n\nParagraph.\n"
        nodes = parse(src, "t.md")
        self.assertEqual(len(nodes), 1)
        self.assertIsInstance(nodes[0], Text)
        self.assertEqual(nodes[0].content, src)

        # Empty input still yields a single empty Text node.
        self.assertEqual(parse("", "e.md"), [Text(content="", line=1, col=1)])

        # Include still produces an Include node.
        inc_nodes = parse('<<include path="f.template.md">>', "t.md")
        self.assertEqual(len(inc_nodes), 1)
        self.assertIsInstance(inc_nodes[0], Include)


class TestTripleBraceEdgeCases(unittest.TestCase):
    """Story 1.4 AC 12 — triple-brace edge cases pinned against regression."""

    def test_four_brace_sequence_parses_correctly(self) -> None:
        # {{{{foo}}}} → semantically: two leading { as Text + VarCompile("foo") + Text("}}")
        nodes = parse("{{{{foo}}}}", "t.md")
        var_nodes = [n for n in nodes if isinstance(n, VarCompile)]
        text_content = "".join(n.content for n in nodes if isinstance(n, Text))
        # Exactly one VarCompile for "foo"
        self.assertEqual(len(var_nodes), 1)
        self.assertEqual(var_nodes[0].name, "foo")
        # Two leading braces + two trailing braces in text nodes
        self.assertIn("{{", text_content)
        self.assertIn("}}", text_content)

    def test_extra_trailing_brace_parses_correctly(self) -> None:
        # {{foo}}} → VarCompile("foo") + Text("}")
        nodes = parse("{{foo}}}", "t.md")
        var_nodes = [n for n in nodes if isinstance(n, VarCompile)]
        self.assertEqual(len(var_nodes), 1)
        self.assertEqual(var_nodes[0].name, "foo")
        text_nodes = [n for n in nodes if isinstance(n, Text)]
        self.assertTrue(text_nodes)
        trailing = "".join(n.content for n in text_nodes)
        self.assertEqual(trailing, "}")


class TestParserPurity(unittest.TestCase):
    def test_parser_module_imports_only_errors_from_bmad_compile(self) -> None:
        """Layering: parser imports `errors` and no other internal module."""
        import ast

        src_path = (
            __import__("pathlib").Path(__file__).parent.parent.parent
            / "src" / "scripts" / "bmad_compile" / "parser.py"
        )
        tree = ast.parse(src_path.read_text(encoding="utf-8"))
        internal_imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if node.level > 0:  # relative import
                    for alias in node.names:
                        internal_imports.append(alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("bmad_compile"):
                        internal_imports.append(alias.name)
        # Only `errors` should be pulled in from sibling modules
        self.assertEqual(set(internal_imports), {"errors"})


if __name__ == "__main__":
    unittest.main()
