# -*- coding: utf-8 -*-
"""G11 探针：REACH_WEIGHT=0 时的打分必须与"没有 reachability 分量"的原式逐位相同。

对照物**不是** _score_task 自己（那变成新实现和自己比，门没牙），而是把 1B-1 之前那一行
`MATCH_WEIGHT*match + DISTANCE_WEIGHT*proximity` 在这里就地重写一遍。

走子进程的理由：REACH_WEIGHT 在 greedy/scheduler.py import 期冻结（模块常量），
同进程改环境变量不会生效 —— 与 1B-1 的 provider 注入同一个套路数。
"""
import json
import os
import pathlib
import shutil
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
# 与 worker/runner 同法：仓库根 + frontend 都要在 path 上。只插 frontend 会让
# environment.py 内部的 `from config.config_loder import ...` 找不到包（本轮实测 ImportError）。
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "frontend"))

OSM = REPO / "frontend" / "data" / "map" / "part_of_yangpu.osm"


def main():
    cfg = json.loads((REPO / "config" / "simulation.json").read_text(encoding="utf-8"))
    cfg["task_generation"]["realistic"].update({"interval_scale": 0.70, "total_tasks": 240})
    cfg["environment"]["num_drones"] = 6
    cfg["heterogeneous"]["fleet_mix"] = {"light_express": 3, "standard_cargo": 2, "heavy_cargo": 1}
    wd = pathlib.Path(tempfile.mkdtemp(prefix="p2equiv_"))
    f = wd / "s.json"
    f.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(f)
    os.environ.pop("SWARM_BALANCE_REACH_WEIGHT", None)     # 干净进程 ⇒ 默认权重
    try:
        from environment import Environment
        from matching import compute_match
        from greedy.scheduler import (GreedyScheduler as GS, MATCH_WEIGHT, DISTANCE_WEIGHT,
                                      VOLUME_TO_LOAD_FACTOR, REACH_WEIGHT)
        from route_cost import PlannedDistanceRouteCostProvider, EuclideanRouteCostProvider

        print("DEFAULT_W=%r" % REACH_WEIGHT)
        env = Environment(str(OSM), episode_max_steps=3600)
        o = env.reset(seed=40901)
        un = [t for t in o["unassigned_tasks"] if not str(t.get("task_id", "")).startswith("__pad_")]
        bad = 0
        n = 0
        for name, prov in (("euclidean", EuclideanRouteCostProvider()),
                           ("planned", PlannedDistanceRouteCostProvider(env.route_planner))):
            for d_idx in range(len(env.drones)):
                cap = o["drone_capabilities"][d_idx]
                pos = tuple(o["drone_positions"][d_idx])
                cand = [t for t in un[:60] if GS._is_feasible(cap, t)]
                dists = prov.batch(pos, [tuple(t["source"]) for t in cand])
                mn, mx = min(dists), max(dists)
                dm = dict(zip([t["task_id"] for t in cand], dists))
                for t in cand:
                    prox = 1.0 if mx <= mn else 1.0 - (dm[t["task_id"]] - mn) / (mx - mn)
                    got = GS._score_task(cap, pos, t, prox, provider=prov, reach_weight=0.0)
                    # ↓ 1B-1 之前的原式，就地重写，不调用被测函数
                    rt = t.get("remaining_time", float("inf"))
                    td = prov.distance(pos, tuple(t["source"])) + \
                        prov.distance(tuple(t["source"]), tuple(t["destination"]))
                    rl = float(t.get("weight", 0.0)) + VOLUME_TO_LOAD_FACTOR * float(t.get("volume", 0.0))
                    exp = MATCH_WEIGHT * compute_match(
                        rl, float(cap.get("remaining_capacity", 1.0)),
                        float(cap.get("speed", 200.0)), rt,
                        float(cap.get("battery_capacity", 15000.0)),
                        float(cap.get("battery_consumption_base", 0.5)), td) + DISTANCE_WEIGHT * prox
                    n += 1
                    if abs(got - exp) > 1e-12:
                        bad += 1
                        if bad <= 3:
                            print("  MISMATCH %s/%s %s got=%.9f exp=%.9f" % (name, d_idx, t["task_id"], got, exp))
        print("N=%d EQUIV_BAD=%d" % (n, bad))
        return 0 if (n > 0 and bad == 0) else 1
    finally:
        shutil.rmtree(wd, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
