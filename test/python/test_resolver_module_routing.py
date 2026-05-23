"""Story 10.0 — `_shared` module routing tests (AC-9, AC-10, AC-11, AC-12).

Exercises the engine + resolver edits that admit `_shared` as the documented
exception to the underscore-prefix module-discovery filter, and the 5-tier
cascade firing for `_shared/...` include paths.

Import pattern: package-relative (no sys.path.insert). The repo's pytest
configuration handles sys.path so direct relative imports work.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from src.scripts.bmad_compile import engine, errors


# ---------- AC-9 --------------------------------------------------------------

def test_shared_module_routing(tmp_path):
    """AC-9: tier-5 base resolution — bmm consumer hits _shared/fragments/X.md."""
    install_root = tmp_path
    (install_root / "_shared/fragments").mkdir(parents=True)
    (install_root / "_shared/fragments/test_routing.md").write_text(
        "shared fragment body\n", encoding="utf-8"
    )
    (install_root / "bmm/sample-skill").mkdir(parents=True)
    (install_root / "bmm/sample-skill/sample-skill.template.md").write_text(
        'Lead: <<include path="_shared/fragments/test_routing.md">>\n',
        encoding="utf-8",
    )
    (install_root / "_config").mkdir()
    engine.compile_skill(
        install_root / "bmm/sample-skill",
        install_root,
        target_ide=None,
        lockfile_root=install_root,
        override_root=None,
    )
    out = (install_root / "bmm/sample-skill/SKILL.md").read_text(encoding="utf-8")
    assert out == "Lead: shared fragment body\n\n", repr(out)


# ---------- AC-10 -------------------------------------------------------------

def test_other_underscore_module_still_rejected(tmp_path):
    """AC-10: guard expansion adds ONLY `_shared` — other `_`-prefix still fails to
    resolve. (Actual error is MissingFragmentError because the underscore filter in
    `_discover_module_roots` excludes the prefix from module_roots BEFORE the guard
    at resolver.py:991 sees it; the prefix-split routine then treats `_not_admitted`
    as a bare-path segment under current_module, no file exists, miss. Either way,
    the narrowness invariant — only `_shared` is admitted — holds.)"""
    install_root = tmp_path
    (install_root / "bmm/sample-skill").mkdir(parents=True)
    (install_root / "bmm/sample-skill/sample-skill.template.md").write_text(
        'Lead: <<include path="_not_admitted/X.md">>\n', encoding="utf-8"
    )
    (install_root / "_config").mkdir()
    with pytest.raises(errors.MissingFragmentError):
        engine.compile_skill(
            install_root / "bmm/sample-skill",
            install_root,
            target_ide=None,
            lockfile_root=install_root,
            override_root=None,
        )


def test_underscore_filter_preserved_for_other_dirs(tmp_path):
    """AC-10: _discover_module_roots still excludes `_`-prefixed dirs OTHER than _shared."""
    install_root = tmp_path
    (install_root / "_other_underscore").mkdir()
    (install_root / "bmm").mkdir()
    install_posix = engine.io.to_posix(install_root)
    roots = engine._discover_module_roots(
        install_posix, "bmm", install_posix / "bmm"
    )
    assert "_other_underscore" not in roots
    assert "_shared" in roots  # injected per AC-1
    assert "bmm" in roots       # current_module fallback or discovered


# ---------- AC-11 -------------------------------------------------------------

def test_shared_module_user_override_tier_hit(tmp_path):
    """AC-11: DN-1 Option 2 escape hatch — user-override global tier hits for _shared paths."""
    install_root = tmp_path
    override_root = install_root / "custom"  # must live under scenario_root
    (install_root / "_shared/fragments").mkdir(parents=True)
    (install_root / "_shared/fragments/test_routing.md").write_text(
        "BASE shared body\n", encoding="utf-8"
    )
    (override_root / "fragments").mkdir(parents=True)
    (override_root / "fragments/test_routing.md").write_text(
        "USER override body\n", encoding="utf-8"
    )
    (install_root / "bmm/sample-skill").mkdir(parents=True)
    (install_root / "bmm/sample-skill/sample-skill.template.md").write_text(
        'Lead: <<include path="_shared/fragments/test_routing.md">>\n',
        encoding="utf-8",
    )
    (install_root / "_config").mkdir()
    engine.compile_skill(
        install_root / "bmm/sample-skill",
        install_root,
        target_ide=None,
        lockfile_root=install_root,
        override_root=override_root,
    )
    out = (install_root / "bmm/sample-skill/SKILL.md").read_text(encoding="utf-8")
    assert out == "Lead: USER override body\n\n", repr(out)


# ---------- AC-12 -------------------------------------------------------------

def test_shared_module_lockfile_records_fragment(tmp_path):
    """AC-12: existing v2 lockfile fragments[] records _shared/... paths
    POSIX-normalized with correct SHA-256, without schema change. Binary fail
    if _normalize_path strips the _shared/ prefix or otherwise loses info."""
    install_root = tmp_path
    fragment_bytes = b"shared fragment body\n"
    fragment_sha = hashlib.sha256(fragment_bytes).hexdigest()
    (install_root / "_shared/fragments").mkdir(parents=True)
    (install_root / "_shared/fragments/test_routing.md").write_bytes(fragment_bytes)
    (install_root / "bmm/sample-skill").mkdir(parents=True)
    (install_root / "bmm/sample-skill/sample-skill.template.md").write_text(
        'Lead: <<include path="_shared/fragments/test_routing.md">>\n',
        encoding="utf-8",
    )
    (install_root / "_config").mkdir()
    engine.compile_skill(
        install_root / "bmm/sample-skill",
        install_root,
        target_ide=None,
        lockfile_root=install_root,
        override_root=None,
    )
    lockfile_path = install_root / "_config" / "bmad.lock"
    assert lockfile_path.exists(), "compile must produce a lockfile"
    lockfile = json.loads(lockfile_path.read_text(encoding="utf-8"))
    entries = lockfile.get("entries", [])
    skill_entry = next(
        (e for e in entries if e.get("skill") == "sample-skill"), None
    )
    assert skill_entry is not None, (
        f"expected bmad_compile lockfile entry with skill=='sample-skill'; "
        f"got skills={[e.get('skill') for e in entries]}"
    )
    fragments = skill_entry.get("fragments", [])
    assert len(fragments) == 1, f"expected exactly 1 fragment, got {fragments!r}"
    frag = fragments[0]
    assert frag["path"] == "_shared/fragments/test_routing.md", (
        f"AC-12 BINARY FAIL: lockfile fragment path is {frag['path']!r}, "
        f"expected '_shared/fragments/test_routing.md'. "
        f"_normalize_path may be stripping the _shared/ prefix — "
        f"this is a story-close blocker, not a DN."
    )
    assert frag["hash"] == fragment_sha, (
        f"hash mismatch: got {frag['hash']}, expected {fragment_sha}"
    )
