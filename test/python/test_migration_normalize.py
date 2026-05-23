"""Unit tests for `src/scripts/migration_normalize.py` (Story 10.1 AC-NORM-4).

13 test cases per spec post R1-ECH-3/ECH-14/BH-10 expansion.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "src" / "scripts" / "migration_normalize.py"


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=str(cwd) if cwd else None,
    )


def _make_skill(tmp_path: Path, name: str, raw_bytes: bytes) -> Path:
    d = tmp_path / "skills" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_bytes(raw_bytes)
    return d


def test_strip_bom(tmp_path: Path) -> None:
    """Test 1: leading UTF-8 BOM stripped; content preserved byte-for-byte."""
    skill = _make_skill(tmp_path, "s", b"\xef\xbb\xbf# Title\n")
    r = _run(["--skill", str(skill)])
    assert r.returncode == 0, r.stderr
    assert (skill / "SKILL.md").read_bytes() == b"# Title\n"


def test_crlf_to_lf(tmp_path: Path) -> None:
    """Test 2: CRLF normalized to LF."""
    skill = _make_skill(tmp_path, "s", b"line1\r\nline2\r\n")
    r = _run(["--skill", str(skill)])
    assert r.returncode == 0, r.stderr
    assert (skill / "SKILL.md").read_bytes() == b"line1\nline2\n"


def test_golden_mode_lf_only(tmp_path: Path) -> None:
    """Test 3: --golden-mode emits LF-only bytes regardless of CRLF source."""
    src = tmp_path / "src.md"
    dst = tmp_path / "dst.md"
    src.write_bytes(b"a\r\nb\r\nc\r\n")
    r = _run(["--golden-mode", str(src), str(dst)])
    assert r.returncode == 0, r.stderr
    data = dst.read_bytes()
    assert b"\r\n" not in data
    assert data == b"a\nb\nc\n"


def test_canonicalize_ascii(tmp_path: Path) -> None:
    """Test 4: --canonicalize-ascii replaces en/em-dash + right arrow with ASCII."""
    skill = _make_skill(tmp_path, "s", "em — dash and → arrow and – en\n".encode("utf-8"))
    r = _run(["--canonicalize-ascii", str(skill)])
    assert r.returncode == 0, r.stderr
    assert (skill / "SKILL.md").read_bytes() == b"em -- dash and -> arrow and - en\n"


def test_non_utf8_hard_fail(tmp_path: Path) -> None:
    """Test 5: --skill on non-UTF-8 input exits 2 with stderr signal."""
    skill = _make_skill(tmp_path, "s", b"\xff\xfeinvalid")
    r = _run(["--skill", str(skill)])
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "not valid UTF-8" in r.stderr


def test_idempotent_on_normalized(tmp_path: Path) -> None:
    """Test 6: --skill twice on already-normalized source — SHA unchanged."""
    skill = _make_skill(tmp_path, "s", b"# Title\n\nSome body.\n")
    _run(["--skill", str(skill)])
    h1 = hashlib.sha256((skill / "SKILL.md").read_bytes()).hexdigest()
    _run(["--skill", str(skill)])
    h2 = hashlib.sha256((skill / "SKILL.md").read_bytes()).hexdigest()
    assert h1 == h2


def test_unicode_preserving_default(tmp_path: Path) -> None:
    """Test 7: default --skill preserves U+2014 em-dash byte-for-byte."""
    body = "preserve — this\n".encode("utf-8")
    skill = _make_skill(tmp_path, "s", body)
    r = _run(["--skill", str(skill)])
    assert r.returncode == 0, r.stderr
    assert (skill / "SKILL.md").read_bytes() == body


def test_validate_manifest_valid(tmp_path: Path) -> None:
    """Test 8: valid manifest against valid schema — exit 0."""
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        },
    }
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text("- name: bmad-correct-course\n", encoding="utf-8")
    r = _run(["--validate-manifest", str(manifest_path), "--schema", str(schema_path)])
    assert r.returncode == 0, (r.stdout, r.stderr)


def test_validate_manifest_invalid(tmp_path: Path) -> None:
    """Test 9: manifest with extra unknown field — exit non-zero."""
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        },
    }
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text("- name: x\n  extra: rogue\n", encoding="utf-8")
    r = _run(["--validate-manifest", str(manifest_path), "--schema", str(schema_path)])
    assert r.returncode != 0


def test_golden_mode_non_utf8_hard_fail(tmp_path: Path) -> None:
    """Test 10 (ECH-3): --golden-mode on non-UTF-8 source — exit 2."""
    src = tmp_path / "src.md"
    dst = tmp_path / "dst.md"
    src.write_bytes(b"\xff\xfeinvalid")
    r = _run(["--golden-mode", str(src), str(dst)])
    assert r.returncode == 2, (r.stdout, r.stderr)
    assert "not valid UTF-8" in r.stderr
    assert not dst.exists()


def test_windows_1252_hard_fail(tmp_path: Path) -> None:
    """Test 11 (ECH-14): Windows-1252 en-dash byte (\\x96) hard-fails as non-UTF-8."""
    skill = _make_skill(tmp_path, "s", b"em\x96dash\n")
    r = _run(["--skill", str(skill)])
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "not valid UTF-8" in r.stderr


def test_body_embedded_u_feff_preserved(tmp_path: Path) -> None:
    """Test 12 (ECH-14): body-embedded U+FEFF (not at byte 0) preserved."""
    # File starts with "# Title\n" then has U+FEFF in body
    raw = "# Title\n﻿## Section\n".encode("utf-8")
    skill = _make_skill(tmp_path, "s", raw)
    r = _run(["--skill", str(skill)])
    assert r.returncode == 0, r.stderr
    # Body U+FEFF preserved
    assert (skill / "SKILL.md").read_bytes() == raw
    # Census reports the U+FEFF
    assert "U+FEFF" in r.stdout


def test_golden_mode_idempotent_on_lf_source(tmp_path: Path) -> None:
    """Test 13 (BH-10): --golden-mode twice on LF source — SHA unchanged."""
    src = tmp_path / "src.md"
    dst = tmp_path / "dst.md"
    src.write_bytes(b"alpha\nbeta\n")
    _run(["--golden-mode", str(src), str(dst)])
    h1 = hashlib.sha256(dst.read_bytes()).hexdigest()
    _run(["--golden-mode", str(src), str(dst)])
    h2 = hashlib.sha256(dst.read_bytes()).hexdigest()
    assert h1 == h2
