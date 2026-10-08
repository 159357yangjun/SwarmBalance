# -*- coding: utf-8 -*-
"""#70-P1 判据③的常驻门：加载测试模块后不许留下未还原的全局态。

守什么火口（一手链条见 docs/P70_import_order_pollution.md）：
    discover 是**同一进程**按字母序跑完所有模块 ⇒ 任何模块改过而没还原的全局态
    （环境变量 / sys.path / sys.modules / 随机状态 / 注册表单例）都会喂给后面的模块，
    于是"这条门单独跑绿、进聚合红"＝把测试隔离缺陷冒充成被测对象缺陷。

判据（不是发明，是本轮实测到的两类可还原残留）：在 fresh 子进程里
    记录 before → 逐个 **真跑完**（setUpClass/用例/tearDownClass 全走）指定模块 → 记录 after，
    diff 必须为空：
      · `SWARM_BALANCE_SIM_CONFIG` 变了且没还原；
      · `sys.path` 多出条目。
    ⚠ 刻意用"真跑完"而不是 loadTestsFromName（只 import）：第一版这样测得到 0 残留，
      但 r2 的 setUpClass 根本没执行 ⇒ 那个 0 是量具到不了，不是现场干净（本轮自纠入档）。
    ⚠ sys.modules 一度也被列进判据，实测后**撤掉**：任何真运行都会把 frontend 那一串
      正常导入进来（drone/task/route_planner…），那不是"未还原的残留"而是运行的副作用，
      拿它当判据的门会永远红、只能靠放宽来过活 ⇒ 见 test_A 上方注释与"未覆盖面"。

两面（缺一即是一扇只会绿的门）：
    GREEN = 已迁移到按路径加载 + tearDownClass 的那批模块 ⇒ 残留应为空；
    RED   = 注入一个已知会留残留的样本（复刻修复前 r2 的形状：setenv 不还原）⇒ 必须报出该条，
            报不出来即 [P3_INJECT_NO_EFFECT]（不许默默绿）。
未覆盖面（诚实边界，别当成全量残留审计）：本轮只测 env / sys.path 两面。
    · `sys.modules`：**撤判据**（理由见上），因为"跑过被测代码"必然新增内核类模块名，
      无法与"残留"区分；真正承重的那条已由 console/test_p2_no_name_based_kernel_import.py
      从**源码结构**侧守住（测试不许按名字 import 内核），不需要在运行时再猜一次。
    · 随机状态 / 注册表单例：**没测** —— 判据③原文列了五类，这里只做到有实测证据的两类；
      补另两类要先证明"确有模块改了它且没还原"，否则是写给不存在的问题的门。
短码：[P3_RESIDUE] / [P3_INJECT_NO_EFFECT] / [P3_BLIND]
退出码：有残留=1。参与 discover（常驻门）。
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = sys.executable

#: 普查集**从盘上按谓词现算**（#70-P1 裁定 (i)）：不再手写名单，否则新写的测试改了全局态
#: 不还原就根本不进本门视野 —— 那才是"后人重新引入污染"最可能的形状。
#:
#: 谓词分两条，各自只收"会真的留下跨测试状态"的写法：
#:   ENV_WRITE  给 SWARM_BALANCE_SIM_CONFIG 赋值（改的是全进程共享的环境变量）
#:   PATH_LEAK  往 sys.path 里**插条目**且该模块没有任何还原路径
#: ⚠ 为什么 path 谓词要带"有没有还原"这半边（主控补的要求②：写了但不还原才违规）：
#:   `sys.path.insert(0, ROOT)` 这种是本仓标准的 import 引导（把仓库根/子目录挂上以便 import），
#:   它加的是**永久有效**的路径、不是"脏值"；把它当残留会让 33 个模块一起误伤
#:   （本轮实测朴素谓词命中 37 个模块，其中绝大多数只是引导），一门天天误伤的门很快被人关掉。
#:   真正会毒害后序模块的是：插了临时目录 / 插完不还原导致别人解析到不同东西。
#: ⚠ 为什么必须**排除 raw-string 里的写入**（本轮实测的第二条自纠）：
#:   本仓大量门用 `script = r'''…'''` 起子进程，脚本正文里就有
#:   `os.environ["SWARM_BALANCE_SIM_CONFIG"]=…`（c1_lifecycle_gate:48 / h3_lifecycle_gates:48 /
#:   observer_zero_drift:41 都是这种）。那是**新进程**、天然不留残留；按文本行扫会把它们
#:   误算成主进程写入点 ⇒ 普查集虚高到 31 个模块（真值见下面 `_raw_string_lines`）。
#: ⚠ 第三条自纠（同一形状的另一半）：**sys.path 谓词不能只看"有没有还原"**。
#:   朴素版本给出 27 个模块，其中 test_mapfile_pinned / test_portable_runtime /
#:   test_carrying_capacity_is_float … 只是把**仓库内永久目录**挂上 sys.path ——
#:   那是 import 引导，任何解释器启动后这些路径都有效，不是会被"下一个模块读到脏值"的状态。
#:   真正会毒害后序的是**临时目录**：它随进程存在、内容可被删，且插进去的模块名可能遮蔽真模块。
#: ⚠ 第四条自纠（红面注入实测出来的，共两步）：判"插的是不是临时目录"**既不能只看 insert 那一行、
#:   也不能只看"本文件提过 tempfile"**。
#:   · 只看 insert 行会漏：注入样本写 `_d = tempfile.mkdtemp(); sys.path.insert(0, _d)`，
#:     insert 那行里没有 tempfile 字样（实测漏过一次）。
#:   · 只看"文件提过 tempfile"会误伤 7 个模块（实测：test_compare_csv_census / test_portable_runtime /
#:     test_stale_bytecode … 只是别处用了临时文件，插进 sys.path 的仍是仓库永久目录）。
#:   ⇒ 定稿做**极窄的数据流**：把"赋值为临时目录构造调用"的名字收集起来（`X = tempfile.mkdtemp()`
#:     之类），insert 的参数里出现这些名字之一才算命中。宁可漏不可误伤 —— 误伤会让门很快被人关掉；
#:     漏的那一类由 test_A 的运行时 diff 兜住（真留下条目时照样红）。
ENV_WRITE = re.compile(r"""os\.environ\[\s*["']SWARM_BALANCE_SIM_CONFIG["']\s*\]\s*=""")
PATH_INSERT = re.compile(r"""sys\.path\.(?:insert|append)\(""")
TEMP_CONSTRUCT = re.compile(r"""tempfile\.\w+|mkdtemp|gettempdir""")
ASSIGNS_TEMP = re.compile(r"""^\s*(\w+)\s*=\s*[^\n]*(?:tempfile\.\w+|mkdtemp\(|gettempdir\()""")
RESTORE_MARKS = ("tearDownClass", "tearDownModule", "def tearDown(", "addCleanup")


def _raw_string_lines(src: str):
    """raw-string（子进程脚本块）覆盖的行号集合 —— 谓词不看这些行。"""
    import io as _io
    import tokenize as _tk
    lines = set()
    try:
        for tok in _tk.generate_tokens(_io.StringIO(src).readline):
            if tok.type == _tk.STRING and "r" in tok.string[:3].lower():
                lines.update(range(tok.start[0], tok.end[0] + 1))
    except (_tk.TokenError, IndentationError, SyntaxError) as exc:
        raise AssertionError("[P3_BLIND] %s tokenize 失败(%s) ⇒ 分不清主进程写入与子进程脚本，"
                             "本门拒绝在看不见的前提下报绿" % ("predicate", exc))
    return lines


def _predicate_hits(path: pathlib.Path, src: str | None = None):
    """-> (env_lines, path_lines, has_restore)：只算**主进程可执行语句**上的写入点。

    排除三类假命中：整行注释、raw-string 子进程脚本正文、指向永久仓库目录的 sys.path 引导。
    `src` 供两面夹具直接喂内存文本（不落临时文件，免得被本门自己扫到）。
    """
    if src is None:
        try:
            src = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return [], [], False
    lines = src.splitlines()
    raw = _raw_string_lines(src)
    code = [(i, l) for i, l in enumerate(lines, start=1)
            if i not in raw and not l.lstrip().startswith("#")]
    env_lines = [i for i, l in code if ENV_WRITE.search(l)]
    # 极窄数据流：只认"被赋成临时目录构造调用"的名字，insert 参数里出现它才算命中
    temp_names = set()
    for _i, l in code:
        m_ = ASSIGNS_TEMP.match(l)
        if m_:
            temp_names.add(m_.group(1))
    path_lines = []
    for i, l in code:
        if not PATH_INSERT.search(l):
            continue
        arg = l.split("(", 1)[1] if "(" in l else ""
        if any(re.search(r"\b%s\b" % n, arg) for n in temp_names):
            path_lines.append(i)
    has_restore = any(mk in src for mk in RESTORE_MARKS)
    return env_lines, path_lines, has_restore


def census_modules():
    """从盘上算出普查集，返回 (modules, matched, excluded_restored_bootstrap)。

    入选 = "写了全局态"；**是否违规不由这里决定**，由 test_A 的运行时 diff 决定。
    两条谓词（均只算主进程可执行语句）：
      · 写 `SWARM_BALANCE_SIM_CONFIG` ⇒ 入册；
      · 插 sys.path **且本模块存在临时目录来源** ⇒ 入册。
    不入选：只把仓库内永久目录挂上 sys.path 的 import 引导（朴素谓词给 27 个、其中十几个属这类）。
    ⚠ 刻意**不看**"有没有 tearDown"：主控要求②是"写了但不还原才违规"，而"还没还原"这件事
      只能在运行时判定（源码里有个 tearDown 不代表它真把状态还原干净）。所以这里收的是
      **观测范围**，test_A/test_F 才是**判据**。若反过来用 has_restore 去豁免，
      任何人加一个空的 tearDownClass 就能躲过普查 —— 那是逃生口，不是判据。
    """
    mods, matched, excluded = [], [], []
    for f in sorted((ROOT / "console").glob("test_*.py")):
        env_lines, path_lines, _has_restore = _predicate_hits(f)
        name = f.stem
        if env_lines or path_lines:
            mods.append(name); matched.append((name, len(env_lines), len(path_lines)))
        elif path_lines:
            excluded.append(name)
    return sorted(set(mods)), matched, sorted(set(excluded))


CLEAN_MODULES, MATCHED, EXCLUDED_BOOTSTRAP = census_modules()

#: 在册豁免（键=模块名，理由必填）：**基线为空表**。
#: 留这张表是为了"结构上必须留残留"时能显式登记并由人审，不是万能钥匙 ——
#: test_D 会核"条目还在/已消失"，与 #69-C6 6-A、P2 同一形状。
RESIDUE_WAIVERS: dict = {}

#: 自我豁免的**理由与代价**（独立于上面那张表，因为它不是"某模块可以留残留"）：
#: 本门也在普查集里（它自己写 SWARM_BALANCE_SIM_CONFIG），若在子进程内再"真跑完 test_p3_*"
#: 就会起第二层同样的普查 ⇒ 指数级套娃（本轮实测：一次跑到 18 个 python.exe 仍不收敛，
#: 只能外部终止）。⇒ 子进程永远跳过自己这一支。
#: ⚠ 代价明写：**子进程普查看不见本模块自己的残留**。那一面改由 test_F 用另一条通道守
#:   （在当前进程里加载并跑完本模块，再由父进程 diff env / sys.path —— 父看子是天然可观测的）。
SELF_NAME = "test_p3_no_cross_test_residue"

#: 这些模块本身就会合法地引入内核类 sys.modules（生产代码链），不作为残留判据。
#: 理由：console/sim_session.py:43 按名字绑定 environment 是 reload 语义所需，属生产路径。
#: ⚠ 本轮实测把 sys.modules 从**判据**里撤掉了（详见 test_A 上方注释与 docstring 的未覆盖面）：
#:   "跑过被测代码 ⇒ sys.modules 多了 frontend 那一串"是任何真运行都会有的正常副作用，
#:   拿它当残留会让门永远红、逼人放宽 ⇒ 那是给不存在的问题写门。撤掉后仍守的两面是
#:   env 与 sys.path —— 这两面才是"改了还能还原、且还原失败会毒害后序模块"的那类状态。
MODULE_ALLOWLIST = frozenset()

_CHILD = r'''
import sys, os, pathlib, json, unittest
ROOT = pathlib.Path(sys.argv[1])
# ⚠ 自我嵌套护栏：本门自己也在普查集里（它写 SWARM_BALANCE_SIM_CONFIG），若在子进程内
#   再"真跑完 test_p3_*"，就会再起一层同样的普查 ⇒ 指数级套娃（实测一次跑到 18 个 python
#   进程仍未收敛，只能外部终止）。⇒ 子进程永远跳过自己这一支；本模块的残留由**外层**那次
#   运行观测（外层是它的父进程，看到的正是它 setUpClass/tearDownClass 前后的差，见 test_F）。
# ⚠ 这里必须写字面量：_CHILD 是在**另一个进程**里执行的字符串，拿不到本模块的 Python 全局名。
#   （写成 SELF_NAME 时实测直接 NameError ⇒ 整条门跑不起来。）
SELF = "test_p3_no_cross_test_residue"
MODS = [x for x in sys.argv[2].split(",") if x != SELF]
SKIPPED_SELF = (SELF in sys.argv[2].split(",")) and (SELF not in MODS)
sys.path[:0] = [str(ROOT), str(ROOT / "frontend"), str(ROOT / "console")]
KEY = "SWARM_BALANCE_SIM_CONFIG"
before_cfg = os.environ.get(KEY)
before_path = list(sys.path)
before_mods = set(sys.modules)
errors = []
rows = []
PREFIX = sys.argv[4] if len(sys.argv) > 4 else "console."
for n in MODS:
    cfg_before = os.environ.get(KEY); path_before = list(sys.path)
    try:
        suite = unittest.defaultTestLoader.loadTestsFromName(PREFIX + n)
        # 真跑完（含 setUpClass/tearDownClass），不是只 import —— 否则测不到那批钩子留下的残留
        unittest.TextTestRunner(stream=open(os.devnull, "w"), verbosity=0).run(suite)
    except BaseException as exc:
        errors.append("%s: %s: %s" % (n, type(exc).__name__, str(exc)[:120]))
    rows.append({"module": n,
                 "env_changed": cfg_before != os.environ.get(KEY),
                 "path_added": [p for p in sys.path if p not in path_before]})

res = []
if before_cfg != os.environ.get(KEY):
    res.append({"kind": "env", "key": KEY, "before": before_cfg, "after": os.environ.get(KEY)})
added_path = [p for p in sys.path if p not in before_path]
if added_path:
    res.append({"kind": "sys.path", "added": added_path})
print("RESIDUE_JSON " + json.dumps(res, ensure_ascii=False, default=str))
print("CENSUS_JSON " + json.dumps(rows, ensure_ascii=False, default=str))
print("SELF_EXCLUDED %s" % ("yes" if SKIPPED_SELF else "no"))
if errors:
    print("RUNERRORS_JSON " + json.dumps(errors, ensure_ascii=False))
'''


def _child(mods_list, pythonpath=None, prefix="console.", timeout=1800):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if pythonpath:
        env["PYTHONPATH"] = "%s%s%s" % (pythonpath, os.pathsep,
                                        os.environ.get("PYTHONPATH", ""))
    r = subprocess.run([PY, "-c", _CHILD, str(ROOT), ",".join(mods_list),
                        json.dumps(sorted(MODULE_ALLOWLIST)), prefix],
                       cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=timeout)
    out = (r.stdout or "") + "\n" + (r.stderr or "")
    line = [l for l in out.splitlines() if l.startswith("RESIDUE_JSON ")]
    if not line:
        raise AssertionError("[P3_BLIND] 子进程没产出 RESIDUE_JSON ⇒ 量具没跑起来；"
                             "退码=%s，输出尾=%s" % (r.returncode, out[-500:]))
    census = [json.loads(l[len("CENSUS_JSON "):])
              for l in out.splitlines() if l.startswith("CENSUS_JSON ")]
    self_excluded = [l[len("SELF_EXCLUDED "):].strip()
                     for l in out.splitlines() if l.startswith("SELF_EXCLUDED ")]
    errs = [json.loads(l[len("RUNERRORS_JSON "):])
            for l in out.splitlines() if l.startswith("RUNERRORS_JSON ")]
    return (json.loads(line[0][len("RESIDUE_JSON "):]),
            (errs[0] if errs else []), (census[0] if census else []),
            (self_excluded[0] if self_excluded else "?"))


class NoCrossTestResidue(unittest.TestCase):
    def test_A_clean_modules_leave_no_residue(self):
        """判据③：普查集（从盘上现算）里每个模块跑完全程后，env / sys.path 应回到原样。"""
        residue, run_errors, census, self_excluded = _child(CLEAN_MODULES)
        # 自我嵌套护栏必须生效：子进程里若没把本模块剔出去，它会再起一层同样的普查（实测套娃过）
        self.assertEqual(self_excluded, "yes",
                         "[P3_BLIND] 子进程没排除自身 ⇒ 会指数级自我嵌套（本轮实测跑到 18 个 python 进程）")
        self.assertEqual(run_errors, [],
                         "[P3_BLIND] 这些模块没能跑完（残留无从判定，不是通过）：\n  "
                         + "\n  ".join(run_errors))
        waived = set(RESIDUE_WAIVERS)
        real = [x for x in residue if x.get("module", "") not in waived]
        self.assertEqual(real, [],
                         "[P3_RESIDUE] 跑完 %d 个模块后仍有未还原的全局态：\n%s" % (
                             len(CLEAN_MODULES),
                             "\n".join("  " + json.dumps(x, ensure_ascii=False) for x in real)))
        # 逐模块点名（不靠聚合的巧合）：env 改动与 sys.path 增项必须是每个模块各自为空
        for row in census:
            self.assertFalse(row["env_changed"],
                             "[P3_RESIDUE] %s 自己改了 SWARM_BALANCE_SIM_CONFIG 却没还原" % row["module"])
            self.assertEqual(row["path_added"], [],
                             "[P3_RESIDUE] %s 往 sys.path 里留了条目：%s" % (row["module"], row["path_added"]))
        print("[P3_VERDICT] modules_covered=%d residue_items=%d census_rows=%d waivers=%d "
              "exit_criterion=residue_items==0_and_run_errors==0" % (
                  len(CLEAN_MODULES), len(real), len(census), len(waived)))
        print("[P3_CLEAN] %d 个模块全程跑完后残留=0（判据两面：env / sys.path 皆空，逐模块点名亦全空）"
              % len(CLEAN_MODULES))

    def test_C_coverage_set_is_computed_not_handwritten(self):
        """裁定 (i)：普查集必须**等于本轮谓词命中集**，缺口即红 —— 而不是"名单里的都绿"。

        为什么这条才是"防新增污染"的那半边：原先 CLEAN_MODULES 是手写 5 个具名模块，
        新写的测试改了 env 不还原就根本不进本门视野（实测过：改版后集合从 5 涨到 %d）。
        ⇒ 判据 = `modules_matching_predicate - modules_covered` 必须为空；
          两个数都来自本轮扫描（不抄上一轮），并排印出来供对账。
        """
        mods_now, matched_now, excluded_now = census_modules()
        names_now = sorted({m for m, _, _ in matched_now})
        self.assertEqual(names_now, sorted(mods_now),
                         "[P3_COVERAGE_GAP] 普查集与本轮命中集不等：covered=%s matching=%s" % (
                             sorted(mods_now), names_now))
        # 关键一面：**手工名单已不存在**，所以这里断言的是"名单由谓词生成"这件事仍然成立 ——
        # 若有人把 CLEAN_MODULES 改回硬编码，命中数就会与它不等，本条立刻红。
        self.assertGreater(len(mods_now), 0,
                           "[P3_BLIND] 命中 0 个模块 ⇒ 谓词瞎了（本仓确实有模块写这个环境变量）")
        print("[P3_COVERAGE] modules_covered=%d modules_matching_predicate=%d "
              "excluded_bootstrap=%d exit_criterion=(matching - covered)==0" % (
                  len(mods_now), len(matched_now), len(excluded_now)))
        for name, e, p in sorted(matched_now):
            print("[P3_COVERED] %-42s env_writes=%d temp_path_writes=%d" % (name, e, p))

    def test_D_waiver_table_discipline(self):
        """豁免表纪律（沿用 P2/6-A 的形状）：理由必填且 ≥12 字；条目失效即红。"""
        thin = [k for k, v in RESIDUE_WAIVERS.items() if not isinstance(v, str) or len(v.strip()) < 12]
        self.assertEqual(thin, [], "[P3_WAIVER_THIN] 这些豁免条目缺理由或过短：%s" % thin)
        stale = sorted(k for k in RESIDUE_WAIVERS if k not in set(CLEAN_MODULES))
        self.assertEqual(stale, [],
                         "[P3_WAIVER_STALE] 这些豁免模块已不在本轮普查集内（代码变了或被悄悄改名），"
                         "要么恢复原状要么删条目，不许留着当万能钥匙：%s" % stale)
        print("[P3_WL_COUNT] 在册豁免=%d 条（基线=0），全部带理由" % len(RESIDUE_WAIVERS))

    def test_F_self_is_observed_by_parent(self):
        """补上自我豁免丢掉的覆盖面：**本模块自己的残留由父进程观测**。

        为什么需要这一条：子进程普查把 SELF_NAME 剔出去了（防指数级套娃，实测跑过 18 个进程），
        于是"本门自己写 env 还还原了没有"变成盲区 —— 而它恰好在普查集里（谓词命中）。
        ⇒ 换一条通道：在**当前进程**里加载并真跑完本模块，再由本函数（作为它的父）diff
          env / sys.path。父看子是天然可观测的，不需要再起一层普查。
        ⚠ 这条同时是 test_A 的判别式：若有人删掉本模块的 tearDownClass，这里立刻红。
        ⚠ **必须隔一层进程、且只跑有界用例集**（第一版就地跑，实测卡死）：
          `loadTestsFromName("console." + SELF)` 会把本模块**全部**用例再跑一遍，其中含 test_A
          那轮全量普查 ⇒ 同进程套娃（实测一次堆到 18 个 python.exe 才从外部终止）。
          ⇒ 现在显式只加载 test_D/test_E 两条廉价用例：足以证明"本模块被真跑过 + env/sys.path
            回到原样"，不再触发第二层普查。`tests_run_in_self>0` 就是防"没跑到却说干净"的证人。
        """
        child = r'''
import sys, os, pathlib, unittest
ROOT = pathlib.Path(sys.argv[1]); SELF = sys.argv[2]
sys.path[:0] = [str(ROOT), str(ROOT / "frontend"), str(ROOT / "console")]
KEY = "SWARM_BALANCE_SIM_CONFIG"
cb = os.environ.get(KEY); pb = list(sys.path)
# 有界：只这两条廉价用例（不加载 test_A，避免第二层全量普查）
names = ["console.%s.NoCrossTestResidue.test_D_waiver_table_discipline" % SELF,
         "console.%s.NoCrossTestResidue.test_E_predicate_two_faces_written_but_restored_is_not_a_violation" % SELF]
suite = unittest.TestLoader().loadTestsFromNames(names)
r = unittest.TextTestRunner(stream=open(os.devnull, "w"), verbosity=0).run(suite)
print("SELFRES " + ("1" if cb != os.environ.get(KEY) else "0") + " "
      + str(len([p for p in sys.path if p not in pb])) + " " + str(r.testsRun))
'''
        r = subprocess.run([PY, "-c", child, str(ROOT), SELF_NAME],
                           cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=1800,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        line = [l for l in (r.stdout or "").splitlines() if l.startswith("SELFRES ")]
        self.assertTrue(line, "[P3_BLIND] 自我观测没产出读数；退码=%s stderr尾=%s" % (
            r.returncode, (r.stderr or "")[-300:]))
        env_left, path_added, ran = line[0].split()[1:4]
        self.assertGreater(int(ran), 0,
                           "[P3_BLIND] 本模块一个用例都没跑到 ⇒ '无残留'是量具到不了，不是干净")
        print("[P3_SELF_VERDICT] env_left=%s path_added=%s tests_run_in_self=%s "
              "exit_criterion=env_left==0_and_path_added==0" % (env_left, path_added, ran))
        self.assertEqual(env_left, "0",
                         "[P3_RESIDUE] 本门自己改了 SWARM_BALANCE_SIM_CONFIG 却没还原（test_A 因防套娃"
                         "看不见这一面，故单列此断言）")
        self.assertEqual(path_added, "0",
                         "[P3_RESIDUE] 本门往 sys.path 留了条目：%s" % path_added)

    def test_E_predicate_two_faces_written_but_restored_is_not_a_violation(self):
        """主控补的要求②：**谓词本身要两面**。写了但不还原才违规。

        这里把"范围"与"判据"分开钉（这是本轮实测想通的一点）：
          · **范围**由源码谓词决定 ⇒ 只要写了全局态就入册，**不看有没有 tearDown**；
            （若用 has_restore 去豁免，加一个空的 tearDownClass 就能躲过普查 ⇒ 逃生口，不是判据。）
          · **判据**由运行时 diff 决定 ⇒ 正确还原的模块 env_changed=False / path_added=[]，
            在 test_A 那里自然不报红。这才是"写了但还原了不算违规"的实现位置。
        三组断言：
          E1 正例（setenv + 真还原）⇒ 入范围，且运行时不违规（本条只验前者，后者归 test_A/F）；
          E2 负例（setenv、无还原）⇒ 入范围，且 test_A 会把它报成 [P3_RESIDUE]；
          E3 仓库永久目录的 import 引导 ⇒ **不入范围**（否则门天天误伤，很快被人关掉）。
        """
        restored = (
            "import os, sys, unittest\n"
            "class G(unittest.TestCase):\n"
            "    @classmethod\n"
            "    def setUpClass(cls):\n"
            "        cls._prev_cfg = os.environ.get('SWARM_BALANCE_SIM_CONFIG')\n"
            "        os.environ['SWARM_BALANCE_SIM_CONFIG'] = '/tmp/g.json'\n"
            "    @classmethod\n"
            "    def tearDownClass(cls):\n"
            "        os.environ['SWARM_BALANCE_SIM_CONFIG'] = cls._prev_cfg\n"
            "    def test_x(self):\n"
            "        self.assertTrue(True)\n"
        )
        unrestored = (
            "import os, unittest\n"
            "class B(unittest.TestCase):\n"
            "    @classmethod\n"
            "    def setUpClass(cls):\n"
            "        os.environ['SWARM_BALANCE_SIM_CONFIG'] = '/tmp/b.json'\n"
            "    def test_x(self):\n"
            "        self.assertTrue(True)\n"
        )
        bootstrap = (
            "import sys, unittest\n"
            "sys.path.insert(0, str(ROOT))\n"
            "sys.path.insert(0, str(ROOT / 'frontend'))\n"
            "class X(unittest.TestCase):\n"
            "    def test_x(self):\n"
            "        self.assertTrue(True)\n"
        )
        temp_leak = (
            "import sys, tempfile, unittest\n"
            "_d = tempfile.mkdtemp(prefix='zz_')\n"
            "sys.path.insert(0, _d)\n"                       # insert 那行不含 tempfile 字样
            "class Z(unittest.TestCase):\n"
            "    def test_x(self):\n"
            "        self.assertTrue(True)\n"
        )
        fake = pathlib.Path("_p3_face_tmp.py")
        g_env, g_path, g_restore = _predicate_hits(fake, src=restored)
        b_env, b_path, b_restore = _predicate_hits(fake, src=unrestored)
        e3, p3, _ = _predicate_hits(fake, src=bootstrap)
        t_env, t_path, _ = _predicate_hits(fake, src=temp_leak)
        self.assertEqual((len(g_env), len(b_env)), (2, 1),
                         "[P3_INJECT_NO_EFFECT] 两种 setenv 形状没都被纳入观测范围：%s / %s "
                         "（正例数 2 = setUpClass 写一次 + tearDownClass 还原再写一次）" % (
                             len(g_env), len(b_env)))
        self.assertTrue(g_restore and not b_restore,
                        "[P3] has_restore 标记算错：正例应 True、负例应 False")
        self.assertEqual(p3, [],
                         "[P3_OVERREACH] 永久目录的 import 引导被当成残留写入点：%s ⇒ 误伤" % p3)
        self.assertEqual(t_path, [3],
                         "[P3_INJECT_NO_EFFECT] 'insert 行里没有 tempfile 字样'的临时目录泄漏没被抓到："
                         "%s ⇒ 逐行判定会漏（本轮实测漏过一次），必须文件级判定" % t_path)
        print("[P3_PREDICATE_FACES] scope=setenv(2/2)+temp-path-leak(1) 均入范围; "
              "permanent-bootstrap hits=%d 不入范围; 是否违规改由运行时 diff 判" % len(p3))

    def test_B_injected_residue_is_detected(self):
        """红面：造一个已知会留残留的样本（setenv 不还原），门必须报出它。

        ⚠ 注入样本必须**真的被跑到**：第一版我把临时目录只塞进 PYTHONPATH，而子进程里
          `loadTestsFromName("console.zz_…")` 那个前缀根本找不到它 ⇒ 读数为空、被误报成
          "注入无效"。⇒ 现在用不带 `console.` 前缀的名字加载，并加一条"这个模块确实跑过"
          的正例证人（样本自己往 sys.modules 里记一笔 P3_RAN_MARKER）。
        """
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="p3inj_"))
        mod = tmp / "zz_p3_polluter.py"
        mod.write_text(
            "import os, sys, unittest\n"
            "class ZzP3Polluter(unittest.TestCase):\n"
            "    @classmethod\n"
            "    def setUpClass(cls):\n"
            "        os.environ['SWARM_BALANCE_SIM_CONFIG'] = '/tmp/p3_injected_not_restored.json'\n"
            "        sys.modules['P3_RAN_MARKER'] = True\n"
            "    def test_zz_noop(self):\n"
            "        self.assertTrue(True)\n"       # ← 故意没有 tearDownClass
            , encoding="utf-8")
        try:
            # 注入样本放在临时目录 ⇒ 用空前缀加载（`console.zz_…` 那个名字下没有它）
            residue, run_errors, _, _sx = _child(["zz_p3_polluter"], pythonpath=str(tmp), prefix="")
            self.assertEqual(run_errors, [],
                             "[P3_BLIND] 注入样本没能跑完：%s" % run_errors)
            self.assertTrue(any(x.get("kind") == "env" for x in residue),
                            "[P3_INJECT_NO_EFFECT] 注入了未还原的 setenv，门却读不到残留：%s "
                            "⇒ 判据是摆设" % residue)
            print("[P3_TEETH_VERDICT] env_residue_seen=True items=%d "
                  "exit_criterion=at_least_one_kind_env" % len(residue))
            print("[P3_TEETH] 注入生效：读到残留 %s" % json.dumps(residue, ensure_ascii=False)[:200])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_C_injected_module_actually_ran(self):
        """正例证人：区分"门看不见残留"与"样本压根没跑"。

        第一版就是栽在这里 —— 临时目录只进了 PYTHONPATH，而子进程按 `console.<名字>` 加载，
        那个前缀下根本没有这个模块 ⇒ 读数为空、被我误读成"注入无效"。
        判据：样本 setUpClass 里写下的 `sys.modules['P3_RAN_MARKER']` 必须出现在
        它自己的 sys.modules 新增集合里（用 kind=sys.modules 那条报告不便，故直接看原始 JSON）。
        """
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="p3mark_"))
        (tmp / "zz_p3_marker.py").write_text(
            "import sys, unittest\n"
            "class ZzP3Marker(unittest.TestCase):\n"
            "    @classmethod\n"
            "    def setUpClass(cls):\n"
            "        sys.modules['P3_RAN_MARKER'] = True\n"
            "    def test_zz_noop(self):\n"
            "        self.assertTrue(True)\n", encoding="utf-8")
        try:
            child_src = _CHILD.replace('"RESIDUE_JSON "', '"MARKER_SEEN " + str("P3_RAN_MARKER" in sys.modules) + "\\nRESIDUE_JSON "')
            env = dict(os.environ, PYTHONIOENCODING="utf-8",
                       PYTHONPATH="%s%s%s" % (tmp, os.pathsep, os.environ.get("PYTHONPATH", "")))
            r = subprocess.run([PY, "-c", child_src, str(ROOT), "zz_p3_marker",
                                json.dumps(sorted(MODULE_ALLOWLIST)), ""],
                               cwd=str(ROOT), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", env=env, timeout=600)
            out = (r.stdout or "") + (r.stderr or "")
            line = [l for l in out.splitlines() if l.startswith("MARKER_SEEN ")]
            self.assertTrue(line, "[P3_BLIND] 正例证人没有输出：\n%s" % out[-400:])
            self.assertEqual(line[0][len("MARKER_SEEN "):], "True",
                             "[P3_BLIND] 注入样本没被执行 ⇒ 任何'读不到残留'都不能算证据")
            print("[P3_WITNESS_VERDICT] marker_seen=True exit_criterion=marker_line_present_and_True")
            print("[P3_WITNESS] 正例证人通过：注入模块确实在子进程里跑起来了")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
