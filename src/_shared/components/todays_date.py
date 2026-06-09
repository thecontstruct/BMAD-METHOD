RENDER_MODE = "jit"
RENDER_ERROR_FALLBACK = "today"


def render(ctx, **props):
    """Return current date formatted via fmt prop.

    Props:
        fmt (str): strftime format string. Default: "%Y-%m-%d"

    Examples:
        <TodaysDate />                     → "2026-05-21"
        <TodaysDate fmt="%B %d, %Y" />     → "May 21, 2026"

    Returns:
        str: formatted date string
    """
    import datetime
    fmt = props.get("fmt", "%Y-%m-%d")
    return datetime.date.today().strftime(fmt)
