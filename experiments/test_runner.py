from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from experiments.runner import build_plan, load_preset


class ExperimentRunnerTests(unittest.TestCase):
    def test_same_condition_uses_same_seed_across_algorithms(self):
        plan = build_plan(load_preset("quick"))
        buckets = {}
        for r in plan:
            key = (r.experiment, r.value, r.repeat)
            buckets.setdefault(key, set()).add(r.seed)
        self.assertTrue(buckets)
        self.assertTrue(all(len(seeds) == 1 for seeds in buckets.values()))


    def test_sensitivity_values_reuse_repeat_seed(self):
        plan = build_plan(load_preset("quick"))
        rows = [r for r in plan if r.experiment == "task_scale" and r.repeat == 1]
        self.assertGreater(len({r.value for r in rows}), 1)
        self.assertEqual(len({r.seed for r in rows}), 1)

    def test_fleet_mix_keeps_num_drones_equal_to_sum(self):
        plan = build_plan(load_preset("quick"))
        rows = [r for r in plan if r.experiment == "fleet_mix"]
        self.assertTrue(rows)
        for r in rows:
            mix = r.patch["heterogeneous"]["fleet_mix"]
            self.assertEqual(r.patch["environment"]["num_drones"], sum(mix.values()))

    def test_config_loader_env_override(self):
        from config.config_loder import get_shared_config
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "simulation.json"
            p.write_text(json.dumps({"marker": 123}), encoding="utf-8")
            old = os.environ.get("SWARM_BALANCE_SIM_CONFIG")
            os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(p)
            try:
                self.assertEqual(get_shared_config()["marker"], 123)
            finally:
                if old is None:
                    os.environ.pop("SWARM_BALANCE_SIM_CONFIG", None)
                else:
                    os.environ["SWARM_BALANCE_SIM_CONFIG"] = old

    def test_dry_run_does_not_create_output_directory(self):
        from experiments.runner import run_experiments
        preset = load_preset("quick")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "out"
            result = run_experiments(preset, root, dry_run=True)
            self.assertFalse(root.exists())
            self.assertTrue(str(result).endswith("quick_dry-run"))


if __name__ == "__main__":
    unittest.main()
