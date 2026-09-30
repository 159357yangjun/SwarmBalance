# -*- coding: utf-8 -*-
"""README 目录树里的测试文件数 / 用例数必须是**跑出来的**，并带 --verify 比对。

为什么（本轮实测）：README:283 手写"7 个文件 / 74 个用例"，而真实是 15 个文件 / 128 个用例；
:316 手写"2 个文件 / 21 个用例"，真实是 4 个文件 / 24 个。手工抄的计数一定会漂，
而且漂的时候没有任何东西报警 —— 与"报告里把 /tmp 探针产物的哈希当成主产物哈希"同形。

用法：
    python console/_readme_counts.py            # 打印应该写成什么
    python console/_readme_counts.py --verify   # 与 README 现状比对，不一致 exit 1
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"

# (README 里的目录标签, 发现起点, 顶层目录)
TARGETS = (
    ("test_*.py", "console", "console"),
    ("test_*.py", "experiments", "experiments"),
)

LINE_RE = "|".join(re.escape(t[0]) for t in TARGETS)


_CHILD = r'''
import sys, unittest
from pathlib import Path
top = Path(sys.argv[1]); sub = sys.argv[2]
files = sorted(p.name for p in (top / sub).glob("test_*.py"))
suite = unittest.TestLoader().discover(str(top / sub), top_level_dir=str(top), pattern="test_*.py")
def count(s):
    n = 0
    for item in s:
        n += count(item) if isinstance(item, unittest.TestSuite) else 1
    return n
print("%d,%d" % (len(files), count(suite)))
'''


def measure(subdir: str):
    """返回 (测试文件数, 用例数) —— **必须在项目 venv 解释器下量**。

    为什么不能就地量：缺依赖的解释器（如系统 Anaconda）里，那些测试模块在导入期就
    整模块 skip，它们的用例根本不进计数 —— 同一条命令在两个解释器下会得到 130 与 77。
    一个随解释器漂的数字没法当"实测真值"，所以固定用 venv 解释器子进程来量，
    谁跑这条命令都得到同一个数。venv 不存在时直接报错，绝不退化成"用当前解释器凑数"。
    """
    import subprocess

    vp = _venv_python()
    if vp is None:
        raise RuntimeError("找不到项目 .venv310 解释器，无法给出解释器无关的用例数；"
                           "请先按 README 建 venv，或修 TARGETS 指向实际环境")
    # 缓存隔离只有一份实现（console/_preflight.py）：这个数是 README 里那两处计数的真值来源，
    # 若它读到过期的 .pyc，报出来的就是"盘上不存在的代码"的用例数。
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _preflight import isolated_env
    proc = subprocess.run([str(vp), "-c", _CHILD, str(ROOT), subdir],
                          cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=isolated_env())
    if proc.returncode != 0:
        raise RuntimeError("在 %s 下测量失败：\n%s" % (vp, (proc.stderr or "")[-600:]))
    nf, nt = proc.stdout.strip().splitlines()[-1].split(",")
    return int(nf), int(nt)


# 项目正式解释器（与 console/_preflight.py、run_tests.bat 的探测顺序一致）。
# 这里内联而不 import _preflight：本文件要能被 `python console/_readme_counts.py`
# 直接跑，那时 sys.path[0] 是 console/ 而不是仓库根，`from console import ...` 会失败。
VENV_CANDIDATES = (
    ROOT.parent / ".venv310" / "Scripts" / "python.exe",
    ROOT / ".venv310" / "Scripts" / "python.exe",
)


def _venv_python():
    for c in VENV_CANDIDATES:
        if c.is_file():
            return c
    return None


def render_lines():
    out = []
    for label, subdir, _ in TARGETS:
        nf, nt = measure(subdir)
        out.append((label, subdir, nf, nt, "%s 个文件 / %d 个用例" % (nf, nt)))
    return out


COUNT_PAT = re.compile(r"(test_\*\.py\s+#\s*)(\d+)( 个文件 / )(\d+)( 个用例)")


def read_text_lossy(path: Path) -> str:
    """读成文本但**保留原始行尾**（不用 read_text：它会把 \\r\\n 折成 \\n）。"""
    return path.read_bytes().decode("utf-8")


def write_text_lossy(path: Path, text: str) -> None:
    """按字节写回（不用 write_text：Windows 下它会把 \\n 翻译回 \\r\\n，
    于是对 LF 检出的工作副本做一次 --fix 就把整份文件的行尾翻掉）。"""
    path.write_bytes(text.encode("utf-8"))


def line_ending_stats(path: Path):
    return line_ending_stats_from_bytes(path.read_bytes())


def line_ending_stats_from_bytes(raw: bytes):
    """(CRLF 数, 裸 LF 数) —— 用来证明"只改数字"没有顺手翻行尾。"""
    crlf = raw.count(b"\r\n")
    return crlf, raw.count(b"\n") - crlf


def verify() -> int:
    text = read_text_lossy(README)
    claims = [(int(m.group(2)), int(m.group(4))) for m in COUNT_PAT.finditer(text)]

    rows = render_lines()
    problems = []
    if len(claims) != len(rows):
        problems.append("README 里有 %d 处计数字位，实测了 %d 个目录 —— 对不上"
                        % (len(claims), len(rows)))
    for (cn, ct), (_label, subdir, nf, nt, _t) in zip(claims, rows):
        if (cn, ct) != (nf, nt):
            problems.append("%s/：README 写 %d 个文件 / %d 个用例，实测 %d / %d"
                            % (subdir, cn, ct, nf, nt))
    if problems:
        print("[FAIL] README 测试计数与实测不一致：")
        for p in problems:
            print("  - " + p)
        print("修复：python console/_readme_counts.py --fix 之后复核 diff")
        return 1
    print("[OK] README 测试计数与实测一致（%s）"
          % "；".join("%s=%d文件/%d用例" % (r[1], r[2], r[3]) for r in rows))
    return 0


def fix() -> int:
    """按 README 中出现顺序，把每个计数字位换成实测值。

    每轮重新扫描并按偏移替换，避免"上一处替换改变文本长度导致下一处偏移"。
    """
    rows = render_lines()
    before = line_ending_stats(README)
    for pos, (_, _subdir, nf, nt, _txt) in enumerate(rows):
        text = read_text_lossy(README)
        matches = list(COUNT_PAT.finditer(text))
        if pos >= len(matches):
            print("[WARN] README 里第 %d 处计数字位不存在，跳过" % (pos + 1))
            continue
        m = matches[pos]
        write_text_lossy(README, text[:m.start()] + "%s%d%s%d%s"
                         % (m.group(1), nf, m.group(3), nt, m.group(5)) + text[m.end():])
    after = line_ending_stats(README)
    if before != after:
        print("[FAIL] --fix 改动了行尾（%s → %s），这会把整份文件显示成已修改" % (before, after))
        return 1
    return verify()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--fix", action="store_true")
    args = ap.parse_args(argv)
    if args.fix:
        return fix()
    if args.verify:
        return verify()
    for label, subdir, nf, nt, txt in render_lines():
        print("%-14s %s" % (subdir + "/", txt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
