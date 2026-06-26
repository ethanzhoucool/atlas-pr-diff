"""Stdlib-only (unittest) tests for atlas_diff.render v0.2 features.

Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from atlas_diff import diff, model, render  # noqa: E402


# --------------------------------------------------------------------------
# Synthetic payload helpers (mirrors tests/test_diff.py style)
# --------------------------------------------------------------------------
def node(id, name, area="Home", kind="screen", desc="", obs=5, actions=(),
         entry=False):
    return {
        "id": id,
        "semantic_name": name,
        "display_name": name,
        "label": name,
        "product_area": area,
        "screen_kind": kind,
        "semantic_description": desc,
        "observation_count": obs,
        "is_entry_point": entry,
        "is_hub": False,
        "is_terminal": False,
        "primary_actions": list(actions),
        "screenshot_s3_key": None,
    }


def edge(src, tgt, label="tap", obs=5, test=0, report=0, session=0):
    return {
        "source_entity_id": src,
        "target_entity_id": tgt,
        "action_label": label,
        "action_type": "tap",
        "observation_count": obs,
        "test_support": test,
        "report_support": report,
        "session_support": session,
    }


def make_payload(nodes=(), edges=(), flows=(), app_id="app-1"):
    return {
        "app_id": app_id,
        "nodes": list(nodes),
        "edges": list(edges),
        "flows": list(flows),
        "stats": {},
        "projection": {"requested_build_id": "build-x"},
    }


def snap(nodes=(), edges=(), flows=(), app_id="app-1"):
    return model.from_graph_payload(make_payload(nodes, edges, flows, app_id))


META = {"base_label": "base", "head_label": "head", "app": "app-1", "title": "Atlas map diff"}


# --------------------------------------------------------------------------
# Untested-with-reach-path scenario
# --------------------------------------------------------------------------
class TestUntestedRendering(unittest.TestCase):
    def _result_with_untested_reachable(self):
        # base: A (entry) -> B, both pre-exist and there is a NEW screen C in head.
        # head: A (entry) -> B -> C, all edges significant (obs=5) but untested.
        # C is brand new, reachable via the 2-hop path A -> B -> C, and no test
        # reaches it => "now untested" with a reach_path of len 3.
        base = snap(
            [node("A", "home", entry=True), node("B", "feed")],
            [edge("A", "B", obs=5, test=0)],
        )
        head = snap(
            [node("A", "home", entry=True), node("B", "feed"),
             node("C", "checkout", area="Cart", obs=5)],
            [edge("A", "B", obs=5, test=0), edge("B", "C", obs=5, test=0)],
        )
        return diff.diff(base, head)

    def test_markdown_contains_viewer_url_and_reach_and_cover(self):
        res = self._result_with_untested_reachable()
        # C must be in the untested set with a multi-step reach path.
        u = next(u for u in res.untested_screens if u["id"] == "C")
        self.assertEqual(u["reach_path"], ["home", "feed", "checkout"])

        md = render.render_markdown(res, META)
        # marker present (and the doc leads with it)
        self.assertIn(render.MARKER, md)
        self.assertTrue(md.startswith(render.MARKER))
        # Atlas viewer URL substring
        self.assertIn("app.revyl.ai/apps/", md)
        # the untested section renders the reach path
        self.assertIn("reach it:", md)
        # path screen names show up too
        self.assertIn("home", md)
        self.assertIn("feed", md)
        self.assertIn("checkout", md)
        # "cover it:" hint
        self.assertIn("cover it:", md)

    def test_json_carries_reach_path_and_viewer_urls(self):
        res = self._result_with_untested_reachable()
        j = render.render_json(res, META)

        self.assertTrue(j["untested_screens"])
        u0 = j["untested_screens"][0]
        self.assertIn("reach_path", u0)
        self.assertIsInstance(u0["reach_path"], list)
        self.assertIn("viewer_url", u0)
        self.assertIsNotNone(u0["viewer_url"])
        self.assertIn("app.revyl.ai/apps/", u0["viewer_url"])

        self.assertTrue(j["added"])
        a0 = j["added"][0]
        self.assertIn("viewer_url", a0)
        self.assertIn("app.revyl.ai/apps/", a0["viewer_url"])

    def test_terminal_includes_reach_arrow(self):
        res = self._result_with_untested_reachable()
        term = render.render_terminal(res, META)
        self.assertIsInstance(term, str)
        # render_terminal joins the reach path with arrows
        self.assertIn("home", term)
        self.assertIn("checkout", term)
        self.assertIn("→", term)


# --------------------------------------------------------------------------
# Collapsible <details> when a section exceeds the threshold
# --------------------------------------------------------------------------
class TestCollapsibleSection(unittest.TestCase):
    def test_many_added_screens_use_details(self):
        # 9 new screens (> _COLLAPSE_OVER == 8) => the "New screens" section
        # must be wrapped in a <details> block.
        base = snap([node("home", "home", entry=True)])
        head_nodes = [node("home", "home", entry=True)]
        for i in range(9):
            head_nodes.append(node(f"new{i}", f"new_screen_{i}"))
        head = snap(head_nodes)
        res = diff.diff(base, head)
        self.assertEqual(len(res.added), 9)

        md = render.render_markdown(res, META)
        self.assertIn("<details>", md)
        self.assertIn("</details>", md)
        self.assertGreater(9, render._COLLAPSE_OVER)


if __name__ == "__main__":
    unittest.main()
