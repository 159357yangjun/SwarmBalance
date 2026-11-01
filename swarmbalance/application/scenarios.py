"""Scenarios; functions operate on the owning session without duplicating state."""
from __future__ import annotations
import json
from typing import Any, Dict, List
from swarmbalance.application.snapshots import _drone_state


def set_demo_context(session, key: str, name: str, script: List[Dict[str, Any]]) -> Dict:
    """绑定演示剧本。剧本动作只是调用现有控制接口，不绕过调度器。"""
    session._demo = {
        "active": True,
        "key": str(key),
        "name": str(name),
        "script": [dict(x) for x in (script or [])],
        "cursor": 0,
    }
    session._emit("demo_loaded", f"已加载演示场景：{name}", level="important", data={"demo_key": str(key)})
    return session.snapshot()

def clear_demo_context(session) -> None:
    session._demo = {"active": False, "key": None, "name": None, "script": [], "cursor": 0}

def advance_demo(session) -> Dict:
    """执行演示剧本的“下一幕”。

    动作均复用公开的 step / inject / incident / charge 控制接口，因此不会出现
    “答辩演示是一套假逻辑、真实仿真又是另一套逻辑”的问题。
    """
    if not session._demo.get("active"):
        raise ValueError("当前没有活动演示场景")
    script = session._demo.get("script") or []
    cursor = int(session._demo.get("cursor", 0))
    if cursor >= len(script):
        session._emit("demo_complete", f"演示剧本《{session._demo.get('name') or ''}》已完成", level="success")
        return session.snapshot()

    item = dict(script[cursor])
    action = str(item.get("action") or "").strip()
    label = str(item.get("label") or action or f"步骤 {cursor+1}")
    session._emit("demo_action", f"演示第 {cursor+1} 幕：{label}", level="important", data={"demo_key": session._demo.get("key")})

    if action == "step":
        session.step_many(int(item.get("count", 1)))
    elif action == "inject_task":
        payload = dict(item.get("task") or {})
        session.inject_task(**payload)
    elif action == "fault_busy_drone":
        online = [(i, d) for i, d in enumerate(session.env.drones) if not getattr(d, "out_of_service", False)]
        if not online:
            raise ValueError("当前没有可故障注入的在线无人机")
        busy = [(i, d) for i, d in online if _drone_state(d) == "busy"]
        i, d = (busy or online)[0]
        session.set_drone_out_of_service(str(getattr(d, "drone_id", f"drone_{i}")), True, "演示剧本：模拟动力/通信故障")
    elif action == "close_busy_nest":
        open_rows = [r for r in session._nests_snapshot() if not r.get("closed")]
        if len(open_rows) <= 1:
            raise ValueError("至少需要两个开放机巢才能执行关闭演示")
        open_rows.sort(key=lambda r: (-(r.get("queue_length") or 0), -(r.get("occupied") or 0), str(r.get("id"))))
        session.set_nest_closed(str(open_rows[0]["id"]), True, "演示剧本：模拟机巢维护/资源故障")
    elif action == "charge_two_drones":
        candidates = [d for d in session.env.drones if not getattr(d, "out_of_service", False)
                      and not getattr(d, "is_charging", False) and not getattr(d, "awaiting_berth", False)
                      and not getattr(d, "_manual_charge_requested", False)]
        candidates.sort(key=lambda d: (0 if _drone_state(d) == "busy" else 1, str(getattr(d, "drone_id", ""))))
        if not candidates:
            raise ValueError("当前没有可调往机巢补能的无人机")
        for d in candidates[:2]:
            session.request_drone_charge(str(d.drone_id))
    elif action == "restore_incidents":
        # 恢复无人机。先恢复机巢，保证无人机恢复后总有可用地面资源。
        for st in list(session.env.charging_stations):
            if getattr(st, "closed", False):
                session.set_nest_closed(str(st.station_id), False, "演示剧本：恢复开放")
        for d in list(session.env.drones):
            if getattr(d, "out_of_service", False):
                session.set_drone_out_of_service(str(d.drone_id), False, "演示剧本：恢复上线")
    elif action == "pause_stream":
        session.set_task_generation_paused(bool(item.get("paused", True)))
    else:
        raise ValueError(f"未知演示动作: {action}")

    session._demo["cursor"] = cursor + 1
    if session._demo["cursor"] >= len(script):
        session._emit("demo_complete", f"演示剧本《{session._demo.get('name') or ''}》已完成", level="success")
    return session.snapshot()


from swarmbalance.contracts.errors import ApplicationError
from swarmbalance.paths import CONFIG_DIR, SCHEDULER_CONFIG
from swarmbalance.application import scenario_presets
from swarmbalance.application.configuration import _deep_merge, _write_scheduler_yaml
_SIM_JSON = CONFIG_DIR / "simulation.json"
_ALG_YAML = SCHEDULER_CONFIG


def apply_scenario(key: str, context):
    """加载答辩演示场景。首次加载时保存用户原 simulation.json，便于一键恢复。"""
    if not _SIM_JSON.exists():
        raise ApplicationError(status_code=404, detail="simulation.json 不存在")
    try:
        preset = scenario_presets.get(key)
    except KeyError:
        raise ApplicationError(status_code=404, detail=f"未知演示场景: {key}")

    current_text = _SIM_JSON.read_text(encoding="utf-8")
    created_backup = False
    with context.operation_lock:
        session = context.get_session()
        previous_runtime = {"algorithm": session.algorithm, "seed": session.seed}
        if context.scenario_backup_text is None:
            # 第一次进入演示模式时保存用户真实配置；之后在多个预设之间切换，
            # 每次都从这份基线重新打 patch，避免上一个预设的泊位数/任务密度等
            # 悄悄泄漏到下一个预设。
            context.scenario_backup_text = current_text
            context.scenario_backup_runtime = dict(previous_runtime)
            created_backup = True
        base_text = context.scenario_backup_text or current_text
        cfg = json.loads(base_text)
        cfg = _deep_merge(cfg, preset.get("config_patch") or {})
        _SIM_JSON.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            # rebuild 让模块级配置常量生效，再按预设算法/Seed 重置一次。
            session.rebuild()
            snap = session.reset(preset.get("algorithm", "ga"), int(preset.get("seed", 100)))
            if bool(preset.get("task_generation_paused", False)):
                snap = session.set_task_generation_paused(True)
            # 初始人工任务沿用 Environment.inject_task，位置为空时继续使用当前随机源合法点规则。
            for task in preset.get("initial_tasks") or []:
                snap = session.inject_task(**dict(task))
            snap = session.set_demo_context(key, preset["name"], preset.get("script") or [])
        except Exception as exc:
            # 加载失败时回到“点击加载前”的配置，而不是把用户卡在半套预设里。
            _SIM_JSON.write_text(current_text, encoding="utf-8")
            try:
                session.rebuild()
                session.reset(previous_runtime["algorithm"], int(previous_runtime["seed"]))
            except Exception:
                pass
            if created_backup:
                context.scenario_backup_text = None
                context.scenario_backup_runtime = None
            raise ApplicationError(status_code=400, detail=f"演示场景加载失败，配置已回滚: {exc}")
    return snap

def restore_scenario(context):
    """恢复进入演示模式前的 simulation.json 与算法/Seed。"""
    if context.scenario_backup_text is None:
        raise ApplicationError(status_code=409, detail="当前没有可恢复的演示前配置")
    restore_text = context.scenario_backup_text
    previous_runtime = dict(context.scenario_backup_runtime or {})
    current_text = _SIM_JSON.read_text(encoding="utf-8") if _SIM_JSON.exists() else ""
    _SIM_JSON.write_text(restore_text, encoding="utf-8")
    try:
        with context.operation_lock:
            session = context.get_session()
            session.rebuild()
            snap = session.reset(previous_runtime.get("algorithm", "greedy"), int(previous_runtime.get("seed", 100)))
            session.clear_demo_context()
            snap = session.snapshot()
    except Exception as exc:
        if current_text:
            _SIM_JSON.write_text(current_text, encoding="utf-8")
        raise ApplicationError(status_code=400, detail=f"恢复演示前配置失败: {exc}")
    context.scenario_backup_text = None
    context.scenario_backup_runtime = None
    return snap

def scene_library_apply(scene_id: str, context):
    """事务式应用场景库配置，并按场景记录的算法/Seed 重建。

    场景库负责“可复现初始配置”；运行态 checkpoint 负责“精确动态节点”。
    为避免用户在答辩预设的临时配置上再次叠加持久场景，演示模式中禁止应用。
    """
    if context.scenario_backup_text is not None:
        raise ApplicationError(status_code=409, detail="当前处于答辩演示场景，请先点击“恢复演示前配置”再应用场景库")
    try:
        doc = context.scene_library.get(scene_id)
    except KeyError:
        raise ApplicationError(status_code=404, detail="场景不存在")
    except ValueError as exc:
        raise ApplicationError(status_code=400, detail=str(exc))

    old_sim = _SIM_JSON.read_text(encoding="utf-8") if _SIM_JSON.exists() else ""
    old_alg = _ALG_YAML.read_text(encoding="utf-8") if _ALG_YAML.exists() else ""
    _SIM_JSON.write_text(json.dumps(doc["simulation_config"], ensure_ascii=False, indent=2), encoding="utf-8")
    if doc.get("scheduler_config") is not None:
        _write_scheduler_yaml(doc["scheduler_config"])
    try:
        with context.operation_lock:
            session = context.get_session()
            session.rebuild()
            snap = session.reset(doc.get("algorithm", "ga"), int(doc.get("seed", 100)))
            session.clear_demo_context()
            snap = session.snapshot()
    except Exception as exc:
        if old_sim:
            _SIM_JSON.write_text(old_sim, encoding="utf-8")
        if old_alg:
            _ALG_YAML.write_text(old_alg, encoding="utf-8")
        try:
            with context.operation_lock:
                session = context.get_session()
                session.rebuild()
        except Exception:
            pass
        raise ApplicationError(status_code=400, detail=f"场景应用失败，配置已回滚: {exc}")
    return snap
