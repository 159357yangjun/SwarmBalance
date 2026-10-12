# -*- coding: utf-8 -*-
"""B4c RED-first: explicit re-quote before resuming a held charging detour.

Runs actual Environment.step(), Drone.update(), RoutePlanner and B1 Wh
model. Reopening a station is not itself authorization to move.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

from scripts.test_p2_4b_b4b_auto_target_closure import AutoTargetAndClosure


FLAGS = {
    "SWARM_BALANCE_AUTO_PLANNED_STATION": "1",
    "SWARM_BALANCE_CHARGE_TARGET_IDENTITY": "1",
    "SWARM_BALANCE_HELD_ROUTE_REQUOTE": "1",
    "SWARM_BALANCE_STATION_ENERGY_GATE": "0",
}


class HeldRouteRequote(AutoTargetAndClosure):
    def _held(self):
        d, env, a, b = self._setup_auto(colocated=False)
        a.closed = True
        manifest = list(d.scheduled_position)
        env.step({})  # choose B by real A* quote
        self.assertEqual(str(d.charge_target_station_id), "B")
        env.step({})  # actual partial flight, battery debit
        self.assertNotEqual(d.get_position(), (0., 0.))
        a.closed = False
        env.set_station_closed("B", True)
        self.assertEqual(d.charge_target_hold_reason, "target_station_closed")
        self.assertEqual(d._suspended_route, manifest)
        return d, env, a, b, manifest

    def _snapshot(self, d, env):
        return (d.get_position(), d.current_battery,
                list(d.scheduled_position), list(d._suspended_route),
                d.executing_task_id, d.charge_target_station_id,
                d.charge_target_hold_reason, env.total_energy_consumed,
                env.total_flight_distance, env.total_swap_sessions)

    @patch.dict(os.environ, FLAGS)
    def test_B4c_01_reopening_alone_does_not_move_but_explicit_quote_resumes(self):
        d, env, a, b, manifest = self._held()
        env.set_station_closed("B", False)
        held = self._snapshot(d, env)
        env.step({})
        self.assertEqual(self._snapshot(d, env), held,
                         "[B4C_REOPENED_STATION_FREE_RESUME]")
        quoted = env.quote_planned_station_energy_wh(d, b)
        self.assertTrue(quoted["feasible"] and quoted["affordable"])
        response = env.resume_held_charge_route(0)
        self.assertTrue(response["changed"])
        self.assertEqual(str(response["station_id"]), "B")
        self.assertEqual(d.scheduled_position,
                         [(x, y, "waypoint") for x, y in quoted["waypoints"]],
                         "[B4C_REUSED_STALE_ROUTE]")
        self.assertIsNone(d.charge_target_hold_reason)
        self.assertEqual(d._suspended_route, manifest)
        self.assertEqual(d.executing_task_id, "T1")
        self.assertEqual(d.get_position(), held[0])
        self.assertEqual(d.current_battery, held[1])
        env.step({})
        self.assertNotEqual(d.get_position(), held[0],
                            "[B4C_REPLAN_DID_NOT_EXECUTE]")
        self.assertLess(d.current_battery, held[1])

    @patch.dict(os.environ, FLAGS)
    def test_B4c_02_closed_target_refuses_recovery_with_no_mutation(self):
        d, env, a, b, manifest = self._held()
        snap = self._snapshot(d, env)
        with self.assertRaisesRegex(ValueError, "B4C_STATION_CLOSED"):
            env.resume_held_charge_route(0)
        self.assertEqual(self._snapshot(d, env), snap)
        env.step({})
        self.assertEqual(self._snapshot(d, env), snap)

    @patch.dict(os.environ, FLAGS)
    def test_B4c_03_new_headwind_unaffordable_must_not_clear_hold(self):
        d, env, a, b, manifest = self._held()
        env.set_station_closed("B", False)
        # Deterministic E1 coefficients in this test only; no config edits.
        windmod = sys.modules[self.Drone.__module__]
        with patch.object(windmod, "WIND_ENABLED", True), \
             patch.object(windmod, "WIND_ENERGY_HEADWIND_PER_MS", 0.18), \
             patch.object(windmod, "WIND_FACTOR_CEIL", 3.0):
            d.set_wind(-8.0, 0.0)  # eastward flight sees headwind
            quoted = env.quote_planned_station_energy_wh(d, b)
            self.assertTrue(quoted["feasible"])
            self.assertFalse(quoted["affordable"],
                             "[B4C_FIXTURE_WIND_NOT_UNAFFORDABLE]")
            before = self._snapshot(d, env)
            with self.assertRaisesRegex(ValueError, "B4C_ROUTE_UNAFFORDABLE"):
                env.resume_held_charge_route(0)
            self.assertEqual(self._snapshot(d, env), before,
                             "[B4C_UNAFFORDABLE_REQUOTE_MUTATED_TASK]")
            env.step({})
            self.assertEqual(self._snapshot(d, env), before,
                             "[B4C_HEADWIND_HOLD_ALLOWED_FLIGHT]")

    @patch.dict(os.environ, {
        "SWARM_BALANCE_HELD_ROUTE_REQUOTE": "0",
        "SWARM_BALANCE_AUTO_PLANNED_STATION": "1",
        "SWARM_BALANCE_CHARGE_TARGET_IDENTITY": "1",
    })
    def test_B4c_04_default_off_recovery_api_refuses_without_mutation(self):
        d, env, a, b, manifest = self._held()
        env.set_station_closed("B", False)
        snap = self._snapshot(d, env)
        with self.assertRaisesRegex(ValueError, "B4C_OPT_IN_REQUIRED"):
            env.resume_held_charge_route(0)
        self.assertEqual(self._snapshot(d, env), snap)


if __name__ == "__main__":
    import unittest
    unittest.main()
