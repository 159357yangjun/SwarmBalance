# -*- coding: utf-8 -*-
"""R2 metadata-only source audit; no downloads or production changes."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
class ResearchR2SourceGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.s = json.loads((ROOT / "data/research_r2_sources.json").read_text(encoding="utf-8"))
    def test_01_no_false_calibration(self):
        self.assertFalse(self.s["flight_calibration_complete"])
        self.assertEqual(self.s["raw_flight_files_acquired"], 0)
    def test_02_no_external_source_masquerades_as_raw(self):
        self.assertEqual(len(self.s["sources"]), 4)
        for src in self.s["sources"]:
            with self.subTest(src=src["id"]):
                self.assertTrue(src["url"].startswith("https://"))
                self.assertFalse(src["usable_for_calibration"])
                self.assertIsNone(src["sha256"])
                self.assertTrue(src["license"] and src["airframe"] and src["note"])
    def test_03_cmu_airframe_cannot_validate_flycart(self):
        cmu = next(x for x in self.s["sources"] if x["id"] == "cmu_m100")
        self.assertEqual(cmu["airframe"], "DJI Matrice 100")
        self.assertEqual(cmu["reported_flights"], 209)
    def test_04_independent_licenses(self):
        src = {x["id"]: x for x in self.s["sources"]}
        self.assertEqual(src["px4_public"]["license"], "CC-BY PX4")
        self.assertEqual(src["asi_manifest"]["license"], "CC BY-ND 4.0")
    def test_05_model_assumptions_cannot_be_flight_measurements(self):
        model = {x["name"]: x for x in self.s["models"]}
        self.assertEqual(set(model), {"light_express","standard_cargo","heavy_cargo"})
        self.assertAlmostEqual(model["heavy_cargo"]["full_load_wh_km"], 248.50)
        self.assertIn("not independently validated", model["heavy_cargo"]["evidence"])
    def test_06_document_has_hard_stops(self):
        d = (ROOT / "docs/RESEARCH_R2_SOURCE_FEASIBILITY.md").read_text(encoding="utf-8")
        for marker in ("D1 文件","BLOCKED","SHA-256","电压","电流","时间积分","MAE","RMSE","按整次飞行","E0/E1","禁止"):
            with self.subTest(marker=marker):
                self.assertIn(marker,d)
if __name__=="__main__":
    unittest.main()
