# -*- coding: utf-8 -*-
"""results/compare/plots/ 这批归档还带着 6 个已撤除算法 —— 本用例把"作废"钉成可执行判据。

起因（本轮实测，不是推测）：
- 6b8c4c8 把 MARL 侧与 iql/iql_u/vdn/vdn_u/qmix/qmix_u 六行从数据源与对比页撤了，
  但 `git log -1 -- results/compare/plots` 停在 **fcc7c5f（2026-09-11）**，
  而 `git merge-base --is-ancestor fcc7c5f 6b8c4c8` 成立 —— 撤除从未到达这个目录。
- 于是这三份派生表仍然是 10 行算法（含那 6 行），12 张 PNG 同批；
  登记表 R2 已把这几行的数字逐格证伪。
- 同目录还并存两份不同口径的 GA：归档表里 ga = 2000 步 / 60 任务，
  而入库的 `backend_ga_metrics.csv` 是 400/600 步、22/30 任务。

为什么要测试而不是只写一张纸：上一轮刚被教育过 —— **"人写没人验的声明就是会过期的声明"**。
所以这里做**双向**指纹：归档还是那 10 行时测试绿；哪天有人清掉 MARL 行重生了这个目录，
测试会红并要求撤销作废通知。单向断言只会把"作废"永久钉在已经修好的产物上。
"""
from __future__ import annotations

import csv
import io
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLOTS = ROOT / "results" / "compare" / "plots"
NOTICE = PLOTS / "README.md"

# 名单只有一份：`console/_rowsets.py`。本用例原先在这里抄了第二份（CORE / WITHDRAWN /
# VOID_SET，连注释都是同一句），于是"改了唯一真源、这条门还按旧名单绿着"是可能的。
import sys as _sys
if str(ROOT / "console") not in _sys.path:
    _sys.path.insert(0, str(ROOT / "console"))
import _rowsets as RS                                     # noqa: E402

CORE, WITHDRAWN, VOID_SET = RS.CORE, RS.WITHDRAWN, RS.ALL_NAMED


def _tables():
    """归档目录里的派生表 —— 与 `results/row_set_delta.py:_tables()` 同一条口径（不写死文件名）。"""
    return sorted(p for p in PLOTS.glob("*.csv"))


def _pngs():
    return sorted(PLOTS.glob("*.png"))


def _algorithms(path):
    """读第一列（算法名）。三张表都以 `Algorithm` 起头，实测过。"""
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows or not rows[0]:
        raise AssertionError("%s 是空表，判据无法成立" % path.name)
    return {r[0].strip() for r in rows[1:] if r and r[0].strip()}


def _steps_of_row(path, algorithm):
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        rd = csv.DictReader(fh)
        cols = rd.fieldnames or []
        step_col = next((c for c in cols if "步数" in c or c.strip().lower() == "total steps"), None)
        if step_col is None:
            return None
        for row in rd:
            if (row.get(cols[0]) or "").strip() == algorithm:
                return row.get(step_col)
    return None


def _last_commit_touching(rel_path):
    pr = subprocess.run(["git", "log", "-1", "--format=%H", "--", rel_path],
                        cwd=str(ROOT), capture_output=True, text=True)
    return pr.stdout.strip()


def _is_ancestor(sha_a, sha_b):
    pr = subprocess.run(["git", "merge-base", "--is-ancestor", sha_a, sha_b],
                        cwd=str(ROOT), capture_output=True)
    return pr.returncode == 0


class PlotsArchiveVoidTests(unittest.TestCase):

    def test_archived_tables_still_carry_the_withdrawn_rows(self):
        """归档仍是那 10 行 -> 作废通知成立；不再是 -> 红，逼着撤销通知（双向）。"""
        tables = _tables()
        self.assertGreaterEqual(len(tables), 1,
                                "归档目录里一份派生表都没有 —— 扫描瞎了，本用例不许报绿")
        for p in tables:
            got = _algorithms(p)
            if got != VOID_SET:
                self.fail("%s 的算法集合已经是 %s，不再含 6 个已撤除算法 —— "
                          "results/compare/plots/README.md 的作废声明随之过期，"
                          "请把那份通知撤掉或改写成新状态，别留下会误导人的旧结论"
                          % (p.name, sorted(got)))
        self.assertTrue((PLOTS / "bar_weighted_overall_score.png").is_file(),
                        "归档图不在，本用例的判据会空转")
        print("[PLOT_VOID_CENSUS] csv=%d png=%d withdrawn=%d all_named=%d"
              " —— 件数只在运行行上印，纸面不许再抄它"
              % (len(tables), len(_pngs()), len(WITHDRAWN), len(VOID_SET)))

    def test_notice_names_every_withdrawn_algorithm(self):
        """纸面声明必须逐个点名 —— 只写"含过期数据"等于没说。"""
        text = NOTICE.read_text(encoding="utf-8")
        self.assertIn("作废", text, "作废通知里没写「作废」二字")
        for alg in sorted(WITHDRAWN):
            self.assertIn(alg, text, "%s 没被点名" % alg)
        self.assertIn("6b8c4c8", text, "要说清是哪次撤除没到达这里")

    def test_rowset_marker_is_required_and_bidirectional(self):
        """作废产物被引用时必须声明行集合；声明 all10 的还必须真是那张 10 行表。

        为什么双向：只查"有没有写标注"，那标注可以永远挂着 —— 表哪天重生成了
        只剩核心 4 行，`行集=all10` 就成了新的假话。所以两个方向都要能红：
        缺标注红，标注与表内容不符也红。
        这里在 results/adhoc/（已 gitignore）下造一个临时作废目录，跑完删，不碰仓库产物。
        """
        import shutil
        import sys as _sys
        _sys.path.insert(0, str(ROOT / "console"))
        import _citations as CJ
        import _rowsets as RS

        sandbox = ROOT / "results" / "adhoc" / "_rowset_probe"
        shutil.rmtree(sandbox, ignore_errors=True)
        try:
            sandbox.mkdir(parents=True)
            (sandbox / "README.md").write_text("本目录已作废（探针）", encoding="utf-8")
            dirty = sandbox / "ten.csv"
            cols = "Algorithm,Score\n"
            dirty.write_text(cols + "\n".join("%s,%d" % (a, n)
                                              for n, a in enumerate(sorted(RS.ALL_NAMED))) + "\n",
                             encoding="utf-8")
            clean = sandbox / "four.csv"
            clean.write_text(cols + "\n".join("%s,%d" % (a, n)
                                              for n, a in enumerate(sorted(RS.CORE))) + "\n",
                             encoding="utf-8")
            rel_d, rel_c = dirty.relative_to(ROOT).as_posix(), clean.relative_to(ROOT).as_posix()
            vdirs = [sandbox]

            # ① 缺标注 -> 红
            _c, _m, bad = CJ.rowset_violations(["引用 `%s` 的均值" % rel_d], "探针", vdirs=vdirs)
            self.assertEqual(len(bad), 1, "裸引用作废表却没报警：%s" % bad)
            self.assertIn("行集=", bad[0], "报警要给出该写什么标注")

            # ② 标注齐全且与表内容相符 -> 绿
            _c, m, bad = CJ.rowset_violations(["引用 `%s` 行集=all10 的均值" % rel_d],
                                              "探针", vdirs=vdirs)
            self.assertEqual(bad, [], "已声明且与 10 行相符却报警：%s" % bad)
            self.assertEqual(m, 1, "标注计数没跟上，说明作用域绑定错了")

            # ③ 声明 all10 但表只有核心 4 行 -> 红（标注过期）
            _c, _m, bad = CJ.rowset_violations(["引用 `%s` 行集=all10 的均值" % rel_c],
                                               "探针", vdirs=vdirs)
            self.assertEqual(len(bad), 1, "过期标注没报警：%s" % bad)
            # 打在短码上而不是中文措辞上（文案随时能改，短码才是契约）
            self.assertTrue(bad[0].startswith("[ROWSET_STALE]"),
                            "标注过期那条的短码不对：%s" % bad[0][:90])

            # ④ 声明 core4 是允许的子集读法，不该被当假话
            _c, _m, bad = CJ.rowset_violations(["引用 `%s` 行集=core4 的均值" % rel_d],
                                               "探针", vdirs=vdirs)
            self.assertEqual(bad, [], "core4 声明被误判：%s" % bad)

            # ⑤ 真文档必须已经全部声明过（否则这条门等于没关门）
            real = CJ.rowset_violations(
                (ROOT / "docs" / "数据来源与可追溯性登记表.md").read_text(
                    encoding="utf-8").splitlines(), "登记簿")
            self.assertEqual(real[2], [], "登记簿里有裸引用作废产物：%s" % real[2])
            self.assertGreaterEqual(real[0], 3, "登记簿里的作废产物引用少于 3 处，判据覆盖面变了")
        finally:
            shutil.rmtree(sandbox, ignore_errors=True)

    def test_rowset_delta_generator_is_pinned_and_goes_red(self):
        """差异表由代码生成，手改一个数字就要红（数字不许手抄进文档）。"""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "row_set_delta_probe", ROOT / "results" / "row_set_delta.py")
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        text = gen.render()
        self.assertEqual(gen.OUT.read_text(encoding="utf-8"), text,
                         "ROW_SETS.md 与代码重算不一致 —— 跑 --write 而不是手改")
        # 非空转：改动一个读数后，核对必须判不一致
        perturbed = text.replace("0.833768", "0.833769", 1)
        self.assertNotEqual(perturbed, text, "扰动没改动任何字节，下面的核对是空转")
        original = gen.OUT.read_bytes()
        try:
            gen.OUT.write_bytes(perturbed.encode("utf-8"))
            self.assertEqual(gen.main(["--verify"]), 1, "盘上产物被改了却不红")
        finally:
            gen.OUT.write_bytes(original)
        self.assertEqual(gen.OUT.read_bytes(), original, "还原失败会留下假差异表")
        self.assertEqual(gen.main(["--verify"]), 0)
        # 差异确实存在（不是"两列都是 0"的摆设）：核心4 与 含撤除10 至少有一列读数不同
        differs = [r for r in gen.compute() if r[6]]
        self.assertGreaterEqual(len(differs), 10,
                                "两种行集合只有 %d 列不同，与实测的 22 列对不上" % len(differs))

    def test_notice_separates_measured_from_inferred(self):
        """PNG 的像素内容没人核过 —— 通知必须自己承认这一点。

        我能证的是"这批图与含 6 行的表同批同脚本"，证不了"图里那几根柱就是 MARL"。
        把推断写成实测是这一路最常见的失败，所以这里把"未实测"钉成断言：
        哪天有人真去逐张比对并补了证据，该改的是通知，而不是让它含糊过去。
        """
        text = NOTICE.read_text(encoding="utf-8")
        self.assertIn("未实测", text, "通知没区分已实测/未实测")
        self.assertIn("像素", text, "要说清未核的是像素内容")

    def test_purge_never_reached_the_artifacts(self):
        """"撤除没到达这里"逐件证，且不拿"整个目录的最后一次改动"当判据。

        第一版写的是 `git log -1 -- results/compare/plots`，我把它自己的作废通知提交进
        那个目录之后，这条立刻红 —— 因为"目录最后一次改动"变成了那次新增通知的提交。
        一个会被"记录缺陷的动作"本身推翻的判据是坏判据；改成对目录里**每一件**产物逐件问
        最后一次入库改动，并各自要求它是 6b8c4c8 的祖先。
        件数不在这里当常量（原先写死 15，而 15 同时抄在通知与登记表里 —— 三处任一处漂了就互相打）：
        两个桶都要求非空（空桶 = 扫描到不了，不是"没问题"），真实数字印在运行行上。
        """
        artifacts = _tables() + _pngs()
        self.assertTrue(_tables(), "归档目录里没有派生表：这一路扫描到不了，不许报绿")
        self.assertTrue(_pngs(), "归档目录里没有 PNG：同上")
        print("[PLOT_VOID_ARTIFACTS] 逐件问祖先：%d 件（csv=%d png=%d）"
              % (len(artifacts), len(_tables()), len(_pngs())))
        stale = {}
        for p in artifacts:
            rel = p.relative_to(ROOT).as_posix()
            last = _last_commit_touching(rel)
            self.assertRegex(last, r"^[0-9a-f]{40}$", "%s 拿不到最后一次入库提交" % rel)
            if not _is_ancestor(last, "6b8c4c8"):
                stale[rel] = last[:7]
        self.assertEqual(stale, {},
                         "这些产物在撤除 MARL（6b8c4c8）之后又被改过，作废通知需要重新评估：%s"
                         % stale)

    def test_two_different_ga_calibers_coexist(self):
        """同目录并存两份口径不同的 GA —— 这是"图里那根 GA 柱说不清来源"的直接证据。"""
        archived = _steps_of_row(PLOTS / "combined_compare_metrics.csv", "ga")
        current = _steps_of_row(ROOT / "results" / "compare" / "backend_ga_metrics.csv", "ga")
        self.assertIsNotNone(archived, "归档表里读不到 ga 的步数列，判据空转")
        self.assertIsNotNone(current, "入库 CSV 里读不到 ga 的步数列，判据空转")
        self.assertNotEqual(str(archived), str(current),
                            "归档表与入库 CSV 的 GA 步数现在一致了（都是 %s）—— "
                            "本用例描述的那份 README 说法要跟着改" % archived)
        print("[PLOT_VOID_GA_CALIBER] archived_ga_steps=%s current_ga_steps=%s —— "
              "通知里不再抄这两个数" % (archived, current))

    def test_detector_is_not_vacuous(self):
        """判别式：把 MARL 六行从同一份表里去掉，判据必须认不出它是"作废那批"。"""
        real = _algorithms(PLOTS / "combined_compare_metrics.csv")
        self.assertEqual(real, VOID_SET, "真表本身就不含 6 个已撤除算法，后面没法测")
        cleaned = {a for a in real if a not in WITHDRAWN}
        self.assertNotEqual(cleaned, VOID_SET)
        # 判据就是"集合相等"，所以清过的表必须被判为不同 —— 这就是双向那一路
        self.assertEqual(cleaned, CORE, "去掉六行后剩下的应当正好是四个核心算法")


    def test_no_second_copy_of_the_counts_or_the_list(self):
        """R8 那对里"改哪边都要动另一边"的机制版：纸面不许再抄件数、读数，也不许抄第二份名单。

        这条是本轮真正要的牙 —— 上一版三处（登记表行 / 作废通知 / 本用例）各自抄了
        `15 / 12 / 10 / 0.833768 / 2000 步`，任一处漂了另外两处都不知道。
        现在数只在运行行与生成的 `ROW_SETS.md` 上，名单只在 `console/_rowsets.py` 里。
        """
        docs = {"作废通知": NOTICE.read_text(encoding="utf-8"),
                "登记表 R8": next(l for l in (ROOT / "docs" / "数据来源与可追溯性登记表.md").read_text(
                                      encoding="utf-8").split("\n")
                                  if l.startswith("| R8 "))}
        banned = [(r"\d+\s*件", "产物件数"), (r"\d+\s*张", "图张数"),
                  (r"\d+\s*个(?:算法|已撤除)", "算法个数"), (r"0\.\d{6}", "ROW_SETS 的读数"),
                  (r"\d+\s*步\s*/\s*\d+\s*任务", "GA 口径读数"),
                  (r"episode_max_steps\s*=\s*\d+", "manifest 里的声明值")]
        bad = []
        for label, text in docs.items():
            for pat, what in banned:
                m = re.search(pat, text)
                if m:
                    bad.append("%s 仍抄着%s：`%s`" % (label, what, m.group(0)))
        self.assertEqual(bad, [], "手抄数又回到纸面上了：\n  " + "\n  ".join(bad))
        # 用例自己也不许留第二份名单（本轮之前它就在文件头部抄了一份）
        src = Path(__file__).read_text(encoding="utf-8")
        body = src.split("import _rowsets as RS", 1)[-1]
        self.assertIsNone(re.search(r"[{（(]\s*[\"']iql_u[\"']", body),
                          "本用例里又出现了第二份撤除名单 —— 请用 RS.WITHDRAWN")
        self.assertEqual(set(CORE | WITHDRAWN), set(RS.ALL_NAMED),
                         "本用例的集合与唯一真源不同步（改了 _rowsets 就得改这里，那正是漂移的起点）")


if __name__ == "__main__":
    unittest.main()
