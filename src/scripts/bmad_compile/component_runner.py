"""ComponentRunner — in-process component execution manager."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import posixpath
import re
import sys

# io_mod is the bmad_compile.io module (not the stdlib io). Imported at module
# load with an alias to avoid shadowing the stdlib `io` import above, which is
# still needed by other consumers in this file.
import bmad_compile.io as io_mod
import tokenize
import traceback
import types
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TYPE_CHECKING, Any, Callable

from bmad_compile.errors import (
    ComponentBatchError,
    ComponentError,
    ComponentPropError,
)

if TYPE_CHECKING:
    from bmad_compile.cache import ComponentCache

_COMPILE_BATCH_WORKERS: int = 4

# Two-phase RENDER_ERROR_FALLBACK extraction (mirrors component_wrapper.py):
# Skeleton applied to STRIPPED source (proves module-level presence; docstrings blanked).
# Full regex applied to RAW source (extracts literal value; strip removes string content).
_FALLBACK_RE = re.compile(
    r'^RENDER_ERROR_FALLBACK\s*=\s*["\'](.+)["\']', re.MULTILINE
)
_FALLBACK_SKELETON_RE = re.compile(r'^RENDER_ERROR_FALLBACK\s*=\s*', re.MULTILINE)


def _strip_string_and_comment_tokens(source: str) -> str:
    """Return source with STRING and COMMENT token text replaced by empty strings.

    Preserves line structure so MULTILINE ^ anchors remain valid on the result.
    On TokenError (unparseable source), returns source unchanged.
    Identical algorithm to component_wrapper.py and engine.py copies.
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except tokenize.TokenError:
        return source
    lines = source.splitlines(keepends=True)
    result = list(lines)
    for tok_type, _tok_str, (srow, scol), (erow, ecol), _ in reversed(tokens):
        if tok_type in (tokenize.STRING, tokenize.COMMENT):
            if srow == erow:
                result[srow - 1] = result[srow - 1][:scol] + result[srow - 1][ecol:]
            else:
                result[srow - 1] = result[srow - 1][:scol]
                for mid in range(srow, erow - 1):
                    result[mid] = "\n"
                result[erow - 1] = result[erow - 1][ecol:]
    return "".join(result)


def _read_component_source(component_path: str) -> str:
    """Read component source text for cache key computation."""
    with open(component_path, encoding="utf-8") as f:  # pragma: allow-raw-io
        return f.read()


def _run_inprocess(
    component_path: str,
    ctx_dict: dict,
    props: dict,
    *,
    component_name: str,
    emit_fn: Callable[[dict], None] | None = None,
) -> str:
    """Execute one component render() in-process. Returns str output.

    Raises:
        ComponentPropError:  props fail JSON serialization (pre-import; emits component_prop_error)
        ComponentError:      import failure or render() exception (exit_code=None; fallback set)
    """
    # Step 1: Props JSON-serializable check (preserved from Story 8.4 for behavior compat)
    try:
        json.dumps(props)
    except (TypeError, ValueError) as exc:
        prop_name = "unknown"
        for k, v in props.items():
            try:
                json.dumps(v)
            except (TypeError, ValueError):
                prop_name = k
                break
        if emit_fn is not None:
            try:
                emit_fn({
                    "kind": "component_prop_error",
                    "component": component_name,
                    "prop_name": prop_name,
                    "reason": str(exc),
                })
            except Exception:
                pass
        raise ComponentPropError(
            f"prop {prop_name!r} is not JSON-serializable: {exc}",
            component_name=component_name,
            props=props,
        ) from exc

    # Step 2: Read RENDER_ERROR_FALLBACK from source BEFORE import (FR-6.2 catch-22 prevention)
    _render_error_fallback: str | None = None
    try:
        with open(component_path, encoding="utf-8") as _f:  # pragma: allow-raw-io
            _raw_src = _f.read()
        _stripped = _strip_string_and_comment_tokens(_raw_src)
        if _FALLBACK_SKELETON_RE.search(_stripped):
            _fb_match = _FALLBACK_RE.search(_raw_src)
            if _fb_match:
                _render_error_fallback = _fb_match.group(1)
    except Exception:
        pass  # pre-read failure is non-fatal; fallback stays None

    # Step 3: Import component module via importlib
    try:
        _spec = importlib.util.spec_from_file_location("_bmad_component", component_path)
        _module = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
        _spec.loader.exec_module(_module)  # type: ignore[union-attr]
    except Exception:
        raise ComponentError(
            f"component import failed: {traceback.format_exc()}",
            component_name=component_name,
            exit_code=None,
            render_error_fallback=_render_error_fallback,
        )

    # Step 4: Build ctx namespace, capture stdout, call render()
    _ctx = types.SimpleNamespace(**ctx_dict)
    _buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(_buf):
            _result = _module.render(_ctx, **props)
    except Exception:
        raise ComponentError(
            f"render() raised {traceback.format_exc()}",
            component_name=component_name,
            exit_code=None,
            render_error_fallback=_render_error_fallback,
        )

    return str(_result)  # str() coercion intentional — mirrors Story 8.4 AC-4 runner contract


class ComponentRunner:
    """In-process component execution manager.

    Serves compile-time (engine.py) and JIT-time (render.py) paths with identical API
    to the Story 8.4 subprocess-based implementation.
    """

    def __init__(
        self,
        emit_fn: Callable[[dict], None] | None = None,
        cache: "ComponentCache | None" = None,
    ) -> None:
        self._emit_fn = emit_fn or (lambda _event: None)
        self._cache = cache

    def _emit(self, event: dict) -> None:
        try:
            self._emit_fn(event)
        except Exception:
            pass  # emit_fn errors MUST NOT propagate into the dispatch path

    def run_compile_batch(
        self,
        invocations: list[Any],
        ctx_dict: dict,
        timeout_seconds: float = 10.0,  # timeout not enforced in-process; deferred to v2
    ) -> dict[int, str]:
        if not invocations:
            return {}

        results: dict[int, str] = {}
        errors: list[tuple[int, ComponentError]] = []

        # Story 10.52: split invocations into cache-hits and misses.
        invocations_to_run: list[Any] = []
        if self._cache is not None:
            for inv in invocations:
                try:
                    src_text = _read_component_source(inv.component_abs_path)
                    props_dict = dict(inv.original.props)
                    hit = self._cache.get(src_text, props_dict, ctx_dict)
                    if hit is not None:
                        results[inv.token_index] = hit
                        continue
                except Exception:
                    pass  # cache failure → treat as miss
                invocations_to_run.append(inv)
        else:
            invocations_to_run = list(invocations)

        with ThreadPoolExecutor(max_workers=_COMPILE_BATCH_WORKERS) as executor:
            future_to_inv = {
                executor.submit(
                    _run_inprocess,
                    inv.component_abs_path,
                    ctx_dict,
                    dict(inv.original.props),
                    component_name=inv.original.name,
                    emit_fn=self._emit,
                ): inv
                for inv in invocations_to_run
            }
            for future in as_completed(future_to_inv):
                inv = future_to_inv[future]
                props_dict = dict(inv.original.props)
                try:
                    output = future.result()
                    results[inv.token_index] = output
                    # Story 10.52: populate cache after successful execution.
                    if self._cache is not None:
                        try:
                            src_text = _read_component_source(inv.component_abs_path)
                            self._cache.put(src_text, props_dict, ctx_dict, output)
                        except Exception as exc:
                            sys.stderr.write(  # pragma: allow-raw-io
                                f"warning: component cache write failed: {exc}\n"
                            )
                except ComponentError as exc:
                    exc.mode = "compile"
                    exc.props = props_dict
                    if not isinstance(exc, ComponentPropError):
                        self._emit({
                            "kind": "component_error",
                            "component": inv.original.name,
                            "mode": "compile",
                            "props": props_dict,
                            "exit_code": exc.exit_code,
                            "stderr": exc.stderr or "",
                            "phase": "compile",
                        })
                    errors.append((inv.token_index, exc))
                except Exception as exc:  # unexpected; BaseException propagates uncaught
                    ce = ComponentError(
                        f"unexpected runner error: {exc}",
                        component_name=inv.original.name,
                        mode="compile",
                        props=props_dict,
                    )
                    self._emit({
                        "kind": "component_error",
                        "component": inv.original.name,
                        "mode": "compile",
                        "props": props_dict,
                        "exit_code": None,
                        "stderr": str(exc),
                        "phase": "compile",
                    })
                    errors.append((inv.token_index, ce))

        if errors:
            errors.sort(key=lambda t: t[0])
            raise ComponentBatchError(
                f"{len(errors)} component(s) failed in compile batch",
                errors=[e for _, e in errors],
            )
        return results

    def run_jit(
        self,
        component_path: str,
        ctx_dict: dict,
        props: dict,
        timeout_seconds: float = 10.0,  # timeout not enforced in-process; deferred to v2
        component_name: str = "",
    ) -> str:
        """Run one component synchronously in-process.

        Raises ComponentError (with render_error_fallback set) on any failure.
        """
        try:
            return _run_inprocess(
                component_path,
                ctx_dict,
                props,
                component_name=component_name,
                emit_fn=self._emit,
            )
        except ComponentError as exc:
            exc.mode = "jit"
            if exc.props is None:
                exc.props = props
            if not isinstance(exc, ComponentPropError):
                self._emit({
                    "kind": "component_error",
                    "component": component_name,
                    "mode": "jit",
                    "props": props,
                    "exit_code": exc.exit_code,
                    "stderr": exc.stderr or "",
                    "phase": "jit",
                })
            raise


class MockComponentRunner(ComponentRunner):
    """Test double: returns pre-configured results without executing components."""

    def __init__(
        self,
        batch_results: dict[int, str | BaseException] | None = None,
        jit_result: str | BaseException | None = None,
        emit_fn: Callable[[dict], None] | None = None,
    ) -> None:
        super().__init__(emit_fn=emit_fn)
        self._batch_results = batch_results
        self._jit_result = jit_result

    def run_compile_batch(
        self,
        invocations: list[Any],
        ctx_dict: dict,
        timeout_seconds: float = 10.0,
    ) -> dict[int, str]:
        if not invocations:
            return {}
        if self._batch_results is None:
            raise ComponentBatchError(
                "mock: batch_results not configured",
                errors=[ComponentError("mock: no batch results")],
            )
        results: dict[int, str] = {}
        errors: list[ComponentError] = []
        for inv in sorted(invocations, key=lambda i: i.token_index):
            val = self._batch_results.get(inv.token_index)
            if isinstance(val, ComponentError):
                errors.append(val)
            elif isinstance(val, BaseException):
                errors.append(ComponentError(str(val), component_name=getattr(inv.original, "name", "")))
            elif val is not None:
                results[inv.token_index] = val
        if errors:
            raise ComponentBatchError(f"{len(errors)} mock failure(s)", errors=errors)
        return results

    def run_jit(
        self,
        component_path: str,
        ctx_dict: dict,
        props: dict,
        timeout_seconds: float = 10.0,
        component_name: str = "",
    ) -> str:
        if self._jit_result is None:
            raise ComponentError(
                "mock: jit_result not configured",
                component_name=component_name,
            )
        if isinstance(self._jit_result, BaseException):
            raise self._jit_result
        return self._jit_result


# =============================================================================
# JIT sentinel resolution (Story 10.65 / AC-5; extracted from
# src/bmm-skills/4-implementation/bmad-quick-dev/render.py)
# =============================================================================

_JIT_SENTINEL_RE = re.compile(
    r'<!--\s*BMAD-JIT:(?P<name>[A-Z][A-Za-z0-9]+):(?P<hash>[0-9a-f]{16})\s*-->'
)
_JIT_BATCH_WORKERS: int = 4


def _emit_jit_event(event: dict) -> None:
    """Emit a component_error NDJSON event to stderr (JIT runtime — not compile stdout).
    Uses sort_keys for deterministic output; flush=True ensures delivery before exceptions.
    try/except prevents emit errors from propagating into the render pipeline."""
    try:
        print(json.dumps(event, sort_keys=True), file=sys.stderr, flush=True)
    except Exception:
        pass


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
            f"_resolve_jit_sentinels: JIT ctx_config failed ({exc}); using empty config",
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
        # Story 10.65 AC-5: route through bmad_compile.io per the io-boundary rule;
        # strip the UTF-8 BOM manually (read_template preserves BOM).
        raw = io_mod.read_template(lockfile_path)
        lockfile_data = json.loads(raw.lstrip("\ufeff"))
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

    runnable: list[tuple[str, str, dict, str]] = []
    for (name, hash_) in unique_pairs:
        sentinel_key = (name, hash_)
        comp = next(
            (c for c in comps_list
             if isinstance(c, dict) and c.get("name") == name and c.get("props_hash") == hash_),
            None,
        )
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
        runnable.append((name, hash_, props_dict, installed_path))

    if len(runnable) <= 1:
        for (name, hash_, props_dict, installed_path) in runnable:
            sentinel_key = (name, hash_)
            try:
                _replacements[sentinel_key] = runner.run_jit(
                    installed_path, ctx_dict, props_dict, component_name=name
                )
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
    else:
        def _run_one(name: str, hash_: str, props_dict: dict, installed_path: str) -> tuple:
            sk = (name, hash_)
            try:
                return sk, runner.run_jit(
                    installed_path, ctx_dict, props_dict, component_name=name
                )
            except ComponentError as exc:
                fb = exc.render_error_fallback
                return sk, (fb if isinstance(fb, str) else f"<!-- BMAD-ERROR:{name} -->")
            except Exception as exc:
                _emit_jit_event({
                    "kind": "component_error", "component": name, "mode": "jit",
                    "props": props_dict, "exit_code": None, "stderr": str(exc),
                    "phase": "jit", "reason": "runner_unexpected_error",
                })
                return sk, f"<!-- BMAD-ERROR:{name} -->"

        with ThreadPoolExecutor(max_workers=_JIT_BATCH_WORKERS) as executor:
            future_map = {
                executor.submit(_run_one, n, h, p, ip): (n, h)
                for (n, h, p, ip) in runnable
            }
            for future in as_completed(future_map):
                key, val = future.result()
                _replacements[key] = val

    def _repl(m: re.Match) -> str:
        key = (m.group("name"), m.group("hash"))
        if key in _replacements:
            return _replacements[key]
        return f"<!-- BMAD-ERROR:{m.group('name')} -->"

    return _JIT_SENTINEL_RE.sub(_repl, content)
