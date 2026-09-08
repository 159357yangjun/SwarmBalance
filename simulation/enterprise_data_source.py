"""企业订单数据接入 —— DataSource 子类示例。

演示如何把企业（ERP / TMS / 低空物流平台）的机队、机巢、订单三类真实数据，
通过 HTTP(S) REST API 映射成仿真数据源的规格记录，供 Environment 直接消费，
无需改动环境与调度算法。

坐标系统（coord_system 参数）：
  - "lonlat" : WGS84 经纬度；运行时用 pyproj 自动投影成 UTM 平面坐标（米）。
  - "utm"    : 已是平面坐标，第一列=东(x)，第二列=北(y)，直接透传。

两种任务流（build_task_source 决定）：
  - 快照（live=False，默认）：一次性拉取当前在用订单全部入池。
  - 实时（live=True）：返回 PollingOrderSource，每个仿真步 poll 一次接口，
    只把"新出现"的订单追加进任务池（按 order_id 去重），对应真实订单流。

用法一（直接传入环境）：
    from simulation.environment import Environment
    from enterprise_data_source import EnterpriseDataSource
    ds = EnterpriseDataSource(base_url="https://tms.example.com", api_token="...")
    env = Environment("data/map/part_of_yangpu.osm", data_source=ds)
    obs = env.reset(seed=0)

用法二（经 simulation.json 配置，由 build_data_source 自动构建）：
    "data_source": {
      "type": "enterprise",
      "enterprise": { "base_url": "https://tms.example.com", "api_token": "…",
                      "coord_system": "lonlat", "live": true }
    }

约定的 REST 契约（示例；按企业真实网关改 _fetch_* / _to_spec 即可）：
    GET {base}/api/v1/drones -> {"items":[{id, model, lon, lat, capacity_kg}]}
    GET {base}/api/v1/nests  -> {"items":[{id, lon, lat, swap_time_s, berths}]}
    GET {base}/api/v1/orders -> {"items":[{order_id, pickup_lon, pickup_lat,
                                            dropoff_lon, dropoff_lat, weight_kg,
                                            volume_m3, priority, deadline_s}]}
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from .data_source import DataSource, DroneSpec, NestSpec, StaticTaskSource, TaskSpec
from .task import Task

# 企业机型名 -> 仿真机型 key；未命中回落 None（走默认无人机参数）。
# 若企业字段直接返回仿真机型 key（如 "heavy_cargo"），则优先使用 explicit type。
MODEL_TYPE_MAP: Dict[str, str] = {
    "meituan_v4": "light_express",
    "sf_ark40": "standard_cargo",
    "dji_flycart30": "heavy_cargo",
}


def _num(raw: Any, default: float = 0.0) -> Optional[float]:
    """安全转 float：空值 / 非法值返回 default。"""
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _utm_zone(longitude: float) -> int:
    return int(math.floor((longitude + 180.0) / 6.0)) + 1


def lonlat_to_utm(lon: float, lat: float) -> Tuple[float, float]:
    """WGS84 经纬度 -> UTM 平面坐标（米）。自动按经度选择分带（南北半球自感知）。"""
    from pyproj import Transformer
    zone = _utm_zone(lon)
    epsg = (32700 if lat < 0.0 else 32600) + zone
    x, y = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True).transform(lon, lat)
    return float(x), float(y)


def _spec_to_task(s: TaskSpec) -> Task:
    return Task(
        task_id=s.task_id, weight=s.weight, source=s.source,
        destination=s.destination, deadline=s.deadline,
        priority=s.priority, generation_time=s.generation_time,
        volume=s.volume, category=s.category,
    )


class PollingOrderSource:
    """实时订单源：每次 step() 轮询企业接口，只追加新订单（按 task_id 去重）。

    与 StaticTaskSource / TaskGenerator 接口同构，环境无需感知差异。
    """

    def __init__(self, fetch: Callable[[], List[Dict]], convert: Callable[[Dict], Task]):
        self._fetch = fetch
        self._convert = convert
        self._unassigned: List[Task] = []
        self._seen: set = set()
        self.total_tasks_generated = 0

    @property
    def unassigned_tasks(self) -> List[Task]:
        return self._unassigned

    @property
    def is_exhausted(self) -> bool:
        # 实时源不"耗尽"；由外部按仿真时长终止。
        return False

    def _poll(self) -> List[Task]:
        fresh: List[Task] = []
        for task in map(self._convert, self._fetch()):
            if task.task_id in self._seen:
                continue
            self._seen.add(task.task_id)
            fresh.append(task)
        return fresh

    def generate_initial_tasks(self, current_time: float = 0.0) -> List[Task]:
        tasks = self._poll()
        self._unassigned = list(tasks)
        self.total_tasks_generated += len(tasks)
        return tasks

    def step(self, current_time: float) -> List[Task]:
        tasks = self._poll()
        self._unassigned.extend(tasks)
        self.total_tasks_generated += len(tasks)
        return tasks

    def reset(self) -> None:
        self._unassigned = []
        self._seen = set()
        self.total_tasks_generated = 0

    def set_seed(self, seed) -> None:
        return None


class EnterpriseDataSource(DataSource):
    """从企业 REST 网关接入机队 / 机巢 / 订单数据。"""

    source_type = "enterprise"

    def __init__(self, base_url: str, api_token: Optional[str] = None,
                 timeout: float = 10.0, coord_system: str = "lonlat",
                 verify: bool = True, live: bool = False,
                 model_type_map: Optional[Dict[str, str]] = None,
                 cfg: Optional[Dict] = None):
        self.base_url = (base_url or "").rstrip("/")
        if not self.base_url:
            raise ValueError("EnterpriseDataSource 需要 base_url")
        self.api_token = api_token
        self.timeout = timeout
        self.coord_system = (coord_system or "lonlat").strip().lower()
        self.verify = verify
        self.live = bool(live)
        self._type_map = dict(model_type_map or MODEL_TYPE_MAP)
        self._cfg = cfg or {}
        self._session = requests.Session()
        self._session.headers["Accept"] = "application/json"
        if api_token:
            self._session.headers["Authorization"] = f"Bearer {api_token}"

    # ---------------- 传输 ----------------
    def _get_json(self, endpoint: str) -> Dict:
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        resp = self._session.get(url, timeout=self.timeout, verify=self.verify)
        resp.raise_for_status()
        return resp.json()

    def _fetch_orders(self) -> List[Dict]:
        return self._get_json("api/v1/orders").get("items", []) or []

    # ---------------- 坐标 / 机型 ----------------
    def _xy(self, a: Any, b: Any) -> Tuple[float, float]:
        if self.coord_system == "utm":
            return float(a), float(b)
        return lonlat_to_utm(float(a), float(b))

    def _map_type(self, item: Dict) -> Optional[str]:
        explicit = (item.get("type") or item.get("drone_type") or "").strip().lower()
        if explicit:
            return explicit
        model = (item.get("model") or "").strip().lower().replace(" ", "_").replace("-", "_")
        return self._type_map.get(model)

    # ---------------- 三类规格 ----------------
    def load_drones(self) -> List[DroneSpec]:
        specs: List[DroneSpec] = []
        for it in self._get_json("api/v1/drones").get("items", []):
            specs.append(DroneSpec(
                drone_id=str(it.get("id") or it.get("drone_id") or "drone"),
                drone_type=self._map_type(it),
                base_position=self._xy(it["lon"], it["lat"]),
                carrying_capacity=_num(it.get("capacity_kg")),
            ))
        return specs

    def load_nests(self) -> List[NestSpec]:
        specs: List[NestSpec] = []
        for it in self._get_json("api/v1/nests").get("items", []):
            specs.append(NestSpec(
                nest_id=it.get("id") or it.get("nest_id") or "nest",
                position=self._xy(it["lon"], it["lat"]),
                charging_power=_num(it.get("charging_power"), 50.0) or 50.0,
                swap_time_seconds=_num(it.get("swap_time_s"), 180.0) or 180.0,
                berths=int(_num(it.get("berths"), 2) or 2),
            ))
        return specs

    def _to_spec(self, it: Dict) -> TaskSpec:
        priority = int(_num(it.get("priority"), 1) or 1)
        category = (it.get("category") or "").strip() or ("urgent" if priority >= 3 else "normal")
        # deadline：企业给"距现在多少秒到期"（与 1 step = 1 秒同口径）；缺省不罚超时
        deadline = _num(it.get("deadline_s"))
        return TaskSpec(
            task_id=str(it.get("order_id") or it.get("id") or "task"),
            source=self._xy(it["pickup_lon"], it["pickup_lat"]),
            destination=self._xy(it["dropoff_lon"], it["dropoff_lat"]),
            weight=_num(it.get("weight_kg"), 0.0) or 0.0,
            volume=_num(it.get("volume_m3"), 0.0) or 0.0,
            category=category,
            priority=priority,
            deadline=deadline,
            generation_time=0.0,
        )

    def load_tasks(self, current_time: float = 0.0) -> List[TaskSpec]:
        return [self._to_spec(it) for it in self._fetch_orders()]

    def build_task_source(self) -> Any:
        if self.live:
            return PollingOrderSource(
                fetch=self._fetch_orders,
                convert=lambda it: _spec_to_task(self._to_spec(it)),
            )
        return StaticTaskSource(self.load_tasks())