"""Story 7.2 — End-to-End Customization Lifecycle Integration Test.

Exercises the full customization lifecycle as a single 9-step sequence:

    1. Fresh install (compile --install-phase) writes lock + compiled SKILL.md.
    2. Simulated bmad-customize session writes a prose-fragment override via
       writer.write_override (real handler, not mocked). Emits propose_diff_review.
    2.5. Non-diff positional compile persists the override record into bmad.lock
       (DN-PA-1 — write_override's compile --diff restores the lockfile in finally).
    3. Verify diff event from write_override is non-empty and references the
       overridden fragment (preflight.md = Fragment X).
    4. Simulate upstream change: mutate Fragment Y (when-this-skill-cant-help.md,
       drift trigger) and Fragment X base (silent — lineage prerequisite).
    5. upgrade --dry-run reports drift on Fragment Y, exit 0.
    6. Bare upgrade halts with exit 3 + stderr drift message.
    7. upgrade --yes resolves: forces compile, lockfile updated, lineage written.
    8. Bare upgrade after resolution exits 0, no drift.
    9. bmad.lock lineage[] non-empty for Fragment X with full schema.

The test crosses real process boundaries — it invokes compile.py and upgrade.py
via subprocess (no MockCompiler). One stateful test method; AC-10 fail-fast
naming via _assert_step().

Per Story 7.2 spec resolutions:
    OQ-1=A: Python test runner. OQ-2=A: direct writer.write_override import.
    OQ-3=A: in-test mutation of tempdir copies. OQ-4: exit 3 confirmed.
    OQ-5: lineage schema {base_hash, bmad_version, override_hash} confirmed.
    DN-R1-1..4 / DN-R2-1..3 / DN-PA-1: see spec Review Findings section.

R1 Sonnet review patches applied (2026-05-08; Phil's resolutions):
    BH-1/ECH-5: sys.path manipulation moved into setUp/tearDown (save+restore).
    BH-2/ECH-3: every subprocess.run wrapped with timeout=120s + TimeoutExpired guard.
    BH-3:       run_fn closure pops 'cwd' from kwargs before injection.
    ECH-1/BH-5: TemporaryDirectory(ignore_cleanup_errors=True) — Windows file-lock safe.
    ECH-2:      chmod fragment files writable before mutation (Windows read-only guard).
    BH-6:       Step 8 success assertion strengthened (non-empty output OR explicit exit 0).
    BH-8/ECH-8: Step 3 diff assertion checks for unified-diff hunk markers, not just path.
    DN-R1-2=B:  Hash contract documented inline (lockfile.py uses io.hash_text(text.encode())).

R2 Opus review patches applied (2026-05-08; Phil's resolutions):
    R2-BH-1:    _e2e_run_fn wraps subprocess.run in try/except TimeoutExpired.
    R2-BH-2:    chmod loop dropped is_file() guard (covers Linux read-only-dir case).
    R2-BH-3 + DN-R2-6=A: Step 5 / Step 8 drift assertions tightened to structured
                'when-this-skill' anchor; loose 'drift' substring dropped.
    R2-ECH-1:   AC-7 base_hash check uses isinstance(str) + len==64 (sha256 hex).
    R2-ECH-5:   Fragment lookups use endswith() not substring `in` (.bak match defense).
    R2-ECH-7:   Step 3 iterates all diff_events with any(...), not just [0].
    R2-ECH-12:  _run_subprocess TimeoutExpired AssertionError includes partial stdout.
    R2-AA-1:    Removed unused `import os`.
    DN-R2-2=A:  Hash-contract comment trimmed (drops the inaccurate
                "disk bytes equal text.encode() on all platforms" claim — Windows CRLF
                translation in write_text means disk bytes can differ; the test depends
                on in-memory hashing only, which is correct).
    DN-R2-5=B:  _e2e_run_fn timeout uses max-with-floor instead of setdefault — caller
                cannot narrow the test's bound, but can extend it.
    DN-R2-7=A:  Explicit `text.encode("utf-8")` (was implicit default).

Story 7.3b retirement (2026-05-09):
    The DN-R2-2=A workaround (run_fn-side --install-dir injection) is retired.
    write_override in writer.py now passes --install-dir directly to
    compile.py --diff, matching the 7.3a fix in discovery.py / routing.py /
    drafting.py. Test fixtures no longer need to rewrite subprocess args.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
COMPILE_SCRIPT = REPO_ROOT / "src" / "scripts" / "compile.py"
UPGRADE_SCRIPT = REPO_ROOT / "src" / "scripts" / "upgrade.py"
SKILL_SRC = REPO_ROOT / "src" / "core-skills" / "bmad-customize"
SCRIPTS_DIR = str(REPO_ROOT / "src" / "scripts")

# BH-2/ECH-3: 120s timeout on every subprocess.run. compile.py + upgrade.py
# run sub-second locally; 120s leaves headroom for slow CI runners while still
# bounding hang risk under the 6-hour GHA job timeout.
SUBPROCESS_TIMEOUT_SECONDS = 120


class TestE2ECustomizationLifecycle(unittest.TestCase):
    """Full 9-step customization lifecycle exercised against real compile.py + upgrade.py."""

    def setUp(self) -> None:
        # ECH-1/BH-5: ignore_cleanup_errors=True — on Windows, a still-running subprocess
        # can hold a file handle inside the tempdir; without this flag tearDown raises
        # PermissionError and masks the real test failure (Python 3.12+ surfaces it).
        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        tmp = Path(self._tmpdir.name)
        # DN-R2-1=α: full skill source tree at tmp/_bmad/core/bmad-customize/
        # install-phase scenario_root = skill_src.parent.parent = tmp/_bmad (matches drift.py).
        # Lockfile: tmp/_bmad/_config/bmad.lock = install_dir/_config/bmad.lock (§3 alignment).
        # SKILL.md: tmp/_bmad/core/bmad-customize/SKILL.md (install_dir/<module>/<basename>).
        self.skill_src = tmp / "_bmad" / "core" / "bmad-customize"
        self.skill_src.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(str(SKILL_SRC), str(self.skill_src))

        # ECH-2 + R2-BH-2: shutil.copytree preserves source permissions on platforms that
        # honor mode bits. Defensive chmod adds owner-write to every copied path (file or
        # directory) so Step 4's write_text and tearDown's cleanup both succeed regardless
        # of source mode. R2-BH-2 dropped the prior is_file() guard — chmod is safe on
        # directories and S_IWUSR on a directory permits modifying its contents.
        for path in self.skill_src.rglob("*"):
            path.chmod(path.stat().st_mode | stat.S_IWUSR)

        # upgrade.py expects project_root/_bmad/_config/bmad.lock; compile.py --install-dir is the _bmad/ dir.
        self.install_dir = tmp / "_bmad"
        self.project_root = tmp

        # BH-1/ECH-5: save sys.path so tearDown can restore it. Inserting the scripts/
        # directory pollutes subsequent unittest-discover modules in the same process
        # if the mutation is left behind.
        self._saved_sys_path = sys.path[:]
        if SCRIPTS_DIR not in sys.path:
            sys.path.insert(0, SCRIPTS_DIR)

    def tearDown(self) -> None:
        # BH-1/ECH-5: restore sys.path so other tests in the same discover run see
        # the unmodified search order.
        sys.path[:] = self._saved_sys_path
        self._tmpdir.cleanup()

    def _assert_step(self, step: int, condition: bool, message: str) -> None:
        """AC-10: fail-fast with step naming. A failure here halts the sequence."""
        if not condition:
            raise AssertionError(f"Step {step} FAIL: {message}")

    def _run_subprocess(self, step: int, args: list[str]) -> subprocess.CompletedProcess:
        """BH-2/ECH-3: subprocess.run with a 120s timeout and AC-10-style step-naming on TimeoutExpired.

        Every Step N subprocess invocation goes through this helper. The run_fn closure
        passed to write_override (Step 2) builds its own subprocess.run call site because
        write_override controls the args; that site mirrors this helper's contract
        (R2-BH-1 added the matching try/except).

        R2-ECH-12: include partial stdout in the timeout message — some upgrade.py failure
        modes write progress to stdout only, and the diagnostic is otherwise lost.
        """
        try:
            return subprocess.run(
                args,
                capture_output=True,
                text=True,
                cwd=str(REPO_ROOT),
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            partial_stderr = exc.stderr if isinstance(exc.stderr, str) else ""
            partial_stdout = exc.stdout if isinstance(exc.stdout, str) else ""
            raise AssertionError(
                f"Step {step} FAIL: subprocess timed out after {SUBPROCESS_TIMEOUT_SECONDS}s "
                f"— args={args!r}, partial stdout={partial_stdout!r}, partial stderr={partial_stderr!r}"
            ) from exc

    def test_lifecycle_sequence(self) -> None:
        from bmad_customize.writer import write_override

        # ──────────────────────────────────────────────────────────────────
        # Step 1 — AC-1: Fresh install.
        # ──────────────────────────────────────────────────────────────────
        result = self._run_subprocess(
            1,
            [sys.executable, str(COMPILE_SCRIPT), "--install-phase", "--install-dir", str(self.install_dir)],
        )
        self._assert_step(1, result.returncode == 0, f"compile exited {result.returncode}: {result.stderr}")
        lock_path = self.install_dir / "_config" / "bmad.lock"
        self._assert_step(1, lock_path.exists(), "bmad.lock not written")
        # WN-R2C-1: verify bmad.lock is valid JSON, not just present.
        _lock_json = json.loads(lock_path.read_text(encoding="utf-8"))
        self._assert_step(1, isinstance(_lock_json, dict), "bmad.lock is not valid JSON dict")
        compiled_skill_md = self.install_dir / "core" / "bmad-customize" / "SKILL.md"
        self._assert_step(
            1,
            compiled_skill_md.exists(),
            "compiled SKILL.md not written (install-phase mode path: <install_dir>/core/bmad-customize/SKILL.md)",
        )

        # ──────────────────────────────────────────────────────────────────
        # Step 2 — AC-2: Simulated bmad-customize session.
        # Override Fragment X = preflight.md (DN-R1-2=A); Fragment Y mutated in Step 4.
        # ──────────────────────────────────────────────────────────────────
        override_dir = self.install_dir / "custom" / "fragments" / "core" / "bmad-customize"
        override_dir.mkdir(parents=True, exist_ok=True)
        override_file = override_dir / "preflight.md"  # Fragment X

        _accepted_content = "<!-- E2E test override: custom preflight -->\n\nCustomized preflight by E2E test.\n"
        events: list[dict] = []

        # BH-3: run_fn closure must not collide with caller-supplied 'cwd' kwarg.
        # write_override's contract today doesn't pass cwd, but a future change shouldn't
        # produce a confusing TypeError (got multiple values for 'cwd'). Pop defensively.
        # BH-2/ECH-3 + R2-BH-1: enforce timeout=120 and wrap TimeoutExpired in step-named
        # AssertionError mirroring _run_subprocess's contract.
        # DN-R2-5=B: max-with-floor on timeout — caller cannot narrow the test's bound,
        # but can extend it (a future write_override that knows it's slow can pass timeout=300).
        def _e2e_run_fn(args: list[str], **kw: object) -> subprocess.CompletedProcess:
            kw.pop("cwd", None)
            caller_timeout = kw.get("timeout") if isinstance(kw.get("timeout"), (int, float)) else 0
            kw["timeout"] = max(caller_timeout, SUBPROCESS_TIMEOUT_SECONDS)
            # Retired by Story 7.3b: write_override now passes --install-dir itself.
            try:
                return subprocess.run(args, cwd=str(REPO_ROOT), **kw)
            except subprocess.TimeoutExpired as exc:
                partial_stderr = exc.stderr if isinstance(exc.stderr, str) else ""
                partial_stdout = exc.stdout if isinstance(exc.stdout, str) else ""
                raise AssertionError(
                    f"Step 2 FAIL: write_override subprocess timed out after {kw['timeout']}s "
                    f"— args={args!r}, partial stdout={partial_stdout!r}, partial stderr={partial_stderr!r}"
                ) from exc

        write_override(
            plane="prose",
            target_file=str(override_file),
            accepted_content=_accepted_content,
            skill_id="core/bmad-customize",  # DN-R2-3=A
            install_dir=str(self.install_dir),
            compile_py=COMPILE_SCRIPT,
            emit_fn=lambda event: events.append(event),
            run_fn=_e2e_run_fn,  # retained for timeout (R2-BH-1, DN-R2-5=B) and cwd-pop (BH-3)
        )
        self._assert_step(2, override_file.exists(), f"override file not created at {override_file}")
        # WN-R2C-2: verify override file content matches accepted_content exactly.
        self._assert_step(
            2,
            override_file.read_text(encoding="utf-8") == _accepted_content,
            "override file content does not match accepted_content",
        )

        # ──────────────────────────────────────────────────────────────────
        # Step 2.5 — Persist override record to bmad.lock (DN-PA-1=A).
        # write_override's compile --diff saves+restores lockfile in finally → net zero writes.
        # This non-diff positional compile is the "session-close" that production performs
        # automatically; without it, lockfile.py:404-406 short-circuits and AC-9 lineage stays empty.
        # ──────────────────────────────────────────────────────────────────
        result = self._run_subprocess(
            2,
            [sys.executable, str(COMPILE_SCRIPT), "core/bmad-customize", "--install-dir", str(self.install_dir)],
        )
        self._assert_step(
            2,
            result.returncode == 0,
            f"Step 2.5 compile (persist override to lockfile) exited {result.returncode}: {result.stderr!r}",
        )

        # ──────────────────────────────────────────────────────────────────
        # Step 3 — AC-3: Verify diff event emitted by write_override.
        # R2-ECH-7: iterate all diff_events with any(...), not just [0] — defends against
        # a future write_override that emits a placeholder empty-diff event before the real one.
        # BH-8/ECH-8 + DN-R2-4=A: a unified-diff with only a path-header line (--- / +++) would
        # satisfy a `'preflight' in diff_text` + non-empty check. Require BOTH a hunk header (`@@`)
        # AND an actual `+`/`-` content line (excluding `+++`/`---` path headers) — AND, not OR,
        # so a content-empty hunk header alone doesn't pass.
        # ──────────────────────────────────────────────────────────────────
        diff_events = [e for e in events if e.get("action") == "propose_diff_review"]
        self._assert_step(
            3,
            len(diff_events) > 0,
            f"write_override did not emit propose_diff_review event (events={events!r})",
        )

        def _is_real_diff(diff_text: str) -> bool:
            if "@@" not in diff_text:
                return False
            return any(
                line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
                for line in diff_text.splitlines()
            )

        self._assert_step(
            3,
            any(
                len(e.get("diff_text", "").strip()) > 0
                and "preflight" in e.get("diff_text", "")
                and _is_real_diff(e.get("diff_text", ""))
                for e in diff_events
            ),
            f"no diff_event has non-empty diff_text mentioning 'preflight' with real hunk content: {[e.get('diff_text', '')[:200] for e in diff_events]!r}",
        )

        # ──────────────────────────────────────────────────────────────────
        # Step 4 — AC-4: Simulate upstream changes.
        # Fragment Y (when-this-skill-cant-help.md, no override) → drift trigger.
        # Fragment X base (preflight.md, has override) → silent for X, lineage prerequisite.
        # ──────────────────────────────────────────────────────────────────
        base_fragment_y = self.skill_src / "fragments" / "when-this-skill-cant-help.md"
        base_fragment_x = self.skill_src / "fragments" / "preflight.md"

        orig_y = base_fragment_y.read_text(encoding="utf-8")
        orig_x = base_fragment_x.read_text(encoding="utf-8")
        upstream_y = orig_y + "\n<!-- Upstream v2 change: scope boundary expanded -->\n"
        upstream_x = orig_x + "\n<!-- Upstream v2 change: preflight step added -->\n"
        base_fragment_y.write_text(upstream_y, encoding="utf-8")
        base_fragment_x.write_text(upstream_x, encoding="utf-8")

        # DN-R1-2=B + DN-R2-2=A (Phil 2026-05-08): match lockfile.py's hashing contract.
        # io.hash_text(text) computes hashlib.sha256(text.encode("utf-8")).hexdigest() — operating
        # on the in-memory STRING (UTF-8 encoded), not the on-disk file bytes. The test depends
        # on this in-memory hashing only; on Windows write_text translates "\n" → "\r\n" on disk,
        # so on-disk file bytes do NOT equal text.encode("utf-8") cross-platform — but compile.py
        # also reads via read_text and hashes via hash_text(text), so both sides operate on the
        # same in-memory text representation. The hash logic below is correct; do not infer from
        # it that disk bytes are platform-stable.
        # DN-R2-7=A: explicit "utf-8" encoding (was implicit default; explicit removes the
        # implicit-encoding risk if a future Python change ever altered the default).
        orig_hash_y = hashlib.sha256(orig_y.encode("utf-8")).hexdigest()
        new_hash_y = hashlib.sha256(upstream_y.encode("utf-8")).hexdigest()
        self._assert_step(
            4,
            orig_hash_y != new_hash_y,
            "upstream change did not produce a different hash for Fragment Y",
        )
        # WN-R2C-3 + R2-ECH-5: verify Y's new hash differs from bmad.lock's recorded base_hash.
        # Use endswith() not substring `in` to avoid matching e.g. `<path>.bak` if a future
        # lockfile entry has near-name collisions.
        _lock_4 = json.loads((self.install_dir / "_config" / "bmad.lock").read_text(encoding="utf-8"))
        _skill_4 = next((e for e in _lock_4.get("entries", []) if e.get("skill") == "bmad-customize"), {})
        _y_lock_path = "core/bmad-customize/fragments/when-this-skill-cant-help.md"
        _frag_y_4 = next(
            (f for f in _skill_4.get("fragments", []) if f.get("path", "").endswith(_y_lock_path)),
            None,
        )
        self._assert_step(
            4,
            _frag_y_4 is not None,
            f"Fragment Y not found in bmad.lock (expected path ending with {_y_lock_path!r})",
        )
        self._assert_step(
            4,
            new_hash_y != _frag_y_4.get("base_hash"),
            "Fragment Y's upstream hash matches bmad.lock base_hash — change is not distinct from locked state",
        )

        # ──────────────────────────────────────────────────────────────────
        # Step 5 — AC-5: upgrade --dry-run reports drift.
        # DN-R2-6=A + R2-BH-3: tightened to the structured 'when-this-skill' anchor only.
        # The prior `'drift' OR 'prose_fragment'` check matched any banner/log mentioning
        # those substrings — vacuous-pass risk on unrelated stdout lines. The structured
        # token uniquely identifies Fragment Y in upgrade.py's drift report.
        # ──────────────────────────────────────────────────────────────────
        result = self._run_subprocess(
            5,
            [sys.executable, str(UPGRADE_SCRIPT), "--dry-run", "--project-root", str(self.project_root)],
        )
        self._assert_step(
            5,
            result.returncode == 0,
            f"upgrade --dry-run exited {result.returncode} (expected 0); stderr={result.stderr!r}",
        )
        combined = result.stdout + result.stderr
        self._assert_step(
            5,
            "when-this-skill" in combined,
            f"drift report does not reference Fragment Y (when-this-skill-cant-help): {combined[:400]!r}",
        )

        # ──────────────────────────────────────────────────────────────────
        # Step 6 — AC-6: bare upgrade exits 3.
        # ──────────────────────────────────────────────────────────────────
        result = self._run_subprocess(
            6,
            [sys.executable, str(UPGRADE_SCRIPT), "--project-root", str(self.project_root)],
        )
        self._assert_step(
            6,
            result.returncode == 3,
            f"upgrade exited {result.returncode} (expected 3); stderr={result.stderr!r}",
        )
        self._assert_step(
            6,
            len(result.stderr.strip()) > 0,
            "upgrade --bare produced no drift message on stderr",
        )

        # ──────────────────────────────────────────────────────────────────
        # Step 7 — AC-7: upgrade --yes resolves drift.
        # ──────────────────────────────────────────────────────────────────
        # WN-R2C-4: capture pre-upgrade compiled_hash to verify it changes.
        _pre_lock_7 = json.loads((self.install_dir / "_config" / "bmad.lock").read_text(encoding="utf-8"))
        _pre_skill_7 = next((e for e in _pre_lock_7.get("entries", []) if e.get("skill") == "bmad-customize"), {})
        pre_compiled_hash = _pre_skill_7.get("compiled_hash")

        result = self._run_subprocess(
            7,
            [sys.executable, str(UPGRADE_SCRIPT), "--yes", "--project-root", str(self.project_root)],
        )
        self._assert_step(
            7,
            result.returncode == 0,
            f"upgrade --yes exited {result.returncode}; stderr={result.stderr!r}",
        )
        lock_data = json.loads((self.install_dir / "_config" / "bmad.lock").read_text(encoding="utf-8"))
        skill_entry = next((e for e in lock_data.get("entries", []) if e.get("skill") == "bmad-customize"), None)
        self._assert_step(
            7,
            skill_entry is not None,
            "bmad-customize entry missing from bmad.lock after upgrade --yes",
        )
        # WN-R2C-4 + R2-ECH-5: post-upgrade Fragment X path is the override file (lockfile.py:206 —
        # resolved_path for user-override IS the override file). endswith() defends against near-name
        # collisions with hypothetical future entries.
        _x_override_path = "custom/fragments/core/bmad-customize/preflight.md"
        _post_frag_x_7 = next(
            (f for f in skill_entry.get("fragments", []) if f.get("path", "").endswith(_x_override_path)),
            None,
        )
        self._assert_step(
            7,
            _post_frag_x_7 is not None,
            "Fragment X override record missing from bmad.lock after upgrade --yes",
        )
        # R2-ECH-1: base_hash must be a 64-char sha256 hex string, not just non-None
        # (a regression that wrote empty string would otherwise silently pass).
        _post_x_base_hash = _post_frag_x_7.get("base_hash")
        self._assert_step(
            7,
            isinstance(_post_x_base_hash, str) and len(_post_x_base_hash) == 64,
            f"Fragment X base_hash is not a 64-char sha256 hex string (got {_post_x_base_hash!r}) — "
            "upgrade did not record a valid new base hash for the overridden fragment",
        )
        self._assert_step(
            7,
            skill_entry.get("compiled_hash") != pre_compiled_hash,
            f"skill compiled_hash unchanged after upgrade --yes (pre={pre_compiled_hash!r})",
        )

        # ──────────────────────────────────────────────────────────────────
        # Step 8 — AC-8: bare upgrade after resolution exits 0.
        # DN-R2-6=A: symmetric with Step 5 — the absence-check now uses the structured
        # 'when-this-skill' anchor (was loose 'drift' substring which would falsely fail
        # on any benign banner mentioning "drift").
        # ──────────────────────────────────────────────────────────────────
        result = self._run_subprocess(
            8,
            [sys.executable, str(UPGRADE_SCRIPT), "--project-root", str(self.project_root)],
        )
        self._assert_step(
            8,
            result.returncode == 0,
            f"upgrade (bare) exited {result.returncode} after resolution; stderr={result.stderr!r}",
        )
        combined = result.stdout + result.stderr
        # BH-6 + DN-R2-6=A: returncode==0 conjunction with absence of the structured
        # Fragment Y drift anchor. A regression that exits 0 silently still satisfies the
        # returncode check above; this absence-check is the corroborating signal that
        # post-resolution upgrade does NOT report Fragment Y as drifted again.
        self._assert_step(
            8,
            "when-this-skill" not in combined,
            f"unexpected drift on Fragment Y after resolution: {combined[:400]!r}",
        )

        # ──────────────────────────────────────────────────────────────────
        # Step 9 — AC-9: bmad.lock lineage[] non-empty for Fragment X with full schema.
        # R2-ECH-5: endswith() instead of substring `in`.
        # ──────────────────────────────────────────────────────────────────
        lock_data = json.loads((self.install_dir / "_config" / "bmad.lock").read_text(encoding="utf-8"))
        skill_entry = next((e for e in lock_data.get("entries", []) if e.get("skill") == "bmad-customize"), None)
        self._assert_step(9, skill_entry is not None, "bmad-customize entry missing from bmad.lock")

        override_fragment_path = "custom/fragments/core/bmad-customize/preflight.md"
        fragment_record = next(
            (f for f in skill_entry.get("fragments", []) if f.get("path", "").endswith(override_fragment_path)),
            None,
        )
        self._assert_step(
            9,
            fragment_record is not None,
            "Fragment X (preflight.md) override record not found in bmad.lock fragments",
        )
        lineage = fragment_record.get("lineage", [])
        self._assert_step(
            9,
            len(lineage) >= 1,
            "lineage[] is empty for Fragment X — expected ≥1 entry after base change + upgrade --yes",
        )
        lineage_entry = lineage[0]
        self._assert_step(9, "base_hash" in lineage_entry, "lineage entry missing 'base_hash'")
        self._assert_step(9, "bmad_version" in lineage_entry, "lineage entry missing 'bmad_version'")
        self._assert_step(9, "override_hash" in lineage_entry, "lineage entry missing 'override_hash'")


if __name__ == "__main__":
    unittest.main()
