RENDER_MODE = "jit"
RENDER_ERROR_FALLBACK = ""


def render(ctx, **props):
    """Resolve a BMAD-domain artifact path or sprint-status key.

    Props:
        kind: 'story' | 'sprint-status' | 'epic-key' | 'retro' |
              'prd' | 'epics' | 'architecture' | 'ux'
        epic: str (required for 'story','epic-key','retro')
        story: str (required for 'story' when story_key absent)
        story_key: str (alternative to epic+story for kind='story';
                        when both provided, story_key wins — see H-3)
        date: str (optional, for 'retro'; passes through unresolved
                  {date} placeholder when omitted)

    Returns:
        str — relative path or glob pattern; sprint-status key for kind='epic-key';
              "" on missing-required-prop or unknown kind (matches RENDER_ERROR_FALLBACK).

    Contract notes:
        - implementation_artifacts and planning_artifacts pulled from
          ctx.config; fall back to default paths if absent.
        - Collision-safety for "1-1 vs 1-10": when called with epic='1'
          + story='1', glob returns "{ia}/1-1-*.md" — NOT "{ia}/1-1*-*.md".
          This matches the canonical reasoning in pinned bmad-quick-dev
          /step-01-clarify-and-route.md so post-pin-lift consumer migration
          is a no-semantic-change refactor.
        - Subsumes hand-rolled call sites: bmad-create-story.template.md:39,228;
          bmad-dev-story.template.md:149; bmad-retrospective.template.md:200,
          1352,1356,1362-1364; bmad-code-review/steps/step-01-gather-context.md:
          38-39; bmad-quick-dev/step-01-clarify-and-route.md:42-67 (pinned ref).
        - Consumer-side template migration tracked as DN-FOLLOWUP-I — NOT in
          Story 10.58 scope. Component sits awaiting adoption like
          _shared/fragments/ did before all migrators adopted them.

    See DN-8 criteria #4 (render-time primitive) and #6 (cross-cutting domain).
    """
    config = getattr(ctx, "config", None) or {}
    ia = config.get("implementation_artifacts", "_bmad-output/implementation-artifacts")
    pa = config.get("planning_artifacts", "_bmad-output/planning-artifacts")
    kind = props.get("kind", "")

    # Truthy checks (not `in props`) so explicit None / "" props degrade to the
    # missing-prop branch instead of interpolating "None" / "" into the path.
    # R3 acceptance audit promoted R1.2/R2-1 — silent string corruption when a
    # template variable resolves to None or empty would emit e.g. "{ia}/None.md".
    if kind == "story":
        story_key = props.get("story_key")
        if story_key:
            return f"{ia}/{story_key}.md"
        epic = props.get("epic")
        story = props.get("story")
        if epic and story:
            return f"{ia}/{epic}-{story}-*.md"
        return ""  # missing required prop
    if kind == "sprint-status":
        return f"{ia}/sprint-status.yaml"
    if kind == "epic-key":
        epic = props.get("epic")
        if not epic:
            return ""
        return f"epic-{epic}"
    if kind == "retro":
        epic = props.get("epic")
        if not epic:
            return ""
        date = props.get("date") or "{date}"
        return f"{ia}/epic-{epic}-retro-{date}.md"
    if kind in ("prd", "epics", "architecture", "ux"):
        return f"{pa}/*{kind}*.md"
    return ""  # unknown kind
