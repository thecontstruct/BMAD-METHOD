"""ComponentRunner — subprocess lifecycle manager for component invocations."""
from __future__ import annotations

import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path  # pragma: allow-raw-io
from typing import Any, Callable

from bmad_compile.errors import (
    ComponentBatchError,
    ComponentError,
    ComponentPropError,
    ComponentTimeoutError,
)

_COMPILE_BATCH_WORKERS: int = 4
_DEFAULT_WRAPPER_PATH = Path(__file__).parent / "component_wrapper.py"

_POPEN_KWARGS: dict[str, Any] = {}
if sys.platform == "win32":
    _POPEN_KWARGS["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
else:
    _POPEN_KWARGS["start_new_session"] = True


def _kill_process_group(proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
    """Kill subprocess process group; cross-platform."""
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
            capture_output=True,
        )
    else:
        import os
        import signal
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except OSError:
            pass  # process already gone (ProcessLookupError) or permission denied (PermissionError)


def _spawn_one(
    component_path: str,
    ctx_dict: dict,
    props: dict,
    *,
    component_name: str,
    wrapper_path: Path,
    timeout_secs: float,
    emit_fn: Callable[[dict], None] | None = None,
) -> str:
    """Spawn one component subprocess. Returns render() output string.

    Raises:
        ComponentPropError:    props fail JSON serialization (pre-spawn; emits component_prop_error)
        ComponentTimeoutError: timeout exceeded (process group killed)
        ComponentError:        non-zero exit, protocol error, or ok=false envelope
    """
    try:
        stdin_bytes = json.dumps({"ctx": ctx_dict, "props": props}).encode("utf-8")
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

    proc = subprocess.Popen(  # pragma: allow-raw-io
        [sys.executable, str(wrapper_path), component_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        **_POPEN_KWARGS,
    )
    try:
        stdout_bytes, stderr_bytes = proc.communicate(
            input=stdin_bytes, timeout=timeout_secs
        )
    except subprocess.TimeoutExpired:
        _kill_process_group(proc)
        try:
            proc.communicate()  # drain pipes; prevents deadlock on full pipe buffers
        except Exception:
            pass
        raise ComponentTimeoutError(
            f"component timed out after {timeout_secs}s",
            component_name=component_name,
        ) from None

    stderr_str = stderr_bytes.decode("utf-8", errors="replace")

    try:
        raw = stdout_bytes.decode("utf-8", errors="replace")
        envelope = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        raise ComponentError(
            f"wrapper produced non-JSON stdout (possible crash); stderr={stderr_str!r}",
            component_name=component_name,
            exit_code=proc.returncode,
            stderr=stderr_str,
        )

    if not isinstance(envelope, dict):
        raise ComponentError(
            f"wrapper stdout is not a JSON object (protocol error); got {type(envelope).__name__}",
            component_name=component_name,
            exit_code=proc.returncode,
            stderr=stderr_str,
        )

    if "ok" not in envelope:
        raise ComponentError(
            "wrapper stdout missing 'ok' field (protocol error)",
            component_name=component_name,
            exit_code=proc.returncode,
            stderr=stderr_str,
        )

    if not envelope["ok"]:
        raise ComponentError(
            envelope.get("error", "unknown error"),
            component_name=component_name,
            exit_code=proc.returncode,
            stderr=stderr_str,
            render_error_fallback=envelope.get("render_error_fallback"),
        )

    if "output" not in envelope:
        raise ComponentError(
            "wrapper stdout ok=true but 'output' field missing (protocol error)",
            component_name=component_name,
            exit_code=proc.returncode,
            stderr=stderr_str,
        )

    return str(envelope["output"])  # str() coercion is intentional; see AC-4


class ComponentRunner:
    """Subprocess lifecycle manager for component invocations.

    Single implementation serving compile-time (engine.py) and JIT-time
    (render.py) paths — satisfies PRD-OQ-I.
    """

    def __init__(
        self,
        emit_fn: Callable[[dict], None] | None = None,
        _wrapper_path: Path | None = None,
    ) -> None:
        self._emit_fn = emit_fn or (lambda _event: None)
        self._wrapper_path = _wrapper_path or _DEFAULT_WRAPPER_PATH

    def _emit(self, event: dict) -> None:
        try:
            self._emit_fn(event)
        except Exception:
            pass  # emit_fn errors MUST NOT propagate into the dispatch path

    def run_compile_batch(
        self,
        invocations: list[Any],
        ctx_dict: dict,
        timeout_seconds: float = 10.0,
    ) -> dict[int, str]:
        if not invocations:
            return {}

        results: dict[int, str] = {}
        errors: list[tuple[int, ComponentError]] = []

        with ThreadPoolExecutor(max_workers=_COMPILE_BATCH_WORKERS) as executor:
            future_to_inv = {
                executor.submit(
                    _spawn_one,
                    inv.component_abs_path,
                    ctx_dict,
                    dict(inv.original.props),
                    component_name=inv.original.name,
                    wrapper_path=self._wrapper_path,
                    timeout_secs=timeout_seconds,
                    emit_fn=self._emit,
                ): inv
                for inv in invocations
            }
            for future in as_completed(future_to_inv):
                inv = future_to_inv[future]
                props_dict = dict(inv.original.props)
                try:
                    output = future.result()
                    results[inv.token_index] = output
                except ComponentError as exc:
                    exc.mode = "compile"
                    exc.props = props_dict
                    # ComponentPropError already emitted component_prop_error inside _spawn_one
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
        timeout_seconds: float = 10.0,
        component_name: str = "",
    ) -> str:
        """Run one JIT-mode component synchronously.

        component_name: PascalCase name for NDJSON events; pass empty string if unknown.
        Raises ComponentError (with render_error_fallback set) on any failure.
        """
        try:
            return _spawn_one(
                component_path,
                ctx_dict,
                props,
                component_name=component_name,
                wrapper_path=self._wrapper_path,
                timeout_secs=timeout_seconds,
                emit_fn=self._emit,
            )
        except ComponentError as exc:
            exc.mode = "jit"
            if exc.props is None:
                exc.props = props
            # ComponentPropError already emitted component_prop_error inside _spawn_one
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
    """Test double: returns pre-configured results without spawning subprocesses."""

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
