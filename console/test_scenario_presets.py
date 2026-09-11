"""演示场景预设的纯配置测试，不加载 OSM。"""
from __future__ import annotations

import unittest

from console import scenario_presets


class ScenarioPresetTests(unittest.TestCase):
    def test_required_demo_presets_exist(self):
        keys = {p["key"] for p in scenario_presets.list_presets()}
        self.assertTrue({"medical_peak", "nest_congestion", "resilience", "balanced"}.issubset(keys))

    def test_preset_returns_deep_copy(self):
        a = scenario_presets.get("medical_peak")
        a["config_patch"]["environment"]["num_drones"] = 999
        b = scenario_presets.get("medical_peak")
        self.assertEqual(b["config_patch"]["environment"]["num_drones"], 10)

    def test_fleet_mix_matches_num_drones(self):
        for meta in scenario_presets.list_presets():
            p = scenario_presets.get(meta["key"])
            env_n = int(p["config_patch"]["environment"]["num_drones"])
            mix = p["config_patch"]["heterogeneous"]["fleet_mix"]
            self.assertEqual(sum(int(v) for v in mix.values()), env_n, meta["key"])


if __name__ == "__main__":
    unittest.main()
