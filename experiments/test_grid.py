# -*- coding: utf-8 -*-
"""`experiments/runner.py` 里 grid 块的判别式夹具（G1–G6）。

为什么这批测试必须先于能耗模型扩展存在：grid 是为修"上一轮 total_tasks 假标签"而加的，
它本身是新量具。新量具没有牙就冻结实验台，等于把"编排 bug"和"模型变化"重新混在一起。

每条测试都断言**施加了什么**，而不只是"生成了几格"——因为踩过的坑正是
"表面上扫两个变量，实际每格只带一个 patch"。
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiments import runner  # noqa: E402


def preset_of(grid_section):
    return {
        "base": {"seed": 900, "episode_steps": 3600, "repeats": 1},
        "algorithms": ["greedy"],
        "experiments": {
            "algorithm_comparison": {"enabled": False},
            "grid": dict(grid_section),
        },
    }


AXIS_A = {"name": "is", "values": [
    {"label": "is0.70", "patch": {"task_generation": {"realistic": {"interval_scale": 0.70}}}},
    {"label": "is0.40", "patch": {"task_generation": {"realistic": {"interval_scale": 0.40}}}},
]}
AXIS_B = {"name": "fleet", "values": [
    {"label": "f4", "patch": {"environment": {"num_drones": 4}}},
    {"label": "f6", "patch": {"environment": {"num_drones": 6}}},
    {"label": "f10", "patch": {"environment": {"num_drones": 10}}},
]}


class GridPlanTests(unittest.TestCase):
    def test_g1_cartesian_product_is_exact(self):
        """G1：2×3 两轴 ⇒ 恰好 6 格，且逐格标签与内容都对得上。"""
        plan = runner.build_plan(preset_of({"enabled": True, "axes": [AXIS_A, AXIS_B]}))
        self.assertEqual(len(plan), 6, "2×3 网格应产出 6 个计划，实得 %d" % len(plan))
        want = {"%s×%s" % (a, b) for a in ("is0.70", "is0.40") for b in ("f4", "f6", "f10")}
        got = {s.value for s in plan}
        self.assertEqual(got, want, "网格标签集合不符：多=%s 少=%s" % (got - want, want - got))
        self.assertEqual({s.variable for s in plan}, {"is×fleet"}, "横轴名应写两个旋钮名，不是'任务规模'")

    def test_g5_every_cell_carries_both_knobs(self):
        """G5（最重要）：每格的 patch 必须**同时**含两轴的键。

        这是本轮真实踩过的坑的反面：把两个变量写成两个独立块时，每格只带一个 patch，
        交叉负载一次都没施加过，而计划数看起来完全正常。
        """
        plan = runner.build_plan(preset_of({"enabled": True, "axes": [AXIS_A, AXIS_B]}))
        for s in plan:
            isv = s.patch.get("task_generation", {}).get("realistic", {}).get("interval_scale")
            nd = s.patch.get("environment", {}).get("num_drones")
            self.assertIsNotNone(isv, "%s 没带 interval_scale ⇒ 该轴静默丢失" % s.value)
            self.assertIsNotNone(nd, "%s 没带 num_drones ⇒ 该轴静默丢失" % s.value)
            self.assertIn(str(isv), s.value.split("×")[0], "%s 的标签与实际 patch 不符" % s.value)
            self.assertEqual(str(s.value.split("×")[1]).strip(), "f%s" % nd,
                             "%s 标签写的架数与 patch 里的不一致" % s.value)

    def test_g2_single_axis_is_a_supported_one_dimensional_scenario(self):
        """G2：单轴 grid **允许**，且必须产出该轴的每一格。

        为什么从"报错"改成"支持"：E1 的风情景（wind_along_ms = 0/+3/+6/-3）就是一维列表，
        它同样需要"标签与 patch 由同一段代码核对"这条保障。原先禁 <2 轴是我把夹具写窄了 ——
        真实用法当场撞上了它（e0_baseline 单轴预设被拒），所以判据修正为：只禁 0 轴。
        """
        plan = runner.build_plan(preset_of({"enabled": True, "axes": [AXIS_A]}))
        self.assertEqual(len(plan), 2, "单轴两值应产出 2 格，实得 %d" % len(plan))
        self.assertEqual({s.value for s in plan}, {"is0.70", "is0.40"})
        self.assertEqual({s.variable for s in plan}, {"is"}, "单轴的横轴名不该硬拼第二个轴名")

    def test_g2b_zero_axis_fails_loudly(self):
        """G2b：0 轴 ⇒ 硬失败（静默返回空计划就是"跑成功了但什么都没测"）。"""
        with self.assertRaises(ValueError) as ctx:
            runner.build_plan(preset_of({"enabled": True, "axes": []}))
        self.assertIn("[GRID_AXES_EMPTY]", str(ctx.exception))

    def test_g3_missing_patch_fails_loudly(self):
        """G3：轴值缺 patch ⇒ 硬失败，不许静忽略那一格（否则分母会悄悄变小）。"""
        bad = {"name": "x", "values": [{"label": "nopatch"}]}
        with self.assertRaises(ValueError) as ctx:
            runner.build_plan(preset_of({"enabled": True, "axes": [bad, AXIS_B]}))
        self.assertIn("[GRID_PATCH_MISSING]", str(ctx.exception))

    def test_g4_empty_values_fails_loudly(self):
        """G4：某轴 values 为空 ⇒ 硬失败。

        先红证据：修之前这里静默跳过整张网格，build_plan 返回不含任何 grid 格的计划、
        进程退码 0 —— 即"跑成功了但什么都没测"。
        """
        empty = {"name": "empty", "values": []}
        with self.assertRaises(ValueError) as ctx:
            runner.build_plan(preset_of({"enabled": True, "axes": [empty, AXIS_B]}))
        self.assertIn("[GRID_AXIS_EMPTY]", str(ctx.exception))

    def test_g6_base_config_not_mutated_across_cells(self):
        """G6：deep-merge 不得污染后续格（dict 引用共享是这里的典型隐蔽错）。"""
        axes = [
            {"name": "a", "values": [
                {"label": "a1", "patch": {"environment": {"num_drones": 4}}},
                {"label": "a2", "patch": {"environment": {"num_drones": 6}}},
            ]},
            {"name": "b", "values": [
                {"label": "b1", "patch": {"nest": {"berths": 1}}},
                {"label": "b2", "patch": {"nest": {"berths": 9}}},
            ]},
        ]
        plan = runner.build_plan(preset_of({"enabled": True, "axes": axes}))
        by = {s.value: s.patch for s in plan}
        self.assertEqual(len(by), 4, "四格标签应有四个不同 patch")
        # 每一格只应看到自己那两个值，不该看到兄弟格的残留
        for val, patch in by.items():
            a_lbl, b_lbl = val.split("×")
            expect_drone = 4 if a_lbl == "a1" else 6
            expect_berth = 1 if b_lbl == "b1" else 9
            self.assertEqual(patch["environment"]["num_drones"], expect_drone,
                             "%s 的机队被别的格污染：%s" % (val, patch))
            self.assertEqual(patch["nest"]["berths"], expect_berth,
                             "%s 的泊位被别的格污染：%s" % (val, patch))
        # 生成器自身的输入字典也不许被改：改了下一轮 preset 复用就会串味
        self.assertEqual(AXIS_A["values"][0]["patch"],
                         {"task_generation": {"realistic": {"interval_scale": 0.70}}},
                         "输入轴定义被 build_plan 就地改写了")

    def test_repeats_pair_same_seed_across_cells(self):
        """同一 repeat 的所有格共用 seed ⇒ 跨格比较是配对的（沿用既有约定）。"""
        p = preset_of({"enabled": True, "repeats": 2, "axes": [AXIS_A, AXIS_B]})
        plan = runner.build_plan(p)
        self.assertEqual(len(plan), 12, "6 格 × 2 重复应为 12")
        r1 = {s.seed for s in plan if s.repeat == 1}
        r2 = {s.seed for s in plan if s.repeat == 2}
        self.assertEqual(len(r1), 1, "repeat=1 的六格应同 seed，实得 %s" % sorted(r1))
        self.assertEqual(len(r2), 1)
        self.assertNotEqual(r1, r2, "两个重复用了同一个 seed ⇒ 无法形成配对差异")


if __name__ == "__main__":
    unittest.main()
