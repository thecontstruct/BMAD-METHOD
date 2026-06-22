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

    def tearDown(self) -> None:
        # FIXTURES / "minimal" → scenario_root = FIXTURES.parent = test/fixtures/
        (FIXTURES.parent / "_bmad" / "_config" / ".bmad.lock.lock").unlink(missing_ok=True)

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

    def test_tools_flag_case_insensitive_cursor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = scenario / "core" / "skill1"
            skill.mkdir(parents=True)
            (skill / "skill1.cursor.template.md").write_text("cursor-body", encoding="utf-8")
            (skill / "skill1.template.md").write_text("universal-body", encoding="utf-8")
            (scenario / "_bmad" / "custom").mkdir(parents=True, exist_ok=True)
            install = scenario / "install"
            install.mkdir()
            result = subprocess.run(
                [sys.executable, str(COMPILE_SCRIPT),
                 "--skill", str(skill),
                 "--install-dir", str(install),
                 "--tools", "Cursor"],
                capture_output=True, text=True, cwd=str(REPO_ROOT),
            )
            self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
            out = install / "skill1" / "SKILL.md"
            self.assertEqual(out.read_text(encoding="utf-8"), "cursor-body")


class TestCompileFixtures(unittest.TestCase):
    """Story 1.2 parametrized scenarios — `<<include>>` pipeline end-to-end."""

    def tearDown(self) -> None:
        (COMPILE_FIXTURES / "include-chain" / "_bmad" / "_config" / ".bmad.lock.lock").unlink(missing_ok=True)

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


class TestVariableResolutionFixtures(unittest.TestCase):
    """Story 1.3 — compile-time variable interpolation end-to-end."""

    def tearDown(self) -> None:
        (COMPILE_FIXTURES / "variable-resolution" / "_bmad" / "_config" / ".bmad.lock.lock").unlink(missing_ok=True)
        (COMPILE_FIXTURES / "variable-resolution" / "_bmad" / "_config" / "bmad.lock").unlink(missing_ok=True)

    def _scenario_skill(self, scenario: str, skill_name: str) -> Path:
        return COMPILE_FIXTURES / scenario / "core" / skill_name

    def test_variable_resolution_compiles_correctly(self) -> None:
        skill = self._scenario_skill("variable-resolution", "var-resolution-skill")
        expected = (
            COMPILE_FIXTURES / "variable-resolution" / "expected" / "SKILL.md"
        ).read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli(skill, Path(tmp))
            self.assertEqual(
                result.returncode, 0, msg=f"stderr={result.stderr!r}"
            )
            out = Path(tmp) / "var-resolution-skill" / "SKILL.md"
            self.assertEqual(out.read_bytes(), expected)

    def test_runtime_var_passes_through(self) -> None:
        skill = self._scenario_skill("variable-resolution", "var-resolution-skill")
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli(skill, Path(tmp))
            self.assertEqual(
                result.returncode, 0, msg=f"stderr={result.stderr!r}"
            )
            out = Path(tmp) / "var-resolution-skill" / "SKILL.md"
            self.assertIn("{runtime_var}", out.read_text(encoding="utf-8"))

    def test_unresolved_variable_cli_exits_nonzero(self) -> None:
        skill = self._scenario_skill("variable-resolution-unresolved", "unresolved-skill")
        subs = [
            ln.strip()
            for ln in (
                COMPILE_FIXTURES / "variable-resolution-unresolved" / "expected" / "stderr.txt"
            ).read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli(skill, Path(tmp))
            self.assertNotEqual(result.returncode, 0)
            for sub in subs:
                self.assertIn(sub, result.stderr)
            self.assertEqual(list(Path(tmp).rglob("SKILL.md")), [])


VARIANT_FIXTURES = COMPILE_FIXTURES / "variant-selection"
VARIANT_SKILL = VARIANT_FIXTURES / "core" / "variant-skill"


def _run_cli_tools(skill: Path, install_dir: Path, tools: str | None = None) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        str(COMPILE_SCRIPT),
        "--skill", str(skill),
        "--install-dir", str(install_dir),
    ]
    if tools is not None:
        cmd += ["--tools", tools]
    return subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)


class TestVariantSelectionFixtures(unittest.TestCase):
    """Story 1.4 — IDE variant selection end-to-end (AC 1, 2, 3, 9)."""

    def tearDown(self) -> None:
        (COMPILE_FIXTURES / "variant-selection" / "_bmad" / "_config" / ".bmad.lock.lock").unlink(missing_ok=True)

    def _expected(self, name: str) -> bytes:
        return (VARIANT_FIXTURES / "expected" / name).read_bytes()

    def test_claudecode_variant_selected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli_tools(VARIANT_SKILL, Path(tmp), tools="claudecode")
            self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
            out = Path(tmp) / "variant-skill" / "SKILL.md"
            self.assertEqual(out.read_bytes(), self._expected("claudecode-SKILL.md"))

    def test_cursor_variant_selected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli_tools(VARIANT_SKILL, Path(tmp), tools="cursor")
            self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
            out = Path(tmp) / "variant-skill" / "SKILL.md"
            self.assertEqual(out.read_bytes(), self._expected("cursor-SKILL.md"))

    def test_no_tools_uses_universal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli_tools(VARIANT_SKILL, Path(tmp), tools=None)
            self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
            out = Path(tmp) / "variant-skill" / "SKILL.md"
            self.assertEqual(out.read_bytes(), self._expected("universal-SKILL.md"))

    def test_unknown_tools_falls_back_to_universal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli_tools(VARIANT_SKILL, Path(tmp), tools="vscode")
            self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
            out = Path(tmp) / "variant-skill" / "SKILL.md"
            self.assertEqual(out.read_bytes(), self._expected("universal-SKILL.md"))

    def test_missing_root_template_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_skill, tempfile.TemporaryDirectory() as tmp_out:
            # Skill dir with no *.template.md at all — just a scenario layout
            skill_dir = Path(tmp_skill) / "core" / "empty-skill"
            skill_dir.mkdir(parents=True)
            result = _run_cli_tools(skill_dir, Path(tmp_out))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("MISSING_FRAGMENT", result.stderr)
            self.assertEqual(list(Path(tmp_out).rglob("SKILL.md")), [])

    def test_uppercase_tools_normalized_to_lowercase(self) -> None:
        # AC 4: --tools Cursor must be equivalent to --tools cursor (CLI lowercases).
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli_tools(VARIANT_SKILL, Path(tmp), tools="Cursor")
            self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
            out = Path(tmp) / "variant-skill" / "SKILL.md"
            self.assertEqual(out.read_bytes(), self._expected("cursor-SKILL.md"))

    def test_empty_string_tools_falls_back_to_universal(self) -> None:
        # AC 4: --tools "" must be treated as None (no target IDE).
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli_tools(VARIANT_SKILL, Path(tmp), tools="")
            self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
            out = Path(tmp) / "variant-skill" / "SKILL.md"
            self.assertEqual(out.read_bytes(), self._expected("universal-SKILL.md"))

    def test_sub_agent_activation_variants_distinct(self) -> None:
        # AC-14 (Story 10.61): universal, claudecode, and cursor expected outputs are
        # all byte-distinct (the sub-agent-activation fragment has truly different text).
        universal = self._expected("universal-SKILL.md")
        claudecode = self._expected("claudecode-SKILL.md")
        cursor = self._expected("cursor-SKILL.md")
        self.assertNotEqual(universal, claudecode, "universal and claudecode SKILL.md must differ")
        self.assertNotEqual(universal, cursor, "universal and cursor SKILL.md must differ")
        self.assertNotEqual(claudecode, cursor, "claudecode and cursor SKILL.md must differ")


class TestCliErrorBoundary(unittest.TestCase):
    """Story 1.4 AC 6 — CLI catches raw OS / encoding exceptions."""

    def test_cli_handles_unicode_decode_error_on_invalid_utf8(self) -> None:
        # AC 6: invalid UTF-8 in a template surfaces as `read error:` (no traceback, exit 1).
        with tempfile.TemporaryDirectory() as tmp_skill, tempfile.TemporaryDirectory() as tmp_out:
            skill_dir = Path(tmp_skill) / "core" / "bad-utf8"
            skill_dir.mkdir(parents=True)
            (skill_dir / "bad-utf8.template.md").write_bytes(b"\xff\xfe invalid utf-8 \x80\x81")
            result = _run_cli(skill_dir, Path(tmp_out))
            self.assertEqual(result.returncode, 1, msg=f"stderr={result.stderr!r}")
            self.assertIn("read error:", result.stderr)
            self.assertIn("UnicodeDecodeError", result.stderr)
            self.assertNotIn("Traceback", result.stderr)
            self.assertEqual(list(Path(tmp_out).rglob("SKILL.md")), [])


class TestLockfileIntegration(unittest.TestCase):
    """Story 1.5 — lockfile written during successful compile; not on error."""

    def setUp(self) -> None:
        self._lockfile = (
            COMPILE_FIXTURES
            / "variable-resolution"
            / "_bmad"
            / "_config"
            / "bmad.lock"
        )
        # Defensive: remove any stale lockfile from a killed prior run so
        # test_lockfile_not_written_on_compile_error cannot false-fail.
        self._lockfile.unlink(missing_ok=True)
        (COMPILE_FIXTURES / "variable-resolution" / "_bmad" / "_config" / ".bmad.lock.lock").unlink(missing_ok=True)

    def tearDown(self) -> None:
        self._lockfile.unlink(missing_ok=True)
        (COMPILE_FIXTURES / "variable-resolution" / "_bmad" / "_config" / ".bmad.lock.lock").unlink(missing_ok=True)

    def _var_res_skill(self) -> Path:
        return COMPILE_FIXTURES / "variable-resolution" / "core" / "var-resolution-skill"

    def test_lockfile_written_on_compile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli(self._var_res_skill(), Path(tmp))
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
        self.assertTrue(self._lockfile.is_file(), "bmad.lock must exist after compile")
        import json
        data = json.loads(self._lockfile.read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 4)  # Story 10.58: bumped to v4

    def test_lockfile_secret_not_plaintext(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli(self._var_res_skill(), Path(tmp))
        self.assertEqual(result.returncode, 0)
        text = self._lockfile.read_text(encoding="utf-8")
        self.assertNotIn("World", text)
        self.assertNotIn('"value":', text)

    def test_lockfile_deterministic(self) -> None:
        # AC 7: two successive compiles produce byte-identical bmad.lock —
        # exercise the natural upsert path (no unlink between runs).
        with tempfile.TemporaryDirectory() as tmp:
            _run_cli(self._var_res_skill(), Path(tmp))
            bytes1 = self._lockfile.read_bytes()
            _run_cli(self._var_res_skill(), Path(tmp))
            bytes2 = self._lockfile.read_bytes()
        self.assertEqual(bytes1, bytes2)

    def test_lockfile_not_written_on_compile_error(self) -> None:
        skill = COMPILE_FIXTURES / "variable-resolution-unresolved" / "core" / "unresolved-skill"
        unresolved_lf = (
            COMPILE_FIXTURES / "variable-resolution-unresolved" / "_bmad" / "_config" / "bmad.lock"
        )
        unresolved_lf.unlink(missing_ok=True)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                result = _run_cli(skill, Path(tmp))
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(unresolved_lf.exists(), "bmad.lock must not be written on compile error")
        finally:
            unresolved_lf.unlink(missing_ok=True)

    def test_lockfile_version_mismatch_warns_and_proceeds(self) -> None:
        import json
        self._lockfile.parent.mkdir(parents=True, exist_ok=True)
        self._lockfile.write_text(
            json.dumps({"version": 3, "compiled_at": "1.0.0",
                        "bmad_version": "1.0.0", "entries": []}),
            encoding="utf-8",
        )
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli(self._var_res_skill(), Path(tmp))
        self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")


STEP_TEMPLATE_FIXTURES = COMPILE_FIXTURES / "step-template-resolution"
STEP_TEMPLATE_SKILL = STEP_TEMPLATE_FIXTURES / "core" / "step-template-skill"
_ST_LOCK_FILE = STEP_TEMPLATE_FIXTURES / "_bmad" / "_config" / "bmad.lock"
_ST_LOCK_LOCK = STEP_TEMPLATE_FIXTURES / "_bmad" / "_config" / ".bmad.lock.lock"


class TestStepTemplateFixtures(unittest.TestCase):
    """Story 10.63 AC-2 through AC-19: step-template engine extension end-to-end."""

    def tearDown(self) -> None:
        _ST_LOCK_LOCK.unlink(missing_ok=True)

    def _expected(self, name: str) -> bytes:
        return (STEP_TEMPLATE_FIXTURES / "expected" / name).read_bytes()

    def _out(self, tmp: str, name: str) -> Path:
        return Path(tmp) / "step-template-skill" / name

    # AC-2: step-template resolved through full pipeline (no component)
    def test_step_template_resolves_includes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli_tools(STEP_TEMPLATE_SKILL, Path(tmp))
            self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
            step3 = self._out(tmp, "step-03.md")
            self.assertTrue(step3.is_file(), f"expected {step3} to exist")
            self.assertEqual(step3.read_bytes(), self._expected("universal-step-03.md"))

    # AC-3: source-side variant resolution (step-02 universal / cursor / claudecode)
    def test_step_template_variant_selected_by_target_ide(self) -> None:
        cases = [
            (None,          "universal-step-02.md"),
            ("cursor",      "cursor-step-02.md"),
            ("claudecode",  "claudecode-step-02.md"),
            ("vscode",      "universal-step-02.md"),  # unknown IDE → universal
        ]
        for tools, expected_file in cases:
            with self.subTest(tools=tools), tempfile.TemporaryDirectory() as tmp:
                result = _run_cli_tools(STEP_TEMPLATE_SKILL, Path(tmp), tools=tools)
                self.assertEqual(result.returncode, 0,
                                 msg=f"tools={tools!r} stderr={result.stderr!r}")
                step2 = self._out(tmp, "step-02.md")
                self.assertEqual(step2.read_bytes(), self._expected(expected_file),
                                 msg=f"tools={tools!r} step-02.md mismatch")

    # AC-4: include-side variant resolution (step-03 fragment note universal / cursor / claudecode)
    def test_step_template_include_variant_resolves_per_target_ide(self) -> None:
        cases = [
            (None,         "universal-step-03.md"),
            ("cursor",     "cursor-step-03.md"),
            ("claudecode", "claudecode-step-03.md"),
        ]
        for tools, expected_file in cases:
            with self.subTest(tools=tools), tempfile.TemporaryDirectory() as tmp:
                result = _run_cli_tools(STEP_TEMPLATE_SKILL, Path(tmp), tools=tools)
                self.assertEqual(result.returncode, 0,
                                 msg=f"tools={tools!r} stderr={result.stderr!r}")
                step3 = self._out(tmp, "step-03.md")
                self.assertEqual(step3.read_bytes(), self._expected(expected_file),
                                 msg=f"tools={tools!r} step-03.md mismatch")

    # AC-5: undeclared step file not engine-emitted
    def test_undeclared_step_file_not_engine_emitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli_tools(STEP_TEMPLATE_SKILL, Path(tmp))
            self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
            # step-99-legacy.md is NOT declared — engine must not emit it
            legacy = self._out(tmp, "step-99-legacy.md")
            self.assertFalse(legacy.exists(),
                             f"step-99-legacy.md should not be engine-emitted but found at {legacy}")

    # AC-13: STEP_TEMPLATE_NO_VARIANT errors report helpful messages
    def test_step_template_variant_probe_miss_reports_helpful_error(self) -> None:
        # Case 1: no .template.md at all for declared source
        with tempfile.TemporaryDirectory() as tmp_skill, tempfile.TemporaryDirectory() as tmp_out:
            skill_dir = Path(tmp_skill) / "core" / "probe-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "probe-skill.template.md").write_text(
                "---\nname: probe-skill\nartifacts:\n"
                "  - kind: step-template\n    source: missing.template.md\n    path: out.md\n---\n# Skill\n",
                encoding="utf-8",
            )
            result = _run_cli(skill_dir, Path(tmp_out))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("STEP_TEMPLATE_NO_VARIANT", result.stderr)
            self.assertIn("missing.template.md", result.stderr)

        # Case 2: only IDE-specific variants exist, no universal, no --tools
        with tempfile.TemporaryDirectory() as tmp_skill, tempfile.TemporaryDirectory() as tmp_out:
            skill_dir = Path(tmp_skill) / "core" / "probe-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "probe-skill.template.md").write_text(
                "---\nname: probe-skill\nartifacts:\n"
                "  - kind: step-template\n    source: step.template.md\n    path: out.md\n---\n# Skill\n",
                encoding="utf-8",
            )
            (skill_dir / "step.cursor.template.md").write_text("# Cursor\n", encoding="utf-8")
            (skill_dir / "step.claudecode.template.md").write_text("# Claude\n", encoding="utf-8")
            result = _run_cli(skill_dir, Path(tmp_out))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("STEP_TEMPLATE_NO_VARIANT", result.stderr)
            # Should mention found variants
            self.assertIn("cursor", result.stderr.lower())
            self.assertIn("claudecode", result.stderr.lower())

    # AC-14: path traversal in artifact.path rejected before any write
    def test_step_template_path_traversal_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_skill, tempfile.TemporaryDirectory() as tmp_out:
            skill_dir = Path(tmp_skill) / "core" / "escape-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "escape-skill.template.md").write_text(
                "---\nname: escape-skill\nartifacts:\n"
                "  - kind: step-template\n    source: step.template.md\n    path: ../escape.md\n---\n# Skill\n",
                encoding="utf-8",
            )
            (skill_dir / "step.template.md").write_text("# Step\n", encoding="utf-8")
            result = _run_cli(skill_dir, Path(tmp_out))
            self.assertNotEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
            # No files written to install dir
            self.assertEqual(list(Path(tmp_out).rglob("*.md")), [])

    # AC-15: component invocation inside step-template body works
    def test_component_invocation_in_step_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli_tools(STEP_TEMPLATE_SKILL, Path(tmp))
            self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
            step4 = self._out(tmp, "step-04.md")
            self.assertTrue(step4.is_file(), f"expected {step4}")
            self.assertEqual(step4.read_bytes(), self._expected("universal-step-04.md"))

    # AC-16: FR-1.7 enforced on fragments included by step-templates
    def test_fr_1_7_enforced_on_step_template_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_skill, tempfile.TemporaryDirectory() as tmp_out:
            skill_dir = Path(tmp_skill) / "core" / "bad-frag-skill"
            skill_dir.mkdir(parents=True)
            frags = skill_dir / "fragments"
            frags.mkdir()
            (skill_dir / "bad-frag-skill.template.md").write_text(
                "---\nname: bad-frag-skill\nartifacts:\n"
                "  - kind: step-template\n    source: step.template.md\n    path: step.md\n---\n# Skill\n",
                encoding="utf-8",
            )
            (skill_dir / "step.template.md").write_text(
                '# Step\n<<include path="fragments/bad.md">>\n',
                encoding="utf-8",
            )
            # Fragment contains a component tag — violates FR-1.7
            (frags / "bad.md").write_text(
                "# Fragment\n<DateBanner />\n",
                encoding="utf-8",
            )
            result = _run_cli(skill_dir, Path(tmp_out))
            self.assertNotEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
            self.assertIn("Component tags are prohibited in fragment files", result.stderr)

    # AC-17: variant + component composition
    def test_step_template_variant_plus_component_composes(self) -> None:
        cases = [
            (None,         "universal-step-05.md"),
            ("cursor",     "cursor-step-05.md"),
            ("claudecode", "claudecode-step-05.md"),
        ]
        for tools, expected_file in cases:
            with self.subTest(tools=tools), tempfile.TemporaryDirectory() as tmp:
                result = _run_cli_tools(STEP_TEMPLATE_SKILL, Path(tmp), tools=tools)
                self.assertEqual(result.returncode, 0,
                                 msg=f"tools={tools!r} stderr={result.stderr!r}")
                step5 = self._out(tmp, "step-05.md")
                self.assertEqual(step5.read_bytes(), self._expected(expected_file),
                                 msg=f"tools={tools!r} step-05.md mismatch")

    # AC-18: component failure in step-template aborts whole skill (atomic FR-6.1)
    def test_step_template_component_failure_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_skill, tempfile.TemporaryDirectory() as tmp_out:
            skill_dir = Path(tmp_skill) / "core" / "fail-skill"
            skill_dir.mkdir(parents=True)
            comps = skill_dir / "components"
            comps.mkdir()
            (skill_dir / "fail-skill.template.md").write_text(
                "---\nname: fail-skill\nartifacts:\n"
                "  - kind: step-template\n    source: step.template.md\n    path: step.md\n---\n# Skill\n",
                encoding="utf-8",
            )
            (skill_dir / "step.template.md").write_text(
                "# Step\n<FailingComponent />\n",
                encoding="utf-8",
            )
            (comps / "failing_component.py").write_text(
                'RENDER_MODE = "compile"\n\ndef render(ctx, **props):\n    raise RuntimeError("boom")\n',
                encoding="utf-8",
            )
            result = _run_cli(skill_dir, Path(tmp_out))
            self.assertNotEqual(result.returncode, 0, msg="expected nonzero exit on component error")
            # No files written — atomicity preserved
            all_out = list(Path(tmp_out).rglob("*"))
            self.assertEqual(
                [f for f in all_out if f.is_file()], [],
                msg=f"Expected no files written on component error, found: {all_out}",
            )

    # AC-19: lockfile component records carry parent attribution
    def test_lockfile_component_records_have_parent(self) -> None:
        import json
        with tempfile.TemporaryDirectory() as tmp:
            result = _run_cli_tools(STEP_TEMPLATE_SKILL, Path(tmp))
            self.assertEqual(result.returncode, 0, msg=f"stderr={result.stderr!r}")
        # Lockfile is written to STEP_TEMPLATE_FIXTURES/_bmad/_config/bmad.lock
        lf_data = json.loads(_ST_LOCK_FILE.read_text(encoding="utf-8"))
        entry = next(
            (e for e in lf_data["entries"] if e["skill"] == "step-template-skill"),
            None,
        )
        self.assertIsNotNone(entry, "step-template-skill entry not found in lockfile")
        parents = {c.get("parent") for c in entry.get("components", [])}
        self.assertIn("SKILL.md", parents,
                      f"expected parent='SKILL.md' in components, got parents={parents}")
        self.assertIn("step-04.md", parents,
                      f"expected parent='step-04.md' in components, got parents={parents}")


if __name__ == "__main__":
    unittest.main()
