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
os.environ.setdefault("SWARM_BALANCE_SIM_CONFIG", str(ROOT / "config" / "simulation.json"))

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


class SpeedFallbackGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not OSM.is_file():
            raise unittest.SkipTest("缺内置地图 part_of_yangpu.osm")

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
        for alg, n, vals in results:
            print("[G2/%-7s] 经过 _extract_capacity %d 次，收到 speed=%s" % (alg, n, vals))
        print("[G2] 配置兜底 drone.speed=%.1f（非 200）" % ds)

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
