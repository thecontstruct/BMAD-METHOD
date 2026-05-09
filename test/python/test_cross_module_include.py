"""Cross-module include resolution tests (Story 7.6 AC-5 / AC-6).

AC-5: A third-party skill template using `<<include path="core/<frag>">>` resolves
to a fragment under the core module's directory and the lockfile records the
resolved path spanning the module boundary.

AC-6: A third-party skill template using `<<include path="other-third-party/<frag>">>`
raises `PrecedenceUndefinedError` (cross-third-party includes not allowed).
Only `core/` and the author's own module namespace are permitted as cross-module
prefixes.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.scripts.bmad_compile import engine, errors


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


class TestCrossModuleCoreIncludeResolves(unittest.TestCase):
    """AC-5 — `<<include path="core/...">>` from a third-party skill resolves
    against the core module's tree and the lockfile records the resolved path."""

    def test_core_include_resolves_and_lockfile_records_cross_module_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            install = scenario / "install"
            install.mkdir()

            # Core module: provides the fragment.
            core_fragment = install / "core" / "fragments" / "persona-guard.template.md"
            _write(core_fragment, "shared persona-guard body\n")

            # Third-party module: skill that includes the core fragment.
            third_party_skill = install / "third-party" / "test-skill"
            third_party_template = third_party_skill / "test-skill.template.md"
            _write(
                third_party_template,
                '<<include path="core/fragments/persona-guard.template.md">>\n'
                "third-party skill body\n",
            )

            # Override root must exist (engine creates the path otherwise).
            (install / "custom").mkdir(parents=True, exist_ok=True)

            # Compile the third-party skill against this install root.
            engine.compile_skill(
                third_party_skill,
                install,
                lockfile_root=install,
                override_root=install / "custom",
            )

            # AC-5 assertion 1: compiled output contains the inlined core fragment text.
            compiled_path = install / "third-party" / "test-skill" / "SKILL.md"
            self.assertTrue(compiled_path.exists(), f"compiled SKILL.md missing at {compiled_path}")
            compiled = compiled_path.read_text(encoding="utf-8")
            self.assertIn("shared persona-guard body", compiled)

            # AC-5 assertion 2: bmad.lock records the resolved path that spans the
            # module boundary (the fragment lives under core/, the skill under third-party/).
            lockfile_path = install / "_config" / "bmad.lock"
            self.assertTrue(lockfile_path.exists(), f"bmad.lock missing at {lockfile_path}")
            lock = json.loads(lockfile_path.read_text(encoding="utf-8"))
            entries = lock["entries"]
            self.assertEqual(len(entries), 1, f"expected 1 entry, got {len(entries)}: {entries}")
            entry = entries[0]
            fragments = entry.get("fragments", [])
            paths = [f["path"] for f in fragments]
            # The cross-module fragment path (relative to scenario_root) must appear.
            cross_module_paths = [p for p in paths if "core/fragments/persona-guard.template.md" in p]
            self.assertTrue(
                cross_module_paths,
                f"lockfile fragments do not record cross-module path; got paths={paths}",
            )


class TestCrossThirdPartyIncludeBlocked(unittest.TestCase):
    """AC-6 — `<<include path="other-third-party/...">>` raises PrecedenceUndefinedError."""

    def test_cross_third_party_include_blocked_with_precedence_undefined(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            scenario = Path(tmp)
            install = scenario / "install"
            install.mkdir()

            # module-a: skill attempting to include a fragment from module-b.
            module_a_skill = install / "module-a" / "test-skill"
            _write(
                module_a_skill / "test-skill.template.md",
                '<<include path="module-b/private-fragment.template.md">>\n'
                "module-a skill body\n",
            )

            # module-b: third-party module that exists (so module_roots picks it up)
            # but is NOT supposed to be reachable from module-a's includes.
            _write(
                install / "module-b" / "private-fragment.template.md",
                "private fragment body\n",
            )

            # Override root.
            (install / "custom").mkdir(parents=True, exist_ok=True)

            with self.assertRaises(errors.PrecedenceUndefinedError) as ctx:
                engine.compile_skill(
                    module_a_skill,
                    install,
                    lockfile_root=install,
                    override_root=install / "custom",
                )

            err = ctx.exception
            self.assertEqual(err.code, errors.ErrorCode.PRECEDENCE_UNDEFINED.value)
            self.assertIn("module-b", err.desc)
            self.assertIn("module-a", err.desc)


if __name__ == "__main__":
    unittest.main()
