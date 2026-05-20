"""Story 8.8 unit tests: component drift detection, mode-drift events, --yes resolution."""
from __future__ import annotations

import hashlib
import json
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent.parent / "src" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import upgrade  # upgrade.py is importable as a module


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _make_project(
    tmp_dir: str,
    lockfile_version: int = 2,
    comp_render_mode: str = "jit",
    comp_hash: str = "abc",
    comp_sfv: int | None = 1,
) -> tuple[str, Path, Path]:
    """Create a minimal project fixture with one JIT component.

    Returns (project_root, lock_path, component_path).
    comp_hash is stored verbatim in the lockfile; use _actual_hash(comp_path)
    to get the real on-disk SHA-256 after creation.
    """
    root = Path(tmp_dir)

    # Component file
    comp_content = f'RENDER_MODE = "{comp_render_mode}"\n'
    comp_dir = root / "_bmad" / "components" / "core" / "test-skill"
    comp_dir.mkdir(parents=True, exist_ok=True)
    comp_path = comp_dir / "date_banner.py"
    comp_path.write_text(comp_content, encoding="utf-8")

    # Lockfile
    lock_dir = root / "_bmad" / "_config"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "bmad.lock"

    if lockfile_version == 2:
        comp_entry = {
            "name": "DateBanner",
            "path": "components/date_banner.py",
            "source_hash": comp_hash,
            "render_mode": comp_render_mode,
            "props": {"format": "short"},
            "props_hash": "abcd1234efgh5678",
            "compiled_hash": None,
            "sentinel_format_version": comp_sfv,
        }
        skill_entry = {
            "skill": "core/test-skill",
            "components": [comp_entry],
        }
    else:
        skill_entry = {"skill": "core/test-skill"}

    lock_data = {"version": lockfile_version, "entries": [skill_entry]}
    lock_path.write_text(json.dumps(lock_data, indent=2) + "\n", encoding="utf-8")

    return str(root), lock_path, comp_path


def _actual_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_main(argv: list[str]) -> tuple[int, str]:
    """Call upgrade.main() with stdout captured. Returns (exit_code, stdout)."""
    buf = StringIO()
    with redirect_stdout(buf):
        rc = upgrade.main(argv)
    return rc, buf.getvalue()


# ---------------------------------------------------------------------------
# Class 1 — AC-1/AC-2/AC-3: _collect_component_drift unit tests
# ---------------------------------------------------------------------------

class TestComponentDriftDetection(TestCase):

    def test_jit_source_drift_detected(self) -> None:
        """v2 lockfile with stale source_hash (JIT): component_drift item returned."""
        with TemporaryDirectory() as tmp:
            root, lock_path, comp_path = _make_project(
                tmp, comp_render_mode="jit", comp_hash="abc"
            )
            entries = json.loads(lock_path.read_text(encoding="utf-8"))["entries"]
            actual = _actual_hash(comp_path)

            drift_items, jit_updates = upgrade._collect_component_drift(entries, root)

            self.assertEqual(len(drift_items), 1)
            item = drift_items[0]
            self.assertEqual(item["kind"], "component_drift")
            self.assertEqual(item["render_mode"], "jit")
            self.assertNotEqual(item["new_hash"], "abc")
            self.assertEqual(item["new_hash"], actual)
            self.assertIn(("core/test-skill", "DateBanner"), jit_updates)

    def test_mode_change_detected(self) -> None:
        """Installed file has RENDER_MODE=jit but lockfile says compile → component_mode_drift."""
        with TemporaryDirectory() as tmp:
            root, lock_path, comp_path = _make_project(
                tmp, comp_render_mode="compile", comp_hash="abc"
            )
            # Overwrite file to have jit mode
            comp_path.write_text('RENDER_MODE = "jit"\n', encoding="utf-8")
            entries = json.loads(lock_path.read_text(encoding="utf-8"))["entries"]

            drift_items, jit_updates = upgrade._collect_component_drift(entries, root)

            self.assertEqual(len(drift_items), 1)
            item = drift_items[0]
            self.assertEqual(item["kind"], "component_mode_drift")
            self.assertEqual(item["render_mode_change"], {"old": "compile", "new": "jit"})
            self.assertNotIn(("core/test-skill", "DateBanner"), jit_updates)

    def test_mode_change_subsumes_source_drift(self) -> None:
        """Mode change AND different hash → only component_mode_drift item (not component_drift)."""
        with TemporaryDirectory() as tmp:
            root, lock_path, comp_path = _make_project(
                tmp, comp_render_mode="compile", comp_hash="abc"
            )
            # Different content AND different mode from lockfile
            comp_path.write_text('RENDER_MODE = "jit"\n# modified content\n', encoding="utf-8")
            entries = json.loads(lock_path.read_text(encoding="utf-8"))["entries"]

            drift_items, jit_updates = upgrade._collect_component_drift(entries, root)

            self.assertEqual(len(drift_items), 1)
            self.assertEqual(drift_items[0]["kind"], "component_mode_drift")
            # No source-hash drift item
            self.assertFalse(any(i["kind"] == "component_drift" for i in drift_items))

    def test_missing_installed_file_skipped(self) -> None:
        """Component file not yet installed → silently skipped, no drift event."""
        with TemporaryDirectory() as tmp:
            root, lock_path, comp_path = _make_project(
                tmp, comp_render_mode="jit", comp_hash="abc"
            )
            comp_path.unlink()
            entries = json.loads(lock_path.read_text(encoding="utf-8"))["entries"]

            drift_items, jit_updates = upgrade._collect_component_drift(entries, root)

            self.assertEqual(drift_items, [])
            self.assertEqual(jit_updates, {})

    def test_v1_lockfile_skipped(self) -> None:
        """v1 lockfile: component drift loop never fires in main()."""
        with TemporaryDirectory() as tmp:
            root, lock_path, comp_path = _make_project(
                tmp, lockfile_version=1, comp_render_mode="jit", comp_hash="abc"
            )
            with patch("upgrade._run_compile_install_phase", return_value=0):
                rc, out = _run_main(["--yes", "--project-root", root])
            self.assertNotIn("component_drift", out)
            self.assertEqual(rc, 0)


# ---------------------------------------------------------------------------
# Class 2 — AC-2/AC-3/AC-5: --yes resolution + exit code tests
# ---------------------------------------------------------------------------

class TestComponentDriftResolution(TestCase):

    def test_jit_source_drift_updates_lockfile(self) -> None:
        """JIT source drift + --yes: source_hash in lockfile updated to new hash."""
        with TemporaryDirectory() as tmp:
            root, lock_path, comp_path = _make_project(
                tmp, comp_render_mode="jit", comp_hash="abc"
            )
            actual = _actual_hash(comp_path)
            with patch("upgrade._run_compile_install_phase", return_value=0):
                rc, out = _run_main(["--yes", "--project-root", root])

            self.assertEqual(rc, 0)
            lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
            updated_hash = lock_data["entries"][0]["components"][0]["source_hash"]
            self.assertEqual(updated_hash, actual)

    def test_compile_mode_drift_triggers_recompile(self) -> None:
        """Compile-mode source drift + --yes: _run_compile_install_phase is called."""
        with TemporaryDirectory() as tmp:
            root, lock_path, comp_path = _make_project(
                tmp, comp_render_mode="compile", comp_hash="abc"
            )
            with patch("upgrade._run_compile_install_phase", return_value=0) as mock_compile:
                rc, out = _run_main(["--yes", "--project-root", root])

            mock_compile.assert_called_once()
            self.assertEqual(rc, 0)

    def test_mode_change_triggers_recompile(self) -> None:
        """compile→jit mode change + --yes: _run_compile_install_phase is called."""
        with TemporaryDirectory() as tmp:
            root, lock_path, comp_path = _make_project(
                tmp, comp_render_mode="compile", comp_hash="abc"
            )
            comp_path.write_text('RENDER_MODE = "jit"\n', encoding="utf-8")
            with patch("upgrade._run_compile_install_phase", return_value=0) as mock_compile:
                rc, out = _run_main(["--yes", "--project-root", root])

            mock_compile.assert_called_once()
            self.assertEqual(rc, 0)

    def test_failed_recompile_returns_nonzero(self) -> None:
        """_run_compile_install_phase fails → main() returns non-zero; lockfile unchanged."""
        with TemporaryDirectory() as tmp:
            root, lock_path, comp_path = _make_project(
                tmp, comp_render_mode="compile", comp_hash="abc"
            )
            comp_path.write_text('RENDER_MODE = "jit"\n', encoding="utf-8")
            with patch("upgrade._run_compile_install_phase", return_value=1):
                rc, out = _run_main(["--yes", "--project-root", root])

            self.assertNotEqual(rc, 0)
            # Lockfile render_mode unchanged — compile phase did not rewrite it
            lock_data = json.loads(lock_path.read_text(encoding="utf-8"))
            rm = lock_data["entries"][0]["components"][0]["render_mode"]
            self.assertEqual(rm, "compile")

    def test_halt_without_yes(self) -> None:
        """Component drift without --yes → exits 3."""
        with TemporaryDirectory() as tmp:
            root, lock_path, comp_path = _make_project(
                tmp, comp_render_mode="jit", comp_hash="abc"
            )
            rc, out = _run_main(["--project-root", root])
            self.assertEqual(rc, 3)

    def test_mixed_skill_jit_and_compile_drift(self) -> None:
        """AC-5 contract: JIT hash updated + recompile called in a mixed-skill run."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)

            # Skill A — JIT component with stale hash
            comp_a_dir = root / "_bmad" / "components" / "core" / "skill-a"
            comp_a_dir.mkdir(parents=True, exist_ok=True)
            comp_a = comp_a_dir / "widget.py"
            comp_a.write_text('RENDER_MODE = "jit"\n# skill-a content\n', encoding="utf-8")
            actual_a = _actual_hash(comp_a)

            # Skill B — compile-mode component with stale hash
            comp_b_dir = root / "_bmad" / "components" / "core" / "skill-b"
            comp_b_dir.mkdir(parents=True, exist_ok=True)
            comp_b = comp_b_dir / "footer.py"
            comp_b.write_text('RENDER_MODE = "compile"\n# skill-b content\n', encoding="utf-8")

            # Lockfile with both skills
            lock_dir = root / "_bmad" / "_config"
            lock_dir.mkdir(parents=True, exist_ok=True)
            lock_path = lock_dir / "bmad.lock"
            lock_data = {
                "version": 2,
                "entries": [
                    {
                        "skill": "core/skill-a",
                        "components": [{
                            "name": "Widget",
                            "path": "components/widget.py",
                            "source_hash": "stale_a",
                            "render_mode": "jit",
                            "props": {},
                            "props_hash": "x",
                            "compiled_hash": None,
                            "sentinel_format_version": 1,
                        }],
                    },
                    {
                        "skill": "core/skill-b",
                        "components": [{
                            "name": "Footer",
                            "path": "components/footer.py",
                            "source_hash": "stale_b",
                            "render_mode": "compile",
                            "props": {},
                            "props_hash": "y",
                            "compiled_hash": None,
                            "sentinel_format_version": 1,
                        }],
                    },
                ],
            }
            lock_path.write_text(json.dumps(lock_data, indent=2) + "\n", encoding="utf-8")

            with patch("upgrade._run_compile_install_phase", return_value=0) as mock_compile:
                rc, out = _run_main(["--yes", "--project-root", str(root)])

            self.assertEqual(rc, 0)
            mock_compile.assert_called_once()

            # Skill A's JIT source_hash must be updated to actual hash
            updated = json.loads(lock_path.read_text(encoding="utf-8"))
            updated_hash_a = updated["entries"][0]["components"][0]["source_hash"]
            self.assertEqual(updated_hash_a, actual_a)


# ---------------------------------------------------------------------------
# Class 3 — AC-4: sentinel_format_migration events
# ---------------------------------------------------------------------------

class TestSentinelFormatMigration(TestCase):

    def test_sfm_event_emitted(self) -> None:
        """sentinel_format_version != 1 → sentinel_format_migration printed; no drift item."""
        with TemporaryDirectory() as tmp:
            root, lock_path, comp_path = _make_project(
                tmp, comp_render_mode="jit", comp_hash="abc", comp_sfv=2
            )
            # Use actual hash so no source drift — only sentinel event fires
            actual = _actual_hash(comp_path)
            data = json.loads(lock_path.read_text(encoding="utf-8"))
            data["entries"][0]["components"][0]["source_hash"] = actual
            lock_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            entries = data["entries"]

            buf = StringIO()
            with redirect_stdout(buf):
                drift_items, _ = upgrade._collect_component_drift(entries, root)

            output = buf.getvalue()
            self.assertIn("sentinel_format_migration", output)
            # Sentinel event does NOT add to drift_items
            self.assertEqual(drift_items, [])

    def test_sfm_null_skipped(self) -> None:
        """sentinel_format_version=null → no sentinel_format_migration event."""
        with TemporaryDirectory() as tmp:
            root, lock_path, comp_path = _make_project(
                tmp, comp_render_mode="jit", comp_hash="abc", comp_sfv=None
            )
            entries = json.loads(lock_path.read_text(encoding="utf-8"))["entries"]

            buf = StringIO()
            with redirect_stdout(buf):
                drift_items, _ = upgrade._collect_component_drift(entries, root)

            self.assertNotIn("sentinel_format_migration", buf.getvalue())

    def test_sfm_version_1_skipped(self) -> None:
        """sentinel_format_version=1 (current) → no sentinel_format_migration event."""
        with TemporaryDirectory() as tmp:
            root, lock_path, comp_path = _make_project(
                tmp, comp_render_mode="jit", comp_hash="abc", comp_sfv=1
            )
            entries = json.loads(lock_path.read_text(encoding="utf-8"))["entries"]

            buf = StringIO()
            with redirect_stdout(buf):
                drift_items, _ = upgrade._collect_component_drift(entries, root)

            self.assertNotIn("sentinel_format_migration", buf.getvalue())


# ---------------------------------------------------------------------------
# Class 4 — AC-6/AC-7: --dry-run and v2 schema migration guard
# ---------------------------------------------------------------------------

class TestDryRunComponentDrift(TestCase):

    def test_dryrun_shows_drift_no_halt(self) -> None:
        """Dry-run with component drift: items displayed, exits 0, lockfile unchanged."""
        with TemporaryDirectory() as tmp:
            root, lock_path, comp_path = _make_project(
                tmp, comp_render_mode="jit", comp_hash="abc"
            )
            original_hash = json.loads(lock_path.read_text(encoding="utf-8"))[
                "entries"
            ][0]["components"][0]["source_hash"]

            rc, out = _run_main(["--dry-run", "--project-root", root])

            self.assertEqual(rc, 0)
            self.assertIn("[component_drift]", out)
            # Lockfile hash must not be updated in dry-run
            updated = json.loads(lock_path.read_text(encoding="utf-8"))
            self.assertEqual(
                updated["entries"][0]["components"][0]["source_hash"], original_hash
            )

    def test_dryrun_no_drift_message(self) -> None:
        """Dry-run with no drift: 'No drift detected.' printed."""
        with TemporaryDirectory() as tmp:
            root, lock_path, comp_path = _make_project(
                tmp, comp_render_mode="jit", comp_hash="abc"
            )
            # Set lockfile hash to match actual file so no drift
            actual = _actual_hash(comp_path)
            data = json.loads(lock_path.read_text(encoding="utf-8"))
            data["entries"][0]["components"][0]["source_hash"] = actual
            lock_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

            rc, out = _run_main(["--dry-run", "--project-root", root])

            self.assertEqual(rc, 0)
            self.assertIn("No drift detected.", out)

    def test_v2_lockfile_no_schema_migration_event(self) -> None:
        """v2 lockfile + --yes: lockfile_schema_migration NOT emitted."""
        with TemporaryDirectory() as tmp:
            root, lock_path, comp_path = _make_project(
                tmp, comp_render_mode="jit", comp_hash="abc"
            )
            with patch("upgrade._run_compile_install_phase", return_value=0):
                rc, out = _run_main(["--yes", "--project-root", root])

            self.assertNotIn("lockfile_schema_migration", out)
