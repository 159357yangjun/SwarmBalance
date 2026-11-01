"""Shared imported-task stream and scalar/path conversion helpers."""
from pathlib import Path
from typing import Any, List, Optional
from swarmbalance.paths import resolve_resource
from swarmbalance.contracts.data_source import TaskSpec
from swarmbalance.simulation.entities.task import Task

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

def _resolve_path(p: Optional[str]) -> Optional[Path]:
    return resolve_resource(p) if p else None


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
