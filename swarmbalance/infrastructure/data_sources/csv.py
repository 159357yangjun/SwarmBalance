"""CSVDataSource implementation."""
from __future__ import annotations
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from swarmbalance.infrastructure.config.loader import get_shared_config
from swarmbalance.contracts.data_source import DataSource, DroneSpec, NestSpec, TaskSpec
from swarmbalance.simulation.entities.task import Task, TaskGenerator, WAREHOUSE_POS
from swarmbalance.infrastructure.data_sources.common import StaticTaskSource, _resolve_path, _opt_float, _opt_int


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
