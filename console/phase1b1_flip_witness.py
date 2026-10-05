# -*- coding: utf-8 -*-
"""Phase 1B-1 追溯证人：同一候选集上，两种距离口径各自会选谁（H1 的"具体一次翻转"）。

为什么单独一个探针而不是只靠 KPI 差分：KPI 只告诉我们"变了几个任务"，而 H1 要求的是
**哪一步、哪一个 drone、哪个候选集、从谁翻到谁**。这个探针把 Greedy 的决策函数
（frontend/greedy/scheduler.py:105-135）在【同一份真实候选集】上按两种 provider 各跑一遍，
直接产出翻转事件。它不改变任何仿真行为 —— 只是重放打分。

与 1B-0 的关系：1B-0 用"drone->pickup 最短"近似排序判据，得到 7/10676 = 0.07%；
本探针用的是 Greedy **真正的评分函数**（MATCH_WEIGHT*match + DISTANCE_WEIGHT*proximity，
且 proximity 在候选集内归一化 ⇒ 依赖整组距离），所以它是更严的证人。两者数字不同是正常的，
报告里要同时给出并说明口径差异。

注意 GA 面：后端优化器零引用 route_cost_provider（test G5），所以 GA 的两面在这里必然
一条翻转都数不出来 —— 数不出就是阴性对照成立；若数出来，说明有第二条通路，须先查机制。
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "frontend"))

OSM = REPO / "frontend" / "data" / "map" / "part_of_yangpu.osm"
FIXTURES = {
    "C1": {"task_generation": {"realistic": {"interval_scale": 0.70, "total_tasks": 240}},
           "environment": {"num_drones": 6},
           "heterogeneous": {"fleet_mix": {"light_express": 3, "standard_cargo": 2, "heavy_cargo": 1}}},
    "C2": {"task_generation": {"realistic": {"interval_scale": 0.55, "total_tasks": 240}},
           "environment": {"num_drones": 4},
           "heterogeneous": {"fleet_mix": {"light_express": 2, "standard_cargo": 1, "heavy_cargo": 1}}},
}


def _merge(base, patch):
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def _score(GS, cap, pos, task, prox, provider):
    """GreedyScheduler._score_task 的重放；provider=None 走原欧氏分支。"""
    return GS._score_task(cap, pos, task, prox, provider=provider)


def scan(fixture: str, seed: int):
    """跑一个 episode，在每次派单机会上重放两种口径的 argmax。"""
    import environment as em
    from greedy.scheduler import GreedyScheduler as GS, greedy_action_from_observation
    from route_cost import EuclideanRouteCostProvider, PlannedDistanceRouteCostProvider
    from greedy import scheduler as gs_mod

    # 【量具缺陷 f】两面必须各用【独立】的 provider 实例：PlannedDistanceRouteCostProvider
    # 自带 _cache，若把同一个实例先后喂给欧氏面和绕障面，第二面会全量命中第一面的缓存 ⇒
    # 两"面"其实是同一组数 ⇒ 恒不翻转 ⇒ flips=0 是【构造出来的 0】，不是测量结果。
    # 本轮实测：C1 seed=40902 正式实验 Δ完成任务数=+4，而旧写法在这里数到 0 翻转 ——
    # 一个解释不了变化的证人比没有证人更坏，因为它会让"追不到"被读成"变化不存在"。

    cfg = json.loads((REPO / "config" / "simulation.json").read_text(encoding="utf-8"))
    _merge(cfg, FIXTURES[fixture])
    wd = pathlib.Path(tempfile.mkdtemp(prefix="p1b1flip_"))
    cfgf = wd / "sim.json"
    cfgf.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    old = os.environ.get("SWARM_BALANCE_SIM_CONFIG")
    os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(cfgf)
    groups = flips = 0
    flip_events = []
    try:
        env = em.Environment(str(OSM), episode_max_steps=3600)
        obs = env.reset(seed=seed)
        # 两面各一个【独立】实例：共享 _cache 会让第二面全量命中第一面 ⇒ 恒不翻转
        plan = PlannedDistanceRouteCostProvider(env.route_planner)
        limit = max(1, gs_mod.CANDIDATE_LIMIT)
        steps, done = 0, False
        while not done and steps < 3600:
            action = greedy_action_from_observation(obs)
            un = [t for t in obs["unassigned_tasks"] if not str(t.get("task_id", "")).startswith("__pad_")]
            caps = obs["drone_capabilities"]
            for d_idx, dpos in enumerate(obs["drone_positions"]):
                if not obs["drone_is_free"][d_idx]:
                    continue
                cap = caps[d_idx] if d_idx < len(caps) else {}
                cand = [t for t in un[:limit] if GS._is_feasible(cap, t)]
                if len(cand) < 2:
                    continue
                pos = tuple(dpos)
                groups += 1

                def argmax(provider=None):
                    # provider=None ⇒ 走生产对照分支（纯欧氏）；传入实例 ⇒ 走该面的距离口径。
                    # 两面【绝不共享】provider：PlannedDistanceRouteCostProvider 自带 _cache，
                    # 共享会让第二面全量命中第一面的缓存 ⇒ 恒不翻转（缺陷 f）。
                    if provider is None:
                        dists = [GS.euclidean_distance(pos, tuple(t["source"])) for t in cand]
                    else:
                        dists = provider.batch(pos, [tuple(t["source"]) for t in cand])
                    mn, mx = min(dists), max(dists)
                    prox = (lambda d: 1.0 if mx <= mn else 1.0 - (d - mn) / (mx - mn))
                    dm = dict(zip([t["task_id"] for t in cand], dists))
                    scored = [(-GS.euclidean_distance(pos, tuple(t["source"]))
                                if not cap or cap.get("drone_type") is None
                                else _score(GS, cap, pos, t, prox(dm[t["task_id"]]), provider=provider),
                                t["task_id"]) for t in cand]
                    best = max(scored)[1]
                    return best, {tid: s for s, tid in scored}

                b_e, sc_e = argmax(None)      # 对照面：不经过任何带缓存的实例
                b_p, sc_p = argmax(plan)      # 实验面：独立 PlannedDistance 实例
                if b_e != b_p:
                    flips += 1
                    if len(flip_events) < 40:
                        flip_events.append(dict(step=steps, drone=d_idx, n=len(cand),
                                                euclid_pick=b_e, planned_pick=b_p,
                                                score_gap_euclid=round(max(sc_e.values()) - sorted(sc_e.values())[-2], 6),
                                                score_gap_planned=round(max(sc_p.values()) - sorted(sc_p.values())[-2], 6)))
            obs, _, done, _ = env.step(action)
            steps += 1
        stats = dict(fixture=fixture, seed=seed, steps=steps, groups=groups, flips=flips,
                     planned_calls=plan.calls, planned_unique_od=plan.stats()["unique_od"],
                     planned_deltas=len(plan.deltas),
                     max_ratio=max([d["ratio"] for d in plan.deltas] or [0.0]))
        return stats, flip_events
    finally:
        if old is None:
            os.environ.pop("SWARM_BALANCE_SIM_CONFIG", None)
        else:
            os.environ["SWARM_BALANCE_SIM_CONFIG"] = old
        shutil.rmtree(wd, ignore_errors=True)


if __name__ == "__main__":
    seeds = [int(x) for x in (sys.argv[1:] or ["40901", "40902", "40903"])]
    total_g = total_f = 0
    events_all = []
    for fx in ("C1", "C2"):
        for sd in seeds:
            st, ev = scan(fx, sd)
            total_g += st["groups"]
            total_f += st["flips"]
            for e in ev:
                e["fixture"], e["seed"] = fx, sd
            events_all += ev
            print("[flip] %s seed=%d 候选组=%d 翻转=%d planner调用=%d 唯一OD=%d "
                  "绕障腿=%d 最大ratio=%.4f" % (fx, sd, st["groups"], st["flips"],
                                              st["planned_calls"], st["planned_unique_od"],
                                              st["planned_deltas"], st["max_ratio"]), flush=True)
    print("\n合计：候选组=%d 翻转=%d 翻转率=%.4f%%" % (total_g, total_f,
          100.0 * total_f / total_g if total_g else 0.0))
    for e in events_all[:20]:
        print("  %s seed=%d step=%d drone=%d n=%d euclid选=%s planned选=%s "
              "分差(e)=%.6f 分差(p)=%.6f" % (e["fixture"], e["seed"], e["step"], e["drone"],
              e["n"], e["euclid_pick"], e["planned_pick"],
              e["score_gap_euclid"], e["score_gap_planned"]))
