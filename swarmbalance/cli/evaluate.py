"""Unified four-algorithm evaluation command; business execution lives in application."""
import argparse
from pathlib import Path
from swarmbalance.paths import PROJECT_ROOT, DEFAULT_MAP
from swarmbalance.diagnostics.dependencies import guard_or_exit


def _get_metrics_output(*args, **kwargs):
    from swarmbalance.application.evaluation import _get_metrics_output as implementation
    return implementation(*args, **kwargs)


def _build_scheduler(*args, **kwargs):
    from swarmbalance.application.evaluation import _build_scheduler as implementation
    return implementation(*args, **kwargs)


def run_one_episode(*args, **kwargs):
    from swarmbalance.application.evaluation import run_one_episode as implementation
    return implementation(*args, **kwargs)


def main(argv=None, *, legacy_paths=False):
    rc = guard_or_exit(("numpy", "shapely", "pandas"), entry="python -m swarmbalance evaluate")
    if rc:
        raise SystemExit(rc)
    from swarmbalance.application.evaluation import POLICY_MAP, _get_metrics_output, run_one_episode
    from swarmbalance.simulation.metrics import METRIC_COLUMNS, to_output_metrics, mean_metrics, write_mean_metrics_row
    from swarmbalance.infrastructure.config.loader import get_episode_max_steps

    parser = argparse.ArgumentParser(description="Evaluate frontend environment metrics.")
    parser.add_argument("--policy", type=str, default="greedy",
                        choices=sorted(POLICY_MAP.keys()),
                        help="Policy type for evaluation.")
    parser.add_argument("--episodes", type=int, default=5, help="Number of evaluation episodes.")
    parser.add_argument("--episode-steps", type=int, default=None, help="Max steps per episode.")
    parser.add_argument("--osm", type=str, default=str(DEFAULT_MAP),
                        help="Relative path to OSM map file.")
    parser.add_argument("--seed", type=int, default=100,
                        help="Base seed; episode ep uses seed+ep+1 (aligns with pso/ga).")
    parser.add_argument("--output", type=str, default=None, metavar="PATH",
                        help="指标 CSV 输出路径。默认写进 results/adhoc/<该算法>.csv（已 gitignore，"
                             "不影响仓库与工作区）。")
    parser.add_argument("--record-into-evidence", action="store_true",
                        help="把这一行追加进 results/compare/<该算法>.csv，供 Web 算法对比页读取。"
                             "该选项只选择输出位置，不代表结果已通过可比性验证。")
    args = parser.parse_args(argv)

    # 原先硬编码 1200 且完全不读配置，是"第二套默认"最典型的一处。
    episode_steps = args.episode_steps or get_episode_max_steps()
    algorithm_key, _ = POLICY_MAP[args.policy]
    metrics_path = (Path(args.output) if args.output
                    else _get_metrics_output(args.policy, args.record_into_evidence))
    if args.output and not metrics_path.is_absolute():
        metrics_path = ((PROJECT_ROOT / "frontend" if legacy_paths else PROJECT_ROOT) / args.output).resolve()

    all_rows = []
    for ep in range(args.episodes):
        episode_seed = args.seed + ep + 1
        stats = run_one_episode(args.osm, episode_steps, args.policy, episode_seed)
        output = to_output_metrics(stats)
        all_rows.append(output)
        print(
            f"Episode {ep + 1} (seed={episode_seed}): "
            f"完成率={output['完成率']:.4f}, "
            f"超时率={output['超时率']:.4f}, "
            f"平均时延={output['平均时延']:.4f}, "
            f"从上机到送达平均时间={output['从上机到送达平均时间']:.4f}, "
            f"完成={output['完成任务数']:.0f}/{output['生成任务数']:.0f}, "
            f"总步数={output['总步数']:.0f}, "
            f"机巢周转率={output['机巢周转率']:.3f}, "
            f"泊位利用率={output['泊位利用率']:.3f}, "
            f"利用率={output['无人机利用率']:.3f}, "
            f"空载率={output['空载率']:.3f}, "
            f"顺路接入={output['顺路接入次数']:.0f}, "
            f"禁飞绕飞={output['禁飞区绕飞次数']:.0f}"
        )

    mean_stats = mean_metrics(all_rows)

    print("=" * 60)
    print(f"Mean Metrics ({algorithm_key})")
    for col in METRIC_COLUMNS:
        print(f"{col}: {mean_stats[col]:.4f}")
    write_mean_metrics_row(metrics_path, algorithm_key, all_rows)
    print(f"metrics_file: {metrics_path}")
    if "results" in metrics_path.parts and "compare" in metrics_path.parts:
        print("已写入算法对比目录；页面按各数据源的读取顺序选择有效记录。")
    print("=" * 60)


if __name__ == "__main__":
    main()
