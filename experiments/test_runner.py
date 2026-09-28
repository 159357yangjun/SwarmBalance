from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from experiments import runner
from experiments.runner import METRIC_COLUMNS, _aggregate, _mean_rows, build_plan, load_preset


class ExperimentRunnerTests(unittest.TestCase):
    def test_same_condition_uses_same_seed_across_algorithms(self):
        plan = build_plan(load_preset("quick"))
        buckets = {}
        for r in plan:
            key = (r.experiment, r.value, r.repeat)
            buckets.setdefault(key, set()).add(r.seed)
        self.assertTrue(buckets)
        self.assertTrue(all(len(seeds) == 1 for seeds in buckets.values()))


    def test_sensitivity_values_reuse_repeat_seed(self):
        plan = build_plan(load_preset("quick"))
        rows = [r for r in plan if r.experiment == "task_scale" and r.repeat == 1]
        self.assertGreater(len({r.value for r in rows}), 1)
        self.assertEqual(len({r.seed for r in rows}), 1)

    def test_fleet_mix_keeps_num_drones_equal_to_sum(self):
        plan = build_plan(load_preset("quick"))
        rows = [r for r in plan if r.experiment == "fleet_mix"]
        self.assertTrue(rows)
        for r in rows:
            mix = r.patch["heterogeneous"]["fleet_mix"]
            self.assertEqual(r.patch["environment"]["num_drones"], sum(mix.values()))

    def test_config_loader_env_override(self):
        from config.config_loder import get_shared_config
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "simulation.json"
            p.write_text(json.dumps({"marker": 123}), encoding="utf-8")
            old = os.environ.get("SWARM_BALANCE_SIM_CONFIG")
            os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(p)
            try:
                self.assertEqual(get_shared_config()["marker"], 123)
            finally:
                if old is None:
                    os.environ.pop("SWARM_BALANCE_SIM_CONFIG", None)
                else:
                    os.environ["SWARM_BALANCE_SIM_CONFIG"] = old

    def test_dry_run_does_not_create_output_directory(self):
        from experiments.runner import run_experiments
        preset = load_preset("quick")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "out"
            result = run_experiments(preset, root, dry_run=True)
            self.assertFalse(root.exists())
            self.assertTrue(str(result).endswith("quick_dry-run"))


class AggregationTests(unittest.TestCase):
    """_mean_rows / _aggregate 回归测试。

    原缺陷：_mean_rows 用 r.get("ok") 过滤，而 raw_rows 里的键是「成功」，
    于是过滤后恒为空、所有聚合指标静默写成 0.0；raw_runs.csv 数据正常、
    进程返回码 0，整份结项证据包全是零且无人被提醒。
    """

    def _row(self, exp, algkey, value="", seed=101, success=True, **metrics):
        row = {
            "实验": exp, "变量": "v", "取值": value, "重复": 1, "Seed": seed,
            "算法key": algkey, "算法": algkey, "成功": success, "耗时秒": 1.0, "错误": "",
        }
        for col in METRIC_COLUMNS:
            row[col] = 0.0
        row.update(metrics)
        return row

    def test_mean_rows_averages_only_successful_runs(self):
        rows = [
            self._row("algorithm_comparison", "greedy", 完成率=1.0, 总步数=100.0),
            self._row("algorithm_comparison", "greedy", 完成率=0.0, 总步数=200.0),
            self._row("algorithm_comparison", "greedy", 完成率=0.5, 总步数=300.0, success=False),
        ]
        means = _mean_rows(rows)
        self.assertAlmostEqual(means["完成率"], 0.5)          # (1.0 + 0.0) / 2，失败行不计入
        self.assertAlmostEqual(means["总步数"], 150.0)

    def test_mean_rows_rejects_silently_emptying_input(self):
        # 有输入却一行都不成功：必须报错，不能再静默补 0（这正是原缺陷的隐藏方式）
        with self.assertRaises(ValueError):
            _mean_rows([self._row("algorithm_comparison", "greedy", 完成率=1.0, success=False)])

    def test_mean_rows_empty_input_returns_zero_template(self):
        self.assertEqual(_mean_rows([]), {c: 0.0 for c in METRIC_COLUMNS})

    def test_aggregate_output_is_not_all_zeros(self):
        raw_rows = [
            self._row("algorithm_comparison", "greedy", 完成率=0.9, 总步数=2000.0),
            self._row("algorithm_comparison", "ga", 完成率=1.0, 总步数=2100.0),
        ]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original = runner.PROJECT_ROOT
            runner.PROJECT_ROOT = root          # 防止写进真实的 results/compare/
            try:
                outputs = _aggregate(raw_rows, root / "exp")
                self.assertTrue((root / "exp" / "algorithm_comparison.csv").exists())
                text = outputs["algorithm_comparison"].read_text(encoding="utf-8-sig")
            finally:
                runner.PROJECT_ROOT = original
        self.assertIn("greedy", text)
        # 完成率必须真的落进均值表；原缺陷下这两格都会是 0.0
        lines = [l.split(",") for l in text.strip().splitlines()]
        header = lines[0]
        rate = header.index("完成率")
        by_alg = {row[0]: float(row[rate]) for row in lines[1:]}
        self.assertAlmostEqual(by_alg["greedy"], 0.9)
        self.assertAlmostEqual(by_alg["ga"], 1.0)

    def test_aggregate_does_not_touch_repo_compare_directory(self):
        # PROJECT_ROOT 被 patch 到临时目录后，真实的 one_click_latest.csv 不应被改写
        target = runner.PROJECT_ROOT / "results" / "compare" / "one_click_latest.csv"
        before = target.read_bytes() if target.exists() else None
        raw_rows = [self._row("algorithm_comparison", "greedy", 完成率=0.9, 总步数=2000.0)]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original = runner.PROJECT_ROOT
            runner.PROJECT_ROOT = root
            try:
                _aggregate(raw_rows, root / "exp")
            finally:
                runner.PROJECT_ROOT = original
        after = target.read_bytes() if target.exists() else None
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
