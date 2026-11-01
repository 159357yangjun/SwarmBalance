"""Snapshots; functions operate on the owning session without duplicating state."""
from __future__ import annotations
import math
import sys
from typing import Any, Dict, List


def _drone_state(d: Any) -> str:
    if getattr(d, "out_of_service", False):
        return "offline"
    if getattr(d, "is_charging", False) or getattr(d, "swap_remaining_steps", 0) > 0:
        return "charging"
    if getattr(d, "awaiting_berth", False):
        return "waiting_berth"
    if getattr(d, "_manual_charge_requested", False):
        return "to_nest"
    if not getattr(d, "is_free", True):
        return "busy"
    return "idle"

def _polygon_rings(geom: Any) -> List[List[List[float]]]:
    """把 shapely Polygon/MultiPolygon 转成外环坐标列表（供 3D 前端拉伸成棱柱）。"""
    if geom is None or getattr(geom, "is_empty", True):
        return []
    from shapely.geometry import MultiPolygon, Polygon
    polys = geom.geoms if isinstance(geom, MultiPolygon) else [geom]
    rings = []
    for p in polys:
        if not isinstance(p, Polygon) or p.is_empty:
            continue
        rings.append([[round(float(x), 2), round(float(y), 2)]
                      for x, y in p.exterior.coords])
    return rings

def snapshot(session) -> Dict:
    return {
        "algorithm": session.algorithm,
        "seed": session.seed,
        "step": session.step_count,
        "time": float(session.env.current_time),
        "done": session.done,
        "num_drones": session.num_drones,
        "map": session._map_snapshot(),
        "drones": session._drones_snapshot(),
        "nests": session._nests_snapshot(),
        "tasks": session._tasks_snapshot(),
        "task_catalog": session._task_catalog_snapshot(),
        "pending_count": len(getattr(session.env.task_generator, "unassigned_tasks", []) or []),
        "controls": {
            "task_generation_paused": bool(getattr(session.env, "task_generation_paused", False)),
        },
        "events": list(session._events)[-80:],
        "stats": session._stats_snapshot(),
        "history": list(session._history),
        "health": session._health_snapshot(),
        "demo": session._demo_snapshot(),
        "checkpoints": session.list_checkpoints(),
    }

def map_static(session) -> Dict:
    """静态地图几何（一次性）：边界 + 建筑轮廓(含高度)。"""
    # 静态几何在同一个 Environment 生命周期内不会变。以前每次调用都从两千多栋建筑
    # 重建全部环（实测 p50 106ms、响应体 885KB），而前端在 mount、场景应用、
    # rebuild、布局保存各处都会重拉一次，且都持着 _op_lock。
    cached = getattr(session, "_map_static_cache", None)
    if cached is not None and getattr(session, "_map_static_src", None) is session.env:
        return cached
    bounds = getattr(session.env, "global_bounds", None)
    if not bounds:
        xs = [d.x for d in session.env.drones] + [s.x for s in session.env.charging_stations]
        ys = [d.y for d in session.env.drones] + [s.y for s in session.env.charging_stations]
        bounds = (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 1000, 1000)
    # 全量建筑（含无高度标注者按默认层高 12m 处理），形成真实城市肌理
    src = getattr(session.env, "all_buildings", None) or getattr(session.env, "high_buildings", []) or []
    buildings = []
    for b in src:
        rings = _polygon_rings(b.get("geometry"))
        try:
            h = round(float(b.get("height")), 2)
        except (TypeError, ValueError):
            h = 12.0
        if not math.isfinite(h) or h <= 0:
            h = 12.0
        for ring in rings:
            pts = []
            for pt in ring:
                try:
                    x = float(pt[0]); y = float(pt[1])
                except (TypeError, ValueError, IndexError):
                    continue
                if math.isfinite(x) and math.isfinite(y):
                    pts.append([x, y])
            if len(pts) >= 3:
                buildings.append({"coords": pts, "height": h})
    # 主干道路网络（街景骨架）
    roads = []
    for rtype, geoms in (getattr(session.env, "roads_by_type", {}) or {}).items():
        for g in geoms:
            pts = []
            for pt in (getattr(g, "coords", None) or []):
                try:
                    x = float(pt[0]); y = float(pt[1])
                except (TypeError, ValueError, IndexError):
                    continue
                if math.isfinite(x) and math.isfinite(y):
                    pts.append([x, y])
            if len(pts) >= 2:
                roads.append({"type": str(rtype), "coords": pts})
    result = {
        "bounds": [float(v) for v in bounds],
        "buildings": buildings,
        "roads": roads,
        "no_fly_zones": session._no_fly_snapshot(),
    }
    session._map_static_cache = result
    session._map_static_src = session.env
    return result

def _no_fly_snapshot(session) -> List[Dict]:
    """禁飞区轮廓（申请书「可灵活配置禁飞区」的可视化）。"""
    nf = getattr(session.env, "no_fly", None)
    if not nf:
        return []
    out = []
    for z in nf.zones:
        rings = _polygon_rings(z.geometry)
        for ring in rings:
            if len(ring) >= 3:
                out.append({"name": z.name, "coords": ring})
    return out

def _map_snapshot(session) -> Dict:
    bounds = getattr(session.env, "global_bounds", None)
    if not bounds:
        xs = [d.x for d in session.env.drones] + [s.x for s in session.env.charging_stations]
        ys = [d.y for d in session.env.drones] + [s.y for s in session.env.charging_stations]
        bounds = (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 1000, 1000)
    return {"bounds": [float(v) for v in bounds]}

def _drones_snapshot(session) -> List[Dict]:
    out = []
    for i, d in enumerate(session.env.drones):
        cap = float(getattr(d, "battery_capacity", 1.0)) or 1.0
        chain = session._assigned_task_list(i)
        route_m = 0.0
        prev = (float(d.x), float(d.y))
        for wp in getattr(d, "scheduled_position", []) or []:
            cur = (float(wp[0]), float(wp[1]))
            route_m += ((cur[0]-prev[0])**2 + (cur[1]-prev[1])**2) ** 0.5
            prev = cur
        out.append({
            "idx": i,
            "id": str(getattr(d, "drone_id", f"drone_{i}")),
            "type": str(getattr(d, "drone_type", "") or "homogeneous"),
            "x": float(d.x),
            "y": float(d.y),
            "state": _drone_state(d),
            "out_of_service": bool(getattr(d, "out_of_service", False)),
            "out_of_service_reason": getattr(d, "out_of_service_reason", None),
            "battery_ratio": round(float(getattr(d, "current_battery", 0.0)) / cap, 4),
            "battery": round(float(getattr(d, "current_battery", 0.0)), 2),
            "battery_capacity": round(cap, 2),
            "speed": round(float(getattr(d, "speed", 0.0)), 2),
            "consumption_base": round(float(getattr(d, "battery_consumption_base", 0.0)), 4),
            "load": float(getattr(d, "current_load", 0.0)),
            "capacity": float(getattr(d, "carrying_capacity", 0.0)),
            "executing_task": str(getattr(d, "executing_task_id", "") or ""),
            "chain_len": len(chain),
            "task_chain": chain,
            "remaining_route_m": round(route_m, 2),
            "awaiting_berth": bool(getattr(d, "awaiting_berth", False)),
            "station_id": getattr(d, "charging_station_id", None) if getattr(d, "is_charging", False) else getattr(d, "berth_station_id", None),
            "swap_remaining": round(float(getattr(d, "swap_remaining_steps", 0.0)), 1),
            "manual_charge_requested": bool(getattr(d, "_manual_charge_requested", False)),
            "home": [float(getattr(d, "home_position", (d.x, d.y))[0]), float(getattr(d, "home_position", (d.x, d.y))[1])],
        })
    return out

def _nests_snapshot(session) -> List[Dict]:
    rows = []
    for s in session.env.charging_stations:
        waiting = list(getattr(session.env, "_nest_waiting", {}).get(s.station_id, []) or [])
        if getattr(session.env, "arbitration_policy", "priority") == "fifo":
            waiting.sort(key=lambda i: (
                getattr(session.env.drones[i], "awaiting_since", None)
                if getattr(session.env.drones[i], "awaiting_since", None) is not None else float("inf")
            ))
        else:
            waiting.sort(key=lambda i: session.env._drone_berth_score(i), reverse=True)
        queue = []
        for rank, idx in enumerate(waiting, start=1):
            d = session.env.drones[idx]
            since = getattr(d, "awaiting_since", None)
            queue.append({
                "rank": rank,
                "drone_idx": idx,
                "drone_id": str(getattr(d, "drone_id", f"drone_{idx}")),
                "battery_ratio": round(float(d.current_battery) / max(1e-9, float(d.battery_capacity)), 4),
                "wait_seconds": round(max(0.0, float(session.env.current_time) - float(since)), 1) if since is not None else 0.0,
                "priority_score": round(float(session.env._drone_berth_score(idx)), 4),
            })
        rows.append({
            "id": str(getattr(s, "station_id", "")),
            "x": float(s.x),
            "y": float(s.y),
            "berths": int(getattr(s, "berths", 1)),
            "occupied": int(getattr(s, "occupied", 0)),
            "free_berths": int(getattr(s, "free_berths", lambda: 0)()),
            "swap_time_seconds": round(float(getattr(s, "swap_time_seconds", 0.0)), 1),
            "queue": queue,
            "queue_length": len(queue),
            "arbitration": str(getattr(session.env, "arbitration_policy", "priority")),
            "closed": bool(getattr(s, "closed", False)),
            "closed_reason": getattr(s, "closed_reason", None),
        })
    return rows

def _tasks_snapshot(session, limit: int = 60) -> List[Dict]:
    tasks = []
    unassigned = getattr(session.env, "unassigned_tasks", []) or []
    for t in unassigned:
        tid = str(getattr(t, "task_id", ""))
        if not tid or tid.startswith("__pad_"):
            continue
        tasks.append({
            "id": tid,
            "source": [float(t.source[0]), float(t.source[1])],
            "destination": [float(t.destination[0]), float(t.destination[1])],
            "weight": float(getattr(t, "weight", 0.0)),
            "volume": float(getattr(t, "volume", 0.0)),
            "priority": int(getattr(t, "priority", 1)),
            "category": str(getattr(t, "category", "normal") or "normal"),
            "deadline": float(getattr(t, "deadline", 0.0) or 0.0),
            "remaining_time": round(max(0.0, float(getattr(t, "deadline", session.env.current_time) or session.env.current_time) - float(session.env.current_time)), 1),
            "status": str(getattr(t, "status", "pending") or "pending"),
            "manual": tid.startswith("manual_"),
        })
        if len(tasks) >= limit:
            break
    return tasks

def _task_base_dict(session, task: Any) -> Dict:
    """把 Task 转为控制台稳定字段，避免前端依赖 Python 对象细节。"""
    deadline = getattr(task, "deadline", None)
    generation_time = getattr(task, "generation_time", None)
    remaining = None if deadline is None else float(deadline) - float(session.env.current_time)
    return {
        "id": str(getattr(task, "task_id", "")),
        "source": [float(task.source[0]), float(task.source[1])],
        "destination": [float(task.destination[0]), float(task.destination[1])],
        "weight": float(getattr(task, "weight", 0.0)),
        "volume": float(getattr(task, "volume", 0.0)),
        "priority": int(getattr(task, "priority", 1)),
        "category": str(getattr(task, "category", "normal") or "normal"),
        "deadline": float(deadline) if deadline is not None else None,
        "generation_time": float(generation_time) if generation_time is not None else None,
        "remaining_time": round(remaining, 1) if remaining is not None else None,
        "manual": str(getattr(task, "task_id", "")).startswith("manual_"),
    }

def _task_catalog_snapshot(session, completed_limit: int = 24) -> List[Dict]:
    """任务生命周期视图：待分配 + 已分配/执行中 + 最近完成。

    `tasks` 字段仍保持“待分配任务”兼容语义；这个 catalog 专供可点击任务详情。
    """
    rows: Dict[str, Dict] = {}
    for task in (getattr(session.env.task_generator, "unassigned_tasks", []) or []):
        tid = str(getattr(task, "task_id", ""))
        if not tid or tid.startswith("__pad_"):
            continue
        row = session._task_base_dict(task)
        row.update({"status": "pending", "assigned_drone_id": None, "assigned_drone_idx": None, "chain_order": None, "loaded": False})
        rows[tid] = row

    for drone_idx in range(len(session.env.drones)):
        d = session.env.drones[drone_idx]
        assigned = getattr(session.env, "drone_assignments", {}).get(drone_idx)
        if not assigned:
            continue
        items = assigned if isinstance(assigned, list) else [assigned]
        for order, a in enumerate(items, start=1):
            if not isinstance(a, dict) or a.get("task") is None:
                continue
            task = a["task"]
            tid = str(task.task_id)
            row = session._task_base_dict(task)
            executing = str(getattr(d, "executing_task_id", "") or "") == tid
            row.update({
                "status": "in_progress" if executing else "assigned",
                "assigned_drone_id": str(getattr(d, "drone_id", f"drone_{drone_idx}")),
                "assigned_drone_idx": drone_idx,
                "chain_order": order,
                "loaded": a.get("load_time") is not None,
                "assigned_time": float(a.get("assigned_time", a.get("start_time", session.env.current_time))),
                "load_time": float(a["load_time"]) if a.get("load_time") is not None else None,
            })
            rows[tid] = row

    completed = list(getattr(session.env, "completed_task_log", []) or [])[-completed_limit:]
    for item in completed:
        task = item.get("task") if isinstance(item, dict) else None
        if task is None:
            continue
        tid = str(task.task_id)
        row = session._task_base_dict(task)
        owner = session._completed_task_owner.get(tid, {})
        row.update({
            "status": "completed",
            "assigned_drone_id": owner.get("drone_id"),
            "assigned_drone_idx": owner.get("drone_idx"),
            "chain_order": None,
            "loaded": True,
            "assigned_time": float(item.get("assigned_time")) if item.get("assigned_time") is not None else None,
            "load_time": float(item.get("load_time")) if item.get("load_time") is not None else None,
            "completion_time": float(item.get("completion_time")) if item.get("completion_time") is not None else None,
            "delay": round(float(item.get("delay", 0.0)), 1),
            "on_time": float(item.get("delay", 0.0)) <= 0.0,
        })
        rows[tid] = row

    # pending/assigned 优先展示，已完成按最新完成时间靠后。
    rank = {"in_progress": 0, "assigned": 1, "pending": 2, "completed": 3}
    return sorted(rows.values(), key=lambda r: (rank.get(r.get("status"), 9), -(r.get("priority") or 0), r.get("id") or ""))

def _health_snapshot(session) -> Dict:
    pending = list(getattr(session.env.task_generator, "unassigned_tasks", []) or [])
    urgent = sum(1 for t in pending if int(getattr(t, "priority", 1)) >= 3)
    drones = list(session.env.drones)
    offline = sum(1 for d in drones if getattr(d, "out_of_service", False))
    _low_thr = getattr(sys.modules.get("swarmbalance.simulation.entities.drone"), "BATTERY_LOW_THRESHOLD", 0.2)
    critical_battery = sum(1 for d in drones if not getattr(d, "out_of_service", False)
                           and not getattr(d, "is_charging", False)
                           and float(getattr(d, "current_battery", 0.0)) / max(1e-9, float(getattr(d, "battery_capacity", 1.0))) < _low_thr)
    nests = list(session.env.charging_stations)
    closed = sum(1 for s in nests if getattr(s, "closed", False))
    queue = sum(len(q) for q in getattr(session.env, "_nest_waiting", {}).values())
    # 侧栏「禁飞区」要的是**区域个数**；_no_fly_snapshot 返回的是多边形环，一块区域可能有多个
    # 环，拿它的长度计数会把 3 块报成 5 个。
    no_fly = len(getattr(getattr(session.env, "no_fly", None), "zones", None) or [])
    online = len(drones) - offline
    level = "normal"
    notes = []
    if online <= 0:
        level = "critical"; notes.append("无可用无人机")
    if urgent:
        level = "warning" if level == "normal" else level; notes.append(f"{urgent} 条 P3 待调度")
    if queue:
        level = "warning" if level == "normal" else level; notes.append(f"{queue} 架等待泊位")
    if offline:
        level = "warning" if level == "normal" else level; notes.append(f"{offline} 架停飞")
    if closed:
        level = "warning" if level == "normal" else level; notes.append(f"{closed} 个机巢关闭")
    if critical_battery:
        level = "warning" if level == "normal" else level; notes.append(f"{critical_battery} 架低电")
    if not notes:
        notes.append("系统运行平稳")
    return {
        "level": level, "summary": "；".join(notes), "pending": len(pending),
        "urgent_pending": urgent, "offline_drones": offline, "critical_battery": critical_battery,
        "closed_nests": closed, "berth_queue": queue, "online_drones": online,
        "no_fly_count": no_fly,
    }

def _demo_snapshot(session) -> Dict:
    d = session._demo or {}
    script = d.get("script") or []
    cursor = int(d.get("cursor", 0))
    next_item = script[cursor] if cursor < len(script) else None
    return {
        "active": bool(d.get("active")), "key": d.get("key"), "name": d.get("name"),
        "cursor": cursor, "total": len(script),
        "next": dict(next_item) if next_item else None,
        "completed": bool(d.get("active")) and cursor >= len(script),
    }

def _stats_snapshot(session) -> Dict:
    s = session.env.get_statistics()
    return {
        "completed": int(s.get("total_completed", 0)),
        "generated": int(s.get("total_generated", 0)),
        "completion_rate": float(s.get("completion_rate", 0.0)),
        "timeout_rate": float(s.get("timeout_rate", 0.0)),
        "avg_delay": float(s.get("avg_delay", 0.0)),
        "energy": float(s.get("total_energy_consumed", 0.0)),
        "nest_turnover": float(s.get("nest_turnover_rate", 0.0)),
        "berth_utilization": float(s.get("berth_utilization_rate", 0.0)),
        "swap_sessions": int(s.get("total_swap_sessions", 0)),
        # 机队效率 + 任务链 / 禁飞区生效观测
        "utilization": float(s.get("avg_drone_utilization", 0.0)),
        "empty_load_ratio": float(s.get("empty_load_ratio", 0.0)),
        "flight_distance": float(s.get("total_flight_distance", 0.0)),
        "chain_insertions": int(s.get("chain_insertions", 0)),
        "no_fly_detours": int(s.get("no_fly_detours", 0)),
    }
