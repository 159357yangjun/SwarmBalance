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
