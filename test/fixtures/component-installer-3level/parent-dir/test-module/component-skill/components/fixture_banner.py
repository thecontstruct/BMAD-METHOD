RENDER_MODE = "jit"
RENDER_ERROR_FALLBACK = "banner-fallback"


def render(ctx, **props):
    return f"[FixtureBanner: prop={props.get('prop', 'none')}]"
