RENDER_ERROR_FALLBACK = "import fallback"

raise ImportError("boom")

def render(ctx, **props):
    return "never reached"
