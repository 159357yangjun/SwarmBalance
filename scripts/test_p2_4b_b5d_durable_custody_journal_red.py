# -*- coding: utf-8 -*-
"""B5d RED: durable, tamper-evident B5c operator-attestation intent.

A fresh fixture represents a separately restored *matching* simulation state.
This does not claim arbitrary complete environment checkpoint/restore or that
the external operator's receipt establishes physical possession in real life.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts.test_p2_4b_b5c_mixed_chain_custody_red import B5cMixedChainCustodyRed

FLAGS = {
    "SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE": "1",
    "SWARM_BALANCE_B5B_EXTERNAL_HANDOFF": "1",
    "SWARM_BALANCE_B5C_MIXED_CHAIN_RELEASE": "1",
    "SWARM_BALANCE_B5D_CUSTODY_JOURNAL": "1",
    "SWARM_BALANCE_B5D_JOURNAL_HMAC_KEY": "test-only-strong-operator-not-physical-auth",
}

class B5dDurableCustodyRed(B5cMixedChainCustodyRed):
    def _path(self, root):
        return Path(root) / "cargo-return-record.json"

    def _take_snapshot(self, d, env):
        return (
            d.get_position(), d.current_battery, d.onboard_load_kg,
            d.current_load, d.executing_task_id, d.out_of_service,
            d.cargo_custody_hold_reason,
            tuple((a["task"].task_id, a.get("load_time"))
                  for a in env.drone_assignments.get(0, [])),
            tuple(t.task_id for t in env.task_generator.unassigned_tasks),
            env.total_energy_consumed, env.total_flight_distance,
            len(getattr(env, "external_custody_events", {})),
        )

    @patch.dict(os.environ, FLAGS)
    def test_B5d_01_durable_before_release_replay_into_matching_restored_fixture(self):
        with tempfile.TemporaryDirectory() as folder:
            d, env, t1, t2, _ = self._mixed()
            env.external_custody_journal_path = str(self._path(folder))
            receipt = self._receipt_for(t1)
            res = env.record_external_manifest_handoff(0, receipts=[receipt])
            self.assertTrue(res["changed"])
            raw = self._path(folder).read_bytes()
            self.assertGreater(len(raw), 150)
            envelope = json.loads(raw)
            self.assertEqual(envelope["format"], "swarmbalance-b5d-v1")
            self.assertIn("mac_sha256", envelope)
            self.assertNotIn(FLAGS["SWARM_BALANCE_B5D_JOURNAL_HMAC_KEY"], raw.decode())
            self.assertEqual(envelope["payload"]["receipts"][0]["event_id"], receipt["event_id"])
            self.assertEqual(envelope["payload"]["drone_id"], str(d.drone_id))
            self.assertTrue(d.out_of_service)
            self.assertEqual([t.task_id for t in env.task_generator.unassigned_tasks],
                             [t1.task_id, t2.task_id])

            # A fresh, independently reconstructed matching HELD checkpoint.
            # The original process and all mutable in-memory event dictionaries
            # are gone. Replay MUST be the only operation that transfers custody.
            recovered_d, recovered_env, rt1, rt2, _ = self._mixed()
            recovered_env.external_custody_journal_path = str(self._path(folder))
            before = self._take_snapshot(recovered_d, recovered_env)
            self.assertTrue(recovered_d.cargo_custody_hold_reason)
            recovered = recovered_env.replay_external_custody_journal(0)
            self.assertTrue(recovered["changed"])
            self.assertNotEqual(self._take_snapshot(recovered_d, recovered_env), before)
            self.assertEqual(recovered["requeued_task_ids"], [rt1.task_id, rt2.task_id])
            self.assertEqual(len(recovered_env.external_custody_events), 1)
            self.assertEqual(recovered_d.onboard_load_kg, 0.0)
            self.assertTrue(recovered_d.out_of_service)
            again = recovered_env.replay_external_custody_journal(0)
            self.assertFalse(again["changed"])
            self.assertEqual(again["requeued_task_ids"], [])
            self.assertEqual(len(recovered_env.task_generator.unassigned_tasks), 2)
            self.assertEqual(self._path(folder).read_bytes(), raw,
                             "[B5D_IDEMPOTENT_REPLAY_REWROTE_JOURNAL]")

    @patch.dict(os.environ, FLAGS)
    def test_B5d_02_tamper_refuses_recovery_without_partial_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            d, env, t1, _, _ = self._mixed()
            env.external_custody_journal_path = str(self._path(folder))
            env.record_external_manifest_handoff(0, receipts=[self._receipt_for(t1)])
            doc = json.loads(self._path(folder).read_text(encoding="utf-8"))
            doc["payload"]["receipts"][0]["received_weight_kg"] = 999.0
            self._path(folder).write_text(json.dumps(doc), encoding="utf-8")
            d2, e2, _, _, _ = self._mixed()
            e2.external_custody_journal_path = str(self._path(folder))
            before = self._take_snapshot(d2, e2)
            with self.assertRaisesRegex(ValueError, "B5D_INTEGRITY"):
                e2.replay_external_custody_journal(0)
            self.assertEqual(self._take_snapshot(d2, e2), before)

    @patch.dict(os.environ, FLAGS)
    def test_B5d_03_missing_secret_or_journal_path_fails_closed(self):
        d, env, t1, _, _ = self._mixed()
        proof = [self._receipt_for(t1)]
        before = self._take_snapshot(d, env)
        with self.assertRaisesRegex(ValueError, "B5D_JOURNAL_PATH_REQUIRED"):
            env.record_external_manifest_handoff(0, receipts=proof)
        self.assertEqual(self._take_snapshot(d, env), before)
        with tempfile.TemporaryDirectory() as folder:
            env.external_custody_journal_path = str(self._path(folder))
            with patch.dict(os.environ, {
                "SWARM_BALANCE_B5D_JOURNAL_HMAC_KEY": ""
            }):
                with self.assertRaisesRegex(ValueError, "B5D_SECRET_REQUIRED"):
                    env.record_external_manifest_handoff(0, receipts=proof)
            self.assertEqual(self._take_snapshot(d, env), before)
            self.assertFalse(self._path(folder).exists())

    @patch.dict(os.environ, FLAGS)
    def test_B5d_04_failed_disk_commit_does_not_release_real_cargo(self):
        with tempfile.TemporaryDirectory() as folder:
            d, env, t1, _, _ = self._mixed()
            # Path parent is an ordinary file, intentionally cannot mkdir.
            occupied = Path(folder) / "not-a-folder"
            occupied.write_text("occupied", encoding="utf-8")
            env.external_custody_journal_path = str(occupied / "handoff.json")
            before = self._take_snapshot(d, env)
            with self.assertRaisesRegex(ValueError, "B5D_WRITE_FAILED"):
                env.record_external_manifest_handoff(0, receipts=[self._receipt_for(t1)])
            self.assertEqual(self._take_snapshot(d, env), before)
            self.assertEqual(occupied.read_text(encoding="utf-8"), "occupied")

    @patch.dict(os.environ, FLAGS)
    def test_B5d_05_recovered_manifest_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            d, env, t1, _, _ = self._mixed()
            env.external_custody_journal_path = str(self._path(folder))
            env.record_external_manifest_handoff(0, receipts=[self._receipt_for(t1)])
            restored_d, restored_env, _, _, _ = self._mixed()
            restored_env.external_custody_journal_path = str(self._path(folder))
            restored_d.onboard_load_kg = 0.4  # checkpoint disagrees with audit record
            before = self._take_snapshot(restored_d, restored_env)
            with self.assertRaisesRegex(ValueError, "B5C_CARGO_MASS_NOT_CONSERVED"):
                restored_env.replay_external_custody_journal(0)
            self.assertEqual(self._take_snapshot(restored_d, restored_env), before)

    @patch.dict(os.environ, FLAGS)
    def test_B5d_06_different_event_not_overwrite_existing_durable_log(self):
        with tempfile.TemporaryDirectory() as folder:
            d, env, t1, _, _ = self._mixed()
            env.external_custody_journal_path = str(self._path(folder))
            receipt = self._receipt_for(t1)
            env.record_external_manifest_handoff(0, receipts=[receipt])
            old = self._path(folder).read_bytes()
            d2, env2, t12, _, _ = self._mixed()
            env2.external_custody_journal_path = str(self._path(folder))
            with self.assertRaisesRegex(ValueError, "B5D_JOURNAL_CONFLICT"):
                env2.record_external_manifest_handoff(
                    0, receipts=[self._receipt_for(t12, event_id="different-id")])
            self.assertEqual(self._path(folder).read_bytes(), old)
            self.assertAlmostEqual(d2.onboard_load_kg, 0.5)
            self.assertFalse(env2.task_generator.unassigned_tasks)

    @patch.dict(os.environ, {
        "SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE": "1",
        "SWARM_BALANCE_B5B_EXTERNAL_HANDOFF": "1",
        "SWARM_BALANCE_B5C_MIXED_CHAIN_RELEASE": "1",
        "SWARM_BALANCE_B5D_CUSTODY_JOURNAL": "0",
    })
    def test_B5d_07_default_off_keeps_original_b5c_in_memory_contract(self):
        d, env, t1, t2, _ = self._mixed()
        outcome = env.record_external_manifest_handoff(
            0, receipts=[self._receipt_for(t1)])
        self.assertEqual(outcome["requeued_task_ids"], [t1.task_id, t2.task_id])
        self.assertFalse(hasattr(env, "external_custody_journal_path"))

if __name__ == "__main__":
    import unittest
    unittest.main()
