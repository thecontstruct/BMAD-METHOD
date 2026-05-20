RENDER_MODE = "jit"
RENDER_ERROR_FALLBACK = "fallback"


def render(ctx, **props):
    return f"Sprint weeks: {props.get('weeks_left', '?')}"
