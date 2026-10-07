# -*- coding: utf-8 -*-
"""ConsistencyObserver —— #68-B 的只读旁路事件轨迹（record fact，不 infer state）。

设计约束（来自用户裁定，逐条对应实现）：
1. **只观察**：不改任何现有对象、不参与状态判断、不返回业务结果、不成为新的状态真源。
   ⇒ 本模块**不写** ``Task.status``、不新增任何被环境/统计读取的字段；所有产出都是本地列表与文件。
2. **记事实，不推断状态**：⇒ 没有 ``TASK_COMPLETED`` 这种带语义的事件，只有
   ``TASK_COMPLETION_RECORDED``（"计数器被加了 1"这个可观测事实），其 reason 由
   **同回合是否发生过 DESTINATION_REACHED** 推出，而不是由本模块判定"任务完成了"。
3. **归因不靠 traceback 行号**（上一轮取证量具的已知缺陷：行号随代码改动静默失效）：
   ``DESTINATION_REACHED`` 在 :func:`observe_step_facts` 里独立重算谓词
   ``assignment['task'].get_destination() == popped[0:2]``，因此即使生产代码挪行，
   归因仍然成立 —— 它锚在**语义**上而不是行号上。

用法见 ``console/test_consistency_observer_zero_drift.py``。
"""
from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List, Optional

__all__ = ["ConsistencyObserver", "install"]


class ConsistencyObserver:
    """收集原始事件事实。每个事件是一条 dict，字段固定，便于后续独立重建与对账。"""

    #: 允许的事件名白名单。**新增事件名必须同时在此登记**，否则 record() 会拒绝，
    #: 防止未来把"推断出的状态"伪装成事实写进轨迹。
    EVENTS = (
        "TASK_GENERATED",
        "TASK_ASSIGNED",
        "TASK_LOADED",
        "DESTINATION_REACHED",
        "ASSIGNMENT_RELEASED",
        "DRONE_BECAME_FREE",
        "TASK_COMPLETION_RECORDED",
        "BERTH_OCCUPIED",
        "BERTH_VACATED",
        "SWAP_STARTED",
        "BATTERY_CONSUMED",
    )

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []
        self.rejected: List[str] = []          # 不在白名单的事件名（自证：本模块不许发明状态）
        self._seen_reached: set = set()         # task_id → 是否出现过 DESTINATION_REACHED
        self._loaded: set = set()               # task_id → 是否出现过 TASK_LOADED

    # ------------------------------------------------------------------
    def record(self, kind: str, *, sim_time: float, **fields: Any) -> None:
        if kind not in self.EVENTS:
            self.rejected.append(kind)
            return
        ev: Dict[str, Any] = {"kind": kind, "sim_time": float(sim_time)}
        ev.update(fields)
        if kind == "DESTINATION_REACHED":
            self._seen_reached.add(ev.get("task_id"))
        elif kind == "TASK_LOADED":
            self._loaded.add(ev.get("task_id"))
        self.events.append(ev)

    # ------------------------------------------------------------------
    def completion_recorded(self, env, drone_idx: int, assignment: Dict[str, Any],
                            counter_delta: Dict[str, float]) -> None:
        """记录"一次 _record_task_completion 调用产生了多少计数增量"这一事实。

        ⚠ 时机约束（本轮实测踩到后修正）：**不能**在 ``env.step()`` 之后再推断送达 ——
        dest 路径紧接着会 ``assignments.remove(assignment)``（environment.py:1220），
        届时该 assignment 已从 ``drone_assignments`` 消失，事后重算谓词恒得 False，
        会把 26 条真实送达误报成"无送达证据"。因此送达证据只能在**本次调用当下**取。

        取法：本方法被包在原 ``_record_task_completion`` 之后调用，此刻 assignment 对象仍在手上；
        用"无人机当前位置是否等于该任务 destination"作为送达的**独立几何证人**——
        位置读 ``Drone.get_position()``（返回 ``(self.x, self.y)``，drone.py:72-73/319-320），
        这是环境既有可读状态，不新增字段、不推断业务状态。
        """
        task = assignment["task"]
        tid = task.task_id
        try:
            drone = env.drones[int(drone_idx)]
            pos = tuple(drone.get_position())
        except Exception:
            pos = ()
        dst = tuple(task.get_destination()) if task.get_destination() else ()
        delivery_evidence = (bool(pos) and bool(dst)
                             and abs(float(pos[0]) - float(dst[0])) < 1e-6
                             and abs(float(pos[1]) - float(dst[1])) < 1e-6)

        if delivery_evidence:
            # 送达事实要在这一刻单独成条：它是 C1 规则①的证人，也是"取货早于送达"的时间锚。
            self.record("DESTINATION_REACHED", sim_time=float(env.current_time),
                        task_id=tid, drone_index=int(drone_idx))
        self.record(
            "TASK_COMPLETION_RECORDED",
            sim_time=float(env.current_time),
            task_id=tid,
            drone_index=int(drone_idx),
            load_time_raw=assignment.get("load_time"),          # 原始事实：None 就是 None，不兜底
            assigned_time_raw=assignment.get("assigned_time", assignment.get("start_time")),
            deadline_raw=task.get_deadline(),
            drone_position=[float(pos[0]), float(pos[1])] if len(pos) >= 2 else None,
            delivery_evidence=delivery_evidence,
            pickup_evidence=(tid in self._loaded) or (assignment.get("load_time") is not None),
            # reason 是**几何证据的直接映射**，不是对业务意图的猜测：
            #   destination_reached ⇒ 无人机此刻恰在该任务 destination 上
            #   no_delivery_evidence ⇒ 此刻不在；至于它为何被记账（is_free 清理？其它路径？）
            #   属于待 #68-C1 之后用轨迹反推的问题，本字段不替它作答。
            reason=("destination_reached" if delivery_evidence else "no_delivery_evidence"),
            **counter_delta,                                     # Δcompleted / Δon_time / Δdelay
        )

    # ------------------------------------------------------------------
    def summary(self) -> Dict[str, Any]:
        comp = [e for e in self.events if e["kind"] == "TASK_COMPLETION_RECORDED"]
        with_ev = [e for e in comp if e["delivery_evidence"]]
        without = [e for e in comp if not e["delivery_evidence"]]
        no_pickup = [e for e in without if not e["pickup_evidence"]]
        kinds: Dict[str, int] = {}
        for e in self.events:
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        return {
            "events_total": len(self.events),
            "event_kinds_observed": dict(sorted(kinds.items())),   # 实际出现过的事件，不是白名单声明
            "rejected_event_names": sorted(set(self.rejected)),
            "completions_recorded": len(comp),
            "with_delivery_evidence": len(with_ev),
            "without_delivery_evidence": len(without),
            "without_delivery_and_never_loaded": len(no_pickup),
            "sum_delta_completed": sum(e["d_completed"] for e in comp),
            "sum_delta_on_time": sum(e["d_ontime"] for e in comp),
            "sum_delta_delay": round(sum(e["d_delay"] for e in comp), 6),
            "berth_occupied_events": kinds.get("BERTH_OCCUPIED", 0),
            "berth_vacated_events": kinds.get("BERTH_VACATED", 0),
        }

    def dump(self, path: pathlib.Path) -> None:
        payload = {"summary": self.summary(), "events": self.events}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")


# ======================================================================
# 挂载：全部是"包一层再调原函数"，除累加器外不产生任何副作用
# ======================================================================

_STATE: Dict[str, Any] = {}


def _delta(before: tuple, after: tuple) -> Dict[str, float]:
    return {"d_delay": after[0] - before[0],
            "d_ontime": after[1] - before[1],
            "d_completed": after[2] - before[2]}


def observe_step_facts(env, obs_action: Dict[int, Any], observer: ConsistencyObserver) -> None:
    """在 ``env.step()`` **之后**调用，从环境的既有可见状态里抽事实。

    只做读取：比较坐标、检查 is_free、遍历 drone_assignments。不写任何对象。
    必须在 step 内已完成 DESTINATION_REACHED 相关判定后调用 —— 这里用"重算谓词"的方式
    独立发现送达事实，而不是去 hook 那一行 if，从而避免侵入式改动。
    """
    t = float(env.current_time)
    # 1) 送达事实：当前位于某任务 destination 的 assignment
    for idx, assignments in list(getattr(env, "drone_assignments", {}).items()):
        items = assignments if isinstance(assignments, list) else [assignments]
        for a in items:
            task = a.get("task")
            if task is None:
                continue
            if a.get("load_time") is not None and task.task_id not in observer._loaded:
                observer.record("TASK_LOADED", sim_time=t, task_id=task.task_id,
                                drone_index=int(idx), load_time=a.get("load_time"))
    # 2) 无人机转空闲
    prev = getattr(env, "_prev_free_status", {})
    for idx, drone in enumerate(env.drones):
        was_free = bool(prev.get(idx, True))
        now_free = bool(getattr(drone, "is_free", False))
        if (not was_free) and now_free:
            observer.record("DRONE_BECAME_FREE", sim_time=t, drone_index=int(idx),
                            battery=float(getattr(drone, "current_battery", 0.0)))
    # 3) 机巢占用快照差分（occupy/vacate 的净效果；不改它们）
    for st in getattr(env, "charging_stations", []) or []:
        sid = getattr(st, "station_id", None)
        occ = int(getattr(st, "occupied", 0))
        last = _STATE.setdefault("berths", {})
        delta = occ - last.get(sid, occ)      # 首次见到该站时基线取当前值，避免造出虚假事件
        last[sid] = occ
        if delta > 0:
            for _ in range(delta):
                observer.record("BERTH_OCCUPIED", sim_time=t, station_id=sid, occupied=occ)
        elif delta < 0:
            for _ in range(-delta):
                observer.record("BERTH_VACATED", sim_time=t, station_id=sid, occupied=occ)


def install(env, observer: ConsistencyObserver):
    """把观察者挂到 env 实例上（仅实例级 monkeypatch，不污染类、不影响其他进程）。

    返回一个 callable：调用它即可卸载并恢复原方法。
    """
    orig_record = env._record_task_completion
    orig_step = env.step

    def rec(drone_idx, assignment):
        before = (env.total_delay, env.total_on_time_tasks, env.total_completed_tasks)
        result = orig_record(drone_idx, assignment)
        after = (env.total_delay, env.total_on_time_tasks, env.total_completed_tasks)
        observer.completion_recorded(env, drone_idx, assignment, _delta(before, after))
        return result                                     # 原样返回（本函数不返回业务结果给环境）

    def step(actions):
        out = orig_step(actions)
        try:
            observe_step_facts(env, actions, observer)
        except Exception as exc:                          # 观察失败绝不影响仿真
            observer.record("_OBSERVER_ERROR", sim_time=float(env.current_time),
                            error=f"{type(exc).__name__}: {exc}")
        return out

    env._record_task_completion = rec
    env.step = step
    _STATE.clear()

    def uninstall():
        env._record_task_completion = orig_record
        env.step = orig_step
        _STATE.clear()
    return uninstall
