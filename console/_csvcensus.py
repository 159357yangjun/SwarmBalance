# -*- coding: utf-8 -*-
r"""`results/compare/*.csv` 的形状普查：每一个数都现算，产物里不许有手抄值。

为什么要有这个生成器（"手抄数"一族的第五次）：`docs/数据来源与可追溯性登记表.md` 的 R4 那行
原先写死「四份手写 / 八份 CSV / 25·20·16 列 / 只有 backend_wx 没有 BOM」。`6b8c4c8` 撤掉
MARL 侧之后那行**四条全失效**（现 7 份、列宽 13/20/25、七份全有 BOM），而且它从来没提
`hetero_vs_homo_*.csv` 那两份 13 列的。同一条注释里抄的数已经错过四次了，所以这次不给它
"更小心地抄"的机会：数由代码扫，产物由 `--write` 生成，`--verify` 不一致就退出码 1。

三条口径写在这里，免得下一个人以为判据是随手定的：
- **声明名单不抄第二份**：两个入口（`console/server.py` 的 `_CSV_FILES` 与
  `results/plot_compare_metrics.py` 的 `CSV_FILES`）从**源码里解析**出来。解析不到就停下，
  绝不用空名单往下算（空名单会把"磁盘上每一份"都变成"没人声明"，那是最贵的假红）。
- **两种 0 分开**：`清单里声明了但磁盘没有` 与 `磁盘有但两份清单都没声明` 是两个桶，
  前者是欠账（今天就是 `backend_wx_metrics.csv` 那一条），只进报告行、**不进退出码**；
  因为"删哪一行清单"是他定，不是这道门能替做的。
- **恒等式**：`两边都有 + 只在磁盘 = 磁盘份数`、`两边都有 + 只在清单 = 声明条数`。
  分桶最容易死成"某一类既不算通过也不算失败"，所以印的是等式。

失败短码（GBK 控制台上中文会变 ??????，所以判定信息一律带 ASCII 码）：
    [CSV_CENSUS_MISSING]   产物不存在
    [CSV_CENSUS_STALE]     产物与现算不一致
    [CSV_CENSUS_RANGE]     扫到的 CSV 少于下限（= 扫描范围塌了，整轮作废）
    [CSV_CENSUS_PARSE]     源码里解析不出声明名单（= 入口改名了，不许用空名单算）
    [CSV_CENSUS_PROBLEM]   有 N 条形状问题（列宽并列不可比之类，见表末）

用法：
    python console/_citations.py --csv-census            # 打印
    python console/_citations.py --csv-census --write    # 生成 docs/compareCSV普查.md
    python console/_citations.py --csv-census --verify   # 与盘上不一致退出码 1
"""
from __future__ import annotations

import csv
import io
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_REL = "docs/compareCSV普查.md"
COMPARE_DIR = "results/compare"
# 扫描范围下限：本目录里"应当存在的对比 CSV"数量级。真数比这还少 = 目录被动过或扫错了地方，
# 那不是"没有缺陷"，那是扫描瞎了 —— 瞎了的扫描必须整轮红，不能报绿。
FLOOR = 5
# 声明名单的两个入口。**写在这里的是"去哪解析"，不是"解析出什么"** —— 名单本体现读。
DECLARED_FROM = (("console/server.py", "_CSV_FILES"),
                 ("results/plot_compare_metrics.py", "CSV_FILES"))
# R2 那六行被撤除后，登记表里点过名、现在磁盘上没有的对比 CSV（用于给"只在清单"那条
# 找到成因；这条只许当线索用，不进退出码）。
DELETED_HINT = "backend_wx_metrics.csv"


def _parse_declared(root, rel, var):
    """从源码里解析出 `VAR = [ "a.csv", ... ]` 的字符串项。解析不到就抛。"""
    path = Path(root) / rel
    if not path.is_file():
        raise ValueError("声明名单的来源文件不在：%s" % rel)
    text = path.read_text(encoding="utf-8", errors="replace")
    # 行首匹配（MULTILINE）：`\nVAR = [` 这种找法会漏掉"名单就写在文件第 1 行"的入口 ——
    # 真仓两个入口都有前导内容所以没暴露，是夹具第一版把它撞出来了。
    m = re.search(r"(?m)^%s = \[" % re.escape(var), text)
    if not m:
        raise ValueError("%s 里找不到 `%s = [`（入口改名了？）" % (rel, var))
    start = m.start()
    # 括号配平找结尾：缩进/换行敏感的边界会把后面的兄弟块吞进来（同一族踩过）。
    i = text.index("[", start)
    # 括号配平，且**引号内的方括号不算**：名单里一旦出现 `"[观测]x.csv"` 这种名字，
    # 不区分引号的配平会提前收尾，把兄弟块当成名单的一部分（同一族踩过）。
    depth = 0
    quote = ""
    j = i
    n = len(text)
    closed = False
    while j < n:
        ch = text[j]
        if quote:
            if ch == quote:
                quote = ""
        elif ch == "#":
            # 注释里的撇号（don't）不能开引号，否则后面的 `]` 会被当成字符串内容而漏收；
            # 名单里带一行注释是现实形状，夹具就造这一行。
            nl = text.find("\n", j)
            if nl < 0:
                raise ValueError("%s 的 `%s` 注释后没有行尾" % (rel, var))
            j = nl            # 直接跳到那行行尾（下一轮再吃换行）
        elif ch in "'\"":
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                closed = True
                break
        j += 1
    if not closed:
        raise ValueError("%s 的 `%s` 没找到列表结尾（括号没配平）" % (rel, var))
    if quote:
        raise ValueError("%s 的 `%s` 里有没闭合的引号" % (rel, var))
    body = text[i:j + 1]
    names = re.findall(r"['\"]([^'\"]+\.csv)['\"]", body)
    if not names:
        raise ValueError("%s 的 `%s` 解析出 0 项 —— 不许用空名单往下算" % (rel, var))
    return names


def declared(root=ROOT):
    """两个入口各自解析出来的声明名单（保持源码顺序，去重靠 set 在外层做）。"""
    out = {}
    for rel, var in DECLARED_FROM:
        out["%s:%s" % (rel, var)] = _parse_declared(root, rel, var)
    return out


def scan(root=ROOT, subdir=COMPARE_DIR):
    """逐文件现算：列数 / 数据行数 / BOM / 首列 / 有没有 seed 列。"""
    d = Path(root) / subdir
    rows = []
    for p in sorted(d.glob("*.csv"), key=lambda x: x.name):
        raw = p.read_bytes()
        has_bom = raw[:3] == b"\xef\xbb\xbf"
        f = io.open(p, encoding="utf-8-sig", newline="")
        try:
            rd = csv.reader(f)
            hdr = next(rd, [])
            # 行数按 csv 记录数，不按物理行：字段里带换行的话物理行会把数读大。
            n = sum(1 for row in rd if row and any(c.strip() for c in row))
        finally:
            f.close()
        if not hdr:
            # 读不出表头 = 这份是 0 字节或被截断的产物。**不抛异常**（抛了就没人在产物里看到它），
            # 记成一行 + 一条问题，让 `--verify` 红并把它印出来。
            rows.append({"name": p.name, "cols": 0, "data_rows": 0, "bom": has_bom,
                         "first": "（读不出表头）", "seed_cols": [], "has_algo": False,
                         "hdr": [], "unreadable": True})
            continue
        rows.append({"name": p.name, "cols": len(hdr), "data_rows": n, "bom": has_bom,
                     "first": hdr[0], "seed_cols": [c for c in hdr if "seed" in c.lower()],
                     "has_algo": any(c.strip() == "算法" for c in hdr),
                     "hdr": hdr, "unreadable": False})
    return rows


def column_gap(rows):
    """同一批对比 CSV 里，宽表比窄表多出哪些列 —— 登记表 R6 那句手抄话的现算版。

    只比**含 `算法` 列**的那些文件：`hetero_vs_homo_*.csv` 讲的是另一件事（13 列、连步数列
    都没有），把它拉进来这张表九成是噪音，而 R6 说的正是"对比表缺列被补 0"。
    分组键用完整列集合，**不去借门禁的 `schema_fingerprint`** —— 两边各自数同一件事、
    数出来不一样就该红，那才叫外部重数；借它的函数等于自己给自己作证。
    """
    fam = [r for r in rows if r["has_algo"] and r["hdr"]]
    groups = {}
    for r in fam:
        groups.setdefault(tuple(sorted(c.strip() for c in r["hdr"])), []).append(r["name"])
    if len(groups) < 2:
        return {"distinct_schemas": len(groups), "algo_files": len(fam), "pairs": [],
                "empty_reason": "含`算法`列的文件只剩 0 或 1 种表头 —— 这一节没有差异可报；"
                                "空着是有原因的，不是扫描漏了"}
    keys = sorted(groups, key=lambda k: (-len(k), k))
    widest = keys[0]
    pairs = [{"wide": sorted(groups[widest]), "narrow": sorted(groups[k]),
              "only_in_wide": sorted(set(widest) - set(k)),
              "only_in_narrow": sorted(set(k) - set(widest))} for k in keys[1:]]
    return {"distinct_schemas": len(groups), "algo_files": len(fam), "pairs": pairs,
            "empty_reason": ""}


def _deleted_via(root, name):
    """这份 CSV 是哪一笔提交删掉的（现算，不抄）。不在清单里/没删过就返回 None。"""
    pr = subprocess.run(["git", "log", "--diff-filter=D", "-1", "--format=%h", "--",
                         "%s/%s" % (COMPARE_DIR, name)],
                        cwd=str(root), capture_output=True)
    if pr.returncode:
        return None
    sha = pr.stdout.decode("utf-8", "replace").strip()
    return sha or None


def report(root=ROOT, subdir=COMPARE_DIR):
    """-> (markdown, 统计字典)。

    声明名单**总是**从 `root` 下的那两个入口解析 —— 不给测试留"传一份名单进来"的后门：
    后门会让夹具绕过解析逻辑，而解析逻辑正是这轮最容易坏的那部分（入口改名、括号配平、
    引号里带方括号）。临时目录要当夹具，就在里面放真的源文件。
    """
    rows = scan(root, subdir)
    dec = declared(root)
    if not dec:
        raise ValueError("声明名单是空的 —— 不许用空名单往下算")
    all_declared = sorted({n for v in dec.values() for n in v})
    disk = sorted(r["name"] for r in rows)
    both = sorted(set(disk) & set(all_declared))
    disk_only = sorted(set(disk) - set(all_declared))
    declared_only = sorted(set(all_declared) - set(disk))
    widths = sorted({r["cols"] for r in rows})
    no_bom = [r["name"] for r in rows if not r["bom"]]
    with_seed = [r["name"] for r in rows if r["seed_cols"]]
    gap = column_gap(rows)          # 下面 counts 与正文都用这一份，不各算一遍
    problems = []
    # 两类失败分开：`blind`（扫描瞎了 ⇒ 整轮不作数，短码 RANGE）与真正的内容缺陷（PROBLEM）。
    # 混在一条码上，读红的人就不知道该去修目录还是该去查扫描器。
    blind = len(rows) < FLOOR
    unreadable = [r["name"] for r in rows if r.get("unreadable")]
    if unreadable:
        problems.append("这些 CSV 读不出表头（0 字节或被截断）：%s"
                        % ", ".join("`%s`" % n for n in unreadable))
    if blind:
        problems.append("扫到 %d 份 CSV，低于范围下限 %d —— 扫描范围塌了，本轮读数不作数"
                        % (len(rows), FLOOR))
    # 恒等式（分桶必须能加回去，否则某一类既不算通过也不算失败）
    if len(both) + len(disk_only) != len(disk) or len(both) + len(declared_only) != len(all_declared):
        problems.append("分桶恒等式不成立：both=%d disk_only=%d declared_only=%d "
                        "disk=%d declared=%d" % (len(both), len(disk_only),
                                              len(declared_only), len(disk), len(all_declared)))
    # `declared_only` 是**待夺事项，不是缺陷**：摘哪一行清单是他定，门不许替它红。
    # （把它塞进 problems 就等于"用退出码逼人做我决定做的事"，模块头里那条口径会被自己推翻。）
    watch = []
    for name in declared_only:
        sha = _deleted_via(root, name)
        watch.append("`%s` 被清单声明、磁盘上没有%s"
                     % (name, "（`%s` 删的）" % sha if sha else "（git 里没找到删除记录）"))
    counts = {"files": len(rows), "widths": widths, "no_bom": no_bom,
              "gap_schemas": gap["distinct_schemas"],
              "gap_only_in_wide": sum(len(p["only_in_wide"]) for p in gap["pairs"]),
              "with_seed": with_seed, "disk_only": disk_only, "watch": watch,
              "blind": blind, "unreadable": unreadable,
              "declared_only": declared_only, "both": both,
              "declared_total": len(all_declared), "problems": len(problems),
              "bom_yes": sum(1 for r in rows if r["bom"])}
    lines = [
        "# `results/compare/*.csv` 形状普查（每个数都由代码现算，禁止手填）",
        "",
        "- 生成：`python console/_citations.py --csv-census --write`",
        "- 核对：`python console/_citations.py --csv-census --verify`（不一致退出码 1）",
        "- 扫描器：`console/_csvcensus.py`；判据用例：`console/test_compare_csv_census.py`",
        "- **这份产物不声明谁对谁错**：它只数出磁盘上现在长什么样。",
        "  口径能不能并列是 `results/compare_gate.py` 的事；本产物被 `--verify` 逐字节核。",
        "",
        "## 恒等式与分桶",
        "",
        "| 量 | 值 | 怎么算的 |",
        "|---|---|---|",
        "| 磁盘上的 CSV | %d | `sorted(glob(%s/*.csv))` |" % (len(rows), subdir),
        "| 两份清单声明的条数（并集去重） | %d | 从源码解析，不抄第二份名单 |"
        % len(all_declared),
        "| ├ 两边都有 | %d | 交集 |" % len(both),
        "| ├ 磁盘有但两份清单都没声明 | %d | %s |" % (
            len(disk_only), ", ".join("`%s`" % x for x in disk_only) or "（无）"),
        "| └ 清单声明但磁盘没有 | %d | %s |" % (
            len(declared_only), ", ".join("`%s`" % x for x in declared_only) or "（无）"),
        "| 恒等式 | %s | `两边都有 + 只在磁盘 = 磁盘份数`，"
          "`两边都有 + 只在清单 = 声明条数` |"
        % ("成立" if not any("恒等式" in p for p in problems) else "**不成立**"),
        "| 扫描可用 | %s | 现数 %d 对下限 %d；低于下限 ⇒ 整轮不作数（`[CSV_CENSUS_RANGE]`），"
        "而不是报一句\"没问题\" |" % ("是" if not blind else "**否**", len(rows), FLOOR),
        "| 读不出表头的 | %s | 0 字节或被截断 ⇒ 记一条问题（不抛异常：抛了就没人看得见它） |"
        % (", ".join("`%s`" % n for n in unreadable) or "（无）"),
        "| 出现的列宽 | %s | 各文件表头字段数去重后排序 |" % (", ".join(str(w) for w in widths)),
        "| 含 UTF-8 BOM 的份数 | %d / %d | 逐文件读首三字节 `efbbbf` |"
        % (counts["bom_yes"], len(rows)),
        "| 没有 BOM 的 | %s | 逐文件判，不问目录 |"
        % (", ".join("`%s`" % x for x in counts["no_bom"]) or "（无）"),
        "| 含 seed 列的 | %s | 列名含 `seed`（不分大小写） |"
        % (", ".join("`%s`" % x for x in counts["with_seed"]) or "（无 —— 一份都没有）"),
        "",
        "## 逐文件",
        "",
        "| 文件 | 列数 | 数据行数 | BOM | 首列 | 有`算法`列 | seed 列 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append("| `%s` | %d | %d | %s | `%s` | %s | %s |" % (
            r["name"], r["cols"], r["data_rows"], "是" if r["bom"] else "**否**",
            r["first"], "是" if r["has_algo"] else "否",
            ", ".join("`%s`" % c for c in r["seed_cols"]) or "—"))
    lines += ["", "## 宽表比窄表多出哪些列（R6 那句手抄话的现算版）", "",
              "含 `算法` 列的文件共 %d 份，出现 %d 种完整列集合。"
              % (gap["algo_files"], gap["distinct_schemas"])]
    if gap["pairs"]:
        for pr in gap["pairs"]:
            lines += ["", "- 宽：%s（%d 列）vs 窄：%s ⇒ **宽表多 %d 列**：%s；"
                      "窄表多 %d 列：%s"
                      % (", ".join("`%s`" % x for x in pr["wide"]),
                         max(r["cols"] for r in rows if r["name"] in pr["wide"]),
                         ", ".join("`%s`" % x for x in pr["narrow"]),
                         len(pr["only_in_wide"]),
                         ", ".join("`%s`" % c for c in pr["only_in_wide"]) or "（无）",
                         len(pr["only_in_narrow"]),
                         ", ".join("`%s`" % c for c in pr["only_in_narrow"]) or "（无）")]
        lines += ["", "缺的那批列在窄表里是**不存在**，不是 0 —— 谁把它们 `fillna(0)` "
                  "或在前端写 `v ?? 0`，图就会把\"没测\"画成\"零缺陷\"。"]
    else:
        lines += ["- %s" % gap["empty_reason"]]
    lines += ["", "## 两份清单各自声明了什么", ""]
    for src, names in sorted(dec.items()):
        lines.append("- `%s`：%s" % (src, ", ".join("`%s`" % n for n in names)))
    lines += ["", "## 与登记表 R4 的关系", "",
              "R4 原先手写的那几个数（份数、列宽、BOM 例外、seed 列）**全部由本产物代管**：",
              "登记表里那行只留结论与指路，不再留数。数一旦写进文档就会漂 —— 上一轮它漂了四条，",
              "而漂了的注释比空白更危险，因为它看着像有依据。",
              ""]
    if watch:
        lines += ["", "## 待你定夺（只报不改，**不进退出码**）", ""]
        lines += ["- %s —— 摘不摘那一行是改 `CSV_FILES` 的决定，不归这道门。" % w
                  for w in watch]
    if disk_only:
        lines += ["**两份清单都没声明**：%s —— 它们仍被 `pd.concat` 之类的方式读进来时，"
                  "口径就绕过了清单。" % ", ".join("`%s`" % n for n in disk_only)]
    if problems:
        lines += ["", "## 问题（这些条不修，`--verify` 就退出码 1）", ""]
        lines += ["- %s" % p for p in problems]
    return "\n".join(lines) + "\n", counts


def render_for_doc(counts):
    """给登记表 R4 那一行用的一句话（数字全部来自本轮现算，不是抄上一轮）。"""
    return "磁盘 %d 份，列宽 %s，BOM %d/%d，含 seed 列 %d 份" % (
        counts["files"], "/".join(str(w) for w in counts["widths"]),
        counts["bom_yes"], counts["files"], len(counts["with_seed"]))


def main(argv, root=ROOT):
    t0 = time.time()
    try:
        text, counts = report(root)
    except ValueError as e:
        # 解析不出声明名单 = 入口改了名。这时候**绝不**退回"空名单"往下算：
        # 空名单会把磁盘上每一份都判成"没人声明"，那是一条会喊狼的红。
        print("[FAIL][CSV_CENSUS_PARSE] %s | fix: 更新 console/_csvcensus.py 的 "
              "DECLARED_FROM，别把普查改成读常量" % e)
        return 1
    counts["ms"] = int((time.time() - t0) * 1000)
    # 瞎了就先说瞎 —— 排在 MISSING/STALE **之前**：扫描范围塌了的时候去比产物，
    # 报出来的会是"表被手改过"，那是把量具坏了说成别人的错。写盘也照红：
    # 一份没人信得过的产物不该因为 --write 就换个退码。
    if counts["blind"]:
        print("[FAIL][CSV_CENSUS_RANGE] files=%d floor=%d 扫描范围塌了，本轮读数不作数"
              " | fix: 确认 results/compare 还在、subdir 没写错（这**不是**\"没问题\"）"
              % (counts["files"], FLOOR))
        return 1
    out = Path(root) / OUT_REL
    if "--write" in argv:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(text.encode("utf-8"))
        print("已写 %s（磁盘 %d 份 / 列宽 %s / 无 BOM %d / 只在清单 %d / 问题 %d）"
              % (OUT_REL, counts["files"], ",".join(str(w) for w in counts["widths"]),
                 len(counts["no_bom"]), len(counts["declared_only"]), counts["problems"]))
        return 0
    if not out.is_file():
        print("[FAIL][CSV_CENSUS_MISSING] %s | fix: python console/_citations.py"
              " --csv-census --write" % OUT_REL)
        return 1
    if out.read_bytes() != text.encode("utf-8"):
        print("[FAIL][CSV_CENSUS_STALE] %s differs from what the CSVs say now"
              " | fix: python console/_citations.py --csv-census --write"
              " —— 产物被手改过，或 `results/compare/` 变了没重生" % OUT_REL)
        return 1
    if counts["problems"]:
        print("[FAIL][CSV_CENSUS_PROBLEM] %d 条问题（范围下限/恒等式）| 见表末"
              % counts["problems"])
        return 1
    if "--verify" in argv:
        print("[CSV_CENSUS] files=%d declared=%d both=%d disk_only=%d declared_only=%d "
              "widths=%s no_bom=%d seed_cols=%d gap_schemas=%d gap_only_in_wide=%d "
              "cost_ms=%d | 产物与盘上现算逐字节一致"
              % (counts["files"], counts["declared_total"], len(counts["both"]),
                 len(counts["disk_only"]), len(counts["declared_only"]),
                 ",".join(str(w) for w in counts["widths"]), len(counts["no_bom"]),
                 len(counts["with_seed"]), counts["gap_schemas"],
                 counts["gap_only_in_wide"], counts["ms"]))
        return 0
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
