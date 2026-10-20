#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L0 only: source audit and a TRUE RED against the unmodified production Environment.
Do not import this file in test discovery. No writes to runtime/fixtures/experiments.
usage:
    python scripts/l0_logic_probe.py --source
    python scripts/l0_logic_probe.py --cleanup-red
"""
from __future__ import annotations
import argparse
import ast
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "frontend" / "environment.py"
TASK_FILE = ROOT / "frontend" / "task.py"
DRONE_FILE = ROOT / "frontend" / "drone.py"


def where(lines, term):
    return [n for n, row in enumerate(lines, 1) if term in row]


def source_audit():
    env = ENV_FILE.read_text(encoding="utf-8")
    task = TASK_FILE.read_text(encoding="utf-8")
    drone = DRONE_FILE.read_text(encoding="utf-8")
    tree = ast.parse(env, filename=str(ENV_FILE))
    methods = {n.name: n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    needed = {"step", "_record_task_completion", "get_statistics", "reset"}
    assert needed.issubset(methods), "[L0_SOURCE_MISSING] core methods changed"
    completion = methods["_record_task_completion"]
    completion_src = ast.get_source_segment(env, completion) or ""
    assert "self.total_completed_tasks += 1" in completion_src, "[L0_COUNT_SOURCE_MISSING]"
    assert "update_status(" not in completion_src, "[L0_STATUS_SOURCE_CHANGED] re-audit task state"
    assert 'self.status = "pending"' in task, "[L0_TASK_STATUS_SOURCE_CHANGED]"
    assert 'valid_statuses = ["pending", "assigned", "in_progress", "completed", "failed"]' in task, "[L0_TASK_LIFECYCLE_CHANGED]"
    marker = "if not self._prev_free_status.get(i, True) and drone.is_free:"
    assert env.count(marker) == 1, "[L0_CLEANUP_BRANCH_CHANGED]"
    near = env.split(marker, 1)[1].split("self._manage_berths()", 1)[0]
    assert near.count("self._record_task_completion(i, ") == 2, "[L0_CLEANUP_WITNESS_CHANGED]"
    stat = methods["get_statistics"]
    stat_src = ast.get_source_segment(env, stat) or ""
    assert "'timeout_rate': 1.0 - (self.total_on_time_tasks / self.total_completed_tasks)" in stat_src, "[L0_TIMEOUT_DENOMINATOR_CHANGED]"
    assert "'timeout_rate': 0.0" in stat_src, "[L0_TIMEOUT_ZERO_CASE_CHANGED]"
    assert "def quote_flight_energy_wh" in drone and "def _flight_step_feasible" in drone
    lines = env.splitlines()
    loc = {
        "completion_method": completion.lineno,
        "completion_counter": where(lines, "self.total_completed_tasks += 1"),
        "assignment_status": where(lines, 'task_to_assign.update_status("assigned")'),
        "release_to_pending": where(lines, "task.update_status('pending')"),
        "cleanup_guard": where(lines, marker),
        "timeout_conditional": where(lines, "'timeout_rate': 1.0 - (self.total_on_time_tasks / self.total_completed_tasks)"),
        "timeout_no_completions": where(lines, "'timeout_rate': 0.0"),
    }
    assert len(loc["completion_counter"]) == 1
    assert len(loc["timeout_conditional"]) == 1
    # Simple arithmetic witness, not an end-to-end episode.
    generated, completed, on_time = 100, 40, 40
    observed_conditional_timeout = 1 - on_time / completed
    unfinished_share = (generated - completed) / generated
    assert observed_conditional_timeout == 0 and unfinished_share == 0.6
    print("[L0_SOURCE_AUDIT_CONFIRMED] " + json.dumps({
        "scope": "three named core source files plus three production methods",
        "evidence_lines": loc,
        "task_status_terminal_written_in_completion": False,
        "cleanup_completion_without_delivery_is_source_reachable": True,
        "timeout_is_conditional_on_completed": True,
        "illustrative_generated": generated,
        "illustrative_completed": completed,
        "conditional_timeout": observed_conditional_timeout,
        "unfinished_share": unfinished_share,
        "not_runtime_proof": True,
    }, ensure_ascii=False, sort_keys=True))


def cleanup_red():
    # Separate process only. Freeze config before importing the simulation kernel.
    os.environ["SWARM_BALANCE_SIM_CONFIG"] = str((ROOT / "config" / "simulation.json").resolve())
    sys.path[:0] = [str(ROOT), str(ROOT / "frontend")]
    from environment import Environment

    env = Environment(str(ROOT / "frontend/data/map/part_of_yangpu.osm"),
                      episode_max_steps=120)
    env.reset(seed=40907)
    env.task_generation_paused = True
    candidates = []
    for i, drone in enumerate(env.drones):
        if not drone.is_free:
            continue
        for task in env.task_generator.unassigned_tasks:
            if float(task.get_weight()) > float(drone.carrying_capacity):
                continue
            distance = math.dist(drone.get_position(), task.get_source()) + math.dist(
                task.get_source(), task.get_destination())
            if distance > 5 * float(drone.speed):
                candidates.append((distance, i, task))
    assert candidates, "[L0_NO_VALID_PRECONDITION] No assignable unfinished order"
    _, idx, task = max(candidates, key=lambda x: x[0])
    drone = env.drones[idx]

    # ACTUAL public action path: an order becomes assigned and begins a route.
    start_count = int(env.total_completed_tasks)
    env.step({idx: [task.task_id]})
    assigned = env.drone_assignments.get(idx) or []
    if isinstance(assigned, dict):
        assigned = [assigned]
    assert any(a["task"] is task for a in assigned), "[L0_ASSIGNMENT_NOT_REAL]"
    assert env.total_completed_tasks == start_count, "[L0_PREMATURE_DELIVERY]"
    assert task.status == "assigned", "[L0_PRECONDITION_STATUS_NOT_ASSIGNED]"

    # Fault injection: cancel the route at the state boundary but leave the
    # actual accepted assignment record. This is NOT a valid public API
    # transition. It demonstrates whether cleanup trusts 'free' as evidence.
    drone.scheduled_position = []
    drone.consumed_waypoints_this_step = []
    drone.is_free = True
    env._prev_free_status[idx] = False
    env.step({})
    new_count = int(env.total_completed_tasks)
    status = task.status
    print("[L0_FAULT_INJECTION_OBSERVED] " + json.dumps({
        "task_id": str(task.task_id), "drone_idx": idx,
        "before_completed": start_count, "after_completed": new_count,
        "task_status": status, "injected_fault": "route-cleared while accepted assignment persists",
        "real_delivery_event_in_second_step": False,
        "note": "forced precondition, not claim of naturally occurring production fault"
    }, ensure_ascii=False, sort_keys=True), flush=True)

    # Intentional TRUE RED: the desired safety invariant is a hard assertion.
    assert new_count == start_count, (
        "[L0_CLEANUP_WITHOUT_DELIVERY] Actual Environment.step counted an "
        "unfinished task as delivered solely when its drone became free"
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--source", action="store_true")
    group.add_argument("--cleanup-red", action="store_true")
    opt = p.parse_args()
    if opt.source:
        source_audit()
    else:
        cleanup_red()
