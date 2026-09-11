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


if __name__ == "__main__":
    unittest.main()
