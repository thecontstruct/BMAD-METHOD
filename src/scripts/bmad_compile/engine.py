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


def compile_skill(
    skill_dir: io.PathLike,
    install_dir: io.PathLike,
    target_ide: str | None = None,
    *,
    lockfile_root: io.PathLike | None = None,
    override_root: io.PathLike | None = None,
) -> None:
    """Compile a single skill directory to `<install_dir>/<skill_basename>/SKILL.md`.

    Staging discipline: parse + resolve + render fully in memory. Only on
    full success do we call `io.write_text`. Any `CompilerError` raised
    mid-compile leaves the filesystem untouched (Story 1.1 AC 10).

    AC 6 (Story 2.1): optional keyword-only `lockfile_root` and `override_root`
    params allow the install-phase caller to override the derived paths.
    When either is None, today's `skill_dir.parent.parent / "_bmad"` derivation
    is used, preserving full backward compatibility.
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
        candidate_override_root = io.to_posix(override_root)
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
        override_root_template = (
            override_root
            / "fragments"
            / current_module
            / basename
            / "SKILL.template.md"
        )
        # `is_file` (not `path_exists`) — a directory at this slot would
        # otherwise pass the probe and crash later in `read_template` with
        # a raw `IsADirectoryError` / `PermissionError` outside the
        # `CompilerError` taxonomy. Mirrors the resolver-level fix in R4.
        if io.is_file(str(override_root_template)):
            root_resolved_from = "user-full-skill"
        else:
            override_root_template = None

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
    nodes = parser.parse(source, relative_path)

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
        toml_layers=_toml_layers or None,
        toml_layer_paths=_toml_layer_paths or None,
    )

    context = resolver.ResolveContext(
        skill_dir=skill_posix,
        module_roots=module_roots,
        current_module=current_module,
        override_root=override_root,
        target_ide=target_ide,
        root_resolved_from=root_resolved_from,
        var_scope=var_scope,
    )
    cache = resolver.CompileCache()
    flat_nodes, dep_tree = resolver.resolve(
        nodes,
        context,
        cache,
        root_src=relative_path,
        root_path=template_path,
        root_source=source,
    )

    # Render fully in memory — AC 10 (no partial writes on error).
    rendered = _render(flat_nodes)

    install_posix = io.to_posix(install_dir)
    # AC 6: when lockfile_root is provided (install-phase mode), output gains
    # the <module>/ segment so SKILL.md lands at <install_dir>/<module>/<skill>/SKILL.md.
    # When lockfile_root is None (per-skill CLI mode), preserve today's layout.
    if lockfile_root is not None:
        module = skill_posix.parent.name
        output_path = install_posix / module / basename / "SKILL.md"
    else:
        output_path = install_posix / basename / "SKILL.md"
    io.write_text(str(output_path), rendered)

    lockfile.write_skill_entry(
        _lockfile_path,
        scenario_root,
        basename,
        source_text=source,
        compiled_text=rendered,
        dep_tree=dep_tree,
        var_scope=var_scope,
        target_ide=target_ide,
        cache=cache,
    )
