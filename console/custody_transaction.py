# -*- coding: utf-8 -*-
"""B5e single-writer transaction-intent audit, NOT automatic queue replay.

A 'committed' record attests an external authoritative queue transition,
not an instruction to perform that transition again. There is no atomic
transaction spanning this file and Environment; callers MUST verify the
external queue token before committing. No physical operator authentication.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from console.custody_journal import CustodyJournal, _canonical


class CustodyTransactionLog:
    def __init__(self, path):
        self.path = Path(path)

    def _read(self):
        if not self.path.exists():
            return []
        try:
            data = self.path.read_bytes()
            if data and not data.endswith(b"\n"):
                raise ValueError("partial tail")
            records = []
            prev = "GENESIS"
            for raw in data.splitlines():
                row = json.loads(raw.decode("utf-8"))
                if (set(row) != {"seq", "prev", "entry", "digest"}
                        or type(row["seq"]) is not int or row["seq"] != len(records) + 1
                        or row["prev"] != prev
                        or not isinstance(row["entry"], dict)):
                    raise ValueError("wrong record type or sequence")
                expected = hashlib.sha256(_canonical({
                    "seq": row["seq"], "prev": prev, "entry": row["entry"],
                }).encode("utf-8")).hexdigest()
                if row["digest"] != expected:
                    raise ValueError("bad digest")
                entry = row["entry"]
                if entry.get("kind") not in ("prepared", "committed"):
                    raise ValueError("unknown entry")
                if not isinstance(entry.get("event_id"), str) or not entry["event_id"]:
                    raise ValueError("bad ID")
                records.append(row)
                prev = expected
            return records
        except (OSError, ValueError, UnicodeError, TypeError, KeyError) as exc:
            raise ValueError("[B5E_JOURNAL_CORRUPT] fail closed") from exc

    def _events(self):
        state = {}
        for row in self._read():
            e = row["entry"]
            ident = e["event_id"]
            if e["kind"] == "prepared":
                if ident in state:
                    raise ValueError("[B5E_JOURNAL_CORRUPT] repeated prepare")
                receipt = CustodyJournal._validated(e["receipt"])
                token = e.get("precondition_token")
                if not isinstance(token, str) or not token:
                    raise ValueError("[B5E_JOURNAL_CORRUPT] missing held token")
                state[ident] = {"kind": "prepared", "receipt": receipt,
                                "precondition_token": token}
            else:
                if ident not in state or state[ident]["kind"] != "prepared":
                    raise ValueError("[B5E_JOURNAL_CORRUPT] bad commit order")
                token = e.get("confirmed_token")
                if not isinstance(token, str) or not token.startswith("queued:"):
                    raise ValueError("[B5E_JOURNAL_CORRUPT] bad commit token")
                state[ident]["kind"] = "committed"
                state[ident]["confirmed_token"] = token
        return state

    def _append(self, entry):
        records = self._read()
        seq = len(records) + 1
        prev = records[-1]["digest"] if records else "GENESIS"
        digest = hashlib.sha256(_canonical({
            "seq": seq, "prev": prev, "entry": entry
        }).encode("utf-8")).hexdigest()
        row = {"seq": seq, "prev": prev, "entry": entry, "digest": digest}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as f:
            f.write((_canonical(row) + "\n").encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())

    def prepare(self, receipt, *, precondition_token):
        valid = CustodyJournal._validated(receipt)
        if not isinstance(precondition_token, str) or not precondition_token.startswith("held:"):
            raise ValueError("[B5E_PRECONDITION_MISMATCH] held task required")
        states = self._events()
        event_id = valid["event_id"]
        if event_id in states:
            previous = states[event_id]
            if previous["receipt"] != valid or previous["precondition_token"] != precondition_token:
                raise ValueError("[B5E_EVENT_CONFLICT] event ID already used")
            return {"changed": False}
        self._append({"kind": "prepared", "event_id": event_id,
                      "receipt": valid, "precondition_token": precondition_token})
        return {"changed": True}

    def commit(self, event_id, *, confirmed_token):
        states = self._events()
        if event_id not in states:
            raise ValueError("[B5E_NOT_PREPARED] no durable intent")
        if not isinstance(confirmed_token, str) or confirmed_token != "queued:"+states[event_id]["receipt"]["task_id"]+":once":
            raise ValueError("[B5E_PRECONDITION_MISMATCH] authoritative queue token required")
        prior = states[event_id]
        if prior["kind"] == "committed":
            return {"changed": False}
        self._append({"kind": "committed", "event_id": event_id,
                      "confirmed_token": confirmed_token})
        return {"changed": True}

    def state(self, event_id):
        return self._events().get(event_id, {}).get("kind")

    def recover(self):
        return sorted(k for k,v in self._events().items() if v["kind"]=="prepared")

    def ready_to_requeue(self):
        # Diagnostic ledger view only: no mutation of Environment/queue.
        return sorted(k for k,v in self._events().items() if v["kind"]=="committed")
