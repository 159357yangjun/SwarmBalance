import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "simulation"))

from simulation.environment import Environment
from scheduling.ga_scheduler import GAScheduler
from scheduling.greedy.scheduler import greedy_action_from_observation

OSM = str(PROJECT_ROOT / "simulation" / "data" / "map" / "part_of_yangpu.osm")

KEYS = [
    ('completion_rate', '完成率'),
    ('on_time_rate', '准时率'),
    ('timeout_rate', '超时率'),
    ('avg_delay', '总时延'),
    ('avg_generation_to_assignment_wait', '生成→分配等待'),
    ('avg_assignment_to_load_wait', '分配→装载等待'),
    ('avg_load_to_delivery_time', '装载→送达(飞行)'),
    ('avg_generation_to_completion_time', '全程耗时'),
]


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


if __name__ == "__main__":
    seeds = [101, 102, 103]
    ga_rows, gr_rows = [], []
    for seed in seeds:
        ga = run_ga(seed)
        gr = run_greedy(seed)
        ga_rows.append(ga)
        gr_rows.append(gr)

        print(f"\n--- seed={seed} ---")
        print(f"{'指标':<16}{'GA':>12}{'greedy':>12}")
        for k, label in KEYS:
            print(f"{label:<16}{ga.get(k, 0):>12.2f}{gr.get(k, 0):>12.2f}")
        print(f"{'优先级1时延':<16}{ga.get('avg_delay_priority_1', 0):>12.2f}{gr.get('avg_delay_priority_1', 0):>12.2f}")
        print(f"{'优先级2时延':<16}{ga.get('avg_delay_priority_2', 0):>12.2f}{gr.get('avg_delay_priority_2', 0):>12.2f}")
        print(f"{'优先级3时延':<16}{ga.get('avg_delay_priority_3', 0):>12.2f}{gr.get('avg_delay_priority_3', 0):>12.2f}")
        print(f"GA sched: {ga.get('_sched')}")

    print("\n" + "=" * 60)
    print(f"{'指标':<16}{'GA均值':>12}{'greedy均值':>12}")
    for k, label in KEYS:
        ga_m = sum(r.get(k, 0) for r in ga_rows) / len(ga_rows)
        gr_m = sum(r.get(k, 0) for r in gr_rows) / len(gr_rows)
        print(f"{label:<16}{ga_m:>12.2f}{gr_m:>12.2f}")
    print("=" * 60)