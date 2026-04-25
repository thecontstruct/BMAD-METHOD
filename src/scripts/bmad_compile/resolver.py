"""Layer 6 — fragment-resolution engine.

Expands `<<include path="...">>` directives in an AST into an inline node
stream via DFS, enforcing:

- **5-tier precedence cascade** (Story 1.2 AC 3): tier-1 (`user-full-skill`)
  is observed only for the root template via `ResolveContext.root_resolved_from`;
  tiers 2–5 (`user-module-fragment`, `user-override`, `variant`, `base`) are
  probed for each nested include in order.
- **Cycle rejection with full chain** (AC 2): a DFS visited-stack of
  `(resolved_path, authored_src)` detects cycles. On a repeat, the `chain`
  attribute on `CyclicIncludeError` lists the authored paths in order, with
  the closing repeat appended so the cycle reads left-to-right.
- **Alphabetical tiebreak within a tier** (AC 4): inherited from
  `io.list_dir_sorted`, which sorts POSIX-path strings case-sensitively.
- **Include-directive attributes become local props** (AC 5): authored
  attributes other than `path` propagate down the tree via
  `ResolveContext.local_scope`. Child props shadow parent props on key
  collision. Sibling includes do not see each other's props.
- **Per-compile fragment cache** (AC 10): the engine allocates a fresh
  `CompileCache` per `compile_skill()` call; siblings that include the same
  fragment share one read+parse. No cross-compile caching.
- **Module-boundary path semantics** (AC 7): `core/<...>` and
  `<moduleId>/<...>` route via `context.module_roots`; bare paths
  (`fragments/...`, `./...`) route to `context.skill_dir`.

Chain strings in `CyclicIncludeError.chain` are the **authored** include
paths — skill-root-relative by construction when authors follow the
`fragments/...` convention. This matches the architecture example's
`[chain: fragments/a.template.md -> fragments/b.template.md -> fragments/a.template.md]`
shape and lets an author map each edge back to a specific `<<include>>`
line they can edit.

Pathlib boundary: imports `PurePosixPath` via the `io.py` re-export.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Union

from . import errors, io, parser, variants
from .io import PurePosixPath

# Tier names — frozen for v1.
_TIER_USER_FULL_SKILL = "user-full-skill"
_TIER_USER_MODULE_FRAGMENT = "user-module-fragment"
_TIER_USER_OVERRIDE = "user-override"
_TIER_VARIANT = "variant"
_TIER_BASE = "base"

# Tiers probed for nested includes, in cascade order. Tier 1
# (`user-full-skill`) is never in this list — it only fires for the root
# template, and the engine communicates that via `root_resolved_from`.
_NESTED_TIERS: tuple[str, ...] = (
    _TIER_USER_MODULE_FRAGMENT,
    _TIER_USER_OVERRIDE,
    _TIER_VARIANT,
    _TIER_BASE,
)

# Single source of truth lives in `variants.py`; aliased here for readability
# at the call sites that still reference `_TEMPLATE_SUFFIX` locally.
_TEMPLATE_SUFFIX = variants.TEMPLATE_SUFFIX


@dataclass(frozen=True)
class ResolveContext:
    skill_dir: PurePosixPath
    module_roots: dict[str, PurePosixPath]
    current_module: str
    override_root: PurePosixPath | None = None
    target_ide: str | None = None
    # Include-directive props merged into this scope as the DFS descends.
    # Child keys shadow parent keys on collision. Recorded on every
    # descendant `ResolvedFragment.local_props` transitively (Story 1.3
    # will consume this during `{{var}}` resolution).
    local_scope: tuple[tuple[str, str], ...] = ()
    # The tier that produced the ROOT template the engine passed into
    # `resolve()`. Engine sets this to `"user-full-skill"` when it swapped
    # the root for the override at
    # `<override_root>/fragments/<current_module>/<skill>/SKILL.template.md`;
    # otherwise `"base"`.
    root_resolved_from: str = _TIER_BASE


@dataclass
class CompileCache:
    """Per-compile, mutable. Engine allocates fresh per `compile_skill()`."""

    fragments: dict[tuple[PurePosixPath, str], list[parser.AstNode]] = field(
        default_factory=dict
    )
    # Keyed identically to `fragments`; holds raw source text so error
    # rendering (caret block) inside a fragment can point at the right
    # source line without re-reading.
    sources: dict[tuple[PurePosixPath, str], str] = field(default_factory=dict)

    def put(
        self,
        key: tuple[PurePosixPath, str],
        ast_nodes: list[parser.AstNode],
        source: str,
    ) -> None:
        """Store a parsed fragment and its source text together."""
        self.fragments[key] = ast_nodes
        self.sources[key] = source

    def get_source(self, key: tuple[PurePosixPath, str]) -> str:
        return self.sources[key]

    def __contains__(self, key: object) -> bool:
        return key in self.fragments


@dataclass(frozen=True)
class ResolvedFragment:
    src: str
    resolved_path: PurePosixPath
    resolved_from: str
    local_props: tuple[tuple[str, str], ...]
    # The scope visible to this fragment's body — local_props merged on top of
    # the parent's scope (child keys shadow parent keys). Recorded for
    # observability; Story 1.3 variable resolution will consume this.
    merged_scope: tuple[tuple[str, str], ...]
    nodes: list[parser.AstNode]


@dataclass
class _StackFrame:
    resolved_path: PurePosixPath
    authored_src: str


def _merge_scope(
    parent_scope: tuple[tuple[str, str], ...],
    include_props: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    """Merge with child (include) wins on key collision."""
    merged = dict(parent_scope)
    for name, value in include_props:
        merged[name] = value
    return tuple(sorted(merged.items()))


def _parse_include_src(
    src: str,
    current_module: str,
    module_roots: dict[str, PurePosixPath],
) -> tuple[str, PurePosixPath, str, bool]:
    """Split authored include src into routing components.

    Returns ``(effective_module, relative_subpath, leaf, had_module_prefix)``:
    - `effective_module` — the module whose root anchors the base tier.
    - `relative_subpath` — path beneath the module root (or the skill
      directory for bare paths), **with `..` segments preserved** so a
      future containment check can inspect escape intent.
    - `leaf` — the last component of `relative_subpath`, used for
      override namespacing at tiers 2 and 3.
    - `had_module_prefix` — True if the authored src started with a
      known module id (controls whether the base tier anchors at
      `module_roots[effective_module]` or at `skill_dir`).
    """
    # `./` prefix is the author's explicit force-skill-local escape hatch.
    # PurePosixPath normalizes `./` away, so we must check the raw string
    # before the conversion to catch `./core/foo.template.md` and route it
    # to the current skill's tree rather than the `core` module root.
    if src.startswith("./"):
        pp = PurePosixPath(src)
        leaf = pp.name
        return current_module, pp, leaf, False

    pp = PurePosixPath(src)
    parts = pp.parts
    if parts and parts[0] in module_roots:
        effective_module = parts[0]
        if len(parts) > 1:
            relative_subpath = PurePosixPath(*parts[1:])
        else:
            relative_subpath = PurePosixPath(".")
        had_module_prefix = True
    else:
        effective_module = current_module
        relative_subpath = pp
        had_module_prefix = False
    leaf = relative_subpath.name
    return effective_module, relative_subpath, leaf, had_module_prefix


def _base_candidate(
    context: ResolveContext,
    effective_module: str,
    relative_subpath: PurePosixPath,
    had_module_prefix: bool,
) -> PurePosixPath | None:
    """The tier-5 base path. Also the anchor for tier-4 variant search.

    Returns `None` only when `effective_module` has no entry in
    `module_roots` (should not happen for bare paths because
    `current_module` must be present, but guarded nonetheless).
    """
    if had_module_prefix:
        root = context.module_roots.get(effective_module)
        if root is None:
            return None
        return root / relative_subpath
    return context.skill_dir / relative_subpath


def _variant_candidate(
    context: ResolveContext,
    base_candidate: PurePosixPath | None,
    leaf: str,
) -> PurePosixPath | None:
    """Tier-4 probe: IDE-suffixed siblings of the base candidate's name."""
    if base_candidate is None:
        return None
    if not leaf.endswith(_TEMPLATE_SUFFIX):
        return None
    parent = base_candidate.parent
    if not io.is_dir(str(parent)):
        return None
    stem = leaf[: -len(_TEMPLATE_SUFFIX)]
    entries = io.list_dir_sorted(str(parent))
    matches: list[PurePosixPath] = []
    for entry in entries:
        for ide in variants.KNOWN_IDES:
            if entry.name == f"{stem}.{ide}{_TEMPLATE_SUFFIX}":
                # Tier-4 `is_file` discipline (mirrors tiers 2/3/5 from R4
                # and engine tier 1 from R5): a directory whose name happens
                # to match `<stem>.<ide>.template.md` would otherwise win
                # the variant probe and crash later in `read_template` with
                # a raw `IsADirectoryError` outside the `CompilerError`
                # taxonomy.
                if io.is_file(str(entry)):
                    matches.append(entry)
                break
    return variants.select_variant(matches, context.target_ide)


def _lookup_tier(
    tier: str,
    context: ResolveContext,
    effective_module: str,
    relative_subpath: PurePosixPath,
    leaf: str,
    had_module_prefix: bool,
) -> PurePosixPath | None:
    skill_basename = context.skill_dir.name
    if tier == _TIER_USER_MODULE_FRAGMENT:
        if context.override_root is None:
            return None
        path = (
            context.override_root
            / "fragments"
            / effective_module
            / skill_basename
            / leaf
        )
        return path if io.is_file(str(path)) else None
    if tier == _TIER_USER_OVERRIDE:
        if context.override_root is None:
            return None
        path = context.override_root / "fragments" / leaf
        return path if io.is_file(str(path)) else None
    if tier == _TIER_BASE:
        base = _base_candidate(
            context, effective_module, relative_subpath, had_module_prefix
        )
        if base is None:
            return None
        return base if io.is_file(str(base)) else None
    if tier == _TIER_VARIANT:
        base = _base_candidate(
            context, effective_module, relative_subpath, had_module_prefix
        )
        return _variant_candidate(context, base, leaf)
    # `user-full-skill` never appears in the nested-tier loop.
    return None


def _relative_file(
    resolved_path: PurePosixPath, context: ResolveContext
) -> str:
    """Relative POSIX path for use in error messages.

    Preference: skill-root-relative; fall back to module-root-relative;
    final fallback: the full resolved path as a string.
    """
    try:
        return str(resolved_path.relative_to(context.skill_dir))
    except ValueError:
        pass
    for root in context.module_roots.values():
        try:
            return str(resolved_path.relative_to(root))
        except ValueError:
            continue
    if context.override_root is not None:
        try:
            return str(resolved_path.relative_to(context.override_root))
        except ValueError:
            pass
    return str(resolved_path)


def _missing_fragment_hint(
    src: str,
    context: ResolveContext,
    effective_module: str,
    relative_subpath: PurePosixPath,
    leaf: str,
    had_module_prefix: bool,
    include_line: int,
) -> str:
    """Per architecture hint quality bar: name a concrete `.template.md`
    path the author can create, plus the change-the-include alternative."""
    skill_basename = context.skill_dir.name
    if context.override_root is not None:
        create_path = (
            context.override_root
            / "fragments"
            / effective_module
            / skill_basename
            / leaf
        )
    else:
        base = _base_candidate(
            context, effective_module, relative_subpath, had_module_prefix
        )
        create_path = base if base is not None else context.skill_dir / leaf
    return (
        f"create {create_path}, or change <<include path=\"...\">> on line "
        f"{include_line} to an existing fragment (see "
        f"{effective_module}/fragments/ for options)"
    )


_MAX_INCLUDE_DEPTH = 200


def _make_include_token(node: parser.Include) -> str:
    """Reconstruct the full directive text including authored props."""
    parts = [f'<<include path="{node.src}"']
    for name, value in node.props:
        parts.append(f' {name}="{value}"')
    parts.append(">>")
    return "".join(parts)


def _walk_nodes(
    nodes: list[parser.AstNode],
    context: ResolveContext,
    cache: CompileCache,
    visited_stack: list[_StackFrame],
    dep_tree: list,
    enclosing_file: str,
    enclosing_source: str | None,
    depth: int = 0,
) -> list[parser.AstNode]:
    """DFS pre-order node walk. Includes get expanded in place."""
    if depth >= _MAX_INCLUDE_DEPTH:
        raise errors.CyclicIncludeError(
            f"include depth reached the {_MAX_INCLUDE_DEPTH}-level cap — "
            "check for a very deep or unbounded include chain",
            file=enclosing_file,
            chain=[f.authored_src for f in visited_stack],
            hint=(
                f"reduce nesting depth below {_MAX_INCLUDE_DEPTH} levels; "
                "if this is a legitimate deep chain, contact the maintainer"
            ),
        )

    flat: list[parser.AstNode] = []
    for node in nodes:
        if not isinstance(node, parser.Include):
            flat.append(node)
            continue

        effective_module, relative_subpath, leaf, had_prefix = _parse_include_src(
            node.src, context.current_module, context.module_roots
        )

        resolved_path: PurePosixPath | None = None
        tier_won: str | None = None
        for tier in _NESTED_TIERS:
            candidate = _lookup_tier(
                tier, context, effective_module, relative_subpath, leaf, had_prefix
            )
            if candidate is not None:
                resolved_path = candidate
                tier_won = tier
                break

        if resolved_path is None or tier_won is None:
            token = _make_include_token(node)
            raise errors.MissingFragmentError(
                "fragment not found",
                file=enclosing_file,
                line=node.line,
                col=node.col,
                token=token,
                hint=_missing_fragment_hint(
                    node.src,
                    context,
                    effective_module,
                    relative_subpath,
                    leaf,
                    had_prefix,
                    node.line,
                ),
                source=enclosing_source,
            )

        # Cycle detection via resolved_path identity on the DFS stack.
        for frame in visited_stack:
            if frame.resolved_path == resolved_path:
                chain = [f.authored_src for f in visited_stack] + [node.src]
                token = _make_include_token(node)
                raise errors.CyclicIncludeError(
                    "cyclic include detected",
                    file=enclosing_file,
                    line=node.line,
                    col=node.col,
                    token=token,
                    chain=chain,
                    hint=(
                        "break the cycle by removing one <<include>> directive "
                        "in the chain above; the most recently added include "
                        "is usually the safest edge to cut"
                    ),
                    source=enclosing_source,
                )

        cache_key = (resolved_path, tier_won)
        if cache_key not in cache:
            fragment_src = io.read_template(str(resolved_path))
            rel_path = _relative_file(resolved_path, context)
            cache.put(cache_key, parser.parse(fragment_src, rel_path), fragment_src)
        fragment_ast = cache.fragments[cache_key]
        fragment_src = cache.get_source(cache_key)

        child_scope = _merge_scope(context.local_scope, node.props)
        child_context = replace(context, local_scope=child_scope)

        visited_stack.append(
            _StackFrame(resolved_path=resolved_path, authored_src=node.src)
        )
        placeholder_idx = len(dep_tree)
        dep_tree.append(None)
        child_flat = _walk_nodes(
            fragment_ast,
            child_context,
            cache,
            visited_stack,
            dep_tree,
            enclosing_file=_relative_file(resolved_path, context),
            enclosing_source=fragment_src,
            depth=depth + 1,
        )
        visited_stack.pop()

        resolved = ResolvedFragment(
            src=node.src,
            resolved_path=resolved_path,
            resolved_from=tier_won,
            local_props=node.props,
            merged_scope=child_scope,
            nodes=child_flat,
        )
        dep_tree[placeholder_idx] = resolved
        flat.extend(child_flat)
    return flat


def resolve(
    ast: list[parser.AstNode],
    context: ResolveContext,
    cache: CompileCache,
    *,
    root_src: str = "",
    root_path: PurePosixPath | None = None,
    root_source: str | None = None,
) -> tuple[list[parser.AstNode], list[ResolvedFragment]]:
    """Expand an AST's includes into an inline node stream.

    Returns `(flat_nodes, dep_tree)`:
    - `flat_nodes` — the input AST with every `Include` replaced in place by
      its recursively-resolved child nodes. Story 1.2 renders this as text
      (still only `Text` nodes after inlining); Story 1.3 will add
      `{{var}}` resolution atop the same walk.
    - `dep_tree` — a flat `list[ResolvedFragment]` in DFS pre-order. The
      first entry is always the root, carrying
      `resolved_from = context.root_resolved_from`. Siblings that include
      the same fragment show up as separate entries (the cache suppresses
      re-read/re-parse, not dep-tree duplication).

    `root_src` / `root_path` / `root_source` exist so the root's
    `ResolvedFragment` and any error raised at the root level can carry
    meaningful file + source context. Engine populates them from the CLI
    arguments; resolver tests can omit them (then `resolved_path` on the
    root entry defaults to the skill directory).
    """
    dep_tree: list = []
    visited_stack: list[_StackFrame] = []

    root_rel_file = (
        _relative_file(root_path, context) if root_path is not None else root_src
    )
    placeholder_idx = len(dep_tree)
    dep_tree.append(None)
    flat = _walk_nodes(
        ast,
        context,
        cache,
        visited_stack,
        dep_tree,
        enclosing_file=root_rel_file or context.skill_dir.name,
        enclosing_source=root_source,
    )

    root_entry = ResolvedFragment(
        src=root_src,
        resolved_path=(
            root_path if root_path is not None else context.skill_dir
        ),
        resolved_from=context.root_resolved_from,
        local_props=context.local_scope,
        merged_scope=context.local_scope,
        nodes=flat,
    )
    dep_tree[placeholder_idx] = root_entry
    return flat, dep_tree
