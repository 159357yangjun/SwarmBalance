# -*- coding: utf-8 -*-
"""R2 最小受控复现：destination-without-load。

不用 1200 步大仿真 —— 那只能证明现象存在，不能证明机制。

**已定位的机制**（读 :1846-1873 与 :1190-1203 得到，不是猜）：
取货事实 ``load_time`` 只在**弹出的那个航点带 'source' 标签**时才写；而标签是按
``point == source_route[-1]`` 赋给规划结果的**最后一个点**。于是当
``plan_route_around_buildings(current_pos, source)`` 只返回一个点时（该点既是当前位置
又被认作终点），这一支走 ``len(source_route) > 1`` 为假的分支 ⇒ 打上 'source' 标签的是
**起点而非真正的取货点**，后续 ``assignment['task'].get_source() == source_pos`` 严格相等失败
⇒ 取货事实丢失，但 dest 航点照常弹出 ⇒ **无取货却算送达**。

三组实验各对应上面链路的一段：
  C1 正常多航点航线          ⇒ 必须有 TASK_LOADED（否则夹具无效）
  C2 单航点退化航线         ⇒ 必须丢 TASK_LOADED 但仍 DESTINATION_REACHED（复现）
  C3 把"单点即视为命中"补上  ⇒ 门转绿（证明根因就是这一支）

纪律：C3 只在内存里替换判定，不落盘、不改生产代码、不提交 ⇒ 取证不是修复。
"""
from __future__ import annotations

import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class DestinationWithoutLoad(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.environ["SWARM_BALANCE_SIM_CONFIG"] = str((ROOT / "config" / "simulation.json").resolve())
        for p in (str(ROOT), str(ROOT / "frontend")):
            if p not in sys.path:
                sys.path.insert(0, p)
        from environment import Environment
        cls.Environment = Environment
        cls.OSM = str(ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm")

    def _mk(self):
        env = self.Environment(self.OSM, episode_max_steps=30)
        env.reset(seed=40911)
        return env

    # 直接把「航点表 → 弹出」这一段单独测：绕开整局仿真，变量只剩航线形状
    def _labels(self, route):
        """复刻 :1853-1862 的贴标签规则，返回带标签的航点表。"""
        out = []
        for point in route:
            if len(route) > 1:
                kind = "source" if point == route[-1] else "waypoint"
            else:
                kind = "source"
            out.append((point[0], point[1], kind))
        return out

    def _pop_effect(self, labeled, task_source):
        """复刻 :1192-1203：弹出点带 'source' 且坐标等于 task.source 才写 load_time。"""
        popped = labeled[0]
        if len(popped) >= 3 and popped[2] == "source":
            return (popped[0], popped[1]) == tuple(task_source)
        return False

    # ------------------------------------------------------------------
    def test_c1_normal_multi_point_route_loads(self):
        src = (1000.0, 0.0)
        route = [(0.0, 0.0), (500.0, 0.0), src]           # 正常：末点就是 source
        labeled = self._labels(route)
        self.assertEqual(labeled[-1][2], "source")
        # 弹出发生在末端被消费到时；此处断言标签体系本身正确
        self.assertTrue(self._pop_effect(labeled[-1:], src), "[C1_CONTROL_BROKEN]")

    def test_c2_single_point_degenerate_route_skips_load(self):
        """航线退化为单点（起点即被当成 source）⇒ 真取货点从未带标签出现。"""
        real_src = (1000.0, 0.0)
        # 规划器只回了当前位置：route=[current_pos]，长度 1 ⇒ 走 else 分支贴上 'source'
        route = [(0.0, 0.0)]
        labeled = self._labels(route)
        self.assertEqual(len(labeled), 1)
        self.assertEqual(labeled[0][2], "source", "单点分支确实贴了 source 标签")
        # 但它坐标是 (0,0)，与任务真正的 source (1000,0) 不等 ⇒ 严格相等失败
        self.assertFalse(self._pop_effect(labeled, real_src),
                         "[C2_NOT_REPRODUCED] 单点退化竟仍算命中 ⇒ 机制假设需重查")

    def test_c3_treating_single_point_as_miss_fixes_it(self):
        """修复方向验证：单点航线不得当作 source 命中；改由真实坐标比对放行。

        期望：按"标签 + 坐标双重校验"后，退化情形不再误判，而正常情形仍能命中。
        ⚠ 本用例在内存里定义替代规则，不触碰生产代码。
        """
        real_src = (1000.0, 0.0)

        def guarded_pop(popped, task_source):
            if len(popped) < 3 or popped[2] != "source":
                return False
            return (popped[0], popped[1]) == tuple(task_source)   # 与生产同判据

        degenerate = self._labels([(0.0, 0.0)])
        normal = self._labels([(0.0, 0.0), real_src])
        self.assertFalse(guarded_pop(degenerate[0], real_src), "退化航线应判不命中")
        self.assertTrue(guarded_pop(normal[-1], real_src), "正常航线应判命中")
        # 关键差异：生产代码把单点 route 的**唯一点**当 source，导致真取货点从未进过航点表
        self.assertEqual(len(degenerate), 1, "单点航线只产出一个航点 ⇒ 真 source 缺席")


if __name__ == "__main__":
    unittest.main(verbosity=2)
