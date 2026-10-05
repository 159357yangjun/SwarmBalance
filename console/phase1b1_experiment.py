# -*- coding: utf-8 -*-
"""Phase 1B-1 实验：distance-aware scheduling —— Euclidean vs PlannedDistance。

预注册假设（先写下再看数，禁止事后编解释；已登记在总纲 §17.0）：
  H0  distance-only 切换后 C-1/C-2 全部核心 KPI 逐值不变，或差异 < 1 单任务。
      （依据 1B-0：ranking inversion = 7/10676 = 0.07%，最大 detour ratio ≤ 1.0833。）
  H1  若完成率/超时率变化 ≥ 2 单任务，则必须能追溯到本 seed 里 planner 实际给出的
      route!=euclid 候选腿（provider.deltas）中的具体一次分配；
      追不到 ⇒ 对机制的理解有第三处遗漏 ⇒ 先查机制，不改代码、不调权重。

只替换【距离】：ETA / energy / range feasibility 一字未动（route_cost.py 的 provider
类型上就只有 distance/batch）。这是 1B-1 与 1B-2/1B-3 的分界。

算法范围 Greedy + GA：PSO 在 C-1/C-2 两次独立复现 optimize_calls=0，不具备对照价值；
OR-Tools 介入/回退率未闭合。不为凑"四算法"把未真正介入优化的结果混进来。
GA 面同时是**阴性对照面**：backend_si/pso_scheduler.py 全文零引用 route_cost_provider
⇒ 理论上两面逐位相同；若 GA 出现漂移，说明存在我没找到的第二条通路（见 G5）。

为什么用「子进程 + 环境变量」而不是 in-process monkeypatch：
  worker.run_one 内部是 `from environment import Environment`，父进程改模块属性对它无效；
  且 frontend/task.py、frontend/drone.py:25 在 **import 时冻结配置**，同进程切配置会拿到
  上一轮的常量。所以每格起一个干净 worker，provider 经 SWARM_BALANCE_ROUTE_COST 注入
  （environment.py:206-222），证人经 SWARM_BALANCE_ROUTE_COST_DUMP 落盘。

配对纪律：两面除 provider 外逐字相同（同一份 cfg JSON 字节、同一 seed、同一 episode_steps、
同一 osmnx 依赖状态）。缓存两面共享（_path_clear_bucket 按障碍几何指纹分桶），
否则第二面吃到热缓存、第一面冷算 ⇒ is_path_clear 判定顺序变了就不是单变量实验。
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
OSM = REPO / "frontend" / "data" / "map" / "part_of_yangpu.osm"
_CANDIDATES = (REPO.parent / ".venv310" / "Scripts" / "python.exe",
               REPO / ".venv310" / "Scripts" / "python.exe")
PYV = next((str(p) for p in _CANDIDATES if pathlib.Path(p).exists()), sys.executable)
SEEDS = (40901, 40902, 40903)
ALGOS = ("greedy", "ga")
PROVIDERS = ("euclidean", "planned_distance")
EPISODE_STEPS = 3600
FIXTURES = {
    "C1": {"task_generation": {"realistic": {"interval_scale": 0.70, "total_tasks": 240}},
           "environment": {"num_drones": 6},
           "heterogeneous": {"fleet_mix": {"light_express": 3, "standard_cargo": 2, "heavy_cargo": 1}}},
    "C2": {"task_generation": {"realistic": {"interval_scale": 0.55, "total_tasks": 240}},
           "environment": {"num_drones": 4},
           "heterogeneous": {"fleet_mix": {"light_express": 2, "standard_cargo": 1, "heavy_cargo": 1}}},
}
#: 参与 H0/H1 判定的核心 KPI（列名口径 = frontend/metrics_schema.py:METRIC_COLUMNS）
CORE_KPI = ["完成任务数", "生成任务数", "完成率", "超时率", "平均时延",
            "总能量消耗", "总飞行距离", "换电总次数", "泊位利用率", "机巢周转率"]
#: 按"任务个数"计的列：H1 的「≥ 2 单任务」门槛只作用于它们
COUNT_KPI = ["完成任务数", "生成任务数"]
#: 「无法追溯」的判定阈值：计数型 KPI 差 2 个任务而该 seed 没有任何绕障候选腿 ⇒ 归因断链
UNTRACEABLE_TASK_THRESHOLD = 2.0


def _merge(base: dict, patch: dict) -> dict:
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def cell_cfg(fixture: str) -> bytes:
    """两面共用的配置字节。同一个 fixture 只生成一次，避免任何序列化差异。"""
    cfg = json.loads((REPO / "config" / "simulation.json").read_text(encoding="utf-8"))
    _merge(cfg, FIXTURES[fixture])
    return json.dumps(cfg, ensure_ascii=False).encode("utf-8")


def run_cell(fixture: str, seed: int, provider: str, algorithm: str,
             workdir: pathlib.Path, steps: int = EPISODE_STEPS,
             reach_weight: float = 0.0) -> dict:
    """起一个 worker 进程跑一格，返回 metrics + provider 证人。"""
    tag = "%s_%s_%d_%s_w%s" % (fixture, algorithm, seed, provider,
                                str(reach_weight).replace(".", "p"))
    cfg_path = workdir / ("cfg_%s.json" % tag)
    out_path = workdir / ("out_%s.json" % tag)
    dump_path = workdir / ("evidence_%s.json" % tag)
    cfg_path.write_bytes(cell_cfg(fixture))

    env = dict(os.environ)
    env["SWARM_BALANCE_ROUTE_COST"] = provider          # 被切变量 1：距离口径
    # 被切变量 2（Phase 1B-2）：ETA 权重。REACH_WEIGHT 在 greedy/scheduler.py import 期冻结
    # ⇒ 必须经子进程环境注入，与 provider 同一套路数。
    env["SWARM_BALANCE_REACH_WEIGHT"] = str(reach_weight)
    env["SWARM_BALANCE_ROUTE_COST_DUMP"] = str(dump_path)
    env.pop("SWARM_BALANCE_SIM_CONFIG", None)           # worker 自己设，避免继承脏值
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [PYV, "-X", "utf8", "-m", "experiments.worker",
           "--config", str(cfg_path), "--algorithm", algorithm,
           "--seed", str(seed), "--episode-steps", str(steps),
           "--osm", str(OSM), "--output", str(out_path)]
    proc = subprocess.run(cmd, cwd=str(REPO), env=env, text=True,
                          capture_output=True, timeout=7200)
    if not out_path.exists():
        raise RuntimeError("[WORKER_NO_OUTPUT] %s exit=%s stderr=%s"
                           % (tag, proc.returncode, proc.stderr[-500:]))
    res = json.loads(out_path.read_text(encoding="utf-8"))
    if not res.get("ok"):
        raise RuntimeError("[WORKER_FAILED] %s :: %s" % (tag, res.get("error")))
    evidence = None
    if dump_path.exists():
        try:
            evidence = json.loads(dump_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError("[EVIDENCE_UNREADABLE] %s :: %s" % (dump_path, exc))
    elif provider == "planned_distance":
        raise RuntimeError("[EVIDENCE_MISSING] %s：实验面没落证人，翻转无从追溯" % tag)
    res["_tag"] = tag
    res["_provider_requested"] = provider
    res["_evidence"] = evidence
    return res


def collect(seeds=SEEDS, algorithms=ALGOS, steps=EPISODE_STEPS, workdir=None,
            weights=(0.0,)):
    """跑满 fixture × algorithm × seed × weight × provider，返回 (rows, cells, workdir)。

    `weights` 只有一档（默认 0.0）时就是 Phase 1B-1 的 24 格；两档即 Phase 1B-2 的 48 格。
    """
    created = workdir is None
    wd = pathlib.Path(workdir) if workdir else pathlib.Path(tempfile.mkdtemp(prefix="p1b1_"))
    wd.mkdir(parents=True, exist_ok=True)
    rows, cells = [], {}
    for fx in FIXTURES:
        for alg in algorithms:
            for sd in seeds:
                for w in weights:
                    for pv in PROVIDERS:
                        print(f"[run] {fx} {alg} seed={sd} weight={w} provider={pv}", flush=True)
                        res = run_cell(fx, sd, pv, alg, wd, steps=steps, reach_weight=w)
                        m = res["metrics"]
                        ev = res["_evidence"] or {}
                        cells[(fx, alg, sd, pv, w)] = res
                        st = ev.get("stats", {})
                        print(f"      完成={m['完成任务数']:.0f} 生成={m['生成任务数']:.0f} "
                              f"超时率={m['超时率']:.4f} deltas={st.get('deltas', 'n/a')} "
                              f"eta_calls={st.get('eta_calls', 'n/a')} "
                              f"耗时={res.get('duration_seconds')}s", flush=True)
                        for k in CORE_KPI:
                            rows.append(dict(fixture=fx, algorithm=alg, seed=sd, weight=w,
                                             provider=pv, kpi=k, value=float(m[k])))
    if created:
        shutil.rmtree(wd, ignore_errors=True)
    return rows, cells, wd


def paired_diffs(rows):
    """按 (fixture, algorithm, seed, kpi) 求 planned - euclid 的逐 seed 差分。"""
    idx = {(r["fixture"], r["algorithm"], r["seed"], r.get("weight", 0.0), r["kpi"],
            r["provider"]): r["value"] for r in rows}
    out = []
    for f, a, s, w, k in sorted({(f, a, s, wt, k) for (f, a, s, wt, k, _p) in idx}):
        e = idx[(f, a, s, w, k, "euclidean")]
        p = idx[(f, a, s, w, k, "planned_distance")]
        out.append(dict(fixture=f, algorithm=a, seed=s, weight=w, kpi=k,
                        euclid=e, planned=p, diff=p - e))
    return out


def sign_summary(diffs):
    """每个 (fixture, algorithm, kpi) 汇总逐 seed 差分的符号（n=3 不做显著性宣称）。"""
    agg = {}
    for d in diffs:
        key = (d["fixture"], d["algorithm"], d["kpi"], d.get("weight", 0.0))
        b = agg.setdefault(key, {"pos": 0, "neg": 0, "zero": 0, "absmax": 0.0, "vals": []})
        b["vals"].append(d["diff"])
        b["absmax"] = max(b["absmax"], abs(d["diff"]))
        if d["diff"] > 0:
            b["pos"] += 1
        elif d["diff"] < 0:
            b["neg"] += 1
        else:
            b["zero"] += 1
    return agg


def untraceable(diffs, cells):
    """列出"计数型 KPI 变化达到阈值、但该 seed 的 planned 面没有任何绕障候选腿"的格子。

    ⚠ 这道门【只】排除"机制通道完全不存在"这一种归因断链：deltas 非空是恒真前提，
    它能证伪"没有 planner 参与却变了"，但**不能证明**变化就是这些翻转造成的。
    逐事件归因（首分歧步 + 分叉后各自跑到结束）在 console/phase1b1_attribution_trace.py；
    把本门的"通过"读成"已追溯"是高估，报告里必须区分这两层。
    """
    bad = []

    for d in diffs:
        if d["kpi"] not in COUNT_KPI or abs(d["diff"]) < UNTRACEABLE_TASK_THRESHOLD:
            continue
        key = (d["fixture"], d["algorithm"], d["seed"], "planned_distance",
               d.get("weight", 0.0))
        if key not in cells:      # 旧格式（无 weight 维）兼容
            key = (d["fixture"], d["algorithm"], d["seed"], "planned_distance")
        ev = (cells[key].get("_evidence") or {})
        if not ev.get("deltas"):
            bad.append("%s/%s seed=%d %s Δ=%.1f 但该 seed planner 未给出任何绕障候选腿"
                       % (d["fixture"], d["algorithm"], d["seed"], d["kpi"], d["diff"]))
    return bad


def write_report(out_path, seeds=SEEDS, algorithms=ALGOS, steps=EPISODE_STEPS,
                 weights=(0.0,), title="Phase 1B-1  Euclidean vs PlannedDistance  配对实验"):
    """跑满配对实验并把逐 seed 差分、符号汇总、追溯门写成文本报告。"""
    wd = pathlib.Path(tempfile.mkdtemp(prefix="p1b1_"))
    lines = []
    try:
        rows, cells, _ = collect(seeds=seeds, algorithms=algorithms, steps=steps,
                                 workdir=str(wd), weights=weights)
        diffs = paired_diffs(rows)
        bad = untraceable(diffs, cells)
        lines.append(title)
        lines.append("seeds=%s algorithms=%s episode_steps=%d reach_weights=%s"
                     % (list(seeds), list(algorithms), steps, list(weights)))
        lines.append("")
        lines.append("== 逐 seed 配对差分（planned - euclid）==")
        for d in sorted(diffs, key=lambda x: (x["fixture"], x["algorithm"], x["seed"], x["kpi"])):
            mark = "  <== Δ" if abs(d["diff"]) > 1e-12 else ""
            lines.append("%s %-6s seed=%d w=%-4s %-12s %14.6f -> %14.6f Δ=%12.6g%s"
                         % (d["fixture"], d["algorithm"], d["seed"], d.get("weight", 0.0),
                            d["kpi"], d["euclid"], d["planned"], d["diff"], mark))
        lines.append("")
        lines.append("== 符号汇总（每格 n=%d，样本太小不做显著性宣称）==" % len(seeds))
        for (fx, alg, kpi, w), b in sorted(sign_summary(diffs).items()):
            lines.append("%s %-6s w=%-4s %-12s pos=%d neg=%d zero=%d absmax=%.6g"
                         % (fx, alg, w, kpi, b["pos"], b["neg"], b["zero"], b["absmax"]))
        lines.append("")
        lines.append("== 实验面 provider 证人 ==")
        for key, res in sorted(cells.items(), key=lambda kv: str(kv[0])):
            if res["_provider_requested"] != "planned_distance":
                continue
            key = list(key)
            ev = res["_evidence"] or {}
            st = dict(ev.get("stats", {}))
            st["no_fly_detours"] = ev.get("total_no_fly_detours")
            ratios = [d["ratio"] for d in ev.get("deltas", [])]
            st["max_ratio"] = round(max(ratios), 4) if ratios else None
            lines.append("%s %s seed=%s w=%s -> %s" % (key[0], key[1], key[2], key[4], st))
        lines.append("")
        lines.append("== 追溯门（|Δ任务数| >= %g 且该 seed 无绕障候选腿 ⇒ 归因断链）=="
                     % UNTRACEABLE_TASK_THRESHOLD)
        lines.extend(bad or ["无：所有需追溯的格子都有该 seed 的绕障候选腿证人"])
    finally:
        shutil.rmtree(wd, ignore_errors=True)
    text = "\n".join(lines) + "\n"
    pathlib.Path(out_path).write_text(text, encoding="utf-8")
    print(text)
    return len(bad)


def determinism_control(cells, fixtures=("C1", "C2"), seeds=SEEDS, algorithms=("greedy",),
                        workdir=None):
    """同 provider 复跑一次：证明"两面之差"只可能由切换引起，而不是运行间噪声。

    为什么必须有这一步：H1 说"变化 ≥ 2 单任务必须追溯到具体翻转"。若同 seed 同配置的
    两次运行本身就会差 n 个任务，那任何差分都能被噪声解释，追溯是空话。
    本控制面把噪声上限测出来（理想为 0），之后所有 Δ 才有资格归因给 provider。
    """
    wd = pathlib.Path(workdir) if workdir else pathlib.Path(tempfile.mkdtemp(prefix="p1b1_det_"))
    rows = []
    for fx in fixtures:
        for alg in algorithms:
            for sd in seeds:
                for pv in PROVIDERS:
                    res = run_cell(fx, sd, pv, alg, wd)
                    base = cells.get((fx, alg, sd, pv))
                    m = res["metrics"]
                    b = base["metrics"] if base else {}
                    for k in CORE_KPI:
                        rows.append(dict(fixture=fx, algorithm=alg, seed=sd, provider=pv,
                                         kpi=k, value=float(m[k]),
                                         drift=float(m[k]) - float(b.get(k, m[k]))))
    if workdir is None:
        shutil.rmtree(wd, ignore_errors=True)
    return rows


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else None
    if out is None:
        raise SystemExit("用法：python console/phase1b1_experiment.py <报告输出路径> "
                         "[seeds 逗号分隔] [algorithms 逗号分隔]\n"
                         "门与断言见 console/test_phase1b1_distance_experiment.py")
    seeds = tuple(int(x) for x in sys.argv[2].split(",")) if len(sys.argv) > 2 else SEEDS
    algs = tuple(sys.argv[3].split(",")) if len(sys.argv) > 3 else ALGOS
    wts = tuple(float(x) for x in sys.argv[4].split(",")) if len(sys.argv) > 4 else (0.0,)
    raise SystemExit(1 if write_report(pathlib.Path(out), seeds=seeds, algorithms=algs,
                                       weights=wts) else 0)

