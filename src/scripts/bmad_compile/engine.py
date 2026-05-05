"""Layer 9 — compile engine.

Reads one `*.template.md` from a skill directory, parses it, resolves its
`<<include>>` tree, renders the AST to a single string, and stages the
write in memory before committing through `io.write_text` — so any
`CompilerError` raised mid-compile leaves the install directory untouched
(Story 1.1 AC 10).

Story 1.2 additions:
- Builds a `resolver.ResolveContext` with hardcoded-`core` module routing
  and an override-root probe at `<skill>/../../_bmad/custom/`.
- If `<override_root>/fragments/<current_module>/<skill>/SKILL.template.md`
  exists, engine swaps the root template for that override and marks
  `root_resolved_from = "user-full-skill"` (tier 1).
- Allocates a fresh `resolver.CompileCache` per `compile_skill()` call.

Story 1.3 will wire in variable interpolation, Story 1.4 multi-IDE
(`--tools`), Story 1.5 lockfile writes. Story 3.0 added
directory-convention module discovery for install-phase mode
(`lockfile_root` not None); per-skill mode (`lockfile_root=None`)
preserves Story 1.2 hardcoded-`core` routing for backward compat.
This module routes every filesystem/hash/time concern through `io`.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

from . import errors, io, lockfile, parser, resolver, toml_merge, variants

# Story 3.0: reserved dir names at install-root depth-1; mirrors
# compile.py's _SKIP_AT_DEPTH_1. Same set, same rationale — these dirs are
# not modules and must not appear in `module_roots`. The two definitions are
# intentionally duplicated because compile.py sits outside the bmad_compile
# package boundary; unifying is a separate single-source-of-truth concern.
_MODULE_DIR_SKIP: frozenset[str] = frozenset(
    {"_config", "custom", "scripts", "memory", "_memory"}
)


def _render(nodes: Iterable[object]) -> str:
    """Render the post-resolve AST to text.

    After resolver.resolve() inlines every `Include` and resolves every
    `VarCompile`, the flat list contains only `Text` and `VarRuntime` nodes.
    `VarRuntime` nodes are emitted verbatim as `{name}` (runtime passthrough).
    """
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, parser.Text):
            parts.append(node.content)
        elif isinstance(node, parser.VarRuntime):
            parts.append("{" + node.name + "}")
        else:
            raise RuntimeError(
                f"engine cannot render node type {type(node).__name__}; "
                "VarCompile should have been resolved by resolver.resolve()"
            )
    return "".join(parts)


def _discover_module_roots(
    install_root: io.PurePosixPath,
    current_module: str,
    current_module_dir: io.PurePosixPath,
) -> dict[str, io.PurePosixPath]:
    """Enumerate module dirs under install_root for install-phase module routing.

    A directory qualifies when it does not start with '_' and is not in
    _MODULE_DIR_SKIP. Mirrors compile.py depth-1 skip logic so the same
    dirs are invisible at both the walker (compile.py) and the resolver
    (engine.py) layers. current_module/current_module_dir are inserted
    unconditionally as a fallback so the calling skill always has a valid
    module root even in sparse test fixtures.
    """
    roots: dict[str, io.PurePosixPath] = {}
    for entry in io.list_dir_sorted(str(install_root)):
        if (
            io.is_dir(str(entry))
            and not entry.name.startswith("_")
            and entry.name not in _MODULE_DIR_SKIP
        ):
            roots[entry.name] = entry
    if current_module not in roots:
        roots[current_module] = current_module_dir
    return roots


def _compile_core(
    skill_dir: io.PathLike,
    install_dir: io.PathLike,
    target_ide: str | None,
    *,
    lockfile_root: io.PathLike | None,
    override_root: io.PathLike | None,
    install_flags: dict[str, str] | None,
    explain_mode: bool = False,
) -> tuple[
    list[Any],                          # flat_nodes (post-resolve, possibly with explain sentinels)
    list[resolver.ResolvedFragment],    # dep_tree
    resolver.VariableScope,              # var_scope
    resolver.CompileCache,               # cache
    io.PurePosixPath,                    # scenario_root
    str,                                 # basename
    str,                                 # source_text (raw root template)
    str,                                 # lockfile_path
    io.PurePosixPath,                    # output_path (computed pre-render for explain)
    str | None,                          # target_ide (passed through unchanged from caller)
    list[tuple[str, dict[str, Any]]],   # _toml_layers (NEW [10]) — [(layer_name, raw_dict)]
    list[str],                           # _toml_layer_paths (NEW [11]) — parallel paths list
]:
    """Story 4.2: shared compile core for compile_skill + explain_skill.

    Performs every step of the compile pipeline EXCEPT rendering and disk
    writes. Returns the resolved AST plus all metadata callers need to
    finish the job. `compile_skill` calls `_render` on the result and writes
    SKILL.md + lockfile. `explain_skill` returns the flat node stream
    directly so `_render_explain` can synthesize the XML provenance view.

    `explain_mode=True` is forwarded into `ResolveContext` so `_walk_nodes`
    injects `FragmentBoundary` sentinels and emits `ExplainVar` nodes for
    `VarCompile` resolutions; otherwise behavior is byte-identical to the
    pre-Story-4.2 `compile_skill` body.
    """
    skill_posix = io.to_posix(skill_dir)
    if not io.is_dir(str(skill_posix)):
        raise NotADirectoryError(
            f"skill path '{skill_dir}' is not a directory — "
            "pass a skill directory (containing '*.template.md'), not a file"
        )
    basename = skill_posix.name

    # Story 3.0: Real module discovery. Per-skill mode (lockfile_root=None)
    # preserves Story 1.2 hardcoded-core behavior for backward compat.
    if lockfile_root is not None:
        current_module = skill_posix.parent.name
        module_roots = _discover_module_roots(
            io.to_posix(lockfile_root), current_module, skill_posix.parent
        )
    else:
        current_module = "core"
        module_roots = {"core": skill_posix.parent}

    # Override root probes `<skill>.parent.parent / _bmad / custom`. For a
    # fixture `.../<scenario>/core/<scenario>-skill/` this lands at
    # `.../<scenario>/_bmad/custom`. If the directory is absent, all
    # override-tier lookups short-circuit to None.
    scenario_root = skill_posix.parent.parent

    # AC 6: lockfile_root param overrides the default derivation.
    if lockfile_root is not None:
        _lockfile_path = str(io.to_posix(lockfile_root) / "_config" / "bmad.lock")
    else:
        _lockfile_path = str(scenario_root / "_bmad" / "_config" / "bmad.lock")
    _lf_ver = lockfile.read_lockfile_version(_lockfile_path)
    if _lf_ver is not None and _lf_ver > 1:
        raise errors.LockfileVersionMismatchError(
            f"bmad.lock declares version {_lf_ver} but this compiler reads up to version 1",
            file=_lockfile_path,
            hint=(
                f"bmad.lock declares version {_lf_ver}; this compiler supports version 1 only. "
                "Run 'bmad upgrade' to regenerate, or delete bmad.lock to start fresh. "
                "Your overrides in _bmad/custom/ will be preserved."
            ),
        )
    # AC 6: override_root param overrides the default derivation (no implicit /custom suffix).
    if override_root is not None:
        # Story 3.5: Caller-supplied override_root is untrusted; reject before any filesystem probe.
        candidate_override_root = io.ensure_within_root(override_root, scenario_root)
    else:
        candidate_override_root = scenario_root / "_bmad" / "custom"
    # `is_dir` (not `path_exists`) — completes the file-type discipline
    # established at every other probe site in R4/R5/R6. A regular file
    # at `<scenario>/_bmad/custom` would otherwise pass `path_exists`,
    # the engine would set `override_root` to that file, every subsequent
    # `<override_root>/fragments/...` join would silently miss
    # (`is_file()` False on a path under a non-directory), and the
    # missing-fragment hint would advise creating `<file>/fragments/...`
    # — a non-creatable path. Symmetric with the resolver-level fix
    # to `_variant_candidate` (R6-P1).
    if io.is_dir(str(candidate_override_root)):
        override_root = candidate_override_root
    else:
        override_root = None

    # Tier 1 (user-full-skill) probe: if a replacement SKILL.template.md
    # exists under the override root, swap the root template and set
    # `root_resolved_from = "user-full-skill"`. Otherwise, read the
    # conventional root template from the skill dir.
    root_resolved_from = "base"
    override_root_template = None
    if override_root is not None:
        _ort = override_root / "fragments" / current_module / basename / "SKILL.template.md"
        # Story 3.5: Reject symlinks in override path pointing outside scenario_root.
        override_root_template = io.ensure_within_root(_ort, scenario_root)
        # `is_file` (not `path_exists`) — a directory at this slot would
        # otherwise pass the probe and crash later in `read_template` with
        # a raw `IsADirectoryError` / `PermissionError` outside the
        # `CompilerError` taxonomy. Mirrors the resolver-level fix in R4.
        if io.is_file(str(override_root_template)):
            root_resolved_from = "user-full-skill"
        else:
            override_root_template = None

    # Story 4.2 fold-in 5: when the root template was swapped to a
    # `user-full-skill` override, locate the tier-5 base template (the
    # non-overridden file in the skill dir) so `dep_tree[0].base_path`
    # carries it through to the explain renderer for `<Include base-hash>`.
    # `None` for `base` roots — there is no upstream base to record.
    root_base_path: io.PurePosixPath | None = None
    if root_resolved_from == "user-full-skill":
        _base_entries = io.list_files_sorted(skill_dir)
        _base_templates = [e for e in _base_entries if e.name.endswith(".template.md")]
        _base_template = variants.select_variant(_base_templates, target_ide)
        if _base_template is not None and io.is_file(str(_base_template)):
            root_base_path = _base_template

    if override_root_template is not None:
        template_path = override_root_template
        assert override_root is not None  # narrowed by the override_root_template != None branch above
        # When the root is swapped to an override-rooted file, error
        # messages must point authors to the override path — otherwise a
        # parse error in the override SKILL.template.md gets reported with
        # a base-shaped relative path, sending the author to edit the
        # wrong file. Same `override_root`-relative form used by
        # `resolver._relative_file` for nested errors under the override.
        relative_path = str(template_path.relative_to(override_root))
    else:
        all_entries = io.list_files_sorted(skill_dir)
        all_templates = [e for e in all_entries if e.name.endswith(".template.md")]
        template_entry = variants.select_variant(all_templates, target_ide)
        if template_entry is None:
            _detected_ides_set: set[str] = set()
            for e in all_entries:
                m = variants._IDE_SUFFIX_RE.match(e.name)
                if m is not None and m.group("base") == basename:
                    _detected_ides_set.add(m.group("ide"))
            _detected_ides = sorted(_detected_ides_set)
            if _detected_ides and target_ide is None:
                hint = (
                    f"no universal '*.template.md' found in '{skill_dir}'. "
                    f"Found IDE-specific variants for: {', '.join(_detected_ides)}. "
                    f"Compile with --tools <ide> to select one, or create "
                    f"'{basename}.template.md' as a universal fallback."
                )
            elif _detected_ides and target_ide is not None and target_ide in _detected_ides:
                # A file matching `{basename}.{target_ide}.template.md` exists,
                # but select_variant still returned None — which can only happen
                # when target_ide is not in KNOWN_IDES (the install-time
                # allowlist). Without this branch the author falls through to
                # the generic "create universal" message and is never told that
                # their requested IDE is unrecognized.
                hint = (
                    f"'{target_ide}' is not a recognized IDE for this install "
                    f"(supported: {', '.join(variants.KNOWN_IDES)}). "
                    f"A file matching '{basename}.{target_ide}.template.md' exists "
                    f"but cannot be selected with --tools {target_ide}. "
                    f"Use --tools {' or --tools '.join(variants.KNOWN_IDES)}, or "
                    f"rename to '{basename}.template.md' for a universal fallback."
                )
            elif _detected_ides and target_ide is not None and target_ide not in _detected_ides:
                tried = [str(skill_posix / f"{basename}.{ide}.template.md") for ide in variants.KNOWN_IDES]
                tried.append(str(skill_posix / f"{basename}.template.md"))
                hint = (
                    f"no '*.template.md' found for --tools {target_ide} in '{skill_dir}'. "
                    f"Tried: {tried!r}. "
                    f"Variants exist for: {', '.join(_detected_ides)} — did you mean "
                    f"--tools {_detected_ides[0]}?"
                )
            else:
                tried = [str(skill_posix / f"{basename}.{ide}.template.md") for ide in variants.KNOWN_IDES]
                tried.append(str(skill_posix / f"{basename}.template.md"))
                hint = (
                    f"no '*.template.md' found in '{skill_dir}'. "
                    f"Tried: {tried!r}. "
                    f"Create '{basename}.template.md' in the skill directory."
                )
            raise errors.MissingFragmentError(
                "no '*.template.md' found in skill directory",
                file=str(skill_posix),
                line=None, col=None,
                hint=hint,
            )
        template_path = template_entry
        relative_path = f"{basename}/{template_entry.name}"

    source = io.read_template(str(template_path))
    parsed_nodes = parser.parse(source, relative_path)

    # --- Variable scope (Decision 3) ---
    # Probe for bmad-config YAML (non-self.* cascade, bmad-config tier).
    # Convention: <scenario_root>/_bmad/core/config.yaml
    yaml_config_path: str | None = None
    # AC 6: when lockfile_root is provided (install-phase), yaml config lives at
    # <lockfile_root>/core/config.yaml; the default derives via scenario_root/_bmad/core/.
    if lockfile_root is not None:
        _yaml_candidate = io.to_posix(lockfile_root) / "core" / "config.yaml"
    else:
        _yaml_candidate = scenario_root / "_bmad" / "core" / "config.yaml"
    if io.is_file(str(_yaml_candidate)):
        yaml_config_path = str(_yaml_candidate)

    # Story 3.3: module-config probe — `_bmad/<current_module>/config.yaml`.
    # Install-phase mode only. Per-skill mode (lockfile_root is None) skips
    # this probe entirely: `current_module` is hardcoded to "core" there, and
    # `core/config.yaml` lacks the marker — an unguarded probe would re-attribute
    # all core keys as "module-config" and overwrite the bmad-config entries
    # (R2-empirical F3 guard, Story 3.3 OQ 5 resolution).
    module_yaml_paths: list[str] = []
    if lockfile_root is not None:
        _module_yaml = io.to_posix(lockfile_root) / current_module / "config.yaml"
        if io.is_file(str(_module_yaml)):
            module_yaml_paths.append(str(_module_yaml))

    # Story 3.3: user-config probe — `_bmad/custom/config.yaml`.
    # Flat path only for v1 (module-scoped / workflow-scoped paths deferred — OQ 1).
    user_yaml_path: str | None = None
    if lockfile_root is not None:
        _user_yaml_candidate = io.to_posix(lockfile_root) / "custom" / "config.yaml"
    else:
        _user_yaml_candidate = scenario_root / "_bmad" / "custom" / "config.yaml"
    if io.is_file(str(_user_yaml_candidate)):
        user_yaml_path = str(_user_yaml_candidate)

    # Build self.* TOML layer stack (lowest → highest: defaults → team → user).
    _toml_layers: list[tuple[str, dict[str, Any]]] = []
    _toml_layer_paths: list[str] = []
    _customize_toml = skill_posix / "customize.toml"
    if io.is_file(str(_customize_toml)):
        _toml_layers.append(("defaults", toml_merge.load_toml_file(str(_customize_toml))))
        _toml_layer_paths.append(str(_customize_toml))
    if override_root is not None:
        _team_toml = override_root / f"{basename}.toml"
        if io.is_file(str(_team_toml)):
            _toml_layers.append(("team", toml_merge.load_toml_file(str(_team_toml))))
            _toml_layer_paths.append(str(_team_toml))
        _user_toml = override_root / f"{basename}.user.toml"
        if io.is_file(str(_user_toml)):
            _toml_layers.append(("user", toml_merge.load_toml_file(str(_user_toml))))
            _toml_layer_paths.append(str(_user_toml))

    var_scope = resolver.VariableScope.build(
        yaml_config_path=yaml_config_path,
        module_yaml_paths=module_yaml_paths or None,
        user_yaml_path=user_yaml_path,
        install_flags=install_flags,
        toml_layers=_toml_layers or None,
        toml_layer_paths=_toml_layer_paths or None,
        # Story 4.4: scenario_root enables `file:`-prefix array glob expansion
        # inside VariableScope.build(). When None (resolver-level unit tests),
        # `_glob_expansions` records get created with `matches=()` and
        # `match_set_hash=None` — no filesystem access.
        scenario_root=str(scenario_root),
    )

    context = resolver.ResolveContext(
        skill_dir=skill_posix,
        module_roots=module_roots,
        current_module=current_module,
        scenario_root=scenario_root,
        override_root=override_root,
        target_ide=target_ide,
        root_resolved_from=root_resolved_from,
        var_scope=var_scope,
        explain_mode=explain_mode,
        root_base_path=root_base_path,
    )
    cache = resolver.CompileCache()
    flat_nodes, dep_tree = resolver.resolve(
        parsed_nodes,
        context,
        cache,
        root_src=relative_path,
        root_path=template_path,
        root_source=source,
    )

    # Story 4.2: seed the cache with the root template's parsed AST + raw
    # source under the same key shape `_render_explain` looks up. The walker
    # does not seed it (the cache is for nested includes); without this seed,
    # `cache.get_source((root.resolved_path, root.resolved_from))` would
    # raise KeyError. Gated on explain_mode to avoid mutating cache state on
    # the normal compile path (where this entry is never read).
    if explain_mode:
        root_cache_key = (dep_tree[0].resolved_path, dep_tree[0].resolved_from)
        if root_cache_key not in cache:
            cache.put(root_cache_key, parsed_nodes, source)

    install_posix = io.to_posix(install_dir)
    # AC 6: when lockfile_root is provided (install-phase mode), output gains
    # the <module>/ segment so SKILL.md lands at <install_dir>/<module>/<skill>/SKILL.md.
    # When lockfile_root is None (per-skill CLI mode), preserve today's layout.
    if lockfile_root is not None:
        module = skill_posix.parent.name
        output_path = install_posix / module / basename / "SKILL.md"
    else:
        output_path = install_posix / basename / "SKILL.md"

    return (
        flat_nodes,
        dep_tree,
        var_scope,
        cache,
        scenario_root,
        basename,
        source,
        _lockfile_path,
        output_path,
        target_ide,
        _toml_layers,       # NEW [10] — list[tuple[str, dict[str, Any]]]
        _toml_layer_paths,  # NEW [11] — list[str]
    )


def compile_skill(
    skill_dir: io.PathLike,
    install_dir: io.PathLike,
    target_ide: str | None = None,
    *,
    lockfile_root: io.PathLike | None = None,
    override_root: io.PathLike | None = None,
    install_flags: dict[str, str] | None = None,
) -> None:
    """Compile a single skill directory to `<install_dir>/<skill_basename>/SKILL.md`.

    Staging discipline: parse + resolve + render fully in memory. Only on
    full success do we call `io.write_text`. Any `CompilerError` raised
    mid-compile leaves the filesystem untouched (Story 1.1 AC 10).

    AC 6 (Story 2.1): optional keyword-only `lockfile_root` and `override_root`
    params allow the install-phase caller to override the derived paths.
    When either is None, today's `skill_dir.parent.parent / "_bmad"` derivation
    is used, preserving full backward compatibility.

    Story 3.3: `install_flags` carries CLI `--set KEY=VALUE` overrides. They
    win over all YAML tiers (bmad-config / module-config / user-config).
    None or empty = no install-flag tier.

    Story 4.2: body extracted into `_compile_core`; this wrapper renders the
    output, writes SKILL.md, and writes the lockfile entry. `_render` is the
    only renderer for normal compiles; explain-mode never enters this path.
    """
    (
        flat_nodes,
        dep_tree,
        var_scope,
        cache,
        scenario_root,
        basename,
        source_text,
        lockfile_path,
        output_path,
        tid,
        _,  # toml_layers — unused in compile mode
        _,  # toml_layer_paths — unused in compile mode
    ) = _compile_core(
        skill_dir, install_dir, target_ide,
        lockfile_root=lockfile_root,
        override_root=override_root,
        install_flags=install_flags,
        explain_mode=False,
    )
    rendered = _render(flat_nodes)
    io.write_text(str(output_path), rendered)
    lockfile.write_skill_entry(
        lockfile_path,
        scenario_root,
        basename,
        source_text=source_text,
        compiled_text=rendered,
        dep_tree=dep_tree,
        var_scope=var_scope,
        target_ide=tid,
        cache=cache,
    )


def explain_skill(
    skill_dir: io.PathLike,
    install_dir: io.PathLike,
    target_ide: str | None = None,
    *,
    lockfile_root: io.PathLike | None = None,
    override_root: io.PathLike | None = None,
    install_flags: dict[str, str] | None = None,
) -> tuple[
    list[Any],
    list[resolver.ResolvedFragment],
    resolver.VariableScope,
    resolver.CompileCache,
    io.PurePosixPath,
    list[tuple[str, str, dict[str, Any]]],  # toml_layers_data: [(layer_name, layer_path, raw_dict)]
]:
    """Story 4.2/4.3: like `compile_skill` but never writes to disk.

    Returns the explain-mode flat node stream (carries `FragmentBoundary`
    and `ExplainVar` sentinels), the dep tree, the variable scope, the
    fragment cache (with the root template seeded), the scenario root, and
    the TOML layer data (Story 4.3) for `--explain --json` toml_fields[].
    """
    (
        flat_nodes,
        dep_tree,
        var_scope,
        cache,
        scenario_root,
        _basename,
        _source_text,
        _lockfile_path,
        _output_path,
        _tid,
        _toml_layers,
        _toml_layer_paths,
    ) = _compile_core(
        skill_dir, install_dir, target_ide,
        lockfile_root=lockfile_root,
        override_root=override_root,
        install_flags=install_flags,
        explain_mode=True,
    )
    # Zip the parallel lists into 3-tuples: (layer_name, layer_path, raw_dict).
    # _toml_layers entries are 2-tuples (name, dict); _toml_layer_paths is a
    # parallel list of file paths. Zip produces ((name, d), path) pairs which
    # we repack as (name, path, d) for the caller.
    toml_layers_data: list[tuple[str, str, dict[str, Any]]] = [
        (name, path, d)
        for (name, d), path in zip(_toml_layers, _toml_layer_paths)
    ]
    return flat_nodes, dep_tree, var_scope, cache, scenario_root, toml_layers_data


# Story 4.2 R2 P1: precompiled regex matching XML 1.0-illegal control
# characters. The XML 1.0 spec forbids U+0000–U+0008, U+000B–U+000C,
# U+000E–U+001F in any position (including escaped entities). A raw byte
# in this range from a YAML/TOML value would defeat the whole point of
# the R1 escape work — `xml.etree.parse` would reject the explain output.
# Replace with U+FFFD (REPLACEMENT CHARACTER) — the standard "lost data"
# substitute, well-formed in XML 1.0.
import re as _re
_XML_ILLEGAL_RE = _re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _xml_escape_attr(value: str) -> str:
    """Story 4.2 R1 P1 + R2 P1: escape a string for safe inclusion as an
    XML double-quoted attribute value. Without this, an attribute value
    containing `"`, `&`, `<`, or `>` produces malformed XML that downstream
    consumers (the LLM, `xml.etree`, lint tooling) parse incorrectly.
    Newlines and tabs are escaped to numeric entities so multi-line values
    don't break attribute parsing. Illegal control chars (R2 P1) are
    replaced with U+FFFD before any other transformation so we don't emit
    `&#10;` for a forbidden code point.
    """
    return (
        _XML_ILLEGAL_RE.sub("�", value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("\n", "&#10;")
        .replace("\r", "&#13;")
        .replace("\t", "&#9;")
    )


def _xml_escape_text(value: str) -> str:
    """Story 4.2 R1 P1 + R2 P1: escape a string for safe inclusion as
    element text content. Specifically, a resolved variable value
    containing the literal `</Variable>` would otherwise close its
    wrapping tag prematurely; escaping `<` and `&` prevents tag-content
    injection. We do NOT escape `>`, `"`, or whitespace — they are valid
    text content. Illegal control chars (R2 P1) are replaced with U+FFFD.
    """
    return (
        _XML_ILLEGAL_RE.sub("�", value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
    )


def _include_attrs(
    frag: resolver.ResolvedFragment,
    cache: resolver.CompileCache,
    scenario_root: io.PurePosixPath,
) -> str:
    """Story 4.2: compose the attribute string for one `<Include>` tag.

    Required attrs (fixed order, most-important-first): `src`,
    `resolved-from`, `hash`. Conditional attrs in alphabetical order for
    twice-run determinism: `base-hash`, `override-hash`, `override-path`,
    `variant`. See AC 5 / Dev Notes "Attribute ordering".

    All string-typed attribute values pass through `_xml_escape_attr` (R1
    P1) so paths/names containing `"`, `&`, `<`, `>` produce well-formed
    XML rather than corrupting the surrounding tag.
    """
    src_text = cache.get_source((frag.resolved_path, frag.resolved_from))
    h = io.hash_text(src_text)
    attrs: list[str] = [
        f'src="{_xml_escape_attr(frag.src)}"',
        f'resolved-from="{_xml_escape_attr(frag.resolved_from)}"',
        f'hash="{h}"',  # SHA-256 hex — no escape needed
    ]
    # Override tiers (including user-full-skill on the root) carry override
    # provenance attrs. `base-hash` is conditional on a base file existing
    # AND being readable (R1 P2: defensive against TOCTOU between probe and
    # render — without this, a deleted base file raises FileNotFoundError
    # mid-render and kills the explain output).
    if frag.resolved_from in ("user-module-fragment", "user-override", "user-full-skill"):
        if frag.base_path is not None and io.is_file(str(frag.base_path)):
            base_src = io.read_template(str(frag.base_path))
            attrs.append(f'base-hash="{io.hash_text(base_src)}"')
        attrs.append(f'override-hash="{h}"')
        op = lockfile._normalize_path(str(frag.resolved_path), scenario_root)
        attrs.append(f'override-path="{_xml_escape_attr(op)}"')
    if frag.resolved_from == "variant":
        # `variants._IDE_SUFFIX_RE` is a module-private regex. Cross-module
        # private access is intentional: `variants.py` is FROZEN for this
        # story, and promoting it to a public name would require modifying
        # a frozen file. Documented in spec Dev Notes.
        m = variants._IDE_SUFFIX_RE.match(frag.resolved_path.name)
        if m:
            attrs.append(f'variant="{_xml_escape_attr(m.group("ide"))}"')
    return " ".join(attrs)


def _variable_attrs(
    node: resolver.ExplainVar,
    scenario_root: io.PurePosixPath,
) -> str:
    """Story 4.2: compose the attribute string for one `<Variable>` tag.

    Required attrs (fixed order): `name`, `source`, `resolved-at`.
    Conditional attrs in alphabetical order: `contributing-paths`,
    `source-path`, `toml-layer`. `resolved-at="compile-time"` is a static
    phase tag, NEVER a wall-clock timestamp (AC 5 determinism).

    All string-typed attribute values pass through `_xml_escape_attr` (R1
    P1).
    """
    rv = node.rv
    attrs: list[str] = [
        f'name="{_xml_escape_attr(node.name)}"',
        f'source="{_xml_escape_attr(rv.source)}"',
        'resolved-at="compile-time"',
    ]
    if rv.contributing_paths:
        # Normalize each contributing path to scenario-root-relative for
        # deterministic, environment-independent output. Sort for
        # twice-run determinism (already sorted in build(), but defensive).
        normalized = sorted(
            lockfile._normalize_path(p, scenario_root) for p in rv.contributing_paths
        )
        joined = ";".join(normalized)
        attrs.append(f'contributing-paths="{_xml_escape_attr(joined)}"')
    if rv.source_path is not None:
        rel = lockfile._normalize_path(rv.source_path, scenario_root)
        attrs.append(f'source-path="{_xml_escape_attr(rel)}"')
    if rv.toml_layer is not None:
        attrs.append(f'toml-layer="{_xml_escape_attr(rv.toml_layer)}"')
    return " ".join(attrs)


def _render_explain(
    flat: list[Any],
    dep_tree: list[resolver.ResolvedFragment],
    var_scope: resolver.VariableScope,
    cache: resolver.CompileCache,
    scenario_root: io.PurePosixPath,
) -> str:
    """Story 4.2: walk the explain-mode flat node stream and emit
    Markdown+XML provenance output.

    Wraps the entire output in the root template's `<Include>` (using
    `dep_tree[0]`'s tier). `FragmentBoundary` sentinels emit nested
    `<Include>` / `</Include>` wrappers; `ExplainVar` emits `<Variable>`;
    `parser.VarRuntime` passes through as `{name}` literally (AC 3);
    `parser.Text` content is emitted verbatim.
    """
    parts: list[str] = []
    root_frag = dep_tree[0]
    parts.append(f"<Include {_include_attrs(root_frag, cache, scenario_root)}>\n")
    for node in flat:
        if isinstance(node, resolver.FragmentBoundary):
            if node.is_start:
                parts.append(
                    f"<Include {_include_attrs(node.fragment, cache, scenario_root)}>\n"
                )
            else:
                parts.append("</Include>\n")
        elif isinstance(node, resolver.ExplainVar):
            attrs = _variable_attrs(node, scenario_root)
            # R1 P1: escape `<` and `&` in element content — without this,
            # a resolved value containing `</Variable>` would close the
            # wrapping tag prematurely and corrupt downstream XML parsing.
            parts.append(f"<Variable {attrs}>{_xml_escape_text(node.value)}</Variable>")
        elif isinstance(node, parser.VarRuntime):
            parts.append("{" + node.name + "}")
        elif isinstance(node, parser.Text):
            parts.append(node.content)
        # Other AstNode types (e.g. Include — should be expanded by resolver)
        # are silently dropped; this matches `_render`'s defensive posture.

    # Story 4.4: append <TomlGlobExpansion> blocks for each `file:` array.
    # Placed BEFORE the closing root `</Include>` so the output stays a
    # single-rooted XML document (downstream parsers + xmllint rely on
    # this). Empty when no `file:` arrays exist (the common case —
    # bmad-help baseline, every Story 1.x–4.3 fixture).
    #
    # R2 P1: sort by `toml_key` to match `_render_explain_json`'s ordering,
    # so markdown and JSON outputs agree on order. TOML insertion order is
    # stable on the same machine but a future re-author could swap two
    # `[section]` blocks; the resulting markdown should not flip with it
    # while the JSON stays sorted. Aligning both on `toml_key` removes the
    # divergence.
    for ge in sorted(var_scope._glob_expansions, key=lambda g: g.toml_key):  # pragma: allow-raw-io
        rp_attr = (
            _xml_escape_attr(ge.resolved_pattern)
            if ge.resolved_pattern is not None else "(deferred)"
        )
        tag_parts: list[str] = [
            f'<TomlGlobExpansion pattern="{_xml_escape_attr(ge.pattern)}"',
            f' resolved_pattern="{rp_attr}"',
            f' toml-layer="{_xml_escape_attr(ge.toml_layer)}"',
        ]
        # `contributing-paths` only when >1 layer contributed (matches the
        # `<Variable>` attribute convention from Story 4.2 fold-in 1).
        if len(ge.contributing_source_paths) > 1:
            csp = ";".join(sorted(ge.contributing_source_paths))
            tag_parts.append(f' contributing-paths="{_xml_escape_attr(csp)}"')
        tag_parts.append(">\n")
        parts.append("".join(tag_parts))
        for m in ge.matches:
            parts.append(
                f'<TomlGlobMatch path="{_xml_escape_attr(m.path)}" '
                f'hash="{m.hash}" />\n'
            )
        parts.append("</TomlGlobExpansion>\n")

    parts.append("\n</Include>\n")
    return "".join(parts)


def _render_explain_tree(
    flat: list[Any],
    dep_tree: list[resolver.ResolvedFragment],
    scenario_root: io.PurePosixPath,  # reserved for path normalisation if needed in future
) -> str:
    """Story 4.3: walk explain-mode flat node stream and emit fragment tree.

    Root fragment at depth 0. FragmentBoundary start/end sentinels drive
    depth tracking. No content (Text, VarRuntime, ExplainVar) is emitted.
    Format per line: '{indent}{src}  [{resolved_from}]'
    """
    _ = scenario_root  # unused in v1; reserved for path normalisation
    parts: list[str] = []
    root = dep_tree[0]
    parts.append(f"{root.src}  [{root.resolved_from}]\n")
    depth = 0
    for node in flat:
        if isinstance(node, resolver.FragmentBoundary):
            if node.is_start:
                depth += 1
                parts.append(
                    f"{'  ' * depth}{node.fragment.src}  [{node.fragment.resolved_from}]\n"
                )
            else:
                depth -= 1
        # Text, VarRuntime, ExplainVar: silently skip
    return "".join(parts)


def _flatten_toml_for_json(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten a TOML dict to dotted-key → raw-value mapping.

    Unlike resolver._flatten_toml, this function does NOT raise on list
    values — it records them as-is. Used exclusively by _render_explain_json
    to enumerate all toml_fields[] entries including array-type fields.
    """
    result: dict[str, Any] = {}
    for k, v in d.items():
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            result.update(_flatten_toml_for_json(v, full_key))
        else:
            result[full_key] = v  # scalar or list — recorded as-is
    return result


def _render_explain_json(
    flat: list[Any],
    dep_tree: list[resolver.ResolvedFragment],
    var_scope: resolver.VariableScope,
    cache: resolver.CompileCache,
    scenario_root: io.PurePosixPath,
    toml_layers_data: list[tuple[str, str, dict[str, Any]]],
) -> str:
    """Story 4.3: walk explain-mode data and emit structured JSON output.

    Produces a JSON object with schema_version, fragments[], variables[], and
    toml_fields[]. All keys are sorted for twice-run determinism.
    """
    # Story 4.4: var_scope is now read for `glob_expansions[]` below.

    # --- fragments[] — DFS pre-order (dep_tree is already in this order) ---
    fragments: list[dict[str, Any]] = []
    for frag in dep_tree:
        src_text = cache.get_source((frag.resolved_path, frag.resolved_from))
        h = io.hash_text(src_text)
        entry: dict[str, Any] = {
            "src": frag.src,
            "resolved_from": frag.resolved_from,
            "hash": h,
        }
        if frag.resolved_from in ("user-module-fragment", "user-override", "user-full-skill"):
            if frag.base_path is not None and io.is_file(str(frag.base_path)):
                base_src = io.read_template(str(frag.base_path))
                entry["base_hash"] = io.hash_text(base_src)
            entry["override_hash"] = h
            entry["override_path"] = lockfile._normalize_path(
                str(frag.resolved_path), scenario_root
            )
        if frag.resolved_from == "variant":
            m = variants._IDE_SUFFIX_RE.match(frag.resolved_path.name)
            if m:
                entry["variant"] = m.group("ide")
        fragments.append(entry)

    # --- variables[] — document order (ExplainVar nodes in flat) ---
    variables: list[dict[str, Any]] = []
    for node in flat:
        if isinstance(node, resolver.ExplainVar):
            rv = node.rv
            var_entry: dict[str, Any] = {
                "name": node.name,
                "source": rv.source,
                "resolved_at": "compile-time",
                "value": node.value,
            }
            if rv.contributing_paths is not None:
                var_entry["contributing_paths"] = sorted(
                    lockfile._normalize_path(p, scenario_root)
                    for p in rv.contributing_paths
                )
            if rv.source_path is not None:
                var_entry["source_path"] = lockfile._normalize_path(
                    rv.source_path, scenario_root
                )
            if rv.toml_layer is not None:
                var_entry["toml_layer"] = rv.toml_layer
            variables.append(var_entry)

    # --- toml_fields[] — all dotted paths across all TOML layers ---
    toml_fields: list[dict[str, Any]] = []
    if toml_layers_data:
        merged_all = toml_merge.merge_layers(*[d for _, _, d in toml_layers_data])
    else:
        merged_all = {}
    merged_flat = _flatten_toml_for_json(merged_all)
    layer_flats: dict[str, dict[str, Any]] = {
        name: _flatten_toml_for_json(d) for name, _, d in toml_layers_data
    }
    all_paths: set[str] = set(merged_flat)
    for lf in layer_flats.values():
        all_paths.update(lf.keys())
    for path in sorted(all_paths):
        current_value = merged_flat.get(path)
        default_value: Any = None
        layers_dict: dict[str, Any] = {}
        for layer_name, _layer_path, _ in toml_layers_data:
            lf = layer_flats.get(layer_name, {})
            if path in lf:
                v = lf[path]
                if layer_name == "defaults":
                    default_value = v
                hash_v = io.hash_text(json.dumps(v, sort_keys=True))
                layers_dict[layer_name] = {"hash": hash_v, "value": v}
        toml_fields.append({
            "current_value": current_value,
            "default_value": default_value,
            "layers": layers_dict,
            "path": path,
        })

    # Story 4.4: glob_expansions[] — additive top-level array. No
    # schema_version bump (the v1 schema does not restrict additionalProperties
    # at root, per Story 4.3 AC 4 → schemas/explain-v1.json). Sort by
    # `toml_key` for twice-run determinism; matches[] is already sorted by
    # path in `VariableScope.build()`.
    glob_expansions_list: list[dict[str, Any]] = []  # pragma: allow-raw-io
    for ge in var_scope._glob_expansions:  # pragma: allow-raw-io
        glob_expansions_list.append({  # pragma: allow-raw-io
            "toml_key": ge.toml_key,
            "pattern": ge.pattern,
            "resolved_pattern": ge.resolved_pattern,
            "match_set_hash": ge.match_set_hash,
            "toml_layer": ge.toml_layer,
            "contributing_source_paths": list(ge.contributing_source_paths),
            "matches": [{"path": m.path, "hash": m.hash} for m in ge.matches],
        })
    glob_expansions_list.sort(key=lambda e: e["toml_key"])  # pragma: allow-raw-io

    result = {
        "fragments": fragments,
        "glob_expansions": glob_expansions_list,  # pragma: allow-raw-io
        "schema_version": 1,
        "toml_fields": toml_fields,
        "variables": variables,
    }
    return json.dumps(result, sort_keys=True, indent=2) + "\n"
