"""GeoJSONDataSource implementation."""
from __future__ import annotations
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from swarmbalance.infrastructure.config.loader import get_shared_config
from swarmbalance.contracts.data_source import DataSource, DroneSpec, NestSpec, TaskSpec
from swarmbalance.simulation.entities.task import Task, TaskGenerator, WAREHOUSE_POS
from swarmbalance.infrastructure.data_sources.common import StaticTaskSource, _resolve_path, _opt_float, _opt_int


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
