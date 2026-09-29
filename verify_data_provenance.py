#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""数据来源可追溯性自检 —— docs/数据来源与可追溯性登记表.md 的可执行版本。

登记表里的每条 `已核实` 都应当能被第三方独立重算，本脚本就是那个"重算"。
默认三段全部只读：不写任何文件、不改配置、不联网。

用法：
    python verify_data_provenance.py              # 三段全跑
    python verify_data_provenance.py --marl        # 只跑 MARL 发布值逐格核对（纯标准库）
    python verify_data_provenance.py --experiments  # 只跑结项 68 次运行重算（纯标准库）
    python verify_data_provenance.py --loader      # 只跑建筑高度双加载路径对比（需 numpy/osmnx）

退出码：0 = 全部通过预期；1 = 发现问题（本仓库当前状态**预期就是 1**，
因为 MARL 六行确实对不上任何一次运算）；2 = 依赖缺失导致某段没跑成。
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
COMPARE_CSV = os.path.join(ROOT, "results", "compare", "backend_wx_metrics.csv")
SACRED = os.path.join(ROOT, "backend_wx", "pymarl-master", "results", "sacred")
EXP_DIR = os.path.join(ROOT, "results", "experiments", "conclusion_20260911-043701")

# name.md 给出的 run 号 <-> 算法 1:1 映射
MARL_RUNS = {
    "qmix_u": "3", "vdn_u": "4", "iql_u": "5",
    "qmix": "6", "vdn": "8", "iql": "9",
}
# 发布表中文列名 -> info.json 里的 test 聚合键名
MARL_METRICS = [
    ("完成率", "test_completion_rate_mean", "higher"),
    ("超时率", "test_timeout_rate_mean", "lower"),
    ("平均时延", "test_avg_delay_mean", "lower"),
    ("总能量消耗", "test_total_energy_consumed_mean", "lower"),
    ("从生成到完成总时间平均", "test_avg_generation_to_completion_time_mean", "lower"),
    ("从生成到完成总时间最大", "test_max_generation_to_completion_time_mean", "lower"),
    ("从生成到分配等待时间", "test_avg_generation_to_assignment_wait_mean", "lower"),
    ("从分配到实际装载上机等待时间", "test_avg_assignment_to_load_wait_mean", "lower"),
    ("从上机到送达平均时间", "test_avg_load_to_delivery_time_mean", "lower"),
]


def _read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _display(path):
    """仓库相对路径：绝对路径会把开发机用户名带进对外输出。"""
    rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
    return rel if not rel.startswith("..") else os.path.basename(path)


def check_marl(report):
    """发布值是否等于该 run 的 test 聚合。核心判据：它不可能优于历史上最好的一局。"""
    if not os.path.isfile(COMPARE_CSV):
        report.append(("INFO", "MARL",
                       "不适用：MARL 模块与其指标行已于本版移除（移除前逐格核对结论为："
                       "54 格中 23 格优于历史最好一局、0 格劣于最差、38 格与任何原始行都不相等）。"
                       "详见 docs/数据来源与可追溯性登记表.md 第五节 R2"))
        return 0
    if not os.path.isdir(SACRED):
        report.append(("FAIL", "MARL",
                       "发布表 %s 存在，但其原始记录目录 %s 不在仓库里 —— clone 之后无法核对，"
                       "等于没有证据" % (_display(COMPARE_CSV), _display(SACRED))))
        return 1

    published = {r["算法"]: r for r in _read_csv(COMPARE_CSV) if r.get("算法")}
    better = worse = nomatch = 0
    cells = 0
    for algo, run_id in MARL_RUNS.items():
        info_path = os.path.join(SACRED, run_id, "info.json")
        rows_path = os.path.join(SACRED, run_id, "backend_wx_metrics.csv")
        if not (os.path.isfile(info_path) and os.path.isfile(rows_path)):
            report.append(("SKIP", "MARL", "run %s 缺文件" % run_id))
            continue
        info = json.load(open(info_path, encoding="utf-8"))
        all_rows = _read_csv(rows_path)
        pub_row = published.get(algo)
        if not pub_row:
            report.append(("FAIL", "MARL", "发布表里没有 %s 行" % algo))
            continue
        for cn, key, better_dir in MARL_METRICS:
            vals = [x for x in (info.get(key) or []) if isinstance(x, (int, float))]
            if not vals or cn not in pub_row:
                continue
            pv = float(pub_row[cn])
            best = max(vals) if better_dir == "higher" else min(vals)
            worst = min(vals) if better_dir == "higher" else max(vals)
            cells += 1
            if (better_dir == "lower" and pv < best - 1e-9) or (
                    better_dir == "higher" and pv > best + 1e-9):
                better += 1
            if (better_dir == "lower" and pv > worst + 1e-9) or (
                    better_dir == "higher" and pv < min(vals) - 1e-9):
                worse += 1
            if not any(abs(float(r[cn]) - pv) < 1e-4 for r in all_rows if r.get(cn)):
                nomatch += 1

    report.append(("NOTE", "MARL", "已核对性能格 %d 个" % cells))
    if worse == 0 and better > 0:
        report.append(("FAIL", "MARL",
                       "%d/%d 格优于该算法历史上最好的一局，而劣于最差一局的有 %d 格 —— "
                       "偏离全部单向朝有利方向，随机误差下概率约 2^-%d" % (better, cells, worse, better)))
    if nomatch:
        report.append(("FAIL", "MARL",
                       "%d/%d 格与该 run 的任何一行（train+test）都不相等" % (nomatch, cells)))
    if not better and not nomatch:
        report.append(("OK", "MARL", "发布值可在原始记录中找到"))
    return 1 if (better or nomatch) else 0


def check_experiments(report):
    """结项实验：raw <-> plan 一一对应，且统计表的均值/标准差/中位数可逐位重算。"""
    if not os.path.isdir(EXP_DIR):
        report.append(("SKIP", "EXPERIMENT", "缺少 %s" % EXP_DIR))
        return 2
    raw = _read_csv(os.path.join(EXP_DIR, "raw_runs.csv"))
    plan = _read_csv(os.path.join(EXP_DIR, "plan.csv"))
    stats = _read_csv(os.path.join(EXP_DIR, "algorithm_comparison_stats.csv"))

    rk = {(r["实验"], r["取值"], r["重复"], r["Seed"], r["算法key"]) for r in raw}
    pk = {(p["实验"], p["取值"], p["重复"], p["Seed"], p["算法"]) for p in plan}
    if rk == pk:
        report.append(("OK", "EXPERIMENT", "raw %d 行与 plan %d 行按 (实验,取值,重复,Seed,算法) 完全一一对应"
                       % (len(raw), len(plan))))
    else:
        report.append(("FAIL", "EXPERIMENT", "raw 独有 %d，plan 独有 %d" % (len(rk - pk), len(pk - rk))))

    failed = [r for r in raw if r.get("成功") != "True"]
    report.append(("OK" if not failed else "FAIL", "EXPERIMENT",
                   "失败运行 %d 个" % len(failed)))

    # 分组键：plan 里算法列存的是 key（ga），raw 里 算法key 同义、算法 存的是中文标签（GA）
    groups = {}
    for r in raw:
        if r["实验"] == "algorithm_comparison":
            groups.setdefault(r["算法key"], []).append(r)
    seedsets = {k: sorted(v["Seed"] for v in vs) for k, vs in groups.items()}
    if len(set(map(tuple, seedsets.values()))) == 1:
        report.append(("OK", "EXPERIMENT", "四算法配对 seed 一致：%s" %
                       ", ".join("%s=%s" % (k, v) for k, v in sorted(seedsets.items()))))
    else:
        report.append(("FAIL", "EXPERIMENT", "配对 seed 不一致：%s" % seedsets))

    cells = bad = 0
    worst_rel = 0.0
    for st in stats:
        rows = groups.get(st["算法key"], [])
        if len(rows) != int(st.get("样本数") or 0):
            report.append(("FAIL", "EXPERIMENT", "%s 样本数标 %s 实%d" % (
                st["算法key"], st.get("样本数"), len(rows))))
        for col in rows[0] if rows else []:
            pass
        for m in ("完成率", "超时率", "从生成到完成总时间平均", "无人机利用率", "空载率",
                  "泊位利用率", "机巢周转率", "平均泊位排队等待", "总能量消耗", "总飞行距离"):
            try:
                vals = [float(r[m]) for r in rows]
            except (KeyError, TypeError, ValueError):
                continue
            fns = {"_均值": statistics.fmean,
                   "_标准差": (lambda x: statistics.stdev(x) if len(x) > 1 else 0.0),
                   "_中位数": statistics.median}
            for suffix, fn in fns.items():
                key = m + suffix
                if key not in st or not st[key]:
                    continue
                cells += 1
                shipped = float(st[key])
                mine = fn(vals)
                rel = abs(mine - shipped) / max(abs(shipped), 1e-300)
                worst_rel = max(worst_rel, rel)
                if rel > 1e-9:
                    bad += 1
                    report.append(("FAIL", "EXPERIMENT", "%s %s 重算=%.12g 印=%.12g" % (
                        st["算法key"], key, mine, shipped)))
    if not bad:
        report.append(("OK", "EXPERIMENT",
                       "统计表 %d 个均值/标准差/中位数全部可重算，最大相对偏差 %.1e"
                       "（IEEE-754 求和顺序噪声，非数据差异）" % (cells, worst_rel)))
    return 1 if bad else 0


def check_loader(report):
    """同一张 OSM，两条加载路径给出的碰撞体规模差 6 倍。"""
    fe = os.path.join(ROOT, "frontend")
    if fe not in sys.path:
        sys.path.insert(0, fe)
    try:
        from tools import osm as osm_mod
    except Exception as exc:
        report.append(("SKIP", "LOADER", "无法导入 tools.osm（%s）；此段需要 numpy/osmnx" % exc))
        return 2
    mapfile = os.path.join(fe, "data", "map", "part_of_yangpu.osm")
    if not os.path.isfile(mapfile):
        report.append(("SKIP", "LOADER", "缺 %s" % mapfile))
        return 2

    def summarize(rows, label):
        n = len(rows)
        nan = sum(1 for b in rows if isinstance(b.get("height"), float) and math.isnan(b["height"]))
        none_ = sum(1 for b in rows if b.get("height") is None)
        over = sum(1 for b in rows
                   if b.get("height") is not None and not (isinstance(b.get("height"), float)
                                                           and math.isnan(b["height"]))
                   and b["height"] > 20)
        report.append(("NOTE", "LOADER",
                       "%-10s 建筑=%-5d 有高度=%-5d NaN=%-5d None=%-5d 碰撞体(>20m)=%d (%.2f%%)"
                       % (label, n, n - nan - none_, nan, none_, over, 100.0 * over / max(1, n))))
        return over

    fb = summarize(osm_mod._load_map_data_fallback(mapfile)[1], "fallback")
    _mode = "osmnx" if osm_mod._osmnx_available() else "fallback"
    ox = summarize(osm_mod.load_map_data(mapfile)[1], _mode)
    if fb != ox:
        report.append(("FAIL", "LOADER",
                       "同一张地图两条路径的障碍物规模不同：fallback=%d vs %s=%d（差 %.1f 倍）。"
                       "能否复现取决于目标机器 import osmnx 是否成功" % (
                           fb, _mode, ox, fb / max(1, ox))))
    else:
        report.append(("OK", "LOADER", "两条路径障碍物规模一致（%d）" % fb))
    return 1 if fb != ox else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--marl", action="store_true", help="只跑 MARL 发布值核对")
    ap.add_argument("--experiments", action="store_true", help="只跑结项实验重算")
    ap.add_argument("--loader", action="store_true", help="只跑建筑高度双路径对比")
    args = ap.parse_args()
    selected = [k for k in ("marl", "experiments", "loader") if getattr(args, k)]
    if not selected:
        selected = ["marl", "experiments", "loader"]

    report = []
    rc = 0
    runners = {"marl": check_marl, "experiments": check_experiments, "loader": check_loader}
    for name in selected:
        rc = max(rc, runners[name](report))

    order = {"FAIL": 0, "SKIP": 1, "INFO": 2, "NOTE": 3, "OK": 4}
    print("=" * 96)
    print("SwarmBalance 数据来源可追溯性自检")
    print("=" * 96)
    for status, section, msg in sorted(report, key=lambda e: order.get(e[0], 9)):
        print("[%s] %-10s %s" % (status, section, msg))
    print("-" * 96)
    counts = {}
    for s, _, _ in report:
        counts[s] = counts.get(s, 0) + 1
    print("合计: " + "  ".join("%s=%d" % (k, counts[k]) for k in ("FAIL", "SKIP", "INFO", "NOTE", "OK")
                            if k in counts))
    if rc == 1:
        print("=> 发现不可追溯/不一致数据。详见 docs/数据来源与可追溯性登记表.md")
    return rc


if __name__ == "__main__":
    sys.exit(main())
