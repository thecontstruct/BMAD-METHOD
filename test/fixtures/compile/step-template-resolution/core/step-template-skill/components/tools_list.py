RENDER_MODE = "compile"


def render(ctx, **props):
    tools = props.get("tools", "all")
    return f"tools: {tools}"
