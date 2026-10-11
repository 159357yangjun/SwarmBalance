# -*- coding: utf-8 -*-
"""B5f experimental SQLite -> real Environment custody reconciliation.

The SQLite record is a durable *operator attestation intent*. An explicit
reconcile call compares it with the caller-supplied live or reconstructed
Environment, then calls the original B5b handoff exactly once (idempotently).
It is NOT a full simulator checkpoint, verified real rescue, or atomic
transaction spanning memory and SQLite. Single Env writer is required.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
from pathlib import Path

from console.custody_journal import _canonical


class DurableCustodyQueueBridge:
    def __init__(self, environment, path):
        self.env = environment
        self.path = Path(path)

    @staticmethod
    def _enabled():
        if (os.environ.get("SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE") != "1"
                or os.environ.get("SWARM_BALANCE_B5B_EXTERNAL_HANDOFF") != "1"
                or os.environ.get("SWARM_BALANCE_B5F_QUEUE_RECONCILIATION") != "1"):
            raise ValueError("[B5F_FEATURE_DISABLED] opt-in bridge only")

    @staticmethod
    def _normal(proof):
        required = ("event_id", "actor_id", "evidence_ref",
                    "receipt_position", "received_weight_kg", "disposition")
        if not isinstance(proof, dict) or any(k not in proof for k in required):
            raise ValueError("[B5F_INVALID_RECEIPT] incomplete attestation")
        for key in ("event_id", "actor_id", "evidence_ref"):
            if not isinstance(proof[key], str) or not proof[key].strip():
                raise ValueError("[B5F_INVALID_RECEIPT] " + key)
        if proof["disposition"] != "returned_to_original_source":
            raise ValueError("[B5F_INVALID_RECEIPT] unsupported disposition")
        point = proof["receipt_position"]
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise ValueError("[B5F_INVALID_RECEIPT] position shape")
        try:
            if any(isinstance(x, bool) for x in point):
                raise ValueError("bool coordinate")
            pos = [float(point[0]), float(point[1])]
            mass = proof["received_weight_kg"]
            if isinstance(mass, bool):
                raise ValueError("bool mass")
            mass = float(mass)
            if (not all(math.isfinite(x) for x in pos)
                    or not math.isfinite(mass) or mass <= 0):
                raise ValueError("nonfinite")
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("[B5F_INVALID_RECEIPT] invalid coordinates/mass") from exc
        return {"event_id": proof["event_id"].strip(),
                "actor_id": proof["actor_id"].strip(),
                "evidence_ref": proof["evidence_ref"].strip(),
                "receipt_position": pos, "received_weight_kg": mass,
                "disposition": proof["disposition"]}

    def _idx(self, drone_id):
        return self.env._drone_index_by_id(drone_id)

    def _assert_held(self, idx, proof, expected_task_id=None):
        d = self.env.drones[idx]
        if (not getattr(d, "out_of_service", False)
                or getattr(d, "cargo_custody_hold_reason", None)
                   != "picked_cargo_requires_external_handoff"):
            raise ValueError("[B5F_CUSTODY_NOT_HELD] no failed drone holding cargo")
        assignments = self.env.drone_assignments.get(idx)
        if (not isinstance(assignments, list) or len(assignments) != 1
                or not isinstance(assignments[0], dict)
                or assignments[0].get("task") is None
                or assignments[0].get("load_time") is None):
            raise ValueError("[B5F_ASSIGNMENT_MISMATCH] no single witnessed pickup")
        task = assignments[0]["task"]
        task_id = str(task.task_id)
        if (expected_task_id is not None and task_id != expected_task_id
                or str(getattr(d, "executing_task_id", None)) != task_id
                or task.status in ("pending", "failed", "completed")):
            raise ValueError("[B5F_ASSIGNMENT_MISMATCH] wrong custody owner or status")
        source = tuple(float(x) for x in task.get_source())
        point = proof["receipt_position"]
        if (len(source) != 2 or not all(math.isfinite(x) for x in source)
                or not all(math.isclose(a, b, rel_tol=0.0, abs_tol=1e-6)
                           for a, b in zip(source, point))):
            raise ValueError("[B5F_INVALID_RECEIPT] not returned to original source")
        weight = proof["received_weight_kg"]
        if (not all(math.isclose(float(v), weight, rel_tol=0.0, abs_tol=1e-6)
                    for v in (task.get_weight(),
                              getattr(d, "onboard_load_kg", 0),
                              getattr(d, "current_load", 0)))):
            raise ValueError("[B5F_INVALID_RECEIPT] receipt and onboard mass differ")
        if any(str(t.task_id) == task_id
               for t in self.env.task_generator.unassigned_tasks):
            raise ValueError("[B5F_ALREADY_QUEUED] cannot requeue twice")
        if any(str(a["task"].task_id) == task_id
               for k, vals in self.env.drone_assignments.items() if k != idx
               for a in (vals if isinstance(vals, list) else [vals])
               if isinstance(a, dict) and a.get("task") is not None):
            raise ValueError("[B5F_ASSIGNMENT_MISMATCH] already owned elsewhere")
        return task_id

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(self.path), timeout=10)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("""CREATE TABLE IF NOT EXISTS handoff_intents (
                event_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL UNIQUE,
                drone_idx INTEGER NOT NULL,
                fingerprint TEXT NOT NULL,
                proof_json TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('recorded','applied'))
            )""")
            db.commit()
            return db
        except BaseException:
            db.close()
            raise

    @staticmethod
    def _row(db, event_id):
        return db.execute(
            "SELECT event_id, task_id, drone_idx, fingerprint, proof_json, state "
            "FROM handoff_intents WHERE event_id=?", (event_id,)
        ).fetchone()

    def event_count(self):
        if not self.path.exists():
            return 0
        db = self._connect()
        try:
            return db.execute("SELECT COUNT(*) FROM handoff_intents").fetchone()[0]
        finally:
            db.close()

    def status(self, event_id):
        if not self.path.exists():
            return None
        db = self._connect()
        try:
            row = self._row(db, event_id)
            return row[-1] if row else None
        finally:
            db.close()

    def record_return(self, drone_id, *, fail_after=None, **attestation):
        self._enabled()
        if fail_after not in (None, "db_commit", "env_apply"):
            raise ValueError("[B5F_BAD_FAILPOINT] unsupported fault injection")
        idx = self._idx(drone_id)
        proof = self._normal(attestation)
        fingerprint = hashlib.sha256(_canonical(proof).encode("utf-8")).hexdigest()
        task_id = None
        # Check existing intent first to allow idempotent retry AFTER cargo was
        # released, without making a second transition.
        if self.path.exists():
            db = self._connect()
            try:
                old = self._row(db, proof["event_id"])
                if old:
                    if old[2] != idx or old[3] != fingerprint:
                        raise ValueError("[B5F_EVENT_CONFLICT] event ID has changed")
                    task_id = old[1]
                else:
                    # A new event ID cannot silently re-credit a task that
                    # this drone has ALREADY returned to the pending queue.
                    # Reject before the generic no-longer-held check. A later
                    # genuinely new pickup remains allowed if it is held.
                    d = self.env.drones[idx]
                    if not getattr(d, "cargo_custody_hold_reason", None):
                        previous = db.execute(
                            "SELECT task_id FROM handoff_intents "
                            "WHERE drone_idx=? AND state='applied'", (idx,)
                        ).fetchall()
                        pending = {str(t.task_id)
                                   for t in self.env.task_generator.unassigned_tasks}
                        if any(task in pending for (task,) in previous):
                            raise ValueError("[B5F_EVENT_CONFLICT] "
                                             "already returned task needs no new receipt")
            finally:
                db.close()

        if task_id is None:
            task_id = self._assert_held(idx, proof)
            db = self._connect()
            try:
                db.execute("BEGIN IMMEDIATE")
                old = self._row(db, proof["event_id"])
                if old is not None:
                    if old[1] != task_id or old[3] != fingerprint:
                        raise ValueError("[B5F_EVENT_CONFLICT] concurrent conflict")
                else:
                    try:
                        db.execute("INSERT INTO handoff_intents "
                                   "(event_id,task_id,drone_idx,fingerprint,proof_json,state) "
                                   "VALUES (?,?,?,?,?,'recorded')",
                                   (proof["event_id"], task_id, idx,
                                    fingerprint, _canonical(proof)))
                    except sqlite3.IntegrityError as exc:
                        raise ValueError("[B5F_EVENT_CONFLICT] task has another receipt") from exc
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

        if fail_after == "db_commit":
            raise RuntimeError("[B5F_INJECTED_CRASH] after SQLite commit")
        return self.reconcile(idx, proof["event_id"], fail_after=fail_after)

    def _already_applied(self, idx, task_id, proof):
        env = self.env
        events = getattr(env, "external_custody_events", None) or {}
        e = events.get(proof["event_id"])
        if not isinstance(e, dict):
            return False
        if (e.get("task_id") != task_id
                or e.get("drone_idx") != idx
                or e.get("operator_id") != proof["actor_id"]
                or e.get("evidence_ref") != proof["evidence_ref"]
                or e.get("received_weight_kg") != proof["received_weight_kg"]
                or list(e.get("receipt_position", ())) != proof["receipt_position"]):
            raise ValueError("[B5F_EVENT_CONFLICT] Environment event disagrees")
        d = env.drones[idx]
        pending = [t for t in env.task_generator.unassigned_tasks
                   if str(t.task_id) == task_id]
        if (len(pending) != 1 or pending[0].status != "pending"
                or env.drone_assignments.get(idx)
                or not d.out_of_service
                or not math.isclose(d.onboard_load_kg, 0.0, abs_tol=1e-9)):
            raise ValueError("[B5F_QUEUE_DIVERGENCE] event and active queue disagree")
        return True

    def reconcile(self, drone_id, event_id, *, fail_after=None):
        self._enabled()
        idx = self._idx(drone_id)
        if not self.path.exists():
            raise ValueError("[B5F_INTENT_MISSING] no durable handoff")
        # B5g opt-in: BEGIN IMMEDIATE serializes the entire
        # read -> live-Environment custody transition -> durable ACK for
        # competing callers using the SAME SQLite file and authoritative Env.
        # Existing B5f mode is unchanged. This is NOT a cross-process
        # simulator checkpoint or transaction spanning RAM and disk.
        serialized = os.environ.get("SWARM_BALANCE_B5G_SERIALIZED_RECONCILIATION") == "1"
        db = self._connect()
        try:
            if serialized:
                db.execute("BEGIN IMMEDIATE")  # acquire write lock BEFORE reading custody
            row = self._row(db, event_id)
            if row is None or row[2] != idx:
                raise ValueError("[B5F_INTENT_MISSING] wrong event or drone")
            _, task_id, _, fingerprint, proof_json, _ = row
            proof = json.loads(proof_json)
            if hashlib.sha256(_canonical(proof).encode("utf-8")).hexdigest() != fingerprint:
                raise ValueError("[B5F_LEDGER_CORRUPT] receipt disagrees with digest")
            applied_in_env = self._already_applied(idx, task_id, proof)
            if serialized and row[-1] == "applied" and not applied_in_env:
                # A rebuilt-but-stale simulator cannot silently earn a second
                # pending-queue credit for an already-committed DB event.
                raise ValueError("[B5G_STALE_ENV] durable applied event conflicts "
                                 "with live or reconstructed simulator state")
            changed = False
            if not applied_in_env:
                self._assert_held(idx, proof, expected_task_id=task_id)
                result = self.env.record_external_cargo_handoff(idx, **proof)
                if not result.get("changed") or result.get("requeued_task_ids") != [task_id]:
                    raise ValueError("[B5F_QUEUE_DIVERGENCE] unexpected Environment outcome")
                changed = True
                if fail_after == "env_apply":
                    raise RuntimeError("[B5F_INJECTED_CRASH] after Environment update")
            if row[-1] != "applied":
                db.execute("UPDATE handoff_intents SET state='applied' "
                           "WHERE event_id=?", (event_id,))
                db.commit()
            elif serialized:
                db.commit()  # release B5g SQLite write lock on idempotent replay
            return {"changed": changed, "requeued_task_ids": [task_id] if changed else [],
                    "event_id": event_id}
        except BaseException:
            if serialized:
                db.rollback()  # durable record remains 'recorded' after failed ACK
            raise
        finally:
            db.close()
