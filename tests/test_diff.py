"""Stdlib-only (unittest) tests for atlas_diff.diff and atlas_diff.render.

Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import os
import sys
import unittest

# Make `from atlas_diff import ...` work when run from the repo root.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from atlas_diff import diff, model, render  # noqa: E402


# --------------------------------------------------------------------------
# Synthetic payload helpers
# --------------------------------------------------------------------------
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


def edge(src, tgt, label="tap", obs=5, test=0, report=0, session=0, action_type="tap"):
    return {
        "source_entity_id": src,
        "target_entity_id": tgt,
        "action_label": label,
        "action_type": action_type,
        "observation_count": obs,
        "test_support": test,
        "report_support": report,
        "session_support": session,
    }


def flow(id, label, area="Home", route=()):
    return {"id": id, "label": label, "area": area, "route_node_ids": list(route)}


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


def reasons_text(changes):
    out = []
    for c in changes:
        out.extend(c.reasons)
    return " || ".join(out)


# --------------------------------------------------------------------------
# 1. Added / removed screens
# --------------------------------------------------------------------------
class TestAddedRemoved(unittest.TestCase):
    def test_added_screen(self):
        base = snap([node("a", "home")])
        head = snap([node("a", "home"), node("b", "settings")])
        res = diff.diff(base, head)
        self.assertEqual([s.id for s in res.added], ["b"])
        self.assertEqual(res.removed, [])
        self.assertTrue(res.has_changes)

    def test_removed_screen(self):
        base = snap([node("a", "home"), node("b", "settings")])
        head = snap([node("a", "home")])
        res = diff.diff(base, head)
        self.assertEqual([s.id for s in res.removed], ["b"])
        self.assertEqual(res.added, [])
        self.assertTrue(res.has_changes)


# --------------------------------------------------------------------------
# 2. Changed screen (semantic)
# --------------------------------------------------------------------------
class TestSemanticChange(unittest.TestCase):
    def test_kind_change(self):
        base = snap([node("a", "home", kind="list")])
        head = snap([node("a", "home", kind="detail")])
        res = diff.diff(base, head)
        ids = [c.screen_id for c in res.changed]
        self.assertIn("a", ids)
        self.assertEqual(res.nav_churn, [])
        self.assertIn("kind", reasons_text(res.changed))

    def test_description_change(self):
        base = snap([node("a", "home", desc="the landing page")])
        head = snap([node("a", "home", desc="a completely different purpose")])
        res = diff.diff(base, head)
        self.assertIn("a", [c.screen_id for c in res.changed])
        self.assertIn("purpose/description changed", reasons_text(res.changed))
        self.assertEqual(res.nav_churn, [])

    def test_area_change(self):
        base = snap([node("a", "home", area="Home")])
        head = snap([node("a", "home", area="Profile")])
        res = diff.diff(base, head)
        self.assertIn("a", [c.screen_id for c in res.changed])
        self.assertIn("area", reasons_text(res.changed))


# --------------------------------------------------------------------------
# 3. Wiring change to a new / removed screen
# --------------------------------------------------------------------------
class TestWiringChange(unittest.TestCase):
    def test_now_navigates_to_new_screen(self):
        # base: a exists, no edges. head: a gains a significant edge to new screen b.
        base = snap([node("a", "home")])
        head = snap(
            [node("a", "home"), node("b", "new_screen")],
            [edge("a", "b", obs=5)],
        )
        res = diff.diff(base, head)
        self.assertIn("a", [c.screen_id for c in res.changed])
        self.assertIn("now navigates to new screen", reasons_text(res.changed))

    def test_no_longer_navigates_to_removed_screen(self):
        # base: a -> b (significant). head: b removed entirely, a stays.
        base = snap(
            [node("a", "home"), node("b", "gone")],
            [edge("a", "b", obs=5)],
        )
        head = snap([node("a", "home")])
        res = diff.diff(base, head)
        self.assertIn("a", [c.screen_id for c in res.changed])
        self.assertIn("no longer navigates to removed screen", reasons_text(res.changed))


# --------------------------------------------------------------------------
# 4. Renamed
# --------------------------------------------------------------------------
class TestRenamed(unittest.TestCase):
    def test_pure_rename(self):
        # same id, only semantic_name differs; everything else identical.
        base = snap([node("a", "old_name", area="Home", kind="screen", desc="d")])
        head = snap([node("a", "new_name", area="Home", kind="screen", desc="d")])
        res = diff.diff(base, head)
        ren_ids = [c.screen_id for c in res.renamed]
        self.assertIn("a", ren_ids)
        self.assertNotIn("a", [c.screen_id for c in res.changed])
        self.assertIn("renamed", res.renamed[0].reasons[0])


# --------------------------------------------------------------------------
# 5. Nav churn vs noise threshold
# --------------------------------------------------------------------------
class TestNavChurnAndNoise(unittest.TestCase):
    def test_single_low_support_edge_is_noise(self):
        # head adds ONE low-support (obs=1, no test/report) nav edge to an
        # existing screen. It is filtered as noise => not changed, not nav_churn.
        nodes = [node("a", "home"), node("b", "other")]
        base = snap(nodes)
        head = snap(nodes, [edge("a", "b", obs=1, test=0, report=0)])
        res = diff.diff(base, head)
        self.assertEqual(res.changed, [])
        self.assertEqual(res.nav_churn, [])

    def test_many_reroutes_among_existing_is_nav_churn(self):
        # 'a' reroutes from {b,c,d} to {e,f,g} -- all existing, matched screens.
        # No new/removed wiring, no semantic change => net_nav=6 >= threshold.
        existing = [node(x, x) for x in ("a", "b", "c", "d", "e", "f", "g")]
        base_edges = [edge("a", "b"), edge("a", "c"), edge("a", "d")]
        head_edges = [edge("a", "e"), edge("a", "f"), edge("a", "g")]
        base = snap(existing, base_edges)
        head = snap(existing, head_edges)
        res = diff.diff(base, head)
        self.assertIn("a", [c.screen_id for c in res.nav_churn])
        self.assertNotIn("a", [c.screen_id for c in res.changed])
        self.assertGreaterEqual(diff.NAV_CHURN_THRESHOLD, 3)


# --------------------------------------------------------------------------
# 6. min_support filtering of edges_added / edges_removed
# --------------------------------------------------------------------------
class TestMinSupportFiltering(unittest.TestCase):
    def test_low_support_edge_ignored(self):
        nodes = [node("a", "home"), node("b", "other")]
        base = snap(nodes)
        head = snap(nodes, [edge("a", "b", obs=1, test=0, report=0)])
        res = diff.diff(base, head, min_support=2)
        keys = [(e.source, e.target) for e in res.edges_added]
        self.assertNotIn(("a", "b"), keys)

    def test_high_support_edge_counted(self):
        nodes = [node("a", "home"), node("b", "other")]
        base = snap(nodes)
        head = snap(nodes, [edge("a", "b", obs=5, test=0, report=0)])
        res = diff.diff(base, head, min_support=2)
        keys = [(e.source, e.target) for e in res.edges_added]
        self.assertIn(("a", "b"), keys)

    def test_report_support_makes_edge_significant(self):
        nodes = [node("a", "home"), node("b", "other")]
        base = snap(nodes)
        head = snap(nodes, [edge("a", "b", obs=1, test=0, report=1)])
        res = diff.diff(base, head, min_support=2)
        keys = [(e.source, e.target) for e in res.edges_added]
        self.assertIn(("a", "b"), keys)

    def test_test_support_makes_edge_significant(self):
        nodes = [node("a", "home"), node("b", "other")]
        base = snap(nodes)
        head = snap(nodes, [edge("a", "b", obs=1, test=1, report=0)])
        res = diff.diff(base, head, min_support=2)
        keys = [(e.source, e.target) for e in res.edges_added]
        self.assertIn(("a", "b"), keys)


# --------------------------------------------------------------------------
# 7. Now untested
# --------------------------------------------------------------------------
class TestNowUntested(unittest.TestCase):
    def test_new_screen_only_reached_by_untested_edges(self):
        base = snap([node("a", "home")])
        head = snap(
            [node("a", "home"), node("b", "new_screen")],
            [edge("a", "b", obs=5, test=0)],
        )
        res = diff.diff(base, head)
        untested_ids = [u["id"] for u in res.untested_screens]
        self.assertIn("b", untested_ids)
        u = next(u for u in res.untested_screens if u["id"] == "b")
        self.assertEqual(u["status"], "new")
        self.assertTrue(res.has_untested)
        # render should mention the untested screen by its label.
        md = render.render_markdown(res, META)
        self.assertIn("new_screen", md)
        self.assertIn("Now untested", md)

    def test_tested_inbound_edge_means_not_untested(self):
        base = snap([node("a", "home")])
        head = snap(
            [node("a", "home"), node("b", "new_screen")],
            [edge("a", "b", obs=5, test=1)],
        )
        res = diff.diff(base, head)
        self.assertNotIn("b", [u["id"] for u in res.untested_screens])
        self.assertFalse(res.has_untested)


# --------------------------------------------------------------------------
# 8. Orphaned
# --------------------------------------------------------------------------
class TestOrphaned(unittest.TestCase):
    def test_orphaned_via_removed(self):
        # base: x -> y (significant), y has no other inbound.
        # head: x removed entirely, y still present with no inbound.
        base = snap(
            [node("x", "entry"), node("y", "target")],
            [edge("x", "y", obs=5)],
        )
        head = snap([node("y", "target")])
        res = diff.diff(base, head)
        orphan_ids = [o["id"] for o in res.orphaned_screens]
        self.assertIn("y", orphan_ids)
        o = next(o for o in res.orphaned_screens if o["id"] == "y")
        self.assertEqual(o["via_removed"], "entry")


# --------------------------------------------------------------------------
# 9. Lost coverage
# --------------------------------------------------------------------------
class TestLostCoverage(unittest.TestCase):
    def test_tested_edge_gone_in_head(self):
        # base: a -> b tested. head: edge gone entirely.
        base = snap(
            [node("a", "home"), node("b", "other")],
            [edge("a", "b", obs=5, test=1)],
        )
        head = snap([node("a", "home"), node("b", "other")])
        res = diff.diff(base, head)
        lost = [(e.source, e.target) for e in res.lost_coverage_edges]
        self.assertIn(("a", "b"), lost)

    def test_tested_edge_now_untested_in_head(self):
        base = snap(
            [node("a", "home"), node("b", "other")],
            [edge("a", "b", obs=5, test=1)],
        )
        head = snap(
            [node("a", "home"), node("b", "other")],
            [edge("a", "b", obs=5, test=0)],
        )
        res = diff.diff(base, head)
        lost = [(e.source, e.target) for e in res.lost_coverage_edges]
        self.assertIn(("a", "b"), lost)

    def test_still_tested_means_no_lost_coverage(self):
        base = snap(
            [node("a", "home"), node("b", "other")],
            [edge("a", "b", obs=5, test=1)],
        )
        head = snap(
            [node("a", "home"), node("b", "other")],
            [edge("a", "b", obs=5, test=1)],
        )
        res = diff.diff(base, head)
        self.assertEqual(res.lost_coverage_edges, [])


# --------------------------------------------------------------------------
# 10. Missing-data warnings
# --------------------------------------------------------------------------
class TestMissingDataWarnings(unittest.TestCase):
    def test_empty_base_warns(self):
        base = snap([])
        head = snap([node("a", "home")])
        res = diff.diff(base, head)
        self.assertTrue(any("Base snapshot has 0 screens" in w for w in res.warnings))

    def test_empty_head_warns(self):
        base = snap([node("a", "home")])
        head = snap([])
        res = diff.diff(base, head)
        self.assertTrue(any("0 screens" in w and "not mapped" in w for w in res.warnings))

    def test_renderers_handle_missing_data(self):
        base = snap([])
        head = snap([node("a", "home")])
        res = diff.diff(base, head)
        # No exceptions, and verdict reflects "Atlas data missing".
        term = render.render_terminal(res, META)
        self.assertIsInstance(term, str)
        self.assertIn("Atlas data missing", term)
        j = render.render_json(res, META)
        self.assertEqual(j["verdict"], "Atlas data missing")
        md = render.render_markdown(res, META)
        self.assertIn("Atlas data missing", md)


# --------------------------------------------------------------------------
# 11. Match across id churn
# --------------------------------------------------------------------------
class TestIdChurnMatch(unittest.TestCase):
    def test_same_name_area_different_id_is_matched(self):
        # different id but same semantic_name + product_area => same screen.
        base = snap([node("old-id", "checkout", area="Cart", kind="form", desc="d")])
        head = snap([node("new-id", "checkout", area="Cart", kind="form", desc="d")])
        res = diff.diff(base, head)
        # not added and not removed (it's the same screen, no real change)
        self.assertEqual(res.added, [])
        self.assertEqual(res.removed, [])

    def test_id_churn_with_real_change_is_changed(self):
        base = snap([node("old-id", "checkout", area="Cart", kind="form", desc="old")])
        head = snap([node("new-id", "checkout", area="Cart", kind="detail", desc="brand new purpose")])
        res = diff.diff(base, head)
        self.assertEqual(res.added, [])
        self.assertEqual(res.removed, [])
        ids = [c.screen_id for c in res.changed]
        self.assertIn("new-id", ids)
        ch = next(c for c in res.changed if c.screen_id == "new-id")
        self.assertEqual(ch.base_id, "old-id")


# --------------------------------------------------------------------------
# 13. render smoke (the render-only assertions)
# --------------------------------------------------------------------------
class TestRenderSmoke(unittest.TestCase):
    def _nontrivial_result(self):
        base = snap([node("a", "home")])
        head = snap(
            [node("a", "home"), node("b", "new_screen")],
            [edge("a", "b", obs=5, test=0)],
        )
        return diff.diff(base, head)

    def test_markdown_starts_with_marker(self):
        res = self._nontrivial_result()
        md = render.render_markdown(res, META)
        self.assertTrue(md.startswith(render.MARKER))
        self.assertIn(render.MARKER, md)

    def test_json_has_documented_keys(self):
        res = self._nontrivial_result()
        j = render.render_json(res, META)
        self.assertIsInstance(j, dict)
        for key in (
            "app", "base", "head", "verdict", "counts", "warnings",
            "added", "removed", "changed", "renamed", "nav_churn",
            "untested_screens", "affected_flows", "orphaned_screens",
            "lost_coverage_edges",
        ):
            self.assertIn(key, j)

    def test_terminal_returns_str(self):
        res = self._nontrivial_result()
        self.assertIsInstance(render.render_terminal(res, META), str)

    def test_identical_base_head_no_exceptions(self):
        nodes = [node("a", "home"), node("b", "other")]
        edges = [edge("a", "b", obs=5)]
        base = snap(nodes, edges)
        head = snap(nodes, edges)
        res = diff.diff(base, head)
        self.assertFalse(res.has_changes)
        # all three renderers run clean on an empty diff
        md = render.render_markdown(res, META)
        self.assertIn(render.MARKER, md)
        self.assertIn("structurally identical", md)
        self.assertIsInstance(render.render_json(res, META), dict)
        self.assertIsInstance(render.render_terminal(res, META), str)
        self.assertEqual(render.render_json(res, META)["verdict"], "No Atlas map changes")


if __name__ == "__main__":
    unittest.main()
