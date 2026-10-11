# -*- coding: utf-8 -*-
"""R1 RED-first unit and provenance audit on REAL Drone quote/debit paths.

No energy coefficients, physics or frozen E0/E1 artifacts are modified.
Matching an internal nameplate-derived scenario is NOT flight calibration.
"""
from __future__ import annotations
import json
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from console import _preflight
from experiments.reproducibility import write_manifest
from scripts.test_p1_load_energy_ledger_audit import LoadEnergyLedgerAudit

ROOT = Path(__file__).resolve().parents[1]


class R1EnergyUnitsProvenance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        envmod, *_ = _preflight.load_kernel_environment()
        cls.Drone = envmod.Drone
        cls.Environment = envmod.Environment
        cls.types = json.loads((ROOT / "config" / "simulation.json")
                               .read_text(encoding="utf-8"))["heterogeneous"]["drone_types"]

    def manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = write_manifest(
                Path(tmp), ROOT, None,
                ROOT / "config" / "simulation.json",
                ROOT / "config" / "algorithms.yaml",
                ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm",
                1, ["greedy"], "r1_readonly",
            )
            return json.loads(p.read_text(encoding="utf-8"))

    def make_drone(self, model, *, load=None, onboard=0.0):
        c = self.types[model]
        d = self.Drone(0.0, 0.0, drone_type=model)
        d.current_load = c["carrying_capacity"] if load is None else float(load)
        d.onboard_load_kg = float(onboard)
        d.set_wind(0.0, 0.0)
        return d

    def test_R1_01_manifest_contains_effective_energy_mode_and_requested_value(self):
        for requested, expected in ((None, "assigned"), ("assigned", "assigned"),
                                    ("onboard", "onboard"), ("unsupported", "assigned")):
            with self.subTest(requested=requested):
                with patch.dict(os.environ, {}, clear=False):
                    if requested is None:
                        os.environ.pop("SWARM_BALANCE_ENERGY_ACCOUNTING", None)
                    else:
                        os.environ["SWARM_BALANCE_ENERGY_ACCOUNTING"] = requested
                    manifest = self.manifest()
                mode = manifest["energy_accounting_policy"]
                self.assertEqual(mode["effective"], expected, "[R1_UNTRACEABLE_MODE]")
                self.assertEqual(mode["requested"], requested, "[R1_UNTRACEABLE_REQUEST]")
                self.assertEqual(mode["fallback_to_assigned"],
                                 requested not in (None, "assigned", "onboard"))

    def test_R1_02_1000_meters_wh_per_km_matches_real_quote_and_debit(self):
        for name, cfg in self.types.items():
            with self.subTest(name=name):
                d = self.make_drone(name)
                before = d.current_battery
                expected = 1000 * cfg["battery_consumption_base"] * (1 + cfg["battery_load_penalty_factor"])
                with patch.dict(os.environ, {"SWARM_BALANCE_ENERGY_ACCOUNTING": "assigned"}):
                    q = d.quote_flight_energy_wh(1000.0, None)
                    paid = d.consume_battery(1000.0, None)
                self.assertTrue(math.isfinite(q) and q > 0.0)
                self.assertAlmostEqual(q, expected, places=8)
                self.assertAlmostEqual(paid, q, places=8)
                self.assertAlmostEqual(before - d.current_battery, q, places=8)
                self.assertAlmostEqual(d.last_energy_debited_wh, q)
                self.assertAlmostEqual(d.last_energy_shortfall_wh, 0.0)
                self.assertEqual(d.speed, cfg["speed"])

    def test_R1_03_real_environment_step_uses_wh_and_meters_without_extra_credit(self):
        d = self.make_drone("standard_cargo", load=0.0)
        d.speed = 20.0
        d.scheduled_position = [(20.0, 0.0, "waypoint")]
        helper = LoadEnergyLedgerAudit("test_zero_load_meters_and_wh_conserve_in_real_step")
        helper.Environment = self.Environment
        env = helper.small_environment(d)
        before = d.current_battery
        with patch.dict(os.environ, {"SWARM_BALANCE_ENERGY_ACCOUNTING": "assigned"}):
            q = d.quote_flight_energy_wh(20.0, None)
            env.step({})
        self.assertAlmostEqual(q, 1.2)
        self.assertEqual((d.x, d.y), (20.0, 0.0))
        self.assertAlmostEqual(env.total_flight_distance, 20.0)
        self.assertAlmostEqual(env.total_energy_consumed, q)
        self.assertAlmostEqual(before - d.current_battery, q)
        self.assertAlmostEqual(env.total_flight_distance,
                               env.total_empty_distance + env.total_loaded_distance)

    def test_R1_04_assigned_vs_onboard_policy_is_a_different_model(self):
        d = self.make_drone("standard_cargo",load=10.0,onboard=0.0)
        with patch.dict(os.environ, {"SWARM_BALANCE_ENERGY_ACCOUNTING": "assigned"}):
            assigned = d.quote_flight_energy_wh(1000.0)
        with patch.dict(os.environ, {"SWARM_BALANCE_ENERGY_ACCOUNTING": "onboard"}):
            onboard = d.quote_flight_energy_wh(1000.0)
        self.assertAlmostEqual(assigned, 79.8, places=8)
        self.assertAlmostEqual(onboard, 60.0, places=8)
        self.assertGreater(assigned, onboard)
        self.assertAlmostEqual(assigned - onboard, 19.8, places=8)

    def test_R1_05_headwind_tailwind_signs_and_neutral_reference(self):
        d = self.make_drone("standard_cargo",load=0.0)
        wind_globals = self.Drone._wind_factor.__globals__
        with patch.dict(wind_globals, {
            "WIND_ENABLED": True,
            "WIND_ENERGY_HEADWIND_PER_MS": 0.05,
            "WIND_ENERGY_TAILWIND_PER_MS": 0.03,
            "WIND_FACTOR_FLOOR": 0.5,
            "WIND_FACTOR_CEIL": 3.0,
        }),patch.dict(os.environ, {"SWARM_BALANCE_ENERGY_ACCOUNTING": "assigned"}):
            neutral = d.quote_flight_energy_wh(1000.0,0.0)
            head = d.quote_flight_energy_wh(1000.0,6.0)
            tail = d.quote_flight_energy_wh(1000.0,-6.0)
        self.assertAlmostEqual(neutral,60.0,places=8)
        self.assertAlmostEqual(head,78.0,places=8)
        self.assertAlmostEqual(tail,49.2,places=8)
        self.assertGreater(head,neutral)
        self.assertLess(tail,neutral)

    def test_R1_06_declared_ranges_are_only_internal_scenario_consistency(self):
        # No assertion that range or per-km values are measured on a real
        # FlyCart/other airframe. Check *only* scenario's internal dimensions.
        for name,cfg in self.types.items():
            with self.subTest(name=name):
                d=self.make_drone(name)
                with patch.dict(os.environ, {"SWARM_BALANCE_ENERGY_ACCOUNTING": "assigned"}):
                    modeled=d.quote_flight_energy_wh(cfg["full_load_range_km"] * 1000.0)
                self.assertTrue(math.isfinite(modeled))
                ratio=modeled / cfg["battery_capacity"]
                self.assertLess(abs(ratio-1),0.01)
                self.assertGreater(cfg["battery_consumption_base"] * 1000.0,0.0)
                self.assertGreater(cfg["battery_capacity"],0.0)


if __name__ == "__main__":
    unittest.main()
