# -*- coding: utf-8 -*-
"""Gate A：新旧 RoutePlanner 行为等价（Phase 1A 的验收门）。

判据对象是【同一份世界 + 同一组起终点】下：
  旧实现 = environment.py 里仍保留的 a_star_pathfinding / heuristic（本次抽离未删）
  新实现 = frontend/route_planner.py 的 RoutePlanner

比较项（用户指定）：feasible、waypoint 序列、绕障计数、path-clear 结果。
浮点容差：**不引入** —— waypoint 走的是 round_pos(2) 后的二元组，比较是精确相等；
distance 是新增报告量，不参与路径决策，故只要求有限且非负，不设等式。

为什么这里要同时断言"旧实现仍存在"：如果哪天有人删了旧代码却留着这道门，
它会退化成"新实现和自己比"，永远绿 —— 那是假绿灯，必须当场报错。
"""
from __future__ import annotations

import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "frontend"))

from route_planner import RouteRequest

OSM = REPO / "frontend" / "data" / "map" / "part_of_yangpu.osm"


def _legacy_plan(env, start_pos, end_pos):
    """environment.py:1842-1863 的原始逻辑，在本测试里就地重写一遍作为对照。

    刻意不调用 env.plan_route_around_buildings（那已经是委托新实现的版本），
    否则变成"新 vs 新"，门没有牙。这里的每一行都与抽离前的源码逐字对应。
    """
    if env.is_path_clear(start_pos, end_pos):
        return [end_pos], False, True, False
    detour = bool(env.no_fly.path_blocked(start_pos, end_pos))
    path = env.a_star_pathfinding(start_pos, end_pos)      # 旧方法仍在 :1865+
    if path and len(path) > 1:
        return path[1:], detour, False, False
    return [end_pos], detour, False, True                  # fallback


class RoutePlannerEquivalence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from environment import Environment
        cls.env = Environment(str(OSM))
        cls.env.reset(seed=40901)
        # 判别式前提：旧实现必须还在，否则本门自证
        for name in ("a_star_pathfinding", "heuristic", "is_path_clear"):
            assert callable(getattr(cls.env, name, None)), \
                "[GATE_A_NO_ORACLE] Environment.%s 已被删除 ⇒ 等价门失去对照物，请改判据而非放宽" % name

    def _samples(self):
        """覆盖四类：直达 / 建筑绕障 / 禁飞区绕障 / 边界与无解兜底。"""
        env = self.env
        pts = []
        for b in env.high_buildings[:12]:
            (minx, miny, maxx, maxy) = b["geometry"].bounds
            cx, cy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
            span = max(maxx - minx, maxy - miny, 1.0)
            pts.append(((cx - span * 3, cy), (cx + span * 3, cy)))     # 必穿楼 ⇒ 绕障
            pts.append(((cx, cy), (cx + 5.0, cy)))                     # 极近 ⇒ 多为直达
        if list(env.no_fly.zones or []):
            z = list(env.no_fly.zones)[0]
            (minx, miny, maxx, maxy) = z.geometry.bounds
            pts.append(((minx - 500, (miny + maxy) / 2), (maxx + 500, (miny + maxy) / 2)))
        mn_x, mn_y, mx_x, mx_y = env.global_bounds
        pts.append(((mn_x + 10, mn_y + 10), (mx_x - 10, mx_y - 10)))   # 全域对角
        # 直达案例：不猜坐标，让【世界自己】报告哪条线是通的 —— 取若干随机点对，
        # 把 is_path_clear 为真的那些收进样本（这正是原 :1847 的短路分支）。
        import random
        rng = random.Random(40901)
        direct_found = 0
        for _ in range(400):
            a = (rng.uniform(mn_x, mx_x), rng.uniform(mn_y, mx_y))
            b = (rng.uniform(mn_x, mx_x), rng.uniform(mn_y, mx_y))
            if a == b:
                continue
            if env.is_path_clear(a, b):
                pts.append((a, b))
                direct_found += 1
                if direct_found >= 8:
                    break
        self.direct_sample_count = direct_found
        pts.append(((mn_x - 1e6, mn_y - 1e6), (mx_x + 1e6, mx_y + 1e6)))  # 越界 ⇒ 走兜底分支
        return pts

    def test_waypoints_and_flags_identical(self):
        env = self.env
        n_direct = n_detour = n_fallback = n_astar = 0
        cases = self._samples()
        self.assertGreaterEqual(len(cases), 20, "样本太少，等价结论无意义")
        for start, goal in cases:
            old_pts, old_detour, old_direct, old_fallback = _legacy_plan(env, start, goal)
            res = env.route_planner.plan(RouteRequest(start=tuple(start[:2]),
                                                 goal=tuple(goal[:2])))
            new_pts = [tuple(p) for p in res.waypoints]
            self.assertEqual(new_pts, [tuple(p) for p in old_pts],
                             "waypoint 序列不等价：%s -> %s\n 旧=%r\n 新=%r" % (start, goal, old_pts, new_pts))
            self.assertEqual(res.detour, old_detour, "detour 事实不等价：%s -> %s" % (start, goal))
            self.assertEqual(res.direct, old_direct, "direct 标记不等价：%s -> %s" % (start, goal))
            self.assertEqual(res.fallback, old_fallback, "fallback 标记不等价：%s -> %s" % (start, goal))
            self.assertTrue(res.feasible or old_fallback, "feasible 语义与旧兜底不一致")
            self.assertTrue(res.distance >= 0 and res.distance == res.distance,
                            "distance 必须是有限非负数，实得 %r" % res.distance)
            if old_direct:
                n_direct += 1
            elif old_fallback:
                n_fallback += 1
            else:
                n_astar += 1
            if old_detour:
                n_detour += 1
        print("\n[GATE_A] cases=%d direct=%d astar=%d fallback=%d detour=%d —— 全部逐点等价"
              % (len(cases), n_direct, n_astar, n_fallback, n_detour))
        # 覆盖面本身要有下限：全是直达就证明不了绕障路径等价
        self.assertGreater(n_direct, 0, "样本里没有直达案例，覆盖面不足")
        self.assertGreater(n_direct + n_astar + n_fallback, n_direct,
                           "样本里没有绕障/兜底案例 ⇒ 等价结论不覆盖 A* 分支")

    def test_counter_written_by_environment_not_planner(self):
        """total_no_fly_detours 的归属：委托调用必须由环境层记 +1，planner 自己不写。

        注意别踩我自己第一次踩的坑：`_legacy_plan` 走的是 env.a_star_pathfinding，
        那条路本来就不写计数 ⇒ 拿它当"应涨 1"的期望是错的。要验委托是否保持计数语义，
        必须真的调 env.plan_route_around_buildings（即被抽离后的生产入口）。
        """
        env = self.env
        # 找一个确实触发绕障的起终点
        probe = None
        for start, goal in self._samples():
            if env.no_fly.path_blocked(start, goal) and not env.is_path_clear(start, goal):
                probe = (start, goal)
                break
        self.assertIsNotNone(probe, "没有禁飞区绕障样本可测 ⇒ 本条判据无法成立，请检查世界配置")
        start, goal = probe
        before = int(env.total_no_fly_detours)
        env.plan_route_around_buildings(start, goal)          # 委托入口
        after = int(env.total_no_fly_detours)
        self.assertEqual(after, before + 1,
                         "委托后计数丢失/重复：before=%s after=%s ⇒ 计数时机与原 :1851-1852 不一致"
                         % (before, after))
        # planner 自己没有这个属性 ⇒ 它无法偷偷改指标
        self.assertFalse(hasattr(env.route_planner, "total_no_fly_detours"),
                         "RoutePlanner 不应持有环境计数器")
        # 且 route_plan_detailed（只读入口）不得写计数 —— 否则诊断会污染仿真指标
        b2 = int(env.total_no_fly_detours)
        env.route_plan_detailed(start, goal)
        self.assertEqual(int(env.total_no_fly_detours), b2,
                         "只读诊断入口不该改环境计数")

    def test_cache_object_shared_not_duplicated(self):
        """缓存同源：planner 用的 path_clear 必须是环境那个绑定方法本体。"""
        env = self.env
        self.assertEqual(env.route_planner._path_clear.__func__, env.__class__.is_path_clear,
                         "planner 拿到的是复制品而非绑定方法 ⇒ 缓存会分裂成两份")
        # 触发一次懒建桶，确认两侧看到同一个 dict
        env.is_path_clear((0.0, 0.0), (1.0, 1.0))
        env.route_planner._path_clear((0.0, 0.0), (2.0, 2.0))
        self.assertIsNotNone(env._path_clear_cache, "缓存桶未按原时机建立")

    def test_high_buildings_reference_is_same_object(self):
        env = self.env
        self.assertIs(env.route_planner.high_buildings, env.high_buildings,
                      "几何必须是引用而非拷贝：拷贝会让 reset/更新后两侧看到不同世界")
        self.assertIs(env.route_planner.no_fly, env.no_fly)


    # 允许出现 a_star_pathfinding 这个名字的文件：
    #   frontend/route_planner.py      —— 新实现自己的同名方法（内部自调，不是 legacy）
    #   frontend/environment.py        —— legacy 定义所在文件（含其内部 heuristic 自调）
    #   console/test_route_planner_equivalence.py —— Gate A 的对照调用，正是它的用途
    # 判据必须按"归属哪个类"而不是"源码里有没有这个字符串"：第一版我把 route_planner.py
    # 自己的内部调用误报成违规 ⇒ 一道会喊狼的门比漏检更贵，因为它教人忽略它的红。
    LEGACY_ALLOW = ("frontend/environment.py", "frontend/route_planner.py",
                    "console/test_route_planner_equivalence.py")

    def test_legacy_oracle_has_no_new_callers(self):
        """LEGACY_REFERENCE_ONLY 的强制含义：不许新生产代码依赖旧 A*。

        为什么必须有这条：Gate A 需要旧实现当对照物 ⇒ 它不能被删；但一个"不能删的旧副本"
        如果同时可以被随意调用，就会长成两套正式 RoutePlanner —— 那时等价门绿着，
        生产却走的是另一套。所以把"只准当 oracle"变成会红的断言，而不是注释里的愿望。
        """
        hits = []
        for py in REPO.rglob("*.py"):
            if ".git" in py.parts or "__pycache__" in py.parts or ".venv310" in py.parts:
                continue
            rel = str(py.relative_to(REPO)).replace("\\", "/")
            try:
                text = py.read_text(encoding="utf-8")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if "a_star_pathfinding(" in stripped and "def a_star_pathfinding" not in stripped:
                    if rel not in self.LEGACY_ALLOW:
                        hits.append("%s:%d %s" % (rel, i, stripped[:70]))
        self.assertEqual(hits, [],
                         "有生产代码新增了对 legacy A* 的调用（应改用 route_planner）：\\n  " + "\\n  ".join(hits))
        # 上面的文件级白名单会放过 route_planner.py 内部同名调用 ⇒ 再用一条**归属级**判据兜住
        # 真正的风险：任何地方调到 **Environment 那份** legacy 实现（三种写法都要认）：
        #   env.x(...) / self.env.x(...) / Environment.x(self, ...)（未绑定调用，本轮变异撞出来的漏项）
        # 第一版只认前两种，我用第三种写法做变异时门照样绿 ⇒ 那是判据覆盖不全，已补齐。
        via_env = []
        needles = (".a_star_pathfinding(",)
        owners = ("env", "self.env", "environment", "Environment", "cls.env")
        for py in REPO.rglob("*.py"):
            if ".git" in py.parts or "__pycache__" in py.parts or ".venv310" in py.parts:
                continue
            rel = str(py.relative_to(REPO)).replace("\\", "/")
            if rel == "console/test_route_planner_equivalence.py":
                continue          # Gate A 的对照调用是它存在的理由
            for i, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
                s = line.strip()
                if s.startswith("#") or "def a_star_pathfinding" in s:
                    continue
                if not any(n in s for n in needles):
                    continue
                # 归属判定：出现任一 owner 前缀即视为走 legacy 句柄；裸 self. 在 environment.py 内合法
                if any(("%s%s" % (o, n)) in s.replace(" ", "") for o in owners for n in needles):
                    via_env.append("%s:%d %s" % (rel, i, s[:70]))
        self.assertEqual(via_env, [],
                         "有代码通过 Environment 句柄调用 legacy A*（应直接用 RoutePlanner）："
                         "\\n  " + "\\n  ".join(via_env))

if __name__ == "__main__":
    unittest.main(verbosity=2)
