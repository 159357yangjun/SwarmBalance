# -*- coding: utf-8 -*-
"""B3a: exercise real RoutePlanner (A*) and energy model; RED before quote API.

No auto-diversion, dispatch, landing or physical-airworthiness claim.
"""
from __future__ import annotations

import math
from types import SimpleNamespace
from unittest.mock import patch

from shapely.geometry import box

from scripts.test_p1_load_energy_ledger_audit import LoadEnergyLedgerAudit


class PlannedStationQuoteTests(LoadEnergyLedgerAudit):
    def _world(self, d, *, blocked_geometry=None, never_clear=False):
        from route_planner import RoutePlanner
        from no_fly_zone import NoFlyZone, NoFlyZoneSet
        env = self.small_environment(d)
        zones = (NoFlyZoneSet([NoFlyZone("test-block", blocked_geometry)])
                 if blocked_geometry is not None else NoFlyZoneSet([]))
        def clear(a, b):
            return not never_clear and not zones.path_blocked(a, b)
        env.route_planner = RoutePlanner(high_buildings=[], no_fly=zones, path_clear=clear,
                                          warn=lambda msg: None)
        return env

    def _station(self, x, y):
        return self.envmod.ChargingStation("B3", x, y)

    def test_B3_blocked_direct_hop_requires_real_detour_energy(self):
        d = self.drone(battery=100.0, base=0.06)
        st = self._station(100.0, 0.0)
        env = self._world(d, blocked_geometry=box(40.0, -10.0, 60.0, 10.0))
        from route_planner import RouteRequest
        planned = env.route_planner.plan(RouteRequest((0.0, 0.0), st.get_position()))
        self.assertTrue(planned.feasible, "[B3_TEST_WORLD_NO_ASTAR_PATH]")
        self.assertFalse(planned.direct)
        self.assertFalse(planned.fallback)
        self.assertGreater(planned.distance, 100.0)
        initial = dict(d.__dict__)
        outcome = env.quote_planned_station_energy_wh(d, st, reserve_fraction=0.05)
        self.assertTrue(outcome["feasible"])
        self.assertFalse(outcome["fallback"])
        self.assertAlmostEqual(outcome["distance_m"], planned.distance, places=5)
        self.assertGreater(outcome["required_wh"], d.quote_flight_energy_wh(100.0))
        self.assertEqual(d.__dict__, initial, "[B3_QUOTE_MUTATED_DRONE]")
        self.assertEqual(outcome["waypoints"], planned.waypoints)

    def test_B3_unaffordable_detour_must_not_pass_on_direct_distance(self):
        d = self.drone(battery=100.0, base=0.06)
        st = self._station(100.0, 0.0)
        env = self._world(d, blocked_geometry=box(40.0, -10.0, 60.0, 10.0))
        from route_planner import RouteRequest
        route = env.route_planner.plan(RouteRequest((0.0, 0.0), st.get_position()))
        self.assertTrue(route.feasible)
        planned_wh = 0.0
        prev = (d.x, d.y)
        for nxt in route.waypoints:
            dx, dy = nxt[0] - prev[0], nxt[1] - prev[1]
            distance = math.hypot(dx, dy)
            planned_wh += d.quote_flight_energy_wh(distance, d._wind_along_for(dx, dy, distance))
            prev = nxt
        direct_wh = d.quote_flight_energy_wh(100.0)
        self.assertGreater(planned_wh, direct_wh)
        reserve_wh = 0.05 * d.battery_capacity
        d.current_battery = (direct_wh + planned_wh) / 2.0 + reserve_wh
        quote = env.quote_planned_station_energy_wh(d, st, reserve_fraction=0.05)
        self.assertFalse(quote["affordable"], "[B3_UNAFFORDABLE_DETOUR_ACCEPTED]")
        self.assertGreater(quote["required_wh"] + reserve_wh, d.current_battery)

    def test_B3_astar_fallback_is_never_called_reachable(self):
        d = self.drone(battery=500.0)
        st = self._station(100.0, 0.0)
        env = self._world(d, never_clear=True)
        result = env.quote_planned_station_energy_wh(d, st)
        self.assertFalse(result["feasible"], "[B3_FALLBACK_TREATED_AS_SAFE_ROUTE]")
        self.assertTrue(result["fallback"])
        self.assertFalse(result["affordable"])
        self.assertEqual(result["reason"], "planner_fallback")
        self.assertAlmostEqual(d.current_battery, 500.0)

    def test_B3_real_osm_geometry_planner_and_quote(self):
        # This smoke checks the actual pinned Yangpu OSM loader/world, not a
        # fabricated planning response. No fixed coordinates are invented.
        from pathlib import Path
        osm = Path(__file__).resolve().parents[1] / "frontend" / "data" / "map" / "part_of_yangpu.osm"
        env = self.Environment(str(osm))
        st = env.charging_stations[0]
        x, y = st.get_position()
        sample = None
        for distance in (2.0, 10.0, 30.0, 100.0):
            for dx, dy in ((distance, 0), (-distance, 0), (0, distance), (0, -distance)):
                a = (x+dx, y+dy)
                if env.is_path_clear(a, (x, y)):
                    sample = a
                    break
            if sample:
                break
        self.assertIsNotNone(sample, "[B3_REAL_OSM_NO_CLEAR_LOCAL_PAIR]")
        d = self.drone(battery=100.0, base=0.06)
        d.x, d.y = sample
        result = env.quote_planned_station_energy_wh(d, st)
        self.assertTrue(result["feasible"])
        self.assertTrue(result["affordable"])
        self.assertGreater(result["distance_m"], 0.0)
        self.assertFalse(result["fallback"])
        self.assertAlmostEqual(result["required_wh"], d.quote_flight_energy_wh(result["distance_m"]),
                               places=7)


if __name__ == "__main__":
    import unittest
    unittest.main()
