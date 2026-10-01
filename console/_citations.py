# -*- coding: utf-8 -*-
"""文档里的 `路径:行号` 引用必须翻得到东西 —— 这个文件是那道判据的唯一实现。

为什么要有独立文件（而不是只写在用例里）：`skipped=12` 那轮的教训是
**判据跑出来的数字要印在纸上**，不能只在红的时候才看得见。引用门禁同理：
覆盖率本身决定了这道门能看见多少，所以它由每次运行自己印 —— 见 `[CITE_SUMMARY]`
那行（`checked=` / `anchored=`）。这里不抄具体数：抄下来就必然随文档漂移，
而漂移的抄件比空白更危险（它看着像有依据）。

两类失效：
① 路径不存在 / 行号越界 —— 旧实现只认 `:123`，登记簿里的 `:118-121`、
   `:141-145,153,195` 这类写法**一条都没进扫描**，所以它们从来没红过。
② 行号在范围内却指向别处 —— 纯行号判据永远看不见，本轮逐条对着盘上内容核，
   这类占了相当一部分（如 P1 抄 :112 实为 :88，M1 抄 :926 实为 :921）。
   对策是 `#锚点`：`config/simulation.json:88#carrying_capacity` 要求第 88 行
   含 `carrying_capacity` 这段字。没写锚点的引用仍只判 ①，覆盖率随结果一起印出来。

两种标注让"历史证据"既可翻又不会被当成现状：
  `path:line 已移除@<sha>`   —— 文件在 <sha> 被删，正文按 `git show <sha>^:<path>` 取；
  `path:line#锚点 已失效@<sha>` —— 文件还在但引的是 <sha> 修复**之前**的行号，
      正文同样按 `git show <sha>^:<path>` 判，且**必须带锚点**：历史行号没法跟磁盘比，
      只有锚点能证明它当时真的对过（本轮三条 `environment.py:282` 就是这么错的，
      它在任何修订里都不是那行，真正那行在 `66016b7^` 的 :268）。

    python console/_citations.py                # 人读版汇总
    python console/_citations.py --verify       # 有失效则退出码 1（含论文侧清单是否过期）
    python console/_citations.py --list-bad     # 只列失效行
    python console/_citations.py --paper-report [--write|--verify]
                                                # 论文侧「撤除未达」具名清单，只报不改
    python console/_citations.py --csv-census [--write|--verify]
                                                # results/compare 形状普查（登记表 R4 的数归它管）
                                                # 短码表在 console/_csvcensus.py 自己的 docstring 里，
                                                # 由 console/test_compare_csv_census.py 逐条驱动证明发得出来

每条失效行都以 ASCII 短码开头（`[FAIL][CODE] 文件:行 …  | fix: …`），中文解释跟在后面。
为什么：这台机的控制台是 GBK，门报红时中文诊断会被打成 `??????` —— **一条没人读得懂的红
等于没有门**。短码 + 文件:行 + ASCII 的 fix 子句保证即使整段中文全丢，还能看出
"哪一行、哪一类、往哪个方向改"，再由短码回这张表查全文。短码不许只存在于运行时字符串：
`console/test_gate_ascii_diagnostics.py` 会核每个被发出的短码都在这里列着（反向也要核）。

    [CITE_SUMMARY]         覆盖率汇总（扫到几条 / 几条带锚点）
    [ROWSET_SUMMARY]       作废产物引用汇总（几处 / 几处已声明行集合）
    [CITE_NOFILE]          引用的文件不在盘上，且没标 已移除@<sha>
    [CITE_RANGE]           行号超出文件长度
    [CITE_RANGE_HISTORY]   行号超出那个历史修订的长度
    [ANCHOR_MISS]          行号在范围内但内容不对（锚点找不到）
    [ANCHOR_MISS_HISTORY]  历史修订里锚点找不到
    [ANCHOR_REQUIRED]      用了 已失效@ 却没带锚点
    [GIT_SHOW_FAIL]        标了 已移除@/已失效@ 但那个修订取不回文件
    [ROWSET_UNDECLARED]    引用作废产物没声明行集合（要写 行集=core4|all10）
    [ROWSET_STALE]         声明 all10 但表里实际不是那 10 个算法
    [PAPER_LIST_MISSING]   论文侧清单不存在
    [PAPER_LIST_STALE]     论文侧清单与代码重算不一致（禁止手改）
    [PAPER_LIST_MATCH]     论文侧清单逐字节相符（附现算的几个数）
    [SUMMARY]              失效总条数
"""
from __future__ import annotations

import io
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# —— 字节码纪律（必须在任何本仓 import 之前；解释见 console/test_stale_bytecode.py）——
# .pyc 默认只按 (源 mtime, 源 size) 判过期：两者相符就跑旧字节码，内容对不对没人问。
# 指往一个不存在的目录 = 读必 miss；写由 dont_write_bytecode 挡住，不在树里留东西。
sys.dont_write_bytecode = True
import os as _bc_os, tempfile as _bc_tf, uuid as _bc_ud
sys.pycache_prefix = _bc_os.path.join(_bc_tf.gettempdir(), "swarmbalance-pyc", _bc_ud.uuid4().hex)

# `路径:行号[#锚点]`；行号支持 单行 / 区间 / 逗号多段
CITE = re.compile(
    r"`([^`\n]*?\.(?:tex|py|csv|json|md|html|ya?ml)):"
    r"(\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)"
    r"(?:#([^`\s]+))?`")
# 登记簿约定：引用已删除的文件时写成 `path:line 已移除@<sha>`，并给出取回命令。
REMOVED = re.compile(r"已移除@([0-9a-f]{7,40})")
# 另一种：文件还在，但引用的行号属于**某个提交之前**的状态（描述的是已修好的历史缺陷）。
# 写成 `path:line#锚点 已失效@<sha>`，正文按 `git show <sha>^:<path>` 取 ——
# 否则"历史行号"就永远只能靠人自觉：本轮三条 `environment.py:282` 就是这么错的，
# 它在任何修订里都不是那行（真正那行在 66016b7^ 的 :268）。
OBSOLETE = re.compile(r"已失效@([0-9a-f]{7,40})")

DEFAULT_DOCS = ("docs/数据来源与可追溯性登记表.md", "README.md")


def ranges(spec: str):
    """:706-710 与 :141-145,153,195 都展开成 [(起, 止), ...]。"""
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out.append((int(a), int(b) if b else int(a)))
    return out


def resolve(path_txt: str):
    """把引用解析成磁盘上的文件；裸文件名按登记簿简写在全仓找同名。"""
    rel = path_txt.replace("\\", "/")
    if "/" in rel:
        target = ROOT / rel
        return [target] if target.is_file() else []
    return [p for p in ROOT.rglob(Path(rel).name)
            if p.is_file() and ".git" not in p.parts
            and "__pycache__" not in p.parts and ".venv310" not in p.parts]


def git_show_text(sha: str, rel: str):
    proc = subprocess.run(["git", "show", "%s^:%s" % (sha, rel)],
                          cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return None if proc.returncode else proc.stdout.splitlines()


ROWSET_MARK = re.compile(r"行集=(core4|all10)")
# 不带行号的数据文件引用（`x.csv`、`y.png`）：CITE 只认 `path:数字`，
# 而这些表恰恰是按名字引用的 —— 不另开一条匹配，作废标注就永远扫不到它们。
BARE_PATH = re.compile(r"`([^`\n]*?\.(?:csv|png|jpe?g))`")


def _inside_any(path, dirs):
    for d in dirs:
        try:
            if path.is_relative_to(d):
                return True
        except (ValueError, OSError):
            continue
    return False


def rowset_violations(lines, origin="", vdirs=None):
    """作废目录里的 .csv/.png 被引用时必须声明行集合；声明 all10 的还得真是那张脏表。

    为什么值得单独一条：`results/compare/plots/ROW_SETS.md`（由 results/row_set_delta.py
    生成、可 --verify）实测 27 个统计量里 **22 个** 在两种行集合下读数不同 ——
    `Weighted Overall Score` 0.833768(核心4) vs 0.588907(含撤除10)，差 -0.244861，
    而混进来的恰好是六个较弱变体，方向确定（拉低）。所以"这批表作废"若不写清
    **按哪几行算**，同一个列名就还能被两头引用而没人报警。
    """
    vdirs = void_dirs() if vdirs is None else list(vdirs)
    if not vdirs:
        return 0, 0, []
    checked = marked = 0
    bad = []
    for i, line in enumerate(lines, 1):
        bounds = sorted([m.end() for m in CITE.finditer(line)]
                        + [m.end() for m in BARE_PATH.finditer(line)])
        starts = sorted([m.start() for m in CITE.finditer(line)]
                        + [m.start() for m in BARE_PATH.finditer(line)])
        for m in BARE_PATH.finditer(line):
            rel = m.group(1).replace("\\", "/")
            target = ROOT / rel
            if not _inside_any(target, vdirs):
                continue
            nxt = [s for s in starts if s > m.start()]
            tail_end = min([s for s in nxt], default=len(line))
            tail = line[m.end():tail_end]
            checked += 1
            mm = ROWSET_MARK.search(tail)
            if not mm:
                bad.append("[ROWSET_UNDECLARED] %s:%d void artifact %s is cited with no row"
                           " set | fix: put the row-set mark right after the reference"
                           " (two tokens: 行集=core4 = the 4 core algorithms,"
                           " 行集=all10 = the 10 rows incl. 6 withdrawn);"
                           " the two readings differ for 22 of 27 columns, see"
                           " results/compare/plots/ROW_SETS.md"
                           % (origin, i, rel))
                continue
            marked += 1
            if mm.group(1) == "all10":
                try:
                    from console import _rowsets
                except ImportError:
                    import _rowsets
                algs = table_algorithms(target)
                if algs is not None and algs != _rowsets.ALL_NAMED:
                    bad.append("[ROWSET_STALE] %s:%d %s declares 行集=all10 but the table"
                               " now holds %d algorithms %s | fix: re-check which row set this"
                               " sentence used, then re-write the mark (or regenerate the table)"
                               % (origin, i, rel, len(algs), sorted(algs)))
    return checked, marked, bad


def scan_lines(lines, origin=""):
    """返回 (引用条数, 带锚点条数, 失效清单)。真文档与合成样本共用同一判据。

    标注（已移除@/已失效@）**绑定到紧跟其后的那一条引用**，不是整行共享：
    一行里写两条引用时（一条现状、一条历史），按整行找会把历史标注错扣到现状那条上，
    于是它被判去跟旧修订比内容 —— 这个坑是我给 已失效@ 加完第一件事就被门自己抓到的。
    """
    checked = anchored = 0
    bad = []
    cache = {}
    for i, line in enumerate(lines, 1):
        ms = list(CITE.finditer(line))
        for k, m in enumerate(ms):
            path_txt, spec, anchor = m.group(1), m.group(2), m.group(3)
            # 标注的作用域：本引用结束 -> 下一条引用开始（或行尾）
            tail = line[m.end(): ms[k + 1].start() if k + 1 < len(ms) else len(line)]
            checked += 1
            rr = ranges(spec)
            hi = max(b for _, b in rr)
            obs = OBSOLETE.search(tail)
            if obs:
                # 行号属于该提交之前的状态：正文只按 `git show <sha>^:<path>` 判，不看磁盘
                blob = git_show_text(obs.group(1), path_txt.replace("\\", "/"))
                if blob is None:
                    bad.append("[GIT_SHOW_FAIL] %s:%d marked 已失效@%s but"
                               " `git show %s^:%s` returns nothing | fix: use the commit that"
                               " *deleted* the file, or correct the sha"
                               % (origin, i, obs.group(1), obs.group(1), path_txt))
                    continue
                if hi > len(blob):
                    bad.append("[CITE_RANGE_HISTORY] %s:%d %s:%s is beyond revision %s^,"
                               " which has only %d lines | fix: re-count lines against"
                               " `git show %s^:%s`"
                               " —— 那一行在那个修订里根本不存在，去旧修订里数行号"
                               % (origin, i, path_txt, spec, obs.group(1), len(blob),
                                  obs.group(1), path_txt))
                elif anchor:
                    anchored += 1
                    joined = "\n".join(l for (a, b) in rr for l in blob[a - 1:b])
                    if anchor not in joined:
                        bad.append("[ANCHOR_MISS_HISTORY] %s:%d %s:%s#%s (revision %s^) does"
                                   " not contain that anchor | fix: the line number was wrong"
                                   " already when it was copied; point it at the line whose"
                                   " text holds the anchor. actual: %s"
                                   " —— 行号多半在抄的那一刻就错了"
                                   % (origin, i, path_txt, spec, anchor, obs.group(1),
                                      joined.strip().replace("\n", " / ")[:120]))
                else:
                    bad.append("[ANCHOR_REQUIRED] %s:%d %s:%s uses 已失效@%s with no #anchor"
                               " | fix: a historical line number cannot be compared with the"
                               " disk, so an anchor is mandatory: `path:line#some_text 已失效@sha`"
                               % (origin, i, path_txt, spec, obs.group(1)))
                continue
            cands = resolve(path_txt)
            if cands:
                hit = None
                longest = 0
                for target in cands:
                    key = str(target)
                    if key not in cache:
                        with io.open(target, encoding="utf-8", errors="replace") as fh:
                            cache[key] = fh.read().splitlines()
                    fl = cache[key]
                    longest = max(longest, len(fl))
                    if hi <= len(fl):
                        hit = fl
                        break
                if hit is None:
                    bad.append("[CITE_RANGE] %s:%d %s:%s is beyond the file, whose longest"
                               " copy has %d lines | fix: open the file and take the real line"
                               " number; never adjust the range to make the gate quiet"
                               " —— 去文件里取真行号，别把范围改到刚好过门"
                               % (origin, i, path_txt, spec, longest))
                    continue
                if anchor:
                    anchored += 1
                    blob = "\n".join(l for (a, b) in rr for l in hit[a - 1:b])
                    if anchor not in blob:
                        bad.append(
                            "[ANCHOR_MISS] %s:%d %s:%s#%s | the cited lines hold no such"
                            " anchor, i.e. the line number points somewhere else while still"
                            " being in range (exactly what a pure range check cannot see)."
                            " | fix: move the line number to the line whose text contains"
                            " `%s`. actual: %s"
                            " —— 行号在范围内却指向别处，正是纯行号判据看不见的那一类"
                            % (origin, i, path_txt, spec, anchor, anchor,
                               blob.strip().replace("\n", " / ")[:120]))
                continue
            m = REMOVED.search(tail)
            if not m:
                bad.append("[CITE_NOFILE] %s:%d %s is not on disk | fix: if the file was"
                           " deleted, cite it as `path:line 已移除@<sha>` plus the"
                           " `git show <sha>^:<path>` command; otherwise the reference is"
                           " unverifiable evidence"
                           % (origin, i, path_txt))
                continue
            blob = git_show_text(m.group(1), path_txt.replace("\\", "/"))
            if blob is None:
                bad.append("[GIT_SHOW_FAIL] %s:%d marked 已移除@%s but"
                           " `git show %s^:%s` returns nothing | fix: the sha must be the"
                           " commit that deleted the file"
                           % (origin, i, m.group(1), m.group(1), path_txt))
                continue
            if hi > len(blob):
                bad.append("[CITE_RANGE_HISTORY] %s:%d %s:%s is beyond revision %s^, which has"
                           " only %d lines | fix: re-count lines in"
                           " `git show %s^:%s` —— 已删除的文件按那个修订里的行号引"
                           % (origin, i, path_txt, spec, m.group(1), len(blob),
                              m.group(1), path_txt))
            elif anchor:
                anchored += 1
                joined = "\n".join(l for (a, b) in rr for l in blob[a - 1:b])
                if anchor not in joined:
                    bad.append("[ANCHOR_MISS_HISTORY] %s:%d %s:%s#%s | the retrieved revision"
                               " has no such anchor | fix: point the line at the line whose"
                               " text holds it, in that revision"
                               " —— 那个修订里这一行不是这段字，行号抄错了"
                               % (origin, i, path_txt, spec, anchor))
    return checked, anchored, bad


def void_dirs(root=None):
    """被标作废的产物目录 = 目录内有 README.md 且其中写着"作废"。

    为什么靠发现而不是写死名单：写死的作废清单会过期 —— 目录清干净了它还红，
    新加了个作废目录它不管。判据只看"那份作废通知在不在"，通知撤了约束就没了。
    """
    root = Path(root) if root is not None else (ROOT if "ROOT" in globals() else Path("."))
    out = []
    for notice in sorted(root.rglob("README.md")):
        parts = set(notice.parts)
        if ".venv310" in parts or "__pycache__" in parts or ".git" in parts:
            continue
        try:
            if "作废" in notice.read_text(encoding="utf-8", errors="replace")[:4000]:
                out.append(notice.parent)
        except OSError:
            continue
    return out


def table_algorithms(path):
    """读 CSV 第一列的算法名集合；非 CSV / 读不到返回 None。"""
    p = Path(path)
    if p.suffix.lower() != ".csv" or not p.is_file():
        return None
    import csv
    import io as _io
    with _io.open(p, encoding="utf-8-sig", newline="") as fh:
        rd = csv.reader(fh)
        try:
            next(rd)
        except StopIteration:
            return set()
        return {r[0].strip() for r in rd if r and r[0].strip()}


ROWSET_MARK = re.compile(r"行集=(core4|all10)")


def scan_docs(doc_names=DEFAULT_DOCS):
    checked = anchored = rs_checked = rs_marked = 0
    bad = []
    vdirs = void_dirs()                      # 只发现一次，别每行都遍历仓库
    for name in doc_names:
        p = ROOT / name
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8").splitlines()
        c, a, b = scan_lines(text, name)
        rc, rm, rb = rowset_violations(text, name, vdirs=vdirs)
        checked += c
        anchored += a
        rs_checked += rc
        rs_marked += rm
        bad += b + rb
    return checked, anchored, bad, rs_checked, rs_marked


def render() -> str:
    checked, anchored, bad, rs_checked, rs_marked = scan_docs()
    lines = ["[CITE_SUMMARY] checked=%d anchored=%d | 文档引用核对：%d 条 path:line，"
             "其中 %d 条带 #锚点（其余只判路径与越界）"
             % (checked, anchored, checked, anchored),
             "[ROWSET_SUMMARY] void_refs=%d declared=%d | 作废产物引用：%d 处，其中 %d 处"
             "已声明行集合（core4 / all10）"
             % (rs_checked, rs_marked, rs_checked, rs_marked)]
    for b in bad:
        lines.append("[FAIL]" + b)
    if bad:
        lines.append("[FAIL][SUMMARY] %d broken reference(s) | fix: correct the citation in"
                     " the document, do not weaken this check"
                     " —— 共 %d 条引用失效，按上面的行号回文档里改引用，别改判据"
                     % (len(bad), len(bad)))
    return "\n".join(lines)


def paper_report(argv):
    """把同一把尺子伸进 paper/：**只报不改**（删哪几行是作者权决定）。

    与行集合那条共用 `console/_rowsets.py` 的定义；分类规则见 `console/_paperscan.py`
    —— 相关工作与文献条目算合法，不当缺陷报；表格行/正文主张算待夺。
    """
    try:
        from console import _paperscan
    except ImportError:
        import _paperscan
    text, rows, facts = _paperscan.render(ROOT)
    out = ROOT / _paperscan.OUT_REL
    if "--write" in argv:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(text.encode("utf-8"))
        print("已写 %s（%d 字节，待夺 %d 处 / 合法 %d 处）"
              % (_paperscan.OUT_REL, out.stat().st_size,
                 sum(1 for r in rows if r[1] in _paperscan.NEEDS_DECISION),
                 sum(1 for r in rows if r[1] not in _paperscan.NEEDS_DECISION)))
        return 0
    if not out.is_file():
        print("[FAIL][PAPER_LIST_MISSING] %s | fix: python console/_citations.py"
              " --paper-report --write —— 缺清单，跑上面这条生成" % _paperscan.OUT_REL)
        return 1
    if out.read_text(encoding="utf-8") != text:
        print("[FAIL][PAPER_LIST_STALE] %s differs from what the code recomputes"
              " | fix: python console/_citations.py --paper-report --write"
              " (the paper changed and the list wasn't regenerated, or the list was"
              " hand-edited —— 它禁止手改) —— 论文改了没重生成，或清单被手改"
              % _paperscan.OUT_REL)
        return 1
    if "--verify" in argv:
        print("[PAPER_LIST_MATCH] byte_equal=yes purge_touched_paper=%d"
              " figures_total=%d figures_before_purge=%d | %s 与代码重算逐字节一致"
              "；paper/ 撤除未达=%d 个文件被改过"
              % (facts["purge_touched_paper"], len(facts["figures"]),
                 sum(1 for f in facts["figures"] if f["before_purge"]),
                 _paperscan.OUT_REL.rsplit("/", 1)[-1], facts["purge_touched_paper"]))
        return 0
    print(text)
    return 0


def rewrite_report(argv):
    """提交改写映射表：整张表从对象库现算（`console/_rewrites.py`），表里不许有手抄值。"""
    try:
        from console import _rewrites
    except ImportError:
        import _rewrites
    return _rewrites.main(argv, ROOT)


def csv_census_report(argv):
    """`results/compare/*.csv` 形状普查：份数/列宽/BOM/seed 列全部现算
    （`console/_csvcensus.py`），登记表 R4 那行从此只指路、不抄数。"""
    try:
        from console import _csvcensus
    except ImportError:
        import _csvcensus
    return _csvcensus.main(argv, ROOT)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:  # GBK 控制台上打中文没问题，但打不出来的字符不能把整条命令崩掉
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - 老解释器没有 reconfigure
        pass
    if "--paper-report" in argv:
        return paper_report(argv)
    if "--rewrite-report" in argv:
        return rewrite_report(argv)
    if "--csv-census" in argv:
        return csv_census_report(argv)
    checked, anchored, bad, _rs_checked, _rs_marked = scan_docs()
    if "--list-bad" in argv:
        for b in bad:
            print(b)
    else:
        print(render())
    if "--verify" in argv:
        rc = 1 if bad else 0
        # 同一把尺子也伸到 paper/：清单过期即红。这边只核"清单还是不是代码现在算出来的
        # 那一份"，不核论文正文 —— 删哪几行是作者权决定，不是这道门能替做的。
        prc = paper_report(["--verify"])
        wrc = rewrite_report(["--verify"])
        crc = csv_census_report(["--verify"])
        return rc or prc or wrc or crc
    return 0


if __name__ == "__main__":
    sys.exit(main())
