"""Tests for github/post_check.py (sticky comment + check run poster).

The GitHub API is never called: `_gh_api` is replaced with a fake that
records calls and serves canned responses.

Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import contextlib
import importlib.util
import io
import os
import sys
import unittest
import urllib.error
from unittest import mock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_spec = importlib.util.spec_from_file_location(
    "post_check", os.path.join(_REPO_ROOT, "github", "post_check.py"))
post_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(post_check)

from atlas_diff import diff, model, render  # noqa: E402

MARKER = post_check.MARKER


class FakeGitHub:
    """Stands in for post_check._gh_api."""

    def __init__(self, pages=None, fail_list=False):
        self.pages = pages or [[]]      # list of comment pages (lists)
        self.fail_list = fail_list
        self.calls = []                 # (method, path, body)

    def __call__(self, method, path, token, body):
        self.calls.append((method, path, body))
        if method == "GET":
            if self.fail_list:
                raise urllib.error.URLError("boom")
            page = int(path.rsplit("page=", 1)[1])
            return self.pages[page - 1] if page <= len(self.pages) else []
        return {"id": 999}

    def writes(self):
        return [(m, p, b) for (m, p, b) in self.calls if m != "GET"]


def _comment(cid, body):
    return {"id": cid, "body": body, "user": {"login": "someone"}}


def _quiet():
    return contextlib.redirect_stderr(io.StringIO())


class TestUpsertStickyComment(unittest.TestCase):
    def _upsert(self, fake, body=MARKER + "\nnew"):
        with mock.patch.object(post_check, "_gh_api", fake), _quiet():
            return post_check.upsert_sticky_comment("o/r", 7, "tok", body)

    def test_posts_when_no_sticky_exists(self):
        fake = FakeGitHub([[_comment(1, "lgtm")]])
        self.assertTrue(self._upsert(fake))
        (method, path, body), = fake.writes()
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/repos/o/r/issues/7/comments")

    def test_patches_existing_sticky_on_later_page(self):
        page1 = [_comment(i, "chatter") for i in range(100)]
        page2 = [_comment(555, MARKER + "\nold report")]
        fake = FakeGitHub([page1, page2])
        self.assertTrue(self._upsert(fake))
        (method, path, _), = fake.writes()
        self.assertEqual((method, path), ("PATCH", "/repos/o/r/issues/comments/555"))

    def test_does_not_overwrite_a_human_quoting_the_marker(self):
        quoted = "> " + MARKER + "\n> ## 🔴 Atlas map diff\n\nwhy is this red?"
        mentions = "the bot looks for `" + MARKER + "` in its comment"
        fake = FakeGitHub([[_comment(10, quoted), _comment(11, mentions)]])
        self._upsert(fake)
        (method, _, _), = fake.writes()
        self.assertEqual(method, "POST")   # neither human comment was PATCHed

    def test_list_failure_does_not_post_a_duplicate(self):
        fake = FakeGitHub(fail_list=True)
        self.assertFalse(self._upsert(fake))
        self.assertEqual(fake.writes(), [])

    def test_unexpected_listing_does_not_post_a_duplicate(self):
        fake = FakeGitHub()
        fake.pages = [{"message": "Not Found"}]
        self.assertFalse(self._upsert(fake))
        self.assertEqual(fake.writes(), [])


class TestFitMarkdown(unittest.TestCase):
    def _big_report(self, n=3000):
        lines = [MARKER, "## 🔴 Atlas map diff", "",
                 "<details><summary>🆕 New screens (%d)</summary>" % n, ""]
        lines += [f"- [`screen_{i}`](https://app.revyl.ai/x/{i}) (form) · _Area_ — "
                  f"a description that is long enough to add up quickly {i}" for i in range(n)]
        lines += ["</details>", "", "---", "<sub>footer</sub>"]
        return "\n".join(lines)

    def test_small_report_unchanged(self):
        md = MARKER + "\n## ok\n"
        self.assertIs(post_check.fit_markdown(md, 1000), md)

    def test_big_report_fits_and_stays_well_formed(self):
        md = self._big_report()
        self.assertGreater(len(md), 65536)
        out = post_check.fit_markdown(md, post_check.COMMENT_LIMIT)
        self.assertLessEqual(len(out), post_check.COMMENT_LIMIT)
        self.assertLessEqual(len(out), 65536)
        self.assertTrue(out.startswith(MARKER))
        self.assertEqual(out.count("<details>"), out.count("</details>"))
        self.assertTrue(out.endswith(post_check.TRUNCATED_NOTE))
        # cut on a line boundary: every kept list item is complete
        for line in out.split("\n"):
            if line.startswith("- [`screen_"):
                self.assertRegex(line, r"quickly \d+$")

    def test_tight_limit_is_respected_exactly(self):
        md = self._big_report(200)
        for limit in (300, 1000, 5000):
            out = post_check.fit_markdown(md, limit)
            self.assertLessEqual(len(out), limit)
            self.assertTrue(out.startswith(MARKER))
            self.assertEqual(out.count("<details>"), out.count("</details>"))

    def test_real_render_of_a_huge_diff(self):
        base = model.from_graph_payload({"app_id": "a", "nodes": [], "edges": []})
        nodes = [{"id": f"s{i}", "semantic_name": f"screen_{i}", "product_area": "Home",
                  "semantic_description": "x" * 120} for i in range(1500)]
        head = model.from_graph_payload({"app_id": "a", "nodes": nodes, "edges": []})
        md = render.render_markdown(diff.diff(base, head), {"base_label": "b", "head_label": "h"})
        self.assertGreater(len(md), 65536)
        out = post_check.fit_markdown(md, post_check.COMMENT_LIMIT)
        self.assertLessEqual(len(out), 65536)
        self.assertEqual(out.count("<details>"), out.count("</details>"))


class TestMain(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.tmp, ignore_errors=True)

    def _write(self, name, text):
        p = os.path.join(self.tmp, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        return p

    def test_oversized_report_is_truncated_for_comment_and_check(self):
        md = MARKER + "\n" + "\n".join(f"- line {i} " + "y" * 80 for i in range(2000))
        md_path = self._write("r.md", md)
        json_path = self._write("r.json", '{"verdict": "Map changed — review impact"}')
        fake = FakeGitHub([[]])
        env = {"GITHUB_TOKEN": "t", "GITHUB_REPOSITORY": "o/r"}
        out = io.StringIO()
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(post_check, "_gh_api", fake), \
                contextlib.redirect_stdout(out), _quiet():
            rc = post_check.main(["--md", md_path, "--json", json_path,
                                  "--pr", "3", "--sha", "abc"])
        self.assertEqual(rc, 0)
        writes = dict((p, b) for (_, p, b) in fake.writes())
        comment = writes["/repos/o/r/issues/3/comments"]["body"]
        check = writes["/repos/o/r/check-runs"]["output"]["summary"]
        self.assertLessEqual(len(comment), 65536)
        self.assertLessEqual(len(check), 65535)
        self.assertTrue(comment.startswith(MARKER))
        # the untruncated report is kept in the job log
        self.assertIn(md, out.getvalue())

    def test_no_token_prints_report_and_succeeds(self):
        md_path = self._write("r.md", MARKER + "\nhello")
        out = io.StringIO()
        env = {k: v for k, v in os.environ.items()
               if k not in ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_REPOSITORY")}
        with mock.patch.dict(os.environ, env, clear=True), \
                contextlib.redirect_stdout(out), _quiet():
            rc = post_check.main(["--md", md_path])
        self.assertEqual(rc, 0)
        self.assertIn("hello", out.getvalue())


if __name__ == "__main__":
    unittest.main()
