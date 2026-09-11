"""数据源适配层 —— 随机生成 ↔ CSV/GeoJSON 导入真实数据。

仿真环境需要三类真实业务数据：机队（机型/载重/起降点）、机巢（充电站）、任务
（重量/体积/类别/优先级/时效/起终点）。本层把它们抽象成一组与来源无关的"规格
记录"(Spec)，并提供统一入口 DataSource：环境只消费 Spec，由环境负责实例化成
Drone / ChargingStation / Task，调度算法与观测 schema 均不感知数据来自何处。

三种实现：
  - RandomDataSource : 随机生成，沿用 simulation.json 的 fleet_mix / charging_stations /
                       task 分布，行为与历史版本完全一致。
  - CSVDataSource    : 从 drones.csv / nests.csv / tasks.csv 导入。
  - GeoJSONDataSource: 从 GeoJSON FeatureCollection 导入（点/线 -> 配送点/机巢/任务）。

接入真实企业数据：新增一个 DataSource 子类，实现 load_drones / load_nests /
load_tasks / build_task_source 四个方法即可，无需改动环境与调度算法。

任务流：静态导入（CSV/GeoJSON）与随机生成（Random）通过"任务源"对象统一，
二者暴露同构接口（generate_initial_tasks / step / unassigned_tasks / reset /
set_seed / is_exhausted），环境无需区分。
"""
from __future__ import annotations

import csv
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config.config_loder import get_shared_config
from task import Task, TaskGenerator, WAREHOUSE_POS

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = Path(__file__).resolve().parent
CONFIG_ROOT = PROJECT_ROOT / "config"


# =============================================================================
# 规格记录（Spec）：环境与数据源之间的中间契约，与环境内部对象解耦。
# =============================================================================

@dataclass
class DroneSpec:
    """单架无人机的规格：编号、机型、起降点、载重覆盖值。

    carrying_capacity 为 None 表示沿用机型默认载重（或全局默认）。
    """
    drone_id: str
    drone_type: Optional[str] = None
    base_position: Tuple[float, float] = WAREHOUSE_POS
    carrying_capacity: Optional[float] = None


@dataclass
class NestSpec:
    """机巢（换电站）规格。"""
    nest_id: Any
    position: Tuple[float, float]
    charging_power: float = 50.0
    swap_time_seconds: float = 180.0
    berths: int = 2


@dataclass
class TaskSpec:
    """单个任务规格。"""
    task_id: str
    source: Tuple[float, float]
    destination: Tuple[float, float]
    weight: float = 0.0
    volume: float = 0.0
    category: str = "normal"
    priority: int = 1
    deadline: Optional[float] = None
    generation_time: float = 0.0


# =============================================================================
# 任务源：随机生成的 TaskGenerator 与静态导入的 StaticTaskSource 接口同构。
# =============================================================================

class StaticTaskSource:
    """静态任务源：把导入的任务一次性放入任务池，之后不再生成。

    对外暴露与 TaskGenerator 相同的子集接口，环境无需感知任务来自静态导入
    还是随机生成。
    """

    def __init__(self, tasks: List[TaskSpec]):
        self._specs = list(tasks)
        self._unassigned: List[Task] = []
        self.total_tasks_generated = len(self._specs)

    @property
    def unassigned_tasks(self) -> List[Task]:
        return self._unassigned

    @property
    def is_exhausted(self) -> bool:
        # 静态任务已全部"生成"，任务池清空且机队空闲即可收尾。
        return True

    def _build_task(self, s: TaskSpec) -> Task:
        return Task(
            task_id=s.task_id,
            weight=s.weight,
            source=s.source,
            destination=s.destination,
            deadline=s.deadline,
            priority=s.priority,
            generation_time=s.generation_time,
            volume=s.volume,
            category=s.category,
        )

    def generate_initial_tasks(self, current_time: float = 0.0) -> List[Task]:
        tasks = [self._build_task(s) for s in self._specs]
        self._unassigned = tasks
        return tasks

    def step(self, current_time: float) -> List[Task]:
        return []

    def reset(self) -> None:
        self._unassigned = []

    def set_seed(self, seed) -> None:
        return None


# =============================================================================
# 数据源抽象基类
# =============================================================================

class DataSource(ABC):
    """数据源抽象：环境只消费三类规格，不关心数据来自随机生成还是文件导入。"""

    source_type: str = "abstract"

    @abstractmethod
    def load_drones(self) -> List[DroneSpec]:
        """机队规格（编号 / 机型 / 起降点）。"""

    @abstractmethod
    def load_nests(self) -> List[NestSpec]:
        """机巢（充电站）规格。"""

    @abstractmethod
    def load_tasks(self, current_time: float = 0.0) -> List[TaskSpec]:
        """静态任务（随机源返回空，动态任务走 build_task_source）。"""

    @abstractmethod
    def build_task_source(self) -> Any:
        """返回任务源对象（TaskGenerator 或 StaticTaskSource，二者接口同构）。"""


# =============================================================================
# 随机生成数据源（历史默认行为）
# =============================================================================

class RandomDataSource(DataSource):
    """随机生成数据源：沿用 simulation.json 配置，行为与历史版本一致。"""

    source_type = "random"

    def __init__(self, cfg: Optional[Dict] = None):
        self._cfg = cfg or get_shared_config()

    def load_drones(self) -> List[DroneSpec]:
        hetero = self._cfg.get("heterogeneous", {})
        fleet_mix = hetero.get("fleet_mix", {}) if hetero.get("enabled", False) else {}
        num_drones = int(self._cfg.get("environment", {}).get("num_drones", 3))

        types: List[Optional[str]] = []
        for dtype, count in fleet_mix.items():
            types.extend([dtype] * int(count))
        types = types[:num_drones]
        if len(types) < num_drones:
            types.extend([None] * (num_drones - len(types)))

        return [
            DroneSpec(drone_id=f"drone_{i}", drone_type=types[i])
            for i in range(num_drones)
        ]

    def load_nests(self) -> List[NestSpec]:
        from charging_station import build_default_charging_stations
        return [
            NestSpec(nest_id=s.station_id, position=s.get_position(),
                     charging_power=s.charging_power,
                     swap_time_seconds=s.swap_time_seconds,
                     berths=s.berths)
            for s in build_default_charging_stations()
        ]

    def load_tasks(self, current_time: float = 0.0) -> List[TaskSpec]:
        return []

    def build_task_source(self) -> TaskGenerator:
        task_cfg = self._cfg.get("task", {})
        positions_file = task_cfg.get("positions_file", "../config/positions.json")
        return TaskGenerator(file_path=positions_file)


# =============================================================================
# 文件型数据源公共工具
# =============================================================================

def _resolve_path(p: Optional[str]) -> Optional[Path]:
    if not p:
        return None
    path = Path(p)
    if path.is_absolute():
        return path
    candidates = [
        FRONTEND_ROOT / path,       # "前端相对路径"约定：../config/import/x.csv
        CONFIG_ROOT / path.name,    # config 目录下按文件名兜底查找
        PROJECT_ROOT / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _opt_float(raw: Any, default: Optional[float] = None) -> Optional[float]:
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _opt_int(raw: Any, default: int) -> int:
    if raw is None or raw == "":
        return default
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return default


# =============================================================================
# CSV 数据源
# =============================================================================

class CSVDataSource(DataSource):
    """从 CSV 文件导入机队 / 机巢 / 任务。

    期望列名（首行为表头，缺失列取默认值）：
      drones.csv : drone_id, drone_type, base_x, base_y, carrying_capacity
      nests.csv  : nest_id, x, y, charging_power, swap_time_seconds, berths
      tasks.csv  : task_id, source_x, source_y, dest_x, dest_y, weight, volume,
                   category, priority, deadline, generation_time
    """

    source_type = "csv"

    def __init__(self, drones_file: Optional[str] = None,
                 nests_file: Optional[str] = None,
                 tasks_file: Optional[str] = None,
                 cfg: Optional[Dict] = None):
        cfg = cfg or get_shared_config()
        ds_cfg = cfg.get("data_source", {}).get("csv", {})
        self._drones_file = drones_file or ds_cfg.get("drones_file")
        self._nests_file = nests_file or ds_cfg.get("nests_file")
        self._tasks_file = tasks_file or ds_cfg.get("tasks_file")

    def load_drones(self) -> List[DroneSpec]:
        specs: List[DroneSpec] = []
        path = _resolve_path(self._drones_file)
        if path is None or not path.exists():
            return specs
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                specs.append(DroneSpec(
                    drone_id=(row.get("drone_id") or "").strip(),
                    drone_type=(row.get("drone_type") or "").strip() or None,
                    base_position=(
                        _opt_float(row.get("base_x"), WAREHOUSE_POS[0]),
                        _opt_float(row.get("base_y"), WAREHOUSE_POS[1]),
                    ),
                    carrying_capacity=_opt_float(row.get("carrying_capacity")),
                ))
        return specs

    def load_nests(self) -> List[NestSpec]:
        specs: List[NestSpec] = []
        path = _resolve_path(self._nests_file)
        if path is None or not path.exists():
            return specs
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                specs.append(NestSpec(
                    nest_id=(row.get("nest_id") or "").strip(),
                    position=(
                        float(row.get("x", 0.0) or 0.0),
                        float(row.get("y", 0.0) or 0.0),
                    ),
                    charging_power=_opt_float(row.get("charging_power"), 50.0) or 50.0,
                    swap_time_seconds=_opt_float(row.get("swap_time_seconds"), 180.0) or 180.0,
                    berths=_opt_int(row.get("berths"), 2),
                ))
        return specs

    def load_tasks(self, current_time: float = 0.0) -> List[TaskSpec]:
        specs: List[TaskSpec] = []
        path = _resolve_path(self._tasks_file)
        if path is None or not path.exists():
            return specs
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                specs.append(TaskSpec(
                    task_id=(row.get("task_id") or "").strip(),
                    source=(float(row.get("source_x", 0.0) or 0.0),
                            float(row.get("source_y", 0.0) or 0.0)),
                    destination=(float(row.get("dest_x", 0.0) or 0.0),
                                 float(row.get("dest_y", 0.0) or 0.0)),
                    weight=_opt_float(row.get("weight"), 0.0) or 0.0,
                    volume=_opt_float(row.get("volume"), 0.0) or 0.0,
                    category=(row.get("category") or "normal").strip() or "normal",
                    priority=_opt_int(row.get("priority"), 1),
                    deadline=_opt_float(row.get("deadline")),
                    generation_time=_opt_float(row.get("generation_time"), current_time) or 0.0,
                ))
        return specs

    def build_task_source(self) -> StaticTaskSource:
        return StaticTaskSource(self.load_tasks())


# =============================================================================
# GeoJSON 数据源
# =============================================================================

class GeoJSONDataSource(DataSource):
    """从 GeoJSON FeatureCollection 导入机队 / 机巢 / 任务。

    feature.properties.role 决定用途：
      - "drone" : geometry Point 为起降点；props: drone_id, drone_type, carrying_capacity
      - "nest"  : geometry Point 为机巢位置；props: nest_id, charging_power,
                   swap_time_seconds, berths
      - "task"  : geometry LineString [source, destination]（或 Point 为 source 时，
                  配合 props.destination=[x,y]）；props: task_id, weight, volume,
                  category, priority, deadline, generation_time
    """

    source_type = "geojson"

    def __init__(self, file: Optional[str] = None, cfg: Optional[Dict] = None):
        cfg = cfg or get_shared_config()
        ds_cfg = cfg.get("data_source", {}).get("geojson", {})
        self._file = file or ds_cfg.get("file")
        self._raw: Optional[Dict] = None

    def _load(self) -> Dict:
        if self._raw is None:
            path = _resolve_path(self._file)
            if path is None or not path.exists():
                self._raw = {"type": "FeatureCollection", "features": []}
            else:
                with open(path, "r", encoding="utf-8") as f:
                    self._raw = json.load(f)
        return self._raw

    def _features(self) -> List[Dict]:
        data = self._load()
        return data.get("features", []) or []

    @staticmethod
    def _endpoints(geometry: Dict) -> Tuple[Optional[Tuple[float, float]],
                                             Optional[Tuple[float, float]]]:
        gtype = geometry.get("type")
        coords = geometry.get("coordinates") or []
        if gtype == "LineString" and len(coords) >= 2:
            return tuple(coords[0][:2]), tuple(coords[-1][:2])
        if gtype == "Point":
            p = tuple(coords[:2])
            return p, p
        if gtype == "MultiPoint" and coords:
            p = tuple(coords[0][:2])
            return p, p
        if gtype == "Polygon" and coords and coords[0]:
            p = tuple(coords[0][0][:2])
            return p, p
        return None, None

    def load_drones(self) -> List[DroneSpec]:
        specs: List[DroneSpec] = []
        for feat in self._features():
            props = feat.get("properties") or {}
            if props.get("role") != "drone":
                continue
            pt, _ = self._endpoints(feat.get("geometry") or {})
            if pt is None:
                continue
            specs.append(DroneSpec(
                drone_id=str(props.get("drone_id") or "drone"),
                drone_type=props.get("drone_type") or None,
                base_position=pt,
                carrying_capacity=_opt_float(props.get("carrying_capacity")),
            ))
        return specs

    def load_nests(self) -> List[NestSpec]:
        specs: List[NestSpec] = []
        for feat in self._features():
            props = feat.get("properties") or {}
            if props.get("role") != "nest":
                continue
            pt, _ = self._endpoints(feat.get("geometry") or {})
            if pt is None:
                continue
            specs.append(NestSpec(
                nest_id=props.get("nest_id", "nest"),
                position=pt,
                charging_power=_opt_float(props.get("charging_power"), 50.0) or 50.0,
                swap_time_seconds=_opt_float(props.get("swap_time_seconds"), 180.0) or 180.0,
                berths=_opt_int(props.get("berths"), 2),
            ))
        return specs

    def load_tasks(self, current_time: float = 0.0) -> List[TaskSpec]:
        specs: List[TaskSpec] = []
        for feat in self._features():
            props = feat.get("properties") or {}
            if props.get("role") != "task":
                continue
            geometry = feat.get("geometry") or {}
            source, dest = self._endpoints(geometry)
            if source is None:
                continue
            # Point 作为 source 时，允许 props.destination=[x,y] 给出终点
            if dest == source:
                extra_dest = props.get("destination")
                if extra_dest and len(extra_dest) >= 2:
                    dest = (float(extra_dest[0]), float(extra_dest[1]))
            specs.append(TaskSpec(
                task_id=str(props.get("task_id") or "task"),
                source=source,
                destination=dest,
                weight=_opt_float(props.get("weight"), 0.0) or 0.0,
                volume=_opt_float(props.get("volume"), 0.0) or 0.0,
                category=props.get("category") or "normal",
                priority=_opt_int(props.get("priority"), 1),
                deadline=_opt_float(props.get("deadline")),
                generation_time=_opt_float(props.get("generation_time"), current_time) or 0.0,
            ))
        return specs

    def build_task_source(self) -> StaticTaskSource:
        return StaticTaskSource(self.load_tasks())


# =============================================================================
# 工厂：根据配置选择数据源
# =============================================================================

def build_data_source(cfg: Optional[Dict] = None) -> DataSource:
    """根据 simulation.json 的 data_source.type 选择并构建数据源。

    未配置或无法识别时回落到 RandomDataSource，保持历史行为。
    """
    cfg = cfg or get_shared_config()
    ds_cfg = cfg.get("data_source", {}) or {}
    stype = str(ds_cfg.get("type", "random")).strip().lower()

    if stype == "csv":
        return CSVDataSource(cfg=cfg)
    if stype in ("geojson", "geo_json"):
        return GeoJSONDataSource(cfg=cfg)
    if stype == "enterprise":
        from enterprise_data_source import EnterpriseDataSource
        e_cfg = ds_cfg.get("enterprise", {}) or {}
        return EnterpriseDataSource(
            base_url=e_cfg.get("base_url"),
            api_token=e_cfg.get("api_token"),
            timeout=float(e_cfg.get("timeout", 10.0)),
            coord_system=e_cfg.get("coord_system", "lonlat"),
            verify=bool(e_cfg.get("verify", True)),
            live=bool(e_cfg.get("live", False)),
            cfg=cfg,
        )
    return RandomDataSource(cfg=cfg)