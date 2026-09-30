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

import ast
import io
import os
import re
import tokenize
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

    # 只认"代码"里的兜底：必须要求 .get( 前缀，否则会误伤
    # assertEqual(s.episode_max_steps, 4321) 这类断言（第一版就误报了）。
    PATTERNS = [
        re.compile(r"""\.get\(\s*["']episode_max_steps["']\s*,\s*\d+"""),
        re.compile(r"""episode_steps\s+or\s+\d+"""),
        re.compile(r"""default_steps\s*=\s*\d+"""),
    ]

    @classmethod
    def _code_lines(cls, text):
        """返回 {行号: 只剩代码的文本}（注释与文档散文按字符抹白，**保留空格**）。

        为什么不能用"整行含『原先/历史上/不再』就放行"这种散文豁免：本轮实测，
        放一行 `PROBE_A = cfg.get("episode_max_steps", 1200)   # 不再使用` 进被扫目录，
        旧版静态扫描照样 OK —— 一个词就把真兜底洗白，属于"修完假红换来假绿"。
        为什么也不能把所有字符串都抹掉：`cfg.get("episode_max_steps", 1200)` 里的键名
        就是字符串，抹了它等于漏检。所以只抹**作为语句出现的字符串**（docstring 与
        孤立文本，即真散文）与**注释 token**；代码里的字符串字面量原样保留。
        保留空格是为了不改变匹配面：拼成 `episode_stepsor2000` 会让 `... or 2000` 漏匹配。
        解析失败（语法错误、编码怪）时退回整行 —— 宁可多报，不可漏报。
        """
        raw = text.split("\n")
        try:
            tree = ast.parse(text)
            comment_cols = {}
            with io.BytesIO(text.encode("utf-8")) as fh:
                for tok in tokenize.tokenize(fh.readline):
                    if tok.type == tokenize.COMMENT:
                        comment_cols[tok.start[0]] = tok.start[1]
        except (SyntaxError, ValueError, tokenize.TokenError, IndentationError):
            return {i: ln for i, ln in enumerate(raw, 1)}      # fail-closed：整行都判

        masked = [list(ln) for ln in raw]
        prose = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                    and isinstance(node.value.value, str)):
                prose.append((node.lineno, node.end_lineno or node.lineno))
        for a, b in prose:
            for ln in range(a, b + 1):
                if 1 <= ln <= len(masked):
                    masked[ln - 1] = [" "] * len(masked[ln - 1])
        out = {}
        for i, chars in enumerate(masked, 1):
            line = "".join(chars)
            if i in comment_cols:
                line = line[:comment_cols[i]]
            out[i] = line
        return out

    def _scan_text(self, rel, text):
        bad = []
        for ln, code in self._code_lines(text).items():
            for pat in self.PATTERNS:
                if pat.search(code):
                    bad.append("%s:%d  %s" % (rel, ln, code.strip()[:88]))
                    break
        return bad

    SELF_REL = "console/test_episode_step_single_source.py"

    def _self_exempt_range(self):
        """本文件里唯一允许出现兜底字面的范围 = `_samples()` 的函数体行号。

        用 ast 现算，不写死行号：样本函数搬到哪，豁免就跟到哪；这个文件的其他地方
        出现兜底，照样红。整文件跳过是更省事的做法，但那等于给自己开了个口子。
        """
        self_rel = self.SELF_REL
        path = ROOT / self_rel
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_samples":
                return node.lineno, node.end_lineno
        raise AssertionError("%s 里找不到 _samples()，无法确定豁免范围" % self_rel)

    def test_no_numeric_fallback_left_in_sources(self):
        """静态证明：不许任何文件再写 episode 步数的数字兜底。"""
        offenders = []
        nfiles = 0
        lo, hi = self._self_exempt_range()
        for dirpath, dirs, files in os.walk(ROOT):
            dirs[:] = [d for d in dirs if d not in
                       {".git", "__pycache__", "node_modules", ".venv310", ".idea",
                        "data", "results", "deliverables", "paper"}]
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                full = os.path.join(dirpath, fn)
                nfiles += 1
                rel = os.path.relpath(full, ROOT).replace("\\", "/")
                with io.open(full, encoding="utf-8", errors="replace") as fh:
                    for hit in self._scan_text(rel, fh.read()):
                        if rel == self.SELF_REL:
                            ln = int(hit.split(":")[1].split()[0])
                            if lo <= ln <= hi:
                                continue          # 样本本体，判别式要用的字面量
                        offenders.append(hit)
        # 扫到多少要印出来：清单为空时 offenders 必然为空，那是"零次通过"不是"通过"
        self.assertGreater(nfiles, 50, "只扫到 %d 个 .py 文件，遍历范围一定错了" % nfiles)
        self.assertEqual(offenders, [],
                         "发现残留的 episode 步数兜底默认值（已扫 %d 个 .py，"
                         "本文件豁免范围仅 _samples() 的 %d-%d 行）：\n  %s"
                         % (nfiles, lo, hi, "\n  ".join(offenders)))

    def expected_self_hits(self):
        """判别式样本里"期望被抓"的条数 —— 与 _samples() 同一份来源，不另抄数字。"""
        return sum(1 for _t, hit, _why in self._samples() if hit)

    @staticmethod
    def _samples():
        """判别式样本：(文本, 期望是否被抓, 为什么)。

        这是"扫描器有没有牙"的唯一答案来源 —— 上面那条"本文件应有几条命中"也用它，
        所以两边不会各抄一份数字。
        """
        return [
            ('a = cfg.get("episode_max_steps", 1200)   # 不再使用', True, "注释洗白"),
            ('a = cfg.get("episode_max_steps", 1200)', True, "裸兜底"),
            ("steps = args.episode_steps or 2000  # 历史上一直是这个数", True, "or 型兜底"),
            ("run(default_steps=1200)  # 原先的默认", True, "default_steps 型"),
            ('# a = cfg.get("episode_max_steps", 1200)  纯注释行放行', False, "纯注释"),
            ('assertEqual(s.episode_max_steps, 4321)', False, "断言不该误伤"),
            ('KEY = "episode_max_steps"  # 只提键名不提数字', False, "无兜底"),
            ('x = "#tag" ; a = cfg.get("episode_max_steps", 999)', True,
             "含 # 的字符串不该把后面的兜底截掉"),
            # 文档散文要放行，但放行靠"它是 docstring"这个**语法事实**，
            # 不是靠句子里出现了"原先/历史上"这几个字
            ('def f():\n    """原先签名收一个 default_steps=1200 作为兜底。"""\n    return 1\n',
             False, "docstring 散文"),
            ('"""\n历史上 args.episode_steps or 2000 是默认值。\n"""\nVALUE = 3600\n',
             False, "模块 docstring 散文"),
            ('def f():\n    """docstring"""\n    return cfg.get("episode_max_steps", 1200)\n',
             True, "docstring 之后的真兜底仍要抓到"),
        ]

    def test_the_scanner_itself_catches_a_laundered_fallback(self):
        """判别式：扫描器必须抓得住"兜底 + 散文注释"这种洗白写法。

        这条是被本轮自己的假绿逼出来的：旧版按整行找关键词放行，
        `... cfg.get("episode_max_steps", 1200)   # 不再使用` 大摇大摆过了扫描。
        这些样本走的是与真文件完全相同的判据（同一个 _scan_text）。
        """
        for text, should_hit, why in self._samples():
            got = self._scan_text("样本.py", text + "\n")
            self.assertEqual(bool(got), should_hit,
                             "%s：%r 判成 %s（期望 %s）"
                             % (why, text, "抓到" if got else "放行",
                                "抓到" if should_hit else "放行"))

    def test_every_entry_point_resolves_to_the_same_number(self):
        """所有入口必须给出同一个数，否则就是第二套默认换了个形式活着。

        为什么不能用 `import environment`：本仓的 discover 里 `test_command_console.py`
        会往 `sys.modules["environment"]` 装一个轻量桩，并且在真实导入失败时**故意把桩留下**
        （对它自己合理）。于是这条守门用例拿到的是假模块，报
        `AttributeError: module 'environment' has no attribute 'DEFAULT_EPISODE_MAX_STEPS'`
        —— 一个"名字对了但不是那个文件"的错误结论，在非作者机器上会被读成"仿真坏了"。
        现在按**文件路径**加载，并断言加载到的确实是那个文件（把判据从"属性存在吗"
        升级成"是不是同一个文件的同一个值"）。
        """
        from console import _preflight

        cfg = get_shared_config()
        expected = cfg["environment"]["episode_max_steps"]

        try:
            env_mod, env_path = _preflight.load_kernel_environment()
        except BaseException as exc:      # 缺 numpy/shapely 等 → 这是环境不够，不是判据失败
            msg = "%s: %s" % (type(exc).__name__, exc)
            m = re.search(r"No module named '([^']+)'", msg)
            if m and m.group(1).split(".")[0] in _preflight.DEPS:
                self.skipTest(msg + "\n" + _preflight.explain(_preflight.DEPS))
            # 缺的是**本仓自己的模块**（如 drone / task_generator）：那不是"机器没装包"，
            # 而是加载方式错了。以前就是这里 skipTest，让这条门在两个解释器下都不跑。
            self.fail("内核加载失败，但不是缺第三方依赖：\n  %s\n"
                      "skip 掉等于这条门永不运行 —— 要修的是加载路径/方式" % msg)
        self.assertEqual(Path(env_mod.__file__).resolve(),
                         (ROOT / "frontend" / "environment.py").resolve(),
                         "加载到的不是内核文件，断言会打在别的东西上")
        self.assertIn("DEFAULT_EPISODE_MAX_STEPS", vars(env_mod),
                      "内核文件里没有该常量（不是被桩顶掉，就是它真被删了）")
        self.assertEqual(int(env_mod.DEFAULT_EPISODE_MAX_STEPS), int(expected))

        for mod_name in ("run_ga", "run_pso", "run_ortools"):
            try:
                mod = _preflight.load_frontend_module(mod_name)
            except BaseException as exc:
                self.skipTest("%s 无法加载（环境不够）：%s: %s" % (mod_name, type(exc).__name__, exc))
            self.assertEqual(int(mod._resolve_episode_steps()), int(expected),
                             "%s 解析到的步数与真源不一致" % mod_name)
        rg = _preflight.load_frontend_package_module("greedy", "run_greedy")
        self.assertEqual(int(rg._resolve_episode_steps()), int(expected))


if __name__ == "__main__":
    unittest.main()
