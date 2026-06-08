"""Tests for watch mode / hot-reload (Story 10.54).

Covers:
  AC-1  --watch flag requires --install-phase
  AC-3  _scan_watch_sources file inventory
  AC-4  _route_changed_file → skill routing
"""
from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

import pytest

# Ensure the scripts/ directory is on sys.path so compile.py is importable.
_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "src" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from compile import (  # noqa: E402
    _WATCH_POLL_INTERVAL,
    _WATCH_SKIP_DIRS,
    _route_changed_file,
    _scan_watch_sources,
    main,
)


# ---------------------------------------------------------------------------
# AC-1: --watch flag guards
# ---------------------------------------------------------------------------


def test_watch_requires_install_phase(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """--watch without --install-phase must exit 1 with a clear error."""
    rc = main(["--watch", "--install-dir", str(tmp_path)])
    assert rc == 1
    captured = capsys.readouterr()
    assert "error: --watch requires --install-phase" in captured.err


def test_watch_incompatible_with_batch(tmp_path: Path) -> None:
    """--watch cannot be combined with --batch (argparse mutex group prevents --install-phase + --batch)."""
    fake_batch = tmp_path / "batch.json"
    fake_batch.write_text("[]", encoding="utf-8")
    with pytest.raises(SystemExit) as exc_info:
        main(["--watch", "--install-phase", "--install-dir", str(tmp_path), "--batch", str(fake_batch)])
    assert exc_info.value.code != 0


# ---------------------------------------------------------------------------
# AC-3: _scan_watch_sources inventory
# ---------------------------------------------------------------------------


def test_scan_includes_template_md(tmp_path: Path) -> None:
    """*.template.md files are included in the watch inventory."""
    skill_dir = tmp_path / "core" / "my-skill"
    skill_dir.mkdir(parents=True)
    tpl = skill_dir / "my-skill.template.md"
    tpl.write_text("hello", encoding="utf-8")

    sources = _scan_watch_sources(tmp_path)

    assert str(tpl) in sources


def test_scan_excludes_skill_md(tmp_path: Path) -> None:
    """SKILL.md (compiled output) must NOT appear in the watch inventory."""
    skill_dir = tmp_path / "core" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "my-skill.template.md").write_text("src", encoding="utf-8")
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("compiled", encoding="utf-8")

    sources = _scan_watch_sources(tmp_path)

    assert str(skill_md) not in sources


def test_scan_excludes_config_dir(tmp_path: Path) -> None:
    """Files under _config/ must NOT appear in the watch inventory."""
    config_dir = tmp_path / "_config"
    config_dir.mkdir()
    lock = config_dir / "bmad.lock"
    lock.write_text("{}", encoding="utf-8")

    sources = _scan_watch_sources(tmp_path)

    assert str(lock) not in sources


def test_scan_includes_customize_toml(tmp_path: Path) -> None:
    """customize.toml inside a skill dir is included."""
    skill_dir = tmp_path / "bmm" / "my-skill"
    skill_dir.mkdir(parents=True)
    toml = skill_dir / "customize.toml"
    toml.write_text("[workflow]\n", encoding="utf-8")

    sources = _scan_watch_sources(tmp_path)

    assert str(toml) in sources


def test_scan_includes_component_py(tmp_path: Path) -> None:
    """components/*.py files are included."""
    comp_dir = tmp_path / "core" / "my-skill" / "components"
    comp_dir.mkdir(parents=True)
    py = comp_dir / "banner.py"
    py.write_text("def render(): pass", encoding="utf-8")

    sources = _scan_watch_sources(tmp_path)

    assert str(py) in sources


# ---------------------------------------------------------------------------
# AC-4: _route_changed_file routing
# ---------------------------------------------------------------------------


def test_route_skill_local_file(tmp_path: Path) -> None:
    """A file inside module/skill/ routes to that single skill dir."""
    skill_dir = tmp_path / "4-implementation" / "bmad-quick-dev"
    skill_dir.mkdir(parents=True)
    tpl = skill_dir / "bmad-quick-dev.template.md"
    tpl.write_text("t", encoding="utf-8")

    result = _route_changed_file(tpl, tmp_path)

    assert result is not None
    assert len(result) == 1
    assert result[0] == skill_dir


def test_route_shared_fragment_returns_none(tmp_path: Path) -> None:
    """A file under _shared/ must return None (all skills)."""
    shared_file = tmp_path / "_shared" / "fragments" / "conventions.md"
    shared_file.parent.mkdir(parents=True)
    shared_file.write_text("c", encoding="utf-8")

    result = _route_changed_file(shared_file, tmp_path)

    assert result is None


def test_route_custom_override_returns_none(tmp_path: Path) -> None:
    """A file under custom/ must return None (all skills)."""
    custom_file = tmp_path / "custom" / "fragments" / "core" / "my-skill" / "SKILL.template.md"
    custom_file.parent.mkdir(parents=True)
    custom_file.write_text("o", encoding="utf-8")

    result = _route_changed_file(custom_file, tmp_path)

    assert result is None


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------


def test_watch_constants_importable() -> None:
    """_WATCH_POLL_INTERVAL and _WATCH_SKIP_DIRS are importable and sensible."""
    assert _WATCH_POLL_INTERVAL == 0.5
    assert "_config" in _WATCH_SKIP_DIRS
    assert "memory" in _WATCH_SKIP_DIRS
