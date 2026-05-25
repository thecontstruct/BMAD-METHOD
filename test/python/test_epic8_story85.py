"""Story 8.5 unit tests: engine compile-mode dispatch and JIT sentinel emission.

Tests cover: _strip_string_and_comment_tokens parity (AC-13), _read_render_mode (AC-2),
_props_hash (AC-6), _discover_components (AC-1, AC-3, AC-9), _assemble_nodes (AC-7),
post-parse Text scan (AC-4), fragment-body scan (AC-5), compile_skill() atomicity (AC-8),
lockfile emit_fn migration event (AC-10).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

BMAD_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS = str(BMAD_ROOT / "src" / "scripts")
_TEST_PY = str(BMAD_ROOT / "test" / "python")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
if _TEST_PY not in sys.path:
    sys.path.insert(0, _TEST_PY)

from bmad_compile import errors, lockfile, parser
from bmad_compile.component_runner import ComponentRunner, MockComponentRunner
from bmad_compile.engine import (
    EnrichedInvocation,
    _assemble_nodes,
    _discover_components,
    _fragment_body_scan,
    _post_parse_text_scan,
    _props_hash,
    _read_render_mode,
    _render,
    _strip_string_and_comment_tokens,
    compile_skill,
)
from bmad_compile.errors import ComponentBatchError, ComponentError


def _ci(name: str, props=()) -> parser.ComponentInvocation:
    return parser.ComponentInvocation(name=name, props=tuple(props), line=1, col=1)


# --------------------------------------------------------------------------- #
# Class 1 — AC-13: strip token parity with wrapper's copy
# --------------------------------------------------------------------------- #

class TestStripTokenParity(unittest.TestCase):
    def test_a_strip_matches_wrapper_copy(self) -> None:
        from test_epic8_story83 import STRIP_TOKEN_VECTORS
        for source, expected in STRIP_TOKEN_VECTORS:
            result = _strip_string_and_comment_tokens(source)
            self.assertEqual(result, expected, f"mismatch for source: {source!r}")


# --------------------------------------------------------------------------- #
# Class 2 — AC-2: _read_render_mode
# --------------------------------------------------------------------------- #

class TestReadRenderMode(unittest.TestCase):
    def test_b_absent_returns_compile(self) -> None:
        src = 'def render(ctx, **props):\n    return ""\n'
        self.assertEqual(_read_render_mode(src, "Foo"), "compile")

    def test_b2_jit_returns_jit(self) -> None:
        src = 'RENDER_MODE = "jit"\nRENDER_ERROR_FALLBACK = "fb"\n'
        self.assertEqual(_read_render_mode(src, "Foo"), "jit")

    def test_b3_compile_explicit(self) -> None:
        src = 'RENDER_MODE = "compile"\n'
        self.assertEqual(_read_render_mode(src, "Foo"), "compile")

    def test_b4_invalid_raises(self) -> None:
        src = 'RENDER_MODE = "batch"\n'
        with self.assertRaises(errors.CompilerError) as ctx:
            _read_render_mode(src, "Foo")
        self.assertIn("Foo", str(ctx.exception))

    def test_b5_docstring_false_positive_blocked(self) -> None:
        # Triple-quoted docstring containing RENDER_MODE = "jit" is tokenize-stripped.
        src = '"""\nRENDER_MODE = "jit"\n"""\ndef render(ctx, **props):\n    return ""\n'
        self.assertEqual(_read_render_mode(src, "Foo"), "compile")


# --------------------------------------------------------------------------- #
# Class 3 — AC-6: _props_hash
# --------------------------------------------------------------------------- #

class TestPropsHash(unittest.TestCase):
    def test_c_empty_props(self) -> None:
        a = _props_hash(())
        b = _props_hash(())
        self.assertEqual(a, b)
        self.assertEqual(len(a), 16)

    def test_c2_deterministic_sort(self) -> None:
        h1 = _props_hash((("b", 1), ("a", 2)))
        h2 = _props_hash((("a", 2), ("b", 1)))
        self.assertEqual(h1, h2)

    def test_c3_hash_length(self) -> None:
        self.assertEqual(len(_props_hash((("x", "y"),))), 16)

    def test_c4_different_props_differ(self) -> None:
        self.assertNotEqual(_props_hash((("x", 1),)), _props_hash((("x", 2),)))


# --------------------------------------------------------------------------- #
# Class 4 — AC-1, AC-3, AC-9: _discover_components
# --------------------------------------------------------------------------- #

class TestDiscoverComponents(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.skill_root = Path(self.tmp.name)
        (self.skill_root / "components").mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self, filename: str, content: str) -> None:
        (self.skill_root / "components" / filename).write_text(content, encoding="utf-8")

    def test_d_no_components(self) -> None:
        flat = [parser.Text(content="hello", line=1, col=1),
                parser.VarRuntime(name="x", line=1, col=6)]
        enriched, compile_inv, jit_inv = _discover_components(flat, self.skill_root)
        self.assertEqual(len(enriched), 2)
        self.assertEqual(compile_inv, [])
        self.assertEqual(jit_inv, [])

    def test_d2_compile_and_jit(self) -> None:
        self._write("date_banner.py",
                    'RENDER_MODE = "compile"\ndef render(ctx, **props):\n    return ""\n')
        self._write("sprint_banner.py",
                    'RENDER_MODE = "jit"\nRENDER_ERROR_FALLBACK = "fb"\n'
                    'def render(ctx, **props):\n    return ""\n')
        flat = [
            parser.Text(content="A", line=1, col=1),
            _ci("DateBanner"),
            parser.Text(content="B", line=1, col=1),
            _ci("SprintBanner", (("weeks_left", 2),)),
        ]
        enriched, compile_inv, jit_inv = _discover_components(flat, self.skill_root)
        self.assertEqual(len(enriched), 4)
        self.assertEqual(len(compile_inv), 1)
        self.assertEqual(len(jit_inv), 1)
        self.assertEqual(compile_inv[0].render_mode, "compile")
        self.assertEqual(compile_inv[0].original.name, "DateBanner")
        self.assertEqual(compile_inv[0].token_index, 1)
        self.assertEqual(jit_inv[0].render_mode, "jit")
        self.assertEqual(jit_inv[0].original.name, "SprintBanner")
        self.assertEqual(jit_inv[0].token_index, 3)
        self.assertTrue(compile_inv[0].component_abs_path.endswith("date_banner.py"))

    def test_d3_missing_file_raises(self) -> None:
        flat = [_ci("Missing")]
        with self.assertRaises(errors.CompilerError) as ctx:
            _discover_components(flat, self.skill_root)
        self.assertIn("Missing", str(ctx.exception))

    def test_d4_collision_raises(self) -> None:
        # FooBar → foo_bar.py; Foo_Bar → foo_bar.py (snake-case transform collapses)
        self._write("foo_bar.py", 'def render(ctx, **props):\n    return ""\n')
        flat = [_ci("FooBar"), _ci("Foo_Bar")]
        with self.assertRaises(errors.CompilerError) as ctx:
            _discover_components(flat, self.skill_root)
        msg = str(ctx.exception)
        self.assertIn("collision", msg)
        self.assertIn("FooBar", msg)
        self.assertIn("Foo_Bar", msg)

    def test_d5_invalid_render_mode_raises(self) -> None:
        self._write("foo.py", 'RENDER_MODE = "typo"\n')
        flat = [_ci("Foo")]
        with self.assertRaises(errors.CompilerError):
            _discover_components(flat, self.skill_root)

    def test_d6_jit_missing_fallback_raises(self) -> None:
        self._write("foo.py", 'RENDER_MODE = "jit"\n'
                              'def render(ctx, **props):\n    return ""\n')
        flat = [_ci("Foo")]
        with self.assertRaises(errors.CompilerError) as ctx:
            _discover_components(flat, self.skill_root)
        self.assertIn("RENDER_ERROR_FALLBACK", str(ctx.exception))

    def test_d7_jit_with_fallback_ok(self) -> None:
        self._write("foo.py", 'RENDER_MODE = "jit"\nRENDER_ERROR_FALLBACK = "fb"\n'
                              'def render(ctx, **props):\n    return ""\n')
        flat = [_ci("Foo")]
        enriched, compile_inv, jit_inv = _discover_components(flat, self.skill_root)
        self.assertEqual(len(jit_inv), 1)
        self.assertEqual(jit_inv[0].render_mode, "jit")


# --------------------------------------------------------------------------- #
# Class 5 — AC-7: _assemble_nodes
# --------------------------------------------------------------------------- #

class TestAssembleNodes(unittest.TestCase):
    def test_e_no_components(self) -> None:
        flat = [parser.Text(content="hello", line=1, col=1),
                parser.VarRuntime(name="x", line=1, col=6)]
        self.assertEqual(_assemble_nodes(flat, {}), "hello{x}")

    def test_e2_compile_node(self) -> None:
        inv = EnrichedInvocation(
            original=_ci("Foo"), render_mode="compile",
            component_abs_path="/fake", token_index=0,
        )
        self.assertEqual(_assemble_nodes([inv], {0: "OUTPUT"}), "OUTPUT")

    def test_e3_jit_node(self) -> None:
        inv = EnrichedInvocation(
            original=_ci("MyComp", (("a", 1),)), render_mode="jit",
            component_abs_path="/fake", token_index=0,
        )
        out = _assemble_nodes([inv], {})
        self.assertTrue(out.startswith("<!-- BMAD-JIT:MyComp:"))
        self.assertTrue(out.endswith(" -->"))
        # 16-hex-char suffix
        hash_part = out[len("<!-- BMAD-JIT:MyComp:"):-len(" -->")]
        self.assertEqual(len(hash_part), 16)
        self.assertTrue(all(c in "0123456789abcdef" for c in hash_part))

    def test_e4_mixed(self) -> None:
        compile_inv = EnrichedInvocation(
            original=_ci("Foo"), render_mode="compile",
            component_abs_path="/fake", token_index=1,
        )
        jit_inv = EnrichedInvocation(
            original=_ci("Bar"), render_mode="jit",
            component_abs_path="/fake", token_index=3,
        )
        flat = [
            parser.Text(content="A:", line=1, col=1),
            compile_inv,
            parser.Text(content=":B:", line=1, col=1),
            jit_inv,
            parser.VarRuntime(name="x", line=1, col=1),
        ]
        out = _assemble_nodes(flat, {1: "C"})
        self.assertTrue(out.startswith("A:C:B:<!-- BMAD-JIT:Bar:"))
        self.assertTrue(out.endswith(" -->{x}"))

    def test_e5_missing_buffer_key(self) -> None:
        inv = EnrichedInvocation(
            original=_ci("Foo"), render_mode="compile",
            component_abs_path="/fake", token_index=0,
        )
        with self.assertRaises(RuntimeError) as ctx:
            _assemble_nodes([inv], {})
        self.assertIn("Foo", str(ctx.exception))


# --------------------------------------------------------------------------- #
# Class 5b — AC-7/AC-8 backward compat for no-component skills
# --------------------------------------------------------------------------- #

class TestNoComponentsRegression(unittest.TestCase):
    def test_e6_no_components_identical_output(self) -> None:
        """A skill with no component tags compiles to the same bytes as _render()."""
        flat = [
            parser.Text(content="# Hello\n", line=1, col=1),
            parser.VarRuntime(name="user_name", line=2, col=1),
            parser.Text(content="\n", line=2, col=12),
        ]
        rendered_via_assemble = _assemble_nodes(flat, {})
        rendered_via_render = _render(flat)
        self.assertEqual(rendered_via_assemble, rendered_via_render)


# --------------------------------------------------------------------------- #
# Class 6 — AC-8: atomicity (ComponentBatchError prevents writes)
# --------------------------------------------------------------------------- #

class TestAtomicity(unittest.TestCase):
    """Wires a real fixture skill + MockComponentRunner; verifies no writes on failure."""

    def _make_skill(self, tmp: Path, with_component: bool = True) -> tuple[Path, Path]:
        """Returns (skill_dir, install_dir). Lays out a minimal valid skill."""
        scenario = tmp / "scenario"
        scenario.mkdir()
        bmad = scenario / "_bmad"
        (bmad / "_config").mkdir(parents=True)
        core = scenario / "core"
        core.mkdir()
        skill_dir = core / "myskill"
        skill_dir.mkdir()
        if with_component:
            (skill_dir / "components").mkdir()
            (skill_dir / "components" / "foo.py").write_text(
                'def render(ctx, **props):\n    return "out"\n', encoding="utf-8"
            )
            (skill_dir / "myskill.template.md").write_text(
                "# Hello\n<Foo />\n", encoding="utf-8"
            )
        else:
            (skill_dir / "myskill.template.md").write_text("# Hello\n", encoding="utf-8")
        install = tmp / "install"
        install.mkdir()
        return skill_dir, install

    def test_f_component_batch_error_no_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_dir, install_dir = self._make_skill(Path(tmp))
            lockfile_path = Path(tmp) / "scenario" / "_bmad" / "_config" / "bmad.lock"
            output_path = install_dir / "myskill" / "SKILL.md"

            failing_runner = MockComponentRunner(
                batch_results={1: ComponentError("boom", component_name="Foo")}
            )
            with self.assertRaises(ComponentBatchError):
                compile_skill(
                    skill_dir, install_dir,
                    component_runner=failing_runner,
                )
            self.assertFalse(output_path.exists(),
                             "SKILL.md must not be written when ComponentBatchError raised")
            self.assertFalse(lockfile_path.exists(),
                             "lockfile must not be written when ComponentBatchError raised")


# --------------------------------------------------------------------------- #
# Class 7 — AC-4: post-parse Text scan (fence-aware)
# --------------------------------------------------------------------------- #

class TestPostParseTextScan(unittest.TestCase):
    """Direct tests for _post_parse_text_scan. The parser splits Text at every `<`,
    so this scan is functionally a backstop for content injected via resolver
    substitutions; we test it by handing it constructed Text nodes."""

    def test_h_fenced_pascalcase_no_error(self) -> None:
        node = parser.Text(
            content="# Hello\n```\n<DateBanner />\n```\nDone\n",
            line=1, col=1,
        )
        _post_parse_text_scan([node])  # fence-stripping suppresses the probe

    def test_h2_unfenced_pascalcase_raises(self) -> None:
        node = parser.Text(content="head\n<DateBanner foo\nmore", line=1, col=1)
        with self.assertRaises(errors.CompilerError) as ctx:
            _post_parse_text_scan([node])
        self.assertIn("Component tag", str(ctx.exception))

    def test_h3_allcaps_tag_no_error(self) -> None:
        node = parser.Text(content="# Hello\n<HTML>foo</HTML>\nDone\n", line=1, col=1)
        _post_parse_text_scan([node])  # probe requires lowercase after cap


# --------------------------------------------------------------------------- #
# Class 8 — AC-5: fragment-body scan
# --------------------------------------------------------------------------- #

class _StubFrag:
    """Minimal stand-in for resolver.ResolvedFragment used by the scan."""
    def __init__(self, src: str, resolved_path: str, resolved_from: str = "base") -> None:
        from bmad_compile.io import PurePosixPath
        self.src = src
        self.resolved_path = PurePosixPath(resolved_path)
        self.resolved_from = resolved_from


class _StubCache:
    def __init__(self, mapping: dict) -> None:
        self._m = mapping

    def get_source(self, key: tuple) -> str:
        return self._m[key]


class TestFragmentBodyScan(unittest.TestCase):
    def test_i_no_fragments_noop(self) -> None:
        # dep_tree[0] is root → loop body skipped.
        _fragment_body_scan([_StubFrag("root", "/root")], _StubCache({}))

    def test_i2_fragment_with_component_raises(self) -> None:
        from bmad_compile.io import PurePosixPath
        frag = _StubFrag("fragments/x.md", "/abs/fragments/x.md")
        cache = _StubCache({
            (PurePosixPath("/abs/fragments/x.md"), "base"): "head\n<DateBanner />\ntail",
        })
        with self.assertRaises(errors.CompilerError) as ctx:
            _fragment_body_scan([_StubFrag("root", "/root"), frag], cache)
        self.assertIn("fragments/x.md", str(ctx.exception))

    def test_i3_fragment_fenced_component_ok(self) -> None:
        from bmad_compile.io import PurePosixPath
        frag = _StubFrag("fragments/x.md", "/abs/fragments/x.md")
        cache = _StubCache({
            (PurePosixPath("/abs/fragments/x.md"), "base"):
                "head\n```\n<DateBanner />\n```\ntail",
        })
        _fragment_body_scan([_StubFrag("root", "/root"), frag], cache)  # no error


# --------------------------------------------------------------------------- #
# Class 9 — AC-10: lockfile schema migration event
# --------------------------------------------------------------------------- #

class TestLockfileMigrationEvent(unittest.TestCase):
    def _write_v1_lockfile(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # A v1 lockfile is just version=1 with no components.
        path.write_text(json.dumps({"version": 1, "entries": []}, indent=2), encoding="utf-8")

    def _call_write(self, lockfile_path: Path, components: list, emit_fn) -> None:
        # Minimal-stub call: use a fake var_scope and cache that the write path tolerates
        # for the no-fragment / no-variable case.
        from bmad_compile import resolver
        from bmad_compile.io import PurePosixPath
        scenario_root = PurePosixPath(str(lockfile_path.parent.parent.parent))
        # Need a CompileCache and VariableScope; build with the resolver helpers.
        cache = resolver.CompileCache()
        var_scope = resolver.VariableScope.build(
            yaml_config_path=None,
            module_yaml_paths=None,
            user_yaml_path=None,
            install_flags=None,
            toml_layers=None,
            toml_layer_paths=None,
            scenario_root=str(scenario_root),
            toml_warning_sink=None,
        )
        lockfile.write_skill_entry(
            str(lockfile_path),
            scenario_root,
            "myskill",
            source_text="x",
            compiled_text="x",
            dep_tree=[None],
            var_scope=var_scope,
            target_ide=None,
            cache=cache,
            components=components,
            emit_fn=emit_fn,
        )

    def test_g_emit_migration_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lockfile_path = Path(tmp) / "scenario" / "_bmad" / "_config" / "bmad.lock"
            self._write_v1_lockfile(lockfile_path)
            events: list = []
            self._call_write(
                lockfile_path,
                components=[{"name": "Foo"}, {"name": "Bar"}],
                emit_fn=events.append,
            )
            migration = [e for e in events if e.get("kind") == "lockfile_schema_migration"]
            self.assertEqual(len(migration), 1)
            ev = migration[0]
            self.assertEqual(ev["old_version"], 1)
            self.assertEqual(ev["new_version"], 3)  # Story 10.26: _VERSION bumped to 3
            self.assertEqual(ev["skill_id"], "myskill")
            self.assertEqual(ev["new_component_names"], ["Bar", "Foo"])

    def test_g2_no_event_empty_components(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lockfile_path = Path(tmp) / "scenario" / "_bmad" / "_config" / "bmad.lock"
            self._write_v1_lockfile(lockfile_path)
            events: list = []
            # empty components → no event
            self._call_write(lockfile_path, components=[], emit_fn=events.append)
            self.assertEqual(
                [e for e in events if e.get("kind") == "lockfile_schema_migration"],
                [],
            )

    def test_g3_v2_lockfile_emits_v3_migration_event(self) -> None:
        """Story 10.26: writing to a v2 lockfile emits a v2→v3 migration event.
        (Previously: test_g3_no_event_for_v2_lockfile — when v2 was current, no event
        fired. Now v3 is current so v2→v3 migration fires.)
        """
        with tempfile.TemporaryDirectory() as tmp:
            lockfile_path = Path(tmp) / "scenario" / "_bmad" / "_config" / "bmad.lock"
            lockfile_path.parent.mkdir(parents=True, exist_ok=True)
            lockfile_path.write_text(
                json.dumps({"version": 2, "entries": []}, indent=2), encoding="utf-8"
            )
            events: list = []
            self._call_write(
                lockfile_path,
                components=[{"name": "Foo"}],
                emit_fn=events.append,
            )
            migration = [e for e in events if e.get("kind") == "lockfile_schema_migration"]
            # Exactly 1 v2→v3 migration event (v1→v2 block is tightened to v1 only).
            self.assertEqual(len(migration), 1)
            ev = migration[0]
            self.assertEqual(ev["old_version"], 2)
            self.assertEqual(ev["new_version"], 3)
            self.assertIn("added_keys", ev)
            self.assertIn("artifacts", ev["added_keys"])
            self.assertIn("deprecations", ev["added_keys"])

    def test_g4_no_event_when_emit_fn_none(self) -> None:
        # Default emit_fn=None must produce no exception and no event.
        with tempfile.TemporaryDirectory() as tmp:
            lockfile_path = Path(tmp) / "scenario" / "_bmad" / "_config" / "bmad.lock"
            self._write_v1_lockfile(lockfile_path)
            self._call_write(lockfile_path, components=[{"name": "Foo"}], emit_fn=None)


if __name__ == "__main__":
    unittest.main()
