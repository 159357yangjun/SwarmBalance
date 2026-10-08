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
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = sys.executable

#: 已迁移的模块：应当零残留。
CLEAN_MODULES = [
    "test_r2_destination_without_load",
    "test_c4_is_carrying_discriminator",
    "test_h_r7_delivery_detection",
    "test_route_planner_equivalence",
    "test_c1_destination_leg_semantics",
]

#: 这些模块本身就会合法地引入内核类 sys.modules（生产代码链），不作为残留判据。
#: 理由：console/sim_session.py:43 按名字绑定 environment 是 reload 语义所需，属生产路径。
#: ⚠ 本轮实测把 sys.modules 从**判据**里撤掉了（详见 test_A 上方注释与 docstring 的未覆盖面）：
#:   "跑过被测代码 ⇒ sys.modules 多了 frontend 那一串"是任何真运行都会有的正常副作用，
#:   拿它当残留会让门永远红、逼人放宽 ⇒ 那是给不存在的问题写门。撤掉后仍守的两面是
#:   env 与 sys.path —— 这两面才是"改了还能还原、且还原失败会毒害后序模块"的那类状态。
MODULE_ALLOWLIST = frozenset()

_CHILD = r'''
import sys, os, pathlib, json, unittest
ROOT = pathlib.Path(sys.argv[1]); MODS = sys.argv[2].split(",")
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
    errs = [json.loads(l[len("RUNERRORS_JSON "):])
            for l in out.splitlines() if l.startswith("RUNERRORS_JSON ")]
    return (json.loads(line[0][len("RESIDUE_JSON "):]),
            (errs[0] if errs else []), (census[0] if census else []))


class NoCrossTestResidue(unittest.TestCase):
    def test_A_clean_modules_leave_no_residue(self):
        """判据③：这批模块跑完全程后，环境变量 / sys.path / sys.modules 应回到原样。"""
        residue, run_errors, census = _child(CLEAN_MODULES)
        self.assertEqual(run_errors, [],
                         "[P3_BLIND] 这些模块没能跑完（残留无从判定，不是通过）：\n  "
                         + "\n  ".join(run_errors))
        self.assertEqual(residue, [],
                         "[P3_RESIDUE] 跑完 %d 个模块后仍有未还原的全局态：\n%s" % (
                             len(CLEAN_MODULES),
                             "\n".join("  " + json.dumps(x, ensure_ascii=False) for x in residue)))
        # 逐模块点名（不靠聚合的巧合）：env 改动与 sys.path 增项必须是每个模块各自为空
        for row in census:
            self.assertFalse(row["env_changed"],
                             "[P3_RESIDUE] %s 自己改了 SWARM_BALANCE_SIM_CONFIG 却没还原" % row["module"])
            self.assertEqual(row["path_added"], [],
                             "[P3_RESIDUE] %s 往 sys.path 里留了条目：%s" % (row["module"], row["path_added"]))
        print("[P3_CLEAN] %d 个模块全程跑完后残留=0（判据两面：env / sys.path 皆空，逐模块点名亦全空）"
              % len(CLEAN_MODULES))

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
            residue, run_errors, _ = _child(["zz_p3_polluter"], pythonpath=str(tmp), prefix="")
            self.assertEqual(run_errors, [],
                             "[P3_BLIND] 注入样本没能跑完：%s" % run_errors)
            self.assertTrue(any(x.get("kind") == "env" for x in residue),
                            "[P3_INJECT_NO_EFFECT] 注入了未还原的 setenv，门却读不到残留：%s "
                            "⇒ 判据是摆设" % residue)
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
            print("[P3_WITNESS] 正例证人通过：注入模块确实在子进程里跑起来了")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
