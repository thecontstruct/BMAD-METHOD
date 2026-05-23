"""FR-12 byte-equivalence harness. Parametric per Arch §8.

Discovers every entry in test/fixtures/migration-goldens/, recompiles the
corresponding skill into a tmp install root, and asserts the compiled
SKILL.md SHA-256 matches the golden SHA-256.

Skills with signed-off whitespace deviations (Arch §14 ≤3 soft target,
SM-7 ≤10% hard cap per DN-3) are listed in migration_equivalence_exceptions.json
and matched against a whitespace-only diff assertion instead.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# component_runner.py uses absolute `from bmad_compile.errors` imports — ensure
# src/scripts is on sys.path BEFORE importing engine (which lazy-loads
# component_runner via compile_skill). Mirrors test_55b_hardening.py pattern.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "src" / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from src.scripts.bmad_compile import engine  # noqa: E402

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "migration-goldens"
EXCEPTIONS_PATH = Path(__file__).parent / "migration_equivalence_exceptions.json"


def _iter_goldens():
    """Yield (skill_basename, golden_path) for every committed golden."""
    if not FIXTURES_DIR.is_dir():
        return
    for skill_dir in sorted(FIXTURES_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        golden = skill_dir / "SKILL.md"
        if golden.is_file():
            yield skill_dir.name, golden


def _hash_text(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _find_skill_source_dir(skill_basename: str) -> Path | None:
    """Locate the migrated skill's source dir under src/{core,bmm}-skills/."""
    repo_root = Path(__file__).parent.parent.parent
    for module_root in (
        repo_root / "src" / "core-skills",
        repo_root / "src" / "bmm-skills",
    ):
        if not module_root.is_dir():
            continue
        for entry in module_root.rglob(skill_basename):
            if entry.is_dir() and (entry / f"{skill_basename}.template.md").is_file():
                return entry
    return None


@pytest.mark.parametrize(
    "skill_basename,golden_path",
    list(_iter_goldens()),
    ids=lambda x: x if isinstance(x, str) else "golden",
)
def test_migration_equivalence(skill_basename: str, golden_path: Path) -> None:
    """For every committed golden, recompile and assert byte-equivalence."""
    skill_dir = _find_skill_source_dir(skill_basename)
    if skill_dir is None:
        # ECH-7: skip when golden is committed before template is authored.
        pytest.skip(
            f"{skill_basename}: golden committed but template not yet authored — "
            f"skip until <skill>.template.md lands under src/{{core,bmm}}-skills/."
        )
    # ECH-4: locate tmp under repo to avoid Windows %TEMP% spaces.
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
        install_root = Path(tmp)
        repo_root = Path(__file__).parent.parent.parent
        # Replicate Story 10.0 installer's _copySharedRoot layout.
        if (repo_root / "src" / "_shared").is_dir():
            shutil.copytree(repo_root / "src" / "_shared", install_root / "_shared")
        (install_root / "_config").mkdir(exist_ok=True)
        module_name = "bmm" if "bmm-skills" in str(skill_dir) else "core"
        (install_root / module_name).mkdir(exist_ok=True)
        shutil.copytree(skill_dir, install_root / module_name / skill_basename)
        engine.compile_skill(
            install_root / module_name / skill_basename,
            install_root,
            target_ide=None,
            lockfile_root=install_root,
            override_root=None,
        )
        compiled = install_root / module_name / skill_basename / "SKILL.md"
        compiled_sha = _hash_text(compiled)
        golden_sha = _hash_text(golden_path)
        if compiled_sha == golden_sha:
            return  # byte-equivalent
        # Check exception list.
        exceptions = json.loads(EXCEPTIONS_PATH.read_text(encoding="utf-8"))
        if skill_basename in exceptions:
            _assert_whitespace_only_diff(golden_path, compiled, exceptions[skill_basename])
            return
        pytest.fail(
            f"{skill_basename}: byte-equivalence broken. "
            f"compiled={compiled_sha} golden={golden_sha}. "
            f"Add to migration_equivalence_exceptions.json with signed-off "
            f"whitespace-only deviation OR fix the regression."
        )


def _assert_whitespace_only_diff(golden: Path, compiled: Path, exception_record: dict) -> None:
    """Confirm the diff is whitespace-only (no semantic content changes).

    ECH-1: line-by-line normalization (rstrip + collapse consecutive blank lines).
    Preserves intra-token content verbatim so semantic changes still fail.
    """
    g = golden.read_text(encoding="utf-8")
    c = compiled.read_text(encoding="utf-8")

    def _norm(s: str) -> str:
        lines = [ln.rstrip() for ln in s.splitlines()]
        out: list[str] = []
        prev_blank = False
        for ln in lines:
            is_blank = ln == ""
            if is_blank and prev_blank:
                continue
            out.append(ln)
            prev_blank = is_blank
        return "\n".join(out).strip()

    assert _norm(g) == _norm(c), (
        f"{golden.name}: diff is NOT whitespace-only (intra-token or content "
        f"change detected). Exception entry must not apply; investigate."
    )
