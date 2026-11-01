"""Compatibility command adapter for the original per-algorithm CLI options."""
import argparse
from pathlib import Path
from swarmbalance.paths import DEFAULT_MAP, PROJECT_ROOT
from swarmbalance.infrastructure.config.loader import get_episode_max_steps
from swarmbalance.application.evaluation import POLICY_MAP, run_one_episode
from swarmbalance.simulation.metrics import METRIC_COLUMNS, to_output_metrics, mean_metrics, write_mean_metrics_row
from swarmbalance.cli import legacy_metrics


def main(policy, argv=None):
    parser = argparse.ArgumentParser(description=f"Run {policy.upper()} scheduler evaluation.")
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--episode-steps", type=int, default=None)
    parser.add_argument("--osm", default=str(DEFAULT_MAP))
    parser.add_argument("--seed", type=int, default=100)
    parser.add_argument("--no-csv", action="store_true")
    args = parser.parse_args(argv)
    steps = args.episode_steps or get_episode_max_steps()
    rows = []
    for index in range(args.episodes):
        seed = args.seed + index + 1
        stats = run_one_episode(args.osm, steps, policy, seed, include_scheduler_stats=True)
        output = to_output_metrics(stats)
        rows.append(output)
        print(f"Episode {index + 1} (seed={seed}): 完成率={output['完成率']:.4f}, "
              f"超时率={output['超时率']:.4f}, 平均时延={output['平均时延']:.4f}, "
              f"完成={output['完成任务数']:.0f}/{output['生成任务数']:.0f}, 总步数={output['总步数']:.0f}")
        if stats.get("_scheduler_stats"):
            print(f"    [scheduler] {stats['_scheduler_stats']}")
    mean = mean_metrics(rows)
    print("=" * 60)
    print("Mean Metrics")
    columns = legacy_metrics.METRIC_COLUMNS if policy == "greedy" else METRIC_COLUMNS
    for column in columns:
        print(f"{column}: {mean[column]:.4f}")
    if not args.no_csv:
        output = PROJECT_ROOT / "results" / "compare" / POLICY_MAP[policy][1]
        if policy == "greedy":
            legacy_metrics._write_csv(output, mean)
        else:
            write_mean_metrics_row(output, policy, rows)
        print(f"csv_file: {output}")
    print("=" * 60)
