# -*- coding: utf-8 -*-
"""paper/ 侧「撤除未达」清单：分类必须双向对，事实必须是算出来的。

为什么单独一条：那六个算法名在论文里有两种身份 —— 别人做过什么（相关工作、\\cite、文献）
与我们评了什么（表格行、正文主张）。混着报的后果不是多报几条，而是**下一轮为了变绿去删
真的相关工作引用**，那是比重复数字更坏的修法。所以这里两类都钉：
待夺类漏报要红，合法类误报也要红。
"""
from __future__ import annotations

import io
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from console import _paperscan as PS  # noqa: E402
from console import _rowsets  # noqa: E402

TEX_REL = "paper/AAMAS-2023 Formatting Instructions/main.tex"


def _cls_of(text, line_no=None):
    rows = PS.classify_text(text)
    return [(r[1], r[0]) for r in rows] if line_no is None else \
        [r[1] for r in rows if r[0] == line_no]


class PaperVoidScanTests(unittest.TestCase):

    def test_legal_kinds_are_not_reported_as_defects(self):
        """相关工作与文献条目必须落在"合法"，否则下一轮会有人去删真引用。"""
        related = ("\\section{Related Work}\n"
                   "Qie et al. propose MARL; QMIX and VDN are also surveyed~\\cite{qmix}.\n")
        self.assertEqual(_cls_of(related, 2), [PS.CLS_RELATED],
                         "相关工作里的提及被当成了待夺缺陷")
        bib = ("\\begin{thebibliography}\n\\bibitem{qmix}\n"
               "QMIX: Monotonic value function factorisation.\n\\end{thebibliography}\n")
        got = [c for c, _ in _cls_of(bib)]
        self.assertEqual(set(got), {PS.CLS_BIB}, "文献条目被当成了待夺缺陷：%s" % got)

    def test_claims_are_quarantined_in_needs_decision(self):
        """表格行、摘要/关键词、正文主张都必须进"待夺"。"""
        table = ("\\begin{table}\n"
                 "QMIX & 1.000 & 0.167 & 13.67 \\\\\n"
                 "\\end{table}\n")
        self.assertEqual(_cls_of(table, 2), [PS.CLS_TABLE])
        intro = "\\section{Introduction}\nOur platform compares Greedy, PSO, GA, IQL, VDN and QMIX.\n"
        self.assertEqual(_cls_of(intro, 2), [PS.CLS_BODY],
                         "Introduction 里的「我们评了哪些算法」被放进了合法筐")
        concl = ("\\section{Conclusion}\nAccording to the weighted overall score, "
                 "the ranking is QMIX-U, VDN-U, and Greedy.\n")
        self.assertEqual(_cls_of(concl, 2), [PS.CLS_BODY],
                         "Conclusion 复述排名必须待夺，不是合法叙述")

    def test_substring_noise_is_not_matched(self):
        """词边界与大小写：`dynamically`/`requires` 这类词不该算命中。

        短名做子串匹配是这类扫描最容易犯的错 —— 报了假项，人们就会开始不信这份清单。
        """
        text = ("The requirement grows dynamically; the iq ratio and vdn-like strings "
                "appear in prose as qmixed text.\n")
        self.assertEqual(PS.NAME_RE.findall(text), [], "子串误命中：%s" % PS.NAME_RE.findall(text))
        self.assertEqual(PS.classify_text(text), [])

    def test_name_set_is_the_same_ruler_as_the_rowset(self):
        """清单顶部写着"算法名集合来自 _rowsets.WITHDRAWN"—— 这句必须可证伪。

        正则若是手抄的六个名字，那边改了这边不会动，清单就会悄悄少扫一个算法；
        所以既验现值全覆盖，也验 name_re 真的按传入集合现算。
        """
        for key in sorted(_rowsets.WITHDRAWN):
            disp = key.replace("_", "-").upper()
            self.assertEqual(PS.NAME_RE.findall("row for %s only" % disp), [disp],
                             "%s 在 WITHDRAWN 里，NAME_RE 却扫不到 —— 名单是手抄的" % disp)
        self.assertEqual(
            PS.NAME_RE.findall("QMIXv2 QMIXX preQMIX dynamically the iq ratio"), [],
            "词边界或大小写失效：清单会报出论文里根本不存在的行")
        got = PS.name_re({"foo_bar", "baz"}).findall("FOO-BAR BAZ FOO and dynamic")
        self.assertEqual(got, ["FOO-BAR", "BAZ", "FOO"],
                         "name_re 不再由键集合现算（实际 %s）—— 改 WITHDRAWN 不会带动扫描" % (got,))

    def test_real_paper_yields_both_kinds_and_is_not_vacuous(self):
        """真文件必须同时给出两类命中 —— 只有一类说明分类器在瞎分。"""
        with io.open(ROOT / TEX_REL, encoding="utf-8", errors="replace") as fh:
            rows = PS.classify_text(fh.read())
        need = [r for r in rows if r[1] in PS.NEEDS_DECISION]
        legal = [r for r in rows if r[1] not in PS.NEEDS_DECISION]
        self.assertGreaterEqual(len(need), 10,
                                "待夺命中只剩 %d 处：论文被改过，或分类器被改坏" % len(need))
        self.assertGreaterEqual(len(legal), 3,
                                "合法命中少于 3 处，说明相关工作/文献那一侧失效了")
        self.assertTrue(any(r[1] == PS.CLS_TABLE for r in need),
                        "结果表格行没被识别成结论形式")
        # 六行数据必须都在待夺里（这正是 R2 逐格证伪的那六行）
        table_rows = [r for r in need if r[1] == PS.CLS_TABLE and "&" in r[3]]
        self.assertGreaterEqual(len(table_rows), 6,
                                "结果表里待夺的行不足 6 行：%s" % [r[0] for r in table_rows])

    def test_the_stated_facts_are_computed_not_copied(self):
        """清单里"撤除没到达论文"那几个数必须由 git 现算，且与盘上的产物逐字节一致。"""
        text, _rows, facts = PS.render(ROOT)
        out = ROOT / PS.OUT_REL
        self.assertTrue(out.is_file(), "缺清单，跑 --paper-report --write")
        self.assertEqual(out.read_text(encoding="utf-8"), text,
                         "清单与代码重算不一致：论文或 paper/figure 变了没重生成")
        self.assertRegex(facts["paper_last_commit"], r"^[0-9a-f]{7}$")
        self.assertEqual(
            facts["purge_touched_paper"], 0,
            "%s 之后 paper/ 又被改过（现算命中 %d 个文件）——"
            "「撤除从未到达论文」这句已过期，重生成清单并改掉本节措辞"
            % (PS.PURGE_SHA, facts["purge_touched_paper"]))
        self.assertTrue(facts["figures"], "paper/figure 一个都没扫到，图侧结论无从谈起")
        self.assertTrue(all(f["before_purge"] for f in facts["figures"]),
                        "有图在撤除之后重生成了：%s" % [f["name"] for f in facts["figures"]
                                                        if not f["before_purge"]])

    def test_greppable_line_numbers_exist_and_match(self):
        """`不得当缺陷报` 必须挂在一行、且那一行就是全集。

        为什么盯这个形状（而不是"有没有行号"）：保护名单是按短语 grep 来用的 ——
        谁 grep `不得当缺陷报` 决定"哪些不许动"。若这个字样只挂在某个子集上（第一版就是这样，
        只挂了 3 个相关工作的行号），少列的那几处就会被当缺陷删掉，而这正是这套分类要防的事故。
        逐字节核对只挡"手改产物"，挡不住"把 render() 里这段删掉然后重生"，也挡不住挂错集合。
        """
        def ids_of(line):
            return sorted(int(x) for x in re.findall(r"\d+", line.rsplit("：", 1)[1]))
        text, rows, _facts = PS.render(ROOT)
        legal = sorted(r[0] for r in rows if r[1] not in PS.NEEDS_DECISION)
        need = sorted(r[0] for r in rows if r[1] in PS.NEEDS_DECISION)
        # 只数"带冒号带数字"的那些行 —— 章节标题 `## 合法，不得当缺陷报（共 6 处）`
        # 也含这个短语，但它不列行号，不构成"读半张名单"的风险
        protect = [l for l in text.split("\n")
                   if "不得当缺陷报" in l and "：" in l]
        self.assertEqual(len(protect), 1,
                         "列行号的保护名单只能有一行（多行就会有人只读其中一行）：%s" % protect)
        self.assertEqual(ids_of(protect[0]), legal,
                         "保护名单与 classify 现算的合法集合不等：名单 %s / 现算 %s"
                         % (ids_of(protect[0]), legal))
        self.assertIn("共 %d 处" % len(legal), protect[0],
                      "名单里印的处数与行号个数不符：%s" % protect[0])
        # 子集拆分只当定位用：并集必须等于全集，且不许互相重叠（否则数两遍）
        subs = [l for l in text.split("\n") if l.startswith("- ├ 子集")]
        self.assertEqual(len(subs), 2, "子集行数变了：%s" % subs)
        parts = [ids_of(l) for l in subs]
        self.assertEqual(sorted(sum(parts, [])), legal,
                         "子集并集 != 全集（%s vs %s）" % (sorted(sum(parts, [])), legal))
        self.assertFalse(set(parts[0]) & set(parts[1]), "两个子集有重叠，合起来会数两遍")
        need_line = [l for l in text.split("\n") if l.startswith("- 待作者定夺")]
        self.assertEqual(len(need_line), 1, "缺待夺那行汇总")
        self.assertEqual(ids_of(need_line[0]), need, "待夺汇总与现算不符")
        # 盘上的产物也得有这一行（不是只在 render 里）
        disk = (ROOT / PS.OUT_REL).read_text(encoding="utf-8")
        self.assertIn(protect[0], disk, "盘上清单缺这行 —— 跑 --paper-report --write")

    def test_verify_mode_goes_red_when_the_report_is_stale(self):
        """判别式：改清单里一个数，`--verify` 必须不通过（否则清单就是手抄件）。"""
        out = ROOT / PS.OUT_REL
        original = out.read_bytes()
        try:
            stale = original.replace("撤除动作从未到达论文".encode("utf-8"),
                                     "撤除动作已经到达论文".encode("utf-8"), 1)
            self.assertNotEqual(stale, original, "扰动没改到任何字节，这条是空转")
            out.write_bytes(stale)
            rc = subprocess.run([sys.executable, str(ROOT / "console" / "_citations.py"),
                                 "--paper-report", "--verify"], cwd=str(ROOT),
                                capture_output=True)
            self.assertEqual(rc.returncode, 1, "清单被改了字却仍判通过")
        finally:
            out.write_bytes(original)
        rc = subprocess.run([sys.executable, str(ROOT / "console" / "_citations.py"),
                             "--paper-report", "--verify"], cwd=str(ROOT), capture_output=True)
        self.assertEqual(rc.returncode, 0, "还原后仍不通过：还原失败")


if __name__ == "__main__":
    unittest.main()
