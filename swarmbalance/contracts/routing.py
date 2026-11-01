"""Immutable route requests/results and the route-cost provider contract."""
from dataclasses import dataclass
from typing import Dict, List, Protocol, Sequence, Tuple
Point = Tuple[float, float]

@dataclass(frozen=True)
class RouteRequest:
    """一次规划的输入。字段以现有调用链为准，不提前加入当前不存在的语义。"""
    start: Point
    goal: Point

@dataclass(frozen=True)
class RouteResult:
    """输出。

    waypoints 保持原 `(x, y)` 二元组列表语义 —— tag（'source'/'dest'/'waypoint'）
    仍由调用方补（见 environment.py:1047-1051、:1763-1766），与原实现一致。
    Phase 1A **不**把 waypoint 结构化成对象：那会把行为变化面叠到架构变化上，
    已排到 Phase 1C / 2.5D 前置（docs/二维假设清单.md H3）。

    direct   直线未被遮挡、短路返回（原 :1847-1848）
    detour   本次因禁飞区触发绕飞（原计数事实，改为返回而非写环境）
    fallback A* 无解、退回直连终点（原 :1862-1863，原实现会 print 警告）
    """
    waypoints: Tuple[Point, ...]
    feasible: bool
    direct: bool
    detour: bool
    fallback: bool
    distance: float

    def as_list(self) -> List[Point]:
        return list(self.waypoints)


class RouteCostProvider(Protocol):
    name: str

    def distance(self, a: Sequence[float], b: Sequence[float]) -> float: ...
    def batch(self, origin: Sequence[float], targets: List[Sequence[float]]) -> List[float]: ...
    def eta(self, a: Sequence[float], b: Sequence[float], speed_m_per_s: float) -> float: ...
    def stats(self) -> Dict[str, int]: ...
