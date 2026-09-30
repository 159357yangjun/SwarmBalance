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

# `路径:行号[#锚点]`；行号支持 单行 / 区间 / 逗号多段
CITE = re.compile(
    r"`([^`\n]*?\.(?:tex|py|csv|json|md|html|ya?ml)):"
    r"(\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)"
    r"(?:#([^`\s]+))?`")
# 登记簿约定：引用已删除的文件时写成 `path:line 已移除@<sha>`，并给出取回命令。
REMOVED = re.compile(r"已移除@([0-9a-f]{7,40})")

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


def scan_lines(lines, origin=""):
    """返回 (引用条数, 带锚点条数, 失效清单)。真文档与合成样本共用同一判据。"""
    checked = anchored = 0
    bad = []
    cache = {}
    for i, line in enumerate(lines, 1):
        for path_txt, spec, anchor in CITE.findall(line):
            checked += 1
            rr = ranges(spec)
            hi = max(b for _, b in rr)
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
            m = REMOVED.search(line)
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


def scan_docs(doc_names=DEFAULT_DOCS):
    checked = anchored = 0
    bad = []
    for name in doc_names:
        p = ROOT / name
        if not p.is_file():
            continue
        c, a, b = scan_lines(p.read_text(encoding="utf-8").splitlines(), name)
        checked += c
        anchored += a
        bad += b
    return checked, anchored, bad


def render() -> str:
    checked, anchored, bad = scan_docs()
    lines = ["文档引用核对：%d 条 path:line，其中 %d 条带 #锚点（其余只判路径与越界）"
             % (checked, anchored)]
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
    checked, anchored, bad = scan_docs()
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
