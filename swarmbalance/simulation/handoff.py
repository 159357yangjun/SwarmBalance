"""Handoff operations on the owning Environment state."""
from __future__ import annotations

def record_external_cargo_handoff(
        environment, drone_id, *, event_id, actor_id, evidence_ref,
        receipt_position, received_weight_kg, disposition):
    """B5b opt-in, *operator-attested* physical return to ORIGINAL source.

    This endpoint records an external operator's supplied receipt; it does
    NOT verify real-world provenance, move an aircraft, or credit battery.
    Restrict to exactly one actually picked task. Mixed task chains and
    unsupported partial transfers fail closed pending a later design.
    All validation precedes every state mutation.
    """
    from swarmbalance.simulation.environment import (math, os)
    if (os.environ.get("SWARM_BALANCE_B5B_EXTERNAL_HANDOFF") != "1"
            or os.environ.get("SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE") != "1"):
        raise ValueError("[B5B_FEATURE_DISABLED] experimental manual return only")
    idx = environment._drone_index_by_id(drone_id)
    drone = environment.drones[idx]

    def _text(value, label):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("[B5B_INVALID_RECEIPT] " + label + " is required")
        return value.strip()

    event_id = _text(event_id, "event_id")
    actor_id = _text(actor_id, "actor_id")
    evidence_ref = _text(evidence_ref, "evidence_ref")
    if disposition != "returned_to_original_source":
        raise ValueError("[B5B_INVALID_DISPOSITION] no implicit customer delivery")

    try:
        if not isinstance(receipt_position, (list, tuple)) or len(receipt_position) != 2:
            raise ValueError("wrong point shape")
        point = (float(receipt_position[0]), float(receipt_position[1]))
        if not all(math.isfinite(v) for v in point):
            raise ValueError("nonfinite point")
        if isinstance(received_weight_kg, bool):
            raise ValueError("bool is not mass")
        mass = float(received_weight_kg)
        if not math.isfinite(mass) or mass <= 0:
            raise ValueError("invalid mass")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("[B5B_INVALID_RECEIPT] finite position and mass required") from exc

    events = getattr(environment, "external_custody_events", None)
    if events is not None and event_id in events:
        prior = events[event_id]
        if (prior["drone_idx"] == idx
                and prior["operator_id"] == actor_id
                and prior["evidence_ref"] == evidence_ref
                and prior["receipt_position"] == point
                and prior["received_weight_kg"] == mass
                and prior["disposition"] == disposition):
            return {"drone_idx": idx, "changed": False, "requeued_task_ids": [],
                    "custody_event": dict(prior)}
        raise ValueError("[B5B_EVENT_CONFLICT] event ID already bound to another receipt")

    if (not getattr(drone, "out_of_service", False)
            or getattr(drone, "cargo_custody_hold_reason", None)
               != "picked_cargo_requires_external_handoff"):
        raise ValueError("[B5B_NOT_HELD] no failed drone with witnessed cargo")
    assigned = environment.drone_assignments.get(idx)
    tasks = (assigned if isinstance(assigned, list)
             else [assigned] if assigned is not None else [])
    if len(tasks) != 1 or not isinstance(tasks[0], dict):
        raise ValueError("[B5B_CHAIN_HANDOFF_NOT_SUPPORTED] partial/mixed tasks rejected")
    assignment = tasks[0]
    task = assignment.get("task")
    if task is None or assignment.get("load_time") is None:
        raise ValueError("[B5B_NOT_PICKED] no real consumed source waypoint")
    task_id = str(task.task_id)
    if (task_id != str(getattr(drone, "executing_task_id", None))
            or task.status in ("pending", "completed", "failed")):
        raise ValueError("[B5B_ASSIGNMENT_MISMATCH] custody identity not stable")

    source = tuple(float(p) for p in task.get_source())
    if len(source) != 2 or not all(math.isfinite(p) for p in source):
        raise ValueError("[B5B_INVALID_SOURCE] no verified original pickup coordinates")
    if not all(math.isclose(a, b, rel_tol=0.0, abs_tol=1e-6)
               for a, b in zip(point, source)):
        raise ValueError("[B5B_WRONG_RECEIPT_LOCATION] cannot requeue from remote holder")

    task_weight = float(task.get_weight())
    onboard = float(getattr(drone, "onboard_load_kg", 0.0))
    assigned_kg = float(getattr(drone, "current_load", 0.0))
    if (not all(math.isfinite(v) and v > 0
                for v in (task_weight, onboard, assigned_kg))
            or not math.isclose(mass, task_weight, rel_tol=0.0, abs_tol=1e-6)
            or not math.isclose(mass, onboard, rel_tol=0.0, abs_tol=1e-6)
            or not math.isclose(mass, assigned_kg, rel_tol=0.0, abs_tol=1e-6)):
        raise ValueError("[B5B_WEIGHT_NOT_CONSERVED] receipt != witnessed load")

    if any(str(t.task_id) == task_id
           for t in environment.task_generator.unassigned_tasks):
        raise ValueError("[B5B_ALREADY_QUEUED] task already pending")
    if any(str(row.get("task").task_id) == task_id
           for row in (getattr(environment, "completed_task_log", None) or [])
           if isinstance(row, dict) and row.get("task") is not None):
        raise ValueError("[B5B_ALREADY_COMPLETED] cannot requeue a delivered order")

    # Only now is the operator's external return attestation *committed*.
    # This is not a simulated instant aircraft/cargo transport event.
    record = {
        "event_id": event_id, "drone_idx": idx, "drone_id": str(drone.drone_id),
        "task_id": task_id, "load_time": assignment["load_time"],
        "operator_id": actor_id, "evidence_ref": evidence_ref,
        "disposition": disposition, "receipt_position": point,
        "received_weight_kg": mass,
        "drone_position_at_handoff": tuple(drone.get_position()),
        "sim_time": float(getattr(environment, "current_time", 0.0)),
        "custody_mode": "operator_attestation_not_physical_verification",
    }
    task.update_status("pending")
    environment.task_generator.unassigned_tasks.append(task)
    environment.drone_assignments.pop(idx, None)
    drone.onboard_load_kg = 0.0
    drone.current_load = 0.0
    drone.executing_task_id = None
    drone.scheduled_position = []
    drone._suspended_route = []
    drone._manual_charge_requested = False
    drone.cargo_custody_hold_reason = None
    drone.is_free = False  # still out of service until explicit reactivation
    environment.drone_chain_len[idx] = 0
    environment._prev_free_status[idx] = False
    if events is None:
        events = {}
        environment.external_custody_events = events
    events[event_id] = record
    return {"drone_idx": idx, "changed": True,
            "requeued_task_ids": [task_id], "custody_event": dict(record)}

def record_external_manifest_handoff(environment, drone_id, *, receipts):
    """B5c experimental *operator-attested* atomic mixed-manifest release.

    Only after valid original-source receipts for ALL actually picked items,
    release the entire ordered manifest. Unpicked items need no receipt and
    remain at their real original sources. No airplane movement, energy
    award, or authenticated physical rescue is asserted by this simulator.
    """
    from swarmbalance.simulation.environment import (math, os)
    if (os.environ.get("SWARM_BALANCE_B5A_CARGO_CUSTODY_GATE") != "1"
            or os.environ.get("SWARM_BALANCE_B5B_EXTERNAL_HANDOFF") != "1"
            or os.environ.get("SWARM_BALANCE_B5C_MIXED_CHAIN_RELEASE") != "1"):
        raise ValueError("[B5C_FEATURE_DISABLED] three opt-in gates required")
    idx = environment._drone_index_by_id(drone_id)
    d = environment.drones[idx]
    if not isinstance(receipts, (tuple, list)) or not receipts:
        raise ValueError("[B5C_RECEIPT_MISSING] picked cargo needs evidence")

    def required_text(value, field):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("[B5C_INVALID_RECEIPT] missing " + field)
        return value.strip()

    proofs = []
    for raw in receipts:
        if not isinstance(raw, dict):
            raise ValueError("[B5C_INVALID_RECEIPT] receipt must be a mapping")
        task_id = required_text(raw.get("task_id"), "task_id")
        event_id = required_text(raw.get("event_id"), "event_id")
        actor_id = required_text(raw.get("actor_id"), "actor_id")
        evidence_ref = required_text(raw.get("evidence_ref"), "evidence_ref")
        if raw.get("disposition") != "returned_to_original_source":
            raise ValueError("[B5C_INVALID_DISPOSITION] returned_to_original_source only")
        try:
            pos = raw.get("receipt_position")
            if not isinstance(pos, (tuple, list)) or len(pos) != 2:
                raise ValueError("point shape")
            point = (float(pos[0]), float(pos[1]))
            if isinstance(raw.get("received_weight_kg"), bool):
                raise ValueError("boolean weight")
            weight = float(raw["received_weight_kg"])
            if not all(math.isfinite(x) for x in point) or not (
                    math.isfinite(weight) and weight > 0):
                raise ValueError("nonfinite value")
        except (TypeError, KeyError, ValueError, OverflowError) as exc:
            raise ValueError("[B5C_INVALID_RECEIPT] finite mass and point required") from exc
        proofs.append((event_id, task_id, actor_id, evidence_ref, point, weight,
                       "returned_to_original_source"))
    event_ids = [r[0] for r in proofs]
    task_ids = [r[1] for r in proofs]
    if len(set(event_ids)) != len(event_ids) or len(set(task_ids)) != len(task_ids):
        raise ValueError("[B5C_DUPLICATE_RECEIPT] each picked task and event only once")

    canonical = tuple(sorted(proofs))
    key = (idx, tuple(sorted(event_ids)))
    replays = getattr(environment, "external_manifest_handoffs", None) or {}
    prior = replays.get(key)
    if prior is not None:
        if prior["proofs"] != canonical:
            raise ValueError("[B5C_EVENT_CONFLICT] same event IDs, altered receipt")
        return {"drone_idx": idx, "changed": False, "requeued_task_ids": [],
                "event_ids": tuple(sorted(event_ids))}

    events = getattr(environment, "external_custody_events", None) or {}
    if any(event_id in events for event_id in event_ids):
        raise ValueError("[B5C_EVENT_CONFLICT] event already recorded")
    if (not getattr(d, "out_of_service", False)
            or getattr(d, "cargo_custody_hold_reason", None)
               != "picked_cargo_requires_external_handoff"):
        raise ValueError("[B5C_NOT_HELD] witnessed cargo must remain on failed drone")

    assigned = environment.drone_assignments.get(idx)
    items = (assigned if isinstance(assigned, list)
             else [assigned] if assigned is not None else [])
    if len(items) < 2 or any(not isinstance(a, dict) or a.get("task") is None
                             for a in items):
        raise ValueError("[B5C_MANIFEST_UNSUPPORTED] needs complete multi-task assignment")
    all_ids = [str(a["task"].task_id) for a in items]
    if len(set(all_ids)) != len(all_ids):
        raise ValueError("[B5C_DUPLICATE_TASK] manifest has repeated task")
    picked = [a for a in items if a.get("load_time") is not None]
    if not picked:
        raise ValueError("[B5C_NO_PICKUP] no witnessed source service")
    picked_ids = {str(a["task"].task_id) for a in picked}
    if set(task_ids) != picked_ids:
        raise ValueError("[B5C_RECEIPT_SET_MISMATCH] require every picked order exactly once")
    if str(getattr(d, "executing_task_id", "")) not in all_ids:
        raise ValueError("[B5C_TASK_IDENTITY_MISMATCH] executing task not assigned")

    receipt_by_task = {r[1]: r for r in proofs}
    total_assigned_kg = 0.0
    total_onboard_kg = 0.0
    for a in items:
        task = a["task"]
        tid = str(task.task_id)
        if task.status not in ("assigned", "in_progress"):
            raise ValueError("[B5C_INVALID_TASK_STATE] no release of completed or pending task")
        tw = float(task.get_weight())
        if not math.isfinite(tw) or tw <= 0:
            raise ValueError("[B5C_INVALID_TASK_WEIGHT] manifest weight invalid")
        total_assigned_kg += tw
        if a.get("load_time") is not None:
            total_onboard_kg += tw
            proof = receipt_by_task[tid]
            point, received_weight = proof[4], proof[5]
            try:
                source = tuple(float(v) for v in task.get_source())
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("[B5C_INVALID_SOURCE] invalid pickup position") from exc
            if (len(source) != 2 or not all(math.isfinite(v) for v in source)
                    or not all(math.isclose(x, y, abs_tol=1e-6, rel_tol=0.0)
                               for x, y in zip(point, source))):
                raise ValueError("[B5C_RECEIPT_LOCATION_MISMATCH] source return unproven")
            if not math.isclose(received_weight, tw, rel_tol=0.0, abs_tol=1e-6):
                raise ValueError("[B5C_RECEIPT_WEIGHT_MISMATCH] bad load receipt")

    if (not math.isclose(float(getattr(d, "onboard_load_kg", 0.0)),
                         total_onboard_kg, rel_tol=0.0, abs_tol=1e-6)
            or not math.isclose(float(getattr(d, "current_load", 0.0)),
                                total_assigned_kg, rel_tol=0.0, abs_tol=1e-6)):
        raise ValueError("[B5C_CARGO_MASS_NOT_CONSERVED] manifest and drone disagree")

    existing_pending = {str(t.task_id) for t in environment.task_generator.unassigned_tasks}
    if existing_pending.intersection(all_ids):
        raise ValueError("[B5C_ALREADY_PENDING] duplicate task in queue")
    if any(str(other.get("task").task_id) in all_ids
           for drone_idx, assignments in environment.drone_assignments.items()
           if drone_idx != idx
           for other in (assignments if isinstance(assignments, list) else [assignments])
           if isinstance(other, dict) and other.get("task") is not None):
        raise ValueError("[B5C_ALREADY_ASSIGNED] duplicate task ownership")
    if any(str(row.get("task").task_id) in all_ids
           for row in (getattr(environment, "completed_task_log", None) or [])
           if isinstance(row, dict) and row.get("task") is not None):
        raise ValueError("[B5C_ALREADY_COMPLETED] cannot requeue delivered orders")

    # PREPARE phase is complete. A single sequential COMMIT transfers the
    # reported custody, task identities, and mass without simulated motion.
    records = {}
    position = tuple(d.get_position())
    now = float(getattr(environment, "current_time", 0.0))
    for event_id, task_id, actor, evidence, point, mass, disposition in proofs:
        assignment = next(a for a in picked if str(a["task"].task_id) == task_id)
        records[event_id] = {
            "event_id": event_id, "task_id": task_id, "drone_idx": idx,
            "drone_id": str(d.drone_id), "operator_id": actor,
            "evidence_ref": evidence, "receipt_position": point,
            "received_weight_kg": mass, "disposition": disposition,
            "load_time": assignment["load_time"],
            "drone_position_at_handoff": position, "sim_time": now,
            "custody_mode": "operator_attestation_not_physical_verification",
        }

    for a in items:
        a["task"].update_status("pending")
        environment.task_generator.unassigned_tasks.append(a["task"])
    environment.drone_assignments.pop(idx, None)
    d.onboard_load_kg = 0.0
    d.current_load = 0.0
    d.executing_task_id = None
    d.scheduled_position = []
    d._suspended_route = []
    d._manual_charge_requested = False
    d.cargo_custody_hold_reason = None
    d.is_free = False  # still out of service; operator must explicitly restore
    environment.drone_chain_len[idx] = 0
    environment._prev_free_status[idx] = False
    if not hasattr(environment, "external_custody_events"):
        environment.external_custody_events = {}
    environment.external_custody_events.update(records)
    if not hasattr(environment, "external_manifest_handoffs"):
        environment.external_manifest_handoffs = {}
    environment.external_manifest_handoffs[key] = {
        "proofs": canonical, "task_ids": tuple(all_ids),
    }
    return {"drone_idx": idx, "changed": True, "requeued_task_ids": all_ids,
            "event_ids": tuple(sorted(event_ids))}
