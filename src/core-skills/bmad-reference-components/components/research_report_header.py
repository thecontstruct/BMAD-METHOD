RENDER_MODE = "compile"
RENDER_ERROR_FALLBACK = "*research report header unavailable*"


def render(ctx, **props):
    """Return the research report document scaffold verbatim.

    This compile-mode component embeds the standard research-report frontmatter
    and heading structure shared across all 3 research skills. Demonstrates the
    compile-mode pattern for purely static content (no runtime data needed).

    Note: {{...}} tokens are BMAD template variables resolved by the skill
    workflow at runtime — they are literal string content of this component.

    Returns:
        str: 30-line research document scaffold
    """
    return (
        "---\n"
        "stepsCompleted: []\n"
        "inputDocuments: []\n"
        "workflowType: 'research'\n"
        "lastStep: 1\n"
        "research_type: '{{research_type}}'\n"
        "research_topic: '{{research_topic}}'\n"
        "research_goals: '{{research_goals}}'\n"
        "user_name: '{{user_name}}'\n"
        "date: '{{date}}'\n"
        "web_research_enabled: true\n"
        "source_verification: true\n"
        "---\n"
        "\n"
        "# Research Report: {{research_type}}\n"
        "\n"
        "**Date:** {{date}}\n"
        "**Author:** {{user_name}}\n"
        "**Research Type:** {{research_type}}\n"
        "\n"
        "---\n"
        "\n"
        "## Research Overview\n"
        "\n"
        "[Research overview and methodology will be appended here]\n"
        "\n"
        "---\n"
        "\n"
        "<!-- Content will be appended sequentially through research workflow steps -->"
    )
