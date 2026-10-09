# -*- coding: utf-8 -*-
"""E1 接入 Environment 的三道门：**等价门 → 符号门 → 非零风行为门**。

顺序是有意的：等价门排在最前，因为它证明"新增结构没有偷偷改变原模型"——
这比"逆风更费电"更重要。任何一条不等价就应当停下，不要继续跑 fixture。

为什么逐 run 而不是只比均值：同 seed 的两批如果均值相同但逐 run 不同，
说明有非确定性混进来了；而均值差被抵消恰好掩盖它。用户明确要求"最好逐 run 对比"。

这里不接 1008 小时 CSV、不做时间序列风、不比四算法 —— 那些都在本轮范围外。
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXP_DIR = ROOT / "results" / "experiments" / "e0_baseline_20261008-210053"  # 重生成基线（见 CHANGELOG 第四十笔；旧基线同名保留待裁）
PRESET = ROOT / "experiments" / "presets" / "e0_baseline.yaml"


def _run_preset(preset_path, out_root):
    """用与结项完全相同的编排器跑一批，返回 raw_runs 行。"""
    cmd = [sys.executable, "-m", "experiments.runner", "--preset", str(preset_path),
           "--output-root", str(out_root)]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError("[RUNNER_RC=%d] %s" % (proc.returncode, (proc.stdout + proc.stderr)[-800:]))
    dirs = sorted(p.name for p in pathlib.Path(out_root).iterdir() if p.is_dir())
    if not dirs:
        raise RuntimeError("[NO_OUTPUT_DIR] %s 下没有产物目录" % out_root)
    csv_path = pathlib.Path(out_root) / dirs[-1] / "raw_runs.csv"
    import csv as _csv
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        return list(_csv.DictReader(fh))


class WindInjectionEquivalenceTests(unittest.TestCase):
    """门 1（最关键）：E1 + zero wind 必须逐 run 复现冻结的 E0 baseline。"""

    @classmethod
    def setUpClass(cls):
        if not EXP_DIR.is_dir():
            raise unittest.SkipTest("E0 基线目录不存在：%s" % EXP_DIR)
        cls.e0 = list(csv_rows(EXP_DIR / "raw_runs.csv"))
        # 同一预设、同一 seeds 再跑一遍：此时 config 无 wind 键 ⇒ 静风 ⇒ 应逐字复现
        cls.tmp = ROOT / "results" / "experiments" / "_e1_zero_wind_check"
        cls.tmp.mkdir(parents=True, exist_ok=True)
        cls.e1_zero = _run_preset(PRESET, cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil_rmtree(cls.tmp)

    def test_same_run_count_and_keys(self):
        self.assertEqual(len(self.e1_zero), len(self.e0),
                         "重跑行数变了：%d vs %d ⇒ 计划本身漂移了" % (len(self.e1_zero), len(self.e0)))
        k0 = {(r["取值"], r["重复"], r["Seed"]) for r in self.e0}
        k1 = {(r["取值"], r["重复"], r["Seed"]) for r in self.e1_zero}
        self.assertEqual(k0, k1, "seed/格次集合不一致，无法逐 run 对撞：%s" % (k0 ^ k1))

    def test_every_run_reproduces_e0_bit_for_bit(self):
        """逐 run、逐指标比对。任何一格不同都算失败并点名是哪一格。"""
        idx = {(r["取值"], r["重复"]): r for r in self.e1_zero}
        metrics = [c for c in list(self.e0[0].keys())[10:]]   # 跳过元数据列
        bad = []
        for r in self.e0:
            s = idx.get((r["取值"], r["重复"]))
            self.assertIsNotNone(s, "缺格 %s×rep%s" % (r["取值"], r["重复"]))
            self.assertEqual(s["Seed"], r["Seed"], "seed 漂移")
            for m in metrics:
                if r[m] != s[m]:
                    bad.append("%s/rep%s/%s: E0=%s E1zero=%s" % (r["取值"], r["重复"], m, r[m], s[m]))
        self.assertEqual(bad, [], "E1+静风未逐字复现 E0（%d 处）:\n  %s" % (len(bad), "\n  ".join(bad[:12])))

    def test_shipped_config_has_no_wind_key(self):
        """默认配置里不该出现 wind 键 —— 出现了就等于把风塞进了正式参数。"""
        cfg = json.loads((ROOT / "config" / "simulation.json").read_text(encoding="utf-8"))
        self.assertNotIn("wind", cfg, "config/simulation.json 出现了 wind 键 ⇒ 违反'不改正式默认'")


class WindSignConventionTests(unittest.TestCase):
    """门 2：符号约定必须有单测钉住（物理含义反掉是最难发现的错）。"""

    def setUp(self):
        sys.path.insert(0, str(ROOT))
        sys.path.insert(0, str(ROOT / "frontend"))
        os.environ.setdefault("SWARM_BALANCE_SIM_CONFIG", str(ROOT / "config" / "simulation.json"))
        import drone as D
        self.D = D

    def make(self):
        return self.D.Drone(drone_id="t", x=0.0, y=0.0, drone_type="heavy_cargo")

    def test_dot_positive_is_tailwind_not_headwind(self):
        """空气吹向方向与航向点积为正 ⇒ **顺风**；内部 wind_along 必须因此为负。

        这条存在是因为很容易写成 `dot(wind, route)` 却把它当"逆风为正"用 ——
        符号反了不会报错，只会让所有结论反向。
        """
        d = self.make(); d.set_wind(wind_u=6.0, wind_v=0.0)     # 空气往东吹
        dot_east = 6.0 * 1.0 + 0.0 * 0.0                        # 向东飞：点积 > 0 ⇒ 顺风
        self.assertGreater(dot_east, 0.0)
        wa = d._wind_along_for(100.0, 0.0, 100.0)
        self.assertLess(wa, 0.0, "点积为正却给出 wind_along>0 ⇒ 顺逆风定义反了")

    def test_headwind_case_is_negative_dot(self):
        d = self.make(); d.set_wind(wind_u=6.0, wind_v=0.0)     # 东风，向西飞 = 逆风
        wa = d._wind_along_for(-100.0, 0.0, 100.0)
        self.assertGreater(wa, 0.0, "逆风应为正")

    def test_crosswind_is_zero_component(self):
        d = self.make(); d.set_wind(wind_u=6.0, wind_v=0.0)
        self.assertAlmostEqual(d._wind_along_for(0.0, 100.0, 100.0), 0.0, places=9)

    def test_environment_default_is_calm(self):
        """Environment 未配风时 wind_u/v 必须是 0 ⇒ 注入后每架机都是静风。"""
        import environment as E
        self.assertEqual(E.WIND_U_DEFAULT, 0.0)
        self.assertEqual(E.WIND_V_DEFAULT, 0.0)


class NonZeroWindBehaviorTests(unittest.TestCase):
    """门 3：非零风必须真的咬到仿真 KPI（不是只在单元测试里有效）。

    做法：直接构造一个极短回合，让一架机沿固定航线飞 N 步，比较静风与强风的电池扣减。
    不用完整 fixture —— 那属于下一步的对撞，且慢两个数量级。
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "frontend"))
        os.environ.setdefault("SWARM_BALANCE_SIM_CONFIG", str(ROOT / "config" / "simulation.json"))
        import drone as D
        self.D = D

    def fly_steps(self, wind_u, steps=20):
        """向东直线飞 steps 步，返回累计耗电 Wh（载荷固定）。"""
        d = self.D.Drone(drone_id="t", x=0.0, y=0.0, drone_type="heavy_cargo")
        d.current_load = 15.0
        d.set_wind(wind_u=wind_u, wind_v=0.0)
        saved = (self.D.WIND_ENABLED, self.D.WIND_ENERGY_HEADWIND_PER_MS,
                 self.D.WIND_ENERGY_TAILWIND_PER_MS)
        self.D.WIND_ENABLED = True
        self.D.WIND_ENERGY_HEADWIND_PER_MS = 0.05
        self.D.WIND_ENERGY_TAILWIND_PER_MS = 0.03
        try:
            before = d.current_battery
            for _ in range(steps):
                d.schedule_route([(d.x + (i + 1) * d.speed, 0.0) for i in range(steps)])
                d.update()
            return before - d.current_battery
        finally:
            (self.D.WIND_ENABLED, self.D.WIND_ENERGY_HEADWIND_PER_MS,
             self.D.WIND_ENERGY_TAILWIND_PER_MS) = saved

    def test_headwind_costs_more_than_calm_in_a_real_flight(self):
        calm = self.fly_steps(0.0)
        head = self.fly_steps(-6.0)      # 空气向西吹 ⇒ 向东飞是逆风 ⇒ wind_along>0
        tail = self.fly_steps(6.0)       # 空气向东吹 ⇒ 顺风
        self.assertGreater(head, calm, "逆风在实际飞行里没有更费电 ⇒ 路径没接通")
        self.assertLess(tail, calm, "顺风在实际飞行里没有更省电 ⇒ 路径没接通")

    def test_distance_is_unchanged_by_wind(self):
        """E1 不许改变运动学：同样步数下位移必须与静风一致（这是②而非③的证据）。"""
        def travel(wu):
            d = self.D.Drone(drone_id="t", x=0.0, y=0.0, drone_type="heavy_cargo")
            d.set_wind(wind_u=wu, wind_v=0.0)
            for _ in range(10):
                d.schedule_route([(d.x + d.speed, 0.0)])
                d.update()
            return d.x
        self.assertAlmostEqual(travel(0.0), travel(6.0), places=9,
                               msg="风改变了位移 ⇒ 这不是 E1（能耗层），而是 E2（运动学层）")


def csv_rows(path):
    import csv as _csv
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(_csv.DictReader(fh))


def shutil_rmtree(path):
    import shutil
    shutil.rmtree(str(path), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
