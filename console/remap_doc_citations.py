# -*- coding: utf-8 -*-
"""按 diff 重映射文档里的 `path:line` 引用 —— 用于代码行号漂移后修引用。

为什么要有它：本轮两次人肉搬动登记表引用（Phase 1A 一次、1B-1 一次），每次都要对着
锚点文本猜新行号；而 `total_swap_sessions` 这类锚点在文件里有 6 个候选，猜会猜错。
diff opcode 给出的是可证的旧→新映射，比"看起来最近的那行"可靠。

⚠️ 两条必须遵守的边界（都是我第一版踩过之后补上的）：
1. **带 `已失效@<sha>` / `已移除@<sha>` 的历史引用不参与平移。** 它们的行号锚定在指定
   revision 内（例如 `environment.py:268#具有高度信息的建筑物 (revision 66016b7^)`），
   当前文件的插入/删除与它无关。第一版我把三条历史引用一起平移了 ⇒ 门立刻红，
   而正确的修法不是"再手改回去"，是让工具认识这个类别。
2. 只平移有唯一映射的行；映射缺失就报出来交给人，绝不猜一个数写进去。

用法：
    python -X utf8 console/remap_doc_citations.py <doc.md> [<doc2.md> ...] [--write]
不带 --write 时只打印将要发生的改动（dry-run）。
"""
from __future__ import annotations

import argparse
import collections
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
CITE = re.compile(r"`([^`\n]*?\.(?:py|md|json|csv|yaml|tex|html)):(\d+(?:-\d+)?)(#[^`\s]*)?`")
HISTORY_MARK = re.compile(r"(已失效@|已移除@)")


def _lines_at(rev: str, rel: str):
    r = subprocess.run(["git", "show", "%s:%s" % (rev, rel)], cwd=str(REPO),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return None if r.returncode else r.stdout.splitlines()


def mapping(rel: str):
    """HEAD 版本 → 工作树版本 的行号映射。

    只用 equal 块（旧第 i 行 == 新第 j 行）建立对应；insert/delete **不产生任何映射**。
    第一版我给 insert 也写了映射（`m[i1] = j1 + (j2-j1)`），后果是把"插入点附近本来就存在
    的行"也算了一次位移 ⇒ dry-run 报出 212→218、833→839 这种错值，而这些行的当前值才是对的
    （实测：212 行就是 `self.total_swap_sessions = 0`）。宁可报"无法定位"交给人，也不猜。
    """
    old = _lines_at("HEAD", rel)
    p = REPO / rel
    if old is None or not p.is_file():
        return None
    new = p.read_text(encoding="utf-8").splitlines()
    import difflib
    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    m = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                m[i1 + k + 1] = j1 + k + 1
    return m


def remap(doc: pathlib.Path, verify_anchor=True):
    """把文档里的 path:line 按 HEAD→工作树 的 diff 平移。

    ⚠️ 用前必读的两条前提（都是我这一轮踩过的）：
     1. **只能对"尚未修过引用"的文档跑一次。** 它的基准是 `git show HEAD:<file>`，
        所以若文档已经指向工作树的新行号，再跑一次就会【重复平移】—— 表现为
        833→839 这种看着合理实则错误的结果（门当时是绿的，因为文档本来就对了）。
        安全做法：先 --dry-run，再逐条对照锚点文本是否真的落在目标行上，最后 --write。
     2. 带 `已失效@sha` / `已移除@sha` 的历史引用不参与平移（见 HISTORY_MARK）：它们的行号
        锚定在指定 revision 内，与当前文件无关。第一版我把三条历史引用一起平移了。
    """
    text = doc.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    caches = {}
    changes = []
    skipped_history = 0
    unresolved = []
    rejected = []
    out = []
    for lineno, line in enumerate(lines, 1):
        # 历史引用整行跳过：它的行号属于某个 revision，不随当前文件漂移
        if HISTORY_MARK.search(line):
            skipped_history += line.count("`") // 2
            out.append(line)
            continue

        def repl(mt):
            nonlocal skipped_history
            rel = mt.group(1)
            spec = mt.group(2)
            anchor = mt.group(3) or ""
            if rel not in caches:
                caches[rel] = mapping(rel)
            m = caches[rel]
            if m is None:
                unresolved.append("%s:%s (无 HEAD 或文件缺失)" % (rel, spec))
                return mt.group(0)
            parts = spec.split("-")
            try:
                mapped = [m.get(int(x)) for x in parts]
            except ValueError:
                return mt.group(0)
            if any(v is None for v in mapped):
                unresolved.append("%s:%s%s" % (rel, spec, anchor))
                return mt.group(0)
            new_spec = "-".join(str(v) for v in mapped)
            # 锚点自证：目标行必须真的含锚点词，否则说明这次平移是错的（例如对已修好的
            # 文档重复跑一次）。宁可跳过并点名，也不写进一个"看起来合理"的错行号。
            if anchor and verify_anchor:
                rel_path = REPO / rel
                if rel_path.is_file():
                    body = rel_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    word = anchor.lstrip("#")
                    ok = all(1 <= v <= len(body) and word in body[v - 1] for v in mapped)
                    if not ok:
                        rejected.append("%s:%s%s -> %s（目标行不含锚点词，判为误平移，未采纳）"
                                        % (rel, spec, anchor, new_spec))
                        return mt.group(0)
            if new_spec != spec:
                changes.append((lineno, rel, spec, new_spec, anchor.strip("#")))
            return "`%s:%s%s`" % (rel, new_spec, anchor)

        out.append(CITE.sub(repl, line))
    return "".join(out), changes, unresolved, skipped_history, rejected


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("docs", nargs="+")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    total = 0
    per_doc = collections.Counter()
    problems = []
    for d in args.docs:
        p = (REPO / d) if not pathlib.Path(d).is_absolute() else pathlib.Path(d)
        if not p.is_file():
            print("[MISSING_DOC] %s" % p)
            return 2
        new_text, changes, unresolved, skipped, rejected = remap(p)
        total += len(changes)
        per_doc[p.name] = len(changes)
        for ln, rel, a, b, anc in changes:
            print("  %s:%d  %s:%s -> %s  #%s" % (p.name, ln, rel, a, b, anc))
        if unresolved:
            print("  [UNRESOLVED] %s: %s" % (p.name, "; ".join(unresolved)))
            problems.extend(unresolved)
        for j in rejected:
            print("  [REJECTED_MISALIGN] %s" % j)
        skipped_note = " 跳过历史引用行=%d" % skipped if skipped else ""
        print("[%s] 采纳改动=%d%s（另有 %d 条因锚点不自证被拒绝）"
              % (p.name, len(changes), skipped_note, len(rejected)))
        if args.write:
            p.write_text(new_text, encoding="utf-8", newline="\n")
    if problems:
        print("[UNRESOLVED_REMAIN] %d 条无法由 diff 唯一定位 ⇒ 未改动，需人工处理" % len(problems))
        return 1
    print(("已写" if args.write else "dry-run"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
