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


if __name__ == "__main__":
    unittest.main()
