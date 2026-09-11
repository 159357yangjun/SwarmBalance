"""Shared lightweight validation for ``config/simulation.json``.

The checks here are intentionally map-independent so they can run before OSM is loaded,
in unit tests, scene import, preflight and Web config saving.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple


def validate_simulation_config(cfg: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    if not isinstance(cfg, dict):
        return ["simulation config 顶层必须是 JSON 对象"], warnings

    env = cfg.get("environment") or {}
    try:
        n = int(env.get("num_drones", 0))
    except (TypeError, ValueError):
        n = 0
    if n <= 0 or n > 200:
        errors.append("environment.num_drones 必须在 1~200 之间")

    hetero = cfg.get("heterogeneous") or {}
    mix = hetero.get("fleet_mix") or {}
    if hetero.get("enabled", False) and mix:
        try:
            vals = [int(v) for v in mix.values()]
        except (TypeError, ValueError):
            vals = []
            errors.append("heterogeneous.fleet_mix 必须全部为整数")
        if vals and any(v < 0 for v in vals):
            errors.append("heterogeneous.fleet_mix 不能出现负数")
        if vals and sum(vals) != n:
            errors.append(f"异构机队数量之和为 {sum(vals)}，但 environment.num_drones={n}")

    stations = cfg.get("charging_stations") or []
    if not isinstance(stations, list) or not stations:
        errors.append("至少需要一个 charging_stations 机巢")
    else:
        ids = [str(s.get("station_id")) for s in stations if isinstance(s, dict)]
        if len(ids) != len(stations):
            errors.append("charging_stations 每项都必须是对象")
        elif len(ids) != len(set(ids)):
            errors.append("charging_stations 存在重复 station_id")

    nest = cfg.get("nest") or {}
    try:
        if int(nest.get("berths", 1)) < 1:
            errors.append("nest.berths 必须至少为 1")
    except (TypeError, ValueError):
        errors.append("nest.berths 必须是整数")

    task = cfg.get("task") or {}
    try:
        dmin = float(task.get("deadline_offset_min", 0))
        dmax = float(task.get("deadline_offset_max", dmin))
        if dmin <= 0 or dmax <= 0:
            errors.append("任务 SLA 上下限必须大于 0")
        elif dmin > dmax:
            errors.append("task.deadline_offset_min 不能大于 deadline_offset_max")
    except (TypeError, ValueError):
        errors.append("任务 SLA 配置必须为数值")

    gen = cfg.get("task_generation") or {}
    realistic = gen.get("realistic") or {}
    if str(gen.get("mode", "realistic")).lower() == "realistic":
        try:
            total = int(realistic.get("total_tasks", 0))
            initial = int(realistic.get("initial_task_count", 0))
            if total <= 0:
                errors.append("task_generation.realistic.total_tasks 必须大于 0")
            if initial < 0 or (total > 0 and initial > total):
                errors.append("initial_task_count 必须在 0~total_tasks 之间")
        except (TypeError, ValueError):
            errors.append("任务生成数量配置必须为整数")

    source_type = str((cfg.get("data_source") or {}).get("type", "random")).lower()
    if source_type not in {"random", "csv", "geojson"}:
        errors.append(f"不支持的数据源类型: {source_type}")
    if source_type != "random":
        warnings.append("当前非 random 数据源：Web 场景布局编辑器不会改写 CSV/GeoJSON 源数据")

    return errors, warnings


def assert_valid_simulation_config(cfg: Dict[str, Any]) -> None:
    errors, _ = validate_simulation_config(cfg)
    if errors:
        raise ValueError("；".join(errors))
