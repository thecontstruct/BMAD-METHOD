"""Self-contained compile coverage for the bounded prompt-protocol pilots."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


_REPO = Path(__file__).resolve().parent.parent.parent
_COMPILE = _REPO / "src" / "scripts" / "compile.py"
_SHARED = _REPO / "src" / "_shared"
_SOURCES = {
    "bmad-agent-dev": _REPO / "src" / "bmm-skills" / "agents" / "bmad-agent-dev",
    "bmad-code-review": _REPO / "src" / "bmm-skills" / "ship" / "bmad-code-review",
}


def _materialize_install(root: Path) -> None:
    """Create the smallest install tree needed to compile both pilot skills."""
    shutil.copytree(_SHARED, root / "_shared")
    for name, source in _SOURCES.items():
        shutil.copytree(source, root / "bmm" / name)
    (root / "_config").mkdir(parents=True)


def _compile_install(root: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(_COMPILE), "--install-phase", "--install-dir", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise AssertionError(f"compile failed:\nstdout={result.stdout}\nstderr={result.stderr}")


class TestPromptProtocolPilots(unittest.TestCase):
    def test_pilots_compile_from_a_materialized_install_with_shared_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            install = Path(temp) / "_bmad"
            _materialize_install(install)
            _compile_install(install)

            agent = (install / "bmm" / "bmad-agent-dev" / "SKILL.md").read_text(encoding="utf-8")
            review = (install / "bmm" / "bmad-code-review" / "steps" / "step-02-review.md").read_text(encoding="utf-8")
            lock = json.loads((install / "_config" / "bmad.lock").read_text(encoding="utf-8"))

            self.assertIn("--skill {skill-root} --key agent", agent)
            self.assertIn("Adopt the Amelia / Senior Software Engineer identity", agent)
            self.assertIn("Entries prefixed `file:`", agent)
            self.assertIn("Do not begin the main workflow until all activation steps have been completed.", agent)
            self.assertIn("Otherwise render `{agent.menu}` as a numbered table", agent)

            context_index = review.index("Collect all findings from the completed layers")
            gate_index = review.index("## Evidence Gate — the collected code-review findings")
            self.assertGreater(gate_index, context_index)
            self.assertIn("`source` — originating review-layer `id`", review)
            self.assertIn("`title` — one-line claim", review)
            self.assertIn("`detail` — the evidence, impact, and smallest credible remediation", review)
            self.assertIn("`location` — file and line reference when available", review)
            self.assertIn("Do not assign final severity, bucket, or a PASS/FAIL verdict here", review)

            component_paths = {
                component["path"].replace("\\", "/")
                for entry in lock["entries"]
                for component in entry.get("components", [])
            }
            self.assertIn("_shared/components/workflow_shell.py", component_paths)
            self.assertIn("_shared/components/evidence_gate.py", component_paths)
            reference_components = _REPO / "src" / "core-skills" / "bmad-reference-components" / "components"
            self.assertFalse((reference_components / "workflow_shell.py").exists())
            self.assertFalse((reference_components / "evidence_gate.py").exists())

    def test_recompiling_the_materialized_install_is_deterministic(self):
        with tempfile.TemporaryDirectory() as temp:
            install = Path(temp) / "_bmad"
            _materialize_install(install)
            _compile_install(install)
            first = (install / "bmm" / "bmad-agent-dev" / "SKILL.md").read_bytes()
            _compile_install(install)
            self.assertEqual(first, (install / "bmm" / "bmad-agent-dev" / "SKILL.md").read_bytes())
