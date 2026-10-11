# -*- coding: utf-8 -*-
"""B5e RED: crash-safe custody intent / commit recovery, no blind requeue.

A persisted operator attestation is NOT the same as a committed simulator
task/queue transition. Reconciliation must fail closed until authoritative
task-state confirmation; these tests intentionally do not claim full restart
of the Environment or real-world physical custody verification.
"""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path

from console.custody_transaction import CustodyTransactionLog


class B5eTransactionRed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "custody-transaction.jsonl"

    def receipt(self, event="receipt-A"):
        return {
            "event_id": event, "task_id": "T1", "operator_id": "operator-1",
            "evidence_ref": "manual-receipt-1", "drone_id": "0",
            "receipt_position": [20.0, 0.0],
            "drone_position_at_handoff": [40.0, 0.0],
            "received_weight_kg": 0.5, "load_time": 1.0,
            "disposition": "returned_to_original_source",
            "custody_mode": "operator_attestation_not_physical_verification",
        }

    def test_B5e_01_durable_prepared_not_automatically_committed(self):
        log = CustodyTransactionLog(self.path)
        log.prepare(self.receipt(), precondition_token="held:T1:0.5")
        new_process = CustodyTransactionLog(self.path)
        self.assertEqual(new_process.state("receipt-A"), "prepared")
        self.assertEqual(new_process.recover(), ["receipt-A"])
        self.assertEqual(new_process.ready_to_requeue(), [],
                         "[B5E_PREPARED_ONLY_REQUEUED]")

    def test_B5e_02_explicit_commit_requires_matching_authoritative_token(self):
        log = CustodyTransactionLog(self.path)
        log.prepare(self.receipt(), precondition_token="held:T1:0.5")
        with self.assertRaisesRegex(ValueError, "B5E_PRECONDITION_MISMATCH"):
            log.commit("receipt-A", confirmed_token="queued:T1:WRONG")
        self.assertEqual(log.state("receipt-A"), "prepared")
        self.assertTrue(log.commit("receipt-A", confirmed_token="queued:T1:once")["changed"])
        self.assertEqual(CustodyTransactionLog(self.path).state("receipt-A"), "committed")
        self.assertEqual(CustodyTransactionLog(self.path).ready_to_requeue(),
                         ["receipt-A"])

    def test_B5e_03_idempotent_replay_never_creates_second_queue_credit(self):
        log = CustodyTransactionLog(self.path)
        log.prepare(self.receipt(), precondition_token="held:T1:0.5")
        log.commit("receipt-A", confirmed_token="queued:T1:once")
        self.assertFalse(CustodyTransactionLog(self.path).prepare(
            self.receipt(), precondition_token="held:T1:0.5")["changed"])
        self.assertFalse(CustodyTransactionLog(self.path).commit(
            "receipt-A", confirmed_token="queued:T1:once")["changed"])
        self.assertEqual(CustodyTransactionLog(self.path).ready_to_requeue(),
                         ["receipt-A"])

    def test_B5e_04_conflicting_event_id_fails_closed_without_mutation(self):
        log = CustodyTransactionLog(self.path)
        log.prepare(self.receipt(), precondition_token="held:T1:0.5")
        changed = self.receipt()
        changed["received_weight_kg"] = 0.7
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "B5E_EVENT_CONFLICT"):
            log.prepare(changed, precondition_token="held:T1:0.5")
        self.assertEqual(before, self.path.read_bytes())

    def test_B5e_05_corrupt_tail_prevents_recovery_or_additional_commits(self):
        log = CustodyTransactionLog(self.path)
        log.prepare(self.receipt(), precondition_token="held:T1:0.5")
        with self.path.open("ab") as f:
            f.write(b'{"incomplete":')
        original = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "B5"):
            CustodyTransactionLog(self.path).recover()
        with self.assertRaisesRegex(ValueError, "B5"):
            CustodyTransactionLog(self.path).commit(
                "receipt-A", confirmed_token="queued:T1:once")
        self.assertEqual(self.path.read_bytes(), original)

    def test_B5e_06_bare_attestation_must_not_authorize_replay(self):
        from console.custody_journal import CustodyJournal
        CustodyJournal(self.path).append(self.receipt())
        with self.assertRaisesRegex(ValueError, "B5E_"):
            CustodyTransactionLog(self.path).ready_to_requeue()


if __name__ == "__main__":
    unittest.main()
