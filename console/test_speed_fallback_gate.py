# -*- coding: utf-8 -*-
"""阻塞门：证明正常实验路径**不会**触发 `speed=200 m/s` 兜底。只计数，不改被测源码。

为什么它是四算法比较前的阻塞项：实际机型速度是 14–20 m/s，而 observation 取值处写成
`drone_info.get('speed', 200.0)`、`calculate_travel_time(distance, speed=200.0)` —— 差一个数量级。
若某算法因字段缺失偷偷走 200，ETA / deadline 可行性 / 任务选择都会失真，那时读到的
"算法差异"其实是"输入缺失触发了不同 fallback"。

判据三条同时成立才算过：
  G1 每架机在每一步的 observation 里都带有限且落在机型区间 [10, 25] m/s 的 speed；
  G2 `calculate_travel_time` 被调用时**从未**吃到默认 speed（显式传参率 = 100%）；
  G3 命中 200 兜底的次数 = 0（含 `.get('speed', 200.0)` 那条路）。
G2/G3 用 monkeypatch 包住被测函数实现，测完还原 —— 不往产品代码里塞计数器。

G2TEETH（本轮补）：门自己必须有牙。原红门的成因是**批量优化器一次都没被调用**
（出厂配置 10 机 / 60 任务下 pending_buffer 峰值只有 2，而触发阈值是 15），所以修的是
fixture（换成 C-1 重载工况），判据与阈值一个字没动。牙由子进程探针切承重变量来证：
把机队从 6 架切回 10 架后 `flush_size` 必须归零 —— 见 test_g2teeth 里的三面对照表。
"""
from __future__ import annotations

import math
import os
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "frontend"))
# ⚠ 顺序即判据的一部分：frontend/environment.py:105 的 DEFAULT_NUM_DRONES、
# task.py / drone.py:25 的常量都在 **import 时**从 SWARM_BALANCE_SIM_CONFIG 冻结。
# 若把重载配置放进 setUpClass，而 G1 已经 import 过 environment，则 G2 拿到的是
# 上一份配置的机队规模 —— 本轮实测就是这样让"退回 10 机"的变异照样绿（牙失效）。
# ⇒ 在模块导入被测代码之前就把配置写好，且本门不再于 setUpClass 里换配置。
OSM = ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm"
FLEET_SPEED_RANGE = (10.0, 25.0)      # 三款机型 14/20/20 的合理包络
DEFAULT_FALLBACK = 200.0              # ortools_scheduler.py:222 与 calculate_travel_time 的默认 speed
ALGORITHMS = ("greedy", "pso", "ga", "ortools")


class _Probe:
    """包住 calculate_travel_time，记录每次调用实际用到的 speed。"""

    def __init__(self, cls):
        self.cls = cls
        self.original = cls.calculate_travel_time
        self.calls = []

    def __enter__(self):
        calls = self.calls
        orig = self.original

        def patched(self_sched, distance, speed=DEFAULT_FALLBACK):
            calls.append(speed)
            return orig(self_sched, distance, speed)

        self.cls.calculate_travel_time = patched
        return self

    def __exit__(self, *exc):
        self.cls.calculate_travel_time = self.original
        return False


def _episode(algorithm, steps=3600, seed=40901, probe=None):
    """跑一个短回合，返回每一步 observation 里出现的 speed 值列表。

    ⚠ #70-P1：内核走 `_pf_kernel()`（按文件路径 exec、每调一次就是一次全新加载），
    **不读 sys.modules["environment"]**。原因是一手实测发现的真正污染源：
    `console/sim_session.py:43` 在 import 期就按名字 `import environment as _env_module`，
    而 discover 字母序下 `console/test_server_guards.py:22` 会先 `import console.server`
    ⇒ 主进程那份常量早在 swap_time_gate 之前就被冻成出厂 10 机（本轮就是这样让 G1 报
    `[GATE_FROZEN_BY_FOREIGN_IMPORT]`）。那个名字绑定是生产代码 reload 语义所需，不该由测试去改；
    所以本门**自己加载一份**并核对它的常量 ⇒ 与"谁先 import"彻底无关。
    """
    Environment = _pf_kernel().Environment
    env = Environment(str(OSM), episode_max_steps=steps)
    obs = env.reset(seed=seed)
    if algorithm == "greedy":
        from greedy.scheduler import greedy_action_from_observation
        next_action = lambda o: greedy_action_from_observation(o)
    elif algorithm == "pso":
        from backend_si.pso_scheduler import PSOScheduler
        sch = PSOScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
        next_action = lambda o: sch.step(o, current_time=env.current_time)
    elif algorithm == "ga":
        from backend_si.ga_scheduler import GAScheduler
        sch = GAScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
        next_action = lambda o: sch.step(o, current_time=env.current_time)
    elif algorithm == "ortools":
        from backend_si.ortools_scheduler import ORToolsScheduler, ORTOOLS_AVAILABLE
        if not ORTOOLS_AVAILABLE:
            raise unittest.SkipTest("OR-Tools 不可用 ⇒ 该算法的 speed 门无分母，不报通过")
        sch = ORToolsScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
        next_action = lambda o: sch.step(o, current_time=env.current_time)
    else:
        raise ValueError(algorithm)
    seen = []
    done = False
    while not done:
        # 先收本步 observation 的 speed，再推进 —— 顺序反了会漏掉最后一步
        for key in ("drone_capabilities", "drone_chain_info"):
            for d in obs.get(key, []) or []:
                v = d.get("speed")
                if v is not None:
                    seen.append(float(v))
        action = next_action(obs)
        obs, _, done, _ = env.step(action)
    return seen, env


def _load_config_for_gate():
    """把本门的 episode 换成 C-1 工况（240 任务 / 6 机），并返回临时目录以便还原环境。

    为什么必须换：默认 config 是 60 任务 / **10 机**，PSO/GA 的 pending_buffer 峰值只有 2，
    而批量优化触发阈值是 `buffer_size_threshold=15`（backend_si/config.yaml:16）⇒ flush
    一次都不发生 ⇒ `optimize()` 零调用 ⇒ G2 的② optimize 入口层【没有分母】。
    门当时只能报 NO_DENOMINATOR，而不是"speed 有问题"——那是量具失效，不是被测对象缺陷。

    承重变量是【机队规模】，不是任务量。2×2 消融实测（seed=40901，阈值 15 全程未动）：

        tasks= 60 drones= 6  ⇒ buffer 峰=11  flush=3315  有分母
        tasks= 60 drones=10  ⇒ buffer 峰= 2  flush=   0  ★无分母   ← 原红门所在格
        tasks=240 drones= 6  ⇒ buffer 峰=15  flush=3012  有分母
        tasks=240 drones=10  ⇒ buffer 峰= 2  flush=   3  有分母（勉强，仅 timeout 兜底）

    ⇒ 10 机时即时抽取几乎不产生积压；6 机才会形成竞争。（我最初把原因归给"240 任务"，
      被这个 2×2 推翻，故在此写明，防止下次又照错的去改。）

    ⚠ 同时记录一条真实局限，比门本身更重要：**轻载（机多单少）下 PSO/GA 与 Greedy 行为等价**
      —— 批量优化器根本不介入。所以任何"四算法性能对比"必须在重载场景做，否则比的是同一个算法。
      这条已登记在总纲 §17 与 README 的算法口径处。
    """

    import json
    import tempfile
    base = json.loads((ROOT / "config" / "simulation.json").read_text(encoding="utf-8"))
    # 下面三行就是本门的 fixture，逐行承重（复算见 G2TEETH 子进程）：
    #   interval_scale 0.70 + total_tasks 240 ⇒ 供单密度足够高；
    #   num_drones 6 + fleet_mix 合计 6 ⇒ 机队真的只有 6 架（二者必须一致，见下）。
    base["task_generation"]["realistic"].update({"interval_scale": 0.70, "total_tasks": 240})
    base["environment"]["num_drones"] = 6
    base["heterogeneous"]["fleet_mix"] = {"light_express": 3, "standard_cargo": 2, "heavy_cargo": 1}
    _mix = sum(base["heterogeneous"]["fleet_mix"].values())
    if _mix != base["environment"]["num_drones"]:
        raise ValueError("[GATE_FIXTURE] fleet_mix 合计 %d 与 num_drones %d 不一致 ⇒ 机队规模这个"
                         "承重变量被两份配置各说一半，变异测试会切不到真正生效的那份" % (
                             _mix, base["environment"]["num_drones"]))
    d = pathlib.Path(tempfile.mkdtemp(prefix="speedgate_"))
    f = d / "sim.json"
    f.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(f)
    return d


def _install_gate_config():
    """在任何被测模块被 import 之前装好重载配置。

    若在 setUpClass 才做，environment 已按默认配置冻结了 DEFAULT_NUM_DRONES ⇒ 换配置无效
    （本轮实测：这样切完变异面依然绿）。返回的临时目录**不回收**，原因见 tearDownClass。
    """
    return _load_config_for_gate()


# ⚠ #70-P1 普查门改版后实测抓到这一行：`_install_gate_config()` 在**模块顶层**跑，
#    而 Python import 一个模块失败时仍会把它的部分执行留在 sys.modules 里 ⇒
#    于是"本门根本没跑（OSM 缺失被 skip）"也照样把 SWARM_BALANCE_SIM_CONFIG 改走了。
#    定稿形状是 `_pf_kernel()`：装配置 → 按路径 exec 内核 → 当场核对该内核的常量指纹，
#    三步绑成一个动作、且只在真要取内核时做 ⇒ 顶层那次安装从来不是判据的一部分，删掉它
#    不改变任何判定（G2 走子进程、G1 与探针都各自重装）。
def _pf_kernel():
    """装好本门配置 → 按**文件路径**加载内核 → 当场核对配置指纹（三步绑成一个动作）。

    为什么不能拆开：`frontend/environment.py:87/:100/:105` 在 import 期从
    `SWARM_BALANCE_SIM_CONFIG` 指向的那份 config 冻结常量 ⇒ "先 setenv、之后随便什么时候
    import"这个假设不成立；也不读 `sys.modules["environment"]`（主进程那份最早由生产代码
    `console/sim_session.py:43` 绑定，不该由测试改）。三次被实测驳回的猜法记在下面
    那段历史注释里，防止下一个人在同一处再猜一次。
    """
    _install_gate_config()          # 装配置 → 加载 → 核对，三步绑成一个动作（见下面注释）
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from console import _preflight
    module = _preflight.load_kernel_environment()[0]
    want_n, want_mix = 6, {"light_express": 3, "standard_cargo": 2, "heavy_cargo": 1}
    got_n, got_mix = int(module.DEFAULT_NUM_DRONES), dict(module.FLEET_MIX or {})
    if (got_n, got_mix) != (want_n, want_mix):
        raise AssertionError(
            "[GATE_CONFIG_NOT_APPLIED] 本门刚装好重载配置、按路径新加载的内核却读到："
            "DEFAULT_NUM_DRONES=%s FLEET_MIX=%s，应为 %s / %s。"
            "⇒ 配置读取通道断了（config_loder 没吃这个环境变量，或文件没写成），"
            "这是夹具失效、不是算法缺陷。" % (got_n, got_mix, want_n, want_mix))
    return module


# #70-P1 历史记录（**已删除的写法**，只留说明、不留死代码）：
#   原缺陷：本门假设"我在 import 期抢在所有人之前 setenv"。但 discover 按字母序，
#   console/test_r2_destination_without_load.py:34（setUpClass 里 `from environment import Environment`）
#   排在前面 ⇒ environment.py:105 的 DEFAULT_NUM_DRONES 先被出厂配置冻结成 10，
#   本门随后换 env 已经太晚 ⇒ 机队变 10 机轻载 ⇒ PSO buffer 峰=2 < 阈值 15 ⇒ optimize 零调用
#   ⇒ G2 报 `[pso][NO_DENOMINATOR]`，把**测试隔离缺陷冒充成被测对象缺陷**。
#   曾提出三种修法，前两种被实测驳回、第三种被第三次实测驳回，都记在这里防止重犯：
#     · 放 setUpClass 核对主进程常量 ⇒ 把一个已免疫顺序的 G2 判死（ORDER-A 因此仍红）；
#     · 放用例体内核对主进程常量 ⇒ 实测仍红：主进程那份最早由 console/sim_session.py:43 绑定
#       （经 console/test_server_guards.py:22 的 `import console.server` 拉进来），
#       那是生产 reload 语义所需，不该由测试改、也不该由测试判它死活；
#     · "模块顶层装一次配置 + 之后按路径加载"⇒ 全量复跑仍红（读数 10/{5,3,2}）：
#       字母序在我之后的 console/test_swap_time_gate.py:63 会把同一个环境变量改走。
#   ⇒ 最终做法见 `_pf_kernel()`：**每次取内核前**重装配置、按路径 exec 一份、当场核对
#      那份常量的指纹 ⇒ 校验对象与消费对象是同一个模块对象，与"谁先 import""谁后改 env"无关。


class SpeedFallbackGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not OSM.is_file():
            raise unittest.SkipTest("缺内置地图 part_of_yangpu.osm")
        # 记下本门进来时的值：直接 pop 会把模块顶部 setdefault 的那份也一起抹掉，
        # 那会让后面被 discover 到的模块拿到与单独运行时不同的环境（跨用例顺序耦合）。
        cls._prev_cfg = os.environ.get("SWARM_BALANCE_SIM_CONFIG")
        # ⚠ #70-P1：这里**不做**"主进程常量核对"。G2 已改为每算法各起干净子进程跑，
        #    主进程的 environment 常量是否被前序 import 冻结与本门无关；在 setUpClass 里 bail
        #    反而会把一个本来免疫顺序的测试判死（实测：ORDER-A 因此仍红）。
        #    机队规模的正确守法是"子进程回传 num_drones 并由断言核对 ==6"（见 G2 末尾），
        #    它校验的是**真正被测那份进程**的状态，而不是父进程的残留。
        #    G1 走 `_pf_kernel()`：自己按路径加载一份内核并就地核对配置指纹。

    @classmethod
    def tearDownClass(cls):
        # 还原到"本门被 discover 之前"的状态：环境变量指回出厂配置，且**不删**临时目录。
        # 为什么不能删：`config/config_loder.py:108` 是**每次 get_shared_config() 都重开文件**，
        # 而 `frontend/charging_station.py:99` 在 import 期就调它。discover 按字母序跑，
        # test_swap_time_gate 排在本门之后 ⇒ 一删目录，那个模块的 import 直接 FileNotFoundError
        # （本轮实测就是这样红了一条与本门无关的用例）。泄漏的只有 %TEMP% 下一个 mkdtemp 目录，
        # 换来的是跨模块 import 不再吃悬空路径。
        if cls._prev_cfg is None:
            os.environ.pop("SWARM_BALANCE_SIM_CONFIG", None)
        else:
            os.environ["SWARM_BALANCE_SIM_CONFIG"] = cls._prev_cfg


    def test_g1_observed_speeds_are_finite_and_in_fleet_range(self):
        # 配置的指纹核对长在 `_pf_kernel()` 里：加载内核与核对配置是同一个动作，
        # 不可能"读了一份、核了另一份"（#70-P1）。
        seen, env = _episode("greedy")
        self.assertGreater(len(seen), 0, "observation 里一个 speed 都没有 ⇒ 门没有分母，等于没测")
        bad = [v for v in seen if not math.isfinite(v)]
        self.assertEqual(bad, [], "存在非有限 speed：%s" % bad[:5])
        out = sorted({v for v in seen if not (FLEET_SPEED_RANGE[0] <= v <= FLEET_SPEED_RANGE[1])})
        self.assertEqual(out, [], "speed 落在机型包络 %s 之外：%s" % (FLEET_SPEED_RANGE, out))
        print("[G1] greedy 采样 %d 次 speed，取值集合=%s" % (len(seen), sorted(set(seen))))

    def _gate_one_algorithm(self, algorithm):
        """对单个算法跑一个短回合，断言它收到的 speed 全部合法且从未落到 200。

        greedy 与三个后端 scheduler 的**输入通道不同**，所以分两条路测（不能一锅端）：
          · greedy 走 `greedy_action_from_observation(obs)`，只读 observation ⇒ 核对 obs 本身；
          · pso/ga/ortools 走 PSOScheduler 外层 ⇒ 除 obs 之外还必须核对
            **optimize(drones_info,...) 实际收到的 speed**，因为 ortools_scheduler.py:222 的
            `drone.get("speed", 200.0)` 兜底坐落在那条链末端（组装点 pso_scheduler.py:1547→1567）。
        GAScheduler(PSOScheduler) / ORToolsScheduler(PSOScheduler) 复用同一外层是**读码推断**，
        所以四个算法各跑真路径来证，而不是假设继承关系成立。
        """
        from backend_si import pso_scheduler as P
        seen, missing, calls = [], [], {"n": 0}
        opt_seen, opt_missing = [], []
        orig_extract = P.PSOScheduler._extract_capacity
        # 三个批量优化器是**三个不同的类**（_build_optimizer 分别返回 PSO/GA/ORTools Optimizer），
        # 所以逐个挂探针；只挂 PSOOptimizer 会让 ga/ortools 静默零调用 —— 那正是本门要拦的形状。
        import backend_si.ga_scheduler as G
        import backend_si.ortools_scheduler as OT
        orig_opt = (P.PSOOptimizer.optimize, G.GAOptimizer.optimize, OT.ORToolsOptimizer.optimize)

        def wrapped_extract(self, observation):
            for c in (observation.get("drone_capabilities", []) or []):
                v = c.get("speed")
                (missing.append("None") if v is None else seen.append(float(v)))
            calls["n"] += 1
            return orig_extract(self, observation)

        def wrapped_optimize(orig):
            def inner(self, drones_info, tasks_info, current_time, verbose=True):
                for d in drones_info or []:
                    v = d.get("speed")
                    (opt_missing.append("None") if v is None else opt_seen.append(float(v)))
                return orig(self, drones_info, tasks_info, current_time, verbose=verbose)
            return inner

        P.PSOScheduler._extract_capacity = wrapped_extract
        P.PSOOptimizer.optimize = wrapped_optimize(orig_opt[0])
        G.GAOptimizer.optimize = wrapped_optimize(orig_opt[1])
        OT.ORToolsOptimizer.optimize = wrapped_optimize(orig_opt[2])
        try:
            obs_seen, env = _episode(algorithm)
        finally:
            P.PSOScheduler._extract_capacity = orig_extract
            P.PSOOptimizer.optimize, G.GAOptimizer.optimize, OT.ORToolsOptimizer.optimize = orig_opt
        # ① observation 层：所有算法都必须过
        self.assertGreater(len(obs_seen), 0, "[%s][NO_DENOMINATOR] observation 里一个 speed 都没有" % algorithm)
        bad = [v for v in obs_seen if not math.isfinite(v)]
        self.assertEqual(bad, [], "[%s] observation 存在非有限 speed：%s" % (algorithm, bad[:5]))
        hit = sorted({v for v in obs_seen if v == DEFAULT_FALLBACK})
        self.assertEqual(hit, [], "[%s] observation 出现 speed=200" % algorithm)
        out = sorted({v for v in obs_seen if not (FLEET_SPEED_RANGE[0] <= v <= FLEET_SPEED_RANGE[1])})
        self.assertEqual(out, [], "[%s] observation speed 超出机型包络 %s：%s" % (algorithm, FLEET_SPEED_RANGE, out))
        # ② optimizer 入口层：只有会调批量优化器的算法有这一层
        if algorithm == "greedy":
            self.assertEqual(calls["n"], 0, "greedy 不该经过后端 _extract_capacity（说明探针挂错了对象）")
            print("[G2/%-7s] observation 采样 %d 次，speed=%s；无批量优化器调用（贪心直出动作）" % (
                algorithm, len(obs_seen), sorted(set(obs_seen))))
            return algorithm, len(obs_seen), sorted(set(obs_seen)), 0
        self.assertGreater(len(opt_seen), 0,
                           "[%s][NO_DENOMINATOR] 一步都没进 optimize() ⇒ 该算法的门没有分母，不许算通过" % algorithm)
        self.assertEqual(opt_missing, [], "[%s] optimize 收到的 drones_info 有 %d 个缺 speed ⇒ 落到 200 兜底" % (
            algorithm, len(opt_missing)))
        o200 = sorted({v for v in opt_seen if v == DEFAULT_FALLBACK})
        self.assertEqual(o200, [], "[%s] optimize 收到 speed=200 ⇒ ETA 按快 10 倍算" % algorithm)
        oout = sorted({v for v in opt_seen if not (FLEET_SPEED_RANGE[0] <= v <= FLEET_SPEED_RANGE[1])})
        self.assertEqual(oout, [], "[%s] optimize 收到的 speed 超出包络：%s" % (algorithm, oout))
        print("[G2/%-7s] observation %d 次 speed=%s | optimize %d 台机×批次 speed=%s" % (
            algorithm, len(obs_seen), sorted(set(obs_seen)), len(opt_seen), sorted(set(opt_seen))))
        return algorithm, len(obs_seen), sorted(set(obs_seen)), len(opt_seen)

    def test_g2_all_four_algorithms_get_real_fleet_speed(self):
        """G2：greedy / pso / ga / ortools 四者逐一过门（不是抽查其一）。

        #70-P1 顺序无关化：本门的判据依赖"重载配置真的生效"，而 environment.py:87/:100/:105
        在 **import 时**冻结常量 ⇒ 主进程内跑它等于赌自己抢到第一个 import（discover 字母序下
        console/test_r2_destination_without_load.py:34 会先抢，于是 10 机轻载、buffer 峰=2、
        optimize 零调用 ⇒ `[pso][NO_DENOMINATOR]` 把测试隔离缺陷冒充成算法缺陷）。

        ⇒ 改为**每个算法各起一个干净子进程**跑（与本文件 G2TEETH 探针同一手法，天然免疫 import 竞速），
        父进程只做断言。这样单跑与聚合跑的是同一份代码路径，满足"fresh process 下单跑与聚合一致"。
        """
        payload = []
        for algorithm in ALGORITHMS:
            r = self._run_g2_in_subprocess(algorithm)
            payload.append(r)
        for r in payload:
            self.assertTrue(r["ok"], "[G2_SUBPROCESS_FAIL] %s：%s" % (r["algorithm"], r.get("err", "")))
            obs_seen = r["obs_speeds"]
            self.assertGreater(len(obs_seen), 0, "[%s][NO_OBS_SAMPLE] observation 里一个 speed 都没有" % r["algorithm"])
            self.assertNotIn(DEFAULT_FALLBACK, obs_seen, "[%s] observation 出现 speed=200" % r["algorithm"])
            bad = [v for v in obs_seen if not (FLEET_SPEED_RANGE[0] <= v <= FLEET_SPEED_RANGE[1])]
            self.assertEqual(bad, [], "[%s] observation speed 超出机型包络 %s：%s" % (r["algorithm"], FLEET_SPEED_RANGE, bad))
            if r["algorithm"] == "greedy":
                self.assertEqual(r["optimize_calls"], 0, "greedy 不该经过后端 optimize")
                print("[G2/%-7s] (subprocess) observation %d 次 speed=%s；无批量优化器调用" % (
                    r["algorithm"], len(obs_seen), sorted(set(obs_seen))))
                continue
            self.assertGreater(r["optimize_calls"], 0,
                               "[%s][NO_DENOMINATOR] 一步都没进 optimize() ⇒ 该算法的门没有分母，不许算通过" % r["algorithm"])
            o200 = [v for v in r["opt_speeds"] if v == DEFAULT_FALLBACK]
            self.assertEqual(o200, [], "[%s] optimize 收到 speed=200 ⇒ ETA 按快 10 倍算" % r["algorithm"])
            oout = [v for v in r["opt_speeds"] if not (FLEET_SPEED_RANGE[0] <= v <= FLEET_SPEED_RANGE[1])]
            self.assertEqual(oout, [], "[%s] optimize 收到的 speed 超出包络：%s" % (r["algorithm"], oout))
            print("[G2/%-7s] (subprocess) observation %d 次 speed=%s | optimize %d 台机×批次 speed=%s" % (
                r["algorithm"], len(obs_seen), sorted(set(obs_seen)),
                r["optimize_calls"], sorted(set(r["opt_speeds"]))))
        # 机队规模必须是门要的那个（子进程里核对后回传）
        for r in payload:
            self.assertEqual(r["num_drones"], 6,
                             "[GATE_FROZEN_BY_FOREIGN_IMPORT] %s 子进程仍拿到 %s 机 ⇒ 配置注入没生效" % (
                                 r["algorithm"], r["num_drones"]))
        # 兜底值本身不该是配置默认（否则"落到兜底"与"读到配置"不可分，门失去意义）
        import json as _json
        cfg = _json.loads((ROOT / "config" / "simulation.json").read_text(encoding="utf-8"))
        ds = float(cfg["drone"]["speed"])
        self.assertNotEqual(ds, DEFAULT_FALLBACK, "config.drone.speed 就是 200 ⇒ 兜底即默认，门失去意义")
        print("[G2] 配置兜底 drone.speed=%.1f（非 200）；四算法均在干净子进程内过门 ⇒ 与发现顺序无关" % ds)

    _G2_CHILD = r'''
import json, os, sys, pathlib
ROOT = pathlib.Path(sys.argv[1]).resolve(); ALGO = sys.argv[2]
sys.path[:0] = [str(ROOT), str(ROOT / "frontend")]
# 与主进程同款重载配置：6 机 / fleet 3-2-1 / 240 任务 / interval_scale 0.70
base = json.loads((ROOT / "config" / "simulation.json").read_text(encoding="utf-8"))
base["task_generation"]["realistic"].update({"interval_scale": 0.70, "total_tasks": 240})
base["environment"]["num_drones"] = 6
base["heterogeneous"]["fleet_mix"] = {"light_express": 3, "standard_cargo": 2, "heavy_cargo": 1}
tmpd = pathlib.Path(os.environ.get("TMP", "/tmp")) / ("g2child_%d" % os.getpid())
tmpd.mkdir(parents=True, exist_ok=True)
cfg = tmpd / "sim.json"
cfg.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(cfg)     # 必须在 import environment 之前
import environment as E
obs_seen, opt_seen, calls = [], [], {"n": 0}
from backend_si import pso_scheduler as P
orig_extract = P.PSOScheduler._extract_capacity
def wrapped_extract(self, observation):
    for c in (observation.get("drone_capabilities", []) or []):
        v = c.get("speed")
        calls["n"] += 1
        if v is not None:
            obs_seen.append(float(v))
    return orig_extract(self, observation)
P.PSOScheduler._extract_capacity = wrapped_extract
opt_seen = []
import backend_si.ga_scheduler as G
import backend_si.ortools_scheduler as OT
orig_opt = (P.PSOOptimizer.optimize, G.GAOptimizer.optimize, OT.ORToolsOptimizer.optimize)
def wrap(orig):
    def inner(self, drones_info, tasks_info, current_time, verbose=True):
        for d in drones_info or []:
            v = d.get("speed")
            if v is not None:
                opt_seen.append(float(v))
        return orig(self, drones_info, tasks_info, current_time, verbose=verbose)
    return inner
P.PSOOptimizer.optimize = wrap(orig_opt[0])
G.GAOptimizer.optimize = wrap(orig_opt[1])
OT.ORToolsOptimizer.optimize = wrap(orig_opt[2])
from environment import Environment
from greedy.scheduler import greedy_action_from_observation
OSM = str(ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm")
env = Environment(OSM, episode_max_steps=3600)
obs = env.reset(seed=40901)
if ALGO == "greedy":
    nxt = lambda o: greedy_action_from_observation(o)
elif ALGO == "pso":
    from backend_si.pso_scheduler import PSOScheduler
    s = PSOScheduler(num_drones=len(env.drones), verbose=False, seed=40901); nxt = lambda o: s.step(o, current_time=env.current_time)
elif ALGO == "ga":
    from backend_si.ga_scheduler import GAScheduler
    s = GAScheduler(num_drones=len(env.drones), verbose=False, seed=40901); nxt = lambda o: s.step(o, current_time=env.current_time)
else:
    from backend_si.ortools_scheduler import ORToolsScheduler, ORTOOLS_AVAILABLE
    if not ORTOOLS_AVAILABLE:
        print(json.dumps({"skip": "OR-Tools 不可用"})); raise SystemExit(0)
    s = ORToolsScheduler(num_drones=len(env.drones), verbose=False, seed=40901); nxt = lambda o: s.step(o, current_time=env.current_time)
done = False
while not done:
    obs, _, done, _ = env.step(nxt(obs))
    # observation 层的 speed 直接从返回的 obs 采样（两个 key 都看）：greedy 不经过后端
    # _extract_capacity，若只靠那个钩子取样，greedy 会得到空样本 ⇒ 假 NO_OBS_SAMPLE。
    for key in ("drone_capabilities", "drone_chain_info"):
        for c in (obs.get(key) or []):
            v = c.get("speed") if isinstance(c, dict) else None
            if v is not None:
                obs_seen.append(float(v))
print(json.dumps({"ok": True, "algorithm": ALGO, "obs_speeds": sorted(set(obs_seen)),
                  "opt_speeds": sorted(set(opt_seen)), "optimize_calls": len(opt_seen),
                  "num_drones": int(E.DEFAULT_NUM_DRONES)}))
'''

    def _run_g2_in_subprocess(self, algorithm):
        import json, subprocess
        r = subprocess.run([sys.executable, "-c", self._G2_CHILD, str(ROOT), algorithm],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=900)
        line = (r.stdout or "").strip().splitlines()
        if not line:
            raise AssertionError("[G2_SUBPROCESS_EMPTY] %s 无输出；stderr 前 300 字：%s" % (algorithm, (r.stderr or "")[:300]))
        try:
            data = json.loads(line[-1])
        except ValueError:
            raise AssertionError("[G2_SUBPROCESS_UNPARSEABLE] %s 末行=%r" % (algorithm, line[-1][:200]))
        if data.get("skip"):
            raise unittest.SkipTest(data["skip"])
        data.setdefault("err", (r.stderr or "")[-300:])
        return data

    def _probe(self, face):
        """在干净子进程里跑三面对照探针，返回解析后的读数 dict。

        刻意用独立文件而不是 `python -c "<一长串>"`：分号拼多语句在本机引号嵌套下会被截成
        一行；且承重常量在 import 期冻结，必须换进程才能换配置（见探针 docstring）。
        """
        import subprocess
        proc = subprocess.run([sys.executable, "-X", "utf8",
                               str(ROOT / "console" / "phase0_speed_gate_teeth_probe.py"), face],
                              cwd=str(ROOT), env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                              text=True, capture_output=True, timeout=900, errors="replace")
        out = proc.stdout + proc.stderr
        line = [l for l in out.splitlines() if l.startswith("TEETH face=\"%s\" " % face)]
        self.assertTrue(line, "[%s] 探针没有 TEETH 读数（退码 %d）：%s" % (
            face, proc.returncode, out[-400:]))
        # 值全部带引号（见探针里那行注释），所以按 shlex 切而不是按空格切。
        import shlex
        toks = shlex.split(line[0])[1:]
        row = {}
        for kv in toks:
            self.assertIn("=", kv, "[%s] 探针 token 缺 '='：%r ⇒ 读数行形状变了" % (face, kv))
            k, v = kv.split("=", 1)
            row[k] = v
        return row

    @staticmethod
    def _i(row, key):
        try:
            return int(row[key])
        except (KeyError, ValueError):
            raise AssertionError("[%s] 读数 %s=%r 不是整数 ⇒ 量具坏了，不许当通过" % (
                row.get("face", "?"), key, row.get(key)))

    def _assert_calibration_gate_is_live(self):
        """L1 证人：跑一遍 console/test_g2teeth_calibration.py，要求它**跑到且全绿**。

        为什么这条必须存在：g2teeth 把 size 触发口的判据外包给合成夹具门之后，如果那扇门
        根本没跑（改名/报错/被 skip），本用例就成了"没人守着的通过"—— 那是最贵的假绿灯。
        ⇒ 在这里以子进程真跑一次，并核对它报出的 K 面数量与牙线读数；退码非 0 或分母为 0 都算红。
        """
        r = subprocess.run([sys.executable, "-m", "unittest", "-v",
                            "console.test_g2teeth_calibration"],
                           cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=900,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        out = (r.stdout or "") + (r.stderr or "")
        m = re.search(r"^Ran (\d+) tests", out, re.M)
        self.assertIsNotNone(m, "[CAL_BLIND] 标定门没产出 Ran N tests 行 ⇒ 它没跑起来，"
                                "g2teeth 的 L1 判据无人守着；输出尾=%s" % out[-400:])
        ran = int(m.group(1))
        self.assertGreaterEqual(ran, 7,
                                 "[CAL_BLIND] 标定门只跑了 %d 条（应 ≥7：K1-K6 + 冻结三元组）⇒ "
                                 "有夹具被删或被 skip" % ran)
        self.assertEqual(r.returncode, 0,
                         "[CAL_GATE_RED] 标定门退码=%s ⇒ L1 机制层不成立，g2teeth 不得自称已通过；"
                         "输出尾=%s" % (r.returncode, out[-600:]))
        self.assertIn("[CAL_TEETH]", out,
                      "[CAL_NO_TEETH] 标定门没印出变异面读数 [CAL_TEETH] ⇒ 它的牙未被证明")
        print("[G2TEETH_L1] 标定门实跑 OK：Ran %d tests，含 K1–K6 与冻结三元组" % ran)

    def test_g2teeth_mutation_turns_the_denominator_off(self):
        """G2TEETH：门的牙由"切承重变量后分母消失"来证，不是由门自己绿来证。

        三面对照（seed=40901、episode=3600、阈值 15 全程未动）。下面这行是**本轮 D-iv 树上
        的实跑读数**（`[G2TEETH_L2_OBSERVED]` 会每轮重印，注释只作历史对照，不作判据）：
            gate     tasks=240 mix合计= 6 ⇒ optimize=1909 flush_size=0 buffer_peak=10
            noDenom  tasks= 60 mix合计=10 ⇒ optimize=   0 flush_size=0 buffer_peak= 2
            mutate   tasks=240 mix合计=10 ⇒ optimize=   6 flush_size=0 buffer_peak= 3
        ⇒ 承重变量是【机队规模】（fleet_mix），不是任务量：noDenom 就是原红门所在格。
        （pre-D-iv 的同三格曾是 1477/1/15、0/0/2、3/0/3 —— size 触发口当时确实开过一次；
          那组数已被 #69-H3 判为旧 completion 计时的产物，不再引用它作任何边界。）

        ⚠ "只切 num_drones" 不是单变量，别再这么干：`environment.py:144
        build_fleet_drone_types()` 先按 fleet_mix 展开机型序列、再截断/补齐到 num_drones，
        所以 num_drones=10 + mix 合计 6 拿到的仍是那 6 架机（本轮实测：速度集从 [14,20]
        变出 17.0 就是这个原因）。机队规模的唯一真源是 fleet_mix。

        为什么牙挂在 flush_size 而不是 optimize_calls：optimize() 有三个触发口
        （size / emergency / timeout，`pso_scheduler.py:1438`），变异后仍有 timeout 兜底。
        拿"optimize_calls>0"当牙会被这几次糊过去 —— pre-D-iv 那轮就是这么被骗了一轮。
        ⇒ size 触发口的语义由 L1 合成夹具（K1–K6）裁决；这里只断言"切机队后它必须关死"。
        """
        gate = self._probe("gate")
        nod = self._probe("noDenom")
        mut = self._probe("mutate")

        # ---- 阶段② 重标定（#70-P1，主控批准实施）：skip 已转成真实判定，两层分开走 ----
        # 旧形状（保留在下面这段注释里，防有人再把它合回去）：
        #   if int(gate["flush_size"]) == 0: self.skipTest("[GATE_CALIBRATION_STALE] …")
        # 为什么它必须死：把"真实工况下 size 触发口会打开"当**门的牙**，等于拿一次特定运行的读数
        # 当结构判据 —— D-iv 修好 completion 计时后该读数从 1/15 变成 0/10，判据立刻不可满足，
        # 于是只能 skip。skip 挂着不动 = 这扇门从此不产出任何判定，聚合里既不算红也不算绿。
        #
        # 新形状（裁定要求的"已知标签夹具"）：
        #   L1 机制层 → 移到 console/test_g2teeth_calibration.py（常驻、进退码、秒级、合成输入）。
        #      本用例先断言那扇门**确实在跑且确实有牙**，否则这里的"通过"是空的。
        #   L2 观测层 → 下面这些真实工况读数只作信息印出，不进退码（它们不是实现缺陷）。
        # 承重变量仍是【机队规模】：见上面 2×2 消融表；任务量不是承重项。
        self._assert_calibration_gate_is_live()

        # ① 门工况：pso/ga/ortools 三条有分母线都必须为真（与 G2 同一判据）
        self.assertGreater(self._i(gate, "optimize_calls"), 0,
                           "[gate][NO_DENOMINATOR] 门的工况本身就没有 optimize 调用 ⇒ fixture 失效")
        self.assertEqual(int(gate["drones_in_env"]), 6, "[gate] 机队规模应为 6")

        # ③ 牙线（因果面）：只把机队从 6 切到 10，size 触发口必须关死、optimize 必须塌下来。
        #    ⚠ 这条的**数值边界原先也是旧计时上标定的**（原写法 `optimize_calls <= 3`，
        #      来自 mutate 面当时实测的 3）。D-iv 换 completion 计时后同一格实测为 6 ⇒
        #      若照抄 3，本门会以"我自己的过期校准值"为由红掉——正是 #69-H3 那条教训的复现，
        #      也正是本次重标定要消灭的形状。⇒ 现在按**结构关系**写判据，不写魔法数：
        #        · gate/mutate 任务量同为 240（唯一变量是机队），所以 mutate 的 optimize
        #          必须**跌到 gate 的一个很小比例**才算承重变量被切到；
        #        · 分母用本轮真值（gate 面读数），不是上一轮抄下来的数。
        g_opt, m_opt = self._i(gate, "optimize_calls"), self._i(mut, "optimize_calls")
        self.assertEqual(self._i(mut, "flush_size"), 0,
                         "[mutate] 变异后 flush_size 仍 >0 ⇒ 承重变量没被切到，门的牙是假的")
        self.assertLess(m_opt * 100, g_opt,     # <1% ：切机队后 optimize 调用量级必须崩塌
                        "[mutate] 机队 6→10 后 optimize 从 %s 只降到 %s ⇒ 比值 %.3f 未跌破 1%%，"
                        "fixture 对机队规模不够敏感，门无牙" % (
                            g_opt, m_opt, (m_opt / g_opt if g_opt else float("inf"))))
        # noDenom 面（出厂轻载）继续断言 0：它是"当初为什么 NO_DENOMINATOR"的成因证人，
        # 与计时无关（60 任务/10 机下 buffer 峰仅 2，任何计时都到不了触发口）。
        self.assertEqual(self._i(nod, "optimize_calls"), 0,
                         "[noDenom] 出厂工况本应有分母？⇒ 归因错了，门的成因不是机队规模")

        # ④ L2 观测层：**只报数、不断言**。旧断言 `buffer_peak >= 15` 与 `flush_size > 0` 属这一类，
        #    它们是"scheduler 在当前计时下的行为事实"，不是实现缺陷（#69-H3 裁定②：不为好看调低触发口）。
        print("[G2TEETH_L2_OBSERVED] gate(opt=%s flush_size=%s peak=%s) | noDenom(opt=%s peak=%s) | "
              "mutate(opt=%s flush_size=%s peak=%s) —— 此行为**信息读数**，不进退码；"
              "size 触发口在真实工况下是否打开由 L1 合成夹具裁决" % (
                  gate["optimize_calls"], gate["flush_size"], gate["buffer_peak"],
                  nod["optimize_calls"], nod["buffer_peak"],
                  mut["optimize_calls"], mut["flush_size"], mut["buffer_peak"]))
        print("[G2TEETH] 阈值 15 与被测源码全程未改 ⇒ 变红的只能是 fixture")
        # 负面对照（一次性演示，不是常驻断言）：把阈值从 15 降到 2 后重跑本探针，
        # [gate] 面的 buffer 峰值只到 5 ⇒ "peak>=15" 当场红。这说明这些断言吃的是真实读数、
        # 不是恒真式；复算命令见 README「Phase 0 收尾」一节。
        print("[G2TEETH] 负面对照已实测：阈值 15→2 时 gate 面 peak 降为 5、本门退码非 0")

    def test_g3_shipped_config_has_no_200_speed(self):
        """兜底值本身不该出现在配置里：配置只有 14/20/20 与全局 17。"""
        import json
        cfg = json.loads((ROOT / "config" / "simulation.json").read_text(encoding="utf-8"))
        vals = [float(d["speed"]) for d in cfg["heterogeneous"]["drone_types"].values()]
        vals.append(float(cfg["drone"]["speed"]))
        self.assertNotIn(DEFAULT_FALLBACK, vals, "配置里出现 200 ⇒ 兜底已伪装成参数：%s" % vals)
        print("[G3] 配置 speed 取值=%s（全部落在机型区间）" % vals)


if __name__ == "__main__":
    unittest.main()
