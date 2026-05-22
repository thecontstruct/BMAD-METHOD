RENDER_MODE = "compile"
RENDER_ERROR_FALLBACK = "*IDE-specific notes unavailable*"


def render(ctx, **props):
    """Return IDE-specific guidance based on ctx.config["core"]["ide"].

    Convention: users add [core]\nide = "cursor"  (or "claude-code", "vscode")
    to _bmad/config.toml. If absent, generic guidance is returned.

    This demonstrates the core conditional-rendering pattern:
    Python if/elif in render() body, NOT JSX-style <Component if={...} />.

    Returns:
        str: markdown-safe guidance paragraph (single line, no trailing newline)
    """
    ide = ctx.config.get("core", {}).get("ide", "generic")
    if ide == "cursor":
        return (
            "**Cursor:** Use ⌘K (Mac) / Ctrl+K (Win) for inline edits. "
            "Use Composer (⌘I) for multi-file changes."
        )
    elif ide in ("claude-code", "claudecode"):
        return (
            "**Claude Code:** Type your intent at the `$` prompt. "
            "Use `--continue` to resume a previous session."
        )
    elif ide == "vscode":
        return (
            "**VS Code:** Open the GitHub Copilot Chat panel (Ctrl+Alt+I). "
            "Use inline chat (Ctrl+I) for code-scoped questions."
        )
    else:
        return (
            "**IDE:** Open your AI assistant's chat panel and describe your intent. "
            "Paste context from the spec or error message as needed."
        )
