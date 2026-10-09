# -*- coding: utf-8 -*-
"""硬边界证人：`frontend/drone.py` 三段的**语义锚点**校验（不吃绝对行号）。

## 为什么要有这个文件（本仓第三次被同一件事咬）
上位硬边界写的是"`drone.py` 三段不得改"，历史上它一直用**绝对行号**表达
（`:328-331` / `:342-343` / `:362-366`）。实测代价：本轮往同文件别处加注释把三段整体下推 5 行 ⇒
① 所有按行号的文档引用被 `_citations` 判 ANCHOR_MISS；② 更糟的是**边界本身看起来像被违反了**
（旧行号取出的 sha 不同），要靠人工比对才分得清"挪了"和"改了"。
⇒ 主控裁定 (一)：行号漂移算合规（AST 剥 docstring 同 sha 是语义未变的证人），并令
   **"这三段以后改用锚点/符号名引用，别继续依赖绝对行号"**。本文件就是那条令的实现。

## 判据形状（不是发明，是照抄 #69-C6 6-A 已验证过的锚定方式）
每段 = 一个**符号锚**（在所属函数体内第 n 处匹配）+ 该段的**首末行原文**。三条同时成立才算"这一段还在原位"：
  A1 锚能在盘上唯一确定地找到（找不到 ⇒ `[SEG_ANCHOR_LOST]`）
  A2 锚所在函数的**源码文本逐字等于登记的首末行**（不等 ⇒ `[SEG_BODY_CHANGED]` = 真改了）
  A3 登记时一并印出该段当前的**真实行号 + sha256[:12]** ⇒ 行号只作可读信息，不作判据
⇒ 于是"加了别的注释导致整段下移"永远不红；"这段本身被人改了"永远红。这正是边界本意。

短码：[SEG_ANCHOR_LOST] / [SEG_BODY_CHANGED] / [SEG_BLIND] / [SEG_COUNT]
退出码：任一段锚丢或体变 = 1。参与 discover（常驻门）。
"""
from __future__ import annotations

import ast
import hashlib
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = "frontend/drone.py"

#: 三段的锚定定义。**lines 是"必须都在该函数体内出现、且顺序不变"的行**（中间允许有注释行，
#:   所以不要求物理相邻 —— pop 段那两行之间就夹着 D-iv 的说明注释）。anchor = 首行；
#:   其余行必须在 anchor 之后、同一函数体内按序命中，否则判 `[SEG_BODY_CHANGED]`。
#: 为什么不写行号：见模块 docstring。为什么逐字比：A2 要吃的是"这段没被人动过"，
#:   只锚"函数里有这么一行"就退化成存在性检查，改半个表达式照样绿。
SEGMENTS = (
    {
        "name": "pop_point",
        "why": "执行器真正消费航点的唯一离散事件点（#69-H3 D-iv 的承重位置）",
        "enclosing": "update",
        "lines": (
            "_popped = self.scheduled_position.pop(0)",
            "self.consumed_waypoints_this_step.append(_popped)",
        ),
    },
    {
        "name": "free_and_load_reset",
        "why": "任务完成后置空闲 + 载重归零（#69-C2b/C3 审计的对象）",
        "enclosing": "update",
        "lines": (
            "self.is_free = True",
            "self.current_load = 0  # 任务完成，卸货",
            "self.executing_task_id = None  # 清除执行中任务ID",
        ),
    },
    {
        "name": "single_step_displacement",
        "why": "单步直线位移（E1/E2 分界：风不得进运动学）",
        "enclosing": "update",
        "lines": (
            "actual_distance = max_distance",
            "self.x += (dx / distance) * actual_distance",
        ),
    },
)


def _func_source_lines(path: pathlib.Path, func_name: str):
    """返回 [(lineno, text)] —— 该名字对应的**函数体**源码行（同名多处则全部并入）。"""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            lo = getattr(node, "lineno", 0)
            hi = getattr(node, "end_lineno", lo)
            out.extend((i, l) for i, l in enumerate(src.splitlines()[lo - 1:hi], start=lo))
    return out


def _locate(path: pathlib.Path, seg):
    """按**整段序列**定位 -> (anchor_lineno, [(lineno, text)...]) ；命中数≠1 即抛 AssertionError。

    ⚠ 锚必须吃"完整的行序列"，不能吃单行：`self.is_free = True` 在 `update()` 内实测有**两处**
      （`:286` 恢复挂起航线那支、`:347` 任务完成那支），单行锚会命中 2 处而让本门永远红 ——
      那不是放宽判据的理由，是我第一版把锚写弱了。
    ⚠ "允许中间夹行"**只容空行与注释行**。第一版写成"一直往后找直到匹配"，于是从 :286 那处
      出发可以跨过 60 行业务代码匹到 :348 ⇒ 同一个锚又命中 2 次，而且更糟的是：**那种写法
      会把"两行之间被插进新代码"也判成通过**（正是硬边界要拦的事）。现在遇到任何非空非注释行
      即断开，所以段中插入代码 ⇒ 该处不匹配。
    比对用 strip() 后的文本 ⇒ **缩进变化不算改动**；跨 if/else 分支不可能匹上（中间必有代码行）。
    """
    body = dict(_func_source_lines(path, seg["enclosing"]))
    want = [w.strip() for w in seg["lines"]]
    maxl = max(body) if body else 0

    def _filler(lineno):
        t = body.get(lineno, "").strip()
        return t == "" or t.startswith("#")

    hits = []
    for start in sorted(body):
        if body[start].strip() != want[0]:
            continue
        cur, seq, ok = start, [start], True
        for w in want[1:]:
            nxt = cur + 1
            while nxt <= maxl and _filler(nxt):
                nxt += 1                     # 只跳过空行/整行注释
            if nxt > maxl or body[nxt].strip() != w:
                ok = False
                break
            cur = nxt
            seq.append(cur)
        if ok:
            hits.append(seq)
    if len(hits) != 1:
        raise AssertionError(
            "[SEG_ANCHOR_LOST] `%s` 的序列锚在 %s() 内命中 %d 处（应为恰好 1）⇒ "
            "该段被改名/复制/删除，硬边界的证人位置已不可识别，须人来定性而不是放宽" % (
                seg["name"], seg["enclosing"], len(hits)))
    return hits[0][0], [(l, body[l]) for l in hits[0]]


class DroneBoundarySegments(unittest.TestCase):
    def test_A_each_segment_body_is_verbatim(self):
        """A1+A2：三段必须能按锚唯一定位，且其原文逐字未变。行号漂不算红。"""
        p = ROOT / TARGET
        self.assertTrue(p.is_file(), "[SEG_BLIND] %s 不存在 ⇒ 无从核对边界" % TARGET)
        report = []
        for seg in SEGMENTS:
            a, seq = _locate(p, seg)
            sha = hashlib.sha256("\n".join(t for _l, t in seq).encode("utf-8")).hexdigest()[:12]
            report.append("%s@%d-%d=%s" % (seg["name"], a, seq[-1][0], sha))
        print("[SEG_VERDICT] segments_checked=%d anchors_with_line_numbers=%s "
              "exit_criterion=(each anchor unique) and (body verbatim) —— 行号只印不判" % (
                  len(SEGMENTS), ";".join(report)))

    def test_B_anchor_set_is_three_and_named(self):
        """分母自证：三段都得在册，少一段就是有人悄悄缩小了保护范围。"""
        names = sorted(s["name"] for s in SEGMENTS)
        self.assertEqual(names, sorted(["free_and_load_reset", "pop_point", "single_step_displacement"]),
                         "[SEG_COUNT] 登记的三段变了：%s ⇒ 增删段属另一类授权，不许顺手改这张表" % names)
        for s in SEGMENTS:
            self.assertGreaterEqual(len(s["lines"]), 2,
                                    "[SEG_BLIND] %s 只登记 1 行 ⇒ 锚点太弱，会被无关代码撞中" % s["name"])
        print("[SEG_COUNT] segments=%d each_min_lines=2 exit_criterion=(segments==3)" % len(SEGMENTS))

    def test_C_line_numbers_are_not_used_as_verdict(self):
        """判别式：证明本门**不吃行号**。构造一份"整段下移 5 行"的副本，A 面必须仍判通过。

        这是要求 (一) 的直接证人：如果哪天有人又把本门改成按行号比，这条会先红。
        """
        p = ROOT / TARGET
        src = p.read_text(encoding="utf-8").splitlines()
        shifted = ["# pad comment line"] * 5 + src          # 整体下移 5 行，内容一字不动
        tmp = ROOT / "frontend" / "_seg_shift_probe_tmp.txt"  # .txt：避开 discover/glob，又能被本函数读
        try:
            tmp.write_text("\n".join(shifted), encoding="utf-8")
            moved, orig = {}, {}
            for seg in SEGMENTS:
                _a, seq = _locate(tmp, seg)                 # 走的是**同一个**定位函数，不另写一份
                moved[seg["name"]] = _a
                self.assertEqual([t.strip() for _l, t in seq], [w.strip() for w in seg["lines"]],
                                 "[SEG_BLIND] 副本里 `%s` 的逐字比对失败 ⇒ 下移影响了比对，锚吃了位置" % seg["name"])
                o_a, _o = _locate(p, seg)
                orig[seg["name"]] = o_a
            self.assertTrue(all(moved[n] == orig[n] + 5 for n in orig),
                            "[SEG_BLIND] 下移 5 行后锚号没跟着动（%s vs %s）⇒ 定位另有蹊跷" % (moved, orig))
            print("[SEG_LINEFREE] original=%s shifted_by_5=%s exit_criterion=(all shifted==orig+5) "
                    "⇒ 锚随内容走、不随行号走" % (
                        ",".join("%d" % orig[s["name"]] for s in SEGMENTS),
                        ",".join("%d" % moved[s["name"]] for s in SEGMENTS)))
        finally:
            tmp.unlink()
            left = [f.name for f in (ROOT / "frontend").glob("_seg_shift_probe_tmp*")]
            self.assertEqual(left, [], "[SEG_TEAR_DOWN] 临时副本没清掉：%s" % left)


if __name__ == "__main__":
    unittest.main()
