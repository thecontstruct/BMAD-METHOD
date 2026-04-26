"""Unit tests for bmad_compile.engine — root-template selection + override swap.

Most engine behavior is covered by the integration tests in
`test/python/integration/test_end_to_end.py` (which invoke `compile.py`
via subprocess). These tests exercise specific engine code paths that
are awkward to construct as fixtures — currently the override-tier
SKILL.template.md probe and its error-reporting contract.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.scripts.bmad_compile import engine, errors


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_skill(scenario_root: Path) -> Path:
    """Create the standard fixture layout under `scenario_root`:

        <scenario>/core/skill1/skill1.template.md
        <scenario>/_bmad/custom/  (override root, may be empty)

    Returns the skill directory.
    """
    skill = scenario_root / "core" / "skill1"
    _write(skill / "skill1.template.md", "base body")
    (scenario_root / "_bmad" / "custom").mkdir(parents=True, exist_ok=True)
    return skill


class TestOverrideTemplateProbe(unittest.TestCase):
    """R5-P1: a directory at the override SKILL.template.md slot must not
    pass the tier-1 probe — `is_file` (not `path_exists`) gates the swap."""

    def test_directory_at_override_slot_falls_through_to_base(self) -> None:
        """Pre-R5: `path_exists` returned True for the directory, the engine
        committed to it as the root template, and `read_template` raised a
        raw `IsADirectoryError` / `PermissionError` outside the
        `CompilerError` taxonomy. Post-R5: the directory fails the
        `is_file` probe, the engine falls back to the base template, and
        compile succeeds normally."""
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = _build_skill(scenario)
            # A directory at the slot the engine probes for the override.
            (
                scenario / "_bmad" / "custom"
                / "fragments" / "core" / "skill1" / "SKILL.template.md"
            ).mkdir(parents=True)

            install = scenario / "install"
            engine.compile_skill(skill, install)
            out = install / "skill1" / "SKILL.md"
            self.assertTrue(out.is_file())
            self.assertEqual(out.read_text(encoding="utf-8"), "base body")


class TestOverrideErrorReporting(unittest.TestCase):
    """R5-P2: when the override SKILL.template.md is swapped in as the root,
    parse errors raised against it must report the override-rooted
    relative path — not the base-shaped `<basename>/SKILL.template.md`
    that would send authors to edit the wrong file."""

    def test_parse_error_in_override_reports_override_relative_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = _build_skill(scenario)
            override_template = (
                scenario / "_bmad" / "custom"
                / "fragments" / "core" / "skill1" / "SKILL.template.md"
            )
            # Malformed directive — triggers UnknownDirectiveError at parse.
            _write(override_template, "<<not_an_include>>")

            install = scenario / "install"
            with self.assertRaises(errors.UnknownDirectiveError) as cm:
                engine.compile_skill(skill, install)
            # The error's file field must point at the override-rooted
            # path, not the base-shaped `skill1/SKILL.template.md`.
            self.assertEqual(
                cm.exception.file,
                "fragments/core/skill1/SKILL.template.md",
            )


class TestFindTemplateDirectoryFilter(unittest.TestCase):
    """R6-P2: a directory whose name happens to end in `.template.md` must
    not be selected by `_find_template` as the root template — the entry
    must be a regular file. Pre-R6 the directory passed the suffix filter,
    was returned as the root template, and crashed in `read_template` with
    a raw `IsADirectoryError` outside the `CompilerError` taxonomy."""

    def test_find_template_skips_directory_with_matching_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = scenario / "core" / "skill1"
            skill.mkdir(parents=True)
            # A directory whose name matches the preferred-template form.
            (skill / "skill1.template.md").mkdir()
            # An adjacent real *.template.md file the engine should fall
            # through to.
            _write(skill / "other.template.md", "fallback body")
            (scenario / "_bmad" / "custom").mkdir(parents=True, exist_ok=True)

            install = scenario / "install"
            engine.compile_skill(skill, install)
            out = install / "skill1" / "SKILL.md"
            self.assertTrue(out.is_file())
            self.assertEqual(out.read_text(encoding="utf-8"), "fallback body")


class TestVariantSelection(unittest.TestCase):
    """Story 1.4 — target_ide wiring and variant-aware root-template selection."""

    def test_compile_target_ide_cursor_selects_cursor_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = scenario / "core" / "skill1"
            _write(skill / "skill1.cursor.template.md", "cursor body")
            _write(skill / "skill1.template.md", "universal body")
            (scenario / "_bmad" / "custom").mkdir(parents=True, exist_ok=True)

            install = scenario / "install"
            engine.compile_skill(skill, install, target_ide="cursor")
            out = install / "skill1" / "SKILL.md"
            self.assertEqual(out.read_text(encoding="utf-8"), "cursor body")

    def test_compile_target_ide_none_selects_universal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = scenario / "core" / "skill1"
            _write(skill / "skill1.cursor.template.md", "cursor body")
            _write(skill / "skill1.template.md", "universal body")
            (scenario / "_bmad" / "custom").mkdir(parents=True, exist_ok=True)

            install = scenario / "install"
            engine.compile_skill(skill, install, target_ide=None)
            out = install / "skill1" / "SKILL.md"
            self.assertEqual(out.read_text(encoding="utf-8"), "universal body")

    def test_compile_target_ide_unknown_falls_back_to_universal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = scenario / "core" / "skill1"
            _write(skill / "skill1.cursor.template.md", "cursor body")
            _write(skill / "skill1.template.md", "universal body")
            (scenario / "_bmad" / "custom").mkdir(parents=True, exist_ok=True)

            install = scenario / "install"
            engine.compile_skill(skill, install, target_ide="vscode")
            out = install / "skill1" / "SKILL.md"
            self.assertEqual(out.read_text(encoding="utf-8"), "universal body")

    def test_compile_missing_template_raises_missing_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = scenario / "core" / "skill1"
            skill.mkdir(parents=True)  # no *.template.md
            (scenario / "_bmad" / "custom").mkdir(parents=True, exist_ok=True)

            install = scenario / "install"
            with self.assertRaises(errors.MissingFragmentError):
                engine.compile_skill(skill, install)

    def test_missing_template_hint_mentions_ide_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = scenario / "core" / "skill1"
            _write(skill / "skill1.cursor.template.md", "cursor-body")
            (scenario / "_bmad" / "custom").mkdir(parents=True, exist_ok=True)

            install = scenario / "install"
            install.mkdir()
            with self.assertRaises(errors.MissingFragmentError) as cm:
                engine.compile_skill(skill, install, target_ide=None)
            self.assertIn("Found IDE-specific variants for: cursor", cm.exception.hint)
            self.assertIn("--tools", cm.exception.hint)

    def test_compile_resolves_user_only_toml_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = scenario / "core" / "skill1"
            _write(skill / "skill1.template.md", "Agent: {{self.agent.name}}")
            # No customize.toml defaults; user TOML only via override root.
            override = scenario / "_bmad" / "custom"
            _write(override / "skill1.user.toml", '[agent]\nname = "UserAgent"\n')

            install = scenario / "install"
            engine.compile_skill(skill, install)
            out = install / "skill1" / "SKILL.md"
            self.assertEqual(out.read_text(encoding="utf-8"), "Agent: UserAgent")

    def test_compile_resolves_team_only_toml_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = scenario / "core" / "skill1"
            _write(skill / "skill1.template.md", "Agent: {{self.agent.name}}")
            # Team TOML only via override root — no user layer.
            override = scenario / "_bmad" / "custom"
            _write(override / "skill1.toml", '[agent]\nname = "TeamAgent"\n')

            install = scenario / "install"
            engine.compile_skill(skill, install)
            out = install / "skill1" / "SKILL.md"
            self.assertEqual(out.read_text(encoding="utf-8"), "Agent: TeamAgent")

    def test_compile_skill_dir_lookup_is_case_sensitive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            # Probe filesystem case-sensitivity.
            probe_dir = scenario / "probe"
            probe_dir.mkdir()
            if (scenario / "PROBE").is_dir():
                self.skipTest("filesystem is case-insensitive (Windows-default / macOS-APFS)")
            # Real test: write skill at lowercase path, look up at uppercase path.
            skill_lower = scenario / "core" / "skill1"
            _write(skill_lower / "skill1.template.md", "baseline body")
            (scenario / "_bmad" / "custom").mkdir(parents=True, exist_ok=True)
            install = scenario / "install"
            skill_upper = scenario / "core" / "Skill1"  # capital S
            with self.assertRaises(NotADirectoryError):
                engine.compile_skill(skill_upper, install)

    def test_missing_template_hint_mentions_unknown_ide_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = scenario / "core" / "skill1"
            # vscode is NOT in variants.KNOWN_IDES.
            # Pre-Story-1.8: _is_universal("skill1.vscode.template.md") == True →
            #   select_variant returns the file → engine compiles it as universal,
            #   never reaching the MissingFragmentError branch.
            # Post-Story-1.8: _is_universal returns False → select_variant returns None →
            #   engine raises MissingFragmentError with hint enumerating "vscode".
            _write(skill / "skill1.vscode.template.md", "vscode body")
            (scenario / "_bmad" / "custom").mkdir(parents=True, exist_ok=True)
            install = scenario / "install"
            with self.assertRaises(errors.MissingFragmentError) as cm:
                engine.compile_skill(skill, install, target_ide=None)
            self.assertIn("vscode", cm.exception.hint)
            self.assertIn("--tools", cm.exception.hint)

    def test_missing_template_hint_warns_when_target_ide_not_in_known_ides(self) -> None:
        # Regression: when --tools <unrecognized> is passed AND a file
        # matching that IDE shape exists, the hint must explain that the
        # IDE is not recognized rather than falling through to the generic
        # "create universal template" branch (which masks the real problem).
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = scenario / "core" / "skill1"
            # vscode is NOT in variants.KNOWN_IDES; file shape matches the
            # requested --tools value, so target_ide ends up in _detected_ides.
            _write(skill / "skill1.vscode.template.md", "vscode body")
            (scenario / "_bmad" / "custom").mkdir(parents=True, exist_ok=True)
            install = scenario / "install"
            with self.assertRaises(errors.MissingFragmentError) as cm:
                engine.compile_skill(skill, install, target_ide="vscode")
            self.assertIn("vscode", cm.exception.hint)
            self.assertIn("not a recognized IDE", cm.exception.hint)
            # KNOWN_IDES enumeration must be present so the author sees alternatives.
            self.assertIn("cursor", cm.exception.hint)


class TestVariableScopeWiring(unittest.TestCase):
    """Story 1.3 — VariableScope built and wired into compile pipeline."""

    def test_compile_resolves_yaml_variable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = scenario / "core" / "skill1"
            _write(skill / "skill1.template.md", "Hello {{user_name}}!")
            # Place config at <scenario>/_bmad/core/config.yaml
            _write(scenario / "_bmad" / "core" / "config.yaml", "user_name: World\n")
            (scenario / "_bmad" / "custom").mkdir(parents=True, exist_ok=True)

            install = scenario / "install"
            engine.compile_skill(skill, install)
            out = install / "skill1" / "SKILL.md"
            self.assertTrue(out.is_file())
            self.assertEqual(out.read_text(encoding="utf-8"), "Hello World!")

    def test_compile_passthrough_runtime_var(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = scenario / "core" / "skill1"
            _write(skill / "skill1.template.md", "Ref: {runtime_ref}.")
            (scenario / "_bmad" / "custom").mkdir(parents=True, exist_ok=True)

            install = scenario / "install"
            engine.compile_skill(skill, install)
            out = install / "skill1" / "SKILL.md"
            self.assertEqual(out.read_text(encoding="utf-8"), "Ref: {runtime_ref}.")

    def test_compile_resolves_self_toml_variable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = scenario / "core" / "skill1"
            _write(skill / "skill1.template.md", "Agent: {{self.agent.name}}")
            _write(skill / "customize.toml", '[agent]\nname = "Test Agent"\n')
            (scenario / "_bmad" / "custom").mkdir(parents=True, exist_ok=True)

            install = scenario / "install"
            engine.compile_skill(skill, install)
            out = install / "skill1" / "SKILL.md"
            self.assertEqual(out.read_text(encoding="utf-8"), "Agent: Test Agent")

    def test_compile_unresolved_var_exits_nonzero_no_partial_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = scenario / "core" / "skill1"
            _write(skill / "skill1.template.md", "{{undefined_var}}")
            (scenario / "_bmad" / "custom").mkdir(parents=True, exist_ok=True)

            install = scenario / "install"
            with self.assertRaises(errors.UnresolvedVariableError):
                engine.compile_skill(skill, install)
            # No SKILL.md should have been written.
            skill_md = install / "skill1" / "SKILL.md"
            self.assertFalse(skill_md.exists())

    def test_compile_var_scope_none_ok_for_text_only_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = scenario / "core" / "skill1"
            _write(skill / "skill1.template.md", "No variables here.")
            (scenario / "_bmad" / "custom").mkdir(parents=True, exist_ok=True)

            install = scenario / "install"
            engine.compile_skill(skill, install)
            out = install / "skill1" / "SKILL.md"
            self.assertEqual(out.read_text(encoding="utf-8"), "No variables here.")

    def test_existing_engine_suite_unchanged(self) -> None:
        """The override slot directory-filter test still passes."""
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            skill = _build_skill(scenario)
            install = scenario / "install"
            engine.compile_skill(skill, install)
            out = install / "skill1" / "SKILL.md"
            self.assertEqual(out.read_text(encoding="utf-8"), "base body")


if __name__ == "__main__":
    unittest.main()
