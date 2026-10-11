# -*- coding: utf-8 -*-
"""B5d opt-in-free *library* for auditable operator-attested receipt persistence.

This module is NOT plugged into Environment task requeue or simulator restart.
SHA-256 chain detects accidental byte changes, not a malicious actor capable
of rewriting the entire file. Filesystem fsync acknowledges local disk flush,
not distributed durability, identity authentication or physical cargo transfer.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path


def _canonical(obj):
    return json.dumps(obj, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


class CustodyJournal:
    def __init__(self, path):
        self.path = Path(path)

    @staticmethod
    def _validated(event):
        required = ("event_id", "task_id", "operator_id", "evidence_ref",
                    "receipt_position", "received_weight_kg", "disposition",
                    "custody_mode", "load_time", "drone_id",
                    "drone_position_at_handoff")
        if not isinstance(event, dict) or any(k not in event for k in required):
            raise ValueError("[B5D_INVALID_EVENT] missing fields")
        if any(not isinstance(event[k], str) or not event[k].strip()
               for k in ("event_id", "task_id", "operator_id",
                         "evidence_ref", "drone_id")):
            raise ValueError("[B5D_INVALID_EVENT] missing identity")
        if (event["disposition"] != "returned_to_original_source"
                or event["custody_mode"] !=
                "operator_attestation_not_physical_verification"):
            raise ValueError("[B5D_INVALID_EVENT] unrecognized attestation")
        for key in ("receipt_position", "drone_position_at_handoff"):
            pos = event[key]
            if (not isinstance(pos, (tuple, list)) or len(pos) != 2
                    or any(isinstance(v, bool) for v in pos)):
                raise ValueError("[B5D_INVALID_EVENT] invalid position")
            try:
                if not all(math.isfinite(float(v)) for v in pos):
                    raise ValueError("nonfinite")
            except (ValueError, TypeError, OverflowError) as exc:
                raise ValueError("[B5D_INVALID_EVENT] nonfinite point") from exc
        try:
            mass = event["received_weight_kg"]
            if isinstance(mass, bool) or not math.isfinite(float(mass)) or float(mass) <= 0:
                raise ValueError("bad mass")
            if not math.isfinite(float(event["load_time"])):
                raise ValueError("bad load_time")
            _canonical(event)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError("[B5D_INVALID_EVENT] malformed data") from exc
        return json.loads(_canonical(event))

    @staticmethod
    def _digest(seq, prev, event):
        return hashlib.sha256(_canonical(
            {"seq": seq, "prev": prev, "event": event}
        ).encode("utf-8")).hexdigest()

    def _read(self):
        if not self.path.exists():
            return []
        try:
            content = self.path.read_bytes()
            if content and not content.endswith(b"\n"):
                raise ValueError("truncated record")
            result, previous = [], "GENESIS"
            for line in content.splitlines():
                record = json.loads(line.decode("utf-8"))
                if (not isinstance(record, dict)
                        or set(record) != {"seq", "prev", "event", "digest"}
                        or type(record["seq"]) is not int
                        or record["seq"] != len(result) + 1
                        or record["prev"] != previous):
                    raise ValueError("invalid sequence")
                event = self._validated(record["event"])
                digest = self._digest(record["seq"], previous, event)
                if record["digest"] != digest:
                    raise ValueError("checksum mismatch")
                result.append(record)
                previous = digest
            return result
        except (UnicodeError, TypeError, KeyError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("[B5D_JOURNAL_CORRUPT] stop before any mutation") from exc

    def all_events(self):
        return [dict(row["event"]) for row in self._read()]

    def get(self, event_id):
        for event in self.all_events():
            if event["event_id"] == event_id:
                return event
        return None

    def append(self, event):
        valid = self._validated(event)
        rows = self._read()
        for row in rows:
            old = row["event"]
            if old["event_id"] == valid["event_id"]:
                if old == valid:
                    return {"changed": False, "event": dict(old)}
                raise ValueError("[B5D_EVENT_CONFLICT] same ID, changed receipt")
        seq = len(rows) + 1
        prev = rows[-1]["digest"] if rows else "GENESIS"
        record = {
            "seq": seq, "prev": prev, "event": valid,
            "digest": self._digest(seq, prev, valid),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Single-writer assumption: a future version MUST add OS-level locking
        # before permitting concurrent receipt producers.
        with self.path.open("ab") as out:
            out.write((_canonical(record) + "\n").encode("utf-8"))
            out.flush()
            os.fsync(out.fileno())
        return {"changed": True, "event": dict(valid)}
