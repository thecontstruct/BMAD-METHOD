"""Story 10.52 — ComponentCache and ComponentRunner cache integration tests."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

BMAD_ROOT = Path(__file__).resolve().parent.parent.parent
FIXTURES = Path(__file__).parent / "fixtures" / "component_runner"

_SCRIPTS = str(BMAD_ROOT / "src" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from bmad_compile.cache import CACHE_VERSION, ComponentCache
from bmad_compile.component_runner import ComponentRunner, _read_component_source

_GOOD = str(FIXTURES / "good_component.py")
_PROPS = str(FIXTURES / "props_component.py")
_CTX = {
    "config": {"theme": "default"},
    "skill_id": "test/skill",
    "skill_source_root": str(FIXTURES),
    "render_mode": "compile",
}

# Minimal invocation stub mirroring _TestInv from test_epic8_story84.py


class _Tok:
    def __init__(self, name: str, props: tuple):
        self.name = name
        self.props = props


class _Inv:
    def __init__(self, token_index: int, path: str, name: str = "C", props: tuple = ()):
        self.token_index = token_index
        self.component_abs_path = path
        self.render_mode = "compile"
        self.original = _Tok(name, props)


# ---------------------------------------------------------------------------
# ComponentCache unit tests
# ---------------------------------------------------------------------------


class TestComponentCacheKey(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.cache = ComponentCache(Path(self._td.name))

    def tearDown(self):
        self._td.cleanup()

    def test_same_inputs_produce_same_key(self):
        src = "def render(ctx): return 'x'"
        props = {"a": 1}
        k1 = self.cache._make_key(src, props, _CTX)
        k2 = self.cache._make_key(src, props, _CTX)
        self.assertEqual(k1, k2)

    def test_source_change_produces_different_key(self):
        props = {}
        k1 = self.cache._make_key("def render(ctx): return 'a'", props, _CTX)
        k2 = self.cache._make_key("def render(ctx): return 'b'", props, _CTX)
        self.assertNotEqual(k1, k2)

    def test_props_change_produces_different_key(self):
        src = "def render(ctx): return 'x'"
        k1 = self.cache._make_key(src, {"greeting": "hello"}, _CTX)
        k2 = self.cache._make_key(src, {"greeting": "goodbye"}, _CTX)
        self.assertNotEqual(k1, k2)

    def test_ctx_config_change_produces_different_key(self):
        src = "def render(ctx): return 'x'"
        ctx_a = dict(_CTX, config={"theme": "light"})
        ctx_b = dict(_CTX, config={"theme": "dark"})
        k1 = self.cache._make_key(src, {}, ctx_a)
        k2 = self.cache._make_key(src, {}, ctx_b)
        self.assertNotEqual(k1, k2)

    def test_render_mode_excluded_from_key(self):
        src = "def render(ctx): return 'x'"
        ctx_compile = dict(_CTX, render_mode="compile")
        ctx_jit = dict(_CTX, render_mode="jit")
        k1 = self.cache._make_key(src, {}, ctx_compile)
        k2 = self.cache._make_key(src, {}, ctx_jit)
        # render_mode is excluded → keys must match
        self.assertEqual(k1, k2)

    def test_cache_version_in_key(self):
        import bmad_compile.cache as cache_mod
        original = cache_mod.CACHE_VERSION
        src = "def render(ctx): return 'x'"
        k1 = self.cache._make_key(src, {}, _CTX)
        cache_mod.CACHE_VERSION = "99"
        try:
            k2 = self.cache._make_key(src, {}, _CTX)
        finally:
            cache_mod.CACHE_VERSION = original
        self.assertNotEqual(k1, k2)


class TestComponentCacheGetPut(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.cache = ComponentCache(Path(self._td.name))

    def tearDown(self):
        self._td.cleanup()

    def test_miss_returns_none(self):
        result = self.cache.get("src", {}, _CTX)
        self.assertIsNone(result)

    def test_put_then_get_returns_value(self):
        self.cache.put("src", {}, _CTX, "hello output")
        result = self.cache.get("src", {}, _CTX)
        self.assertEqual(result, "hello output")

    def test_cache_file_created(self):
        self.cache.put("src", {}, _CTX, "value")
        files = list(Path(self._td.name).glob("*.txt"))
        self.assertEqual(len(files), 1)

    def test_get_corrupt_file_returns_none(self):
        self.cache.put("src", {}, _CTX, "good value")
        cache_files = list(Path(self._td.name).glob("*.txt"))
        cache_files[0].write_bytes(b"\xff\xfe BAD BYTES")
        result = self.cache.get("src", {}, _CTX)
        self.assertIsNone(result)

    def test_put_write_failure_logs_warning(self):
        cache = ComponentCache(Path(self._td.name))
        import io as _io
        buf = _io.StringIO()
        # Force a write failure by making io.write_text raise
        with patch("bmad_compile.io.write_text", side_effect=OSError("disk full")):
            with patch("sys.stderr", buf):
                cache.put("src", {}, _CTX, "output")
        warning = buf.getvalue()
        self.assertIn("cache", warning.lower())

    def test_put_creates_cache_dir(self):
        subdir = Path(self._td.name) / "nested" / "dir"
        cache = ComponentCache(subdir)
        self.assertFalse(subdir.exists())
        cache.put("src", {}, _CTX, "output")
        self.assertTrue(subdir.exists())


# ---------------------------------------------------------------------------
# ComponentRunner cache integration tests
# ---------------------------------------------------------------------------


class TestComponentRunnerCache(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._td = tempfile.TemporaryDirectory()
        self.cache_root = Path(self._td.name)
        self.cache = ComponentCache(self.cache_root)

    def tearDown(self):
        self._td.cleanup()

    def _make_runner(self):
        return ComponentRunner(cache=self.cache)

    def test_no_cache_no_caching(self):
        runner = ComponentRunner(cache=None)
        inv = _Inv(0, _GOOD)
        result = runner.run_compile_batch([inv], _CTX)
        self.assertEqual(result[0], "runner output")
        # Cache dir should not be created
        self.assertEqual(list(self.cache_root.glob("*.txt")), [])

    def test_cache_miss_runs_and_writes(self):
        runner = self._make_runner()
        inv = _Inv(0, _GOOD)
        result = runner.run_compile_batch([inv], _CTX)
        self.assertEqual(result[0], "runner output")
        # Cache file should now exist
        files = list(self.cache_root.glob("*.txt"))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_text(encoding="utf-8"), "runner output")

    def test_cache_hit_skips_execution(self):
        runner = self._make_runner()
        inv = _Inv(0, _GOOD)
        # First call populates cache
        runner.run_compile_batch([inv], _CTX)

        # Second call: spy on _run_inprocess to confirm it is NOT called
        call_count = [0]
        import bmad_compile.component_runner as cr_mod
        original_run = cr_mod._run_inprocess

        def spy(*args, **kwargs):
            call_count[0] += 1
            return original_run(*args, **kwargs)

        with patch.object(cr_mod, "_run_inprocess", side_effect=spy):
            result = runner.run_compile_batch([inv], _CTX)

        self.assertEqual(result[0], "runner output")
        self.assertEqual(call_count[0], 0, "cache hit must not call _run_inprocess")

    def test_source_change_busts_cache(self):
        runner = self._make_runner()
        inv = _Inv(0, _GOOD)
        runner.run_compile_batch([inv], _CTX)

        # Write a modified source to a different temp file
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False,
                                         encoding="utf-8") as f:
            f.write("def render(ctx, **props):\n    return 'modified output'\n")
            modified_path = f.name
        try:
            inv2 = _Inv(0, modified_path)
            call_count = [0]
            import bmad_compile.component_runner as cr_mod
            original_run = cr_mod._run_inprocess

            def spy(*args, **kwargs):
                call_count[0] += 1
                return original_run(*args, **kwargs)

            with patch.object(cr_mod, "_run_inprocess", side_effect=spy):
                result = runner.run_compile_batch([inv2], _CTX)

            self.assertEqual(call_count[0], 1, "source change must cause cache miss")
            self.assertEqual(result[0], "modified output")
        finally:
            os.unlink(modified_path)

    def test_props_change_busts_cache(self):
        runner = self._make_runner()
        inv1 = _Inv(0, _PROPS, props=(("greeting", "hello"),))
        runner.run_compile_batch([inv1], _CTX)

        inv2 = _Inv(0, _PROPS, props=(("greeting", "goodbye"),))
        call_count = [0]
        import bmad_compile.component_runner as cr_mod
        original_run = cr_mod._run_inprocess

        def spy(*args, **kwargs):
            call_count[0] += 1
            return original_run(*args, **kwargs)

        with patch.object(cr_mod, "_run_inprocess", side_effect=spy):
            result = runner.run_compile_batch([inv2], _CTX)

        self.assertEqual(call_count[0], 1, "props change must cause cache miss")
        self.assertIn("goodbye", result[0])

    def test_ctx_config_change_busts_cache(self):
        runner = self._make_runner()
        inv = _Inv(0, _GOOD)
        runner.run_compile_batch([inv], _CTX)

        ctx_changed = dict(_CTX, config={"theme": "new-theme"})
        call_count = [0]
        import bmad_compile.component_runner as cr_mod
        original_run = cr_mod._run_inprocess

        def spy(*args, **kwargs):
            call_count[0] += 1
            return original_run(*args, **kwargs)

        with patch.object(cr_mod, "_run_inprocess", side_effect=spy):
            runner.run_compile_batch([inv], ctx_changed)

        self.assertEqual(call_count[0], 1, "ctx config change must cause cache miss")

    def test_cache_storage_location(self):
        runner = self._make_runner()
        inv = _Inv(0, _GOOD)
        runner.run_compile_batch([inv], _CTX)
        files = list(self.cache_root.glob("*.txt"))
        self.assertEqual(len(files), 1)
        self.assertTrue(files[0].name.endswith(".txt"))
        # key is a sha256 hex string (64 chars) + .txt
        self.assertEqual(len(files[0].stem), 64)

    def test_cache_read_failure_falls_back(self):
        runner = self._make_runner()
        inv = _Inv(0, _GOOD)
        runner.run_compile_batch([inv], _CTX)
        # Corrupt the cache file
        for f in self.cache_root.glob("*.txt"):
            f.write_bytes(b"\xff\xfe")
        # Should fall back to execution without raising
        result = runner.run_compile_batch([inv], _CTX)
        self.assertEqual(result[0], "runner output")


class TestReadComponentSource(unittest.TestCase):
    def test_reads_source_text(self):
        text = _read_component_source(_GOOD)
        self.assertIn("runner output", text)


if __name__ == "__main__":
    unittest.main()
