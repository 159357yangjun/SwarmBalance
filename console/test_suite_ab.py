# -*- coding: utf-8 -*-
"""A/B 那把尺子自己的用例：它说"零丢失"之前，先被要求咬得住两类**真发生过**的回归。

来历：`release_check` 合批那次，改前 939 行、改后 43 行，缺的全是 `ResourceWarning` ——
而套件**照样全绿**。也就是说"换了采集方式会不会少信息"这件事，靠读代码看不出来，
靠跑一遍绿也看不出来。所以尺子入库，并且：
- 正例（探针小套件两面）必须 `only_before=0`；
- 两个反例（M1 静音 warning、M2 丢掉 stdout 那一路）必须 `only_before>0`，
  且丢的东西能被点名 —— 不然它的 0 只是一个"没东西可比"的 0。
探针套件只跑一次 A、一次 B、一次 M1，成本在秒级；真套件（200+ 条）的同一比对由
`python console/_suite_ab.py --capture/--compare` 手动跑，不进 discover。
"""
from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "console") not in sys.path:
    sys.path.insert(0, str(ROOT / "console"))
import _suite_ab as SA                            # noqa: E402
import _preflight as PF                           # noqa: E402
from test_preflight_capture import (M_FAIL, M_GLUE, M_STDERR,  # noqa: E402
                                    M_STDOUT1, M_STDOUT2, build_probe)

SANDBOX = ROOT / "results" / "adhoc" / "_suite_ab_probe"
FLOOR = 6                       # 探针套件的单元数远小于真套件，下限跟着降（真跑用默认 FLOOR）


class SuiteAbTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        shutil.rmtree(str(SANDBOX), ignore_errors=True)
        SANDBOX.mkdir(parents=True)
        cls.probe = build_probe()
        SA.capture(str(SANDBOX), cwd=cls.probe)
        cls.a_text = SA.join_streams(SA.read(SANDBOX / "a_stdout.txt"),
                                      SA.read(SANDBOX / "a_stderr.txt"))
        cls.b_stdout = SA.read(SANDBOX / "b_stdout.txt")
        cls.b_stderr = SA.read(SANDBOX / "b_stderr.txt")
        cls.b_text = SA.merge_b(cls.b_stdout, cls.b_stderr)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(str(cls.probe), ignore_errors=True)
        shutil.rmtree(str(SANDBOX), ignore_errors=True)

    def test_probe_sides_carry_every_marked_output(self):
        """前提不成立就别往下比：三路标记 + 失败正文都必须在两侧出现。"""
        for mark in (M_STDOUT1, M_STDOUT2, M_STDERR, M_FAIL):
            self.assertIn(mark, self.a_text, "A 面（改前那条命令）里没有 %s" % mark)
            self.assertIn(mark, self.b_text, "B 面（现在的采集）里没有 %s" % mark)
        self.assertIn(M_GLUE, self.a_text, "A 面没有那条以 `{` 开头不带换行的 print")
        self.assertIn(M_GLUE, self.b_text, "B 面没有那条以 `{` 开头不带换行的 print")

    def test_current_collector_loses_nothing(self):
        """正例：两侧同尺之后 only_before 必须是 0，且用例数与点串恒等式都成立。"""
        r = SA.compare(self.a_text, self.b_text, floor=FLOOR)
        self.assertEqual(r["tests_a"], r["tests_b"], "两侧跑的用例数不同，不是受控比对")
        self.assertTrue(r["identity"], "点总数与 testsRun 对不上：%s" % r)
        self.assertEqual(r["only_before"], 0,
                         "现采集方式仍有丢失：%s"
                         % [k for k, _n in r["only_before_items"]])
        # 改后独有的那些必须只是采集器自己的标头，不许混进内容
        for k, _n in r["only_after_items"]:
            self.assertEqual(k, "<section-header>", "改后多出来的不是标头，是内容对不上：%s" % k)
        print("[SA_REAL] only_before=%d only_after=%d common=%d dots=%d/%d tests=%d"
              % (r["only_before"], r["only_after"], r["common"],
                 r["dots_before"], r["dots_after"], r["tests_a"]))

    def test_ruler_bites_when_warnings_are_silenced(self):
        """反例 M1（上一轮真实发生）：去掉 `warnings="default"`，尺子必须报出丢了多少行。"""
        mut = PF._CHILD_SKIP.replace('warnings="default"', '')
        self.assertNotEqual(mut, PF._CHILD_SKIP, "替换没生效，这一条会空转")
        import subprocess
        p = subprocess.run([sys.executable, "-c", mut, str(self.probe)], cwd=str(self.probe),
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=PF.isolated_env())
        r = SA.compare(self.a_text, SA.merge_b(p.stdout, p.stderr),
                       require_identity=False, floor=FLOOR)
        self.assertGreater(r["only_before"], 0,
                           "静音了整类 warning，尺子却报 0 —— 那它的 0 不值得信")
        self.assertTrue(any("ResourceWarning" in k for k, _n in r["only_before_items"]),
                        "丢失清单里没有 ResourceWarning：%s" % [k for k, _n in r["only_before_items"]])
        print("[SA_M1] only_before=%d kinds=%d"
              % (r["only_before"], len(r["only_before_items"])))

    def test_ruler_bites_when_stdout_stream_is_dropped(self):
        """反例 M2（更早一轮真实发生）：不并子进程 stdout，测试自己 print 的行必须被点名。"""
        r = SA.compare(self.a_text,
                       SA.merge_b(self.b_stdout, self.b_stderr, keep_stdout=False),
                       require_identity=False, floor=FLOOR)
        self.assertGreater(r["only_before"], 0, "丢掉一整路输出，尺子却报 0")
        missing = " ".join(k for k, _n in r["only_before_items"])
        for mark in (M_STDOUT1, M_STDOUT2):
            self.assertIn(mark, missing, "%s 被丢了却没被点名：%s" % (mark, missing[:200]))

    def test_blind_dots_make_the_run_void_not_green(self):
        """恒等式是**门**不是读数：点串切漏了就整轮作废，不许拿着可疑的 0 报通过。"""
        good = "." * 20 + "\nRan 20 tests in 0.10s\nOK\n"
        blind = "." * 5 + "\n" + "." * 5 + "\nRan 20 tests in 0.10s\nOK\n"   # 只数到 10 个
        with self.assertRaises(AssertionError) as cm:
            SA.compare(good, blind, floor=1)
        self.assertIn("[AB_DOTS_MISMATCH]", str(cm.exception))

    def test_empty_side_is_refused_not_reported_as_zero_loss(self):
        """一侧几乎空了的时候，`only_before=0` 是假的 —— 范围下限必须挡住这种空转。"""
        body = "\n".join("LINE-%d 内容" % i for i in range(30)) + "\nRan 30 tests in 0.1s\nOK\n"
        empty = "Ran 30 tests in 0.1s\nOK\n"
        with self.assertRaises(AssertionError) as cm:
            SA.compare(body, empty, floor=FLOOR)
        self.assertIn("[AB_RANGE]", str(cm.exception))

    @staticmethod
    def _fixture(extra, n=12):
        """合成夹具：n 个点 + `Ran n tests` —— 恒等式自己先成立，才轮到比内容。

        为什么点与用例数要配平：这条门（`[AB_DOTS_MISMATCH]`）先于内容比对触发，
        夹具不配平的话我测到的就只是"夹具写歪了"。
        """
        pad = "".join("PAD-%d 行\n" % i for i in range(n))
        return "." * n + "\n" + pad + extra + "Ran %d tests in 0.1s\nOK\n" % n

    def test_rules_only_flatten_spelling_not_content(self):
        """归一化只抹"同一信息的不同写法"：四条规则各自造一对，必须判为等价；
        而"少一行"必须判为不等价 —— 否则规则是在替丢失打掩护。"""
        pairs = [
            ("runner-timing", "门用时 in 0.51s\n", "门用时 in 9.99s\n"),
            ("pkg-prefix", "FAIL (console.test_a.T.t)\n", "FAIL (test_a.T.t)\n"),
            ("path-sep", "C:\\w\\console\\t.py:3: ResourceWarning: x\n",
             "C:/w/console/t.py:3: ResourceWarning: x\n"),
            ("cost-ms", "[G] cost_ms=12 | 说明\n", "[G] cost_ms=9983 | 说明\n"),
        ]
        for name, a, b in pairs:
            r = SA.compare(self._fixture(a), self._fixture(b), floor=FLOOR)
            self.assertEqual((r["only_before"], r["only_after"]), (0, 0),
                             "%s 这条规则抹平的不是写法差异：%s" % (name, r))
        # 反向：删掉一行就不是"写法差异"，必须能报出来
        r = SA.compare(self._fixture("只有改前有的一行\n"), self._fixture(""), floor=FLOOR)
        self.assertEqual(r["only_before"], 1, "少了一行却报等价：%s" % r)
        print("[SA_RULES] pairs=%d only_before_on_deleted_line=%d" % (len(pairs), r["only_before"]))

    def test_refusing_to_compare_counts_as_a_bite(self):
        """`--ablate` 不能把"尺子拒比"读成"没有回归"：AB_RANGE 必须归成有牙。

        两侧都要 25 行起步 —— 默认下限是 20 个可比单元，夹具本身太小的话这一条会
        因为"两侧都低于下限"而红，那就不是在测 `_bite`，是在测夹具写歪了。
        """
        body = self._fixture("只有改前有的一行\n", n=25)
        collapsed = self._fixture("", n=1)          # 塌到只剩裁决行：低于下限，必须被拒
        r, code = SA._bite("T", body, collapsed)
        self.assertIsNone(r, "这一对被拒了却当成比对成功：%r" % (r,))
        self.assertEqual(code, "AB_RANGE", "拒比的原因不是范围下限：%s" % code)
        # 对照：同一把尺子吃一对够大的，返回的是数字而不是拒比
        r2, code2 = SA._bite("T", self._fixture("A 行\n", n=25), self._fixture("B 行\n", n=25))
        self.assertIsNotNone(r2)
        self.assertEqual(code2, "")
        self.assertEqual(r2["only_before"], 1, "对照面没咬住那一行差异：%r" % r2)

    def test_every_rule_carries_a_reason(self):
        """规则必须写清它抹平哪个字节差 —— 无名目的规则就是给丢失开后门。"""
        for item in SA.RULES:
            self.assertEqual(len(item), 4, "规则四元组不全：%r" % (item,))
            name, rx, rep, why = item
            self.assertTrue(name and rx.pattern and why, "规则有空字段：%r" % (item,))
            self.assertTrue(len(why) >= 8, "%s 的理由太短，等于没写：%s" % (name, why))


if __name__ == "__main__":
    unittest.main()
