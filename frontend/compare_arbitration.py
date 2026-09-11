"""机巢泊位仲裁机制量化验证：动态优先级 vs 先到先服务(FIFO) 基线对比。

用法：
    python compare_arbitration.py --seeds 3 --steps 3000 --nests 2 --berths 1

原理：
    在"机巢泊位稀缺"（nests 少 / berths 少）场景下，无人机换电时会在机巢排队，
    本脚本用同样的随机种子分别跑出 priority（电量紧迫+等待+任务）与 fifo（先到先服务）
    两种仲裁策略，对比完成的换电次数、机巢周转率、排队等待与任务完成/超时，量化
    动态优先级仲裁相较于朴素 FIFO 的价值（创新点2 + 缺口1/3 的立论证据）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(FRONTEND_ROOT))

from environment import Environment
from greedy.scheduler import greedy_action_from_observation

OSM = str(FRONTEND_ROOT / "data" / "map" / "part_of_yangpu.osm")

METRICS = [
    "completion_rate", "on_time_rate", "timeout_rate", "avg_delay",
    "total_swap_sessions", "berth_utilization_rate", "nest_turnover_rate",
    "avg_berth_wait_time", "max_berth_wait_time", "avg_urgency_weighted_wait",
    "berth_wait_count",
]


def run(seed: int, steps: int, policy: str, nests: int, berths: int) -> dict:
    env = Environment(OSM, visualize=False, episode_max_steps=steps)
    obs = env.reset(seed=seed)
    env.arbitration_policy = policy
    # 强制机巢竞争：只保留前 nests 个机巢、每个机巢 berths 个泊位
    env.charging_stations = env.charging_stations[:nests]
    for st in env.charging_stations:
        st.berths = max(1, int(berths))
        st.occupied = 0
    for d in env.drones:
        d.known_stations = env.charging_stations
    env._nest_waiting = {st.station_id: [] for st in env.charging_stations}

    done = False
    while not done:
        obs, _, done, _ = env.step(greedy_action_from_observation(obs))
    return env.get_statistics()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3, help="随机种子数")
    ap.add_argument("--start", type=int, default=100, help="起始种子号")
    ap.add_argument("--steps", type=int, default=3000, help="每回合仿真步数")
    ap.add_argument("--nests", type=int, default=2, help="保留的机巢数（制造竞争）")
    ap.add_argument("--berths", type=int, default=1, help="每个机巢泊位数（制造竞争）")
    args = ap.parse_args()

    agg = {p: {k: 0.0 for k in METRICS} for p in ("priority", "fifo")}
    for ep in range(args.seeds):
        seed = args.start + ep + 1
        print(f"--- seed={seed}  (nests={args.nests}, berths={args.berths}) ---")
        for policy in ("priority", "fifo"):
            s = run(seed, args.steps, policy, args.nests, args.berths)
            for k in METRICS:
                agg[policy][k] += s[k]
            print(f"  {policy:9s} 完成率={s['completion_rate']:.4f} "
                  f"准时率={s['on_time_rate']:.4f} 超时率={s['timeout_rate']:.4f} "
                  f"时延={s['avg_delay']:.1f} 换电={s['total_swap_sessions']} "
                  f"周转={s['nest_turnover_rate']:.2f} "
                  f"平均排队={s['avg_berth_wait_time']:.1f}s "
                  f"最大排队={s['max_berth_wait_time']:.1f}s "
                  f"紧迫加权排队={s['avg_urgency_weighted_wait']:.1f} "
                  f"排队事件={s['berth_wait_count']}")

    n = args.seeds
    print("\n" + "=" * 96)
    print(f"{'指标':26s} {'priority':>14s} {'fifo':>14s} {'delta(pri-fifo)':>16s}")
    print("=" * 96)
    for k in METRICS:
        p = agg["priority"][k] / n
        f = agg["fifo"][k] / n
        print(f"{k:26s} {p:14.4f} {f:14.4f} {p - f:+16.4f}")
    print("=" * 96)


if __name__ == "__main__":
    main()