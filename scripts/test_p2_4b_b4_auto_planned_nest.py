# -*- coding: utf-8 -*-
"""B4 RED-first automatic low-battery charging detour, real execution.

Synthetic actual Shapely blocked geometry + actual RoutePlanner and
Environment.step/Drone.update; not airworthiness/OSM flight certification.
Only experimental SWARM_BALANCE_AUTO_PLANNED_STATION=1 is under test.
"""
from __future__ import annotations

import os
from unittest.mock import patch

from scripts.test_p2_4b_b3b_planned_charge_route import PlannedManualChargeRoute

_OPTIN = {
    "SWARM_BALANCE_AUTO_PLANNED_STATION": "1",
    "SWARM_BALANCE_STATION_ENERGY_GATE": "0",
    "SWARM_BALANCE_PLANNED_STATION_ROUTE": "0",
    "SWARM_BALANCE_CHARGE_TARGET_IDENTITY": "0",
}

class AutoPlannedLowBatteryNest(PlannedManualChargeRoute):
    def _low_battery(self, *, wh=12.0, no_path=False):
        d, env, st = self._setup_route(battery=wh, no_path=no_path, obstacle=not no_path)
        self.assertTrue(d.is_low_battery(), "[B4_FIXTURE_NOT_LOW_BATTERY]")
        self.assertFalse(d._manual_charge_requested)
        self.assertEqual(d._suspended_route, [])
        return d, env, st

    @patch.dict(os.environ, _OPTIN)
    def test_B4_01_auto_low_battery_schedules_actual_Astar_waypoints(self):
        d, env, st = self._low_battery()
        original = list(d.scheduled_position)
        quote = env.quote_planned_station_energy_wh(d, st)
        self.assertTrue(quote["feasible"] and quote["affordable"])
        self.assertGreater(quote["distance_m"], 100.0)
        start_wh = d.current_battery
        env.step({})
        self.assertEqual(d.get_position(), (0.0, 0.0))
        self.assertEqual(d.current_battery, start_wh)
        self.assertEqual(d._suspended_route, original)
        self.assertEqual(d.scheduled_position,
                         [(x,y,"waypoint") for x,y in quote["waypoints"]],
                         "[B4_AUTO_NEAREST_DIRECT_NOT_ASTAR]")
        self.assertEqual(d.executing_task_id, "T1")
        self.assertFalse(d.is_free)

    @patch.dict(os.environ, _OPTIN)
    def test_B4_02_direct_affordable_but_detour_not_must_hold_original_manifest(self):
        d, env, st = self._low_battery(wh=12.0)
        planned = env.quote_planned_station_energy_wh(d, st)
        direct = d.quote_flight_energy_wh(100.0)
        reserve = planned["reserve_wh"]
        self.assertGreater(planned["required_wh"], direct)
        # Strictly above straight-hop+reserve, below A*+reserve.
        d.current_battery = reserve + (direct + planned["required_wh"]) / 2.0
        self.assertLess(d.current_battery, 0.20 * d.battery_capacity)
        self.assertGreater(d.current_battery, direct + reserve)
        self.assertLess(d.current_battery, planned["total_wh"])
        original = list(d.scheduled_position)
        before = (d.get_position(), d.current_battery)
        env.step({})
        self.assertEqual(d.scheduled_position, original,
                         "[B4_AUTO_UNAFFORDABLE_DETOUR_REPLACED_TASK]")
        self.assertEqual(d._suspended_route, [])
        self.assertEqual((d.get_position(), d.current_battery), before)
        self.assertTrue(d.flight_energy_blocked)
        self.assertFalse(d.is_free)
        self.assertEqual(d.executing_task_id, "T1")

    @patch.dict(os.environ, _OPTIN)
    def test_B4_03_Astar_fallback_never_becomes_auto_charging_route(self):
        d, env, st = self._low_battery(no_path=True)
        self.assertFalse(env.quote_planned_station_energy_wh(d, st)["feasible"])
        original = list(d.scheduled_position)
        before = (d.get_position(), d.current_battery)
        env.step({})
        self.assertEqual(d.scheduled_position, original,
                         "[B4_AUTO_ASTAR_FALLBACK_AS_SAFE_ROUTE]")
        self.assertEqual(d._suspended_route, [])
        self.assertEqual((d.get_position(), d.current_battery), before)
        self.assertTrue(d.flight_energy_blocked)

    @patch.dict(os.environ, _OPTIN)
    def test_B4_04_real_auto_detour_wh_ledger_and_no_phantom_service(self):
        d, env, st = self._low_battery(wh=12.0)
        quote = env.quote_planned_station_energy_wh(d, st)
        original = list(d.scheduled_position)
        before_wh = d.current_battery
        env.step({})  # low-battery diversion assignment
        for _ in range(80):
            if d.awaiting_berth:
                break
            env.step({})  # actual movement
        self.assertTrue(d.awaiting_berth)
        self.assertEqual(d.get_position(), st.get_position())
        self.assertEqual(d._suspended_route, original)
        self.assertEqual(d.executing_task_id, "T1")
        self.assertAlmostEqual(before_wh - d.current_battery,
                               quote["required_wh"], places=6)
        self.assertAlmostEqual(env.total_energy_consumed,
                               quote["required_wh"], places=6)
        self.assertAlmostEqual(env.total_flight_distance,
                               quote["distance_m"], places=6)
        self.assertFalse(d.is_free)

    @patch.dict(os.environ, {
        "SWARM_BALANCE_AUTO_PLANNED_STATION": "0",
        "SWARM_BALANCE_STATION_ENERGY_GATE": "0",
    })
    def test_B4_05_default_off_follows_legacy_nearest_direct(self):
        d, env, st = self._low_battery()
        old = list(d.scheduled_position)
        env.step({})
        self.assertEqual(d.scheduled_position, [st.get_position()],
                         "[B4_DEFAULT_OFF_POLICY_DRIFT]")
        self.assertEqual(d._suspended_route, old)
        self.assertEqual(d.get_position(), (0.0, 0.0))


if __name__ == "__main__":
    import unittest
    unittest.main()
