"""Keep-contract tests for the bmad-help reference skill (Story 2.2 AC 3).

Asserts that engine.compile_skill produces byte-identical output to the
checked-in frozen baseline at src/core-skills/bmad-help/SKILL.md.

Each test method creates its own tempdir and copytree so tests are fully
independent.  The copytree hermetic pattern keeps the engine's default
lockfile derivation (skill_dir.parent.parent / "_bmad") inside the tempdir,
preventing source-tree pollution on every run.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "src" / "scripts"))

from bmad_compile import engine  # noqa: E402

_SOURCE_SKILL_DIR = _REPO / "src" / "core-skills" / "bmad-help"


class TestBmadHelpKeepContract(unittest.TestCase):
    def setUp(self) -> None:
        self._baseline_bytes = (_SOURCE_SKILL_DIR / "SKILL.md").read_bytes()

    def _compile_in_tmp(self, tmp: Path) -> bytes:
        """Copy skill dir into tmp, compile, return output bytes."""
        skill_copy = tmp / "skill_root" / "core-skills" / "bmad-help"
        shutil.copytree(_SOURCE_SKILL_DIR, skill_copy)
        install_dir = tmp / "install"
        engine.compile_skill(
            skill_dir=skill_copy,
            install_dir=install_dir,
            target_ide=None,
        )
        return (install_dir / "bmad-help" / "SKILL.md").read_bytes()

    def test_compile_output_byte_identical_to_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            tmp = Path(raw_tmp)
            output = self._compile_in_tmp(tmp)
        self.assertEqual(
            output,
            self._baseline_bytes,
            "Compiled output differs from the checked-in SKILL.md baseline.",
        )

    def test_repeat_compile_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as raw1:
            output1 = self._compile_in_tmp(Path(raw1))
        with tempfile.TemporaryDirectory() as raw2:
            output2 = self._compile_in_tmp(Path(raw2))
        self.assertEqual(output1, self._baseline_bytes, "First compile differs from baseline.")
        self.assertEqual(output2, self._baseline_bytes, "Second compile differs from baseline.")
        self.assertEqual(output1, output2, "Two compile runs produced different output.")

    def test_compile_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as raw_tmp:
            self._compile_in_tmp(Path(raw_tmp))


if __name__ == "__main__":
    unittest.main()
