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

    def test_f_leak(self):
        # 故意漏一个句柄：`ResourceWarning` 默认是被忽略的，只有 runner 带
        # warnings='default'（`unittest.main()` 的默认）才会浮出来 —— 这条就是钉那个开关的。
        import gc
        _fh = open(__import__("os").devnull, "w")
        del _fh
        gc.collect()

    def test_e_ok(self):
        self.assertTrue(True)
''' % {"s1": M_STDOUT1, "s2": M_STDOUT2, "e": M_STDERR, "g": M_GLUE, "f": M_FAIL}


def build_probe():
    d = tempfile.mkdtemp(prefix="pf-capture-")
    os.makedirs(os.path.join(d, "console"))
    # 用 write_text 而不是 io.open(...).write(...)：后者漏句柄，会在真套件里冒出两条
    # `ResourceWarning` —— 那是**我自己漏的**，不是探针。探针是 PROBE_SRC 里的 test_f_leak。
    (Path(d) / "console" / "__init__.py").write_text("", encoding="utf-8")
    (Path(d) / "console" / "test_probe_io.py").write_text(PROBE_SRC, encoding="utf-8")
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
        self.assertIn("Ran 6 tests", det, self.info["detail"][-400:])

    def test_counts_are_not_replaced_by_the_text(self):
        """计数与正文都得在：只有正文就退化成 grep 文本，只有计数就是"FAIL 但不说为什么"。"""
        self.assertEqual(self.info["failures"], 1, self.info["detail"][-400:])
        self.assertEqual(self.info["errors"], 0, self.info["detail"][-400:])
        self.assertEqual(self.info["tests"], 6)
        self.assertEqual(len(self.info["skipped"]), 0)

    def test_resource_warnings_are_not_silenced(self):
        """`ResourceWarning` 必须浮出来。

        真套件 A/B 实测：合并成一遍之后改前 939 行可见、改后只剩 43 行，缺的 896 行全是
        `ResourceWarning: unclosed file` —— 因为 `unittest.main()` 会给 runner 传
        `warnings="default"`，而手写的 `TextTestRunner(...)` 不传就等于让这类诊断回到
        默认过滤器（对它是 ignore）。这条钉住那个开关：漏一个句柄，detail 里必须有它。
        """
        det = self.info["detail"]
        self.assertIn("ResourceWarning", det,
                      "warning 通道被静音了 —— 那就是把 896 行诊断悄悄丢掉的那次改动")
        self.assertIn("[stderr]", det, "warning 走的是子进程 stderr，段标头必须具名")
        cen = PF.warning_census(det)
        self.assertIn("ResourceWarning", cen, cen)
        self.assertEqual(PF.warning_census("一段没有 warning 的输出"), "warnings=0",
                         "0 要能印出来 —— 否则分不清「没有」和「通道被静音」")
        print("[PF_WARN_CENSUS] %s" % cen)
        print("[PF_WARN_CHANNEL] ResourceWarning 到达 detail=%s"
              % ("ResourceWarning" in det))

    def test_warning_census_is_not_inflated_by_the_instrument(self):
        """量具不能把自己印的行算成被测量的量 —— 这条就是被抓过之后的形状。

        上一版按类名在全文里计数，真套件实测报 `ResourceWarning:6` 而盘上只漏 2 个句柄：
        多出的是本用例自己那两行 `[PF_*]` 与 Python 每条 warning 的 `Enable tracemalloc` 伴行。
        现在数的是**带出处的发射行**，同时把"全文提及"并排列出来 —— 自占的部分要看得见，
        不是把它抹掉（抹掉之后 `warnings=0` 与"通道被静音"就又分不开了）。
        """
        det = "\n".join([
            r"C:\w\console\test_x.py:11: ResourceWarning: unclosed file <_io.TextIOWrapper>",
            "ResourceWarning: Enable tracemalloc to get the object allocation traceback",
            r"C:\w\console\test_x.py:12: ResourceWarning: unclosed file <_io.TextIOWrapper>",
            "ResourceWarning: Enable tracemalloc to get the object allocation traceback",
            "[PF_WARN_CENSUS] warnings=ResourceWarning:2 带出处=2 全文提及=6",
            "[PF_WARN_CHANNEL] ResourceWarning 到达 detail=True",
        ])
        cen = PF.warning_census(det)
        self.assertEqual(cen.split()[0], "warnings=ResourceWarning:2", cen)
        self.assertIn("带出处=2", cen, "只漏 2 个句柄却报出别的数：%s" % cen)
        self.assertIn("全文提及=6", cen, "自占的那部分没有并列印出来：%s" % cen)
        # 反例：只看得到字样、看不到出处 ⇒ 带出处必须是 0，不许把提及当发射
        self.assertEqual(PF.warning_census("[SOMETHING] ResourceWarning 只是文档里提了一句").split()[0],
                         "warnings=ResourceWarning:0")
        print("[PF_WARN_SELFTEST] %s" % cen)

    def test_summary_line_is_the_verdict_not_the_last_print(self):
        """给人看的那一行必须是 `OK`/`FAILED (…)`，不能是三路合并后碰巧排最后的某条 print。

        这是本次改完真撞到的：`release_check` 的 `[OK] console 单元测试 · …` 末尾
        变成了 `[ESCAPE_MECHANISM] import=…`（一条测试自己的 print），扫输出找 OK 的人会读空。
        """
        det = self.info["detail"]
        picked = PF.summary_line(det)
        self.assertTrue(picked.startswith(("OK", "FAILED (", "ERROR")),
                        "挑出来的总结行不是裁决行：%r" % picked[:80])
        # 反例形状：detail 末尾挂一条 print，中间才有 FAILED
        fake = ("....\nFAIL: x\nAssertionError: boom\nRan 4 tests in 0.1s\nFAILED (failures=1)\n"
                + "[stdout]\nSOME-TEST-PRINT [X] import=[1, 0]\n")
        self.assertEqual(PF.summary_line(fake), "FAILED (failures=1)")
        self.assertEqual(PF.summary_line("Ran 1 test in 0.0s\nOK\n"), "OK")
        # 混合形状（这条才是真洞）：段标头是追加在正文之后的，某条测试只要打印一行以
        # `OK` 开头的内容，在合并后的全文里倒着找就会把真裁决顶掉。
        mixed = ("....\nFAIL: x\nAssertionError: boom\nRan 4 tests in 0.1s\nFAILED (failures=1)\n"
                 "[stdout]\nOK 这只是某条测试自己打印的一行\n")
        self.assertEqual(PF.summary_line(mixed), "FAILED (failures=1)",
                         "裁决行被测试自己的 print 顶掉了 —— 只能在 runner 正文那段里找")
        # 真探针套件上再验一次：它有 1 条 fail，挑出来的必须是 FAILED 而不是任何一条 print
        self.assertTrue(PF.summary_line(det).startswith("FAILED ("),
                        repr(PF.summary_line(det))[:120])
        self.assertEqual(PF.summary_line("only a print\n"), "only a print")
        self.assertEqual(PF.summary_line(""), "")

    def test_parser_takes_the_last_sentinel_not_the_first_brace(self):
        """解析按哨兵、且取**最后**一条：JSON 是套件跑完后才写的。"""
        self.assertTrue(PF._CHILD_MARK.endswith("\t"), "哨兵要能挡住正常输出行")
        self.assertNotIn(PF._CHILD_MARK, self.info["detail"],
                         "哨兵行漏进 detail —— 等于把整份 JSON 又抄一遍进正文")


if __name__ == "__main__":
    unittest.main()
