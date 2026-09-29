# -*- coding: utf-8 -*-
"""单回合步数必须只有一个来源：config/simulation.json 的 environment.episode_max_steps。

为什么值得一条测试：历史上这个"默认值"散落 7 处且互不相同 —— 配置 3600、
frontend/environment.py 1200、console/sim_session.py 2000、evaluate_metrics.py 1200
（且完全不读配置）、run_ga/run_pso/run_ortools/run_greedy 各 1200。
同一个"默认"能跑出 3 种长度的实验，而答辩里"可复现"依赖的正是这个数。
实测后果已经落在对外产物上：results/compare/ 里 greedy/si/ortools 三份 CSV 的
总步数就是 2000，与结项实验的 3600 上限不同口径。

三条断言：① 缺配置必须抛错（不许悄悄兜底）；② 源码里不许再出现数字字面量形式的
episode 兜底默认；③ 所有入口解析到同一个值。
"""
from __future__ import annotations

import io
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.config_loder import get_episode_max_steps, get_shared_config  # noqa: E402


class EpisodeStepSingleSourceTests(unittest.TestCase):

    def test_config_value_is_the_answer(self):
        """真源确实存在且被读到。"""
        self.assertEqual(get_episode_max_steps(), 3600)

    def test_missing_key_raises_instead_of_silently_defaulting(self):
        """缺配置必须抛错。这是"不存在第二套默认"的行为证明。"""
        with self.assertRaises(RuntimeError) as ctx:
            get_episode_max_steps(config={"environment": {}})
        self.assertIn("episode_max_steps", str(ctx.exception))

        for bad in (None, {}, {"environment": None}):
            with self.assertRaises(RuntimeError):
                get_episode_max_steps(config=bad)

    def test_invalid_values_rejected(self):
        for bad in ({"environment": {"episode_max_steps": 0}},
                    {"environment": {"episode_max_steps": -5}},
                    {"environment": {"episode_max_steps": "abc"}}):
            with self.assertRaises(RuntimeError):
                get_episode_max_steps(config=bad)

    def test_no_numeric_fallback_left_in_sources(self):
        """静态证明：不许任何文件再写 episode 步数的数字兜底。"""
        patterns = [
            # .get("episode_max_steps", <数字>)  —— 必须要求 .get( 前缀，
            # 否则会误伤 assertEqual(s.episode_max_steps, 4321) 这类断言（第一版就误报了）
            re.compile(r"""\.get\(\s*["']episode_max_steps["']\s*,\s*\d+"""),
            # args.episode_steps or <数字>
            re.compile(r"""episode_steps\s+or\s+\d+"""),
            # default_steps=<数字>
            re.compile(r"""default_steps\s*=\s*\d+"""),
        ]
        offenders = []
        for dirpath, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in
                       {".git", "__pycache__", "node_modules", ".venv310", ".idea",
                        "data", "results", "deliverables", "paper"}]
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                full = os.path.join(dirpath, fn)
                with io.open(full, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
                for i, line in enumerate(text.split("\n"), 1):
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue          # 纯注释行允许叙述历史
                    if "原先" in line or "历史上" in line or "不再" in line:
                        continue          # 说明性散文，不是代码
                    for pat in patterns:
                        if pat.search(line):
                            offenders.append("%s:%d  %s"
                                             % (os.path.relpath(full, ROOT).replace("\\", "/"),
                                                i, stripped[:88]))
        self.assertEqual(offenders, [],
                         "发现残留的 episode 步数兜底默认值：\n  " + "\n  ".join(offenders))

    def test_every_entry_point_resolves_to_the_same_number(self):
        """所有入口必须给出同一个数，否则就是第二套默认换了个形式活着。"""
        cfg = get_shared_config()
        expected = cfg["environment"]["episode_max_steps"]
        # 内核模块级常量
        sys.path.insert(0, str(ROOT / "frontend"))
        import environment as env_mod
        self.assertEqual(int(env_mod.DEFAULT_EPISODE_MAX_STEPS), int(expected))
        # 四个 CLI 解析器
        for mod_name in ("run_ga", "run_pso", "run_ortools"):
            mod = __import__(mod_name)
            self.assertEqual(int(mod._resolve_episode_steps()), int(expected),
                             "%s 解析到的步数与真源不一致" % mod_name)
        import greedy.run_greedy as rg
        self.assertEqual(int(rg._resolve_episode_steps()), int(expected))


if __name__ == "__main__":
    unittest.main()
