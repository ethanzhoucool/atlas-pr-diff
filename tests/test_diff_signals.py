"""False-positive guards for the lost-coverage, edge-diff and orphan signals.

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


def node(id, name, area="Home", entry=False):
    return {"id": id, "semantic_name": name, "product_area": area,
            "screen_kind": "screen", "observation_count": 5, "is_entry_point": entry}


def edge(src, tgt, label="tap", obs=5, test=0):
    return {"source_entity_id": src, "target_entity_id": tgt, "action_label": label,
            "action_type": "tap", "observation_count": obs, "test_support": test}


def snap(nodes=(), edges=()):
    return model.from_graph_payload({"app_id": "app", "nodes": list(nodes),
                                     "edges": list(edges)})


HOME_ACCT = [node("home", "home"), node("acct", "account_profile_hub")]


class TestLostCoverageParallelEdges(unittest.TestCase):
    """Atlas keeps several edges for one transition when the exploration
    describes the same tap in different words (the shipped Ubert baseline
    has 85 tested edges over only 67 distinct transitions)."""

    def test_reworded_tap_still_tested_is_not_lost(self):
        base = snap(HOME_ACCT, [edge("home", "acct", "the 'Account' tab", test=2)])
        head = snap(HOME_ACCT, [
            edge("home", "acct", "the 'Account' icon in the bottom bar", test=1),
            edge("home", "acct", "a person icon at the bottom right", test=0),
        ])
        res = diff.diff(base, head)
        self.assertEqual(res.lost_coverage_edges, [])

    def test_lost_transition_reported_once(self):
        base = snap(HOME_ACCT, [
            edge("home", "acct", "the 'Account' tab", test=1),
            edge("home", "acct", "the 'Account' icon", test=1),
            edge("home", "acct", "the person icon", test=1),
        ])
        head = snap(HOME_ACCT, [edge("home", "acct", "the 'Account' tab", test=0)])
        res = diff.diff(base, head)
        self.assertEqual([(e.source, e.target) for e in res.lost_coverage_edges],
                         [("home", "acct")])
        self.assertEqual(res.summary_counts()["lost_coverage_edges"], 1)

    def test_lost_coverage_through_id_churn(self):
        # head re-ids both screens (matched by name); coverage still lost
        base = snap(HOME_ACCT, [edge("home", "acct", test=1)])
        head = snap([node("home2", "home"), node("acct2", "account_profile_hub")],
                    [edge("home2", "acct2", test=0)])
        res = diff.diff(base, head)
        self.assertEqual(len(res.lost_coverage_edges), 1)

    def test_coverage_kept_through_id_churn(self):
        base = snap(HOME_ACCT, [edge("home", "acct", test=1)])
        head = snap([node("home2", "home"), node("acct2", "account_profile_hub")],
                    [edge("home2", "acct2", "reworded", test=0),
                     edge("home2", "acct2", test=3)])
        res = diff.diff(base, head)
        self.assertEqual(res.lost_coverage_edges, [])


class TestEdgeDiffCountsTransitions(unittest.TestCase):
    def test_parallel_new_edges_count_once(self):
        nodes = HOME_ACCT + [node("help", "help")]
        base = snap(nodes, [edge("home", "acct")])
        head = snap(nodes, [edge("home", "acct"),
                            edge("acct", "help", "Help row"),
                            edge("acct", "help", "the row labeled Help"),
                            edge("acct", "help", "question mark icon")])
        res = diff.diff(base, head)
        self.assertEqual([(e.source, e.target) for e in res.edges_added], [("acct", "help")])
        self.assertEqual(res.edges_removed, [])

    def test_parallel_removed_edges_count_once(self):
        nodes = HOME_ACCT
        base = snap(nodes, [edge("home", "acct", "a"), edge("home", "acct", "b")])
        head = snap(nodes)
        res = diff.diff(base, head)
        self.assertEqual(len(res.edges_removed), 1)
        self.assertEqual(res.edges_added, [])


class TestOrphanedFalsePositives(unittest.TestCase):
    def test_entry_point_is_never_orphaned(self):
        # base: login -> home -> logout -> login. head: logout removed, so
        # login lost its only inbound edge, but it is the app's entry point.
        base = snap([node("login", "login", entry=True), node("home", "home"),
                     node("logout", "logout")],
                    [edge("login", "home"), edge("home", "logout"), edge("logout", "login")])
        head = snap([node("login", "login", entry=True), node("home", "home")],
                    [edge("login", "home")])
        res = diff.diff(base, head)
        self.assertEqual(res.orphaned_screens, [])

    def test_self_loop_is_not_an_inbound_path(self):
        # base: menu -> filters (filters also refreshes itself). head: menu removed.
        base = snap([node("menu", "menu"), node("filters", "filters")],
                    [edge("menu", "filters"), edge("filters", "filters", "refresh")])
        head = snap([node("filters", "filters")],
                    [edge("filters", "filters", "refresh")])
        res = diff.diff(base, head)
        self.assertEqual([o["id"] for o in res.orphaned_screens], ["filters"])

    def test_screen_with_another_way_in_is_not_orphaned(self):
        base = snap([node("menu", "menu"), node("home", "home"), node("filters", "filters")],
                    [edge("menu", "filters"), edge("home", "filters")])
        head = snap([node("home", "home"), node("filters", "filters")],
                    [edge("home", "filters")])
        res = diff.diff(base, head)
        self.assertEqual(res.orphaned_screens, [])


if __name__ == "__main__":
    unittest.main()
