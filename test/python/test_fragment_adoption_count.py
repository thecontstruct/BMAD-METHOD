"""Permanent fragment-adoption ratchet witness (Story 10.59 — DN-4=1).

Asserts a monotone-non-decreasing adoption count for two shared activation
fragments (`resolver-fallback.md`, `persistent-facts.md`) across the BMAD
template corpus, so future hand-roll regressions fail loud rather than
silently re-introducing inline drift after Story 10.59 closes the last
byte-equivalent adoption gap (bmad-prfaq).

Ratcheting baseline at story commit:
  - resolver-fallback adoption: 24 (= 23 pre-story + bmad-prfaq)
  - persistent-facts  adoption: 10 (= 9  pre-story + bmad-prfaq)

Story 10.60 ratchet update:
  - resolver-fallback: 24 → 23 (bmad-create-architecture.template.md dropped;
    bmad-architecture.template.md follows upstream design with inline abbreviated
    fallback, not the <<include>> fragment — legitimate structural divergence)
"""
from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOTS = (REPO_ROOT / "src" / "bmm-skills", REPO_ROOT / "src" / "core-skills")

RESOLVER_FALLBACK_INCLUDE_PREFIX = '<<include path="_shared/fragments/resolver-fallback.md"'
PERSISTENT_FACTS_INCLUDE_PREFIX = '<<include path="_shared/fragments/persistent-facts.md"'

PERSISTENT_FACTS_INLINE_BODY = (
    "Treat every entry in `{workflow.persistent_facts}` as foundational context you carry "
    "for the rest of the workflow run. Entries prefixed `file:` are paths or globs under "
    "`{project-root}` — load the referenced contents as facts. All other entries are "
    "facts verbatim."
)

BMAD_PRFAQ_TEMPLATE = (
    REPO_ROOT / "src" / "bmm-skills" / "1-analysis" / "bmad-prfaq" / "bmad-prfaq.template.md"
)


def _all_templates() -> list[Path]:
    paths: list[Path] = []
    for root in SRC_ROOTS:
        paths.extend(root.rglob("*.template.md"))
    return paths


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_e1_resolver_fallback_adoption_ratchet() -> None:
    """E-1: resolver-fallback include adoption >= 23 (Story 10.60 baseline).

    Dropped from 24 to 23: bmad-create-architecture.template.md removed (Story 10.60
    Path 2); replacement bmad-architecture.template.md uses upstream's abbreviated
    inline fallback, not the <<include>> fragment.
    """
    hits = [p for p in _all_templates() if RESOLVER_FALLBACK_INCLUDE_PREFIX in _read(p)]
    assert len(hits) >= 23, (
        f"Resolver-fallback adoption regressed: found {len(hits)} templates including "
        f"resolver-fallback.md, expected >= 23. Did a template hand-roll the Step 1 "
        f"fallback inline instead of using the include?"
    )


def test_e2_persistent_facts_adoption_ratchet() -> None:
    """E-2: persistent-facts include adoption >= 9 (Story 10.60 baseline).

    Dropped from 10 to 9: bmad-create-architecture.template.md removed (Story 10.60
    Path 2); replacement bmad-architecture.template.md uses upstream's abbreviated
    inline persistent_facts reference, not the <<include>> fragment.
    """
    hits = [p for p in _all_templates() if PERSISTENT_FACTS_INCLUDE_PREFIX in _read(p)]
    assert len(hits) >= 9, (
        f"Persistent-facts adoption regressed: found {len(hits)} templates including "
        f"persistent-facts.md, expected >= 9. Did a template hand-roll the Step 3 "
        f"body inline instead of using the include?"
    )


def test_e3_inline_persistent_facts_only_with_include() -> None:
    """E-3: every template that inlines the persistent-facts body must ALSO carry
    the persistent-facts include (i.e. it's a doc-string elsewhere, not Step 3 hand-roll)."""
    offenders: list[str] = []
    for path in _all_templates():
        body = _read(path)
        if PERSISTENT_FACTS_INLINE_BODY in body and PERSISTENT_FACTS_INCLUDE_PREFIX not in body:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert not offenders, (
        f"Templates hand-roll the persistent-facts inline body without the include "
        f"(should use `<<include path=\"_shared/fragments/persistent-facts.md\">>` "
        f"at Step 3): {offenders}"
    )


def test_e4_bmad_prfaq_carries_both_includes() -> None:
    """E-4: bmad-prfaq.template.md carries both new includes (positive assertion of
    this story's two edits)."""
    body = _read(BMAD_PRFAQ_TEMPLATE)
    assert '<<include path="_shared/fragments/resolver-fallback.md" skill_kind="workflow">>' in body, (
        "bmad-prfaq.template.md is missing the resolver-fallback include — Story 10.59 Edit 1 regressed."
    )
    assert '<<include path="_shared/fragments/persistent-facts.md">>' in body, (
        "bmad-prfaq.template.md is missing the persistent-facts include — Story 10.59 Edit 2 regressed."
    )


# ---------------------------------------------------------------------------
# Story 10.61 — Sub-agent activation fragment adoption ratchet
# ---------------------------------------------------------------------------

_SHARED_FRAGMENTS = REPO_ROOT / "src" / "_shared" / "fragments"

_SUB_AGENT_INCLUDE_PREFIX = '<<include path="_shared/fragments/sub-agent-activation.template.md"'

_IN_SCOPE_CONSUMERS: list[Path] = [
    REPO_ROOT / "src" / "bmm-skills" / "4-implementation" / "bmad-quick-dev" / "step-03-implement.template.md",
    REPO_ROOT / "src" / "bmm-skills" / "4-implementation" / "bmad-quick-dev" / "step-04-review.template.md",
    REPO_ROOT / "src" / "bmm-skills" / "4-implementation" / "bmad-quick-dev" / "step-oneshot.template.md",
    REPO_ROOT / "src" / "bmm-skills" / "4-implementation" / "bmad-code-review" / "step-02-review.template.md",
]

_OLD_BOILERPLATE_SNIPPETS: list[str] = [
    "If no sub-agents are available, implement directly.",
    "If no sub-agents are available, generate three review prompt files",
    "If no sub-agents are available, write the changed files to a review prompt file",
    "If subagents are not available, generate prompt files",
]


class TestSubAgentActivationFragment:
    """Story 10.61 — sub-agent-activation fragment existence and adoption."""

    def test_fragment_files_exist(self) -> None:
        for suffix in ("", ".claudecode", ".cursor"):
            p = _SHARED_FRAGMENTS / f"sub-agent-activation{suffix}.template.md"
            assert p.exists(), f"Fragment missing: {p.relative_to(REPO_ROOT)}"

    def test_all_consumers_carry_include(self) -> None:
        missing = [
            str(p.relative_to(REPO_ROOT))
            for p in _IN_SCOPE_CONSUMERS
            if _SUB_AGENT_INCLUDE_PREFIX not in _read(p)
        ]
        assert not missing, (
            f"Consumers missing sub-agent-activation include: {missing}. "
            "Each must contain `<<include path=\"_shared/fragments/sub-agent-activation.template.md\" ...>>`."
        )

    def test_no_consumer_has_old_boilerplate(self) -> None:
        offenders: list[str] = []
        for p in _IN_SCOPE_CONSUMERS:
            body = _read(p)
            for snippet in _OLD_BOILERPLATE_SNIPPETS:
                if snippet in body:
                    offenders.append(f"{p.relative_to(REPO_ROOT)}: found {snippet!r}")
        assert not offenders, (
            f"Consumers still contain hand-rolled sub-agent boilerplate: {offenders}"
        )
