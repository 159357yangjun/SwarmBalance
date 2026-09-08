import argparse
import copy
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path


SUMMARY_KEYS = [
    "总步数",
    "完成任务数",
    "生成任务数",
    "完成率",
    "从生成到分配等待时间",
    "从分配到实际装载上机等待时间",
    "从上机到送达平均时间",
    "从生成到完成总时间平均",
    "从生成到完成总时间最大",
    "超时率",
    "平均时延",
    "优先级1平均时延",
    "优先级2平均时延",
    "优先级3平均时延",
    "总能量消耗",
]


def _wait_for_file(path, timeout_s=30):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if path.exists():
            return True
        time.sleep(0.2)
    return path.exists()


def _load_metrics_rows(csv_path):
    if not csv_path.exists():
        return [], []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    return rows, reader.fieldnames or []


def _filter_test_rows(rows):
    test_rows = [row for row in rows if row.get("mode") == "test" or row.get("模式") == "test"]
    return test_rows if test_rows else rows


def _mean(values):
    if not values:
        return None
    return sum(values) / len(values)


def _average_metrics(rows, columns):
    if not rows:
        return {}
    ignore_cols = {"source", "episode", "t_env", "mode", "时间步", "模式"}
    metrics = {}
    for col in columns:
        if col in ignore_cols:
            continue
        numeric_vals = []
        for row in rows:
            val = row.get(col, "")
            if val == "":
                continue
            try:
                numeric_vals.append(float(val))
            except ValueError:
                numeric_vals = []
                break
        if numeric_vals:
            metrics[col] = _mean(numeric_vals)
    return metrics


def _normalize_metric_names(metrics):
    normalized = dict(metrics)
    aliases = {
        "episode_step": "总步数",
        "total_completed": "完成任务数",
        "total_generated": "生成任务数",
        "total_generated_mean": "生成任务数",
        "completion_rate": "完成率",
        "avg_generation_to_assignment_wait": "从生成到分配等待时间",
        "avg_assignment_to_load_wait": "从分配到实际装载上机等待时间",
        "avg_wait_time_to_load": "从分配到实际装载上机等待时间",
        "avg_load_to_delivery_time": "从上机到送达平均时间",
        "avg_delivery_time": "从上机到送达平均时间",
        "avg_generation_to_completion_time": "从生成到完成总时间平均",
        "avg_gen_to_done": "从生成到完成总时间平均",
        "max_generation_to_completion_time": "从生成到完成总时间最大",
        "max_delivery_time": "从生成到完成总时间最大",
        "timeout_rate": "超时率",
        "avg_delay": "平均时延",
        "avg_delay_priority_1": "优先级1平均时延",
        "avg_delay_priority_2": "优先级2平均时延",
        "avg_delay_priority_3": "优先级3平均时延",
        "total_energy_consumed": "总能量消耗",
    }
    for old_key, new_key in aliases.items():
        if old_key in normalized and new_key not in normalized:
            normalized[new_key] = normalized[old_key]
    return {key: normalized[key] for key in SUMMARY_KEYS if key in normalized}


def _parse_interval_scales(values):
    if isinstance(values, str):
        values = [values]

    scales = []
    for item in values:
        if item is None:
            continue
        for part in str(item).split(","):
            part = part.strip()
            if not part:
                continue
            scales.append(float(part))
    return scales


def _load_shared_config(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_shared_config(config_path, config_data):
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)


def _set_interval_scale(config_data, interval_scale):
    updated = copy.deepcopy(config_data)
    task_generation_cfg = updated.setdefault("task_generation", {})
    realistic_cfg = task_generation_cfg.setdefault("realistic", {})
    realistic_cfg["interval_scale"] = float(interval_scale)
    return updated


def main():
    pymarl_root = Path(__file__).resolve().parents[1]
    workspace_root = Path(__file__).resolve().parents[3]
    compare_dir = workspace_root / "results" / "compare"
    compare_csv = compare_dir / "backend_wx_metrics.csv"
    config_path = workspace_root / "config" / "simulation.json"

    parser = argparse.ArgumentParser(description="Batch evaluate backend_wx and aggregate metrics by interval_scale.")
    parser.add_argument(
        "--interval-scales",
        nargs="+",
        default=["3.5", "3", "2.5", "2", "1.5", "1"],
        help="Interval scales to evaluate. Supports space-separated values and comma-separated strings.",
    )
    parser.add_argument("--repeats", type=int, default=3, help="Number of runs per interval_scale.")
    parser.add_argument("--test-nepisode", type=int, default=3, help="test_nepisode passed to PyMARL.")
    parser.add_argument("--batch-size-run", type=int, default=1, help="batch_size_run passed to PyMARL.")
    parser.add_argument("--use-cuda", action="store_true", default=False, help="Enable CUDA for evaluation.")
    parser.add_argument("--save-model", action="store_true", default=False, help="Enable model saving.")
    parser.add_argument(
        "--checkpoint-path",
        type=str,
        default="results/models/qmix__2026-05-10_20-33-19",
        help="Checkpoint directory relative to pymarl_root.",
    )
    parser.add_argument(
        "--load-step",
        type=int,
        default=0,
        help="Load step passed to PyMARL. 0 means latest.",
    )
    parser.add_argument("--unique-task-assignment", action="store_true", default=False, help="Use unique task assignment.")
    parser.add_argument("--label-prefix", type=str, default="backend_wx_interval_scale_test", help="Run label prefix.")
    args = parser.parse_args()

    interval_scales = _parse_interval_scales(args.interval_scales)
    if not interval_scales:
        raise ValueError("--interval-scales cannot be empty")

    original_config = _load_shared_config(config_path)
    results = []

    try:
        for interval_scale in interval_scales:
            scale_config = _set_interval_scale(original_config, interval_scale)
            _write_shared_config(config_path, scale_config)

            repeat_metrics = []
            for repeat_idx in range(args.repeats):
                label = f"{args.label_prefix}_scale_{interval_scale:g}_rep_{repeat_idx + 1}"
                env = os.environ.copy()
                env["PYMARL_DISABLE_SACRED"] = "1"
                env["PYMARL_METRICS_DIR"] = str(compare_dir)
                cmd = [
                    sys.executable,
                    str(pymarl_root / "src" / "main.py"),
                    "--config=qmix",
                    "--env-config=env_drone",
                    "with",
                    f"unique_task_assignment={str(bool(args.unique_task_assignment))}",
                    "evaluate=True",
                    f"checkpoint_path={args.checkpoint_path}",
                    f"load_step={int(args.load_step)}",
                    f"test_nepisode={int(args.test_nepisode)}",
                    f"batch_size_run={int(args.batch_size_run)}",
                    f"use_cuda={str(bool(args.use_cuda))}",
                    f"save_model={str(bool(args.save_model))}",
                    f"label={label}",
                ]
                print("Running:", " ".join(cmd))
                subprocess.run(cmd, cwd=str(pymarl_root), check=True, env=env)

                if not _wait_for_file(compare_csv, timeout_s=30):
                    print(f"Warning: metrics CSV not found at {compare_csv}; skip.")
                    continue

                rows, columns = _load_metrics_rows(compare_csv)
                rows = _filter_test_rows(rows)
                metric_means = _normalize_metric_names(_average_metrics(rows, columns))
                repeat_metrics.append(metric_means)

            combined = _normalize_metric_names(
                _average_metrics(repeat_metrics, sorted({key for metrics in repeat_metrics for key in metrics}))
            )
            combined["interval_scale"] = float(interval_scale)
            combined["repeats"] = int(args.repeats)
            combined["test_nepisode"] = int(args.test_nepisode)

            results.append(combined)
            print(
                f"interval_scale={interval_scale:g}: 完成率={combined.get('完成率', 0.0):.4f}, "
                f"超时率={combined.get('超时率', 0.0):.4f}, "
                f"平均时延={combined.get('平均时延', 0.0):.4f}, "
                f"完成任务数={combined.get('完成任务数', 0.0):.1f}, "
                f"生成任务数={combined.get('生成任务数', 0.0):.1f}, "
                f"总能量消耗={combined.get('总能量消耗', 0.0):.4f}"
            )
    finally:
        _write_shared_config(config_path, original_config)

    compare_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["interval_scale", "repeats", "test_nepisode"] + SUMMARY_KEYS
    with open(compare_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(row)

    print(f"Wrote summary to: {compare_csv}")


if __name__ == "__main__":
    main()
