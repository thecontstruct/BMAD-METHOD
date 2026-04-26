"""Layer 5 — IDE variant selection (Story 1.2 minimal stub).

Given a directory of sibling template candidates, pick the one matching a
requested IDE target. Variant suffixes frozen for v1: `.cursor.template.md`
and `.claudecode.template.md`. Universal (no-suffix) form: `.template.md`.

Scope of Story 1.2:
- `select_variant()` returns a single `PurePosixPath` or `None`.
- `target_ide=None` or an unrecognized value → fall back to universal.
- No multi-IDE batch logic, no `--tools` CLI flag, no
  `<Include variant="...">` provenance — those land in Story 1.4 alongside
  the `MISSING_FRAGMENT` path for "IDE requested, no variant and no
  universal present".

Pathlib boundary: imports `PurePosixPath` via the re-export on `io.py`;
the grep in `test_io_boundary.py` never sees the `pathlib` token in this
module's source.
"""

from __future__ import annotations

import re

from .io import PurePosixPath

# Frozen for v1. New IDE targets add to this tuple and grow their own
# `<name>.<ide>.template.md` suffix.
KNOWN_IDES: tuple[str, ...] = ("cursor", "claudecode")
# Public so sibling layers (resolver.py) can reuse the single definition.
TEMPLATE_SUFFIX = ".template.md"

# Detects `<base>.<ide-token>.template.md` filenames regardless of
# KNOWN_IDES membership. Used by `_is_universal` to classify
# universality by SHAPE (not by allowlist membership), and by
# engine.compile_skill's MissingFragmentError hint to enumerate
# detected variants for any IDE-shape suffix.
_IDE_SUFFIX_RE = re.compile(r"^(?P<base>.+)\.(?P<ide>[a-zA-Z0-9_-]+)\.template\.md$")


def _ide_suffix(ide: str) -> str:
    return f".{ide}{TEMPLATE_SUFFIX}"


def _is_universal(name: str) -> bool:
    if not name.endswith(TEMPLATE_SUFFIX):
        return False
    return _IDE_SUFFIX_RE.match(name) is None


def select_variant(
    candidates: list[PurePosixPath],
    target_ide: str | None,
) -> PurePosixPath | None:
    """Pick one candidate per Story 1.2 AC 11.

    - `target_ide=None` → the universal candidate, else `None`.
    - `target_ide="cursor"` or `"claudecode"` → the matching variant if
      present; otherwise the universal candidate; otherwise `None`.
    - Unrecognized `target_ide` → the universal candidate, else `None`.
    - Empty `candidates` → `None`.

    The caller is responsible for error wording (`MISSING_FRAGMENT` etc.)
    when this returns `None`.
    """
    if not candidates:
        return None

    if target_ide in KNOWN_IDES:
        wanted_suffix = _ide_suffix(target_ide)
        for candidate in candidates:
            if candidate.name.endswith(wanted_suffix):
                return candidate
        # Fall through to universal fallback.

    for candidate in candidates:
        if _is_universal(candidate.name):
            return candidate

    return None
