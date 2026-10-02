# -*- coding: utf-8 -*-
r"""两种"套件输出采集方式"之间**信息有没有丢**的那把尺子（唯一一份实现）。

为什么要有它：`release_check` 把"父进程跑 discover + 子进程再跑一遍拿 skip"合成一遍之后，
所有关于"没丢东西"的话都只是我说。上一轮就是教训 —— 合批顺手把 `warnings="default"` 漏掉了，
`ResourceWarning` 整类被静音（实测改前 939 行、改后 43 行），而套件**照样全绿**。
所以"采集方式换了、输出等价吗"必须是一个能跑的核对，而不是一段证不了也假不了的话。

三条口径写在这里，免得下一个人以为判据是随手定的：
- **两侧同尺**：归一化规则（下面 `RULES`）对 A/B 一视同仁；规则只做"同一信息的不同写法"，
  不做"把看着不顺的剔掉"。每加一条规则都要能说清它抹平的是哪个字节差。
- **进度点不入集合**：一条 warning 会把点串和正文挤在同一行 ⇒ 行边界不同、内容相同。
  点串按**行首连续进度符**识别（必须含 `.`，或整行都是进度符，否则 `FAILED` 开头那个 `F`
  会被数成一个点），单独用恒等式 `点总数 == testsRun`（两侧各自）+ `两侧点总数相等` 来证，
  不成立就整轮作废（`[AB_DOTS_MISMATCH]`）。识别规则被判歪的后果是恒等式响，不是悄悄放行。
- **残差必须具名**：`only_before` 里每一条都要能被点名。要么补回来，要么说清它不可达、
  为什么。"数量差不多"不算结论。

A 面 = 合并前 `release_check` 用的那条命令（`python -m unittest discover -s console`，
`_run` 收 `stdout+stderr`）；B 面 = 现在的 `_preflight.run_console_suite()["detail"]`
（哨兵解析与三路合一都复用 `_preflight`，不在这里抄第二份）。

失败短码（GBK 控制台上中文会变 ??????，判定信息一律带 ASCII 码）：
    [AB_NO_SENTINEL]   B 面 stdout 里没有哨兵行 —— 采集器换过格式，比对作废
    [AB_NO_TESTS_RUN]  某一面没印出 `Ran N tests`，恒等式无从成立
    [AB_DOTS_MISMATCH] 点串切分与 testsRun 对不上，尺子本身不可信
    [AB_RANGE]         可比单元少于下限（= 两侧里有一侧几乎啥都没有，比对是空转）
    [ABLATION_VACUOUS] 这一份取证上根本没有可回归的 warning，M1 比不出差别

`--ablate` 的退出码分三态，别把 2 读成 0：0 = 两个消融都咬到；1 = 有一个没咬到；
2 = M1 在这份取证上无从咬（A 面带出处 warning=0），只有 M2 咬到 —— 不是"没问题"。

用法：
    python console/_suite_ab.py --capture <目录>   # 真跑 A/B 两面（各约 1 分钟），落原样取证
    python console/_suite_ab.py --compare <目录>   # 只比不跑，吃已有取证
    python console/_suite_ab.py --ablate <目录>    # 判别式：M1 静音 warning / M2 丢 stdout，
                                                   # 两种已知回归都必须被报成 only_before>0
"""
from __future__ import annotations

import io
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "console"))
import _preflight as PF                           # noqa: E402

LEAD_DOTS = re.compile(r"^[.sxFE]+")        # unittest 的进度符只会出现在一段流的最前面
PURE_DOTS = re.compile(r"^[.sxFE]+$")       # 整行只有进度符
WARN_EMIT = re.compile(r"^(?P<loc>.*?:\d+): (?P<cls>[A-Z]\w*Warning): ")   # 带出处的发射行

# 每条规则抹平的是哪个字节差（顺序有意义：先换分隔符，再匹绝对路径）
RULES = [
    ("runner-timing", re.compile(r"in \d+\.\d+s"), "in Ts",
     "同一句 `Ran N tests in 0.5s`，两次跑的秒数不同"),
    ("pkg-prefix", re.compile(r"\bconsole\.(test_)"), r"\1",
     "discover 起头的 id 不带包名、子进程 loader 起的带 `console.`，是同一条用例"),
    ("pf-tempdir", re.compile(r"pf-capture-\w+"), "pf-capture-TMP",
     "探针临时目录名每次随机"),
    ("path-sep", re.compile(r"\\+"), "/",
     "Windows 路径在 repr 里是双反斜杠、在正文里是单反反斜杠"),
    ("abs-root", re.compile(r"(?i)C:/Users/yyyy/AppData/Roaming/TRAE SOLO CN/ModularData/ai-agent"
                            r"/work-mode-projects/6a91893e4cc261f69a0a52a0/drone-scheduling"),
     "ROOT", "仓的绝对路径写进了 warning 出处，与仓名无关"),
    ("cost-ms", re.compile(r"cost_ms=\d+(\.\d+)?"), "cost_ms=N",
     "门自己印的耗时，每次不同"),
]

FLOOR = 20                                  # 可比单元下限：低于它就是有一侧空了，比对在空转


def read(path):
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def join_streams(stdout_text, stderr_text):
    """A 面（改前那条命令）收到的就是 `stdout+stderr` 两段。

    中间必须补一个换行：探针夹具里有一条**不带换行**的 stdout print，直接相接会和
    stderr 的第一行（进度点行）粘成一行 ⇒ 点串数不出来、恒等式响在量具自己身上。
    实测过：`{"PFMARK-GLUE-003": "no newline"}....F.` 就是这么造出来的。
    B 面不存在这个问题 —— 三路合一时有 `[stderr]` 标头隔开。
    """
    a, b = stdout_text or "", stderr_text or ""
    if not a.strip():
        return b
    if not b.strip():
        return a
    return a.rstrip("\n") + "\n" + b


def merge_b(stdout_text, stderr_text, keep_stdout=True):
    """B 面的三路合一 —— 复用 `_preflight`，不在此抄第二份解析。"""
    payload, rest = PF.split_sentinel(stdout_text)
    if payload is None:
        raise AssertionError("[AB_NO_SENTINEL] B 面 stdout 里没有哨兵行，采集器换过格式")
    return PF.merge_detail(payload, rest, stderr_text, keep_stdout=keep_stdout)


def units(text, side):
    """切成可比单元：行首的进度符串折成计数、不入集合；采集器自己的段标头具名保留。

    为什么按"行首"而不是按"长度阈值"：一条 warning 会把点串拦腰截断（实测 A 面点串是
    `..F.` + 正文），而小套件的点串只有 1~4 个字符 —— 用"够长才算"会把它当正文，
    于是 `点总数 == testsRun` 恒等式响在量具自己身上（探针夹具第一轮就是这么红的）。
    行首进度符串必须**含 `.`** 或整行都是进度符才认，否则 `FAILED (failures=1)` 的开头
    那个 `F` 会被当成一个点。误判的后果是恒等式红，不是悄悄放行。
    """
    out, dot_total, dot_runs = [], 0, 0
    for raw in (text or "").splitlines():
        line = raw.rstrip("\r\n")
        if side == "b" and line.startswith(PF._CHILD_MARK):
            continue
        if side == "b" and line.strip() in ("[stdout]", "[stderr]"):
            out.append("<section-header>")
            continue
        m = LEAD_DOTS.match(line)
        if m and ("." in m.group(0) or PURE_DOTS.match(line)):
            dot_total += len(m.group(0))
            dot_runs += 1
            line = line[m.end():]
            if not line.strip():
                continue
        t = line.strip()
        for _n, rx, rep, _why in RULES:
            t = rx.sub(rep, t)
        if t:
            out.append(t)
    return out, dot_total, dot_runs


def ran_tests(text, side):
    m = re.search(r"^Ran (\d+) tests? in", text, re.M)
    if not m:
        raise AssertionError("[AB_NO_TESTS_RUN] %s 面没印出 `Ran N tests`，恒等式无从成立" % side)
    return int(m.group(1))


def compare(a_text, b_text, require_identity=True, floor=FLOOR):
    a_u, a_dot, a_runs = units(a_text, "a")
    b_u, b_dot, b_runs = units(b_text, "b")
    a_tests, b_tests = ran_tests(a_text, "A"), ran_tests(b_text, "B")
    if min(len(a_u), len(b_u)) < floor:
        raise AssertionError("[AB_RANGE] 可比单元 A=%d B=%d，低于下限 %d —— 有一侧几乎空了，"
                             "这时候报 only_before=0 是假的" % (len(a_u), len(b_u), floor))
    ca, cb = Counter(a_u), Counter(b_u)
    only_a, only_b = ca - cb, cb - ca
    ident = (a_dot == a_tests and b_dot == b_tests and a_dot == b_dot)
    if require_identity and not ident:
        raise AssertionError("[AB_DOTS_MISMATCH] A 点=%d/tests=%d, B 点=%d/tests=%d —— "
                             "点串切分与 testsRun 对不上，尺子不可信，本次比对作废"
                             % (a_dot, a_tests, b_dot, b_tests))
    return {
        "raw_before": len((a_text or "").splitlines()),
        "raw_after": len((b_text or "").splitlines()),
        "units_before": len(a_u), "units_after": len(b_u),
        "only_before": sum(only_a.values()), "only_after": sum(only_b.values()),
        "common": sum((ca & cb).values()),
        "dots_before": a_dot, "dots_before_runs": a_runs,
        "dots_after": b_dot, "dots_after_runs": b_runs,
        "tests_a": a_tests, "tests_b": b_tests, "identity": ident,
        "only_before_items": sorted(only_a.items()),
        "only_after_items": sorted(only_b.items()),
    }


def _line(tag, r):
    print("[%s] only_before=%d only_after=%d common=%d units=%d/%d raw=%d/%d "
          "dots=%d/%d runs=%d/%d tests=%d/%d identity=%s"
          % (tag, r["only_before"], r["only_after"], r["common"],
             r["units_before"], r["units_after"], r["raw_before"], r["raw_after"],
             r["dots_before"], r["dots_after"], r["dots_before_runs"], r["dots_after_runs"],
             r["tests_a"], r["tests_b"], r["identity"]))


def _named(r, limit=80):
    for k, n in r["only_before_items"][:limit]:
        print("  [ONLY_BEFORE] x%d %s" % (n, k[:150].encode("ascii", "replace")))
    for k, n in r["only_after_items"][:limit]:
        print("  [ONLY_AFTER] x%d %s" % (n, k[:150].encode("ascii", "replace")))


def _save(d, name, text):
    with io.open(Path(d) / name, "w", encoding="utf-8") as fh:
        fh.write(text or "")


def capture(d, cwd=None):
    """跑 A/B 两面各一次，四份原样输出落进 <目录>。"""
    cwd = Path(cwd or ROOT)
    env = PF.isolated_env()
    a = subprocess.run([sys.executable, "-m", "unittest", "discover",
                        "-s", "console", "-p", "test_*.py"],
                       cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    _save(d, "a_stdout.txt", a.stdout)
    _save(d, "a_stderr.txt", a.stderr)
    b = subprocess.run([sys.executable, "-c", PF._CHILD_SKIP, str(cwd)],
                       cwd=str(cwd), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    _save(d, "b_stdout.txt", b.stdout)
    _save(d, "b_stderr.txt", b.stderr)
    print("[RUN_A] rc=%d out=%d err=%d | [RUN_B] rc=%d out=%d err=%d"
          % (a.returncode, len((a.stdout or "").splitlines()), len((a.stderr or "").splitlines()),
             b.returncode, len((b.stdout or "").splitlines()), len((b.stderr or "").splitlines())))
    return 0


def _compare_dir(d):
    d = Path(d)
    a_text = join_streams(read(d / "a_stdout.txt"), read(d / "a_stderr.txt"))
    r = compare(a_text, merge_b(read(d / "b_stdout.txt"), read(d / "b_stderr.txt")))
    _line("AB_REAL", r)
    _named(r)
    if r["only_before"] or r["tests_a"] != r["tests_b"]:
        print("[AB_FAIL] 现采集方式仍有丢失（only_before=%d）或用例数不一致（%d/%d）"
              % (r["only_before"], r["tests_a"], r["tests_b"]))
        return 1
    print("[AB_PASS] 零丢失；改后独有的 %d 条已具名（采集器自己的段标头，不是内容）"
          % r["only_after"])
    return 0


def _bite(tag, a_text, b_text):
    """跑一次消融比对，并把"尺子当场拒绝比对"也算成有牙。

    为什么 `[AB_RANGE]` 算证据而不是算炸：丢掉一整路输出之后，B 面可能塌到只剩进度点与
    裁决行（本轮真套件实测只剩 3 个可比单元），范围下限直接拒比 —— 那正是"信息没了"的形状，
    比报一个 only_before 更大声。拒比若不当成有牙，我就会把"炸了"读成"没回归"。
    """
    try:
        r = compare(a_text, b_text, require_identity=False)
    except AssertionError as exc:
        code = str(exc).split("]")[0].lstrip("[") or "AB_ERROR"
        print("[%s] refused=[%s] %s" % (tag, code, str(exc)[:200].encode("ascii", "replace")))
        return None, code
    _line(tag, r)
    _named(r, limit=12)
    return r, ""


def ablate(d, cwd=None):
    """判别式：尺子必须咬得住两类**真实发生过**的回归，否则它的 0 不值得信。

    M1 在内存里改子进程脚本（去掉 `warnings="default"`），不落盘、不碰仓里任何文件；
    M2 复用已取证的 B 原样三路，只在父侧丢掉 stdout 那一路 —— 不重跑，省一半时间。
    """
    d = Path(d)
    cwd = str(Path(cwd or ROOT))
    a_text = join_streams(read(d / "a_stdout.txt"), read(d / "a_stderr.txt"))
    b_stdout, b_stderr = read(d / "b_stdout.txt"), read(d / "b_stderr.txt")

    mut = PF._CHILD_SKIP.replace('warnings="default"', '')
    if mut == PF._CHILD_SKIP:
        print("[ABLATION_NOOP] M1 的替换没生效（子进程脚本里已不写这个开关），尺子的牙未证")
        return 1
    m = subprocess.run([sys.executable, "-c", mut, cwd], cwd=cwd,
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=PF.isolated_env())
    r1, c1 = _bite("AB_M1_no_warnings_default", a_text, merge_b(m.stdout, m.stderr))
    r2, c2 = _bite("AB_M2_no_stdout", a_text,
                   merge_b(b_stdout, b_stderr, keep_stdout=False))

    # M1 有没有牙，还取决于 A 面**本来**存不存在带出处的 warning：本轮真套件把漏句柄都修完之后
    # 两侧都是 0 条，`only_before=0` 就不再是证据（那是"没有东西可丢"，不是"没丢"）。
    # 所以这里先印 A 面的普查数，为 0 就明写空转并指出去哪儿看非空转的证明。
    located_a = sum(1 for ln in (a_text or "").splitlines() if WARN_EMIT.match(ln.strip()))
    bit1 = (r1["only_before"] > 0) if r1 else c1 == "AB_RANGE"
    bit2 = (r2["only_before"] > 0) if r2 else c2 == "AB_RANGE"
    if located_a == 0:
        bit1 = "vacuous"
    print("[AB_VERDICT] a_located_warnings=%d m1_bit=%s m2_bit=%s" % (located_a, bit1, bit2))
    if located_a == 0:
        print("[ABLATION_VACUOUS] A 面带出处 warning=0 —— M1 在这一份取证上比不出差别（不是没回归，"
              "是没东西可回归）。非空转的 M1 证据在 `console/test_suite_ab.py` 的夹具里"
              "（故意漏一个句柄，报 `[SA_M1] only_before>0`），夹具随 discover 与 release_check 跑。"
              "退出码给 2、不给 0：这一路确实没在本目录证成。")
        return 2 if bit2 else 1
    return 0 if (bit1 and bit2) else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        print("[AB_USAGE] --capture <目录> | --compare <目录> | --ablate <目录>")
        return 2
    cmd = argv[0]
    if len(argv) < 2:
        print("[AB_USAGE] %s 需要一个目录参数" % cmd)
        return 2
    target = argv[1]
    Path(target).mkdir(parents=True, exist_ok=True)
    if cmd == "--capture":
        return capture(target)
    if cmd == "--compare":
        return _compare_dir(target)
    if cmd == "--ablate":
        return ablate(target)
    print("[AB_USAGE] 不认识的子命令：%s" % cmd)
    return 2


if __name__ == "__main__":
    sys.exit(main())
