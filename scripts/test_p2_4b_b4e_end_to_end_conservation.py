# -*- coding: utf-8 -*-
"""B4e integration: actual dispatch, wind hold, closure, re-quote, berth and swap.

Experimental only. This is a real Environment.step / RoutePlanner scenario,
not a physical UAV flight validation. Preserve original order and cargo custody.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import patch

from scripts.test_p2_4b_b4d_inflight_wind_energy import InflightWindRouteEnergy

FLAGS = {
    "SWARM_BALANCE_AUTO_PLANNED_STATION": "1",
    "SWARM_BALANCE_CHARGE_TARGET_IDENTITY": "1",
    "SWARM_BALANCE_HELD_ROUTE_REQUOTE": "1",
    "SWARM_BALANCE_INFLIGHT_WIND_REQUOTE": "1",
    "SWARM_BALANCE_STATION_ENERGY_GATE": "0",
}


class B4eEndToEndConservation(InflightWindRouteEnergy):
    def _immutable_custody(self, d):
        return (d.executing_task_id, tuple(d._suspended_route))

    @patch.dict(os.environ, FLAGS)
    def test_B4e_01_full_station_wind_hold_requote_swap_and_order_resume(self):
        d, env, a, b, original = self._inflight()
        self.assertEqual(self._immutable_custody(d), ("T1", tuple(original)))
        self.assertEqual(str(d.charge_target_station_id), "B")
        mod = sys.modules[self.Drone.__module__]
        with patch.object(mod, "WIND_ENABLED", True), \
             patch.object(mod, "WIND_ENERGY_HEADWIND_PER_MS", 0.18), \
             patch.object(mod, "WIND_FACTOR_CEIL", 3.0):
            env.wind_u, env.wind_v = -8.0, 0.0
            frozen = self._flight_snapshot(d, env)
            env.step({})
            self.assertEqual(self._flight_snapshot(d, env), frozen,
                             "[B4E_HEADWIND_ALLOWED_MOTION_OR_DEBIT]")
            self.assertEqual(d.charge_target_hold_reason,
                             "inflight_wind_energy_unaffordable")
            # Leave A open: the environment deliberately forbids closing
            # the last usable nest. Only the contracted target B may close.
            a.closed = False
            self.assertFalse(a.closed)
            env.set_station_closed("B", True)
            self.assertTrue(b.closed)
            self.assertEqual(str(d.charge_target_station_id), "B")
            env.wind_u, env.wind_v = 0.0, 0.0
            frozen = self._flight_snapshot(d, env)
            for _ in range(2):
                env.step({})
                self.assertEqual(self._flight_snapshot(d, env), frozen,
                                 "[B4E_CLOSED_NEST_CHANGED_LEDGER_OR_CARGO]")
            with self.assertRaisesRegex(ValueError, "B4C_STATION_CLOSED"):
                env.resume_held_charge_route(0)
            env.set_station_closed("B", False)
            env.step({})
            self.assertEqual(self._flight_snapshot(d, env), frozen,
                             "[B4E_REOPEN_AUTOMATIC_UNQUOTED_RESUME]")
            res = env.resume_held_charge_route(0)
            self.assertTrue(res["changed"])
            self.assertEqual(str(res["station_id"]), "B")
            self.assertEqual(self._immutable_custody(d), ("T1", tuple(original)))
            previous_distance = env.total_flight_distance
            previous_wh = env.total_energy_consumed
            seen_berth = False
            seen_swap = False
            for _ in range(120):
                env.step({})
                self.assertGreaterEqual(env.total_energy_consumed + 1e-9, previous_wh,
                                        "[B4E_ENERGY_LEDGER_DECREASED]")
                self.assertGreaterEqual(env.total_flight_distance + 1e-9, previous_distance,
                                        "[B4E_DISTANCE_LEDGER_DECREASED]")
                previous_wh, previous_distance = (env.total_energy_consumed,
                                                  env.total_flight_distance)
                self.assertEqual(d.executing_task_id, "T1",
                                 "[B4E_ORIGINAL_ORDER_LOST]")
                if d.awaiting_berth or d.is_charging:
                    seen_berth = True
                    self.assertEqual(d.get_position(), b.get_position(),
                                     "[B4E_REMOTE_BERTH_OR_SWAP]")
                    self.assertEqual(str(d.berth_station_id or d.charging_station_id), "B",
                                     "[B4E_WRONG_STATION_BERTH]")
                # total_swap_sessions increments at berth admission, NOT
                # at completed battery replacement. Require real elapsed swap.
                if env.total_swap_sessions > 0 and not d.is_charging:
                    self.assertEqual(d.swap_remaining_steps, 0.0,
                                     "[B4E_SWAP_TIMER_NOT_EXPIRED]")
                    self.assertAlmostEqual(d.current_battery, d.battery_capacity,
                                           msg="[B4E_SWAP_DID_NOT_RESTORE_BATTERY]")
                    seen_swap = True
                    break
            self.assertTrue(seen_berth, "[B4E_BERTH_NEVER_REACHED]")
            self.assertTrue(seen_swap, "[B4E_SWAP_NEVER_COMPLETED]")
            self.assertEqual(a.occupied, 0, "[B4E_WRONG_NEST_OCCUPANCY]")
            self.assertEqual(d.executing_task_id, "T1")
            self.assertEqual(d._suspended_route, [],
                             "[B4E_ORIGINAL_MANIFEST_NOT_RESTORED]")
            self.assertEqual(list(d.scheduled_position), original,
                             "[B4E_ORIGINAL_TASK_ROUTE_NOT_RESUMED]")
            self.assertIsNone(d.charge_target_station_id)
            self.assertIsNone(d.charge_target_hold_reason)


    @patch.dict(os.environ, FLAGS)
    def test_B4e_02_real_onboard_cargo_waiting_berth_swap_and_single_delivery(self):
        # This fixture STARTS AFTER a witnessed pickup: the assigned task
        # exists, onboard cargo is 0.5kg, and only the destination remains.
        # No loading/transfer is faked by the charging detour.
        d, env, a, b = self._setup_auto(colocated=False)
        task = self.envmod.Task("T1", 0.5, (0.0, 0.0), (320.0, 0.0),
                                deadline=1000, priority=1, generation_time=0)
        task.update_status("in_progress")
        d.current_load = 0.5
        d.onboard_load_kg = 0.5
        d.scheduled_position = [(320.0, 0.0, "dest")]
        original = list(d.scheduled_position)
        env.drone_assignments = {0: [{
            "task": task, "assigned_time": 0.0, "start_time": 0.0,
            "load_time": 0.0,
        }]}
        env.completed_tasks = []
        env.completed_task_log = []
        for name in (
            "total_completed_tasks", "total_on_time_tasks", "total_delay",
            "total_generation_to_assignment_wait", "total_assignment_to_load_wait",
            "total_wait_time", "total_delivery_time",
            "total_generation_to_completion_time", "max_delivery_time",
            "max_generation_to_completion_time",
        ):
            setattr(env, name, 0.0)
        env.priority_delay_totals = {1: 0.0, 2: 0.0, 3: 0.0}
        env.priority_delay_counts = {1: 0, 2: 0, 3: 0}

        def cargo_intact(stage):
            self.assertAlmostEqual(d.current_load, 0.5,
                                   msg="[B4E_ASSIGNED_CARGO_LOST] " + stage)
            self.assertAlmostEqual(d.onboard_load_kg, 0.5,
                                   msg="[B4E_ONBOARD_CARGO_LOST] " + stage)
            self.assertEqual(d.executing_task_id, "T1")
            self.assertEqual(env.total_completed_tasks, 0,
                             "[B4E_PHANTOM_DELIVERY] " + stage)
            self.assertEqual(len(env.completed_task_log), 0)
            self.assertEqual([a["task"].task_id for a in env.drone_assignments[0]],
                             ["T1"])

        a.closed = True
        env.step({})  # real auto low-energy dispatch to B
        self.assertEqual(str(d.charge_target_station_id), "B")
        self.assertEqual(d._suspended_route, original)
        cargo_intact("dispatch")
        env.step({})  # real first 20m of charging route
        self.assertGreater(d.x, 0.0)
        cargo_intact("in flight")
        mod = sys.modules[self.Drone.__module__]
        with patch.object(mod, "WIND_ENABLED", True), \
             patch.object(mod, "WIND_ENERGY_HEADWIND_PER_MS", 0.18), \
             patch.object(mod, "WIND_FACTOR_CEIL", 3.0):
            env.wind_u, env.wind_v = -8.0, 0.0
            before = self._flight_snapshot(d, env)
            env.step({})
            self.assertEqual(self._flight_snapshot(d, env), before,
                             "[B4E_LOADED_HEADWIND_NOT_HELD]")
            self.assertEqual(d.charge_target_hold_reason,
                             "inflight_wind_energy_unaffordable")
            cargo_intact("wind hold")
            a.closed = False  # keep one nest open while closing target B
            env.set_station_closed("B", True)
            env.wind_u, env.wind_v = 0.0, 0.0
            env.step({})
            self.assertEqual(self._flight_snapshot(d, env), before,
                             "[B4E_LOADED_CLOSED_NEST_MOVED]")
            cargo_intact("closed target")
            env.set_station_closed("B", False)
            env.step({})
            self.assertEqual(self._flight_snapshot(d, env), before,
                             "[B4E_LOADED_AUTO_RESUMED_WITHOUT_QUOTE]")
            self.assertTrue(env.resume_held_charge_route(0)["changed"])
            cargo_intact("explicit re-quote")

            # Occupied berth must force a real queue, with zero phantom swaps.
            b.occupied = 1
            for _ in range(30):
                env.step({})
                cargo_intact("on approach")
                if d.awaiting_berth:
                    break
            self.assertTrue(d.awaiting_berth, "[B4E_LOADED_NO_BERTH_WAIT]")
            self.assertFalse(d.is_charging)
            self.assertEqual(str(d.berth_station_id), "B")
            self.assertEqual(d.get_position(), b.get_position())
            self.assertEqual(env._nest_waiting.get("B"), [0])
            self.assertEqual(env.total_swap_sessions, 0)
            for _ in range(2):
                env.step({})
                self.assertTrue(d.awaiting_berth)
                self.assertFalse(d.is_charging)
                cargo_intact("berth blocked")

            # Explicitly release the competing berth, then wait for full swap.
            b.vacate()
            env.step({})
            self.assertTrue(d.is_charging)
            self.assertEqual(str(d.charging_station_id), "B")
            self.assertEqual(env.total_swap_sessions, 1)
            cargo_intact("swap started")
            for _ in range(10):
                env.step({})
                cargo_intact("swap in progress")
                if not d.is_charging:
                    break
            self.assertFalse(d.is_charging, "[B4E_LOADED_SWAP_NOT_FINISHED]")
            self.assertAlmostEqual(d.current_battery, d.battery_capacity)
            self.assertEqual(b.occupied, 0)
            self.assertEqual(d.scheduled_position, original)
            self.assertEqual(d._suspended_route, [])
            self.assertIsNone(d.charge_target_station_id)
            cargo_intact("task restored")

            for _ in range(40):
                env.step({})  # real continuation to DEST event
                if env.total_completed_tasks:
                    break
            self.assertEqual(env.total_completed_tasks, 1,
                             "[B4E_LOADED_ORDER_NOT_DELIVERED]")
            self.assertEqual(len(env.completed_task_log), 1)
            self.assertEqual(env.completed_task_log[0]["task"].task_id, "T1")
            self.assertAlmostEqual(d.onboard_load_kg, 0.0,
                                   msg="[B4E_LOADED_DELIVERY_NOT_UNLOADED]")
            self.assertAlmostEqual(d.current_load, 0.0)
            self.assertFalse(env.drone_assignments.get(0),
                             "[B4E_DELIVERED_ORDER_STILL_ASSIGNED]")
            env.step({})
            self.assertEqual(env.total_completed_tasks, 1,
                             "[B4E_DUPLICATE_DELIVERY]")


if __name__ == "__main__":
    import unittest
    unittest.main()
