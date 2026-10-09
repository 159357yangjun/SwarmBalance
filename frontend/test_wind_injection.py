# -*- coding: utf-8 -*-
"""E1 接入 Environment 的三道门：**等价门 → 符号门 → 非零风行为门**。

顺序是有意的：等价门排在最前，因为它证明"新增结构没有偷偷改变原模型"——
这比"逆风更费电"更重要。任何一条不等价就应当停下，不要继续跑 fixture。

为什么逐 run 而不是只比均值：同 seed 的两批如果均值相同但逐 run 不同，
说明有非确定性混进来了；而均值差被抵消恰好掩盖它。用户明确要求"最好逐 run 对比"。

这里不接 1008 小时 CSV、不做时间序列风、不比四算法 —— 那些都在本轮范围外。
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXP_DIR = ROOT / "results" / "experiments" / "e0_baseline_20261008-221039"  # pin 含 route_planner 的基线（第四十二笔；上一版 210053 钉住清单少一个承重文件）
PRESET = ROOT / "experiments" / "presets" / "e0_baseline.yaml"

#: 参照物缺失时的行为开关。**默认不存在 ⇒ 门红**，不是 skip。
#: 理由（本轮实测付出过代价）：把旧基线目录改名 `_deprecated-20261008` 之后，
#: 这把门从"红/绿"双双变成 `skipped=1` —— 聚合读数仍是 OK，守着的门却已经不咬了，
#: 而没有任何东西报警。⇒ 局部修复可以静默摘掉一把常驻门。
#: 只有显式设这个环境变量才允许跳过，且跳过时**必须印出 opt-in 具名原因**（见 test_Z），
#: 退出码由 unittest 记为 skipped；本仓口径是 skipped ≠ 通过，须逐条点名（README §套件真值）。
SKIP_OPT_IN = "SWARM_BALANCE_ALLOW_MISSING_E0_BASELINE"


def _reference_state():
    """(ok, 具名原因)：参照物是否可用。**只描述事实，不做放行判断。**"""
    if not EXP_DIR.is_dir():
        return False, "E0 基线目录不存在: %s" % EXP_DIR.relative_to(ROOT)
    raw = EXP_DIR / "raw_runs.csv"
    if not raw.is_file():
        return False, "E0 基线缺 raw_runs.csv: %s" % raw.relative_to(ROOT)
    if not PRESET.is_file():
        return False, "预设文件不存在: %s" % PRESET.relative_to(ROOT)
    return True, "reference present"


def _run_preset(preset_path, out_root):
    """用与结项完全相同的编排器跑一批，返回 raw_runs 行。"""
    cmd = [sys.executable, "-m", "experiments.runner", "--preset", str(preset_path),
           "--output-root", str(out_root)]
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError("[RUNNER_RC=%d] %s" % (proc.returncode, (proc.stdout + proc.stderr)[-800:]))
    dirs = sorted(p.name for p in pathlib.Path(out_root).iterdir() if p.is_dir())
    if not dirs:
        raise RuntimeError("[NO_OUTPUT_DIR] %s 下没有产物目录" % out_root)
    csv_path = pathlib.Path(out_root) / dirs[-1] / "raw_runs.csv"
    import csv as _csv
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        return list(_csv.DictReader(fh))


class WindInjectionEquivalenceTests(unittest.TestCase):
    """门 1（最关键）：E1 + zero wind 必须逐 run 复现冻结的 E0 baseline。"""

    @classmethod
    def setUpClass(cls):
        ok, why = _reference_state()
        if not ok:
            # 默认红：参照物缺失是**事实缺陷**，不是"本轮无从判定"。
            # 只有显式 opt-in 才降级为 skip（且 test_Z 会把它印成具名信息）。
            if os.environ.get(SKIP_OPT_IN) == "1":
                raise unittest.SkipTest("[E0_REF_MISSING_OPT_IN] %s ⇒ 依环境变量放行" % why)
            raise AssertionError("[E0_REF_MISSING] %s ⇒ 等价门失去参照物。"
                                 "本条**故意不 skip**：改名/删除基线目录曾把这把门静默摘掉过（见 CHANGELOG 第四十笔）。"
                                 "要么恢复该目录，要么用 %s=1 显式声明并知道自己在跳过什么。"
                                 % (why, SKIP_OPT_IN))
        cls.e0 = list(csv_rows(EXP_DIR / "raw_runs.csv"))
        # 同一预设、同一 seeds 再跑一遍：此时 config 无 wind 键 ⇒ 静风 ⇒ 应逐字复现
        cls.tmp = ROOT / "results" / "experiments" / "_e1_zero_wind_check"
        cls.tmp.mkdir(parents=True, exist_ok=True)
        cls.e1_zero = _run_preset(PRESET, cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil_rmtree(cls.tmp)

    def test_same_run_count_and_keys(self):
        self.assertEqual(len(self.e1_zero), len(self.e0),
                         "重跑行数变了：%d vs %d ⇒ 计划本身漂移了" % (len(self.e1_zero), len(self.e0)))
        k0 = {(r["取值"], r["重复"], r["Seed"]) for r in self.e0}
        k1 = {(r["取值"], r["重复"], r["Seed"]) for r in self.e1_zero}
        self.assertEqual(k0, k1, "seed/格次集合不一致，无法逐 run 对撞：%s" % (k0 ^ k1))

    def test_every_run_reproduces_e0_bit_for_bit(self):
        """逐 run、逐指标比对。任何一格不同都算失败并点名是哪一格。"""
        idx = {(r["取值"], r["重复"]): r for r in self.e1_zero}
        metrics = [c for c in list(self.e0[0].keys())[10:]]   # 跳过元数据列
        bad = []
        for r in self.e0:
            s = idx.get((r["取值"], r["重复"]))
            self.assertIsNotNone(s, "缺格 %s×rep%s" % (r["取值"], r["重复"]))
            self.assertEqual(s["Seed"], r["Seed"], "seed 漂移")
            for m in metrics:
                if r[m] != s[m]:
                    bad.append("%s/rep%s/%s: E0=%s E1zero=%s" % (r["取值"], r["重复"], m, r[m], s[m]))
        self.assertEqual(bad, [], "E1+静风未逐字复现 E0（%d 处）:\n  %s" % (len(bad), "\n  ".join(bad[:12])))

    def test_shipped_config_has_no_wind_key(self):
        """默认配置里不该出现 wind 键 —— 出现了就等于把风塞进了正式参数。"""
        cfg = json.loads((ROOT / "config" / "simulation.json").read_text(encoding="utf-8"))
        self.assertNotIn("wind", cfg, "config/simulation.json 出现了 wind 键 ⇒ 违反'不改正式默认'")


class WindSignConventionTests(unittest.TestCase):
    """门 2：符号约定必须有单测钉住（物理含义反掉是最难发现的错）。"""

    def setUp(self):
        sys.path.insert(0, str(ROOT))
        sys.path.insert(0, str(ROOT / "frontend"))
        os.environ.setdefault("SWARM_BALANCE_SIM_CONFIG", str(ROOT / "config" / "simulation.json"))
        import drone as D
        self.D = D

    def make(self):
        return self.D.Drone(drone_id="t", x=0.0, y=0.0, drone_type="heavy_cargo")

    def test_dot_positive_is_tailwind_not_headwind(self):
        """空气吹向方向与航向点积为正 ⇒ **顺风**；内部 wind_along 必须因此为负。

        这条存在是因为很容易写成 `dot(wind, route)` 却把它当"逆风为正"用 ——
        符号反了不会报错，只会让所有结论反向。
        """
        d = self.make(); d.set_wind(wind_u=6.0, wind_v=0.0)     # 空气往东吹
        dot_east = 6.0 * 1.0 + 0.0 * 0.0                        # 向东飞：点积 > 0 ⇒ 顺风
        self.assertGreater(dot_east, 0.0)
        wa = d._wind_along_for(100.0, 0.0, 100.0)
        self.assertLess(wa, 0.0, "点积为正却给出 wind_along>0 ⇒ 顺逆风定义反了")

    def test_headwind_case_is_negative_dot(self):
        d = self.make(); d.set_wind(wind_u=6.0, wind_v=0.0)     # 东风，向西飞 = 逆风
        wa = d._wind_along_for(-100.0, 0.0, 100.0)
        self.assertGreater(wa, 0.0, "逆风应为正")

    def test_crosswind_is_zero_component(self):
        d = self.make(); d.set_wind(wind_u=6.0, wind_v=0.0)
        self.assertAlmostEqual(d._wind_along_for(0.0, 100.0, 100.0), 0.0, places=9)

    def test_environment_default_is_calm(self):
        """Environment 未配风时 wind_u/v 必须是 0 ⇒ 注入后每架机都是静风。"""
        import environment as E
        self.assertEqual(E.WIND_U_DEFAULT, 0.0)
        self.assertEqual(E.WIND_V_DEFAULT, 0.0)


class NonZeroWindBehaviorTests(unittest.TestCase):
    """门 3：非零风必须真的咬到仿真 KPI（不是只在单元测试里有效）。

    做法：直接构造一个极短回合，让一架机沿固定航线飞 N 步，比较静风与强风的电池扣减。
    不用完整 fixture —— 那属于下一步的对撞，且慢两个数量级。
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "frontend"))
        os.environ.setdefault("SWARM_BALANCE_SIM_CONFIG", str(ROOT / "config" / "simulation.json"))
        import drone as D
        self.D = D

    def fly_steps(self, wind_u, steps=20):
        """向东直线飞 steps 步，返回累计耗电 Wh（载荷固定）。"""
        d = self.D.Drone(drone_id="t", x=0.0, y=0.0, drone_type="heavy_cargo")
        d.current_load = 15.0
        d.set_wind(wind_u=wind_u, wind_v=0.0)
        saved = (self.D.WIND_ENABLED, self.D.WIND_ENERGY_HEADWIND_PER_MS,
                 self.D.WIND_ENERGY_TAILWIND_PER_MS)
        self.D.WIND_ENABLED = True
        self.D.WIND_ENERGY_HEADWIND_PER_MS = 0.05
        self.D.WIND_ENERGY_TAILWIND_PER_MS = 0.03
        try:
            before = d.current_battery
            for _ in range(steps):
                d.schedule_route([(d.x + (i + 1) * d.speed, 0.0) for i in range(steps)])
                d.update()
            return before - d.current_battery
        finally:
            (self.D.WIND_ENABLED, self.D.WIND_ENERGY_HEADWIND_PER_MS,
             self.D.WIND_ENERGY_TAILWIND_PER_MS) = saved

    def test_headwind_costs_more_than_calm_in_a_real_flight(self):
        calm = self.fly_steps(0.0)
        head = self.fly_steps(-6.0)      # 空气向西吹 ⇒ 向东飞是逆风 ⇒ wind_along>0
        tail = self.fly_steps(6.0)       # 空气向东吹 ⇒ 顺风
        self.assertGreater(head, calm, "逆风在实际飞行里没有更费电 ⇒ 路径没接通")
        self.assertLess(tail, calm, "顺风在实际飞行里没有更省电 ⇒ 路径没接通")

    def test_distance_is_unchanged_by_wind(self):
        """E1 不许改变运动学：同样步数下位移必须与静风一致（这是②而非③的证据）。"""
        def travel(wu):
            d = self.D.Drone(drone_id="t", x=0.0, y=0.0, drone_type="heavy_cargo")
            d.set_wind(wind_u=wu, wind_v=0.0)
            for _ in range(10):
                d.schedule_route([(d.x + d.speed, 0.0)])
                d.update()
            return d.x
        self.assertAlmostEqual(travel(0.0), travel(6.0), places=9,
                               msg="风改变了位移 ⇒ 这不是 E1（能耗层），而是 E2（运动学层）")


def csv_rows(path):
    import csv as _csv
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(_csv.DictReader(fh))


class FrozenReferenceGuardTests(unittest.TestCase):
    """门 4（裁定 (二)）：常驻门不得因为参照物目录被改名/删除而变成 skip。

    这条存在的原因不是理论风险，是本轮实测：把旧 E0 基线改名 `_deprecated-20261008` 后，
    `discover -s frontend` 的聚合读数从 `FAILED` 变成 `OK (skipped=1)` —— 一把守着的门被静默摘掉。
    所以这里断言两件事：① 这个文件里**不存在**"参照物缺失 ⇒ SkipTest"的形状；
    ② 缺失面必须真的判红（用临时目录里的假路径构造，不碰真产物）。
    """

    def test_no_unconditional_skip_on_missing_reference(self):
        """结构断言：文件里**真正会执行的** SkipTest 只允许 1 处，且绑在 opt-in 环境变量上。

        ⚠ 判据必须是 AST 级，不能按行匹配 —— 第一版写成 `"SkipTest" in line`，
          于是把 docstring、注释、以及本条断言自己的源码行全算进去（实测数到 7），
          门红在自己身上；那是谓词不认得它扫的东西（本仓第 N 次同一形状）。
        """
        import ast as _ast
        src = pathlib.Path(__file__).read_text(encoding="utf-8")
        tree = _ast.parse(src)
        skips, guarded = [], 0
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Raise) and isinstance(node.exc, _ast.Call):
                nm = getattr(node.exc.func, "attr", None) or getattr(node.exc.func, "id", None)
                if nm == "SkipTest":
                    skips.append(node.lineno)
                    # ⚠ 不能只断言"文件里出现过 SKIP_OPT_IN 这个字符串"：实测把
                    #   `if os.environ.get(SKIP_OPT_IN) == "1"` 改成 `if True:` 后，
                    #   字符串仍在（定义行、其它引用都在），那条断言照样绿 ⇒ 半坏自检比没有更坏。
                    #   判据必须落在**那个 skip 自己的控制流**上：它的直接父 If 的 test 里要吃得到 SKIP_OPT_IN。
        self.assertEqual(len(skips), 1,
                         "[WIND_SKIP_SHAPES] 可执行的 SkipTest 应恰好 1 处（opt-in 分支），实得 %d 处 @行%s"
                         % (len(skips), skips))

        parents = {}
        for node in _ast.walk(tree):
            for child in _ast.iter_child_nodes(node):
                parents[id(child)] = node

        # ⚠ 判据必须**按名字解析到那个 raise 自己的控制流上**。本轮在这里连错三次，同一类形状：
        #   ① `assertIn(SKIP_OPT_IN, src)`（只查字符串存在）⇒ 变异成 `if True:` 时定义行仍在，门照样绿；
        #   ② `{n.id for n in walk(anc.test) if isinstance(n, Name)}` ⇒ `os.environ.get(SKIP_OPT_IN)`
        #      里的 Name 只有 `os`（SKIP_OPT_IN 是 Call 的参数），正常树上 guarded=0、门红在自己身上；
        #   ③ 取到参数名 `SKIP_OPT_IN` 后拿它跟环境变量**字面值**比 ⇒ 比的是变量名不是它的值，照样 0。
        #      谓词要认得自己扫的形状，还得把符号解析成值（下面 _module_str_consts）。
        def _module_str_consts(tree_):
            out = {}
            for n in tree_.body:
                if isinstance(n, _ast.Assign) and len(n.targets) == 1 \
                        and isinstance(n.targets[0], _ast.Name) \
                        and isinstance(n.value, _ast.Constant) and isinstance(n.value.value, str):
                    out[n.targets[0].id] = n.value.value
            return out

        CONSTS = _module_str_consts(tree)

        def _env_arg_names(test):
            got = set()
            for call in (c for c in _ast.walk(test) if isinstance(c, _ast.Call)):
                fn = call.func
                if not (isinstance(fn, _ast.Attribute) and fn.attr in ("get", "getenv")):
                    continue
                chain, cur = [], fn.value
                while isinstance(cur, _ast.Attribute):
                    chain.append(cur.attr)
                    cur = cur.value
                base = cur.id if isinstance(cur, _ast.Name) else ""
                if not (("environ" in chain) or base in ("environ", "env")):
                    continue
                for a in call.args:
                    if isinstance(a, _ast.Name):
                        got.add(CONSTS.get(a.id, a.id))     # 符号 → 值
                    elif isinstance(a, _ast.Constant) and isinstance(a.value, str):
                        got.add(a.value)
            return got

        guarded = 0
        for node in _ast.walk(tree):
            if not (isinstance(node, _ast.Raise) and isinstance(node.exc, _ast.Call)):
                continue
            if (getattr(node.exc.func, "attr", None) or getattr(node.exc.func, "id", None)) != "SkipTest":
                continue
            anc, depth = parents.get(id(node)), 0
            while anc is not None and depth < 6:
                if isinstance(anc, _ast.If):
                    consts = {str(c.value) for c in _ast.walk(anc.test) if isinstance(c, _ast.Constant)}
                    if SKIP_OPT_IN in _env_arg_names(anc.test) and "1" in consts:
                        guarded += 1
                    break
                anc = parents.get(id(anc)); depth += 1
        self.assertEqual(guarded, 1,
                         "[WIND_NO_OPT_IN_GATE] 那处 SkipTest 的直接判据里没有 `if os.environ.get(%s) == \"1\"` ⇒ "
                         "它是无条件 skip（本轮变异实测：只查字符串存在会被 `if True:` 骗过去）" % SKIP_OPT_IN)
        print("[WIND_SKIP_SHAPE] executable_skips=%d at_line=%s env_guarded=%d "
              "exit_criterion=(executable_skips==1 and env_guarded==1)"
              % (len(skips), skips, guarded))



    def test_missing_reference_face_goes_red_not_skipped(self):
        """判别式：把 EXP_DIR 指到一个不存在的目录，必须得到红（AssertionError），不是 skip。"""
        saved = globals()["EXP_DIR"]
        saved_env = os.environ.pop(SKIP_OPT_IN, None)
        try:
            globals()["EXP_DIR"] = ROOT / "results" / "experiments" / "no_such_baseline_20260101-000000"
            ok, why = _reference_state()
            self.assertFalse(ok, "[WIND_NO_TEETH] 指向不存在目录却判参照可用 ⇒ 判据空转")
            self.assertIn("no_such_baseline_20260101-000000", why,
                          "[WIND_BLIND] 具名原因没写出缺的是哪个目录：%s" % why)
            with self.assertRaises(AssertionError) as ctx:
                WindInjectionEquivalenceTests.setUpClass()
            self.assertIn("[E0_REF_MISSING]", str(ctx.exception),
                          "[WIND_WRONG_CODE] 缺失面抛的不是默认红分支：%s" % str(ctx.exception)[:80])
            # opt-in 面：同一缺失状态，显式放行时才是 skip
            os.environ[SKIP_OPT_IN] = "1"
            with self.assertRaises(unittest.SkipTest):
                WindInjectionEquivalenceTests.setUpClass()
        finally:
            globals()["EXP_DIR"] = saved
            os.environ.pop(SKIP_OPT_IN, None)
            if saved_env is not None:
                os.environ[SKIP_OPT_IN] = saved_env
            print("[WIND_REF_GUARD] missing_face=AssertionError opt_in_face=SkipTest "
                  "skip_shapes=1 exit_criterion=(missing goes red unless env==1)")


def shutil_rmtree(path):
    import shutil
    shutil.rmtree(str(path), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
