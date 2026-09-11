"""前端环境贪心测试脚本。

功能：
- 使用贪心算法跑环境
- 统计任务平均生成时间
- 统计订单从装载到送达的平均时间
- 统计订单从装载到送达的最大时间
- 可选输出 CSV
- 支持通过命令行覆盖 num_drones、total_tasks、interval_scale、deadline_offset

用法示例：
    python frontend/environment_metrics_test.py --interval-scale 4.0
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
OUTPUT_CSV = PROJECT_ROOT / "results" / "compare" / "frontend_environment_metrics.csv"

sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(FRONTEND_ROOT))

from seed_interface import apply_seed


def _load_base_config() -> Dict[str, Any]:
    config_path = PROJECT_ROOT / "config" / "simulation.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _deep_update(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def _build_override_config(args: argparse.Namespace) -> Dict[str, Any]:
    config = copy.deepcopy(_load_base_config())

    environment_cfg = config.setdefault("environment", {})
    task_generation_cfg = config.setdefault("task_generation", {})
    realistic_cfg = task_generation_cfg.setdefault("realistic", {})
    task_cfg = config.setdefault("task", {})

    if args.num_drones is not None:
        environment_cfg["num_drones"] = int(args.num_drones)
    if args.total_tasks is not None:
        realistic_cfg["total_tasks"] = int(args.total_tasks)
    if args.interval_scale is not None:
        realistic_cfg["interval_scale"] = float(args.interval_scale)
    if args.deadline_offset_min is not None:
        task_cfg["deadline_offset_min"] = int(args.deadline_offset_min)
    if args.deadline_offset_max is not None:
        task_cfg["deadline_offset_max"] = int(args.deadline_offset_max)
    if args.initial_task_count is not None:
        realistic_cfg["initial_task_count"] = int(args.initial_task_count)
    if args.peak_steps_per_task is not None:
        realistic_cfg["peak_steps_per_task"] = int(args.peak_steps_per_task)
    if args.off_peak_steps_per_task is not None:
        realistic_cfg["off_peak_steps_per_task"] = int(args.off_peak_steps_per_task)
    if args.peak_probability is not None:
        realistic_cfg["peak_probability"] = float(args.peak_probability)
    if args.cycle_length is not None:
        realistic_cfg["cycle_length"] = int(args.cycle_length)

    return config


def _patch_shared_config(config_data: Dict[str, Any]) -> None:
    import config.config_loder as config_loader

    def _patched_get_shared_config(config_path=None):
        del config_path
        return copy.deepcopy(config_data)

    config_loader.get_shared_config = _patched_get_shared_config


def _load_runtime(config_data: Dict[str, Any]):
    _patch_shared_config(config_data)
    from environment import Environment
    from greedy.scheduler import greedy_action_from_observation

    return Environment, greedy_action_from_observation


def _estimate_avg_generation_interval(config_data: Dict[str, Any], interval_scale: float) -> float:
    task_generation_cfg = config_data.get("task_generation", {})
    realistic_cfg = task_generation_cfg.get("realistic", {})
    peak_steps = float(realistic_cfg.get("peak_steps_per_task", 5.0))
    off_peak_steps = float(realistic_cfg.get("off_peak_steps_per_task", 9.0))
    peak_probability = float(realistic_cfg.get("peak_probability", 0.85))
    cycle_length = float(realistic_cfg.get("cycle_length", 500.0))
    peak_window_ratio = 0.25  # 对应 task.py 中固定的 peak_start/peak_end 窗口
    peak_window_ratio = min(max(peak_window_ratio, 0.0), 1.0)
    off_peak_ratio = 1.0 - peak_window_ratio
    expected_base = off_peak_ratio * off_peak_steps + peak_window_ratio * (
        peak_probability * peak_steps + (1.0 - peak_probability) * off_peak_steps
    )
    # 抖动项是对称的，期望近似不变；这里只给一个线性估计值。
    _ = cycle_length
    return expected_base * float(interval_scale)


def _run_one_episode(Environment, greedy_action_from_observation, osm_path: Path, episode_steps: int, seed: int | None = None):
    previous_cwd = os.getcwd()
    os.chdir(str(FRONTEND_ROOT))
    try:
        env = Environment(str(osm_path), visualize=True, episode_max_steps=episode_steps)
        if seed is not None:
            apply_seed(seed)
            obs = env.reset(seed=seed)
        else:
            obs = env.reset()
        done = False
        while not done:
            action = greedy_action_from_observation(obs)
            obs, _, done, _ = env.step(action)
    finally:
        os.chdir(previous_cwd)

    stats = env.get_statistics()
    result = {
        "episode_step": int(env.current_time),
        "completion_rate": float(stats.get("completion_rate", 0.0)),
        "on_time_rate": float(stats.get("on_time_rate", 0.0)),
        "avg_delay": float(stats.get("avg_delay", 0.0)),
        "avg_wait_time_to_load": float(stats.get("avg_wait_time_to_load", 0.0)),
        "avg_delivery_time": float(stats.get("avg_delivery_time", 0.0)),
        "avg_generation_to_completion_time": float(stats.get("avg_generation_to_completion_time", 0.0)),
        "avg_generation_time": float(stats.get("avg_generation_time", 0.0)),
        "avg_steps_per_order": float(stats.get("avg_steps_per_order", 0.0)),
        "total_completed": int(stats.get("total_completed", 0)),
        "total_generated": int(stats.get("total_generated", getattr(env, "total_generated_tasks", 0))),
        "total_energy_consumed": float(stats.get("total_energy_consumed", 0.0)),
        "max_delivery_time": float(stats.get("max_delivery_time", 0.0)),
    }
    return result


def _write_summary_csv(output_path: Path, summary: Dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "source",
        "interval_scale",
        "episodes",
        "completion_rate",
        "on_time_rate",
        "avg_delay",
        "avg_wait_time_to_load",
        "avg_delivery_time",
        "avg_gen_to_done",
        "avg_generation_time",
        "total_energy_consumed",
        "total_generated_mean",
    ]

    existing_header = None
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as existing:
            existing_header = existing.readline().strip()

    need_header = existing_header != ",".join(header)
    write_mode = "w" if need_header else "a"
    with open(output_path, write_mode, newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if need_header:
            writer.writerow(header)
        writer.writerow([
            "frontend_environment_test",
            float(summary.get("interval_scale", 0.0)),
            int(summary.get("episodes", 0)),
            float(summary.get("completion_rate", 0.0)),
            float(summary.get("on_time_rate", 0.0)),
            float(summary.get("avg_delay", 0.0)),
            float(summary.get("avg_wait_time_to_load", 0.0)),
            float(summary.get("avg_delivery_time", 0.0)),
            float(summary.get("avg_gen_to_done", 0.0)),
            float(summary.get("avg_generation_time", 0.0)),
            float(summary.get("total_energy_consumed", 0.0)),
            float(summary.get("total_generated_mean", 0.0)),
        ])


def _parse_args():
    parser = argparse.ArgumentParser(description="前端环境贪心测试脚本")
    parser.add_argument("--episodes", type=int, default=1, help="测试回合数")
    parser.add_argument("--episode-steps", type=int, default=None, help="单回合最大步数")
    parser.add_argument("--osm", type=str, default="data/map/part_of_yangpu.osm", help="OSM 地图相对路径")
    parser.add_argument("--csv", action="store_true", default=True, help="是否输出 CSV")
    parser.add_argument("--output", type=str, default=str(OUTPUT_CSV), help="CSV 输出路径")
    parser.add_argument("--seed", type=int, default=187, help="基础随机种子，默认与后端 qmix 一致")
    parser.add_argument("--num-drones", type=int, default=None, help="覆盖无人机数量")
    parser.add_argument("--total-tasks", type=int, default=None, help="覆盖真实模式总任务数")
    parser.add_argument("--interval-scale", type=float, default=None, help="覆盖任务生成间隔缩放")
    parser.add_argument("--deadline-offset-min", type=int, default=None, help="覆盖最小截止时间偏移")
    parser.add_argument("--deadline-offset-max", type=int, default=None, help="覆盖最大截止时间偏移")
    parser.add_argument("--initial-task-count", type=int, default=None, help="覆盖初始任务数")
    parser.add_argument("--peak-steps-per-task", type=int, default=None, help="覆盖高峰间隔")
    parser.add_argument("--off-peak-steps-per-task", type=int, default=None, help="覆盖低谷间隔")
    parser.add_argument("--peak-probability", type=float, default=None, help="覆盖高峰概率")
    parser.add_argument("--cycle-length", type=int, default=None, help="覆盖周期长度")
    parser.add_argument(
        "--show-interval-table",
        action="store_true",
        default=False,
        help="打印 interval_scale 与平均生成间隔的近似表",
    )
    parser.add_argument(
        "--table-scales",
        type=str,
        default="0.5,1,2,5,10",
        help="interval_scale 近似表使用的缩放值，逗号分隔",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    config_data = _build_override_config(args)
    Environment, greedy_action_from_observation = _load_runtime(config_data)

    base_seed = args.seed
    if base_seed is not None:
        apply_seed(base_seed)

    episode_steps = args.episode_steps or int(config_data.get("environment", {}).get("episode_max_steps", 1200))
    osm_path = FRONTEND_ROOT / args.osm
    output_path = Path(args.output)

    all_stats = []
    for episode in range(args.episodes):
        episode_seed = None if base_seed is None else int(base_seed) + int(episode) + 1
        stats = _run_one_episode(Environment, greedy_action_from_observation, osm_path, episode_steps, episode_seed)
        all_stats.append(stats)
        print(
            f"Episode {episode + 1} (seed={episode_seed}): completion={stats['completion_rate']:.4f}, "
            f"on_time={stats['on_time_rate']:.4f}, avg_delay={stats['avg_delay']:.4f}, "
            f"avg_wait={stats['avg_wait_time_to_load']:.4f}, "
            f"avg_delivery={stats['avg_delivery_time']:.4f}, "
            f"avg_gen_to_done={stats['avg_generation_to_completion_time']:.4f}, "
            f"avg_gen_interval={stats['avg_generation_time']:.4f}, "
            f"max_delivery={stats['max_delivery_time']:.4f}, "
            f"total_generated={stats['total_generated']}, "
            f"steps={stats['episode_step']}"
        )

    n = max(len(all_stats), 1)
    mean_completion = sum(item["completion_rate"] for item in all_stats) / n
    mean_on_time = sum(item["on_time_rate"] for item in all_stats) / n
    mean_delay = sum(item["avg_delay"] for item in all_stats) / n
    mean_wait = sum(item["avg_wait_time_to_load"] for item in all_stats) / n
    mean_delivery = sum(item["avg_delivery_time"] for item in all_stats) / n
    mean_gen_to_done = sum(item["avg_generation_to_completion_time"] for item in all_stats) / n
    mean_gen_interval = sum(item["avg_generation_time"] for item in all_stats) / n
    mean_energy = sum(item["total_energy_consumed"] for item in all_stats) / n
    mean_total_generated = sum(item["total_generated"] for item in all_stats) / n
    summary_row = {
        "interval_scale": float(args.interval_scale) if args.interval_scale is not None else 0.0,
        "episodes": int(args.episodes),
        "completion_rate": mean_completion,
        "on_time_rate": mean_on_time,
        "avg_delay": mean_delay,
        "avg_wait_time_to_load": mean_wait,
        "avg_delivery_time": mean_delivery,
        "avg_gen_to_done": mean_gen_to_done,
        "avg_generation_time": mean_gen_interval,
        "total_energy_consumed": mean_energy,
        "total_generated_mean": mean_total_generated,
    }

    print("=" * 72)
    print("Mean Metrics")
    print(f"completion_rate:        {mean_completion:.4f}")
    print(f"on_time_rate:           {mean_on_time:.4f}")
    print(f"avg_delay:              {mean_delay:.4f}")
    print(f"avg_wait_time_to_load:  {mean_wait:.4f}")
    print(f"avg_delivery_time:      {mean_delivery:.4f}")
    print(f"avg_gen_to_done:        {mean_gen_to_done:.4f}")
    print(f"avg_generation_time:    {mean_gen_interval:.4f}")
    print(f"total_energy_consumed:   {mean_energy:.4f}")
    print(f"total_generated (mean):   {mean_total_generated:.1f}")
    if args.csv:
        _write_summary_csv(output_path, summary_row)
        print(f"csv_file:               {output_path}")
    print("=" * 72)

    if args.show_interval_table:
        scales = []
        for part in args.table_scales.split(","):
            part = part.strip()
            if not part:
                continue
            scales.append(float(part))
        print("interval_scale vs estimated avg_generation_time")
        print("scale,estimated_avg_generation_time")
        for scale in scales:
            estimated = _estimate_avg_generation_interval(config_data, scale)
            print(f"{scale},{estimated:.4f}")


if __name__ == "__main__":
    main()
