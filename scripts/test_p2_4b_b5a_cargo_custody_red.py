# -*- coding: utf-8 -*-
"""B5a RED-first: fault after a *real* source pickup must not teleport cargo.

This executes real Environment.step()/Drone.update(), consumes a real source
waypoint and observes its assignment.load_time and onboard mass before fault
injection. No simulated transfer, manufactured delivery or physical flight
certification. Safety branch is experimental-only and default-OFF.
"""
from __future__ import annotations

import os
from unittest.mock import patch

from scripts.test_p1_load_energy_ledger_audit import LoadEnergyLedgerAudit

FLAG = {"SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE": "1"}


class B5aCargoCustodyRed(LoadEnergyLedgerAudit):
    def _assigned(self):
        drone = self.drone(capacity=10.0, load=0.5,
                           battery=100.0, base=0.06)
        drone.current_battery = 90.0
        drone.executing_task_id = "B5-T1"
        drone.is_free = False
        drone.scheduled_position = [
            (20.0, 0.0, "source"), (100.0, 0.0, "dest")]
        task = self.envmod.Task(
            "B5-T1", 0.5, (20.0, 0.0), (100.0, 0.0),
            deadline=1000.0, priority=1, generation_time=0.0)
        task.update_status("assigned")
        env = self.small_environment(drone)
        env._nest_waiting = {}
        env.drone_assignments = {0: [{
            "task": task, "assigned_time": 0.0,
            "start_time": 0.0, "load_time": None,
        }]}
        return drone, env, task

    def _picked(self):
        drone, env, task = self._assigned()
        env.step({})  # REAL source event: physically advances to (20, 0)
        self.assertEqual(drone.get_position(), (20.0, 0.0))
        self.assertEqual(drone.scheduled_position,
                         [(100.0, 0.0, "dest")])
        assignment = env.drone_assignments[0][0]
        self.assertIsNotNone(assignment["load_time"],
                             "[B5A_FIXTURE_SOURCE_NOT_CONSUMED]")
        self.assertAlmostEqual(drone.onboard_load_kg, 0.5,
                               msg="[B5A_FIXTURE_MISSING_ONBOARD_CARGO]")
        self.assertAlmostEqual(drone.current_load, 0.5)
        self.assertEqual(drone.executing_task_id, "B5-T1")
        return drone, env, task, assignment["load_time"]

    @patch.dict(os.environ, FLAG)
    def test_B5a_01_fault_after_real_pickup_never_teleports_or_requeues(self):
        drone, env, task, load_time = self._picked()
        before = (drone.get_position(), drone.current_battery,
                  env.total_energy_consumed, env.total_flight_distance,
                  list(drone.scheduled_position))
        initial_status = task.status
        result = env.set_drone_out_of_service(
            0, True, reason="B5a deterministic in-flight fault")
        self.assertTrue(result["changed"])
        self.assertEqual(result["requeued_task_ids"], [],
                         "[B5A_PICKED_ORDER_REQUEUED]")
        self.assertTrue(drone.out_of_service)
        self.assertFalse(drone.is_free)
        self.assertEqual((drone.get_position(), drone.current_battery,
                          env.total_energy_consumed, env.total_flight_distance,
                          list(drone.scheduled_position)), before,
                         "[B5A_FAULT_TELEPORTED_OR_REPLANNED_CARGO]")
        self.assertAlmostEqual(drone.onboard_load_kg, 0.5,
                               msg="[B5A_FAULT_DISCARDED_ONBOARD_CARGO]")
        self.assertAlmostEqual(drone.current_load, 0.5)
        self.assertEqual(drone.executing_task_id, "B5-T1")
        self.assertEqual(task.status, initial_status)
        self.assertNotEqual(task.status, "pending")
        self.assertFalse(env.task_generator.unassigned_tasks)
        self.assertEqual(len(env.drone_assignments[0]), 1)
        self.assertIs(env.drone_assignments[0][0]["task"], task)
        self.assertEqual(env.drone_assignments[0][0]["load_time"], load_time)
        self.assertEqual(getattr(drone, "cargo_custody_hold_reason", None),
                         "picked_cargo_requires_external_handoff")
        for _ in range(3):
            env.step({})
            self.assertEqual((drone.get_position(), drone.current_battery,
                              env.total_energy_consumed, env.total_flight_distance,
                              list(drone.scheduled_position)), before,
                             "[B5A_FAULTED_DRONE_MOVED]")
            self.assertAlmostEqual(drone.onboard_load_kg, 0.5)
        again = env.set_drone_out_of_service(0, True)
        self.assertFalse(again["changed"])
        self.assertEqual(again["requeued_task_ids"], [])
        self.assertEqual(len(env.drone_assignments[0]), 1)

    @patch.dict(os.environ, FLAG)
    def test_B5a_02_operator_reactivation_without_handoff_refuses(self):
        drone, env, task, _ = self._picked()
        env.set_drone_out_of_service(0, True)
        saved = (drone.get_position(), drone.current_battery,
                 drone.onboard_load_kg, drone.current_load,
                 drone.executing_task_id, task.status,
                 tuple(env.drone_assignments[0][0].items()))
        with self.assertRaisesRegex(ValueError, "B5A_EXTERNAL_HANDOFF_REQUIRED"):
            env.set_drone_out_of_service(0, False)
        self.assertTrue(drone.out_of_service)
        self.assertEqual((drone.get_position(), drone.current_battery,
                          drone.onboard_load_kg, drone.current_load,
                          drone.executing_task_id, task.status,
                          tuple(env.drone_assignments[0][0].items())), saved,
                         "[B5A_FAILED_RESUME_MUTATED_CARGO]")
        self.assertEqual(env.task_generator.unassigned_tasks, [])

    @patch.dict(os.environ, FLAG)
    def test_B5a_03_unpicked_fault_may_requeue_with_no_phantom_cargo(self):
        drone, env, task = self._assigned()
        self.assertIsNone(env.drone_assignments[0][0]["load_time"])
        self.assertEqual(drone.onboard_load_kg, 0.0)
        result = env.set_drone_out_of_service(0, True)
        self.assertEqual(result["requeued_task_ids"], ["B5-T1"])
        self.assertEqual([t.task_id for t in env.task_generator.unassigned_tasks],
                         ["B5-T1"])
        self.assertEqual(task.status, "pending")
        self.assertFalse(env.drone_assignments)
        self.assertEqual(drone.onboard_load_kg, 0.0)
        self.assertEqual(drone.current_load, 0.0)

    @patch.dict(os.environ, {"SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE": "0"})
    def test_B5a_04_optout_preserves_legacy_fault_requeue_control(self):
        drone, env, task, _ = self._picked()
        result = env.set_drone_out_of_service(0, True)
        self.assertEqual(result["requeued_task_ids"], ["B5-T1"])
        self.assertEqual(task.status, "pending")
        self.assertEqual(drone.onboard_load_kg, 0.0)
        self.assertEqual(drone.current_load, 0.0)
        self.assertIsNone(drone.executing_task_id)


if __name__ == "__main__":
    import unittest
    unittest.main()
