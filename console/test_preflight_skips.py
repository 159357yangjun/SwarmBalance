# -*- coding: utf-8 -*-
"""skip 归因清单本身必须不是空转 —— 它是个探针，探针要自报扫到多少、命中多少。

为什么单独一条：`OK (skipped=12)` 会被读成"过了 12 条"，所以 release_check 与
`_preflight --skips` 会把每条 skip 归因成「缺哪个包 → 哪个测试模块 → 几条」。
但如果归因本身漏识别（第一版就是 12 条只认出 1 条），这份清单会**看起来很干净地少报**，
比没有清单更危险 —— 它给人一种"已经解释过了"的感觉。

本文件的输入是**合成**的 skip 列表，所以不依赖本机装了哪些包：
两种 reason 写法都要认（`缺少依赖：X` 与裹在 traceback 里的 `No module named 'X'`），
不认的那种会被诚实归到 "(原因里没写缺哪个包)" 而不是被悄悄丢掉。
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _pf():
    spec = importlib.util.spec_from_file_location(
        "console_preflight_skips", ROOT / "console" / "_preflight.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class SkipAttributionTests(unittest.TestCase):

    def setUp(self):
        self.pf = _pf()

    def test_both_reason_styles_are_attributed_to_a_package(self):
        skipped = [
            ("console.test_a.Some.test_one",
             "  缺少依赖：fastapi, shapely（pip 包名：fastapi shapely）\n"
             "  受影响测试模块：console/test_server_guards.py\n"),
            ("console.test_b.LiveTests.test_two",
             "tools.osm 导入失败（缺 numpy 等）：ModuleNotFoundError: No module named 'shapely'"),
        ]
        buckets = self.pf.bucket_skips(skipped)
        pk = {k[0] for k in buckets}
        self.assertIn("fastapi, shapely", pk, "explain() 那种写法没被认出来")
        self.assertIn("shapely", pk, "traceback 里 No module named 那种写法没被认出来")
        self.assertNotIn("(原因里没写缺哪个包)", pk,
                         "两条都该归因成功，出现兜底值说明识别漏了")
        self.assertEqual(sum(buckets.values()), 2, "条数不等于输入条数，说明有合并/丢弃")

    def test_every_input_case_is_accounted_for(self):
        """恒等式：分桶后的总数必须等于输入条数，且每个桶都要能追溯到具体用例。

        模块名是从 test id 尾部截掉的（`模块.类.方法` -> `模块`），
        第一版我在这里写成了 `console.t0.C`，把**类名也当成了模块的一部分**，
        红的是用例不是实现 —— 但红得有价值：它证明桶的键不是摆设，写错就抓得到。
        """
        skipped = [("console.mod_%02d.C.test_%d" % (i, i), "缺少依赖：foo（pip 包名：foo）")
                   for i in range(5)]
        buckets = self.pf.bucket_skips(skipped)
        self.assertEqual(sum(buckets.values()), len(skipped),
                         "有 skip 没进任何桶（被吞）或重复计数")
        self.assertEqual(sorted(buckets), sorted([("foo", "console.mod_%02d" % i) for i in range(5)]),
                         "桶键应当一一对应到 5 个不同模块；合并或截错都会让这张表骗人")

    def test_attribution_reads_the_repo_own_skip_message(self):
        """归因要认**本仓自己生成的**那份 skip 原因，而不是我在用例里手抄的近似文本。

        这是本文件唯一接上真实生产者的一条：手抄文本会把"explain() 改了措辞、
        正则不再匹配"这类漂移悄悄吞掉 —— 而漂移的后果正是清单少报，与第一版
        12 条只认出 1 条是同一种失败。
        """
        bogus = "definitely_not_installed_probe_pkg"
        self.assertEqual(self.pf.missing([bogus]), [bogus],
                         "探针包竟然能导入，本用例的判据会空转")
        try:
            self.pf.require(bogus, gated_in="console/test_probe_gate.py")
        except unittest.SkipTest as exc:
            reason = str(exc)
        else:
            self.fail("require() 在缺依赖时没有抛 SkipTest")

        self.assertIn("缺少依赖：%s" % bogus, reason, "explain() 的措辞变了，下面这条断言要跟着改")
        skipped = [("console.test_probe_gate.ProbeTests.test_x", reason)]
        buckets = self.pf.bucket_skips(skipped)
        self.assertEqual(list(buckets), [(bogus, "console/test_probe_gate.py")],
                         "真实 skip 原因没能归因到「缺哪个包 -> 哪个模块」")
        self.assertNotIn("(原因里没写缺哪个包)", list(buckets)[0][0],
                         "识别失败兜底值不该出现在这里")
        self.assertIn("console/test_probe_gate.py", self.pf.render_skips(skipped))

    def test_empty_input_says_no_skip_rather_than_looking_clean(self):
        """空集合要明说"没有 skip"，不能渲染成一张空白表让人以为已经解释过了。"""
        self.assertEqual(self.pf.render_skips([]), "（本次运行没有 skip）")

    def test_unattributable_case_is_labeled_not_dropped(self):
        """认不出包名时必须留下可见标签，而不是静默少一条。"""
        buckets = self.pf.bucket_skips([("console.t.X.test_y", "某些别的原因")])
        self.assertEqual(sum(buckets.values()), 1)
        self.assertIn("(原因里没写缺哪个包)", {k[0] for k in buckets})

    def test_render_is_ascii_safe_for_gbk_console(self):
        """输出里不许有 GBK 打不出的字符。

        第一版用了 `⇒`，在本机 GBK 控制台直接 UnicodeEncodeError 把整条命令崩掉 ——
        一个用来解释环境的工具自己崩了，比没有更糟。
        """
        text = self.pf.render_skips([("console.t.C.test_a", "缺少依赖：shapely（pip 包名：shapely）")])
        try:
            text.encode("gbk")
        except UnicodeEncodeError as exc:
            self.fail("render_skips 输出含 GBK 打不出的字符（评审控制台常见）：%s\n%s" % (exc, text))
        self.assertIn("->", text)

    def test_summary_line_counts_agree_with_lists(self):
        """自报行里的数字必须与真实结构一致（checked/matched 同形检查）。"""
        data = {"tests": 78, "failures": 0, "errors": 0,
                "skipped": [("console.t.C.test_a", "缺少依赖：shapely（pip 包名：shapely）")]}
        rendered = self.pf.render_skips(data["skipped"])
        self.assertIn("合计 1 条", rendered)
        self.assertNotIn("(未写明", rendered + self.pf.render_skips(data["skipped"]))


if __name__ == "__main__":
    unittest.main()
