"""Tests for compile.py --batch <skills.json> mode (Story 5.6).

Coverage:
- TestShimIntegrity: AC-1 SKILL.md shim + bmad-quick-dev.template.md exist
- TestBatchMode: --batch JSON contract, NDJSON output, validation, dedup
- TestHashSkip: AC-3 hash-based skip on re-install (compiled=false on repeat)
- TestBatchPerf: advisory perf targets (gated by BMAD_RUN_PERF=1; @pytest.mark.perf)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

try:
    import pytest
except ImportError:
    # Lightweight shim so the file imports under unittest discover even when
    # pytest isn't installed (project uses unittest by default).
    class _PytestShim:
        class mark:
            @staticmethod
            def perf(fn):
                return fn
    pytest = _PytestShim()  # type: ignore[assignment]


_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_COMPILE_PY = _PROJECT_ROOT / "src" / "scripts" / "compile.py"
_BMAD_QUICK_DEV = _PROJECT_ROOT / "src" / "bmm-skills" / "4-implementation" / "bmad-quick-dev"

# In-process import for _compile_one_skill (AC-3 tests: cannot test via subprocess
# because unittest.mock.patch does not cross the subprocess boundary).
_SCRIPTS_DIR = str(_PROJECT_ROOT / "src" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from compile import _compile_one_skill  # noqa: E402 — must follow sys.path setup


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_batch(batch_file: Path) -> tuple[int, list[dict], str]:
    """Invoke compile.py --batch and return (exit_code, events, stderr)."""
    result = subprocess.run(
        [sys.executable, str(_COMPILE_PY), "--batch", str(batch_file)],
        capture_output=True,
        text=True,
    )
    events = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return result.returncode, events, result.stderr


def _make_batch_file(tmp: Path, entries: list[dict]) -> Path:
    p = tmp / "skills.json"
    p.write_text(json.dumps(entries), encoding="utf-8")
    return p


def _make_skill(install: Path, module: str, name: str, body: str = "Hello world") -> Path:
    skill_dir = install / module / name
    _write(skill_dir / f"{name}.template.md", body)
    return skill_dir


# ---------------------------------------------------------------------------
# TestShimIntegrity (AC-1)
# ---------------------------------------------------------------------------

class TestShimIntegrity(unittest.TestCase):
    """AC-1: SKILL.md shim contents + bmad-quick-dev.template.md existence."""

    def test_shim_contains_lazy_compile(self) -> None:
        skill_md = (_BMAD_QUICK_DEV / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("lazy_compile", skill_md)

    def test_shim_is_at_most_15_lines(self) -> None:
        lines = (_BMAD_QUICK_DEV / "SKILL.md").read_text(encoding="utf-8").splitlines()
        # Drop a single trailing empty line (POSIX EOL convention) before counting.
        if lines and lines[-1] == "":
            lines = lines[:-1]
        self.assertLessEqual(
            len(lines), 15, f"SKILL.md is {len(lines)} lines (must be ≤ 15)"
        )

    def test_shim_has_error_halt_fallback(self) -> None:
        skill_md = (_BMAD_QUICK_DEV / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("non-zero", skill_md)
        self.assertIn("halt", skill_md.lower())

    def test_shim_no_project_root_token_in_body(self) -> None:
        text = (_BMAD_QUICK_DEV / "SKILL.md").read_text(encoding="utf-8")
        # Strip YAML front matter (between leading --- markers); description may legally use {var} tokens.
        body = text
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                body = text[end + 4:]
        self.assertNotIn("{project-root}", body)

    def test_shim_no_skill_root_token_in_body(self) -> None:
        text = (_BMAD_QUICK_DEV / "SKILL.md").read_text(encoding="utf-8")
        body = text
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                body = text[end + 4:]
        self.assertNotIn("{skill-root}", body)

    def test_template_file_exists_and_nonempty(self) -> None:
        template = _BMAD_QUICK_DEV / "bmad-quick-dev.template.md"
        self.assertTrue(template.is_file(), f"template not found at {template}")
        self.assertGreater(template.stat().st_size, 0, "template is empty")


# ---------------------------------------------------------------------------
# TestBatchMode (AC-2)
# ---------------------------------------------------------------------------

class TestBatchMode(unittest.TestCase):

    def test_single_skill_emits_skill_event_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "_bmad"
            install.mkdir()
            skill_dir = _make_skill(install, "mod1", "sk1")
            batch = _make_batch_file(tmp_path, [
                {"skill_dir": str(skill_dir), "install_dir": str(install)}
            ])

            code, events, _ = _run_batch(batch)
            self.assertEqual(code, 0)
            skill_events = [e for e in events if e["kind"] == "skill"]
            summary = next(e for e in events if e["kind"] == "summary")
            self.assertEqual(len(skill_events), 1)
            self.assertEqual(skill_events[0]["skill"], "mod1/sk1")
            self.assertEqual(skill_events[0]["status"], "ok")
            self.assertTrue(skill_events[0]["lockfile_updated"])
            self.assertTrue(skill_events[0]["compiled"])
            self.assertEqual(summary["compiled"], 1)
            self.assertEqual(summary["errors"], 0)
            self.assertIsNotNone(summary["lockfile_path"])

    def test_multiple_skills_emit_events_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "_bmad"
            install.mkdir()
            skill_a = _make_skill(install, "mod1", "skill-a", "A body")
            skill_b = _make_skill(install, "mod2", "skill-b", "B body")
            batch = _make_batch_file(tmp_path, [
                {"skill_dir": str(skill_a), "install_dir": str(install)},
                {"skill_dir": str(skill_b), "install_dir": str(install)},
            ])

            code, events, _ = _run_batch(batch)
            self.assertEqual(code, 0)
            skill_events = [e for e in events if e["kind"] == "skill"]
            self.assertEqual(len(skill_events), 2)
            self.assertEqual(skill_events[0]["skill"], "mod1/skill-a")
            self.assertEqual(skill_events[1]["skill"], "mod2/skill-b")
            summary = next(e for e in events if e["kind"] == "summary")
            self.assertEqual(summary["compiled"], 2)

    def test_error_skill_emits_error_event_and_continues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "_bmad"
            install.mkdir()
            broken = _make_skill(install, "mod", "broken", "{{undefined_var}}")
            ok = _make_skill(install, "mod", "ok-skill", "fine")
            batch = _make_batch_file(tmp_path, [
                {"skill_dir": str(broken), "install_dir": str(install)},
                {"skill_dir": str(ok), "install_dir": str(install)},
            ])

            code, events, _ = _run_batch(batch)
            self.assertEqual(code, 1)
            error_events = [e for e in events if e["kind"] == "error"]
            ok_events = [
                e for e in events
                if e["kind"] == "skill" and e.get("status") == "ok"
            ]
            self.assertEqual(len(error_events), 1)
            self.assertEqual(len(ok_events), 1)
            self.assertEqual(ok_events[0]["skill"], "mod/ok-skill")
            summary = next(e for e in events if e["kind"] == "summary")
            self.assertEqual(summary["errors"], 1)
            self.assertEqual(summary["compiled"], 1)

    def test_summary_compiled_count_matches_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "_bmad"
            install.mkdir()
            for i in range(3):
                _make_skill(install, "mod", f"sk{i}", f"body {i}")
            batch = _make_batch_file(tmp_path, [
                {
                    "skill_dir": str(install / "mod" / f"sk{i}"),
                    "install_dir": str(install),
                }
                for i in range(3)
            ])
            code, events, _ = _run_batch(batch)
            self.assertEqual(code, 0)
            compiled_true = sum(
                1 for e in events
                if e["kind"] == "skill" and e.get("compiled") is True
            )
            summary = next(e for e in events if e["kind"] == "summary")
            self.assertEqual(summary["compiled"], compiled_true)
            self.assertEqual(summary["compiled"], 3)

    def test_empty_array_emits_summary_zero_compiled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            batch = _make_batch_file(tmp_path, [])
            code, events, _ = _run_batch(batch)
            self.assertEqual(code, 0)
            kinds = [e["kind"] for e in events]
            self.assertNotIn("skill", kinds)
            self.assertNotIn("error", kinds)
            summary = next(e for e in events if e["kind"] == "summary")
            self.assertEqual(summary["compiled"], 0)
            self.assertEqual(summary["errors"], 0)
            self.assertIsNone(summary["lockfile_path"])

    def test_nonexistent_json_file_emits_ndjson_error_exits_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            missing = tmp_path / "missing.json"
            code, events, _ = _run_batch(missing)
            self.assertEqual(code, 1)
            error_events = [e for e in events if e["kind"] == "error"]
            self.assertEqual(len(error_events), 1)
            self.assertEqual(error_events[0]["code"], "BATCH_FILE_NOT_FOUND")
            # JS caller's parser handles either kind:"error" + non-zero exit
            # OR kind:"error" + summary; the contract is "at least one
            # NDJSON line so JSON.parse doesn't see empty stdout".
            self.assertGreaterEqual(len(events), 1)

    def test_malformed_json_emits_ndjson_error_exits_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            batch = tmp_path / "skills.json"
            batch.write_text("not valid json {{{", encoding="utf-8")
            code, events, _ = _run_batch(batch)
            self.assertEqual(code, 1)
            error_events = [e for e in events if e["kind"] == "error"]
            self.assertEqual(error_events[0]["code"], "BATCH_FILE_MALFORMED")

    def test_missing_skill_dir_key_exits_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "_bmad"
            install.mkdir()
            batch = _make_batch_file(tmp_path, [
                {"install_dir": str(install)}  # missing skill_dir
            ])
            code, events, stderr = _run_batch(batch)
            self.assertEqual(code, 1)
            self.assertIn("BATCH_ENTRY_INVALID", stderr + json.dumps(events))

    def test_relative_path_exits_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            batch = _make_batch_file(tmp_path, [
                {"skill_dir": "relative/path", "install_dir": "also/relative"}
            ])
            code, events, _ = _run_batch(batch)
            self.assertEqual(code, 1)
            error_events = [e for e in events if e["kind"] == "error"]
            self.assertEqual(error_events[0]["code"], "BATCH_ENTRY_INVALID")
            self.assertIn("absolute", error_events[0]["message"])

    def test_duplicate_entries_compile_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "_bmad"
            install.mkdir()
            skill_dir = _make_skill(install, "mod", "sk")
            entry = {"skill_dir": str(skill_dir), "install_dir": str(install)}
            batch = _make_batch_file(tmp_path, [entry, entry, entry])
            code, events, _ = _run_batch(batch)
            self.assertEqual(code, 0)
            skill_events = [
                e for e in events
                if e["kind"] == "skill" and e.get("compiled") is True
            ]
            warning_events = [e for e in events if e["kind"] == "warning"]
            self.assertEqual(len(skill_events), 1)
            self.assertGreaterEqual(len(warning_events), 2)
            self.assertTrue(any(
                "duplicate batch entry" in e.get("message", "")
                for e in warning_events
            ))

    def test_batch_rejects_diff_combination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            batch = _make_batch_file(tmp_path, [])
            result = subprocess.run(
                [
                    sys.executable, str(_COMPILE_PY),
                    "--batch", str(batch), "--diff",
                ],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("--batch cannot be combined with --diff", result.stderr)

    def test_batch_rejects_set_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            batch = _make_batch_file(tmp_path, [])
            result = subprocess.run(
                [
                    sys.executable, str(_COMPILE_PY),
                    "--batch", str(batch), "--set", "k=v",
                ],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("--set cannot be used with --batch", result.stderr)

    def test_batch_rejects_explain_combination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            batch = _make_batch_file(tmp_path, [])
            result = subprocess.run(
                [
                    sys.executable, str(_COMPILE_PY),
                    "--batch", str(batch), "--explain",
                ],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("--batch cannot be combined with --explain", result.stderr)

    def test_batch_rejects_tree_combination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            batch = _make_batch_file(tmp_path, [])
            result = subprocess.run(
                [
                    sys.executable, str(_COMPILE_PY),
                    "--batch", str(batch), "--tree",
                ],
                capture_output=True, text=True,
            )
            # The --batch+--tree guard at compile.py:644 fires before the
            # --tree-requires-explain guard at line 678. Pin the exact message
            # so a guard-order regression surfaces (R2 F1).
            self.assertEqual(result.returncode, 1)
            self.assertIn("--batch cannot be combined with --tree", result.stderr)

    def test_batch_rejects_json_combination(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            batch = _make_batch_file(tmp_path, [])
            result = subprocess.run(
                [
                    sys.executable, str(_COMPILE_PY),
                    "--batch", str(batch), "--json",
                ],
                capture_output=True, text=True,
            )
            # Same guard-order pin as test_batch_rejects_tree_combination (R2 F1).
            self.assertEqual(result.returncode, 1)
            self.assertIn("--batch cannot be combined with --json", result.stderr)


# ---------------------------------------------------------------------------
# TestHashSkip (AC-3)
# ---------------------------------------------------------------------------

class TestHashSkip(unittest.TestCase):

    def test_second_run_summary_compiled_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "_bmad"
            install.mkdir()
            skill_dir = _make_skill(install, "mod", "sk", "stable body")
            batch = _make_batch_file(tmp_path, [
                {"skill_dir": str(skill_dir), "install_dir": str(install)}
            ])

            code1, events1, _ = _run_batch(batch)
            self.assertEqual(code1, 0)
            self.assertEqual(
                next(e for e in events1 if e["kind"] == "summary")["compiled"],
                1,
            )

            code2, events2, _ = _run_batch(batch)
            self.assertEqual(code2, 0)
            summary2 = next(e for e in events2 if e["kind"] == "summary")
            self.assertEqual(summary2["compiled"], 0)
            skill2 = next(e for e in events2 if e["kind"] == "skill")
            self.assertFalse(skill2["compiled"])
            self.assertEqual(skill2["status"], "skipped")
            self.assertFalse(skill2["lockfile_updated"])
            self.assertEqual(skill2["written"], [])

    def test_second_run_skill_md_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "_bmad"
            install.mkdir()
            skill_dir = _make_skill(install, "mod", "sk", "stable body")
            batch = _make_batch_file(tmp_path, [
                {"skill_dir": str(skill_dir), "install_dir": str(install)}
            ])

            _run_batch(batch)
            skill_md = install / "mod" / "sk" / "SKILL.md"
            bytes_after_first = skill_md.read_bytes()

            _run_batch(batch)
            bytes_after_second = skill_md.read_bytes()
            self.assertEqual(bytes_after_first, bytes_after_second)

    def test_second_run_lockfile_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "_bmad"
            install.mkdir()
            skill_dir = _make_skill(install, "mod", "sk", "stable body")
            batch = _make_batch_file(tmp_path, [
                {"skill_dir": str(skill_dir), "install_dir": str(install)}
            ])

            _run_batch(batch)
            lockfile = install / "_config" / "bmad.lock"
            bytes_after_first = lockfile.read_bytes()

            _run_batch(batch)
            bytes_after_second = lockfile.read_bytes()
            # Hash-skip path doesn't write the lockfile (lockfile_updated=False),
            # so byte-identity is exact (unchanged file).
            self.assertEqual(bytes_after_first, bytes_after_second)


# ---------------------------------------------------------------------------
# TestBatchPerf — advisory perf targets
# ---------------------------------------------------------------------------

_PERF_GATE = os.environ.get("BMAD_RUN_PERF") == "1"


@unittest.skipUnless(_PERF_GATE, "perf tests gated by BMAD_RUN_PERF=1")
class TestBatchPerf(unittest.TestCase):
    """Advisory performance tests — run with BMAD_RUN_PERF=1 or `pytest -m perf`.

    Targets are advisory (not CI gates per AC-2/AC-3). Wide margins so transient
    CI noise does not flake the suite when these are explicitly invoked.
    """

    @pytest.mark.perf
    def test_batch_install_overhead_advisory(self) -> None:
        # Compare 5 sequential cold-starts vs one --batch with 5 skills.
        n = 5
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "_bmad"
            install.mkdir()
            skill_dirs = [
                _make_skill(install, "mod", f"perf-sk{i}", f"body {i}")
                for i in range(n)
            ]

            # Baseline: N cold-starts of `python3 -c "pass"`.
            t0 = time.perf_counter()
            for _ in range(n):
                subprocess.run(
                    [sys.executable, "-c", "pass"],
                    capture_output=True, check=True,
                )
            cold_baseline = time.perf_counter() - t0

            # Batch: single cold-start.
            batch = _make_batch_file(tmp_path, [
                {"skill_dir": str(d), "install_dir": str(install)}
                for d in skill_dirs
            ])
            t1 = time.perf_counter()
            code, events, _ = _run_batch(batch)
            batch_time = time.perf_counter() - t1
            self.assertEqual(code, 0)

            # Wide-margin advisory: batch should not be MORE than 10x the
            # baseline (target is ≤ 1.1x, but flake tolerance is generous).
            self.assertLess(
                batch_time, cold_baseline * 10,
                f"batch={batch_time:.3f}s vs {n}× cold-start baseline={cold_baseline:.3f}s",
            )

    @pytest.mark.perf
    def test_batch_reinstall_overhead_advisory(self) -> None:
        n = 5
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "_bmad"
            install.mkdir()
            skill_dirs = [
                _make_skill(install, "mod", f"perf-sk{i}", f"body {i}")
                for i in range(n)
            ]
            batch = _make_batch_file(tmp_path, [
                {"skill_dir": str(d), "install_dir": str(install)}
                for d in skill_dirs
            ])
            # Warm the lockfile.
            _run_batch(batch)

            # Re-install: hash-skip path; should be substantially faster than first run.
            t0 = time.perf_counter()
            code, events, _ = _run_batch(batch)
            reinstall_time = time.perf_counter() - t0
            self.assertEqual(code, 0)
            summary = next(e for e in events if e["kind"] == "summary")
            self.assertEqual(summary["compiled"], 0)
            # Wide-margin advisory: re-install should still complete (<10s on
            # any reasonable machine; this catches catastrophic regression).
            self.assertLess(reinstall_time, 10.0)


# ---------------------------------------------------------------------------
# TestRunBatchInstallDirValidation (AC-2 / L526)
# ---------------------------------------------------------------------------


class TestRunBatchInstallDirValidation(unittest.TestCase):
    """_run_batch rejects missing install_dir with BATCH_ENTRY_INVALID."""

    def test_missing_install_dir_emits_batch_entry_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "_bmad"
            install.mkdir()
            skill_dir = _make_skill(install, "mod", "sk")
            nonexistent_install = tmp_path / "no_such_dir"
            batch = _make_batch_file(tmp_path, [
                {"skill_dir": str(skill_dir), "install_dir": str(nonexistent_install)}
            ])

            code, events, _ = _run_batch(batch)
            self.assertEqual(code, 1)
            error_events = [e for e in events if e["kind"] == "error"]
            self.assertEqual(len(error_events), 1)
            self.assertEqual(error_events[0]["code"], "BATCH_ENTRY_INVALID")
            self.assertIn("does not exist or is not a directory", error_events[0]["message"])
            self.assertIn(str(nonexistent_install), error_events[0]["message"])

    def test_missing_install_dir_continues_to_next_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "_bmad"
            install.mkdir()
            skill_bad = _make_skill(install, "mod", "sk-bad")
            skill_ok = _make_skill(install, "mod", "sk-ok")
            nonexistent = tmp_path / "no_such_dir"
            batch = _make_batch_file(tmp_path, [
                {"skill_dir": str(skill_bad), "install_dir": str(nonexistent)},
                {"skill_dir": str(skill_ok), "install_dir": str(install)},
            ])

            code, events, _ = _run_batch(batch)
            # One error (bad install_dir) + one successful skill → exit 1
            self.assertEqual(code, 1)
            skill_events = [e for e in events if e["kind"] == "skill" and e.get("status") == "ok"]
            self.assertEqual(len(skill_events), 1, "second entry (valid install_dir) compiled ok")
            self.assertEqual(skill_events[0]["skill"], "mod/sk-ok")


# ---------------------------------------------------------------------------
# TestCompileOneSkillHashSkipDiagnostics (AC-3 / L528 + L530)
# ---------------------------------------------------------------------------


class TestCompileOneSkillHashSkipDiagnostics(unittest.TestCase):
    """_compile_one_skill warning on non-OSError hash-skip exception + root guard."""

    def test_oserror_in_hash_skip_silent_recompile(self) -> None:
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "_bmad"
            install.mkdir()
            skill_dir = _make_skill(install, "mod", "sk")

            with patch(
                "bmad_compile.lazy_compile._find_lockfile_entry",
                side_effect=OSError("simulated TOCTOU"),
            ):
                events = _compile_one_skill(skill_dir, install, hash_skip=True)

            # No warning emitted — OSError is silent recompile path
            warning_events = [e for e in events if e["kind"] == "warning"]
            self.assertFalse(
                any(e.get("code") == "HASH_SKIP_DIAGNOSTIC" for e in warning_events),
                "OSError must not emit HASH_SKIP_DIAGNOSTIC warning",
            )
            # Compile still runs (skill or error event present)
            outcome_events = [e for e in events if e["kind"] in ("skill", "error")]
            self.assertGreater(len(outcome_events), 0, "compile still ran after OSError")

    def test_programming_error_in_hash_skip_emits_warning(self) -> None:
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "_bmad"
            install.mkdir()
            skill_dir = _make_skill(install, "mod", "sk")

            with patch(
                "bmad_compile.lazy_compile._find_lockfile_entry",
                side_effect=KeyError("corrupt_key"),
            ):
                events = _compile_one_skill(skill_dir, install, hash_skip=True)

            warning_events = [e for e in events if e["kind"] == "warning"]
            diag = [e for e in warning_events if e.get("code") == "HASH_SKIP_DIAGNOSTIC"]
            self.assertEqual(len(diag), 1, "exactly one HASH_SKIP_DIAGNOSTIC warning emitted")
            self.assertIn("may be corrupt", diag[0]["message"])
            self.assertEqual(diag[0]["skill"], "mod/sk")
            # Compile still runs after warning
            outcome_events = [e for e in events if e["kind"] in ("skill", "error")]
            self.assertGreater(len(outcome_events), 0, "compile still ran after KeyError")

    def test_filesystem_root_skill_dir_emits_batch_entry_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "_bmad"
            install.mkdir()
            # Path("/skill_only").parent.name == "" on both POSIX and Windows
            root_child = Path("/skill_only")
            events = _compile_one_skill(root_child, install, hash_skip=False)
            error_events = [e for e in events if e["kind"] == "error"]
            self.assertEqual(len(error_events), 1)
            self.assertEqual(error_events[0]["code"], "BATCH_ENTRY_INVALID")
            self.assertIn("skill_dir has no parent module component", error_events[0]["message"])


# ---------------------------------------------------------------------------
# TestRunBatchUnknownKeyWarning (AC-4 / L532)
# ---------------------------------------------------------------------------


class TestRunBatchUnknownKeyWarning(unittest.TestCase):
    """_run_batch emits warning for unknown batch entry keys."""

    def test_known_keys_only_no_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "_bmad"
            install.mkdir()
            skill_dir = _make_skill(install, "mod", "sk")
            batch = _make_batch_file(tmp_path, [
                {"skill_dir": str(skill_dir), "install_dir": str(install)}
            ])

            code, events, _ = _run_batch(batch)
            self.assertEqual(code, 0)
            unknown_key_warnings = [
                e for e in events
                if e["kind"] == "warning" and "unknown key" in e.get("message", "")
            ]
            self.assertEqual(len(unknown_key_warnings), 0, "no unknown-key warnings for known keys")

    def test_unknown_key_emits_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            install = tmp_path / "_bmad"
            install.mkdir()
            skill_dir = _make_skill(install, "mod", "sk")
            batch = _make_batch_file(tmp_path, [
                {
                    "skill_dir": str(skill_dir),
                    "install_dir": str(install),
                    "target_ide": "cursor",
                }
            ])

            code, events, _ = _run_batch(batch)
            self.assertEqual(code, 0, "unknown key does not cause failure")
            unknown_key_warnings = [
                e for e in events
                if e["kind"] == "warning" and "unknown key" in e.get("message", "")
            ]
            self.assertEqual(len(unknown_key_warnings), 1)
            self.assertIn("target_ide", unknown_key_warnings[0]["message"])
            self.assertEqual(unknown_key_warnings[0].get("code"), "UNKNOWN_BATCH_KEY")
            # Skill still compiled despite unknown key
            skill_events = [e for e in events if e["kind"] == "skill" and e.get("status") == "ok"]
            self.assertEqual(len(skill_events), 1, "skill compiled successfully")


if __name__ == "__main__":
    unittest.main()
