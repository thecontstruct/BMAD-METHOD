"""Unit tests for bmad_compile.lockfile — lockfile v1 writer."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.scripts.bmad_compile import engine, errors, io, lockfile, resolver
from src.scripts.bmad_compile.io import PurePosixPath
from src.scripts.bmad_compile.resolver import (
    CompileCache,
    ResolvedFragment,
    ResolvedValue,
    VariableScope,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_scope() -> VariableScope:
    return VariableScope({})


def _empty_cache() -> CompileCache:
    return CompileCache()


def _make_dep_tree_root_only(scenario_root: PurePosixPath) -> list:
    """Minimal dep_tree: just a root entry, no fragments."""
    root = ResolvedFragment(
        src="skill1/skill1.template.md",
        resolved_path=scenario_root / "core" / "skill1" / "skill1.template.md",
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
    skill_basename: str = "skill1",
    source_text: str = "source",
    compiled_text: str = "compiled",
    dep_tree: list | None = None,
    var_scope: VariableScope | None = None,
    target_ide: str | None = None,
    cache: CompileCache | None = None,
) -> None:
    if dep_tree is None:
        dep_tree = _make_dep_tree_root_only(scenario_root)
    if var_scope is None:
        var_scope = _empty_scope()
    if cache is None:
        cache = _empty_cache()
    lockfile.write_skill_entry(
        lockfile_path,
        scenario_root,
        skill_basename,
        source_text=source_text,
        compiled_text=compiled_text,
        dep_tree=dep_tree,
        var_scope=var_scope,
        target_ide=target_ide,
        cache=cache,
    )


# ---------------------------------------------------------------------------
# TestReadLockfileVersion
# ---------------------------------------------------------------------------

class TestReadLockfileVersion(unittest.TestCase):

    def test_returns_none_for_missing_file(self) -> None:
        self.assertIsNone(lockfile.read_lockfile_version("/nonexistent/bmad.lock"))

    def test_returns_version_for_valid_lockfile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lf = Path(tmp) / "bmad.lock"
            lf.write_text(json.dumps({"version": 1, "compiled_at": "1.0.0"}), encoding="utf-8")
            self.assertEqual(lockfile.read_lockfile_version(str(lf)), 1)

    def test_returns_0_for_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lf = Path(tmp) / "bmad.lock"
            lf.write_text("not json {{{{", encoding="utf-8")
            self.assertEqual(lockfile.read_lockfile_version(str(lf)), 0)

    def test_returns_0_for_non_dict_top_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lf = Path(tmp) / "bmad.lock"
            lf.write_text("[1, 2, 3]", encoding="utf-8")
            self.assertEqual(lockfile.read_lockfile_version(str(lf)), 0)

    def test_returns_future_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lf = Path(tmp) / "bmad.lock"
            lf.write_text(json.dumps({"version": 2}), encoding="utf-8")
            self.assertEqual(lockfile.read_lockfile_version(str(lf)), 2)

    def test_handles_utf8_bom_prefixed_lockfile(self) -> None:
        # Round 3 EC-2: Windows authors / editors may save bmad.lock with a
        # UTF-8 BOM. Without BOM stripping the file would parse as malformed
        # and the engine would silently overwrite a perfectly valid v1 lockfile.
        with tempfile.TemporaryDirectory() as tmp:
            lf = Path(tmp) / "bmad.lock"
            lf.write_bytes(b"\xef\xbb\xbf" + json.dumps({"version": 1}).encode("utf-8"))
            self.assertEqual(lockfile.read_lockfile_version(str(lf)), 1)


# ---------------------------------------------------------------------------
# TestWriteSkillEntry
# ---------------------------------------------------------------------------

class TestWriteSkillEntry(unittest.TestCase):

    def test_lockfile_created_on_first_compile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "_bmad" / "_config" / "bmad.lock")
            _call_write(lf, root)
            self.assertTrue(io.is_file(lf))
            data = json.loads(io.read_template(lf))
            self.assertIsInstance(data, dict)

    def test_schema_version_is_1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root)
            data = json.loads(io.read_template(lf))
            self.assertEqual(data["version"], 1)

    def test_compiled_at_is_sentinel_not_datetime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root)
            data = json.loads(io.read_template(lf))
            self.assertEqual(data["compiled_at"], "1.0.0")
            # Must not look like a datetime string
            self.assertNotIn("T", data["compiled_at"])
            self.assertNotIn("-", data["compiled_at"])

    def test_keys_sorted_alphabetically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root)
            data = json.loads(io.read_template(lf))
            keys = list(data.keys())
            self.assertEqual(keys, sorted(keys))

    def test_source_hash_and_compiled_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root, source_text="hello", compiled_text="world")
            data = json.loads(io.read_template(lf))
            entry = data["entries"][0]
            self.assertEqual(entry["source_hash"], io.hash_text("hello"))
            self.assertEqual(entry["compiled_hash"], io.hash_text("world"))

    def test_secret_not_in_lockfile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = PurePosixPath(tmp_dir)
            # Write a real YAML config file with a secret value
            config_dir = Path(tmp_dir) / "_bmad" / "core"
            config_dir.mkdir(parents=True)
            config_path = config_dir / "config.yaml"
            config_path.write_text("user_name: SECRET_VALUE\n", encoding="utf-8")
            scope = VariableScope.build(yaml_config_path=str(config_path))
            lf = str(root / "bmad.lock")
            _call_write(lf, root, var_scope=scope)
            text = io.read_template(lf)
            self.assertNotIn("SECRET_VALUE", text)
            self.assertNotIn('"value":', text)

    def test_variable_source_path_is_relative(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = PurePosixPath(io.to_posix(tmp_dir))
            # Create the config file at _bmad/core/config.yaml
            config_dir = Path(tmp_dir) / "_bmad" / "core"
            config_dir.mkdir(parents=True)
            config_path = config_dir / "config.yaml"
            config_path.write_text("user_name: World\n", encoding="utf-8")
            scope = VariableScope.build(yaml_config_path=str(config_path))
            lf = str(root / "bmad.lock")
            _call_write(lf, root, var_scope=scope)
            data = json.loads(io.read_template(lf))
            variables = data["entries"][0]["variables"]
            var = next(v for v in variables if v["name"] == "user_name")
            self.assertEqual(var["source_path"], "_bmad/core/config.yaml")

    def test_toml_variable_source_path_and_layer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = PurePosixPath("/abs/scenario")
            scope = VariableScope.build(
                toml_layers=[("team", {"agent": {"name": "PM"}})],
                toml_layer_paths=["/abs/scenario/_bmad/custom/my-skill.toml"],
            )
            lf_path = Path(tmp_dir) / "bmad.lock"
            _call_write(str(lf_path), root, var_scope=scope)
            data = json.loads(lf_path.read_text(encoding="utf-8"))
            variables = data["entries"][0]["variables"]
            var = next(v for v in variables if v["name"] == "self.agent.name")
            self.assertEqual(var["source_path"], "_bmad/custom/my-skill.toml")
            self.assertEqual(var["toml_layer"], "team")

    def test_local_scope_vars_excluded(self) -> None:
        table = {
            "regular_var": ResolvedValue(
                value="val", source="bmad-config", value_hash=io.hash_text("val")
            ),
            "ephemeral": ResolvedValue(
                value="eph", source="local-scope", value_hash=io.hash_text("eph")
            ),
        }
        scope = VariableScope(table)
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root, var_scope=scope)
            data = json.loads(io.read_template(lf))
            names = [v["name"] for v in data["entries"][0]["variables"]]
            self.assertIn("regular_var", names)
            self.assertNotIn("ephemeral", names)

    def test_no_value_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = PurePosixPath(tmp_dir)
            config_dir = Path(tmp_dir) / "_bmad" / "core"
            config_dir.mkdir(parents=True)
            config_path = config_dir / "config.yaml"
            config_path.write_text("user_name: World\n", encoding="utf-8")
            scope = VariableScope.build(yaml_config_path=str(config_path))
            lf = str(root / "bmad.lock")
            _call_write(lf, root, var_scope=scope)
            text = io.read_template(lf)
            self.assertNotIn('"value":', text)

    def test_fragment_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(io.to_posix(tmp))
            # Create the fragment file so we have a real path
            frag_dir = Path(tmp) / "core" / "skill1" / "fragments"
            frag_dir.mkdir(parents=True)
            frag_file = frag_dir / "header.template.md"
            frag_src = "# Header fragment"
            frag_file.write_text(frag_src, encoding="utf-8")

            frag_path = PurePosixPath(io.to_posix(frag_file))
            cache = CompileCache()
            cache.put((frag_path, "base"), [], frag_src)

            root_rf = ResolvedFragment(
                src="skill1/skill1.template.md",
                resolved_path=root / "core" / "skill1" / "skill1.template.md",
                resolved_from="base",
                local_props=(),
                merged_scope=(),
                nodes=[],
            )
            frag_rf = ResolvedFragment(
                src="fragments/header.template.md",
                resolved_path=frag_path,
                resolved_from="base",
                local_props=(),
                merged_scope=(),
                nodes=[],
            )
            dep_tree = [root_rf, frag_rf]

            lf = str(root / "bmad.lock")
            _call_write(lf, root, dep_tree=dep_tree, cache=cache)
            data = json.loads(io.read_template(lf))
            fragments = data["entries"][0]["fragments"]
            self.assertEqual(len(fragments), 1)
            self.assertEqual(fragments[0]["hash"], io.hash_text(frag_src))
            self.assertEqual(fragments[0]["resolved_from"], "base")
            # path must be root-relative
            self.assertFalse(fragments[0]["path"].startswith("/"))

    def test_glob_inputs_is_empty_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root)
            data = json.loads(io.read_template(lf))
            self.assertEqual(data["entries"][0]["glob_inputs"], [])

    def test_variant_null_when_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root, target_ide=None)
            data = json.loads(io.read_template(lf))
            self.assertIsNone(data["entries"][0]["variant"])

    def test_variant_set_when_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root, target_ide="cursor")
            data = json.loads(io.read_template(lf))
            self.assertEqual(data["entries"][0]["variant"], "cursor")


# ---------------------------------------------------------------------------
# TestDeterminism
# ---------------------------------------------------------------------------

class TestDeterminism(unittest.TestCase):

    def test_byte_identical_on_two_writes(self) -> None:
        # AC 7: rewriting the same lockfile path with identical inputs must be
        # byte-identical — exercises the read-modify-write upsert path, not
        # just two independent fresh writes.
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            kwargs = dict(
                source_text="hello world",
                compiled_text="rendered output",
                target_ide=None,
            )
            _call_write(lf, root, **kwargs)
            b1 = Path(lf).read_bytes()
            _call_write(lf, root, **kwargs)
            b2 = Path(lf).read_bytes()
            self.assertEqual(b1, b2)


# ---------------------------------------------------------------------------
# TestForwardCompat
# ---------------------------------------------------------------------------

class TestForwardCompat(unittest.TestCase):

    def test_unknown_top_level_key_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            initial = {
                "version": 1,
                "compiled_at": "1.0.0",
                "bmad_version": "1.0.0",
                "entries": [],
                "future_key": "preserved_value",
            }
            Path(lf).write_text(json.dumps(initial), encoding="utf-8")
            _call_write(lf, root)
            data = json.loads(io.read_template(lf))
            self.assertEqual(data["future_key"], "preserved_value")

    def test_existing_skill_entry_updated_not_duplicated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root, skill_basename="skill1", source_text="v1")
            _call_write(lf, root, skill_basename="skill1", source_text="v2")
            data = json.loads(io.read_template(lf))
            skill_entries = [e for e in data["entries"] if e.get("skill") == "skill1"]
            self.assertEqual(len(skill_entries), 1)
            self.assertEqual(skill_entries[0]["source_hash"], io.hash_text("v2"))

    def test_other_skill_entry_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = PurePosixPath(tmp)
            lf = str(root / "bmad.lock")
            _call_write(lf, root, skill_basename="skill-a", source_text="aaa")
            _call_write(lf, root, skill_basename="skill-b", source_text="bbb")
            _call_write(lf, root, skill_basename="skill-a", source_text="aaa-v2")
            data = json.loads(io.read_template(lf))
            names = [e.get("skill") for e in data["entries"]]
            self.assertIn("skill-a", names)
            self.assertIn("skill-b", names)

    def test_corrupt_entries_field_does_not_crash(self) -> None:
        # Round 3 EC-1: a dict-shaped lockfile whose ``entries`` key is null,
        # an int, or a string would TypeError on list(...) (None) or silently
        # explode a string into per-character entries. Treat as fresh start.
        for bad in (None, 42, "abc"):
            with tempfile.TemporaryDirectory() as tmp:
                root = PurePosixPath(tmp)
                lf = str(root / "bmad.lock")
                Path(lf).write_text(
                    json.dumps({"version": 1, "entries": bad}), encoding="utf-8"
                )
                _call_write(lf, root)
                data = json.loads(io.read_template(lf))
                self.assertEqual(len(data["entries"]), 1)
                self.assertEqual(data["entries"][0]["skill"], "skill1")


# ---------------------------------------------------------------------------
# TestVersionMismatch
# ---------------------------------------------------------------------------

class TestVersionMismatch(unittest.TestCase):

    def test_version_mismatch_raises(self) -> None:
        """write a v2 lockfile into the fixture tree, compile should raise."""
        import pathlib
        repo_root = pathlib.Path(__file__).resolve().parents[2]
        fixture_scenario = (
            repo_root / "test" / "fixtures" / "compile" / "variable-resolution"
        )
        lockfile_path = fixture_scenario / "_bmad" / "_config" / "bmad.lock"
        try:
            lockfile_path.parent.mkdir(parents=True, exist_ok=True)
            lockfile_path.write_text(
                json.dumps({"version": 2, "compiled_at": "1.0.0",
                            "bmad_version": "1.0.0", "entries": []}),
                encoding="utf-8",
            )
            skill = fixture_scenario / "core" / "var-resolution-skill"
            with tempfile.TemporaryDirectory() as tmp_out:
                with self.assertRaises(errors.LockfileVersionMismatchError) as ctx:
                    engine.compile_skill(str(skill), tmp_out)
            self.assertEqual(ctx.exception.code, "LOCKFILE_VERSION_MISMATCH")
            self.assertIn("upgrade", ctx.exception.hint or "")
        finally:
            lockfile_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
