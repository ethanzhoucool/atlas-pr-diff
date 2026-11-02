"""Snapshot graph helpers: the cached edge index and the single-BFS
shortest_paths() must give exactly what the old per-call scans gave.

Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import os
import random
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from atlas_diff import model  # noqa: E402


def _reference_shortest_path(snap, target, sources=None):
    """The original per-target implementation, kept as an oracle."""
    if target not in snap.screens:
        return []
    sources = sources or snap.entry_points()
    if target in sources:
        return [target]
    adj = {}
    for e in snap.edges:
        adj.setdefault(e.source, []).append(e.target)
    prev, seen, queue = {}, set(sources), list(sources)
    while queue:
        cur = queue.pop(0)
        for nxt in adj.get(cur, []):
            if nxt in seen:
                continue
            seen.add(nxt)
            prev[nxt] = cur
            if nxt == target:
                path = [target]
                while path[-1] in prev:
                    path.append(prev[path[-1]])
                return list(reversed(path))
            queue.append(nxt)
    return []


def _random_snapshot(rnd, n, m, entries):
    nodes = [{"id": f"s{i}", "semantic_name": f"s{i}", "is_entry_point": i < entries}
             for i in range(n)]
    # random edges: includes self-loops, parallel edges, cycles, dangling targets
    edges = [{"source_entity_id": f"s{rnd.randrange(n)}",
              "target_entity_id": f"s{rnd.randrange(n + 2)}", "observation_count": 1}
             for _ in range(m)]
    return model.from_graph_payload({"nodes": nodes, "edges": edges})


class TestShortestPathsMatchesReference(unittest.TestCase):
    def test_random_graphs(self):
        rnd = random.Random(1234)
        for trial in range(60):
            n = rnd.randint(1, 40)
            snap = _random_snapshot(rnd, n, rnd.randint(0, 3 * n), entries=rnd.randint(0, 3))
            targets = [f"s{i}" for i in range(n + 2)]   # includes unknown ids
            got = snap.shortest_paths(targets)
            for t in targets:
                want = _reference_shortest_path(snap, t)
                self.assertEqual(got.get(t, []), want, (trial, t))
                self.assertEqual(snap.shortest_path(t), want, (trial, t))

    def test_explicit_sources(self):
        rnd = random.Random(99)
        snap = _random_snapshot(rnd, 30, 60, entries=1)
        sources = ["s5", "s9"]
        got = snap.shortest_paths(snap.screens, sources)
        for t in snap.screens:
            self.assertEqual(got.get(t, []), _reference_shortest_path(snap, t, sources))

    def test_empty_graph(self):
        snap = model.from_graph_payload({"nodes": [], "edges": []})
        self.assertEqual(snap.shortest_paths(["x"]), {})
        self.assertEqual(snap.shortest_path("x"), [])
        self.assertEqual(snap.out_edges("x"), [])


class TestEdgeIndex(unittest.TestCase):
    def _snap(self):
        return model.from_graph_payload({
            "nodes": [{"id": i, "semantic_name": i} for i in "abc"],
            "edges": [{"source_entity_id": "a", "target_entity_id": "b"},
                      {"source_entity_id": "a", "target_entity_id": "c"},
                      {"source_entity_id": "b", "target_entity_id": "c"}],
        })

    def test_matches_linear_scan(self):
        s = self._snap()
        for sid in "abcz":
            self.assertEqual(s.out_edges(sid), [e for e in s.edges if e.source == sid])
            self.assertEqual(s.in_edges(sid), [e for e in s.edges if e.target == sid])

    def test_rebuilt_when_edges_change(self):
        s = self._snap()
        self.assertEqual(len(s.out_edges("c")), 0)
        s.edges.append(model.Edge("c", "a", "back", "tap", 1, 0, 0, 0))
        self.assertEqual([e.target for e in s.out_edges("c")], ["a"])
        s.edges = [e for e in s.edges if e.source != "a"]
        self.assertEqual(s.out_edges("a"), [])
        self.assertEqual(s.reachable_from({"b"}), {"a", "b", "c"})

    def test_returned_lists_are_copies(self):
        s = self._snap()
        s.out_edges("a").clear()
        self.assertEqual(len(s.out_edges("a")), 2)

    def test_index_not_part_of_equality_or_repr(self):
        a, b = self._snap(), self._snap()
        a.out_edges("a")          # builds a's index only
        self.assertEqual(a, b)
        self.assertNotIn("_index", repr(a))


if __name__ == "__main__":
    unittest.main()
