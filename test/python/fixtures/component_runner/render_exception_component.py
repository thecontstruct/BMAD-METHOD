RENDER_ERROR_FALLBACK = "render exception fallback"

def render(ctx, **props):
    raise ValueError("deliberate render error")
