"""Events; functions operate on the owning session without duplicating state."""
from __future__ import annotations
from typing import Dict, List, Optional


def _emit(session, kind: str, message: str, level: str = "info", data: Optional[Dict] = None):
    session._event_seq += 1
    session._events.append({
        "seq": session._event_seq,
        "step": int(session.step_count),
        "time": float(getattr(session.env, "current_time", 0.0)),
        "kind": kind,
        "level": level,
        "message": message,
        "data": data or {},
    })

def _assigned_task_list(session, drone_idx: int) -> List[Dict]:
    assigned = getattr(session.env, "drone_assignments", {}).get(drone_idx)
    if not assigned:
        return []
    items = assigned if isinstance(assigned, list) else [assigned]
    out = []
    for pos, a in enumerate(items, start=1):
        if not isinstance(a, dict):
            continue
        t = a.get("task")
        if t is None:
            continue
        deadline = t.get_deadline()
        out.append({
            "order": pos,
            "task_id": str(t.task_id),
            "priority": int(t.get_priority()),
            "weight": float(t.get_weight()),
            "volume": float(getattr(t, "volume", 0.0)),
            "category": str(getattr(t, "category", "normal") or "normal"),
            "deadline": float(deadline) if deadline is not None else None,
            "remaining_time": round(float(deadline) - float(session.env.current_time), 1) if deadline is not None else None,
            "loaded": a.get("load_time") is not None,
        })
    return out

def _assignment_map(session) -> Dict[str, Dict]:
    out = {}
    for i in range(len(session.env.drones)):
        for task in session._assigned_task_list(i):
            out[task["task_id"]] = {
                "drone_idx": i,
                "drone_id": str(getattr(session.env.drones[i], "drone_id", f"drone_{i}")),
                "task": task,
            }
    return out

def _drone_transition_state(session) -> Dict[int, Dict]:
    out = {}
    for i, d in enumerate(session.env.drones):
        out[i] = {
            "waiting": bool(getattr(d, "awaiting_berth", False)),
            "charging": bool(getattr(d, "is_charging", False)),
            "station": getattr(d, "charging_station_id", None) if getattr(d, "is_charging", False)
                       else getattr(d, "berth_station_id", None),
        }
    return out

def _record_transition_events(session, *, before_unassigned, before_assign,
                              before_completed, before_drone_states):
    after_unassigned = {
        str(t.task_id) for t in (getattr(session.env.task_generator, "unassigned_tasks", []) or [])
        if getattr(t, "task_id", None) and not str(t.task_id).startswith("__pad_")
    }
    after_assign = session._assignment_map()

    # 自动订单到达（人工注入在 inject_task() 中单独记录）
    for tid in sorted(after_unassigned - before_unassigned):
        if tid not in before_assign:
            session._emit("task_generated", f"新任务 {tid} 到达待调度池", data={"task_id": tid})

    # 新分配 / 任务链插入。按每架无人机的链内顺序判断第一单与后续插单，
    # 避免同一步一次分到多单时把“第一单”误写成链式插入。
    before_count_by_drone = {}
    for old in before_assign.values():
        before_count_by_drone[old["drone_idx"]] = before_count_by_drone.get(old["drone_idx"], 0) + 1
    for drone_idx in range(len(session.env.drones)):
        chain = session._assigned_task_list(drone_idx)
        new_chain_items = [t for t in chain if t["task_id"] not in before_assign]
        if not new_chain_items:
            continue
        prior = before_count_by_drone.get(drone_idx, 0)
        drone_id = str(getattr(session.env.drones[drone_idx], "drone_id", f"drone_{drone_idx}"))
        for j, task in enumerate(new_chain_items):
            is_insert = (prior + j) > 0
            kind = "chain_insert" if is_insert else "task_assigned"
            suffix = f"（任务链位置 {prior+j+1}/{len(chain)}）" if is_insert else ""
            session._emit(kind, f"{task['task_id']} → {drone_id} {suffix}",
                       level="important" if task["priority"] >= 3 else "info",
                       data={"task_id": task["task_id"], "drone_id": drone_id, "drone_idx": drone_idx})

    # 完成：用累计完成数确认“从任务链消失”确实对应送达，不把其它状态迁移误报为完成。
    completed_delta = int(getattr(session.env, "total_completed_tasks", 0)) - int(before_completed)
    disappeared = [tid for tid in before_assign if tid not in after_assign and tid not in after_unassigned]
    for tid in disappeared[:max(0, completed_delta)]:
        old = before_assign[tid]
        session._completed_task_owner[tid] = {"drone_id": old["drone_id"], "drone_idx": old["drone_idx"]}
        session._emit("task_completed", f"{old['drone_id']} 已完成 {tid}", level="success",
                   data={"task_id": tid, "drone_id": old["drone_id"], "drone_idx": old["drone_idx"]})

    # 机巢资源竞争状态变化
    after_states = session._drone_transition_state()
    for i, after in after_states.items():
        before = before_drone_states.get(i, {})
        d = session.env.drones[i]
        did = str(getattr(d, "drone_id", f"drone_{i}"))
        if after["waiting"] and not before.get("waiting"):
            sid = after.get("station")
            score = float(session.env._drone_berth_score(i))
            session._emit("berth_wait", f"{did} 在机巢 {sid} 等待泊位（动态优先级 {score:.3f}）", level="warning",
                       data={"drone_id": did, "drone_idx": i, "nest_id": str(sid)})
        if after["charging"] and not before.get("charging"):
            sid = after.get("station")
            session._emit("berth_granted", f"机巢 {sid} 向 {did} 分配泊位，开始换电", level="success",
                       data={"drone_id": did, "drone_idx": i, "nest_id": str(sid)})
        if before.get("charging") and not after["charging"]:
            session._emit("swap_completed", f"{did} 换电完成，恢复调度", level="success",
                       data={"drone_id": did, "drone_idx": i})

def _record_history(session, force: bool = False) -> None:
    """每 5 步记录一次关键指标；趋势由服务端持有，浏览器刷新后也能继续。"""
    if not force and session.step_count % 5 != 0:
        return
    stats = session._stats_snapshot()
    pending = len(getattr(session.env.task_generator, "unassigned_tasks", []) or [])
    session._history.append({
        "step": int(session.step_count),
        "time": round(float(session.env.current_time), 1),
        "completion_rate": round(float(stats.get("completion_rate", 0.0)), 6),
        "timeout_rate": round(float(stats.get("timeout_rate", 0.0)), 6),
        "utilization": round(float(stats.get("utilization", 0.0)), 6),
        "berth_utilization": round(float(stats.get("berth_utilization", 0.0)), 6),
        "pending": int(pending),
        "queue": int(sum(len(q) for q in getattr(session.env, "_nest_waiting", {}).values())),
    })
