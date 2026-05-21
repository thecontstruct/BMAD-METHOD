RENDER_MODE = "compile"

def render(ctx, **props):
    return f"greeting={props.get('greeting', 'none')}"
