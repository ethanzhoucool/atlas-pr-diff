"""Stdlib-only (unittest) tests for atlas_diff.config (v0.2).

Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# Make `from atlas_diff import ...` work when run from the repo root.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from atlas_diff import config  # noqa: E402


# --------------------------------------------------------------------------
# _parse_flat_yaml
# --------------------------------------------------------------------------
class TestParseFlatYaml(unittest.TestCase):
    def test_representative_config(self):
        text = "\n".join([
            "# leading comment line",
            "app: my-app                 # which app",
            "base: main",
            "fail-on: changes",
            "limit: 10",
            "min_support: 3",
            'title: "My PR Diff"',
            "baseline: 'cached'",
            "embed: true",
            "verbose: false",
            "nothing: null",
            "also_nothing:",
            "  nested: should-be-skipped",
            "",
        ])
        out = config._parse_flat_yaml(text)
        self.assertEqual(out, {
            "app": "my-app",
            "base": "main",
            "fail-on": "changes",
            "limit": 10,
            "min_support": 3,
            "title": "My PR Diff",
            "baseline": "cached",
            "embed": True,
            "verbose": False,
            "nothing": None,
            "also_nothing": None,
        })
        # nested (indented) line must NOT leak in
        self.assertNotIn("nested", out)

    def test_coercions(self):
        out = config._parse_flat_yaml("\n".join([
            "a: true",
            "b: false",
            "c: 42",
            "d: -7",
            "e: none",
            "f: ~",
            "g: hello",
            'h: "quoted"',
            "i: ''",
        ]))
        self.assertIs(out["a"], True)
        self.assertIs(out["b"], False)
        self.assertEqual(out["c"], 42)
        self.assertEqual(out["d"], -7)
        self.assertIsNone(out["e"])
        self.assertIsNone(out["f"])
        self.assertEqual(out["g"], "hello")
        self.assertEqual(out["h"], "quoted")
        # empty quoted string strips to empty string
        self.assertEqual(out["i"], "")

    def test_inline_comment_stripped(self):
        out = config._parse_flat_yaml("base: main   # use the trunk branch")
        self.assertEqual(out["base"], "main")


# --------------------------------------------------------------------------
# load_config
# --------------------------------------------------------------------------
class TestLoadConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_yaml_normalizes_dashed_keys_and_path(self):
        p = os.path.join(self.tmp, ".atlas-diff.yml")
        with open(p, "w") as fh:
            fh.write("fail-on: changes\nmin-support: 4\napp: demo\n")
        cfg = config.load_config(p)
        self.assertEqual(cfg["fail_on"], "changes")
        self.assertEqual(cfg["min_support"], 4)
        self.assertEqual(cfg["app"], "demo")
        self.assertEqual(cfg["_path"], p)
        # dashed form must be gone after normalization
        self.assertNotIn("fail-on", cfg)
        self.assertNotIn("min-support", cfg)

    def test_json_config(self):
        p = os.path.join(self.tmp, ".atlas-diff.json")
        with open(p, "w") as fh:
            json.dump({"app": "json-app", "fail-on": "untested", "limit": 5}, fh)
        cfg = config.load_config(p)
        self.assertEqual(cfg["app"], "json-app")
        self.assertEqual(cfg["fail_on"], "untested")
        self.assertEqual(cfg["limit"], 5)
        self.assertEqual(cfg["_path"], p)

    def test_nonexistent_path_returns_empty(self):
        missing = os.path.join(self.tmp, "does-not-exist.yml")
        self.assertEqual(config.load_config(missing), {})


# --------------------------------------------------------------------------
# find_config
# --------------------------------------------------------------------------
class TestFindConfig(unittest.TestCase):
    def test_walks_up_to_find_config(self):
        with tempfile.TemporaryDirectory() as top:
            top = os.path.realpath(top)
            cfg_path = os.path.join(top, ".atlas-diff.yml")
            with open(cfg_path, "w") as fh:
                fh.write("app: walked-up\n")
            nested = os.path.join(top, "a", "b", "c")
            os.makedirs(nested)
            found = config.find_config(nested)
            self.assertIsNotNone(found)
            self.assertEqual(os.path.realpath(found), cfg_path)

    def test_returns_none_when_no_config(self):
        with tempfile.TemporaryDirectory() as top:
            nested = os.path.join(top, "x", "y")
            os.makedirs(nested)
            # walking up from an isolated tmp tree should not hit a config here;
            # but a repo-level config could exist above tmp. Only assert when the
            # walk stays clean — guard by checking the tmp tree itself.
            found = config.find_config(nested)
            # If anything is found it must be ABOVE our tmp tree (a real machine
            # config), never inside it.
            if found is not None:
                self.assertFalse(os.path.realpath(found).startswith(os.path.realpath(top)))


# --------------------------------------------------------------------------
# git helpers
# --------------------------------------------------------------------------
class TestGitHelpers(unittest.TestCase):
    def setUp(self):
        if shutil.which("git") is None:
            self.skipTest("git not on PATH")
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_in_git_repo_false_before_init(self):
        self.assertFalse(config.in_git_repo(cwd=self.tmp))

    def test_in_git_repo_and_head_sha_after_commit(self):
        def run(*args):
            return subprocess.run(["git", *args], cwd=self.tmp,
                                  capture_output=True, text=True)

        if run("init").returncode != 0:
            self.skipTest("git init failed in this environment")
        run("config", "user.email", "test@example.com")
        run("config", "user.name", "Test User")
        commit = run("commit", "--allow-empty", "-m", "init")
        if commit.returncode != 0:
            self.skipTest("git commit failed in this environment")

        self.assertTrue(config.in_git_repo(cwd=self.tmp))
        sha = config.git_head_sha(cwd=self.tmp)
        self.assertIsNotNone(sha)
        self.assertEqual(len(sha), 40)
        # 40-char hex
        int(sha, 16)


if __name__ == "__main__":
    unittest.main()
