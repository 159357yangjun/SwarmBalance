# -*- coding: utf-8 -*-
"""README 里的手抄计数必须与实测一致。

为什么单独一条：README 目录树里写"7 个文件 / 74 个用例"，实测是 13 / 128；
另一处写"2 个文件 / 21 个用例"，实测 2 / 24。计数这种东西一旦手抄就必然漂，
而漂了没人报警 —— 本轮就是被评审照 README 跑一遍才发现的（他跑出 75，我说 74）。

判据不是"我再看一遍数字"，而是真 discover 一遍去比对：
    python console/_readme_counts.py --verify      # 不一致退出码 1
本用例把同一段逻辑跑起来，所以计数漂移会让 `unittest discover` 直接红。
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReadmeCountTests(unittest.TestCase):

    def test_readme_counts_match_measured(self):
        import importlib.util

        path = ROOT / "console" / "_readme_counts.py"
        spec = importlib.util.spec_from_file_location("readme_counts_gate", path)
        rc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rc)

        rows = rc.render_lines()
        # 先证明测量本身非空转：真的数到了文件与用例
        for label, subdir, nfiles, ntests, _txt in rows:
            self.assertGreater(nfiles, 0, "%s/ 一个测试文件都没数到，测量失效" % subdir)
            self.assertGreater(ntests, 10, "%s/ 只数到 %d 个用例，discovery 可能没生效"
                               % (subdir, ntests))

        text = (ROOT / "README.md").read_text(encoding="utf-8")
        claims = [(int(a), int(b)) for a, b in re.findall(
            r"test_\*\.py\s+#\s*(\d+) 个文件 / (\d+) 个用例", text)]
        self.assertEqual(len(claims), len(rows),
                         "README 里有 %d 处计数字位，测量了 %d 个目录 —— 对不上"
                         % (len(claims), len(rows)))
        for (cn, ct), (_label, subdir, nf, nt, _t) in zip(claims, rows):
            self.assertEqual((cn, ct), (nf, nt),
                             "%s/：README 写 %d 个文件 / %d 个用例，实测 %d / %d。"
                             "修复：python console/_readme_counts.py --fix"
                             % (subdir, cn, ct, nf, nt))

    def test_preflight_gate_reports_red_when_readme_stale(self):
        """证明 --verify 真的会红：临时把 README 的计数改错再还原。

        这里刻意**不硬编码当前数字** —— 上一版我写死了 "13 个文件 / 128 个用例" 当锚点，
        而 --fix 一跑它就变了，replace 变成空操作、断言以"替换没生效"失败。
        一个会检测手抄计数的用例，自己不能靠手抄锚点。
        """
        import os
        import subprocess
        import sys

        readme = ROOT / "README.md"
        original = readme.read_bytes()
        pat = re.compile(r"(test_\*\.py\s+#\s*)(\d+)( 个文件 / )(\d+)( 个用例)")
        try:
            text = original.decode("utf-8")
            m = pat.search(text)
            self.assertIsNotNone(m, "README 里找不到计数字位，本用例的判据是空转")
            # 用 +7 保证与任何真实值都不相等，无需知道当前是多少
            stale = pat.sub(lambda x: "%s%d%s%d%s" % (
                x.group(1), int(x.group(2)) + 7, x.group(3),
                int(x.group(4)) + 7, x.group(5)), text, count=1)
            self.assertNotEqual(stale, text, "扰动没改动任何字节，判据是空转")
            readme.write_text(stale, encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(ROOT / "console" / "_readme_counts.py"), "--verify"],
                cwd=str(ROOT), capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                env={**os.environ, "PYTHONUTF8": "1"})
            self.assertEqual(proc.returncode, 1,
                             "README 计数被改错了，--verify 却没红：\n%s" % proc.stdout[-600:])
            self.assertIn("实测", proc.stdout, "拒绝原文里要给实测值，不能只说不一致")
        finally:
            readme.write_bytes(original)
        self.assertEqual(readme.read_bytes(), original, "还原失败会弄脏共用工作树")


if __name__ == "__main__":
    unittest.main()
