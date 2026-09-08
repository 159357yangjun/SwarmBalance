"""OR-Tools (CP-SAT) 经典求解器基线评测入口。

项目书「四、项目实施方案（二）核心调度算法实现」：
    对比基线：搭建贪心调度基线……并集成 OR-Tools 求解器作为经典 VRP
    降维求解的性能参照。

用法（与 run_pso.py / run_ga.py 完全对称）:
    cd frontend
    python run_ortools.py --episodes 5             # 默认 base seed=100
    python run_ortools.py --episodes 5 --seed 200  # 换一组场景
    python run_ortools.py --no-csv                 # 只打印不写 CSV

seed 约定与 qmix / pso / ga 一致：第 ep 个 episode 使用 `base_seed + ep + 1`，
保证四类算法跑的是同一批任务场景，横向对比才成立。
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "simulation"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SIMULATION_ROOT))

from config.config_loder import get_shared_config
from simulation.environment import Environment
from scheduling.ortools_scheduler import ORToolsScheduler, ORTOOLS_AVAILABLE
from app.metrics_schema import (METRIC_COLUMNS, to_output_metrics, mean_metrics,
                            write_mean_metrics_row)


CSV_OUTPUT = PROJECT_ROOT / "results" / "compare" / "backend_ortools_metrics.csv"
ALGORITHM_KEY = "ortools"


def _resolve_episode_steps(default_steps):
    cfg = get_shared_config()
    env_cfg = cfg.get("environment", {}) if isinstance(cfg, dict) else {}
    return int(env_cfg.get("episode_max_steps", default_steps))


def run_one_episode(osm_path, episode_steps, seed):
    env = Environment(str(osm_path), visualize=False, episode_max_steps=episode_steps)
    obs = env.reset(seed=seed)
    # 调度器持有队列 / 已知任务等内部状态，必须每个 episode 新建
    scheduler = ORToolsScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
    done = False
    while not done:
        action = scheduler.step(obs, current_time=env.current_time)
        obs, _, done, _ = env.step(action)

    stats = env.get_statistics()
    stats["episode_step"] = int(env.current_time)
    stats["_scheduler_stats"] = scheduler.get_stats()
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Run OR-Tools (CP-SAT) classical solver baseline evaluation.")
    parser.add_argument("--episodes", type=int, default=1, help="Number of episodes to run.")
    parser.add_argument("--episode-steps", type=int, default=None, help="Max steps per episode.")
    parser.add_argument("--osm", type=str, default="data/map/part_of_yangpu.osm",
                        help="OSM path relative to frontend.")
    parser.add_argument("--seed", type=int, default=100,
                        help="Base seed; episode ep uses seed+ep+1 (aligns with pso/ga/qmix).")
    parser.add_argument("--no-csv", action="store_true", help="Do not write the averaged CSV summary.")
    args = parser.parse_args()

    if not ORTOOLS_AVAILABLE:
        print("错误：未检测到 OR-Tools。请先安装：pip install ortools")
        return 1

    episode_steps = args.episode_steps or _resolve_episode_steps(default_steps=1200)
    osm_path = FRONTEND_ROOT / args.osm

    output_rows = []
    for ep in range(args.episodes):
        episode_seed = args.seed + ep + 1
        stats = run_one_episode(osm_path, episode_steps, episode_seed)
        output = to_output_metrics(stats)
        output_rows.append(output)
        print(
            f"Episode {ep + 1} (seed={episode_seed}): "
            f"完成率={output['完成率']:.4f}, "
            f"超时率={output['超时率']:.4f}, "
            f"平均时延={output['平均时延']:.4f}, "
            f"从上机到送达平均时间={output['从上机到送达平均时间']:.4f}, "
            f"完成={output['完成任务数']:.0f}/{output['生成任务数']:.0f}, "
            f"总步数={output['总步数']:.0f}, "
            f"机巢周转率={output['机巢周转率']:.3f}, "
            f"泊位利用率={output['泊位利用率']:.3f}"
        )
        sched_stats = stats.get("_scheduler_stats")
        if sched_stats:
            print(f"    [scheduler] {sched_stats}")

    mean_stats = mean_metrics(output_rows)

    print("=" * 60)
    print("Mean Metrics")
    for col in METRIC_COLUMNS:
        print(f"{col}: {mean_stats[col]:.4f}")
    if not args.no_csv:
        write_mean_metrics_row(CSV_OUTPUT, ALGORITHM_KEY, output_rows)
        print(f"csv_file: {CSV_OUTPUT}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
