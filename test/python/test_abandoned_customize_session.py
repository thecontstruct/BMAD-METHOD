"""Integration test: abandoned bmad-customize session must not write any files (FR55)."""
from __future__ import annotations

import shutil
import stat
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_SRC = REPO_ROOT / "src" / "core-skills" / "bmad-customize"
SCRIPTS_DIR = REPO_ROOT / "src" / "scripts"
COMPILE_SCRIPT = REPO_ROOT / "src" / "scripts" / "compile.py"


class AbandonedCustomizeSessionTest(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp_dir = Path(self._tmp.name)
        # Mirror Story 7.2 setUp: install_dir = _bmad/, skill at install_dir/core/bmad-customize/
        self.install_dir = self.tmp_dir / "_bmad"
        skill_dst = self.install_dir / "core" / "bmad-customize"
        skill_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(SKILL_SRC), str(skill_dst))
        # R2-BH-2 pattern: chmod covers dirs too (Linux read-only dir guard).
        for p in skill_dst.rglob("*"):
            p.chmod(p.stat().st_mode | stat.S_IWUSR)
        # DN-7.4-1: seed bmad.lock with sentinel bytes so byte-identity assertion is load-bearing.
        _lock = self.install_dir / "_config" / "bmad.lock"
        _lock.parent.mkdir(parents=True, exist_ok=True)
        _lock.write_bytes(b'{"sentinel":true}')
        # DN-7.4-2: pre-seed sentinel custom file to detect modification of existing overrides.
        _sentinel = self.install_dir / "custom" / "fragments" / "core" / "bmad-customize" / "sentinel.md"
        _sentinel.parent.mkdir(parents=True, exist_ok=True)
        _sentinel.write_bytes(b"sentinel-fr55-test")
        # sys.path injection (import bmad_customize from source)
        self._orig_path = sys.path[:]
        sys.path.insert(0, str(SCRIPTS_DIR))

    def tearDown(self) -> None:
        sys.path[:] = self._orig_path
        for key in list(sys.modules):
            if key == "bmad_customize" or key.startswith("bmad_customize."):
                del sys.modules[key]
        self._tmp.cleanup()

    def _assert_step(self, step: str, condition: bool, message: str) -> None:
        if not condition:
            self.fail(f"[{step}] {message}")

    def _make_run_fn(self):  # type: ignore[return]
        """Custom run_fn: sets cwd=REPO_ROOT, enforces 120s timeout floor (BH-3 cwd-pop)."""
        def run_fn(*args, **kwargs):  # type: ignore[return]
            kwargs.pop("cwd", None)
            kwargs["cwd"] = str(REPO_ROOT)
            if "timeout" in kwargs:
                kwargs["timeout"] = max(kwargs["timeout"], 120)
            else:
                kwargs["timeout"] = 120
            try:
                return subprocess.run(*args, **kwargs)
            except subprocess.TimeoutExpired as exc:
                raise subprocess.TimeoutExpired(
                    exc.cmd, exc.timeout, output=exc.output, stderr=exc.stderr
                ) from exc
        return run_fn

    def _capture_custom_state(self, custom_dir: Path) -> frozenset:
        if not custom_dir.exists():
            return frozenset()
        return frozenset(
            p.relative_to(custom_dir)
            for p in custom_dir.rglob("*")
            if p.is_file()
        )

    def test_abandon_does_not_write(self) -> None:
        from bmad_customize.discovery import discover_surface
        from bmad_customize.routing import route_intent
        from bmad_customize.drafting import draft_content

        skill_id = "core/bmad-customize"
        intent_text = "update preflight"
        compile_py = COMPILE_SCRIPT
        run_fn = self._make_run_fn()

        all_events: list[dict] = []
        emit_fn = all_events.append

        install_dir = self.install_dir
        custom_dir = install_dir / "custom"
        lock_path = install_dir / "_config" / "bmad.lock"

        # Capture pre-session state
        pre_custom = self._capture_custom_state(custom_dir)
        pre_lock_bytes = lock_path.read_bytes() if lock_path.exists() else b""

        # Step 1: discover_surface
        discover_surface(
            intent=intent_text,
            skill_id=skill_id,
            install_dir=str(install_dir),
            compile_py=compile_py,
            emit_fn=emit_fn,
            run_fn=run_fn,
        )
        self._assert_step(
            "discover",
            any(e.get("action") == "discover" for e in all_events),
            "discover_surface emitted no discover event",
        )

        # Step 2: route_intent
        # Handler independently re-invokes compiler — no surface dict input needed.
        route_intent(
            intent=intent_text,
            skill_id=skill_id,
            install_dir=str(install_dir),
            compile_py=compile_py,
            emit_fn=emit_fn,
            run_fn=run_fn,
        )
        self._assert_step(
            "route",
            any(e.get("action") in ("propose_route", "request_disambiguation",
                                    "request_plane_disambiguation", "warn_full_skill")
                for e in all_events),
            "route_intent emitted no routing event",
        )

        # Step 3: draft_content
        # Extract route fields from propose_route event before calling.
        route_event = next(
            (e for e in all_events if e.get("action") == "propose_route"),
            None,
        )
        # DN-7.4-3: skip (not fail) when skill surface drifted to disambiguation.
        if route_event is None:
            self.skipTest(
                "route_intent emitted no propose_route for intent 'update preflight' — "
                "skill surface has changed; update INTENT selection to restore unambiguous prose route"
            )
        draft_content(
            intent=intent_text,
            plane=route_event["plane"],
            field_path=route_event.get("field_path"),
            fragment_name=route_event.get("fragment_name"),
            target_file=route_event["target_file"],
            skill_id=skill_id,
            install_dir=str(install_dir),
            compile_py=compile_py,
            emit_fn=emit_fn,
            run_fn=run_fn,
        )

        # AC-1: propose_draft was emitted
        self._assert_step(
            "ac1",
            any(e.get("action") == "propose_draft" for e in all_events),
            "No propose_draft event emitted — session did not reach draft stage",
        )

        # Capture post-session state
        post_custom = self._capture_custom_state(custom_dir)
        post_lock_bytes = lock_path.read_bytes() if lock_path.exists() else b""

        # AC-2 + AC-3: no files written under _bmad/custom/
        added = post_custom - pre_custom
        assert not added, (
            f"FR55 VIOLATION: files created during abandoned session: {sorted(added)!r}"
        )

        # DN-7.4-2: sentinel custom file bytes unchanged (detect modification of existing overrides)
        sentinel_path = custom_dir / "fragments" / "core" / "bmad-customize" / "sentinel.md"
        self.assertEqual(
            b"sentinel-fr55-test",
            sentinel_path.read_bytes(),
            "FR55 VIOLATION: existing custom file modified during abandoned session",
        )

        # bmad.lock byte identity (DN-7.4-1: load-bearing — lock seeded with sentinel in setUp)
        self.assertEqual(
            pre_lock_bytes,
            post_lock_bytes,
            "FR55 VIOLATION: bmad.lock modified during abandoned session",
        )


if __name__ == "__main__":
    unittest.main()
