RENDER_MODE = "compile"

def render(ctx, **props):
    return f"skill={ctx.skill_id} mode={ctx.render_mode}"
