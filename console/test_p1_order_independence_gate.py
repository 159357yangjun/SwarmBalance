# -*- coding: utf-8 -*-
"""#70-P1：order-independence 回归门 —— 后人重新引入全局污染时会红。

上位裁定给的是"阶段通过 = 六条结构事实同时成立"，不是"这次聚合刚好绿"。本门负责其中
第 1/2/4/6 条里可机器化的部分；第 3 条（残留审计）由 test_census_no_leak 面守。

被守的既有缺陷（一手定位见 docs/P70_import_order_pollution.md）：
    console/test_r2_destination_without_load.py:30 setenv(出厂 config) → :34 `from environment import ...`
    ⇒ frontend/environment.py:87/:100/:105 在 **import 期**把 DEFAULT_NUM_DRONES/FLEET_MIX 冻结成出厂值；
    随后 console/test_speed_fallback_gate.py 换 SWARM_BALANCE_SIM_CONFIG 已经太晚
    ⇒ 机队 10 机轻载 ⇒ PSO buffer 峰=2 < 阈值 15 ⇒ optimize 零调用
    ⇒ G2 报 `[pso][NO_DENOMINATOR]`，把测试隔离缺陷冒充成被测算法缺陷。

两面（缺一即是一扇只会绿的门）：
  GREEN —— 至少两种显式不同发现顺序下跑目标测试，断言结果一致且为通过；
  RED   —— 注入一个**已知**的全局污染样本（一个先 setenv+import environment 的临时模块），
           再跑同一目标 ⇒ 若目标仍要依赖主进程常量就会被带偏；本面断言"污染确实改变了可见状态"，
           否则说明注入无效、门等于摆设（[P1_INJECT_NO_EFFECT]）。
短码：[P1_ORDER_DEPENDENT] / [P1_TARGET_RED] / [P1_INJECT_NO_EFFECT] / [P1_BLIND]
退出码：顺序相关或注入无效=1。参与 discover（常驻门）。
"""
from __future__ import annotations
import os, pathlib, shutil, subprocess, sys, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = sys.executable

#: 目标测试：历史上唯一随顺序翻脸的用例。
TARGET = "console.test_speed_fallback_gate.SpeedFallbackGateTests.test_g2_all_four_algorithms_get_real_fleet_speed"
#: 前序模块：字母序天然排在 speed_gate 之前，且**修复前**会在 setUpClass 里抢先按名字 import
#: environment（污染源本体）。修复后它走按路径加载器 ⇒ 这一对现在应当两向皆绿；
#: 若有人把它改回 `from environment import ...`，本门的 ORDER-A 面就会重新变红（判据②的活证人）。
PRECEIDER = "console.test_r2_destination_without_load"


def _run(module_list, timeout=1200):
    """在 fresh process 里按给定顺序跑一组模块，返回 (returncode, stdout+stderr)。"""
    r = subprocess.run([PY, "-m", "unittest", "-v"] + module_list,
                       cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    return r.returncode, (r.stdout or "") + (r.stderr or "")


class OrderIndependenceGate(unittest.TestCase):
    def test_A_two_opposite_orders_agree(self):
        """判据①②④：两种显式相反顺序下各跑一次，结果必须都是通过、且关键读数一致。"""
        rc_ab, out_ab = _run([PRECEIDER, TARGET])       # 曾经的红序（discover 字母序就是这个方向）
        rc_ba, out_ba = _run([TARGET, PRECEIDER])       # 反序
        self.assertEqual(rc_ab, 0, "[P1_TARGET_RED] 顺序[r2→G2] 未通过：\n%s" % out_ab[-900:])
        self.assertEqual(rc_ba, 0, "[P1_TARGET_RED] 顺序[G2→r2] 未通过：\n%s" % out_ba[-900:])
        # 读数一致性：optimize 台机×批次计数是这门的核心分母，两个顺序必须相同
        def opt_count(text):
            for line in text.splitlines():
                if "[G2/pso" in line and "optimize" in line:
                    tok = line.split("optimize")[1].split()[0]
                    return int(tok)
            raise AssertionError("[P1_BLIND] 两路输出里都没抓到 [G2/pso ...] optimize 读数行")
        n_ab, n_ba = opt_count(out_ab), opt_count(out_ba)
        self.assertGreater(n_ab, 0, "[P1_TARGET_RED] pso 分母为 0 ⇒ 又回到 NO_DENOMINATOR")
        self.assertEqual(n_ab, n_ba,
                         "[P1_ORDER_DEPENDENT] pso optimize 读数随顺序变化：%s(先r2) vs %s(后r2)" % (n_ab, n_ba))
        print("[P1_AGREE] 两种顺序均通过且 pso optimize=%d 一致（单跑与聚合走同一子进程路径）" % n_ab)

    def test_B_injected_pollution_is_detected(self):
        """判据⑥的红面：造一个已知全局污染样本，门必须能看见它——否则这扇门是摆设。

        污染样本 = 一个临时测试模块，在 setUpClass 里 setenv(出厂 config) 并**按名字** import
        environment（正是修复前 r2 的形状）。断言：该模块跑完后，它自己看到的
        `DEFAULT_NUM_DRONES` 确实是出厂 10 而非重载 6 ⇒ 证明"抢在别的模块之前按名字 import
        就会把常量冻进 sys.modules['environment']"这条通道仍然真实存在、值得被守；
        注入无效果则报 [P1_INJECT_NO_EFFECT]（不许默默绿）。

        ⚠ 诚实边界：这一面证的是"污染机制仍在"，不是"目标会被带偏"——目标已经子进程化，
        真的不再吃主进程常量（这正是修复本身）。所以本门的牙分两处：
          · B 面 = 污染机制可复现（防"门守的是一个已不存在的东西"）；
          · A 面 = 两向读数逐字相同（若有人把 r2 改回按名字 import、或把 G2 改回主进程跑，
            ORDER-A 立刻红）。B 面不能替代 A 面，两面都留着。
        """
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="p1inj_"))
        mod = tmp / "zz_p1_polluter.py"
        mod.write_text(
            "import os, pathlib, sys, unittest\n"
            "ROOT = pathlib.Path(%r)\n"
            "class ZzPolluter(unittest.TestCase):\n"
            "    @classmethod\n"
            "    def setUpClass(cls):\n"
            "        os.environ['SWARM_BALANCE_SIM_CONFIG'] = str(ROOT / 'config' / 'simulation.json')\n"
            "        for p in (str(ROOT), str(ROOT / 'frontend')):\n"
            "            if p not in sys.path: sys.path.insert(0, p)\n"
            "        from environment import Environment\n"
            "        cls.E = Environment\n"
            "    def test_zz_noop(self):\n"
            "        import environment as E\n"
            "        print('[P1_POLLUTED_FLEET]', int(E.DEFAULT_NUM_DRONES))\n"
            "        self.assertTrue(True)\n" % str(ROOT).replace("\\", "\\\\"),
            encoding="utf-8",
        )
        try:
            env = dict(os.environ, PYTHONIOENCODING="utf-8",
                       PYTHONPATH="%s;%s" % (tmp, os.environ.get("PYTHONPATH", "")))
            r = subprocess.run([PY, "-m", "unittest", "zz_p1_polluter"],
                               cwd=str(tmp), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=600, env=env)
            out = (r.stdout or "") + (r.stderr or "")
            line = [l for l in out.splitlines() if "[P1_POLLUTED_FLEET]" in l]
            self.assertTrue(line, "[P1_INJECT_NO_EFFECT] 污染模块没打印读数，注入无从判定：\n%s" % out[-500:])
            got = int(line[0].split("[P1_POLLUTED_FLEET]")[1].strip())
            self.assertEqual(got, 10,
                             "[P1_INJECT_NO_EFFECT] 抢先 import 后冻结到的机队是 %s 而非出厂 10 ⇒ "
                             "这条全局态通道已不存在，本门的红面失效，须重判是否还需要它" % got)
            print("[P1_TEETH] 注入生效：抢先 setenv+import 会把 DEFAULT_NUM_DRONES 冻成 %s（出厂值）" % got)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)   # 子进程会在 tmp 里落 __pycache__，rmdir 必炸


if __name__ == "__main__":
    unittest.main(verbosity=2)
