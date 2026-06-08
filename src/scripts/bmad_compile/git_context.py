"""Git context builder for compile-mode components (Story 10.56).

Provides build_git_ctx() — called once per compile batch in engine.py and
attached as ctx_dict["git"]. Components receive ctx.git.branch, ctx.git.commit_sha,
etc. without shelling out themselves.
"""
from __future__ import annotations

import subprocess
import types


def build_git_ctx(cwd: str | None = None) -> types.SimpleNamespace | None:
    """Build ctx.git namespace by running git commands in `cwd`.

    Returns a SimpleNamespace with fields below, or None if `cwd` is not
    inside a git repo (git not found, not a repo, or any fatal error).

    Fields:
        branch (str | None): Current branch name; None in detached HEAD.
        commit_sha (str | None): Full 40-char hex SHA of HEAD.
        commit_short_sha (str | None): First 8 chars of commit_sha.
        is_dirty (bool): True if working tree has uncommitted changes.
        tag (str | None): Exact tag at HEAD, or None.
        repo_root (str | None): Absolute path to repository root.
    """
    # Call 1: SHA + repo root. If this fails, we're not in a repo — return None.
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD", "--show-toplevel"],
            capture_output=True, text=True, timeout=5, cwd=cwd,
        )
    except FileNotFoundError:
        return None  # git not on PATH
    except Exception:
        return None

    if r.returncode != 0:
        return None  # not a git repo

    lines = r.stdout.strip().splitlines()
    commit_sha = lines[0].strip() if len(lines) > 0 else None
    repo_root = lines[1].strip() if len(lines) > 1 else None
    commit_short_sha = commit_sha[:8] if commit_sha else None

    # Call 2: branch name
    branch = None
    try:
        rb = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=cwd,
        )
        if rb.returncode == 0:
            branch = rb.stdout.strip() or None
    except Exception:
        pass

    # Call 3: dirty flag
    is_dirty = False
    try:
        rs = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=5, cwd=cwd,
        )
        if rs.returncode == 0:
            is_dirty = bool(rs.stdout.strip())
    except Exception:
        pass

    # Call 4: exact tag at HEAD
    tag = None
    try:
        rt = subprocess.run(
            ["git", "describe", "--tags", "--exact-match", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=cwd,
        )
        if rt.returncode == 0:
            tag = rt.stdout.strip() or None
    except Exception:
        pass

    return types.SimpleNamespace(
        branch=branch,
        commit_sha=commit_sha,
        commit_short_sha=commit_short_sha,
        is_dirty=is_dirty,
        tag=tag,
        repo_root=repo_root,
    )
