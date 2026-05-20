#!/usr/bin/env python3
"""render.py — bmad-quick-dev template renderer.

Resolves compile-time {{.variable}} placeholders from BMad's central config,
bakes absolute paths for {project-root} into derived values, and writes
rendered .md files to {project-root}/_bmad/render/bmad-quick-dev/.

Config: four-layer merge of _bmad/config.toml + config.user.toml +
custom/config.toml + custom/config.user.toml (post-#2285 installs).
Keys surface from [core] and [modules.bmm]. Missing config.toml → HALT.

Runtime {variable} placeholders (single curly) pass through untouched for
the LLM to resolve during workflow execution.

Every invocation rebuilds from scratch — no hash, no cache.
Python 3.11+ stdlib only. UTF-8 I/O.
"""

import json
import os
import posixpath
import re
import sys
import tomllib

_render_dir = os.path.dirname(os.path.abspath(__file__))
_bmad_scripts = os.path.normpath(os.path.join(_render_dir, "..", "..", "scripts"))
if os.path.isdir(_bmad_scripts) and _bmad_scripts not in sys.path:
    sys.path.insert(0, _bmad_scripts)

_JIT_SENTINEL_RE = re.compile(
    r'<!--\s*BMAD-JIT:(?P<name>[A-Z][A-Za-z0-9]+):(?P<hash>[0-9a-f]{16})\s*-->'
)


def find_project_root() -> str:
    """Walk up from cwd until a _bmad/ directory is found. On failure, print a
    HALT instruction to stdout and exit non-zero.
    Returns an OS-native path; callers must normalize with `.replace(os.sep, "/")` before
    passing to `posixpath` functions."""
    current = os.path.abspath(os.getcwd())
    while True:
        candidate = os.path.join(current, "_bmad")
        if os.path.isdir(candidate):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            print(
                f"HALT and report to the user: no _bmad/ directory found walking up from {os.getcwd()}"
            )
            sys.exit(1)
        current = parent


def _deep_merge(base: object, override: object) -> object:
    """Dict-aware deep merge. Lists and scalars: override wins (we don't need
    the full keyed-merge semantics of resolve_config.py — quick-dev only reads
    flat scalars out of [core] and [modules.bmm])."""
    if isinstance(base, dict) and isinstance(override, dict):
        result = dict(base)
        for key, value in override.items():
            result[key] = _deep_merge(result[key], value) if key in result else value
        return result
    return override


def load_central_config(root: str) -> dict[str, object]:
    """Four-layer merge of _bmad/config.toml and its peers. HALTs if the base
    _bmad/config.toml is absent.
    `root` must be POSIX-normalized (forward slashes only) before calling this function."""
    bmad_dir = posixpath.join(root, "_bmad")
    base = posixpath.join(bmad_dir, "config.toml")
    if not os.path.isfile(base):
        print(
            f"HALT and report to the user: central config not found at {base} — "
            "ensure this is a post-#2285 BMAD install"
        )
        sys.exit(1)

    layers = [
        base,
        posixpath.join(bmad_dir, "config.user.toml"),
        posixpath.join(bmad_dir, "custom", "config.toml"),
        posixpath.join(bmad_dir, "custom", "config.user.toml"),
    ]
    merged = {}
    for path in layers:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as fh:
                data = tomllib.load(fh)
        except (tomllib.TOMLDecodeError, OSError) as error:
            print(f"render.py: skipping {path}: {error}", file=sys.stderr)
            continue
        if isinstance(data, dict):
            merged = _deep_merge(merged, data)
    return merged


def flatten_central_config(merged: dict[str, object]) -> dict[str, str]:
    """Lift scalar keys from [core] and [modules.bmm] into a single namespace.
    Module keys take precedence on collision (installer strips core keys from
    module buckets, so collisions shouldn't happen in practice)."""
    flat = {}
    for section in (merged.get("core"), merged.get("modules", {}).get("bmm")):
        if not isinstance(section, dict):
            continue
        for key, value in section.items():
            if isinstance(value, bool):
                flat[key] = "true" if value else "false"
            elif isinstance(value, (str, int, float)):
                flat[key] = str(value)
    return flat


def render_template(content: str, vars_: dict[str, str]) -> str:
    """Resolve {{.var}} substitutions. Unresolved references emit an empty string
    (Go's missingkey=zero semantics)."""
    return re.sub(r"\{\{\.(\w+)\}\}", lambda m: vars_.get(m.group(1), ""), content)


def _build_jit_ctx_config(root: str) -> dict:
    """Four-layer central config merge for JIT ctx.config.
    Uses bmad_compile.toml_merge.merge_layers — not the local _deep_merge."""
    from bmad_compile.toml_merge import merge_layers, load_toml_file
    bmad_dir = posixpath.join(root, "_bmad")
    return merge_layers(
        load_toml_file(posixpath.join(bmad_dir, "config.toml")),
        load_toml_file(posixpath.join(bmad_dir, "config.user.toml")),
        load_toml_file(posixpath.join(bmad_dir, "custom", "config.toml")),
        load_toml_file(posixpath.join(bmad_dir, "custom", "config.user.toml")),
    )


def _emit_jit_event(event: dict) -> None:
    """Emit a component_error NDJSON event to stderr (JIT runtime — not compile stdout).
    Uses sort_keys for deterministic output; flush=True ensures delivery before exceptions.
    try/except prevents emit errors from propagating into the render pipeline."""
    try:
        print(json.dumps(event, sort_keys=True), file=sys.stderr, flush=True)
    except Exception:
        pass


def _resolve_jit_sentinels(
    content: str,
    root: str,
    skill_name: str,
    module_name: str,
    _runner=None,  # test injection: pre-built ComponentRunner-compatible instance
) -> str:
    matches = list(_JIT_SENTINEL_RE.finditer(content))
    if not matches:
        return content

    try:
        from bmad_compile.component_runner import ComponentRunner
        from bmad_compile.errors import ComponentError
    except ImportError as exc:
        _emit_jit_event({
            "kind": "component_error", "component": "<all>", "mode": "jit",
            "props": {}, "exit_code": None, "stderr": str(exc),
            "phase": "jit", "reason": "bmad_compile_unavailable",
        })
        return _JIT_SENTINEL_RE.sub(
            lambda m: f"<!-- BMAD-ERROR:{m.group('name')} -->", content
        )

    try:
        ctx_config = _build_jit_ctx_config(root)
    except Exception as exc:
        print(
            f"render.py: JIT ctx_config failed ({exc}); using empty config",
            file=sys.stderr,
        )
        ctx_config = {}

    if sys.version_info < (3, 11):
        _emit_jit_event({
            "kind": "component_error", "component": "<all>", "mode": "jit",
            "props": {}, "exit_code": None, "stderr": "",
            "phase": "jit", "reason": "python_version_too_old",
        })
        return _JIT_SENTINEL_RE.sub(
            lambda m: f"<!-- BMAD-ERROR:{m.group('name')} -->", content
        )

    lockfile_path = posixpath.join(root, "_bmad", "_config", "bmad.lock")
    if not os.path.isfile(lockfile_path):
        _emit_jit_event({
            "kind": "component_error", "component": "<all>", "mode": "jit",
            "props": {}, "exit_code": None, "stderr": "", "phase": "jit",
            "reason": "lockfile_absent",
        })
        return _JIT_SENTINEL_RE.sub(
            lambda m: f"<!-- BMAD-ERROR:{m.group('name')} -->", content
        )

    try:
        with open(lockfile_path, encoding="utf-8") as fh:
            raw = fh.read()
        lockfile_data = json.loads(raw.lstrip("﻿"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        _emit_jit_event({
            "kind": "component_error", "component": "<all>",
            "mode": "jit", "props": {}, "exit_code": None,
            "stderr": str(exc), "phase": "jit",
            "reason": "lockfile_malformed",
        })
        return _JIT_SENTINEL_RE.sub(
            lambda m: f"<!-- BMAD-ERROR:{m.group('name')} -->", content
        )

    raw_entries = lockfile_data.get("entries")
    entries_list = raw_entries if isinstance(raw_entries, list) else []
    skill_entry = None
    for entry in entries_list:
        if isinstance(entry, dict) and entry.get("skill") == skill_name:
            skill_entry = entry
            break

    # Collect unique (name, hash) pairs in encounter order
    seen_keys: dict[tuple[str, str], None] = {}
    for m in matches:
        key = (m.group("name"), m.group("hash"))
        if key not in seen_keys:
            seen_keys[key] = None
    unique_pairs = list(seen_keys.keys())

    if skill_entry is None:
        for (name, _) in unique_pairs:
            _emit_jit_event({
                "kind": "component_error", "component": name,
                "mode": "jit", "props": {}, "exit_code": None,
                "stderr": "", "phase": "jit",
                "reason": "lockfile_entry_missing",
            })
        return _JIT_SENTINEL_RE.sub(
            lambda m: f"<!-- BMAD-ERROR:{m.group('name')} -->", content
        )

    raw_comps = skill_entry.get("components")
    comps_list = raw_comps if isinstance(raw_comps, list) else []

    installed_component_dir = posixpath.join(
        root, "_bmad", "components", module_name, skill_name
    )
    ctx_dict = {
        "config": ctx_config,
        "skill_id": f"{module_name}/{skill_name}",
        "skill_source_root": installed_component_dir,
        "render_mode": "jit",
    }
    runner = _runner if _runner is not None else ComponentRunner(emit_fn=_emit_jit_event)

    _replacements: dict[tuple[str, str], str] = {}

    for (name, hash_) in unique_pairs:
        comp = None
        for c in comps_list:
            if (isinstance(c, dict)
                    and c.get("name") == name
                    and c.get("props_hash") == hash_):
                comp = c
                break

        sentinel_key = (name, hash_)

        if comp is None:
            _emit_jit_event({
                "kind": "component_error", "component": name,
                "mode": "jit", "props": {}, "exit_code": None,
                "stderr": "", "phase": "jit",
                "reason": "lockfile_entry_missing",
            })
            _replacements[sentinel_key] = f"<!-- BMAD-ERROR:{name} -->"
            continue

        props_val = comp.get("props")
        props_dict = props_val if isinstance(props_val, dict) else {}

        path_val = comp.get("path")
        if not isinstance(path_val, str) or not path_val:
            _emit_jit_event({
                "kind": "component_error", "component": name, "mode": "jit",
                "props": props_dict, "exit_code": None, "stderr": "",
                "phase": "jit", "reason": "component_file_missing",
            })
            _replacements[sentinel_key] = f"<!-- BMAD-ERROR:{name} -->"
            continue

        filename = posixpath.basename(path_val)
        installed_path = posixpath.join(installed_component_dir, filename)

        if not os.path.isfile(installed_path):
            _emit_jit_event({
                "kind": "component_error", "component": name, "mode": "jit",
                "props": props_dict, "exit_code": None, "stderr": "",
                "phase": "jit", "reason": "component_file_missing",
            })
            _replacements[sentinel_key] = f"<!-- BMAD-ERROR:{name} -->"
            continue

        try:
            result = runner.run_jit(
                installed_path, ctx_dict, props_dict, component_name=name
            )
            _replacements[sentinel_key] = result
        except ComponentError as exc:
            fb = exc.render_error_fallback
            _replacements[sentinel_key] = (
                fb if isinstance(fb, str) else f"<!-- BMAD-ERROR:{name} -->"
            )
        except Exception as exc:
            _emit_jit_event({
                "kind": "component_error", "component": name, "mode": "jit",
                "props": props_dict, "exit_code": None, "stderr": str(exc),
                "phase": "jit", "reason": "runner_unexpected_error",
            })
            _replacements[sentinel_key] = f"<!-- BMAD-ERROR:{name} -->"

    def _repl(m: re.Match) -> str:
        key = (m.group("name"), m.group("hash"))
        if key in _replacements:
            return _replacements[key]
        return f"<!-- BMAD-ERROR:{m.group('name')} -->"

    return _JIT_SENTINEL_RE.sub(_repl, content)


def main() -> None:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_name = os.path.basename(script_dir)
    module_name = os.path.basename(os.path.dirname(script_dir))
    script_dir = script_dir.replace(os.sep, "/")
    root = find_project_root()
    root = root.replace(os.sep, "/")
    bmad_dir = posixpath.join(root, "_bmad")

    vars_ = flatten_central_config(load_central_config(root))

    for key in list(vars_.keys()):
        vars_[key] = vars_[key].replace("{project-root}", root)

    vars_["project_root"] = root
    vars_["main_config"] = posixpath.join(bmad_dir, "config.toml")
    if "implementation_artifacts" not in vars_:
        print(
            "HALT and report to the user: render.py: config missing 'implementation_artifacts' key — "
            "ensure [modules.bmm] implementation_artifacts is set in _bmad/config.toml"
        )
        sys.exit(1)
    vars_["sprint_status"] = posixpath.join(
        vars_["implementation_artifacts"], "sprint-status.yaml"
    )
    vars_["deferred_work_file"] = posixpath.join(
        vars_["implementation_artifacts"], "deferred-work.md"
    )

    out_dir = posixpath.join(root, "_bmad", "render", skill_name)
    os.makedirs(out_dir, exist_ok=True)

    for fname in os.listdir(out_dir):
        if fname.endswith(".md"):
            os.remove(posixpath.join(out_dir, fname))

    count = 0
    for fname in sorted(os.listdir(script_dir)):
        if not fname.endswith(".md") or fname == "SKILL.md":
            continue
        src = posixpath.join(script_dir, fname)
        dst = posixpath.join(out_dir, fname)
        with open(src, "r", encoding="utf-8", newline="") as fh:
            content = fh.read()
        with open(dst, "w", encoding="utf-8", newline="") as fh:
            fh.write(render_template(content, vars_))
        count += 1

    print(f"render.py: rendered {count} files -> {out_dir}", file=sys.stderr)

    skill_md_src = posixpath.join(script_dir, "SKILL.md")
    if os.path.isfile(skill_md_src):
        with open(skill_md_src, "r", encoding="utf-8", newline="") as fh:
            skill_md_content = fh.read()
        resolved = _resolve_jit_sentinels(
            skill_md_content, root, skill_name, module_name
        )
        skill_md_dst = posixpath.join(out_dir, "SKILL.md")
        with open(skill_md_dst, "w", encoding="utf-8", newline="") as fh:
            fh.write(resolved)

    workflow_md = posixpath.join(out_dir, "workflow.md")
    print(f"read and follow {workflow_md}")


if __name__ == "__main__":
    main()
