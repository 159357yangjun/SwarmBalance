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
# —— 字节码纪律（必须在任何本仓 import 之前；解释见 console/test_stale_bytecode.py）——
# .pyc 默认只按 (源 mtime, 源 size) 判过期：两者相符就跑旧字节码，内容对不对没人问。
# 指往一个不存在的目录 = 读必 miss；写由 dont_write_bytecode 挡住，不在树里留东西。
sys.dont_write_bytecode = True
import os as _bc_os, tempfile as _bc_tf, uuid as _bc_ud
sys.pycache_prefix = _bc_os.path.join(_bc_tf.gettempdir(), "swarmbalance-pyc", _bc_ud.uuid4().hex)
README = ROOT / "README.md"

# (README 里的目录标签, 发现起点, 顶层目录, 文件名模式)
#: ⚠ 第三项是 top_level_dir，不是"显示用的名字"——它决定 discover 能不能进得去那个目录：
#:   `frontend/` **没有 __init__.py** ⇒ 以仓库根为顶层时 `discover('frontend', top_level_dir='.')`
#:   会直接抛 `ImportError: Start directory is not importable`（本轮实测），所以它的顶层只能是它自己。
#:   这一条的来历见 docs/P70_invisible_gate_census.md：frontend 的两把 E1 门长期红却从没被跑到，
#:   根因就是本表历史上只列 console/experiments。
#: ⚠ 第四项 pattern 是**根条目逼出来的**：仓库根有 `__init__.py` 的 console/ 与 experiments/ 两个包，
#:   以 root='.' 为顶层做 `discover('.', pattern='test_*.py')` 会把它们递归吃进来 —— 本轮实测
#:   根 + test_*.py = **1 个文件 / 408 个用例**（373+32+3 的双计），而根 + test_build*.py = **1 / 3**。
#:   所以根条目只能吃窄模式；宽模式那条 408 的数字不许出现在任何分母里。
TARGETS = (
    ("test_*.py", "console", "console", "test_*.py"),
    ("test_*.py", "experiments", "experiments", "test_*.py"),
    ("test_*.py", "frontend", "frontend", "test_*.py"),
    ("test_build*.py", ".", ".", "test_build*.py"),
)

LINE_RE = "|".join(re.escape(t[3]) for t in TARGETS)


_CHILD = r'''
import sys, unittest
from pathlib import Path
top = Path(sys.argv[1]); sub = sys.argv[2]; tld = sys.argv[3] if len(sys.argv) > 3 else sub
# pattern 显式入 argv：根条目只能吃窄模式（理由见 TARGETS 上方第二条实测），
# 在这里写死 test_*.py 会让"加了根条目"变成"把 console+experiments 数了两遍"。
pat = sys.argv[4] if len(sys.argv) > 4 else "test_*.py"
files = sorted(p.name for p in (top / sub).glob(pat))
# ⚠ top_level_dir 必须能显式给：`frontend/` 没有 __init__.py，以仓库根为顶层时 discover 直接抛
#   `ImportError: Start directory is not importable`（本轮实测）。历史上这里写死 str(top)，
#   所以即便往 TARGETS 加了 frontend 也只会让本工具自己红 —— 接线要连这里一起改。
suite = unittest.TestLoader().discover(str(top / sub), top_level_dir=str(top / tld), pattern=pat)
def count(s):
    n = 0
    for item in s:
        n += count(item) if isinstance(item, unittest.TestSuite) else 1
    return n
print("%d,%d" % (len(files), count(suite)))
'''


def measure(subdir: str, tld: str = None, pattern: str = "test_*.py"):
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
    proc = subprocess.run([str(vp), "-c", _CHILD, str(ROOT), subdir, tld or subdir, pattern],
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
    #: 行形状 = TARGETS 的字段 + 实测值。加一个 TARGETS 字段就要在这里多带一位 ——
    #:   main() 与 fix() 各自解包，历史上这类"改了配置忘了改解包"是当场 ValueError（本轮实测），
    #:   比静默错位好；但更糟的是它只在使用 --fix/main 时炸，所以 test_readme_counts 走 render_lines
    #:    本身才算真证人。
    out = []
    for label, subdir, tld, pattern in TARGETS:
        nf, nt = measure(subdir, tld, pattern)
        out.append((label, subdir, tld, pattern, nf, nt, "%s 个文件 / %d 个用例" % (nf, nt)))
    return out


#: ⚠ 配对**必须按目录标签，不能按出现顺序**。旧实现是 `zip(claims, rows)`（位置式），
#:   本轮往 README 的 frontend 段加一个计数字位时，它把 experiments 那行顶到第三位 ⇒
#:   verify 报出 "experiments/：README 写 2 个文件 / 19 个用例" —— **那是误配不是漂移**，
#:   而它长得太像真漂移，很容易被下一个人当成"README 数字过期了"直接用 --fix 覆盖掉。
#:   （同一条教训在文档引用上已经付过四次代价：见 docs/P70_invisible_gate_census.md 与登记表 :495。）
#:   ⇒ 现在声明行必须自带目录名，形如 `# console: 51 个文件 / 367 个用例`。
#: ⚠ 目录名捕获放宽到含 `.`：仓库根那一条的标签就是 `.`（README 里写成 `# .: 1 个文件 / 3 个用例`）。
CLAIM_PAT = re.compile(
    r"(?P<prefix>(?P<pat>test_[a-z*]+\.py)\s+#\s*(?P<dir>[a-z_.]+): )"
    r"(?P<nf>\d+)(?P<mid> 个文件 / )(?P<nt>\d+)(?P<tail> 个用例)")


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
    # 按**目录标签**取声明，不再依赖出现顺序（见 CLAIM_PAT 上方那段实测驳回记录）
    claims = {m.group("dir"): (int(m.group("nf")), int(m.group("nt"))) for m in CLAIM_PAT.finditer(text)}

    rows = render_lines()
    problems = []
    # 索引写死三处（r[4]/r[5]）：行形状由 TARGETS 字段数决定，改字段必须同时改这里、
    # measured/OK 行与 fix() 的解包 —— test_readme_counts 走 render_lines，错位会当场炸。
    measured = {r[1]: (r[4], r[5]) for r in rows}
    missing = sorted(set(measured) - set(claims))
    extra = sorted(set(claims) - set(measured))
    if missing:
        problems.append("README 里缺这些目录的计数字位（带目录名那种）：%s" % missing)
    if extra:
        problems.append("README 里有 %s 处计数字位，但 TARGETS 没测它 ⇒ 要么补 TARGETS 要么删该位"
                        % extra)
    for subdir, (nf, nt) in sorted(measured.items()):
        if subdir in claims and claims[subdir] != (nf, nt):
            problems.append("%s/：README 写 %d 个文件 / %d 个用例，实测 %d / %d"
                            % (subdir, claims[subdir][0], claims[subdir][1], nf, nt))
    if problems:
        print("[FAIL] README 测试计数与实测不一致：")
        for p in problems:
            print("  - " + p)
        print("修复：python console/_readme_counts.py --fix 之后复核 diff")
        return 1
    print("[OK] README 测试计数与实测一致（%s）"
          % "；".join("%s=%d文件/%d用例" % (r[1], r[4], r[5]) for r in rows))
    return 0


def fix() -> int:
    """按**目录标签**把每个计数字位换成实测值（不靠出现顺序，理由见 CLAIM_PAT 上方注释）。"""
    rows = render_lines()
    before = line_ending_stats(README)
    for _label, subdir, _tld, _pattern, nf, nt, _txt in rows:
        text = read_text_lossy(README)
        hit = [m for m in CLAIM_PAT.finditer(text) if m.group("dir") == subdir]
        if len(hit) != 1:
            print("[FAIL] README 里 `%s:` 那种计数字位找到 %d 处（应为恰好 1 处）⇒ "
                  "--fix 拒绝猜位置；请在对应目录段补/删成一处" % (subdir, len(hit)))
            return 1
        m = hit[0]
        write_text_lossy(README, text[:m.start()] + "%s%d%s%d%s"
                         % (m.group("prefix"), nf, m.group("mid"), nt, m.group("tail")) + text[m.end():])
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
    for label, subdir, _tld, _pattern, nf, nt, txt in render_lines():
        print("%-14s %s" % (subdir + "/", txt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
