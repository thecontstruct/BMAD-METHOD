"""Story 8.6 unit tests: JIT-time sentinel resolution."""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

BMAD_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS = str(BMAD_ROOT / "src" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from bmad_compile.component_runner import (
    MockComponentRunner,
    _JIT_SENTINEL_RE,
    _resolve_jit_sentinels,
)
from bmad_compile.errors import ComponentError

# ── constants ─────────────────────────────────────────────────────────────────

_MODULE = "test-module"
_SKILL = "test-skill"
_HASH_A = "aaaa1111bbbb2222"
_HASH_B = "cccc3333dddd4444"
_SENTINEL_A = f"<!-- BMAD-JIT:BannerA:{_HASH_A} -->"
_SENTINEL_B = f"<!-- BMAD-JIT:BannerB:{_HASH_B} -->"


# ── fixture helpers ───────────────────────────────────────────────────────────

def _make_root(
    tmp: Path,
    *,
    with_lock: bool = False,
    lock_data: dict | None = None,
) -> str:
    (tmp / "_bmad" / "_config").mkdir(parents=True)
    (tmp / "_bmad" / "config.toml").write_text("[core]\n", encoding="utf-8")
    if with_lock:
        data = lock_data if lock_data is not None else {"version": 2, "entries": []}
        (tmp / "_bmad" / "_config" / "bmad.lock").write_text(
            json.dumps(data), encoding="utf-8"
        )
    return str(tmp).replace(os.sep, "/")


def _lock_entry(
    skill: str,
    name: str,
    hash_: str,
    *,
    include_props: bool = True,
    props: dict | None = None,
    filename: str = "comp.py",
) -> dict:
    comp: dict = {
        "name": name,
        "path": f"components/{_MODULE}/{skill}/{filename}",
        "props_hash": hash_,
        "render_mode": "jit",
        "sentinel_format_version": 1,
    }
    if include_props:
        comp["props"] = props if props is not None else {}
    return {"version": 2, "entries": [{"skill": skill, "components": [comp]}]}


def _make_comp(tmp: Path, skill: str, filename: str = "comp.py") -> None:
    comp_dir = tmp / "_bmad" / "components" / _MODULE / skill
    comp_dir.mkdir(parents=True, exist_ok=True)
    (comp_dir / filename).write_text(
        "def render(ctx, **props):\n    return 'ok'\n", encoding="utf-8"
    )


def _stderr_events(buf: io.StringIO) -> list[dict]:
    return [
        json.loads(line)
        for line in buf.getvalue().splitlines()
        if line.strip().startswith("{")
    ]


# ── (a) regex ─────────────────────────────────────────────────────────────────

class TestJITSentinelRegex(unittest.TestCase):

    def test_a_matches_valid_sentinel(self):
        m = _JIT_SENTINEL_RE.fullmatch(f"<!-- BMAD-JIT:BannerX:{_HASH_A} -->")
        self.assertIsNotNone(m)
        self.assertEqual(m.group("name"), "BannerX")
        self.assertEqual(m.group("hash"), _HASH_A)

    def test_a_matches_extra_whitespace(self):
        self.assertIsNotNone(
            _JIT_SENTINEL_RE.fullmatch(f"<!--  BMAD-JIT:BannerX:{_HASH_A}  -->")
        )

    def test_a_rejects_lowercase_name(self):
        self.assertIsNone(
            _JIT_SENTINEL_RE.fullmatch(f"<!-- BMAD-JIT:bannerX:{_HASH_A} -->")
        )

    def test_a_rejects_short_hash(self):
        self.assertIsNone(
            _JIT_SENTINEL_RE.fullmatch("<!-- BMAD-JIT:BannerX:abcd1234 -->")
        )

    def test_a_rejects_long_hash(self):
        self.assertIsNone(
            _JIT_SENTINEL_RE.fullmatch("<!-- BMAD-JIT:BannerX:abcd1234ef5678901 -->")
        )

    def test_a_rejects_uppercase_hex(self):
        self.assertIsNone(
            _JIT_SENTINEL_RE.fullmatch("<!-- BMAD-JIT:BannerX:ABCD1234EF567890 -->")
        )


# ── (b) no sentinels ──────────────────────────────────────────────────────────

class TestNoSentinels(unittest.TestCase):

    def test_b_no_sentinels_returns_unchanged(self):
        content = "# Hello\nNo sentinels here.\n"
        self.assertEqual(
            _resolve_jit_sentinels(content, "/fake/root", _SKILL, _MODULE), content
        )

    def test_b_empty_string_returns_unchanged(self):
        self.assertEqual(_resolve_jit_sentinels("", "/fake/root", _SKILL, _MODULE), "")

    def test_b_whitespace_only_returns_unchanged(self):
        s = "   \n   "
        self.assertEqual(_resolve_jit_sentinels(s, "/fake/root", _SKILL, _MODULE), s)


# ── (c) python version guard ──────────────────────────────────────────────────

class TestPythonVersionTooOld(unittest.TestCase):

    def test_c_version_too_old_all_error_slots_one_event(self):
        content = f"before\n{_SENTINEL_A}\nafter\n"
        buf = io.StringIO()
        with patch.object(sys, "version_info", (3, 10, 0, "final", 0)):
            with patch("sys.stderr", buf):
                result = _resolve_jit_sentinels(content, "/fake/root", _SKILL, _MODULE)
        self.assertIn("<!-- BMAD-ERROR:BannerA -->", result)
        self.assertNotIn(_SENTINEL_A, result)
        events = _stderr_events(buf)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["reason"], "python_version_too_old")
        self.assertEqual(events[0]["component"], "<all>")


# ── (d) lockfile absent ───────────────────────────────────────────────────────

class TestLockfileAbsent(unittest.TestCase):

    def test_d_lockfile_absent_error_slot_one_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_root(Path(tmp), with_lock=False)
            buf = io.StringIO()
            with patch("sys.stderr", buf):
                result = _resolve_jit_sentinels(
                    f"x\n{_SENTINEL_A}\ny\n", root, _SKILL, _MODULE
                )
        self.assertIn("<!-- BMAD-ERROR:BannerA -->", result)
        events = _stderr_events(buf)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["reason"], "lockfile_absent")


# ── (e1/e2) lockfile entry missing ────────────────────────────────────────────

class TestLockfileEntryMissing(unittest.TestCase):

    def test_e1_no_skill_entry_all_error_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = {"version": 2, "entries": [{"skill": "other-skill", "components": []}]}
            root = _make_root(Path(tmp), with_lock=True, lock_data=lock)
            buf = io.StringIO()
            with patch("sys.stderr", buf):
                result = _resolve_jit_sentinels(
                    f"{_SENTINEL_A}\n{_SENTINEL_B}\n", root, _SKILL, _MODULE
                )
        self.assertIn("<!-- BMAD-ERROR:BannerA -->", result)
        self.assertIn("<!-- BMAD-ERROR:BannerB -->", result)
        events = _stderr_events(buf)
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e["reason"] == "lockfile_entry_missing" for e in events))

    def test_e2_component_hash_miss_others_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Only BannerA has a lockfile entry; BannerB does not
            lock = _lock_entry(_SKILL, "BannerA", _HASH_A)
            root = _make_root(Path(tmp), with_lock=True, lock_data=lock)
            _make_comp(Path(tmp), _SKILL)
            mock_runner = MockComponentRunner(jit_result="resolved_a")
            result = _resolve_jit_sentinels(
                f"{_SENTINEL_A}\n{_SENTINEL_B}\n",
                root, _SKILL, _MODULE,
                _runner=mock_runner,
            )
        self.assertIn("resolved_a", result)
        self.assertIn("<!-- BMAD-ERROR:BannerB -->", result)
        self.assertNotIn(_SENTINEL_A, result)
        self.assertNotIn(_SENTINEL_B, result)


# ── (f) props key absent ──────────────────────────────────────────────────────

class TestPropsAbsent(unittest.TestCase):

    def test_f_absent_props_calls_component_with_empty_dict(self):
        class _CaptureMock(MockComponentRunner):
            def __init__(self):
                super().__init__(jit_result="ok")
                self.captured_props = None

            def run_jit(self, component_path, ctx_dict, props, **kw):
                self.captured_props = props
                return super().run_jit(component_path, ctx_dict, props, **kw)

        with tempfile.TemporaryDirectory() as tmp:
            # no "props" key in entry
            lock = _lock_entry(_SKILL, "BannerA", _HASH_A, include_props=False)
            root = _make_root(Path(tmp), with_lock=True, lock_data=lock)
            _make_comp(Path(tmp), _SKILL)
            cap = _CaptureMock()
            result = _resolve_jit_sentinels(
                f"{_SENTINEL_A}\n", root, _SKILL, _MODULE, _runner=cap
            )
        self.assertEqual(cap.captured_props, {})
        self.assertNotIn("BMAD-ERROR", result)


# ── (g) component file missing ────────────────────────────────────────────────

class TestComponentFileMissing(unittest.TestCase):

    def test_g_file_missing_error_slot_one_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = _lock_entry(_SKILL, "BannerA", _HASH_A)
            root = _make_root(Path(tmp), with_lock=True, lock_data=lock)
            # component file NOT created
            buf = io.StringIO()
            with patch("sys.stderr", buf):
                result = _resolve_jit_sentinels(
                    f"{_SENTINEL_A}\n", root, _SKILL, _MODULE
                )
        self.assertIn("<!-- BMAD-ERROR:BannerA -->", result)
        events = _stderr_events(buf)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["reason"], "component_file_missing")


# ── (h) successful JIT ────────────────────────────────────────────────────────

class TestSuccessfulJIT(unittest.TestCase):

    def test_h_sentinel_replaced_with_runner_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = _lock_entry(_SKILL, "BannerA", _HASH_A)
            root = _make_root(Path(tmp), with_lock=True, lock_data=lock)
            _make_comp(Path(tmp), _SKILL)
            result = _resolve_jit_sentinels(
                f"before\n{_SENTINEL_A}\nafter\n",
                root, _SKILL, _MODULE,
                _runner=MockComponentRunner(jit_result="## Banner Output"),
            )
        self.assertEqual(result, "before\n## Banner Output\nafter\n")


# ── (i/j) ComponentError fallback ─────────────────────────────────────────────

class TestComponentErrorFallback(unittest.TestCase):

    def test_i_fallback_string_used(self):
        class _FallbackMock(MockComponentRunner):
            def run_jit(self, *args, **kw):
                raise ComponentError("fail", render_error_fallback="fallback text")

        with tempfile.TemporaryDirectory() as tmp:
            lock = _lock_entry(_SKILL, "BannerA", _HASH_A)
            root = _make_root(Path(tmp), with_lock=True, lock_data=lock)
            _make_comp(Path(tmp), _SKILL)
            result = _resolve_jit_sentinels(
                f"{_SENTINEL_A}\n", root, _SKILL, _MODULE,
                _runner=_FallbackMock(jit_result="ok"),
            )
        self.assertEqual(result, "fallback text\n")

    def test_j_fallback_none_uses_error_slot(self):
        class _NullFallbackMock(MockComponentRunner):
            def run_jit(self, *args, **kw):
                raise ComponentError("fail", render_error_fallback=None)

        with tempfile.TemporaryDirectory() as tmp:
            lock = _lock_entry(_SKILL, "BannerA", _HASH_A)
            root = _make_root(Path(tmp), with_lock=True, lock_data=lock)
            _make_comp(Path(tmp), _SKILL)
            result = _resolve_jit_sentinels(
                f"{_SENTINEL_A}\n", root, _SKILL, _MODULE,
                _runner=_NullFallbackMock(jit_result="ok"),
            )
        self.assertIn("<!-- BMAD-ERROR:BannerA -->", result)


# ── (k) duplicate sentinel ────────────────────────────────────────────────────

class TestDuplicateSentinel(unittest.TestCase):

    def test_k_run_jit_once_all_occurrences_replaced(self):
        call_count = []

        class _CountMock(MockComponentRunner):
            def run_jit(self, *args, **kw):
                call_count.append(1)
                return "banner"

        with tempfile.TemporaryDirectory() as tmp:
            lock = _lock_entry(_SKILL, "BannerA", _HASH_A)
            root = _make_root(Path(tmp), with_lock=True, lock_data=lock)
            _make_comp(Path(tmp), _SKILL)
            content = f"{_SENTINEL_A}\nmiddle\n{_SENTINEL_A}\nend\n{_SENTINEL_A}\n"
            result = _resolve_jit_sentinels(
                content, root, _SKILL, _MODULE,
                _runner=_CountMock(jit_result="banner"),
            )
        self.assertEqual(len(call_count), 1)
        self.assertEqual(result.count("banner"), 3)
        self.assertNotIn(_SENTINEL_A, result)


# ── (l) two distinct sentinels ────────────────────────────────────────────────

class TestTwoDistinctSentinels(unittest.TestCase):

    def test_l_two_sentinels_both_resolved_independently(self):
        calls: list[str] = []

        class _TrackMock(MockComponentRunner):
            def run_jit(self, path, ctx, props, component_name="", **kw):
                calls.append(component_name)
                return f"result_{component_name}"

        with tempfile.TemporaryDirectory() as tmp:
            lock_data = {
                "version": 2,
                "entries": [{
                    "skill": _SKILL,
                    "components": [
                        {"name": "BannerA", "path": f"components/{_MODULE}/{_SKILL}/comp_a.py",
                         "props_hash": _HASH_A, "props": {}, "render_mode": "jit",
                         "sentinel_format_version": 1},
                        {"name": "BannerB", "path": f"components/{_MODULE}/{_SKILL}/comp_b.py",
                         "props_hash": _HASH_B, "props": {}, "render_mode": "jit",
                         "sentinel_format_version": 1},
                    ],
                }],
            }
            root = _make_root(Path(tmp), with_lock=True, lock_data=lock_data)
            comp_dir = Path(tmp) / "_bmad" / "components" / _MODULE / _SKILL
            comp_dir.mkdir(parents=True)
            (comp_dir / "comp_a.py").write_text(
                "def render(ctx, **props): return 'a'\n", encoding="utf-8"
            )
            (comp_dir / "comp_b.py").write_text(
                "def render(ctx, **props): return 'b'\n", encoding="utf-8"
            )
            result = _resolve_jit_sentinels(
                f"{_SENTINEL_A}\n{_SENTINEL_B}\n",
                root, _SKILL, _MODULE,
                _runner=_TrackMock(jit_result="x"),
            )
        self.assertEqual(sorted(calls), ["BannerA", "BannerB"])
        self.assertIn("result_BannerA", result)
        self.assertIn("result_BannerB", result)


# ── (m) non-ComponentError exception ─────────────────────────────────────────

class TestRunnerUnexpectedError(unittest.TestCase):

    def test_m_oserror_produces_error_slot_and_event(self):
        class _OSErrorMock(MockComponentRunner):
            def run_jit(self, *args, **kw):
                raise OSError("disk error")

        with tempfile.TemporaryDirectory() as tmp:
            lock = _lock_entry(_SKILL, "BannerA", _HASH_A)
            root = _make_root(Path(tmp), with_lock=True, lock_data=lock)
            _make_comp(Path(tmp), _SKILL)
            buf = io.StringIO()
            with patch("sys.stderr", buf):
                result = _resolve_jit_sentinels(
                    f"{_SENTINEL_A}\n", root, _SKILL, _MODULE,
                    _runner=_OSErrorMock(jit_result="ok"),
                )
        self.assertIn("<!-- BMAD-ERROR:BannerA -->", result)
        events = _stderr_events(buf)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["reason"], "runner_unexpected_error")
        self.assertIn("disk error", events[0]["stderr"])


if __name__ == "__main__":
    unittest.main()
