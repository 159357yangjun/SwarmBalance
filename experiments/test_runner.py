from __future__ import annotations

import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from experiments import runner
from experiments.reproducibility import ALGORITHM_SOURCES, SHARED_SOURCES, write_manifest
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


    def test_quick_preset_cannot_overwrite_shared_compare_table(self):
        """覆盖答辩对比页数据源需要**两道**闸门：预设是 conclusion，且显式 publish_latest。

        闸门①（预设）：此前 quick（1200 步 / repeats=1）跑完也写 results/compare/one_click_latest.csv，
        而 /api/compare 按 keep="last" 读取，点一次「快速自检」就等于悄悄换掉了对比页背后的一整批数字。
        闸门②（显式发布）：这个文件**已入库**，_write_csv 以 "w" 打开会就地截断重写。
        评审照 README 跑 `--preset conclusion` 即使预设合法，也不该在没点名的情况下
        替换掉答辩页正在展示的、已提交的那份证据。
        """
        raw_rows = [self._row("algorithm_comparison", "greedy", 完成率=0.9, 总步数=2000.0)]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original = runner.PROJECT_ROOT
            runner.PROJECT_ROOT = root
            try:
                shared = root / "results" / "compare" / "one_click_latest.csv"
                quick = _aggregate(list(raw_rows), root / "quick", {"_preset_key": "quick"},
                                   publish_latest=True)
                self.assertNotIn("compare_latest", quick)
                self.assertFalse(shared.exists(), "quick 预设即使带发布开关也不应写共享对比表")

                silent = _aggregate(list(raw_rows), root / "concl0", {"_preset_key": "conclusion"})
                self.assertNotIn("compare_latest", silent,
                                 "没带 publish_latest 就写了入库证据文件 —— 照 README 跑一遍结论预设"
                                 "就会截断重写已提交文件，这正是第②道闸门要拦的")
                self.assertFalse(shared.exists(), "默认（不加开关）不得写共享对比表")

                concl = _aggregate(list(raw_rows), root / "concl", {"_preset_key": "conclusion"},
                                   publish_latest=True)
                self.assertIn("compare_latest", concl)
                self.assertTrue(shared.exists(), "conclusion + 显式开关才应写入共享对比表")
            finally:
                runner.PROJECT_ROOT = original

    def test_aggregate_without_preset_is_backwards_compatible(self):
        raw_rows = [self._row("algorithm_comparison", "greedy", 完成率=0.9, 总步数=2000.0)]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original = runner.PROJECT_ROOT
            runner.PROJECT_ROOT = root
            try:
                out = _aggregate(raw_rows, root / "exp")        # 不传 preset 也不能报错
                self.assertTrue((root / "exp" / "algorithm_comparison.csv").exists())
                self.assertNotIn("compare_latest", out)
            finally:
                runner.PROJECT_ROOT = original


CONCLUSION_ALGOS = ["greedy", "ga", "pso", "ortools"]


class ReproducibilityManifestTests(unittest.TestCase):
    def _manifest(self, root, algorithms, tmp):
        return write_manifest(
            Path(tmp), root, None,
            root / "config" / "simulation.json",
            root / "config" / "algorithms.yaml",
            root / "frontend" / "data" / "map.osm",
            1, algorithms, "conclusion",
        )

    def test_every_algorithm_row_carries_its_own_source_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = json.loads(self._manifest(runner.PROJECT_ROOT, CONCLUSION_ALGOS, tmp).read_text(encoding="utf-8"))
        hashes = doc["core_source_sha256"]
        # v1 清单只哈希 GA 相关源码：PSO / OR-Tools / greedy 三行结果是零源码证据的。
        for algo in CONCLUSION_ALGOS:
            for rel in ALGORITHM_SOURCES[algo]:
                self.assertIn(rel, hashes, f"{algo} 的实现源码 {rel} 没进清单")
        self.assertTrue(all(hashes[f] for f in hashes), "存在被静默记成 null 的源码哈希")

    def test_no_listed_source_is_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            doc = json.loads(self._manifest(runner.PROJECT_ROOT, CONCLUSION_ALGOS, tmp).read_text(encoding="utf-8"))
        for rel in SHARED_SOURCES:
            self.assertIn(rel, doc["core_source_sha256"], f"共用执行路径 {rel} 没进清单")
        self.assertEqual(doc["schema_version"], 2)

    def test_unknown_algorithm_is_rejected_instead_of_left_unhashed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(KeyError):
                self._manifest(runner.PROJECT_ROOT, CONCLUSION_ALGOS + ["qmix"], tmp)

    def test_missing_source_file_raises_instead_of_recording_null(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                self._manifest(Path(root), ["pso"], tmp)

    def test_manifest_carries_no_absolute_path(self):
        """归档清单曾把 C:\\Users\\<user>\\... 整条写进去，等于把开发机目录结构发给评委。"""
        with tempfile.TemporaryDirectory() as tmp:
            text = self._manifest(runner.PROJECT_ROOT, CONCLUSION_ALGOS, tmp).read_text(encoding="utf-8")
        self.assertNotIn("\\\\", text, "清单里仍有 Windows 绝对路径")
        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", text), "清单里仍有盘符路径")
        self.assertNotIn(str(Path.home()), text)

    def test_algorithm_sources_stay_in_sync_with_worker_choices(self):
        src = (runner.PROJECT_ROOT / "experiments" / "worker.py").read_text(encoding="utf-8")
        found = re.search(r'--algorithm"[^\]]*choices=\[([^\]]+)\]', src)
        self.assertIsNotNone(found, "worker.py 的 --algorithm choices 写法变了，这个防漂移断言需要一起改")
        choices = set(re.findall(r'"([a-z_]+)"', found.group(1)))
        self.assertEqual(choices, set(ALGORITHM_SOURCES),
                         "worker 能跑的算法与复现清单登记表的键不一致")


if __name__ == "__main__":
    unittest.main()
