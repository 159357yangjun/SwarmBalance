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

    def test_B_distinct_sources_pick_up_only_at_their_own_events(self):
        """Two different pickup events must not load the later parcel early."""
        from scripts.test_p1_load_energy_ledger_audit import LoadEnergyLedgerAudit

        d = self.new_drone(load=7, onboard=0)
        d.speed = 20.0
        d.is_free = False
        d.scheduled_position = [
            (20.0, 0.0, "source"), (40.0, 0.0, "dest"),
            (60.0, 0.0, "source"), (80.0, 0.0, "dest"),
        ]
        shell = LoadEnergyLedgerAudit()
        shell.Environment = self.mod.Environment
        env = shell.small_environment(d)
        tasks = [
            self.mod.Task(task_id="p1-a", weight=3,
                          source=(20.0, 0.0), destination=(40.0, 0.0)),
            self.mod.Task(task_id="p1-b", weight=4,
                          source=(60.0, 0.0), destination=(80.0, 0.0)),
        ]
        env.drone_assignments = {0: [
            {"task": task, "load_time": None} for task in tasks
        ]}
        env.drone_chain_len[0] = 2
        env._record_task_completion = lambda *_args: None
        with patch.dict(os.environ, {"SWARM_BALANCE_ENERGY_ACCOUNTING": "onboard"}):
            expected = [(3, 7), (0, 4), (4, 4), (0, 0)]
            for mass, pending in expected:
                env.step({})
                self.assertAlmostEqual(d.onboard_load_kg, mass)
                self.assertAlmostEqual(d.current_load, pending)
            self.assertAlmostEqual(env.total_empty_distance, 40.0)
            self.assertAlmostEqual(env.total_loaded_distance, 40.0)

    def test_B_duplicate_source_event_is_idempotent(self):
        """Repeated service event cannot put the same package onboard twice."""
        from scripts.test_p1_load_energy_ledger_audit import LoadEnergyLedgerAudit
        d = self.new_drone(load=3, onboard=0)
        d.speed = 20.0
        d.is_free = False
        d.scheduled_position = [
            (20.0, 0.0, "source"), (40.0, 0.0, "source"),
            (60.0, 0.0, "dest"),
        ]
        shell = LoadEnergyLedgerAudit()
        shell.Environment = self.mod.Environment
        env = shell.small_environment(d)
        task = self.mod.Task(task_id="p1-duplicate", weight=3,
                             source=(20.0, 0.0), destination=(60.0, 0.0))
        env.drone_assignments = {0: [{"task": task, "load_time": None}]}
        env._record_task_completion = lambda *_args: None
        with patch.dict(os.environ, {"SWARM_BALANCE_ENERGY_ACCOUNTING": "onboard"}):
            env.step({})
            self.assertAlmostEqual(d.onboard_load_kg, 3.0)
            env.step({})
            self.assertAlmostEqual(d.onboard_load_kg, 3.0)
            env.step({})
            self.assertAlmostEqual(d.onboard_load_kg, 0.0)

    def test_B_swap_suspension_preserves_physical_cargo(self):
        """Charging changes battery only; a suspended delivery keeps the load."""
        d = self.new_drone(load=4, onboard=4)
        d.is_free = False
        d.is_charging = True
        d.swap_remaining_steps = 2.0
        d._suspended_route = [(20.0, 0.0, "dest")]
        d.scheduled_position = []
        with patch.dict(os.environ, {"SWARM_BALANCE_ENERGY_ACCOUNTING": "onboard"}):
            d.update()
            self.assertTrue(d.is_charging)
            self.assertAlmostEqual(d.onboard_load_kg, 4.0)
            d.update()
            self.assertFalse(d.is_charging)
            self.assertEqual(d.scheduled_position, [(20.0, 0.0, "dest")])
            self.assertAlmostEqual(d.onboard_load_kg, 4.0)
            self.assertAlmostEqual(d.current_load, 4.0)

    def test_B_fault_requeue_resets_onboard_mass_before_reassignment(self):
        """OOS returns a picked-up parcel to its source and zeroes onboard kg."""
        from scripts.test_p1_load_energy_ledger_audit import LoadEnergyLedgerAudit
        d = self.new_drone(load=4, onboard=4)
        d.is_free = False
        d.executing_task_id = "p1-fault"
        shell = LoadEnergyLedgerAudit()
        shell.Environment = self.mod.Environment
        env = shell.small_environment(d)
        env._nest_waiting = {}
        env.charging_stations = []
        task = self.mod.Task(task_id="p1-fault", weight=4,
                             source=(20.0, 0.0), destination=(60.0, 0.0))
        env.drone_assignments = {0: [{"task": task, "load_time": 1.0}]}
        with patch.dict(os.environ, {"SWARM_BALANCE_ENERGY_ACCOUNTING": "onboard"}):
            result = env.set_drone_out_of_service(0, True)
            self.assertTrue(result["changed"])
            self.assertEqual(result["requeued_task_ids"], ["p1-fault"])
            self.assertEqual([t.task_id for t in env.task_generator.unassigned_tasks],
                             ["p1-fault"])
            self.assertAlmostEqual(d.current_load, 0.0)
            self.assertAlmostEqual(d.onboard_load_kg, 0.0,
                msg="[B_FAULT_STALE_CARGO] requeued load must leave aircraft")
            env.set_drone_out_of_service(0, False)
            self.assertAlmostEqual(d.onboard_load_kg, 0.0)
            self.assertTrue(d.is_free)

    def test_B_on_invalid_onboard_mass_is_rejected(self):
        with patch.dict(os.environ, {"SWARM_BALANCE_ENERGY_ACCOUNTING": "onboard"}):
            for kg in (-1, 11, float("nan")):
                with self.subTest(onboard=kg):
                    d = self.new_drone(load=10, onboard=kg)
                    with self.assertRaisesRegex(ValueError, "ONBOARD_LOAD_INVALID"):
                        d.consume_battery(20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
