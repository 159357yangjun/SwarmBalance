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
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLOTS = ROOT / "results" / "compare" / "plots"
NOTICE = PLOTS / "README.md"

TABLES = ("combined_compare_metrics.csv",
          "weighted_overall_score.csv",
          "normalized_capability_scores.csv")

CORE = {"greedy", "pso", "ga", "ortools"}
WITHDRAWN = {"iql", "iql_u", "vdn", "vdn_u", "qmix", "qmix_u"}   # 6b8c4c8 撤除的六个
VOID_SET = CORE | WITHDRAWN


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
        for name in TABLES:
            got = _algorithms(PLOTS / name)
            if got != VOID_SET:
                self.fail("%s 的算法集合已经是 %s，不再含 6 个已撤除算法 —— "
                          "results/compare/plots/README.md 的作废声明随之过期，"
                          "请把那份通知撤掉或改写成新状态，别留下会误导人的旧结论"
                          % (name, sorted(got)))
        self.assertTrue((PLOTS / "bar_weighted_overall_score.png").is_file(),
                        "归档图不在，本用例的判据会空转")

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
            self.assertIn("过期", bad[0])

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
        一个会被"记录缺陷的动作"本身推翻的判据是坏判据；改成对 15 件产物逐件问
        最后一次入库改动，并各自要求它是 6b8c4c8 的祖先。
        """
        artifacts = [PLOTS / n for n in TABLES] + sorted(PLOTS.glob("*.png"))
        self.assertEqual(len(artifacts), 15,
                         "产物应有 3 表 + 12 图 = 15 件，实得 %d 件 —— 目录内容变了，"
                         "本用例与通知都要重新核" % len(artifacts))
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

    def test_detector_is_not_vacuous(self):
        """判别式：把 MARL 六行从同一份表里去掉，判据必须认不出它是"作废那批"。"""
        real = _algorithms(PLOTS / "combined_compare_metrics.csv")
        self.assertEqual(real, VOID_SET, "真表本身就不含 6 个已撤除算法，后面没法测")
        cleaned = {a for a in real if a not in WITHDRAWN}
        self.assertNotEqual(cleaned, VOID_SET)
        # 判据就是"集合相等"，所以清过的表必须被判为不同 —— 这就是双向那一路
        self.assertEqual(cleaned, CORE, "去掉六行后剩下的应当正好是四个核心算法")


if __name__ == "__main__":
    unittest.main()
