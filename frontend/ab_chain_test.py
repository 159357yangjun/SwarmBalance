"""任务链 / 顺路接入 A/B 对照脚本。

用途：量化「顺路接入 + 禁飞区」两项机制的净效应，供结项报告引用。
开关都在进程内切换（不动配置文件），保证同一随机种子下严格对照。

用法:
    cd frontend
    python ab_chain_test.py --episodes 1 --episode-steps 1200
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(FRONTEND_ROOT))

import environment  # noqa: E402
from environment import Environment  # noqa: E402
from metrics_schema import to_output_metrics  # noqa: E402

FOCUS = [
    "完成率", "完成任务数", "从生成到分配等待时间", "从上机到送达平均时间",
    "从生成到完成总时间平均", "平均时延", "无人机利用率", "空载率",
    "总飞行距离", "顺路接入次数", "禁飞区绕飞次数",
]


def build_scheduler(policy, env, seed):
    if policy == "greedy":
        from greedy.scheduler import greedy_action_from_observation
        return lambda obs, t: greedy_action_from_observation(obs)
    if policy == "pso":
        from backend_si.pso_scheduler import PSOScheduler
        sch = PSOScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
    elif policy == "ga":
        from backend_si.ga_scheduler import GAScheduler
        sch = GAScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
    elif policy == "ortools":
        from backend_si.ortools_scheduler import ORToolsScheduler
        sch = ORToolsScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
    else:
        raise ValueError(policy)
    return lambda obs, t: sch.step(obs, current_time=t)


def run_one(osm, steps, policy, seed, chain_on):
    # 进程内开关：environment 里的常量与方法都以全局名引用，直接改模块属性即可
    environment.CHAIN_ENABLED = chain_on
    env = Environment(str(osm), episode_max_steps=steps)
    obs = env.reset(seed=seed)
    act = build_scheduler(policy, env, seed)
    done = False
    while not done:
        obs, _, done, _ = env.step(act(obs, env.current_time))
    stats = env.get_statistics()
    stats["episode_step"] = int(env.current_time)
    return to_output_metrics(stats)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policies", nargs="+", default=["pso", "ga"],
                    choices=["greedy", "pso", "ga", "ortools"])
    ap.add_argument("--episodes", type=int, default=1)
    ap.add_argument("--episode-steps", type=int, default=1200)
    ap.add_argument("--osm", type=str, default="data/map/part_of_yangpu.osm")
    ap.add_argument("--seed", type=int, default=100)
    args = ap.parse_args()

    for policy in args.policies:
        for chain_on in (False, True):
            acc = {k: 0.0 for k in FOCUS}
            for ep in range(args.episodes):
                row = run_one(args.osm, args.episode_steps, policy,
                              args.seed + ep + 1, chain_on)
                for k in FOCUS:
                    acc[k] += row[k]
            n = max(1, args.episodes)
            tag = "链ON " if chain_on else "链OFF"
            print(f"[{policy:7s}] {tag} " + "  ".join(
                f"{k}={acc[k] / n:.3f}" for k in FOCUS))
        print("-" * 100)


if __name__ == "__main__":
    main()
