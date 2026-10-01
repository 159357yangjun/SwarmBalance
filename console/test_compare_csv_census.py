# -*- coding: utf-8 -*-
"""`results/compare` 形状普查的判据：分桶恒等式、范围下限、产物新鲜度、短码都发得出来。

为什么每条都要自己造正例（而不是只跑真仓）：真仓现在的答案是 `no_bom=0 / seed_cols=0 /
declared_only=1`，只跑真仓等于只测了"这些桶是空的"那一面 —— 而**读数为 0 的桶有两种**：
现场没有，和量具到不了。所以临时目录里造一份"没有 BOM 的、带 seed 列的、列宽不同的、
被清单声明却不存在的"，逼每个桶各出一次非零读数；再拿真仓比一次外部独立重数。

夹具必须提供**真的入口源文件**（`console/server.py` 与 `results/plot_compare_metrics.py`
各含一份名单），而不是给 `main()` 加一个"测试专用参数"：后门会让夹具绕过解析逻辑，
而解析逻辑正是最容易坏的那部分（入口改名、括号配平、注释里的撇号）。
"""
from __future__ import annotations

import csv
import glob
import hashlib
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from console import _csvcensus as CC        # noqa: E402

LEDGER = "docs/数据来源与可追溯性登记表.md"


def write_csv(dirpath, name, header, rows, bom=True):
    """在临时目录里写一份受控 CSV：BOM、列宽、seed 列都由调用方决定。"""
    p = os.path.join(dirpath, name)
    body = u",".join(header) + u"\n"
    for r in rows:
        body += u",".join(str(x) for x in r) + u"\n"
    with open(p, "wb") as f:
        if bom:
            f.write(b"\xef\xbb\xbf")
        f.write(body.encode("utf-8"))
    return p


def _entry_file(dirpath, rel, var, names, comment=None):
    os.makedirs(os.path.dirname(dirpath + "/" + rel), exist_ok=True)
    body = "%s = [\n" % var
    for k, n in enumerate(names):
        if k == 1 and comment:
            body += "    # %s\n" % comment       # 注释里带撇号，测的是配平器的注释分支
        body += '    "%s",\n' % n
    body += "]\n"
    with io.open(os.path.join(dirpath, rel), "w", encoding="utf-8") as f:
        f.write(body)


def make_compare(with_sources=True, floor_case=False):
    """一个临时 results/compare：故意做出四种形状 + 两份入口清单。

    - `a_no_bom.csv`：**没有 BOM**（真仓现在一份都没有，这一桶靠它出非零读数）
    - `b_seed.csv`：带 `Seed` 列（真仓也是零，同样必须能数到）
    - 列宽 2 / 3 / 13 / 25 并存
    - `undeclared_present.csv`：磁盘有、两份清单都没声明
    - 清单里声明 `gone.csv`：声明了、磁盘没有
    - server 那份清单第 2 项前插一行带 `don't` 的注释 —— 解析器的注释分支只有这里有证人
    """
    d = tempfile.mkdtemp(prefix="csvcensus-")
    sub = os.path.join(d, "results", "compare")
    os.makedirs(sub)
    if floor_case:
        write_csv(sub, "only1.csv", [u"算法", u"完成率"], [[u"greedy", 1]])
        write_csv(sub, "only2.csv", [u"算法", u"完成率"], [[u"pso", 1]])
        if with_sources:
            # 两个入口都得给：`declared()` 读的是两份清单的并集，少一份就变成 PARSE 报错而不是
            # "扫到 2 份" —— 下限那条判据要红得因为份数，不能红得因为夹具偷懒。
            _entry_file(d, "console/server.py", "_CSV_FILES", ["only1.csv", "only2.csv"])
            _entry_file(d, "results/plot_compare_metrics.py", "CSV_FILES",
                        ["only1.csv", "only2.csv"])
        return d, sub
    write_csv(sub, "a_no_bom.csv", [u"算法", u"完成率"], [[u"greedy", 1]], bom=False)
    write_csv(sub, "b_seed.csv", [u"算法", u"Seed", u"完成率"],
              [[u"pso", 101, 1], [u"pso", 102, 1]], bom=True)
    write_csv(sub, "c_25.csv", [u"算法"] + [u"m%d" % i for i in range(24)],
              [[u"ga"] + [0] * 24], bom=True)
    write_csv(sub, "d_13.csv", [u"mode"] + [u"m%d" % i for i in range(12)],
              [[u"h"] + [0] * 12] * 3, bom=True)
    write_csv(sub, "undeclared_present.csv", [u"算法", u"完成率"], [[u"ortools", 1]],
              bom=True)
    write_csv(sub, "e_rows.csv", [u"算法", u"完成率"],
              [[u"greedy", 1], [u"pso", 2], [u"ga", 3], [u"ortools", 4]], bom=True)
    if with_sources:
        _entry_file(d, "console/server.py", "_CSV_FILES",
                    ["a_no_bom.csv", "b_seed.csv", "c_25.csv", "e_rows.csv"],
                    comment=u"这一行故意带个 don't 的撇号")
        _entry_file(d, "results/plot_compare_metrics.py", "CSV_FILES",
                    ["a_no_bom.csv", "d_13.csv", "c_25.csv", "gone.csv"])
    return d, sub


def _run_main(argv, d):
    """在子进程里跑 `main(argv, root=临时目录)` —— 退码与 stdout 都是被测对象的产出。"""
    pr = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, 'console');"
         "import _csvcensus as C; import pathlib;"
         "sys.exit(C.main(%r, pathlib.Path(r'%s')))" % (argv, d)],
        cwd=str(ROOT), capture_output=True)
    return pr.returncode, pr.stdout.decode("utf-8", "replace")


class CsvCensusTests(unittest.TestCase):

    def test_live_artifact_matches_an_independent_recount(self):
        """产物里逐文件那几个数，必须能用另一条代码路径独立重数一遍。

        只比"产物 == 生成器现在算的"不够 —— 那验的是自洽，不是正确；生成器把列数算错，
        两边一起错。所以这里测试自己用 `glob` + `csv.reader` 再数一次，与表里的行对。
        """
        text, counts = CC.report(ROOT)
        rows = {}
        for line in text.split("\n"):
            m = re.match(r"^\| `(.+)` \| (\d+) \| (\d+) \| (是|\*\*否\*\*) \|", line)
            if m:
                rows[m.group(1)] = (int(m.group(2)), int(m.group(3)), m.group(4) == "是")
        self.assertEqual(len(rows), counts["files"],
                         "表里 %d 行 / 计数 %d 份，对不上" % (len(rows), counts["files"]))
        self.assertGreaterEqual(len(rows), CC.FLOOR, "扫描范围塌了")
        mismatch = []
        for p in sorted(glob.glob(str(ROOT / "results" / "compare" / "*.csv"))):
            name = os.path.basename(p)
            raw = open(p, "rb").read()
            f = io.open(p, encoding="utf-8-sig", newline="")
            rd = csv.reader(f)
            try:
                hdr = next(rd, [])
                n = sum(1 for row in rd if row and any(c.strip() for c in row))
            finally:
                f.close()
            want = rows.get(name)
            got = (len(hdr), n, raw[:3] == b"\xef\xbb\xbf")
            if want != got:
                mismatch.append("%s 表=%r 独立重数=%r" % (name, want, got))
        self.assertEqual(mismatch, [], "产物与独立重数不一致：\n  " + "\n  ".join(mismatch))
        print("[CSV_CENSUS_XRECOUNT] files=%d widths=%s bom=%d/%d 独立重数全部相符"
              % (counts["files"], ",".join(str(w) for w in counts["widths"]),
                 counts["bom_yes"], counts["files"]))

    def test_output_is_deterministic_across_hash_seeds(self):
        """同一份盘、四个 PYTHONHASHSEED，产物文本必须一字不差。

        列宽/分桶都用 set 收，set 序受 hash 种子影响 —— 这是 `_rewrites.py` 第一版
        刚 --write 完就 --verify 红的同一个坑，这里提前钉住而不是等它再发生一次。
        """
        hashes = set()
        for seed in ("0", "1", "7", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            pr = subprocess.run([sys.executable, "console/_citations.py", "--csv-census"],
                                cwd=str(ROOT), capture_output=True, env=env)
            self.assertEqual(pr.returncode, 0, pr.stderr.decode("utf-8", "replace")[:300])
            hashes.add(hashlib.sha256(pr.stdout).hexdigest()[:16])
        self.assertEqual(len(hashes), 1, "同一份盘量出 %d 种文本：%s" % (len(hashes), hashes))

    def test_fixture_buckets_are_all_nonzero_and_identity_holds(self):
        d, _sub = make_compare()
        text, counts = CC.report(Path(d))
        self.assertEqual(counts["files"], 6, counts)
        self.assertEqual(counts["no_bom"], ["a_no_bom.csv"],
                         "没有 BOM 那一桶必须数到夹具（真仓是 0，不代表量具到不了）")
        self.assertEqual(counts["with_seed"], ["b_seed.csv"], "seed 列那一桶要能数到")
        self.assertEqual(counts["disk_only"], ["undeclared_present.csv"])
        self.assertEqual(counts["declared_only"], ["gone.csv"])
        self.assertEqual(len(counts["both"]) + len(counts["disk_only"]), counts["files"])
        self.assertEqual(len(counts["both"]) + len(counts["declared_only"]),
                         counts["declared_total"])
        self.assertEqual(counts["problems"], 0, "夹具不该触发硬失败：%s" % counts)
        self.assertIn("恒等式 | 成立", text)
        self.assertIn("`gone.csv`", text)
        # 待夺桶只进报告行，不进退出码（它是"他定"，不是"缺陷"）
        rc, out = _run_main(["--write"], d)
        self.assertEqual(rc, 0, out)
        rc, out = _run_main(["--verify"], d)
        self.assertEqual(rc, 0, "待夺事项把退出码变红了 —— 那条口径被自己推翻：" + out)
        self.assertIn("[CSV_CENSUS] files=6", out)

    def test_comment_with_apostrophe_inside_the_list_still_parses(self):
        """夹具那份清单里带一行 `don't` 注释：解析器若把撇号当开引号，名单就会塌。

        这条不是补装饰 —— 真仓两份清单目前都没有这种注释（已核），所以**只有这里有证人**；
        没有它，注释分支就是一段没人跑过的代码。
        """
        d, _sub = make_compare()
        dec = CC.declared(Path(d))
        self.assertEqual(dec["console/server.py:_CSV_FILES"],
                         ["a_no_bom.csv", "b_seed.csv", "c_25.csv", "e_rows.csv"],
                         "带撇号的注释把名单解析塌了")

    def test_range_floor_bites_as_a_code(self):
        """CSV 少到低于下限时必须整轮红，而不是"扫到 2 份，没问题"。

        而且红在比产物**之前**：范围塌了还去比产物，报出来的是"表被手改过"，
        那是把量具坏了说成别人的错。
        """
        d, _sub = make_compare(floor_case=True)
        _text, counts = CC.report(Path(d))
        self.assertLess(counts["files"], CC.FLOOR)
        self.assertTrue(counts["blind"])
        rc, out = _run_main(["--verify"], d)
        self.assertEqual(rc, 1, out)
        self.assertIn("[FAIL][CSV_CENSUS_RANGE]", out)
        self.assertNotIn("CSV_CENSUS_STALE", out, "瞎了却先报\"表被改过\"—— 顺序错了")
        rc, out = _run_main(["--write"], d)
        self.assertEqual(rc, 1, "扫描瞎了还允许 --write 返回 0")

    def test_headerless_csv_bites_as_problem_code(self):
        """0 字节 / 截断的 CSV：记一条问题并红在 `[CSV_CENSUS_PROBLEM]`，不抛异常。

        这条夹具存在的理由是给 PROBLEM 一个证人 —— 短码表里列着而没人驱动过的码，
        和没写一样。
        """
        d, sub = make_compare()
        open(os.path.join(sub, "truncated.csv"), "wb").close()     # 0 字节
        _text, counts = CC.report(Path(d))
        self.assertEqual(counts["unreadable"], ["truncated.csv"], counts)
        self.assertGreaterEqual(counts["problems"], 1)
        self.assertFalse(counts["blind"], "这份夹具该红在缺陷，不该红在范围")
        rc, out = _run_main(["--write"], d)
        self.assertEqual(rc, 0, out)
        rc, out = _run_main(["--verify"], d)
        self.assertEqual(rc, 1, out)
        self.assertIn("[FAIL][CSV_CENSUS_PROBLEM]", out)

    def test_missing_and_stale_artifact_are_red(self):
        d, _sub = make_compare()
        _run_main(["--write"], d)
        out = Path(d) / CC.OUT_REL
        self.assertTrue(out.is_file(), "--write 之后产物不在盘上")
        original = out.read_bytes()
        out.unlink()
        rc, o = _run_main(["--verify"], d)
        self.assertEqual(rc, 1, o)
        self.assertIn("[FAIL][CSV_CENSUS_MISSING]", o)
        out.write_bytes(original.replace("## 逐文件".encode("utf-8"),
                                         "## 逐 文 件".encode("utf-8")))
        rc, o = _run_main(["--verify"], d)
        self.assertEqual(rc, 1, o)
        self.assertIn("[FAIL][CSV_CENSUS_STALE]", o)
        out.write_bytes(original)
        self.assertEqual(out.read_bytes(), original, "还原没做到逐字节相同")

    def test_unparseable_declared_list_is_a_code_not_an_empty_list(self):
        """入口改名 ⇒ `[FAIL][CSV_CENSUS_PARSE]` + 退出码 1；不许当成"声明了 0 项"继续算。"""
        d, _sub = make_compare(with_sources=False)
        rc, out = _run_main(["--verify"], d)
        self.assertEqual(rc, 1, out)
        self.assertIn("[FAIL][CSV_CENSUS_PARSE]", out)
        self.assertNotIn("files=0", out, "解析失败还往下算了个空名单 —— 那会把每份都判成未声明")

    def test_documented_codes_are_all_emitted(self):
        """`_csvcensus.py` docstring 里那张短码表，每一条都得有一次"真被发出来"的驱动。

        同一条纪律在 `test_gate_ascii_diagnostics.py` 里管着引用门禁与论文侧的码；
        这两个新模块（`_rewrites`、`_csvcensus`）不在它的取样面里，所以自己核自己一遍。
        四个面各自唯一对应一条码，缺一面就说明那条码是暗号。
        """
        doc = set(re.findall(r"\[(CSV_CENSUS_[A-Z_]+)\]",
                             io.open(str(ROOT / "console" / "_csvcensus.py"),
                                     encoding="utf-8").read().split('"""')[1]))
        seen = set()
        drivers = []
        d1 = make_compare()[0]                                  # → STALE
        _run_main(["--write"], d1)
        p1 = Path(d1) / CC.OUT_REL
        p1.write_bytes(p1.read_bytes() + "手改一个字节\n".encode("utf-8"))
        drivers = [[["--verify"], d1]]
        d2 = make_compare()[0]                                  # → MISSING
        drivers.append([["--verify"], d2])
        drivers.append([["--verify"], make_compare(floor_case=True)[0]])   # → RANGE
        dp, subp = make_compare()                               # → PROBLEM（0 字节那份）
        open(os.path.join(subp, "truncated.csv"), "wb").close()
        _run_main(["--write"], dp)
        drivers.append([["--verify"], dp])
        drivers.append([["--verify"], make_compare(with_sources=False)[0]])   # → PARSE
        for argv, root in drivers:
            rc, out = _run_main(argv, root)
            self.assertEqual(rc, 1, "%s 本该红：%s" % (argv, out))
            seen |= set(re.findall(r"\[(CSV_CENSUS_[A-Z_]+)\]", out))
        self.assertTrue(doc, "短码表空了 —— docstring 被改过？")
        self.assertEqual(doc - seen, set(),
                         "这些短码写在表里但从没发出来（等于暗号）：%s" % sorted(doc - seen))
        self.assertTrue(seen <= doc, "发出来的码不在表里：%s" % sorted(seen - doc))
        print("[CSV_CENSUS_CODES] 表里 %d 条全部被驱动过：%s" % (len(doc), sorted(doc)))

    def test_column_gap_matches_external_recount(self):
        """宽表比窄表多出的那批列，必须在测试里用另一条路径重算一遍再对。

        这一节讲的是"窄表里根本没有这些列"（R6 的成因），所以它的正确性不取决于
        生成器自己怎么说 —— 两边一起错就等于没核。
        """
        text, counts = CC.report(ROOT)
        self.assertGreaterEqual(counts["gap_schemas"], 2,
                                "真仓里只剩一种表头：这一节的正例消失了，判据要改法而不是删掉")
        rows = {r["name"]: r for r in CC.scan(ROOT) if r["has_algo"]}
        pairs = re.findall(r"^- 宽：(.+?)（(\d+) 列）vs 窄：(.+?) ⇒ \*\*宽表多 (\d+) 列\*\*：(.+?)；",
                           text, re.M)
        self.assertTrue(pairs, "产物里没有一对宽/窄，可 gap_schemas>=2 ⇒ 渲染漏了")
        bad = []
        for wide_grp, wide_cols, narrow_grp, n_s, listed in pairs:
            wide = re.findall(r"`([^`]+)`", wide_grp)[0]      # 一组里可能有好几份
            narrow = re.findall(r"`([^`]+)`", narrow_grp)[0]
            want = sorted(set(c.strip() for c in rows[wide]["hdr"])
                          - set(c.strip() for c in rows[narrow]["hdr"]))
            got = re.findall(r"`([^`]+)`", listed)
            if want != got or len(want) != int(n_s):
                bad.append("%s vs %s：产物=%r 独立重算=%r" % (wide, narrow, got, want))
        self.assertEqual(bad, [], "列差集算错：\n  " + "\n  ".join(bad))
        print("[CSV_CENSUS_GAP] schemas=%d pairs=%d 第一对差 %d 列，独立重算相符"
              % (counts["gap_schemas"], len(pairs), int(pairs[0][3])))

    def test_gap_shrinks_when_narrow_table_gains_a_column(self):
        """窄表补上一列 ⇒ 差集必须跟着缩一格。

        这条是那一节的牙：只差集"会动"，才说明它是算出来的，不是把某天的结果印成常量。
        """
        def gap_of(narrow_hdr):
            d = tempfile.mkdtemp(prefix="csvcensus-gap-")
            sub = os.path.join(d, "results", "compare")
            os.makedirs(sub)
            write_csv(sub, "wide.csv", [u"算法", "A", "B", "C"], [[u"ga", 1, 2, 3]])
            write_csv(sub, "narrow.csv", narrow_hdr, [[u"greedy"] + [1] * (len(narrow_hdr) - 1)])
            return CC.column_gap(CC.scan(Path(d)))
        g2 = gap_of([u"算法", "A"])
        self.assertEqual(g2["distinct_schemas"], 2)
        self.assertEqual(g2["pairs"][0]["only_in_wide"], ["B", "C"], g2["pairs"])
        g3 = gap_of([u"算法", "A", "B"])
        self.assertEqual(g3["pairs"][0]["only_in_wide"], ["C"], "补了 B 却没让差集缩 —— 这节是常量")
        self.assertEqual(g3["pairs"][0]["only_in_narrow"], [])
        g1 = gap_of([u"算法", "A", "B", "C"])          # 两边同表头
        self.assertEqual(g1["distinct_schemas"], 1)
        self.assertEqual(g1["pairs"], [])
        self.assertIn("没有差异可报", g1["empty_reason"], "空表要说出为什么空")

    def test_ledger_r5_r6_point_at_their_owners(self):
        """R5 归 manifest、R6 归普查产物：两行都不许再自己扛数。"""
        lines = io.open(ROOT / LEDGER, encoding="utf-8").read().split("\n")
        want = {"| R5 ": "compare_gate.py", "| R6 ": "compareCSV普查.md"}
        for prefix, needle in want.items():
            row = [l for l in lines if l.startswith(prefix)]
            self.assertEqual(len(row), 1, "%s 应恰好一行，现在 %d 行" % (prefix.strip(), len(row)))
            self.assertIn(needle, row[0], "%s 没指向它的唯一真源 %s" % (prefix.strip(), needle))
            for pat in (r"\d+\s*列", r"\d+\s*步", r"\d+\s*次重复"):
                self.assertIsNone(re.search(pat, row[0]),
                                  "%s 里还有手抄数（%s）：%s" % (prefix.strip(), pat, row[0][:80]))

    def test_ledger_r4_row_delegates_its_numbers(self):
        """登记表 R4 那一行必须**指路**而不是**抄数**：出现列宽/份数的字面量就算回归。

        这条是给"改完生成器又把手抄数粘回文档"兜底的 —— 上一轮 R4 一次漂了四条，
        而漂了的注释比空白更危险。
        """
        lines = io.open(ROOT / LEDGER, encoding="utf-8").read().split("\n")
        r4 = [l for l in lines if l.startswith("| R4 ")]
        self.assertEqual(len(r4), 1, "登记表里 R4 行应当恰好一条，现在 %d 条" % len(r4))
        self.assertIn("compareCSV普查.md", r4[0],
                      "R4 还在自己扛数：没指向 docs/compareCSV普查.md")
        for pat, why in ((r"\d+\s*列", "手抄列宽"),
                         (r"[四七八九十]\s*份", "手抄份数"),
                         (r"efbbbf|e7ae97", "手抄首字节")):
            self.assertIsNone(re.search(pat, r4[0]),
                              "R4 里还留着%s（%s）：数归产物管，文档只指路" % (why, pat))


if __name__ == "__main__":
    unittest.main()
