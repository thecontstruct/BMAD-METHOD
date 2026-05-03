"""Parity + integration tests for the upstream CLI resolve_*.py scripts.

Story 3.2 refactored both scripts to import `merge_layers` from
`bmad_compile.toml_merge`, removing duplicated deep-merge code. These
tests pin the behavioral parity invariant: the CLI scripts must produce
output identical to a direct `merge_layers()` call against the same
TOML inputs.

ACs 1, 2, 4, 5 are exercised here:
  - AC 1: defaults-only layer produces correct value + lockfile records
    `toml_layer: defaults`.
  - AC 2: user tier overrides defaults; lockfile records `toml_layer: user`.
  - AC 4: parity tests for both resolve_customization.py (3-layer) and
    resolve_config.py (4-layer).
  - AC 5: `toml_layer` provenance is observable in the lockfile (the
    3-layer scope within resolve_customization.py's domain).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from typing import Any

from src.scripts.bmad_compile import io, lockfile
from src.scripts.bmad_compile.resolver import VariableScope
from src.scripts.bmad_compile.toml_merge import merge_layers

# Path to the upstream CLI scripts under test.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_RESOLVE_CUSTOMIZATION = _REPO_ROOT / "src" / "scripts" / "resolve_customization.py"
_RESOLVE_CONFIG = _REPO_ROOT / "src" / "scripts" / "resolve_config.py"


def _run(script: Path, *args: str) -> dict[str, Any]:
    """Invoke a CLI script with --skill/--project-root and return JSON stdout."""
    try:
        proc = subprocess.run(
            [sys.executable, str(script), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise AssertionError(
            f"{script.name} exited {exc.returncode}\nstdout: {exc.stdout}\nstderr: {exc.stderr}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AssertionError(
            f"{script.name} timed out after {exc.timeout}s\nstdout: {exc.stdout}\nstderr: {exc.stderr}"
        ) from exc
    parsed: dict[str, Any] = json.loads(proc.stdout)
    return parsed


class TestResolveCustomizationParity(unittest.TestCase):
    """AC 4: resolve_customization.py CLI output equals merge_layers(...) directly."""

    def test_parity_with_merge_layers(self) -> None:
        # 3-layer fixture: defaults / team / user
        defaults_toml = '[workflow]\nicon = "🔧"\nname = "default"\n'
        team_toml = '[workflow]\nname = "team-name"\n'
        user_toml = '[workflow]\nicon = "⚡"\n'

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "proj"
            skill_dir = project_root / "skills" / "my-skill"
            skill_dir.mkdir(parents=True)
            custom_dir = project_root / "_bmad" / "custom"
            custom_dir.mkdir(parents=True)

            (skill_dir / "customize.toml").write_text(defaults_toml, encoding="utf-8")
            (custom_dir / "my-skill.toml").write_text(team_toml, encoding="utf-8")
            (custom_dir / "my-skill.user.toml").write_text(user_toml, encoding="utf-8")

            cli_output = _run(_RESOLVE_CUSTOMIZATION, "--skill", str(skill_dir))

        # Direct call to the shared module — the parity reference.
        import tomllib
        defaults = tomllib.loads(defaults_toml)
        team = tomllib.loads(team_toml)
        user = tomllib.loads(user_toml)
        expected = merge_layers(defaults, team, user)

        self.assertEqual(cli_output, expected)
        # User-tier value wins on `icon`; team-tier value wins on `name`.
        self.assertEqual(cli_output["workflow"]["icon"], "⚡")
        self.assertEqual(cli_output["workflow"]["name"], "team-name")

    def test_parity_aot_keyed_merge_three_layers(self) -> None:
        defaults_toml = (
            '[[steps]]\nid = "plan"\nlabel = "Plan"\nenabled = true\n\n'
            '[[steps]]\nid = "review"\nlabel = "Review"\nenabled = true\n'
        )
        team_toml = '[[steps]]\nid = "plan"\nlabel = "Plan (Team)"\n'
        user_toml = '[[steps]]\nid = "review"\nlabel = "Review (User)"\nenabled = false\n'

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_root = root / "proj"
            skill_dir = project_root / "skills" / "skill-x"
            skill_dir.mkdir(parents=True)
            custom_dir = project_root / "_bmad" / "custom"
            custom_dir.mkdir(parents=True)
            (skill_dir / "customize.toml").write_text(defaults_toml, encoding="utf-8")
            (custom_dir / "skill-x.toml").write_text(team_toml, encoding="utf-8")
            (custom_dir / "skill-x.user.toml").write_text(user_toml, encoding="utf-8")

            cli_output = _run(_RESOLVE_CUSTOMIZATION, "--skill", str(skill_dir))

        import tomllib
        expected = merge_layers(
            tomllib.loads(defaults_toml),
            tomllib.loads(team_toml),
            tomllib.loads(user_toml),
        )
        self.assertEqual(cli_output, expected)

        # AoT full-replacement: `enabled` field dropped on the `plan` item
        # because the team override doesn't carry it.
        plan = next(s for s in cli_output["steps"] if s["id"] == "plan")
        self.assertEqual(plan["label"], "Plan (Team)")
        self.assertNotIn("enabled", plan)


class TestResolveConfigParity(unittest.TestCase):
    """AC 4: resolve_config.py CLI output equals merge_layers(...) directly."""

    def test_parity_with_merge_layers(self) -> None:
        # 4-layer fixture: base-team / base-user / custom-team / custom-user.
        base_team = '[core]\nproject_name = "default"\nuser_name = "Alice"\n'
        base_user = '[core]\nuser_name = "Bob"\n'
        custom_team = '[core]\nproject_name = "team-project"\n'
        custom_user = '[core]\nuser_name = "Carol"\n'

        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            bmad_dir = project_root / "_bmad"
            bmad_dir.mkdir(parents=True)
            (bmad_dir / "config.toml").write_text(base_team, encoding="utf-8")
            (bmad_dir / "config.user.toml").write_text(base_user, encoding="utf-8")
            (bmad_dir / "custom").mkdir()
            (bmad_dir / "custom" / "config.toml").write_text(custom_team, encoding="utf-8")
            (bmad_dir / "custom" / "config.user.toml").write_text(custom_user, encoding="utf-8")

            cli_output = _run(_RESOLVE_CONFIG, "--project-root", str(project_root))

        import tomllib
        expected = merge_layers(
            tomllib.loads(base_team),
            tomllib.loads(base_user),
            tomllib.loads(custom_team),
            tomllib.loads(custom_user),
        )
        self.assertEqual(cli_output, expected)
        # Highest-priority layer (custom-user) wins on user_name.
        self.assertEqual(cli_output["core"]["user_name"], "Carol")
        # custom-team wins on project_name (no custom-user value).
        self.assertEqual(cli_output["core"]["project_name"], "team-project")

    def test_parity_aot_keyed_merge_four_layers(self) -> None:
        # 4-layer fixture verifying AoT keyed-merge parity for resolve_config.py.
        # base-team has two code-keyed plugins; base-user replaces "alpha" (full
        # replacement — base `enabled` field dropped because override lacks it).
        base_team = (
            '[[plugins]]\ncode = "alpha"\nlabel = "Alpha"\nenabled = true\n\n'
            '[[plugins]]\ncode = "beta"\nlabel = "Beta"\n'
        )
        base_user = '[[plugins]]\ncode = "alpha"\nlabel = "Alpha (custom)"\n'
        custom_team = ""
        custom_user = ""

        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp)
            bmad_dir = project_root / "_bmad"
            bmad_dir.mkdir(parents=True)
            (bmad_dir / "config.toml").write_text(base_team, encoding="utf-8")
            (bmad_dir / "config.user.toml").write_text(base_user, encoding="utf-8")
            (bmad_dir / "custom").mkdir()
            (bmad_dir / "custom" / "config.toml").write_text(custom_team, encoding="utf-8")
            (bmad_dir / "custom" / "config.user.toml").write_text(custom_user, encoding="utf-8")

            cli_output = _run(_RESOLVE_CONFIG, "--project-root", str(project_root))

        import tomllib
        expected = merge_layers(
            tomllib.loads(base_team),
            tomllib.loads(base_user),
            tomllib.loads(custom_team),
            tomllib.loads(custom_user),
        )
        self.assertEqual(cli_output, expected)
        alpha = next(p for p in cli_output["plugins"] if p["code"] == "alpha")
        self.assertEqual(alpha["label"], "Alpha (custom)")
        self.assertNotIn("enabled", alpha)  # full replacement — base field dropped
        beta = next(p for p in cli_output["plugins"] if p["code"] == "beta")
        self.assertEqual(beta["label"], "Beta")


class TestResolveCustomizationSingleLayer(unittest.TestCase):
    """AC 1: defaults-only layer — value resolves correctly and the lockfile
    records `toml_layer: defaults` for the variable."""

    def test_defaults_value_returned(self) -> None:
        defaults_toml = '[workflow]\nicon = "🔧"\n'
        with tempfile.TemporaryDirectory() as tmp:
            # Isolated project root stops find_project_root() here; no custom
            # files exist so only the defaults layer is loaded.
            project_root = Path(tmp) / "isolated"
            skill_dir = project_root / "skills" / "my-skill"
            skill_dir.mkdir(parents=True)
            (project_root / "_bmad").mkdir()
            (skill_dir / "customize.toml").write_text(defaults_toml, encoding="utf-8")

            cli_output = _run(
                _RESOLVE_CUSTOMIZATION,
                "--skill", str(skill_dir),
                "--key", "workflow.icon",
            )

        # CLI emits the merged value; provenance lives in the lockfile (asserted
        # in test_defaults_toml_layer below).
        self.assertEqual(cli_output["workflow.icon"], "🔧")

    def test_defaults_toml_layer(self) -> None:
        # Verify the lockfile writer records `toml_layer: defaults` when only
        # the defaults tier contributes a value (AC 1 provenance).
        with tempfile.TemporaryDirectory() as tmp:
            scope = VariableScope.build(
                toml_layers=[("defaults", {"workflow": {"icon": "🔧"}})],
                toml_layer_paths=["/abs/scenario/skill/customize.toml"],
            )
            lf_path = Path(tmp) / "bmad.lock"
            lockfile.write_skill_entry(
                str(lf_path),
                PurePosixPath("/abs/scenario"),
                "my-skill",
                source_text="placeholder",
                compiled_text="placeholder",
                dep_tree=[None],
                var_scope=scope,
                target_ide=None,
                cache=None,  # type: ignore[arg-type]
            )
            data = json.loads(lf_path.read_text(encoding="utf-8"))
            variables = data["entries"][0]["variables"]
            var = next(v for v in variables if v["name"] == "self.workflow.icon")
            self.assertEqual(var["toml_layer"], "defaults")


class TestResolveCustomizationUserWins(unittest.TestCase):
    """AC 2 + AC 5: user tier overrides defaults; lockfile records
    `toml_layer: user` and `value_hash` matches SHA-256 of the user value."""

    def test_user_override_wins(self) -> None:
        defaults_toml = '[workflow]\nicon = "🔧"\n'
        user_toml = '[workflow]\nicon = "⚡"\n'
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "proj"
            skill_dir = project_root / "skills" / "my-skill"
            skill_dir.mkdir(parents=True)
            custom_dir = project_root / "_bmad" / "custom"
            custom_dir.mkdir(parents=True)
            (skill_dir / "customize.toml").write_text(defaults_toml, encoding="utf-8")
            (custom_dir / "my-skill.user.toml").write_text(user_toml, encoding="utf-8")

            cli_output = _run(
                _RESOLVE_CUSTOMIZATION,
                "--skill", str(skill_dir),
                "--key", "workflow.icon",
            )
        self.assertEqual(cli_output["workflow.icon"], "⚡")

        # Lockfile-side: provenance + value_hash assertions (AC 2 + AC 5).
        with tempfile.TemporaryDirectory() as tmp:
            scope = VariableScope.build(
                toml_layers=[
                    ("defaults", {"workflow": {"icon": "🔧"}}),
                    ("user", {"workflow": {"icon": "⚡"}}),
                ],
                toml_layer_paths=[
                    "/abs/scenario/skill/customize.toml",
                    "/abs/scenario/_bmad/custom/my-skill.user.toml",
                ],
            )
            lf_path = Path(tmp) / "bmad.lock"
            lockfile.write_skill_entry(
                str(lf_path),
                PurePosixPath("/abs/scenario"),
                "my-skill",
                source_text="placeholder",
                compiled_text="placeholder",
                dep_tree=[None],
                var_scope=scope,
                target_ide=None,
                cache=None,  # type: ignore[arg-type]
            )
            data = json.loads(lf_path.read_text(encoding="utf-8"))
            variables = data["entries"][0]["variables"]
            var = next(v for v in variables if v["name"] == "self.workflow.icon")
            self.assertEqual(var["toml_layer"], "user")
            self.assertEqual(var["value_hash"], io.hash_text("⚡"))


if __name__ == "__main__":
    unittest.main()
