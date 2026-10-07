# -*- coding: utf-8 -*-
"""#69-B source-leg 语义夹具：A/B/C/D 四组，**全部走真实 planner 出口**。

上一版这三组测的是我复刻的标签逻辑 ⇒ 按 BI 标准不算通过（"复刻断言"只能证明我的复制品自洽）。
本版改为调用 `Environment.plan_route_for_tasks`（真实装配 + 真实 A*），只检查它产出的航点标签表。

四组与各自要钉住的东西：
  A direct          无障碍直达            ⇒ source leg 末点带 'source'，且全表恰一个 source 标签
  B detour          中间必穿楼需绕障       ⇒ transit 若干 + 服务航点 'source'；**不要求坐标精确等于 source**
  C regression      #69-A 确认的 bug 形态   ⇒ 修复后该服务航点仍被标 'source'（旧代码此处会漏标/错标）
  D forced cleanup  无送达证据却进 completion ⇒ C1 必须 RED（由 test_c1_lifecycle_gate 的
                    C1_FACE=forced_cleanup 面承担，本文件只做一条轻量哨兵，避免两处判据漂移）

纪律：不改 planner、不新增精确 goal 点、不改 destination 语义、不改 cleanup accounting。
"""
from __future__ import annotations

import math
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class SourceLegSemantics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["SWARM_BALANCE_SIM_CONFIG"] = str((ROOT / "config" / "simulation.json").resolve())
        for p in (str(ROOT), str(ROOT / "frontend")):
            if p not in sys.path:
                sys.path.insert(0, p)
        from environment import Environment
        cls.Environment = Environment
        cls.OSM = str(ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm")
        env = Environment(cls.OSM, episode_max_steps=2)
        env.reset(seed=40913)
        cls.env = env
        bb = env.global_bounds
        cls.cx = (bb[0] + bb[2]) / 2.0
        cls.cy = (bb[1] + bb[3]) / 2.0

    # ------------------------------------------------------------------
    def _route_tags(self, start, src, dst):
        """用真实规划器为一条任务链生成带标签航点表。"""
        class _T:
            def __init__(s, a, b):
                s._a, s._b = tuple(a[:2]), tuple(b[:2])
            def get_source(s): return s._a
            def get_destination(s): return s._b
        d = self.env.drones[0]
        d.x, d.y = float(start[0]), float(start[1])
        route = self.env.plan_route_for_tasks(d, [_T(src, dst)])
        return [(p[0], p[1], p[2]) for p in route], (tuple(src[:2]), tuple(dst[:2]))

    def _leg_slice(self, tags, src, dst):
        """切出 source leg：从表头到第一个 dest 标签之前。"""
        end = next((i for i, t in enumerate(tags) if t[2] == 'dest'), len(tags))
        return tags[:end], tags[end:]

    # ---------------- A. direct -------------------------------------
    def test_A_direct_has_exactly_one_source_tag(self):
        if not self.env.is_path_clear((self.cx, self.cy), (self.cx + 5.0, self.cy)):
            self.skipTest("[A_NEEDS_CLEAR_CORRIDOR] 世界未给出直达走廊，改日重取坐标")
        start = (self.cx, self.cy)
        src = (self.cx + 5.0, self.cy)
        dst = (self.cx + 400.0, self.cy)
        tags, (s, e) = self._route_tags(start, src, dst)
        leg, rest = self._leg_slice(tags, s, e)
        kinds = [t[2] for t in leg]
        self.assertEqual(kinds.count('source'), 1,
                         f"[A_SOURCE_TAG_COUNT] {kinds} ⇒ source leg 应恰有一个服务航点")
        self.assertEqual(kinds[-1], 'source', "[A_SOURCE_NOT_LAST] 服务航点必须是该 leg 的末点")
        self.assertTrue(any(t[2] == 'dest' for t in rest), "[A_NO_DEST_LEG] dest leg 缺失")

    # ---------------- B. detour -------------------------------------
    def test_B_detour_service_waypoint_is_last_of_leg(self):
        """必穿楼 ⇒ 有 transit 航点；服务航点仍是 leg 末点，且不要求其坐标等于 source。"""
        hs = getattr(self.env, "high_buildings", []) or []
        if not hs:
            self.skipTest("[B_NO_OBSTACLE_IN_WORLD] 本机环境无 >20 m 建筑，detour 分支无从触发")
        b = hs[0]["geometry"].bounds                      # (minx,miny,maxx,maxy)
        bcx, bcy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
        span = max(b[2] - b[0], b[3] - b[1], 1.0)
        start, src = (bcx - span * 3, bcy), (bcx + span * 3, bcy)
        if self.env.is_path_clear(start, src):
            self.skipTest("[B_LINE_NOT_BLOCKED] 该起终点对未穿越障碍，换对再测")
        tags, (s, e) = self._route_tags(start, src, src)  # dst 同 src 无关紧要，只看 source leg
        leg, _ = self._leg_slice(tags, s, e)
        kinds = [t[2] for t in leg]
        self.assertGreater(len(leg), 1, "[B_NO_TRANSIT] 绕障却没产生 transit 航点")
        self.assertEqual(kinds.count('source'), 1, f"[B_SOURCE_TAG_COUNT] {kinds}")
        self.assertEqual(kinds[-1], 'source', "[B_SERVICE_NOT_LAST]")
        # 关键：服务航点允许与 source 不精确相等（A* <1m 容差是既有模型语义）
        near = math.hypot(leg[-1][0] - s[0], leg[-1][1] - s[1])
        self.assertLess(near, 1.5,
                        f"[B_SERVICE_TOO_FAR] 服务航点距 source {near:.3f} m，超出既有容差语义")
        # transit 航点**不得**带 source 标签：除末点外计数必须为 0
        self.assertEqual(kinds[:-1].count('source'), 0, "[B_TRANSIT_MISLABELED]")

    # ---------------- C. regression（#69-A 确认的 bug 形态）----------
    def test_C_regression_service_point_gets_load_semantics(self):
        """旧缺陷：服务航点非精确 source 时标签虽在、消费侧还要坐标严格相等 ⇒ 永不取货。

        修复后判据只剩标签一条 ⇒ 这里验证「弹出该航点即可解锁取货」：
        即 source leg 末点必须携带 'source' 标签（消费侧据此写 load_time）。
        若哪天有人把坐标相等判据加回去，本用例不会红 —— 所以真正的守卫是 C1 的 R2 与 D 面。
        """
        hs = getattr(self.env, "high_buildings", []) or []
        if not hs:
            self.skipTest("[C_NO_OBSTACLE_IN_WORLD]")
        b = hs[0]["geometry"].bounds
        bcx, bcy = (b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0
        span = max(b[2] - b[0], b[3] - b[1], 1.0)
        start, src = (bcx - span * 3, bcy), (bcx + span * 3, bcy)
        if self.env.is_path_clear(start, src):
            self.skipTest("[C_LINE_NOT_BLOCKED]")
        tags, (s, e) = self._route_tags(start, src, src)
        leg, _ = self._leg_slice(tags, s, e)
        self.assertEqual(leg[-1][2], 'source', "[C_REGRESSION_STILL_PRESENT] 服务航点没拿到 source 语义")
        # 并且这个点的坐标**不必**等于 source —— 若等于则说明走了 direct 分支，测不到回归点
        exact = (abs(leg[-1][0] - s[0]) < 1e-9 and abs(leg[-1][1] - s[1]) < 1e-9)
        print(f"[C_INFO] 服务航点是否精确等于 source: {exact}"
              f"（False 才是真正覆盖到容差抵达这条路径）")

    # ---------------- D. 哨兵（主判据在 C1 forced_cleanup 面）---------
    def test_D_consumer_requires_label_only(self):
        """静态守卫：消费侧不得再出现「标签 + 坐标严格相等」两套判据并存。"""
        src = pathlib.Path(ROOT / "frontend" / "environment.py").read_text(encoding="utf-8")
        i = src.find("popped[2] == 'source'")
        self.assertGreater(i, 0, "[D_CONSUMER_GONE] 找不到取货消费块，检查是否被改名")
        block = src[i:i + 900]
        self.assertNotIn("get_source() == source_pos", block,
                         "[D_DOUBLE_CRITERION_REINTRODUCED] 坐标严格相等判据被加回来了")


if __name__ == "__main__":
    unittest.main(verbosity=2)
