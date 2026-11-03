"""Untrusted Atlas text (screen names, descriptions, areas, flow and action
labels) must not be able to inject Markdown/HTML into the PR comment.

Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import os
import re
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from atlas_diff import diff, mdsafe, model, render  # noqa: E402

META = {"base_label": "main-1", "head_label": "pr-2", "app": "Ubert"}


def node(id, name, area="Home", kind="screen", desc="", entry=False, **extra):
    n = {"id": id, "semantic_name": name, "product_area": area, "screen_kind": kind,
         "semantic_description": desc, "observation_count": 5, "is_entry_point": entry}
    n.update(extra)
    return n


def edge(src, tgt, label="tap", test=0):
    return {"source_entity_id": src, "target_entity_id": tgt, "action_label": label,
            "observation_count": 5, "test_support": test}


def snap(nodes, edges=(), flows=()):
    return model.from_graph_payload({"app_id": "app-1", "nodes": list(nodes),
                                     "edges": list(edges), "flows": list(flows)})


def md_for(base, head, meta=META):
    return render.render_markdown(diff.diff(base, head), meta)


HOSTILE_DESC = ("Shows @octocat's profile </details> <!-- hidden <img src=x> "
                "[Fix it here](https://evil.example) **bold**\n# Not a heading")


class TestHostileDescription(unittest.TestCase):
    def setUp(self):
        base = snap([node("home", "home", entry=True)])
        head = snap([node("home", "home", entry=True),
                     node("p", "profile", desc=HOSTILE_DESC)],
                    [edge("home", "p")])
        self.md = md_for(base, head)

    def test_mentions_do_not_ping(self):
        self.assertNotRegex(self.md, r"@octocat")
        self.assertIn("@&#8203;octocat", self.md)

    def test_html_cannot_close_details_or_open_a_comment(self):
        body = self.md.split("\n", 1)[1]          # skip the sticky marker line
        self.assertNotIn("<!--", body)
        self.assertNotIn("<img", body)
        self.assertEqual(self.md.count("<details>"), self.md.count("</details>"))
        self.assertIn("&lt;/details&gt;", self.md)

    def test_no_planted_link_or_emphasis(self):
        self.assertNotRegex(self.md, r"(?<!\\)\]\(https://evil")   # no unescaped "](" link
        self.assertIn(r"\[Fix it here\]", self.md)
        self.assertIn(r"\*\*bold\*\*", self.md)

    def test_newline_cannot_start_a_heading(self):
        self.assertFalse(any(l.startswith("# ") for l in self.md.splitlines()))
        line = next(l for l in self.md.splitlines() if "Shows" in l)
        self.assertTrue(line.endswith(" # Not a heading"), line)


class TestHostileNames(unittest.TestCase):
    def test_backtick_in_name_stays_inside_one_link(self):
        evil = "evil`](https://evil.example) `x"
        base = snap([node("home", "home", entry=True)])
        head = snap([node("home", "home", entry=True), node("b", evil)], [edge("home", "b")])
        md = md_for(base, head)
        self.assertIn(mdsafe.code(evil), md)
        # every link in the comment points at the Atlas viewer
        for target in re.findall(r"\]\((\S+?)\)", md.replace(mdsafe.code(evil), "")):
            self.assertTrue(target.startswith("https://app.revyl.ai/"), target)

    def test_names_in_reasons_reach_paths_and_flows_are_code_spans(self):
        base = snap([node("home", "home", entry=True), node("old", "old`one")],
                    [edge("home", "old")],
                    [{"id": "f1", "label": "Checkout @team", "route_node_ids": ["old"]}])
        head = snap([node("home", "home", entry=True), node("new", "new`one"),
                     node("deep", "deep@scr")],
                    [edge("home", "new"), edge("new", "deep")])
        md = md_for(base, head)
        self.assertIn("now navigates to new screen ``new`one``", md)
        self.assertIn("no longer navigates to removed screen ``old`one``", md)
        self.assertIn("reach it: `home` → ``new`one`` → `deep@scr`", md)
        self.assertIn("**Checkout @&#8203;team**", md)

    def test_area_and_action_label_escaped(self):
        base = snap([node("a", "a", entry=True), node("b", "b")],
                    [edge("a", "b", label="tap [here](https://evil.example)", test=1)])
        head = snap([node("a", "a", entry=True), node("b", "b", area="_Payments_ @ops")],
                    [edge("a", "b")])
        md = md_for(base, head)
        self.assertIn(r"_\_Payments\_ @&#8203;ops_", md)
        self.assertIn(r"(tap \[here\](https://evil.example))", md)


class TestLinksAndAttributes(unittest.TestCase):
    def test_non_http_viewer_url_is_not_linked(self):
        base = snap([])
        head = snap([node("x", "x", viewer_url="javascript:alert(1)")])
        md = md_for(base, head)
        self.assertNotIn("javascript:", md)
        self.assertIn("- `x` (screen)", md)

    def test_viewer_url_with_spaces_and_parens_is_encoded(self):
        head = snap([node("x", "x", viewer_url="https://app.revyl.ai/a b(c)")])
        md = md_for(snap([]), head)
        self.assertIn("[`x`](https://app.revyl.ai/a%20b%28c%29)", md)

    def test_screenshot_path_cannot_break_out_of_img_src(self):
        head = snap([node("x", "x", local_screenshot_path='s.png" onerror="alert(1)')])
        md = md_for(snap([]), head, dict(META, embed_shots=True))
        self.assertIn('<img src="s.png&quot; onerror=&quot;alert(1)" width="200">', md)


class TestOrdinaryTextUnchanged(unittest.TestCase):
    """Escaping must not uglify normal Atlas output."""

    def test_snake_case_and_punctuation_untouched(self):
        desc = "Review the driver's ETA, cost ($26.14) and pickup_location - then confirm."
        head = snap([node("x", "ride_service_selection", kind="empty_state", desc=desc)])
        md = md_for(snap([]), head)
        self.assertIn("[`ride_service_selection`](https://app.revyl.ai/apps/app-1/atlas"
                      "?focus=screen&entityId=x) (empty_state) · _Home_ — " + desc, md)

    def test_code_helper(self):
        self.assertEqual(mdsafe.code("plain"), "`plain`")
        self.assertEqual(mdsafe.code("a`b"), "``a`b``")
        self.assertEqual(mdsafe.code("`x"), "`` `x ``")
        self.assertEqual(mdsafe.code("a\n\nb"), "`a b`")


if __name__ == "__main__":
    unittest.main()
