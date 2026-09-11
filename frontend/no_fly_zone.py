"""禁飞区（No-Fly Zone）约束 —— 对应申请书「可灵活配置禁飞区等障碍物布局」。

设计要点
--------
1. **配置驱动**：区域由 `config/simulation.json` 的 `no_fly_zones` 段描述，支持
   `circle`（圆心 + 半径，米）与 `polygon`（顶点环，米）两种形状，逐区可 `enabled`
   开关，整体可 `enabled: false` 一键关闭 —— 便于做「有/无禁飞区」的 A/B 对比。
2. **安全余量**：`reserve_margin_m` 对区域做外扩缓冲，模拟真实空管的间隔要求，
   避免航线贴边穿过。
3. **参与路径规划**：`Environment.is_path_clear()` 会同时检测建筑物与禁飞区；
   A* 可见图会补充禁飞区的轮廓采样点，从而真正绕飞而不是撞进去。
4. **参与场景生成**：`TaskGenerator` 过滤落在禁飞区内的取送货点，避免生成
   天然不可达的任务（否则会污染完成率指标）。

坐标口径：与项目其余部分一致，使用 OSM 导出的投影坐标（单位：米）。
"""

from __future__ import annotations

import math
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from shapely.geometry import LineString, Point, Polygon, box

__all__ = [
    "NoFlyZone",
    "NoFlyZoneSet",
    "load_no_fly_zones",
    "get_no_fly_zones",
    "reset_no_fly_zones",
]

# 单个禁飞区在 A* 可见图中的轮廓采样点上限（圆形按角度均匀采样）
_MAX_SAMPLES_PER_ZONE = 24


class NoFlyZone:
    """单个禁飞区。几何以「含安全余量」的外扩面参与判定。"""

    def __init__(self, name: str, geometry, margin: float = 0.0, raw=None):
        self.name = name
        self.raw = raw if raw is not None else geometry
        self.margin = float(margin)
        self.geometry = geometry.buffer(margin) if margin > 0 else geometry
        # 可见图采样点（A* 绕飞用）：外扩后轮廓上再外扩一小步，保证贴边不判碰撞
        self._samples: Optional[List[Tuple[float, float]]] = None

    # ---------- 判定 ----------

    def contains(self, x: float, y: float) -> bool:
        return self.geometry.contains(Point(x, y))

    def intersects_line(self, p1: Sequence[float], p2: Sequence[float]) -> bool:
        line = LineString([tuple(p1[:2]), tuple(p2[:2])])
        if not self.geometry.intersects(line):
            return False
        # 与建筑物判定保持同一口径：忽略"擦角"级别的接触
        return self.geometry.intersection(line).length > 0.1

    # ---------- A* 可见图采样 ----------

    def sample_points(self) -> List[Tuple[float, float]]:
        if self._samples is not None:
            return self._samples

        geom = self.geometry
        pts: List[Tuple[float, float]] = []
        if isinstance(geom, Polygon):
            coords = list(geom.exterior.coords)
            # 均匀抽稀，避免可见图爆炸
            step = max(1, len(coords) // _MAX_SAMPLES_PER_ZONE)
            pts = [(float(c[0]), float(c[1])) for c in coords[::step]]
        else:
            bounds = geom.bounds  # (minx, miny, maxx, maxy)
            pts = [
                (bounds[0], bounds[1]), (bounds[2], bounds[1]),
                (bounds[2], bounds[3]), (bounds[0], bounds[3]),
            ]

        # 再向外退一小步，使绕行点本身不在禁飞区内
        self._samples = self._push_outward(pts)
        return self._samples

    def _push_outward(self, pts: List[Tuple[float, float]],
                      delta: float = 8.0) -> List[Tuple[float, float]]:
        centroid = self.geometry.centroid
        cx, cy = float(centroid.x), float(centroid.y)
        pushed = []
        for (x, y) in pts:
            dx, dy = x - cx, y - cy
            norm = math.hypot(dx, dy)
            if norm < 1e-6:
                continue
            pushed.append((x + dx / norm * delta, y + dy / norm * delta))
        return pushed


class NoFlyZoneSet:
    """禁飞区集合。未启用时所有判定恒为 False，调用方无需额外分支。"""

    def __init__(self, zones: Optional[Iterable[NoFlyZone]] = None,
                 enabled: bool = True):
        self.zones: List[NoFlyZone] = list(zones or [])
        self.enabled: bool = bool(enabled) and bool(self.zones)

    def __len__(self) -> int:
        return len(self.zones) if self.enabled else 0

    def __bool__(self) -> bool:
        return self.enabled and bool(self.zones)

    def contains(self, x: float, y: float) -> bool:
        if not self.enabled:
            return False
        return any(z.contains(x, y) for z in self.zones)

    def path_blocked(self, p1: Sequence[float], p2: Sequence[float]) -> bool:
        if not self.enabled:
            return False
        return any(z.intersects_line(p1, p2) for z in self.zones)

    def corner_points(self) -> List[Tuple[float, float]]:
        """A* 可见图补充点：使航线能沿禁飞区外沿绕行。"""
        if not self.enabled:
            return []
        pts: List[Tuple[float, float]] = []
        for z in self.zones:
            pts.extend(z.sample_points())
        return pts

    def describe(self) -> List[Dict]:
        return [
            {"name": z.name, "bounds": [round(v, 2) for v in z.raw.bounds]}
            for z in self.zones
        ]


def load_no_fly_zones(cfg: Optional[Dict] = None) -> NoFlyZoneSet:
    """从配置字典构建禁飞区集合。cfg 为空时自动读取共享配置。"""
    if cfg is None:
        from config.config_loder import get_shared_config
        cfg = get_shared_config().get("no_fly_zones", {})

    if not cfg or not bool(cfg.get("enabled", False)):
        return NoFlyZoneSet([], enabled=False)

    margin = float(cfg.get("reserve_margin_m", 0.0))
    zones: List[NoFlyZone] = []
    for spec in cfg.get("zones", []) or []:
        if not spec.get("enabled", True):
            continue
        ztype = str(spec.get("type", "circle")).strip().lower()
        name = str(spec.get("name", f"NFZ-{len(zones)}"))
        if ztype == "circle":
            center = spec.get("center") or [0.0, 0.0]
            radius = float(spec.get("radius", 0.0))
            if radius <= 0:
                continue
            geom = Point(float(center[0]), float(center[1])).buffer(radius)
        elif ztype == "polygon":
            points = spec.get("points") or []
            if len(points) < 3:
                continue
            ring = [(float(p[0]), float(p[1])) for p in points]
            geom = Polygon(ring)
            if not geom.is_valid:
                geom = geom.buffer(0)
        elif ztype == "bbox":
            b = spec.get("bbox")
            if not b or len(b) != 4:
                continue
            geom = box(float(b[0]), float(b[1]), float(b[2]), float(b[3]))
        else:
            continue
        zones.append(NoFlyZone(name, geom, margin=margin, raw=geom))

    return NoFlyZoneSet(zones, enabled=bool(zones))


# ---------------------------------------------------------------------------
# 进程级缓存：禁飞区在单个进程内是静态的，避免每次 Environment 构造都重建几何
# ---------------------------------------------------------------------------
_CACHE: Optional[NoFlyZoneSet] = None


def get_no_fly_zones(refresh: bool = False) -> NoFlyZoneSet:
    global _CACHE
    if _CACHE is None or refresh:
        _CACHE = load_no_fly_zones()
    return _CACHE


def reset_no_fly_zones() -> None:
    """清空缓存（配置热重载 / 测试用例使用）。"""
    global _CACHE
    _CACHE = None
