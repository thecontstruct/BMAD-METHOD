RENDER_MODE = "jit"
RENDER_ERROR_FALLBACK = "*project context unavailable*"


def render(ctx, **props):
    """Return project name + current git branch for session context.

    Reads project_name from ctx.config["core"]["project_name"].
    Reads git branch via subprocess — trusted-code premise; read-only.
    Falls back gracefully if git unavailable or errors.

    Returns:
        str: "Project: <name> | Branch: <branch>" or "Project: <name>"
    """
    import subprocess  # subprocess: git read-only — trusted-code premise (Epic 9)
    project = ctx.config.get("core", {}).get("project_name", "unknown")
    branch = None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
    except Exception:
        pass  # git unavailable, detached HEAD, or timeout — degrade gracefully

    if branch:
        return f"Project: {project} | Branch: {branch}"
    return f"Project: {project}"
