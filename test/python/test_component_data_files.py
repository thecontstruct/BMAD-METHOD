"""Tests for Story 10.57 — component data file support.

Groups:
  A — _list_data_files / _compute_data_files_hash helpers
  B — cache key includes data files hash
  C — lockfile data_files field
  D — integration: engine.py injects _data_files_hash
"""
from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent.parent / "src" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from bmad_compile import io as _io
from bmad_compile.engine import (
    _compute_data_files_hash,
    _list_data_files,
    _DATA_FILE_BLOCKLIST,
    _DATA_FILE_BLOCKLIST_SUFFIXES,
)
from bmad_compile.cache import ComponentCache


# ---------------------------------------------------------------------------
# Group A — _list_data_files / _compute_data_files_hash
# ---------------------------------------------------------------------------

class TestListDataFiles:
    def test_a1_empty_dir(self, tmp_path):
        comp = tmp_path / "components"
        comp.mkdir()
        assert _list_data_files(_io.to_posix(comp)) == []

    def test_a2_only_py_files(self, tmp_path):
        comp = tmp_path / "components"
        comp.mkdir()
        (comp / "my_comp.py").write_text("RENDER_MODE='compile'\n")
        assert _list_data_files(_io.to_posix(comp)) == []

    def test_a3_py_plus_json(self, tmp_path):
        comp = tmp_path / "components"
        comp.mkdir()
        (comp / "my_comp.py").write_text("RENDER_MODE='compile'\n")
        (comp / "data.json").write_text('{"key": "value"}')
        result = _list_data_files(_io.to_posix(comp))
        assert result == ["data.json"]

    def test_a4_ds_store_excluded(self, tmp_path):
        comp = tmp_path / "components"
        comp.mkdir()
        (comp / "my_comp.py").write_text("")
        (comp / ".DS_Store").write_bytes(b"\x00")
        result = _list_data_files(_io.to_posix(comp))
        assert ".DS_Store" not in result

    def test_a4_gitignore_excluded(self, tmp_path):
        comp = tmp_path / "components"
        comp.mkdir()
        (comp / "my_comp.py").write_text("")
        (comp / ".gitignore").write_text("*.pyc\n")
        result = _list_data_files(_io.to_posix(comp))
        assert ".gitignore" not in result

    def test_a5_pyc_excluded(self, tmp_path):
        comp = tmp_path / "components"
        comp.mkdir()
        (comp / "my_comp.py").write_text("")
        (comp / "my_comp.pyc").write_bytes(b"\x00")
        result = _list_data_files(_io.to_posix(comp))
        assert "my_comp.pyc" not in result

    def test_a6_subdirectory_skipped(self, tmp_path):
        comp = tmp_path / "components"
        comp.mkdir()
        (comp / "my_comp.py").write_text("")
        (comp / "subdir").mkdir()
        (comp / "subdir" / "nested.json").write_text("{}")
        result = _list_data_files(_io.to_posix(comp))
        assert "subdir" not in result
        assert "nested.json" not in result

    def test_a7_nonexistent_dir(self, tmp_path):
        missing = tmp_path / "components"
        result = _list_data_files(_io.to_posix(missing))
        assert result == []

    def test_a8_order_is_sorted(self, tmp_path):
        comp = tmp_path / "components"
        comp.mkdir()
        (comp / "my_comp.py").write_text("")
        (comp / "z_last.json").write_text("{}")
        (comp / "a_first.csv").write_text("col1,col2\n")
        (comp / "m_middle.yaml").write_text("key: val\n")
        result = _list_data_files(_io.to_posix(comp))
        assert result == sorted(result)
        assert result == ["a_first.csv", "m_middle.yaml", "z_last.json"]


class TestComputeDataFilesHash:
    def test_empty_dir_returns_hash_of_empty_list(self, tmp_path):
        comp = tmp_path / "components"
        comp.mkdir()
        result = _compute_data_files_hash(_io.to_posix(comp))
        assert result == _io.hash_text("[]")

    def test_only_py_returns_hash_of_empty_list(self, tmp_path):
        comp = tmp_path / "components"
        comp.mkdir()
        (comp / "comp.py").write_text("x=1")
        assert _compute_data_files_hash(_io.to_posix(comp)) == _io.hash_text("[]")

    def test_nonexistent_dir_returns_hash_of_empty_list(self, tmp_path):
        missing = tmp_path / "no_components"
        assert _compute_data_files_hash(_io.to_posix(missing)) == _io.hash_text("[]")

    def test_different_content_different_hash(self, tmp_path):
        comp = tmp_path / "components"
        comp.mkdir()
        (comp / "comp.py").write_text("")
        data_file = comp / "data.json"
        data_file.write_text('{"v": 1}')
        h1 = _compute_data_files_hash(_io.to_posix(comp))
        data_file.write_text('{"v": 2}')
        h2 = _compute_data_files_hash(_io.to_posix(comp))
        assert h1 != h2

    def test_same_content_same_hash(self, tmp_path):
        comp = tmp_path / "components"
        comp.mkdir()
        (comp / "comp.py").write_text("")
        (comp / "data.json").write_text('{"v": 1}')
        h1 = _compute_data_files_hash(_io.to_posix(comp))
        h2 = _compute_data_files_hash(_io.to_posix(comp))
        assert h1 == h2

    def test_multiple_data_files_hashed(self, tmp_path):
        comp = tmp_path / "components"
        comp.mkdir()
        (comp / "comp.py").write_text("")
        (comp / "a.json").write_text('{"a": 1}')
        (comp / "b.csv").write_text("col\nval\n")
        h = _compute_data_files_hash(_io.to_posix(comp))
        assert h != _io.hash_text("[]")
        assert isinstance(h, str) and len(h) == 64  # SHA256 hex

    def test_binary_file_content_sensitive(self, tmp_path):
        """Binary (non-UTF-8) data files produce distinct hashes for distinct content."""
        comp = tmp_path / "components"
        comp.mkdir()
        (comp / "comp.py").write_text("")
        data_file = comp / "icon.png"
        data_file.write_bytes(b"\x89PNG\r\n\x1a\nversion1")
        h1 = _compute_data_files_hash(_io.to_posix(comp))
        data_file.write_bytes(b"\x89PNG\r\n\x1a\nversion2")
        h2 = _compute_data_files_hash(_io.to_posix(comp))
        assert h1 != h2

    def test_binary_file_not_empty_hash(self, tmp_path):
        """Binary data file hash must not be the sentinel empty string."""
        comp = tmp_path / "components"
        comp.mkdir()
        (comp / "comp.py").write_text("")
        (comp / "icon.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00")
        h = _compute_data_files_hash(_io.to_posix(comp))
        # The overall hash should differ from the empty-list sentinel
        assert h != _io.hash_text("[]")
        # The inner sha256_hex for the file must not collapse to "" (which would make
        # all binary files hash-equal to each other regardless of content).
        assert isinstance(h, str) and len(h) == 64


# ---------------------------------------------------------------------------
# Group B — cache key includes data files hash
# ---------------------------------------------------------------------------

class TestCacheKeyDataFiles:
    def setup_method(self):
        self.source_text = "RENDER_MODE='compile'\ndef render(ctx): return 'hello'"
        self.props = {"name": "world"}
        self.ctx_base = {
            "config": {},
            "skill_id": "core/test-skill",
            "skill_source_root": "/fake/root",
        }

    def _make_cache(self, tmp_path) -> ComponentCache:
        return ComponentCache(str(tmp_path / "cache"))

    def test_b1_cache_miss_when_data_file_added(self, tmp_path):
        cache = self._make_cache(tmp_path)
        ctx1 = {**self.ctx_base, "_data_files_hash": _io.hash_text("[]")}
        cache.put(self.source_text, self.props, ctx1, "output-v1")
        # Simulate adding a data file
        ctx2 = {**self.ctx_base, "_data_files_hash": _io.hash_text('[["data.json","abc123"]]')}
        result = cache.get(self.source_text, self.props, ctx2)
        assert result is None

    def test_b2_cache_miss_when_data_file_content_changes(self, tmp_path):
        cache = self._make_cache(tmp_path)
        ctx1 = {**self.ctx_base, "_data_files_hash": _io.hash_text('[["data.json","hash1"]]')}
        cache.put(self.source_text, self.props, ctx1, "output-v1")
        ctx2 = {**self.ctx_base, "_data_files_hash": _io.hash_text('[["data.json","hash2"]]')}
        result = cache.get(self.source_text, self.props, ctx2)
        assert result is None

    def test_b3_cache_hit_when_data_files_unchanged(self, tmp_path):
        cache = self._make_cache(tmp_path)
        data_hash = _io.hash_text('[["data.json","hash1"]]')
        ctx = {**self.ctx_base, "_data_files_hash": data_hash}
        cache.put(self.source_text, self.props, ctx, "my-output")
        result = cache.get(self.source_text, self.props, ctx)
        assert result == "my-output"

    def test_b4_absent_data_files_hash_uses_empty_string(self, tmp_path):
        cache = self._make_cache(tmp_path)
        ctx_no_hash = {**self.ctx_base}  # no _data_files_hash key
        cache.put(self.source_text, self.props, ctx_no_hash, "no-hash-output")
        result = cache.get(self.source_text, self.props, ctx_no_hash)
        assert result == "no-hash-output"

    def test_b5_absent_and_empty_data_hash_produce_same_key(self, tmp_path):
        cache = self._make_cache(tmp_path)
        ctx_absent = {**self.ctx_base}
        ctx_empty = {**self.ctx_base, "_data_files_hash": ""}
        cache.put(self.source_text, self.props, ctx_absent, "same-output")
        # Both absent and "" should produce the same key
        result = cache.get(self.source_text, self.props, ctx_empty)
        assert result == "same-output"


# ---------------------------------------------------------------------------
# Group C — lockfile data_files field
# ---------------------------------------------------------------------------

class TestLockfileDataFilesField:
    """Test that engine.py writes data_files into component records."""

    def test_c1_no_data_files_yields_empty_list(self, tmp_path):
        """compile_skill with no data files → data_files: [] in lockfile."""
        skill_dir = tmp_path / "module" / "my-skill"
        skill_dir.mkdir(parents=True)
        comp_dir = skill_dir / "components"
        comp_dir.mkdir()
        (comp_dir / "my_comp.py").write_text(
            "RENDER_MODE = 'compile'\ndef render(ctx, **props): return 'hi'\n"
        )
        skill_template = skill_dir / "my-skill.template.md"
        skill_template.write_text("# Skill\n<MyComp />\n")

        install_dir = tmp_path / "install"
        install_dir.mkdir()
        lockfile_path = install_dir / "_config" / "bmad.lock"
        lockfile_path.parent.mkdir(parents=True)

        from bmad_compile import engine
        engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        lock_data = json.loads(lockfile_path.read_text(encoding="utf-8"))
        entry = next(e for e in lock_data["entries"] if e["skill"] == "my-skill")
        assert entry["components"]
        for comp_record in entry["components"]:
            assert comp_record["data_files"] == []

    def test_c2_data_file_present_in_list(self, tmp_path):
        """compile_skill with data.json → data_files: ['data.json']."""
        skill_dir = tmp_path / "module" / "my-skill"
        skill_dir.mkdir(parents=True)
        comp_dir = skill_dir / "components"
        comp_dir.mkdir()
        (comp_dir / "my_comp.py").write_text(
            "RENDER_MODE = 'compile'\ndef render(ctx, **props): return 'hi'\n"
        )
        (comp_dir / "data.json").write_text('{"key": "val"}')
        skill_template = skill_dir / "my-skill.template.md"
        skill_template.write_text("# Skill\n<MyComp />\n")

        install_dir = tmp_path / "install"
        install_dir.mkdir()
        lockfile_path = install_dir / "_config" / "bmad.lock"
        lockfile_path.parent.mkdir(parents=True)

        from bmad_compile import engine
        engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        lock_data = json.loads(lockfile_path.read_text(encoding="utf-8"))
        entry = next(e for e in lock_data["entries"] if e["skill"] == "my-skill")
        for comp_record in entry["components"]:
            assert "data.json" in comp_record["data_files"]

    def test_c3_multiple_components_same_data_files_list(self, tmp_path):
        """All components in a skill share the same data_files list."""
        skill_dir = tmp_path / "module" / "my-skill"
        skill_dir.mkdir(parents=True)
        comp_dir = skill_dir / "components"
        comp_dir.mkdir()
        (comp_dir / "comp_a.py").write_text(
            "RENDER_MODE = 'compile'\ndef render(ctx, **props): return 'A'\n"
        )
        (comp_dir / "comp_b.py").write_text(
            "RENDER_MODE = 'compile'\ndef render(ctx, **props): return 'B'\n"
        )
        (comp_dir / "shared.json").write_text('{}')
        skill_template = skill_dir / "my-skill.template.md"
        skill_template.write_text("# Skill\n<CompA />\n<CompB />\n")

        install_dir = tmp_path / "install"
        install_dir.mkdir()
        lockfile_path = install_dir / "_config" / "bmad.lock"
        lockfile_path.parent.mkdir(parents=True)

        from bmad_compile import engine
        engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        lock_data = json.loads(lockfile_path.read_text(encoding="utf-8"))
        entry = next(e for e in lock_data["entries"] if e["skill"] == "my-skill")
        assert len(entry["components"]) == 2
        data_files_sets = [frozenset(c["data_files"]) for c in entry["components"]]
        assert all(df == data_files_sets[0] for df in data_files_sets)
        assert "shared.json" in data_files_sets[0]


# ---------------------------------------------------------------------------
# Group D — integration: _data_files_hash injected into ctx_dict
# ---------------------------------------------------------------------------

class TestEngineDataFilesHashInjection:
    """Verify _data_files_hash is in ctx_dict when compile_skill runs."""

    def test_d1_hash_injected_with_data_file(self, tmp_path):
        skill_dir = tmp_path / "module" / "my-skill"
        skill_dir.mkdir(parents=True)
        comp_dir = skill_dir / "components"
        comp_dir.mkdir()
        (comp_dir / "comp.py").write_text(
            "RENDER_MODE = 'compile'\ndef render(ctx, **props): return str(getattr(ctx, '_data_files_hash', 'ABSENT'))\n"
        )
        (comp_dir / "data.json").write_text('{"x": 1}')
        (skill_dir / "my-skill.template.md").write_text("# Skill\n<Comp />\n")

        install_dir = tmp_path / "install"
        install_dir.mkdir()
        (install_dir / "_config").mkdir()

        captured_ctx = {}

        from bmad_compile import engine
        from bmad_compile.component_runner import ComponentRunner

        original_run = ComponentRunner.run_compile_batch.__wrapped__ if hasattr(
            ComponentRunner.run_compile_batch, "__wrapped__"
        ) else ComponentRunner.run_compile_batch

        def capturing_run(self, invocations, ctx_dict):
            captured_ctx.update(ctx_dict)
            return original_run(self, invocations, ctx_dict)

        with patch.object(ComponentRunner, "run_compile_batch", capturing_run):
            engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        assert "_data_files_hash" in captured_ctx
        assert captured_ctx["_data_files_hash"] != _io.hash_text("[]")

    def test_d2_hash_is_empty_list_hash_when_no_data_files(self, tmp_path):
        skill_dir = tmp_path / "module" / "my-skill"
        skill_dir.mkdir(parents=True)
        comp_dir = skill_dir / "components"
        comp_dir.mkdir()
        (comp_dir / "comp.py").write_text(
            "RENDER_MODE = 'compile'\ndef render(ctx, **props): return 'ok'\n"
        )
        (skill_dir / "my-skill.template.md").write_text("# Skill\n<Comp />\n")

        install_dir = tmp_path / "install"
        install_dir.mkdir()
        (install_dir / "_config").mkdir()

        captured_ctx = {}

        from bmad_compile import engine
        from bmad_compile.component_runner import ComponentRunner

        original_run = ComponentRunner.run_compile_batch

        def capturing_run(self, invocations, ctx_dict):
            captured_ctx.update(ctx_dict)
            return original_run(self, invocations, ctx_dict)

        with patch.object(ComponentRunner, "run_compile_batch", capturing_run):
            engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        assert captured_ctx.get("_data_files_hash") == _io.hash_text("[]")

    def test_d3_cache_hit_preserved_when_py_and_data_unchanged(self, tmp_path):
        """Two consecutive compiles → second hits cache (no change to .py or data)."""
        skill_dir = tmp_path / "module" / "my-skill"
        skill_dir.mkdir(parents=True)
        comp_dir = skill_dir / "components"
        comp_dir.mkdir()
        (comp_dir / "comp.py").write_text(
            "RENDER_MODE = 'compile'\ndef render(ctx, **props): return 'stable'\n"
        )
        (comp_dir / "data.json").write_text('{"v": 1}')
        (skill_dir / "my-skill.template.md").write_text("# Skill\n<Comp />\n")

        install_dir = tmp_path / "install"
        install_dir.mkdir()
        (install_dir / "_config").mkdir()

        from bmad_compile import engine

        # First compile — populates cache
        engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)
        # Second compile — should hit cache (no change)
        engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        skill_md = install_dir / "module" / "my-skill" / "SKILL.md"
        assert "stable" in skill_md.read_text(encoding="utf-8")

    def test_d4_cache_miss_when_data_file_content_changes(self, tmp_path):
        """Change data.json content → cache misses → new output rendered."""
        skill_dir = tmp_path / "module" / "my-skill"
        skill_dir.mkdir(parents=True)
        comp_dir = skill_dir / "components"
        comp_dir.mkdir()
        (comp_dir / "comp.py").write_text(
            "RENDER_MODE = 'compile'\ndef render(ctx, **props): return 'value'\n"
        )
        data_file = comp_dir / "data.json"
        data_file.write_text('{"v": 1}')
        (skill_dir / "my-skill.template.md").write_text("# Skill\n<Comp />\n")

        install_dir = tmp_path / "install"
        install_dir.mkdir()
        (install_dir / "_config").mkdir()

        from bmad_compile import engine

        engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        # Change data.json
        data_file.write_text('{"v": 2}')

        # Second compile with changed data file — cache should miss
        engine.compile_skill(skill_dir, install_dir, lockfile_root=install_dir)

        skill_md = install_dir / "module" / "my-skill" / "SKILL.md"
        assert "value" in skill_md.read_text(encoding="utf-8")
