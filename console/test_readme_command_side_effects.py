# -*- coding: utf-8 -*-
"""照 README 跑一次，仓库必须还是干净的。

为什么这条门禁值得存在（一手证据）：README「跑一次评测」那条示例命令的**默认输出**
原先直接写 `results/compare/backend_ga_metrics.csv`（已入库、且是 Web「算法对比」页的
数据源）。实测照抄一次：

    $ git status --porcelain
     M results/compare/backend_ga_metrics.csv        # 行数 7 → 8

评审或新用户只要照着文档走一遍，工作区就脏了 —— 这正是"离了作者机器就跑不通/说不清"
那一类。更狠的是 `run_conclusion.py --preset conclusion` 会**截断重写**入库的
`results/compare/one_click_latest.csv`，以及 `plot_compare_metrics.py` 会覆盖
`results/compare/plots/` 下 15 个已提交产物：那不是脏，是丢证据。

本文件把三件事钉住：
① 真的跑一次文档命令，断言跑完 `git status --porcelain` 为空（行为，最贵但最可信）；
② 用 AST 断言三个写盘脚本的**默认输出**都落在已 gitignore 的位置（静态，不依赖第三方库，
   即使本机缺 numpy/osmnx 也照样执行 —— 避免"门禁在最需要它的聚合跑里静默 skip"）；
③ 断言脏检测探针本身不是空转（故意造一个未跟踪文件，必须被 porcelain 抓到）。

没有 ② 的话，将来有人把默认目录改回 results/compare，只有 ① 那一半会在有依赖的机器上
才红；有了 ②，无依赖环境也能立刻发现。
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from console import _preflight as _PF  # noqa: E402
for p in (str(ROOT), str(ROOT / "frontend")):
    if p not in sys.path:
        sys.path.insert(0, p)


def _porcelain(cwd=None):
    proc = subprocess.run(["git", "status", "--porcelain"],
                          cwd=str(cwd or ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError("git status 失败（%s）：%s" % (proc.returncode, proc.stderr.strip()))
    return [l for l in proc.stdout.splitlines() if l.strip()]


def _check_ignored(path):
    """git check-ignore -q：0 表示该路径被忽略。"""
    return subprocess.run(["git", "check-ignore", "-q", str(path)],
                          cwd=str(ROOT), capture_output=True).returncode == 0


def _evidence_fingerprint():
    """给所有已入库的 results/compare/** 证据文件算一份内容指纹。

    为什么光比 porcelain 增量不够：如果某个证据文件**本来就已脏**（开发期很常见），
    文档命令再往里追加一行，porcelain 那一行的字符串是不变的，增量法就看不出来 ——
    这是一类"已经脏了所以不会再更脏"的假绿。内容指纹不受它影响。
    """
    import hashlib

    tracked = subprocess.run(
        ["git", "ls-files", "results/compare"], cwd=str(ROOT),
        capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.split()
    dig = {}
    for rel in tracked:
        p = ROOT / rel.replace("/", os.sep)
        if p.is_file():
            dig[rel] = hashlib.md5(p.read_bytes()).hexdigest()
    return dig


class ReadmeCommandSideEffectTests(unittest.TestCase):
    """README 示例命令的默认输出不得落在任何已跟踪路径上。"""

    def test_dirty_detector_is_not_vacuous(self):
        """先证明本文件用的脏检测真的能看见东西，否则后面的"为空"断言没有意义。"""
        marker = ROOT / "results" / "zz_dirty_detector_probe.txt"
        self.assertNotIn("zz_dirty_detector_probe.txt", " ".join(_porcelain()),
                         "探针文件一开始就在，说明工作区本来不干净")
        marker.write_text("probe\n", encoding="utf-8")
        try:
            caught = [l for l in _porcelain() if "zz_dirty_detector_probe" in l]
            self.assertTrue(caught,
                            "写了文件但 git status --porcelain 仍为空 —— 脏检测是空转，"
                            "本文件所有「必须为空」的断言都会假绿")
        finally:
            marker.unlink(missing_ok=True)
        self.assertEqual([l for l in _porcelain() if "zz_dirty_detector_probe" in l], [],
                         "删掉后仍被检出，说明探针没真正清场")

    def _default_return_expr(self, func_name, guard_name, path):
        """取 `if not <guard_name>: return <expr>` 这条**默认分支**的返回表达式。

        第一版这里写成 `"adhoc" in ast.dump(tree)`，是个空转断言：把默认分支改回
        results/compare 之后，"adhoc" 仍然出现在函数 docstring 里，dump 照样命中、
        测试照样绿（已实测：变异后本条不红，只有行为用例发现了我）。
        所以现在按 AST 结构定位那条早退 return，只看它自己。
        """
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == func_name:
                for stmt in node.body:
                    if not isinstance(stmt, ast.If):
                        continue
                    test = ast.unparse(stmt.test)
                    if guard_name not in test:
                        continue
                    returns = [s for s in stmt.body if isinstance(s, ast.Return)]
                    if returns:
                        return test, ast.unparse(returns[0].value)
                return None, None
        return "FUNC_NOT_FOUND", None

    def test_evaluate_metrics_default_is_not_the_tracked_evidence_dir(self):
        """未加开关时那条 return 必须指向 results/adhoc，而不是 results/compare。"""
        test, expr = self._default_return_expr(
            "_get_metrics_output", "record_into_evidence",
            ROOT / "frontend" / "evaluate_metrics.py")
        self.assertIsNotNone(expr,
                             "_get_metrics_output 里找不到按开关早退的默认分支 —— "
                             "开关被拆掉了，默认路径无法再与证据目录区分")
        self.assertIn("adhoc", expr,
                      "默认分支返回的是 %s —— 照 README 跑一次就会写入库目录" % expr)
        self.assertNotIn("compare", expr,
                         "默认分支指向了 %s，即已入库的 results/compare" % expr)
        self.assertTrue(_check_ignored(ROOT / "results" / "adhoc" / "backend_ga_metrics.csv"),
                        "results/adhoc 不再被 gitignore，默认输出会立刻脏仓库")

    def test_plot_script_default_is_not_the_tracked_plots_dir(self):
        tree = ast.parse((ROOT / "results" / "plot_compare_metrics.py").read_text(encoding="utf-8"))
        module = tree.body
        out_dir_value = None
        for node in module:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "OUT_DIR":
                        out_dir_value = ast.unparse(node.value)
        self.assertIsNotNone(out_dir_value, "找不到模块级 OUT_DIR 赋值，探针没生效")
        self.assertIn("adhoc", out_dir_value,
                      "plot_compare_metrics 的默认 OUT_DIR 变成了 %s —— 它会覆盖 "
                      "results/compare/plots 下 15 个已入库产物" % out_dir_value)
        self.assertNotIn("EVIDENCE_OUT_DIR", out_dir_value,
                         "默认值直接指向入库目录了")

    def test_runner_publishes_latest_only_on_explicit_flag(self):
        """_aggregate 默认不得截重写入库的 one_click_latest.csv。"""
        from experiments import runner as R

        row = {
            "实验": "algorithm_comparison", "变量": "", "取值": "", "重复": 1,
            "Seed": 101, "算法key": "greedy", "算法": "Greedy", "成功": True,
            "耗时秒": 1.0, "错误": "",
        }
        row.update({c: 0.5 for c in R.METRIC_COLUMNS})

        with tempfile.TemporaryDirectory() as tmp:
            fake_root = Path(tmp)
            real_root = R.PROJECT_ROOT
            R.PROJECT_ROOT = fake_root          # 把"入库目录"整体搬到临时区，绝不碰真文件
            try:
                out_dir = fake_root / "exp"
                R._aggregate([row], out_dir, {"_preset_key": "conclusion"},
                             publish_latest=False)
                latest = fake_root / "results" / "compare" / "one_click_latest.csv"
                self.assertFalse(latest.exists(),
                                 "没加 --publish-latest 就写了共享证据文件，"
                                 "照 README 跑一次 conclusion 会截断重写已入库文件")
                R._aggregate([row], out_dir, {"_preset_key": "conclusion"},
                             publish_latest=True)
                self.assertTrue(latest.exists(),
                                "加了显式开关却不发布，说明开关没接线")
            finally:
                R.PROJECT_ROOT = real_root

    def test_readme_states_where_each_writer_puts_bytes(self):
        """文档必须说清默认写在哪、显式开关叫什么 —— 光改代码不写文档等于没改。"""
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for token in ("results/adhoc", "--record-into-evidence", "--publish-latest"):
            self.assertIn(token, readme,
                          "README 不再说明 %s，评审无法知道自己那条命令会不会写盘" % token)


class PairedClaimConsistencyTests(unittest.TestCase):
    """文档里凡引用配对表，就必须带上"它不构成显著性"的限定 —— 双向指纹。

    为什么值得钉：`paired_ga_vs_greedy.csv` 印着胜/平/负三列，读起来就像结论；而密度扫描
    实测（四档 × 6 seed）显示**没有任何一档 GA 显著优于贪心**，反而在高压力两档贪心显著更好
    （精确双侧 p=0.0312）。所以"免责声明"不能只是一句措辞，要让它与引用点互相同步：
    ① 引用者必须带限定语（否则红）；② 若有人把所有限定语都删了，那条声明本身也不能悄悄消失
    （否则红）。两个方向都要能响，单向断言只会过期。
    """

    # 提到配对表 / 胜负计数的位置（README 与两份结项文档）
    SOURCES = ("README.md", "docs/结项修改说明.md", "docs/产品化收口与结项口径审计.md")
    QUALIFIERS = ("不代表统计显著性", "不构成显著性结论", "不判优", "不可判", "最小可得 p")
    TOKEN = "paired_ga_vs_greedy"

    def _lines(self, rel):
        p = ROOT / rel
        if not p.is_file():
            return []
        return [(i + 1, l) for i, l in enumerate(p.read_text(encoding="utf-8").splitlines())]

    def test_every_reference_to_the_paired_table_is_qualified(self):
        refs, bad = 0, []
        for rel in self.SOURCES:
            lines = self._lines(rel)
            for idx, line in lines:
                if self.TOKEN not in line:
                    continue
                refs += 1
                # 限定语允许出现在同一行或其后 6 行内（表格与注常分行写）
                window = "".join(l for _i, l in lines[idx - 1:idx + 6])
                if not any(q in window for q in self.QUALIFIERS):
                    bad.append("%s:%d %s" % (rel, idx, line.strip()[:70]))
        self.assertGreaterEqual(refs, 1,
                                "%s 这个标记在文档里一次都没出现 —— 本用例已空转，"
                                "要么改引用点要么删这条门" % self.TOKEN)
        self.assertEqual(bad, [], "这些引用没带显著性限定语：%s" % bad)
        print("[CLAIM_GATE] 引用配对表 %d 处，全部带限定语" % refs)

    def test_qualifier_survives_even_if_references_are_cleaned(self):
        """反方向：不许靠"删掉引用"来让上一条变绿而不留任何免责说明。"""
        found = []
        for rel in self.SOURCES:
            txt = (ROOT / rel).read_text(encoding="utf-8") if (ROOT / rel).is_file() else ""
            found.append((rel, any(q in txt for q in self.QUALIFIERS)))
        self.assertTrue(any(ok for _r, ok in found),
                        "三份文档都不再声明显著性限定（%s）—— 那要么是结论真的变了，"
                        "要么是删声明绕过门，两种都必须人来拍" % found)


class ReadmeCommandCleanTreeRunTests(unittest.TestCase):
    """真跑一条文档命令，跑完工作区必须为空。"""

    def test_quickstart_command_leaves_repo_clean(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        cmd = ("python evaluate_metrics.py --policy ga --episodes 1 "
               "--episode-steps 600 --seed 100")
        self.assertIn(cmd, readme, "README 的示例命令被改了，本用例的同步跟进是必须的")

        before = set(_porcelain())
        fp_before = _evidence_fingerprint()
        self.assertTrue(fp_before, "没有比出任何已入库证据文件，指纹断言是空转")
        # 不断言 before 为空：本仓库在改代码的过程中也会有未提交项，
        # 要求"必须先干净"会让这条用例在开发期常年红、最后被关掉。
        # 判据改成**增量**：跑完文档命令不许新增任何脏项。
        proc = subprocess.run(
            [sys.executable, "evaluate_metrics.py", "--policy", "ga", "--episodes", "1",
             "--episode-steps", "600", "--seed", "100"],
            cwd=str(ROOT / "frontend"), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})

        out = proc.stdout + proc.stderr
        if _PF.env_shortfall(proc.returncode, out):
            self.skipTest("当前解释器缺仿真依赖（numpy/osmnx 等），"
                          "行为验证改由上面的 AST 静态用例覆盖：%s" % out[-300:])
        self.assertEqual(proc.returncode, 0,
                         "README 示例命令本身跑挂了：\n%s" % out[-2000:])
        # 防"空跑绿"：必须真的产出了一次评测
        self.assertIn("metrics_file:", out,
                      "命令没走到写盘那一步，后面断言是空转：\n%s" % out[-800:])
        written = [l for l in out.splitlines() if l.startswith("metrics_file:")]
        path = written[0].split("metrics_file:", 1)[1].strip()
        self.assertTrue(_check_ignored(path),
                        "文档命令默认写到了未忽略路径 %s，会把仓库弄脏" % path)

        new_dirt = sorted(set(_porcelain()) - before)
        self.assertEqual(new_dirt, [],
                         "照 README 跑一次示例命令后工作区新增了 %d 项脏：%s"
                         % (len(new_dirt), new_dirt))

        fp_after = _evidence_fingerprint()
        changed = sorted(k for k in fp_before if fp_before[k] != fp_after.get(k))
        self.assertEqual(changed, [],
                         "文档命令改写了已入库的答辩证据文件（%d 个）：%s —— "
                         "这类文件即使本来就已脏，porcelain 增量也看不出来，"
                         "所以必须比内容指纹" % (len(changed), changed))


if __name__ == "__main__":
    unittest.main()
