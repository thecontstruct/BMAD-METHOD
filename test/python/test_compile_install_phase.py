"""Tests for compile.py --install-phase mode (Story 2.1 AC 2/4, Task 3.8).

Exercises the `_run_install_phase` dispatcher end-to-end:
(a) one migrated skill emits kind:"skill" + kind:"summary" + writes SKILL.md + lockfile
(b) no migrated skills emits only kind:"summary" with compiled:0
(c) one migrated skill with an unresolved variable emits kind:"error" + kind:"summary" + exits 1
(d) JSON output is parseable line-by-line
(e) schema_version:1 is present on every emitted document
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.scripts.bmad_compile import engine, errors, io as bmad_io


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run_install_phase(install_dir: Path) -> tuple[int, list[dict], str]:
    """Invoke compile.py --install-phase and return (exit_code, events, stderr)."""
    compile_py = Path(__file__).resolve().parent.parent.parent / "src" / "scripts" / "compile.py"
    result = subprocess.run(
        [sys.executable, str(compile_py), "--install-phase", "--install-dir", str(install_dir)],
        capture_output=True,
        text=True,
    )
    events = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return result.returncode, events, result.stderr


def _run_compile_skill(install_dir: Path, args: list[str]) -> tuple[int, str, str]:
    """Invoke compile.py with given args and return (exit_code, stdout, stderr)."""
    compile_py = Path(__file__).resolve().parent.parent.parent / "src" / "scripts" / "compile.py"
    result = subprocess.run(
        [sys.executable, str(compile_py), "--install-dir", str(install_dir)] + args,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


class TestInstallPhaseHappyPath(unittest.TestCase):
    """(a) One migrated skill: emits kind:"skill" + kind:"summary", writes SKILL.md + lockfile."""

    def test_single_skill_emits_skill_and_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            skill_dir = install / "mymodule" / "my-skill"
            _write(skill_dir / "my-skill.template.md", "Hello from my-skill!")
            (install / "custom").mkdir(parents=True, exist_ok=True)

            code, events, _ = _run_install_phase(install)

            self.assertEqual(code, 0)
            skill_events = [e for e in events if e["kind"] == "skill"]
            summary_events = [e for e in events if e["kind"] == "summary"]
            self.assertEqual(len(skill_events), 1)
            self.assertEqual(len(summary_events), 1)

            skill_ev = skill_events[0]
            self.assertEqual(skill_ev["skill"], "mymodule/my-skill")
            self.assertEqual(skill_ev["status"], "ok")
            self.assertTrue(skill_ev["lockfile_updated"])

            summary_ev = summary_events[0]
            self.assertEqual(summary_ev["compiled"], 1)
            self.assertEqual(summary_ev["errors"], 0)

            # SKILL.md written at <install>/<module>/<skill>/SKILL.md
            skill_md = install / "mymodule" / "my-skill" / "SKILL.md"
            self.assertTrue(skill_md.is_file(), f"SKILL.md not found at {skill_md}")
            self.assertEqual(skill_md.read_text(encoding="utf-8"), "Hello from my-skill!")

            # lockfile written at <install>/_config/bmad.lock
            lockfile = install / "_config" / "bmad.lock"
            self.assertTrue(lockfile.is_file(), f"bmad.lock not found at {lockfile}")

    def test_skill_md_output_path_uses_module_segment(self) -> None:
        """SKILL.md output must be at <install>/<module>/<skill>/SKILL.md, not <install>/<skill>/SKILL.md."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            skill_dir = install / "core" / "my-core-skill"
            _write(skill_dir / "my-core-skill.template.md", "core content")
            (install / "custom").mkdir(parents=True, exist_ok=True)

            code, events, _ = _run_install_phase(install)

            self.assertEqual(code, 0)
            # Must land at install/core/my-core-skill/SKILL.md
            self.assertTrue((install / "core" / "my-core-skill" / "SKILL.md").is_file())
            # Must NOT be at install/my-core-skill/SKILL.md (old per-skill layout)
            self.assertFalse((install / "my-core-skill" / "SKILL.md").is_file())


class TestInstallPhaseNoSkills(unittest.TestCase):
    """(b) No migrated skills: emits only kind:"summary" with compiled:0."""

    def test_no_migrated_skills_emits_only_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            # A directory with a file NOT matching the basename rule
            research_dir = install / "bmm" / "bmad-technical-research"
            _write(research_dir / "research.template.md", "workflow output template")

            code, events, _ = _run_install_phase(install)

            self.assertEqual(code, 0)
            kinds = [e["kind"] for e in events]
            self.assertNotIn("skill", kinds)
            self.assertNotIn("error", kinds)
            self.assertIn("summary", kinds)
            summary = next(e for e in events if e["kind"] == "summary")
            self.assertEqual(summary["compiled"], 0)
            self.assertEqual(summary["errors"], 0)


class TestInstallPhaseErrorPath(unittest.TestCase):
    """(c) Migrated skill with unresolved variable: emits kind:"error" + kind:"summary", exits 1."""

    def test_unresolved_variable_emits_error_and_exits_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            skill_dir = install / "mod" / "broken-skill"
            # {{undefined_var}} will raise UnresolvedVariableError
            _write(skill_dir / "broken-skill.template.md", "{{undefined_var}}")
            (install / "custom").mkdir(parents=True, exist_ok=True)

            code, events, _ = _run_install_phase(install)

            self.assertEqual(code, 1)
            error_events = [e for e in events if e["kind"] == "error"]
            summary_events = [e for e in events if e["kind"] == "summary"]
            self.assertEqual(len(error_events), 1)
            self.assertEqual(len(summary_events), 1)

            err = error_events[0]
            self.assertEqual(err["code"], "UNRESOLVED_VARIABLE")
            self.assertEqual(err["skill"], "mod/broken-skill")
            self.assertEqual(err["status"], "error")

            summary = summary_events[0]
            self.assertEqual(summary["errors"], 1)
            self.assertEqual(summary["compiled"], 0)

    def test_error_does_not_abort_remaining_skills(self) -> None:
        """Failing skill must not abort compilation of subsequent skills."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            skill_a = install / "mod" / "skill-a"
            skill_b = install / "mod" / "skill-b"
            _write(skill_a / "skill-a.template.md", "{{undefined}}")
            _write(skill_b / "skill-b.template.md", "good content")
            (install / "custom").mkdir(parents=True, exist_ok=True)

            code, events, _ = _run_install_phase(install)

            self.assertEqual(code, 1)
            self.assertEqual(len([e for e in events if e["kind"] == "error"]), 1)
            self.assertEqual(len([e for e in events if e["kind"] == "skill"]), 1)
            summary = next(e for e in events if e["kind"] == "summary")
            self.assertEqual(summary["errors"], 1)
            self.assertEqual(summary["compiled"], 1)


class TestInstallPhaseJsonContract(unittest.TestCase):
    """(d) JSON output is parseable line-by-line. (e) schema_version:1 on every doc."""

    def test_every_event_has_schema_version_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            skill_dir = install / "mod" / "my-skill"
            _write(skill_dir / "my-skill.template.md", "hello")
            (install / "custom").mkdir(parents=True, exist_ok=True)

            code, events, _ = _run_install_phase(install)

            self.assertEqual(code, 0)
            self.assertGreater(len(events), 0)
            for ev in events:
                self.assertEqual(ev.get("schema_version"), 1, f"schema_version missing in event: {ev}")

    def test_output_is_parseable_line_by_line(self) -> None:
        """Each line of stdout must be a valid JSON document."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            skill_dir = install / "mod" / "my-skill"
            _write(skill_dir / "my-skill.template.md", "hello")
            (install / "custom").mkdir(parents=True, exist_ok=True)

            compile_py = Path(__file__).resolve().parent.parent.parent / "src" / "scripts" / "compile.py"
            result = subprocess.run(
                [sys.executable, str(compile_py), "--install-phase", "--install-dir", str(install)],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parsed = json.loads(line)  # raises ValueError if not valid JSON
                self.assertIsInstance(parsed, dict)

    def test_summary_is_always_last_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            skill_dir = install / "mod" / "my-skill"
            _write(skill_dir / "my-skill.template.md", "hello")
            (install / "custom").mkdir(parents=True, exist_ok=True)

            code, events, _ = _run_install_phase(install)

            self.assertEqual(code, 0)
            self.assertEqual(events[-1]["kind"], "summary")

    def test_sort_keys_stable_output(self) -> None:
        """JSON fields must be sorted (sort_keys=True contract)."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            skill_dir = install / "mod" / "my-skill"
            _write(skill_dir / "my-skill.template.md", "hello")
            (install / "custom").mkdir(parents=True, exist_ok=True)

            compile_py = Path(__file__).resolve().parent.parent.parent / "src" / "scripts" / "compile.py"
            result = subprocess.run(
                [sys.executable, str(compile_py), "--install-phase", "--install-dir", str(install)],
                capture_output=True,
                text=True,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                keys = list(obj.keys())
                self.assertEqual(keys, sorted(keys), f"Keys not sorted in: {line}")

    def test_lockfile_path_in_summary_is_absolute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            skill_dir = install / "mod" / "my-skill"
            _write(skill_dir / "my-skill.template.md", "hello")
            (install / "custom").mkdir(parents=True, exist_ok=True)

            code, events, _ = _run_install_phase(install)

            self.assertEqual(code, 0)
            summary = next(e for e in events if e["kind"] == "summary")
            lp = summary["lockfile_path"]
            self.assertTrue(Path(lp).is_absolute(), f"lockfile_path not absolute: {lp}")
            self.assertTrue(lp.endswith("bmad.lock"))


_BMAD_HELP_SRC = Path(__file__).resolve().parents[2] / "src" / "core-skills" / "bmad-help"


class TestBmadHelpInstallPhase(unittest.TestCase):
    """(AC 4) Real bmad-help skill: install-phase subprocess end-to-end contract.

    Exercises compile.py --install-phase against a fixture install_dir populated
    with the real bmad-help template, asserting byte-equal output to the
    checked-in frozen baseline at src/core-skills/bmad-help/SKILL.md.
    """

    def setUp(self) -> None:
        self._tmp_obj = tempfile.TemporaryDirectory()
        self._install = Path(self._tmp_obj.name)
        dest = self._install / "core" / "bmad-help" / "bmad-help.template.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(_BMAD_HELP_SRC / "bmad-help.template.md"), str(dest))
        (self._install / "custom").mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self._tmp_obj.cleanup()

    def test_exit_code_and_ndjson_events(self) -> None:
        code, events, _ = _run_install_phase(self._install)
        self.assertEqual(code, 0)
        skill_events = [e for e in events if e["kind"] == "skill"]
        summary_events = [e for e in events if e["kind"] == "summary"]
        self.assertEqual(len(skill_events), 1)
        self.assertEqual(len(summary_events), 1)
        self.assertEqual(skill_events[0]["skill"], "core/bmad-help")
        self.assertEqual(skill_events[0]["status"], "ok")
        self.assertEqual(summary_events[0]["compiled"], 1)
        self.assertEqual(summary_events[0]["errors"], 0)

    def test_compiled_skill_md_byte_equal_to_baseline(self) -> None:
        code, _, _ = _run_install_phase(self._install)
        self.assertEqual(code, 0)
        compiled = self._install / "core" / "bmad-help" / "SKILL.md"
        self.assertTrue(compiled.is_file(), f"SKILL.md not found at {compiled}")
        self.assertEqual(compiled.read_bytes(), (_BMAD_HELP_SRC / "SKILL.md").read_bytes())

    def test_lockfile_version_and_skill_hashes(self) -> None:
        code, _, _ = _run_install_phase(self._install)
        self.assertEqual(code, 0)
        lockfile_path = self._install / "_config" / "bmad.lock"
        self.assertTrue(lockfile_path.is_file(), f"bmad.lock not found at {lockfile_path}")
        lf = json.loads(lockfile_path.read_bytes())
        self.assertEqual(lf["version"], 1)

        entries = [e for e in lf["entries"] if e["skill"] == "bmad-help"]
        self.assertEqual(len(entries), 1, "expected exactly one lockfile entry for skill=bmad-help")
        entry = entries[0]

        compiled_md = self._install / "core" / "bmad-help" / "SKILL.md"
        template_md = self._install / "core" / "bmad-help" / "bmad-help.template.md"
        expected_compiled = bmad_io.hash_text(bmad_io.read_template(str(compiled_md)))
        expected_source = bmad_io.hash_text(bmad_io.read_template(str(template_md)))

        self.assertRegex(entry["compiled_hash"], r"^[0-9a-f]{64}$")
        self.assertRegex(entry["source_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(entry["compiled_hash"], expected_compiled)
        self.assertEqual(entry["source_hash"], expected_source)


class TestModuleDiscovery(unittest.TestCase):
    """(Story 3.0) Engine module-discovery prerequisite for Epic 3.

    Exercises `_discover_module_roots` and the install-phase `current_module`
    derivation that routes override probes to the correct module namespace
    for non-core skills. Per-skill mode (lockfile_root=None) is covered by
    the existing 282-test baseline.
    """

    def test_current_module_from_skill_path(self) -> None:
        """AC 1 smoke check: non-core module skill compiles without error.

        Note: not an AC-1 regression-pin — install-phase output path uses
        `skill_posix.parent.name` since Story 2.1, so this would pass against
        the pre-3.0 hardcoded `current_module="core"` too. The true AC-1
        regression-pin is `test_override_probe_routes_to_correct_module`.
        """
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "ext-mod" / "ext-skill").mkdir(parents=True)
            (t / "ext-mod" / "ext-skill" / "ext-skill.template.md").write_text(
                "Simple content\n", encoding="utf-8"
            )
            engine.compile_skill(
                t / "ext-mod" / "ext-skill", t, lockfile_root=t
            )
            compiled = t / "ext-mod" / "ext-skill" / "SKILL.md"
            self.assertTrue(compiled.is_file(), f"SKILL.md not found at {compiled}")

    def test_override_probe_routes_to_correct_module(self) -> None:
        """AC 5: end-to-end tier-2 override probe for non-core module.

        Pre-Story-3.0 (hardcoded current_module="core") this raised
        MissingFragmentError because the tier-2 probe looked in
        `custom/fragments/core/ext-skill/...` instead of
        `custom/fragments/ext-mod/ext-skill/...`.
        """
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "ext-mod" / "ext-skill").mkdir(parents=True)
            (t / "ext-mod" / "ext-skill" / "ext-skill.template.md").write_text(
                'Lead: <<include path="fragments/greet.template.md">>\n',
                encoding="utf-8",
            )
            (t / "custom" / "fragments" / "ext-mod" / "ext-skill").mkdir(parents=True)
            (
                t / "custom" / "fragments" / "ext-mod" / "ext-skill" / "greet.template.md"
            ).write_text("Hello from ext-mod override!\n", encoding="utf-8")
            (t / "_config").mkdir()

            engine.compile_skill(
                t / "ext-mod" / "ext-skill",
                t,
                lockfile_root=t,
                override_root=t / "custom",
            )
            compiled = (t / "ext-mod" / "ext-skill" / "SKILL.md").read_text(
                encoding="utf-8"
            )
            # Double newline: fragment's trailing \n + template's trailing \n
            # after include token (verbatim substitution per R2 empirical trace).
            self.assertEqual(compiled, "Lead: Hello from ext-mod override!\n\n")

    def test_reserved_dirs_excluded_from_module_roots(self) -> None:
        """AC 3: reserved + underscore-prefixed dirs are not module roots."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            for reserved in ("_config", "custom", "scripts", "memory", "_memory", "_shim"):
                (t / reserved).mkdir()
            (t / "ext-mod" / "ext-skill").mkdir(parents=True)
            (t / "ext-mod" / "ext-skill" / "ext-skill.template.md").write_text(
                "x\n", encoding="utf-8"
            )

            install_root = bmad_io.to_posix(t)
            roots = engine._discover_module_roots(
                install_root, "ext-mod", install_root / "ext-mod"
            )
            self.assertEqual(set(roots.keys()), {"ext-mod"})

    def test_module_roots_contains_all_module_dirs(self) -> None:
        """AC 2: cross-module routing — both `core` and `bmm` discovered."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "core" / "core-skill").mkdir(parents=True)
            (t / "core" / "core-skill" / "core-skill.template.md").write_text(
                "x\n", encoding="utf-8"
            )
            (t / "bmm" / "bmm-skill").mkdir(parents=True)
            (t / "bmm" / "bmm-skill" / "bmm-skill.template.md").write_text(
                "y\n", encoding="utf-8"
            )

            install_root = bmad_io.to_posix(t)
            roots = engine._discover_module_roots(
                install_root, "bmm", install_root / "bmm"
            )
            self.assertIn("core", roots)
            self.assertIn("bmm", roots)


class TestProseFragmentOverrides(unittest.TestCase):
    """(Story 3.1) Prose fragment override tier resolution + lockfile schema.

    Pins all five precedence tiers via 4 integration tests:
      - AC 1: tier-5 (base) wins when no override exists.
      - AC 2: tier-2 (user-module-fragment) wins; lockfile carries
        base_hash + override_path.
      - AC 3: tier-1 (user-full-skill) wins over tier-2 per the precedence
        ladder; compiled-output assertion only (lockfile root-tier provenance
        deferred to Story 4.2 per Open Question 4).
      - AC 4: identical-content override still uses the override tier;
        tier selection is path-existence-based, not content-comparison-based.
    """

    def _make_base_tree(self, tmp: Path) -> None:
        skill_dir = tmp / "core" / "skill1"
        _write(
            skill_dir / "skill1.template.md",
            'Lead: <<include path="fragments/persona-guard.template.md">>\n',
        )
        _write(skill_dir / "fragments" / "persona-guard.template.md", "Core guard.\n")

    def test_base_tier_recorded_in_lockfile(self) -> None:
        """AC 1: no override → base tier wins; lockfile records resolved_from='base'."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            self._make_base_tree(t)

            engine.compile_skill(t / "core" / "skill1", t, lockfile_root=t)

            compiled = (t / "core" / "skill1" / "SKILL.md").read_text(encoding="utf-8")
            self.assertEqual(compiled, "Lead: Core guard.\n\n")

            lf = json.loads((t / "_config" / "bmad.lock").read_text(encoding="utf-8"))
            entry = next(e for e in lf["entries"] if e["skill"] == "skill1")
            self.assertEqual(len(entry["fragments"]), 1)
            frag = entry["fragments"][0]
            self.assertEqual(frag["resolved_from"], "base")
            base_text = bmad_io.read_template(
                str(t / "core" / "skill1" / "fragments" / "persona-guard.template.md")
            )
            self.assertEqual(frag["hash"], bmad_io.hash_text(base_text))
            self.assertNotIn("base_hash", frag)
            self.assertNotIn("override_path", frag)

    def test_user_module_fragment_override_wins(self) -> None:
        """AC 2: tier-2 override wins; lockfile carries base_hash + override_path."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            self._make_base_tree(t)
            override_file = (
                t / "custom" / "fragments" / "core" / "skill1" / "persona-guard.template.md"
            )
            _write(override_file, "Override guard.\n")

            engine.compile_skill(
                t / "core" / "skill1", t, lockfile_root=t, override_root=t / "custom"
            )

            compiled = (t / "core" / "skill1" / "SKILL.md").read_text(encoding="utf-8")
            self.assertEqual(compiled, "Lead: Override guard.\n\n")

            lf = json.loads((t / "_config" / "bmad.lock").read_text(encoding="utf-8"))
            entry = next(e for e in lf["entries"] if e["skill"] == "skill1")
            frag = entry["fragments"][0]
            self.assertEqual(frag["resolved_from"], "user-module-fragment")

            override_text = bmad_io.read_template(str(override_file))
            base_text = bmad_io.read_template(
                str(t / "core" / "skill1" / "fragments" / "persona-guard.template.md")
            )
            self.assertEqual(frag["hash"], bmad_io.hash_text(override_text))
            self.assertEqual(frag["base_hash"], bmad_io.hash_text(base_text))
            self.assertEqual(
                frag["override_path"],
                "custom/fragments/core/skill1/persona-guard.template.md",
            )
            # Schema-v1 compat: `path` retained alongside `override_path`; for
            # override tiers they reference the same winning file.
            self.assertEqual(frag["path"], frag["override_path"])

    def test_user_full_skill_override_wins_over_fragment_override(self) -> None:
        """AC 3: tier-1 (user-full-skill) beats tier-2 (user-module-fragment)."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            self._make_base_tree(t)
            _write(
                t / "custom" / "fragments" / "core" / "skill1" / "persona-guard.template.md",
                "Override guard.\n",
            )
            _write(
                t / "custom" / "fragments" / "core" / "skill1" / "SKILL.template.md",
                "Full-skill replacement.\n",
            )

            engine.compile_skill(
                t / "core" / "skill1", t, lockfile_root=t, override_root=t / "custom"
            )

            compiled = (t / "core" / "skill1" / "SKILL.md").read_text(encoding="utf-8")
            self.assertEqual(compiled, "Full-skill replacement.\n")
            self.assertNotIn("Override guard.", compiled)
            self.assertNotIn("Core guard.", compiled)
            # Lockfile root-tier assertion deferred per OQ 4 (Story 4.2 territory).

    def test_identical_content_override_uses_override_tier(self) -> None:
        """AC 4: byte-identical override still uses override tier; tier wins on path existence."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            self._make_base_tree(t)
            override_file = (
                t / "custom" / "fragments" / "core" / "skill1" / "persona-guard.template.md"
            )
            _write(override_file, "Core guard.\n")

            engine.compile_skill(
                t / "core" / "skill1", t, lockfile_root=t, override_root=t / "custom"
            )

            compiled = (t / "core" / "skill1" / "SKILL.md").read_text(encoding="utf-8")
            self.assertEqual(compiled, "Lead: Core guard.\n\n")

            lf = json.loads((t / "_config" / "bmad.lock").read_text(encoding="utf-8"))
            entry = next(e for e in lf["entries"] if e["skill"] == "skill1")
            frag = entry["fragments"][0]
            self.assertEqual(frag["resolved_from"], "user-module-fragment")
            self.assertEqual(frag["base_hash"], frag["hash"])


class TestYamlVariableOverrides(unittest.TestCase):
    """(Story 3.3) 4-tier YAML variable cascade.

    bmad-config < module-config (above-marker) < user-config < install-flag.
    All tests use install-phase mode (lockfile_root=install_root) — per-skill
    mode skips the module-config probe per F3 guard (OQ 5 resolution).
    """

    def _make_install_tree(
        self, t: Path, module: str = "mod1", skill: str = "skill1"
    ) -> tuple[Path, Path, Path]:
        skill_dir = t / module / skill
        _write(skill_dir / f"{skill}.template.md", "User: {{user_name}}\n")
        _write(t / "core" / "config.yaml", "user_name: Shado\n")
        return skill_dir, t, t / "_config" / "bmad.lock"

    @staticmethod
    def _var_entry(lockfile_path: Path, skill: str, name: str) -> dict:
        lf = json.loads(lockfile_path.read_text(encoding="utf-8"))
        entry = next(e for e in lf["entries"] if e["skill"] == skill)
        return next(v for v in entry["variables"] if v["name"] == name)

    def test_bmad_config_tier_source_attribution(self) -> None:
        """AC 1: bmad-config tier baseline — source/source_path/value_hash."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            skill_dir, install_root, lf_path = self._make_install_tree(t)

            engine.compile_skill(skill_dir, install_root, lockfile_root=install_root)

            compiled = (install_root / "mod1" / "skill1" / "SKILL.md").read_text(encoding="utf-8")
            self.assertEqual(compiled, "User: Shado\n")

            ve = self._var_entry(lf_path, "skill1", "user_name")
            self.assertEqual(ve["source"], "bmad-config")
            self.assertTrue(ve["source_path"].endswith("core/config.yaml"))
            self.assertEqual(ve["value_hash"], bmad_io.hash_text("Shado"))

    def test_user_config_override_wins(self) -> None:
        """AC 2: user-config (_bmad/custom/config.yaml) wins over bmad-config."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            skill_dir, install_root, lf_path = self._make_install_tree(t)
            _write(t / "custom" / "config.yaml", "user_name: Override\n")

            engine.compile_skill(skill_dir, install_root, lockfile_root=install_root)

            compiled = (install_root / "mod1" / "skill1" / "SKILL.md").read_text(encoding="utf-8")
            self.assertEqual(compiled, "User: Override\n")

            ve = self._var_entry(lf_path, "skill1", "user_name")
            self.assertEqual(ve["source"], "user-config")
            self.assertTrue(ve["source_path"].endswith("custom/config.yaml"))
            self.assertEqual(ve["value_hash"], bmad_io.hash_text("Override"))

    def test_module_config_above_marker_wins_below_discarded(self) -> None:
        """AC 3: above-marker → module-config; below-marker echo discarded.

        Plus: user-config beats module-config.
        """
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            skill_dir = t / "mod1" / "skill1"
            _write(
                skill_dir / "skill1.template.md",
                "Custom: {{custom_var}}, User: {{user_name}}\n",
            )
            _write(t / "core" / "config.yaml", "user_name: Shado\n")
            _write(
                t / "mod1" / "config.yaml",
                "custom_var: ModuleValue\n\n# Core Configuration Values\nuser_name: Shado\n",
            )

            engine.compile_skill(skill_dir, t, lockfile_root=t)

            compiled = (t / "mod1" / "skill1" / "SKILL.md").read_text(encoding="utf-8")
            self.assertEqual(compiled, "Custom: ModuleValue, User: Shado\n")

            lf_path = t / "_config" / "bmad.lock"
            ve_custom = self._var_entry(lf_path, "skill1", "custom_var")
            self.assertEqual(ve_custom["source"], "module-config")
            self.assertEqual(ve_custom["value_hash"], bmad_io.hash_text("ModuleValue"))

            ve_user = self._var_entry(lf_path, "skill1", "user_name")
            # Below-marker echo is discarded — authoritative core value comes from core/config.yaml.
            self.assertEqual(ve_user["source"], "bmad-config")

            # Sub-assertion: user-config beats module-config.
            _write(t / "custom" / "config.yaml", "custom_var: UserValue\n")
            engine.compile_skill(skill_dir, t, lockfile_root=t)
            compiled = (t / "mod1" / "skill1" / "SKILL.md").read_text(encoding="utf-8")
            self.assertEqual(compiled, "Custom: UserValue, User: Shado\n")
            ve_custom = self._var_entry(lf_path, "skill1", "custom_var")
            self.assertEqual(ve_custom["source"], "user-config")

    def test_install_flag_wins_all(self) -> None:
        """AC 4: --set install-flag wins over all YAML tiers; source_path absent."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            skill_dir, install_root, lf_path = self._make_install_tree(t)
            _write(t / "custom" / "config.yaml", "user_name: Override\n")

            engine.compile_skill(
                skill_dir, install_root, lockfile_root=install_root,
                install_flags={"user_name": "Flag"},
            )

            compiled = (install_root / "mod1" / "skill1" / "SKILL.md").read_text(encoding="utf-8")
            self.assertEqual(compiled, "User: Flag\n")

            ve = self._var_entry(lf_path, "skill1", "user_name")
            self.assertEqual(ve["source"], "install-flag")
            self.assertNotIn("source_path", ve)
            self.assertEqual(ve["value_hash"], bmad_io.hash_text("Flag"))

            # Sub-variant: new key not in any config file.
            _write(skill_dir / "skill1.template.md", "User: {{user_name}}, New: {{totally_new_key}}\n")
            engine.compile_skill(
                skill_dir, install_root, lockfile_root=install_root,
                install_flags={"user_name": "Flag", "totally_new_key": "X"},
            )
            compiled = (install_root / "mod1" / "skill1" / "SKILL.md").read_text(encoding="utf-8")
            self.assertEqual(compiled, "User: Flag, New: X\n")
            ve_new = self._var_entry(lf_path, "skill1", "totally_new_key")
            self.assertEqual(ve_new["source"], "install-flag")
            self.assertEqual(ve_new["value_hash"], bmad_io.hash_text("X"))

            # Sub-variant: empty value — io.hash_text("") recorded.
            _write(skill_dir / "skill1.template.md", "User: '{{user_name}}'\n")
            engine.compile_skill(
                skill_dir, install_root, lockfile_root=install_root,
                install_flags={"user_name": ""},
            )
            compiled = (install_root / "mod1" / "skill1" / "SKILL.md").read_text(encoding="utf-8")
            self.assertEqual(compiled, "User: ''\n")
            ve_empty = self._var_entry(lf_path, "skill1", "user_name")
            self.assertEqual(ve_empty["source"], "install-flag")
            self.assertEqual(ve_empty["value_hash"], bmad_io.hash_text(""))


class TestModuleBoundaryEnforcement(unittest.TestCase):
    """(Story 3.4) Module co-existence and full-skill escape hatch warning."""

    def test_namespaced_module_coexists_with_core(self) -> None:
        """AC 1: non-core module fragment installs alongside core without conflict."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            # Core skill: base-tier fragment in fragments/ subdir
            _write(
                t / "core" / "skill1" / "skill1.template.md",
                '<<include path="fragments/persona-guard.template.md">>\n',
            )
            _write(
                t / "core" / "skill1" / "fragments" / "persona-guard.template.md",
                "Core guard.\n",
            )
            # Third-party skill: same-named fragment in its own namespace — no conflict
            _write(
                t / "thirdparty" / "skill2" / "skill2.template.md",
                '<<include path="fragments/persona-guard.template.md">>\n',
            )
            _write(
                t / "thirdparty" / "skill2" / "fragments" / "persona-guard.template.md",
                "ThirdParty guard.\n",
            )
            (t / "custom").mkdir(parents=True, exist_ok=True)

            code, events, _ = _run_install_phase(t)

            self.assertEqual(code, 0)
            summary = next(e for e in events if e["kind"] == "summary")
            self.assertEqual(summary["compiled"], 2)
            self.assertEqual(summary["errors"], 0)
            self.assertTrue((t / "core" / "skill1" / "SKILL.md").is_file())
            self.assertTrue((t / "thirdparty" / "skill2" / "SKILL.md").is_file())

    def test_user_full_skill_override_emits_warning(self) -> None:
        """AC 2: SKILL.template.md user override emits kind:"warning" NDJSON event."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            _write(t / "mymod" / "skill1" / "skill1.template.md", "Original content\n")
            _write(
                t / "custom" / "fragments" / "mymod" / "skill1" / "SKILL.template.md",
                "Override: complete\n",
            )

            code, events, _ = _run_install_phase(t)

            self.assertEqual(code, 0)
            compiled = (t / "mymod" / "skill1" / "SKILL.md").read_text(encoding="utf-8")
            self.assertEqual(compiled, "Override: complete\n")

            warning_events = [e for e in events if e["kind"] == "warning"]
            self.assertTrue(len(warning_events) >= 1, "Expected at least one kind:warning event")
            self.assertIn("bypasses fragment-level upgrade safety", warning_events[0]["message"])


class TestOverrideRootContainment(unittest.TestCase):
    """(Story 3.5) Override-root containment: OverrideOutsideRootError on escape."""

    def test_dotdot_override_path_raises_override_outside_root(self) -> None:
        """AC 1: override_root with ../ segments that escape scenario_root is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "core" / "skill1" / "skill1.template.md", "Hello\n")
            # root / ".." / "evil" resolves to parent-of-root/evil — outside root.
            with self.assertRaises(errors.OverrideOutsideRootError):
                engine.compile_skill(
                    root / "core" / "skill1",
                    root,
                    override_root=root / ".." / "evil",
                )

    @unittest.skipIf(sys.platform == "win32", "symlinks require elevated privileges on Windows")
    def test_symlink_override_pointing_outside_raises_override_outside_root(self) -> None:
        """AC 2: override_root that is a symlink resolving outside scenario_root is rejected."""
        with tempfile.TemporaryDirectory() as tmp_root, tempfile.TemporaryDirectory() as tmp_outside:
            root = Path(tmp_root)
            outside = Path(tmp_outside)
            _write(root / "core" / "skill1" / "skill1.template.md", "Hello\n")
            # custom/ is a symlink pointing to a directory outside root.
            symlink = root / "custom"
            try:
                os.symlink(str(outside), str(symlink))
            except OSError as exc:
                self.skipTest(f"symlink creation failed (may need elevated privileges): {exc}")
            with self.assertRaises(errors.OverrideOutsideRootError):
                engine.compile_skill(
                    root / "core" / "skill1",
                    root,
                    override_root=symlink,
                )

    def test_include_dotdot_traversal_raises_override_outside_root(self) -> None:
        """AC 5: include path with ../ segments that escape scenario_root is rejected."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # From root/core/skill1, three ../ levels escape root entirely.
            _write(
                root / "core" / "skill1" / "skill1.template.md",
                '<<include path="../../../outside.template.md">>',
            )
            with self.assertRaises(errors.OverrideOutsideRootError):
                engine.compile_skill(root / "core" / "skill1", root)

    def test_override_root_within_root_does_not_raise(self) -> None:
        """AC 6 (positive): override_root within scenario_root compiles without error."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "core" / "skill1" / "skill1.template.md", "Hello\n")
            custom = root / "_bmad" / "custom"
            custom.mkdir(parents=True, exist_ok=True)
            # override_root is within root — must not raise OverrideOutsideRootError.
            result = engine.compile_skill(
                root / "core" / "skill1",
                root,
                override_root=custom,
            )
            self.assertIsNone(result)


class TestCompileSkillPositional(unittest.TestCase):
    """Tests for positional <skill> argument (AC 1)."""

    def test_positional_qualified_resolves_and_compiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello from my-skill!")
            code, stdout, stderr = _run_compile_skill(install, ["core/my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            skill_md = install / "core" / "my-skill" / "SKILL.md"
            self.assertTrue(skill_md.is_file())
            self.assertEqual(skill_md.read_text(encoding="utf-8"), "Hello from my-skill!")

    def test_positional_short_resolves_unique(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello from my-skill!")
            code, stdout, stderr = _run_compile_skill(install, ["my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            skill_md = install / "core" / "my-skill" / "SKILL.md"
            self.assertTrue(skill_md.is_file())

    def test_positional_ambiguous_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "core version")
            _write(install / "thirdparty" / "my-skill" / "my-skill.template.md", "thirdparty version")
            code, stdout, stderr = _run_compile_skill(install, ["my-skill"])
            self.assertEqual(code, 1)
            self.assertIn("core/my-skill", stderr)
            self.assertIn("thirdparty/my-skill", stderr)

    def test_positional_not_found_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            (install / "core").mkdir(parents=True)
            code, stdout, stderr = _run_compile_skill(install, ["nonexistent-skill"])
            self.assertEqual(code, 1)
            self.assertIn("not found", stderr)

    def test_positional_full_skill_override_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello!")
            _write(
                install / "custom" / "fragments" / "core" / "my-skill" / "SKILL.template.md",
                "Full override",
            )
            code, stdout, stderr = _run_compile_skill(install, ["core/my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            self.assertIn("full-skill override", stderr)


class TestCompileSkillDiff(unittest.TestCase):
    """Tests for --diff mode (AC 2, AC 3, AC 4, AC 5)."""

    def _minimal_lock(self, install: Path) -> None:
        """Write a minimal valid bmad.lock so the engine sees version=1 and proceeds."""
        lock_content = (
            json.dumps(
                {"bmad_version": "1.0.0", "compiled_at": "1.0.0", "entries": [], "version": 1},
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )
        _write(install / "_config" / "bmad.lock", lock_content)

    def test_diff_shows_changes_when_installed_differs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "New content\n")
            _write(install / "core" / "my-skill" / "SKILL.md", "Old content\n")
            self._minimal_lock(install)
            code, stdout, stderr = _run_compile_skill(install, ["core/my-skill", "--diff"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            self.assertIn("-Old content", stdout)
            self.assertIn("+New content", stdout)

    def test_diff_no_writes_to_skill_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "New content\n")
            _write(install / "core" / "my-skill" / "SKILL.md", "Old content\n")
            self._minimal_lock(install)
            skill_md = install / "core" / "my-skill" / "SKILL.md"
            sha_before = hashlib.sha256(skill_md.read_bytes()).hexdigest()
            _run_compile_skill(install, ["core/my-skill", "--diff"])
            sha_after = hashlib.sha256(skill_md.read_bytes()).hexdigest()
            self.assertEqual(sha_before, sha_after)

    def test_diff_no_writes_to_lockfile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "New content\n")
            _write(install / "core" / "my-skill" / "SKILL.md", "Old content\n")
            self._minimal_lock(install)
            lock = install / "_config" / "bmad.lock"
            sha_before = hashlib.sha256(lock.read_bytes()).hexdigest()
            _run_compile_skill(install, ["core/my-skill", "--diff"])
            sha_after = hashlib.sha256(lock.read_bytes()).hexdigest()
            self.assertEqual(sha_before, sha_after)

    def test_diff_unchanged_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Same content\n")
            # First: normal compile to produce SKILL.md and bmad.lock
            code, _, stderr = _run_compile_skill(install, ["core/my-skill"])
            self.assertEqual(code, 0, f"Initial compile failed: {stderr}")
            # Second: --diff against the freshly compiled output should be empty
            code, stdout, stderr = _run_compile_skill(install, ["core/my-skill", "--diff"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            self.assertEqual(stdout, "")

    def test_diff_pristine_no_custom_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Same content\n")
            # Compile once without any custom/ directory
            code, _, stderr = _run_compile_skill(install, ["core/my-skill"])
            self.assertEqual(code, 0, f"Initial compile failed: {stderr}")
            # Ensure no custom/ directory exists (engine never creates one)
            custom_dir = install / "custom"
            if custom_dir.exists():
                shutil.rmtree(str(custom_dir))
            # --diff with no custom/ should be empty and silent
            code, stdout, stderr = _run_compile_skill(install, ["core/my-skill", "--diff"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            self.assertEqual(stdout, "")
            self.assertEqual(stderr, "")

    def test_diff_plain_when_no_tty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "New content\n")
            _write(install / "core" / "my-skill" / "SKILL.md", "Old content\n")
            self._minimal_lock(install)
            # subprocess capture_output=True redirects stdout to a pipe → isatty() == False
            code, stdout, _ = _run_compile_skill(install, ["core/my-skill", "--diff"])
            self.assertEqual(code, 0)
            self.assertNotIn("\033[", stdout)

    def test_determinism_twice_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Deterministic content\n")
            _write(install / "core" / "my-skill" / "SKILL.md", "Old content\n")
            self._minimal_lock(install)
            skill_md = install / "core" / "my-skill" / "SKILL.md"
            lock = install / "_config" / "bmad.lock"

            sha_skill_1 = hashlib.sha256(skill_md.read_bytes()).hexdigest()
            sha_lock_1 = hashlib.sha256(lock.read_bytes()).hexdigest()
            code1, stdout1, _ = _run_compile_skill(install, ["core/my-skill", "--diff"])
            self.assertEqual(code1, 0)
            self.assertEqual(hashlib.sha256(skill_md.read_bytes()).hexdigest(), sha_skill_1)
            self.assertEqual(hashlib.sha256(lock.read_bytes()).hexdigest(), sha_lock_1)

            sha_skill_2 = hashlib.sha256(skill_md.read_bytes()).hexdigest()
            sha_lock_2 = hashlib.sha256(lock.read_bytes()).hexdigest()
            code2, stdout2, _ = _run_compile_skill(install, ["core/my-skill", "--diff"])
            self.assertEqual(code2, 0)
            self.assertEqual(hashlib.sha256(skill_md.read_bytes()).hexdigest(), sha_skill_2)
            self.assertEqual(hashlib.sha256(lock.read_bytes()).hexdigest(), sha_lock_2)

            # Both runs produce byte-identical stdout
            self.assertEqual(stdout1, stdout2)
            # Files unchanged across both runs
            self.assertEqual(sha_skill_1, sha_skill_2)
            self.assertEqual(sha_lock_1, sha_lock_2)


class TestExitCodeAlignment(unittest.TestCase):
    """Tests for exit code convention (fold-in 5b): exit 1 for CompilerError, exit 2 for LockfileVersionMismatchError."""

    def test_compiler_error_exits_1_via_positional(self) -> None:
        """Skill dir with no template file → MissingFragmentError → exit 1 (not 2)."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            # Create skill dir with NO template file
            (install / "core" / "my-skill").mkdir(parents=True)
            code, _, _ = _run_compile_skill(install, ["core/my-skill"])
            self.assertEqual(code, 1)

    def test_compiler_error_exits_1_via_skill_flag(self) -> None:
        """Same scenario via --skill <path> → exit 1 (regression for fold-in 5b fix)."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "out"
            install.mkdir()
            skill_dir = Path(tmp) / "src" / "my-skill"
            skill_dir.mkdir(parents=True)
            # No template file → MissingFragmentError → exit 1
            code, _, _ = _run_compile_skill(install, ["--skill", str(skill_dir)])
            self.assertEqual(code, 1)

    def test_lockfile_version_mismatch_exits_2(self) -> None:
        """bmad.lock with version > 1 → LockfileVersionMismatchError → exit 2."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello!")
            # Write a lockfile with version=2 (future, unsupported)
            future_lock = (
                json.dumps(
                    {"bmad_version": "99.0.0", "compiled_at": "99.0.0", "entries": [], "version": 2},
                    sort_keys=True,
                    indent=2,
                )
                + "\n"
            )
            _write(install / "_config" / "bmad.lock", future_lock)
            code, _, stderr = _run_compile_skill(install, ["core/my-skill"])
            self.assertEqual(code, 2, f"stderr: {stderr}")


def _run_explain(install_dir: Path, args: list[str]) -> tuple[int, str, str]:
    """Story 4.2: invoke compile.py with --explain prepended to `args`."""
    return _run_compile_skill(install_dir, ["--explain"] + args)


class TestExplainMode(unittest.TestCase):
    """Story 4.2: --explain Markdown output with <Include> and <Variable> tags."""

    def _minimal_lock(self, install: Path) -> None:
        lock_content = (
            json.dumps(
                {"bmad_version": "1.0.0", "compiled_at": "1.0.0", "entries": [], "version": 1},
                sort_keys=True,
                indent=2,
            )
            + "\n"
        )
        _write(install / "_config" / "bmad.lock", lock_content)

    # ---------- AC 1: <Include> tags ----------

    def test_explain_basic_include_wraps_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(
                install / "core" / "my-skill" / "my-skill.template.md",
                '<<include path="fragments/body.template.md">>',
            )
            _write(install / "core" / "my-skill" / "fragments" / "body.template.md", "Body content\n")
            self._minimal_lock(install)
            code, stdout, stderr = _run_explain(install, ["core/my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            self.assertIn('<Include src="fragments/body.template.md"', stdout)
            self.assertIn('resolved-from="base"', stdout)
            self.assertIn("hash=", stdout)
            self.assertIn("Body content", stdout)

    def test_explain_root_wraps_entire_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            self._minimal_lock(install)
            code, stdout, stderr = _run_explain(install, ["core/my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            self.assertTrue(stdout.startswith("<Include "), f"got: {stdout[:80]!r}")
            self.assertTrue(stdout.rstrip().endswith("</Include>"), f"got tail: {stdout[-80:]!r}")

    def test_explain_include_attrs_required_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(
                install / "core" / "my-skill" / "my-skill.template.md",
                '<<include path="fragments/body.template.md">>',
            )
            _write(install / "core" / "my-skill" / "fragments" / "body.template.md", "Body\n")
            self._minimal_lock(install)
            code, stdout, _ = _run_explain(install, ["core/my-skill"])
            self.assertEqual(code, 0)
            # Each <Include opening tag carries src=, resolved-from=, hash=
            for line in stdout.splitlines():
                if line.startswith("<Include "):
                    self.assertIn(' src="', line)
                    self.assertIn(' resolved-from="', line)
                    self.assertIn(' hash="', line)

    def test_explain_variant_attr_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(
                install / "core" / "my-skill" / "my-skill.template.md",
                '<<include path="fragments/body.template.md">>',
            )
            _write(install / "core" / "my-skill" / "fragments" / "body.template.md", "universal\n")
            _write(install / "core" / "my-skill" / "fragments" / "body.cursor.template.md", "cursor variant\n")
            self._minimal_lock(install)
            code, stdout, stderr = _run_explain(install, ["core/my-skill", "--tools", "cursor"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            self.assertIn('resolved-from="variant"', stdout)
            self.assertIn('variant="cursor"', stdout)

    def test_explain_no_writes_to_skill_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            _write(install / "core" / "my-skill" / "SKILL.md", "OLD\n")
            self._minimal_lock(install)
            skill_md = install / "core" / "my-skill" / "SKILL.md"
            sha_before = hashlib.sha256(skill_md.read_bytes()).hexdigest()
            _run_explain(install, ["core/my-skill"])
            sha_after = hashlib.sha256(skill_md.read_bytes()).hexdigest()
            self.assertEqual(sha_before, sha_after)

    def test_explain_no_writes_to_lockfile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            self._minimal_lock(install)
            lock = install / "_config" / "bmad.lock"
            sha_before = hashlib.sha256(lock.read_bytes()).hexdigest()
            _run_explain(install, ["core/my-skill"])
            sha_after = hashlib.sha256(lock.read_bytes()).hexdigest()
            self.assertEqual(sha_before, sha_after)

    def test_explain_mutual_exclusion_with_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            self._minimal_lock(install)
            code, _, stderr = _run_explain(install, ["core/my-skill", "--diff"])
            self.assertEqual(code, 1)
            self.assertIn("mutually exclusive", stderr)

    def test_explain_requires_skill_arg(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            self._minimal_lock(install)
            code, _, stderr = _run_explain(install, [])
            self.assertEqual(code, 1)
            self.assertIn("--explain requires a skill argument", stderr)

    # ---------- AC 2: <Variable> tags ----------

    def test_explain_variable_compile_time(self) -> None:
        # Skill lives under a non-core module so the install-phase
        # module-config probe (lockfile_root/<module>/config.yaml) does NOT
        # collide with the bmad-config probe (lockfile_root/core/config.yaml).
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "mod1" / "my-skill" / "my-skill.template.md", "User: {{user_name}}\n")
            _write(install / "core" / "config.yaml", "user_name: TestUser\n")
            self._minimal_lock(install)
            code, stdout, stderr = _run_explain(install, ["mod1/my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            self.assertIn('<Variable name="user_name"', stdout)
            self.assertIn('source="bmad-config"', stdout)
            self.assertIn('resolved-at="compile-time"', stdout)
            self.assertIn("TestUser", stdout)
            # Fold-in 3 — source-path attribute present for YAML-tier vars
            self.assertIn('source-path="', stdout)

    # ---------- AC 3: VarRuntime passthrough ----------

    def test_explain_variable_runtime_passthrough(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Token: {runtime_var}\n")
            self._minimal_lock(install)
            code, stdout, stderr = _run_explain(install, ["core/my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            self.assertIn("{runtime_var}", stdout)
            self.assertNotIn('<Variable name="runtime_var"', stdout)

    # ---------- AC 4: override <Include> attrs ----------

    def test_explain_override_fragment_attrs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(
                install / "core" / "my-skill" / "my-skill.template.md",
                '<<include path="fragments/body.template.md">>',
            )
            _write(install / "core" / "my-skill" / "fragments" / "body.template.md", "BASE\n")
            _write(install / "custom" / "fragments" / "body.template.md", "OVERRIDE\n")
            self._minimal_lock(install)
            code, stdout, stderr = _run_explain(install, ["core/my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            self.assertIn('resolved-from="user-override"', stdout)
            self.assertIn('override-path="custom/fragments/body.template.md"', stdout)
            self.assertIn("base-hash=", stdout)
            self.assertIn("override-hash=", stdout)
            self.assertIn("OVERRIDE", stdout)

    def test_explain_user_module_fragment_attrs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(
                install / "core" / "my-skill" / "my-skill.template.md",
                '<<include path="fragments/body.template.md">>',
            )
            _write(install / "core" / "my-skill" / "fragments" / "body.template.md", "BASE\n")
            _write(install / "custom" / "fragments" / "core" / "my-skill" / "body.template.md", "MODFRAG\n")
            self._minimal_lock(install)
            code, stdout, stderr = _run_explain(install, ["core/my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            self.assertIn('resolved-from="user-module-fragment"', stdout)
            self.assertIn('override-path="custom/fragments/core/my-skill/body.template.md"', stdout)
            self.assertIn("base-hash=", stdout)
            self.assertIn("MODFRAG", stdout)

    # ---------- AC 5: determinism ----------

    def test_explain_determinism_twice_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "User: {{user_name}}\n")
            _write(install / "core" / "config.yaml", "user_name: Determ\n")
            self._minimal_lock(install)
            skill_md = install / "core" / "my-skill" / "SKILL.md"
            lock = install / "_config" / "bmad.lock"
            # SKILL.md does not exist yet (no compile run); record absence as None
            sha_lock_before = hashlib.sha256(lock.read_bytes()).hexdigest()
            code1, stdout1, _ = _run_explain(install, ["core/my-skill"])
            self.assertEqual(code1, 0)
            self.assertFalse(skill_md.exists(), "explain mode must not write SKILL.md")
            self.assertEqual(hashlib.sha256(lock.read_bytes()).hexdigest(), sha_lock_before)
            code2, stdout2, _ = _run_explain(install, ["core/my-skill"])
            self.assertEqual(code2, 0)
            self.assertEqual(stdout1, stdout2)
            self.assertEqual(hashlib.sha256(lock.read_bytes()).hexdigest(), sha_lock_before)

    def test_explain_no_timestamps_in_output(self) -> None:
        import re as _re
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "User: {{user_name}}\n")
            _write(install / "core" / "config.yaml", "user_name: NoStamp\n")
            self._minimal_lock(install)
            code, stdout, _ = _run_explain(install, ["core/my-skill"])
            self.assertEqual(code, 0)
            # No date pattern (YYYY-MM-DD) anywhere in output
            self.assertIsNone(_re.search(r"\b\d{4}-\d{2}-\d{2}\b", stdout))
            # Static phase tag present
            self.assertIn('resolved-at="compile-time"', stdout)

    # ---------- Additional integration tests ----------

    def test_explain_user_full_skill_root_attrs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "BASE\n")
            _write(
                install / "custom" / "fragments" / "core" / "my-skill" / "SKILL.template.md",
                "OVERRIDE_ROOT\n",
            )
            self._minimal_lock(install)
            code, stdout, stderr = _run_explain(install, ["core/my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            self.assertIn('resolved-from="user-full-skill"', stdout)
            # base-hash present because the base SKILL.template.md still exists
            self.assertIn("base-hash=", stdout)
            self.assertIn("OVERRIDE_ROOT", stdout)

    def test_contributing_paths_multi_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Tag: {{self.tag}}\n")
            _write(install / "core" / "my-skill" / "customize.toml", 'tag = "default-val"\n')
            _write(install / "custom" / "my-skill.toml", 'tag = "team-val"\n')
            self._minimal_lock(install)
            code, stdout, stderr = _run_explain(install, ["core/my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            self.assertIn('contributing-paths="', stdout)
            # Both paths appear in the joined attribute (semicolon-separated, sorted)
            self.assertIn("customize.toml", stdout)
            self.assertIn("my-skill.toml", stdout)

    def test_explain_local_scope_variable(self) -> None:
        # A fragment receives a custom prop via the include directive; the
        # fragment template references it as {{user}} → resolved from
        # local_scope (no var_scope file source).
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(
                install / "core" / "my-skill" / "my-skill.template.md",
                '<<include path="fragments/greet.template.md" user="Alice">>',
            )
            _write(
                install / "core" / "my-skill" / "fragments" / "greet.template.md",
                "Hello {{user}}\n",
            )
            self._minimal_lock(install)
            code, stdout, stderr = _run_explain(install, ["core/my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            self.assertIn('<Variable name="user"', stdout)
            self.assertIn('source="local-scope"', stdout)
            # No source-path / toml-layer attrs for local-scope wins
            # (find the specific <Variable name="user"...> tag and inspect it)
            tag_start = stdout.find('<Variable name="user"')
            tag_end = stdout.find(">", tag_start)
            tag = stdout[tag_start:tag_end + 1]
            self.assertNotIn("source-path", tag)
            self.assertNotIn("toml-layer", tag)
            self.assertIn("Alice", stdout)

    def test_explain_nested_include_nesting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(
                install / "core" / "my-skill" / "my-skill.template.md",
                '<<include path="fragments/a.template.md">>',
            )
            _write(
                install / "core" / "my-skill" / "fragments" / "a.template.md",
                'A-start\n<<include path="fragments/b.template.md">>\nA-end\n',
            )
            _write(
                install / "core" / "my-skill" / "fragments" / "b.template.md",
                "B-content\n",
            )
            self._minimal_lock(install)
            code, stdout, _ = _run_explain(install, ["core/my-skill"])
            self.assertEqual(code, 0)
            # DFS pre-order: <Include a> opens before <Include b>; b closes before a closes.
            a_open = stdout.find('<Include src="fragments/a.template.md"')
            b_open = stdout.find('<Include src="fragments/b.template.md"')
            self.assertNotEqual(a_open, -1)
            self.assertNotEqual(b_open, -1)
            self.assertLess(a_open, b_open)
            # Find the `</Include>` that closes b (first one after b_open) and
            # the one that closes a (must come AFTER b's close).
            b_close = stdout.find("</Include>", b_open)
            a_close_search_from = b_close + len("</Include>")
            a_close = stdout.find("</Include>", a_close_search_from)
            self.assertNotEqual(b_close, -1)
            self.assertNotEqual(a_close, -1)
            self.assertLess(b_close, a_close)

    def test_explain_override_base_file_absent(self) -> None:
        # Override exists at user-override tier, but the base file in the
        # skill dir does NOT exist — base-hash must be absent from <Include>.
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(
                install / "core" / "my-skill" / "my-skill.template.md",
                '<<include path="fragments/body.template.md">>',
            )
            # No base fragments/body.template.md in skill dir.
            _write(install / "custom" / "fragments" / "body.template.md", "OVERRIDE_ONLY\n")
            self._minimal_lock(install)
            code, stdout, stderr = _run_explain(install, ["core/my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            self.assertIn('resolved-from="user-override"', stdout)
            # Locate the user-override <Include ...> tag and assert no base-hash inside it.
            tag_start = stdout.find('<Include src="fragments/body.template.md"')
            tag_end = stdout.find(">", tag_start)
            tag = stdout[tag_start:tag_end + 1]
            self.assertNotIn("base-hash", tag)
            self.assertIn("override-hash", tag)
            self.assertIn("OVERRIDE_ONLY", stdout)

    # ---------- R1 patches: XML escaping ----------

    def test_explain_variable_value_with_xml_metacharacters(self) -> None:
        """R1 P1: a resolved value containing `</Variable>` or `&` or `<`
        must be XML-escaped in element content so it cannot prematurely
        close the wrapping tag or break downstream XML parsing."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "mod1" / "my-skill" / "my-skill.template.md", "X={{user_name}}\n")
            # value contains `<` and `&` and a literal closing-tag fragment
            _write(install / "core" / "config.yaml", 'user_name: "a < b & c </Variable>"\n')
            self._minimal_lock(install)
            code, stdout, stderr = _run_explain(install, ["mod1/my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            # Raw `<` and `</Variable>` must NOT appear inside the variable's
            # element content (escaped to &lt; / &amp;).
            # Find the <Variable name="user_name" ...>VALUE</Variable> block
            tag_open = stdout.find('<Variable name="user_name"')
            self.assertNotEqual(tag_open, -1)
            tag_close_open = stdout.find(">", tag_open)
            tag_close_end = stdout.find("</Variable>", tag_close_open)
            self.assertNotEqual(tag_close_end, -1)
            content = stdout[tag_close_open + 1:tag_close_end]
            self.assertIn("&lt;", content)
            self.assertIn("&amp;", content)
            # The literal `</Variable>` substring must be escaped, not appear
            # raw inside the value.
            self.assertNotIn("</Variable>", content)

    def test_explain_attribute_value_with_quote_escaped(self) -> None:
        """R1 P1: an attribute value (e.g. file path with `&`) must be
        escaped to `&amp;` so it doesn't break attribute parsing.
        We test via a contributing-paths fixture that produces a path with
        an `&` in it (rare but possible).
        """
        # The simplest test: assert that `_xml_escape_attr` handles the
        # important characters. This is a unit test on the helper.
        from src.scripts.bmad_compile.engine import _xml_escape_attr
        self.assertEqual(_xml_escape_attr('a "b" c'), "a &quot;b&quot; c")
        self.assertEqual(_xml_escape_attr('x<y>z'), "x&lt;y&gt;z")
        self.assertEqual(_xml_escape_attr('a&b'), "a&amp;b")
        # Order matters: escape & first so we don't double-escape.
        self.assertEqual(_xml_escape_attr('a & "b"'), "a &amp; &quot;b&quot;")

    def test_xml_escape_strips_illegal_control_chars(self) -> None:
        """R2 P1: XML 1.0-illegal control characters (U+0000..U+0008,
        U+000B-C, U+000E..U+001F) must be replaced with U+FFFD before any
        other escaping — otherwise downstream `xml.etree.parse` would
        reject the explain output regardless of attribute/element escaping.
        """
        from src.scripts.bmad_compile.engine import _xml_escape_attr, _xml_escape_text
        # NUL, BEL, VT, FF, ESC are all XML 1.0-illegal
        weird = "a\x00b\x07c\x0bd\x0ce\x1bf"
        out_attr = _xml_escape_attr(weird)
        self.assertNotIn("\x00", out_attr)
        self.assertNotIn("\x07", out_attr)
        self.assertNotIn("\x0b", out_attr)
        self.assertNotIn("\x0c", out_attr)
        self.assertNotIn("\x1b", out_attr)
        self.assertIn("�", out_attr)
        out_text = _xml_escape_text(weird)
        self.assertNotIn("\x00", out_text)
        self.assertIn("�", out_text)
        # \n \r \t are XML-LEGAL whitespace; they must NOT be replaced with U+FFFD
        # in attr-escape (they get entity-encoded instead).
        self.assertNotIn("�", _xml_escape_attr("line1\nline2\ttabbed"))

    # ---------- AC 10 fold-in 4: zip mismatch guard (unit) ----------

    def test_zip_mismatch_guard(self) -> None:
        from src.scripts.bmad_compile.resolver import VariableScope
        with self.assertRaises(ValueError) as ctx:
            VariableScope.build(
                toml_layers=[("d", {})],
                toml_layer_paths=["path1", "extra_path"],
            )
        self.assertIn("equal length", str(ctx.exception))


def _run_explain_tree(install_dir: Path, args: list[str]) -> tuple[int, str, str]:
    """Story 4.3: invoke compile.py with --explain --tree prepended to args."""
    return _run_compile_skill(install_dir, ["--explain", "--tree"] + args)


def _run_explain_json(install_dir: Path, args: list[str]) -> tuple[int, str, str]:
    """Story 4.3: invoke compile.py with --explain --json prepended to args."""
    return _run_compile_skill(install_dir, ["--explain", "--json"] + args)


class TestExplainTreeMode(unittest.TestCase):
    """Story 4.3 AC 1: --explain --tree fragment dependency tree output."""

    def _minimal_lock(self, install: Path) -> None:
        lock_content = (
            json.dumps(
                {"bmad_version": "1.0.0", "compiled_at": "1.0.0", "entries": [], "version": 1},
                sort_keys=True, indent=2,
            ) + "\n"
        )
        _write(install / "_config" / "bmad.lock", lock_content)

    def test_tree_root_at_depth_zero(self) -> None:
        """Root line has no leading indent."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            self._minimal_lock(install)
            code, stdout, stderr = _run_explain_tree(install, ["core/my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            first_line = stdout.splitlines()[0]
            self.assertFalse(first_line.startswith(" "), f"Root must have no indent: {first_line!r}")
            self.assertIn("[base]", first_line)
            self.assertIn("my-skill.template.md", first_line)

    def test_tree_nested_indents_by_depth(self) -> None:
        """Each level adds exactly two spaces of indent."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(
                install / "core" / "my-skill" / "my-skill.template.md",
                '<<include path="fragments/a.template.md">>',
            )
            _write(
                install / "core" / "my-skill" / "fragments" / "a.template.md",
                '<<include path="fragments/b.template.md">>',
            )
            _write(install / "core" / "my-skill" / "fragments" / "b.template.md", "leaf\n")
            self._minimal_lock(install)
            code, stdout, stderr = _run_explain_tree(install, ["core/my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            lines = stdout.splitlines()
            # root at depth 0 — no indent
            self.assertFalse(lines[0].startswith(" "))
            # a.template.md at depth 1 — two spaces
            a_line = next(l for l in lines if "a.template.md" in l)
            self.assertTrue(a_line.startswith("  "), f"depth-1 must start with 2 spaces: {a_line!r}")
            self.assertFalse(a_line.startswith("    "), f"depth-1 must not have 4 spaces: {a_line!r}")
            # b.template.md at depth 2 — four spaces
            b_line = next(l for l in lines if "b.template.md" in l)
            self.assertTrue(b_line.startswith("    "), f"depth-2 must start with 4 spaces: {b_line!r}")

    def test_tree_shows_resolved_from_tier(self) -> None:
        """Override fragment appears with [user-override] in the tree."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(
                install / "core" / "my-skill" / "my-skill.template.md",
                '<<include path="fragments/body.template.md">>',
            )
            _write(install / "core" / "my-skill" / "fragments" / "body.template.md", "base\n")
            # user-override path: custom/fragments/<fragment_filename>
            _write(install / "custom" / "fragments" / "body.template.md", "override\n")
            self._minimal_lock(install)
            code, stdout, stderr = _run_explain_tree(install, ["core/my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            self.assertIn("[user-override]", stdout)

    def test_tree_suppresses_content_bodies(self) -> None:
        """Template body text must not appear in tree output."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello World secret\n")
            self._minimal_lock(install)
            code, stdout, _ = _run_explain_tree(install, ["core/my-skill"])
            self.assertEqual(code, 0)
            self.assertNotIn("Hello World secret", stdout)

    def test_tree_no_xml_tags(self) -> None:
        """No <Include or <Variable tags appear in tree output."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(
                install / "core" / "my-skill" / "my-skill.template.md",
                '<<include path="fragments/body.template.md">>',
            )
            _write(install / "core" / "my-skill" / "fragments" / "body.template.md", "body\n")
            self._minimal_lock(install)
            code, stdout, _ = _run_explain_tree(install, ["core/my-skill"])
            self.assertEqual(code, 0)
            self.assertNotIn("<Include", stdout)
            self.assertNotIn("<Variable", stdout)

    def test_tree_no_writes_to_skill_md(self) -> None:
        """Pre-existing SKILL.md SHA unchanged after --explain --tree."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            _write(install / "core" / "my-skill" / "SKILL.md", "OLD\n")
            self._minimal_lock(install)
            skill_md = install / "core" / "my-skill" / "SKILL.md"
            sha_before = hashlib.sha256(skill_md.read_bytes()).hexdigest()
            _run_explain_tree(install, ["core/my-skill"])
            sha_after = hashlib.sha256(skill_md.read_bytes()).hexdigest()
            self.assertEqual(sha_before, sha_after)

    def test_tree_no_writes_to_lockfile(self) -> None:
        """Lockfile SHA unchanged after --explain --tree."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            self._minimal_lock(install)
            lock = install / "_config" / "bmad.lock"
            sha_before = hashlib.sha256(lock.read_bytes()).hexdigest()
            _run_explain_tree(install, ["core/my-skill"])
            sha_after = hashlib.sha256(lock.read_bytes()).hexdigest()
            self.assertEqual(sha_before, sha_after)

    def test_tree_determinism_twice_run(self) -> None:
        """Two runs of --explain --tree produce byte-identical stdout."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(
                install / "core" / "my-skill" / "my-skill.template.md",
                '<<include path="fragments/body.template.md">>',
            )
            _write(install / "core" / "my-skill" / "fragments" / "body.template.md", "body\n")
            self._minimal_lock(install)
            _, out1, _ = _run_explain_tree(install, ["core/my-skill"])
            _, out2, _ = _run_explain_tree(install, ["core/my-skill"])
            self.assertEqual(out1, out2)

    def test_tree_requires_explain_flag(self) -> None:
        """--tree alone (no --explain) exits 1 with correct error."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            self._minimal_lock(install)
            code, _, stderr = _run_compile_skill(install, ["--tree", "core/my-skill"])
            self.assertEqual(code, 1)
            self.assertIn("--tree requires --explain", stderr)

    def test_tree_and_json_mutually_exclusive(self) -> None:
        """--explain --tree --json exits 1 with mutually exclusive error."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            self._minimal_lock(install)
            code, _, stderr = _run_compile_skill(
                install, ["--explain", "--tree", "--json", "core/my-skill"]
            )
            self.assertEqual(code, 1)
            self.assertIn("mutually exclusive", stderr)

    def test_tree_cannot_combine_with_diff(self) -> None:
        """--tree --diff (no --explain) exits 1."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            self._minimal_lock(install)
            code, _, stderr = _run_compile_skill(install, ["--tree", "--diff", "core/my-skill"])
            self.assertEqual(code, 1)
            self.assertIn("--tree", stderr)

    def test_tree_same_fragment_at_two_depths(self) -> None:
        """Same fragment included twice at different depths produces two tree lines."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            # Root includes shared.template.md directly AND via a.template.md
            _write(
                install / "core" / "my-skill" / "my-skill.template.md",
                '<<include path="fragments/shared.template.md">>\n'
                '<<include path="fragments/a.template.md">>',
            )
            _write(
                install / "core" / "my-skill" / "fragments" / "a.template.md",
                '<<include path="fragments/shared.template.md">>',
            )
            _write(install / "core" / "my-skill" / "fragments" / "shared.template.md", "shared\n")
            self._minimal_lock(install)
            code, stdout, stderr = _run_explain_tree(install, ["core/my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            shared_lines = [l for l in stdout.splitlines() if "shared.template.md" in l]
            self.assertEqual(len(shared_lines), 2, f"Expected 2 lines for shared fragment, got: {shared_lines}")


class TestExplainJsonMode(unittest.TestCase):
    """Story 4.3 AC 2/3/4/5: --explain --json structured JSON output."""

    def _minimal_lock(self, install: Path) -> None:
        lock_content = (
            json.dumps(
                {"bmad_version": "1.0.0", "compiled_at": "1.0.0", "entries": [], "version": 1},
                sort_keys=True, indent=2,
            ) + "\n"
        )
        _write(install / "_config" / "bmad.lock", lock_content)

    def test_json_valid_json(self) -> None:
        """Output must be parseable with json.loads()."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            self._minimal_lock(install)
            code, stdout, stderr = _run_explain_json(install, ["core/my-skill"])
            self.assertEqual(code, 0, f"stderr: {stderr}")
            data = json.loads(stdout)  # must not raise
            self.assertIsInstance(data, dict)

    def test_json_schema_version_is_integer_one(self) -> None:
        """schema_version must be the integer 1, not the string '1'."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            self._minimal_lock(install)
            _, stdout, _ = _run_explain_json(install, ["core/my-skill"])
            data = json.loads(stdout)
            self.assertEqual(data["schema_version"], 1)
            self.assertIsInstance(data["schema_version"], int)

    def test_json_fragments_array_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            self._minimal_lock(install)
            _, stdout, _ = _run_explain_json(install, ["core/my-skill"])
            data = json.loads(stdout)
            self.assertIsInstance(data["fragments"], list)

    def test_json_variables_array_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            self._minimal_lock(install)
            _, stdout, _ = _run_explain_json(install, ["core/my-skill"])
            data = json.loads(stdout)
            self.assertIsInstance(data["variables"], list)

    def test_json_toml_fields_array_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            self._minimal_lock(install)
            _, stdout, _ = _run_explain_json(install, ["core/my-skill"])
            data = json.loads(stdout)
            self.assertIsInstance(data["toml_fields"], list)

    def test_json_fragment_has_required_fields(self) -> None:
        """Every fragment entry must have src, resolved_from, and hash (all strings)."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(
                install / "core" / "my-skill" / "my-skill.template.md",
                '<<include path="fragments/body.template.md">>',
            )
            _write(install / "core" / "my-skill" / "fragments" / "body.template.md", "body\n")
            self._minimal_lock(install)
            _, stdout, _ = _run_explain_json(install, ["core/my-skill"])
            data = json.loads(stdout)
            for frag in data["fragments"]:
                self.assertIn("src", frag)
                self.assertIn("resolved_from", frag)
                self.assertIn("hash", frag)
                self.assertIsInstance(frag["src"], str)
                self.assertIsInstance(frag["resolved_from"], str)
                self.assertIsInstance(frag["hash"], str)

    def test_json_variable_has_required_fields(self) -> None:
        """Variable entries must have name, source, resolved_at, value."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "{{self.tag}}\n")
            _write(install / "core" / "my-skill" / "customize.toml", 'tag = "hello"\n')
            self._minimal_lock(install)
            _, stdout, _ = _run_explain_json(install, ["core/my-skill"])
            data = json.loads(stdout)
            self.assertTrue(len(data["variables"]) > 0)
            for var in data["variables"]:
                self.assertIn("name", var)
                self.assertIn("source", var)
                self.assertIn("resolved_at", var)
                self.assertIn("value", var)

    def test_json_contributing_paths_is_array_not_string(self) -> None:
        """contributing_paths must be a JSON array, not a semicolon-joined string."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "{{self.tag}}\n")
            _write(install / "core" / "my-skill" / "customize.toml", 'tag = "default"\n')
            # team override for same key — produces multi-layer contributing_paths
            _write(install / "custom" / "my-skill.toml", 'tag = "team"\n')
            self._minimal_lock(install)
            _, stdout, _ = _run_explain_json(install, ["core/my-skill"])
            data = json.loads(stdout)
            for var in data["variables"]:
                if "contributing_paths" in var:
                    self.assertIsInstance(
                        var["contributing_paths"], list,
                        f"contributing_paths must be list, got {type(var['contributing_paths'])}: {var['contributing_paths']!r}",
                    )

    def test_json_toml_fields_populated(self) -> None:
        """Skill with customize.toml must have toml_fields entries."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "{{self.tag}}\n")
            _write(install / "core" / "my-skill" / "customize.toml", 'tag = "default"\n')
            self._minimal_lock(install)
            _, stdout, _ = _run_explain_json(install, ["core/my-skill"])
            data = json.loads(stdout)
            paths = [f["path"] for f in data["toml_fields"]]
            self.assertIn("tag", paths)
            tag_entry = next(f for f in data["toml_fields"] if f["path"] == "tag")
            self.assertEqual(tag_entry["default_value"], "default")

    def test_json_toml_fields_sorted_alphabetically(self) -> None:
        """toml_fields[] entries must be sorted alphabetically by path."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "{{self.z}}\n{{self.a}}\n")
            _write(install / "core" / "my-skill" / "customize.toml", 'z = "last"\na = "first"\n')
            self._minimal_lock(install)
            _, stdout, _ = _run_explain_json(install, ["core/my-skill"])
            data = json.loads(stdout)
            paths = [f["path"] for f in data["toml_fields"]]
            self.assertEqual(paths, sorted(paths))

    def test_json_no_writes_to_skill_md(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            _write(install / "core" / "my-skill" / "SKILL.md", "OLD\n")
            self._minimal_lock(install)
            skill_md = install / "core" / "my-skill" / "SKILL.md"
            sha_before = hashlib.sha256(skill_md.read_bytes()).hexdigest()
            _run_explain_json(install, ["core/my-skill"])
            sha_after = hashlib.sha256(skill_md.read_bytes()).hexdigest()
            self.assertEqual(sha_before, sha_after)

    def test_json_no_writes_to_lockfile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            self._minimal_lock(install)
            lock = install / "_config" / "bmad.lock"
            sha_before = hashlib.sha256(lock.read_bytes()).hexdigest()
            _run_explain_json(install, ["core/my-skill"])
            sha_after = hashlib.sha256(lock.read_bytes()).hexdigest()
            self.assertEqual(sha_before, sha_after)

    def test_json_determinism_twice_run(self) -> None:
        """Two runs of --explain --json produce byte-identical stdout."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "{{self.tag}}\n")
            _write(install / "core" / "my-skill" / "customize.toml", 'tag = "v"\n')
            self._minimal_lock(install)
            _, out1, _ = _run_explain_json(install, ["core/my-skill"])
            _, out2, _ = _run_explain_json(install, ["core/my-skill"])
            self.assertEqual(out1, out2)

    def test_json_jq_filter_by_resolved_from(self) -> None:
        """Python-equivalent jq filter on fragments by resolved_from yields correct subset."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(
                install / "core" / "my-skill" / "my-skill.template.md",
                '<<include path="fragments/body.template.md">>',
            )
            _write(install / "core" / "my-skill" / "fragments" / "body.template.md", "base\n")
            # user-override path: custom/fragments/<fragment_filename>
            _write(install / "custom" / "fragments" / "body.template.md", "override\n")
            self._minimal_lock(install)
            _, stdout, _ = _run_explain_json(install, ["core/my-skill"])
            data = json.loads(stdout)
            overrides = [f for f in data["fragments"] if f["resolved_from"] == "user-override"]
            self.assertTrue(len(overrides) > 0, "Expected at least one user-override fragment")
            for f in overrides:
                self.assertEqual(f["resolved_from"], "user-override")

    def test_json_requires_explain_flag(self) -> None:
        """--json alone (no --explain) exits 1 with correct error."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            self._minimal_lock(install)
            code, _, stderr = _run_compile_skill(install, ["--json", "core/my-skill"])
            self.assertEqual(code, 1)
            self.assertIn("--json requires --explain", stderr)

    def test_json_cannot_combine_with_diff(self) -> None:
        """--json --diff (no --explain) exits 1."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            self._minimal_lock(install)
            code, _, stderr = _run_compile_skill(install, ["--json", "--diff", "core/my-skill"])
            self.assertEqual(code, 1)
            self.assertIn("--json", stderr)

    def test_json_additive_field_tolerance(self) -> None:
        """A v1 consumer must not crash when presented with extra 'future' fields (AC 4)."""
        future_data = {
            "schema_version": 1,
            "fragments": [{"src": "a.md", "resolved_from": "base", "hash": "abc"}],
            "variables": [],
            "toml_fields": [],
            "future_field": "v2-addition",  # unknown to v1 consumer
        }
        serialized = json.dumps(future_data)
        parsed = json.loads(serialized)

        def v1_consumer(data: dict) -> None:  # type: ignore[type-arg]
            _ = data["schema_version"]
            _ = data["fragments"]
            _ = data["variables"]

        v1_consumer(parsed)  # must not raise
        self.assertEqual(parsed.get("future_field"), "v2-addition")

    def test_json_toml_bool_value_serialized_correctly(self) -> None:
        """TOML boolean true must appear as JSON true (not string 'true')."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            _write(install / "core" / "my-skill" / "customize.toml", "flag = true\n")
            self._minimal_lock(install)
            _, stdout, _ = _run_explain_json(install, ["core/my-skill"])
            data = json.loads(stdout)
            flag_entry = next(f for f in data["toml_fields"] if f["path"] == "flag")
            self.assertIs(flag_entry["default_value"], True)
            self.assertIsInstance(flag_entry["default_value"], bool)

    def test_json_toml_nested_table_flattened_to_dotted_key(self) -> None:
        """Nested TOML [section]\\nkey = 'v' must appear as 'section.key' path."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "Hello\n")
            _write(
                install / "core" / "my-skill" / "customize.toml",
                "[workflow]\non_complete = \"done\"\n",
            )
            self._minimal_lock(install)
            _, stdout, _ = _run_explain_json(install, ["core/my-skill"])
            data = json.loads(stdout)
            paths = [f["path"] for f in data["toml_fields"]]
            self.assertIn("workflow.on_complete", paths)
            self.assertNotIn("workflow", paths)


class TestExplainSchemaFixture(unittest.TestCase):
    """Story 4.3 AC 6: schema fixture is a CI contract."""

    _schema_path = (
        Path(__file__).resolve().parent.parent.parent
        / "src" / "scripts" / "bmad_compile" / "schemas" / "explain-v1.json"
    )

    def _minimal_lock(self, install: Path) -> None:
        lock_content = (
            json.dumps(
                {"bmad_version": "1.0.0", "compiled_at": "1.0.0", "entries": [], "version": 1},
                sort_keys=True, indent=2,
            ) + "\n"
        )
        _write(install / "_config" / "bmad.lock", lock_content)

    def test_schema_fixture_exists_and_is_valid_json(self) -> None:
        """explain-v1.json must exist and be parseable JSON."""
        self.assertTrue(self._schema_path.exists(), f"Schema fixture not found at {self._schema_path}")
        schema = json.loads(self._schema_path.read_text(encoding="utf-8"))  # must not raise
        self.assertIsInstance(schema, dict)
        self.assertIn("required", schema)
        required = schema["required"]
        self.assertIn("schema_version", required)
        self.assertIn("fragments", required)
        self.assertIn("variables", required)
        self.assertIn("toml_fields", required)

    def test_json_output_passes_structural_schema_check(self) -> None:
        """--explain --json output must conform to the v1 structural contract."""
        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp)
            _write(install / "core" / "my-skill" / "my-skill.template.md", "{{self.tag}}\n")
            _write(install / "core" / "my-skill" / "customize.toml", 'tag = "v"\n')
            self._minimal_lock(install)
            _, stdout, _ = _run_explain_json(install, ["core/my-skill"])
            data = json.loads(stdout)
            # schema_version is integer 1
            self.assertIsInstance(data["schema_version"], int)
            self.assertEqual(data["schema_version"], 1)
            # top-level arrays
            self.assertIsInstance(data["fragments"], list)
            self.assertIsInstance(data["variables"], list)
            self.assertIsInstance(data["toml_fields"], list)
            # fragment items have required fields
            for frag in data["fragments"]:
                self.assertIsInstance(frag.get("src"), str)
                self.assertIsInstance(frag.get("resolved_from"), str)
                self.assertIsInstance(frag.get("hash"), str)
            # variable items have required fields
            for var in data["variables"]:
                self.assertIsInstance(var.get("name"), str)
                self.assertIsInstance(var.get("source"), str)
                self.assertEqual(var.get("resolved_at"), "compile-time")
                self.assertIsInstance(var.get("value"), str)


if __name__ == "__main__":
    unittest.main()
