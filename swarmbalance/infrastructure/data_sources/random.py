"""RandomDataSource implementation."""
from __future__ import annotations
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from swarmbalance.infrastructure.config.loader import get_shared_config
from swarmbalance.contracts.data_source import DataSource, DroneSpec, NestSpec, TaskSpec
from swarmbalance.simulation.entities.task import Task, TaskGenerator, WAREHOUSE_POS
from swarmbalance.infrastructure.data_sources.common import StaticTaskSource, _resolve_path, _opt_float, _opt_int


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
        from swarmbalance.simulation.entities.charging_station import build_default_charging_stations
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
