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
        self.assertEqual(len(rows), 2, "TARGETS 配了两处，同步检查一下")
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
        claims = [(int(m.group(2)), int(m.group(4))) for m in rc.COUNT_PAT.finditer(text)]
        self.assertEqual(len(claims), len(rows),
                         "README 里有 %d 处计数字位，测量了 %d 个目录 —— 对不上"
                         % (len(claims), len(rows)))
        for (cn, ct), (_label, subdir, nf, nt, _t) in zip(claims, rows):
            self.assertEqual((cn, ct), (nf, nt),
                             "%s/：README 写 %d 个文件 / %d 个用例，实测 %d / %d。"
                             "修复：python console/_readme_counts.py --fix"
                             % (subdir, cn, ct, nf, nt))

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
            m = rc.COUNT_PAT.search(text)
            self.assertIsNotNone(m, "README 里找不到计数字位，本用例的判据是空转")
            stale = rc.COUNT_PAT.sub(lambda x: "%s%d%s%d%s" % (
                x.group(1), int(x.group(2)) + 7, x.group(3),
                int(x.group(4)) + 7, x.group(5)), text, count=1)
            self.assertNotEqual(stale, text, "扰动没改动任何字节，判据是空转")
            # 只该有数字变：把数字抹成 # 后两份文本必须同形 —— 这比"长度差多少"稳，
            # 因为 +7 跨不进位（14→21、131→138）是巧合，95→102 就会变长。
            skel = lambda s: re.sub(r"\d", "#", s)
            self.assertEqual(skel(stale), skel(text),
                             "扰动改到了数字以外的字符，测的就不是计数判据了")
            self.assertEqual(len(rc.COUNT_PAT.findall(stale)), len(rc.COUNT_PAT.findall(text)))
            self.assertNotEqual(rc.COUNT_PAT.findall(stale), rc.COUNT_PAT.findall(text),
                                "扰动后计数字位的值仍然相同")

            rc.write_text_lossy(readme, stale)
            back = readme.read_bytes().decode("utf-8")
            self.assertEqual(back, stale, "写盘没生效 —— 后面测的是没改过的文件")
            self.assertIn(str(int(m.group(4)) + 7), back, "盘上找不到扰动后的值")
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
