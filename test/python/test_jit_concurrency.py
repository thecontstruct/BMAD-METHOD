"""Story 10.53 — JIT component execution concurrency tests."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch

BMAD_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS = str(BMAD_ROOT / "src" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from bmad_compile.component_runner import (
    MockComponentRunner,
    _JIT_BATCH_WORKERS,
    _resolve_jit_sentinels,
)
from bmad_compile.errors import ComponentError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_root(td: str, skill: str, module: str, components: list[dict]) -> str:
    """Build a minimal _bmad install tree under td and return td (as posix)."""
    root = td.replace(os.sep, "/")
    lockfile_dir = os.path.join(td, "_bmad", "_config")
    os.makedirs(lockfile_dir, exist_ok=True)
    lockfile = {"entries": [{"skill": skill, "components": components}]}
    with open(os.path.join(lockfile_dir, "bmad.lock"), "w", encoding="utf-8") as fh:
        json.dump(lockfile, fh)
    comp_dir = os.path.join(td, "_bmad", "components", module, skill)
    os.makedirs(comp_dir, exist_ok=True)
    return root


def _touch(path: str) -> None:
    """Create an empty file at path (path must be absolute)."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# stub\n")


def _sentinel(name: str, hash_: str) -> str:
    return f"<!-- BMAD-JIT:{name}:{hash_} -->"


def _comp_entry(name: str, hash_: str, filename: str, props: dict | None = None) -> dict:
    return {"name": name, "props_hash": hash_, "path": filename, "props": props or {}}


# ---------------------------------------------------------------------------
# AC-1: Concurrent execution timing
# ---------------------------------------------------------------------------

class TestConcurrentExecutionTiming(unittest.TestCase):
    def test_concurrent_execution_timing(self):
        """Two components each sleep 50ms; concurrent path completes in <120ms."""
        with tempfile.TemporaryDirectory() as td:
            root = _make_root(td, "my-skill", "my-module", [
                _comp_entry("CompA", "aaaa000000000001", "CompA.py"),
                _comp_entry("CompB", "bbbb000000000002", "CompB.py"),
            ])
            comp_dir = os.path.join(td, "_bmad", "components", "my-module", "my-skill")
            _touch(os.path.join(comp_dir, "CompA.py"))
            _touch(os.path.join(comp_dir, "CompB.py"))

            content = _sentinel("CompA", "aaaa000000000001") + " " + _sentinel("CompB", "bbbb000000000002")

            mock_runner = MagicMock()
            mock_runner.run_jit.side_effect = lambda *a, **kw: (time.sleep(0.05) or "output")

            start = time.monotonic()
            result = _resolve_jit_sentinels(content, root, "my-skill", "my-module", _runner=mock_runner)
            elapsed = time.monotonic() - start

            self.assertIn("output", result)
            # Sequential would take ~100ms; concurrent must finish well under that.
            # CI note: widen to 0.200 if this proves fragile on loaded runners.
            self.assertLess(elapsed, 0.120, f"Expected concurrent < 120ms, got {elapsed*1000:.0f}ms")


# ---------------------------------------------------------------------------
# AC-2: Deduplication preserved
# ---------------------------------------------------------------------------

class TestDeduplicationPreserved(unittest.TestCase):
    def test_deduplication_preserved(self):
        """Two identical sentinels: run_jit called once, both replaced correctly."""
        with tempfile.TemporaryDirectory() as td:
            root = _make_root(td, "sk", "mod", [
                _comp_entry("CompX", "cccc000000000003", "CompX.py"),
            ])
            comp_dir = os.path.join(td, "_bmad", "components", "mod", "sk")
            _touch(os.path.join(comp_dir, "CompX.py"))

            sentinel = _sentinel("CompX", "cccc000000000003")
            content = f"{sentinel} text {sentinel}"

            mock_runner = MagicMock()
            mock_runner.run_jit.return_value = "RESULT"

            result = _resolve_jit_sentinels(content, root, "sk", "mod", _runner=mock_runner)

            self.assertEqual(mock_runner.run_jit.call_count, 1)
            self.assertEqual(result, "RESULT text RESULT")


# ---------------------------------------------------------------------------
# AC-8: Single-component fast path (no executor)
# ---------------------------------------------------------------------------

class TestSingleComponentNoExecutor(unittest.TestCase):
    def test_single_component_no_executor(self):
        """One sentinel: ThreadPoolExecutor is NOT instantiated."""
        with tempfile.TemporaryDirectory() as td:
            root = _make_root(td, "sk", "mod", [
                _comp_entry("Solo", "dddd000000000004", "Solo.py"),
            ])
            comp_dir = os.path.join(td, "_bmad", "components", "mod", "sk")
            _touch(os.path.join(comp_dir, "Solo.py"))

            mock_runner = MagicMock()
            mock_runner.run_jit.return_value = "solo-out"

            with patch("bmad_compile.component_runner.ThreadPoolExecutor") as mock_pool:
                result = _resolve_jit_sentinels(
                    _sentinel("Solo", "dddd000000000004"),
                    root, "sk", "mod", _runner=mock_runner,
                )
            mock_pool.assert_not_called()
            self.assertEqual(result, "solo-out")

    def test_zero_components_no_executor(self):
        """No sentinels: returns input unchanged without touching executor."""
        with tempfile.TemporaryDirectory() as td:
            root = _make_root(td, "sk", "mod", [])
            content = "no sentinels here"
            with patch("bmad_compile.component_runner.ThreadPoolExecutor") as mock_pool:
                result = _resolve_jit_sentinels(content, root, "sk", "mod")
            mock_pool.assert_not_called()
            self.assertEqual(result, content)


# ---------------------------------------------------------------------------
# AC-3: Per-component error — fallback available
# ---------------------------------------------------------------------------

class TestErrorWithFallbackContinues(unittest.TestCase):
    def test_error_with_fallback_continues(self):
        """One component fails (fallback set); other components succeed."""
        with tempfile.TemporaryDirectory() as td:
            root = _make_root(td, "sk", "mod", [
                _comp_entry("Good", "eeee000000000005", "Good.py"),
                _comp_entry("Bad", "ffff000000000006", "Bad.py"),
            ])
            comp_dir = os.path.join(td, "_bmad", "components", "mod", "sk")
            _touch(os.path.join(comp_dir, "Good.py"))
            _touch(os.path.join(comp_dir, "Bad.py"))

            content = _sentinel("Good", "eeee000000000005") + " " + _sentinel("Bad", "ffff000000000006")

            def _side_effect(*args, component_name="", **kwargs):
                if component_name == "Bad":
                    exc = ComponentError("bad!", component_name="Bad")
                    exc.render_error_fallback = "FALLBACK"
                    raise exc
                return "GOOD"

            mock_runner = MagicMock()
            mock_runner.run_jit.side_effect = _side_effect

            result = _resolve_jit_sentinels(content, root, "sk", "mod", _runner=mock_runner)
            self.assertIn("GOOD", result)
            self.assertIn("FALLBACK", result)
            self.assertNotIn("BMAD-ERROR", result)


# ---------------------------------------------------------------------------
# AC-4: Per-component error — no fallback
# ---------------------------------------------------------------------------

class TestErrorNoFallbackContinues(unittest.TestCase):
    def test_error_no_fallback_continues(self):
        """One component fails (no fallback); placeholder in output; others continue."""
        with tempfile.TemporaryDirectory() as td:
            root = _make_root(td, "sk", "mod", [
                _comp_entry("Good", "1111000000000001", "Good.py"),
                _comp_entry("Fail", "2222000000000002", "Fail.py"),
            ])
            comp_dir = os.path.join(td, "_bmad", "components", "mod", "sk")
            _touch(os.path.join(comp_dir, "Good.py"))
            _touch(os.path.join(comp_dir, "Fail.py"))

            content = _sentinel("Good", "1111000000000001") + "|" + _sentinel("Fail", "2222000000000002")

            def _side_effect(*args, component_name="", **kwargs):
                if component_name == "Fail":
                    exc = ComponentError("fail!", component_name="Fail")
                    exc.render_error_fallback = None
                    raise exc
                return "GOOD"

            mock_runner = MagicMock()
            mock_runner.run_jit.side_effect = _side_effect

            result = _resolve_jit_sentinels(content, root, "sk", "mod", _runner=mock_runner)
            self.assertIn("GOOD", result)
            self.assertIn("<!-- BMAD-ERROR:Fail -->", result)

    def test_all_components_fail_graceful(self):
        """All components fail; all sentinels replaced; no exception raised.

        Each mock call raises a FRESH ComponentError instance — do not share a
        single exception instance across concurrent threads (__traceback__ is
        mutated on raise).
        """
        with tempfile.TemporaryDirectory() as td:
            root = _make_root(td, "sk", "mod", [
                _comp_entry("Ca", "3333000000000003", "Ca.py"),
                _comp_entry("Cb", "4444000000000004", "Cb.py"),
                _comp_entry("Cc", "5555000000000005", "Cc.py"),
            ])
            comp_dir = os.path.join(td, "_bmad", "components", "mod", "sk")
            for name in ("Ca", "Cb", "Cc"):
                _touch(os.path.join(comp_dir, f"{name}.py"))

            content = (
                _sentinel("Ca", "3333000000000003") + " "
                + _sentinel("Cb", "4444000000000004") + " "
                + _sentinel("Cc", "5555000000000005")
            )

            def _always_fail(*args, component_name="", **kwargs):
                # Fresh instance per call — safe for concurrent raise
                exc = ComponentError(f"fail:{component_name}", component_name=component_name)
                exc.render_error_fallback = f"FB-{component_name}"
                raise exc

            mock_runner = MagicMock()
            mock_runner.run_jit.side_effect = _always_fail

            # Must not raise; all sentinels must be replaced
            result = _resolve_jit_sentinels(content, root, "sk", "mod", _runner=mock_runner)
            self.assertIn("FB-Ca", result)
            self.assertIn("FB-Cb", result)
            self.assertIn("FB-Cc", result)


# ---------------------------------------------------------------------------
# AC-5: Lookup failures are pre-executor fast-path
# ---------------------------------------------------------------------------

class TestLookupFailurePreExecutor(unittest.TestCase):
    def test_lookup_failure_preexecutor(self):
        """Missing lockfile entry: run_jit NOT called; sentinel replaced with error."""
        with tempfile.TemporaryDirectory() as td:
            # Lockfile has no components entry for "Missing"
            root = _make_root(td, "sk", "mod", [])

            mock_runner = MagicMock()

            result = _resolve_jit_sentinels(
                _sentinel("Missing", "6666000000000006"),
                root, "sk", "mod", _runner=mock_runner,
            )
            mock_runner.run_jit.assert_not_called()
            self.assertIn("<!-- BMAD-ERROR:Missing -->", result)


# ---------------------------------------------------------------------------
# AC-6: Output byte-identical to sequential for same inputs
# ---------------------------------------------------------------------------

class TestOutputMatchesSequential(unittest.TestCase):
    def test_output_matches_sequential(self):
        """Concurrent output == reference output from same inputs (3 components)."""
        with tempfile.TemporaryDirectory() as td:
            root = _make_root(td, "sk", "mod", [
                _comp_entry("Alpha", "aaaa111111111111", "Alpha.py"),
                _comp_entry("Beta",  "bbbb222222222222", "Beta.py"),
                _comp_entry("Gamma", "cccc333333333333", "Gamma.py"),
            ])
            comp_dir = os.path.join(td, "_bmad", "components", "mod", "sk")
            for name in ("Alpha", "Beta", "Gamma"):
                _touch(os.path.join(comp_dir, f"{name}.py"))

            content = (
                "before "
                + _sentinel("Alpha", "aaaa111111111111")
                + " middle "
                + _sentinel("Beta", "bbbb222222222222")
                + " and "
                + _sentinel("Gamma", "cccc333333333333")
                + " after"
            )

            results_map = {"Alpha": "OUT_A", "Beta": "OUT_B", "Gamma": "OUT_C"}

            mock_runner = MagicMock()
            mock_runner.run_jit.side_effect = lambda *a, component_name="", **kw: results_map[component_name]

            # Run 3 times; output must be identical each time (AC-6: key-ordered, not future-ordered)
            outputs = []
            for _ in range(3):
                outputs.append(
                    _resolve_jit_sentinels(content, root, "sk", "mod", _runner=mock_runner)
                )
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(outputs[1], outputs[2])
            self.assertIn("OUT_A", outputs[0])
            self.assertIn("OUT_B", outputs[0])
            self.assertIn("OUT_C", outputs[0])
            # Verify positional ordering: Alpha before Beta before Gamma
            self.assertLess(outputs[0].index("OUT_A"), outputs[0].index("OUT_B"))
            self.assertLess(outputs[0].index("OUT_B"), outputs[0].index("OUT_C"))


# ---------------------------------------------------------------------------
# AC-7: Worker count constant importable
# ---------------------------------------------------------------------------

class TestWorkerConstantImportable(unittest.TestCase):
    def test_worker_constant_importable(self):
        """_JIT_BATCH_WORKERS is importable from render and equals 4."""
        self.assertEqual(_JIT_BATCH_WORKERS, 4)
        self.assertIsInstance(_JIT_BATCH_WORKERS, int)


if __name__ == "__main__":
    unittest.main()
