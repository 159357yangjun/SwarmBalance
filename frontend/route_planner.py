# -*- coding: utf-8 -*-
"""RoutePlanner —— 从 Environment 抽离的绕障路径规划（Phase 1A）。

**本轮只做搬家，不做重写。** A* 与可见图构造的逻辑逐字来自
`frontend/environment.py:1842-1945`：未优化搜索、未改启发式、未加 z、未改建筑高度规则。
等价性由 `console/test_route_planner_equivalence.py`（Gate A）钉住，仿真零漂移由 Gate B 钉住。

为什么能抽：审计实测该段只依赖 Environment 的 6 个成员
（no_fly / high_buildings / _high_buildings_bbox / heuristic / is_path_clear+缓存 / total_no_fly_detours），
耦合面远小于 2024 行的体量所暗示的范围。

两个必须显式处理的点：
1. `total_no_fly_detours`（原 :1851-1852）是路径规划顺手写的统计副作用 ⇒ 抽离后 planner
   只在 RouteResult.detour 里返回事实，由上层决定如何记账；planner 不偷改环境指标。
2. 缓存生命周期不得改变：`is_path_clear` 实测被调 18 万次而 A* 仅 34 次（原注释 :1983-1984）。
   因此 path_clear 以**回调**形式注入并保持同一绑定方法 ⇒ 结果桶仍按同一份障碍几何指纹共享，
   不会因抽离分裂成两份缓存（那会让行为不变但性能塌掉，且是最难查的那类回归）。
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Sequence, Tuple

Point = Tuple[float, float]


def euclidean(pos1: Sequence[float], pos2: Sequence[float]) -> float:
    """二维欧氏距离。**逐字照搬** environment.py:1947-1951 的 heuristic。

    它在原实现里同时承担三职：h（:1910/:1938）、边权 g 增量（:1933）、终止判据（:1918）。
    ⇒ 它不是"仅供排序的启发式"，改它等于换搜索空间（docs/二维假设清单.md H2）。
    """
    return math.sqrt((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2)


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


class RoutePlanner:
    """绕障路径规划器。世界依赖通过构造注入，全部为引用而非复制。

    参数
      high_buildings : Environment.high_buildings（同一列表对象，:174）
      no_fly         : NoFlyZoneSet（:1842 起用到 path_blocked / corner_points）
      path_clear     : 必须是 Environment.is_path_clear 的**同一绑定方法**，
                       以便复用其结果缓存与几何指纹桶
      warn           : 兜底时的告警出口，默认 print，与原实现一致（可注入以便测试静默）
    """

    def __init__(self, high_buildings: List[Dict[str, Any]],
                 no_fly: Any,
                 path_clear: Callable[[Sequence[float], Sequence[float]], bool],
                 warn: Callable[[str], None] = print) -> None:
        self.high_buildings = high_buildings
        self.no_fly = no_fly
        self._path_clear = path_clear
        self._warn = warn

    # ---------------------------------------------------------------- 公共入口
    def plan(self, req: RouteRequest) -> RouteResult:
        """等价于原 Environment.plan_route_around_buildings(start, end)（:1842-1863）。"""
        start, end_pos = req.start, req.goal
        detour = False

        # 直线可行 ⇒ 短路返回。原实现返回 [end_pos]，此处保持一致。
        if self._path_clear(start, end_pos):
            return RouteResult(waypoints=(tuple(end_pos),), feasible=True,
                               direct=True, detour=False, fallback=False,
                               distance=euclidean(start, end_pos))

        # 直线被禁飞区拦截：记一次绕飞【事实】，不再由 planner 写环境计数器
        if self.no_fly.path_blocked(start, end_pos):
            detour = True

        path = self.a_star_pathfinding(start, end_pos)
        if path and len(path) > 1:
            pts = tuple(path[1:])          # 去掉起点，与原 :1857-1859 一致
            return RouteResult(waypoints=pts, feasible=True, direct=False,
                               detour=detour, fallback=False,
                               distance=_polyline_distance((start,) + pts))

        # 最后兜底：直连终点并告警（原 :1861-1863）
        self._warn("Warning: Could not find obstacle-free path from %s to %s" % (start, end_pos))
        return RouteResult(waypoints=(tuple(end_pos),), feasible=False, direct=False,
                           detour=detour, fallback=True, distance=euclidean(start, end_pos))

    # ---------------------------------------------------------------- A*（照搬）
    def a_star_pathfinding(self, start, goal):
        """A* + 可见图，考虑建筑障碍。逻辑逐字来自 environment.py:1865-1945。"""
        def round_pos(pos, decimals=2):
            return (round(pos[0], decimals), round(pos[1], decimals))

        start = round_pos(start)
        goal = round_pos(goal)

        all_points = [start, goal]

        for building in self.high_buildings:
            geom = building['geometry']
            if hasattr(geom, 'exterior'):          # Polygon
                for coord in list(geom.exterior.coords)[:-1]:
                    rounded_coord = round_pos(coord)
                    if rounded_coord != start and rounded_coord != goal:
                        all_points.append(rounded_coord)
            elif hasattr(geom, 'coords'):          # Point or LineString
                for coord in geom.coords:
                    rounded_coord = round_pos(coord)
                    if rounded_coord != start and rounded_coord != goal:
                        all_points.append(rounded_coord)

        # 禁飞区：补充外沿采样点，使 A* 能真正绕飞而不是直接穿越
        for pt in self.no_fly.corner_points():
            rounded_coord = round_pos(pt)
            if rounded_coord != start and rounded_coord != goal:
                all_points.append(rounded_coord)

        all_points = list(set(all_points))

        open_set = [(0, start)]
        came_from = {}
        g_score = {start: 0}
        f_score = {start: euclidean(start, goal)}

        open_set_set = {start}

        while open_set:
            _, current = heapq.heappop(open_set)
            open_set_set.remove(current)

            if euclidean(current, goal) < 1:      # Close enough to goal
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                return path

            for neighbor in all_points:
                if neighbor == current:
                    continue
                if self._path_clear(current, neighbor):
                    tentative_g = g_score.get(current, float('inf')) + euclidean(current, neighbor)
                    if tentative_g < g_score.get(neighbor, float('inf')):
                        came_from[neighbor] = current
                        g_score[neighbor] = tentative_g
                        f_score[neighbor] = tentative_g + euclidean(neighbor, goal)
                        if neighbor not in open_set_set:
                            heapq.heappush(open_set, (f_score[neighbor], neighbor))
                            open_set_set.add(neighbor)

        return None


def _polyline_distance(pts: Tuple[Point, ...]) -> float:
    """折线累加长度。注意：这是新增的**报告量**，不参与任何决策，
    原实现没有等价值 ⇒ 不影响 Gate A 的路径等价判定。"""
    total = 0.0
    prev = pts[0]
    for cur in pts[1:]:
        total += euclidean(prev, cur)
        prev = cur
    return total
