#!/usr/bin/env python3
"""ci-hash.py — compile all migrated skills and record hashes per platform.

Arguments: --output-file <path>

Output JSON schema:
{
  "runner_os":      str,   # RUNNER_OS env var or sys.platform
  "runner_arch":    str,   # RUNNER_ARCH env var or platform.machine()
  "python_version": str,   # major.minor.micro
  "skills": {
    "<module>/<skill>": "<64-char lowercase hex sha256>",
    ...
  }
}

Discovery rule (R3-A1): a directory <dir>/ is a migrated-skill candidate iff
it contains a file named exactly <dir>.template.md. Walks src/ across both
core-skills/ and bmm-skills/ (and any future module) subtrees.

Uses compile.py --install-phase as a subprocess (sys.executable) so the same
Python binary is used across platforms — critical for correct import paths.
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]  # BMAD-METHOD/
_COMPILE_PY = _REPO_ROOT / "src" / "scripts" / "compile.py"
_SRC = _REPO_ROOT / "src"


def _read_module_code(module_dir: Path) -> str | None:
    """Return the 'code:' field from module.yaml, or None if absent."""
    module_yaml = module_dir / "module.yaml"
    if not module_yaml.is_file():
        return None
    for line in module_yaml.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("code:"):
            return stripped[5:].strip().strip('"').strip("'")
    return None


def _discover_migrated_skills() -> list[tuple[str, Path]]:
    """Return (module_code, skill_dir) pairs for all migrated skills in src/."""
    results: list[tuple[str, Path]] = []
    for module_dir in sorted(_SRC.iterdir()):
        if not module_dir.is_dir():
            continue
        module_code = _read_module_code(module_dir)
        if module_code is None:
            continue
        for skill_dir in sorted(module_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            if (skill_dir / f"{skill_dir.name}.template.md").is_file():
                results.append((module_code, skill_dir))
    return results


def _compile_and_hash(module_code: str, skill_dir: Path) -> tuple[str, str]:
    """Compile skill in a fresh tempdir. Returns (skill_key, compiled_hash)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        install_seed = tmp_path / "install_seed"
        dest = install_seed / module_code / skill_dir.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(skill_dir), str(dest))
        (install_seed / "custom").mkdir(exist_ok=True)

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(_COMPILE_PY),
                    "--install-phase",
                    "--install-dir",
                    str(install_seed),
                ],
                capture_output=True,
                text=True,
                cwd=str(_REPO_ROOT),
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            sys.stderr.write(
                f"ci-hash: compile timed out after 120s for {module_code}/{skill_dir.name}\n"
            )
            sys.exit(1)

        if result.returncode != 0:
            sys.stderr.write(f"ci-hash: compile failed for {module_code}/{skill_dir.name}:\n")
            sys.stderr.write(result.stdout)
            sys.stderr.write(result.stderr)
            sys.exit(1)

        # Extract skill key from NDJSON stdout
        skill_key: str | None = None
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("kind") == "skill" and event.get("status") == "ok":
                skill_key = event["skill"]

        if skill_key is None:
            sys.stderr.write(
                f"ci-hash: no skill event found for {module_code}/{skill_dir.name}\n"
            )
            sys.stderr.write(result.stdout)
            sys.exit(1)

        # Read compiled_hash from lockfile
        lockfile = install_seed / "_config" / "bmad.lock"
        lf_data = json.loads(lockfile.read_text(encoding="utf-8"))
        skill_basename = skill_dir.name
        for entry in lf_data.get("entries", []):
            if entry.get("skill") == skill_basename:
                return skill_key, entry["compiled_hash"]

        sys.stderr.write(
            f"ci-hash: compiled_hash not found in lockfile for skill={skill_basename}\n"
        )
        sys.exit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description="Compile migrated skills and record hashes.")
    ap.add_argument("--output-file", required=True, help="Path to write hashes JSON.")
    args = ap.parse_args()

    runner_os = os.environ.get("RUNNER_OS", sys.platform)
    runner_arch = os.environ.get("RUNNER_ARCH", platform.machine())
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    skills = _discover_migrated_skills()
    if not skills:
        sys.stderr.write("ci-hash: no migrated skills discovered under src/\n")
        sys.exit(1)

    hashes: dict[str, str] = {}
    for module_code, skill_dir in skills:
        skill_key, compiled_hash = _compile_and_hash(module_code, skill_dir)
        hashes[skill_key] = compiled_hash

    output = {
        "runner_os": runner_os,
        "runner_arch": runner_arch,
        "python_version": python_version,
        "skills": hashes,
    }

    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")

    n = len(hashes)
    print(f"ci-hash: compiled {n} skill(s) on {runner_os}/{runner_arch}. Hashes written to {args.output_file}.")


if __name__ == "__main__":
    main()
