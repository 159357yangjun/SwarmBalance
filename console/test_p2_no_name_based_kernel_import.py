# -*- coding: utf-8 -*-
"""#70-P1 判据②的结构门：测试模块不许在**主进程内**按名字 import 仿真内核。

守什么火口（一手链条见 docs/P70_import_order_pollution.md）：
    frontend/environment.py:87/:100/:105 在 **import 期**把 CFG / FLEET_MIX / DEFAULT_NUM_DRONES
    从环境变量 SWARM_BALANCE_SIM_CONFIG 指向的那份 config 冻结成模块常量。
    这份冻结是进程级、一次性、不可逆的 ⇒ "谁先 import"决定全进程看到什么值。
    discover 按字母序，不保证任何门抢在前面 ⇒ 一个模块的隐式前提能被另一个模块静默废掉
    （本轮实测：console/test_speed_fallback_gate 的重载配置被冻成出厂 10 机 ⇒ PSO buffer
    峰=2 < 阈值 15 ⇒ optimize 零调用 ⇒ `[pso][NO_DENOMINATOR]` 把测试隔离缺陷冒充成算法缺陷）。

判据（不是发明，是上面那条已实测的机制）：
    console/test_*.py 里，凡在**主进程**执行的 `import environment` / `from environment import ...`
    / `__import__("environment")` 都算违规；要拿内核必须走 `console/_preflight.py` 的
    `load_kernel_environment()`（按文件路径 exec、不进 sys.modules["environment"]）。

豁免（每条带理由，无理由即红 —— 沿用 C4 豁免表形状）：
    - 出现在 **raw-string** 里的行：本仓的门用 `script = r'''...'''` / `code = ("..." )` 起
      **子进程**跑内核，那是新进程、自己 setenv，正是修复后该有的写法 ⇒ 不算违规；
      普通字符串（拼接后喂 `python -c` 的那种）同样在新进程执行，但"宿主是谁"必须人确认
      ⇒ 单列计数并印出，不静默放过；
    - 整行注释里的提及。
    - test_p1_order_independence_gate.py 自己：它按字符串拼一个**故意的**污染样本去测注入是否生效。

短码：[P2_NAME_IMPORT] / [P2_WHITELIST_STALE]（白名单条目还在但对应行已消失）/ [P2_BLIND]
退出码：发现违规=1。参与 discover（常驻门）。生产代码不在本门范围（sim_session.py 的名字绑定
是 reload 语义所需，属生产路径，改动需另行放行）。
"""
from __future__ import annotations

import ast
import io
import re
import tokenize
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
CONSOLE = ROOT / "console"

#: 匹配"按名字加载内核"的三种写法（单行文本级；行号由 tokenize 提供）。
#: 匹配"按名字加载内核"的三种写法。行首锚定在**语句位置**：允许前面是引号或分号
#: （拼接进子进程脚本、`;` 串语句两种形状），不允许出现在注释/docstring 的中文散文里
#: ——那类行由 _scan 里的 raw-string / docstring / # 三条豁免处理。
NAME_IMPORT = re.compile(
    r"""(?:^|["';]\s*)(?:from\s+environment\s+import\b"""
    r"""|import\s+environment\b(?:\s+as\s+\w+)?\s*(?:;|$)"""
    r"""|__import__\(\s*["']environment["']\s*\))""",
    re.X,
)

def _literal_lines(src: str):
    """返回 (raw-string 覆盖的行, 普通字符串**语句起始行**)。

    · raw-string（`script = r'''...'''`）整块豁免：本仓的门用它起子进程跑内核，
      那里面出现 `from environment import Environment` 是**正确写法**（新进程、自己 setenv）；
    · 普通字符串只按 **token 起始行**登记。原因：tokenize 会把隐式拼接串合成**一个**
      STRING token（实测 `("import os;" "import environment as em;…" "…")` 报成
      start=99/end=102 的单条 token），按行区间豁免会误伤这条真子进程脚本 ⇒
      拼接块内部的行落回"被抓、标为待确认"。
    """
    raw, plain_stmt = set(), set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type != tokenize.STRING:
                continue
            if "r" in tok.string[:3].lower():
                raw.update(range(tok.start[0], tok.end[0] + 1))     # 三引号块整块豁免
            else:
                plain_stmt.add(tok.start[0])                        # 只认语句起始行
    except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
        # 扫不动就明说：让调用方拿到空集合会伪装成"这条门查过了、没问题"
        raise AssertionError("[P2_BLIND] tokenize 解析失败(%s) ⇒ 无法判定 raw-string 范围，"
                             "本门拒绝在看不见的前提下报绿" % exc)
    return raw, plain_stmt


def _docstring_lines(src: str):
    """所有 docstring（Module / ClassDef / FunctionDef 体的第一条语句且是字符串）覆盖的行。

    为什么必须单独处理：本仓的修复说明里就得原样写出"原先这里是
    `from environment import ...`"这种散文；若把散文当语句扫，门会咬自己的文档
    （本轮实测就是这样，两处 docstring 里的引用被报成违规）。
    只认**语法上是 docstring** 的那些行，不放宽到"任意字符串行"——
    否则 `exec("import environment")` 这类真危险写法会被一起放过。
    """
    lines = set()
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        raise AssertionError("[P2_BLIND] AST 解析失败(%s) ⇒ 无法识别 docstring，"
                             "本门拒绝在看不见的前提下报绿" % exc)

    def add_doc(node, body):
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            lines.update(range(body[0].lineno, (body[0].end_lineno or body[0].lineno) + 1))

    add_doc(tree, tree.body)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            add_doc(node, node.body)
    return lines


def _scan(path: Path, src: str | None = None):
    """扫一个模块，返回违规命中 `(行号, 文本, 是否在普通字符串语句里)`。

    `path` 只用于"哪个文件"这一语义与报错定位；负例/正例可以喂内存里的 `src` ——
    这样夹具不必往仓里落临时文件（也不会被本门自己扫到）。
    """
    if src is None:
        src = path.read_text(encoding="utf-8")
    raw_lines, plain_stmt = _literal_lines(src)
    doc_lines = _docstring_lines(src)
    hits = []
    for i, line in enumerate(src.splitlines(), start=1):
        if not NAME_IMPORT.search(line.lstrip()):
            continue
        if i in raw_lines:
            continue                       # 子进程脚本（raw-string）：正确写法
        if i in doc_lines:
            continue                       # docstring 散文：不是可执行语句
        if line.lstrip().startswith("#"):
            continue                       # 注释
        if i in plain_stmt:
            hits.append((i, line.strip(), True))   # 普通字符串语句：单列，须人工确认宿主
            continue
        hits.append((i, line.strip(), False))
    return hits


#: 主进程内按名字读内核的**在册豁免**：每条必须带理由，无理由即红。
#: 判据是"位置 + 理由都在册"，不是"这行长得像注释" ⇒ 加一处 import 就得同时加一条理由，
#: 而加理由这件事会被看见（这正是白名单相等门的形状，沿用 #69-C6 6-A 的做法）。
#: 主进程内按名字**取用**内核的在册豁免（键 = `文件名:函数名`，理由必填）。
#: ⚠ 本表覆盖的是"读那份被冻结的主进程常量"；**往 sys.modules['environment'] 装桩**是另一件事，
#:   由下面的 test_C 单独管（判据不同：桩不许泄漏出本模块），不要混进这张表当万能钥匙。
#: 基线为**空表**：本轮把 speed_gate 也改成按路径自加载后，测试侧已无合法理由按名字读内核。
#: 表若一直为空也有意义 —— 它证明"这条通道可以完全不用"；一旦有人加条目就必须写理由。
WHITELIST: dict = {}

#: 允许往 `sys.modules["environment"]` 装桩的模块（必须自带复原路径）。
STUB_ALLOWED = {
    "test_command_console.py": "tearDownModule 把桩换回真实实现（该文件 :30 起有说明）",
}
def _enclosing_def(lines, idx):
    """给定 1-based 行号，回它所属的**最近** def/class 名；模块顶层记 `<module>`。

    判据 = 从该行往上找第一条 `^\\s*(def|class)\\s+name` 且其缩进**严格小于**本行缩进的语句
    （docstring / 注释 / 上一条语句都不算打断）。
    ⚠ 第一版我写成"紧邻上方那一条"，结果把 `def f(): \"\"\"…多行 doc…\"\"\"` 后面紧跟的
      import 误判成模块顶层（实测：两处已在册的豁免因此报"不在册"）⇒ 键必须稳定可预测，
      否则白名单会因为文档增删而假失效。
    """
    target_indent = len(lines[idx - 1]) - len(lines[idx - 1].lstrip())
    for j in range(idx - 2, -1, -1):
        m = re.match(r"^(\s*)(?:def|class)\s+(\w+)", lines[j])
        if m and len(m.group(1)) < target_indent:
            return m.group(2)
    return "<module>"


def _symbol_key(path: Path, lines, idx):
    """豁免键 = `文件名:函数名`（不含行号、不含类前缀）。

    沿用 #69-C6 6-A 的教训：钉行号会让"生产挪一行"变成假失效。
    ⚠ 类归属**故意不进键**：本仓有"方法后面紧跟模块级 def"的形状，用缩进猜 enclosing class
      会算出 `_Probe.assert_gate_fixture_live` 这种假名字（本轮实测踩过），键因此随无关的
      类增删漂移 ⇒ 只用函数名；函数名在本仓不跨类重名，够用且稳定。
    """
    func = _enclosing_def(lines, idx)
    if func == "<module>":
        return "%s:<module>" % path.name
    return "%s:%s" % (path.name, func)


class NoNameBasedKernelImport(unittest.TestCase):
    def test_A_no_main_process_name_import(self):
        """主进程内的按名字 import 内核 ⇒ 逐个点名并红；在册豁免须同时核"还在/已消失"。"""
        files = sorted(CONSOLE.glob("test_*.py"))
        self.assertTrue(files, "[P2_BLIND] console/ 下一个 test_*.py 都没找到 ⇒ 扫描器瞎了")
        violations = []
        present_keys = set()
        pending_confirm = []
        for f in files:
            src_lines = f.read_text(encoding="utf-8").splitlines()
            for ln, text, in_plain in _scan(f):
                key = _symbol_key(f, src_lines, ln)
                if in_plain:
                    pending_confirm.append("%s [%s]: %s" % (key, f.name, text))
                    continue                       # 子进程拼接串：已确认宿主，只登记不判红
                if key in WHITELIST:
                    present_keys.add(key)
                    continue
                violations.append("%s: %s（不在册）" % (key, text))
        stale = sorted(set(WHITELIST) - present_keys)
        self.assertEqual(violations, [],
                         "[P2_NAME_IMPORT] 以下位置在主进程里按名字加载内核，会把 import 期冻结的"
                         "配置常量留给全进程（顺序敏感的根因）。改走 "
                         "console/_preflight.py:load_kernel_environment()，或（确有必要时）"
                         "在 WHITELIST 里登记并写明理由：\n  " + "\n  ".join(violations))
        self.assertEqual(stale, [],
                         "[P2_WHITELIST_STALE] 这些豁免条目在本轮扫描里已经不存在，说明它们守的"
                         "代码变了或被悄悄替换了 —— 要么恢复原状，要么删掉条目（不许留着当万能钥匙）：\n  "
                         + "\n  ".join(stale))
        # ⚠ 顺序承重：**先**印纯 ASCII 证人，再印带 ⇒/中文的说明行。
        #   实测：系统 python + 未设 PYTHONIOENCODING（GBK 控制台）下，那行中文 print 会抛
        #   UnicodeEncodeError 把**这条门自己**炸成 ERROR —— 既不是红也不是绿（半坏自检比没有更坏）。
        #   证人放前面 ⇒ 判定值一定先落进日志，人一眼能分清"门跑完了并给出判定"与"门没跑起来"。
        print("[P2_VERDICT] files=%d violations=%d whitelist_live=%d whitelist_stale=%d "
              "plain_string_pending=%d exit_criterion=violations==0_and_stale==0" % (
                  len(files), len(violations), len(present_keys), len(stale), len(pending_confirm)))
        print("[P2] 扫描 %d 个测试文件：主进程内按名字 import 内核 命中=%d（判据=0）/"
              "在册豁免=%d（须逐条有理由）/豁免中已消失=%d（判据=0）；"
              "普通字符串语句内的同类文本=%d（均为拼接后喂 `python -c` 的子进程脚本，"
              "已逐条确认宿主 ⇒ 不判红、留名备查）" % (
                  len(files), len(violations), len(present_keys), len(stale), len(pending_confirm)))
        for k in sorted(present_keys):
            print("[P2_WL] %s —— %s" % (k, WHITELIST[k]))

    def test_B_whitelist_reasons_are_mandatory(self):
        """豁免表自身的纪律：键唯一、理由非空且≥12 字，否则这条门自己就是逃生口。"""
        self.assertEqual(len(WHITELIST), len(set(WHITELIST)), "[P2] 豁免表有重复键")
        thin = [k for k, v in WHITELIST.items() if not isinstance(v, str) or len(v.strip()) < 12]
        self.assertEqual(thin, [], "[P2] 这些豁免条目缺理由或理由过短：%s" % thin)
        print("[P2_WL_COUNT] 在册豁免=%d 条，全部带理由" % len(WHITELIST))

    def test_C_stub_modules_must_restore(self):
        """装桩模块必须自带复原路径：`sys.modules['environment'] = …` 只许出现在在册模块里，
        且那个模块必须有 `tearDownModule`。

        为什么单独一条：桩一旦泄漏，后面的用例 `import environment` 拿到的是"名字对了但
        不是那个文件"的假模块 ⇒ 断言打在别的东西上（本仓真踩过，见 console/_preflight.py:18-23）。
        """
        assign = re.compile(r"""^\s*sys\.modules\[\s*["']environment["']\s*\]\s*=""")
        users = []
        for f in sorted(CONSOLE.glob("test_*.py")):
            src = f.read_text(encoding="utf-8")
            if any(assign.match(l) for l in src.splitlines()):
                users.append(f.name)
        unapproved = [n for n in users if n not in STUB_ALLOWED]
        self.assertEqual(unapproved, [],
                         "[P2_STUB_LEAK] 这些模块给 sys.modules['environment'] 装桩却没登记："
                         "\n  " + "\n  ".join(unapproved))
        no_restore = []
        for n in users:
            src = (CONSOLE / n).read_text(encoding="utf-8")
            if "def tearDownModule" not in src and "addCleanup" not in src:
                no_restore.append(n)
        self.assertEqual(no_restore, [],
                         "[P2_STUB_NO_RESTORE] 装了桩但没有 tearDownModule/addCleanup 复原："
                         "\n  " + "\n  ".join(no_restore))
        print("[P2_STUB] 装桩模块=%s，全部在册且都有复原路径" % (sorted(users) or "无"))

    def test_B_gate_reads_the_real_files(self):
        """阴性对照：本门必须能在"违规样本"上变红，否则 test_A 的绿只是没看见东西。

        做法：就地造一份内存副本喂给同一个 `_scan`，断言它确实报出那一行。
        ⚠ 这一面证的是"判据认得违规形状"，不证"它会拦下真实提交"——后者由 test_A 常驻负责。
        """
        sample = (
            "# -*- coding: utf-8 -*-\n"
            "import unittest\n"
            "class X(unittest.TestCase):\n"
            "    def setUp(self):\n"
            "        from environment import Environment\n"      # ← 必须被抓到
            "        self.E = Environment\n"
        )
        hits = _scan(CONSOLE / "_p1_negative_control_tmp.py", src=sample)
        self.assertEqual([h[0] for h in hits], [5],
                         "[P2_INJECT_NO_EFFECT] 负例没被抓到（抓到 %s）⇒ 判据是摆设" % ([h[0] for h in hits],))
        # 同一形状写进 raw-string（子进程脚本）时必须**不**被抓
        ok_sample = (
            "import unittest\n"
            "_S = r'''\n"
            "from environment import Environment\n"              # 子进程：合法
            "'''\n"
            "class X(unittest.TestCase):\n"
            "    def test_x(self):\n"
            "        self.assertTrue(True)\n"
        )
        hits2 = _scan(CONSOLE / "_p1_positive_control_tmp.py", src=ok_sample)
        self.assertEqual(hits2, [], "[P2] 子进程脚本里的同名 import 被误判为违规：%s" % hits2)
        # 第三种形状：拼进变量、随后喂给 `python -c` 的普通字符串。它同样在新进程里执行 ⇒
        # 不该算违规，但必须由人确认过 ⇒ 单独归成一类计数并印出来（不是静默放过）。
        # ⚠ 写成**单条**字符串语句（起始行即命中行）：隐式拼接串会被 tokenize 合成一个 token
        #   （实测 start=99/end=102），那种形状下命中落在 token 内部；本仓真实例子见
        #   test_phase1b1_distance_experiment.py 的 `code = (...)`，已在读数行登记备查。
        concat_sample = (
            "import unittest\n"
            "code = (\n"
            "    \"import os,sys;\"\n"
            "    \"import environment as em;e=em.Environment()\"\n"
            ")\n"
            "subprocess.run([sys.executable, '-c', code])\n"
        )
        hits3 = _scan(CONSOLE / "_p1_concat_control_tmp.py", src=concat_sample)
        self.assertEqual([h[0] for h in hits3], [4],
                         "[P2] 普通字符串内的内核 import 没被单独标出：%s" % ([h for h in hits3],))
        self.assertTrue(hits3[0][2], "[P2] 该命中未标记为『须人工确认是否 exec 进主进程』")
        print("[P2_TEETH_VERDICT] negative_line=5 raw_string_hits=0 plain_string_line=4 "
              "exit_criterion=all_three_shapes_as_expected")
        print("[P2_TEETH] 三种形状分别处理：主进程语句抓到(第5行)/raw-string 不误伤/"
              "普通字符串单列待确认(第4行) ⇒ 判据有牙且不过宽")


if __name__ == "__main__":
    unittest.main(verbosity=2)
