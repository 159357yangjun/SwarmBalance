"""统一评测入口：Greedy / PSO / GA / OR-Tools 四选一跑评测。

历史问题（本次修复）
--------------------
本文件原来写的是**英文表头且没有 `算法` 列**，而 `run_pso.py` / `run_ga.py` 写的是
**中文表头带 `算法` 列**，`results/plot_compare_metrics.py` 又只认中文表头 + 算法列
——于是汇总脚本一跑就抛 `KeyError: Missing algorithm column`，四类算法根本没法出图。

同时原实现有**静默覆盖**风险：表头不一致时切 `w` 模式重写，之前攒的实验结果会被
无声抹掉。

现在四个入口（本文件 / run_pso / run_ga / run_ortools）统一走
`metrics_schema`，列定义只有一份，表头不兼容时先备份再重建。

另一处修复：**随机种子对齐**。原来跑 Greedy 时 `env.reset()` 不传 seed，而
PSO/GA/MARL 用 `seed = 100 + ep`，等于 Greedy 和对手跑的不是同一批任务场景，
横向对比结论不成立。现在统一用 `--seed`（默认 100）+ `ep + 1`。

用法:
    cd frontend
    python evaluate_metrics.py --policy greedy  --episodes 5 --episode-steps 2000
    python evaluate_metrics.py --policy pso     --episodes 5 --episode-steps 2000
    python evaluate_metrics.py --policy ga      --episodes 5 --episode-steps 2000
    python evaluate_metrics.py --policy ortools --episodes 5 --episode-steps 2000
"""

import argparse
import sys
from pathlib import Path

# Allow importing backend scheduler from project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = Path(__file__).resolve().parent

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(FRONTEND_ROOT))

from environment import Environment
from metrics_schema import (METRIC_COLUMNS, to_output_metrics, mean_metrics,
                            write_mean_metrics_row)

# policy -> (算法 key, 输出 CSV 文件名)。文件名沿用既有约定，避免破坏历史结果路径。
POLICY_MAP = {
    "greedy": ("greedy", "frontend_greedy_metrics.csv"),
    "pso": ("pso", "backend_si_metrics.csv"),
    "ga": ("ga", "backend_ga_metrics.csv"),
    "ortools": ("ortools", "backend_ortools_metrics.csv"),
}


def _get_metrics_output(policy):
    """解析输出路径：优先读 simulation.json 的 metrics 配置，否则用默认文件名。"""
    _, default_filename = POLICY_MAP[policy]
    cfg_path = PROJECT_ROOT / "config" / "simulation.json"
    compare_dir = PROJECT_ROOT / "results" / "compare"
    filename = default_filename

    if cfg_path.exists():
        import json
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        metrics_cfg = cfg.get("metrics", {}) if isinstance(cfg, dict) else {}
        compare_dir = PROJECT_ROOT / metrics_cfg.get("compare_dir", "results/compare")
        # 允许配置覆盖文件名；未配置则保持默认
        override_key = f"{policy}_file"
        filename = metrics_cfg.get(override_key, filename)

    return compare_dir / filename


def _build_scheduler(policy, env, seed):
    """按 policy 构造调度器。有状态的调度器必须每个 episode 新建，故在此构造。"""
    if policy == "greedy":
        return None  # greedy 是无状态的纯函数
    if policy == "pso":
        from backend_si.pso_scheduler import PSOScheduler
        return PSOScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
    if policy == "ga":
        from backend_si.ga_scheduler import GAScheduler
        return GAScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
    if policy == "ortools":
        from backend_si.ortools_scheduler import ORToolsScheduler, ORTOOLS_AVAILABLE
        if not ORTOOLS_AVAILABLE:
            raise RuntimeError("OR-Tools 未安装，无法运行 ortools 基线：pip install ortools")
        return ORToolsScheduler(num_drones=len(env.drones), verbose=False, seed=seed)
    raise ValueError(f"未知 policy: {policy}")


def run_one_episode(osm_path, episode_steps, policy, seed):
    env = Environment(str(osm_path), visualize=False, episode_max_steps=episode_steps)
    # 与 pso / ga / qmix 一致地固定 seed，保证四类算法跑同一批任务场景
    obs = env.reset(seed=seed)

    if policy == "greedy":
        from greedy.scheduler import greedy_action_from_observation

        def _act(observation, current_time):
            return greedy_action_from_observation(observation)
    else:
        scheduler = _build_scheduler(policy, env, seed)

        def _act(observation, current_time):
            return scheduler.step(observation, current_time=current_time)

    done = False
    while not done:
        action = _act(obs, env.current_time)
        obs, _, done, _ = env.step(action)

    stats = env.get_statistics()
    stats["episode_step"] = int(env.current_time)
    return stats


def main():
    parser = argparse.ArgumentParser(description="Evaluate frontend environment metrics.")
    parser.add_argument("--policy", type=str, default="greedy",
                        choices=sorted(POLICY_MAP.keys()),
                        help="Policy type for evaluation.")
    parser.add_argument("--episodes", type=int, default=5, help="Number of evaluation episodes.")
    parser.add_argument("--episode-steps", type=int, default=None, help="Max steps per episode.")
    parser.add_argument("--osm", type=str, default="data/map/part_of_yangpu.osm",
                        help="Relative path to OSM map file.")
    parser.add_argument("--seed", type=int, default=100,
                        help="Base seed; episode ep uses seed+ep+1 (aligns with pso/ga/qmix).")
    args = parser.parse_args()

    episode_steps = args.episode_steps or 1200
    algorithm_key, _ = POLICY_MAP[args.policy]
    metrics_path = _get_metrics_output(args.policy)

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
    print("=" * 60)


if __name__ == "__main__":
    main()
