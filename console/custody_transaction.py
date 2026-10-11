# -*- coding: utf-8 -*-
"""B5e experimental single-writer write-ahead protocol for B5c manifest release.

PREPARE is fsynced *before* volatile task-state mutation; COMMIT is fsynced
after it. A surviving PREPARE is deliberately IN-DOUBT and must NOT auto-replay
an order. This is NOT a durable Environment snapshot, an authenticated receipt,
or an atomic database transaction across disk and RAM. No concurrent writers.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from console.custody_journal import _canonical


def _stable(obj):
    return json.loads(_canonical(obj))


class CustodyTransactionLog:
    def __init__(self, path):
        self.path = Path(path)

    @staticmethod
    def _identity(drone_idx, receipts):
        if not isinstance(receipts, (list, tuple)) or not receipts:
            raise ValueError("[B5E_INVALID_RECEIPTS] nonempty list required")
        if not all(isinstance(p, dict) and isinstance(p.get("event_id"), str)
                   and p["event_id"].strip() for p in receipts):
            raise ValueError("[B5E_INVALID_RECEIPTS] missing event_id")
        event_ids = [p["event_id"] for p in receipts]
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("[B5E_INVALID_RECEIPTS] duplicate event_id")
        return hashlib.sha256(_canonical(
            {"drone_idx": int(drone_idx), "event_ids": sorted(event_ids)}
        ).encode("utf-8")).hexdigest()

    @staticmethod
    def _payload(drone_idx, receipts, expected_task_ids):
        values = _stable(receipts)
        values.sort(key=lambda d: d["event_id"])
        return {
            "drone_idx": int(drone_idx), "receipts": values,
            "expected_task_ids": list(expected_task_ids),
        }

    @staticmethod
    def _digest(seq, prev, txn_id, phase, payload):
        return hashlib.sha256(_canonical({
            "seq": seq, "prev": prev, "txn_id": txn_id,
            "phase": phase, "payload": payload,
        }).encode("utf-8")).hexdigest()

    def _read(self):
        if not self.path.exists():
            return []
        try:
            contents = self.path.read_bytes()
            if contents and not contents.endswith(b"\n"):
                raise ValueError("incomplete tail")
            rows = []
            prev = "GENESIS"
            stages = {}
            for raw in contents.splitlines():
                row = json.loads(raw.decode("utf-8"))
                if (not isinstance(row, dict)
                        or set(row) != {"seq", "prev", "txn_id", "phase",
                                       "payload", "digest"}
                        or type(row["seq"]) is not int
                        or row["seq"] != len(rows) + 1
                        or row["prev"] != prev
                        or not isinstance(row["txn_id"], str)
                        or row["phase"] not in ("PREPARE", "COMMIT")
                        or not isinstance(row["payload"], dict)):
                    raise ValueError("invalid journal record")
                digest = self._digest(row["seq"], row["prev"], row["txn_id"],
                                      row["phase"], row["payload"])
                if row["digest"] != digest:
                    raise ValueError("digest mismatch")
                state = stages.get(row["txn_id"])
                if row["phase"] == "PREPARE":
                    if state is not None:
                        raise ValueError("repeated PREPARE")
                    stages[row["txn_id"]] = ("PREPARE", row["payload"])
                else:
                    if state is None or state[0] != "PREPARE" or state[1] != row["payload"]:
                        raise ValueError("COMMIT without matching PREPARE")
                    stages[row["txn_id"]] = ("COMMIT", row["payload"])
                rows.append(row)
                prev = digest
            return rows
        except (UnicodeError, TypeError, ValueError, KeyError, OverflowError) as exc:
            raise ValueError("[B5E_JOURNAL_CORRUPT] stop until operator reconciliation") from exc

    def _states(self):
        states = {}
        for row in self._read():
            states[row["txn_id"]] = {
                "txn_id": row["txn_id"],
                "phase": row["phase"],
                "payload": row["payload"],
            }
        return states

    def in_doubt(self):
        return [dict(s) for s in self._states().values() if s["phase"] == "PREPARE"]

    def committed(self):
        return [dict(s) for s in self._states().values() if s["phase"] == "COMMIT"]

    def lookup(self, drone_idx, receipts):
        tid = self._identity(drone_idx, receipts)
        stages = self._states()
        state = stages.get(tid)
        if state is not None:
            current = self._payload(drone_idx, receipts,
                                    state["payload"]["expected_task_ids"])
            if state["payload"] != current:
                raise ValueError("[B5E_EVENT_CONFLICT] same IDs but changed evidence")
            return dict(state)
        incoming = {p["event_id"] for p in receipts}
        for prior in stages.values():
            existing = {p["event_id"] for p in prior["payload"]["receipts"]}
            if incoming.intersection(existing):
                raise ValueError("[B5E_EVENT_CONFLICT] event already belongs to another manifest")
        return None

    def _append_record(self, txn_id, phase, payload):
        rows = self._read()  # corruption must be detected BEFORE writing
        seq = len(rows) + 1
        prev = rows[-1]["digest"] if rows else "GENESIS"
        row = {
            "seq": seq, "prev": prev, "txn_id": txn_id,
            "phase": phase, "payload": payload,
            "digest": self._digest(seq, prev, txn_id, phase, payload),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as handle:
            handle.write((_canonical(row) + "\n").encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        return row

    def prepare(self, drone_idx, receipts, expected_task_ids):
        if self.lookup(drone_idx, receipts) is not None:
            raise ValueError("[B5E_IN_DOUBT] previously recorded; reconcile explicitly")
        tid = self._identity(drone_idx, receipts)
        payload = self._payload(drone_idx, receipts, expected_task_ids)
        self._append_record(tid, "PREPARE", payload)
        return tid

    def commit(self, txn_id):
        state = self._states().get(txn_id)
        if state is None or state["phase"] != "PREPARE":
            raise ValueError("[B5E_IN_DOUBT] no pending matching PREPARE")
        self._append_record(txn_id, "COMMIT", state["payload"])


class HandoffCoordinator:
    def __init__(self, environment, journal):
        self.environment = environment
        self.journal = journal

    def handoff(self, drone_id, receipts, *, after_prepare=None):
        if os.environ.get("SWARM_BALANCE_B5E_JOURNALED_HANDOFF") != "1":
            raise ValueError("[B5E_FEATURE_DISABLED] transaction gate is OFF")
        env = self.environment
        idx = env._drone_index_by_id(drone_id)
        prior = self.journal.lookup(idx, receipts)
        if prior is not None:
            if prior["phase"] == "PREPARE":
                raise ValueError("[B5E_IN_DOUBT] manual state reconciliation required")
            pending = [str(t.task_id) for t in env.task_generator.unassigned_tasks]
            expected = prior["payload"]["expected_task_ids"]
            if (any(pending.count(tid) != 1 for tid in expected)
                    or env.drone_assignments.get(idx)):
                raise ValueError("[B5E_RECONCILIATION_REQUIRED] journal and tasks disagree")
            return {"drone_idx": idx, "changed": False, "requeued_task_ids": []}

        # Exact same identity, mass, source and mixed-chain checks as B5c,
        # but NO mutation is permitted during this dry-run validation.
        preview = env.record_external_manifest_handoff(
            idx, receipts=receipts, preview_only=True)
        if not preview.get("validated"):
            raise ValueError("[B5E_INVALID_PREVIEW] already applied without journal")
        txn_id = self.journal.prepare(
            idx, receipts, preview["requeued_task_ids"])
        if after_prepare is not None:
            after_prepare()  # deliberate crash injection, never auto-replayed
        result = env.record_external_manifest_handoff(idx, receipts=receipts)
        try:
            self.journal.commit(txn_id)
        except Exception as exc:
            # No claim of atomic rollback across a failed COMMIT fsync.
            # The surviving PREPARE blocks automatic replay after restart.
            raise RuntimeError(
                "[B5E_COMMIT_UNCERTAIN] no further dispatch before reconciliation"
            ) from exc
        return result
