"""Historical result loading and comparability annotations, without HTTP state."""
from typing import Any, Dict, List, Optional, Tuple
from swarmbalance.paths import PROJECT_ROOT as _PROJECT_ROOT
AMBIGUOUS_DIRECTION_METRICS = {"泊位利用率", "机巢周转率"}
_CSV_FILES = [
    "frontend_greedy_metrics.csv",
    "backend_si_metrics.csv",
    "backend_ga_metrics.csv",
    "backend_ortools_metrics.csv",
    "one_click_latest.csv",
]

def _resolve_basis(meta_rows: List[Dict[str, Any]]) -> Tuple[Optional[int], List[Dict[str, Any]]]:
    """按「生成任务数」的众数确定共同口径，返回 (基准任务数, 偏离行列表)。

    为什么不用总步数：总步数是 episode 提前跑完时的**运行结果**，同一设定下各算法
    天然互不相等，拿它当基准会把正常的性能差异误报成口径不一致（曾实测 10 行步数
    全不相等 → 众数退化成无意义的 858 → 9/10 行被误标）。完成率等指标的分母是
    生成任务数，所以只有它不一致才是真正不可比。

    众数只出现一次时返回 (None, [])：宁可不给基准，也不硬选一个误导人的。
    """
    counts: Dict[int, int] = {}
    for row in meta_rows:
        try:
            n = int(float(row.get("生成任务数", 0)))
        except (TypeError, ValueError):
            continue
        if n > 0:
            counts[n] = counts.get(n, 0) + 1
    if not counts:
        return None, []
    top = max(counts.items(), key=lambda kv: (kv[1], -kv[0]))
    if top[1] < 2:
        return None, []
    basis = top[0]
    off: List[Dict[str, Any]] = []
    for row in meta_rows:
        try:
            n = int(float(row.get("生成任务数", 0)))
            steps = int(float(row.get("总步数", 0)))
        except (TypeError, ValueError):
            continue
        if n > 0 and n != basis:
            off.append({"算法": row.get("算法"), "生成任务数": n, "总步数": steps})
    return basis, off

def compare():
    """读 results/compare/*.csv，返回各算法最后一行指标（供前端 ECharts 对比）。"""
    import math
    import pandas as pd
    compare_dir = _PROJECT_ROOT / "results" / "compare"
    frames: List[pd.DataFrame] = []
    for name in _CSV_FILES:
        path = compare_dir / name
        if not path.exists():
            continue
        df = pd.read_csv(path, encoding="utf-8-sig")
        if "算法" not in df.columns:
            continue
        df["_来源"] = path.name          # 记录每行来自哪个文件，供下面标注来源
        frames.append(df)
    if not frames:
        return {"rows": [], "columns": [], "basis": None, "inconsistent": []}

    data = pd.concat(frames, ignore_index=True)
    # 先去掉"空跑"行：全零 / 全 NaN 的一行没有任何评测意义。
    # 否则 one_click_latest.csv 这类全零记录会在下面 keep="last" 时
    # 覆盖掉同一个算法在其它 CSV 里的真实结果（实测 greedy/ga/pso/ortools 被清零）。
    num_cols_all = [c for c in data.columns if c not in ("算法", "_来源")]
    numeric = data[num_cols_all].apply(pd.to_numeric, errors="coerce")
    valid_mask = numeric.abs().sum(axis=1) > 0
    data = data.loc[valid_mask].reset_index(drop=True)
    if data.empty:
        return {"rows": [], "columns": []}

    # 同一算法取最后一条（保留最近一次评测），但只从有效行里取
    data = data.drop_duplicates("算法", keep="last").reset_index(drop=True)

    # 口径门禁 compare_gate 已随 results/ 一并移除；重新生成对比数据时须恢复判据。
    selected_sources = []
    for src in data["_来源"].tolist():
        if src not in selected_sources:
            selected_sources.append(src)
    compare_refusal = None

    # 口径守卫：只有分母（生成任务数）不一致才算不可比。历史上的真实反例是 ga 以
    # 30 任务进图、其余算法 60 任务。这里只标注、不改数值、不剔除行。
    # 只保留数值列 + 算法列，去掉总步数/完成任务数等冗余
    drop_cols = {"总步数", "完成任务数", "生成任务数", "换电总次数"}
    keep_cols = [c for c in data.columns if c not in ("算法", "_来源") and c not in drop_cols]
    rows = data[["算法"] + keep_cols].to_dict(orient="records")
    scale_rows = data[["算法", "总步数", "生成任务数", "_来源"]].to_dict(orient="records")
    basis_tasks, inconsistent = _resolve_basis(scale_rows)
    flagged = {i["算法"] for i in inconsistent}

    def _clean(v):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        if isinstance(v, float):
            return round(v, 4)
        return v

    def _as_int(v):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None

    for row, scale in zip(rows, scale_rows):
        for k in list(row.keys()):
            row[k] = _clean(row[k])
        row["口径"] = {
            "生成任务数": _as_int(scale.get("生成任务数")),
            "总步数": _as_int(scale.get("总步数")),
            "偏离": row.get("算法") in flagged,
            # keep="last" 会让后读到的文件顶掉先读到的；标出来源，避免答辩时
            # 说不清这一行到底是手工评测还是一次一键实验的结果。
            "来源": scale.get("_来源"),
        }

    return {
        "rows": rows,
        "columns": keep_cols,
        "basis": {"生成任务数": basis_tasks} if basis_tasks is not None else None,
        "inconsistent": inconsistent,
        # 方向随容量配置同向变化的指标：前端表格不得为它们高亮"最优算法"。
        # 名单维护点在本文件顶部常量，前端只消费 /api/compare 下发值、不另抄一份。
        "direction_ambiguous": sorted(AMBIGUOUS_DIRECTION_METRICS),
        # 门禁判据：false 时前端不得画对比图、不得高亮"最优算法"，并原样显示 refusal。
        "comparable": compare_refusal is None,
        "comparability_refusal": compare_refusal,
        "compared_sources": selected_sources,
    }
