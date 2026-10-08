# -*- coding: utf-8 -*-
"""#69-C4 加固②：扫描门 —— 禁止新代码拿 `current_load` 与阈值比较当"机上有没有货"的真值。

规则来源（#69-C3 审计，docs/C3_state_field_audit.md）：`add_load` 在**派单时刻**就被调用
（environment.py:1109/1121/1818），所以 `current_load` 表示"已指派重量"而非"机上物理有货"；
把它当载货真值会让"飞往取货点"那段被误判带货 ⇒ 空载率被低估。载货真值的唯一合法证人
是航线形状（`_is_carrying`, environment.py:1741）。本门把这条人工结论变成机器守住的结论。

本轮基线读数（先原样跑一次、如实报，不为计数归零而发明判据）：
    现存命中 = 2 处，**违规 = 0** ⇒ **此门是预防性的**。两处均登记豁免且带理由：
      frontend/environment.py:1751   LEGIT：`_is_carrying` 内部把 load<=1e-9 当**下界短路**
                                    （没派过货直接返回 False），随后仍按航线标签定夺，
                                    不是拿它当载货真值。
      console/test_c4_is_carrying_discriminator.py:82  LEGIT：变异面**故意**构造的退化写法
                                    （lambda bad），用来证明加固①的夹具会咬；扫它会自杀。

判别式两面（缺一即是一扇只会绿的门）：
    clean 面 —— 扫真仓库：hits == exempt ⇒ 退码 0（绿）
    dirty 面 —— 喂一段含违规的代码样本 ⇒ 必须红并具名报出该行
短码：[C4_SCAN_VIOLATION] / [C4_SCAN_BLIND] / [C4_EXEMPT_STALE] / [C4_DIRTY_NOT_CAUGHT]
退出码：违规或量具瞎 ⇒ 1；否则 0。参与 discover（常驻门）。
"""
from __future__ import annotations
import os, pathlib, re, sys, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCAN_ROOTS = ["frontend", "console", "experiments", "backend_si", "greedy"]

#: 命中式：current_load 与"数值阈值比较"出现在同一行代码里（两个方向都抓）。
#: 说明：本仓两处合法写法都是 `float(getattr(d,'current_load',0.0)) <= 1e-9 / > 0`，
#: 属性名与运算符之间隔着 `, 0.0 ) )`，所以 gap 必须允许逗号/括号/数字常量。
#: 这不是"越宽越好"——过宽会把 `current_load + task_weight > capacity`（env:1065，容量算术，合法）
#: 也扫进来；因此额外要求：**比较右侧必须是裸数值阈值（0 / 0.0 / 1e-9）**，容量比较的右值是变量/表达式，不会被抓。
#: 正向：运算符后面跟裸零阈值（`current_load > 0`）。
_NUMCMP = re.compile(r"(?:>|<|>=|<=|!=|==)\s*(?:0\.0|0|1e-9|1e-12|1e-6)\b")
#: 反向：裸零阈值在前、运算符在后（`0 == current_load`、`0 < drone.current_load`）。
_NUMCMP_REV = re.compile(r"\b(?:0\.0|0|1e-9|1e-12|1e-6)\s*(?:>|<|>=|<=|!=|==)")


def _is_cargo_truth_test(code):
    """判定一行重建代码是否"拿 current_load 跟裸零阈值比"（两种书写顺序都抓）。"""
    if "current_load" not in code:
        return False
    # 正向：`... current_load ... > 0`
    for m in _NUMCMP.finditer(code):
        left = code[:m.start()]
        if re.search(r"current_load[^<>!=]*$", left):
            return True
    # 反向：`0 == ... current_load ...`
    for m in _NUMCMP_REV.finditer(code):
        right = code[m.end():]
        if re.match(r"\s*[^<>!=]*current_load", right):
            return True
    return False

#: 豁免表：path → {lineno → 理由}。**无理由不得进表**（无条目即视为违规）。
EXEMPT = {
    "frontend/environment.py": {
        1751: "_is_carrying 内部把 load<=1e-9 当下界短路，随后仍按航线标签定夺；非载货真值",
    },
    "console/test_c4_is_carrying_discriminator.py": {
        82: "变异面故意构造的退化写法（lambda bad），用于证明加固①夹具会咬；扫它等于自杀",
    },
}


def _iter_py_files():
    for sub in SCAN_ROOTS:
        base = ROOT / sub
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fn in filenames:
                if fn.endswith(".py"):
                    yield pathlib.Path(dirpath) / fn


def _code_lines(path):
    """用 Python 自己的 tokenize 把"可执行代码"与注释/文档字符串分开。

    为什么不用行级正则：本仓的反例大量出现在 docstring 与报错文案里（第一版实测造出 7 条假违规、
    6 条是散文 ⇒ 那是量具瞎，不是现场有）。
    为什么不能整串丢掉 STRING：`getattr(drone, 'current_load', 0.0) > 0` 这类写法把属性名放在
    **字符串**里，丢掉 STRING 会让门对本仓最常见的访问方式失明（第二版就因此扫不到 env:1751）。
    折中：STRING 保留其内容参与匹配，但只认"内容等于 current_load 的标识符字面量"；
    其余字符串（docstring/文案）不参与匹配 —— 靠 PATTERN 要求 current_load 与数字相邻来保证。
    返回 {lineno: "重建的代码文本"}。
    """
    import io, tokenize
    try:
        src = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return {}
    out = {}
    for tok in toks:
        if tok.type in (tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                        tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING):
            continue
        if tok.type == tokenize.STRING:
            inner = tok.string.strip("\"'")
            # 只有恰为属性名的字面量才当代码参与判定；docstring/长文案走 else 丢弃
            if inner in ("current_load", "payload_at_reach"):
                parts = out.setdefault(tok.start[0], [])
                parts.append(inner)
            continue
        out.setdefault(tok.start[0], []).append(tok.string)
    return {ln: " ".join(parts) for ln, parts in out.items()}


def scan(files=None):
    """-> (hits, violations)；hit=(relpath, lineno, text)。violations = hits - exempt。"""
    hits, violations = [], []
    for path in (files if files is not None else _iter_py_files()):
        try:
            rel = path.relative_to(ROOT).as_posix()
        except ValueError:
            rel = str(path)
        raw = {}
        try:
            raw = {i: l for i, l in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)}
        except (OSError, UnicodeDecodeError):
            continue
        for ln, code in _code_lines(path).items():
            if _is_cargo_truth_test(code):
                hits.append((rel, ln, raw.get(ln, code).strip()[:90]))
                reason = EXEMPT.get(rel, {}).get(ln)
                if reason is None:
                    violations.append((rel, ln, raw.get(ln, code).strip()[:90]))
    return hits, violations


class CargoTruthScanGate(unittest.TestCase):
    def test_clean_face_repo_has_no_violation(self):
        hits, violations = scan()
        self.assertGreater(len(hits), 0,
                           "[C4_SCAN_BLIND] 一条命中都没有 ⇒ 扫描器或模式失效；"
                           "已知至少应有 environment.py:1751 与变异面")
        print("[C4_SCAN_BASELINE] hits=%d exempt=%d violations=%d（本轮判：预防性门，零违规）" % (
            len(hits), len(hits) - len(violations), len(violations)))
        for rel, ln, txt in violations:
            print("  [C4_SCAN_VIOLATION] %s:%d | %s" % (rel, ln, txt))
        self.assertEqual(violations, [],
                         "[C4_SCAN_VIOLATION] %d 处把 current_load 与阈值比较当载货真值且无豁免理由"
                         % len(violations))

    def test_exempt_entries_are_not_stale(self):
        """豁免项必须真的还能扫到——条目还在表里却扫不到 ⇒ 该豁免已过期，要删。"""
        hits, _ = scan()
        seen = {(rel, ln) for rel, ln, _ in hits}
        stale = [(rel, ln) for rel, d in EXEMPT.items() for ln in d if (rel, ln) not in seen]
        self.assertEqual(stale, [],
                         "[C4_EXEMPT_STALE] 这些豁免行已扫不到，请从表里删除：%s" % stale)

    def test_detector_shape_specificity(self):
        """检测器自身的两面：该命中的必须命中，不该命中的（容量算术）绝不能命中。

        没有这一面，"零违规"可能只是检测器太窄；有了它，零违规才说明现场确实干净。
        """
        must_hit = [
            "if float(getattr(drone, 'current_load', 0.0)) <= 1e-9:",
            "bad = lambda d: float(getattr(d, 'current_load', 0.0)) > 0",
            "return self.current_load > 0",
            "if 0 == drone.current_load:",
        ]
        must_not_hit = [
            # env:1065 的容量算术：右值是变量/表达式，不是裸零阈值 ⇒ 合法
            "planned_total_weight = float(drone.current_load) + float(task_to_assign.get_weight())",
            "if planned_total_weight > MAX_MULTI_TASK_TOTAL_WEIGHT:",
            # env:1797 的比值：不是与零比较
            "load_ratio = min(1.0, float(drone.current_load) / float(drone.carrying_capacity))",
        ]
        for s in must_hit:
            self.assertTrue(_is_cargo_truth_test(s), "[C4_SCAN_BLIND] 应命中却漏：%s" % s)
        for s in must_not_hit:
            self.assertFalse(_is_cargo_truth_test(s), "[C4_SCAN_OVERREACH] 容量算术被误判：%s" % s)

    def test_dirty_face_catches_a_real_violation(self):
        """红面：写一段含违规用法的临时文件，扫描必须抓到并具名。"""
        import tempfile
        src = (
            "class Fake:\n"
            "    current_load = 3.0\n"
            "    def has_cargo(self):\n"
            "        return self.current_load > 0   # BAD: 派单即置重，不是机上货物\n"
        )
        tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="c4dirty_"))
        f = tmpdir / "offender.py"
        f.write_text(src, encoding="utf-8")
        try:
            hits, violations = scan(files=[f])
            self.assertEqual(len(hits), 1, "[C4_DIRTY_NOT_CAUGHT] 违规样本没被扫到（hits=%d）" % len(hits))
            self.assertEqual(len(violations), 1,
                             "[C4_DIRTY_NOT_CAUGHT] 违规样本被扫到却没判违规 ⇒ 豁免逻辑漏了")
            print("  [C4_DIRTY_WITNESS] 抓到并具名：%s:%d | %s" % violations[0])
        finally:
            f.unlink(); tmpdir.rmdir()


if __name__ == "__main__":
    unittest.main(verbosity=2)
