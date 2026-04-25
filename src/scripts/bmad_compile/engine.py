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
(`--tools`), Story 1.5 lockfile writes. Real module discovery (reading
`module.yaml` etc.) lands in Story 2.x. This module routes every
filesystem/hash/time concern through `io`.
"""

from __future__ import annotations

from typing import Iterable

from . import io, parser, resolver, toml_merge


def _find_template(skill_dir):
    """Pick the template source from a skill directory.

    Preference order (deterministic):
    1. `<skill_basename>.template.md`  (conventional single-file skill)
    2. First `*.template.md` by sorted POSIX name (fallback)

    Returns the POSIX-style path object from `io.list_dir_sorted`.
    """
    skill_posix = io.to_posix(skill_dir)
    basename = skill_posix.name
    preferred_name = f"{basename}.template.md"

    entries = io.list_dir_sorted(skill_dir)
    # `is_file` filter mirrors the resolver tier probes (R4/R5/R6): a
    # subdirectory whose name ends in `.template.md` would otherwise be
    # selected here and crash later in `read_template` with a raw
    # `IsADirectoryError` outside the `CompilerError` taxonomy.
    templates = [
        e for e in entries
        if e.name.endswith(".template.md") and io.is_file(str(e))
    ]

    for entry in templates:
        if entry.name == preferred_name:
            return entry

    if len(templates) == 1:
        return templates[0]

    if templates:
        names = [e.name for e in templates]
        raise FileNotFoundError(
            f"skill directory '{skill_dir}' contains {len(templates)} "
            f"'*.template.md' files with no preferred match "
            f"('{preferred_name}'): {names!r} — "
            f"rename one to '{preferred_name}' to disambiguate"
        )

    raise FileNotFoundError(
        f"no '*.template.md' found in skill directory '{skill_dir}'"
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


def compile_skill(skill_dir, install_dir) -> None:
    """Compile a single skill directory to `<install_dir>/<skill_basename>/SKILL.md`.

    Staging discipline: parse + resolve + render fully in memory. Only on
    full success do we call `io.write_text`. Any `CompilerError` raised
    mid-compile leaves the filesystem untouched (Story 1.1 AC 10).
    """
    skill_posix = io.to_posix(skill_dir)
    if not io.is_dir(str(skill_posix)):
        raise NotADirectoryError(
            f"skill path '{skill_dir}' is not a directory — "
            "pass a skill directory (containing '*.template.md'), not a file"
        )
    basename = skill_posix.name

    # Story 1.2: hardcoded-`core` module discovery. Real discovery (reading
    # `module.yaml`, enumerating installed modules) lands in Story 2.x. The
    # fixture convention `<scenario>/core/<scenario>-skill/` makes
    # `skill_dir.parent` the synthetic module root.
    module_roots = {"core": skill_posix.parent}
    current_module = "core"

    # Override root probes `<skill>.parent.parent / _bmad / custom`. For a
    # fixture `.../<scenario>/core/<scenario>-skill/` this lands at
    # `.../<scenario>/_bmad/custom`. If the directory is absent, all
    # override-tier lookups short-circuit to None.
    scenario_root = skill_posix.parent.parent
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
        # When the root is swapped to an override-rooted file, error
        # messages must point authors to the override path — otherwise a
        # parse error in the override SKILL.template.md gets reported with
        # a base-shaped relative path, sending the author to edit the
        # wrong file. Same `override_root`-relative form used by
        # `resolver._relative_file` for nested errors under the override.
        relative_path = str(template_path.relative_to(override_root))
    else:
        template_path = _find_template(skill_dir)
        relative_path = f"{basename}/{template_path.name}"

    source = io.read_template(str(template_path))
    nodes = parser.parse(source, relative_path)

    # --- Variable scope (Decision 3) ---
    # Probe for bmad-config YAML (non-self.* cascade, bmad-config tier).
    # Convention: <scenario_root>/_bmad/core/config.yaml
    yaml_config_path: str | None = None
    _yaml_candidate = scenario_root / "_bmad" / "core" / "config.yaml"
    if io.is_file(str(_yaml_candidate)):
        yaml_config_path = str(_yaml_candidate)

    # Build self.* TOML layer stack (lowest → highest: defaults → team → user).
    _toml_layers: list[tuple[str, dict]] = []
    _customize_toml = skill_posix / "customize.toml"
    if io.is_file(str(_customize_toml)):
        _toml_layers.append(("defaults", toml_merge.load_toml_file(str(_customize_toml))))
    if override_root is not None:
        _team_toml = override_root / f"{basename}.toml"
        if io.is_file(str(_team_toml)):
            _toml_layers.append(("team", toml_merge.load_toml_file(str(_team_toml))))
        _user_toml = override_root / f"{basename}.user.toml"
        if io.is_file(str(_user_toml)):
            _toml_layers.append(("user", toml_merge.load_toml_file(str(_user_toml))))

    var_scope = resolver.VariableScope.build(
        yaml_config_path=yaml_config_path,
        toml_layers=_toml_layers or None,
    )

    context = resolver.ResolveContext(
        skill_dir=skill_posix,
        module_roots=module_roots,
        current_module=current_module,
        override_root=override_root,
        target_ide=None,  # Story 1.4 wires --tools
        root_resolved_from=root_resolved_from,
        var_scope=var_scope,
    )
    cache = resolver.CompileCache()
    flat_nodes, _dep_tree = resolver.resolve(
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
    output_path = install_posix / basename / "SKILL.md"
    io.write_text(str(output_path), rendered)

    # TODO(Story 1.5): emit lockfile entry from `_dep_tree`.
