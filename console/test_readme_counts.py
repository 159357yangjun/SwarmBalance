# -*- coding: utf-8 -*-
"""README 里的手抄计数必须与实测一致。

为什么单独一条：README 目录树里写"7 个文件 / 74 个用例"，实测 14 / 131；
另一处写"2 个文件 / 21 个用例"，实测 2 / 24。计数一旦手抄就必然漂，而漂了没人报警 ——
本轮就是被评审照 README 跑一遍才发现的（他跑出 75，我报 74）。

判据不是"我再看一遍数字"，而是真 discover 一遍去比对：
    python console/_readme_counts.py --verify      # 不一致退出码 1
本文件把同一段判据接进 discover，所以计数漂移会让测试直接红。

三条自约束，每条都对应本轮踩过或防过的坑：
1. 测量固定用**项目 venv 解释器**起子进程 —— 就地 discover 会在缺依赖的解释器里
   量出 77 而 venv 量出 131，两个"真值"等于没有真值；
2. 扰动锚点**不硬编码当前数字** —— 上一版写死 "13 个文件 / 128 个用例"，--fix 一跑
   锚点就失效、replace 成空操作，用例以"替换没生效"失败；
3. 读写一律**按字节原样**，不用 read_text / write_text —— 仓里 README 是 CRLF，
   而 write_text(newline=None) 会把每个 \n 换成 os.linesep，于是 "\r\n" 变成 "\r\r\n"，
   一次"只改两个数字"的操作会把整份文件的行尾搞坏。
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _tool():
    spec = importlib.util.spec_from_file_location(
        "readme_counts_gate", ROOT / "console" / "_readme_counts.py")
    rc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rc)
    return rc


class ReadmeCountTests(unittest.TestCase):

    def test_measure_is_not_vacuous(self):
        """先证明测量本身数到了东西，否则后面的比对全是空转。"""
        rc = _tool()
        rows = rc.render_lines()
        # 与 TARGETS 对账，而不是钉一个手写的 2：钉死数字会让"加一个目录"这件事必须同时改这里，
        #   于是它迟早被顺手改成通过（隐身门普查那轮的根因之一就是 TARGETS 只列两处而无人报警）。
        self.assertEqual(len(rows), len(rc.TARGETS),
                         "render_lines 行数 %d != TARGETS 配置数 %d ⇒ 有目录被静默丢掉" % (
                             len(rows), len(rc.TARGETS)))
        self.assertGreaterEqual(len(rows), 3,
                                "接线后至少应覆盖 console/experiments/frontend 三处；只剩两处说明有人把 "
                                "frontend 又摘掉了（见 docs/P70_invisible_gate_census.md）")
        for _label, subdir, nfiles, ntests, _txt in rows:
            self.assertGreater(nfiles, 0, "%s/ 一个测试文件都没数到，测量失效" % subdir)
            self.assertGreater(ntests, 10,
                               "%s/ 只数到 %d 个用例，discovery 可能没生效" % (subdir, ntests))

    def test_measure_is_interpreter_independent(self):
        """用哪个解释器跑本用例，都必须量到同一个数。

        这是本轮真实缺陷的固化：早先 measure() 就地 discover，缺依赖时那 12 条所属模块
        在导入期整模块 skip、用例不进计数，同一条命令量出 130 与 77。
        """
        rc = _tool()
        if rc._venv_python() is None:
            self.skipTest("找不到 .venv310，无法交叉验证（当前解释器 %s）" % sys.executable)
        mine = rc.measure("console")
        proc = subprocess.run(
            [sys.executable, "-c",
             "import sys;sys.path.insert(0, r'%s');import _readme_counts as r;"
             "print('%%d,%%d' %% r.measure('console'))" % str(ROOT / "console")],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONUTF8": "1"})
        self.assertEqual(proc.returncode, 0, (proc.stderr or "")[-400:])
        got = tuple(int(x) for x in proc.stdout.strip().split(","))
        self.assertEqual(got, mine,
                         "两个解释器量出不同的数（%s vs %s）—— 计数不能当「实测真值」"
                         % (got, mine))

    def test_readme_counts_match_measured(self):
        rc = _tool()
        rows = rc.render_lines()
        text = (ROOT / "README.md").read_bytes().decode("utf-8")
        #: ⚠ 按**目录标签**配对，不按出现顺序。位置式 zip 是本轮实测驳回的形状：
        #:   往 README 中间插一个新目录的计数字位会把后面的位顶偏，于是 verify 报出
        #:   "experiments/：README 写 2 个文件 / 19 个用例" —— 那是**误配不是漂移**，
        #:   但它长得太像真漂移，很容易被下一个人当"数字过期"直接 --fix 覆盖掉。
        claims = {m.group("dir"): (int(m.group("nf")), int(m.group("nt")))
                  for m in rc.CLAIM_PAT.finditer(text)}
        measured = {r[1]: (r[2], r[3]) for r in rows}
        self.assertEqual(sorted(claims), sorted(measured),
                         "README 的计数字位目录集与 TARGETS 测到的目录集不等：README=%s TARGETS=%s"
                         % (sorted(claims), sorted(measured)))
        for subdir, (nf, nt) in sorted(measured.items()):
            self.assertEqual(claims[subdir], (nf, nt),
                             "%s/：README 写 %s，实测 %s。修复：python console/_readme_counts.py --fix"
                             % (subdir, claims[subdir], (nf, nt)))
        # 判别式：把三段声明**打乱顺序**重排后，按标签配对仍必须全对（位置式在这里会红）
        order = [l for l in text.splitlines() if rc.CLAIM_PAT.search(l)]
        self.assertGreaterEqual(len(order), 3, "[RC_BLIND] 计数字位不足三处，顺序判据无从构造")
        shuffled = list(reversed(order))
        for line_new, line_old in zip(shuffled, order):
            d_new = rc.CLAIM_PAT.search(line_new).group("dir")
            d_old = rc.CLAIM_PAT.search(line_old).group("dir")
            self.assertIn(d_new, measured, "[RC_BLIND] 打乱后出现未知目录 %s" % d_new)
            vals = tuple(int(x) for x in rc.CLAIM_PAT.search(line_new).group("nf", "nt"))
            self.assertEqual(vals, measured[d_new],
                             "[RC_POSITIONAL] 第 %s 行的值与其目录不符 ⇒ 说明声明是按位置写的" % d_new)

    def test_fix_is_byte_noop_when_readme_is_current(self):
        """README 已是实测值时，--fix 必须一个字节都不动（含行尾）。

        原先 fix() 用 read_text/write_text：CRLF 副本上读时 \r\n 被折成 \n、
        写时又把每个 \n 换成 os.linesep，结果把整份文件重写成 \r\r\n 那类坏行尾；
        在 LF 检出的副本上则会把全文件行尾翻成 CRLF，git diff 显示整份文件被改。
        """
        rc = _tool()
        readme = ROOT / "README.md"
        original = readme.read_bytes()
        before = rc.line_ending_stats(readme)
        try:
            self.assertEqual(rc.fix(), 0, "--fix 之后 --verify 应当通过")
        finally:
            readme.write_bytes(original)
        self.assertEqual(rc.line_ending_stats(readme), before, "行尾统计被改动了")
        self.assertEqual(readme.read_bytes(), original,
                         "README 本已是实测值，--fix 却改动了字节 —— fix 不幂等或行尾被翻")

    def test_verify_goes_red_when_readme_is_stale(self):
        """证明 --verify 真会红。三道"变异自证生效"：改到内存、落到盘上、子进程报红。

        少任何一道，都可能像本轮那样"看到一个 FAIL 其实是上一个变异的残留"。
        """
        rc = _tool()
        readme = ROOT / "README.md"
        original = readme.read_bytes()
        try:
            text = original.decode("utf-8")
            m = rc.CLAIM_PAT.search(text)
            self.assertIsNotNone(m, "README 里找不到计数字位，本用例的判据是空转")
            stale = rc.CLAIM_PAT.sub(lambda x: "%s%d%s%d%s" % (
                x.group("prefix"), int(x.group("nf")) + 7, x.group("mid"),
                int(x.group("nt")) + 7, x.group("tail")), text, count=1)
            self.assertNotEqual(stale, text, "扰动没改动任何字节，判据是空转")
            # 只该有数字变：把数字抹成 # 后两份文本必须同形 —— 这比"长度差多少"稳，
            # 因为 +7 跨不进位（14→21、131→138）是巧合，95→102 就会变长。
            skel = lambda s: re.sub(r"\d", "#", s)
            self.assertEqual(skel(stale), skel(text),
                             "扰动改到了数字以外的字符，测的就不是计数判据了")
            self.assertEqual(len(rc.CLAIM_PAT.findall(stale)), len(rc.CLAIM_PAT.findall(text)))
            self.assertNotEqual(rc.CLAIM_PAT.findall(stale), rc.CLAIM_PAT.findall(text),
                                "扰动后计数字位的值仍然相同")

            rc.write_text_lossy(readme, stale)
            back = readme.read_bytes().decode("utf-8")
            self.assertEqual(back, stale, "写盘没生效 —— 后面测的是没改过的文件")
            self.assertIn(str(int(m.group("nt")) + 7), back, "盘上找不到扰动后的值")
            self.assertEqual(rc.line_ending_stats(readme), rc.line_ending_stats_from_bytes(
                original), "写扰动时把行尾改了")

            proc = subprocess.run(
                [sys.executable, str(ROOT / "console" / "_readme_counts.py"), "--verify"],
                cwd=str(ROOT), capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                env={**os.environ, "PYTHONUTF8": "1"})
            self.assertEqual(proc.returncode, 1,
                             "README 计数被改错了，--verify 却没红：\n%s" % proc.stdout[-600:])
            self.assertIn("实测", proc.stdout, "拒绝原文要带实测值，不能只说不一致")
        finally:
            readme.write_bytes(original)
        self.assertEqual(readme.read_bytes(), original, "还原失败会弄脏共用工作树")


if __name__ == "__main__":
    unittest.main()
