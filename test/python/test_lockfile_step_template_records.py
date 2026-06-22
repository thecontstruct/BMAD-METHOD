"""Story 10.63 AC-10: lockfile accepts step-template artifact records and parent field.

Tests:
- AC-10: step-template kind in artifacts[] round-trips through write_skill_entry
- AC-10: components[].parent field is preserved in lockfile records
- AC-10: lockfile version stays at v4 (no bump)
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_SCRIPTS = str(_PROJECT_ROOT / "src" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from bmad_compile import lockfile
from bmad_compile.io import PurePosixPath


class TestStepTemplateKindAccepted(unittest.TestCase):
    """AC-10: step-template records write and round-trip correctly."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        lf_dir = self.tmp / "_bmad" / "_config"
        lf_dir.mkdir(parents=True)
        self.lf_path = str(lf_dir / "bmad.lock")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_scenario(self) -> PurePosixPath:
        from bmad_compile.io import to_posix
        return to_posix(self.tmp)

    def _dep_tree(self, source_text: str):
        from bmad_compile import parser, resolver
        var_scope = resolver.VariableScope({})
        cache = resolver.CompileCache()
        scenario = self._make_scenario()
        skill_dir = scenario / "core" / "test-skill"
        context = resolver.ResolveContext(
            skill_dir=skill_dir,
            module_roots={"core": skill_dir.parent},
            current_module="core",
            scenario_root=scenario,
            override_root=None,
            target_ide=None,
            var_scope=var_scope,
            explain_mode=False,
        )
        parsed = parser.parse(source_text, "test-skill/test-skill.template.md")
        flat, dep_tree = resolver.resolve(parsed, context, cache,
                                          root_src="test-skill/test-skill.template.md",
                                          root_path=skill_dir / "test-skill.template.md",
                                          root_source=source_text)
        return dep_tree, var_scope, cache

    def test_step_template_kind_accepted(self) -> None:
        """AC-10: write_skill_entry stores step-template artifact record."""
        source = "# Skill\n"
        dep_tree, var_scope, cache = self._dep_tree(source)
        artifacts = [
            {
                "kind": "step-template",
                "path": "step-01.md",
                "hash": "abc123",
                "source_hash": "def456",
                "variant": None,
            }
        ]
        lockfile.write_skill_entry(
            self.lf_path,
            self._make_scenario(),
            "test-skill",
            source_text=source,
            compiled_text=source,
            dep_tree=dep_tree,
            var_scope=var_scope,
            target_ide=None,
            cache=cache,
            artifacts=artifacts,
        )
        data = json.loads(Path(self.lf_path).read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 4)
        entry = next(e for e in data["entries"] if e["skill"] == "test-skill")
        self.assertEqual(len(entry["artifacts"]), 1)
        art = entry["artifacts"][0]
        self.assertEqual(art["kind"], "step-template")
        self.assertEqual(art["path"], "step-01.md")
        self.assertEqual(art["source_hash"], "def456")

    def test_component_parent_field_preserved(self) -> None:
        """AC-10: components[].parent value round-trips through the lockfile."""
        source = "# Skill\n"
        dep_tree, var_scope, cache = self._dep_tree(source)
        components = [
            {
                "name": "ToolsList",
                "path": "components/tools_list.py",
                "source_hash": "aaa",
                "render_mode": "compile",
                "props": {},
                "props_hash": "bbb",
                "compiled_hash": "ccc",
                "sentinel_format_version": None,
                "data_files": [],
                "parent": "SKILL.md",
            },
            {
                "name": "ToolsList",
                "path": "components/tools_list.py",
                "source_hash": "aaa",
                "render_mode": "compile",
                "props": {},
                "props_hash": "bbb",
                "compiled_hash": "ccc",
                "sentinel_format_version": None,
                "data_files": [],
                "parent": "step-04.md",
            },
        ]
        lockfile.write_skill_entry(
            self.lf_path,
            self._make_scenario(),
            "test-skill",
            source_text=source,
            compiled_text=source,
            dep_tree=dep_tree,
            var_scope=var_scope,
            target_ide=None,
            cache=cache,
            components=components,
        )
        data = json.loads(Path(self.lf_path).read_text(encoding="utf-8"))
        entry = next(e for e in data["entries"] if e["skill"] == "test-skill")
        self.assertEqual(len(entry["components"]), 2)
        parents = {c["parent"] for c in entry["components"]}
        self.assertIn("SKILL.md", parents)
        self.assertIn("step-04.md", parents)

    def test_lockfile_version_stays_v4(self) -> None:
        """AC-10: no version bump — lockfile stays at v4 after step-template records."""
        source = "# Skill\n"
        dep_tree, var_scope, cache = self._dep_tree(source)
        lockfile.write_skill_entry(
            self.lf_path,
            self._make_scenario(),
            "test-skill",
            source_text=source,
            compiled_text=source,
            dep_tree=dep_tree,
            var_scope=var_scope,
            target_ide=None,
            cache=cache,
            artifacts=[{"kind": "step-template", "path": "x.md", "hash": "h",
                        "source_hash": "sh", "variant": "cursor"}],
        )
        data = json.loads(Path(self.lf_path).read_text(encoding="utf-8"))
        self.assertEqual(data["version"], 4)


if __name__ == "__main__":
    unittest.main()
