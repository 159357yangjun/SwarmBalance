# -*- coding: utf-8 -*-
"""A2 那两个死字段的现状门 —— 它不替用户做决定，它保证"决定还没做"这件事不会悄悄过期。

为什么要有这条（而不是只在登记表写一段话）：待批记录一旦写下，代码是可以自己变的 ——
有人把键接上、有人把键删掉、有人把记录删了却没改代码，三种情况都不会有东西报警。
这条用例把三件事钉住：
1. **现状**：两个键各自只有 1 处定义、0 个写入点、0 个读取点、0 处导出（键名不在任何指标名单里）。
2. **记录与现状同生共死**：`docs/数据来源与可追溯性登记表.md` 里必须留着 awaiting-user 那一节
   与两个带锚点的行号引用；删了字段却不撤记录 ⇒ 红（第 1 条先红），撤了记录但字段还在 ⇒ 也红。
3. **判据不是摆设**：同一套分类函数喂一份"有人读"的夹具，必须把它判成活键（两面夹具）。

扫描**范围下限**是 `MIN_PY`：只数到很少的 .py 说明扫描器瞎了，那一条红比不红更贵。
"""
from __future__ import annotations

import io
import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "数据来源与可追溯性登记表.md"
ENV = ROOT / "frontend" / "environment.py"
# 键名拼出来，免得本文件自己变成一处"读取点"
NAMES = ["total_charging_" + s for s in ("energy", "sessions")]
# 只算代码类文件：登记簿与 CHANGELOG 里当然写着这两个词，那不是"有人在读"
CODE_EXT = (".py", ".js", ".html", ".vue", ".json", ".yaml", ".yml")
SKIP_DIR = ("__pycache__", ".git", "node_modules", ".wt", "adhoc")
MIN_PY = 60


def _w(path, text):
    """写文件并确保句柄关闭：漏了就是一条 `ResourceWarning`，而 `warnings="default"` 一开它就会冒出来。"""
    Path(path).write_text(text, encoding="utf-8")


def code_files(root=ROOT):
    out = []
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR]
        for f in filenames:
            if f.endswith(CODE_EXT):
                out.append(os.path.join(dirpath, f))
    return sorted(out)


def classify(name, files):
    """把某名字在代码里的出现分成 定义 / 写入 / 读取 / 导出 四桶。"""
    d = {"def_": [], "write": [], "read": [], "export": []}
    pat = re.compile(r"\b%s\b" % re.escape(name))
    for p in files:
        try:
            text = Path(p).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for ln, line in enumerate(text.split("\n"), 1):
            if not pat.search(line):
                continue
            # Windows runner may place TEMP on C: while checkout lives on D:.
            # Only in-repo files have a meaningful repo-relative path.
            src = Path(p).resolve()
            try:
                rel = src.relative_to(ROOT.resolve()).as_posix()
            except ValueError:
                rel = src.as_posix()
            if re.search(r"self\.%s\s*=\s*(0\.0|0)\b" % re.escape(name), line):
                d["def_"].append("%s:%d" % (rel, ln))
            elif re.search(r"self\.%s\s*(\+=|-=|=)" % re.escape(name), line):
                d["write"].append("%s:%d" % (rel, ln))
            elif re.search(r"['\"]%s['\"]" % re.escape(name), line):
                d["export"].append("%s:%d" % (rel, ln))
            else:
                d["read"].append("%s:%d" % (rel, ln))
    return d


class DeadChargingFieldTests(unittest.TestCase):

    def setUp(self):
        self.files = code_files()
        self.py_count = len([f for f in self.files if f.endswith(".py")])
        self.assertGreaterEqual(self.py_count, MIN_PY,
                                "只扫到 %d 个 .py —— 扫描范围塌了，这条用例不作数" % self.py_count)

    def test_both_fields_are_definition_only(self):
        """现状：各 1 处定义、0 写入、0 读取、0 导出。"""
        for name in NAMES:
            c = classify(name, self.files)
            print("[DEAD_FIELD] name=%s defs=%d writers=%d readers=%d exports=%d 定义处=%s "
                  "(扫到 %d 个 .py)"
                  % (name, len(c["def_"]), len(c["write"]), len(c["read"]),
                     len(c["export"]), c["def_"], self.py_count))
            self.assertEqual(len(c["def_"]), 1,
                             "%s 的定义处应有 1 行，现在 %s —— 记录里的行号要跟着改"
                             % (name, c["def_"]))
            self.assertEqual(c["write"], [], "%s 出现了写入点：%s —— 它不再是死键，A2 要重开"
                             % (name, c["write"]))
            self.assertEqual(c["read"], [], "%s 出现了读取点：%s —— 删它会改行为，不再是零风险"
                             % (name, c["read"]))
            self.assertEqual(c["export"], [], "%s 出现在指标名单/字符串键里：%s —— 那属对外口径"
                             % (name, c["export"]))

    def _line_of(self, name):
        """按内容定位定义行，不写死行号。

        原先这里硬编 (295, 296)：本轮把 `high_buildings` 那行抽成方法（environment.py:178→
        `_recompute_high_buildings`）使文件行数变化，两行一起漂 ⇒ 本门红。
        **为了让计数消失而发明判据**是不干的；但行号本来就不该由人抄 —— 它唯一的真源是文件本身。
        现在改成"从源码里查这个属性在哪行被赋值"，漂了会自动跟，且仍能被内容核对证伪。
        """
        lines = ENV.read_text(encoding="utf-8").split("\n")
        hits = [i + 1 for i, l in enumerate(lines) if ("self.%s =" % name) in l]
        self.assertEqual(len(hits), 1,
                         "%s 的定义行应为 1 处，实得 %s：%r ⇒ 内容定位失效，不许猜行号" % (
                             name, hits, [lines[h - 1][:40] for h in hits]))
        return hits[0]

    def test_ledger_still_holds_the_awaiting_user_record(self):
        """记录必须在，且带着两个可被引用门禁翻开的行号锚点。"""
        text = LEDGER.read_text(encoding="utf-8")
        self.assertIn("awaiting-user", text,
                      "A2 的待批记录不见了 —— 决定做了就改写它，别直接删掉这一段")
        # 这两个断言串也用拼出来的名字：写全名的话，本文件就成了那个键的一处"读取点"
        want = [self._line_of(n) for n in NAMES]
        for ln, name in zip(want, NAMES):
            anchor = "frontend/environment.py:%d#%s" % (ln, name)
            self.assertIn(anchor, text,
                          "M10 缺了引用 %s —— 引用门禁扫不到它，行号漂也没人报警" % anchor)
        for key in ("选「删」的后果", "选「不删」的后果"):
            self.assertIn(key, text, "待批记录缺了 `%s` —— 只给一边等于替用户做了决定" % key)

    def test_classifier_is_not_vacuous(self):
        """两面夹具：同一个分类函数必须能把"有人读的键"判成活键。

        没有这一条，上面那些 `== []` 断言可能只是因为我那正则谁都不匹配。
        """
        d = os.path.join(os.environ.get("TEMP", "/tmp"), "deadfield-fixture")
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "mini.py")
        nm = NAMES[0]          # 拼出来，别在本文件里留下那个全名的字面量（否则我就在数自己）
        _w(p,
            "class E:\n"
            "    def __init__(self):\n"
            "        self.%s = 0.0\n"
            "        self.%s += 5\n"
            "        return self.%s * 2\n"
            "SCHEMA = ['%s']\n" % (nm, nm, nm, nm))
        c = classify(nm, [p])
        self.assertEqual(len(c["def_"]), 1, c)
        self.assertEqual(len(c["write"]), 1, "写入点没被认出来：%s" % c)
        self.assertEqual(len(c["read"]), 1, "读取点没被认出来：%s" % c)
        self.assertEqual(len(c["export"]), 1, "字符串键没被认出来：%s" % c)
        os.remove(p)

    def test_definition_lines_match_the_cited_anchors(self):
        """记录里写的行号必须真是那两行 —— 行号漂了引用门禁会红，这里再补一层内容核对。"""
        lines = ENV.read_text(encoding="utf-8").split("\n")
        for name in NAMES:
            ln = self._line_of(name)
            self.assertIn(name, lines[ln - 1],
                          "%s 已不在 environment.py:%d，那一行的原文是 %r —— 记录与锚点都要改"
                          % (name, ln, lines[ln - 1][:60]))


if __name__ == "__main__":
    unittest.main()
