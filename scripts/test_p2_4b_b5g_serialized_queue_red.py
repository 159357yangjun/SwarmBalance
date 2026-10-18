# -*- coding: utf-8 -*-
"""B5g RED: opt-in serialized SQLite + live Environment custody reconciliation.

No persisted Environment checkpoint is invented. Two threads share one
authoritative simulator instance and local SQLite DB. A different reconstructed
but stale simulator must FAIL CLOSED after the durable event was applied.
"""
from __future__ import annotations

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from console.custody_queue_bridge import DurableCustodyQueueBridge
from scripts.test_p2_4b_b5f_queue_reconcile_red import B5fDurableQueueRed


B5G = {
    "SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE": "1",
    "SWARM_BALANCE_B5B_EXTERNAL_HANDOFF": "1",
    "SWARM_BALANCE_B5F_QUEUE_RECONCILIATION": "1",
    "SWARM_BALANCE_B5G_SERIALIZED_RECONCILIATION": "1",
}


class B5gSerializedQueueRed(B5fDurableQueueRed):
    @patch.dict("os.environ", B5G)
    def test_B5g_01_two_racing_reconcilers_release_once(self):
        d, env, task, _ = self._held()  # real source-service pickup
        receipt = self._proof(task)
        with self.assertRaisesRegex(RuntimeError, "B5F_INJECTED_CRASH"):
            self.bridge(env).record_return(0, **receipt, fail_after="db_commit")
        before = (d.get_position(), d.current_battery,
                  env.total_energy_consumed, env.total_flight_distance)
        start = Barrier(3)
        original = DurableCustodyQueueBridge._already_applied

        def widen_pre_apply_window(bridge, idx, task_id, proof):
            applied = original(bridge, idx, task_id, proof)
            if not applied:
                time.sleep(0.08)
            return applied

        def worker():
            start.wait(timeout=10)
            return self.bridge(env).reconcile(0, receipt["event_id"])

        with patch.object(DurableCustodyQueueBridge, "_already_applied",
                          widen_pre_apply_window):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(worker) for _ in range(2)]
                start.wait(timeout=10)
                results = [f.result(timeout=25) for f in futures]
        self.assertEqual(sorted(r["changed"] for r in results), [False, True],
                         "[B5G_CONCURRENT_DOUBLE_APPLY]")
        self.assert_requeued_once(d, env, task)
        self.assertEqual(self.bridge(env).event_count(), 1)
        self.assertEqual(self.bridge(env).status(receipt["event_id"]), "applied")
        self.assertEqual((d.get_position(), d.current_battery,
                          env.total_energy_consumed, env.total_flight_distance), before)

    @patch.dict("os.environ", B5G)
    def test_B5g_02_applied_db_rejects_stale_reconstructed_held_environment(self):
        d, env, task, _ = self._held()
        receipt = self._proof(task)
        self.assertTrue(self.bridge(env).record_return(0, **receipt)["changed"])
        self.assert_requeued_once(d, env, task)
        new_d, stale_env, stale_task, _ = self._held()
        self.assert_held(new_d, stale_env, stale_task)
        with self.assertRaisesRegex(ValueError, "B5G_STALE_ENV"):
            self.bridge(stale_env).reconcile(0, receipt["event_id"])
        self.assert_held(new_d, stale_env, stale_task)
        self.assertEqual(self.bridge(env).status(receipt["event_id"]), "applied")

    @patch.dict("os.environ", B5G)
    def test_B5g_03_database_ack_failure_leaves_recoverable_recorded_state(self):
        d, env, task, _ = self._held()
        receipt = self._proof(task)
        with self.assertRaisesRegex(RuntimeError, "B5F_INJECTED_CRASH"):
            self.bridge(env).record_return(0, **receipt, fail_after="db_commit")
        con = sqlite3.connect(self.db)
        try:
            con.execute("""
                CREATE TRIGGER b5g_reject_ack BEFORE UPDATE OF state
                ON handoff_intents WHEN NEW.state='applied'
                BEGIN SELECT RAISE(FAIL, 'simulated ACK disk write error'); END
            """)
            con.commit()
        finally:
            con.close()
        with self.assertRaises(sqlite3.IntegrityError):
            self.bridge(env).reconcile(0, receipt["event_id"])
        self.assert_requeued_once(d, env, task)
        self.assertEqual(self.bridge(env).status(receipt["event_id"]), "recorded")
        con = sqlite3.connect(self.db)
        try:
            con.execute("DROP TRIGGER b5g_reject_ack")
            con.commit()
        finally:
            con.close()
        self.assertFalse(self.bridge(env).reconcile(0, receipt["event_id"])["changed"])
        self.assertEqual(self.bridge(env).status(receipt["event_id"]), "applied")
        self.assert_requeued_once(d, env, task)

    @patch.dict("os.environ", B5G)
    def test_B5g_04_database_busy_fails_without_aircraft_mutation(self):
        d, env, task, _ = self._held()
        receipt = self._proof(task)
        with self.assertRaisesRegex(RuntimeError, "B5F_INJECTED_CRASH"):
            self.bridge(env).record_return(0, **receipt, fail_after="db_commit")
        held = sqlite3.connect(self.db, timeout=1, isolation_level=None)
        held.execute("BEGIN IMMEDIATE")
        real_connect = sqlite3.connect

        def short_timeout_connection(path, **kwargs):
            kwargs["timeout"] = 0.05
            return real_connect(path, **kwargs)

        try:
            with patch("console.custody_queue_bridge.sqlite3.connect",
                       side_effect=short_timeout_connection):
                with self.assertRaises(sqlite3.OperationalError):
                    self.bridge(env).reconcile(0, receipt["event_id"])
        finally:
            held.rollback()
            held.close()
        self.assert_held(d, env, task)
        self.assertEqual(self.bridge(env).status(receipt["event_id"]), "recorded")
        self.assertTrue(self.bridge(env).reconcile(0, receipt["event_id"])["changed"])
        self.assert_requeued_once(d, env, task)

    @patch.dict("os.environ", B5G)
    def test_B5g_05_two_distinct_event_ids_cannot_credit_same_cargo(self):
        d, env, task, _ = self._held()
        original = self._proof(task)
        alternate = self._proof(task, event_id="B5G-RACE-SECOND")
        first = self.bridge(env).record_return(0, **original)
        self.assertTrue(first["changed"])
        with self.assertRaisesRegex(ValueError, "B5F_EVENT_CONFLICT"):
            self.bridge(env).record_return(0, **alternate)
        self.assertEqual(self.bridge(env).event_count(), 1)
        self.assert_requeued_once(d, env, task)

    @patch.dict("os.environ", {
        "SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE": "1",
        "SWARM_BALANCE_B5B_EXTERNAL_HANDOFF": "1",
        "SWARM_BALANCE_B5F_QUEUE_RECONCILIATION": "1",
        "SWARM_BALANCE_B5G_SERIALIZED_RECONCILIATION": "0",
    })
    def test_B5g_06_optout_keeps_accepted_b5f_behavior(self):
        d, env, task, _ = self._held()
        receipt = self._proof(task)
        self.assertTrue(self.bridge(env).record_return(0, **receipt)["changed"])
        self.assertFalse(self.bridge(env).reconcile(0, receipt["event_id"])["changed"])
        self.assert_requeued_once(d, env, task)


if __name__ == "__main__":
    import unittest
    unittest.main()
