"""The CI gate (`diff --fail-on`), its exit code, and the Check Run conclusion
must agree. Runs `atlas-diff diff` end-to-end on two committed-baseline style
snapshot files, so no Revyl call is made.

Run from the repo root:
    python3 -m unittest discover -s tests -v
"""

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from atlas_diff import cli, model  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "post_check", os.path.join(_REPO_ROOT, "github", "post_check.py"))
post_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(post_check)


def node(id, name, area="Home"):
    return {"id": id, "semantic_name": name, "product_area": area,
            "screen_kind": "screen", "observation_count": 5}


def edge(src, tgt, test=0):
    return {"source_entity_id": src, "target_entity_id": tgt, "action_label": "tap",
            "observation_count": 5, "test_support": test}


HOME = node("home", "home")
SETTINGS = node("settings", "settings")
TESTED = [edge("home", "settings", test=1)]


class GateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _snap(self, name, nodes, edges=()):
        path = os.path.join(self.tmp, name)
        model.from_graph_payload({"app_id": "app", "nodes": list(nodes),
                                  "edges": list(edges)}).save(path)
        return path

    def run_diff(self, base_nodes, head_nodes, base_edges=(), head_edges=(),
                 fail_on=None, config_text=None):
        base = self._snap("base.json", base_nodes, base_edges)
        head = self._snap("head.json", head_nodes, head_edges)
        out_json = os.path.join(self.tmp, "result.json")
        conf = os.path.join(self.tmp, ".atlas-diff.yml")
        if config_text is not None:
            with open(conf, "w") as fh:
                fh.write(config_text)
        argv = ["--config", conf, "diff", "--app", "app", "--base", base,
                "--head", head, "--json-out", out_json, "-q"]
        if fail_on:
            argv += ["--fail-on", fail_on]
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = cli.main(argv)
        result = {}
        if os.path.exists(out_json):
            with open(out_json) as fh:
                result = json.load(fh)
        return code, result, err.getvalue()


class TestGateAndCheckAgree(GateCase):
    def assertAgree(self, code, result):
        """failure <=> non-zero exit; never failure on a passing gate."""
        conclusion = post_check.conclusion_for(result)
        self.assertEqual(conclusion == "failure", code == 1, (code, conclusion, result))
        return conclusion

    def test_untested_under_fail_on_none_is_not_a_red_check(self):
        code, result, _ = self.run_diff([HOME], [HOME, SETTINGS], fail_on="none")
        self.assertEqual(result["verdict"], "New/changed screens are untested")
        self.assertEqual(code, 0)
        self.assertEqual(result["gate"], {"fail_on": "none", "failed": False})
        self.assertEqual(self.assertAgree(code, result), "neutral")

    def test_untested_under_default_gate_fails(self):
        code, result, _ = self.run_diff([HOME], [HOME, SETTINGS])
        self.assertEqual(code, 1)
        self.assertEqual(result["gate"], {"fail_on": "untested", "failed": True})
        self.assertEqual(self.assertAgree(code, result), "failure")

    def test_change_under_fail_on_changes_is_a_failing_check(self):
        # settings removed; nothing new, so nothing untested
        code, result, _ = self.run_diff([HOME, SETTINGS], [HOME], fail_on="changes")
        self.assertEqual(result["verdict"], "Map changed — review impact")
        self.assertEqual(code, 1)
        self.assertEqual(self.assertAgree(code, result), "failure")

    def test_change_under_default_gate_passes_neutral(self):
        code, result, _ = self.run_diff([HOME, SETTINGS], [HOME])
        self.assertEqual(code, 0)
        self.assertEqual(self.assertAgree(code, result), "neutral")

    def test_tested_new_screen_passes_default_gate(self):
        code, result, _ = self.run_diff([HOME], [HOME, SETTINGS], head_edges=TESTED)
        self.assertEqual(result["verdict"], "Map changed — review impact")
        self.assertEqual(code, 0)
        self.assertAgree(code, result)

    def test_no_changes_is_success(self):
        code, result, _ = self.run_diff([HOME, SETTINGS], [HOME, SETTINGS], fail_on="changes")
        self.assertEqual(code, 0)
        self.assertEqual(self.assertAgree(code, result), "success")


class TestMissingDataNeverFails(GateCase):
    def test_unmapped_head_under_fail_on_changes(self):
        # every base screen looks "removed", which used to trip --fail-on changes
        code, result, _ = self.run_diff([HOME, SETTINGS], [], fail_on="changes")
        self.assertEqual(result["verdict"], "Atlas data missing")
        self.assertEqual(code, 0)
        self.assertEqual(post_check.conclusion_for(result), "neutral")

    def test_unmapped_base_under_default_gate(self):
        # every head screen looks "added" and untested, which used to exit 1
        code, result, _ = self.run_diff([], [HOME, SETTINGS])
        self.assertEqual(result["verdict"], "Atlas data missing")
        self.assertEqual(code, 0)
        self.assertEqual(post_check.conclusion_for(result), "neutral")


class TestFailOnFromConfig(GateCase):
    def test_typo_is_rejected_instead_of_disabling_the_gate(self):
        code, result, err = self.run_diff([HOME], [HOME, SETTINGS],
                                          config_text="app: app\nfail_on: untestd\n")
        self.assertEqual(code, 2)
        self.assertIn("untestd", err)
        self.assertIn("untested", err)
        self.assertEqual(result, {})   # bailed out before diffing

    def test_case_and_whitespace_are_normalized(self):
        code, result, _ = self.run_diff([HOME], [HOME, SETTINGS],
                                        config_text="fail_on: Untested \n")
        self.assertEqual(code, 1)
        self.assertEqual(result["gate"]["fail_on"], "untested")

    def test_cli_flag_overrides_config(self):
        code, _, _ = self.run_diff([HOME], [HOME, SETTINGS], fail_on="none",
                                   config_text="fail_on: untested\n")
        self.assertEqual(code, 0)


class TestConclusionForOldResults(unittest.TestCase):
    """JSON from an atlas-diff without the "gate" field keeps the old mapping."""

    def test_verdict_mapping_fallback(self):
        for verdict, expected in post_check.VERDICT_CONCLUSION.items():
            self.assertEqual(post_check.conclusion_for({"verdict": verdict}), expected)
        self.assertEqual(post_check.conclusion_for({}), "neutral")


if __name__ == "__main__":
    unittest.main()
