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

import importlib
import math
import sys
from collections import deque
from typing import Any, Dict, List, Optional

from swarmbalance.application import checkpoints as _checkpoints
from swarmbalance.application import snapshots as _snapshots
from swarmbalance.application import events as _events
from swarmbalance.application import scenarios as _scenarios
from swarmbalance.application.snapshots import _drone_state

# 定位项目根与 frontend 目录，确保 environment / config / backend_si 可导入
from swarmbalance.paths import PROJECT_ROOT as _PROJECT_ROOT
_FRONTEND = _PROJECT_ROOT


from swarmbalance.paths import DEFAULT_MAP
from swarmbalance.scheduling.registry import ALGORITHM_KEYS, create_scheduler
ALGORITHMS = list(ALGORITHM_KEYS)

# 顶层只 import 模块（不 from import 值），便于 rebuild 时刷新到 reload 后的新类
import swarmbalance.simulation.environment as _env_module  # noqa: E402
from swarmbalance.infrastructure.config.loader import get_episode_max_steps, get_shared_config


def reload_sim_modules():
    """按依赖序 reload 在顶层固化 simulation.json 配置的模块。

    `config.loader.get_shared_config()` 每次调用都重读文件（无缓存），
    但 drone/task/charging_station/environment 四模块在**模块顶层**把配置算成了
    模块级常量。改配置后必须按依赖序 reload 它们（以及顶层 from-import 了这些
    类引用的 data_source / tools.osm），才能让新配置真正生效。
    """
    mods = ['swarmbalance.simulation.entities.charging_station', 'swarmbalance.simulation.entities.drone', 'swarmbalance.simulation.routing.no_fly_zone', 'swarmbalance.simulation.entities.task', 'swarmbalance.contracts.data_source', 'swarmbalance.infrastructure.data_sources.common', 'swarmbalance.infrastructure.data_sources.random', 'swarmbalance.infrastructure.data_sources.csv', 'swarmbalance.infrastructure.data_sources.geojson', 'swarmbalance.infrastructure.data_sources.enterprise', 'swarmbalance.infrastructure.data_sources.factory', 'swarmbalance.infrastructure.maps.osm', 'swarmbalance.scheduling.greedy', 'swarmbalance.simulation.environment']
    for name in mods:
        if name in sys.modules:
            try:
                importlib.reload(sys.modules[name])
            except Exception:
                # reload 失败不应阻断：最坏退回旧模块，仍可继续
                continue






class SimSession:
    """单个仿真会话。一个进程里通常只持有一个实例。"""

    def __init__(self,
                 osm_path: Optional[str] = None,
                 episode_max_steps: Optional[int] = None):
        self.osm_path = osm_path or str(DEFAULT_MAP)
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

        action = self.scheduler.act(self.obs, current_time=self.env.current_time)
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
        active_tasks = {}
        for idx in range(self.num_drones):
            assigned = getattr(self.env, "drone_assignments", {}).get(idx)
            if not assigned:
                continue
            items = assigned if isinstance(assigned, list) else [assigned]
            active = []
            for assignment in items:
                task = assignment.get("task") if isinstance(assignment, dict) else None
                if task is None:
                    continue
                active.append({
                    "task_id": str(task.task_id), "source": list(task.get_source()),
                    "destination": list(task.get_destination()), "priority": int(task.get_priority()),
                    "weight": float(task.get_weight()), "volume": float(getattr(task, "volume", 0.0)),
                    "_abs_deadline": float(task.get_deadline()) if task.get_deadline() is not None else float("inf"),
                })
            if active:
                active_tasks[idx] = active
        self.scheduler.synchronize(obs, active_tasks)

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
        return _checkpoints._env_generation(self)

    def list_checkpoints(self) -> List[Dict[str, Any]]:
        return _checkpoints.list_checkpoints(self)

    def save_checkpoint(self, name: str='checkpoint') -> Dict:
        return _checkpoints.save_checkpoint(self, name)

    def load_checkpoint(self, name: str) -> Dict:
        return _checkpoints.load_checkpoint(self, name)

    def delete_checkpoint(self, name: str) -> Dict:
        return _checkpoints.delete_checkpoint(self, name)

    # ------------------------------------------------------------------
    # 可复现演示剧本
    # ------------------------------------------------------------------

    def set_demo_context(self, key: str, name: str, script: List[Dict[str, Any]]) -> Dict:
        return _scenarios.set_demo_context(self, key, name, script)

    def clear_demo_context(self) -> None:
        return _scenarios.clear_demo_context(self)

    def advance_demo(self) -> Dict:
        return _scenarios.advance_demo(self)

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
        return _snapshots.snapshot(self)

    def map_static(self) -> Dict:
        return _snapshots.map_static(self)

    def _no_fly_snapshot(self) -> List[Dict]:
        return _snapshots._no_fly_snapshot(self)

    def _map_snapshot(self) -> Dict:
        return _snapshots._map_snapshot(self)

    def _drones_snapshot(self) -> List[Dict]:
        return _snapshots._drones_snapshot(self)

    def _nests_snapshot(self) -> List[Dict]:
        return _snapshots._nests_snapshot(self)

    def _tasks_snapshot(self, limit: int=60) -> List[Dict]:
        return _snapshots._tasks_snapshot(self, limit)

    def _task_base_dict(self, task: Any) -> Dict:
        return _snapshots._task_base_dict(self, task)

    def _task_catalog_snapshot(self, completed_limit: int=24) -> List[Dict]:
        return _snapshots._task_catalog_snapshot(self, completed_limit)

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

        from swarmbalance.scheduling.matching import VOLUME_TO_LOAD_FACTOR, compute_match

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

    def _emit(self, kind: str, message: str, level: str='info', data: Optional[Dict]=None):
        return _events._emit(self, kind, message, level, data)

    def _assigned_task_list(self, drone_idx: int) -> List[Dict]:
        return _events._assigned_task_list(self, drone_idx)

    def _assignment_map(self) -> Dict[str, Dict]:
        return _events._assignment_map(self)

    def _drone_transition_state(self) -> Dict[int, Dict]:
        return _events._drone_transition_state(self)

    def _record_transition_events(self, *, before_unassigned, before_assign, before_completed, before_drone_states):
        return _events._record_transition_events(self, before_unassigned=before_unassigned, before_assign=before_assign, before_completed=before_completed, before_drone_states=before_drone_states)

    def _record_history(self, force: bool=False) -> None:
        return _events._record_history(self, force)

    def _health_snapshot(self) -> Dict:
        return _snapshots._health_snapshot(self)

    def _demo_snapshot(self) -> Dict:
        return _snapshots._demo_snapshot(self)

    def _stats_snapshot(self) -> Dict:
        return _snapshots._stats_snapshot(self)

    # ------------------------------------------------------------------
    # 调度器构造
    # ------------------------------------------------------------------

    def _build_scheduler(self, algorithm: str, seed: int):
        return create_scheduler(algorithm, num_drones=self.num_drones, seed=seed)
