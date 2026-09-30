# -*- coding: utf-8 -*-
r"""非 raw 字符串里的非法转义（`"\cite"` 那一类）是常驻判据，不是本轮的一次性普查。

这条门自己的文档里就写着 `\cite`，所以它必须是 raw —— 它是这条判据的第一个"活样本"：
写成人话时差点把自己判红（第一版就是非 raw 的 docstring，跑自己就被自己抓了）。

为什么必须自己 compile、而不是拿 `-W error` 或"import 没喷"当证据
（下面每一格都实测过；实测环境写在括号里，别把某一行当通用结论）：

    机制                                        Python 3.10.11            Python 3.13.5
    警告类别名                                  DeprecationWarning         SyntaxWarning
    compile() + catch_warnings(record=True)     裸进程：**0 条**            裸进程：1 条
    同上 + simplefilter("always")               裸进程：1 条                裸进程：1 条
    同上，但在 unittest 进程里、不加 simplefilter  1 条（unittest 自己插了滤镜） 1 条
    `python -W error` 跑 compile                退出码 1                   退出码 1
    同一模块**第二次 import**（吃 .pyc 缓存）    0 条                       0 条

⇒ 四条结论，分清哪条被变异证明过、哪条只是推理：
① **按类别过滤是瞎的**（3.10 抛 Deprecation、3.12+ 才升成 SyntaxWarning）。判据只看消息文本
   `invalid escape sequence`。**这条被变异证明过**：把匹配改成
   `issubclass(x.category, SyntaxWarning)` 后，本模块 3 条里有 2 条当场变红
   —— 也就是本轮我真犯过的错（第一遍普查按 SyntaxWarning 过滤，报了"0 命中"，
   被别人在自己解释器上跑出的一行推翻）。
② `simplefilter("always")` 挡的是**环境**：裸进程/别的滤镜下不加它就 0 条（见表第 3 行 vs 第 5 行）。
   **诚实标注：这条没被变异证明**——把 `simplefilter` 摘掉后，本用例在 unittest 进程里仍全绿
   （因为 unittest 默认给 DeprecationWarning 开了滤镜）。所以它是一道保险，不是被判据抓到的 bug；
   别把它写成"证明过了"。
③ **不能拿 `-W error` 或"跑一次没喷"当证据**：警告是 compile 那一刻吐的，同模块第二次 import
   走缓存就 0 条（表最后一行，两档解释器都实测）。一个人连跑两次会先看到一次、之后永远"干净"。
④ 反面样本必须真 raw：只在我这边的字面量前加 r、再用拼接凑后半，产出的源码里
   并没有那个 r（三引号部分没带上前缀）。第一版就这么造了个假对照组，被自己判红
   （这条也是实测，不是推测）。

两面都要有：植一条非 raw 的 `\cite` 必须红；当前仓必须绿。
扫描必须有**范围下限**：没有下限的扫描只会永远绿（文件列表一旦塌成空，它就"通过"了）。
普查数印在行上，不能只当"测试过了"。
"""
from __future__ import annotations

import io
import json
import os
import sys
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 第三方与产物目录。第一方代码一律不许进这个名单 —— 名单每加一项，覆盖面就塌一寸，
#: 所以范围下限（下面 FLOOR）才是真正兜住"扫了个空"的东西。
SKIP_DIRS = {"__pycache__", "node_modules", ".idea", "vendor", "data", ".git"}
FLOOR = 80          # 下限；**实测条数不写在这儿**（写死一次就过期一次），它只印在
                    # [ESCAPE_CENSUS] 那行上，并由下面那条 `n >= FLOOR` 断言兜着。
MSG = "invalid escape sequence"


def py_files(root=ROOT):
    out = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs
                   if d not in SKIP_DIRS and not d.startswith(".venv")]
        for fn in files:
            if fn.endswith(".py"):
                out.append(Path(dirpath) / fn)
    return sorted(out)


def scan_source(src, name):
    """-> (转义命中 [(行, 文本)], 编不过的文件标记)。

    `always` 是必须的：默认滤镜在 3.10 上会把这一类藏起来（模块注释里的实测表第 3 行）。
    SyntaxError 不算"没问题"，算"这个文件没被检查过"，由调用方断言它必须为 0。
    """
    hits, broken = [], None
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            compile(src, name, "exec")
        except SyntaxError as exc:
            broken = "%s: SyntaxError %s" % (name, exc.msg)
        for x in w:
            if MSG in str(x.message):
                hits.append((getattr(x, "lineno", None) or 0, str(x.message)))
    return hits, broken


def scan_repo(root=ROOT):
    """整仓扫一遍。-> (扫描文件数, 命中 [(相对路径, 行, 文本)], 编不过的清单)。"""
    hits, broken, n = [], [], 0
    for p in py_files(root):
        n += 1
        with io.open(p, encoding="utf-8", errors="replace") as fh:
            src = fh.read()
        rel = p.relative_to(root).as_posix()
        got, bad = scan_source(src, rel)
        broken += [bad] if bad else []
        hits += [(rel, ln, txt) for ln, txt in got]
    return n, sorted(hits), broken


class EscapeSequenceGateTests(unittest.TestCase):

    def test_census_has_a_floor_and_is_printed_on_the_line(self):
        """范围下限：文件数塌了就红，而不是"绿得悄无声息"。"""
        n, hits, broken = scan_repo()
        print("[ESCAPE_CENSUS] py_files=%d hits=%d floor=%d broken=%d"
              " | 扫描=%d 个 .py，非法转义命中=%d 处，编不过=%d 个"
              % (n, len(hits), FLOOR, len(broken), n, len(hits), len(broken)))
        self.assertGreaterEqual(n, FLOOR,
                                "只扫到 %d 个 .py（下限 %d）—— 是**扫描范围塌了**，"
                                "不是没有缺陷：查 SKIP_DIRS 名单与 walk 是否被截断"
                                % (n, FLOOR))
        self.assertEqual(broken, [], "有文件 compile 不过，本次检查对它无效：%s" % broken[:3])
        self.assertEqual(hits, [],
                         "发现非 raw 字符串里的非法转义（被 import 就喷一行噪声）：\n  %s\n"
                         "  修法：那段字符串加 r 前缀，或把 \\ 写成 \\\\"
                         % "\n  ".join("%s:%d %s" % h for h in hits[:10]))

    def test_planted_positive_is_caught(self):
        """两面之一：植一条非 raw 的 `\\cite`，判据必须当场抓到它。

        这条同时也是①的判别式 —— 把匹配改回"只认 SyntaxWarning 类别"，在 3.10 上这里
        记到 0 条而当场变红（实测过）。注意：**摘掉 simplefilter 不会让本用例红**，
        因为 unittest 进程默认给 DeprecationWarning 开了滤镜（模块注释②里已按实测标注）。
        """
        bad_src = '"""docstring 里有 \\cite 这段。"""\nX = 1\n'
        hits, broken = scan_source(bad_src, "planted_bad.py")
        self.assertEqual(broken, None, "样本本身编不过，下面的断言是空转")
        self.assertEqual(len(hits), 1, "植了一条却抓到 %d 条：%s" % (len(hits), hits))
        self.assertIn(MSG, hits[0][1])
        # 反面样本必须真是 raw：写 `r'"""..."""' + ...` 只会让**我这个字面量**变 raw，
        # 拼出来的源码里并没有 r 前缀 —— 第一版就这么造了个假对照组，被自己判红才发现。
        good_src = 'r"""docstring 里有 \\cite 这段。"""\nX = 1\n'
        self.assertTrue(good_src.startswith('r"""'),
                        "反面样本没带上真正的 r 前缀，这条对照是假的")
        hits2, broken2 = scan_source(good_src, "planted_raw.py")
        self.assertEqual(broken2, None)
        self.assertEqual(hits2, [], "raw 字符串被误报（说明判据在乱抓）：%s" % hits2)

    def test_planted_positive_goes_red_through_the_repo_path(self):
        """整仓那条路也要能红：把坏文件真放进被扫目录，`scan_repo()` 必须报它。

        只测 `scan_source` 挡不住"目录名单把第一方排除了"这类失效 —— 那只有走完整路径才看得见。
        临时文件放在 results/adhoc/（已 gitignore），跑完删。
        """
        plant = ROOT / "results" / "adhoc" / "_escape_probe_bad.py"
        plant.parent.mkdir(parents=True, exist_ok=True)
        old_n, old_hits, _ = scan_repo()
        try:
            plant.write_text('"""docstring 里有 \\cite 这段。"""\nX = 1\n', encoding="utf-8")
            n, hits, broken = scan_repo()
            self.assertEqual(broken, [])
            mine = [h for h in hits if h[0].endswith("_escape_probe_bad.py")]
            self.assertEqual(len(mine), 1, "种进仓库却没扫到：%s" % hits[:5])
            self.assertGreater(n, old_n, "文件数没跟着涨，说明 walk 根本没看到它")
            # 第二遍也必须抓到 —— 只有"复扫仍红"才排除掉吃缓存的那一类瞎法：
            # 换成 import 来扫的话，这一句就是它当场露馅的地方（实测见
            # test_compile_is_what_keeps_the_second_pass_alive）。
            n2, hits2, _b2 = scan_repo()
            again = [h for h in hits2 if h[0].endswith("_escape_probe_bad.py")]
            self.assertEqual(len(again), 1,
                             "同一个坏文件第二遍扫不到了（%s）—— 判据依赖了 compile 之外的状态"
                             % (hits2[:3],))
        finally:
            plant.unlink(missing_ok=True)
        _n2, hits2, _b2 = scan_repo()
        self.assertEqual([h for h in hits2 if h[0].endswith("_escape_probe_bad.py")], [],
                         "临时文件没删干净，下一轮会红在探针上")


    def test_compile_is_what_keeps_the_second_pass_alive(self):
        """`compile()` 到底替什么买单 —— 两边结果都在这里测，不是注释里的说法。

        子进程（干净解释器，`PYTHONPYCACHEPREFIX` 指到仓外临时目录，缓存真会落盘）跑两条路：
          A. `import` 同一个坏模块两次 —— 期望 1 条 then **0 条**（第二次吃缓存）；
          B. `scan_source()` 的 compile 路数三次 —— 期望 **1/1/1**。
        哪天 A 的第二次也能抓到（解释器改了重编译策略），这条会红 —— 那就不是"门坏了"，
        而是模块注释③里"`-W error` 与'跑一次没喷'都不能当证据"这句失去依据，要连注释一起改。
        """
        import subprocess
        import tempfile
        work = tempfile.mkdtemp(prefix="esc-import-")
        child = r'''
import io, os, sys, warnings, importlib, json
sys.path.insert(0, os.getcwd())
from console.test_source_escape_sequences import scan_source
d = sys.argv[1]
Q = chr(34) * 3                    # 三引号；子进程自己的代码里不许出现非法转义
BS = chr(92)                       # （否则它一启动就喷我们正要门控的那一行）
src = Q + 'docstring ' + BS + 'cite here.' + Q + chr(10) + 'X = 1'
io.open(os.path.join(d, "badimp.py"), "w", encoding="utf-8", newline="\n").write(src)
sys.path.insert(0, d)
imports = []
for _ in range(2):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        sys.modules.pop("badimp", None)
        importlib.import_module("badimp")
        imports.append(sum(1 for x in w if "invalid escape" in str(x.message)))
compiles = [len(scan_source(src, "badimp.py")[0]) for _ in range(3)]
pc = os.path.join(os.environ.get("PYTHONPYCACHEPREFIX", ""), d)
found = []
for root, _dirs, files in os.walk(os.environ["PYTHONPYCACHEPREFIX"]):
    found += [f for f in files if f.startswith("badimp") and f.endswith(".pyc")]
print(json.dumps({"imports": imports, "compiles": compiles, "pyc": len(found)}))
'''
        env = dict(os.environ)
        env.pop("PYTHONDONTWRITEBYTECODE", None)
        env["PYTHONPYCACHEPREFIX"] = work          # 仓外，不污染树
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            pr = subprocess.run([sys.executable, "-c", child, work], cwd=str(ROOT),
                                capture_output=True, env=env)
        finally:
            import shutil
            shutil.rmtree(work, ignore_errors=True)
        self.assertEqual(pr.returncode, 0, "子进程没跑成：%s" % pr.stderr.decode("utf-8", "replace")[-300:])
        got = json.loads(pr.stdout.decode("utf-8", "replace").strip())
        imports, compiles, pyc = got["imports"], got["compiles"], got["pyc"]
        print("[ESCAPE_MECHANISM] import=%s compile=%s pyc=%d"
              " | import 路：%s -> compile 路：%s -> 缓存文件 %d 个"
              % (imports, compiles, pyc, imports, compiles, pyc))
        self.assertGreaterEqual(pyc, 1,
                                "缓存压根没落盘，'第二次 import'不是真吃缓存，这条判据空转")
        self.assertEqual(imports[0], 1, "第一次 import 都没抓到 —— 对照基线变了，重写判据")
        self.assertEqual(imports[1], 0,
                         "第二次 import 也抓到了（%s）：缓存不再掩盖警告，"
                         "模块注释③那句'-W error / 跑一次没喷 不能当证据'失去依据，"
                         "要连注释一起改；compile 路此时依然正确" % (imports,))
        self.assertEqual(compiles, [1, 1, 1],
                         "compile 路不再稳定复现（%s）：本门的前提塌了" % (compiles,))


if __name__ == "__main__":
    unittest.main()
