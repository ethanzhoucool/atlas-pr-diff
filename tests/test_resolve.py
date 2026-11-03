"""Commit/branch/baseline ref resolution. `revyl build list` is mocked;
nothing calls Revyl.

Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from atlas_diff import cli, model, revyl  # noqa: E402

SHA_A = "4138aac" + "1" * 33          # two different commits whose first
SHA_B = "4138aac" + "2" * 33          # 7 characters collide


def build(version, full=None, short=None):
    git = {}
    if full is not None:
        git["commit"] = full
    if short is not None:
        git["commit_short"] = short
    return {"id": f"id-{version}", "version": version, "metadata": {"git": git}}


class TestBuildForCommit(unittest.TestCase):
    def resolve(self, builds, commit):
        with mock.patch.object(revyl, "list_builds", return_value=builds):
            b = revyl.build_for_commit("app", commit)
        return b and b["version"]

    def test_exact_match_beats_newer_prefix_collision(self):
        builds = [build("new", SHA_B, SHA_B[:7]), build("old", SHA_A, SHA_A[:7])]
        self.assertEqual(self.resolve(builds, SHA_A), "old")   # was "new"

    def test_different_full_sha_with_same_prefix_is_not_a_match(self):
        builds = [build("other", SHA_B, SHA_B[:7])]
        self.assertIsNone(self.resolve(builds, SHA_A))         # was "other"

    def test_short_sha_picks_newest_matching_build(self):
        builds = [build("v3", SHA_A, SHA_A[:7]), build("v2", SHA_A, SHA_A[:7]),
                  build("v1", "f" * 40, "fffffff")]
        self.assertEqual(self.resolve(builds, SHA_A[:7]), "v3")
        self.assertEqual(self.resolve(builds, SHA_A[:10].upper()), "v3")

    def test_full_sha_matches_build_that_recorded_only_a_short_sha(self):
        builds = [build("short-only", short=SHA_A[:7])]
        self.assertEqual(self.resolve(builds, SHA_A), "short-only")   # was None

    def test_no_builds_or_empty_commit(self):
        self.assertIsNone(self.resolve([], SHA_A))
        self.assertIsNone(self.resolve([build("x", SHA_A)], ""))


class TestRefErrorsInCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.head = os.path.join(self.tmp, "head.json")
        model.from_graph_payload({"nodes": [{"id": "a", "semantic_name": "a"}]}).save(self.head)

    def run_cli(self, *argv):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["--config", os.path.join(self.tmp, "none.yml"), *argv])
        return code, err.getvalue()

    def test_missing_baseline_file_is_a_clear_usage_error(self):
        missing = os.path.join(self.tmp, "atlas-baseline.json")
        with mock.patch.object(revyl, "list_builds", side_effect=AssertionError("no Revyl call")), \
                mock.patch.object(revyl, "atlas_graph", side_effect=AssertionError("no Revyl call")):
            code, err = self.run_cli("diff", "--app", "app", "--base", missing, "--head", self.head)
        self.assertEqual(code, 2)
        self.assertIn("atlas-baseline.json not found", err)
        self.assertIn("atlas-diff snapshot", err)

    def test_commit_with_no_build_exits_3_not_gate_failure(self):
        with mock.patch.object(revyl, "list_builds", return_value=[]):
            code, err = self.run_cli("diff", "--app", "app", "--base", self.head,
                                     "--head", "commit:" + SHA_A)
        self.assertEqual(code, 3)          # was 1, which the Action reports as "gate failed"
        self.assertIn("no Revyl build found for commit", err)

    def test_branch_with_no_build_exits_3(self):
        with mock.patch.object(revyl, "list_builds", return_value=[]):
            code, err = self.run_cli("snapshot", "--app", "app", "--build", "branch:nope",
                                     "-o", os.path.join(self.tmp, "out.json"))
        self.assertEqual(code, 3)
        self.assertIn("branch nope", err)

    def test_existing_baseline_file_still_works(self):
        code, _ = self.run_cli("diff", "--app", "app", "--base", self.head, "--head", self.head,
                               "--fail-on", "changes", "-q")
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
