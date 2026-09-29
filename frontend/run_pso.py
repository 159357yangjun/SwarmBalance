"""PSO (backend_si) scheduler evaluation entrypoint.

跑多个 episode，对指标求均值，并把汇总追加到 results/compare/backend_si_metrics.csv。

表头统一由 metrics_schema 定义（中文列名 + `算法` 列 + 机巢周转率/泊位利用率），
与 run_ga.py / run_ortools.py / evaluate_metrics.py 共用，保证绘图脚本可直接汇总。

为了和 ga 使用相同的任务场景，本脚本对第 ep 个 episode 使用
seed = base_seed + ep（base_seed 默认 100），与 qmix 的
episode_runner.py 中 `episode_seed = seed + episode_id`（seed=100）完全一致。

用法:
    cd frontend
    python run_pso.py --episodes 5            # 默认 base seed=100
    python run_pso.py --episodes 5 --seed 200 # 换一组场景
    python run_pso.py --no-csv                # 只打印不写 CSV
"""

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(FRONTEND_ROOT))

from config.config_loder import get_episode_max_steps
from environment import Environment
from backend_si.pso_scheduler import PSOScheduler
from metrics_schema import (METRIC_COLUMNS, to_output_metrics, mean_metrics,
                            write_mean_metrics_row)


CSV_OUTPUT = PROJECT_ROOT / "results" / "compare" / "backend_si_metrics.csv"
ALGORITHM_KEY = "pso"

# 列定义统一收敛到 metrics_schema.METRIC_COLUMNS（含机巢周转率/泊位利用率），
# 不再在本文件重复维护一份表头 —— 之前就是两份表头打架导致绘图脚本崩溃。


def _resolve_episode_steps():
    """单回合步数：只认 config/simulation.json 的 environment.episode_max_steps。
    原先签名收一个 default_steps=1200 作为兜底，等于允许第二套默认值存在。"""
    return get_episode_max_steps()


def run_one_episode(osm_path, episode_steps, seed):
    env = Environment(str(osm_path), episode_max_steps=episode_steps)
    # 用固定 seed 复现与 qmix 相同的任务场景
    obs = env.reset(seed=seed)
    # PSOScheduler 持有队列/已知任务等内部状态，必须每个 episode 新建
    scheduler = PSOScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
    done = False
    while not done:
        action = scheduler.step(obs, current_time=env.current_time)
        obs, _, done, _ = env.step(action)

    stats = env.get_statistics()
    stats["episode_step"] = int(env.current_time)
    stats["_scheduler_stats"] = scheduler.get_stats()
    return stats


def main():
    parser = argparse.ArgumentParser(description="Run PSO (backend_si) scheduler evaluation.")
    parser.add_argument("--episodes", type=int, default=1, help="Number of episodes to run.")
    parser.add_argument("--episode-steps", type=int, default=None, help="Max steps per episode.")
    parser.add_argument("--osm", type=str, default="data/map/part_of_yangpu.osm", help="OSM path relative to frontend.")
    parser.add_argument("--seed", type=int, default=100, help="Base seed; episode ep uses seed+ep (aligns with qmix, default 100).")
    parser.add_argument("--no-csv", action="store_true", help="Do not write the averaged CSV summary.")
    args = parser.parse_args()

    episode_steps = args.episode_steps or _resolve_episode_steps()
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


if __name__ == "__main__":
    main()
