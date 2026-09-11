"""Map-independent configuration validation tests."""
from __future__ import annotations

import unittest

from console.config_validation import validate_simulation_config


def valid_cfg():
    return {
        "environment": {"num_drones": 3},
        "heterogeneous": {"enabled": True, "fleet_mix": {"light": 1, "standard": 1, "heavy": 1}},
        "charging_stations": [{"station_id": 0, "x": 0, "y": 0}],
        "nest": {"berths": 1},
        "task": {"deadline_offset_min": 300, "deadline_offset_max": 900},
        "task_generation": {"mode": "realistic", "realistic": {"total_tasks": 10, "initial_task_count": 2}},
        "data_source": {"type": "random"},
    }


class ConfigValidationTests(unittest.TestCase):
    def test_valid_config_passes(self):
        errors, warnings = validate_simulation_config(valid_cfg())
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_mismatched_fleet_mix_is_rejected(self):
        cfg = valid_cfg()
        cfg["heterogeneous"]["fleet_mix"]["heavy"] = 0
        errors, _ = validate_simulation_config(cfg)
        self.assertTrue(any("异构机队数量之和" in e for e in errors))

    def test_invalid_sla_and_duplicate_station_are_rejected(self):
        cfg = valid_cfg()
        cfg["task"]["deadline_offset_min"] = 1000
        cfg["charging_stations"].append({"station_id": 0, "x": 1, "y": 1})
        errors, _ = validate_simulation_config(cfg)
        self.assertTrue(any("deadline_offset_min" in e for e in errors))
        self.assertTrue(any("重复" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
