# -*- coding: utf-8 -*-
r"""把同一把尺子伸进 paper/：扫 main.tex 与图，按**语义**分类具名清单，只报不改。

为什么必须分类而不是"见名就报"：IQL/VDN/QMIX 在论文里有两种完全不同的身份 ——
(a) 别人做过什么（相关工作、\cite、文献条目）＝**合法**，删了就是造假引用；
(b) 我们评了什么、表格里的数、结论里的排名＝**结论形式**，这些数字正是 R2 逐格证伪的那六行。
如果把两类混在一起报，下一轮为了变绿就会去删 (a)，那是更坏的修法。
所以分类写进输出，且由 console/test_paper_void_scan.py 双向钉住：
"合法那类被误报"同样算测试失败。

    python console/_citations.py --paper-report                 # 打印
    python console/_citations.py --paper-report --write         # 生成清单
    python console/_citations.py --paper-report --verify         # 不一致退出码 1

改论文内容是**作者权决定**，本文件不自动改 paper/ 下任何东西。
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

try:                                   # 与包内其它模块用同一把尺子，不另立算法名单
    from console import _rowsets
except ImportError:                    # 以脚本方式直接跑时
    import _rowsets

PURGE_SHA = "6b8c4c8"          # 撤除 MARL 侧与那六行的提交
FIG_DIR = "paper/figure"


def name_re(withdrawn):
    """由算法键集合现算显示名正则：`qmix_u` -> 匹配 `QMIX-U` 与 `QMIX`。

    大小写敏感 + 词边界是判别式的一半：不敏感会命中 `dynamically` 里的 iql，
    没边界会把 `QMIXv2` 也算成一行已撤除的数据。
    """
    disp = {k.replace("_", "-").upper() for k in withdrawn}
    bases = sorted({d.split("-")[0] for d in disp})
    tails = sorted({d[d.index("-"):] for d in disp if "-" in d}, key=len, reverse=True)
    return re.compile(r"\b(?:%s)%s\b" % ("|".join(bases),
                                         "(?:%s)?" % "|".join(tails) if tails else ""))


#: 清单顶部写着"算法名集合来自 `console/_rowsets.py` 的 `WITHDRAWN`"。
#: 这句可证伪：NAME_RE 由它现算，改那边一个键这里就跟着变，
#: 由 console/test_paper_void_scan.py 的 test_name_set_is_the_same_ruler_as_the_rowset 钉住。
NAME_RE = name_re(_rowsets.WITHDRAWN)
WITHDRAWN_DISPLAY = tuple(sorted(d.replace("_", "-").upper()
                                 for d in _rowsets.WITHDRAWN))
KEY_RE = re.compile(r"\\(?:cite|citep|autocite|bibitem)\s*\*?\{([^}]*)\}")
SECTION_RE = re.compile(r"^\s*\\(?:section|subsection|subsubsection|paragraph)\*?\{([^}]*)\}")
BIB_RE = re.compile(r"^\s*\\begin\{thebibliography\}|^\s*\\bibitem")

#: **只有**这些标题下的命中才算"别人做过什么"。刻意不含 introduction / conclusion ——
#: 那里写的是"我们做了什么、结论是什么"，把默认放宽就是让真主张藏进合法筐里，
#: 与把真相关工作当缺陷删掉同样是错，只是方向相反。默认一律进"待夺"。
RELATED_HINTS = ("related work", "survey", "literature", "background", "preliminar")
VERDICT_SECTIONS = ("experiment", "result", "evaluation", "performance", "ablation")

CLS_TABLE = "结论/数据形式（表格行或图注）"
CLS_BODY = "结论/方法叙述（正文）"
CLS_RELATED = "合法：相关工作叙述（提及他人方法）"
CLS_BIB = "合法：文献/引用键"
NEEDS_DECISION = (CLS_TABLE, CLS_BODY)


def _git(root, *args):
    pr = subprocess.run(["git"] + list(args), cwd=str(root), capture_output=True)
    return pr.stdout.decode("utf-8", "replace").strip()


def paper_facts(root):
    """「撤除从未到达论文」是事实陈述，且必须是算出来的，不是抄的。"""
    last = _git(root, "log", "-1", "--format=%H", "--", "paper")
    touched = _git(root, "show", "--numstat", "--format=", PURGE_SHA, "--", "paper")
    out = {"paper_last_commit": last[:7] if last else "(无)",
           "paper_last_date": _git(root, "log", "-1", "--format=%ad",
                                   "--date=short", "--", "paper"),
           "purge_touched_paper": len([l for l in touched.splitlines() if l.strip()]),
           "figures": []}
    for p in sorted((Path(root) / FIG_DIR).glob("*")):
        rel = "%s/%s" % (FIG_DIR, p.name)
        sha = _git(root, "log", "-1", "--format=%H", "--", rel)
        anc = subprocess.run(["git", "merge-base", "--is-ancestor", sha, PURGE_SHA],
                             cwd=str(root), capture_output=True).returncode == 0 if sha else False
        out["figures"].append({"name": p.name, "last": sha[:7] if sha else "(未入库)",
                               "date": _git(root, "log", "-1", "--format=%ad",
                                            "--date=short", sha) if sha else "",
                               "before_purge": anc})
    return out


def classify_text(text, names=None):
    """-> [(行号, 分类, 命中的算法显示名, 该行截断)]，按行号升序。"""
    names = tuple(_rowsets.WITHDRAWN) if names is None else names
    lines = text.split("\n")
    in_table = False
    section = "(文首/摘要)"
    in_bib = False
    out = []
    for i, raw in enumerate(lines, 1):
        if re.match(r"^\s*\\begin\{table\*?\}", raw):
            in_table = True
        if re.match(r"^\s*\\end\{table\*?\}", raw):
            in_table = False
        if BIB_RE.match(raw):
            in_bib = True
        m = SECTION_RE.match(raw)
        if m:
            section = m.group(1).strip()
            in_bib = in_bib and "bibliograph" in section.lower()
        hits = NAME_RE.findall(raw)
        if hits:
            low = section.lower()
            if in_table or "\\caption" in raw:
                cls = CLS_TABLE
            elif in_bib:
                cls = CLS_BIB
            elif any(h in low for h in RELATED_HINTS):
                cls = CLS_RELATED
            else:
                cls = CLS_BODY          # 默认进"待夺"，不让真主张藏进合法筐
            out.append((i, cls, sorted(set(h.upper() for h in hits)), raw.strip()[:110]))
        if not hits:                    # 只在没有显示名命中时才看引用键，
            for key in KEY_RE.findall(raw):   # 否则"We evaluate … ~\cite{vdn}"这种
                keys = {k.strip().lower() for k in key.split(",")}
                if keys & {n.lower() for n in names}:
                    out.append((i, CLS_BIB, sorted(keys), raw.strip()[:110]))
    seen, deduped = set(), []
    for row in out:
        if (row[0], row[1]) in seen:
            continue
        seen.add((row[0], row[1]))
        deduped.append(row)
    return sorted(deduped)


def render(root, tex_rel="paper/AAMAS-2023 Formatting Instructions/main.tex"):
    import io
    with io.open(Path(root) / tex_rel, encoding="utf-8", errors="replace") as fh:
        tex = fh.read()
    rows = classify_text(tex)
    facts = paper_facts(root)
    need = [r for r in rows if r[1] in NEEDS_DECISION]
    legal = [r for r in rows if r[1] not in NEEDS_DECISION]
    lines = [
        "# 论文侧「撤除未达」具名清单（只报不改）",
        "",
        "- 生成：`python console/_citations.py --paper-report --write`",
        "- 核对：`python console/_citations.py --paper-report --verify`（不一致退出码 1）",
        "- 算法名集合来自 `console/_rowsets.py` 的 `WITHDRAWN`（与作废判据、差异表同一把尺子）",
        "- **本清单不自动改 `paper/` 任何文件**：删哪几行、改成什么口径是作者权决定。",
        "",
        "## 为什么必须分类",
        "",
        "`IQL / VDN / QMIX` 在论文里有两种身份。把它们混成一锅报，下一轮为了变绿就会去删",
        "**真的相关工作引用** —— 那是比重复数字更坏的修法。所以分类本身就是判据的一部分，",
        "由 `console/test_paper_void_scan.py` 双向钉住：误报合法项同样算测试失败。",
        "",
        "## 事实（算出来的，不是抄的）",
        "",
        "| 量 | 值 |",
        "|---|---|",
        "| `%s` 最后一次入库改动 | `%s`（%s） |" % (tex_rel, facts["paper_last_commit"],
                                            facts["paper_last_date"]),
        "| %s 这次撤除动过 `paper/` 几个文件 | **%d** |" % (PURGE_SHA,
                                                       facts["purge_touched_paper"]),
        "| 图的总数 / 其中最后一次改动早于 %s 的 | %d / %d |" % (
            PURGE_SHA, len(facts["figures"]),
            sum(1 for f in facts["figures"] if f["before_purge"])),
        "",
        "⇒ **撤除动作从未到达论文**：那六行仍以论文作者的身份出现在结果表与结论文字里。",
        "",
        "## 待作者定夺（结论形式，共 %d 处）" % len(need),
        "",
        "| 行 | 类别 | 命中 | 该行 |",
        "|---|---|---|---|",
    ]
    for ln, cls, names, snippet in need:
        lines.append("| %d | %s | %s | `%s` |" % (ln, cls, "、".join(names),
                                                  snippet.replace("|", "\\|")))
    lines += ["", "## 合法，不得当缺陷报（共 %d 处）" % len(legal), "",
              "| 行 | 类别 | 命中 | 该行 |", "|---|---|---|---|"]
    for ln, cls, names, snippet in legal:
        lines.append("| %d | %s | %s | `%s` |" % (ln, cls, "、".join(names)[:40],
                                                  snippet.replace("|", "\\|")[:80]))
    lines += ["", "## 图的产物来源", "",
              "| 文件 | 最后入库 | 日期 | 早于撤除 |", "|---|---|---|---|"]
    for f in facts["figures"]:
        lines.append("| `%s` | `%s` | %s | %s |" % (f["name"], f["last"], f["date"],
                                                    "是" if f["before_purge"] else "否"))
    lines += ["", "图的**像素内容未单独核验**（位图读不出列）；能核的是：它们与含 6 行的",
              "派生表同批、且数据源已标作废（见 `results/compare/plots/README.md`）。", ""]
    return "\n".join(lines), rows, facts


OUT_REL = "docs/论文侧撤除未达清单.md"
