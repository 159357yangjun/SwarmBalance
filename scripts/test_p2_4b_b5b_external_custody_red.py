# -*- coding: utf-8 -*-
"""B5b operator-attested external handoff after real pickup + B5a custody hold.

This is an in-memory *simulation* attestation API, NOT independently
authenticated physical delivery evidence. Never silently relocate cargo.
"""
from __future__ import annotations

import os
from unittest.mock import patch

from scripts.test_p2_4b_b5a_cargo_custody_red import B5aCargoCustodyRed

FLAGS = {"SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE": "1",
         "SWARM_BALANCE_B5B_EXTERNAL_HANDOFF": "1"}


class B5bExternalCustodyRed(B5aCargoCustodyRed):
    def _held(self):
        drone, env, task, load_time = self._picked()  # witnessed real source arrival
        ack = env.set_drone_out_of_service(0, True, "in-flight failure")
        self.assertTrue(ack["cargo_custody_held"])
        self.assertEqual(ack["requeued_task_ids"], [])
        self.assertAlmostEqual(drone.onboard_load_kg, task.weight)
        return drone, env, task, load_time

    def _proof(self, task, **overrides):
        proof = {"event_id": "B5B-RECEIPT-0001",
                 "actor_id": "recovery-operator-001",
                 "evidence_ref": "signed-return-receipt-001",
                 "receipt_position": tuple(task.source),
                 "received_weight_kg": task.weight,
                 "disposition": "returned_to_original_source"}
        proof.update(overrides)
        return proof

    @patch.dict(os.environ, FLAGS)
    def test_B5b_01_witnessed_source_return_requeues_once_no_drone_teleport(self):
        d, env, task, loading = self._held()
        before = (d.get_position(), d.current_battery,
                  env.total_energy_consumed, env.total_flight_distance)
        proof = self._proof(task)
        result = env.record_external_cargo_handoff(0, **proof)
        self.assertTrue(result["changed"])
        self.assertEqual(result["requeued_task_ids"], [task.task_id])
        self.assertTrue(d.out_of_service, "[B5B_RESCUE_MUST_NOT_REACTIVATE_DRONE]")
        self.assertEqual((d.get_position(), d.current_battery,
                          env.total_energy_consumed, env.total_flight_distance), before)
        self.assertEqual(d.onboard_load_kg, 0.0)
        self.assertEqual(d.current_load, 0.0)
        self.assertIsNone(d.executing_task_id)
        self.assertIsNone(d.cargo_custody_hold_reason)
        self.assertFalse(env.drone_assignments.get(0))
        self.assertEqual(task.status, "pending")
        self.assertEqual([t.task_id for t in env.task_generator.unassigned_tasks], [task.task_id])
        self.assertEqual(tuple(task.source), proof["receipt_position"])
        self.assertEqual(task.get_route(), [task.source, task.destination])
        events = env.external_custody_events
        self.assertEqual(len(events), 1)
        e = events[proof["event_id"]]
        self.assertEqual(e["task_id"], task.task_id)
        self.assertEqual(e["operator_id"], proof["actor_id"])
        self.assertEqual(e["evidence_ref"], proof["evidence_ref"])
        self.assertEqual(e["load_time"], loading)
        self.assertEqual(e["custody_mode"], "operator_attestation_not_physical_verification")
        self.assertEqual(e["received_weight_kg"], task.weight)
        self.assertEqual(tuple(e["receipt_position"]), tuple(task.source))
        self.assertEqual(tuple(e["drone_position_at_handoff"]), before[0])
        again = env.record_external_cargo_handoff(0, **proof)
        self.assertFalse(again["changed"])
        self.assertEqual(again["requeued_task_ids"], [])
        self.assertEqual(len(events), 1)
        self.assertEqual(len(env.task_generator.unassigned_tasks), 1)
        env.step({})
        self.assertTrue(d.out_of_service)
        self.assertEqual(d.get_position(), before[0])

    @patch.dict(os.environ, FLAGS)
    def test_B5b_02_incomplete_or_forged_attestation_must_fail_atomically(self):
        d, env, task, loading = self._held()
        original = (d.current_load, d.onboard_load_kg, d.executing_task_id,
                    tuple(d.scheduled_position), task.status, loading)
        bad = [
            ("missing actor", {"actor_id": ""}),
            ("missing receipt", {"evidence_ref": ""}),
            ("missing event ID", {"event_id": ""}),
            ("wrong place", {"receipt_position": (999.0, 0.0)}),
            ("wrong weight", {"received_weight_kg": 0.1}),
            ("wrong disposition", {"disposition": "delivered_to_customer"}),
            ("invalid weight", {"received_weight_kg": float("nan")}),
        ]
        for label, changes in bad:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, "B5B_"):
                    env.record_external_cargo_handoff(0, **self._proof(task, **changes))
                self.assertTrue(d.out_of_service)
                self.assertEqual((d.current_load, d.onboard_load_kg,
                                  d.executing_task_id, tuple(d.scheduled_position),
                                  task.status, loading), original,
                                 "[B5B_INVALID_EVIDENCE_MUTATED_LEDGER]")
                self.assertEqual(len(env.drone_assignments[0]), 1)
                self.assertEqual(env.task_generator.unassigned_tasks, [])
                self.assertFalse(getattr(env, "external_custody_events", {}))

    @patch.dict(os.environ, FLAGS)
    def test_B5b_03_duplicate_event_id_with_conflicting_details_rejected(self):
        d, env, task, _ = self._held()
        proof = self._proof(task)
        env.record_external_cargo_handoff(0, **proof)
        with self.assertRaisesRegex(ValueError, "B5B_EVENT_CONFLICT"):
            env.record_external_cargo_handoff(
                0, **self._proof(task, actor_id="different-operator"))
        self.assertEqual(len(env.external_custody_events), 1)
        self.assertEqual([t.task_id for t in env.task_generator.unassigned_tasks], [task.task_id])

    @patch.dict(os.environ, {"SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE": "1",
                              "SWARM_BALANCE_B5B_EXTERNAL_HANDOFF": "0"})
    def test_B5b_04_default_off_refuses_any_external_credit(self):
        d, env, task, _ = self._held()
        with self.assertRaisesRegex(ValueError, "B5B_FEATURE_DISABLED"):
            env.record_external_cargo_handoff(0, **self._proof(task))
        self.assertAlmostEqual(d.onboard_load_kg, task.weight)
        self.assertEqual(env.task_generator.unassigned_tasks, [])
        self.assertTrue(d.out_of_service)

    @patch.dict(os.environ, FLAGS)
    def test_B5b_05_unpicked_or_mixed_chain_has_no_fabricated_handoff(self):
        d, env, task = self._assigned()  # source NOT consumed
        env.set_drone_out_of_service(0, True)
        with self.assertRaisesRegex(ValueError, "B5B_"):
            env.record_external_cargo_handoff(0, **self._proof(task))
        self.assertEqual([t.task_id for t in env.task_generator.unassigned_tasks], [task.task_id])
        self.assertFalse(getattr(env, "external_custody_events", {}))
        d, env, task, _ = self._held()
        t2 = self.envmod.Task("B5-OTHER", 1.0, (20, 0), (120, 0))
        env.drone_assignments[0].append({"task": t2, "load_time": None})
        with self.assertRaisesRegex(ValueError, "B5B_"):
            env.record_external_cargo_handoff(0, **self._proof(task))
        self.assertAlmostEqual(d.onboard_load_kg, 0.5)
        self.assertEqual(len(env.drone_assignments[0]), 2)

    @patch.dict(os.environ, FLAGS)
    def test_B5b_06_ordinary_restart_only_after_handoff_event(self):
        d, env, task, _ = self._held()
        with self.assertRaisesRegex(ValueError, "B5A_EXTERNAL_HANDOFF_REQUIRED"):
            env.set_drone_out_of_service(0, False)
        env.record_external_cargo_handoff(0, **self._proof(task))
        result = env.set_drone_out_of_service(0, False)
        self.assertTrue(result["changed"])
        self.assertFalse(d.out_of_service)
        self.assertEqual(d.onboard_load_kg, 0.0)
        self.assertEqual([t.task_id for t in env.task_generator.unassigned_tasks], [task.task_id])
        self.assertEqual(len(env.external_custody_events), 1)


if __name__ == "__main__":
    import unittest
    unittest.main()
