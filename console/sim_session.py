"""仿真会话封装（SimSession）—— 可视化控制台的仿真服务层。

把 `evaluate_metrics.py` / `run_*.py` 里那段同步循环：

    while not done:
        action = scheduler.step(obs, current_time)
        obs, _, done, _ = env.step(action)

抽象成可由外部驱动的最小会话对象，支持 启动/重置/单步/查询快照/**热重载重建**。
物理口径、算法逻辑、指标定义一律不动，只是把"跑循环"变成"按需推进"。

阶段二新增：
- `rebuild()`：写回 simulation.json 后热重载配置，重建 Environment（无需重启服务）；
- `map_static()`：导出建筑轮廓 + 高度 + 边界，供前端 3D 视图一次性加载。
"""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import math
import random
import sys
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

# 定位项目根与 frontend 目录，确保 environment / config / backend_si 可导入
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_FRONTEND = _PROJECT_ROOT / "frontend"

for _p in (str(_PROJECT_ROOT), str(_FRONTEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ALGORITHMS = ["greedy", "pso", "ga", "ortools"]

# 顶层只 import 模块（不 from import 值），便于 rebuild 时刷新到 reload 后的新类
import environment as _env_module  # noqa: E402
from config.config_loder import (config_signature, get_episode_max_steps,
                                get_shared_config)  # noqa: E402


def reload_sim_modules():
    """按依赖序 reload 在顶层固化 simulation.json 配置的模块。

    `config.config_loder.get_shared_config()` 每次调用都重读文件（无缓存），
    但 drone/task/charging_station/environment 四模块在**模块顶层**把配置算成了
    模块级常量。改配置后必须按依赖序 reload 它们（以及顶层 from-import 了这些
    类引用的 data_source / tools.osm），才能让新配置真正生效。
    """
    mods = [
        "charging_station",
        "drone",
        "task",
        "no_fly_zone",
        "data_source",
        "tools.osm",
        "environment",
    ]
    for name in mods:
        if name in sys.modules:
            try:
                importlib.reload(sys.modules[name])
            except Exception:
                # reload 失败不应阻断：最坏退回旧模块，仍可继续
                continue


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


class SimSession:
    """单个仿真会话。一个进程里通常只持有一个实例。"""

    def __init__(self,
                 osm_path: Optional[str] = None,
                 episode_max_steps: Optional[int] = None):
        self.osm_path = osm_path or str(_FRONTEND / "data" / "map" / "part_of_yangpu.osm")
        if episode_max_steps is None:
            # 传自己解析到的配置：保留 sim_session 这一层可被 patch/被
            # SWARM_BALANCE_SIM_CONFIG 影响的语义，同时仍然没有数字兜底。
            episode_max_steps = get_episode_max_steps(config=get_shared_config())
        self.episode_max_steps = int(episode_max_steps)
        # 动态取类，保证 rebuild 后能拿到 reload 后的新 Environment
        env_cls = _env_module.Environment
        self.env = env_cls(self.osm_path,
                           episode_max_steps=self.episode_max_steps)
        self.num_drones = len(self.env.drones)
        self.algorithm: str = "greedy"
        self.seed: int = 100
        self.scheduler: Any = None
        self.obs: Optional[Dict] = None
        self.done: bool = False
        self.step_count: int = 0
        self.trajectories: List[List[List[float]]] = [[] for _ in range(self.num_drones)]
        # 控制台事件流：只保存最近若干条，避免长时间仿真内存持续增长。
        self._events = deque(maxlen=300)
        self._event_seq = 0
        # 已完成任务对应的执行无人机，仅用于控制台任务生命周期回看。
        self._completed_task_owner: Dict[str, Dict[str, Any]] = {}
        # 服务端指标历史：避免前端刷新/切页后趋势丢失。每 5 步采样，最多保留 360 点。
        self._history = deque(maxlen=360)
        # 一键演示上下文。只保存“剧本光标”，不替代真实算法。
        self._demo: Dict[str, Any] = {
            "active": False, "key": None, "name": None, "script": [], "cursor": 0
        }
        # 运行态快照（仅当前服务进程，最多 5 个）。保存动态状态，不复制 OSM 建筑几何。
        self._checkpoints: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # 控制接口
    # ------------------------------------------------------------------

    def reset(self, algorithm: str, seed: int = 100) -> Dict:
        algorithm = algorithm if algorithm in ALGORITHMS else "greedy"
        self.algorithm = algorithm
        self.seed = int(seed)
        self.scheduler = self._build_scheduler(algorithm, seed)
        self.obs = self.env.reset(seed=self.seed)
        self.done = False
        self.step_count = 0
        self.trajectories = [[] for _ in range(self.num_drones)]
        self._events.clear()
        self._event_seq = 0
        self._completed_task_owner.clear()
        self._history.clear()
        # 普通 reset 退出演示剧本；应用预设后会重新 set_demo_context。
        self._demo = {"active": False, "key": None, "name": None, "script": [], "cursor": 0}
        self._emit("system", f"仿真已重置：算法 {algorithm.upper()}，Seed={self.seed}")
        initial = len(getattr(self.env.task_generator, "unassigned_tasks", []) or [])
        if initial:
            self._emit("task_generated", f"初始任务池已生成 {initial} 个任务")
        self._record_history(force=True)
        return self.snapshot()

    def step(self) -> Dict:
        """推进一个仿真步，并把关键状态变化转成可读事件。"""
        if self.done:
            return self.snapshot()

        before_unassigned = {
            str(t.task_id) for t in (getattr(self.env.task_generator, "unassigned_tasks", []) or [])
            if getattr(t, "task_id", None) and not str(t.task_id).startswith("__pad_")
        }
        before_assign = self._assignment_map()
        before_completed = int(getattr(self.env, "total_completed_tasks", 0))
        before_drone_states = self._drone_transition_state()

        if self.algorithm == "greedy":
            from greedy.scheduler import greedy_action_from_observation
            action = greedy_action_from_observation(self.obs)
        else:
            action = self.scheduler.step(self.obs, current_time=self.env.current_time)
        self.obs, _, done, _ = self.env.step(action)
        self.done = bool(done)
        self.step_count += 1
        for i, d in enumerate(self.env.drones):
            self.trajectories[i].append([float(d.x), float(d.y)])

        self._record_transition_events(
            before_unassigned=before_unassigned,
            before_assign=before_assign,
            before_completed=before_completed,
            before_drone_states=before_drone_states,
        )
        if self.done:
            self._emit("system", "本回合仿真已结束")
        self._record_history(force=self.done)
        return self.snapshot()

    def step_many(self, count: int = 1) -> Dict:
        """一次 HTTP 请求推进多个仿真步，供 2x/5x/10x 播放降低请求压力。"""
        count = max(1, min(50, int(count)))
        snap = None
        for _ in range(count):
            snap = self.step()
            if self.done:
                break
        return snap if snap is not None else self.snapshot()

    def inject_task(self, **kwargs) -> Dict:
        """向当前任务池插入任务，并立即刷新 observation（不推进仿真时间）。"""
        task = self.env.inject_task(**kwargs)
        # 调度器下一步应立刻看到新任务，不能沿用注入前的旧 observation。
        self.obs = self.env._obs()
        self._emit(
            "task_injected",
            f"人工加入 {task.task_id}：{task.get_category()} / {task.get_weight():g}kg / "
            f"优先级 {task.get_priority()} / 剩余 {max(0.0, task.get_deadline()-self.env.current_time):.0f}s",
            level="important" if task.get_priority() >= 3 else "info",
            data={"task_id": str(task.task_id)},
        )
        return self.snapshot()

    def set_drone_out_of_service(self, drone_id: str, out_of_service: bool = True, reason: str = "人工故障注入") -> Dict:
        """故障/恢复无人机，并把未完成任务回收到待调度池。"""
        result = self.env.set_drone_out_of_service(
            drone_id, out_of_service=out_of_service, reason=reason)
        self.obs = self.env._obs()
        if result.get("changed"):
            if out_of_service:
                self._emit(
                    "drone_fault",
                    f"{result['drone_id']} 故障停飞：{reason or '人工故障注入'}",
                    level="warning",
                    data={"drone_id": result["drone_id"], "drone_idx": result["drone_idx"]},
                )
                for tid in result.get("requeued_task_ids", []):
                    self._emit(
                        "task_requeued",
                        f"{tid} 因 {result['drone_id']} 停飞回到待调度池，等待重新分配",
                        level="important",
                        data={"task_id": tid, "drone_id": result["drone_id"]},
                    )
            else:
                self._emit(
                    "drone_recovered",
                    f"{result['drone_id']} 已恢复上线，可重新参与调度",
                    level="success",
                    data={"drone_id": result["drone_id"], "drone_idx": result["drone_idx"]},
                )
            self._restart_scheduler_for_runtime_change()
        return self.snapshot()

    def set_nest_closed(self, station_id: str, closed: bool = True, reason: str = "人工场景事件") -> Dict:
        """临时关闭/恢复机巢；关闭时等待与补能改道由 Environment 处理。"""
        result = self.env.set_station_closed(station_id, closed=closed, reason=reason)
        self.obs = self.env._obs()
        if result.get("changed"):
            if closed:
                self._emit(
                    "nest_closed",
                    f"机巢 {result['station_id']} 临时关闭：{reason or '人工场景事件'}",
                    level="warning",
                    data={"nest_id": str(result["station_id"])},
                )
                for did in result.get("rerouted_drone_ids", []):
                    self._emit(
                        "nest_reroute",
                        f"{did} 因机巢 {result['station_id']} 关闭改道至其它可用机巢",
                        level="important",
                        data={"drone_id": did, "nest_id": str(result["station_id"])},
                    )
            else:
                self._emit(
                    "nest_reopened",
                    f"机巢 {result['station_id']} 已重新开放",
                    level="success",
                    data={"nest_id": str(result["station_id"])},
                )
            self._restart_scheduler_for_runtime_change()
        return self.snapshot()

    def _restart_scheduler_for_runtime_change(self):
        """运行时事故后重建调度器内部缓存，但不重置物理仿真状态。

        PSO/GA 的事件驱动调度器会缓存 known_task_ids / drone_queues。故障任务被
        回收到待调度池后，如果沿用旧缓存会被误认为“已经见过”，因此这里仅重启
        调度器对象，并用当前 observation 给它预热忙碌机状态。
        """
        self.scheduler = self._build_scheduler(self.algorithm, self.seed)
        if self.scheduler is None:
            return
        obs = self.obs or self.env._obs()
        free = list(obs.get("drone_is_free", []))
        if hasattr(self.scheduler, "prev_is_free") and len(free) == self.num_drones:
            self.scheduler.prev_is_free = free

        # 预热仍在执行的任务，避免新调度器把忙碌机视作立刻可用。
        if hasattr(self.scheduler, "active_task_ids") and hasattr(self.scheduler, "active_tasks"):
            for idx in range(self.num_drones):
                assigned = getattr(self.env, "drone_assignments", {}).get(idx)
                if not assigned:
                    continue
                items = assigned if isinstance(assigned, list) else [assigned]
                active = []
                for a in items:
                    task = a.get("task") if isinstance(a, dict) else None
                    if task is None:
                        continue
                    active.append({
                        "task_id": str(task.task_id),
                        "source": list(task.get_source()),
                        "destination": list(task.get_destination()),
                        "priority": int(task.get_priority()),
                        "weight": float(task.get_weight()),
                        "volume": float(getattr(task, "volume", 0.0)),
                        "_abs_deadline": float(task.get_deadline()) if task.get_deadline() is not None else float("inf"),
                    })
                if active:
                    self.scheduler.active_task_ids[idx] = active[0]["task_id"]
                    self.scheduler.active_tasks[idx] = active

    def set_task_generation_paused(self, paused: bool = True) -> Dict:
        """暂停/恢复自动任务流，保留当前任务池与运行状态。"""
        result = self.env.set_task_generation_paused(paused)
        self.obs = self.env._obs()
        if result.get("changed"):
            self._emit(
                "task_stream_paused" if paused else "task_stream_resumed",
                "自动任务流已暂停：仅保留当前任务与人工注入任务" if paused else "自动任务流已恢复",
                level="warning" if paused else "success",
            )
        return self.snapshot()

    def update_pending_task(self, task_id: str, **kwargs) -> Dict:
        """调整待调度任务的优先级/时限/重量/类别。"""
        result = self.env.update_pending_task(task_id, **kwargs)
        self.obs = self.env._obs()
        changed = result.get("changed") or {}
        if changed:
            pieces = []
            if "priority" in changed:
                pieces.append(f"优先级 {changed['priority'][0]}→{changed['priority'][1]}")
            if "deadline" in changed:
                remain = max(0.0, float(changed['deadline'][1]) - float(self.env.current_time))
                pieces.append(f"剩余时限→{remain:.0f}s")
            if "weight" in changed:
                pieces.append(f"重量 {changed['weight'][0]:g}→{changed['weight'][1]:g}kg")
            if "category" in changed:
                pieces.append(f"类别 {changed['category'][0]}→{changed['category'][1]}")
            self._emit(
                "task_updated",
                f"{task_id} 已调整：" + "，".join(pieces),
                level="important",
                data={"task_id": str(task_id)},
            )
            # 任务约束变化后重启调度器缓存，但不改物理状态。
            self._restart_scheduler_for_runtime_change()
        return self.snapshot()

    def request_drone_charge(self, drone_id: str, station_id=None) -> Dict:
        """人工调无人机前往机巢换电，仍参与泊位排队与动态仲裁。"""
        result = self.env.request_drone_charge(drone_id, station_id=station_id)
        self.obs = self.env._obs()
        if result.get("changed"):
            suffix = "，换电后恢复原任务链" if result.get("resume_tasks_after_charge") else ""
            self._emit(
                "drone_charge_requested",
                f"{result['drone_id']} 人工调往机巢 {result['station_id']} 补能{suffix}",
                level="important",
                data={"drone_id": result["drone_id"], "nest_id": result["station_id"]},
            )
            # 人工补能会让无人机由可分配状态切换为资源调度状态，刷新事件驱动
            # 调度器缓存，避免下一步仍按旧的 free 状态给它派新任务。
            self._restart_scheduler_for_runtime_change()
        return self.snapshot()

    # ------------------------------------------------------------------
    # 运行态快照 / 检查点
    # ------------------------------------------------------------------

    _CHECKPOINT_STATIC_ENV_KEYS = {"global_bounds", "high_buildings", "no_fly", "data_source",
                                   # 纯派生的查询缓存，最深拷贝一次可达数十 MB 且对恢复无意义：
                                   # 障碍几何由上面几个静态键决定，重建后缓存自然会重新填充。
                                   "_high_buildings_bbox", "_path_clear_cache"}
    _CHECKPOINT_LIMIT = 5

    # 配置没变则指纹不可能变。以前每次 /api/snapshot 都要重开文件 + json.load + md5
    # （实测占快照构建的大头），而 UI 每 350ms 轮询一次。按 (路径, mtime_ns, size) 记忆，
    # 界外手改配置文件同样会让签名变化、缓存自动失效。
    _GEN_CACHE: Dict[tuple, str] = {}

    def _env_generation(self) -> str:
        """环境结构指纹：机队规模、机巢数量与泊位、禁飞区数量、回合上限等。

        这些一变，旧快照里的无人机下标、泊位编号、任务归属就对不上了。旧实现在
        rebuild() 里直接 ``_checkpoints.clear()`` 把用户存的快照一并销毁（误点一次
        「保存并应用」就丢掉答辩前存的「故障注入前」节点，且无法撤销）。改成打标：
        快照保留，跨代恢复时给出可执行的错误提示。
        """
        sig = config_signature()
        cached = self._GEN_CACHE.get(sig)
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
        if len(self._GEN_CACHE) > 32:      # 一键实验会换很多临时配置，别让它无限长
            self._GEN_CACHE.clear()
        self._GEN_CACHE[sig] = digest
        return digest

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        current = self._env_generation()
        rows = []
        for name, item in self._checkpoints.items():
            meta = item.get("meta") or {}
            gen = item.get("env_gen")
            rows.append({
                "name": name, "step": int(meta.get("step", 0)), "time": float(meta.get("time", 0.0)),
                "algorithm": meta.get("algorithm"), "seed": meta.get("seed"),
                # 跨环境重建的快照仍可列出（不销毁用户数据），但不可恢复
                "可用": gen is None or gen == current,
            })
        return rows

    def save_checkpoint(self, name: str = "checkpoint") -> Dict:
        """保存当前完整运行态（内存检查点）。

        为控制内存，不复制 OSM 建筑几何、地图边界和 DataSource；其余 Environment
        动态属性、无人机/机巢/任务、Scheduler 缓存、事件、轨迹和指标历史一起保存。
        """
        name = str(name or "checkpoint").strip()[:40]
        if not name:
            raise ValueError("快照名称不能为空")
        env_dynamic = {k: v for k, v in self.env.__dict__.items() if k not in self._CHECKPOINT_STATIC_ENV_KEYS}
        state = {
            "env_dynamic": env_dynamic,
            "scheduler": self.scheduler,
            "obs": self.obs,
            "done": self.done,
            "step_count": self.step_count,
            "num_drones": self.num_drones,
            "trajectories": self.trajectories,
            "events": list(self._events),
            "event_seq": self._event_seq,
            "completed_task_owner": self._completed_task_owner,
            "history": list(self._history),
            "demo": self._demo,
            "algorithm": self.algorithm,
            "seed": self.seed,
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
            "step": int(self.step_count), "time": float(self.env.current_time),
            "algorithm": self.algorithm, "seed": self.seed,
        }
        # 记录保存时的环境结构，供 rebuild 后判断该快照是否还可安全恢复
        frozen["env_gen"] = self._env_generation()
        # 覆盖同名快照；新名称超过上限时移除最早插入的一项。
        # 这两件事过去都是静默的——实测存第 6 个快照时第一个会无声消失，
        # 而界面只写了一句「当前服务内最多 5 个」。改为如实回报，由前端提示用户。
        replaced = name if name in self._checkpoints else None
        evicted = None
        if replaced is None and len(self._checkpoints) >= self._CHECKPOINT_LIMIT:
            evicted = next(iter(self._checkpoints))
            self._checkpoints.pop(evicted, None)
        self._checkpoints[name] = frozen
        self._emit("checkpoint_saved", f"已保存运行态快照：{name}", level="success")
        return {
            "ok": True,
            "checkpoints": self.list_checkpoints(),
            "snapshot": self.snapshot(),
            "覆盖": replaced,
            "淘汰": evicted,
            "槽位": "%d/%d" % (len(self._checkpoints), self._CHECKPOINT_LIMIT),
        }

    def load_checkpoint(self, name: str) -> Dict:
        name = str(name or "").strip()
        if name not in self._checkpoints:
            raise ValueError(f"运行态快照不存在: {name}")
        try:
            state = copy.deepcopy(self._checkpoints[name])
        except Exception as exc:
            raise ValueError(f"运行态快照无法恢复: {exc}") from exc
        gen = state.get("env_gen")
        if gen is not None and gen != self._env_generation():
            raise ValueError(
                f"快照「{name}」保存于另一次环境重建之前（机队规模、机巢数量与泊位、"
                "禁飞区数量或回合上限已改变），跨代恢复会让无人机下标与泊位编号错位，"
                "已拒绝。请在当前配置下重新保存一个快照。"
            )
        # 保留当前静态地图对象，只覆盖保存时的动态环境状态。
        current_static = {k: self.env.__dict__.get(k) for k in self._CHECKPOINT_STATIC_ENV_KEYS}
        for key in list(self.env.__dict__):
            if key not in self._CHECKPOINT_STATIC_ENV_KEYS and key not in state["env_dynamic"]:
                self.env.__dict__.pop(key, None)
        self.env.__dict__.update(state["env_dynamic"])
        for key, value in current_static.items():
            if value is not None:
                self.env.__dict__[key] = value

        self.scheduler = state["scheduler"]
        self.obs = state["obs"]
        self.done = bool(state["done"])
        self.step_count = int(state["step_count"])
        self.num_drones = int(state["num_drones"])
        self.trajectories = state["trajectories"]
        self._events = deque(state["events"], maxlen=300)
        self._event_seq = int(state["event_seq"])
        self._completed_task_owner = state["completed_task_owner"]
        self._history = deque(state["history"], maxlen=360)
        self._demo = state["demo"]
        self.algorithm = state["algorithm"]
        self.seed = int(state["seed"])
        # 最后恢复进程级 RNG，保证 TaskGenerator / Greedy / PSO 从该节点继续时
        # 复用保存时的下一段随机序列，而不是沿用恢复前的随机状态。
        if state.get("python_random_state") is not None:
            random.setstate(state["python_random_state"])
        if state.get("numpy_random_state") is not None:
            np.random.set_state(state["numpy_random_state"])
        seed_mod = sys.modules.get("seed_interface")
        if seed_mod is not None and hasattr(seed_mod, "CURRENT_SEED"):
            seed_mod.CURRENT_SEED = self.seed
        self._emit("checkpoint_loaded", f"已恢复运行态快照：{name}", level="important")
        snap = self.snapshot()
        # 仅恢复检查点时携带历史轨迹，避免每个 step 响应都重复发送大量坐标。
        snap["trajectories_restore"] = copy.deepcopy(self.trajectories)
        return snap

    def delete_checkpoint(self, name: str) -> Dict:
        name = str(name or "").strip()
        if name not in self._checkpoints:
            raise ValueError(f"运行态快照不存在: {name}")
        self._checkpoints.pop(name, None)
        return {"ok": True, "checkpoints": self.list_checkpoints()}

    # ------------------------------------------------------------------
    # 可复现演示剧本
    # ------------------------------------------------------------------

    def set_demo_context(self, key: str, name: str, script: List[Dict[str, Any]]) -> Dict:
        """绑定演示剧本。剧本动作只是调用现有控制接口，不绕过调度器。"""
        self._demo = {
            "active": True,
            "key": str(key),
            "name": str(name),
            "script": [dict(x) for x in (script or [])],
            "cursor": 0,
        }
        self._emit("demo_loaded", f"已加载演示场景：{name}", level="important", data={"demo_key": str(key)})
        return self.snapshot()

    def clear_demo_context(self) -> None:
        self._demo = {"active": False, "key": None, "name": None, "script": [], "cursor": 0}

    def advance_demo(self) -> Dict:
        """执行演示剧本的“下一幕”。

        动作均复用公开的 step / inject / incident / charge 控制接口，因此不会出现
        “答辩演示是一套假逻辑、真实仿真又是另一套逻辑”的问题。
        """
        if not self._demo.get("active"):
            raise ValueError("当前没有活动演示场景")
        script = self._demo.get("script") or []
        cursor = int(self._demo.get("cursor", 0))
        if cursor >= len(script):
            self._emit("demo_complete", f"演示剧本《{self._demo.get('name') or ''}》已完成", level="success")
            return self.snapshot()

        item = dict(script[cursor])
        action = str(item.get("action") or "").strip()
        label = str(item.get("label") or action or f"步骤 {cursor+1}")
        self._emit("demo_action", f"演示第 {cursor+1} 幕：{label}", level="important", data={"demo_key": self._demo.get("key")})

        if action == "step":
            self.step_many(int(item.get("count", 1)))
        elif action == "inject_task":
            payload = dict(item.get("task") or {})
            self.inject_task(**payload)
        elif action == "fault_busy_drone":
            online = [(i, d) for i, d in enumerate(self.env.drones) if not getattr(d, "out_of_service", False)]
            if not online:
                raise ValueError("当前没有可故障注入的在线无人机")
            busy = [(i, d) for i, d in online if _drone_state(d) == "busy"]
            i, d = (busy or online)[0]
            self.set_drone_out_of_service(str(getattr(d, "drone_id", f"drone_{i}")), True, "演示剧本：模拟动力/通信故障")
        elif action == "close_busy_nest":
            open_rows = [r for r in self._nests_snapshot() if not r.get("closed")]
            if len(open_rows) <= 1:
                raise ValueError("至少需要两个开放机巢才能执行关闭演示")
            open_rows.sort(key=lambda r: (-(r.get("queue_length") or 0), -(r.get("occupied") or 0), str(r.get("id"))))
            self.set_nest_closed(str(open_rows[0]["id"]), True, "演示剧本：模拟机巢维护/资源故障")
        elif action == "charge_two_drones":
            candidates = [d for d in self.env.drones if not getattr(d, "out_of_service", False)
                          and not getattr(d, "is_charging", False) and not getattr(d, "awaiting_berth", False)
                          and not getattr(d, "_manual_charge_requested", False)]
            candidates.sort(key=lambda d: (0 if _drone_state(d) == "busy" else 1, str(getattr(d, "drone_id", ""))))
            if not candidates:
                raise ValueError("当前没有可调往机巢补能的无人机")
            for d in candidates[:2]:
                self.request_drone_charge(str(d.drone_id))
        elif action == "restore_incidents":
            # 恢复无人机。先恢复机巢，保证无人机恢复后总有可用地面资源。
            for st in list(self.env.charging_stations):
                if getattr(st, "closed", False):
                    self.set_nest_closed(str(st.station_id), False, "演示剧本：恢复开放")
            for d in list(self.env.drones):
                if getattr(d, "out_of_service", False):
                    self.set_drone_out_of_service(str(d.drone_id), False, "演示剧本：恢复上线")
        elif action == "pause_stream":
            self.set_task_generation_paused(bool(item.get("paused", True)))
        else:
            raise ValueError(f"未知演示动作: {action}")

        self._demo["cursor"] = cursor + 1
        if self._demo["cursor"] >= len(script):
            self._emit("demo_complete", f"演示剧本《{self._demo.get('name') or ''}》已完成", level="success")
        return self.snapshot()

    def rebuild(self) -> Dict:
        """热重载配置并重建 Environment（写回 simulation.json 后调用）。"""
        reload_sim_modules()
        # episode_max_steps 属于可编辑场景配置。旧实现仅在 SimSession 创建时读取一次，
        # 导致 Web 修改“回合步数上限”后 rebuild 实际仍沿用旧值；这里每次重建都刷新。
        self.episode_max_steps = get_episode_max_steps(config=get_shared_config())
        # reload 后 _env_module.Environment 已是最新类
        self.env = _env_module.Environment(
            self.osm_path, episode_max_steps=self.episode_max_steps)
        self.num_drones = len(self.env.drones)
        self.trajectories = [[] for _ in range(self.num_drones)]
        # 配置结构可能变化（机队/机巢/禁飞区），旧快照不再可安全恢复——但**不再销毁**：
        # 每个快照带环境代次标记，跨代恢复由 load_checkpoint 明确拒绝并解释原因。
        # 旧实现此处 clear() 会让误点一次「保存并应用」就丢掉答辩前存的全部节点且不可撤销。
        return self.reset(self.algorithm, self.seed)

    # ------------------------------------------------------------------
    # 快照
    # ------------------------------------------------------------------

    def snapshot(self) -> Dict:
        return {
            "algorithm": self.algorithm,
            "seed": self.seed,
            "step": self.step_count,
            "time": float(self.env.current_time),
            "done": self.done,
            "num_drones": self.num_drones,
            "map": self._map_snapshot(),
            "drones": self._drones_snapshot(),
            "nests": self._nests_snapshot(),
            "tasks": self._tasks_snapshot(),
            "task_catalog": self._task_catalog_snapshot(),
            "pending_count": len(getattr(self.env.task_generator, "unassigned_tasks", []) or []),
            "controls": {
                "task_generation_paused": bool(getattr(self.env, "task_generation_paused", False)),
            },
            "events": list(self._events)[-80:],
            "stats": self._stats_snapshot(),
            "history": list(self._history),
            "health": self._health_snapshot(),
            "demo": self._demo_snapshot(),
            "checkpoints": self.list_checkpoints(),
        }

    def map_static(self) -> Dict:
        """静态地图几何（一次性）：边界 + 建筑轮廓(含高度)。"""
        # 静态几何在同一个 Environment 生命周期内不会变。以前每次调用都从两千多栋建筑
        # 重建全部环（实测 p50 106ms、响应体 885KB），而前端在 mount、场景应用、
        # rebuild、布局保存各处都会重拉一次，且都持着 _op_lock。
        cached = getattr(self, "_map_static_cache", None)
        if cached is not None and getattr(self, "_map_static_src", None) is self.env:
            return cached
        bounds = getattr(self.env, "global_bounds", None)
        if not bounds:
            xs = [d.x for d in self.env.drones] + [s.x for s in self.env.charging_stations]
            ys = [d.y for d in self.env.drones] + [s.y for s in self.env.charging_stations]
            bounds = (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 1000, 1000)
        # 全量建筑（含无高度标注者按默认层高 12m 处理），形成真实城市肌理
        src = getattr(self.env, "all_buildings", None) or getattr(self.env, "high_buildings", []) or []
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
        for rtype, geoms in (getattr(self.env, "roads_by_type", {}) or {}).items():
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
            "no_fly_zones": self._no_fly_snapshot(),
        }
        self._map_static_cache = result
        self._map_static_src = self.env
        return result

    def _no_fly_snapshot(self) -> List[Dict]:
        """禁飞区轮廓（申请书「可灵活配置禁飞区」的可视化）。"""
        nf = getattr(self.env, "no_fly", None)
        if not nf:
            return []
        out = []
        for z in nf.zones:
            rings = _polygon_rings(z.geometry)
            for ring in rings:
                if len(ring) >= 3:
                    out.append({"name": z.name, "coords": ring})
        return out

    def _map_snapshot(self) -> Dict:
        bounds = getattr(self.env, "global_bounds", None)
        if not bounds:
            xs = [d.x for d in self.env.drones] + [s.x for s in self.env.charging_stations]
            ys = [d.y for d in self.env.drones] + [s.y for s in self.env.charging_stations]
            bounds = (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 1000, 1000)
        return {"bounds": [float(v) for v in bounds]}

    def _drones_snapshot(self) -> List[Dict]:
        out = []
        for i, d in enumerate(self.env.drones):
            cap = float(getattr(d, "battery_capacity", 1.0)) or 1.0
            chain = self._assigned_task_list(i)
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

    def _nests_snapshot(self) -> List[Dict]:
        rows = []
        for s in self.env.charging_stations:
            waiting = list(getattr(self.env, "_nest_waiting", {}).get(s.station_id, []) or [])
            if getattr(self.env, "arbitration_policy", "priority") == "fifo":
                waiting.sort(key=lambda i: (
                    getattr(self.env.drones[i], "awaiting_since", None)
                    if getattr(self.env.drones[i], "awaiting_since", None) is not None else float("inf")
                ))
            else:
                waiting.sort(key=lambda i: self.env._drone_berth_score(i), reverse=True)
            queue = []
            for rank, idx in enumerate(waiting, start=1):
                d = self.env.drones[idx]
                since = getattr(d, "awaiting_since", None)
                queue.append({
                    "rank": rank,
                    "drone_idx": idx,
                    "drone_id": str(getattr(d, "drone_id", f"drone_{idx}")),
                    "battery_ratio": round(float(d.current_battery) / max(1e-9, float(d.battery_capacity)), 4),
                    "wait_seconds": round(max(0.0, float(self.env.current_time) - float(since)), 1) if since is not None else 0.0,
                    "priority_score": round(float(self.env._drone_berth_score(idx)), 4),
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
                "arbitration": str(getattr(self.env, "arbitration_policy", "priority")),
                "closed": bool(getattr(s, "closed", False)),
                "closed_reason": getattr(s, "closed_reason", None),
            })
        return rows

    def _tasks_snapshot(self, limit: int = 60) -> List[Dict]:
        tasks = []
        unassigned = getattr(self.env, "unassigned_tasks", []) or []
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
                "remaining_time": round(max(0.0, float(getattr(t, "deadline", self.env.current_time) or self.env.current_time) - float(self.env.current_time)), 1),
                "status": str(getattr(t, "status", "pending") or "pending"),
                "manual": tid.startswith("manual_"),
            })
            if len(tasks) >= limit:
                break
        return tasks

    def _task_base_dict(self, task: Any) -> Dict:
        """把 Task 转为控制台稳定字段，避免前端依赖 Python 对象细节。"""
        deadline = getattr(task, "deadline", None)
        generation_time = getattr(task, "generation_time", None)
        remaining = None if deadline is None else float(deadline) - float(self.env.current_time)
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

    def _task_catalog_snapshot(self, completed_limit: int = 24) -> List[Dict]:
        """任务生命周期视图：待分配 + 已分配/执行中 + 最近完成。

        `tasks` 字段仍保持“待分配任务”兼容语义；这个 catalog 专供可点击任务详情。
        """
        rows: Dict[str, Dict] = {}
        for task in (getattr(self.env.task_generator, "unassigned_tasks", []) or []):
            tid = str(getattr(task, "task_id", ""))
            if not tid or tid.startswith("__pad_"):
                continue
            row = self._task_base_dict(task)
            row.update({"status": "pending", "assigned_drone_id": None, "assigned_drone_idx": None, "chain_order": None, "loaded": False})
            rows[tid] = row

        for drone_idx in range(len(self.env.drones)):
            d = self.env.drones[drone_idx]
            assigned = getattr(self.env, "drone_assignments", {}).get(drone_idx)
            if not assigned:
                continue
            items = assigned if isinstance(assigned, list) else [assigned]
            for order, a in enumerate(items, start=1):
                if not isinstance(a, dict) or a.get("task") is None:
                    continue
                task = a["task"]
                tid = str(task.task_id)
                row = self._task_base_dict(task)
                executing = str(getattr(d, "executing_task_id", "") or "") == tid
                row.update({
                    "status": "in_progress" if executing else "assigned",
                    "assigned_drone_id": str(getattr(d, "drone_id", f"drone_{drone_idx}")),
                    "assigned_drone_idx": drone_idx,
                    "chain_order": order,
                    "loaded": a.get("load_time") is not None,
                    "assigned_time": float(a.get("assigned_time", a.get("start_time", self.env.current_time))),
                    "load_time": float(a["load_time"]) if a.get("load_time") is not None else None,
                })
                rows[tid] = row

        completed = list(getattr(self.env, "completed_task_log", []) or [])[-completed_limit:]
        for item in completed:
            task = item.get("task") if isinstance(item, dict) else None
            if task is None:
                continue
            tid = str(task.task_id)
            row = self._task_base_dict(task)
            owner = self._completed_task_owner.get(tid, {})
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

    def _find_active_task(self, task_id: str):
        task_id = str(task_id)
        for task in (getattr(self.env.task_generator, "unassigned_tasks", []) or []):
            if str(getattr(task, "task_id", "")) == task_id:
                return task, "pending", None
        for drone_idx, assigned in (getattr(self.env, "drone_assignments", {}) or {}).items():
            items = assigned if isinstance(assigned, list) else [assigned]
            for a in items:
                if not isinstance(a, dict) or a.get("task") is None:
                    continue
                if str(a["task"].task_id) == task_id:
                    return a["task"], "assigned", int(drone_idx)
        return None, None, None

    def task_candidates(self, task_id: str, limit: int = 5) -> Dict:
        """给待分配任务生成“可解释候选机”近似评分，供答辩观察。

        这是解释层，不替代各算法真实决策：距离/ETA 使用当前平面距离和剩余航线近似，
        最终调度仍由 Greedy/GA/PSO/OR-Tools 自身约束与目标函数决定。
        """
        task, status, assigned_idx = self._find_active_task(task_id)
        if task is None:
            # 已完成任务不再做候选重算。
            return {"task_id": str(task_id), "status": "completed_or_missing", "candidates": [], "note": "任务已完成或已不在活动任务池中。"}
        if status != "pending":
            d = self.env.drones[assigned_idx]
            return {
                "task_id": str(task_id), "status": "assigned",
                "candidates": [{"drone_idx": assigned_idx, "drone_id": str(getattr(d, "drone_id", f"drone_{assigned_idx}")), "selected": True}],
                "note": "任务已经进入任务链；此处显示当前执行无人机，不再重新排名。",
            }

        from backend_si.matching import VOLUME_TO_LOAD_FACTOR, compute_match

        source = (float(task.source[0]), float(task.source[1]))
        destination = (float(task.destination[0]), float(task.destination[1]))
        task_leg = math.dist(source, destination)
        required_load = float(task.get_weight()) + VOLUME_TO_LOAD_FACTOR * float(getattr(task, "volume", 0.0))
        remaining_time = None if task.get_deadline() is None else float(task.get_deadline()) - float(self.env.current_time)
        candidates = []
        for idx, d in enumerate(self.env.drones):
            current = (float(d.x), float(d.y))
            queue_distance = 0.0
            prev = current
            for wp in (getattr(d, "scheduled_position", []) or []):
                p = (float(wp[0]), float(wp[1]))
                queue_distance += math.dist(prev, p)
                prev = p
            approach_from = prev if queue_distance > 0 else current
            approach = math.dist(approach_from, source)
            total_distance = queue_distance + approach + task_leg
            speed = max(1e-9, float(getattr(d, "speed", 0.0)))
            eta = total_distance / speed
            remaining_capacity = max(0.0, float(getattr(d, "carrying_capacity", 0.0)) - float(getattr(d, "current_load", 0.0)))
            battery = float(getattr(d, "current_battery", 0.0))
            battery_capacity = max(1e-9, float(getattr(d, "battery_capacity", 0.0)))
            consumption_base = max(1e-9, float(getattr(d, "battery_consumption_base", 0.0)))
            load_penalty = float(getattr(d, "battery_load_penalty_factor", 0.0))
            load_ratio = min(1.0, required_load / max(1e-9, float(getattr(d, "carrying_capacity", 0.0))))
            est_energy = total_distance * consumption_base * (1.0 + load_ratio * load_penalty)
            payload_ok = remaining_capacity + 1e-9 >= required_load
            energy_ok = battery + 1e-9 >= est_energy
            time_ok = remaining_time is None or eta <= max(0.0, remaining_time)
            score = compute_match(
                required_load=required_load, remaining_capacity=max(1e-9, remaining_capacity),
                speed=speed, remaining_time=remaining_time, battery_capacity=battery_capacity,
                consumption_base=consumption_base, total_distance=total_distance,
            )
            blockers = []
            operational = not bool(getattr(d, "out_of_service", False))
            if not operational:
                blockers.append("故障停飞")
            if not payload_ok:
                blockers.append("载重不足")
            if not energy_ok:
                blockers.append("电量不足")
            if not time_ok:
                blockers.append("预计超时")
            if getattr(d, "is_charging", False):
                blockers.append("换电中")
            elif getattr(d, "awaiting_berth", False):
                blockers.append("等待泊位")
            candidates.append({
                "drone_idx": idx,
                "drone_id": str(getattr(d, "drone_id", f"drone_{idx}")),
                "drone_type": str(getattr(d, "drone_type", "") or "homogeneous"),
                "state": _drone_state(d),
                "match_score": round(float(score), 4),
                "feasible": operational and payload_ok and energy_ok,
                "payload_ok": payload_ok,
                "energy_ok": energy_ok,
                "time_ok": time_ok,
                "eta_seconds": round(float(eta), 1),
                "estimated_distance_m": round(float(total_distance), 1),
                "estimated_energy": round(float(est_energy), 1),
                "battery_ratio": round(battery / battery_capacity, 4),
                "remaining_capacity": round(remaining_capacity, 2),
                "blockers": blockers,
            })
        candidates.sort(key=lambda r: (not r["feasible"], not r["time_ok"], -r["match_score"], r["eta_seconds"]))
        return {
            "task_id": str(task_id),
            "status": "pending",
            "remaining_time": round(float(remaining_time), 1) if remaining_time is not None else None,
            "candidates": candidates[:max(1, min(20, int(limit)))],
            "note": "候选机为控制台解释层的近似评估：能力匹配 + 当前剩余航线 + 平面距离/ETA；最终分配以所选调度算法真实决策为准。",
        }

    # ------------------------------------------------------------------
    # 事件 / 调度决策可视化辅助
    # ------------------------------------------------------------------

    def _emit(self, kind: str, message: str, level: str = "info", data: Optional[Dict] = None):
        self._event_seq += 1
        self._events.append({
            "seq": self._event_seq,
            "step": int(self.step_count),
            "time": float(getattr(self.env, "current_time", 0.0)),
            "kind": kind,
            "level": level,
            "message": message,
            "data": data or {},
        })

    def _assigned_task_list(self, drone_idx: int) -> List[Dict]:
        assigned = getattr(self.env, "drone_assignments", {}).get(drone_idx)
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
                "remaining_time": round(float(deadline) - float(self.env.current_time), 1) if deadline is not None else None,
                "loaded": a.get("load_time") is not None,
            })
        return out

    def _assignment_map(self) -> Dict[str, Dict]:
        out = {}
        for i in range(len(self.env.drones)):
            for task in self._assigned_task_list(i):
                out[task["task_id"]] = {
                    "drone_idx": i,
                    "drone_id": str(getattr(self.env.drones[i], "drone_id", f"drone_{i}")),
                    "task": task,
                }
        return out

    def _drone_transition_state(self) -> Dict[int, Dict]:
        out = {}
        for i, d in enumerate(self.env.drones):
            out[i] = {
                "waiting": bool(getattr(d, "awaiting_berth", False)),
                "charging": bool(getattr(d, "is_charging", False)),
                "station": getattr(d, "charging_station_id", None) if getattr(d, "is_charging", False)
                           else getattr(d, "berth_station_id", None),
            }
        return out

    def _record_transition_events(self, *, before_unassigned, before_assign,
                                  before_completed, before_drone_states):
        after_unassigned = {
            str(t.task_id) for t in (getattr(self.env.task_generator, "unassigned_tasks", []) or [])
            if getattr(t, "task_id", None) and not str(t.task_id).startswith("__pad_")
        }
        after_assign = self._assignment_map()

        # 自动订单到达（人工注入在 inject_task() 中单独记录）
        for tid in sorted(after_unassigned - before_unassigned):
            if tid not in before_assign:
                self._emit("task_generated", f"新任务 {tid} 到达待调度池", data={"task_id": tid})

        # 新分配 / 任务链插入。按每架无人机的链内顺序判断第一单与后续插单，
        # 避免同一步一次分到多单时把“第一单”误写成链式插入。
        before_count_by_drone = {}
        for old in before_assign.values():
            before_count_by_drone[old["drone_idx"]] = before_count_by_drone.get(old["drone_idx"], 0) + 1
        for drone_idx in range(len(self.env.drones)):
            chain = self._assigned_task_list(drone_idx)
            new_chain_items = [t for t in chain if t["task_id"] not in before_assign]
            if not new_chain_items:
                continue
            prior = before_count_by_drone.get(drone_idx, 0)
            drone_id = str(getattr(self.env.drones[drone_idx], "drone_id", f"drone_{drone_idx}"))
            for j, task in enumerate(new_chain_items):
                is_insert = (prior + j) > 0
                kind = "chain_insert" if is_insert else "task_assigned"
                suffix = f"（任务链位置 {prior+j+1}/{len(chain)}）" if is_insert else ""
                self._emit(kind, f"{task['task_id']} → {drone_id} {suffix}",
                           level="important" if task["priority"] >= 3 else "info",
                           data={"task_id": task["task_id"], "drone_id": drone_id, "drone_idx": drone_idx})

        # 完成：用累计完成数确认“从任务链消失”确实对应送达，不把其它状态迁移误报为完成。
        completed_delta = int(getattr(self.env, "total_completed_tasks", 0)) - int(before_completed)
        disappeared = [tid for tid in before_assign if tid not in after_assign and tid not in after_unassigned]
        for tid in disappeared[:max(0, completed_delta)]:
            old = before_assign[tid]
            self._completed_task_owner[tid] = {"drone_id": old["drone_id"], "drone_idx": old["drone_idx"]}
            self._emit("task_completed", f"{old['drone_id']} 已完成 {tid}", level="success",
                       data={"task_id": tid, "drone_id": old["drone_id"], "drone_idx": old["drone_idx"]})

        # 机巢资源竞争状态变化
        after_states = self._drone_transition_state()
        for i, after in after_states.items():
            before = before_drone_states.get(i, {})
            d = self.env.drones[i]
            did = str(getattr(d, "drone_id", f"drone_{i}"))
            if after["waiting"] and not before.get("waiting"):
                sid = after.get("station")
                score = float(self.env._drone_berth_score(i))
                self._emit("berth_wait", f"{did} 在机巢 {sid} 等待泊位（动态优先级 {score:.3f}）", level="warning",
                           data={"drone_id": did, "drone_idx": i, "nest_id": str(sid)})
            if after["charging"] and not before.get("charging"):
                sid = after.get("station")
                self._emit("berth_granted", f"机巢 {sid} 向 {did} 分配泊位，开始换电", level="success",
                           data={"drone_id": did, "drone_idx": i, "nest_id": str(sid)})
            if before.get("charging") and not after["charging"]:
                self._emit("swap_completed", f"{did} 换电完成，恢复调度", level="success",
                           data={"drone_id": did, "drone_idx": i})

    def _record_history(self, force: bool = False) -> None:
        """每 5 步记录一次关键指标；趋势由服务端持有，浏览器刷新后也能继续。"""
        if not force and self.step_count % 5 != 0:
            return
        stats = self._stats_snapshot()
        pending = len(getattr(self.env.task_generator, "unassigned_tasks", []) or [])
        self._history.append({
            "step": int(self.step_count),
            "time": round(float(self.env.current_time), 1),
            "completion_rate": round(float(stats.get("completion_rate", 0.0)), 6),
            "timeout_rate": round(float(stats.get("timeout_rate", 0.0)), 6),
            "utilization": round(float(stats.get("utilization", 0.0)), 6),
            "berth_utilization": round(float(stats.get("berth_utilization", 0.0)), 6),
            "pending": int(pending),
            "queue": int(sum(len(q) for q in getattr(self.env, "_nest_waiting", {}).values())),
        })

    def _health_snapshot(self) -> Dict:
        pending = list(getattr(self.env.task_generator, "unassigned_tasks", []) or [])
        urgent = sum(1 for t in pending if int(getattr(t, "priority", 1)) >= 3)
        drones = list(self.env.drones)
        offline = sum(1 for d in drones if getattr(d, "out_of_service", False))
        _low_thr = getattr(sys.modules.get("drone"), "BATTERY_LOW_THRESHOLD", 0.2)
        critical_battery = sum(1 for d in drones if not getattr(d, "out_of_service", False)
                               and not getattr(d, "is_charging", False)
                               and float(getattr(d, "current_battery", 0.0)) / max(1e-9, float(getattr(d, "battery_capacity", 1.0))) < _low_thr)
        nests = list(self.env.charging_stations)
        closed = sum(1 for s in nests if getattr(s, "closed", False))
        queue = sum(len(q) for q in getattr(self.env, "_nest_waiting", {}).values())
        # 侧栏「禁飞区」要的是**区域个数**；_no_fly_snapshot 返回的是多边形环，一块区域可能有多个
        # 环，拿它的长度计数会把 3 块报成 5 个。
        no_fly = len(getattr(getattr(self.env, "no_fly", None), "zones", None) or [])
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

    def _demo_snapshot(self) -> Dict:
        d = self._demo or {}
        script = d.get("script") or []
        cursor = int(d.get("cursor", 0))
        next_item = script[cursor] if cursor < len(script) else None
        return {
            "active": bool(d.get("active")), "key": d.get("key"), "name": d.get("name"),
            "cursor": cursor, "total": len(script),
            "next": dict(next_item) if next_item else None,
            "completed": bool(d.get("active")) and cursor >= len(script),
        }

    def _stats_snapshot(self) -> Dict:
        s = self.env.get_statistics()
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

    # ------------------------------------------------------------------
    # 调度器构造
    # ------------------------------------------------------------------

    def _build_scheduler(self, algorithm: str, seed: int):
        if algorithm == "greedy":
            return None
        if algorithm == "pso":
            from backend_si.pso_scheduler import PSOScheduler
            return PSOScheduler(num_drones=self.num_drones, verbose=False, seed=seed)
        if algorithm == "ga":
            from backend_si.ga_scheduler import GAScheduler
            return GAScheduler(num_drones=self.num_drones, verbose=False, seed=seed)
        if algorithm == "ortools":
            from backend_si.ortools_scheduler import ORToolsScheduler, ORTOOLS_AVAILABLE
            if not ORTOOLS_AVAILABLE:
                raise RuntimeError("OR-Tools 未安装：pip install ortools")
            return ORToolsScheduler(num_drones=self.num_drones, verbose=False, seed=seed)
        raise ValueError(f"未知算法: {algorithm}")
