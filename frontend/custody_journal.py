# -*- coding: utf-8 -*-
"""B5d experimental single-transaction custody intent journal (stdlib only).

A journal HMAC prevents accidental or unauthenticated edits only insofar as
the configured key remains secret. It does NOT authenticate a physical receipt.
Writing an intent BEFORE changing in-memory custody permits fail-closed replay
against a separate, matching restored simulator checkpoint. This module does
not persist/restore complete flight simulations or provide distributed locks.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
from pathlib import Path


FORMAT = "swarmbalance-b5d-v1"


def _secret(value):
    if not isinstance(value, str) or not value:
        raise ValueError("[B5D_SECRET_REQUIRED] nonempty separate audit key is required")
    return value.encode("utf-8")


def _path(value):
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise ValueError("[B5D_JOURNAL_PATH_REQUIRED] configure an isolated audit path")
    return Path(value)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _signed(payload, secret):
    signature = hmac.new(secret, _canonical({"format": FORMAT, "payload": payload}),
                         hashlib.sha256).hexdigest()
    return {"format": FORMAT, "payload": payload, "mac_sha256": signature}


def read_intent(path, secret):
    path = _path(path)
    secret = _secret(secret)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("[B5D_INTEGRITY] missing, truncated, or invalid journal") from exc
    if (not isinstance(data, dict) or data.get("format") != FORMAT
            or not isinstance(data.get("payload"), dict)
            or not isinstance(data.get("mac_sha256"), str)):
        raise ValueError("[B5D_INTEGRITY] unrecognized signed journal envelope")
    try:
        expected = _signed(data["payload"], secret)["mac_sha256"]
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("[B5D_INTEGRITY] journal not canonicalizable") from exc
    if not hmac.compare_digest(expected, data["mac_sha256"]):
        raise ValueError("[B5D_INTEGRITY] signed journal mismatch")
    return data["payload"]


def write_intent(path, payload, secret):
    """One immutable journal file per handoff transaction.

    Exclusive lock prevents concurrent cooperating writers. A crash leaving a
    stale lock intentionally fails closed until an operator reconciles it.
    Writes and fsyncs a same-directory temp file, then os.replace() it. No
    in-memory business state should be changed until this returns.
    """
    path = _path(path)
    secret = _secret(secret)
    try:
        encoded = _canonical(_signed(payload, secret))
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("[B5D_INVALID_PAYLOAD] nonfinite/nonserializable journal") from exc
    try:
        if path.exists():
            previous = read_intent(path, secret)
            if previous != payload:
                raise ValueError("[B5D_JOURNAL_CONFLICT] immutable receipt differs")
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = path.with_name(path.name + ".lock")
        try:
            fd = os.open(str(lock), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except OSError as exc:
            raise ValueError("[B5D_WRITE_FAILED] journal busy or lock unavailable") from exc
        try:
            os.close(fd)
            # A prior writer could have created the journal while lock waited.
            if path.exists():
                existing = read_intent(path, secret)
                if existing != payload:
                    raise ValueError("[B5D_JOURNAL_CONFLICT] immutable receipt differs")
                return False
            tmp = None
            try:
                with tempfile.NamedTemporaryFile(
                        mode="wb", dir=str(path.parent), prefix=".custody-",
                        suffix=".tmp", delete=False) as stream:
                    tmp = stream.name
                    stream.write(encoded)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(tmp, path)
                return True
            except OSError as exc:
                raise ValueError("[B5D_WRITE_FAILED] audit intent not durably staged") from exc
            finally:
                if tmp and os.path.exists(tmp):
                    os.unlink(tmp)
        finally:
            try:
                lock.unlink()
            except OSError:
                pass
    except OSError as exc:
        raise ValueError("[B5D_WRITE_FAILED] audit journal path unavailable") from exc


def manifest_snapshot(items, drone):
    """Canonical pre-commit identity needed to replay in a matching checkpoint."""
    return {
        "manifest": [{
            "task_id": str(a["task"].task_id),
            "status": str(a["task"].status),
            "load_time": a.get("load_time"),
            "weight_kg": float(a["task"].get_weight()),
            "source": list(a["task"].get_source()),
        } for a in items],
        "onboard_load_kg": float(getattr(drone, "onboard_load_kg", 0.0)),
        "assigned_load_kg": float(getattr(drone, "current_load", 0.0)),
    }
