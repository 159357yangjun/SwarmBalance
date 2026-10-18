# -*- coding: utf-8 -*-
"""B4d RED: in-flight change of ENVIRONMENT wind on an already-planned auto
charge route, before actual Drone.update() and battery debit.

The step-level P2.2 gate is not enough when the full remaining path +
reserve has become unaffordable. Never treat a step that fits as full
planned route feasibility. All behavior opt-in; default-off is control.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

from scripts.test_p2_4b_b4c_held_route_requote import HeldRouteRequote

FLAGS = {
    "SWARM_BALANCE_AUTO_PLANNED_STATION": "1",
    "SWARM_BALANCE_CHARGE_TARGET_IDENTITY": "1",
    "SWARM_BALANCE_INFLIGHT_WIND_REQUOTE": "1",
    "SWARM_BALANCE_HELD_ROUTE_REQUOTE": "1",
}

class InflightWindRouteEnergy(HeldRouteRequote):
    def _inflight(self):
        d, env, a, b = self._setup_auto(colocated=False)
        a.closed = True
        env.wind_u, env.wind_v = 0.0, 0.0
        original = list(d.scheduled_position)
        env.step({})  # B selected with actual RoutePlanner quotation
        self.assertEqual(str(d.charge_target_station_id), "B")
        self.assertEqual(d._suspended_route, original)
        env.step({})  # actually fly first 20 m in calm air
        self.assertGreater(d.x, 0.)
        self.assertFalse(d.awaiting_berth)
        self.assertTrue(d.scheduled_position)
        return d, env, a, b, original

    def _flight_snapshot(self, d, env):
        return (d.get_position(), d.current_battery, list(d.scheduled_position),
                list(d._suspended_route), d.executing_task_id,
                str(d.charge_target_station_id), env.total_energy_consumed,
                env.total_flight_distance, env.total_swap_sessions)

    @patch.dict(os.environ, FLAGS)
    def test_B4d_01_sudden_env_headwind_blocks_before_step_and_preserves_cargo(self):
        d, env, a, b, original = self._inflight()
        mod = sys.modules[self.Drone.__module__]
        with patch.object(mod, "WIND_ENABLED", True), \
             patch.object(mod, "WIND_ENERGY_HEADWIND_PER_MS", 0.18), \
             patch.object(mod, "WIND_FACTOR_CEIL", 3.0):
            env.wind_u, env.wind_v = -8.0, 0.0
            before = self._flight_snapshot(d, env)
            env.step({})  # must refresh drone wind from ENV, check full remaining Wh
            self.assertEqual(self._flight_snapshot(d, env), before,
                             "[B4D_FULL_REMAINING_ENERGY_IGNORED]")
            self.assertEqual(d.charge_target_hold_reason, "inflight_wind_energy_unaffordable")
            self.assertTrue(d.flight_energy_blocked)
            self.assertEqual(d.executing_task_id, "T1")
            self.assertEqual(d._suspended_route, original)
            self.assertFalse(d.is_charging)

    @patch.dict(os.environ, FLAGS)
    def test_B4d_02_mild_env_wind_can_continue_when_full_remain_affordable(self):
        d, env, a, b, original = self._inflight()
        mod = sys.modules[self.Drone.__module__]
        with patch.object(mod, "WIND_ENABLED", True), \
             patch.object(mod, "WIND_ENERGY_HEADWIND_PER_MS", 0.02), \
             patch.object(mod, "WIND_FACTOR_CEIL", 3.0):
            env.wind_u, env.wind_v = -1.0, 0.0
            before_wh, before_x = d.current_battery, d.x
            env.step({})
            self.assertGreater(d.x, before_x)
            self.assertLess(d.current_battery, before_wh)
            self.assertIsNone(getattr(d, "charge_target_hold_reason", None))
            self.assertEqual(d._suspended_route, original)

    @patch.dict(os.environ, dict(FLAGS, SWARM_BALANCE_INFLIGHT_WIND_REQUOTE="0"))
    def test_B4d_03_optout_retains_historical_no_continuous_requote(self):
        d, env, a, b, original = self._inflight()
        before_x = d.x
        env.wind_u, env.wind_v = -8.0, 0.0
        env.step({})
        self.assertGreater(d.x, before_x, "[B4D_LEGACY_DEFAULT_CHANGED]")
        self.assertIsNone(getattr(d, "charge_target_hold_reason", None))

    @patch.dict(os.environ, FLAGS)
    def test_B4d_04_wind_relief_alone_cannot_release_hold_without_explicit_quote(self):
        d, env, a, b, original = self._inflight()
        mod = sys.modules[self.Drone.__module__]
        with patch.object(mod, "WIND_ENABLED", True), \
             patch.object(mod, "WIND_ENERGY_HEADWIND_PER_MS", 0.18), \
             patch.object(mod, "WIND_FACTOR_CEIL", 3.0):
            env.wind_u, env.wind_v = -8.0, 0.0
            env.step({})
            self.assertEqual(d.charge_target_hold_reason, "inflight_wind_energy_unaffordable")
            env.wind_u, env.wind_v = 0.0, 0.0
            frozen = self._flight_snapshot(d, env)
            env.step({})
            self.assertEqual(self._flight_snapshot(d, env), frozen,
                             "[B4D_WIND_CLEAR_AUTOMATIC_UNQUOTED_RESUME]")
            outcome = env.resume_held_charge_route(0)
            self.assertTrue(outcome["changed"])
            self.assertIsNone(d.charge_target_hold_reason)
            env.step({})
            self.assertNotEqual(d.get_position(), frozen[0])
            self.assertLess(d.current_battery, frozen[1])
            self.assertEqual(d._suspended_route, original)

if __name__ == "__main__":
    import unittest
    unittest.main()
