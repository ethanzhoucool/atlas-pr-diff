"""Stdlib-only (unittest) tests for atlas_diff.model.

Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from atlas_diff import model  # noqa: E402


def node(id, name, area="Home", kind="screen", desc="", obs=5, actions=()):
    return {
        "id": id,
        "semantic_name": name,
        "display_name": name,
        "label": name,
        "product_area": area,
        "screen_kind": kind,
        "semantic_description": desc,
        "observation_count": obs,
        "is_entry_point": False,
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
        "stats": {"foo": 1},
        "projection": {"requested_build_id": "build-x"},
    }


class TestFromGraphPayload(unittest.TestCase):
    def test_basic_parse(self):
        payload = make_payload(
            [node("a", "home", obs=7), node("b", "settings")],
            [edge("a", "b", obs=5, test=1)],
            [{"id": "f1", "label": "onboarding", "area": "Home", "route_node_ids": ["a", "b"]}],
        )
        s = model.from_graph_payload(payload, build_version="v1.2", git={"sha": "abc"})
        self.assertEqual(s.app_id, "app-1")
        self.assertEqual(set(s.screens), {"a", "b"})
        self.assertEqual(s.build_version, "v1.2")
        self.assertEqual(s.git, {"sha": "abc"})
        self.assertEqual(s.source, "live")
        self.assertEqual(len(s.edges), 1)
        self.assertEqual(len(s.flows), 1)

        a = s.screens["a"]
        self.assertEqual(a.id, "a")
        self.assertEqual(a.name, "home")
        self.assertEqual(a.product_area, "Home")
        self.assertEqual(a.screen_kind, "screen")
        self.assertEqual(a.observation_count, 7)
        self.assertEqual(a.label, "home")

        e = s.edges[0]
        self.assertEqual(e.source, "a")
        self.assertEqual(e.target, "b")
        self.assertEqual(e.test_support, 1)
        self.assertTrue(e.tested)
        self.assertEqual(e.key, ("a", "b"))

    def test_graph_helpers(self):
        s = model.from_graph_payload(make_payload(
            [node("a", "home"), node("b", "mid"), node("c", "leaf")],
            [edge("a", "b"), edge("b", "c")],
        ))
        self.assertEqual([e.target for e in s.out_edges("a")], ["b"])
        self.assertEqual([e.source for e in s.in_edges("c")], ["b"])
        self.assertEqual(s.reachable_from({"a"}), {"a", "b", "c"})
        self.assertEqual(s.reachable_from({"c"}), {"c"})
        self.assertEqual(s.name_of("a"), "home")

    def test_name_of_unknown(self):
        s = model.from_graph_payload(make_payload([node("a", "home")]))
        # unknown id falls back to a truncated id
        self.assertEqual(s.name_of("zzzzzzzzzz"), "zzzzzzzz")


class TestSnapshotRoundTrip(unittest.TestCase):
    def test_save_and_reload(self):
        payload = make_payload(
            [node("a", "home", obs=7), node("b", "settings", area="Profile")],
            [edge("a", "b", obs=5, test=1, report=2), edge("b", "a", obs=3)],
            [{"id": "f1", "label": "onboarding", "area": "Home", "route_node_ids": ["a", "b"]}],
        )
        original = model.from_graph_payload(payload, build_version="v9", git={"sha": "deadbeef"})

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            path = fh.name
        try:
            original.save(path)
            reloaded = model.from_snapshot_file(path)

            self.assertEqual(reloaded.source, "snapshot-file")
            self.assertEqual(set(reloaded.screens), set(original.screens))
            self.assertEqual(len(reloaded.edges), len(original.edges))
            self.assertEqual(reloaded.app_id, original.app_id)
            self.assertEqual(reloaded.build_version, "v9")
            self.assertEqual(reloaded.git, {"sha": "deadbeef"})

            # edges survive round-trip with their support fields
            ekeys_before = sorted((e.source, e.target, e.test_support, e.report_support)
                                  for e in original.edges)
            ekeys_after = sorted((e.source, e.target, e.test_support, e.report_support)
                                 for e in reloaded.edges)
            self.assertEqual(ekeys_before, ekeys_after)

            # flows survive
            self.assertEqual([f.id for f in reloaded.flows], [f.id for f in original.flows])
            self.assertEqual(reloaded.flows[0].route_node_ids, ["a", "b"])
        finally:
            os.unlink(path)

    def test_to_dict_marker(self):
        s = model.from_graph_payload(make_payload([node("a", "home")]))
        d = s.to_dict()
        self.assertEqual(d["_atlas_diff_snapshot"], 1)
        self.assertEqual(d["app_id"], "app-1")
        self.assertEqual(len(d["screens"]), 1)


if __name__ == "__main__":
    unittest.main()
