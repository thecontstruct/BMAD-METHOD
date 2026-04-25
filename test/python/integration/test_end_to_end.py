"""End-to-end integration tests — invoke compile.py via subprocess.

The process boundary is part of what's being tested: argparse behaviour,
exit codes, stderr formatting, and that the shim stays ≤50 lines of real
Python. We deliberately do NOT import `engine` directly here.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPILE_SCRIPT = REPO_ROOT / "src" / "scripts" / "compile.py"
FIXTURES = REPO_ROOT / "test" / "fixtures" / "bootstrap"
COMPILE_FIXTURES = REPO_ROOT / "test" / "fixtures" / "compile"


def _run_cli(skill: Path, install_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(COMPILE_SCRIPT),
            "--skill",
            str(skill),
            "--install-dir",
            str(install_dir),
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )


class TestMinimalFixture(unittest.TestCase):
    """AC 8: byte-identical passthrough + idempotent re-run."""

    def test_exit_zero_and_skill_md_matches_expected(self) -> None:
        fixture = FIXTURES / "minimal"
        expected_bytes = (fixture / "expected.md").read_bytes()

        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli(fixture, Path(tmp))
            self.assertEqual(
                result.returncode,
                0,
                msg=f"stdout={result.stdout!r}\nstderr={result.stderr!r}",
            )

            out = Path(tmp) / "minimal" / "SKILL.md"
            self.assertTrue(out.is_file(), f"expected {out} to exist")
            self.assertEqual(
                out.read_bytes(),
                expected_bytes,
                msg="compiled SKILL.md bytes must equal expected.md bytes",
            )

    def test_idempotent_second_run(self) -> None:
        fixture = FIXTURES / "minimal"
        expected_bytes = (fixture / "expected.md").read_bytes()

        with tempfile.TemporaryDirectory() as tmp:
            first = _run_cli(fixture, Path(tmp))
            second = _run_cli(fixture, Path(tmp))
            self.assertEqual(first.returncode, 0)
            self.assertEqual(second.returncode, 0)

            out = Path(tmp) / "minimal" / "SKILL.md"
            self.assertEqual(out.read_bytes(), expected_bytes)

            # No stale artifacts: only the one SKILL.md under the basename dir.
            produced = sorted(p.name for p in (Path(tmp) / "minimal").iterdir())
            self.assertEqual(produced, ["SKILL.md"])


class TestUnknownDirectiveFixture(unittest.TestCase):
    """AC 7 + AC 10: stderr carries UNKNOWN_DIRECTIVE; no output file written."""

    def test_nonzero_exit_and_formatted_error_on_stderr(self) -> None:
        fixture = FIXTURES / "unknown-directive"

        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli(fixture, Path(tmp))

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("UNKNOWN_DIRECTIVE", result.stderr)
            # Error contract: <CODE>: <path>:<line>:<col>:
            self.assertIn("input.template.md:2:1:", result.stderr)
            # hint present
            self.assertIn("hint:", result.stderr)

    def test_no_partial_write_on_error(self) -> None:
        """AC 10: zero bytes written under install-dir on compile failure."""
        fixture = FIXTURES / "unknown-directive"

        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli(fixture, Path(tmp))
            self.assertNotEqual(result.returncode, 0)

            # No SKILL.md anywhere under tmp.
            any_skill_md = list(Path(tmp).rglob("SKILL.md"))
            self.assertEqual(any_skill_md, [])

            # No stray temp files either (atomic-write cleanup).
            stray = [p for p in Path(tmp).rglob("*") if p.is_file()]
            self.assertEqual(stray, [], msg=f"unexpected files: {stray}")


class TestCliArgumentValidation(unittest.TestCase):
    """AC 9: argparse rejects missing required flags."""

    def test_missing_install_dir_exits_nonzero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(COMPILE_SCRIPT), "--skill", str(FIXTURES / "minimal")],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_missing_skill_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(COMPILE_SCRIPT), "--install-dir", tmp],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)


class TestCompileFixtures(unittest.TestCase):
    """Story 1.2 parametrized scenarios — `<<include>>` pipeline end-to-end."""

    def _scenario_skill(self, scenario: str) -> Path:
        return (
            COMPILE_FIXTURES / scenario / "core" / f"{scenario}-skill"
        )

    def _expected_substrings(self, stderr_txt: Path) -> list[str]:
        # Each non-empty line in expected/stderr.txt is a required substring.
        return [
            ln.strip()
            for ln in stderr_txt.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]

    def test_include_chain_inlines_bytes_identical(self) -> None:
        scenario = "include-chain"
        skill = self._scenario_skill(scenario)
        expected = (
            COMPILE_FIXTURES / scenario / "expected" / "SKILL.md"
        ).read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli(skill, Path(tmp))
            self.assertEqual(
                result.returncode, 0, msg=f"stderr={result.stderr!r}"
            )
            out = Path(tmp) / f"{scenario}-skill" / "SKILL.md"
            self.assertEqual(out.read_bytes(), expected)

    def test_cyclic_include_error_and_no_partial_write(self) -> None:
        scenario = "cyclic-include"
        skill = self._scenario_skill(scenario)
        subs = self._expected_substrings(
            COMPILE_FIXTURES / scenario / "expected" / "stderr.txt"
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli(skill, Path(tmp))
            self.assertNotEqual(result.returncode, 0)
            for sub in subs:
                self.assertIn(sub, result.stderr)
            # AC 10: no SKILL.md on compile failure.
            self.assertEqual(list(Path(tmp).rglob("SKILL.md")), [])

    def test_missing_fragment_error_and_no_partial_write(self) -> None:
        scenario = "missing-fragment"
        skill = self._scenario_skill(scenario)
        subs = self._expected_substrings(
            COMPILE_FIXTURES / scenario / "expected" / "stderr.txt"
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli(skill, Path(tmp))
            self.assertNotEqual(result.returncode, 0)
            for sub in subs:
                self.assertIn(sub, result.stderr)
            self.assertEqual(list(Path(tmp).rglob("SKILL.md")), [])

    def test_precedence_cascade_collapse_down_the_ladder(self) -> None:
        scenario = "precedence-all-tiers"
        src_fixture = COMPILE_FIXTURES / scenario
        expected_full_skill = (
            src_fixture / "expected" / "SKILL.md"
        ).read_bytes()

        # Full cascade — user-full-skill wins.
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / scenario
            shutil.copytree(src_fixture, work)
            skill = work / "core" / f"{scenario}-skill"
            with tempfile.TemporaryDirectory() as out_tmp:
                result = _run_cli(skill, Path(out_tmp))
                self.assertEqual(
                    result.returncode, 0, msg=f"stderr={result.stderr!r}"
                )
                out = Path(out_tmp) / f"{scenario}-skill" / "SKILL.md"
                self.assertEqual(out.read_bytes(), expected_full_skill)

            # Strip user-full-skill — user-module-fragment now wins the
            # inner include; the root template returns to the base shape.
            (
                work
                / "_bmad"
                / "custom"
                / "fragments"
                / "core"
                / f"{scenario}-skill"
                / "SKILL.template.md"
            ).unlink()
            with tempfile.TemporaryDirectory() as out_tmp:
                result = _run_cli(skill, Path(out_tmp))
                self.assertEqual(result.returncode, 0)
                body = (
                    Path(out_tmp) / f"{scenario}-skill" / "SKILL.md"
                ).read_text(encoding="utf-8")
                self.assertIn("USER-MODULE-FRAGMENT BODY", body)
                self.assertIn("root_pre", body)

            # Strip user-module-fragment — user-override now wins.
            (
                work
                / "_bmad"
                / "custom"
                / "fragments"
                / "core"
                / f"{scenario}-skill"
                / "menu.template.md"
            ).unlink()
            with tempfile.TemporaryDirectory() as out_tmp:
                result = _run_cli(skill, Path(out_tmp))
                self.assertEqual(result.returncode, 0)
                body = (
                    Path(out_tmp) / f"{scenario}-skill" / "SKILL.md"
                ).read_text(encoding="utf-8")
                self.assertIn("USER-OVERRIDE BODY", body)

            # Strip user-override — base wins.
            (
                work / "_bmad" / "custom" / "fragments" / "menu.template.md"
            ).unlink()
            with tempfile.TemporaryDirectory() as out_tmp:
                result = _run_cli(skill, Path(out_tmp))
                self.assertEqual(result.returncode, 0)
                body = (
                    Path(out_tmp) / f"{scenario}-skill" / "SKILL.md"
                ).read_text(encoding="utf-8")
                self.assertIn("BASE BODY", body)


if __name__ == "__main__":
    unittest.main()
