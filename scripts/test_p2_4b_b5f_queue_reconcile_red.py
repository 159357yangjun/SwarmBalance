# -*- coding: utf-8 -*-
"""B5f RED: real Environment handoff + SQLite intent + explicit reconciliation.

Simulates process crashes at precise DB and volatile-queue boundaries.
The authoritative Environment is supplied by caller; reconstructing it
from durable simulator state is NOT within this isolated stage.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts.test_p2_4b_b5b_external_custody_red import B5bExternalCustodyRed
from console.custody_queue_bridge import DurableCustodyQueueBridge

FLAGS = {
    "SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE": "1",
    "SWARM_BALANCE_B5B_EXTERNAL_HANDOFF": "1",
    "SWARM_BALANCE_B5F_QUEUE_RECONCILIATION": "1",
}


class B5fDurableQueueRed(B5bExternalCustodyRed):
    def setUp(self):
        super().setUp()
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.db = Path(self.tempdir.name) / "handoff.sqlite3"

    def bridge(self, env):
        return DurableCustodyQueueBridge(env, self.db)

    def assert_held(self, drone, env, task):
        self.assertTrue(drone.out_of_service)
        self.assertAlmostEqual(drone.onboard_load_kg, task.weight)
        self.assertEqual([a["task"].task_id for a in env.drone_assignments[0]],
                         [task.task_id])
        self.assertEqual([t.task_id for t in env.task_generator.unassigned_tasks], [])

    def assert_requeued_once(self, drone, env, task):
        self.assertTrue(drone.out_of_service)
        self.assertEqual([t.task_id for t in env.task_generator.unassigned_tasks],
                         [task.task_id])
        self.assertAlmostEqual(drone.onboard_load_kg, 0.0)
        self.assertFalse(env.drone_assignments.get(0))
        self.assertEqual(task.status, "pending")
        self.assertEqual(len(env.external_custody_events), 1)

    @patch.dict(os.environ, FLAGS)
    def test_B5f_01_crash_after_sqlite_commit_leaves_held_then_reconciles(self):
        d, env, task, _ = self._held()  # actual source step and fault
        proof = self._proof(task)
        before = (d.get_position(), d.current_battery,
                  env.total_energy_consumed, env.total_flight_distance)
        with self.assertRaisesRegex(RuntimeError, "B5F_INJECTED_CRASH"):
            self.bridge(env).record_return(0, **proof, fail_after="db_commit")
        self.assert_held(d, env, task)
        self.assertEqual(self.bridge(env).status(proof["event_id"]), "recorded")
        restarted = self.bridge(env)
        result = restarted.reconcile(0, proof["event_id"])
        self.assertTrue(result["changed"])
        self.assertEqual(restarted.status(proof["event_id"]), "applied")
        self.assert_requeued_once(d, env, task)
        self.assertEqual((d.get_position(), d.current_battery,
                          env.total_energy_consumed, env.total_flight_distance), before)
        self.assertFalse(self.bridge(env).reconcile(0, proof["event_id"])["changed"])
        self.assert_requeued_once(d, env, task)

    @patch.dict(os.environ, FLAGS)
    def test_B5f_02_crash_after_environment_apply_never_duplicates(self):
        d, env, task, _ = self._held()
        proof = self._proof(task)
        with self.assertRaisesRegex(RuntimeError, "B5F_INJECTED_CRASH"):
            self.bridge(env).record_return(0, **proof, fail_after="env_apply")
        self.assert_requeued_once(d, env, task)
        self.assertEqual(self.bridge(env).status(proof["event_id"]), "recorded")
        result = self.bridge(env).reconcile(0, proof["event_id"])
        self.assertFalse(result["changed"])
        self.assertEqual(self.bridge(env).status(proof["event_id"]), "applied")
        self.assert_requeued_once(d, env, task)

    @patch.dict(os.environ, FLAGS)
    def test_B5f_03_db_write_error_does_not_mutate_volatile_cargo(self):
        d, env, task, _ = self._held()
        with patch("console.custody_queue_bridge.sqlite3.connect",
                   side_effect=OSError("simulated local disk unavailable")):
            with self.assertRaises(OSError):
                self.bridge(env).record_return(0, **self._proof(task))
        self.assert_held(d, env, task)
        self.assertFalse(self.db.exists())

    @patch.dict(os.environ, FLAGS)
    def test_B5f_04_conflicting_receipt_and_new_event_for_same_task_rejected(self):
        d, env, task, _ = self._held()
        proof = self._proof(task)
        self.bridge(env).record_return(0, **proof)
        self.assert_requeued_once(d, env, task)
        with self.assertRaisesRegex(ValueError, "B5F_EVENT_CONFLICT"):
            self.bridge(env).record_return(
                0, **self._proof(task, actor_id="unexpected-operator"))
        with self.assertRaisesRegex(ValueError, "B5F_EVENT_CONFLICT"):
            self.bridge(env).record_return(
                0, **self._proof(task, event_id="second-receipt"))
        self.assert_requeued_once(d, env, task)
        self.assertEqual(self.bridge(env).event_count(), 1)

    @patch.dict(os.environ, FLAGS)
    def test_B5f_05_bad_receipt_fails_before_database_or_task_mutation(self):
        d, env, task, _ = self._held()
        for changes in ({"received_weight_kg": 0.1},
                        {"receipt_position": (999.0, 0.0)},
                        {"evidence_ref": ""},
                        {"received_weight_kg": float("nan")}):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(ValueError, "B5F_"):
                    self.bridge(env).record_return(0, **self._proof(task, **changes))
                self.assert_held(d, env, task)
                self.assertEqual(self.bridge(env).event_count(), 0)

    @patch.dict(os.environ, FLAGS)
    def test_B5f_06_reconcile_mismatched_task_owner_fails_closed(self):
        d, env, task, _ = self._held()
        proof = self._proof(task)
        with self.assertRaisesRegex(RuntimeError, "B5F_INJECTED_CRASH"):
            self.bridge(env).record_return(0, **proof, fail_after="db_commit")
        env.drone_assignments[0][0]["load_time"] = None
        with self.assertRaisesRegex(ValueError, "B5F_"):
            self.bridge(env).reconcile(0, proof["event_id"])
        self.assertEqual(env.task_generator.unassigned_tasks, [])
        self.assertAlmostEqual(d.onboard_load_kg, task.weight)
        self.assertEqual(self.bridge(env).status(proof["event_id"]), "recorded")

    @patch.dict(os.environ, FLAGS)
    def test_B5f_07_fresh_reconstructed_held_fixture_replays_one_receipt(self):
        d, env, task, _ = self._held()
        proof = self._proof(task)
        with self.assertRaisesRegex(RuntimeError, "B5F_INJECTED_CRASH"):
            self.bridge(env).record_return(0, **proof, fail_after="db_commit")
        # Independent fixture simulates a correctly reconstructed held state,
        # not actual persistence/restoration of the entire Environment.
        fresh_d, fresh_env, fresh_task, _ = self._held()
        self.bridge(fresh_env).reconcile(0, proof["event_id"])
        self.assert_requeued_once(fresh_d, fresh_env, fresh_task)
        self.assertEqual(self.bridge(fresh_env).status(proof["event_id"]), "applied")
        self.assert_held(d, env, task)

    @patch.dict(os.environ, {
        "SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE": "1",
        "SWARM_BALANCE_B5B_EXTERNAL_HANDOFF": "1",
        "SWARM_BALANCE_B5F_QUEUE_RECONCILIATION": "0",
    })
    def test_B5f_08_default_off_refuses_persistent_return(self):
        d, env, task, _ = self._held()
        with self.assertRaisesRegex(ValueError, "B5F_FEATURE_DISABLED"):
            self.bridge(env).record_return(0, **self._proof(task))
        self.assert_held(d, env, task)
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    import unittest
    unittest.main()
