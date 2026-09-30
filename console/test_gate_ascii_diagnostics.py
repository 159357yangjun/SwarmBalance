# -*- coding: utf-8 -*-
"""门禁报红时，人必须能看出"哪一行、哪一类、往哪改"—— 中文掉色之后也要能。

起因是实测而不是推测：这台机的控制台/输出通道是 GBK 系，中文会被替换成 `??????`
（本轮就有一次：`_paperscan.py` 的 SyntaxWarning 里那段中文在用户的运行里整片糊掉）。
一条只有中文诊断的红等于没有门 —— 值班的人看得见 `[FAIL]`，看不见它在说什么。
所以每条失效行的形状固定为

    [FAIL][<ASCII 短码>] <文档>:<行> <ASCII 事实> | fix: <ASCII 方向><中文解释>

双向钉三件事：
① 每个发得出来的短码都必须在 `console/_citations.py` 头部的短码表里有解释（否则短码是暗号）；
② 表里解释过的每个短码都必须真的被发出来过（否则表是装饰，代码早换了叫法）；
③ 掉色后仍可读：整行按 ASCII 有损编码再解回来，短码 / `文档:行` / `| fix:` 必须仍在，
   而中文必须**确实丢掉** —— 后半句是这条用例的非空转证明。

样本按登记簿的真实写法排：`已移除@`/`已失效@` 在反引号**外面**（`path:line` 在里面的锚点
之后不能有空格，写进去整条就匹配不上，这个坑是样本第一次全绿时抓到的）。
"""
from __future__ import annotations

import contextlib
import io
import re
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from console import _citations as CJ      # noqa: E402
from console import _paperscan as PS      # noqa: E402  与 paper_report 用同一个模块实例
from console import _rowsets as RS        # noqa: E402

SELF = "console/_citations.py"
GONE = "frontend/no_such_file_anywhere.py"
LINE = 1                     # 每个样本单独喂一遍，所以报警里的行号恒为 1


def git(*args):
    return subprocess.run(["git"] + list(args), cwd=str(ROOT), capture_output=True,
                          text=True, encoding="utf-8", errors="replace").stdout


def a_retrievable_sha():
    """找一个"它的父修订里真的有 SELF"的提交 —— 找不到就报错，不许静默跳过。"""
    for sha in git("rev-list", "HEAD", "--", SELF).split():
        pr = subprocess.run(["git", "show", "%s^:%s" % (sha, SELF)], cwd=str(ROOT),
                            capture_output=True)
        if pr.returncode == 0 and len(pr.stdout.splitlines()) > 3:
            return sha[:7]
    raise AssertionError("没有一个提交的历史修订能取回 %s，历史类样本无从构造" % SELF)


SHA = a_retrievable_sha()
BAD_SHA = "deadbeef"          # 16 进制、语法上合法、但仓里不存在

# (期望短码, 引用文本)：全部按登记簿约定写（标注在反引号外）
CITE_SAMPLES = [
    ("[CITE_NOFILE]", "见 `%s:12`" % GONE),
    ("[CITE_RANGE]", "见 `%s:9999999`" % SELF),
    ("[ANCHOR_MISS]", "见 `%s:5#这段字绝不在那一行`" % SELF),
    ("[ANCHOR_REQUIRED]", "见 `%s:2` 已失效@%s" % (SELF, SHA)),
    ("[CITE_RANGE_HISTORY]", "见 `%s:9999999` 已失效@%s" % (SELF, SHA)),
    ("[ANCHOR_MISS_HISTORY]", "见 `%s:2#绝无此锚点` 已失效@%s" % (SELF, SHA)),
    ("[GIT_SHOW_FAIL]", "见 `%s:2#x` 已失效@%s" % (SELF, BAD_SHA)),
    ("[GIT_SHOW_FAIL]", "见 `%s:5` 已移除@%s" % (GONE, BAD_SHA)),
]


def docstring_codes():
    """`_citations.py` 头部那张短码表里的短码集合。"""
    return set(re.findall(r"^\s{4}\[([A-Z][A-Z_]+)\]\s", CJ.__doc__ or "", re.M))


def codes_in(text):
    """一行里出现的短码；`FAIL`/`OK` 是包裹前缀不是短码，排除掉。"""
    return {c for c in re.findall(r"\[([A-Z][A-Z_]+)\]", text) if c not in ("FAIL", "OK")}


class GateAsciiDiagnosticsTests(unittest.TestCase):

    def setUp(self):
        self.sandbox = ROOT / "results" / "adhoc" / "_ascii_probe"
        shutil.rmtree(self.sandbox, ignore_errors=True)

    def tearDown(self):
        shutil.rmtree(self.sandbox, ignore_errors=True)

    def assert_legible(self, msg, code, origin="docs/p.md", line=LINE):
        """断言这一行即使整段中文变成 `?` 也还能用。"""
        self.assertTrue(msg.startswith(code), "失效行必须以短码开头，实际：%s" % msg[:60])
        self.assertIn("%s:%d" % (origin, line), msg, "短码后面要跟着 文档:行 —— %s" % msg[:70])
        self.assertIn("| fix:", msg, "报警必须给 ASCII 的 fix 方向：%s" % msg[:70])
        faded = msg.encode("ascii", "replace").decode("ascii")
        self.assertNotEqual(faded, msg, "这一行本来就没中文，用例在空转")
        for token in (code, "%s:%d" % (origin, line), "| fix:"):
            self.assertIn(token, faded,
                          "掉色后丢了 %s —— 这条门在打不出中文的通道上没人能读" % token)
        return faded

    def rowset_cases(self):
        self.sandbox.mkdir(parents=True)
        (self.sandbox / "README.md").write_text("本目录已作废（探针）", encoding="utf-8")
        head = "Algorithm,Score\n"
        for name, keys in (("ten.csv", sorted(RS.ALL_NAMED)), ("four.csv", sorted(RS.CORE))):
            (self.sandbox / name).write_text(
                head + "\n".join("%s,%d" % (a, n) for n, a in enumerate(keys)) + "\n",
                encoding="utf-8")
        rel = lambda n: (self.sandbox / n).relative_to(ROOT).as_posix()
        return [("[ROWSET_UNDECLARED]", "引用 `%s` 的均值" % rel("ten.csv")),
                ("[ROWSET_STALE]", "引用 `%s` 行集=all10 的均值" % rel("four.csv"))]

    def rowset_msgs(self):
        out = []
        for code, text in self.rowset_cases():
            msgs = CJ.rowset_violations([text], "docs/p.md", vdirs=[self.sandbox])[2]
            self.assertEqual(len(msgs), 1, "%s 应恰好弄红一条：%s" % (code, msgs))
            out.append((code, msgs[0]))
        return out

    # ---- ① / ③ 每条判据都能被真的弄红，且掉色后仍可读 ----------------------
    def test_citation_failures_survive_a_console_that_cannot_print_chinese(self):
        seen = []
        for code, text in CITE_SAMPLES:
            msgs = CJ.scan_lines([text], "docs/p.md")[2]
            self.assertEqual(len(msgs), 1,
                             "样本应恰好弄红一条（期望 %s）：\n  %s\n  -> %s" % (code, text, msgs))
            self.assert_legible(msgs[0], code, "docs/p.md")
            seen.append(code)
        self.assertGreaterEqual(len(set(seen)), 6,
                                "样本只覆盖到 %s，覆盖面塌了" % sorted(set(seen)))

    def test_rowset_failures_survive_color_loss(self):
        for code, msg in self.rowset_msgs():
            self.assert_legible(msg, code, "docs/p.md")

    def test_summary_and_paper_lines_are_legible(self):
        old = CJ.scan_docs
        try:
            CJ.scan_docs = lambda: (68, 68, ["[CITE_NOFILE] docs/p.md:9 x | fix: y"], 3, 3)
            out = CJ.render()
        finally:
            CJ.scan_docs = old
        lines = out.split("\n")
        for code, needle in (("[CITE_SUMMARY]", "checked=68"),
                             ("[ROWSET_SUMMARY]", "void_refs=3"),
                             ("[SUMMARY]", "1 broken reference(s)")):
            hit = [l for l in lines if code in l]
            self.assertEqual(len(hit), 1, "%s 那行没出现：%s" % (code, lines))
            faded = hit[0].encode("ascii", "replace").decode("ascii")
            self.assertNotEqual(faded, hit[0], "%s 本来就没中文，用例空转" % code)
            self.assertIn(needle, faded, "%s 掉色后丢了现值" % code)

        # 清单缺失 / 被手改 / 相符 三条分支：短码与现值都要在 ASCII 侧站得住；
        # 只有两条失败分支需要带上 ASCII 的修法（成功行不该有 fix）
        need_fix = {"PAPER_LIST_MISSING", "PAPER_LIST_STALE"}
        for code, text in self.paper_branch_texts():
            faded = text.encode("ascii", "replace").decode("ascii")
            self.assertNotEqual(faded, text, "%s 那行本来没中文，用例空转" % code)
            self.assertIn("[%s]" % code, faded, "%s 掉色后丢了短码：%s" % (code, faded[:120]))
            if code in need_fix:
                self.assertIn("--paper-report --write", faded,
                              "%s 掉色后丢了那条修法：%s" % (code, faded[:120]))
            else:
                self.assertIn("byte_equal=yes", faded,
                              "%s 掉色后丢了那个现值：%s" % (code, faded[:120]))

    def paper_branch_texts(self):
        """把 paper_report 的三条分支各跑一遍，返回 [(短码, 打出来的那行)]。

        用 ghost 路径制造"清单不存在"，再写一份内容不符的制造"被手改"，最后写回重算结果
        制造"相符"。全程只动 results/adhoc/（已 gitignore）下的临时文件，不碰真清单。
        """
        ghost = "results/adhoc/_不存在的清单_探针.md"
        real_rel = PS.OUT_REL
        out = []
        try:
            PS.OUT_REL = ghost
            path = ROOT / ghost
            for mode in ("missing", "stale", "match"):
                if mode == "stale":
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("手改过的一份", encoding="utf-8")
                elif mode == "match":
                    text, _rows, _facts = PS.render(ROOT)
                    path.write_text(text, encoding="utf-8")
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    rc = CJ.paper_report(["--paper-report", "--verify"])
                code = {"missing": "PAPER_LIST_MISSING", "stale": "PAPER_LIST_STALE",
                        "match": "PAPER_LIST_MATCH"}[mode]
                self.assertEqual(rc, 0 if mode == "match" else 1,
                                 "%s 分支退出码不对（%s）：%s" % (mode, rc, buf.getvalue()[:200]))
                self.assertIn("[%s]" % code, buf.getvalue(),
                              "%s 分支没打预期的短码：%s" % (mode, buf.getvalue()[:200]))
                out.append((code, buf.getvalue().strip()))
        finally:
            PS.OUT_REL = real_rel
            if (ROOT / ghost).is_file():
                (ROOT / ghost).unlink()
        return out

    # ---- ② 短码表与实发短码互印 -------------------------------------------
    def test_documented_codes_and_emitted_codes_match(self):
        doc = docstring_codes()
        self.assertGreaterEqual(len(doc), 12,
                                "短码表只剩 %d 条（%s）—— 判据改过名而表没跟上"
                                % (len(doc), sorted(doc)))
        emitted = set()
        for _code, text in CITE_SAMPLES:
            first = CJ.scan_lines([text], "docs/p.md")[2][0]
            emitted |= {c for c in codes_in(first[:24])}
        for code, _msg in self.rowset_msgs():
            emitted.add(code.strip("[]"))
        old = CJ.scan_docs
        try:
            CJ.scan_docs = lambda: (1, 1, ["[CITE_NOFILE] docs/p.md:9 x | fix: y"], 1, 0)
            for line in CJ.render().split("\n"):
                emitted |= codes_in(line[:28])
        finally:
            CJ.scan_docs = old
        for _code, text in self.paper_branch_texts():
            emitted |= codes_in(text[:30])
        self.assertEqual(emitted - doc, set(),
                         "这些短码发得出来却没有解释（等于暗号）：%s" % sorted(emitted - doc))
        self.assertEqual(doc - emitted, set(),
                         "表里解释了却从没被发出（代码早换叫法了）：%s" % sorted(doc - emitted))

    # ---- 真·弄红一次，走一遍真的子进程通道 --------------------------------
    def test_a_real_red_run_keeps_the_actionable_parts(self):
        out = ROOT / PS.OUT_REL
        original = out.read_bytes()
        try:
            perturbed = original.replace("撤除动作从未到达论文".encode("utf-8"),
                                         "撤除动作已经到达论文".encode("utf-8"), 1)
            self.assertNotEqual(perturbed, original, "扰动没改到字节，这条是空转")
            out.write_bytes(perturbed)
            pr = subprocess.run([sys.executable, str(ROOT / "console" / "_citations.py"),
                                 "--paper-report", "--verify"], cwd=str(ROOT),
                                capture_output=True)
        finally:
            out.write_bytes(original)
        self.assertEqual(pr.returncode, 1, "清单改了字却不红，后面都白测")
        raw = pr.stdout
        utf8 = raw.decode("utf-8", "replace")
        self.assertIn("[FAIL][PAPER_LIST_STALE]", utf8)
        self.assertTrue(any(ord(ch) > 127 for ch in utf8),
                        "输出本来就没中文，「掉色」这一步无从谈起 —— 用例空转")
        faded = raw.decode("cp1252", "replace")
        self.assertNotIn("论文改了没重生成", faded, "这条模拟没把中文打坏，判据要更严")
        self.assertIn("[FAIL][PAPER_LIST_STALE]", faded)
        self.assertIn("console/_citations.py --paper-report --write", faded)
        self.assertEqual(out.read_bytes(), original, "还原失败会留下一份假清单")


if __name__ == "__main__":
    unittest.main()
