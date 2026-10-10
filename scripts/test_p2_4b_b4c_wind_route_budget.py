# -*- coding: utf-8 -*-
"""B4c real mid-flight wind-shift energy-budget RED witness.

Safety property: even when the next 1-second move can be paid, do not
continue a suspended charging diversion when the WHOLE remaining planned
route plus reserve becomes unaffordable after a wind change.
Test uses actual Drone.update, Environment.step, and shared Wh quote.
This is a deterministic stress scenario, not calibrated wind prediction.
"""
from __future__ import annotations

import os
from unittest.mock import patch

from scripts.test_p2_4b_b4_auto_planned_nest import AutoPlannedLowBatteryNest


OPT = {
    "SWARM_BALANCE_AUTO_PLANNED_STATION": "1",
    "SWARM_BALANCE_AUTO_WIND_BUDGET_GATE": "1",
    "SWARM_BALANCE_CHARGE_TARGET_IDENTITY": "1",
    "SWARM_BALANCE_PLANNED_STATION_ROUTE": "0",
    "SWARM_BALANCE_STATION_ENERGY_GATE": "0",
}
WIND = {
    "WIND_ENABLED": True,
    "WIND_ENERGY_HEADWIND_PER_MS": 0.3,
    "WIND_ENERGY_TAILWIND_PER_MS": 0.10,
    "WIND_FACTOR_FLOOR": 0.5,
    "WIND_FACTOR_CEIL": 3.0,
}


class AutoChargingWindBudget(AutoPlannedLowBatteryNest):
    @patch.dict(os.environ, OPT)
    def test_B4c_01_wind_shift_makes_whole_route_unaffordable_hold_before_next_move(self):
        d, env, st = self._low_battery(wh=12.0)
        old_mission = list(d.scheduled_position)
        with patch.dict(d._wind_factor.__globals__, WIND):
            d.set_wind(0.0, 0.0)
            calm = env.quote_planned_station_energy_wh(d, st)
            self.assertTrue(calm["feasible"] and calm["affordable"])
            env.step({})  # initial A* diversion planning
            self.assertEqual(d._suspended_route, old_mission)
            self.assertTrue(d.scheduled_position)
            old_route = list(d.scheduled_position)
            self.assertEqual(d.get_position(), (0.0, 0.0))
            d.set_wind(-12.0, 0.0)  # newly unexpected severe easterly headwind
            revised = env.quote_planned_station_energy_wh(d, st)
            self.assertTrue(revised["feasible"] and not revised["fallback"])
            self.assertFalse(revised["affordable"],
                             "[B4C_SCENARIO_WIND_STILL_AFFORDABLE]")
            # The next short leg is STILL affordable, so a simple P2.2
            # step-feasibility gate cannot prove remaining-route safety.
            first = old_route[0]
            dx, dy = first[0] - d.x, first[1] - d.y
            leg = (dx * dx + dy * dy) ** 0.5
            one_step = min(leg, d.speed)
            along = d._wind_along_for(dx, dy, leg)
            self.assertLess(d.quote_flight_energy_wh(one_step, along),
                            d.current_battery)
            before = (d.get_position(), d.current_battery,
                      env.total_flight_distance, env.total_energy_consumed)
            env.step({})
            self.assertEqual(before, (d.get_position(), d.current_battery,
                                      env.total_flight_distance, env.total_energy_consumed),
                             "[B4C_FULL_ROUTE_BUDGET_VIOLATED]")
            self.assertEqual(d.scheduled_position, old_route)
            self.assertEqual(d._suspended_route, old_mission)
            self.assertEqual(d.executing_task_id, "T1")
            self.assertFalse(d.is_free)
            self.assertFalse(d.awaiting_berth)
            self.assertEqual(env.total_swap_sessions, 0)
            self.assertTrue(d.flight_energy_blocked)

    @patch.dict(os.environ, OPT)
    def test_B4c_02_no_energy_wind_effect_does_not_block_affordable_route(self):
        d, env, st = self._low_battery(wh=12.0)
        with patch.dict(d._wind_factor.__globals__, dict(WIND, WIND_ENABLED=False)):
            d.set_wind(0.0, 0.0)
            env.step({})
            start = d.get_position()
            d.set_wind(-12.0, 0.0)
            q = env.quote_planned_station_energy_wh(d, st)
            self.assertTrue(q["feasible"] and q["affordable"])
            env.step({})
            self.assertNotEqual(d.get_position(), start,
                                "[B4C_E0_CALM_ROUTE_INCORRECTLY_BLOCKED]")
            self.assertFalse(d.flight_energy_blocked)

    @patch.dict(os.environ, dict(OPT, SWARM_BALANCE_AUTO_WIND_BUDGET_GATE="0"))
    def test_B4c_03_explicit_budget_guard_off_keeps_legacy_step_only_policy(self):
        d, env, st = self._low_battery(wh=12.0)
        with patch.dict(d._wind_factor.__globals__, WIND):
            d.set_wind(0.0, 0.0)
            env.step({})  # A* planned under affordable calm conditions
            before = d.get_position()
            d.set_wind(-12.0, 0.0)
            self.assertFalse(env.quote_planned_station_energy_wh(d, st)["affordable"])
            env.step({})
            self.assertNotEqual(d.get_position(), before,
                                "[B4C_DEFAULT_OFF_POLICY_DRIFT]")
            self.assertGreater(env.total_energy_consumed, 0.0)


if __name__ == "__main__":
    import unittest
    unittest.main()
