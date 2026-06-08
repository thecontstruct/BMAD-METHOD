"""Story 10.56 — ctx.git fields: unit tests for git_context.build_git_ctx()."""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

BMAD_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPTS = str(BMAD_ROOT / "src" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from bmad_compile.git_context import build_git_ctx


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(stdout="", returncode=0):
    """Build a mock CompletedProcess-like object."""
    r = types.SimpleNamespace()
    r.stdout = stdout
    r.returncode = returncode
    return r


def _patch_run(side_effects):
    """Patch subprocess.run to return results in sequence."""
    import itertools
    it = iter(side_effects)

    def _run(*args, **kwargs):
        try:
            val = next(it)
        except StopIteration:
            return _make_result("", 1)
        if isinstance(val, Exception):
            raise val
        return val

    return patch("bmad_compile.git_context.subprocess.run", side_effect=_run)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildGitCtxInRepo(unittest.TestCase):
    """Happy-path tests: inside a git repository."""

    def _standard_mocks(self, sha="a" * 40, root="/repo", branch="main",
                        dirty="", tag="v1.0.0"):
        """Return side_effects list for a clean, tagged repo on `branch`."""
        sha_root = _make_result(f"{sha}\n{root}", 0)
        branch_r = _make_result(branch, 0)
        status_r = _make_result(dirty, 0)
        tag_r = _make_result(tag, 0)
        return [sha_root, branch_r, status_r, tag_r]

    def test_returns_namespace_not_none(self):
        with _patch_run(self._standard_mocks()):
            result = build_git_ctx()
        self.assertIsNotNone(result)
        self.assertIsInstance(result, types.SimpleNamespace)

    def test_branch_populated(self):
        with _patch_run(self._standard_mocks(branch="feature/foo")):
            result = build_git_ctx()
        self.assertEqual(result.branch, "feature/foo")

    def test_commit_sha_40_chars(self):
        sha = "b" * 40
        with _patch_run(self._standard_mocks(sha=sha)):
            result = build_git_ctx()
        self.assertEqual(result.commit_sha, sha)
        self.assertEqual(len(result.commit_sha), 40)

    def test_commit_short_sha_8_chars(self):
        sha = "c" * 40
        with _patch_run(self._standard_mocks(sha=sha)):
            result = build_git_ctx()
        self.assertEqual(result.commit_short_sha, sha[:8])

    def test_short_sha_derived_not_separate_call(self):
        """commit_short_sha == commit_sha[:8] always, never None when sha present."""
        sha = "deadbeef" + "0" * 32
        with _patch_run(self._standard_mocks(sha=sha)):
            result = build_git_ctx()
        self.assertEqual(result.commit_short_sha, "deadbeef")

    def test_dirty_true(self):
        dirty = " M file.py\n?? other.py\n"
        with _patch_run(self._standard_mocks(dirty=dirty)):
            result = build_git_ctx()
        self.assertTrue(result.is_dirty)

    def test_dirty_false(self):
        with _patch_run(self._standard_mocks(dirty="")):
            result = build_git_ctx()
        self.assertFalse(result.is_dirty)

    def test_tag_present(self):
        with _patch_run(self._standard_mocks(tag="v2.3.4")):
            result = build_git_ctx()
        self.assertEqual(result.tag, "v2.3.4")

    def test_tag_absent_returns_none(self):
        side = self._standard_mocks()
        # Replace tag result with non-zero returncode
        side[3] = _make_result("", 128)
        with _patch_run(side):
            result = build_git_ctx()
        self.assertIsNone(result.tag)

    def test_repo_root_populated(self):
        with _patch_run(self._standard_mocks(root="/workspace/myrepo")):
            result = build_git_ctx()
        self.assertEqual(result.repo_root, "/workspace/myrepo")

    def test_all_fields_present(self):
        with _patch_run(self._standard_mocks()):
            result = build_git_ctx()
        for field in ("branch", "commit_sha", "commit_short_sha",
                      "is_dirty", "tag", "repo_root"):
            self.assertTrue(hasattr(result, field), f"missing field: {field}")


class TestBuildGitCtxDetachedHead(unittest.TestCase):
    """branch is None in detached HEAD state."""

    def test_detached_head_branch_is_none(self):
        sha_root = _make_result(f"{'a'*40}\n/repo", 0)
        branch_r = _make_result("", 128)  # symbolic-ref exits non-zero in detached HEAD
        status_r = _make_result("", 0)
        tag_r = _make_result("", 128)
        with _patch_run([sha_root, branch_r, status_r, tag_r]):
            result = build_git_ctx()
        self.assertIsNotNone(result)
        self.assertIsNone(result.branch)


class TestBuildGitCtxOutOfRepo(unittest.TestCase):
    """Returns None when not inside a git repository."""

    def test_not_in_repo_returns_none(self):
        sha_root = _make_result("", 128)  # non-zero → not a repo
        with _patch_run([sha_root]):
            result = build_git_ctx()
        self.assertIsNone(result)

    def test_git_not_on_path_returns_none(self):
        with _patch_run([FileNotFoundError("git: command not found")]):
            result = build_git_ctx()
        self.assertIsNone(result)

    def test_unexpected_exception_returns_none(self):
        with _patch_run([OSError("some unexpected OS error")]):
            result = build_git_ctx()
        self.assertIsNone(result)


class TestBuildGitCtxPartialFailure(unittest.TestCase):
    """One field command fails; others still populate; function does not raise."""

    def test_branch_failure_still_returns_namespace(self):
        sha_root = _make_result(f"{'a'*40}\n/repo", 0)
        branch_r = _make_result("", 1)   # branch call fails
        status_r = _make_result("", 0)
        tag_r = _make_result("v1.0", 0)
        with _patch_run([sha_root, branch_r, status_r, tag_r]):
            result = build_git_ctx()
        self.assertIsNotNone(result)
        self.assertIsNone(result.branch)
        self.assertEqual(result.tag, "v1.0")

    def test_status_exception_does_not_raise(self):
        sha_root = _make_result(f"{'a'*40}\n/repo", 0)
        branch_r = _make_result("main", 0)
        # status call raises unexpectedly
        tag_r = _make_result("", 128)
        with _patch_run([sha_root, branch_r, OSError("disk read error"), tag_r]):
            result = build_git_ctx()
        self.assertIsNotNone(result)
        self.assertFalse(result.is_dirty)  # default False on failure
        self.assertEqual(result.branch, "main")

    def test_cwd_passed_to_subprocess(self):
        """cwd parameter is forwarded to subprocess.run calls."""
        calls = []
        sha_root = _make_result(f"{'a'*40}\n/repo", 0)
        branch_r = _make_result("main", 0)
        status_r = _make_result("", 0)
        tag_r = _make_result("", 128)

        import bmad_compile.git_context as gc_mod

        original = gc_mod.subprocess.run

        def spy(*args, **kwargs):
            calls.append(kwargs.get("cwd"))
            return [sha_root, branch_r, status_r, tag_r][len(calls) - 1]

        with patch.object(gc_mod.subprocess, "run", side_effect=spy):
            build_git_ctx(cwd="/some/path")

        self.assertTrue(all(c == "/some/path" for c in calls),
                        f"Expected all cwd='/some/path', got: {calls}")


if __name__ == "__main__":
    unittest.main()
