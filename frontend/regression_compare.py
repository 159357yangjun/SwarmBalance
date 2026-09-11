"""回归对比：greedy / PSO / GA 在相同 seed 下三路对照。

验证真实数据 + 换电模型改造后的运行正确性与三算法相对表现。
用法:
    cd frontend
    python regression_compare.py --seeds 3 --start 100
"""
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(FRONTEND_ROOT))

from environment import Environment
from backend_si.pso_scheduler import PSOScheduler
from backend_si.ga_scheduler import GAScheduler
from greedy.scheduler import greedy_action_from_observation

OSM = str(PROJECT_ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm")


def run_greedy(seed, steps):
    env = Environment(OSM, visualize=False, episode_max_steps=steps)
    obs = env.reset(seed=seed)
    done = False
    while not done:
        obs, _, done, _ = env.step(greedy_action_from_observation(obs))
    return env.get_statistics()


def run_psos(seed, steps):
    env = Environment(OSM, visualize=False, episode_max_steps=steps)
    obs = env.reset(seed=seed)
    sched = PSOScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
    done = False
    while not done:
        obs, _, done, _ = env.step(sched.step(obs, current_time=env.current_time))
    s = env.get_statistics()
    s["_sched"] = sched.get_stats()
    return s


def run_ga(seed, steps):
    env = Environment(OSM, visualize=False, episode_max_steps=steps)
    obs = env.reset(seed=seed)
    sched = GAScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
    done = False
    while not done:
        obs, _, done, _ = env.step(sched.step(obs, current_time=env.current_time))
    s = env.get_statistics()
    s["_sched"] = sched.get_stats()
    return s


def report(name, stats):
    print(f"{name:8s} 完成率={stats['completion_rate']:.4f} "
          f"准时率={stats['on_time_rate']:.4f} "
          f"超时率={stats['timeout_rate']:.4f} "
          f"时延={stats['avg_delay']:.2f} "
          f"完成={stats['total_completed']}/{stats['total_generated']} "
          f"能耗={stats['total_energy_consumed']:.0f} "
          f"换电={stats['total_swap_sessions']} "
          f"泊位利用率={stats['berth_utilization_rate']:.4f} "
          f"周转={stats['nest_turnover_rate']:.2f} "
          f"排队={stats['avg_berth_wait_time']:.1f}s")


KEYS = ["completion_rate", "on_time_rate", "timeout_rate", "avg_delay",
        "total_completed", "total_generated", "total_energy_consumed",
        "total_swap_sessions", "berth_utilization_rate", "nest_turnover_rate",
        "avg_berth_wait_time"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--start", type=int, default=100)
    ap.add_argument("--steps", type=int, default=2000)
    args = ap.parse_args()

    rows = {"greedy": [], "pso": [], "ga": []}
    for ep in range(args.seeds):
        seed = args.start + ep + 1
        rows["greedy"].append(run_greedy(seed, args.steps))
        rows["pso"].append(run_psos(seed, args.steps))
        rows["ga"].append(run_ga(seed, args.steps))
        print(f"\n--- seed={seed} ---")
        for name in ["greedy", "pso", "ga"]:
            report(name, rows[name][-1])

    def mean(name, k):
        return sum(r[k] for r in rows[name]) / max(1, len(rows[name]))

    print("\n" + "=" * 72)
    for k in KEYS:
        line = f"{k:20s} " + "  ".join(
            f"{name}={mean(name, k):.4f}" for name in ["greedy", "pso", "ga"])
        print(line)
    print("=" * 72)


if __name__ == "__main__":
    main()