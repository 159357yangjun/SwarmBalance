# -*- coding: utf-8 -*-
"""文档里的 `路径:行号` 引用必须翻得到东西 —— 这个文件是那道判据的唯一实现。

为什么要有独立文件（而不是只写在用例里）：`skipped=12` 那轮的教训是
**判据跑出来的数字要印在纸上**，不能只在红的时候才看得见。引用门禁同理：
"扫到 70 条、其中 61 条带锚点" 这个覆盖率本身决定了这道门能看见多少 ——
只有用例红时才打印，等于平时没人知道自己被半盲的门放过了。

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
    python console/_citations.py --verify       # 有失效则退出码 1
    python console/_citations.py --list-bad     # 只列失效行
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
                bad.append("%s:%d 作废产物 %s 被引用却没声明行集合：紧跟写 `行集=core4`"
                           "（只取 4 个核心算法）或 `行集=all10`（含 6 个已撤除）；"
                           "两种读数的差异见 results/compare/plots/ROW_SETS.md"
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
                    bad.append("%s:%d %s 声明 `行集=all10`，但表里的算法集合实际是 %s ——"
                               " 表已重生或本就不是 10 行，这个作废标注过期了"
                               % (origin, i, rel, sorted(algs)))
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
                    bad.append("%s:%d 标了已失效@%s，但 `git show %s^:%s` 取不回来"
                               % (origin, i, obs.group(1), obs.group(1), path_txt))
                    continue
                if hi > len(blob):
                    bad.append("%s:%d 引用 %s:%s（已失效@%s 之前），但该修订只有 %d 行"
                               % (origin, i, path_txt, spec, obs.group(1), len(blob)))
                elif anchor:
                    anchored += 1
                    joined = "\n".join(l for (a, b) in rr for l in blob[a - 1:b])
                    if anchor not in joined:
                        bad.append("%s:%d 引用历史 %s:%s#%s（已失效@%s），"
                                   "但那个修订的对应行里没有锚点 —— 行号可能是手抄时就已经错了。"
                                   " 实际内容：%s"
                                   % (origin, i, path_txt, spec, anchor, obs.group(1),
                                      joined.strip().replace("\n", " / ")[:160]))
                else:
                    bad.append("%s:%d 用 已失效@%s 引历史行号却不带 #锚点：%s:%s"
                               " —— 历史行号没法跟磁盘比，只有锚点能证明它当时真的对过"
                               % (origin, i, obs.group(1), path_txt, spec))
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
                    bad.append("%s:%d 引用 %s:%s，但同名文件最长只有 %d 行"
                               % (origin, i, path_txt, spec, longest))
                    continue
                if anchor:
                    anchored += 1
                    blob = "\n".join(l for (a, b) in rr for l in hit[a - 1:b])
                    if anchor not in blob:
                        bad.append(
                            "%s:%d 引用 %s:%s#%s，但那些行里找不到锚点 `%s`"
                            "（行号在范围内却指向别处，正是纯行号门禁看不见的一类）"
                            " 实际内容：%s"
                            % (origin, i, path_txt, spec, anchor, anchor,
                               blob.strip().replace("\n", " / ")[:160]))
                continue
            m = REMOVED.search(tail)
            if not m:
                bad.append("%s:%d 引用了找不到的文件 %s（若该文件已删除，"
                           "请按约定写成 `path:line 已移除@<sha>` 并附取回命令）"
                           % (origin, i, path_txt))
                continue
            blob = git_show_text(m.group(1), path_txt.replace("\\", "/"))
            if blob is None:
                bad.append("%s:%d 标了已移除@%s，但 `git show %s^:%s` 取不回来"
                           % (origin, i, m.group(1), m.group(1), path_txt))
                continue
            if hi > len(blob):
                bad.append("%s:%d 引用 %s:%s，但该修订只有 %d 行"
                           % (origin, i, path_txt, spec, len(blob)))
            elif anchor:
                anchored += 1
                joined = "\n".join(l for (a, b) in rr for l in blob[a - 1:b])
                if anchor not in joined:
                    bad.append("%s:%d 引用历史 %s:%s#%s，但取回的正文里找不到锚点"
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
    lines = ["文档引用核对：%d 条 path:line，其中 %d 条带 #锚点（其余只判路径与越界）"
             % (checked, anchored),
             "作废产物引用：%d 处，其中 %d 处已声明行集合（core4 / all10）"
             % (rs_checked, rs_marked)]
    for b in bad:
        lines.append("[FAIL] " + b)
    if bad:
        lines.append("共 %d 条引用失效 —— 按上面的行号回到文档里改引用，别改判据" % len(bad))
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    try:  # GBK 控制台上打中文没问题，但打不出来的字符不能把整条命令崩掉
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - 老解释器没有 reconfigure
        pass
    checked, anchored, bad, _rs_checked, _rs_marked = scan_docs()
    if "--list-bad" in argv:
        for b in bad:
            print(b)
    else:
        print(render())
    if "--verify" in argv:
        return 1 if bad else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
