"""统一指标落盘 schema —— 所有评测入口（greedy / pso / ga / ortools / marl）共用。

背景
----
历史上项目里存在两套互不相通的落盘口径：

* `evaluate_metrics.py` 写**英文**表头（`completion_rate` …），且**没有算法列**；
* `run_pso.py` / `run_ga.py` 写**中文**表头（`完成率` …），带 `算法` 列。

而 `results/plot_compare_metrics.py` 只认中文表头 + `算法` 列，于是汇总脚本一跑就
抛 `KeyError: Missing algorithm column`。此外两边都有「表头不一致就切 `w` 模式」的
逻辑，一旦误跑就会**静默覆盖**掉之前攒的实验结果，且不可恢复。

本模块把「列定义 + 统计量映射 + 写盘策略」收敛成唯一一份事实来源（single source
of truth），任何新的评测入口都应当 import 它，不再自己拼表头。

设计要点
--------
1. **单一表头**：`METRIC_COLUMNS` 即 CSV 列顺序，新增指标只改这里。
2. **算法列在第一位**：`算法` 恒定是第一列，绘图脚本据此识别算法。
3. **绝不静默覆盖**：表头不兼容时先把旧文件备份成 `*.bak-<时间戳>`，再写新表头，
   而不是直接 `w` 掉历史数据。
4. **机巢指标入表**：`berth_utilization_rate` / `nest_turnover_rate` 早就由
   `environment.Environment._berth_metrics()` 算出，但旧 `METRIC_COLUMNS` 没导出，
   导致项目书承诺的「机巢周转率 / 泊位利用率」进不了对比 CSV。此处补上。
"""

from __future__ import annotations

import csv
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

__all__ = [
    "ALGORITHM_COLUMN",
    "METRIC_COLUMNS",
    "CSV_HEADER",
    "ALGORITHM_LABELS",
    "to_output_metrics",
    "mean_metrics",
    "write_metrics_rows",
    "write_mean_metrics_row",
]

# ---------------------------------------------------------------------------
# 列定义
# ---------------------------------------------------------------------------

#: 算法名列，恒为第一列（plot_compare_metrics.py 依赖它）
ALGORITHM_COLUMN = "算法"

#: 统一指标列（不含算法列）。顺序即 CSV 列顺序。
#: 命名与 plot_compare_metrics.py 的 COLUMN_ALIASES 一一对应，勿随意改名。
METRIC_COLUMNS: List[str] = [
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
    # --- 机巢地面资源（项目书「机巢周转率 / 利用率」指标，此前算了没导出）---
    "泊位利用率",
    "机巢周转率",
    "平均泊位排队等待",
    "换电总次数",
    # --- 机队效率（申请书「提升无人机利用率 / 降低空载率」）---
    "无人机利用率",
    "空载率",
    "总飞行距离",
    # --- 任务链与禁飞区（申请书「任务链 / 顺路接入」「可配置禁飞区」）---
    "顺路接入次数",
    "禁飞区绕飞次数",
]

#: 完整表头 = 算法列 + 指标列
CSV_HEADER: List[str] = [ALGORITHM_COLUMN] + METRIC_COLUMNS

#: 算法 key -> 中文显示名（与 plot_compare_metrics.py 的 DISPLAY_NAMES 保持一致）
ALGORITHM_LABELS: Dict[str, str] = {
    "greedy": "贪心调度",
    "pso": "PSO",
    "ga": "GA",
    "ortools": "OR-Tools",
    "iql": "IQL",
    "iql_u": "IQL-U",
    "vdn": "VDN",
    "vdn_u": "VDN-U",
    "qmix": "QMIX",
    "qmix_u": "QMIX-U",
}

# environment.Environment.get_statistics() 的原始 key -> 统一列名
_STAT_KEY_MAP: Dict[str, str] = {
    "总步数": "episode_step",
    "完成任务数": "total_completed",
    "生成任务数": "total_generated",
    "完成率": "completion_rate",
    "从生成到分配等待时间": "avg_generation_to_assignment_wait",
    "从分配到实际装载上机等待时间": "avg_assignment_to_load_wait",
    "从上机到送达平均时间": "avg_load_to_delivery_time",
    "从生成到完成总时间平均": "avg_generation_to_completion_time",
    "从生成到完成总时间最大": "max_generation_to_completion_time",
    "超时率": "timeout_rate",
    "平均时延": "avg_delay",
    "优先级1平均时延": "avg_delay_priority_1",
    "优先级2平均时延": "avg_delay_priority_2",
    "优先级3平均时延": "avg_delay_priority_3",
    "总能量消耗": "total_energy_consumed",
    "泊位利用率": "berth_utilization_rate",
    "机巢周转率": "nest_turnover_rate",
    "平均泊位排队等待": "avg_berth_wait_time",
    "换电总次数": "total_swap_sessions",
    "无人机利用率": "avg_drone_utilization",
    "空载率": "empty_load_ratio",
    "总飞行距离": "total_flight_distance",
    "顺路接入次数": "chain_insertions",
    "禁飞区绕飞次数": "no_fly_detours",
}


# ---------------------------------------------------------------------------
# 统计量映射
# ---------------------------------------------------------------------------

def to_output_metrics(stats: Dict[str, Any]) -> Dict[str, float]:
    """把 `Environment.get_statistics()` 的原始字典映射成统一列的值。

    缺失字段按 0.0 兜底，保证任何入口写出的 CSV 都是完整的一行。
    """
    out: Dict[str, float] = {}
    for column in METRIC_COLUMNS:
        raw = stats.get(_STAT_KEY_MAP[column], 0.0)
        try:
            out[column] = float(raw)
        except (TypeError, ValueError):
            out[column] = 0.0
    return out


def mean_metrics(rows: Iterable[Dict[str, float]]) -> Dict[str, float]:
    """对多个 episode 的 `to_output_metrics` 结果按列求均值。"""
    rows = list(rows)
    if not rows:
        return {column: 0.0 for column in METRIC_COLUMNS}
    return {
        column: sum(float(row.get(column, 0.0)) for row in rows) / len(rows)
        for column in METRIC_COLUMNS
    }


# ---------------------------------------------------------------------------
# 写盘
# ---------------------------------------------------------------------------

def _backup_incompatible(path: Path, reason: str) -> Optional[Path]:
    """表头不兼容时把旧文件另存备份，返回备份路径。"""
    if not path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_suffix(path.suffix + f".bak-{stamp}")
    try:
        shutil.copy2(path, backup)
        print(f"[metrics_schema] 旧文件表头不兼容（{reason}），已备份至 {backup}")
        return backup
    except OSError as exc:  # pragma: no cover - 备份失败不应阻断主流程
        print(f"[metrics_schema] 警告：备份 {path} 失败（{exc}），将直接重建文件")
        return None


def write_metrics_rows(
    output_path: Path,
    algorithm: str,
    rows: Iterable[Dict[str, float]],
    mode: str = "append",
) -> Path:
    """把若干行（每个 episode 一行）写入统一 CSV。

    :param output_path: 目标 CSV 路径。
    :param algorithm: 算法 key（写入 `算法` 列），见 `ALGORITHM_LABELS`。
    :param rows: `to_output_metrics()` 产出的字典序列。
    :param mode:
        - ``"append"``（默认）：表头兼容则追加；
        - ``"overwrite"``：清空后重建（仅用于明确要重跑该算法时）。
    :return: 实际写入的路径。

    表头不兼容时不会静默覆盖：先备份旧文件，再写新表头。
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rows = list(rows)

    need_header = True
    if mode == "append" and output_path.exists():
        with open(output_path, "r", encoding="utf-8-sig", newline="") as f:
            existing = f.readline().strip().lstrip("\ufeff")
        if existing == ",".join(CSV_HEADER):
            need_header = False
        else:
            _backup_incompatible(output_path, reason="列定义已变更")

    write_mode = "a" if (mode == "append" and not need_header) else "w"
    with open(output_path, write_mode, newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if write_mode == "w" or need_header:
            writer.writerow(CSV_HEADER)
        for row in rows:
            writer.writerow([algorithm] + [row.get(c, 0.0) for c in METRIC_COLUMNS])
    return output_path


def write_mean_metrics_row(
    output_path: Path,
    algorithm: str,
    rows: Iterable[Dict[str, float]],
    mode: str = "append",
) -> Path:
    """把多个 episode 的**均值**写成一行。语义同 `write_metrics_rows`。"""
    return write_metrics_rows(output_path, algorithm, [mean_metrics(rows)], mode=mode)
