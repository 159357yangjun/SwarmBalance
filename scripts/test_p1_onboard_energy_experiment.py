# -*- coding: utf-8 -*-
"""B experimental accounting test: actual on-board kg, opt-in only."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from console import _preflight  # noqa: E402


class OnboardEnergyExperiment(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _preflight.load_kernel_environment()[0]
        cls.Drone = cls.mod.Drone

    def new_drone(self, load=10, onboard=0):
        d = self.Drone(0, 0, carrying_capacity=10, battery_capacity=1600)
        d.battery_consumption_base = 0.06
        d.battery_load_penalty_factor = 0.33
        d.current_load = load
        d.onboard_load_kg = onboard
        d.set_wind(0, 0)
        return d

    def test_B_off_exactly_retains_assigned_control(self):
        d = self.new_drone(load=10, onboard=0)
        with patch.dict(os.environ, {"SWARM_BALANCE_ENERGY_ACCOUNTING": "assigned"}):
            self.assertAlmostEqual(d.consume_battery(20), 1.596)
            self.assertAlmostEqual(d.last_energy_debited_wh, 1.596)

    def test_B_on_pre_pickup_charges_empty_and_post_pickup_loaded(self):
        d = self.new_drone(load=10, onboard=0)
        with patch.dict(os.environ, {"SWARM_BALANCE_ENERGY_ACCOUNTING": "onboard"}):
            self.assertAlmostEqual(d.consume_battery(20), 1.2)
            # Source service event supplies onboard_load_kg in Environment.step.
            # Mimic its resulting weight here, then test the destination leg.
            d.onboard_load_kg = 10
            self.assertAlmostEqual(d.consume_battery(20), 1.596)
            d.onboard_load_kg = 0
            self.assertAlmostEqual(d.consume_battery(20), 1.2)

    def test_B_same_source_group_real_environment_pickup_and_deliveries(self):
        """Catch loss of co-dispatched mass when only one source is popped."""
        from types import SimpleNamespace
        from scripts.test_p1_load_energy_ledger_audit import LoadEnergyLedgerAudit

        d = self.new_drone(load=7, onboard=0)
        d.speed = 20.0
        d.is_free = False
        d.scheduled_position = [
            (20.0, 0.0, "source"), (40.0, 0.0, "dest"),
            (60.0, 0.0, "dest")
        ]
        shell = LoadEnergyLedgerAudit()
        shell.Environment = self.mod.Environment
        env = shell.small_environment(d)
        def task(weight):
            return SimpleNamespace(get_source=lambda: (20.0, 0.0),
                                   get_weight=lambda: weight)
        env.drone_assignments = {0: [
            {"task": task(3), "load_time": None},
            {"task": task(4), "load_time": None},
        ]}
        env._record_task_completion = lambda *_args: None
        with patch.dict(os.environ, {"SWARM_BALANCE_ENERGY_ACCOUNTING": "onboard"}):
            env.step({})
            self.assertAlmostEqual(d.onboard_load_kg, 7.0)
            self.assertTrue(all(a["load_time"] is not None for a in env.drone_assignments[0]))
            self.assertAlmostEqual(env.total_empty_distance, 20.0)
            before = d.current_battery
            env.step({})
            self.assertAlmostEqual(before - d.current_battery,
                                   20 * 0.06 * (1 + 0.33 * 0.7))
            self.assertAlmostEqual(d.onboard_load_kg, 4.0)
            env.step({})
            self.assertAlmostEqual(d.onboard_load_kg, 0.0)
            self.assertAlmostEqual(env.total_loaded_distance, 40.0)

    def test_B_on_invalid_onboard_mass_is_rejected(self):
        with patch.dict(os.environ, {"SWARM_BALANCE_ENERGY_ACCOUNTING": "onboard"}):
            for kg in (-1, 11, float("nan")):
                with self.subTest(onboard=kg):
                    d = self.new_drone(load=10, onboard=kg)
                    with self.assertRaisesRegex(ValueError, "ONBOARD_LOAD_INVALID"):
                        d.consume_battery(20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
