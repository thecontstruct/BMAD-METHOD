"""Story 8.1 unit tests: error classes, lockfile v2 schema, engine demotion, upgrade event."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src/scripts to path so upgrade.py (non-package) is importable.
_SCRIPTS_DIR = str(
    Path(__file__).resolve().parent.parent.parent / "src" / "scripts"
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from src.scripts.bmad_compile import engine, errors, io, lockfile, resolver
from src.scripts.bmad_compile.io import PurePosixPath
from src.scripts.bmad_compile.resolver import (
    CompileCache,
    ResolvedFragment,
    VariableScope,
)

import upgrade as _upgrade_mod


# ---------------------------------------------------------------------------
# Minimal fixture helpers
# ---------------------------------------------------------------------------

def _empty_scope() -> VariableScope:
    return VariableScope({})


def _empty_cache() -> CompileCache:
    return CompileCache()


def _make_dep_tree(scenario_root: PurePosixPath, skill: str = "test-skill") -> list:
    root = ResolvedFragment(
        src=f"{skill}/{skill}.template.md",
        resolved_path=scenario_root / "core" / skill / f"{skill}.template.md",
        resolved_from="base",
        local_props=(),
        merged_scope=(),
        nodes=[],
    )
    return [root]


def _call_write(
    lockfile_path: str,
    scenario_root: PurePosixPath,
    *,
    skill_basename: str = "test-skill",
    source_text: str = "source",
    compiled_text: str = "compiled",
    components: list | None = None,
) -> None:
    dep_tree = _make_dep_tree(scenario_root, skill_basename)
    lockfile.write_skill_entry(
        lockfile_path,
        scenario_root,
        skill_basename,
        source_text=source_text,
        compiled_text=compiled_text,
        dep_tree=dep_tree,
        var_scope=_empty_scope(),
        target_ide=None,
        cache=_empty_cache(),
        components=components,
    )


# ---------------------------------------------------------------------------
# Class 1 — error classes
# ---------------------------------------------------------------------------

class TestComponentErrorClasses(unittest.TestCase):

    def test_four_new_classes_importable(self) -> None:
        for cls in (
            errors.ComponentError,
            errors.ComponentTimeoutError,
            errors.ComponentPropError,
            errors.ComponentBatchError,
        ):
            with self.subTest(cls=cls.__name__):
                e = cls("msg")
                self.assertIsInstance(e, errors.CompilerError)

    def test_component_error_attributes(self) -> None:
        e = errors.ComponentError(
            "msg",
            component_name="X",
            exit_code=1,
            stderr="err",
            render_error_fallback="fb",
        )
        self.assertEqual(e.component_name, "X")
        self.assertEqual(e.exit_code, 1)
        self.assertEqual(e.stderr, "err")
        self.assertEqual(e.render_error_fallback, "fb")

    def test_component_batch_error_wraps_errors(self) -> None:
        inner = errors.ComponentError("inner")
        batch = errors.ComponentBatchError("batch", errors=[inner])
        self.assertEqual(len(batch.errors), 1)
        self.assertEqual(batch.errors[0].desc, "inner")

    def test_subclasses_tuple_updated(self) -> None:
        self.assertEqual(len(errors.SUBCLASSES), 11)
        self.assertIn(errors.ComponentError, errors.SUBCLASSES)
        self.assertIn(errors.ComponentTimeoutError, errors.SUBCLASSES)
        self.assertIn(errors.ComponentPropError, errors.SUBCLASSES)
        self.assertIn(errors.ComponentBatchError, errors.SUBCLASSES)


# ---------------------------------------------------------------------------
# Class 2 — lockfile v2 schema
# ---------------------------------------------------------------------------

class TestLockfileV2Schema(unittest.TestCase):

    def test_version_is_3(self) -> None:
        """Story 10.58: lockfile schema bumped to v4 (was v3 in Story 10.26).

        Test name retained for continuity; asserts current expected value.
        """
        self.assertEqual(lockfile._VERSION, 4)

    def test_components_field_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root)
            data = json.loads(io.read_template(lf))
            self.assertIn("components", data["entries"][0])
            self.assertEqual(data["entries"][0]["components"], [])

    def test_components_kwarg_defaults_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            # None (default) → []
            _call_write(lf, root, components=None)
            data = json.loads(io.read_template(lf))
            self.assertEqual(data["entries"][0]["components"], [])
            # Explicit list preserved
            _call_write(lf, root, components=[{"name": "X"}])
            data2 = json.loads(io.read_template(lf))
            self.assertEqual(data2["entries"][0]["components"], [{"name": "X"}])

    def test_v1_lockfile_tolerant_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            # Write a v1-style lockfile entry without "components" key
            v1_data = {
                "version": 1,
                "compiled_at": "1.0.0",
                "bmad_version": "1.0.0",
                "entries": [],
            }
            io.write_text(lf, json.dumps(v1_data) + "\n")
            # Now write via v2 writer; components should default to []
            _call_write(lf, root)
            data = json.loads(io.read_template(lf))
            self.assertEqual(data["entries"][0]["components"], [])

    def test_in_lock_version_read_is_first_statement(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            with patch.object(
                lockfile,
                "read_lockfile_version",
                wraps=lockfile.read_lockfile_version,
            ) as spy:
                _call_write(lf, root)
            # _do_write_skill_entry must call read_lockfile_version with lockfile_path
            spy.assert_called_once_with(lf)


# ---------------------------------------------------------------------------
# Class 3 — engine version guard demotion
# ---------------------------------------------------------------------------

class TestEngineVersionMismatchDemotion(unittest.TestCase):

    def test_version_mismatch_warns_not_raises(self) -> None:
        """Story 10.58: bumped from v4→v5 fixture now that _VERSION=4.

        Asserts the future-version warning path: lockfile.version > _VERSION
        causes a single WARNING-level log and compile proceeds.
        """
        from bmad_compile.component_runner import MockComponentRunner as _MR
        from bmad_compile import engine as _engine
        future_version = lockfile._VERSION + 1
        with tempfile.TemporaryDirectory() as tmp_root:
            tmp = Path(tmp_root)
            skill_dir = tmp / "core" / "warn-skill"
            skill_dir.mkdir(parents=True)
            (skill_dir / "warn-skill.template.md").write_text(
                "Hello!", encoding="utf-8"
            )
            # Future-version lockfile — declared > current _VERSION
            lock_path = tmp / "_bmad" / "_config" / "bmad.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path.write_text(
                json.dumps(
                    {"version": future_version, "compiled_at": "1.0.0",
                     "bmad_version": "1.0.0", "entries": []}
                ),
                encoding="utf-8",
            )
            install_dir = tmp / "install"
            install_dir.mkdir()
            with self.assertLogs(level="WARNING") as cm:
                _engine.compile_skill(str(skill_dir), str(install_dir),
                                      component_runner=_MR(batch_results={}))
            self.assertTrue(
                any(
                    f"version {future_version}" in msg
                    or f"version {lockfile._VERSION}" in msg
                    for msg in cm.output
                ),
                f"Expected warning mentioning version mismatch in: {cm.output}",
            )


# ---------------------------------------------------------------------------
# Class 4 — upgrade migration event
# ---------------------------------------------------------------------------

class TestUpgradeMigrationEvent(unittest.TestCase):

    def _write_file(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_migration_event_emitted_for_v1_with_components(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_root:
            tmp = Path(tmp_root)
            lockfile_path = tmp / "_bmad" / "_config" / "bmad.lock"
            self._write_file(
                lockfile_path,
                json.dumps({
                    "version": 1,
                    "compiled_at": "1.0.0",
                    "bmad_version": "1.0.0",
                    "entries": [
                        {
                            "skill": "test-skill",
                            "compiled_hash": "abc",
                            "source_hash": "def",
                            "variant": None,
                            "fragments": [],
                            "variables": [],
                            "glob_inputs": [],
                        }
                    ],
                }),
            )
            # Install template with a component tag
            template_path = tmp / "_bmad" / "core" / "test-skill" / "test-skill.template.md"
            self._write_file(template_path, "<DateBanner format=\"short\" />")

            mock_dr = MagicMock()
            mock_dr.has_drift.return_value = False

            captured: list[str] = []

            def _fake_print(*args: object, **kwargs: object) -> None:
                if args:
                    captured.append(str(args[0]))

            with patch.object(_upgrade_mod, "_run_compile_install_phase", return_value=0), \
                 patch.object(_upgrade_mod, "detect_drift", return_value=mock_dr), \
                 patch("builtins.print", side_effect=_fake_print):
                result = _upgrade_mod.main(["--yes", "--project-root", str(tmp)])

            self.assertEqual(result, 0)
            migration_lines = [
                ln for ln in captured
                if '"kind": "lockfile_schema_migration"' in ln
                or (ln.startswith("{") and "lockfile_schema_migration" in ln)
            ]
            self.assertTrue(migration_lines, f"No migration event in captured: {captured}")
            event = json.loads(migration_lines[0])
            self.assertEqual(event["kind"], "lockfile_schema_migration")
            self.assertEqual(event["old_version"], 1)
            self.assertEqual(event["new_version"], 2)
            self.assertEqual(event["skill_id"], "test-skill")
            self.assertEqual(event["new_component_names"], ["DateBanner"])

    def test_migration_event_not_emitted_for_v2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_root:
            tmp = Path(tmp_root)
            lockfile_path = tmp / "_bmad" / "_config" / "bmad.lock"
            self._write_file(
                lockfile_path,
                json.dumps({
                    "version": 2,
                    "compiled_at": "1.0.0",
                    "bmad_version": "1.0.0",
                    "entries": [
                        {
                            "skill": "test-skill",
                            "compiled_hash": "abc",
                            "source_hash": "def",
                            "variant": None,
                            "fragments": [],
                            "variables": [],
                            "glob_inputs": [],
                            "components": [],
                        }
                    ],
                }),
            )
            template_path = tmp / "_bmad" / "core" / "test-skill" / "test-skill.template.md"
            self._write_file(template_path, "<DateBanner format=\"short\" />")

            mock_dr = MagicMock()
            mock_dr.has_drift.return_value = False

            captured: list[str] = []

            def _fake_print(*args: object, **kwargs: object) -> None:
                if args:
                    captured.append(str(args[0]))

            with patch.object(_upgrade_mod, "_run_compile_install_phase", return_value=0), \
                 patch.object(_upgrade_mod, "detect_drift", return_value=mock_dr), \
                 patch("builtins.print", side_effect=_fake_print):
                result = _upgrade_mod.main(["--yes", "--project-root", str(tmp)])

            self.assertEqual(result, 0)
            migration_lines = [
                ln for ln in captured if "lockfile_schema_migration" in ln
            ]
            self.assertEqual(migration_lines, [], f"Unexpected migration events: {migration_lines}")


if __name__ == "__main__":
    unittest.main()
