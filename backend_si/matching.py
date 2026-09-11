"""Shared heterogeneous UAV capability-task matching utilities.

The score is intentionally lightweight and deterministic so it can be used by
GA/PSO/greedy heuristics without introducing another model dependency.

score = w_load * load_match + w_speed * speed_match + w_range * range_match

All component scores are normalized to [0, 1]. Hard feasibility (payload,
battery reserve, time-window tolerance) is still enforced by the scheduler;
this module only ranks feasible UAV-task pairs.
"""
from __future__ import annotations

DEFAULT_WEIGHTS = {"load": 0.4, "speed": 0.3, "range": 0.3}
SPEED_MAX = 320.0
VOLUME_TO_LOAD_FACTOR = 0.3


def load_match(required_load: float, remaining_capacity: float) -> float:
    """Prefer enough payload headroom without wasting a very large airframe."""
    if remaining_capacity <= 0:
        return 0.0
    utilization = float(required_load) / float(remaining_capacity)
    return max(0.0, min(1.0, 1.0 - abs(utilization - 0.9) / 0.9))


def speed_match(speed: float, remaining_time: float | None) -> float:
    """Urgent tasks increasingly prefer faster UAVs; relaxed tasks stay neutral."""
    speed_norm = min(1.0, max(0.0, float(speed)) / SPEED_MAX)
    if remaining_time is None or remaining_time == float("inf"):
        urgency = 0.0
    else:
        urgency = max(0.0, min(1.0, 1.0 - float(remaining_time) / 300.0))
    return (1.0 - urgency) * 0.5 + urgency * speed_norm


def range_match(battery_capacity: float, consumption_base: float,
                total_distance: float) -> float:
    """Prefer long-endurance UAVs for routes that use a larger share of range."""
    consumption_base = max(1e-9, float(consumption_base))
    est_range = max(0.0, float(battery_capacity)) / consumption_base
    total_distance = max(0.0, float(total_distance))
    if total_distance <= 0:
        return 0.5
    if est_range < total_distance:
        return 0.0
    ratio = total_distance / max(est_range, 1e-9)
    return max(0.0, min(1.0, 1.0 - abs(ratio - 0.5) / 0.5))


def compute_match(required_load: float,
                  remaining_capacity: float,
                  speed: float,
                  remaining_time: float | None,
                  battery_capacity: float,
                  consumption_base: float,
                  total_distance: float,
                  weights=None) -> float:
    """Return a 0..1 capability-demand compatibility score."""
    w = weights or DEFAULT_WEIGHTS
    return (
        float(w.get("load", 0.4)) * load_match(required_load, remaining_capacity)
        + float(w.get("speed", 0.3)) * speed_match(speed, remaining_time)
        + float(w.get("range", 0.3)) * range_match(
            battery_capacity, consumption_base, total_distance
        )
    )
