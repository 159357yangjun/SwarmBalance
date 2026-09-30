# -*- coding: utf-8 -*-
"""results/compare 口径门禁必须真的会拒 —— 门从来没红就是假绿灯。

为什么需要这一组（全部为本机实测）：`results/compare/` 里混着三种口径 ——
400/600 步 22/30 任务的 GA 短跑、2000 步 60 任务的手工基线、3600 步 5 次重复的
one_click_latest。两个生成入口（`results/plot_compare_metrics.py` 与
`console/server.py` 的 `/api/compare`）过去都只做 `pd.concat` + `keep="last"`，
于是：

  - 图侧选出 `ga=600步/30任务` 与 `greedy/pso/ortools=2000步/60任务` 并排；
  - 25 列与 20 列混放，机队 5 列在基线侧变成 NaN；
  - 前端柱图原先写 `r[m] ?? 0`，把"没测"画成"测了且为 0"，
    在越低越好的指标上直接造出"基线空载率 0 优于 GA 的 0.4994"这种假胜利。

本文件钉四件事：
① 混口径组必须被拒（用现有 ga 与 ortools，不构造假数据）；
② 同口径组必须被放行 —— 只有①会测不出"永远红的门"；
③ 拒绝判据来自**磁盘实测**（表头指纹、总步数取值、生成任务数取值），
   把我手写的 quarantine 标签和 not_comparable_with 全删掉也必须照样拒 ——
   否则门禁真正依赖的只是我抄的一行字；
④ `README.md` 必须由 `manifest.json` 渲染而来且当前内容一致（防止手抄声明漂移）。
"""
from __future__ import annotations

import copy
import io
import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "results"
COMPARE_DIR = RESULTS_DIR / "compare"
for _p in (str(ROOT), str(RESULTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import compare_gate as G  # noqa: E402

MAN = G.load_manifest()

MIXED = list(MAN["expected_refused_group"])          # ga(400/600) + ortools(2000)
SAME = list(MAN["expected_comparable_group"])        # greedy + pso + ortools，全 2000/60/n20


class GateRefusesTests(unittest.TestCase):
    """核心那条：混口径必须拒，并且拒的理由是数据而不是标签。"""

    def test_mixed_horizon_group_is_refused(self):
        with self.assertRaises(G.GateRefused) as cm:
            G.check_group(MIXED, MAN)
        msg = cm.exception.message
        self.assertIn("拒绝", msg)
        # 理由里必须把冲突的口径值打出来，不能只说"不可比"
        self.assertIn("2000", msg, "拒绝原文里没有对比双方的步数，读者无法复核：%s" % msg)

    def test_refusal_survives_removing_my_handwritten_labels(self):
        """判别式：删掉 quarantined / not_comparable_with 这些**我手写的标签**，
        门禁必须照样拒绝。否则它真正依赖的是标签而不是盘上的数字。"""
        bare = copy.deepcopy(MAN)
        for decl in bare["files"].values():
            decl.pop("quarantined", None)
            decl.pop("not_comparable_with", None)
        with self.assertRaises(G.GateRefused) as cm:
            G.check_group(MIXED, bare)
        kinds = {c["kind"] for c in cm.exception.conflicts}
        self.assertIn("disk_mismatch", kinds,
                      "去掉标签后只剩声明级冲突 —— 说明拒绝是靠我抄的字，不是盘上实测")
        fields = {c["field"] for c in cm.exception.conflicts if c["kind"] == "disk_mismatch"}
        self.assertIn("total_steps_values", fields,
                      "总步数没被算进判据：%s" % fields)
        self.assertIn("schema", fields, "表头指纹没被算进判据：%s" % fields)

    def test_same_horizon_group_passes(self):
        """反面对照：同口径必须放行。只会红的门会被当噪声关掉。"""
        res = G.check_group(SAME, MAN)
        self.assertTrue(res["ok"])
        # 放行时仍要把"口径没被真正记录"说出来，否则 unknown 被静默当成可比
        self.assertTrue(res["warnings"],
                        "三个 ad-hoc 文件的种子集是 unknown，放行却不报警 = 假装可比")

    def test_strict_level_refuses_unrecorded_provenance(self):
        """strict 级必须真的更严，否则它是个空开关。"""
        with self.assertRaises(G.GateRefused):
            G.check_group(SAME, MAN, strict=True)

    def test_quarantined_file_cannot_be_grouped(self):
        ga = "backend_ga_metrics.csv"
        self.assertTrue(MAN["files"][ga].get("quarantined"), "前提：ga 已标隔离")
        with self.assertRaises(G.GateRefused) as cm:
            G.check_group([ga, SAME[0]], MAN)
        self.assertIn("隔离", cm.exception.message)


    def test_quarantine_still_blocks_when_signatures_match(self):
        """盘上算不出差别时标签仍要拦 —— 否则那条分支是死代码。

        这里不新增文件，只是把 ortools 临时标成隔离：它与 greedy 的实测签名完全相同
        （n20 / 2000 步 / 60 任务），所以口径判据放行，只能靠隔离声明拦。
        真实场景对应"口径没错但不该对外"的判定。
        """
        bare = copy.deepcopy(MAN)
        bare["files"]["backend_ortools_metrics.csv"]["quarantined"] = True
        pair = ["frontend_greedy_metrics.csv", "backend_ortools_metrics.csv"]
        self.assertEqual(G.disk_signature(pair[0]), G.disk_signature(pair[1]),
                         "前提破了：这两个文件的实测签名本应相同")
        with self.assertRaises(G.GateRefused) as cm:
            G.check_group(pair, bare)
        self.assertIn("隔离", cm.exception.message)
        self.assertEqual({c["kind"] for c in cm.exception.conflicts}, {"quarantined"})

    def test_data_reason_is_reported_before_label_reason(self):
        """操作者第一眼看到的必须是实测差异，而不是我抄的标签。"""
        with self.assertRaises(G.GateRefused) as cm:
            G.check_group(MIXED, MAN)
        lines = cm.exception.message.splitlines()
        first_conflict = next(i for i, l in enumerate(lines) if "[盘上实测]" in l)
        label_line = next((i for i, l in enumerate(lines) if "已被隔离" in l), None)
        self.assertIsNotNone(label_line, "隔离信息应当一并显示")
        self.assertLess(first_conflict, label_line,
                        "标签理由排在实测理由之前，运维看到的会是『因为某个布尔值被拒』"
                        "而不是因为哪个数字不一致")


class GateDiskFactsTests(unittest.TestCase):
    """声明必须与磁盘一致 —— 手抄的口径表会过期，这里把它变成机器断言。"""

    def test_manifest_matches_disk(self):
        problems = G.check_all(MAN)
        self.assertEqual(problems, [], "manifest 与磁盘不一致：%s" % problems)

    def test_every_csv_on_disk_is_declared(self):
        on_disk = {p.name for p in COMPARE_DIR.glob("*.csv")}
        declared = set(MAN["files"])
        self.assertEqual(on_disk - declared, set(),
                         "这些 CSV 没登记口径，不得参与任何并列：%s" % sorted(on_disk - declared))

    def test_ga_file_actually_contains_short_runs(self):
        """manifest 说 ga 是 400/600 步，这里自己去盘上数，不信任声明。"""
        vals = sorted({float(v) for v in G.column_values(COMPARE_DIR / "backend_ga_metrics.csv", "总步数")})
        self.assertIn(400.0, vals, "盘上没有 400 步行，那 manifest 的隔离理由不成立：%s" % vals)
        self.assertNotIn(2000.0, vals,
                        "ga 文件里已经出现 2000 步行 —— 口径可能已对齐，本用例的前提要重估")

    def test_baseline_files_genuinely_lack_the_fleet_columns(self):
        """机队 5 列只在 25 列 schema 里有。若哪天基线补上了，这条会红并提醒更新声明。"""
        five = ["无人机利用率", "空载率", "总飞行距离", "顺路接入次数", "禁飞区绕飞次数"]
        for name in SAME:
            hdr = G.header_of(COMPARE_DIR / name)
            missing = [c for c in five if c not in hdr]
            self.assertEqual(missing, five,
                             "%s 的缺列情况与 manifest 声明不符：%s" % (name, missing))

    def test_fingerprint_is_computed_not_transcribed(self):
        sig = G.disk_signature("backend_ortools_metrics.csv")
        self.assertEqual(sig["schema"], MAN["files"]["backend_ortools_metrics.csv"]["metrics_schema_version"])
        self.assertEqual(sig["total_steps_values"], ("2000.0",))


class EntryWiringTests(unittest.TestCase):
    """门禁必须真的接在生成入口上，而不是只有一个能被单独调用的库函数。"""

    def test_plot_entry_refuses_by_default(self):
        proc = subprocess.run(
            [sys.executable, str(RESULTS_DIR / "plot_compare_metrics.py")],
            cwd=str(ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        out = proc.stdout + proc.stderr
        self.assertNotIn("Traceback", out, "崩溃不等于拒绝：\n%s" % out[-1200:])
        self.assertEqual(proc.returncode, 1,
                         "出图入口默认竟然没拒绝混口径输入（exit=%d）：\n%s"
                         % (proc.returncode, out[-1500:]))
        self.assertIn("REFUSED", out)
        self.assertIn("口径组", out)

    def test_api_compare_marks_inconsistency_and_refuses_on_fallback(self):
        """今天的页面安全是**侥幸**：keep="last" 恰好把四行都落到 one_click_latest.csv。
        把那份文件移开，页面就会混口径 —— 那时必须 comparable=False 并给出原文理由。"""
        import console.server as server

        ok = server.compare()
        self.assertTrue(ok["comparable"], "今天这条应当通过；不通过说明读取链变了，判据要重估")
        self.assertEqual(ok["compared_sources"], ["one_click_latest.csv"],
                         "页面数据源不再是单一口径：%s" % ok["compared_sources"])

        latest = COMPARE_DIR / "one_click_latest.csv"
        saved = latest.read_bytes()
        latest.unlink()
        try:
            bad = server.compare()
        finally:
            latest.write_bytes(saved)
        self.assertFalse(bad["comparable"],
                         "one_click_latest 缺失后仍判可比 —— 门禁没接在 API 上")
        self.assertIn("口径组", bad["comparability_refusal"])
        self.assertEqual(latest.read_bytes(), saved, "还原失败，会把别人的工作区弄脏")

    def test_frontend_does_not_coerce_missing_columns_to_zero(self):
        """`r[m] ?? 0` 是那个假胜利的直接来源，禁止再回来。"""
        html = (ROOT / "console" / "static" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("compareRows.map(r => r[m] ?? 0)", html,
                         "柱图又把缺失列补成 0 了：缺失必须是断柱（null），"
                         "否则 20 列 schema 的基线在空载率上显示为 0，读成优于 GA")
        self.assertIn("this.compareComparable === false", html,
                      "前端不再消费门禁的 comparable，拒绝结果到不了用户眼前")


class SidecarConsistencyTests(unittest.TestCase):
    """README.md 是 manifest 的渲染产物，不能各写各的。"""

    def test_readme_matches_manifest_rendering(self):
        readme = COMPARE_DIR / "README.md"
        self.assertTrue(readme.is_file(), "缺 results/compare/README.md（口径声明必须同目录）")
        self.assertEqual(readme.read_text(encoding="utf-8"), G.render_readme(MAN),
                         "results/compare/README.md 与 manifest.json 不一致 —— "
                         "改了 manifest 要重跑 `python results/compare_gate.py --render-readme`")

    def test_readme_states_the_ga_verdict_in_plain_words(self):
        txt = (COMPARE_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn("400", txt)
        self.assertIn("2000", txt)
        self.assertIn("不可与", txt, "README 没写明哪个文件不能与谁并列")

    def test_missing_column_policy_is_written_down(self):
        txt = (COMPARE_DIR / "README.md").read_text(encoding="utf-8")
        for col in ("无人机利用率", "空载率", "总飞行距离", "顺路接入次数", "禁飞区绕飞次数"):
            self.assertIn(col, txt, "口径声明漏了 %s" % col)
        self.assertIn("绝不能补 0", txt, "缺失列的渲染规则没写进声明")


class CitationIntegrityTests(unittest.TestCase):
    """登记簿/README 里写的 `路径:行号` 引用必须真的解析得到。

    这条是被本轮的真实事故逼出来的：登记表一直写 `paper/main.tex:303`，
    而 `.tex` 的真路径是 `paper/AAMAS-2023 Formatting Instructions/main.tex` ——
    行号对、路径不存在，人照着翻是找不到的。手抄引用会过期，所以变成机器断言。
    """

    CITE = re.compile(r"`([^`\n]*?\.(?:tex|py|csv|json|md|html)):(\d+)`")
    # 登记簿约定：引用已删除的文件时写成 `path:line 已移除@<sha>`，
    # 并给出取回命令。这样"历史证据"不被抹掉，但也不会假装文件还在。
    REMOVED = re.compile(r"已移除@([0-9a-f]{7,40})")

    def _resolve(self, path_txt: str):
        """把引用解析成磁盘上的文件。

        带目录分隔的是完整路径，必须原样存在（本轮就是被 `paper/main.tex` 这种
        "行号对、路径不存在"的引用逼出这条用例的）。
        只写裸文件名的（`environment.py:927`）是登记簿里的常用简写，不判错 ——
        但全仓必须能找到同名文件，且行号不越界。
        """
        rel = path_txt.replace("\\", "/")
        if "/" in rel:
            target = ROOT / rel
            return [target] if target.is_file() else []
        # 裸文件名：全仓找同名
        return [p for p in ROOT.rglob(Path(rel).name)
                if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts
                and ".venv310" not in p.parts]

    def _git_show_lines(self, sha: str, rel: str):
        proc = subprocess.run(["git", "show", "%s^:%s" % (sha, rel)],
                              cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            return None
        return len([l for l in proc.stdout.splitlines()])

    def _docs(self):
        return [ROOT / "docs" / "数据来源与可追溯性登记表.md", ROOT / "README.md"]

    def test_cited_path_line_targets_exist(self):
        checked = 0
        bad = []
        for doc in self._docs():
            if not doc.is_file():
                continue
            for i, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
                for path_txt, lineno_s in self.CITE.findall(line):
                    checked += 1
                    cands = self._resolve(path_txt)
                    if cands:
                        ok_line = False
                        for target in cands:
                            with io.open(target, encoding="utf-8", errors="replace") as fh:
                                n = sum(1 for _ in fh)
                            if int(lineno_s) <= n:
                                ok_line = True
                                break
                        if not ok_line:
                            bad.append("%s:%d 引用 %s:%s，但同名文件最长只有 %d 行"
                                       % (doc.name, i, path_txt, lineno_s, n))
                        continue
                    # 盘上找不到：只有按约定标了"已移除@<sha>"且真能在该修订取回才算合格
                    m = self.REMOVED.search(line)
                    if not m:
                        bad.append("%s:%d 引用了找不到的文件 %s（若该文件已删除，"
                                   "请按约定写成 `path:line 已移除@<sha>` 并附取回命令）"
                                   % (doc.name, i, path_txt))
                        continue
                    n = self._git_show_lines(m.group(1), path_txt.replace("\\", "/"))
                    if n is None:
                        bad.append("%s:%d 标了已移除@%s，但 `git show %s^:%s` 取不回来"
                                   % (doc.name, i, m.group(1), m.group(1), path_txt))
                    elif int(lineno_s) > n:
                        bad.append("%s:%d 引用 %s:%s，但该修订只有 %d 行"
                                   % (doc.name, i, path_txt, lineno_s, n))
        self.assertGreater(checked, 0, "一条引用都没扫到，本用例是空转")
        self.assertEqual(bad, [], "引用失效：\n  " + "\n  ".join(bad))

    def test_removed_marker_convention_is_exercised(self):
        """正面用一次约定本身：登记簿里确实有按 `已移除@sha` 标注的历史引用，
        而且它们的取回命令真的能用 —— 否则上面那条拒绝分支永远走不到，等于没测。"""
        doc = (ROOT / "docs" / "数据来源与可追溯性登记表.md").read_text(encoding="utf-8")
        self.assertTrue(self.REMOVED.findall(doc),
                        "登记簿里没有一条 已移除@sha 标注，无法验证该约定可用")
        verified = 0
        for line in doc.splitlines():
            m = self.REMOVED.search(line)
            if not m:
                continue
            for path_txt, lineno_s in self.CITE.findall(line):
                if "/" not in path_txt or (ROOT / path_txt).exists():
                    continue
                n = self._git_show_lines(m.group(1), path_txt)
                self.assertIsNotNone(n, "取回命令失效：%s" % path_txt)
                self.assertGreaterEqual(
                    n, int(lineno_s),
                    "%s 在 %s^ 里只有 %d 行，引用却指 :%s" % (path_txt, m.group(1), n, lineno_s))
                verified += 1
        self.assertGreater(verified, 0, "一条历史引用都没验到，本用例空转")

    def test_paper_tex_is_located_by_its_real_path(self):
        """专门钉 paper/main.tex 这个曾经写错的路径。"""
        self.assertFalse((ROOT / "paper" / "main.tex").exists(),
                         "paper/main.tex 现在竟然存在了 —— 若已移动请同步更新登记引用")
        real = list((ROOT / "paper").glob("**/main.tex"))
        self.assertTrue(real, "paper 下找不到任何 main.tex")
        txt = real[0].read_text(encoding="utf-8")
        self.assertIn("Greedy & 0.967", txt,
                      "真 .tex 里找不到登记表 R1 引用的 Greedy 行，行号断言已失效")


if __name__ == "__main__":
    unittest.main()
