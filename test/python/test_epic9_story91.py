"""Story 9.1 unit tests: in-process ComponentRunner execution.

Replaces Story 8.3's TestComponentWrapper (subprocess-based) and Story 8.4's
subprocess-mock tests. All tests use real fixture components.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

BMAD_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "component_runner"

_SCRIPTS = str(BMAD_ROOT / "src" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import bmad_compile.component_runner as _runner_mod
from bmad_compile.component_runner import ComponentRunner, _COMPILE_BATCH_WORKERS
from bmad_compile.errors import ComponentBatchError, ComponentError, ComponentPropError

_CTX = {
    "config": {},
    "skill_id": "test/skill",
    "render_mode": "compile",
    "skill_source_root": str(FIXTURES),
}


class _OriginalToken:
    def __init__(self, name: str, props: tuple = ()):
        self.name = name
        self.props = props


class _TestInv:
    def __init__(self, token_index: int, component_path: str, name: str = "TestComp", props: tuple = ()):
        self.token_index = token_index
        self.component_abs_path = component_path
        self.render_mode = "compile"
        self.original = _OriginalToken(name, props)


class TestInProcessRunner(unittest.TestCase):

    def test_a_valid_render(self):
        """Valid component renders successfully in-process."""
        runner = ComponentRunner()
        result = runner.run_jit(
            str(FIXTURES / "good_component.py"), _CTX, {}, component_name="GoodComponent"
        )
        self.assertEqual(result, "runner output")

    def test_b_stdout_captured(self):
        """Stray print() in render() does not appear in result."""
        runner = ComponentRunner()
        result = runner.run_jit(
            str(FIXTURES / "print_component.py"), _CTX, {}, component_name="PrintComponent"
        )
        # Result is the render() return value; "noise" must not bleed through
        self.assertNotIn("noise", result)

    def test_c_import_failure_with_fallback(self):
        """Module-level exception during import → ComponentError with fallback."""
        runner = ComponentRunner()
        with self.assertRaises(ComponentError) as cm:
            runner.run_jit(
                str(FIXTURES / "import_fail_component.py"), _CTX, {}, component_name="ImportFail"
            )
        self.assertEqual(cm.exception.render_error_fallback, "import fallback")
        self.assertIsNone(cm.exception.exit_code)  # no subprocess; exit_code is always None

    def test_d_render_exception_with_fallback(self):
        """render() raises with RENDER_ERROR_FALLBACK declared → fallback preserved."""
        runner = ComponentRunner()
        with self.assertRaises(ComponentError) as cm:
            runner.run_jit(
                str(FIXTURES / "render_exception_component.py"), _CTX, {}, component_name="RenderEx"
            )
        self.assertEqual(cm.exception.render_error_fallback, "render exception fallback")

    def test_e_docstring_trap_fallback_none(self):
        """RENDER_ERROR_FALLBACK only in docstring → tokenize-strip → fallback is None."""
        runner = ComponentRunner()
        with self.assertRaises(ComponentError) as cm:
            runner.run_jit(
                str(FIXTURES / "docstring_trap_component.py"), _CTX, {}, component_name="DocTrap"
            )
        self.assertIsNone(cm.exception.render_error_fallback)

    def test_f_ctx_attributes_accessible(self):
        """ctx.skill_id and ctx.render_mode are accessible inside render()."""
        runner = ComponentRunner()
        result = runner.run_jit(
            str(FIXTURES / "ctx_access_component.py"), _CTX, {}, component_name="CtxAccess"
        )
        self.assertIn("test/skill", result)
        self.assertIn("compile", result)

    def test_g_emit_fn_called_on_failure(self):
        """emit_fn receives component_error event on failure; exit_code is None."""
        events = []
        runner = ComponentRunner(emit_fn=events.append)
        with self.assertRaises(ComponentError):
            runner.run_jit(
                str(FIXTURES / "render_exception_component.py"),
                _CTX, {}, component_name="EmitTest",
            )
        self.assertEqual(len(events), 1)
        evt = events[0]
        self.assertEqual(evt["kind"], "component_error")
        self.assertIsNone(evt["exit_code"])  # no subprocess
        for key in ("kind", "component", "mode", "props", "exit_code", "stderr", "phase"):
            self.assertIn(key, evt)

    def test_h_timeout_param_accepted(self):
        """timeout_seconds accepted without error (not enforced in v1)."""
        runner = ComponentRunner()
        result = runner.run_jit(
            str(FIXTURES / "good_component.py"), _CTX, {}, timeout_seconds=0.001,
            component_name="TimeoutTest",
        )
        self.assertEqual(result, "runner output")

    def test_i_non_string_return_coerced(self):
        """render() returning non-str → str() coercion; no ComponentError raised."""
        runner = ComponentRunner()
        # bad_return_component.py returns 42 (int)
        result = runner.run_jit(
            str(FIXTURES / "bad_return_component.py"), _CTX, {}, component_name="BadReturn"
        )
        self.assertEqual(result, "42")

    def test_j_jit_mode_component_renders(self):
        """JIT-mode component (RENDER_MODE = 'jit') renders normally in-process."""
        runner = ComponentRunner()
        result = runner.run_jit(
            str(FIXTURES / "jit_component.py"), _CTX, {}, component_name="JitComponent"
        )
        self.assertEqual(result, "jit ok")

    def test_k_props_passed_to_render(self):
        """Props dict is passed to render() as keyword arguments."""
        runner = ComponentRunner()
        result = runner.run_jit(
            str(FIXTURES / "props_component.py"), _CTX, {"greeting": "hi"},
            component_name="PropsComponent",
        )
        self.assertIn("hi", result)


class TestInProcessBatch(unittest.TestCase):

    def test_l_batch_single_success(self):
        """Single-component compile batch returns {token_index: output}."""
        runner = ComponentRunner()
        inv = _TestInv(0, str(FIXTURES / "good_component.py"), "GoodComponent")
        result = runner.run_compile_batch([inv], _CTX)
        self.assertEqual(result, {0: "runner output"})

    def test_m_batch_failure_exit_code_none(self):
        """Failed component in batch → ComponentBatchError; exit_code is None."""
        runner = ComponentRunner()
        inv = _TestInv(0, str(FIXTURES / "render_exception_component.py"), "FailComp")
        with self.assertRaises(ComponentBatchError) as cm:
            runner.run_compile_batch([inv], _CTX)
        self.assertEqual(len(cm.exception.errors), 1)
        self.assertIsNone(cm.exception.errors[0].exit_code)

    def test_n_empty_batch_returns_immediately(self):
        """Empty invocations list returns {} without any file I/O."""
        runner = ComponentRunner()
        result = runner.run_compile_batch([], _CTX)
        self.assertEqual(result, {})


class TestWrapperGone(unittest.TestCase):

    def test_o_wrapper_file_deleted(self):
        """component_wrapper.py no longer exists at former path."""
        former_path = BMAD_ROOT / "src" / "scripts" / "bmad_compile" / "component_wrapper.py"
        self.assertFalse(
            former_path.exists(),
            f"component_wrapper.py still exists at {former_path}",
        )

    def test_p_spawn_one_not_in_runner(self):
        """_spawn_one is not present in the rewritten component_runner module."""
        self.assertFalse(
            hasattr(_runner_mod, "_spawn_one"),
            "_spawn_one should be removed from component_runner",
        )


if __name__ == "__main__":
    unittest.main()
