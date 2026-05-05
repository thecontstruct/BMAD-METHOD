"""Story 5.5a: Integration tests for concurrency (AC-1, AC-2, AC-3).

Kept separate from test_lazy_compile.py to isolate subprocess/SIGKILL fixtures.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

_SRC_PATH = Path(__file__).resolve().parent.parent.parent / "src" / "scripts"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))

from src.scripts.bmad_compile import engine as bmad_engine
from src.scripts.bmad_compile import io as bmad_io
from src.scripts.bmad_compile.lazy_compile import _find_lockfile_entry


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_minimal_skill(
    project_root: Path,
    module: str = "mymodule",
    skill: str = "my-skill",
) -> Path:
    """Create a minimal compilable skill directory tree. Return skill_dir."""
    scenario_root = project_root / "_bmad"
    skill_dir = scenario_root / module / skill
    skill_dir.mkdir(parents=True, exist_ok=True)
    _write(skill_dir / "fragments" / "content.template.md", f"# {skill}\n\nHello world.\n")
    _write(skill_dir / f"{skill}.template.md",
           '<<include path="fragments/content.template.md">>')
    (scenario_root / "custom").mkdir(parents=True, exist_ok=True)
    (scenario_root / "_config").mkdir(parents=True, exist_ok=True)
    return skill_dir


def _compile_skill(
    project_root: Path,
    module: str = "mymodule",
    skill: str = "my-skill",
) -> None:
    """Run engine.compile_skill to produce a real lockfile + SKILL.md."""
    scenario_root = project_root / "_bmad"
    skill_dir = scenario_root / module / skill
    bmad_engine.compile_skill(
        skill_dir,
        scenario_root,
        None,
        lockfile_root=scenario_root,
        override_root=scenario_root / "custom",
    )


def _run_guard(
    project_root: Path,
    skill: str,
    extra_args: list[str] | None = None,
) -> "subprocess.CompletedProcess[str]":
    """Invoke the guard as a subprocess. cwd=_SRC_PATH so bmad_compile is found."""
    cmd = [
        sys.executable, "-m", "bmad_compile.lazy_compile",
        skill, "--project-root", str(project_root),
    ]
    if extra_args:
        cmd.extend(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(_SRC_PATH))


def _hold_lock_subprocess(lock_path_str: str) -> "subprocess.Popen[bytes]":
    """Start a child process that acquires the advisory lock and signals when ready.

    Uses a subprocess so OS-level lock contention is real (same-process flock
    re-grants on POSIX; subprocess is a distinct process identity on both POSIX
    and Windows).
    """
    helper = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(_SRC_PATH)!r})
        from bmad_compile import io as bmad_io
        fd = bmad_io.acquire_lock({lock_path_str!r}, 60)
        sys.stdout.write("LOCKED\\n")
        sys.stdout.flush()
        time.sleep(60)
    """)
    p: subprocess.Popen[bytes] = subprocess.Popen(
        [sys.executable, "-c", helper],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    line = p.stdout.readline()  # type: ignore[union-attr]
    if not line:
        p.wait()
        err = p.stderr.read().decode(errors="replace")  # type: ignore[union-attr]
        raise RuntimeError(f"Lock holder subprocess failed: {err!r}")
    assert line.strip() == b"LOCKED"
    return p


# ---------------------------------------------------------------------------
# TestSerialization (AC-1)
# ---------------------------------------------------------------------------

class TestSerialization(unittest.TestCase):
    """Advisory lock serializes concurrent slow-path invocations (AC-1)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self._tmp.name) / "project"
        self.skill_dir = _make_minimal_skill(self.project_root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_lock_file_in_skill_dir(self) -> None:
        """Guard creates .compiling.lock inside skill_dir on slow path (AC-1)."""
        # No prior compile: guard takes slow path unconditionally.
        _run_guard(self.project_root, "my-skill")
        lock_path = self.skill_dir / ".compiling.lock"
        self.assertTrue(lock_path.exists(), ".compiling.lock not created in skill_dir")

    def test_p2_waits_and_emits_without_recompile(self) -> None:
        """P2 waits for P1's lock, then emits SKILL.md without recompile (AC-1)."""
        _compile_skill(self.project_root)
        scenario_root = self.project_root / "_bmad"
        skill_md = self.skill_dir / "SKILL.md"

        # Modify fragment so both guard passes see slow path.
        frag = self.skill_dir / "fragments" / "content.template.md"
        frag.write_text("# my-skill\n\nModified content.\n", encoding="utf-8")

        # Acquire the lock in-process before starting P2.
        lock_path_str = str(self.skill_dir / ".compiling.lock")
        lock_fd = bmad_io.acquire_lock(lock_path_str, timeout_seconds=60)

        # Start P2 with text=True so stdout newlines are normalized on all platforms.
        p2: subprocess.Popen[str] = subprocess.Popen(
            [
                sys.executable, "-m", "bmad_compile.lazy_compile",
                "my-skill", "--project-root", str(self.project_root),
                "--lock-timeout-seconds", "30",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(_SRC_PATH),
        )

        # Give P2 time to start and block on the lock.
        time.sleep(1.0)

        # Recompile in-process (still holding lock): updates lockfile + SKILL.md.
        bmad_engine.compile_skill(
            self.skill_dir,
            scenario_root,
            None,
            lockfile_root=scenario_root,
            override_root=scenario_root / "custom",
        )
        mtime_before = os.stat(skill_md).st_mtime_ns

        # Release the lock — P2 can now acquire it.
        bmad_io.release_lock(lock_fd)

        stdout_str, stderr_str = p2.communicate(timeout=45)
        mtime_after = os.stat(skill_md).st_mtime_ns

        self.assertEqual(p2.returncode, 0, stderr_str)
        expected = skill_md.read_text(encoding="utf-8")
        self.assertEqual(stdout_str, expected)
        # SKILL.md must NOT be rewritten by P2 — it emitted without recompiling.
        self.assertEqual(mtime_before, mtime_after, "P2 should not have recompiled")


# ---------------------------------------------------------------------------
# TestSigkillRecovery (AC-2)
# ---------------------------------------------------------------------------

class TestSigkillRecovery(unittest.TestCase):
    """Guard recovers from a lock-holder killed mid-compile (AC-2)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self._tmp.name) / "project"
        self.skill_dir = _make_minimal_skill(self.project_root)
        _compile_skill(self.project_root)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_sigkill_stale_lock_recovery(self) -> None:
        """After lock-holder is killed, next guard invocation recompiles cleanly (AC-2)."""
        # Modify fragment so lockfile is now stale relative to on-disk inputs.
        frag = self.skill_dir / "fragments" / "content.template.md"
        frag.write_text("# my-skill\n\nKilled content.\n", encoding="utf-8")

        # Simulate P1 killed mid-compile: holds lock but never updates lockfile.
        lock_path_str = str(self.skill_dir / ".compiling.lock")
        p1 = _hold_lock_subprocess(lock_path_str)
        try:
            p1.kill()
        finally:
            p1.wait()

        # Guard must detect stale lockfile, recompile, and exit 0.
        result = _run_guard(self.project_root, "my-skill")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip(), "stdout should contain SKILL.md content")

        lockfile_path = self.project_root / "_bmad" / "_config" / "bmad.lock"
        entry = _find_lockfile_entry(lockfile_path, "my-skill")
        self.assertIsNotNone(
            entry,
            "_find_lockfile_entry must return non-None dict after SIGKILL recovery",
        )


# ---------------------------------------------------------------------------
# TestLockTimeout (AC-3)
# ---------------------------------------------------------------------------

class TestLockTimeout(unittest.TestCase):
    """Timeout exits 1 with clear message; stdout is empty (AC-3)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.project_root = Path(self._tmp.name) / "project"
        self.skill_dir = _make_minimal_skill(self.project_root)
        _compile_skill(self.project_root)
        # Modify fragment so guard enters slow path.
        frag = self.skill_dir / "fragments" / "content.template.md"
        frag.write_text("# my-skill\n\nTimeout content.\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run_with_lock_held(self, extra_args: list[str]) -> "subprocess.CompletedProcess[str]":
        """Hold compile lock, run guard, release lock. Return guard result."""
        lock_path_str = str(self.skill_dir / ".compiling.lock")
        p_holder = _hold_lock_subprocess(lock_path_str)
        try:
            return _run_guard(self.project_root, "my-skill", extra_args)
        finally:
            p_holder.kill()
            p_holder.wait()

    def test_lock_timeout_exits_1(self) -> None:
        """Timeout causes exit 1; stderr names the skill and indicates timeout (AC-3)."""
        result = self._run_with_lock_held(["--lock-timeout-seconds", "2"])
        self.assertEqual(result.returncode, 1)
        self.assertIn("my-skill", result.stderr)
        self.assertTrue(
            "timeout" in result.stderr.lower(),
            f"Expected timeout message in stderr; got: {result.stderr!r}",
        )

    def test_timeout_does_not_emit_stale_content(self) -> None:
        """Stdout is empty on timeout — no stale content emitted (AC-3)."""
        result = self._run_with_lock_held(["--lock-timeout-seconds", "2"])
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
