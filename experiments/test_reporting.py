from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from experiments.reporting import descriptive_stats, paired_comparison, write_rows


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"实验":"algorithm_comparison","成功":True,"算法key":"greedy","Seed":101,"完成率":0.8,"超时率":0.2,"无人机利用率":0.6,"空载率":0.3,"从生成到完成总时间平均":100,"泊位利用率":0.4,"机巢周转率":2,"平均泊位排队等待":10,"总能量消耗":50,"总飞行距离":1000},
            {"实验":"algorithm_comparison","成功":True,"算法key":"ga","Seed":101,"完成率":0.9,"超时率":0.1,"无人机利用率":0.7,"空载率":0.2,"从生成到完成总时间平均":90,"泊位利用率":0.5,"机巢周转率":2.2,"平均泊位排队等待":8,"总能量消耗":48,"总飞行距离":950},
            {"实验":"algorithm_comparison","成功":True,"算法key":"greedy","Seed":102,"完成率":0.7,"超时率":0.3,"无人机利用率":0.5,"空载率":0.4,"从生成到完成总时间平均":120,"泊位利用率":0.3,"机巢周转率":1.8,"平均泊位排队等待":12,"总能量消耗":60,"总飞行距离":1100},
            {"实验":"algorithm_comparison","成功":True,"算法key":"ga","Seed":102,"完成率":0.8,"超时率":0.2,"无人机利用率":0.6,"空载率":0.3,"从生成到完成总时间平均":100,"泊位利用率":0.4,"机巢周转率":2.0,"平均泊位排队等待":9,"总能量消耗":55,"总飞行距离":1000},
        ]

    def test_descriptive_stats_has_dispersion(self):
        out = descriptive_stats(self.rows)
        ga = next(r for r in out if r["算法key"] == "ga")
        self.assertEqual(ga["样本数"], 2)
        self.assertAlmostEqual(ga["完成率_均值"], 0.85)
        self.assertGreater(ga["完成率_标准差"], 0)

    def test_paired_comparison_uses_matching_seed_and_direction(self):
        out = paired_comparison(self.rows)
        completion = next(r for r in out if r["指标"] == "完成率")
        timeout = next(r for r in out if r["指标"] == "超时率")
        self.assertEqual(completion["配对样本数"], 2)
        self.assertAlmostEqual(completion["平均改进"], 0.1)
        self.assertAlmostEqual(timeout["平均改进"], 0.1)
        self.assertEqual(completion["胜"], 2)

    def test_write_rows_utf8_csv(self):
        with tempfile.TemporaryDirectory() as td:
            path = write_rows(Path(td) / "x.csv", paired_comparison(self.rows))
            text = path.read_text(encoding="utf-8-sig")
            self.assertIn("相对改进率", text)
            self.assertIn("完成率", text)


    def test_capacity_metrics_are_not_judged_higher_is_better(self):
        """泊位利用率 / 机巢周转率 不许被标成"越高越好"。

        实测反例（seed=101、greedy、1800 步）：泊位 1→2→4 时排队总时长 359s→0→0、
        完成率 0.85→0.9167（真实改善），但周转率 1.80→0.70→0.35、
        泊位利用率 0.1526→0.0700→0.0350 —— 两个指标都随系统变好而下降。
        这个集合会决定 improvements 的符号与 胜/平/负 计数，标错就是在
        paired_ga_vs_greedy.csv 里造出一条方向反了的胜负结论。
        """
        from experiments.reporting import DIRECTION_AMBIGUOUS, HIGHER_IS_BETTER, LOWER_IS_BETTER

        for m in ("泊位利用率", "机巢周转率"):
            self.assertNotIn(m, HIGHER_IS_BETTER, "%s 方向不是单向的越高越好" % m)
            self.assertNotIn(m, LOWER_IS_BETTER, "%s 也不是单向的越低越好" % m)
            self.assertIn(m, DIRECTION_AMBIGUOUS)
        # 三个集合必须互斥，否则一个指标会被两条规则同时命中
        self.assertFalse(HIGHER_IS_BETTER & LOWER_IS_BETTER)
        self.assertFalse(HIGHER_IS_BETTER & DIRECTION_AMBIGUOUS)
        self.assertFalse(LOWER_IS_BETTER & DIRECTION_AMBIGUOUS)

    def test_ambiguous_metrics_get_no_win_loss_tally(self):
        """方向未定的指标不许产出胜/平/负，否则读者会把未定方向当结论。"""
        rows = paired_comparison(self.rows, baseline="greedy", candidate="ga")
        by_metric = {r["指标"]: r for r in rows}
        for m in ("泊位利用率", "机巢周转率"):
            self.assertIn(m, by_metric)
            self.assertEqual(by_metric[m]["胜"], "", "%s 不该有胜/平/负计数" % m)
            self.assertEqual(by_metric[m]["负"], "")
            self.assertIn("视运营目标", by_metric[m]["方向"])
            # 但原始差值仍要保留，供人自行判断
            self.assertIsInstance(by_metric[m]["候选减基线"], float)
        # 对照：方向明确的指标照常计数
        self.assertGreater(by_metric["完成率"]["胜"], 0)

    def test_markdown_render_handles_unjudged_rows(self):
        from experiments.reporting import render_paired_markdown

        rows = paired_comparison(self.rows, baseline="greedy", candidate="ga")
        text = "\n".join(render_paired_markdown(rows))
        self.assertIn("不判", text)
        self.assertIn("方向", text)


if __name__ == "__main__":
    unittest.main()
