import sys, argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "frontend"))

from environment import Environment
from backend_si.ga_scheduler import GAScheduler
from greedy.scheduler import greedy_action_from_observation

OSM = str(PROJECT_ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm")


def run_greedy(seed):
    env = Environment(OSM, visualize=False, episode_max_steps=2000)
    obs = env.reset(seed=seed)
    done = False
    while not done:
        action = greedy_action_from_observation(obs)
        obs, _, done, _ = env.step(action)
    return env.get_statistics()


def run_ga(seed):
    env = Environment(OSM, visualize=False, episode_max_steps=2000)
    obs = env.reset(seed=seed)
    sched = GAScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
    done = False
    while not done:
        action = sched.step(obs, current_time=env.current_time)
        obs, _, done, _ = env.step(action)
    s = env.get_statistics()
    s["_sched"] = sched.get_stats()
    return s


def report(name, stats):
    print(f"{name:8s} 完成率={stats['completion_rate']:.4f} "
          f"准时率={stats['on_time_rate']:.4f} "
          f"超时率={stats['timeout_rate']:.4f} "
          f"平均时延={stats['avg_delay']:.2f} "
          f"完成={stats['total_completed']}/{stats['total_generated']} "
          f"能耗={stats['total_energy_consumed']:.0f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--start", type=int, default=100)
    args = ap.parse_args()

    ga_rows, gr_rows = [], []
    for ep in range(args.seeds):
        seed = args.start + ep + 1
        ga = run_ga(seed)
        gr = run_greedy(seed)
        ga_rows.append(ga)
        gr_rows.append(gr)
        print(f"\n--- seed={seed} ---")
        report("GA", ga)
        print("    GA sched:", ga.get("_sched"))
        report("greedy", gr)

    def mean(rows, k):
        return sum(r[k] for r in rows) / len(rows)

    print("\n" + "=" * 60)
    for k in ["completion_rate", "on_time_rate", "timeout_rate", "avg_delay"]:
        print(f"{k:16s} GA={mean(ga_rows,k):.4f}  greedy={mean(gr_rows,k):.4f}")
    print(f"{'total_completed':16s} GA={mean(ga_rows,'total_completed'):.1f}  greedy={mean(gr_rows,'total_completed'):.1f}")
    print("=" * 60)