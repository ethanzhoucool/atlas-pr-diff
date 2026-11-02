"""Same inputs must give byte-identical output on every run, or the sticky PR
comment is re-edited (and reshuffled) on each CI rerun.

Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import os
import subprocess
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from atlas_diff import diff, model  # noqa: E402

# One hub that gains links to eight new screens, plus duplicate-named
# screens; rendered as Markdown + JSON.
_SCRIPT = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from atlas_diff import diff, model, render

def node(i, name, area="Home"):
    return {"id": i, "semantic_name": name, "product_area": area, "observation_count": 5}

def edge(s, t):
    return {"source_entity_id": s, "target_entity_id": t, "observation_count": 5}

new = ["n%d" % i for i in range(8)]
base = model.from_graph_payload({"app_id": "a", "nodes": [node("hub", "hub")], "edges": []})
head = model.from_graph_payload({
    "app_id": "a",
    "nodes": [node("hub", "hub")] + [node(n, "screen_" + n) for n in new]
             + [node("dup-b", "dup"), node("dup-a", "dup")],
    "edges": [edge("hub", n) for n in new],
})
res = diff.diff(base, head)
meta = {"base_label": "b", "head_label": "h", "app": "a"}
print(render.render_markdown(res, meta))
print(json.dumps(render.render_json(res, meta), sort_keys=True))
"""


def _run(seed: str) -> str:
    env = dict(os.environ, PYTHONHASHSEED=seed)
    return subprocess.run([sys.executable, "-c", _SCRIPT, _REPO_ROOT], env=env,
                          capture_output=True, text=True, check=True).stdout


class TestHashSeedIndependence(unittest.TestCase):
    def test_output_identical_across_hash_seeds(self):
        outputs = {seed: _run(seed) for seed in ("0", "1", "2", "3", "4", "5")}
        first = outputs["0"]
        self.assertIn("now navigates to new screen", first)
        for seed, out in outputs.items():
            self.assertEqual(out, first, f"output differs under PYTHONHASHSEED={seed}")


class TestReasonOrder(unittest.TestCase):
    def test_new_screen_reasons_sorted_by_name(self):
        def node(i, name):
            return {"id": i, "semantic_name": name, "product_area": "Home", "observation_count": 5}
        base = model.from_graph_payload({"nodes": [node("hub", "hub")]})
        head = model.from_graph_payload({
            "nodes": [node("hub", "hub"), node("x", "zeta"), node("y", "alpha"), node("z", "mid")],
            "edges": [{"source_entity_id": "hub", "target_entity_id": t, "observation_count": 5}
                      for t in ("x", "y", "z")],
        })
        res = diff.diff(base, head)
        self.assertEqual(res.changed[0].reasons, [
            "now navigates to new screen `alpha`",
            "now navigates to new screen `mid`",
            "now navigates to new screen `zeta`",
        ])

    def test_same_named_added_screens_ordered_by_id(self):
        def node(i):
            return {"id": i, "semantic_name": "dup", "product_area": "Home", "observation_count": 5}
        base = model.from_graph_payload({"nodes": []})
        for order in (["b", "a", "c"], ["c", "b", "a"]):
            head = model.from_graph_payload({"nodes": [node(i) for i in order]})
            self.assertEqual([s.id for s in diff.diff(base, head).added], ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
