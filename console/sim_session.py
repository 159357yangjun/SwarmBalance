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
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 定位项目根与 frontend 目录，确保 environment / config / backend_si 可导入
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_FRONTEND = _PROJECT_ROOT / "frontend"

for _p in (str(_PROJECT_ROOT), str(_FRONTEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

ALGORITHMS = ["greedy", "pso", "ga", "ortools"]

# 顶层只 import 模块（不 from import 值），便于 rebuild 时刷新到 reload 后的新类
import environment as _env_module  # noqa: E402


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
    if getattr(d, "is_charging", False) or getattr(d, "swap_remaining_steps", 0) > 0:
        return "charging"
    if getattr(d, "awaiting_berth", False):
        return "waiting_berth"
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
                 episode_max_steps: int = 2000):
        self.osm_path = osm_path or str(_FRONTEND / "data" / "map" / "part_of_yangpu.osm")
        self.episode_max_steps = episode_max_steps
        # 动态取类，保证 rebuild 后能拿到 reload 后的新 Environment
        env_cls = _env_module.Environment
        self.env = env_cls(self.osm_path, visualize=False,
                           episode_max_steps=self.episode_max_steps)
        self.num_drones = len(self.env.drones)
        self.algorithm: str = "greedy"
        self.seed: int = 100
        self.scheduler: Any = None
        self.obs: Optional[Dict] = None
        self.done: bool = False
        self.step_count: int = 0
        self.trajectories: List[List[List[float]]] = [[] for _ in range(self.num_drones)]

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
        return self.snapshot()

    def step(self) -> Dict:
        if self.done:
            return self.snapshot()
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
        return self.snapshot()

    def rebuild(self) -> Dict:
        """热重载配置并重建 Environment（写回 simulation.json 后调用）。"""
        reload_sim_modules()
        # reload 后 _env_module.Environment 已是最新类
        self.env = _env_module.Environment(
            self.osm_path, visualize=False, episode_max_steps=self.episode_max_steps)
        self.num_drones = len(self.env.drones)
        self.trajectories = [[] for _ in range(self.num_drones)]
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
            "stats": self._stats_snapshot(),
        }

    def map_static(self) -> Dict:
        """静态地图几何（一次性）：边界 + 建筑轮廓(含高度)。"""
        bounds = getattr(self.env, "global_bounds", None)
        if not bounds:
            xs = [d.x for d in self.env.drones] + [s.x for s in self.env.charging_stations]
            ys = [d.y for d in self.env.drones] + [s.y for s in self.env.charging_stations]
            bounds = (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 1000, 1000)
        buildings = []
        for b in getattr(self.env, "high_buildings", []) or []:
            rings = _polygon_rings(b.get("geometry"))
            for ring in rings:
                if len(ring) >= 3:
                    buildings.append({
                        "coords": ring,
                        "height": round(float(b.get("height") or 20.0), 2),
                    })
        return {
            "bounds": [float(v) for v in bounds],
            "buildings": buildings,
            "no_fly_zones": self._no_fly_snapshot(),
        }

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
            out.append({
                "idx": i,
                "id": str(getattr(d, "drone_id", f"drone_{i}")),
                "type": str(getattr(d, "drone_type", "") or ""),
                "x": float(d.x),
                "y": float(d.y),
                "state": _drone_state(d),
                "battery_ratio": round(float(getattr(d, "current_battery", 0.0)) / cap, 4),
                "load": float(getattr(d, "current_load", 0.0)),
                "capacity": float(getattr(d, "carrying_capacity", 0.0)),
                "executing_task": str(getattr(d, "executing_task_id", "") or ""),
            })
        return out

    def _nests_snapshot(self) -> List[Dict]:
        return [{
            "id": str(getattr(s, "station_id", "")),
            "x": float(s.x),
            "y": float(s.y),
            "berths": int(getattr(s, "berths", 1)),
            "occupied": int(getattr(s, "occupied", 0)),
        } for s in self.env.charging_stations]

    def _tasks_snapshot(self, limit: int = 60) -> List[Dict]:
        tasks = []
        try:
            unassigned = getattr(self.env.task_generator, "unassigned_tasks", []) or []
        except Exception:
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
                "priority": int(getattr(t, "priority", 1)),
            })
            if len(tasks) >= limit:
                break
        return tasks

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
