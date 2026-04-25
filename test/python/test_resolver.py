"""Unit tests for bmad_compile.resolver — fragment resolution, cycles, cascade."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.scripts.bmad_compile import errors, io, parser
from src.scripts.bmad_compile.io import PurePosixPath
from src.scripts.bmad_compile.resolver import (
    CompileCache,
    ResolveContext,
    ResolvedFragment,
    ResolvedValue,
    VariableScope,
    resolve,
)


# -- helpers ------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _context(
    scenario_root: Path,
    *,
    skill_subdir: tuple[str, ...] = ("core", "skill1"),
    current_module: str = "core",
    extra_module_roots: dict[str, Path] | None = None,
    override_root: Path | None = None,
    target_ide: str | None = None,
    root_resolved_from: str = "base",
    var_scope: VariableScope | None = None,
) -> ResolveContext:
    skill_dir = scenario_root.joinpath(*skill_subdir)
    module_roots = {
        current_module: PurePosixPath(
            scenario_root.joinpath(skill_subdir[0]).as_posix()
        )
    }
    if extra_module_roots:
        for name, p in extra_module_roots.items():
            module_roots[name] = PurePosixPath(p.as_posix())
    return ResolveContext(
        skill_dir=PurePosixPath(skill_dir.as_posix()),
        module_roots=module_roots,
        current_module=current_module,
        override_root=(
            PurePosixPath(override_root.as_posix())
            if override_root is not None
            else None
        ),
        target_ide=target_ide,
        root_resolved_from=root_resolved_from,
        var_scope=var_scope,
    )


def _render(nodes: list[parser.AstNode]) -> str:
    """Render the post-resolve AST to text, mirroring engine._render's
    contract — non-Text nodes (un-expanded Include, etc.) raise instead of
    being silently dropped. R7-P4: dropping them in the test helper would
    let an Include-not-expanded regression pass `assertIn(...)` checks
    even though production would raise; the helper must be as strict as
    the engine."""
    parts: list[str] = []
    for n in nodes:
        if isinstance(n, parser.Text):
            parts.append(n.content)
        else:
            raise AssertionError(
                f"_render received non-Text node {type(n).__name__} — "
                "resolver.resolve() should have inlined every Include"
            )
    return "".join(parts)


def _render_v13(nodes: list[parser.AstNode]) -> str:
    """Story 1.3 render helper: handles Text and VarRuntime passthrough."""
    parts: list[str] = []
    for n in nodes:
        if isinstance(n, parser.Text):
            parts.append(n.content)
        elif isinstance(n, parser.VarRuntime):
            parts.append("{" + n.name + "}")
        else:
            raise AssertionError(
                f"_render_v13 received unexpected node {type(n).__name__}"
            )
    return "".join(parts)


# -- tests --------------------------------------------------------------------


class TestIncludeChain(unittest.TestCase):
    def test_two_level_chain_inlines_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            _write(
                skill / "fragments" / "a.template.md",
                'a_pre <<include path="fragments/b.template.md">> a_post',
            )
            _write(skill / "fragments" / "b.template.md", "b_content")

            src_text = 'template_pre <<include path="fragments/a.template.md">> template_post'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            cache = CompileCache()
            flat, dep = resolve(
                ast, ctx, cache, root_src="skill1.template.md", root_source=src_text
            )

            self.assertEqual(
                _render(flat),
                "template_pre a_pre b_content a_post template_post",
            )
            self.assertEqual(len(dep), 3)
            self.assertEqual(dep[0].src, "skill1.template.md")
            self.assertEqual(dep[0].resolved_from, "base")
            self.assertEqual(dep[1].src, "fragments/a.template.md")
            self.assertEqual(dep[1].resolved_from, "base")
            self.assertEqual(dep[2].src, "fragments/b.template.md")
            self.assertEqual(dep[2].resolved_from, "base")


class TestCycles(unittest.TestCase):
    def test_direct_self_cycle_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            _write(
                skill / "fragments" / "a.template.md",
                '<<include path="fragments/a.template.md">>',
            )
            src_text = '<<include path="fragments/a.template.md">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            with self.assertRaises(errors.CyclicIncludeError) as cm:
                resolve(ast, ctx, CompileCache(), root_source=src_text)
            self.assertEqual(
                cm.exception.chain,
                ["fragments/a.template.md", "fragments/a.template.md"],
            )

    def test_indirect_cycle_raises_with_full_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            _write(
                skill / "fragments" / "a.template.md",
                '<<include path="fragments/b.template.md">>',
            )
            _write(
                skill / "fragments" / "b.template.md",
                '<<include path="fragments/a.template.md">>',
            )
            src_text = '<<include path="fragments/a.template.md">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            with self.assertRaises(errors.CyclicIncludeError) as cm:
                resolve(ast, ctx, CompileCache(), root_source=src_text)
            self.assertEqual(
                cm.exception.chain,
                [
                    "fragments/a.template.md",
                    "fragments/b.template.md",
                    "fragments/a.template.md",
                ],
            )
            # The back-edge-containing file is the one the author must edit.
            self.assertEqual(cm.exception.file, "fragments/b.template.md")

    def test_three_step_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            _write(
                skill / "fragments" / "a.template.md",
                '<<include path="fragments/b.template.md">>',
            )
            _write(
                skill / "fragments" / "b.template.md",
                '<<include path="fragments/c.template.md">>',
            )
            _write(
                skill / "fragments" / "c.template.md",
                '<<include path="fragments/a.template.md">>',
            )
            src_text = '<<include path="fragments/a.template.md">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            with self.assertRaises(errors.CyclicIncludeError) as cm:
                resolve(ast, ctx, CompileCache(), root_source=src_text)
            self.assertEqual(
                cm.exception.chain,
                [
                    "fragments/a.template.md",
                    "fragments/b.template.md",
                    "fragments/c.template.md",
                    "fragments/a.template.md",
                ],
            )

    def test_diamond_dep_not_a_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            _write(skill / "fragments" / "shared.template.md", "S")
            src_text = (
                '<<include path="fragments/shared.template.md">>'
                '<<include path="fragments/shared.template.md">>'
            )
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            flat, dep = resolve(ast, ctx, CompileCache(), root_source=src_text)
            self.assertEqual(_render(flat), "SS")
            # Root + two sibling entries.
            self.assertEqual(len(dep), 3)


class TestDepthGuard(unittest.TestCase):
    """Pins the `_MAX_INCLUDE_DEPTH` boundary so the `>=` vs `>` comparison
    cannot silently drift. See resolver._walk_nodes depth-guard."""

    def test_depth_below_cap_succeeds(self) -> None:
        """Chain with depth one below the cap must succeed."""
        from src.scripts.bmad_compile import resolver
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            # With cap=2: root body walks at depth=0, f0 body at depth=1
            # (1 < 2 → passes). f0 is a text leaf so no deeper recursion.
            _write(skill / "fragments" / "f0.template.md", "leaf")
            src_text = '<<include path="fragments/f0.template.md">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            with mock.patch.object(resolver, "_MAX_INCLUDE_DEPTH", 2):
                flat, _ = resolve(
                    ast, ctx, CompileCache(), root_source=src_text
                )
            self.assertEqual(_render(flat), "leaf")

    def test_depth_at_cap_raises(self) -> None:
        """A chain that would enter a body at depth == cap must raise."""
        from src.scripts.bmad_compile import resolver
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            # With cap=1: root body walks at depth=0 (0 < 1 passes), then
            # enters f0 body at depth=1 (1 >= 1 → raises).
            _write(skill / "fragments" / "f0.template.md", "leaf")
            src_text = '<<include path="fragments/f0.template.md">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            with mock.patch.object(resolver, "_MAX_INCLUDE_DEPTH", 1):
                with self.assertRaises(errors.CyclicIncludeError) as cm:
                    resolve(
                        ast, ctx, CompileCache(), root_source=src_text
                    )
            # Error message must reflect the configured cap.
            self.assertIn("1-level cap", cm.exception.desc)

    def test_depth_one_past_cap_raises_with_chain(self) -> None:
        """Chain of N fragments at cap=N-1 raises and reports the chain."""
        from src.scripts.bmad_compile import resolver
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            _write(
                skill / "fragments" / "f0.template.md",
                '<<include path="fragments/f1.template.md">>',
            )
            _write(skill / "fragments" / "f1.template.md", "leaf")
            src_text = '<<include path="fragments/f0.template.md">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            # cap=2: root body at depth=0, f0 body at depth=1 (passes),
            # f1 body at depth=2 (2 >= 2 → raises).
            with mock.patch.object(resolver, "_MAX_INCLUDE_DEPTH", 2):
                with self.assertRaises(errors.CyclicIncludeError) as cm:
                    resolve(
                        ast, ctx, CompileCache(), root_source=src_text
                    )
            # The visited stack at the raise site holds the two authored
            # includes traversed so far.
            self.assertEqual(
                cm.exception.chain,
                ["fragments/f0.template.md", "fragments/f1.template.md"],
            )


class TestMissingFragment(unittest.TestCase):
    def test_missing_fragment_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            skill.mkdir(parents=True)
            src_text = '<<include path="fragments/nope.template.md">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            with self.assertRaises(errors.MissingFragmentError) as cm:
                resolve(ast, ctx, CompileCache(), root_source=src_text)
            self.assertEqual(cm.exception.line, 1)
            self.assertEqual(cm.exception.col, 1)

    def test_missing_fragment_hint_names_concrete_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            skill.mkdir(parents=True)
            src_text = '<<include path="fragments/nope.template.md">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            with self.assertRaises(errors.MissingFragmentError) as cm:
                resolve(ast, ctx, CompileCache(), root_source=src_text)
            hint = cm.exception.hint or ""
            self.assertIn("create", hint)
            self.assertIn(".template.md", hint)

    def test_missing_fragment_hint_uses_well_formed_directive_syntax(self) -> None:
        """R5-P3: the hint's example directive must read `<<include
        path="...">>` with the closing `>>` — not `<<include path="...">`
        with a single `>` (which would mislead authors into copying a
        malformed shape that the parser then rejects)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            skill.mkdir(parents=True)
            src_text = '<<include path="fragments/nope.template.md">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            with self.assertRaises(errors.MissingFragmentError) as cm:
                resolve(ast, ctx, CompileCache(), root_source=src_text)
            hint = cm.exception.hint or ""
            self.assertIn('<<include path="...">>', hint)
            self.assertNotIn('<<include path="...">,', hint + ",")  # guard against a `>,` regression
            self.assertNotIn('<<include path="..."> ', hint)

    def test_include_targeting_directory_raises_missing_fragment(self) -> None:
        """R4-P2: tier probes use `is_file`, not `path_exists`, so a directory
        target does not trip a raw `IsADirectoryError` in `read_template`.
        Instead the cascade falls through and raises MissingFragmentError —
        the typed error in the CompilerError taxonomy."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            skill.mkdir(parents=True)
            # Create a directory where a fragment is being probed.
            (skill / "fragments" / "subdir").mkdir(parents=True)
            src_text = '<<include path="fragments/subdir">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            # Must NOT raise IsADirectoryError / PermissionError / OSError —
            # must raise the typed MissingFragmentError.
            with self.assertRaises(errors.MissingFragmentError):
                resolve(ast, ctx, CompileCache(), root_source=src_text)


class TestPrecedence(unittest.TestCase):
    """AC 3: 5-tier cascade with collapse-down-the-ladder semantics."""

    def _build_all_tiers(self, root: Path) -> tuple[Path, Path, Path]:
        """Populate the full precedence cascade. Returns
        (skill_dir, override_root, scenario_root)."""
        skill = root / "core" / "precedence-skill"
        override = root / "_bmad" / "custom"
        _write(
            skill / "precedence-skill.template.md",
            'root_pre <<include path="fragments/menu.template.md">> root_post',
        )
        _write(skill / "fragments" / "menu.template.md", "BASE BODY")
        _write(skill / "fragments" / "menu.cursor.template.md", "VARIANT BODY")
        _write(
            override / "fragments" / "menu.template.md",
            "USER-OVERRIDE BODY",
        )
        _write(
            override
            / "fragments"
            / "core"
            / "precedence-skill"
            / "menu.template.md",
            "USER-MODULE-FRAGMENT BODY",
        )
        _write(
            override
            / "fragments"
            / "core"
            / "precedence-skill"
            / "SKILL.template.md",
            'full_skill_pre <<include path="fragments/menu.template.md">> full_skill_post',
        )
        return skill, override, root

    def test_precedence_user_full_skill_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill, override, _ = self._build_all_tiers(root)
            # Engine-level swap: read the override SKILL.template.md and
            # mark root_resolved_from = "user-full-skill".
            root_path = (
                override
                / "fragments"
                / "core"
                / "precedence-skill"
                / "SKILL.template.md"
            )
            src_text = root_path.read_text(encoding="utf-8")
            ast = parser.parse(src_text, "SKILL.template.md")
            ctx = _context(
                root,
                skill_subdir=("core", "precedence-skill"),
                override_root=override,
                root_resolved_from="user-full-skill",
            )
            cache = CompileCache()
            _, dep = resolve(
                ast,
                ctx,
                cache,
                root_src="SKILL.template.md",
                root_path=PurePosixPath(root_path.as_posix()),
                root_source=src_text,
            )
            self.assertEqual(dep[0].resolved_from, "user-full-skill")

    def test_precedence_collapses_down_the_ladder(self) -> None:
        expected_tiers = [
            ("user-module-fragment", "USER-MODULE-FRAGMENT BODY"),
            ("user-override", "USER-OVERRIDE BODY"),
            ("base", "BASE BODY"),
        ]
        # Walk top-down: remove higher-tier files between iterations.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill, override, _ = self._build_all_tiers(root)

            for tier, expected_body in expected_tiers:
                with self.subTest(tier=tier):
                    src_text = (
                        'root_pre <<include path="fragments/menu.template.md">> root_post'
                    )
                    ast = parser.parse(src_text, "precedence-skill.template.md")
                    ctx = _context(
                        root,
                        skill_subdir=("core", "precedence-skill"),
                        override_root=override,
                    )
                    flat, dep = resolve(
                        ast, ctx, CompileCache(), root_source=src_text
                    )
                    body = _render(flat)
                    self.assertIn(expected_body, body)
                    menu = [r for r in dep if r.src == "fragments/menu.template.md"]
                    self.assertEqual(len(menu), 1)
                    self.assertEqual(menu[0].resolved_from, tier)
                # Strip the winning tier's file so the next subTest falls down.
                if tier == "user-module-fragment":
                    (
                        override
                        / "fragments"
                        / "core"
                        / "precedence-skill"
                        / "menu.template.md"
                    ).unlink()
                elif tier == "user-override":
                    (override / "fragments" / "menu.template.md").unlink()

    def test_precedence_variant_tier_via_cursor_target(self) -> None:
        """AC 3 variant-tier pass — resolver-unit only (CLI has no --tools)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill, override, _ = self._build_all_tiers(root)
            # Strip all higher tiers so variant can win.
            (
                override
                / "fragments"
                / "core"
                / "precedence-skill"
                / "menu.template.md"
            ).unlink()
            (override / "fragments" / "menu.template.md").unlink()
            src_text = '<<include path="fragments/menu.template.md">>'
            ast = parser.parse(src_text, "precedence-skill.template.md")
            ctx = _context(
                root,
                skill_subdir=("core", "precedence-skill"),
                override_root=override,
                target_ide="cursor",
            )
            flat, dep = resolve(ast, ctx, CompileCache(), root_source=src_text)
            self.assertIn("VARIANT BODY", _render(flat))
            menu = [r for r in dep if r.src == "fragments/menu.template.md"]
            self.assertEqual(len(menu), 1)
            self.assertEqual(menu[0].resolved_from, "variant")
            self.assertEqual(menu[0].resolved_path.name, "menu.cursor.template.md")

    def test_variant_candidate_skips_directory_with_matching_name(self) -> None:
        """R6-P1: a directory whose name happens to match
        `<stem>.<ide>.template.md` must not win the tier-4 variant probe.

        Pre-R6: `_variant_candidate` accepted any entry whose name matched
        the variant pattern, including directories. The directory then
        propagated through `select_variant` and crashed in `read_template`
        with a raw `IsADirectoryError` outside the `CompilerError` taxonomy.
        Post-R6: `is_file` filters the entry; with no real variant present,
        the resolver falls down to the base tier."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            _write(skill / "fragments" / "menu.template.md", "BASE BODY")
            # A directory at the slot the variant probe would otherwise pick.
            (skill / "fragments" / "menu.cursor.template.md").mkdir()

            src_text = '<<include path="fragments/menu.template.md">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root, target_ide="cursor")
            flat, dep = resolve(ast, ctx, CompileCache(), root_source=src_text)
            self.assertIn("BASE BODY", _render(flat))
            menu = [r for r in dep if r.src == "fragments/menu.template.md"]
            self.assertEqual(len(menu), 1)
            self.assertEqual(menu[0].resolved_from, "base")


class TestAlphabeticalTiebreak(unittest.TestCase):
    def test_alphabetical_tiebreak_within_tier(self) -> None:
        """io.list_dir_sorted alphabetical order feeds the variant tier correctly.

        Creates two IDE variants for the same logical fragment — `claudecode`
        sorts before `cursor` alphabetically. Verifies that with
        `target_ide="cursor"` the cursor variant wins (not the alphabetically-
        first claudecode one), confirming that list_dir_sorted provides the
        ordered candidate list and select_variant makes the correct IDE-aware
        pick from it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            _write(skill / "fragments" / "menu.claudecode.template.md", "CLAUDECODE_BODY")
            _write(skill / "fragments" / "menu.cursor.template.md", "CURSOR_BODY")
            _write(skill / "fragments" / "menu.template.md", "UNIVERSAL_BODY")

            src_text = '<<include path="fragments/menu.template.md">>'
            ast_ = parser.parse(src_text, "skill1.template.md")

            # Confirm list_dir_sorted puts claudecode before cursor alphabetically.
            from src.scripts.bmad_compile import io as _io
            sorted_names = [e.name for e in _io.list_dir_sorted(str(skill / "fragments"))]
            self.assertLess(
                sorted_names.index("menu.claudecode.template.md"),
                sorted_names.index("menu.cursor.template.md"),
            )

            # Cursor target: the cursor variant wins despite claudecode being first.
            ctx = _context(root, target_ide="cursor")
            flat, dep = resolve(ast_, ctx, CompileCache(), root_source=src_text)
            menu = [r for r in dep if r.src == "fragments/menu.template.md"]
            self.assertEqual(len(menu), 1)
            self.assertEqual(menu[0].resolved_path.name, "menu.cursor.template.md")
            self.assertEqual(menu[0].resolved_from, "variant")
            self.assertIn("CURSOR_BODY", _render(flat))


class TestModuleRouting(unittest.TestCase):
    def test_core_module_namespace_routes_to_core(self) -> None:
        """Cross-module include from a `bmm` skill → resolved under `core`."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            core_root = root / "core"
            bmm_root = root / "bmm"
            _write(core_root / "intro.template.md", "CORE_INTRO")
            bmm_skill = bmm_root / "skill1"
            bmm_skill.mkdir(parents=True)
            src_text = '<<include path="core/intro.template.md">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = ResolveContext(
                skill_dir=PurePosixPath(bmm_skill.as_posix()),
                module_roots={
                    "core": PurePosixPath(core_root.as_posix()),
                    "bmm": PurePosixPath(bmm_root.as_posix()),
                },
                current_module="bmm",
            )
            flat, dep = resolve(ast, ctx, CompileCache(), root_source=src_text)
            self.assertIn("CORE_INTRO", _render(flat))
            intro = [r for r in dep if r.src == "core/intro.template.md"]
            self.assertEqual(len(intro), 1)
            # Resolved path must be under the core root, not bmm.
            self.assertTrue(
                str(intro[0].resolved_path).startswith(str(PurePosixPath(core_root.as_posix())))
            )

    def test_bare_fragments_path_routes_to_current_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bmm_root = root / "bmm"
            bmm_skill = bmm_root / "skill1"
            _write(bmm_skill / "fragments" / "local.template.md", "LOCAL_BMM")
            src_text = '<<include path="fragments/local.template.md">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = ResolveContext(
                skill_dir=PurePosixPath(bmm_skill.as_posix()),
                module_roots={"bmm": PurePosixPath(bmm_root.as_posix())},
                current_module="bmm",
            )
            flat, _ = resolve(ast, ctx, CompileCache(), root_source=src_text)
            self.assertIn("LOCAL_BMM", _render(flat))

    def test_dotslash_prefix_forces_skill_local_route(self) -> None:
        """AC 7 (R7-P3): `./<modulename>/<...>` must route under the
        skill, not under the module-id whose name happens to collide.

        Pre-R1: the resolver inspected `parts[0]` against `module_roots`
        first, so an authored include `./bmm/foo.template.md` from a `bmm`
        skill would resolve as `<bmm-root>/foo.template.md` — silently
        cross-module — instead of `<skill_dir>/bmm/foo.template.md` as
        the `./` prefix demands. R1 fixed this with a `./`-short-circuit
        in `_parse_include_src`. This test pins the skill-local routing
        so a future refactor that moves the `./` short-circuit after the
        module-id check would fail here."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bmm_root = root / "bmm"
            bmm_skill = bmm_root / "skill1"
            # The collision: a directory under the skill named like the
            # current module, with a sibling actually under the module
            # root. The `./bmm/...` form must read the skill-local copy.
            _write(bmm_skill / "bmm" / "local.template.md", "SKILL_LOCAL_BMM")
            _write(bmm_root / "local.template.md", "MODULE_ROOT_BMM")
            src_text = '<<include path="./bmm/local.template.md">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = ResolveContext(
                skill_dir=PurePosixPath(bmm_skill.as_posix()),
                module_roots={"bmm": PurePosixPath(bmm_root.as_posix())},
                current_module="bmm",
            )
            flat, dep = resolve(ast, ctx, CompileCache(), root_source=src_text)
            self.assertIn("SKILL_LOCAL_BMM", _render(flat))
            entry = [r for r in dep if r.src == "./bmm/local.template.md"]
            self.assertEqual(len(entry), 1)
            # Resolved path must sit under skill_dir, not module_roots["bmm"].
            self.assertTrue(
                str(entry[0].resolved_path).startswith(str(PurePosixPath(bmm_skill.as_posix())))
            )


class TestIncludeProps(unittest.TestCase):
    def test_include_props_attached_to_resolved_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            _write(skill / "fragments" / "intro.template.md", "X")
            src_text = '<<include path="fragments/intro.template.md" speaker="Mary">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            flat, dep = resolve(ast, ctx, CompileCache(), root_source=src_text)
            intro = [r for r in dep if r.src == "fragments/intro.template.md"]
            self.assertEqual(intro[0].local_props, (("speaker", "Mary"),))

    def test_include_props_shadow_enclosing_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            _write(
                skill / "fragments" / "outer.template.md",
                '<<include path="fragments/inner.template.md" speaker="Mary">>',
            )
            _write(skill / "fragments" / "inner.template.md", "X")
            src_text = '<<include path="fragments/outer.template.md" speaker="Bob">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            _, dep = resolve(ast, ctx, CompileCache(), root_source=src_text)
            inner = [r for r in dep if r.src == "fragments/inner.template.md"]
            self.assertEqual(inner[0].local_props, (("speaker", "Mary"),))
            # merged_scope: Mary's inner prop shadows Bob from the parent scope.
            self.assertEqual(inner[0].merged_scope, (("speaker", "Mary"),))

    def test_include_props_do_not_leak_to_siblings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            _write(skill / "fragments" / "a.template.md", "A")
            _write(skill / "fragments" / "b.template.md", "B")
            src_text = (
                '<<include path="fragments/a.template.md" speaker="Mary">>'
                '<<include path="fragments/b.template.md">>'
            )
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            _, dep = resolve(ast, ctx, CompileCache(), root_source=src_text)
            b = [r for r in dep if r.src == "fragments/b.template.md"]
            self.assertEqual(b[0].local_props, ())
            # merged_scope: Mary's scope from sibling `a` must not appear here.
            self.assertEqual(b[0].merged_scope, ())

    def test_include_props_do_not_leak_upward(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            _write(
                skill / "fragments" / "outer.template.md",
                '<<include path="fragments/inner.template.md" speaker="X">>',
            )
            _write(skill / "fragments" / "inner.template.md", "I")
            src_text = '<<include path="fragments/outer.template.md">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            _, dep = resolve(ast, ctx, CompileCache(), root_source=src_text)
            outer = [r for r in dep if r.src == "fragments/outer.template.md"]
            self.assertEqual(outer[0].local_props, ())
            # merged_scope: the inner include's speaker prop must not bleed back
            # up into the outer fragment's scope.
            self.assertEqual(outer[0].merged_scope, ())


class TestFragmentCache(unittest.TestCase):
    def test_fragment_cache_reads_same_fragment_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            _write(skill / "fragments" / "shared.template.md", "S")
            src_text = (
                '<<include path="fragments/shared.template.md">>'
                '<<include path="fragments/shared.template.md">>'
            )
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            cache = CompileCache()
            original = io.read_template
            with mock.patch.object(
                io, "read_template", wraps=original
            ) as wrapped:
                resolve(ast, ctx, cache, root_source=src_text)
                shared_calls = [
                    c
                    for c in wrapped.call_args_list
                    if "shared.template.md" in str(c)
                ]
                self.assertEqual(len(shared_calls), 1)

    def test_fresh_cache_per_resolve_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            _write(skill / "fragments" / "shared.template.md", "S")
            src_text = '<<include path="fragments/shared.template.md">>'
            ctx = _context(root)
            original = io.read_template
            with mock.patch.object(
                io, "read_template", wraps=original
            ) as wrapped:
                ast1 = parser.parse(src_text, "skill1.template.md")
                resolve(ast1, ctx, CompileCache(), root_source=src_text)
                ast2 = parser.parse(src_text, "skill1.template.md")
                resolve(ast2, ctx, CompileCache(), root_source=src_text)
                shared_calls = [
                    c
                    for c in wrapped.call_args_list
                    if "shared.template.md" in str(c)
                ]
                self.assertEqual(len(shared_calls), 2)


class TestTransitiveAndEscape(unittest.TestCase):
    def test_include_inside_included_fragment_resolves_transitively(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            _write(
                skill / "fragments" / "outer.template.md",
                '<<include path="fragments/inner.template.md">>',
            )
            _write(skill / "fragments" / "inner.template.md", "I_CONTENT")
            src_text = '<<include path="fragments/outer.template.md">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            flat, _ = resolve(ast, ctx, CompileCache(), root_source=src_text)
            self.assertIn("I_CONTENT", _render(flat))

    def test_dotdot_segments_are_not_normalized_away(self) -> None:
        """Story 3.5 needs `..` preserved on `resolved_path` for its audit."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / "core" / "skill1"
            # Create a file reachable via `..` from the skill dir.
            _write(root / "core" / "leaked.template.md", "L")
            src_text = '<<include path="../leaked.template.md">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root)
            _, dep = resolve(ast, ctx, CompileCache(), root_source=src_text)
            leaked = [r for r in dep if r.src == "../leaked.template.md"]
            self.assertEqual(len(leaked), 1)
            self.assertIn("..", leaked[0].resolved_path.parts)


class TestVariableResolution(unittest.TestCase):
    """Story 1.3 — VariableScope, VarCompile resolution, VarRuntime passthrough."""

    def test_var_compile_resolved_from_yaml_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            yaml_path = str(root / "config.yaml")
            _write(root / "config.yaml", "user_name: Shado\n")
            var_scope = VariableScope.build(yaml_config_path=yaml_path)
            src = "Hello {{user_name}}!"
            ast = parser.parse(src, "t.md")
            ctx = _context(root, var_scope=var_scope)
            flat, _ = resolve(ast, ctx, CompileCache(), root_source=src)
            self.assertEqual(_render_v13(flat), "Hello Shado!")
            # AC 5: provenance for YAML-sourced values.
            rv = var_scope.resolve("user_name")
            self.assertEqual(rv.source, "bmad-config")
            self.assertEqual(rv.value, "Shado")
            self.assertIsNone(rv.toml_layer)

    def test_var_runtime_passes_through(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = "Ref: {ref_id}."
            ast = parser.parse(src, "t.md")
            ctx = _context(root)
            flat, _ = resolve(ast, ctx, CompileCache(), root_source=src)
            self.assertEqual(_render_v13(flat), "Ref: {ref_id}.")

    def test_unresolved_variable_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            var_scope = VariableScope.build()
            src = "{{unknown_var}}"
            ast = parser.parse(src, "t.md")
            ctx = _context(root, var_scope=var_scope)
            with self.assertRaises(errors.UnresolvedVariableError) as cm:
                resolve(ast, ctx, CompileCache(), root_source=src)
            err = cm.exception
            self.assertEqual(err.code, "UNRESOLVED_VARIABLE")
            self.assertEqual(err.line, 1)
            self.assertEqual(err.col, 1)
            # hint must mention the variable name
            self.assertIn("unknown_var", err.hint or "")

    def test_self_var_resolved_from_toml(self) -> None:
        var_scope = VariableScope.build(
            toml_layers=[("defaults", {"agent": {"name": "PM Agent"}})]
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = "Agent: {{self.agent.name}}"
            ast = parser.parse(src, "t.md")
            ctx = _context(root, var_scope=var_scope)
            flat, _ = resolve(ast, ctx, CompileCache(), root_source=src)
            self.assertEqual(_render_v13(flat), "Agent: PM Agent")
            # AC 8: provenance — source="toml", toml_layer="defaults".
            rv = var_scope.resolve("self.agent.name")
            self.assertEqual(rv.source, "toml")
            self.assertEqual(rv.toml_layer, "defaults")
            self.assertEqual(rv.value, "PM Agent")

    def test_toml_cascade_team_wins_over_defaults(self) -> None:
        var_scope = VariableScope.build(
            toml_layers=[
                ("defaults", {"agent": {"name": "PM Agent"}}),
                ("team", {"agent": {"name": "Product Manager"}}),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = "{{self.agent.name}}"
            ast = parser.parse(src, "t.md")
            ctx = _context(root, var_scope=var_scope)
            flat, _ = resolve(ast, ctx, CompileCache(), root_source=src)
            self.assertEqual(_render_v13(flat), "Product Manager")
            # AC 9: provenance reflects winning layer, not just merged value.
            rv = var_scope.resolve("self.agent.name")
            self.assertEqual(rv.toml_layer, "team")

    def test_toml_cascade_user_wins_over_team(self) -> None:
        var_scope = VariableScope.build(
            toml_layers=[
                ("defaults", {"agent": {"name": "Default"}}),
                ("team", {"agent": {"name": "Team"}}),
                ("user", {"agent": {"name": "User"}}),
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = "{{self.agent.name}}"
            ast = parser.parse(src, "t.md")
            ctx = _context(root, var_scope=var_scope)
            flat, _ = resolve(ast, ctx, CompileCache(), root_source=src)
            self.assertEqual(_render_v13(flat), "User")
            # AC 9: provenance reflects highest-priority layer.
            rv = var_scope.resolve("self.agent.name")
            self.assertEqual(rv.toml_layer, "user")

    def test_toml_cascade_remove_team_reverts_to_defaults(self) -> None:
        """AC 9 second case: removing the team layer causes the defaults
        value to win, with toml_layer="defaults" in provenance."""
        # With team layer present, team wins.
        var_scope_with_team = VariableScope.build(
            toml_layers=[
                ("defaults", {"agent": {"name": "PM Agent"}}),
                ("team", {"agent": {"name": "Product Manager"}}),
            ]
        )
        rv = var_scope_with_team.resolve("self.agent.name")
        self.assertEqual(rv.value, "Product Manager")
        self.assertEqual(rv.toml_layer, "team")

        # Removing the team layer reverts to defaults.
        var_scope_no_team = VariableScope.build(
            toml_layers=[("defaults", {"agent": {"name": "PM Agent"}})]
        )
        rv = var_scope_no_team.resolve("self.agent.name")
        self.assertEqual(rv.value, "PM Agent")
        self.assertEqual(rv.toml_layer, "defaults")

    def test_local_scope_wins_over_yaml_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            yaml_path = str(root / "config.yaml")
            _write(root / "config.yaml", "speaker: Global\n")
            var_scope = VariableScope.build(yaml_config_path=yaml_path)
            # Fragment body uses {{speaker}}, include prop passes "Local".
            skill = root / "core" / "skill1"
            _write(
                skill / "fragments" / "intro.template.md",
                "{{speaker}} says hi.",
            )
            src_text = '<<include path="fragments/intro.template.md" speaker="Local">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root, var_scope=var_scope)
            flat, _ = resolve(ast, ctx, CompileCache(), root_source=src_text)
            self.assertEqual(_render_v13(flat), "Local says hi.")

    def test_local_scope_does_not_affect_self_vars(self) -> None:
        # Weird edge case: even if local_scope contains a "self.*" key
        # (artificially constructed — include props cannot have dots in names),
        # self.* resolution must still use TOML cascade, not local_scope.
        var_scope = VariableScope.build(
            toml_layers=[("defaults", {"agent": {"name": "TOML Name"}})]
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = "{{self.agent.name}}"
            ast = parser.parse(src, "t.md")
            # Manually inject a self.* entry into local_scope.
            ctx = ResolveContext(
                skill_dir=PurePosixPath((root / "core" / "skill1").as_posix()),
                module_roots={"core": PurePosixPath((root / "core").as_posix())},
                current_module="core",
                local_scope=(("self.agent.name", "SCOPE"),),
                var_scope=var_scope,
            )
            flat, _ = resolve(ast, ctx, CompileCache(), root_source=src)
            # self.* must use TOML, not local_scope.
            self.assertEqual(_render_v13(flat), "TOML Name")

    def test_var_compile_resolved_within_fragment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            yaml_path = str(root / "config.yaml")
            _write(root / "config.yaml", "user_name: World\n")
            var_scope = VariableScope.build(yaml_config_path=yaml_path)
            skill = root / "core" / "skill1"
            _write(skill / "fragments" / "frag.template.md", "Hello {{user_name}}!")
            src_text = '<<include path="fragments/frag.template.md">>'
            ast = parser.parse(src_text, "skill1.template.md")
            ctx = _context(root, var_scope=var_scope)
            flat, _ = resolve(ast, ctx, CompileCache(), root_source=src_text)
            self.assertEqual(_render_v13(flat), "Hello World!")

    def test_var_scope_none_raises_on_var_compile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = "{{some_var}}"
            ast = parser.parse(src, "t.md")
            ctx = _context(root)  # var_scope=None
            with self.assertRaises(errors.UnresolvedVariableError):
                resolve(ast, ctx, CompileCache(), root_source=src)

    def test_var_scope_none_ok_when_no_var_compile_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = "Plain text only."
            ast = parser.parse(src, "t.md")
            ctx = _context(root)  # var_scope=None
            flat, _ = resolve(ast, ctx, CompileCache(), root_source=src)
            self.assertEqual(_render_v13(flat), "Plain text only.")

    def test_available_names_in_hint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            yaml_path = str(root / "config.yaml")
            _write(root / "config.yaml", "known_var: value\n")
            var_scope = VariableScope.build(yaml_config_path=yaml_path)
            src = "{{missing_var}}"
            ast = parser.parse(src, "t.md")
            ctx = _context(root, var_scope=var_scope)
            with self.assertRaises(errors.UnresolvedVariableError) as cm:
                resolve(ast, ctx, CompileCache(), root_source=src)
            self.assertIn("known_var", cm.exception.hint or "")

    def test_self_var_toml_integer_converted_to_string(self) -> None:
        var_scope = VariableScope.build(
            toml_layers=[("defaults", {"version": 3})]
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = "v{{self.version}}"
            ast = parser.parse(src, "t.md")
            ctx = _context(root, var_scope=var_scope)
            flat, _ = resolve(ast, ctx, CompileCache(), root_source=src)
            self.assertEqual(_render_v13(flat), "v3")

    def test_parse_flat_yaml_basic_key_value(self) -> None:
        from src.scripts.bmad_compile.resolver import _parse_flat_yaml
        result = _parse_flat_yaml("user_name: Shado\n")
        self.assertEqual(result, {"user_name": "Shado"})

    def test_parse_flat_yaml_skips_comments(self) -> None:
        from src.scripts.bmad_compile.resolver import _parse_flat_yaml
        result = _parse_flat_yaml("# comment\nkey: val\n")
        self.assertNotIn("# comment", result)
        self.assertEqual(result["key"], "val")

    def test_parse_flat_yaml_skips_empty_lines(self) -> None:
        from src.scripts.bmad_compile.resolver import _parse_flat_yaml
        result = _parse_flat_yaml("\n\nkey: val\n\n")
        self.assertEqual(result, {"key": "val"})

    def test_parse_flat_yaml_skips_indented_lines(self) -> None:
        from src.scripts.bmad_compile.resolver import _parse_flat_yaml
        result = _parse_flat_yaml("key: val\n  nested: ignored\n")
        self.assertNotIn("nested", result)
        self.assertEqual(result["key"], "val")

    def test_parse_flat_yaml_strips_quotes(self) -> None:
        from src.scripts.bmad_compile.resolver import _parse_flat_yaml
        result = _parse_flat_yaml('key: "quoted value"\n')
        self.assertEqual(result["key"], "quoted value")

    def test_parse_flat_yaml_lone_quote_not_stripped(self) -> None:
        """Round-1 patch: len>=2 guard prevents single-char quote being stripped to ''."""
        from src.scripts.bmad_compile.resolver import _parse_flat_yaml
        with self.subTest("lone double-quote preserved"):
            self.assertEqual(_parse_flat_yaml('key: "\n'), {"key": '"'})
        with self.subTest("lone single-quote preserved"):
            self.assertEqual(_parse_flat_yaml("key: '\n"), {"key": "'"})
        with self.subTest("two-double-quotes strip to empty string"):
            self.assertEqual(_parse_flat_yaml('key: ""\n'), {"key": ""})
        with self.subTest("mixed outer double strip, inner single remain"):
            self.assertEqual(_parse_flat_yaml("key: \"'val'\"\n"), {"key": "'val'"})

    def test_parse_flat_yaml_strips_leading_utf8_bom(self) -> None:
        """Round-3 patch: a leading UTF-8 BOM (\\ufeff) is stripped before parsing.

        Without this, the first key would be stored as '\\ufeffkey' and every
        '{{key}}' lookup would silently fail. This is common when YAML is
        authored on Windows in Notepad or saved with a BOM.
        """
        from src.scripts.bmad_compile.resolver import _parse_flat_yaml
        with self.subTest("BOM at start is stripped, first key parses cleanly"):
            result = _parse_flat_yaml("\ufeffuser_name: Shado\n")
            self.assertEqual(result, {"user_name": "Shado"})
            self.assertNotIn("\ufeffuser_name", result)
        with self.subTest("BOM-only input parses to empty dict"):
            self.assertEqual(_parse_flat_yaml("\ufeff"), {})
        with self.subTest("no BOM still works (no double-strip)"):
            self.assertEqual(_parse_flat_yaml("k: v\n"), {"k": "v"})

    def test_self_var_toml_bool_serialized_lowercase(self) -> None:
        """Round-1 patch: TOML booleans serialize as lowercase 'true'/'false'."""
        var_scope = VariableScope.build(
            toml_layers=[("defaults", {"flags": {"enabled": True, "debug": False}})]
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for var, expected in (
                ("self.flags.enabled", "true"),
                ("self.flags.debug", "false"),
            ):
                with self.subTest(var=var):
                    src = f"{{{{{var}}}}}"
                    ast = parser.parse(src, "t.md")
                    ctx = _context(root, var_scope=var_scope)
                    flat, _ = resolve(ast, ctx, CompileCache(), root_source=src)
                    self.assertEqual(_render_v13(flat), expected)
        # Integer 1 must NOT serialize as "true" (bool subclass check).
        var_scope_int = VariableScope.build(
            toml_layers=[("defaults", {"count": 1})]
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = "{{self.count}}"
            ast = parser.parse(src, "t.md")
            ctx = _context(root, var_scope=var_scope_int)
            flat, _ = resolve(ast, ctx, CompileCache(), root_source=src)
            self.assertEqual(_render_v13(flat), "1")

    def test_resolved_value_hash_is_well_formed_sha256(self) -> None:
        """Round-3 patch: value_hash is computed via io.hash_text and must be
        a 64-char lowercase-hex SHA-256 of the stringified value. Story 1.5
        will read this field from ResolvedValue directly; a regression that
        nulls or mis-hashes it must surface here, not at lockfile-write time."""
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            yaml_path = str(root / "config.yaml")
            _write(root / "config.yaml", "user_name: Shado\n")
            var_scope = VariableScope.build(
                yaml_config_path=yaml_path,
                toml_layers=[("defaults", {"version": 3, "flags": {"on": True}})],
            )
            for name, expected_value in (
                ("user_name", "Shado"),
                ("self.version", "3"),
                ("self.flags.on", "true"),
            ):
                with self.subTest(name=name):
                    rv = var_scope.resolve(name)
                    self.assertIsNotNone(rv.value_hash)
                    self.assertEqual(len(rv.value_hash), 64)
                    int(rv.value_hash, 16)  # well-formed hex (raises otherwise)
                    self.assertEqual(
                        rv.value_hash,
                        hashlib.sha256(expected_value.encode()).hexdigest(),
                    )

    def test_unresolved_self_var_hint_shows_only_self_keys(self) -> None:
        """Round-1 patch: self.* miss hint shows only self.* keys, not YAML keys."""
        var_scope = VariableScope.build(
            yaml_config_path=None,
            toml_layers=[("defaults", {"agent": {"name": "Bot"}})],
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = "{{self.agent.missing}}"
            ast = parser.parse(src, "t.md")
            ctx = _context(root, var_scope=var_scope)
            with self.assertRaises(errors.UnresolvedVariableError) as cm:
                resolve(ast, ctx, CompileCache(), root_source=src)
            hint = cm.exception.hint or ""
            self.assertIn("self.agent.name", hint)
            self.assertIn("customize.toml", hint)

    def test_unresolved_non_self_var_hint_excludes_self_keys(self) -> None:
        """Round-1 patch: non-self.* miss hint must NOT list self.* names."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            yaml_path = str(Path(tmp) / "config.yaml")
            _write(Path(tmp) / "config.yaml", "known_var: x\n")
            var_scope = VariableScope.build(
                yaml_config_path=yaml_path,
                toml_layers=[("defaults", {"agent": {"name": "Bot"}})],
            )
            src = "{{missing_var}}"
            ast = parser.parse(src, "t.md")
            ctx = _context(root, var_scope=var_scope)
            with self.assertRaises(errors.UnresolvedVariableError) as cm:
                resolve(ast, ctx, CompileCache(), root_source=src)
            hint = cm.exception.hint or ""
            self.assertIn("known_var", hint)
            # self.* names from TOML scope must not appear in the available list.
            self.assertNotIn("self.agent.name", hint)
            # AC 7: hint must direct the author to _bmad/core/config.yaml.
            # R4 patch: prior tests checked only available-name listing.
            self.assertIn("_bmad/core/config.yaml", hint)

    def test_existing_resolver_suite_unchanged(self) -> None:
        """Smoke check: plain text still resolves without errors."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = "plain text"
            ast = parser.parse(src, "t.md")
            ctx = _context(root)
            flat, dep = resolve(ast, ctx, CompileCache(), root_source=src)
            self.assertEqual(_render(flat), "plain text")
            self.assertEqual(len(dep), 1)

    # AC 13 — per-leaf TOML source_path provenance
    def test_flatten_toml_team_array_error_reports_team_path(self) -> None:
        """Array error on a team TOML key reports the team file path, not user."""
        with self.assertRaises(errors.UnknownDirectiveError) as ctx:
            VariableScope.build(
                toml_layers=[("team", {"tags": ["a", "b"]})],
                toml_layer_paths=["/fake/team.toml"],
            )
        self.assertEqual(ctx.exception.file, "/fake/team.toml")

    def test_toml_variable_source_path_populated(self) -> None:
        """AC 13: TOML ResolvedValue gets source_path from winning layer."""
        scope = VariableScope.build(
            toml_layers=[("team", {"agent": {"name": "PM"}})],
            toml_layer_paths=["/fake/team.toml"],
        )
        rv = scope.resolve("self.agent.name")
        self.assertEqual(rv.source_path, "/fake/team.toml")
        self.assertEqual(rv.toml_layer, "team")

    # AC 14 — _make_include_token legacy fallback sorted
    def test_make_include_token_legacy_fallback(self) -> None:
        """Fallback reconstructs token with props sorted alphabetically."""
        from src.scripts.bmad_compile.resolver import _make_include_token
        node = parser.Include(
            src="fragments/a.template.md",
            props=(("z", "1"), ("a", "2")),
            line=1,
            col=1,
            raw_token="",
        )
        result = _make_include_token(node)
        self.assertEqual(
            result,
            '<<include path="fragments/a.template.md" a="2" z="1">>',
        )


if __name__ == "__main__":
    unittest.main()
