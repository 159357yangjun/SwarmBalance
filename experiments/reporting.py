"""Experiment reporting helpers for reproducible conclusion/defense evidence.

This module intentionally uses only the Python standard library so report generation does
not depend on pandas/scipy. It adds descriptive dispersion (mean/std) and paired-seed
comparisons without claiming statistical significance.
"""
from __future__ import annotations

import csv
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from frontend.metrics_schema import ALGORITHM_LABELS, METRIC_COLUMNS

KEY_METRICS: Sequence[str] = (
    "完成率",
    "超时率",
    "从生成到完成总时间平均",
    "无人机利用率",
    "空载率",
    "泊位利用率",
    "机巢周转率",
    "平均泊位排队等待",
    "总能量消耗",
    "总飞行距离",
)

HIGHER_IS_BETTER = {"完成率", "无人机利用率", "泊位利用率", "机巢周转率"}
LOWER_IS_BETTER = {
    "超时率",
    "从生成到完成总时间平均",
    "空载率",
    "平均泊位排队等待",
    "总能量消耗",
    "总飞行距离",
}


def _float(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def descriptive_stats(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return one wide descriptive row per algorithm for algorithm_comparison runs."""
    rows = [r for r in rows if r.get("成功") and r.get("实验") == "algorithm_comparison"]
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("算法key", "")), []).append(row)

    out: List[Dict[str, Any]] = []
    for alg, items in sorted(grouped.items()):
        record: Dict[str, Any] = {
            "算法key": alg,
            "算法": ALGORITHM_LABELS.get(alg, alg),
            "样本数": len(items),
        }
        for metric in KEY_METRICS:
            vals = [_float(r.get(metric)) for r in items]
            record[f"{metric}_均值"] = mean(vals) if vals else 0.0
            record[f"{metric}_标准差"] = stdev(vals) if len(vals) > 1 else 0.0
            record[f"{metric}_中位数"] = median(vals) if vals else 0.0
        out.append(record)
    return out


def paired_comparison(
    rows: Iterable[Dict[str, Any]],
    candidate: str = "ga",
    baseline: str = "greedy",
) -> List[Dict[str, Any]]:
    """Compare two algorithms on exactly matched seeds.

    ``平均改进`` is direction-normalized: positive means candidate is better according
    to the metric's declared direction. ``相对改进率`` is descriptive only.
    """
    rows = [r for r in rows if r.get("成功") and r.get("实验") == "algorithm_comparison"]
    by_alg_seed: Dict[Tuple[str, int], Dict[str, Any]] = {}
    for row in rows:
        try:
            seed = int(row.get("Seed"))
        except (TypeError, ValueError):
            continue
        by_alg_seed[(str(row.get("算法key", "")), seed)] = row

    seeds = sorted(
        seed for alg, seed in by_alg_seed
        if alg == candidate and (baseline, seed) in by_alg_seed
    )
    out: List[Dict[str, Any]] = []
    for metric in KEY_METRICS:
        pairs = [
            (_float(by_alg_seed[(baseline, s)].get(metric)), _float(by_alg_seed[(candidate, s)].get(metric)))
            for s in seeds
        ]
        if not pairs:
            continue
        baseline_vals = [a for a, _ in pairs]
        candidate_vals = [b for _, b in pairs]
        raw_deltas = [b - a for a, b in pairs]
        if metric in HIGHER_IS_BETTER:
            improvements = raw_deltas
            direction = "越高越好"
        elif metric in LOWER_IS_BETTER:
            improvements = [a - b for a, b in pairs]
            direction = "越低越好"
        else:
            improvements = raw_deltas
            direction = "未定义"
        base_mean = mean(baseline_vals)
        cand_mean = mean(candidate_vals)
        imp_mean = mean(improvements)
        rel = (imp_mean / abs(base_mean)) if abs(base_mean) > 1e-12 else 0.0
        eps = 1e-12
        wins = sum(1 for x in improvements if x > eps)
        ties = sum(1 for x in improvements if abs(x) <= eps)
        losses = sum(1 for x in improvements if x < -eps)
        out.append({
            "指标": metric,
            "方向": direction,
            "配对样本数": len(pairs),
            "基线算法": ALGORITHM_LABELS.get(baseline, baseline),
            "候选算法": ALGORITHM_LABELS.get(candidate, candidate),
            "基线均值": base_mean,
            "候选均值": cand_mean,
            "候选减基线": mean(raw_deltas),
            "平均改进": imp_mean,
            "相对改进率": rel,
            "胜": wins,
            "平": ties,
            "负": losses,
        })
    return out


def write_rows(path: Path, rows: List[Dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return path
    fields: List[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def render_paired_markdown(rows: List[Dict[str, Any]]) -> List[str]:
    if not rows:
        return []
    lines = [
        "## GA 与 Greedy 的配对 Seed 描述性比较",
        "",
        "> 下表只做描述性比较，不等价于统计显著性检验；正的“平均改进”表示 GA 按该指标方向更优。",
        "",
        "| 指标 | Greedy 均值 | GA 均值 | 平均改进 | 相对改进率 | 胜/平/负 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| {r['指标']} | {float(r['基线均值']):.6g} | {float(r['候选均值']):.6g} | "
            f"{float(r['平均改进']):.6g} | {float(r['相对改进率']):.2%} | "
            f"{r['胜']}/{r['平']}/{r['负']} |"
        )
    lines.append("")
    return lines
