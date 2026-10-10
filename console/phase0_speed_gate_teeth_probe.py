# -*- coding: utf-8 -*-
"""G2TEETH 的探针：在**干净子进程**里切单个承重变量，打印 PSO 进优化器的次数。

为什么必须起子进程而不是同进程改配置：`frontend/environment.py:105 DEFAULT_NUM_DRONES`、
`task.py` / `drone.py:22 STEP_SECONDS` 都在 **import 时**从 SWARM_BALANCE_SIM_CONFIG 冻结。
同进程改了再实例化 Environment 也不会生效 —— 本轮我就是因此把"门照样绿"误读成"门无牙"。

三面对照（seed=40901，episode=3600 步，阈值 15 全程未动）：
    gate     tasks=240 mix合计=6 (3,2,1)   ⇒ flush_size= 1  optimize=1477  ← 门的真实工况
    noDenom  tasks= 60 mix合计=10 (5,3,2)  ⇒ flush_size= 0  optimize=   0  ← 原红门所在格（出厂配置）
    mutate   tasks=240 mix合计=10 (5,3,2)  ⇒ flush_size= 0  optimize=   3  ← 只切机队规模

为什么门的牙挂在 **flush_size** 而不是 optimize_calls：optimize() 有三个触发口
（`pso_scheduler.py:1438 _maybe_flush_buffer` 的 size / emergency / timeout），而阈值 15
是工程约束、不许动。实测把机队从 6 架切到 10 架后 size 触发归零，只剩 3 次 timeout 兜底
—— 若拿"optimize_calls>0"当牙，这 3 次就能把它糊过去。所以门的两条线分开：
    · 有分母线（G2 对 pso/ga/ortools 断言）= optimize_calls > 0；
    · 牙线（G2TEETH 的 mutate 面）        = flush_size == 0。
emergency 在轻载下同样不出现（mutate 面 flush_size=0 且 optimize=3 全来自 timeout），
所以用"size 归零 + 总量 ≤ 非零小值"两面夹住，不需要给 emergency 开白名单。

⚠ "只切 num_drones" 不是单变量：`environment.py:144 build_fleet_drone_types()` 按 fleet_mix
  展开机型序列后再截断/补齐到 num_drones，所以 num_drones=10 + mix 合计 6 得到的仍是
  3×20 + 2×14 + 1×20 = 6 架机（本轮实测）。机队规模的**唯一真源是 fleet_mix**，
  变异必须打在 mix 上；fixture 里的恒等式只用于把两者钉在一起、防止两份配置各说一半。

用法：python console/phase0_speed_gate_teeth_probe.py <gate|noDenom|mutate>
输出行前缀 GATEFIX / TEETH，供门解析。
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "frontend"))
OSM = ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm"

MIX_GATE = {"light_express": 3, "standard_cargo": 2, "heavy_cargo": 1}
MIX_LIGHT = {"light_express": 5, "standard_cargo": 3, "heavy_cargo": 2}
FACES = {
    "gate":    dict(tasks=240, mix=MIX_GATE),
    "noDenom": dict(tasks=60,  mix=MIX_LIGHT),
    "mutate":  dict(tasks=240, mix=MIX_LIGHT),
}


def _write_cfg(tasks, mix):
    base = json.loads((ROOT / "config" / "simulation.json").read_text(encoding="utf-8"))
    base["task_generation"]["realistic"].update({"interval_scale": 0.70, "total_tasks": tasks})
    # Isolated fixture counterfactual only: DO NOT bypass the production gate.
    # A speed/PSO denominator test may remove battery exhaustion as a confound.
    _battery_scale = float(os.environ.get("SWARM_G2_DIAG_BATTERY_SCALE", "1.0"))
    if not 1.0 <= _battery_scale <= 100.0:
        raise ValueError("Diagnostic battery scale must be in [1, 100]")
    if _battery_scale != 1.0:
        base["drone"]["battery_capacity"] *= _battery_scale
        for profile in base["heterogeneous"]["drone_types"].values():
            profile["battery_capacity"] *= _battery_scale
    base["heterogeneous"]["fleet_mix"] = mix
    # num_drones 与 mix 合计对齐：见 test_speed_fallback_gate._load_config_for_gate() 的恒等式。
    base["environment"]["num_drones"] = sum(int(v) for v in mix.values())
    d = pathlib.Path(tempfile.mkdtemp(prefix="speedteeth_"))
    f = d / "sim.json"
    f.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    return d, f


def _read_flush_reasons(sch):
    """从 scheduler.stats 读三种 flush 触发口的真实次数（不抄第二份计数）。"""
    return {k: int(sch.stats.get(k, 0)) for k in ("flush_size", "flush_emergency", "flush_timeout")}


def main(face):
    spec = FACES[face]
    tmp, cfg = _write_cfg(**spec)
    os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(cfg)
    try:
        from environment import Environment
        env = Environment(str(OSM), episode_max_steps=3600)
        obs = env.reset(seed=40901)
        n_in_env = len(env.drones)
        speeds = sorted({float(d.speed) for d in env.drones})

        if face == "gate":
            # 跨文件对账：探针自己装的配置必须与门 fixture 逐字段一致，否则下面的对比
            # 不是同一工况（量具与被测物各拿一份参数就是漂移）。
            import test_speed_fallback_gate as G
            gtmp = G._load_config_for_gate()
            g = json.loads((pathlib.Path(gtmp) / "sim.json").read_text(encoding="utf-8"))
            shutil.rmtree(gtmp, ignore_errors=True)
            same = (g["task_generation"]["realistic"]["total_tasks"] == 240 and
                    g["heterogeneous"]["fleet_mix"] == MIX_GATE and
                    g["environment"]["num_drones"] == sum(MIX_GATE.values()))
            print("GATEFIX tasks=%d mix=%s num_drones=%d match_gate=%s" % (
                spec["tasks"], sorted(spec["mix"].values()),
                g["environment"]["num_drones"], same))
            assert same, "[GATEFIX] 探针工况与门 fixture 不一致 ⇒ 对照无效"

        counts = {"n": 0}
        peak = {"p": 0}
        blocked_steps = 0
        blocked_ids = set()
        first_block = None
        from backend_si import pso_scheduler as P
        orig = P.PSOOptimizer.optimize
        orig_maybe = P.PSOScheduler._maybe_flush_buffer

        def wrapped(self, drones_info, tasks_info, current_time, verbose=True):
            counts["n"] += 1
            return orig(self, drones_info, tasks_info, current_time, verbose=verbose)

        def peek(self, observation, current_time):
            # 峰值要在触发**之前**采：flush 会把 pending_buffer 清空，之后采到的永远是 0。
            peak["p"] = max(peak["p"], len(self.pending_buffer))
            return orig_maybe(self, observation, current_time)

        P.PSOOptimizer.optimize = wrapped
        P.PSOScheduler._maybe_flush_buffer = peek
        try:
            from backend_si.pso_scheduler import PSOScheduler
            sch = PSOScheduler(num_drones=n_in_env, verbose=False, seed=40901)
            done = False
            while not done:
                action = sch.step(obs, current_time=env.current_time)
                obs, _, done, _ = env.step(action)
                # P2.2-only diagnostic: read-only blocked-state census after real step().
                # This is not a scheduling intervention or a change to the safety gate.
                blocked_now = [d for d in env.drones
                               if getattr(d, "flight_energy_blocked", False)]
                blocked_steps += len(blocked_now)
                for d in blocked_now:
                    blocked_ids.add(getattr(d, "drone_id", id(d)))
                if blocked_now and first_block is None:
                    d = blocked_now[0]
                    first_block = (float(env.current_time), float(d.current_battery),
                                   float(d.last_energy_required_wh),
                                   len(d.scheduled_position))
            reasons = _read_flush_reasons(sch)
        finally:
            P.PSOOptimizer.optimize = orig
            P.PSOScheduler._maybe_flush_buffer = orig_maybe
        print("[G2_POLICY_TRACE] face=%s blocked_drone_steps=%d blocked_unique=%d "
              "first=(time,battery,required,route_len)=%s flush_size=%d "
              "flush_emergency=%d flush_timeout=%d optimize=%d" % (
                  face, blocked_steps, len(blocked_ids), first_block,
                  reasons["flush_size"], reasons["flush_emergency"],
                  reasons["flush_timeout"], counts["n"]))
        # 每个值都加引号：mix=[...] 内部本身带空格，裸 token 会让门按空格切分时拿到
        # "mix=[1," / "2," ..." 这种残片（本轮实测 ValueError）。
        print('TEETH face="%s" tasks=%d mix="%s" drones_in_env=%d speeds="%s" '
              'optimize_calls=%d flush_size=%d flush_emergency=%d flush_timeout=%d '
              'buffer_peak=%d has_denominator=%s' % (
                  face, spec["tasks"], ",".join(str(v) for v in sorted(spec["mix"].values())),
                  n_in_env, ",".join("%.1f" % s for s in speeds),
                  counts["n"], reasons["flush_size"], reasons["flush_emergency"],
                  reasons["flush_timeout"], peak["p"], counts["n"] > 0))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main(sys.argv[1])
