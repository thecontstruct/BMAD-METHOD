"""Story 8.4 unit tests: ComponentRunner, MockComponentRunner, errors.py DN-2 lift."""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BMAD_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "component_runner"

_SCRIPTS = str(BMAD_ROOT / "src" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from bmad_compile.component_runner import (
    ComponentRunner,
    MockComponentRunner,
    _COMPILE_BATCH_WORKERS,
)
from bmad_compile.errors import (
    ComponentBatchError,
    ComponentError,
    ComponentPropError,
    ComponentTimeoutError,
)

_CTX = {
    "config": {},
    "skill_id": "test/skill",
    "render_mode": "compile",
    "skill_source_root": str(FIXTURES),
}

_MOCK_CTX = {
    "skill_id": "x",
    "render_mode": "jit",
    "config": {},
    "skill_source_root": "/",
}


class _OriginalToken:
    def __init__(self, name: str, props: tuple):
        self.name = name
        self.props = props


class _TestInv:
    def __init__(self, token_index: int, component_path: str, name: str = "TestComp", props: tuple = ()):
        self.token_index = token_index
        self.component_abs_path = component_path
        self.render_mode = "compile"
        self.original = _OriginalToken(name, props)


class TestErrorsDN2Lift(unittest.TestCase):
    def test_k_mode_and_props_attrs(self):
        e = ComponentError("m", mode="compile", props={"x": 1})
        self.assertEqual(e.mode, "compile")
        self.assertEqual(e.props, {"x": 1})

    def test_k_defaults_are_none(self):
        e = ComponentError("m")
        self.assertIsNone(e.mode)
        self.assertIsNone(e.props)

    def test_k_subclasses_forward_via_kwargs(self):
        e = ComponentTimeoutError("t", mode="jit", props={})
        self.assertEqual(e.mode, "jit")


class TestComponentRunnerUnit(unittest.TestCase):
    def test_a_constant_is_4(self):
        self.assertEqual(_COMPILE_BATCH_WORKERS, 4)

    def test_l_run_jit_success(self):
        runner = ComponentRunner()
        result = runner.run_jit(
            str(FIXTURES / "good_component.py"),
            _CTX,
            {},
            component_name="GoodComponent",
        )
        self.assertEqual(result, "runner output")

    def test_c_run_jit_real_fail_with_fallback(self):
        runner = ComponentRunner()
        with self.assertRaises(ComponentError) as cm:
            runner.run_jit(
                str(FIXTURES / "jit_fail_component.py"),
                _CTX,
                {},
                component_name="JitFailComponent",
            )
        self.assertEqual(cm.exception.render_error_fallback, "jit fb")

    def test_g_timeout_raises_component_timeout_error(self):
        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd=[], timeout=0.1),
            (b"", b""),
        ]
        mock_proc.pid = 99999
        with patch("subprocess.Popen", return_value=mock_proc), \
             patch("bmad_compile.component_runner._kill_process_group") as mock_kill:
            runner = ComponentRunner()
            with self.assertRaises(ComponentTimeoutError) as cm:
                runner.run_jit(
                    "/fake/path.py",
                    _MOCK_CTX,
                    {"p": 1},
                    component_name="Fake",
                )
            mock_kill.assert_called_once_with(mock_proc)
            exc = cm.exception
            self.assertEqual(exc.mode, "jit")
            self.assertEqual(exc.props, {"p": 1})

    def test_h_empty_stdout_raises_component_error(self):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"", b"stderr stuff")
        mock_proc.returncode = 1
        with patch("subprocess.Popen", return_value=mock_proc):
            runner = ComponentRunner()
            with self.assertRaises(ComponentError):
                runner.run_jit("/fake/path.py", _MOCK_CTX, {}, component_name="Fake")

    def test_i_ok_false_no_fallback(self):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            json.dumps({"ok": False, "error": "oops", "render_error_fallback": None}).encode(),
            b"",
        )
        mock_proc.returncode = 1
        with patch("subprocess.Popen", return_value=mock_proc):
            runner = ComponentRunner()
            with self.assertRaises(ComponentError) as cm:
                runner.run_jit("/fake/path.py", _MOCK_CTX, {}, component_name="Fake")
            self.assertIsNone(cm.exception.render_error_fallback)

    def test_d_ok_false_with_fallback(self):
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            json.dumps({"ok": False, "error": "oops", "render_error_fallback": "fallback"}).encode(),
            b"",
        )
        mock_proc.returncode = 1
        with patch("subprocess.Popen", return_value=mock_proc):
            runner = ComponentRunner()
            with self.assertRaises(ComponentError) as cm:
                runner.run_jit("/fake/path.py", _MOCK_CTX, {}, component_name="Fake")
            self.assertEqual(cm.exception.render_error_fallback, "fallback")

    def test_j_emit_fn_called_on_failure(self):
        events = []
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (
            json.dumps({"ok": False, "error": "fail"}).encode(),
            b"some stderr",
        )
        mock_proc.returncode = 1
        with patch("subprocess.Popen", return_value=mock_proc):
            runner = ComponentRunner(emit_fn=events.append)
            with self.assertRaises(ComponentError):
                runner.run_jit(
                    "/fake/path.py",
                    _MOCK_CTX,
                    {"key": "val"},
                    component_name="TestComp",
                )
        self.assertEqual(len(events), 1)
        evt = events[0]
        self.assertEqual(evt["kind"], "component_error")
        for key in ("kind", "component", "mode", "props", "exit_code", "stderr", "phase"):
            self.assertIn(key, evt)

    def test_m_prop_error_emits_component_prop_error_event(self):
        events = []
        runner = ComponentRunner(emit_fn=events.append)
        bad_props = {"x": {1, 2, 3}}
        with self.assertRaises(ComponentPropError):
            runner.run_jit(
                "/fake/path.py",
                _MOCK_CTX,
                bad_props,
                component_name="BadComp",
            )
        self.assertEqual(len(events), 1)
        evt = events[0]
        self.assertEqual(evt["kind"], "component_prop_error")
        self.assertEqual(evt["component"], "BadComp")
        self.assertEqual(evt["prop_name"], "x")
        self.assertIn("reason", evt)


class TestMockComponentRunner(unittest.TestCase):
    def test_e_batch_all_succeed(self):
        mock = MockComponentRunner(batch_results={0: "out0", 1: "out1"})
        invocations = [_TestInv(0, ""), _TestInv(1, "")]
        result = mock.run_compile_batch(invocations, {})
        self.assertEqual(result, {0: "out0", 1: "out1"})

    def test_f_batch_one_fail_raises(self):
        mock = MockComponentRunner(batch_results={0: "out0", 1: ComponentError("fail")})
        invocations = [_TestInv(0, ""), _TestInv(1, "")]
        with self.assertRaises(ComponentBatchError) as cm:
            mock.run_compile_batch(invocations, {})
        self.assertEqual(len(cm.exception.errors), 1)

    def test_l_mock_jit_success(self):
        mock = MockComponentRunner(jit_result="jit out")
        self.assertEqual(mock.run_jit("/p", {}, {}), "jit out")

    def test_l2_mock_jit_exception(self):
        mock = MockComponentRunner(jit_result=ComponentError("fail"))
        with self.assertRaises(ComponentError):
            mock.run_jit("/p", {}, {})

    def test_none_batch_results_raises(self):
        mock = MockComponentRunner(batch_results=None)
        with self.assertRaises(ComponentBatchError):
            mock.run_compile_batch([_TestInv(0, "")], {})
        result = MockComponentRunner(batch_results=None).run_compile_batch([], {})
        self.assertEqual(result, {})

    def test_n_batch_errors_sorted_by_token_index(self):
        mock = MockComponentRunner(batch_results={
            0: ComponentError("fail-0", component_name="Comp0"),
            1: "out1",
            2: ComponentError("fail-2", component_name="Comp2"),
        })
        invocations = [_TestInv(2, "", "Comp2"), _TestInv(0, "", "Comp0"), _TestInv(1, "", "Comp1")]
        with self.assertRaises(ComponentBatchError) as cm:
            mock.run_compile_batch(invocations, {})
        errors = cm.exception.errors
        self.assertEqual(len(errors), 2)
        self.assertEqual(errors[0].component_name, "Comp0")
        self.assertEqual(errors[1].component_name, "Comp2")


if __name__ == "__main__":
    unittest.main()
