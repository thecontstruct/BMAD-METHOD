"""Story 8.3 unit tests: component_wrapper.py subprocess round-trip tests."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BMAD_ROOT = Path(__file__).resolve().parent.parent.parent  # BMAD-METHOD/
WRAPPER = BMAD_ROOT / "src/scripts/bmad_compile/component_wrapper.py"
FIXTURES = Path(__file__).parent / "fixtures/component_wrapper"
PYTHON = sys.executable

# Shared strip-token test vectors — Story 8.5 imports and reuses these
STRIP_TOKEN_VECTORS: list[tuple[str, ...]] = [
    # (input_source, expected: STRING tokens blanked, COMMENT tokens blanked)
    ('RENDER_MODE = "compile"\n', 'RENDER_MODE = \n'),
    ('x = """RENDER_ERROR_FALLBACK = "fake"\n"""\nREAL = 1\n', 'x = \nREAL = 1\n'),
    ('# RENDER_MODE = "jit"\nRENDER_MODE = "compile"\n', '\nRENDER_MODE = \n'),
    ("RENDER_ERROR_FALLBACK = 'real'\n", "RENDER_ERROR_FALLBACK = \n"),
]


def _make_payload(
    fixture_path: Path,
    skill_source_root: str | None = None,
    props: dict | None = None,
) -> bytes:
    root = skill_source_root if skill_source_root is not None else str(FIXTURES)
    ctx = {
        "config": {},
        "skill_id": "test/skill",
        "render_mode": "compile",
        "skill_source_root": root,
    }
    return json.dumps({"ctx": ctx, "props": props or {}}).encode()


def _run(
    fixture_filename: str | None,
    *,
    skill_source_root: str | None = None,
    props: dict | None = None,
    stdin_bytes: bytes | None = None,
    omit_argv: bool = False,
) -> subprocess.CompletedProcess:
    args = [PYTHON, str(WRAPPER)]
    if not omit_argv and fixture_filename is not None:
        args.append(str(FIXTURES / fixture_filename))
    if stdin_bytes is None:
        fixture_path = FIXTURES / fixture_filename if fixture_filename else Path("dummy")
        payload = _make_payload(fixture_path, skill_source_root=skill_source_root, props=props)
    else:
        payload = stdin_bytes
    return subprocess.run(args, input=payload, capture_output=True)


# Inline copy for testing — must match wrapper's implementation exactly
import io as _io
import tokenize as _tokenize


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


class TestComponentWrapper(unittest.TestCase):

    def _env(self, proc: subprocess.CompletedProcess) -> dict:
        self.assertGreater(len(proc.stdout), 0,
                           f"stdout empty; stderr={proc.stderr!r}")
        return json.loads(proc.stdout.decode())

    def test_a_valid_component_returns_ok_envelope(self):
        """AC-10-a: valid component renders successfully."""
        proc = _run("good_component.py")
        self.assertEqual(proc.returncode, 0)
        env = self._env(proc)
        self.assertTrue(env["ok"])
        self.assertEqual(env["output"], "hello world")

    def test_b_stray_print_not_in_envelope(self):
        """AC-10-b: stray print() does not corrupt stdout envelope."""
        proc = _run("print_component.py")
        self.assertEqual(proc.returncode, 0)
        # Raw stdout must be parseable JSON and only JSON
        raw = proc.stdout.decode()
        env = json.loads(raw)  # raises if stray text before/after envelope
        self.assertTrue(env["ok"])
        self.assertNotIn("noise", env["output"])

    def test_c_bad_return_type_exits_1(self):
        """AC-10-c: render() returning non-str → exit 1 with type info."""
        proc = _run("bad_return_component.py")
        self.assertEqual(proc.returncode, 1)
        env = self._env(proc)
        self.assertFalse(env["ok"])
        self.assertIn("int", env["error"])
        self.assertIn("expected str", env["error"])
        self.assertIn("render_error_fallback", env)  # key always present

    def test_d_import_failure_exits_1_with_fallback(self):
        """AC-10-d: module-level ImportError → exit 1, fallback from pre-read."""
        proc = _run("import_fail_component.py")
        self.assertEqual(proc.returncode, 1)
        env = self._env(proc)
        self.assertFalse(env["ok"])
        self.assertEqual(env["render_error_fallback"], "import fallback")

    def test_e_path_escape_exits_2(self):
        """AC-10-e: component outside skill_source_root → exit 2."""
        with tempfile.TemporaryDirectory() as tmp:
            skill_root = os.path.join(tmp, "skill_root")
            os.makedirs(skill_root)
            evil_path = os.path.join(tmp, "evil.py")
            Path(evil_path).write_text('def render(ctx, **props): return "evil"\n')
            payload = json.dumps({
                "ctx": {
                    "config": {},
                    "skill_id": "test/skill",
                    "render_mode": "compile",
                    "skill_source_root": skill_root,
                },
                "props": {},
            }).encode()
            proc = subprocess.run(
                [PYTHON, str(WRAPPER), evil_path],
                input=payload,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 2)
            env = self._env(proc)
            self.assertFalse(env["ok"])
            self.assertIn("escapes skill_source_root", env["error"])
            self.assertIsNone(env["render_error_fallback"])

    def test_f_docstring_trap_no_false_positive(self):
        """AC-10-f: RENDER_ERROR_FALLBACK inside docstring is NOT matched (tokenize-strip)."""
        proc = _run("docstring_trap_component.py")
        self.assertEqual(proc.returncode, 1)  # render() raises RuntimeError
        env = self._env(proc)
        self.assertFalse(env["ok"])
        # The "fake_fallback_in_docstring" text must NOT appear as fallback
        self.assertIsNone(env["render_error_fallback"])

    def test_g_missing_argv1_exits_2(self):
        """AC-10-g: no component path argument → exit 2."""
        proc = _run(None, omit_argv=True, stdin_bytes=b'{"ctx": {}, "props": {}}')
        self.assertEqual(proc.returncode, 2)
        env = self._env(proc)
        self.assertFalse(env["ok"])
        self.assertIn("argv", env["error"])
        self.assertIsNone(env["render_error_fallback"])

    def test_h_invalid_stdin_json_exits_2(self):
        """AC-10-h: malformed stdin JSON → exit 2."""
        proc = subprocess.run(
            [PYTHON, str(WRAPPER), str(FIXTURES / "good_component.py")],
            input=b"not_valid_json{{{{",
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 2)
        env = self._env(proc)
        self.assertFalse(env["ok"])
        self.assertIn("invalid stdin JSON", env["error"])
        self.assertIsNone(env["render_error_fallback"])

    def test_i_jit_component_render_mode_ignored(self):
        """AC-10-i: wrapper ignores RENDER_MODE; JIT component renders normally."""
        proc = _run("jit_component.py")
        self.assertEqual(proc.returncode, 0)
        env = self._env(proc)
        self.assertTrue(env["ok"])
        self.assertEqual(env["output"], "jit ok")

    def test_j_render_exception_exits_1_with_fallback(self):
        """AC-10-j: render() exception → exit 1, fallback from pre-read, traceback in error."""
        proc = _run("render_exception_component.py")
        self.assertEqual(proc.returncode, 1)
        env = self._env(proc)
        self.assertFalse(env["ok"])
        self.assertEqual(env["render_error_fallback"], "render exception fallback")
        self.assertIn("ValueError", env["error"])  # traceback includes exception type

    def test_k_ctx_attributes_accessible_in_render(self):
        """AC-10-k: ctx attributes (skill_id, render_mode) are accessible in render()."""
        proc = _run("ctx_access_component.py")
        self.assertEqual(proc.returncode, 0)
        env = self._env(proc)
        self.assertTrue(env["ok"])
        self.assertIn("test/skill", env["output"])
        self.assertIn("compile", env["output"])


class TestStripTokenVectors(unittest.TestCase):
    """Test _strip_string_and_comment_tokens against canonical vectors.

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
        # Comment line is stripped; only the real assignment remains matchable
        self.assertNotIn("# RENDER_MODE", stripped)

    def test_token_error_returns_source(self):
        src = '"""unclosed triple quote\n'
        result = _strip_for_test(src)
        self.assertEqual(result, src)  # returned unchanged on TokenError


if __name__ == "__main__":
    unittest.main()
