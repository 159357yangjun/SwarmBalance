# -*- coding: utf-8 -*-
"""对每张作废归档表，算「仅核心 4 算法」与「含 6 个已撤除（共 10 行）」两种行集合下的
每一个统计量，并把**差异表**生成到 `results/compare/plots/ROW_SETS.md`。

为什么要有这个文件（而不是一句"这批表作废"）：作废通知说的是"含已撤除算法"，
但没人量过**这件事值多少**。同一列名在两种行集合下可以差出 0.24 量级，
而且被混进来的恰好是六个较弱的变体 —— 方向确定（拉低聚合值）。
没有这张表，"作废"只是个态度；有了它，任何引用这些表的人都知道自己少声明了什么。

    python results/row_set_delta.py            # 打印 + 与盘上的 ROW_SETS.md 比对
    python results/row_set_delta.py --write    # 重新生成那份产物
    python results/row_set_delta.py --verify   # 不一致退出码 1（数字不许手抄）

行集合的定义不在这里：只有 console/_rowsets.py 一份。
"""
from __future__ import annotations

import csv
import io
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from console import _rowsets  # noqa: E402

TABLE_DIR = ROOT / "results" / "compare" / "plots"
OUT = TABLE_DIR / "ROW_SETS.md"


def _tables():
    """归档目录里的派生表（不写死文件名：新增一张就自动进表）。"""
    return sorted(p for p in TABLE_DIR.glob("*.csv"))


def _numeric_cols(rows, cols):
    out = []
    for c in cols:
        vals = [r.get(c, "").strip() for r in rows if (r.get(c) or "").strip()]
        if not vals:
            continue
        try:
            [float(v) for v in vals]
        except ValueError:
            continue
        out.append(c)
    return out


def _fmt(x):
    return "—" if x is None else "%.6f" % x


def compute():
    """-> [(表名, 列名, n_core, n_all, mean_core, mean_all, 是否不同)]"""
    out = []
    for p in _tables():
        with io.open(p, encoding="utf-8-sig", newline="") as fh:
            rd = csv.DictReader(fh)
            rows = list(rd)
            cols = rd.fieldnames or []
        if not rows:
            out.append((p.name, "(空表)", 0, 0, None, None, False))
            continue
        key = cols[0]
        core, wd, other = _rowsets.split(rows, key=key)
        if other:
            raise AssertionError("%s 出现了 CORE/WITHDRAWN 之外的算法名：%s —— "
                                 "行集合定义或表内容变了，先核对再重生成"
                                 % (p.name, sorted({r[key] for r in other})[:5]))
        allrows = core + wd
        for c in _numeric_cols(allrows, cols[1:]):
            def mean(sub):
                vals = [float(r[c]) for r in sub if (r.get(c) or "").strip()]
                return statistics.fmean(vals) if vals else None
            mc, ma = mean(core), mean(allrows)
            differs = (mc is None) != (ma is None) or (
                mc is not None and ma is not None and abs(ma - mc) > 5e-12)
            out.append((p.name, c, len(core), len(allrows), mc, ma, differs))
    return out


def render():
    rec = compute()
    n_diff = sum(1 for r in rec if r[6])
    lines = [
        "# 两种行集合下的统计量差异（本文件由代码生成，禁止手改）",
        "",
        "- 生成：`python results/row_set_delta.py --write`",
        "- 核对：`python results/row_set_delta.py --verify`（不一致退出码 1）",
        "- 行集合定义：`console/_rowsets.py` 的 `CORE` / `WITHDRAWN`（唯一一份）",
        "- 被作废的产物：本目录 3 份派生表 + 12 张图，作废理由见同目录 `README.md`（R8）",
        "",
        "| 表 | 统计量（列） | n(核心) | n(含撤除) | 均值(核心4) | 均值(含撤除10) | 差 | 两读数是否相同 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, col, nc, na, mc, ma, differs in rec:
        delta = "—" if (mc is None or ma is None) else "%+.6f" % (ma - mc)
        lines.append("| `%s` | %s | %d | %d | %s | %s | %s | %s |"
                     % (name, col, nc, na, _fmt(mc), _fmt(ma), delta,
                        "相同" if not differs else "**不同**"))
    lines += ["",
              "合计 %d 个统计量，其中 **%d 个在两种行集合下读数不同**；"
              "引用这些表的每一行都必须声明用的是哪一种（标注写法见 `console/_citations.py`）。"
              % (len(rec), n_diff),
              ""]
    return "\n".join(lines)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    text = render()
    if "--write" in argv:
        OUT.write_bytes(text.encode("utf-8"))
        print("已写 %s（%d 字节）" % (OUT.relative_to(ROOT).as_posix(), OUT.stat().st_size))
        return 0
    if not OUT.is_file():
        print("[FAIL] 缺 %s —— 跑 python results/row_set_delta.py --write" % OUT)
        return 1
    on_disk = OUT.read_text(encoding="utf-8")
    if on_disk != text:
        print("[FAIL] %s 与代码重算结果不一致（数字被手改过，或表内容变了没重生成）" % OUT)
        a, b = on_disk.splitlines(), text.splitlines()
        for i in range(max(len(a), len(b))):
            x = a[i] if i < len(a) else "<无>"
            y = b[i] if i < len(b) else "<无>"
            if x != y:
                print("  第 %d 行不同：\n    盘上: %s\n    重算: %s" % (i + 1, x, y))
        return 1
    if "--verify" in argv:
        print("[OK] %s 与代码重算逐字节一致" % OUT.name)
        return 0
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
