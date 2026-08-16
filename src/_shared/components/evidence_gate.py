"""Render an evidence-backed finding contract for an in-progress review.

This is a bounded, single-consumer pilot for ``bmad-code-review``.  It does
not issue a review verdict: triage owns final severity, routing, and outcome.
"""

RENDER_MODE = "compile"
RENDER_ERROR_FALLBACK = "*evidence gate unavailable*"


def _csv(value: object, default: str) -> list[str]:
    return [item.strip() for item in str(value or default).split(",") if item.strip()]


def render(ctx, **props):
    subject = str(props.get("subject", "the submitted work")).strip()
    dimensions = _csv(props.get("dimensions"), "correctness,completeness,operability")
    evidence = _csv(props.get("evidence"), "source location,observed behavior")
    deletion_check = str(props.get("deletion_check", "optional")).strip().lower()

    lines = [
        f"## Evidence Gate — {subject}",
        "",
        "Before triage, do not infer conclusions from plausible prose. Inspect the collected review context and attach evidence to every material finding.",
        "",
        "### Review dimensions",
        "",
        *(f"- {dimension}" for dimension in dimensions),
        "",
        "### Finding contract",
        "",
        "Preserve each layer's raw finding in the triage-compatible shape:",
        "- `source` — originating review-layer `id`",
        "- `title` — one-line claim",
        "- `detail` — the evidence, impact, and smallest credible remediation",
        "- `location` — file and line reference when available",
        "",
        f"Evidence in `detail` must identify: {'; '.join(evidence)}.",
        "Do not assign final severity, bucket, or a PASS/FAIL verdict here; the next step verifies context and makes those decisions.",
    ]
    if deletion_check == "required":
        lines.extend([
            "",
            "### Simplification pass",
            "",
            "Explicitly test whether any part can be removed, merged, or made smaller without violating the stated contract. Record a resulting concern using the same finding shape.",
        ])
    lines.extend(["", "Continue to triage with the collected findings."])
    return "\n".join(lines)
