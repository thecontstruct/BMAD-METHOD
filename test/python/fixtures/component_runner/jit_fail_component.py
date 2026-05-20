RENDER_MODE = "jit"
RENDER_ERROR_FALLBACK = "jit fb"


def render(ctx, **props):
    raise ValueError("deliberate jit error")
