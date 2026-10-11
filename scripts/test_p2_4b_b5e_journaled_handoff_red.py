# -*- coding: utf-8 -*-
"""B5e RED-first: durable PREPARE before queue release; COMMIT after in-memory apply.

This is a single-writer, operator-attested simulation protocol. A PREPARE left
behind by a crash MUST become an explicit reconciliation block, not an auto-
replayed delivery or inferred physical pickup. It is NOT a full simulator
checkpoint or multi-process database transaction.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts.test_p2_4b_b5c_mixed_chain_custody_red import B5cMixedChainCustodyRed

FLAGS = {
    "SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE": "1",
    "SWARM_BALANCE_B5B_EXTERNAL_HANDOFF": "1",
    "SWARM_BALANCE_B5C_MIXED_CHAIN_RELEASE": "1",
    "SWARM_BALANCE_B5E_JOURNALED_HANDOFF": "1",
}


class B5eJournaledHandoffRed(B5cMixedChainCustodyRed):
    def _journal(self):
        from console.custody_transaction import CustodyTransactionLog, HandoffCoordinator
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        log = CustodyTransactionLog(Path(tmp.name) / "handoff.wal")
        return log, HandoffCoordinator

    def _snapshot(self, d, env, tasks):
        return (d.get_position(), d.current_battery,
                env.total_energy_consumed, env.total_flight_distance,
                d.onboard_load_kg, d.current_load, d.executing_task_id,
                d.cargo_custody_hold_reason, d.out_of_service,
                tuple(d.scheduled_position), tuple(t.status for t in tasks),
                tuple((a["task"].task_id, a.get("load_time"))
                      for a in env.drone_assignments.get(0, [])),
                tuple(t.task_id for t in env.task_generator.unassigned_tasks))

    @patch.dict(os.environ, FLAGS)
    def test_B5e_01_prepare_io_failure_cannot_release_cargo_or_orders(self):
        d, env, t1, t2, _ = self._mixed()
        log, Coordinator = self._journal()
        snap = self._snapshot(d, env, [t1, t2])
        with patch.object(log, "_append_record", side_effect=OSError("disk unavailable")):
            with self.assertRaisesRegex(OSError, "disk unavailable"):
                Coordinator(env, log).handoff(0, [self._receipt_for(t1)])
        self.assertEqual(self._snapshot(d, env, [t1, t2]), snap)
        self.assertEqual(log.in_doubt(), [])

    @patch.dict(os.environ, FLAGS)
    def test_B5e_02_invalid_receipt_fails_before_any_durable_intent(self):
        d, env, t1, t2, _ = self._mixed()
        log, Coordinator = self._journal()
        snap = self._snapshot(d, env, [t1, t2])
        with self.assertRaisesRegex(ValueError, "B5C_"):
            Coordinator(env, log).handoff(
                0, [{**self._receipt_for(t1), "received_weight_kg": 9.0}])
        self.assertFalse(log.path.exists(), "[B5E_INVALID_EVIDENCE_WAS_JOURNALED]")
        self.assertEqual(self._snapshot(d, env, [t1, t2]), snap)

    @patch.dict(os.environ, FLAGS)
    def test_B5e_03_durable_prepare_then_commit_then_replay_is_exact_once(self):
        d, env, t1, t2, _ = self._mixed()
        log, Coordinator = self._journal()
        proof = self._receipt_for(t1)
        before = (d.get_position(), d.current_battery,
                  env.total_energy_consumed, env.total_flight_distance)
        result = Coordinator(env, log).handoff(0, [proof])
        self.assertTrue(result["changed"])
        self.assertEqual(result["requeued_task_ids"], [t1.task_id, t2.task_id])
        self.assertEqual((d.get_position(), d.current_battery,
                          env.total_energy_consumed, env.total_flight_distance), before)
        self.assertTrue(d.out_of_service)
        self.assertEqual(len(env.task_generator.unassigned_tasks), 2)
        from console.custody_transaction import CustodyTransactionLog
        reopened = CustodyTransactionLog(log.path)
        self.assertEqual(reopened.in_doubt(), [])
        self.assertEqual(len(reopened.committed()), 1)
        again = Coordinator(env, reopened).handoff(0, [proof])
        self.assertFalse(again["changed"])
        self.assertEqual(again["requeued_task_ids"], [])
        self.assertEqual(len(env.task_generator.unassigned_tasks), 2)

    @patch.dict(os.environ, FLAGS)
    def test_B5e_04_crash_after_prepare_stays_held_on_restart(self):
        d, env, t1, t2, _ = self._mixed()
        log, Coordinator = self._journal()
        proof = self._receipt_for(t1)
        snap = self._snapshot(d, env, [t1, t2])
        def crash():
            raise SystemExit("injected process termination before state commit")
        with self.assertRaises(SystemExit):
            Coordinator(env, log).handoff(0, [proof], after_prepare=crash)
        self.assertEqual(self._snapshot(d, env, [t1, t2]), snap)
        from console.custody_transaction import CustodyTransactionLog
        reopened = CustodyTransactionLog(log.path)
        self.assertEqual(len(reopened.in_doubt()), 1)
        self.assertEqual(reopened.committed(), [])
        with self.assertRaisesRegex(ValueError, "B5E_IN_DOUBT"):
            Coordinator(env, reopened).handoff(0, [proof])
        self.assertEqual(self._snapshot(d, env, [t1, t2]), snap)

    @patch.dict(os.environ, FLAGS)
    def test_B5e_05_changed_receipt_after_commit_rejected(self):
        d, env, t1, t2, _ = self._mixed()
        log, Coordinator = self._journal()
        Coordinator(env, log).handoff(0, [self._receipt_for(t1)])
        with self.assertRaisesRegex(ValueError, "B5E_EVENT_CONFLICT"):
            Coordinator(env, log).handoff(
                0, [{**self._receipt_for(t1), "actor_id": "new-operator"}])
        self.assertEqual(len(env.task_generator.unassigned_tasks), 2)
        self.assertEqual(len(log.committed()), 1)

    @patch.dict(os.environ, FLAGS)
    def test_B5e_06_two_real_pickups_require_one_durable_batch(self):
        d, env, t1, t2, _ = self._mixed()
        d.out_of_service = False
        d.cargo_custody_hold_reason = None
        d.is_free = False
        env.step({})
        self.assertIsNotNone(env.drone_assignments[0][1]["load_time"])
        self.assertAlmostEqual(d.onboard_load_kg, 1.2)
        env.set_drone_out_of_service(0, True)
        log, Coordinator = self._journal()
        proofs = [self._receipt_for(t1),
                  self._receipt_for(t2, event_id="B5E-RECEIPT-T2")]
        result = Coordinator(env, log).handoff(0, proofs)
        self.assertEqual(result["requeued_task_ids"], [t1.task_id, t2.task_id])
        self.assertEqual(len(log.committed()), 1)
        self.assertEqual(log.in_doubt(), [])
        self.assertEqual(len(env.task_generator.unassigned_tasks), 2)

    @patch.dict(os.environ, {
        "SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE": "1",
        "SWARM_BALANCE_B5B_EXTERNAL_HANDOFF": "1",
        "SWARM_BALANCE_B5C_MIXED_CHAIN_RELEASE": "1",
        "SWARM_BALANCE_B5E_JOURNALED_HANDOFF": "0",
    })
    def test_B5e_07_optout_cannot_create_transaction(self):
        d, env, t1, t2, _ = self._mixed()
        log, Coordinator = self._journal()
        snap = self._snapshot(d, env, [t1, t2])
        with self.assertRaisesRegex(ValueError, "B5E_FEATURE_DISABLED"):
            Coordinator(env, log).handoff(0, [self._receipt_for(t1)])
        self.assertFalse(log.path.exists())
        self.assertEqual(self._snapshot(d, env, [t1, t2]), snap)


    @patch.dict(os.environ, FLAGS)
    def test_B5e_08_commit_fsync_failure_is_in_doubt_not_replayed(self):
        d, env, t1, t2, _ = self._mixed()
        log, Coordinator = self._journal()
        proof = self._receipt_for(t1)
        with patch.object(log, "commit", side_effect=OSError("commit fsync failed")):
            with self.assertRaisesRegex(RuntimeError, "B5E_COMMIT_UNCERTAIN"):
                Coordinator(env, log).handoff(0, [proof])
        self.assertEqual(len(env.task_generator.unassigned_tasks), 2)
        from console.custody_transaction import CustodyTransactionLog
        reopened = CustodyTransactionLog(log.path)
        self.assertEqual(len(reopened.in_doubt()), 1)
        with self.assertRaisesRegex(ValueError, "B5E_IN_DOUBT"):
            Coordinator(env, reopened).handoff(0, [proof])
        self.assertEqual(len(env.task_generator.unassigned_tasks), 2,
                         "[B5E_IN_DOUBT_REPLAY_DUPLICATED_QUEUE]")

    @patch.dict(os.environ, FLAGS)
    def test_B5e_09_corrupt_wal_blocks_replay_without_state_mutation(self):
        d, env, t1, t2, _ = self._mixed()
        log, Coordinator = self._journal()
        proof = self._receipt_for(t1)
        snap = self._snapshot(d, env, [t1, t2])
        def crash():
            raise SystemExit("stop after durable prepare")
        with self.assertRaises(SystemExit):
            Coordinator(env, log).handoff(0, [proof], after_prepare=crash)
        with log.path.open("ab") as handle:
            handle.write(b'{"incomplete":')
        from console.custody_transaction import CustodyTransactionLog
        with self.assertRaisesRegex(ValueError, "B5E_JOURNAL_CORRUPT"):
            Coordinator(env, CustodyTransactionLog(log.path)).handoff(0, [proof])
        self.assertEqual(self._snapshot(d, env, [t1, t2]), snap)

    @patch.dict(os.environ, FLAGS)
    def test_B5e_10_stale_new_session_cannot_assume_durable_commit_replayed(self):
        d, env, t1, t2, _ = self._mixed()
        log, Coordinator = self._journal()
        proof = self._receipt_for(t1)
        Coordinator(env, log).handoff(0, [proof])
        # A newly created simulation object still has faulted cargo onboard.
        # Persisted COMMIT is not an Environment checkpoint.
        d2, env2, tt1, tt2, _ = self._mixed()
        snap = self._snapshot(d2, env2, [tt1, tt2])
        from console.custody_transaction import CustodyTransactionLog
        with self.assertRaisesRegex(ValueError, "B5E_RECONCILIATION_REQUIRED"):
            Coordinator(env2, CustodyTransactionLog(log.path)).handoff(
                0, [self._receipt_for(tt1)])
        self.assertEqual(self._snapshot(d2, env2, [tt1, tt2]), snap)


if __name__ == "__main__":
    import unittest
    unittest.main()
