"""Regenerate the frozen bmad-help SKILL.md baseline from the template.

This helper is the **only** supported way to intentionally update the
bmad-help keep-contract baseline. The normal flow is:

1. Edit src/core-skills/bmad-help/bmad-help.template.md (the template).
2. Run this script: python3 BMAD-METHOD/tools/regenerate-bmad-help-baseline.py
3. The script compiles the template via engine.compile_skill and overwrites
   src/core-skills/bmad-help/SKILL.md with the fresh compiled output.
4. Commit both the template change AND the regenerated baseline in the same PR.
5. CI (npm run test:python via AC 5) verifies the keep-contract holds.

This script is single-purpose and stdlib-only (architecture NFR-S6). It does
not generalize to other skills; Story 4.1's `bmad compile <skill>` will replace
the one-off helpers when the CLI layer ships.

See Story 2.2 AC 6 and src/core-skills/bmad-help/README.md for full rationale.
"""

import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SKILL_DIR = _REPO_ROOT / "src" / "core-skills" / "bmad-help"
_BASELINE = _SKILL_DIR / "SKILL.md"

sys.path.insert(0, str(_REPO_ROOT / "src" / "scripts"))

from bmad_compile import engine  # noqa: E402


def main() -> int:
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            engine.compile_skill(
                skill_dir=_SKILL_DIR,
                install_dir=tmp_path,
                target_ide=None,
                lockfile_root=tmp_path,
            )
            # With lockfile_root set, output is at <tmp>/<module>/<skill>/SKILL.md
            # where module = skill_dir.parent.name = "core-skills"
            compiled = tmp_path / "core-skills" / "bmad-help" / "SKILL.md"
            compiled_bytes = compiled.read_bytes()
    except Exception as exc:
        print(f"regeneration failed: {exc}", file=sys.stderr)
        return 1

    _BASELINE.write_bytes(compiled_bytes)
    print(f"regenerated {_BASELINE} ({len(compiled_bytes)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
