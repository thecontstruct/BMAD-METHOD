"""Story 10.63 AC-1: _extract_artifacts_from_frontmatter accepts kind: step-template.

Tests:
- AC-1: step-template kind parsed correctly from frontmatter YAML
- AC-1: source not ending with .template.md raises CompilerError with hint
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_SCRIPTS = str(_PROJECT_ROOT / "src" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from bmad_compile import errors
from bmad_compile.engine import Artifact, _extract_artifacts_from_frontmatter

STEP_TEMPLATE_FRONTMATTER = """\
---
name: example-skill
artifacts:
  - kind: step-template
    source: step-01.template.md
    path: step-01.md
---
# Skill body
"""

BAD_SOURCE_EXTENSION = """\
---
name: example-skill
artifacts:
  - kind: step-template
    source: step-01.md
    path: step-01.md
---
# Skill body
"""

MIXED_ARTIFACTS = """\
---
name: example-skill
artifacts:
  - kind: scaffold-verbatim
    source: data.csv
    path: data.csv
  - kind: step-template
    source: step-02.template.md
    path: step-02.md
---
# Skill body
"""


class TestStepTemplateArtifactExtraction(unittest.TestCase):

    def test_step_template_kind_parsed(self) -> None:
        """AC-1: kind=step-template produces an Artifact with correct fields."""
        result = _extract_artifacts_from_frontmatter(STEP_TEMPLATE_FRONTMATTER)
        self.assertEqual(len(result), 1)
        art = result[0]
        self.assertIsInstance(art, Artifact)
        self.assertEqual(art.kind, "step-template")
        self.assertEqual(art.source, "step-01.template.md")
        self.assertEqual(art.path, "step-01.md")

    def test_step_template_source_must_end_with_template_md(self) -> None:
        """AC-1: source not ending with .template.md raises CompilerError."""
        with self.assertRaises(errors.CompilerError) as ctx:
            _extract_artifacts_from_frontmatter(BAD_SOURCE_EXTENSION)
        msg = str(ctx.exception)
        self.assertIn(".template.md", msg)

    def test_mixed_scaffold_and_step_template_both_extracted(self) -> None:
        """AC-1: scaffold-verbatim and step-template can coexist in artifacts list."""
        result = _extract_artifacts_from_frontmatter(MIXED_ARTIFACTS)
        self.assertEqual(len(result), 2)
        kinds = {a.kind for a in result}
        self.assertIn("scaffold-verbatim", kinds)
        self.assertIn("step-template", kinds)


if __name__ == "__main__":
    unittest.main()
