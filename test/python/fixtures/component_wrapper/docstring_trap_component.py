"""
RENDER_ERROR_FALLBACK = "fake_fallback_in_docstring"
This assignment is inside a docstring. Tokenize-strip must prevent a false match.
"""
# No real RENDER_ERROR_FALLBACK at module level — _FALLBACK_RE finds nothing after strip.

def render(ctx, **props):
    raise RuntimeError("deliberate error to trigger fallback path")
