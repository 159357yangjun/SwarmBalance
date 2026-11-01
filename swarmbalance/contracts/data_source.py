"""Data-source records and abstract input contract, without simulation entities."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from swarmbalance.infrastructure.config.loader import get_shared_config

# Preserve the existing configured default without importing concrete Task entities.
WAREHOUSE_POS = tuple(get_shared_config().get("task", {}).get("warehouse_pos", [357600.574872369, 3462308.772003661]))

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
