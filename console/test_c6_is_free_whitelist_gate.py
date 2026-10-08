# -*- coding: utf-8 -*-
"""#69-C6 加固：`is_free = True` 赋值点白名单结构门（结项报告 §6-A 落地）。

本门只覆盖 #69-C6 缺口分析的 **§6-A（守得住的那半）**；§6-B（is_free 语义归属，无可读取状态⇒守不住）
的判据与理由**唯一版本在 docs/#69_结项报告.md §6-B**，此处不复述，以免两处措辞分叉。

为什么这半守得住：可达性的**前提**是"存在一个把机子置为可接单的赋值点"，这类赋值点有限且可静态枚举。
所以期望值写成**白名单集合相等**，不是"抓到违规样本"——现场没有违规时它照样会红（多一个赋值点即红）。
这正是 #69-C3/C5 判为首要残余盲区的那一半。

⚠ 定位用 `符号名 + 同函数内第几处`，不用裸行号：本会话两次被"生产代码挪行→引用失效"咬到
   （citation 门 14→12→1 条 ANCHOR_MISS）。行号只作读数打印，不参与判定。

两面注入（给牙；都在**临时副本**上跑 ⇒ 生产文件零改动）：
    ADD —— 副本里多一处 is_free=True ⇒ 必须冒出白名单外的新键
    DEL —— 副本里抹掉一处        ⇒ 必须有一个既有键消失
另有一面防量具失明：census 自身必须 ≥4 命中，否则 [C6_BLIND]。

动态 free_with_assignment 不变量的定位：**第二证人，不得升为主门**（论证同见报告 §6-A-2，此处不另写一版）。

短码：[C6_BLIND] / [C6_WHITELIST_DRIFT] / [C6_NO_REASON] / [C6_INJECT_NOT_CAUGHT]
退出码：漂移或量具瞎=1。参与 discover（常驻门）。
"""
from __future__ import annotations
import os, pathlib, re, shutil, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: 受检文件（生产代码；测试文件里的 is_free 赋值不算，那是夹具搭状态）。
SCANNED = ["frontend/drone.py", "frontend/environment.py"]

#: 白名单：(文件, 符号标签) → 「它为什么合法」一句理由。**无理由即算违规**。
WHITELIST = {
    ("frontend/drone.py", "__init__"):
        "构造初值：新机未派单本就可接单，是唯一合法的 True 起点",
    ("frontend/drone.py", "update"):
        "换电完成且无挂起航线(_suspended_route 为空)才置真；有挂起任务时同函数另一分支置假，"
        "故此刻确实无待办服务，Q2 成立",
    ("frontend/drone.py", "update#2"):
        "scheduled_position 被 pop 空后(最后一个航点已被执行器消费)才置真，与 dest-pop 同帧，"
        "assignment 已在 environment 侧移除，不会留下 is_free 且 assignment 并存",
    ("frontend/environment.py", "set_drone_out_of_service"):
        "故障注入复位：同一函数内先 drone_assignments.pop(idx) 摘走并回队任务，再置 is_free=True，"
        "故置真时该机已无 assignment",
}

_ASSIGN = re.compile(r"^\s*(?:self|drone|d|[a-z_]+)\.is_free\s*=\s*True\b")
_DEF = re.compile(r"^\s*(?:def|class)\s+(\w+)")


def _enclosing_name(lines, idx):
    """往上找最近的 def/class 名（不依赖行号常量）。"""
    for i in range(idx, -1, -1):
        m = _DEF.match(lines[i])
        if m:
            return m.group(1)
    return "?"


def census(path, rel=None):
    """-> [(lineno, (relpath, symbol_tag))]；symbol_tag = 'fn' 或 'fn#nth'（同函数内第 n 处）。

    rel 显式传入 ⇒ 扫临时副本时不必 relative_to(ROOT)。
    """
    if rel is None:
        rel = path.relative_to(ROOT).as_posix()
    lines = path.read_text(encoding="utf-8").splitlines()
    hits = []
    per_scope = {}
    for idx, text in enumerate(lines):
        if not _ASSIGN.match(text):
            continue
        name = _enclosing_name(lines, idx)
        per_scope[name] = per_scope.get(name, 0) + 1
        tag = name if per_scope[name] == 1 else "%s#%d" % (name, per_scope[name])
        hits.append((idx + 1, (rel, tag)))
    return hits


def current_set():
    got = {}
    for rel in SCANNED:
        p = ROOT / rel
        if not p.is_file():
            continue
        for ln, key in census(p, rel):
            got.setdefault(key, []).append(ln)
    return got


class IsFreeAssignmentWhitelist(unittest.TestCase):
    def test_A_census_is_not_blind(self):
        """量具自检：至少扫到 4 处，否则是本正则失明而非现场真的干净。"""
        got = current_set()
        self.assertGreaterEqual(len(got), 4,
                                "[C6_BLIND] 只扫到 %d 处 is_free=True 赋值 ⇒ 匹配式失效，"
                                "下面那句'白名单相符'不可信" % len(got))

    def test_B_whitelist_exact_equality(self):
        """核心断言：赋值点集合 == 白名单（多一个少一个都红）。期望值是集合本身，不依赖违规样本。"""
        got = current_set()
        extra = sorted(set(got) - set(WHITELIST))
        missing = sorted(set(WHITELIST) - set(got))
        for (rel, sym), lns in sorted(got.items()):
            print("[C6_SITE] %-24s %-28s line=%s" % (rel, sym, ",".join(map(str, lns))))
        self.assertEqual([], extra,
                         "[C6_WHITELIST_DRIFT] 新增 is_free=True 赋值点未登记理由：%s ⇒ cleanup "
                         "可达性前提可能被重新打开，须补语义审查后才可入表" % extra)
        self.assertEqual([], missing,
                         "[C6_WHITELIST_DRIFT] 白名单条目已不存在：%s ⇒ 更新表而不是留僵尸豁免" % missing)

    def test_C_every_entry_must_have_a_reason(self):
        """无理由即算违规（沿用 C4 豁免表那套形状，不另建机制）。"""
        no_reason = [k for k, v in WHITELIST.items() if not str(v).strip()]
        self.assertEqual([], no_reason, "[C6_NO_REASON] 这些白名单项没有理由：%s" % no_reason)
        short = [k for k, v in WHITELIST.items() if len(str(v).strip()) < 12]
        self.assertEqual([], short, "[C6_NO_REASON] 理由过短(<12字)等于没写：%s" % short)

    def test_D_inject_faces_have_teeth(self):
        """ADD/DEL 两面都在临时副本上跑 ⇒ 生产文件零改动，同时证明门真的会红。"""
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="c6inj_"))
        try:
            drone_path = ROOT / "frontend" / "drone.py"
            src = drone_path.read_text(encoding="utf-8")

            # ---- ADD 面：副本里多一处赋值 ⇒ 必须冒出白名单外的新键 ----
            copy_add = tmp / "drone_add.py"
            copy_add.write_text(src + "\n\ndef _c6_probe(d):\n    d.is_free = True\n", encoding="utf-8")
            baseline = {k for _, k in census(drone_path, rel="frontend/drone.py")}
            after_add = {k for _, k in census(copy_add, rel="frontend/drone.py")}
            fresh = after_add - baseline
            self.assertTrue(fresh, "[C6_INJECT_NOT_CAUGHT] ADD 面：注入的赋值点没被扫到 ⇒ 门无牙")
            unlisted = sorted(fresh - set(WHITELIST))
            self.assertTrue(unlisted,
                            "[C6_INJECT_NOT_CAUGHT] ADD 面：注入点被归进了既有白名单 ⇒ test_B 不会因它红，"
                            "门等于摆设（fresh=%s）" % sorted(fresh))

            # ---- DEL 面：副本里抹掉一处 ⇒ 必须有一个既有键消失 ----
            env_path = ROOT / "frontend" / "environment.py"
            env_src = env_path.read_text(encoding="utf-8")
            needle = "            drone.is_free = True\n"
            self.assertIn(needle, env_src, "[C6_BLIND] DEL 面：找不到待抹语句，注入无从构造")
            copy_del = tmp / "environment_del.py"
            copy_del.write_text(env_src.replace(needle, "            drone.is_free = False\n", 1),
                                encoding="utf-8")
            before = {k for _, k in census(env_path, rel="frontend/environment.py")}
            after = {k for _, k in census(copy_del, rel="frontend/environment.py")}
            gone = before - after
            self.assertTrue(gone, "[C6_INJECT_NOT_CAUGHT] DEL 面：删掉赋值点后集合没变小 ⇒ 门无牙")
            print("[C6_TEETH] ADD 新增键=%s | DEL 失去键=%s" % (sorted(fresh), sorted(gone)))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
