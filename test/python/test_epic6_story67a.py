import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]  # BMAD-METHOD/
_COMPILE_PY = _REPO_ROOT / "src" / "scripts" / "compile.py"
_SKILL_SRC = _REPO_ROOT / "src" / "core-skills" / "bmad-customize"


class TestTemplateSource(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        # Two-level-deep copy: engine override_root = skill.parent.parent/_bmad/custom = tmpdir/_bmad/custom
        # (fully inside tmpdir; no src/_bmad/custom/ mutation from test runs)
        self.skill_copy = self.tmpdir / "src" / "bmad-customize"
        shutil.copytree(str(_SKILL_SRC), str(self.skill_copy))
        self.install_dir = self.tmpdir / "install"
        self.install_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_compile_exits_zero(self):
        result = subprocess.run(
            [sys.executable, str(_COMPILE_PY),
             "--skill", str(self.skill_copy),
             "--install-dir", str(self.install_dir)],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_skill_md_written(self):
        subprocess.run(
            [sys.executable, str(_COMPILE_PY),
             "--skill", str(self.skill_copy),
             "--install-dir", str(self.install_dir)],
            capture_output=True, text=True, check=True
        )
        skill_md = self.install_dir / "bmad-customize" / "SKILL.md"
        self.assertTrue(skill_md.exists(), f"SKILL.md not found at {skill_md}")
        self.assertGreater(skill_md.stat().st_size, 0, "SKILL.md is empty")

    def test_skill_md_content(self):
        # Functional equivalence check: key section headers must appear in compiled output.
        subprocess.run(
            [sys.executable, str(_COMPILE_PY),
             "--skill", str(self.skill_copy),
             "--install-dir", str(self.install_dir)],
            capture_output=True, text=True, check=True
        )
        skill_md = self.install_dir / "bmad-customize" / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        for header in (
            "## Preflight", "## Activation",
            "## Step 1", "## Step 2", "## Step 3", "## Step 4", "## Step 5", "## Step 6",
            "## Complete when", "## When this skill can't help",
        ):
            self.assertIn(header, content, f"Missing section: {header}")
        # Frontmatter variables must be resolved to concrete values.
        self.assertIn("name: bmad-customize", content, "Frontmatter {{self.name}} not resolved")
        # Verify no unresolved compile-time markers remain.
        self.assertNotIn("{{", content, "Unresolved {{ marker in compiled output")
        self.assertNotIn("<<include", content, "Unresolved <<include in compiled output")
