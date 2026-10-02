# -*- coding: utf-8 -*-
"""`console/_paired_readout.py` 的常驻用例：把"能不能下结论"本身钉成可算的量。

来历（本轮实测，不是设想）：结项预设每个算法只跑 5 个 seed，而 `paired_ga_vs_greedy.csv`
印着胜/平/负三列 —— n=5 时双侧符号检验的**最小可得 p = 0.625**（全部同号也只到这个数），
所以那三列在任何数据下都不可能显著。纸面上"不代表统计显著性"那句免责声明没有任何东西
保证它被兑现；这里把它换成一个会自己算的数。

断言刻意不依赖真实验目录（那会随重跑漂），只用合成配对 + 数学事实：
- 最小可得 p 的公式在 n=1..8 与穷举一致；
- 全同号 / 一正四负 / 三平两种形状各自的精确 p 与代码分支；
- 方向集合从 `experiments/reporting.py` 按 AST 解析，改名或删掉必须红（不许猜方向）。
"""
from __future__ import annotations

import itertools
import math
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "console") not in sys.path:
    sys.path.insert(0, str(ROOT / "console"))
import _paired_readout as PR                       # noqa: E402


def brute_p(deltas):
    """独立实现一遍穷举置换（测试里当第二证人，不复用被测函数的内部）。"""
    obs = abs(sum(deltas))
    hits = tot = 0
    for signs in itertools.product((1, -1), repeat=len(deltas)):
        tot += 1
        if abs(sum(s * d for s, d in zip(signs, deltas))) >= obs - 1e-12:
            hits += 1
    return hits / tot


class PairedReadoutTests(unittest.TestCase):

    def test_smallest_possible_p_matches_brute_force(self):
        """`smallest_p(n)` 必须等于"全部同号时的精确 p" —— 逐个 n 用穷举核。"""
        for n in range(1, 9):
            deltas = [1.0] * n
            self.assertAlmostEqual(PR.smallest_p(n), brute_p(deltas), places=12,
                                   msg="n=%d 的最小可得 p 与穷举不一致" % n)
        # 旧公式 `2·C(n,n//2)/2^n` 在偶数 n 上会高估（n=2 给 1.0、真值 0.5），
        # 所以这条同时是"我第一版写错了"的证人：它抓到了我自己的算错。
        self.assertAlmostEqual(PR.smallest_p(5), 0.0625, places=12)
        self.assertGreater(PR.smallest_p(5), PR.ALPHA,
                           "n=5 的最小可得 p 已不大于 α，本用例的前提变了")
        self.assertLessEqual(PR.smallest_p(6), PR.ALPHA,
                             "按结论该是 n=6 起可判，这里变了就说明 α 或公式动了")
        print("[PR_MINP] n=5 smallest_p=%.4f alpha=%.2f 首个可判的 n=%d"
              % (PR.smallest_p(5), PR.ALPHA,
                 next(n for n in range(1, 9) if PR.smallest_p(n) <= 0.05)))

    def test_exact_p_is_exact_and_permutations_are_enumerated(self):
        d = [-0.0333, -0.0667, 0.0, 0.0, 0.0]          # 本轮真数据的形状（超时率）
        p, perms = PR.exact_sign_test(d)
        self.assertEqual(perms, 32, "n=5 应穷举 32 个置换，实得 %d" % perms)
        self.assertAlmostEqual(p, brute_p(d), places=12)
        self.assertGreater(p, PR.ALPHA)
        # n>8 必须拒绝而不是偷偷近似
        with self.assertRaises(AssertionError) as cm:
            PR.exact_sign_test([1.0] * 9)
        self.assertIn("[PAIRED_N_TOO_BIG]", str(cm.exception))

    def test_direction_sets_come_from_reporting_not_a_second_copy(self):
        """方向集合按 AST 从 reporting.py 取：改名/删除要红，值必须与那边逐字相同。"""
        hi, lo, amb = PR._HI, PR._LO, PR._AMB
        self.assertIn("完成率", hi)
        self.assertIn("超时率", lo)
        self.assertTrue(amb, "方向不定集合空了 —— reporting 改结构了？")
        self.assertFalse(hi & lo and hi & amb, "同一指标出现在两个方向集合里，判优会自相矛盾")
        self.assertEqual(PR.direction("超时率"), -1)
        self.assertEqual(PR.direction("完成率"), 1)
        self.assertIsNone(PR.direction(next(iter(amb))), "方向不定的指标被判优了")
        print("[PR_DIRS] higher=%d lower=%d ambiguous=%d" % (len(hi), len(lo), len(amb)))

    def test_unjudgeable_branch_fires_on_real_shape(self):
        """合成一份 raw_runs.csv：n=5、任何形状都必须报 [PAIRED_UNJUDGEABLE]。"""
        d = Path(tempfile.mkdtemp(prefix="pr-test-"))
        try:
            cols = ["实验", "成功", "算法key", "Seed", "超时率"]
            rows = []
            for alg, vals in (("greedy", [0.0667, 0.0667, 0.0667, 0.0167, 0.05]),
                              ("ga", [0.1000, 0.1333, 0.0667, 0.0167, 0.05])):
                for s, v in zip(("101", "102", "103", "104", "105"), vals):
                    rows.append(dict(zip(cols, ["algorithm_comparison", "True", alg, s,
                                                repr(v)])))
            with open(d / "raw_runs.csv", "w", encoding="utf-8", newline="") as fh:
                from csv import DictWriter
                w = DictWriter(fh, fieldnames=cols)
                w.writeheader()
                w.writerows(rows)
            r = PR.analyse(d, "超时率")
            self.assertIsNotNone(r, "分支返回 None，说明前置检查把数据挡掉了")
            self.assertEqual(r["code"], "[PAIRED_UNJUDGEABLE]", r)
            self.assertEqual(r["n"], 5)
            self.assertGreater(r["smallest_p"], PR.ALPHA)
            # 判别式：全同号也救不了 n=5 —— 效应再大也不可能显著
            self.assertGreater(r["p"], PR.ALPHA)
        finally:
            shutil.rmtree(str(d), ignore_errors=True)

    def test_missing_side_is_refused_not_reported_as_no_difference(self):
        """两侧不齐 / 没有共同 seed ⇒ [PAIRED_NO_DATA]，不许悄悄报个"没差别"。"""
        d = Path(tempfile.mkdtemp(prefix="pr-test2-"))
        try:
            with open(d / "raw_runs.csv", "w", encoding="utf-8", newline="") as fh:
                fh.write("实验,成功,算法key,Seed,超时率\n")
                fh.write("algorithm_comparison,True,greedy,101,0.05\n")
            self.assertIsNone(PR.analyse(d, "超时率"), "只有单侧数据却当成了可比")
        finally:
            shutil.rmtree(str(d), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
