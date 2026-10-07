# -*- coding: utf-8 -*-
"""ConsistencyObserver —— #68-B/#68-C1 的只读旁路事件轨迹（record fact，不 infer state）。

三条不变的设计约束：
1. **只观察**：不改任何现有对象、不参与状态判断、不返回业务结果、不成为新的状态真源。
   ⇒ 本模块**不写** ``Task.status``，也不给生产 dict 添加键；产出只是本地列表与文件。
2. **记事实，不推断业务语义**：字段命名严格区分"代码走了哪条分支"与"这件事在业务上算什么"。
   ``record_origin`` 只取 ``destination_branch`` / ``is_free_cleanup_branch`` 两个值 —— 它们是
   :func:`_frame_line` 读到的**源码字面行内容**的分类，不是对任务命运的判定。
   ⚠ 早期版本用过 ``reason="cleanup_released"``：**released 是业务语义，未经证明 ⇒ 已作废**。
3. **归因锚在源码文本而非行号**：行号会随代码改动静默失效（本项目踩过）。这里比对的是
   调用点那一行的**文本**，若生产代码改写导致匹配不上，则记为 ``unknown_call_site`` 并计入
   ``unattributed_completions`` —— 让"量具瞎了"变成可见读数，而不是伪装成一次成功归因。

用法见 ``console/test_consistency_observer_zero_drift.py`` 与 ``console/test_c1_lifecycle_gate.py``。
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any, Callable, Dict, List, Optional

__all__ = ["ConsistencyObserver", "install"]

#: 调用点文本 → record_origin。键是 environment.py 里那两行**语句本身**。
_ORIGIN_MARKERS = (
    ("dest_pos_matches_completion", "assignment['task'].get_destination() == dest_pos"),
    ("is_free_cleanup", "if not self._prev_free_status.get(i, True) and drone.is_free:"),
)


#: 分支判定的**源码文本锚**。每条 = (标识, 该分支内调用语句上方若干行必须包含的子串)。
#: 用文本而非行号 ⇒ 生产代码挪行仍成立；若两处都匹配不上则 unknown（可见失败），不猜。
_BRANCH_ANCHORS = (
    ("destination_branch", ("get_destination() == dest_pos",)),
    ("is_free_cleanup_branch", ("not self._prev_free_status.get(i, True) and drone.is_free",)),
)


def _classify_origin(src_lines: List[str]) -> str:
    """在调用点上方的源码窗口里找分支锚文本。**找不到就明说 unknown_call_site。**"""
    window = "\n".join(src_lines)
    for name, needles in _BRANCH_ANCHORS:
        if any(n in window for n in needles):
            return name
    return "unknown_call_site"


class ConsistencyObserver:
    """收集原始事件事实。每个事件是一条 dict，字段固定，便于后续独立重建与对账。"""

    EVENTS = (
        "TASK_GENERATED",
        "TASK_ASSIGNED",
        "TASK_LOADED",
        "DESTINATION_REACHED",
        "ASSIGNMENT_RELEASED",
        "DRONE_BECAME_FREE",
        "TASK_RETURNED_TO_POOL",
        "DRONE_OUT_OF_SERVICE",
        "TASK_COMPLETION_RECORDED",
        "BERTH_OCCUPIED",
        "BERTH_VACATED",
        "SWAP_STARTED",
        "BATTERY_CONSUMED",
    )

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []
        self.rejected: List[str] = []
        self.unattributed: int = 0            # 归因失败的 completion 数（量具瞎了的可见读数）
        self._loaded: set = set()
        self._seq: int = 0                    # 全局事件序号：离散仿真同一 sim_time 可有多个事件

    # ------------------------------------------------------------------
    def record(self, kind: str, *, sim_time: float, **fields: Any) -> None:
        if kind not in self.EVENTS:
            self.rejected.append(kind)
            return
        self._seq += 1
        ev: Dict[str, Any] = {"seq": self._seq, "kind": kind, "sim_time": float(sim_time)}
        ev.update(fields)
        if kind == "TASK_LOADED":
            self._loaded.add(ev.get("task_id"))
        self.events.append(ev)

    # ------------------------------------------------------------------
    def completion_recorded(self, env, drone_idx: int, assignment: Dict[str, Any],
                            counter_delta: Dict[str, float],
                            caller_line: Optional[str],
                            caller_ctx: Optional[List[str]] = None) -> None:
        """记录"一次 _record_task_completion 调用产生了多少计数增量"这一事实。

        字段全部是可观测事实或其直接映射，**不含业务判定**：
          ``record_origin``            调用点源码文本分类（destination_branch / is_free_cleanup_branch / unknown_call_site）
          ``has_destination_evidence`` 此刻无人机位置是否等于该任务 destination（几何证人）
          ``has_load_evidence``        assignment['load_time'] 是否被写过（None 就是没写过）
        """
        task = assignment["task"]
        tid = task.task_id
        try:
            pos = tuple(env.drones[int(drone_idx)].get_position())
        except Exception:
            pos = ()
        dst = tuple(task.get_destination()) if task.get_destination() else ()
        has_dst_ev = (bool(pos) and bool(dst)
                      and abs(float(pos[0]) - float(dst[0])) < 1e-6
                      and abs(float(pos[1]) - float(dst[1])) < 1e-6)
        origin = _classify_origin(list(caller_ctx or []))
        if origin == "unknown_call_site":
            self.unattributed += 1
        if has_dst_ev:
            # 送达事实单独成条：它是 C1 R1 的证人，也是 R2 的顺序锚。
            # payload_at_reach / task_weight 是**当时的实际载重与货重**：
            # 用于回答"未取货却送达的任务，无人机是不是仍按空载在飞"——只记事实，不下结论。
            self.record("DESTINATION_REACHED", sim_time=float(env.current_time),
                        task_id=tid, drone_index=int(drone_idx),
                        payload_at_reach=float(getattr(env.drones[int(drone_idx)], "current_load", 0.0)),
                        task_weight=float(task.get_weight()),
                        reach_has_load_evidence=assignment.get("load_time") is not None,
                        # ⚠ payload_at_reach **不能**用来判断"是否空载飞完全程"：
                        # dest 弹出后紧接着才卸货的写法是 :1211 record → :1214 current_load 扣减，
                        # 但实测连**有取货证据**的 19 条也全是 0 ⇒ 该时刻的读数无区分力。
                        # 途中真实载重看 BATTERY_CONSUMED 事件的 load_at_consumption（每步飞行时采）。
                        )
        self.record(
            "TASK_COMPLETION_RECORDED",
            sim_time=float(env.current_time),
            task_id=tid,
            drone_index=int(drone_idx),
            record_origin=origin,
            caller_line=(caller_line or "").strip()[:120],
            has_destination_evidence=has_dst_ev,
            has_load_evidence=assignment.get("load_time") is not None,
            load_time_raw=assignment.get("load_time"),      # 原始事实：None 就是 None，不兜底
            assigned_time_raw=assignment.get("assigned_time", assignment.get("start_time")),
            deadline_raw=task.get_deadline(),
            drone_position=[float(pos[0]), float(pos[1])] if len(pos) >= 2 else None,
            **counter_delta,
        )

    # ------------------------------------------------------------------
    def summary(self) -> Dict[str, Any]:
        comp = [e for e in self.events if e["kind"] == "TASK_COMPLETION_RECORDED"]
        legal = [e for e in comp if e["has_destination_evidence"]]
        illegal = [e for e in comp if not e["has_destination_evidence"]]
        kinds: Dict[str, int] = {}
        for e in self.events:
            kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
        origins: Dict[str, int] = {}
        for e in comp:
            origins[e["record_origin"]] = origins.get(e["record_origin"], 0) + 1
        return {
            "events_total": len(self.events),
            "event_kinds_observed": dict(sorted(kinds.items())),
            "rejected_event_names": sorted(set(self.rejected)),
            "completions_recorded": len(comp),
            "legal_completions": len(legal),
            "illegal_completions_no_destination_evidence": len(illegal),
            "illegal_and_never_loaded": sum(1 for e in illegal if not e["has_load_evidence"]),
            "destination_without_load": sum(1 for e in legal if not e["has_load_evidence"]),
            "completion_origins": dict(sorted(origins.items())),
            "unattributed_completions": self.unattributed,
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
# 挂载：包一层再调原函数；额外用 settrace 行回调抓"调用点源码文本"
# ======================================================================

_STATE: Dict[str, Any] = {}


def _delta(before: tuple, after: tuple) -> Dict[str, float]:
    return {"d_delay": after[0] - before[0],
            "d_ontime": after[1] - before[1],
            "d_completed": after[2] - before[2]}


def observe_step_facts(env, observer: ConsistencyObserver) -> None:
    """在 ``env.step()`` 之后从环境既有可读状态抽事实。只做读取，不写任何对象。

    事件靠**状态差分**发现（不锚源码行号）：
      ASSIGNMENT_RELEASED   —— 上一步还在 ``drone_assignments``、这一步没了的 assignment
      TASK_RETURNED_TO_POOL —— 该任务此刻重新出现在 ``task_generator.unassigned_tasks``
      DRONE_OUT_OF_SERVICE  —— ``out_of_service`` 由假变真
    ⚠ 这三个都是"动作发生过"的事实，不是对任务命运的判定；尤其 RELEASED ≠ 失败、
      RETURNED ≠ 可重试成功。业务语义留待 BI 裁定后再引入。
    """
    t = float(env.current_time)
    cur_assigns = getattr(env, "drone_assignments", {}) or {}
    prev_snap: Dict[Any, Any] = _STATE.setdefault("assigns", {})

    # ---- 1) 本步在飞的 assignment 快照 + 取货事实 ----------------------
    now_snap: Dict[Any, Any] = {}
    for idx, assignments in list(cur_assigns.items()):
        items = assignments if isinstance(assignments, list) else [assignments]
        for a in items:
            task = a.get("task")
            if task is None:
                continue
            tid = task.task_id
            now_snap[tid] = dict(drone_index=int(idx), load_time=a.get("load_time"))
            if a.get("load_time") is not None and tid not in observer._loaded:
                observer.record("TASK_LOADED", sim_time=t, task_id=tid,
                                drone_index=int(idx), load_time=a.get("load_time"))

    # ---- 2) 上一步还在、这一步没了 ⇒ 释放动作发生过 --------------------
    released = sorted(set(prev_snap) - set(now_snap))
    pool_now = {str(x.task_id) for x in (getattr(getattr(env, "task_generator", None),
                                                 "unassigned_tasks", []) or [])}
    for tid in released:
        info = prev_snap.get(tid, {})
        observer.record("ASSIGNMENT_RELEASED", sim_time=t, task_id=tid,
                        drone_index=int(info.get("drone_index", -1)),
                        had_load=bool(info.get("load_time") is not None))
        if str(tid) in pool_now:
            # 只有代码真的把它放回 unassigned_tasks 才记这条（BI：动作不存在就不许记）
            observer.record("TASK_RETURNED_TO_POOL", sim_time=t, task_id=tid)

    _STATE["assigns"] = now_snap

    # ---- 3) 无人机转空闲 + 途中载重采样 --------------------------------
    prev = getattr(env, "_prev_free_status", {})
    for idx, drone in enumerate(env.drones):
        was_free = bool(prev.get(idx, True))
        now_free = bool(getattr(drone, "is_free", False))
        if (not was_free) and now_free:
            observer.record("DRONE_BECAME_FREE", sim_time=t, drone_index=int(idx),
                            battery=float(getattr(drone, "current_battery", 0.0)))
        # 每步采一次"在飞时的实际载重与电量"：这是判断空载飞行/能耗口径的唯一有效证人。
        # 只采非空闲且有航线的机子，避免把停场状态当成"载重 0 在飞"。
        if not now_free and getattr(drone, "scheduled_position", None):
            load = float(getattr(drone, "current_load", 0.0))
            bat = float(getattr(drone, "current_battery", 0.0))
            last = _STATE.setdefault("flight", {})
            prev_bat = last.get(idx)
            if prev_bat is not None and prev_bat - bat > 1e-12:
                observer.record("BATTERY_CONSUMED", sim_time=t, drone_index=int(idx),
                                load_at_consumption=load,
                                wh_used=round(prev_bat - bat, 6))
            last[idx] = bat

    # ---- 3) out_of_service 由假变真 -----------------------------------
    oos_prev = _STATE.setdefault("oos", {})
    for idx, drone in enumerate(env.drones):
        now_oos = bool(getattr(drone, "out_of_service", False))
        if now_oos and not oos_prev.get(idx, False):
            observer.record("DRONE_OUT_OF_SERVICE", sim_time=t, drone_index=int(idx))
        oos_prev[idx] = now_oos

    # ---- 4) 泊位占用差分 -------------------------------------------------
    for st in getattr(env, "charging_stations", []) or []:
        sid = getattr(st, "station_id", None)
        occ = int(getattr(st, "occupied", 0))
        last = _STATE.setdefault("berths", {})
        delta = occ - last.get(sid, occ)
        last[sid] = occ
        for _ in range(max(0, delta)):
            observer.record("BERTH_OCCUPIED", sim_time=t, station_id=sid, occupied=occ)
        for _ in range(max(0, -delta)):
            observer.record("BERTH_VACATED", sim_time=t, station_id=sid, occupied=occ)


def install(env, observer: ConsistencyObserver):
    """挂载观察者。返回 callable 用于卸载并恢复原方法。

    ``record_origin`` 的来源：用 ``traceback.extract_stack()`` 读**调用者那一行的源码文本**，
    再按文本分类成分支标识。锚在文本而非行号上 ⇒ 生产代码挪行不会让归因静默错位；
    若那两行文字本身被改写导致匹配不上，则记 ``unknown_call_site`` 并计入
    ``unattributed_completions``，让"量具瞎了"成为可见读数而不是一次猜出来的归因。
    （曾试过 ``sys.settrace`` 行回调：实测在本包装里拿不到被包裹函数的帧，38/38 全成 unknown。）
    """
    orig_record = env._record_task_completion
    orig_step = env.step

    def rec(drone_idx, assignment):
        before = (env.total_delay, env.total_on_time_tasks, env.total_completed_tasks)
        caller_line = None
        caller_ctx: List[str] = []
        try:
            import linecache
            import traceback
            # 只认「语句本身就是那一次调用」的帧。⚠ 不能只判子串 —— 外层包装帧的行文本同样含
            # `_record_task_completion`，倒序遍历会先撞上它，导致 38/38 全被误判成同一分支（本轮实测踩过）。
            for fr in reversed(traceback.extract_stack()[:-1]):
                if not fr.filename.endswith("environment.py"):
                    continue
                t = (fr.line or "").strip()
                if t.startswith("self._record_task_completion("):
                    caller_line = t
                    # 取该调用点上方窗口读**守卫语句文本**：dest 分支的调用行不含分支特征，
                    # 必须看它的 if。窗口取 12 行足以跨过两层循环而不越到相邻块。
                    caller_ctx = [linecache.getline(fr.filename, ln) or ""
                                  for ln in range(max(1, fr.lineno - 12), fr.lineno + 1)]
                    break
        except Exception:
            caller_line, caller_ctx = None, []
        result = orig_record(drone_idx, assignment)
        after = (env.total_delay, env.total_on_time_tasks, env.total_completed_tasks)
        observer.completion_recorded(env, drone_idx, assignment,
                                     _delta(before, after), caller_line, caller_ctx)
        return result

    def step(actions):
        out = orig_step(actions)
        try:
            observe_step_facts(env, observer)
        except Exception as exc:
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
