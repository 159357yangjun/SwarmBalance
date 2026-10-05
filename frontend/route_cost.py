# -*- coding: utf-8 -*-
"""RouteCostProvider —— 让调度器的距离口径可切换（Phase 1B-1）。

设计约束（用户冻结）：**本阶段只替换 distance cost。**
ETA / energy / range feasibility 一律保持原逻辑不变 —— 否则结果变化无法归因到具体那一层。

两个实现：
  EuclideanRouteCostProvider    现状口径（对照组）。默认启用 ⇒ 未开实验时行为逐字不变。
  PlannedDistanceRouteCostProvider  实际航路距离（实验组），走 RoutePlanner。

为什么用 provider 而不是直接改 scheduler 里的 math.dist：
  1) 保留对照面是预注册假设 H0/H1 的前提（同一份代码只切一个开关）；
  2) 距离查询有真实成本（A* 非 O(1)），必须集中管理缓存与调用计数，
     散在三处改写会让"这次实验到底跑了多少次 A*"无从核对。

生效值注意：Greedy 的 candidate_limit 由 config/simulation.json:11 覆盖为 60（代码默认 1），
所以每次派单会对至多 60 个候选各测一次距离 ⇒ 调用量级 = 派单机会 × 候选数。
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

Point = Tuple[float, float]


def _euclid(a: Sequence[float], b: Sequence[float]) -> float:
    return ((float(a[0]) - float(b[0])) ** 2 + (float(a[1]) - float(b[1])) ** 2) ** 0.5


def _check_speed(speed_m_per_s: float) -> float:
    """ETA 的分母必须是个真的航速。

    不兜底：speed<=0 时若静默返回 inf/0，全体候选的 ETA 会退化成同一个值 ⇒
    reachability 分量悄悄失效（实现存在、无信息），那是最难查的一类假实验。
    """
    s = float(speed_m_per_s)
    if not (s > 0.0):
        raise ValueError("[BAD_SPEED] eta 需要正的航速（m/s），实得 %r" % (speed_m_per_s,))
    return s


class EuclideanRouteCostProvider:
    """现状口径：纯欧氏直线。名字/返回与 GreedyScheduler.euclidean_distance 一致。"""

    name = "euclidean"

    def __init__(self) -> None:
        self.calls = 0
        self.cache_hits = 0
        self.eta_calls = 0

    def distance(self, a: Sequence[float], b: Sequence[float]) -> float:
        self.calls += 1
        return _euclid(a, b)

    def batch(self, origin: Sequence[float], targets: List[Sequence[float]]) -> List[float]:
        self.calls += len(targets)
        return [_euclid(origin, t) for t in targets]

    def eta(self, a: Sequence[float], b: Sequence[float], speed_m_per_s: float) -> float:
        """预计耗时，单位 = env-step。

        口径与执行侧同源：`drone.py:259 max_distance = v * time_step` ⇒
        一个 env-step 飞 `speed × STEP_SECONDS` 米 ⇒ 耗时 = 距离 ÷ (speed × STEP_SECONDS)。
        刻意**不**写成"秒"再让调用方换算 —— 登记表 M5 的同族缺陷就是分子按步、分母按秒，
        只在 time_step=1.0 时凑巧一致。门 G12 用改 time_step 的方式钉这条。
        """
        from drone import STEP_SECONDS
        self.eta_calls += 1
        return _euclid(a, b) / (_check_speed(speed_m_per_s) * STEP_SECONDS)

    def stats(self) -> Dict[str, int]:
        return {"provider": 0, "calls": self.calls, "cache_hits": 0, "planner_calls": 0,
                "eta_calls": self.eta_calls}



class PlannedDistanceRouteCostProvider:
    """实验口径：drone->pickup 走 RoutePlanner 的实际航路长度与由它导出的耗时。

    Phase 1B-1 只替换【距离】；1B-2 追加 `eta()`，但 eta 严格定义为 distance/speed 的
    同一份量（复用 `_cache` ⇒ **不多一次 A\\***）。energy / range feasibility 仍不在这里取数 ——
    那是 1B-3 的分界。

    ⚠ eta 是 distance 的单调仿射函数 ⇒ 候选集【内部】的相对排序与 1B-1 完全一致。
    所以 1B-2 的判别式不是"排序变了"，而是"同一候选在两面的 reachability 值不同且进了总分"
    （门 G10）。这条写在类文档里，防止以后有人拿"排序没变"当"ETA 无效"的证据。
    """

    name = "planned_distance"

    def __init__(self, planner) -> None:
        self.planner = planner
        self.calls = 0
        self.cache_hits = 0
        self.eta_calls = 0
        self._cache: Dict[Tuple[float, float, float, float], float] = {}
        # 退化对（起终点重合）单独计数：它会让 ratio 无定义，不能混进分位统计
        self.degenerate = 0
        # 实验证人（Phase 1B-1 H1 的追溯面）：planner 给出 route != euclid 的候选腿。
        # 只有这些 OD 才【有可能】改变 Greedy 的排序 ⇒ KPI 若变化必须能落到这里。
        # 上限防内存：episode 里唯一 OD 量级为几百~几千，留 20000 条绰绰有余。
        self.deltas: List[Dict[str, float]] = []
        self._delta_cap = 20000

    def _record_delta(self, a, b, e, d):
        if len(self.deltas) >= self._delta_cap:
            return
        self.deltas.append({"ax": round(float(a[0]), 2), "ay": round(float(a[1]), 2),
                           "bx": round(float(b[0]), 2), "by": round(float(b[1]), 2),
                           "euclid": e, "planned": d, "ratio": d / e})

    @staticmethod
    def _key(a, b):
        # 与 RoutePlanner 内部 round_pos(2) 同精度量化，避免亚毫米级抖动击穿缓存
        return (round(float(a[0]), 2), round(float(a[1]), 2),
                round(float(b[0]), 2), round(float(b[1]), 2))

    def distance(self, a: Sequence[float], b: Sequence[float]) -> float:
        self.calls += 1
        k = self._key(a, b)
        hit = self._cache.get(k)
        if hit is not None:
            self.cache_hits += 1
            return hit
        e = _euclid(a, b)
        if e <= 1e-9:
            self.degenerate += 1
            self._cache[k] = 0.0
            return 0.0
        from route_planner import RouteRequest
        res = self.planner.plan(RouteRequest(start=(float(a[0]), float(a[1])),
                                             goal=(float(b[0]), float(b[1]))))
        if res.direct or res.fallback:
            # direct：直线本就通畅；fallback：A* 无解、环境也会按直线飞 ⇒ 两者都取欧氏
            d = e
        else:
            prev = (float(a[0]), float(a[1]))
            d = 0.0
            for p in res.waypoints:
                d += _euclid(prev, (float(p[0]), float(p[1])))
                prev = (float(p[0]), float(p[1]))
            if abs(d - e) > 1e-9:
                self._record_delta(a, b, e, d)
        self._cache[k] = d
        return d

    def batch(self, origin: Sequence[float], targets: List[Sequence[float]]) -> List[float]:
        return [self.distance(origin, t) for t in targets]

    def eta(self, a: Sequence[float], b: Sequence[float], speed_m_per_s: float) -> float:
        """航路耗时 = 航路长度 ÷ (speed × STEP_SECONDS)，单位 env-step。

        先调 `distance()` 而不是自己算直线：这样 ETA 与距离口径**必然同源**，
        不可能出现"排序用绕障、时效用直线"（那正是 1B-1 之后留下的裂缝，本方法就是去修它的）。
        复用 _cache ⇒ 与 distance 同一批 OD 不额外触发 A*。
        """
        from drone import STEP_SECONDS
        self.eta_calls += 1
        return self.distance(a, b) / (_check_speed(speed_m_per_s) * STEP_SECONDS)

    def stats(self) -> Dict[str, int]:
        return {"calls": self.calls, "cache_hits": self.cache_hits,
                "unique_od": len(self._cache), "degenerate": self.degenerate,
                "deltas": len(self.deltas), "eta_calls": self.eta_calls}


def make_provider(kind: str, planner=None):
    """工厂：kind ∈ {euclidean, planned_distance}。未知值直接报错，不做静默兜底。"""
    k = (kind or "euclidean").strip().lower()
    if k in ("euclidean", "e", ""):
        return EuclideanRouteCostProvider()
    if k in ("planned_distance", "planned", "astar", "route"):
        if planner is None:
            raise ValueError("[PLANNER_REQUIRED] planned_distance 需要 RoutePlanner 实例")
        return PlannedDistanceRouteCostProvider(planner)
    raise ValueError(f"[UNKNOWN_COST_PROVIDER] {kind!r}；可用: euclidean | planned_distance")
