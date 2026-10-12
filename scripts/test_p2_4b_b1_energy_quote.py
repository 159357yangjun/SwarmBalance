# -*- coding: utf-8 -*-
"""P2.4b-B1 actual Drone energy quote contract. Expected RED before quote refactor.

This is *not* a physical calibration, multi-stop planning, or a policy change.
Both real gate and real debit must consume one pure deterministic Wh quote.
No skip/xfail, no mocked movement or disabled flight safety gate.
"""
from __future__ import annotations

import math
import os
from unittest.mock import patch

from scripts.test_p1_load_energy_ledger_audit import LoadEnergyLedgerAudit


class EnergyQuoteContract(LoadEnergyLedgerAudit):
    def _case(self, *, mode="assigned", load=0.0, onboard=0.0, battery=200.0):
        d = self.drone(capacity=10.0, load=load, battery=battery, base=0.06, penalty=0.33)
        d.onboard_load_kg = onboard
        return d

    def test_B1_quote_is_pure_on_real_drone(self):
        d = self._case(load=6.0, onboard=3.0)
        before = dict(d.__dict__)
        required = d.quote_flight_energy_wh(20.0, None)
        self.assertAlmostEqual(required, 1.2 * (1 + 0.6 * 0.33))
        self.assertEqual(d.__dict__, before, "[B1_QUOTE_MUTATED_DRONE_STATE]")
        self.assertAlmostEqual(d.current_battery, 200.0)

    def test_B1_quote_matches_real_consume_ledger_under_both_modes(self):
        for mode in ("assigned", "onboard"):
            for distance in (0.0, 7.5, 20.0, 100.0):
                with self.subTest(mode=mode, distance=distance):
                    d = self._case(load=8.0, onboard=3.0)
                    with patch.dict(os.environ, {"SWARM_BALANCE_ENERGY_ACCOUNTING": mode}):
                        quote = d.quote_flight_energy_wh(distance, None)
                        expected = distance * 0.06 * (1 + (0.8 if mode == "assigned" else 0.3) * 0.33)
                        self.assertAlmostEqual(quote, expected, places=10)
                        debited = d.consume_battery(distance, None)
                    self.assertAlmostEqual(debited, quote, places=10)
                    self.assertAlmostEqual(d.last_energy_required_wh, quote, places=10)
                    self.assertAlmostEqual(d.last_energy_shortfall_wh, 0.0)
                    self.assertAlmostEqual(200.0 - d.current_battery, quote, places=10)

    def test_B1_quote_preserves_insufficient_battery_direct_debit_ledger(self):
        d = self._case(load=0.0, battery=5.0)
        d.current_battery = 0.2
        quote = d.quote_flight_energy_wh(20.0)
        debit = d.consume_battery(20.0)
        self.assertAlmostEqual(quote, 1.2)
        self.assertAlmostEqual(debit, 0.2)
        self.assertAlmostEqual(d.last_energy_required_wh, 1.2)
        self.assertAlmostEqual(d.last_energy_shortfall_wh, 1.0)
        self.assertAlmostEqual(d.current_battery, 0.0)

    def test_B1_gate_and_debit_are_bound_to_same_quote_function(self):
        d = self._case(load=0.0)
        calls = []

        def authoritative_quote(distance, wind_along=None):
            calls.append((distance, wind_along))
            return 0.7

        # Pure read-only override of this one instance's quote. Both real
        # production call sites must use this injected authoritative source.
        d.quote_flight_energy_wh = authoritative_quote
        self.assertTrue(d._flight_step_feasible(10.0, None))
        self.assertAlmostEqual(d.consume_battery(10.0, None), 0.7)
        self.assertEqual(calls, [(10.0, None), (10.0, None)],
                         "[B1_DOUBLE_FORMULA_DRIFT] gate and debit did not use same quote")
        self.assertAlmostEqual(d.last_energy_required_wh, 0.7)

    def test_B1_quote_and_gate_wind_coefficients_same_real_formula(self):
        d = self._case(load=4.0, onboard=2.0)
        globals_ = self.Drone._wind_factor.__globals__
        with patch.dict(globals_, {
            "WIND_ENABLED": True,
            "WIND_ENERGY_HEADWIND_PER_MS": 0.05,
            "WIND_ENERGY_TAILWIND_PER_MS": 0.03,
            "WIND_FACTOR_FLOOR": 0.5,
            "WIND_FACTOR_CEIL": 3.0,
        }), patch.dict(os.environ, {"SWARM_BALANCE_ENERGY_ACCOUNTING": "assigned"}):
            for wind, factor in ((None, 1.0), (0.0, 1.0), (6.0, 1.3), (-6.0, 0.82), (100.0, 3.0), (-100.0, 0.5)):
                with self.subTest(wind=wind):
                    required = 20.0 * 0.06 * (1 + 0.4 * 0.33) * factor
                    quote = d.quote_flight_energy_wh(20.0, wind)
                    self.assertAlmostEqual(quote, required, places=10)
                    self.assertTrue(d._flight_step_feasible(20.0, wind))
                    self.assertAlmostEqual(d.consume_battery(20.0, wind), quote, places=10)

    def test_B1_quote_rejects_invalid_input_without_changing_state(self):
        for distance in (-1.0, math.nan, math.inf):
            d = self._case(load=0)
            before = dict(d.__dict__)
            with self.subTest(distance=distance), self.assertRaises(ValueError):
                d.quote_flight_energy_wh(distance)
            self.assertEqual(d.__dict__, before)
        d = self._case(load=11)
        with self.assertRaises(ValueError):
            d.quote_flight_energy_wh(20.0)
        d = self._case(load=1, onboard=float("nan"))
        with patch.dict(os.environ, {"SWARM_BALANCE_ENERGY_ACCOUNTING": "onboard"}):
            with self.assertRaises(ValueError):
                d.quote_flight_energy_wh(20.0)

    def test_B1_real_environment_step_uses_quote_for_gate_and_debit(self):
        d = self._case(load=0.0)
        d.scheduled_position = [(20.0, 0.0, "waypoint")]
        env = self.small_environment(d)
        original_quote = d.quote_flight_energy_wh
        witness = []

        def monitored_quote(distance, wind_along=None):
            required = original_quote(distance, wind_along)
            witness.append((distance, wind_along, required))
            return required

        d.quote_flight_energy_wh = monitored_quote
        env.step({})
        self.assertEqual((d.x, d.y), (20.0, 0.0))
        self.assertEqual(len(witness), 2, "[B1_REAL_PATH_NOT_SHARED]")
        self.assertEqual(witness[0], witness[1])
        self.assertAlmostEqual(env.total_energy_consumed, witness[0][2])
        self.assertAlmostEqual(env.total_flight_distance, 20.0)


if __name__ == "__main__":
    import unittest
    unittest.main()
