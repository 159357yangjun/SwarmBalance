"""Compatibility projection for the original Greedy-only CSV format."""
import csv
from swarmbalance.simulation.metrics import to_output_metrics
METRIC_COLUMNS = [
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


def _to_output_metrics(stats):
    output = to_output_metrics(stats)
    return {column: output[column] for column in METRIC_COLUMNS}


def _mean_metrics(rows):
    if not rows:
        return {col: 0.0 for col in METRIC_COLUMNS}
    return {
        col: sum(float(row.get(col, 0.0)) for row in rows) / len(rows)
        for col in METRIC_COLUMNS
    }

def _write_csv(output_path, stats):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = ",".join(METRIC_COLUMNS)
    existing_header = None
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8-sig", newline="") as f:
            existing_header = f.readline().strip()

    write_mode = "a" if existing_header == header else "w"
    with open(output_path, write_mode, newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if write_mode == "w":
            writer.writerow(METRIC_COLUMNS)
        writer.writerow([stats[col] for col in METRIC_COLUMNS])
