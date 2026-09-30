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
from console import _preflight  # noqa: E402

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
    """门禁必须真的接在生成入口上，而不是只有一个能被单独调用的库函数。

    本类需要 fastapi/pandas：缺依赖时整体 skip 并写明该用哪个解释器，
    而不是留一个 ImportError 让评审以为代码坏了。
    """

    def setUp(self):
        _preflight.require("fastapi", "pandas",
                           gated_in="console/test_compare_gate.py::EntryWiringTests")

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


class FrontendStaticTests(unittest.TestCase):
    """纯文本断言，不需要任何第三方依赖 —— 单独成类，不被上面的 fastapi 连坐 skip。"""

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

    def test_readme_carries_every_declared_field(self):
        """README 里必须出现每个文件声明的 note 文本。

        为什么不能只靠上面那条逐字相等：相等断言只看"两边一样"，渲染器少读一个字段时
        两边会**一起缺**，测试照样绿。本轮真实踩过：`backend_ga_metrics.csv` 的
        "400 步的 GA 行不可与 2000 步的基线并列"只存在于 manifest.note，
        渲染器当时根本不读 note —— README 里 0 次命中，而漂移测试全绿。
        拿 CSV 的人看的是 README，所以这条按**字段是否落到读者眼前**来判。
        """
        txt = (COMPARE_DIR / "README.md").read_text(encoding="utf-8")
        missing = []
        checked = 0
        for name, decl in MAN["files"].items():
            note = (decl.get("note") or "").strip()
            if not note:
                continue
            checked += 1
            probe = note[:24]
            if probe not in txt:
                missing.append("%s 的 note（%r…）没进 README" % (name, probe))
        self.assertEqual(checked, len(MAN["files"]),
                         "%d/%d 个文件有 note，声明本身就不齐" % (checked, len(MAN["files"])))
        self.assertEqual(missing, [], "\n  ".join(missing))

    def test_ga_verdict_sentence_reaches_the_csv_reader(self):
        """把你那句要求钉死：'400 步…不可与 2000 步…并列' 必须在 sidecar 里可见。"""
        txt = (COMPARE_DIR / "README.md").read_text(encoding="utf-8")
        self.assertIn("400 步的 GA 行不可与 2000 步的基线并列", txt,
                      "sidecar 里没有这句结论 —— 只在 manifest / 提交信息里说不算")
        self.assertIn('不画这根柱子', txt,
                      "matplotlib 侧缺列的读者观感（三根柱子根本不出现）必须写进 sidecar")

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

    本轮又补了两层，因为发现上一层是**半盲**的：
    ① 旧正则只认 `:123`，登记簿里 `:118-121`、`:141-145,153,195` 这类写法
       一条都没进断言 —— 拿 HEAD 的文档喂新判据，实测 5 条立刻红（含 1 条
       指向 6b8c4c8 已删除的文件却不带 已移除@ 标注）。旧门禁不是"没报错"，
       是**根本没看见**。
    ② 只判"路径存在 + 行号不越界"挡不住**行号在范围内却指向别处**：本轮逐条
       对着盘上内容核，发现相当一部分引用属于这一类（如 P1 抄 :112 实为 :88，
       M1 抄 :926 实为 :921）。所以加了 `#锚点`：被引行必须含这段字。
       没带锚点的仍然只判越界，因此每条断言都把「扫到几条 / 带锚点几条」一起报出来
       —— 具体数字只在报警行里印，不抄进这段说明，免得它自己也过期。
    """

    # 判据只有一份实现：console/_citations.py。用例负责喂样本，不再抄一遍，
    # 否则"门禁与测试各判各的"就是下一轮假绿灯的来源。按路径加载，不接受同名撞车。
    CJ = None

    @classmethod
    def setUpClass(cls):
        import importlib.util
        path = ROOT / "console" / "_citations.py"
        spec = importlib.util.spec_from_file_location("console_citations_gate", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        cls.CJ = mod
        if Path(mod.__file__).resolve() != path.resolve():
            raise AssertionError("加载到了别的 _citations.py：" + mod.__file__)

    @property
    def CITE(self):
        return self.CJ.CITE

    @property
    def REMOVED(self):
        return self.CJ.REMOVED

    def _ranges(self, spec):
        return self.CJ.ranges(spec)

    def _resolve(self, path_txt):
        return self.CJ.resolve(path_txt)

    def _git_show_text(self, sha, rel):
        return self.CJ.git_show_text(sha, rel)

    def _scan_lines(self, lines, origin=""):
        return self.CJ.scan_lines(lines, origin)

    def _docs(self):
        return [ROOT / "docs" / "数据来源与可追溯性登记表.md", ROOT / "README.md"]

    def test_cited_path_line_targets_exist(self):
        checked = anchored = 0
        bad = []
        for doc in self._docs():
            if not doc.is_file():
                continue
            c, a, b = self._scan_lines(doc.read_text(encoding="utf-8").splitlines(), doc.name)
            checked += c
            anchored += a
            bad += b
        self.assertGreater(checked, 0, "一条引用都没扫到，本用例是空转")
        # 锚点是"行号对但内容不对"的唯一防线；一条都没标就等于这道防线没架起来
        self.assertGreater(anchored, 0,
                           "全仓没有一条引用带 #锚点，行号漂移（在范围内指错处）无人能测")
        self.assertEqual(bad, [], "引用失效：\n  " + "\n  ".join(bad))

    def test_detector_itself_is_not_vacuous(self):
        """判别式：喂合成文本，检测器必须**该红的红、该绿的绿**。

        为什么专门加一条：上面那条只读真文档，若哪天有人把判据放宽（例如给
        "文件不存在"加个 except 跳过），真文档里没有坏引用时它照样绿 —— 这就是
        "门从此刻意看不见那一类"。合成样本能主动把它测红。
        本轮实测过：往登记表临时插一条 `frontend/does_not_exist_anywhere.py:9999`
        → test_cited_path_line_targets_exist FAILED（退出码 1），随后已还原。
        """
        good = ["引用 `console/server.py:1` 合法",
                "区间 `console/server.py:1-3` 合法",
                "多段 `config/simulation.json:166,162-163` 合法",
                "锚点 `config/simulation.json:166#battery_low_threshold` 合法",
                "历史 `frontend/map_drawer_3d.py:40` 已移除@6b8c4c8 取回可用",
                "历史区间 `backend_wx/pymarl-master/analyze_sacred_run.py:74-101`"
                " 已移除@6b8c4c8 取回可用"]
        gc, ga, gb = self._scan_lines(good, "合成")
        self.assertEqual(gc, 6, "合成样本没被全部扫到引用（%d/6），判据没跑起来" % gc)
        self.assertEqual(gb, [], "合法引用被判失效：%s" % gb)
        self.assertEqual(ga, 1, "锚点计数应当只认带 # 的那条，实得 %d" % ga)

        bad = ["`frontend/does_not_exist_anywhere.py:9999`",
               "`frontend/map_drawer_3d.py:40` 已移除@deadbee",
               # 下面三条是上一版**完全扫不到**的形式：区间越界、区间指向已删文件却无标注、
               # 以及行号在范围内但内容不对（锚点失配）
               "`config/simulation.json:1-99999`",
               "`frontend/map_drawer_3d.py:145-149`",
               "`config/simulation.json:166#not_a_real_key_in_that_block`"]
        bc, ba, bb = self._scan_lines(bad, "合成")
        self.assertEqual(bc, 5, "区间/多段形式仍然没进扫描（%d/5）" % bc)
        self.assertEqual(len(bb), 5, "5 条坏引用只报了 %d 条：%s" % (len(bb), bb))
        self.assertEqual(ba, 1)
        self.assertIn("找不到", "\n".join(bb))
        self.assertIn("取不回来", "\n".join(bb))
        self.assertIn("最长只有", "\n".join(bb))
        self.assertIn("已移除", "\n".join(bb))
        self.assertIn("锚点", "\n".join(bb))

    def test_coverage_is_printed_not_just_asserted(self):
        """绿的时候也要看得见覆盖率：判据扫到几条、其中几条真带锚点。

        只在红的时候才打印数字，等于"没人知道自己被半盲的门放过去"——
        与 skipped=12 被读成"过了 12 条"是同一种失败。
        """
        checked, anchored, bad = self.CJ.scan_docs()
        text = self.CJ.render()
        self.assertGreater(checked, 0, "一条引用都没扫到，判据空转")
        self.assertGreater(anchored, 0, "一条锚点都没有，行号漂移无人能测")
        self.assertIn("条 path:line", text)
        for n in (checked, anchored):
            self.assertIn("%d 条" % n, text, "汇总行没把 %d 印出来" % n)
        self.assertEqual(text.count("[FAIL]"), len(bad),
                         "打印的失效条数与真实失效条数不一致（%d vs %d）"
                         % (text.count("[FAIL]"), len(bad)))
        # 答辩机控制台常是 GBK：一个打不出来的字符会把整条命令崩掉，
        # 而崩掉的检查比没有检查更糟（_preflight 第一版就是这么坏的）。
        try:
            text.encode("gbk")
        except UnicodeEncodeError as exc:
            self.fail("引用汇总含 GBK 打不出的字符：%s" % exc)
        self.assertEqual(self.CJ.main(["--verify"]), 1 if bad else 0,
                         "--verify 的退出码没有跟随失效条数")

    def test_obsolete_marker_is_bound_to_its_own_citation(self):
        """`已失效@sha` 只对它**紧跟其后**的那一条引用生效，不是整行共享。

        这条是加约定当下一轮门自己抓出来的 bug：一行里同时写"历史行号"和"现状行号"时，
        按整行找标注会把历史标注错扣到现状那条上，于是它被判去跟旧修订比内容 ——
        报出来的"失效"是假的，而假的报警比没报警更容易把人带偏。
        """
        hist = "`frontend/environment.py:268#具有高度信息的建筑物` 已失效@66016b7"
        live = "`frontend/environment.py:276-277#地图建筑`"
        both = "10. ~~%s~~ 已做：现在分三数打印 %s" % (hist, live)
        c, a, b = self._scan_lines([both], "合成")
        self.assertEqual(c, 2, "两条引用都应被扫到")
        self.assertEqual(b, [], "现状那条不该被历史标注连坐：%s" % b)
        self.assertEqual(a, 2, "历史那条带锚点也要计进覆盖率")

        # 摘掉标注后，两条都被判去跟**磁盘**比：现状那条照旧绿，历史那条当场红 ——
        # 因为 268 在磁盘上早已是另一行。这个对照证明标注真的改变了比对对象，
        # 而不是"加了个没人读的记号"。
        c2, a2, b2 = self._scan_lines([both.replace(" 已失效@66016b7", "")], "合成")
        self.assertEqual((c2, a2), (2, 2), "摘掉标注后两条仍应被扫到并带锚点")
        self.assertEqual(len(b2), 1, "摘掉标注后历史那条必须红：%s" % b2)
        self.assertIn("找不到锚点", b2[0])

    def test_obsolete_marker_branches_go_red_when_wrong(self):
        """历史引用四种错法都要红：缺锚点、行号手抄时就错、sha 取不回、越界。"""
        cases = [
            ("`frontend/environment.py:268` 已失效@66016b7", "却不带 #锚点"),
            ("`frontend/environment.py:282#具有高度信息的建筑物` 已失效@66016b7", "没有锚点"),
            ("`frontend/environment.py:268#具有高度信息的建筑物` 已失效@deadbee", "取不回来"),
            ("`frontend/environment.py:268-999999#具有高度信息的建筑物` 已失效@66016b7", "只有"),
        ]
        for text, expect in cases:
            _c, _a, b = self._scan_lines([text], "合成")
            self.assertEqual(len(b), 1, "%s 没被判红" % text)
            self.assertIn(expect, b[0], "%s 的报警文不对题：%s" % (text, b[0]))
        # 正面：登记簿里实际用的那两条历史标注必须能用（否则上面四种错法都走不到分支）
        doc = (ROOT / "docs" / "数据来源与可追溯性登记表.md").read_text(encoding="utf-8")
        _c, a, b = self._scan_lines(doc.splitlines(), "登记簿")
        self.assertEqual(b, [], "真文档里有失效引用：%s" % b)
        self.assertGreater(a, 0)

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
            for path_txt, spec, _anchor in self.CITE.findall(line):
                if "/" not in path_txt or (ROOT / path_txt).exists():
                    continue
                blob = self._git_show_text(m.group(1), path_txt)
                self.assertIsNotNone(blob, "取回命令失效：%s" % path_txt)
                hi = max(b for _, b in self._ranges(spec))
                self.assertGreaterEqual(
                    len(blob), hi,
                    "%s 在 %s^ 里只有 %d 行，引用却指 :%s" % (path_txt, m.group(1), len(blob), spec))
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
