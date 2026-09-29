# -*- coding: utf-8 -*-
"""同配置同 Seed 必须逐位复现 —— 把"差 0.001 算不算噪声"这个问题钉住。

为什么这条用例值得跑 4 秒 × N：README 的逐 episode 行写 `利用率=0.705`，同一条命令末尾的
Mean Metrics 块写 `0.7045`，两处差约 0.001。这不能用"四舍五入"糊过去，因为本项目已经
证实过环境差异会**真的**改变航线（osmnx 在与不在，避障碰撞体 18 vs 108 栋），
所以只有两种可能：固定的显示舍入路径，或者同 seed 不同运行不稳定。后者直接顶撞"可复现"。

判据因此定得很硬：把 Mean Metrics 块的 24 个数值逐字段比对，要求**文本完全相同**，
而不是"差值小于某个 ε"。 ε 会把真实的不稳定读成通过。

实测结论（2026-09-29）：5 次运行 24/24 字段逐位一致，方差为 0；
0.001 之差纯粹是同一个数的 `.3f` 与 `.4f` 两种显示。详见
docs/数据来源与可追溯性登记表.md 的「七点五、同配置同 Seed 的运行确定性」。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# 与 README「跑一次评测」那条命令逐字相同 —— 用例测的就是文档里那条，不是另编一条。
README_CMD = ["evaluate_metrics.py", "--policy", "ga", "--episodes", "1",
              "--episode-steps", "600", "--seed", "100"]

MEAN_LINE = re.compile(r"^(?P<name>[^:]+): (?P<val>-?[\d.]+)$")


def _run_once():
    proc = subprocess.run(
        [sys.executable] + README_CMD,
        cwd=str(ROOT / "frontend"), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    return proc.returncode, proc.stdout + proc.stderr


def _mean_metrics(text):
    """抓 Mean Metrics 块里的 `名称: 数值` 行。"""
    parts = text.split("Mean Metrics")
    if len(parts) < 2:
        return None
    rows = {}
    for line in parts[1].splitlines()[1:]:
        m = MEAN_LINE.match(line.strip())
        if m:
            rows[m.group("name").strip()] = m.group("val")
    return rows


class RunDeterminismTests(unittest.TestCase):
    """同一命令重复运行必须逐位一致，否则"可复现"三个字不能对外说。"""

    repeats = int(os.environ.get("SWARM_DETERMINISM_REPEATS", "2"))
    _cache = None      # 每条真跑约 20s，两个用例共用同一批运行结果，别再乘一遍

    @classmethod
    def _runs(cls):
        if cls._cache is not None:
            return cls._cache
        runs = []
        for i in range(cls.repeats):
            rc, out = _run_once()
            if "No module named" in out:
                raise unittest.SkipTest(
                    "解释器缺仿真依赖，无法测确定性（这是未执行，不是通过）：%s" % out[-200:])
            if rc != 0:
                raise AssertionError("第 %d 次运行就挂了：\n%s" % (i + 1, out[-1500:]))
            rows = _mean_metrics(out)
            if rows is None:
                raise AssertionError("第 %d 次没抓到 Mean Metrics 块，后面的比对是空转：\n%s"
                                     % (i + 1, out[-800:]))
            if len(rows) <= 10:
                raise AssertionError("只解析到 %d 个字段，解析式可能已失效" % len(rows))
            runs.append((rows, out))
        cls._cache = runs
        return runs

    def test_same_seed_same_config_is_bit_identical(self):
        runs = [rows for rows, _ in self._runs()]
        base = runs[0]
        diffs = []
        for name, val in base.items():
            others = [r.get(name) for r in runs[1:]]
            if any(o != val for o in others):
                diffs.append("%s: %s vs %s" % (name, val, others))
        self.assertEqual(diffs, [],
                         "同配置同 Seed 的 %d 次运行出现 %d 个字段不一致 —— "
                         "这是真不确定性，不是显示舍入，必须查明来源：\n  %s"
                         % (self.repeats, len(diffs), "\n  ".join(diffs)))

    def test_the_0001_gap_is_display_precision_not_a_different_run(self):
        """钉住 0.001 的归因：同一个数的 .3f 与 .4f，不是两次不同运行。"""
        rows, out = self._runs()[0]
        episode = [l for l in out.splitlines() if l.startswith("Episode 1")]
        self.assertTrue(episode, "没抓到逐 episode 行，两条打印精度无从对照")

        # 无人机利用率：.4f 显示 0.7045，.3f 显示 0.705 —— 必须能对得上
        util4 = rows.get("无人机利用率")
        self.assertIsNotNone(util4, "Mean Metrics 块里没有无人机利用率字段")
        self.assertIn("利用率=%.3f" % float(util4), episode[0],
                      "逐 episode 行的 3 位显示与均值块的 4 位值不是同一个数 —— "
                      "那 README 的 0.001 差值就不是舍入，得重开归因")
