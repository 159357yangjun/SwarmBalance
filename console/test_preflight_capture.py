# -*- coding: utf-8 -*-
"""套件输出必须**一路不少**地到达 `release_check` —— 这条用例钉住三路捕获与哨兵解析。

来历（本轮 A/B 取证，不是设想）：把"父进程跑 discover + 子进程再跑一遍拿 skip"合成一遍之后，
逐行比对改前/改后可见输出，发现两件事：
1. 测试自己 print 到 **stdout** 的内容掉在 `proc.stdout` 里被丢弃（改前那一段是 `stdout+stderr` 全收）；
2. 更糟的一条：有一条测试**不带换行**打印以 `{` 开头的内容，JSON 就和它粘成同一行，
   `startswith("{")` 选中混合行 ⇒ `JSONDecodeError`，**整份诊断归零**（实测改前 14 行可见、改后 0 行）。
   也就是说：一条正常的测试输出，能让发布检查把"跑过的套件"报成"没能跑起来"。

所以这里同时钉住三路（runner 正文 / 子进程 stdout / 子进程 stderr）、进度点行、以及那个反例。
断言只用标记，不钉 id 前缀 —— 改后的测试 id 是 `console.test_probe_io.…`（带包名），
这一点在 CHANGELOG 里具名说明，不假装它没变。
"""
from __future__ import annotations

import io
import os
import re
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys                                        # noqa: E402
if str(ROOT / "console") not in sys.path:
    sys.path.insert(0, str(ROOT / "console"))
import _preflight as PF                           # noqa: E402

M_STDOUT1 = "PFMARK-STDOUT-001"
M_STDOUT2 = "PFMARK-STDOUT-004"
M_STDERR = "PFMARK-STDERR-002"
M_GLUE = "PFMARK-GLUE-003"
M_FAIL = "PFMARK-FAIL-005"

PROBE_SRC = u'''# -*- coding: utf-8 -*-
import sys, unittest


class ProbeIO(unittest.TestCase):
    def test_a_stdout(self):
        print("%(s1)s 测试自己 print 到 stdout")
        print("%(s2)s 第二行 stdout")

    def test_b_stderr(self):
        sys.stderr.write("%(e)s 测试自己写到 stderr\\n")

    def test_c_glue(self):
        # 不带换行、以 `{` 开头：这一条就是那个能让 JSON 解析崩掉的形状
        sys.stdout.write('{"%(g)s": "no newline"}')

    def test_d_fail(self):
        self.fail("%(f)s 故意失败")

    def test_e_ok(self):
        self.assertTrue(True)
''' % {"s1": M_STDOUT1, "s2": M_STDOUT2, "e": M_STDERR, "g": M_GLUE, "f": M_FAIL}


def build_probe():
    d = tempfile.mkdtemp(prefix="pf-capture-")
    os.makedirs(os.path.join(d, "console"))
    io.open(os.path.join(d, "console", "__init__.py"), "w", encoding="utf-8").write("")
    io.open(os.path.join(d, "console", "test_probe_io.py"), "w",
            encoding="utf-8").write(PROBE_SRC)
    return Path(d)


class PreflightCaptureTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.d = build_probe()
        cls._real_root = PF.ROOT
        PF.ROOT = cls.d                     # 让子进程发现这份小套件，而不是重跑仓里 209 条
        try:
            cls.info = PF.run_console_suite()
            cls.err = None
        except Exception as exc:           # noqa: BLE001 - 崩了要能报出来，不能吞
            cls.info, cls.err = None, "%s: %s" % (type(exc).__name__, str(exc)[:300])
        finally:
            PF.ROOT = cls._real_root

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(str(cls.d), ignore_errors=True)

    def test_sentinel_survives_a_brace_prefixed_print(self):
        """④ 的反例：测试可以打印以 `{` 开头且不带换行的内容，解析不许崩。"""
        self.assertIsNone(self.err, "run_console_suite() 被一条正常 print 打崩：%s" % self.err)
        self.assertGreaterEqual(self.info["tests"], 5, self.info)

    def test_all_three_streams_reach_the_detail(self):
        """三路都要到：runner 正文、子进程 stdout、子进程 stderr。少一路就是改了采集方式偷信息。"""
        det = self.info["detail"]
        for m in (M_STDOUT1, M_STDOUT2, M_STDERR, M_GLUE, M_FAIL):
            self.assertIn(m, det, "%s 没到达 detail —— 有一路输出被丢了" % m)
        self.assertIn("[stdout]", det, "stdout 段没有具名标头（丢的时候没人看得出来）")
        self.assertIn("[stderr]", det, "stderr 段没有具名标头")
        self.assertIn("FAIL: test_d_fail", det, "失败正文不在 detail 里")
        self.assertTrue(re.search(r"^\s*\.{1,}[FE]", det, re.M),
                        "进度点行没了 —— verbosity 被调回去就等于关了一种输出")
        self.assertIn("Ran 5 tests", det, self.info["detail"][-400:])

    def test_counts_are_not_replaced_by_the_text(self):
        """计数与正文都得在：只有正文就退化成 grep 文本，只有计数就是"FAIL 但不说为什么"。"""
        self.assertEqual(self.info["failures"], 1, self.info["detail"][-400:])
        self.assertEqual(self.info["errors"], 0, self.info["detail"][-400:])
        self.assertEqual(self.info["tests"], 5)
        self.assertEqual(len(self.info["skipped"]), 0)

    def test_parser_takes_the_last_sentinel_not_the_first_brace(self):
        """解析按哨兵、且取**最后**一条：JSON 是套件跑完后才写的。"""
        self.assertTrue(PF._CHILD_MARK.endswith("\t"), "哨兵要能挡住正常输出行")
        self.assertNotIn(PF._CHILD_MARK, self.info["detail"],
                         "哨兵行漏进 detail —— 等于把整份 JSON 又抄一遍进正文")


if __name__ == "__main__":
    unittest.main()
