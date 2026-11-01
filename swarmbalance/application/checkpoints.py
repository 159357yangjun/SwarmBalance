"""Checkpoints; functions operate on the owning session without duplicating state."""
from __future__ import annotations
import copy
import hashlib
import json
import random
import sys
from collections import deque
from typing import Any, Dict, List
import numpy as np
from swarmbalance.infrastructure.config.loader import config_signature, get_shared_config


def _env_generation(session) -> str:
    """环境结构指纹：机队规模、机巢数量与泊位、禁飞区数量、回合上限等。

    这些一变，旧快照里的无人机下标、泊位编号、任务归属就对不上了。旧实现在
    rebuild() 里直接 ``_checkpoints.clear()`` 把用户存的快照一并销毁（误点一次
    「保存并应用」就丢掉答辩前存的「故障注入前」节点，且无法撤销）。改成打标：
    快照保留，跨代恢复时给出可执行的错误提示。
    """
    sig = config_signature()
    cached = session._GEN_CACHE.get(sig)
    if cached is not None:
        return cached
    cfg = get_shared_config()
    env_cfg = cfg.get("environment") or {}
    het = cfg.get("heterogeneous") or {}
    structural = {
        "num_drones": env_cfg.get("num_drones"),
        "episode_max_steps": env_cfg.get("episode_max_steps"),
        "allow_multi_task": env_cfg.get("allow_multi_task"),
        "hetero_enabled": het.get("enabled"),
        "fleet_mix": het.get("fleet_mix"),
        "nests": len(cfg.get("charging_stations") or []),
        "berths": (cfg.get("nest") or {}).get("berths"),
        "no_fly_zones": len(cfg.get("no_fly_zones") or []),
    }
    raw = json.dumps(structural, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]
    if len(session._GEN_CACHE) > 32:      # 一键实验会换很多临时配置，别让它无限长
        session._GEN_CACHE.clear()
    session._GEN_CACHE[sig] = digest
    return digest

def list_checkpoints(session) -> List[Dict[str, Any]]:
    current = session._env_generation()
    rows = []
    for name, item in session._checkpoints.items():
        meta = item.get("meta") or {}
        gen = item.get("env_gen")
        rows.append({
            "name": name, "step": int(meta.get("step", 0)), "time": float(meta.get("time", 0.0)),
            "algorithm": meta.get("algorithm"), "seed": meta.get("seed"),
            # 跨环境重建的快照仍可列出（不销毁用户数据），但不可恢复
            "可用": gen is None or gen == current,
        })
    return rows

def save_checkpoint(session, name: str = "checkpoint") -> Dict:
    """保存当前完整运行态（内存检查点）。

    为控制内存，不复制 OSM 建筑几何、地图边界和 DataSource；其余 Environment
    动态属性、无人机/机巢/任务、Scheduler 缓存、事件、轨迹和指标历史一起保存。
    """
    name = str(name or "checkpoint").strip()[:40]
    if not name:
        raise ValueError("快照名称不能为空")
    env_dynamic = {k: v for k, v in session.env.__dict__.items() if k not in session._CHECKPOINT_STATIC_ENV_KEYS}
    state = {
        "env_dynamic": env_dynamic,
        "scheduler": session.scheduler,
        "obs": session.obs,
        "done": session.done,
        "step_count": session.step_count,
        "num_drones": session.num_drones,
        "trajectories": session.trajectories,
        "events": list(session._events),
        "event_seq": session._event_seq,
        "completed_task_owner": session._completed_task_owner,
        "history": list(session._history),
        "demo": session._demo,
        "algorithm": session.algorithm,
        "seed": session.seed,
        # TaskGenerator / Greedy / PSO 会使用进程级 Python / NumPy RNG。
        # 只保存对象树还不足以保证从检查点继续后的随机序列一致。
        "python_random_state": random.getstate(),
        "numpy_random_state": np.random.get_state(),
    }
    try:
        frozen = copy.deepcopy(state)
    except Exception as exc:
        raise ValueError(f"当前运行态无法创建快照: {exc}") from exc
    frozen["meta"] = {
        "step": int(session.step_count), "time": float(session.env.current_time),
        "algorithm": session.algorithm, "seed": session.seed,
    }
    # 记录保存时的环境结构，供 rebuild 后判断该快照是否还可安全恢复
    frozen["env_gen"] = session._env_generation()
    # 覆盖同名快照；新名称超过上限时移除最早插入的一项。
    # 这两件事过去都是静默的——实测存第 6 个快照时第一个会无声消失，
    # 而界面只写了一句「当前服务内最多 5 个」。改为如实回报，由前端提示用户。
    replaced = name if name in session._checkpoints else None
    evicted = None
    if replaced is None and len(session._checkpoints) >= session._CHECKPOINT_LIMIT:
        evicted = next(iter(session._checkpoints))
        session._checkpoints.pop(evicted, None)
    session._checkpoints[name] = frozen
    session._emit("checkpoint_saved", f"已保存运行态快照：{name}", level="success")
    return {
        "ok": True,
        "checkpoints": session.list_checkpoints(),
        "snapshot": session.snapshot(),
        "覆盖": replaced,
        "淘汰": evicted,
        "槽位": "%d/%d" % (len(session._checkpoints), session._CHECKPOINT_LIMIT),
    }

def load_checkpoint(session, name: str) -> Dict:
    name = str(name or "").strip()
    if name not in session._checkpoints:
        raise ValueError(f"运行态快照不存在: {name}")
    try:
        state = copy.deepcopy(session._checkpoints[name])
    except Exception as exc:
        raise ValueError(f"运行态快照无法恢复: {exc}") from exc
    gen = state.get("env_gen")
    if gen is not None and gen != session._env_generation():
        raise ValueError(
            f"快照「{name}」保存于另一次环境重建之前（机队规模、机巢数量与泊位、"
            "禁飞区数量或回合上限已改变），跨代恢复会让无人机下标与泊位编号错位，"
            "已拒绝。请在当前配置下重新保存一个快照。"
        )
    # 保留当前静态地图对象，只覆盖保存时的动态环境状态。
    current_static = {k: session.env.__dict__.get(k) for k in session._CHECKPOINT_STATIC_ENV_KEYS}
    for key in list(session.env.__dict__):
        if key not in session._CHECKPOINT_STATIC_ENV_KEYS and key not in state["env_dynamic"]:
            session.env.__dict__.pop(key, None)
    session.env.__dict__.update(state["env_dynamic"])
    for key, value in current_static.items():
        if value is not None:
            session.env.__dict__[key] = value

    session.scheduler = state["scheduler"]
    session.obs = state["obs"]
    session.done = bool(state["done"])
    session.step_count = int(state["step_count"])
    session.num_drones = int(state["num_drones"])
    session.trajectories = state["trajectories"]
    session._events = deque(state["events"], maxlen=300)
    session._event_seq = int(state["event_seq"])
    session._completed_task_owner = state["completed_task_owner"]
    session._history = deque(state["history"], maxlen=360)
    session._demo = state["demo"]
    session.algorithm = state["algorithm"]
    session.seed = int(state["seed"])
    # 最后恢复进程级 RNG，保证 TaskGenerator / Greedy / PSO 从该节点继续时
    # 复用保存时的下一段随机序列，而不是沿用恢复前的随机状态。
    if state.get("python_random_state") is not None:
        random.setstate(state["python_random_state"])
    if state.get("numpy_random_state") is not None:
        np.random.set_state(state["numpy_random_state"])
    seed_mod = sys.modules.get("swarmbalance.simulation.seed")
    if seed_mod is not None and hasattr(seed_mod, "CURRENT_SEED"):
        seed_mod.CURRENT_SEED = session.seed
    session._emit("checkpoint_loaded", f"已恢复运行态快照：{name}", level="important")
    snap = session.snapshot()
    # 仅恢复检查点时携带历史轨迹，避免每个 step 响应都重复发送大量坐标。
    snap["trajectories_restore"] = copy.deepcopy(session.trajectories)
    return snap

def delete_checkpoint(session, name: str) -> Dict:
    name = str(name or "").strip()
    if name not in session._checkpoints:
        raise ValueError(f"运行态快照不存在: {name}")
    session._checkpoints.pop(name, None)
    return {"ok": True, "checkpoints": session.list_checkpoints()}
