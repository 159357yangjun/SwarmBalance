"""Persistent scene library tests; no OSM/network dependency."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from console.scene_library import SceneLibrary, validate_document


def sample_sim():
    return {
        "environment": {"num_drones": 3},
        "charging_stations": [{"station_id": 0, "x": 0.0, "y": 0.0}],
        "heterogeneous": {"enabled": True, "fleet_mix": {"light_express": 1, "standard_cargo": 1, "heavy_cargo": 1}},
        "nest": {"berths": 1},
        "task": {"deadline_offset_min": 300, "deadline_offset_max": 900},
        "task_generation": {"mode": "realistic", "realistic": {"total_tasks": 10, "initial_task_count": 2}},
        "data_source": {"type": "random"},
    }


class SceneLibraryTests(unittest.TestCase):
    def test_save_list_get_delete(self):
        with tempfile.TemporaryDirectory() as td:
            lib = SceneLibrary(Path(td))
            doc = lib.save(name="答辩场景", description="test", simulation_config=sample_sim(),
                           scheduler_config={"ga": {"population_size": 20}}, algorithm="ga", seed=42)
            self.assertTrue(doc["scene_id"].startswith("scene_"))
            rows = lib.list()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["num_drones"], 3)
            loaded = lib.get(doc["scene_id"])
            self.assertEqual(loaded["name"], "答辩场景")
            self.assertEqual(loaded["seed"], 42)
            lib.delete(doc["scene_id"])
            self.assertEqual(lib.list(), [])

    def test_import_assigns_new_id_and_rejects_path_trick(self):
        with tempfile.TemporaryDirectory() as td:
            lib = SceneLibrary(Path(td))
            raw = {
                "schema_version": 1, "scene_id": "../../bad", "name": "外部场景",
                "algorithm": "greedy", "seed": 7, "simulation_config": sample_sim(),
                "scheduler_config": None,
            }
            imported = lib.import_document(raw)
            self.assertNotEqual(imported["scene_id"], "../../bad")
            self.assertTrue(imported["scene_id"].startswith("scene_"))
            self.assertEqual(len(list(Path(td).glob("*.json"))), 1)

    def test_invalid_document_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_document({"name": "bad", "simulation_config": {"environment": {"num_drones": 0}}})
        with self.assertRaises(ValueError):
            validate_document({"name": "bad", "algorithm": "unknown", "simulation_config": sample_sim()})


if __name__ == "__main__":
    unittest.main()
