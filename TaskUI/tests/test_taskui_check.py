import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("taskui_check", ROOT / "tools" / "taskui_check.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class ManifestChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.good_path = ROOT / "examples" / "good.project.taskui.json"
        cls.good = json.loads(cls.good_path.read_text(encoding="utf-8"))

    def verify(self, mutation=None):
        doc = copy.deepcopy(self.good)
        if mutation:
            mutation(doc)
        return checker.Checker(doc, self.good_path).run()

    def test_good_example_has_no_diagnostics(self):
        result = checker.check(self.good_path)
        self.assertTrue(result["ok"], result["diagnostics"])
        self.assertEqual(result["summary"]["warnings"], 0, result["diagnostics"])

    def test_bad_example_fails(self):
        result = checker.check(ROOT / "examples" / "bad.project.taskui.json")
        codes = {item["code"] for item in result["diagnostics"]}
        self.assertFalse(result["ok"])
        self.assertTrue({"E114", "E210", "E330", "E331", "E401"}.issubset(codes))

    def test_duplicate_task_id_is_error(self):
        diagnostics = self.verify(lambda d: d["tasks"].append(copy.deepcopy(d["tasks"][0])))
        self.assertIn("E010", {x["code"] for x in diagnostics})

    def test_task_budget_overflow_is_error(self):
        diagnostics = self.verify(lambda d: d["tasks"][0].update(step_budget=1))
        self.assertIn("E112", {x["code"] for x in diagnostics})

    def test_invalid_entrypoint_region_is_error(self):
        diagnostics = self.verify(lambda d: d["actions"][1]["entrypoints"][0].update(region_id="no-such-region"))
        self.assertIn("E313", {x["code"] for x in diagnostics})

    def test_high_risk_without_recovery_or_confirmation_fails(self):
        diagnostics = self.verify(lambda d: d["actions"][2].update(recovery="none"))
        self.assertIn("E330", {x["code"] for x in diagnostics})

    def test_deep_only_high_frequency_warns(self):
        def change(d):
            d["actions"][1]["entrypoints"] = [{"screen_id": "S-library", "region_id": "R-list", "surface": "menu", "menu_depth": 3, "context": "selected"}]
        diagnostics = self.verify(change)
        self.assertIn("W320", {x["code"] for x in diagnostics})

    def test_missing_evidence_is_error(self):
        diagnostics = self.verify(lambda d: d["design_evidence"].update(wireframe="not-a-file.md"))
        self.assertIn("E401", {x["code"] for x in diagnostics})

    def test_invalid_json_is_structured_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{ broken", encoding="utf-8")
            result = checker.check(path)
        self.assertFalse(result["ok"])
        self.assertEqual(result["diagnostics"][0]["code"], "EJSON")


if __name__ == "__main__":
    unittest.main()
