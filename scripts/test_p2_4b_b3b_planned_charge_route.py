# -*- coding: utf-8 -*-
"""B3b real Environment.request_drone_charge and Drone.update opt-in RED.

A synthetic no-fly rectangle forces A* detour; the executed waypoints, energy
ledger and cargo/service events must be checked. This is NOT flight certification.
"""
from __future__ import annotations

import os
from unittest.mock import patch
from shapely.geometry import box

from scripts.test_p2_4b_b3_planned_station_quote import PlannedStationQuoteTests


class PlannedManualChargeRoute(PlannedStationQuoteTests):
    def _setup_route(self, *, battery=100.0, no_path=False, obstacle=True):
        d = self.drone(battery=100.0, base=0.06)
        d.current_battery = battery
        d.executing_task_id = "T1"
        d.is_free = False
        d.scheduled_position = [(240.0, 0.0, "source"),
                                (320.0, 0.0, "dest")]
        st = self._station(100.0, 0.0)
        d.known_stations = [st]
        env = self._world(d,
                          blocked_geometry=box(40.0, -10.0, 60.0, 10.0) if obstacle else None,
                          never_clear=no_path)
        env.charging_stations = [st]
        return d, env, st

    @patch.dict(os.environ, {"SWARM_BALANCE_PLANNED_STATION_ROUTE": "1"})
    def test_B3b_01_optin_manual_charge_uses_actual_planner_waypoints(self):
        d, env, st = self._setup_route()
        initial = list(d.scheduled_position)
        quoted = env.quote_planned_station_energy_wh(d, st)
        self.assertTrue(quoted["feasible"] and quoted["affordable"])
        self.assertGreater(len(quoted["waypoints"]), 1,
                           "[B3B_WORLD_HAS_NO_DETOUR]")
        answer = env.request_drone_charge(0, station_id=st.station_id)
        self.assertTrue(answer["changed"])
        self.assertEqual(d.scheduled_position,
                         [(x, y, "waypoint") for x, y in quoted["waypoints"]],
                         "[B3B_PLANNED_QUOTE_NOT_SCHEDULED]")
        self.assertEqual(d._suspended_route, initial)
        self.assertFalse(d.is_free)
        self.assertTrue(d._manual_charge_requested)
        self.assertEqual((d.x, d.y), (0.0, 0.0))
        self.assertAlmostEqual(d.current_battery, 100.0)

    @patch.dict(os.environ, {"SWARM_BALANCE_PLANNED_STATION_ROUTE": "1"})
    def test_B3b_02_unaffordable_detour_fails_before_any_mutation(self):
        d, env, st = self._setup_route(battery=8.0)
        snapshot = (list(d.scheduled_position), list(d._suspended_route),
                    d.current_battery, d.is_free, d._manual_charge_requested)
        with self.assertRaisesRegex(ValueError, "B3B_NO_AFFORDABLE_PLANNED_ROUTE"):
            env.request_drone_charge(0, station_id=st.station_id)
        self.assertEqual(snapshot,
                         (list(d.scheduled_position), list(d._suspended_route),
                          d.current_battery, d.is_free, d._manual_charge_requested))
        self.assertEqual((d.x, d.y), (0.0, 0.0))
        self.assertEqual(d.consumed_waypoints_this_step, [])

    @patch.dict(os.environ, {"SWARM_BALANCE_PLANNED_STATION_ROUTE": "1"})
    def test_B3b_03_astar_fallback_cannot_be_scheduled(self):
        d, env, st = self._setup_route(no_path=True, obstacle=False)
        snapshot = list(d.scheduled_position)
        with self.assertRaisesRegex(ValueError, "B3B_NO_AFFORDABLE_PLANNED_ROUTE"):
            env.request_drone_charge(0, station_id=st.station_id)
        self.assertEqual(d.scheduled_position, snapshot)
        self.assertEqual(d._suspended_route, [])
        self.assertFalse(d._manual_charge_requested)

    @patch.dict(os.environ, {"SWARM_BALANCE_PLANNED_STATION_ROUTE": "1"})
    def test_B3b_04_real_step_traces_all_detour_points_and_no_phantom_service(self):
        d, env, st = self._setup_route()
        quote = env.quote_planned_station_energy_wh(d, st)
        self.assertTrue(quote["affordable"])
        original = list(d.scheduled_position)
        env.request_drone_charge(0, station_id=st.station_id)
        passed = []
        before = d.current_battery
        for _ in range(80):
            if d.awaiting_berth:
                break
            pos = d.get_position()
            env.step({})  # real Drone.update and real Environment.step
            if d.get_position() != pos:
                passed.append(d.get_position())
            self.assertEqual(d._suspended_route, original,
                             "[B3B_LOST_TASK_MANIFEST]")
            self.assertFalse(d.is_free)
            self.assertEqual(d.executing_task_id, "T1")
        self.assertTrue(d.awaiting_berth, "[B3B_DID_NOT_REACH_NEST]")
        self.assertEqual(d.get_position(), st.get_position())
        self.assertTrue(passed)
        self.assertAlmostEqual(before - d.current_battery, quote["required_wh"], places=6)
        self.assertAlmostEqual(env.total_energy_consumed, quote["required_wh"], places=6)
        self.assertAlmostEqual(env.total_flight_distance, quote["distance_m"], places=6)
        self.assertTrue(all(len(wp) >= 3 and wp[2] == "waypoint"
                            for wp in d.consumed_waypoints_this_step),
                        "[B3B_PHANTOM_TASK_SERVICE_WAYPOINT]")
        self.assertTrue(all(env.route_planner._path_clear(
            (0., 0.) if i == 0 else passed[i-1], p)
            for i, p in enumerate(passed)), "[B3B_EXECUTED_OBSTACLE_CROSSING]")

    @patch.dict(os.environ, {"SWARM_BALANCE_PLANNED_STATION_ROUTE": "0"})
    def test_B3b_05_legacy_manual_charge_is_exact_default_control(self):
        d, env, st = self._setup_route()
        old = list(d.scheduled_position)
        env.request_drone_charge(0, station_id=st.station_id)
        self.assertEqual(d.scheduled_position, [st.get_position()])
        self.assertEqual(d._suspended_route, old)
        self.assertTrue(d._manual_charge_requested)


if __name__ == "__main__":
    import unittest
    unittest.main()
