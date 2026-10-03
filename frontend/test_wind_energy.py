# -*- coding: utf-8 -*-
"""E1（风能耗修正）的行为验证 —— 逐条带人工真值，且**必须证明风真的会咬**。

两条来自本轮实测的教训，写在这里是为了防止下一版又把测试写回假绿：
  · 默认 config 里 K_HEAD=K_TAIL=0 ⇒ 任何 wind_along 都乘 1.0。第一版 B4 因此红，
    而 B2/B3 用 `>=`/`<=` 在恒等情况下**照样绿** —— 那是"量具坏了却报通过"。
    ⇒ 单调性一律用严格不等号，并且先注入非零情景系数再断言。
  · "能生成计划 / 能返回数值"不等于"施加了该负载"（同 grid 块 G5 的教训）。

符号约定（与 frontend/drone.py:_wind_factor 一致）：**wind_along 正=逆风、负=顺风**。
情景系数是 assumption（无厂商公布、无实机日志可拟合），本文件不声称它们是真值。
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "frontend"))
os.environ.setdefault("SWARM_BALANCE_SIM_CONFIG", str(ROOT / "config" / "simulation.json"))

import drone as D  # noqa: E402

K_HEAD, K_TAIL = 0.05, 0.03   # 只在测试内注入的情景系数，不写进正式配置


class WindScenario(unittest.TestCase):
    """公共夹具：进入时挂上情景系数，离开时还原 —— 否则测试之间会串味。"""

    def setUp(self):
        self._saved = (D.WIND_ENABLED, D.WIND_ENERGY_HEADWIND_PER_MS,
                       D.WIND_ENERGY_TAILWIND_PER_MS, D.WIND_FACTOR_FLOOR, D.WIND_FACTOR_CEIL)
        D.WIND_ENABLED = True
        D.WIND_ENERGY_HEADWIND_PER_MS = K_HEAD
        D.WIND_ENERGY_TAILWIND_PER_MS = K_TAIL

    def tearDown(self):
        (D.WIND_ENABLED, D.WIND_ENERGY_HEADWIND_PER_MS, D.WIND_ENERGY_TAILWIND_PER_MS,
         D.WIND_FACTOR_FLOOR, D.WIND_FACTOR_CEIL) = self._saved

    def make(self, dtype="heavy_cargo"):
        return D.Drone(drone_id="t", x=0.0, y=0.0, drone_type=dtype)

    def energy(self, load, wind, dist):
        d = self.make()
        d.current_load = load
        return d.consume_battery(dist, wind)


class WindBehaviorTests(WindScenario):
    def test_b1_wind_zero_and_none_reproduce_e0_bit_for_bit(self):
        """B1 wind=0 / None ⇒ 与 E0 公式逐位相同（即使 K 已开，零风也必须无副作用）。"""
        dist, load = 1234.5, 7.5
        d = self.make(); d.current_load = load
        e0 = dist * d.battery_consumption_base * (
            1 + (load / d.carrying_capacity) * d.battery_load_penalty_factor)
        for w in (None, 0.0):
            got = self.energy(load, w, dist)
            self.assertAlmostEqual(got, e0, places=9,
                                   msg="wind_along=%r 未退回 E0：%r vs %r" % (w, got, e0))

    def test_b2_headwind_strictly_increases_energy(self):
        """B2 逆风增大 ⇒ 耗能严格上升（不是 >=；>= 在 K=0 时会假绿）。"""
        seq = [self.energy(0.0, w, 1000.0) for w in (0.0, 1.0, 2.0, 3.0, 6.0, 12.0)]
        for i in range(1, len(seq)):
            self.assertGreater(seq[i], seq[i - 1],
                               "逆风序列非严格递增：%s" % ["%.2f" % v for v in seq])

    def test_b3_tailwind_strictly_decreases_but_stays_positive(self):
        """B3 顺风增强 ⇒ 严格下降但恒 >0（绝不允许负耗能或给电池充电）。"""
        prev = self.energy(0.0, 0.0, 1000.0)
        for w in (-1.0, -3.0, -6.0, -12.0):
            e = self.energy(0.0, w, 1000.0)
            self.assertLess(e, prev, "顺风 %r 没比上一档更省 ⇒ K_TAIL 没吃到风" % w)
            self.assertGreater(e, 0.0, "顺风 %r 出现非正耗能" % w)
            prev = e

    def test_b4_headwind_gt_calm_gt_tailwind_at_same_distance_and_load(self):
        """B4 三点式判别式：同距离同载荷下 逆风 > 无风 > 顺风。

        这一条就是第一版红的地方 —— 它抓到的是"默认 K=0 时风完全不起作用"。
        保留为回归用例：以后谁把 K 改回 0 或删掉倍率，这里立刻红。
        """
        for head, tail in ((3.0, -3.0), (6.0, -6.0)):
            h, c, t = (self.energy(0.0, w, 2000.0) for w in (head, 0.0, tail))
            self.assertGreater(h, c, "逆风 %s 未高于静风" % head)
            self.assertGreater(c, t, "静风未高于顺风 %s" % tail)

    def test_b5_golden_case_wh_and_coefficient_by_hand(self):
        """B5 golden case：手算得出来的 Wh，程序必须落在上面。

        heavy_cargo base=0.142 Wh/m，空载 ⇒ 载荷倍率 1；逆风 6 m/s ⇒ factor=1+0.05×6=1.30
        飞 1 km ⇒ 1000 × 0.142 × 1 × 1.30 = **184.6 Wh**（人工可验）。
        顺风 6 m/s ⇒ factor=1−0.03×6=0.82 ⇒ 1000×0.142×0.82 = **116.44 Wh**。
        """
        d = self.make()
        self.assertAlmostEqual(d.battery_consumption_base, 0.142, places=6)
        self.assertAlmostEqual(d._wind_factor(6.0), 1.30, places=9)
        self.assertAlmostEqual(d.consume_battery(1000.0, 6.0), 184.6, places=6)
        self.assertAlmostEqual(self.energy(0.0, -6.0, 1000.0), 116.44, places=6)

    def test_b6_extreme_inputs_bounded_or_rejected(self):
        """B6 极端输入：有限大风被上界夹住，非有限风报错而不是静默。"""
        self.assertLessEqual(self.energy(0.0, 1e9, 1000.0),
                             1000.0 * 0.142 * D.WIND_FACTOR_CEIL + 1e-9,
                             "逆风上界失效 ⇒ 一次就能把电量掏空")
        self.assertGreaterEqual(self.energy(0.0, -1e9, 1000.0),
                                1000.0 * 0.142 * D.WIND_FACTOR_FLOOR - 1e-9,
                                "顺风下界失效")
        for bad in (float("nan"), float("inf")):
            with self.assertRaises(ValueError, msg="wind_along=%r 应报错而非静默通过" % bad):
                self.energy(0.0, bad, 1000.0)

    def test_b7_battery_ledger_is_the_single_source(self):
        """B7 返回值 == 实际扣减 ⇒ environment 的 prev−now 统计自动吃到风耗，无需第二套账。"""
        d = self.make()
        before = d.current_battery
        spent = d.consume_battery(5000.0, 6.0)
        self.assertAlmostEqual(before - d.current_battery, spent, places=9)

    def test_b8_direction_sign_convention(self):
        """B8 符号约定：东风(u>0)下，向东飞=顺风(负)、向西飞=逆风(正)、向北=横风(0)。"""
        d = self.make(); d.set_wind(wind_u=6.0, wind_v=0.0)
        self.assertAlmostEqual(d._wind_along_for(100.0, 0.0, 100.0), -6.0, places=9)
        self.assertAlmostEqual(d._wind_along_for(-100.0, 0.0, 100.0), 6.0, places=9)
        self.assertAlmostEqual(d._wind_along_for(0.0, 100.0, 100.0), 0.0, places=9)
        self.assertAlmostEqual(
            d._wind_along_for(70.71067811865476, 70.71067811865476, 100.0),
            -6.0 * math.sqrt(0.5), places=6, msg="45 度斜风的沿程分量应是 6*cos45")


class ShippedDefaultsTests(unittest.TestCase):
    def test_b9_shipped_config_keeps_wind_off(self):
        """B9 正式默认关风：config 里没有 wind_energy.enabled ⇒ 全链路退回 E0。

        这条守的是约束"不改正式默认风值"。若有人把风写进默认配置，这里红。
        """
        cfg = json.loads((ROOT / "config" / "simulation.json").read_text(encoding="utf-8"))
        we = cfg.get("drone", {}).get("wind_energy")
        self.assertTrue(we is None or not we.get("enabled", False),
                        "config/simulation.json 默认开了风 ⇒ %r" % we)
        self.assertFalse(D.WIND_ENABLED)
        self.assertEqual(D.WIND_ENERGY_HEADWIND_PER_MS, 0.0)
        self.assertEqual(D.WIND_ENERGY_TAILWIND_PER_MS, 0.0)

    def test_b10_with_shipped_defaults_any_wind_is_a_no_op(self):
        """B10 阴性对照：默认配置下 ±6 m/s 与 0 给出同一个数 ⇒ 钉死"结构存在但未启用"。

        为什么必须有这条：只测 B2/B3（注入系数后有效）无法区分
        "代码有牙但默认关着" 与 "代码根本没接上"。
        """
        vals = [D.Drone(drone_id="t", x=0.0, y=0.0, drone_type="heavy_cargo")
                .consume_battery(1000.0, w) for w in (6.0, -6.0, 0.0)]
        self.assertEqual(vals[0], vals[1], "默认 K=0 却出现方向差 ⇒ 有东西在偷偷生效")
        self.assertEqual(vals[0], vals[2], "默认 K=0 却出现风力差 ⇒ 有东西在偷偷生效")


if __name__ == "__main__":
    unittest.main()
