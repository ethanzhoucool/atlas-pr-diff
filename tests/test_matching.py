"""Screen matching across builds: id churn with duplicate names, unnamed
screens, and screens that moved product area.

Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from atlas_diff import diff, model  # noqa: E402


def node(id, name, area="Home", kind="screen", desc="", actions=()):
    return {"id": id, "semantic_name": name, "product_area": area, "screen_kind": kind,
            "semantic_description": desc, "observation_count": 5,
            "primary_actions": list(actions)}


def snap(nodes):
    return model.from_graph_payload({"app_id": "app", "nodes": list(nodes), "edges": []})


def ids(res):
    return {
        "added": sorted(s.id for s in res.added),
        "removed": sorted(s.id for s in res.removed),
        "changed": sorted(c.screen_id for c in res.changed),
    }


class TestDuplicateNames(unittest.TestCase):
    def test_two_same_named_screens_both_survive_id_churn(self):
        base = snap([node("a1", "settings", desc="app settings"),
                     node("a2", "settings", desc="ride settings")])
        head = snap([node("b1", "settings", desc="app settings"),
                     node("b2", "settings", desc="ride settings")])
        res = diff.diff(base, head)
        # used to be: b2 added + a2 removed
        self.assertEqual(ids(res), {"added": [], "removed": [], "changed": []})

    def test_same_named_screens_pair_with_their_look_alike(self):
        # head order is the reverse of base order; pairing by position would
        # report both as "description changed"
        base = snap([node("a1", "settings", kind="list", desc="app settings"),
                     node("a2", "settings", kind="form", desc="ride settings")])
        head = snap([node("b2", "settings", kind="form", desc="ride settings"),
                     node("b1", "settings", kind="list", desc="app settings")])
        res = diff.diff(base, head)
        self.assertEqual(ids(res), {"added": [], "removed": [], "changed": []})

    def test_extra_same_named_screen_is_added(self):
        base = snap([node("a1", "settings")])
        head = snap([node("b1", "settings"), node("b2", "settings", desc="new one")])
        res = diff.diff(base, head)
        self.assertEqual(len(res.added), 1)
        self.assertEqual(res.removed, [])


class TestUnnamedScreens(unittest.TestCase):
    def test_unnamed_screens_are_not_matched_to_each_other(self):
        base = snap([node("a1", "", kind="list")])
        head = snap([node("b1", "", kind="form")])
        res = diff.diff(base, head)
        # used to be: "changed: kind list -> form" between two unrelated screens
        self.assertEqual(ids(res), {"added": ["b1"], "removed": ["a1"], "changed": []})

    def test_unnamed_screen_still_matches_by_id(self):
        base = snap([node("a1", "", kind="list")])
        head = snap([node("a1", "", kind="form")])
        res = diff.diff(base, head)
        self.assertEqual(ids(res)["changed"], ["a1"])


class TestMovedScreens(unittest.TestCase):
    def test_area_move_with_id_churn_is_a_change(self):
        base = snap([node("home", "home"), node("a1", "trip_receipt", area="Home", kind="detail")])
        head = snap([node("home", "home"), node("b1", "trip_receipt", area="Activity", kind="detail")])
        res = diff.diff(base, head)
        self.assertEqual(ids(res), {"added": [], "removed": [], "changed": ["b1"]})
        self.assertIn("area `Home` → `Activity`", res.changed[0].reasons)
        self.assertEqual(res.changed[0].base_id, "a1")

    def test_ambiguous_cross_area_name_is_not_guessed(self):
        base = snap([node("a1", "search_results", area="Rides", kind="list")])
        head = snap([node("b1", "search_results", area="Eats", kind="list"),
                     node("b2", "search_results", area="Shops", kind="list")])
        res = diff.diff(base, head)
        self.assertEqual(ids(res), {"added": ["b1", "b2"], "removed": ["a1"], "changed": []})

    def test_cross_area_name_needs_same_kind(self):
        base = snap([node("a1", "settings", area="Rides", kind="list")])
        head = snap([node("b1", "settings", area="Eats", kind="form")])
        res = diff.diff(base, head)
        self.assertEqual(ids(res), {"added": ["b1"], "removed": ["a1"], "changed": []})

    def test_same_area_match_wins_over_cross_area(self):
        base = snap([node("a1", "settings", area="Rides"), node("a2", "settings", area="Eats")])
        head = snap([node("b2", "settings", area="Eats")])
        res = diff.diff(base, head)
        self.assertEqual(ids(res), {"added": [], "removed": ["a1"], "changed": []})


class TestIdMatchPrecedence(unittest.TestCase):
    def test_id_match_beats_name_match(self):
        base = snap([node("a1", "home"), node("a2", "home_v2")])
        head = snap([node("a1", "home_v2")])   # a1 renamed to a2's old name
        res = diff.diff(base, head)
        self.assertEqual([c.screen_id for c in res.renamed], ["a1"])
        self.assertEqual([s.id for s in res.removed], ["a2"])


if __name__ == "__main__":
    unittest.main()
