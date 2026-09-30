"""Installation proof for the ticketing skill's shared method runtime."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from src.scripts.bmad_compile import engine


SKILL_SOURCE = REPOSITORY_ROOT / "src" / "bmm-skills" / "plan" / "bmad-preview-ticketing"
TEMPLATE_NAME = "bmad-preview-ticketing.template.md"


class TicketingRuntimeInstallTests(unittest.TestCase):
    def test_tickets_script_installs_once_at_the_shared_method_runtime_path(self) -> None:
        template = (SKILL_SOURCE / TEMPLATE_NAME).read_text(encoding="utf-8")
        artifacts = engine._extract_artifacts_from_frontmatter(template)
        runtime = [artifact for artifact in artifacts if artifact.kind == "method-runtime-verbatim"]
        self.assertEqual(
            [(artifact.path, artifact.source) for artifact in runtime],
            [("scripts/tickets.py", "scripts/tickets.py")],
        )

        with tempfile.TemporaryDirectory() as tmp:
            install = Path(tmp) / "_bmad"
            destination = install / "bmm" / "bmad-preview-ticketing"
            shutil.copytree(
                SKILL_SOURCE,
                destination,
                ignore=shutil.ignore_patterns("tests", "__pycache__", "*.pyc"),
            )
            (install / "custom").mkdir(parents=True)
            compile_script = REPOSITORY_ROOT / "src" / "scripts" / "compile.py"
            result = subprocess.run(
                [sys.executable, str(compile_script), "--install-phase", "--install-dir", str(install)],
                capture_output=True,
                encoding="utf-8",
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            installed = install / "method" / "scripts" / "tickets.py"
            source = SKILL_SOURCE / "scripts" / "tickets.py"
            self.assertEqual(installed.read_bytes(), source.read_bytes())

            lock = json.loads((install / "_config" / "bmad.lock").read_text(encoding="utf-8"))
            entry = next(item for item in lock["entries"] if item["skill"] == "bmad-preview-ticketing")
            self.assertEqual(
                [artifact for artifact in entry["artifacts"] if artifact["kind"] == "method-runtime-verbatim"],
                [{
                    "hash": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "kind": "method-runtime-verbatim",
                    "owner": "bmm/bmad-preview-ticketing",
                    "path": "scripts/tickets.py",
                }],
            )


if __name__ == "__main__":
    unittest.main()
