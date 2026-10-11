# -*- coding: utf-8 -*-
"""B5c RED-first: mixed picked/unpicked orders require atomic custody release.

All pickups in these scenarios execute real Environment.step() source-service
events. Recovery evidence remains operator-attested, not authenticated proof
that a real package was transported back to its original collection point.
"""
from __future__ import annotations

import os
from unittest.mock import patch

from scripts.test_p2_4b_b5b_external_custody_red import B5bExternalCustodyRed

FLAGS = {
    "SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE": "1",
    "SWARM_BALANCE_B5B_EXTERNAL_HANDOFF": "1",
    "SWARM_BALANCE_B5C_MIXED_CHAIN_RELEASE": "1",
}


class B5cMixedChainCustodyRed(B5bExternalCustodyRed):
    def _mixed(self):
        d, env, t1, first_load_time = self._picked()  # real source waypoint
        t2 = self.envmod.Task("B5C-T2", 0.7, (40.0, 0.0), (140.0, 0.0),
                              deadline=1000.0, priority=1, generation_time=0)
        t2.update_status("assigned")
        env.drone_assignments[0].append({
            "task": t2, "assigned_time": env.current_time,
            "start_time": env.current_time, "load_time": None})
        d.current_load += 0.7  # assignment reservation, NOT physical onboard mass
        d.scheduled_position = [(40.0, 0.0, "source"),
                                (100.0, 0.0, "dest"),
                                (140.0, 0.0, "dest")]
        env.drone_chain_len[0] = 2
        self.assertAlmostEqual(d.onboard_load_kg, 0.5)
        self.assertEqual(env.drone_assignments[0][0]["load_time"], first_load_time)
        self.assertIsNone(env.drone_assignments[0][1]["load_time"])
        result = env.set_drone_out_of_service(0, True, "mixed-chain fault")
        self.assertEqual(result["requeued_task_ids"], [])
        self.assertEqual(result["held_task_ids"], [t1.task_id, t2.task_id])
        self.assertAlmostEqual(d.onboard_load_kg, 0.5)
        self.assertEqual(env.task_generator.unassigned_tasks, [])
        return d, env, t1, t2, first_load_time

    def _receipt_for(self, task, event_id="B5C-RECEIPT-T1"):
        return {
            "task_id": str(task.task_id),
            "event_id": event_id,
            "actor_id": "recovery-operator-001",
            "evidence_ref": "signed-manifest-return-" + str(task.task_id),
            "receipt_position": tuple(task.source),
            "received_weight_kg": float(task.weight),
            "disposition": "returned_to_original_source",
        }

    @patch.dict(os.environ, FLAGS)
    def test_B5c_01_one_picked_one_unpicked_released_atomically(self):
        d, env, t1, t2, load_time = self._mixed()
        before = (d.get_position(), d.current_battery,
                  env.total_energy_consumed, env.total_flight_distance)
        proof = self._receipt_for(t1)
        res = env.record_external_manifest_handoff(0, receipts=[proof])
        self.assertTrue(res["changed"])
        self.assertEqual(res["requeued_task_ids"], [t1.task_id, t2.task_id])
        self.assertEqual((d.get_position(), d.current_battery,
                          env.total_energy_consumed, env.total_flight_distance), before,
                         "[B5C_MANIFEST_RECONCILIATION_MOVED_AIRCRAFT_OR_WH]")
        self.assertEqual([t.task_id for t in env.task_generator.unassigned_tasks],
                         [t1.task_id, t2.task_id])
        self.assertFalse(env.drone_assignments.get(0))
        self.assertEqual(d.onboard_load_kg, 0.0)
        self.assertEqual(d.current_load, 0.0)
        self.assertTrue(d.out_of_service)
        self.assertFalse(d.is_free)
        self.assertIsNone(d.cargo_custody_hold_reason)
        self.assertIsNone(d.executing_task_id)
        self.assertEqual(t1.status, "pending")
        self.assertEqual(t2.status, "pending")
        self.assertEqual(env.drone_chain_len[0], 0)
        self.assertEqual(len(env.external_custody_events), 1)
        self.assertEqual(env.external_custody_events[proof["event_id"]]["load_time"],
                         load_time)
        replay = env.record_external_manifest_handoff(0, receipts=[proof])
        self.assertFalse(replay["changed"])
        self.assertEqual(replay["requeued_task_ids"], [])
        self.assertEqual(len(env.task_generator.unassigned_tasks), 2)
        env.step({})
        self.assertTrue(d.out_of_service)
        self.assertEqual(d.get_position(), before[0])

    @patch.dict(os.environ, FLAGS)
    def test_B5c_02_invalid_receipts_leave_mixed_chain_unchanged(self):
        d, env, t1, t2, _ = self._mixed()
        receipt = self._receipt_for(t1)
        corrupted = [
            [],
            [{**receipt, "received_weight_kg": 0.9}],
            [{**receipt, "receipt_position": (999.0, 0.0)}],
            [{**receipt, "task_id": t2.task_id}],
            [{**receipt, "actor_id": ""}],
            [{**receipt, "evidence_ref": ""}],
            [{**receipt, "disposition": "delivered_to_customer"}],
            [receipt, receipt],
            [{**receipt, "received_weight_kg": float("nan")}],
        ]
        snapshot = (d.get_position(), d.current_battery,
                    d.onboard_load_kg, d.current_load, d.executing_task_id,
                    tuple(d.scheduled_position), t1.status, t2.status)
        for proofs in corrupted:
            with self.subTest(proofs=repr(proofs)):
                with self.assertRaisesRegex(ValueError, "B5C_"):
                    env.record_external_manifest_handoff(0, receipts=proofs)
                self.assertEqual(
                    (d.get_position(), d.current_battery,
                     d.onboard_load_kg, d.current_load, d.executing_task_id,
                     tuple(d.scheduled_position), t1.status, t2.status),
                    snapshot, "[B5C_INVALID_PARTIAL_HANDOFF_MUTATED_STATE]")
                self.assertEqual(len(env.drone_assignments[0]), 2)
                self.assertEqual(env.task_generator.unassigned_tasks, [])
                self.assertFalse(getattr(env, "external_custody_events", {}))

    @patch.dict(os.environ, FLAGS)
    def test_B5c_03_two_real_pickups_require_both_receipts(self):
        d, env, t1, t2, _ = self._mixed()
        # Reopen only for fixture: genuinely consume the second source point.
        d.out_of_service = False
        d.cargo_custody_hold_reason = None
        d.is_free = False
        env.step({})
        self.assertEqual(d.get_position(), (40.0, 0.0))
        self.assertIsNotNone(env.drone_assignments[0][1]["load_time"],
                             "[B5C_SECOND_SOURCE_SERVICE_MISSING]")
        self.assertAlmostEqual(d.onboard_load_kg, 1.2)
        env.set_drone_out_of_service(0, True)
        with self.assertRaisesRegex(ValueError, "B5C_"):
            env.record_external_manifest_handoff(
                0, receipts=[self._receipt_for(t1)])
        self.assertEqual(env.task_generator.unassigned_tasks, [])
        proofs = [self._receipt_for(t1),
                  self._receipt_for(t2, event_id="B5C-RECEIPT-T2")]
        result = env.record_external_manifest_handoff(0, receipts=proofs)
        self.assertEqual(result["requeued_task_ids"], [t1.task_id, t2.task_id])
        self.assertEqual(len(env.external_custody_events), 2)
        self.assertAlmostEqual(d.onboard_load_kg, 0.0)

    @patch.dict(os.environ, FLAGS)
    def test_B5c_04_duplicate_id_with_changed_receipt_is_not_idempotent(self):
        d, env, t1, t2, _ = self._mixed()
        receipt = self._receipt_for(t1)
        env.record_external_manifest_handoff(0, receipts=[receipt])
        with self.assertRaisesRegex(ValueError, "B5C_EVENT_CONFLICT"):
            env.record_external_manifest_handoff(
                0, receipts=[{**receipt, "actor_id": "different-operator"}])
        self.assertEqual(len(env.task_generator.unassigned_tasks), 2)
        self.assertEqual(len(env.external_custody_events), 1)

    @patch.dict(os.environ, {
        "SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE": "1",
        "SWARM_BALANCE_B5B_EXTERNAL_HANDOFF": "1",
        "SWARM_BALANCE_B5C_MIXED_CHAIN_RELEASE": "0",
    })
    def test_B5c_05_flag_off_refuses_to_release_cargo(self):
        d, env, t1, t2, _ = self._mixed()
        with self.assertRaisesRegex(ValueError, "B5C_FEATURE_DISABLED"):
            env.record_external_manifest_handoff(
                0, receipts=[self._receipt_for(t1)])
        self.assertAlmostEqual(d.onboard_load_kg, 0.5)
        self.assertEqual(len(env.drone_assignments[0]), 2)
        self.assertEqual(env.task_generator.unassigned_tasks, [])


if __name__ == "__main__":
    import unittest
    unittest.main()
