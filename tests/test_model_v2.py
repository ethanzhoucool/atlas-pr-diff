"""Stdlib-only (unittest) tests for atlas_diff.model v0.2 features.

Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from atlas_diff import model  # noqa: E402


# --------------------------------------------------------------------------
# Synthetic payload helpers (mirrors tests/test_diff.py style)
# --------------------------------------------------------------------------
def node(id, name, area="Home", kind="screen", desc="", obs=5, actions=(),
         entry=False, viewer_url=None, local_screenshot_path=None):
    n = {
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
    if viewer_url is not None:
        n["viewer_url"] = viewer_url
    if local_screenshot_path is not None:
        n["local_screenshot_path"] = local_screenshot_path
    return n


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


# --------------------------------------------------------------------------
# viewer_url construction
# --------------------------------------------------------------------------
class TestViewerUrl(unittest.TestCase):
    def test_viewer_url_built_from_app_and_id(self):
        s = snap([node("scr-1", "home")], app_id="app-42")
        sc = s.screens["scr-1"]
        self.assertEqual(
            sc.viewer_url,
            model.ATLAS_VIEWER.format(app="app-42", sid="scr-1"),
        )
        # sanity: it embeds the app id and screen id
        self.assertIn("app-42", sc.viewer_url)
        self.assertIn("scr-1", sc.viewer_url)

    def test_existing_viewer_url_preserved(self):
        custom = "https://example.com/custom-link"
        s = snap([node("scr-1", "home", viewer_url=custom)], app_id="app-42")
        self.assertEqual(s.screens["scr-1"].viewer_url, custom)


# --------------------------------------------------------------------------
# entry_points
# --------------------------------------------------------------------------
class TestEntryPoints(unittest.TestCase):
    def test_flagged_entry_point(self):
        s = snap(
            [node("a", "home", entry=True), node("b", "other")],
            [edge("a", "b")],
        )
        self.assertEqual(s.entry_points(), ["a"])

    def test_roots_when_none_flagged(self):
        # a -> b -> c : a is never an edge target, so it is the root.
        s = snap(
            [node("a", "home"), node("b", "mid"), node("c", "leaf")],
            [edge("a", "b"), edge("b", "c")],
        )
        self.assertEqual(s.entry_points(), ["a"])


# --------------------------------------------------------------------------
# shortest_path
# --------------------------------------------------------------------------
class TestShortestPath(unittest.TestCase):
    def _chain(self):
        # A -> B -> C, A is the flagged entry.
        return snap(
            [node("A", "a", entry=True), node("B", "b"), node("C", "c")],
            [edge("A", "B"), edge("B", "C")],
        )

    def test_full_chain(self):
        s = self._chain()
        self.assertEqual(s.shortest_path("C"), ["A", "B", "C"])

    def test_entry_returns_itself(self):
        s = self._chain()
        self.assertEqual(s.shortest_path("A"), ["A"])

    def test_unreachable_returns_empty(self):
        # D exists but nothing leads to it, and it is not an entry point.
        s = snap(
            [node("A", "a", entry=True), node("B", "b"), node("D", "d")],
            [edge("A", "B")],
        )
        self.assertEqual(s.shortest_path("D"), [])

    def test_unknown_target_returns_empty(self):
        s = self._chain()
        self.assertEqual(s.shortest_path("not-a-screen"), [])


# --------------------------------------------------------------------------
# viewer_of
# --------------------------------------------------------------------------
class TestViewerOf(unittest.TestCase):
    def test_known_id(self):
        s = snap([node("a", "home")], app_id="app-9")
        self.assertEqual(s.viewer_of("a"), s.screens["a"].viewer_url)
        self.assertIn("app-9", s.viewer_of("a"))

    def test_unknown_id_returns_none(self):
        s = snap([node("a", "home")])
        self.assertIsNone(s.viewer_of("nope"))


# --------------------------------------------------------------------------
# local_screenshot_path carried onto the Screen
# --------------------------------------------------------------------------
class TestLocalScreenshotPath(unittest.TestCase):
    def test_local_path_carried(self):
        s = snap([node("a", "home", local_screenshot_path="/tmp/a.png")])
        self.assertEqual(s.screens["a"].local_screenshot_path, "/tmp/a.png")

    def test_local_path_defaults_none(self):
        s = snap([node("a", "home")])
        self.assertIsNone(s.screens["a"].local_screenshot_path)


if __name__ == "__main__":
    unittest.main()
