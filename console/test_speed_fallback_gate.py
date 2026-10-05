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
    """跑一个短回合，返回每一步 observation 里出现的 speed 值列表。"""
    from environment import Environment
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


_install_gate_config()


class SpeedFallbackGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not OSM.is_file():
            raise unittest.SkipTest("缺内置地图 part_of_yangpu.osm")
        # 记下本门进来时的值：直接 pop 会把模块顶部 setdefault 的那份也一起抹掉，
        # 那会让后面被 discover 到的模块拿到与单独运行时不同的环境（跨用例顺序耦合）。
        cls._prev_cfg = os.environ.get("SWARM_BALANCE_SIM_CONFIG")

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
        """G2：greedy / pso / ga / ortools 四者逐一过门（不是抽查其一）。"""
        results = [self._gate_one_algorithm(a) for a in ALGORITHMS]
        import json
        cfg = json.loads((ROOT / "config" / "simulation.json").read_text(encoding="utf-8"))
        ds = float(cfg["drone"]["speed"])
        self.assertNotEqual(ds, DEFAULT_FALLBACK, "config.drone.speed 就是 200 ⇒ 兜底即默认，门失去意义")
        for alg, n, vals, opt_n in results:
            # 4 元组：_gate_one_algorithm 从 1B-* 起多返回一个 optimize 调用数。
            # 这处解包此前从未被执行到（pso 在上面就 assert 失败），门有分母后才暴露成
            # ValueError ⇒ 修 fixture 顺带抓出一个真实的测试缺陷，不是本次改坏的。
            print("[G2/%-7s] _extract_capacity %d 次 / optimize 入口 %d 台机·批次，speed=%s"
                  % (alg, n, opt_n, vals))
        print("[G2] 配置兜底 drone.speed=%.1f（非 200）" % ds)

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

    def test_g2teeth_mutation_turns_the_denominator_off(self):
        """G2TEETH：门的牙由"切承重变量后分母消失"来证，不是由门自己绿来证。

        三面对照（seed=40901、episode=3600、阈值 15 全程未动）：
            gate     tasks=240 mix合计= 6 ⇒ optimize=1477  flush_size=1  buffer_peak=15
            noDenom  tasks= 60 mix合计=10 ⇒ optimize=   0  flush_size=0  buffer_peak= 2
            mutate   tasks=240 mix合计=10 ⇒ optimize=   3  flush_size=0  buffer_peak= 3
        ⇒ 承重变量是【机队规模】（fleet_mix），不是任务量：noDenom 就是原红门所在格。

        ⚠ "只切 num_drones" 不是单变量，别再这么干：`environment.py:144
        build_fleet_drone_types()` 先按 fleet_mix 展开机型序列、再截断/补齐到 num_drones，
        所以 num_drones=10 + mix 合计 6 拿到的仍是那 6 架机（本轮实测：速度集从 [14,20]
        变出 17.0 就是这个原因）。机队规模的唯一真源是 fleet_mix。

        为什么牙挂在 flush_size 而不是 optimize_calls：optimize() 有三个触发口
        （size / emergency / timeout，`pso_scheduler.py:1438`），变异后仍有 3 次 timeout 兜底。
        拿"optimize_calls>0"当牙会被这 3 次糊过去 —— 本轮就是这么被骗了一轮。
        """
        gate = self._probe("gate")
        nod = self._probe("noDenom")
        mut = self._probe("mutate")

        # ① 门工况：pso/ga/ortools 三条有分母线都必须为真（与 G2 同一判据）
        self.assertGreater(self._i(gate, "optimize_calls"), 0,
                           "[gate][NO_DENOMINATOR] 门的工况本身就没有 optimize 调用 ⇒ fixture 失效")
        self.assertEqual(int(gate["drones_in_env"]), 6, "[gate] 机队规模应为 6")
        self.assertGreaterEqual(self._i(gate, "buffer_peak"), 15,
                                "[gate] buffer 峰值没到过阈值 15 ⇒ size 触发口从未打开，"
                                "门是在靠别的触发口蒙混")

        # ② 原红门复现：出厂轻载下 optimize 必须为 0 —— 这行证明"当初为什么 NO_DENOMINATOR"
        self.assertEqual(self._i(nod, "optimize_calls"), 0,
                         "[noDenom] 出厂工况本应有分母？⇒ 归因错了，门的成因不是机队规模")

        # ③ 牙线：只把机队从 6 切到 10，size 触发口必须关死
        self.assertEqual(self._i(mut, "flush_size"), 0,
                         "[mutate] 变异后 flush_size 仍 >0 ⇒ 承重变量没被切到，门的牙是假的")
        self.assertLessEqual(self._i(mut, "optimize_calls"), 3,
                             "[mutate] 变异后 optimize 仍成规模 ⇒ fixture 不依赖机队规模，门无牙")
        self.assertLess(self._i(mut, "buffer_peak"), 15,
                        "[mutate] 变异后 buffer 峰值仍达阈值 ⇒ 同上")

        print("[G2TEETH] gate(opt=%s flush_size=%s peak=%s) | noDenom(opt=%s peak=%s) | "
              "mutate(opt=%s flush_size=%s peak=%s)" % (
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
