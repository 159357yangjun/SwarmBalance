# -*- coding: utf-8 -*-
"""Phase 1A 前置诊断：GA/PSO objective 各组成项【加权后】的真实贡献占比。

为什么必须有它：我曾把系数之比（w_dist 0.01 : w_tardy 2.0）当成贡献之比，据此写过
"里程项只占超时项的 1/200 ⇒ 路线口径分裂对 GA/PSO 不承重"。那是错的 —— 两项量纲与数值
尺度不同：distance 是米级（数千），tardiness 是秒级但可能只有几十。0.01×3000=30 与
2.0×20=40 已经同量级。所以那句话必须由实测替换。

做法：monkeypatch backend_si.chain_codec.chain_cost 为记录版（**返回值逐字不变**），
走 experiments/worker.py 的真实调用链跑 C-1/C-2 × GA/PSO，累加每次调用的各加权项。
只读诊断：不改权重、不改算法、不改任何返回值，也不落 results/ 目录。

判据写法（避免又得出一个形容词结论）：
  占比 < 5%   ⇒ 距离项对当前目标函数属次要；
  5% ~ 20%    ⇒ 如实报"中等"，不硬贴标签；
  ≥ 20%       ⇒ 属核心项，Phase 1B 的收益预期相应上调。
分母（chain_cost 调用次数 n）必须一起打印；n=0 时本条读数作废并明说，不得沉默通过。
"""
from __future__ import annotations

import inspect
import os
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "frontend"))

TERMS = [("makespan", "w_makespan"), ("total_tardiness", "w_tardy"),
         ("total_distance", "w_dist"), ("unassigned", "w_unassigned"),
         ("total_match_score", "w_match")]
CAP = 200000          # 采样上限护栏：长 run 下不让探针自己吃爆内存



def _deep(base: dict, patch: dict) -> dict:
    """与 experiments.runner._deep_merge 同语义（dict 递归、其余整体替换）。"""
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep(base[k], v)
        else:
            base[k] = v
    return base


def _fixture_patch(label: str) -> dict:
    """与 e0_baseline / S1 / S2 同一份 fixture 定义，保证可比。"""
    if label == "C1":
        return {"task_generation": {"realistic": {"interval_scale": 0.70, "total_tasks": 240}},
                "environment": {"num_drones": 6},
                "heterogeneous": {"fleet_mix": {"light_express": 3, "standard_cargo": 2, "heavy_cargo": 1}}}
    return {"task_generation": {"realistic": {"interval_scale": 0.55, "total_tasks": 240}},
            "environment": {"num_drones": 4},
            "heterogeneous": {"fleet_mix": {"light_express": 2, "standard_cargo": 1, "heavy_cargo": 1}}}


def measure(algorithm: str, fixture: str, seed: int) -> dict:
    """跑一次真实优化，返回 {term: (mean, max, share)}、n、以及是否触及采样上限。"""
    from backend_si import chain_codec
    import experiments.worker as worker

    original = chain_codec.chain_cost
    sig = inspect.signature(original)
    samples = {k: [] for k, _ in TERMS}
    totals = []
    truncated = [False]

    def spy(metrics, **kw):
        got = original(metrics, **kw)          # 返回值原样透传 ⇒ 行为零改变
        eff = {}
        for key, wname in TERMS:
            w = kw.get(wname, sig.parameters[wname].default)
            eff[key] = float(w) * float(metrics.get(key, 0.0) or 0.0)
        if len(totals) < CAP:
            for k, v in eff.items():
                samples[k].append(v)
            totals.append(got)
        else:
            truncated[0] = True
        return got

    # 真实入口：run_one(config_path, algorithm, seed, episode_steps, osm_path)
    # 它自己会把 SWARM_BALANCE_SIM_CONFIG 指向 config_path ⇒ fixture 必须先落到临时配置文件。
    import json
    import tempfile
    cfg = json.loads((REPO / "config" / "simulation.json").read_text(encoding="utf-8"))
    _deep(cfg, _fixture_patch(fixture))
    tmpd = tempfile.mkdtemp(prefix="objterm_")
    cfg_file = pathlib.Path(tmpd) / "sim.json"
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    osm = REPO / "frontend" / "data" / "map" / "part_of_yangpu.osm"
    chain_codec.chain_cost = spy
    try:
        res = worker.run_one(cfg_file, algorithm, int(seed), 3600, osm)
    finally:
        chain_codec.chain_cost = original
        for f in cfg_file.parent.glob("*"):
            f.unlink(missing_ok=True)
        os.rmdir(tmpd)
    n = len(totals)
    out = {"n": n, "truncated": truncated[0], "share": {}, "worker_ok": bool(res.get("ok")),
           "optimize_calls": (res.get("scheduler_stats") or {}).get("optimize_calls")}
    if n == 0:
        return out
    denom = sum(abs(x) for k in samples for x in samples[k]) or 1.0
    for k, _wn in TERMS:
        arr = samples[k]
        out["share"][k] = (sum(arr) / n, max(arr) if arr else 0.0,
                           sum(abs(x) for x in arr) / denom)
    out["cost_mean"] = sum(totals) / n
    return out


def report():
    print("=" * 78)
    print("Objective term decomposition（加权后实际贡献）— 只读诊断，不改行为")
    print("真源 backend_si/chain_codec.py:477-490；权重 config.yaml:124-126")
    print("=" * 78)
    rows = []
    for alg in ("ga", "pso"):
        for fx in ("C1", "C2"):
            try:
                r = measure(alg, fx, 40901)
            except SystemExit:
                raise
            except Exception as e:
                print(f"\n[{alg} × {fx}] 探针未能运行：{type(e).__name__}: {e}")
                print("  ⇒ 该格无读数，不得用别处的数代替")
                continue
            print(f"\n[{alg} × {fx}] chain_cost 调用次数 n={r['n']} "
                  f"worker_ok={r['worker_ok']} optimize_calls={r.get('optimize_calls')}"
                  + ("  ⚠ 采样已达上限被截断" if r["truncated"] else ""))
            if r["n"] == 0:
                print("  [NO_CALLS] 优化器一次都没被调用 ⇒ 无法归因，本格作废")
                continue
            for key, wn in TERMS:
                mean, mx, share = r["share"][key]
                print(f"  {wn:>13} × {key:<17} mean={mean:>12.3f} max={mx:>12.3f} "
                      f"占比={share*100:5.1f}%")
                if key == "total_distance":
                    rows.append((alg, fx, share))
            print(f"  cost mean={r.get('cost_mean', float('nan')):.3f}")
    print("\n" + "=" * 78)
    print("判读（阈值来自本文档头，先写下再看数）")
    for alg, fx, share in rows:
        tag = "次要(<5%)" if share < 0.05 else ("核心(>=20%)" if share >= 0.20 else "中等(5~20%)")
        print(f"  {alg} × {fx}: w_dist*total_distance 占总绝对贡献 {share*100:.1f}% ⇒ {tag}")
    if not rows:
        print("  无任何有效格 ⇒ 本轮没有结论，需要先把探针接进真实调用链")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(report())
