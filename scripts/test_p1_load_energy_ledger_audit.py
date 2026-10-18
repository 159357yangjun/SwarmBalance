# -*- coding: utf-8 -*-
"""P1 read-only characterization + hard physical-contract audit.

DO NOT xfail / skip mismatches. Failures are decision items, not an approved
model change. These tests call real Drone and Environment.step(). A small
environment shell removes OSM and dispatch randomness, not the ledger path.
No model, parameters, or archived results are written by these tests.
"""
from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from console import _preflight  # noqa: E402


class LoadEnergyLedgerAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.envmod = _preflight.load_kernel_environment()[0]
        # _preflight loads the real environment module by file path; drone is
        # its same-file dependency and is loaded in that module's namespace.
        cls.Drone = cls.envmod.Drone
        cls.Environment = cls.envmod.Environment
        cls.types = json.loads((ROOT / "config" / "simulation.json").read_text(encoding="utf-8"))[
            "heterogeneous"]["drone_types"]

    def drone(self, *, capacity=10.0, load=0.0, battery=1600.0, base=0.06, penalty=0.33):
        d = self.Drone(0.0, 0.0, carrying_capacity=capacity, battery_capacity=battery)
        d.speed = 20.0  # m/s, deterministic one-second boundaries
        d.current_load = load  # assigned kg, not necessarily physically picked up
        d.battery_consumption_base = base  # Wh/m
        d.battery_load_penalty_factor = penalty
        d.known_stations = []
        d.set_wind(0.0, 0.0)
        return d

    def small_environment(self, d):
        """Real step() and real update(); stub only unrelated map/dispatch/report."""
        env = self.Environment.__new__(self.Environment)
        env.drones = [d]
        env.current_time = 0
        env.episode_max_steps = 99
        env.task_generator = SimpleNamespace(
            step=lambda now: [], unassigned_tasks=[], is_exhausted=False)
        env.task_generation_paused = True
        env.total_generated_tasks = 0
        env.generated_task_times = []
        env.drone_assignments = {}
        env.drone_chain_len = {0: 1}
        env._prev_free_status = {0: False}
        env.total_energy_consumed = 0.0
        env.total_flight_distance = 0.0
        env.total_loaded_distance = 0.0
        env.total_empty_distance = 0.0
        env.drone_busy_steps = 0.0
        env._manage_berths = lambda: None
        env._obs = lambda: {}
        env._reward = lambda: 0.0
        env.get_statistics = lambda: {
            "completion_rate": 0.0, "on_time_rate": 0.0, "avg_delay": 0.0,
            "total_completed": 0, "total_generated": 0,
        }
        return env

    # ---- Control cases: expected to PASS regardless of the unresolved policy ----

    def test_zero_load_meters_and_wh_conserve_in_real_step(self):
        d = self.drone(load=0)
        d.scheduled_position = [(20.0, 0.0, "waypoint")]
        env = self.small_environment(d)
        before = d.current_battery
        env.step({})
        self.assertAlmostEqual(env.total_flight_distance, 20.0)
        self.assertAlmostEqual(env.total_empty_distance, 20.0)
        self.assertAlmostEqual(env.total_loaded_distance, 0.0)
        self.assertAlmostEqual(env.total_energy_consumed, 20.0 * 0.06)
        self.assertAlmostEqual(env.total_energy_consumed, before - d.current_battery)
        self.assertAlmostEqual(env.total_flight_distance,
                               env.total_empty_distance + env.total_loaded_distance)
        print("[P1_LEDGER_OK] zero_load=0 kg, distance=20 m, energy=1.2 Wh")

    def test_full_load_meter_wh_unit_conversion(self):
        for name in ("light_express", "standard_cargo", "heavy_cargo"):
            cfg = self.types[name]
            d = self.drone(capacity=cfg["carrying_capacity"],
                           load=cfg["carrying_capacity"], battery=cfg["battery_capacity"],
                           base=cfg["battery_consumption_base"],
                           penalty=cfg["battery_load_penalty_factor"])
            base_per_km = cfg["battery_consumption_base"] * 1000  # Wh/m => Wh/km
            want = base_per_km * (1.0 + cfg["battery_load_penalty_factor"])
            before = d.current_battery
            reported = d.consume_battery(1000.0, wind_along=None)
            with self.subTest(type=name):
                self.assertAlmostEqual(reported, want, places=7)
                self.assertAlmostEqual(before - d.current_battery, want, places=7)
                # Nameplate scenario range/capacity may have rounding but
                # should at least share the same Wh/km and km convention.
                energy_at_declared_range = want * cfg["full_load_range_km"]
                self.assertLess(abs(energy_at_declared_range / cfg["battery_capacity"] - 1), 0.01)
            print("[P1_UNITS] type=%s full_Wh_per_km=%.6f battery_Wh=%.2f" %
                  (name, want, cfg["battery_capacity"]))

    def test_zero_distance_has_zero_energy_at_full_load(self):
        d = self.drone(load=10)
        before = d.current_battery
        self.assertEqual(d.consume_battery(0.0), 0.0)
        self.assertEqual(d.current_battery, before)

    def test_full_load_has_more_energy_than_empty_at_same_distance(self):
        a = self.drone(load=0.0)
        b = self.drone(load=10.0)
        self.assertAlmostEqual(a.consume_battery(100), 6.0)
        self.assertAlmostEqual(b.consume_battery(100), 7.98)
        self.assertGreater(7.98, 6.0)

    # ---- Hard contract tests: keep RED until user approves a semantics change ----

    def test_pickup_arrival_step_remains_empty_mileage(self):
        d = self.drone(load=10)
        d.scheduled_position = [(20.0, 0.0, "source"), (60.0, 0.0, "dest")]
        env = self.small_environment(d)
        env.step({})  # real update pops source, then Environment classifies
        print("[P1_PICKUP_ACTUAL] empty_m=%.3f loaded_m=%.3f expected_empty_m=20" %
              (env.total_empty_distance, env.total_loaded_distance))
        self.assertAlmostEqual(env.total_empty_distance, 20.0,
                               msg="[P1_PICKUP_RECLASS] pre-pickup 20m counted as loaded")
        self.assertAlmostEqual(env.total_loaded_distance, 0.0)

    def test_delivery_arrival_step_remains_loaded_mileage(self):
        d = self.drone(load=10)
        d.scheduled_position = [(20.0, 0.0, "dest")]
        env = self.small_environment(d)
        env.step({})  # real update clears current_load and dest route before KPI
        print("[P1_DELIVERY_ACTUAL] empty_m=%.3f loaded_m=%.3f expected_loaded_m=20" %
              (env.total_empty_distance, env.total_loaded_distance))
        self.assertAlmostEqual(env.total_loaded_distance, 20.0,
                               msg="[P1_DELIVERY_RECLASS] pre-delivery 20m counted as empty")

    def test_assigned_load_penalty_is_frozen_before_pickup(self):
        """B is NOT approved for production. Assert exact conservative control."""
        d = self.drone(load=10)
        d.scheduled_position = [(100.0, 0.0, "source"), (200.0, 0.0, "dest")]
        self.assertFalse(self.Environment._is_carrying(d))
        cost = d.consume_battery(20.0)
        physically_empty_cost = 20.0 * 0.06
        assigned_baseline_cost = physically_empty_cost * (1 + 0.33)
        print("[P1_B_CONTROL] charged=%.6fWh physical_empty=%.6fWh excess=%.6fWh" %
              (cost, physically_empty_cost, cost - physically_empty_cost))
        self.assertAlmostEqual(cost, assigned_baseline_cost,
                               msg="[P1_B_CONTROL_DRIFT] approved B control formula changed")
        self.assertGreater(cost, physically_empty_cost,
                           "[P1_B_CONTROL_DROPPED] pickup leg no longer carries assigned penalty")
        self.assertAlmostEqual(d.last_energy_required_wh, assigned_baseline_cost)
        self.assertAlmostEqual(d.last_energy_debited_wh, cost)
        self.assertEqual(d.last_energy_shortfall_wh, 0.0)

    def test_battery_depletion_return_equals_actual_ledger_delta(self):
        d = self.drone(load=0)
        d.current_battery = 1.0
        before = d.current_battery
        reported = d.consume_battery(100.0)
        booked = before - d.current_battery
        print("[P1_DEPLETION] required_Wh=%.6f debited_Wh=%.6f shortfall_Wh=%.6f" %
              (d.last_energy_required_wh, reported, d.last_energy_shortfall_wh))
        self.assertAlmostEqual(reported, booked,
                               msg="[P1_DEPLETION_GAP] return must equal actual battery debit")
        self.assertAlmostEqual(d.last_energy_required_wh, 6.0)
        self.assertAlmostEqual(d.last_energy_debited_wh, 1.0)
        self.assertAlmostEqual(d.last_energy_shortfall_wh, 5.0)
        self.assertTrue(d.energy_insufficient)

    def test_negative_distance_is_rejected_without_charging_battery(self):
        d = self.drone(load=0.0)
        before = d.current_battery
        try:
            d.consume_battery(-10.0)
        except ValueError:
            self.assertEqual(d.current_battery, before)
        else:
            print("[P1_NEG_DISTANCE] before_Wh=%.6f after_Wh=%.6f" %
                  (before, d.current_battery))
            self.fail("[P1_NEG_DISTANCE] negative distance accepted / artificial battery gain")

    def test_nan_distance_is_rejected_without_mutating_battery(self):
        d = self.drone(load=0.0)
        before = d.current_battery
        try:
            d.consume_battery(math.nan)
        except ValueError:
            self.assertEqual(d.current_battery, before)
        else:
            print("[P1_NAN_DISTANCE] battery=%r" % d.current_battery)
            self.fail("[P1_NAN_DISTANCE] non-finite distance accepted")

    def test_zero_capacity_is_rejected_explicitly(self):
        d = self.drone(capacity=0.0, load=0.0)
        with self.assertRaisesRegex(ValueError, "capacity|容量|载重"):
            d.consume_battery(10.0)

    def test_over_capacity_load_is_rejected_explicitly(self):
        d = self.drone(capacity=10.0, load=11.0)
        with self.assertRaisesRegex(ValueError, "load|载重|容量"):
            d.consume_battery(10.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
