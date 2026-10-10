# -*- coding: utf-8 -*-
"""P2.4b-B2 real Drone.update/Environment.step energy reachability RED probes.

Scope: synthetic unobstructed straight-line geometry ONLY. This proves a
necessary energy check, not OSM/no-fly route or physical-return safety.
The P2.2 fail-closed step motion gate remains enabled.
"""
from __future__ import annotations

from unittest.mock import patch
from scripts.test_p1_load_energy_ledger_audit import LoadEnergyLedgerAudit


class StationEnergyGateContract(LoadEnergyLedgerAudit):
    def _scenario(self, *, available_wh, capacity_wh, stations):
        d = self.drone(capacity=10, load=0, battery=capacity_wh, base=0.06, penalty=0.33)
        d.current_battery = available_wh
        d.known_stations = [self.envmod.ChargingStation(n, x, y) for n, x, y in stations]
        d.executing_task_id = "T1"
        d.is_free = False
        d.scheduled_position = [(240.0, 0.0, "source"), (320.0, 0.0, "dest")]
        env = self.small_environment(d)
        return d, env

    def test_B2_a03_unaffordable_all_nests_does_not_overwrite_mission(self):
        d, env = self._scenario(available_wh=0.4, capacity_wh=50.0,
                                stations=[(1, 100.0, 0.0), (2, 0.0, 150.0)])
        old_route = list(d.scheduled_position)
        before = d.current_battery
        # Real scheduler-connected Environment.step(), not mocked Drone.move.
        env.step({})
        self.assertEqual((d.x, d.y), (0.0, 0.0))
        self.assertEqual(d.current_battery, before)
        self.assertEqual(d.scheduled_position, old_route,
                         "[B2_UNREACHABLE_NEST_REPLACED_MISSION]")
        self.assertEqual(d._suspended_route, [],
                         "[B2_UNREACHABLE_NEST_SUSPENDED_MISSION]")
        self.assertFalse(d.is_free)
        self.assertEqual(d.consumed_waypoints_this_step, [])
        self.assertTrue(d.flight_energy_blocked,
                        "[B2_UNREACHABLE_NEST_NO_EXPLICIT_HOLD]")

    def test_B2_wind_makes_farther_station_cheaper_than_nearest(self):
        d, env = self._scenario(available_wh=8.0, capacity_wh=50.0,
                                stations=[(1, 100.0, 0.0), (2, 0.0, 150.0)])
        d.set_wind(-6.0, 6.0)  # eastbound headwind, northbound tailwind
        globals_ = self.Drone._wind_factor.__globals__
        original_route = list(d.scheduled_position)
        with patch.dict(globals_, {
            "WIND_ENABLED": True,
            "WIND_ENERGY_HEADWIND_PER_MS": 0.3,
            "WIND_ENERGY_TAILWIND_PER_MS": 0.12,
            "WIND_FACTOR_FLOOR": 0.5,
            "WIND_FACTOR_CEIL": 3.0,
        }):
            east_cost = d.quote_flight_energy_wh(100.0, d._wind_along_for(100, 0, 100))
            north_cost = d.quote_flight_energy_wh(150.0, d._wind_along_for(0, 150, 150))
            self.assertGreater(east_cost, 8.0)
            self.assertLess(north_cost, 8.0)
            env.step({})
        self.assertEqual((d.x, d.y), (0.0, 0.0))
        self.assertEqual(d._suspended_route, original_route)
        self.assertEqual(d.scheduled_position, [(0.0, 150.0)],
                         "[B2_ENERGY_OPTIMIZATION_STILL_NEAREST_DISTANCE]")
        self.assertEqual(d.consumed_waypoints_this_step, [])

    def test_B2_closed_station_never_selected_even_if_shortest(self):
        d, env = self._scenario(available_wh=8.0, capacity_wh=50.0,
                                stations=[(1, 20.0, 0.0), (2, 0.0, 40.0)])
        d.known_stations[0].closed = True
        env.step({})
        self.assertEqual(d.scheduled_position, [(0.0, 40.0)])
        self.assertEqual(d.consumed_waypoints_this_step, [])

    def test_B2_unreachable_nest_does_not_pay_or_fake_pickup_after_multiple_steps(self):
        d, env = self._scenario(available_wh=0.4, capacity_wh=50.0,
                                stations=[(1, 100.0, 0.0)])
        previous = d.current_battery
        for _ in range(3):
            env.step({})
            self.assertEqual((d.x, d.y), (0.0, 0.0))
            self.assertEqual(d.current_battery, previous)
            self.assertEqual(d.consumed_waypoints_this_step, [])
        self.assertAlmostEqual(env.total_flight_distance, 0.0)
        self.assertAlmostEqual(env.total_energy_consumed, 0.0)


if __name__ == "__main__":
    import unittest
    unittest.main()
