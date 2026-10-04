# -*- coding: utf-8 -*-
"""Phase 1B-0：Route discrepancy profiling —— 量 Euclidean 与 RoutePlanner 的真实分歧。

**本轮是诊断，不改调度行为。** 目的不是"平均多绕了 x%"，而是回答一个更值钱的问题：

    会不会因为距离口径不同而【选错无人机】？

用户给的例子即本门的核心指标：
    Drone A: Euclidean 1.8km, Route 3.5km
    Drone B: Euclidean 2.1km, Route 2.4km
    ⇒ 欧氏模型选 A，航路感知模型选 B。这叫 candidate/ranking inversion。

为什么占比不能替代它（我在 Phase 1A 报告里犯的错，已在 §7/§8 撤回）：
GA objective 里 distance 项的直接贡献只有 C-1 8.4% / C-2 1.0%，但一次分配翻转经
任务链 → makespan → tardiness → feasibility → unassigned 是离散放大，1% 也能造成大变化；
反之若绝大多数 OD 对本来就 is_path_clear 直达，两种成本完全相同，改了就等于没改。
⇒ 所以先量分歧本身。

统计对象严格对齐真实消费点（不自己发明口径）：
  Greedy 的选择实际只看 euclidean(drone_pos -> task.source)（greedy/scheduler.py:130），
  route_distance 只进 _score_task 的匹配项（:172）。因此本探针同时量两类 OD：
    leg "drone->pickup"  —— Greedy 真正用来排序的那一段
    leg "pickup->delivery" —— 环境执行侧必然经过的一段（task.py:543 也算这条的直线）
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "frontend"))

OSM = REPO / "frontend" / "data" / "map" / "part_of_yangpu.osm"
FIXTURES = {
    # 与 e0_baseline / S1 / S2 同一份 fixture 定义
    "C1": {"task_generation": {"realistic": {"interval_scale": 0.70, "total_tasks": 240}},
           "environment": {"num_drones": 6},
           "heterogeneous": {"fleet_mix": {"light_express": 3, "standard_cargo": 2, "heavy_cargo": 1}}},
    "C2": {"task_generation": {"realistic": {"interval_scale": 0.55, "total_tasks": 240}},
           "environment": {"num_drones": 4},
           "heterogeneous": {"fleet_mix": {"light_express": 2, "standard_cargo": 1, "heavy_cargo": 1}}},
}


def _pct(sorted_vals, q):
    if not sorted_vals:
        return float("nan")
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def _merge(base: dict, patch: dict) -> dict:
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def collect(fixture: str, seed: int):
    """跑一次真实 episode，在每次派单时刻记录该 drone 的全部候选任务的两种距离。"""
    import environment as env_mod
    from route_planner import RoutePlanner, RouteRequest
    from greedy.scheduler import GreedyScheduler, greedy_action_from_observation

    cfg = json.loads((REPO / "config" / "simulation.json").read_text(encoding="utf-8"))
    _merge(cfg, FIXTURES[fixture])
    tmp = tempfile.mkdtemp(prefix="routedis_")
    cfg_file = pathlib.Path(tmp) / "sim.json"
    cfg_file.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    old_env = os.environ.get("SWARM_BALANCE_SIM_CONFIG")
    os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(cfg_file)

    legs = []          # 每条：fixture/seed/leg/euclid/route/detour/direct/fallback
    pairs = []         # 候选对层面的 ranking inversion 记录
    try:
        env = env_mod.Environment(str(OSM), episode_max_steps=3600)
        obs = env.reset(seed=seed)
        planner = RoutePlanner(high_buildings=env.high_buildings, no_fly=env.no_fly,
                               path_clear=env.is_path_clear, warn=lambda _m: None)

        def measure_leg(a, b, leg):
            e = GreedyScheduler.euclidean_distance(a, b)
            r = planner.plan(RouteRequest(start=(float(a[0]), float(a[1])),
                                          goal=(float(b[0]), float(b[1]))))
            route_len = e if r.direct else _polyline(a, r.as_list())
            rec = dict(fixture=fixture, seed=seed, leg=leg, euclid=e, route=route_len,
                       direct=bool(r.direct), fallback=bool(r.fallback), detour=bool(r.detour),
                       ratio=(route_len / e) if e > 1e-9 else float("nan"))
            legs.append(rec)
            return rec

        steps = 0
        done = False
        while not done and steps < 3600:
            action = greedy_action_from_observation(obs)
            # 复现 Greedy 真正的候选枚举（scheduler.py:96-107）：取前 candidate_limit 个未分配
            # 任务，再按载重硬过滤 —— 这才是参与排序的集合。action 只含已选中的那一个任务，
            # 不能用它当候选集（第一版就是这么错的，结果 groups=0）。
            from greedy import scheduler as gsched
            limit = max(1, gsched.CANDIDATE_LIMIT)
            un = obs["unassigned_tasks"]
            caps = obs["drone_capabilities"]
            for d_idx, drone_pos in enumerate(obs["drone_positions"]):
                if not obs["drone_is_free"][d_idx]:
                    continue
                cap = caps[d_idx] if d_idx < len(caps) else {}
                cand = [t for t in un[:limit] if GreedyScheduler._is_feasible(cap, t)]
                if len(cand) < 2:
                    continue
                pos = tuple(drone_pos)
                scored = []
                for t in cand:
                    src, dst = tuple(t["source"]), tuple(t["destination"])
                    l1 = measure_leg(pos, src, "drone->pickup")
                    l2 = measure_leg(src, dst, "pickup->delivery")
                    scored.append(dict(task_id=t["task_id"], e_pickup=l1["euclid"],
                                       r_pickup=l1["route"], e_leg=l2["euclid"], r_leg=l2["route"]))
                by_e = min(scored, key=lambda x: x["e_pickup"])["task_id"]
                by_r = min(scored, key=lambda x: x["r_pickup"])["task_id"]
                pairs.append(dict(fixture=fixture, seed=seed, drone_idx=d_idx, n=len(scored),
                                  pick_euclid_best=by_e, pick_route_best=by_r, inverted=(by_e != by_r)))
            obs, _, done, _ = env.step(action)
            steps += 1
    finally:
        if old_env is None:
            os.environ.pop("SWARM_BALANCE_SIM_CONFIG", None)
        else:
            os.environ["SWARM_BALANCE_SIM_CONFIG"] = old_env
        for f in pathlib.Path(tmp).glob("*"):
            f.unlink(missing_ok=True)
        os.rmdir(tmp)
    return legs, pairs, steps


def _polyline(start, pts):
    total = 0.0
    prev = (float(start[0]), float(start[1]))
    for p in pts:
        total += ((float(p[0]) - prev[0]) ** 2 + (float(p[1]) - prev[1]) ** 2) ** 0.5
        prev = (float(p[0]), float(p[1]))
    return total


def report(seeds=(40901, 40902, 40903)):
    all_legs, all_pairs = [], []
    for fx in ("C1", "C2"):
        for sd in seeds:
            print(f"[run] {fx} seed={sd} ...", flush=True)
            legs, pairs, steps = collect(fx, sd)
            print(f"      steps={steps} legs={len(legs)} candidate-groups={len(pairs)}")
            all_legs += legs
            all_pairs += pairs

    print("\n" + "=" * 78)
    print("Phase 1B-0  Route discrepancy profiling（诊断，不改行为）")
    print("=" * 78)
    for fx in ("C1", "C2"):
        for leg in ("drone->pickup", "pickup->delivery"):
            rs = [l["ratio"] for l in all_legs
                  if l["fixture"] == fx and l["leg"] == leg and l["ratio"] == l["ratio"]]
            if not rs:
                print(f"{fx} {leg:<18} 无有效读数")
                continue
            srt = sorted(rs)
            sub = [l for l in all_legs if l["fixture"] == fx and l["leg"] == leg]
            # 分母必须是本 (fixture, leg) 的子集：第一版误用了全体 legs 的 n，
            # 于是 pickup->delivery 这种少数量的 leg 会算出 >100% 的"直达率"。
            nd = sum(1 for l in sub if l["direct"])
            nt = sum(1 for l in sub if not l["direct"])
            nf = sum(1 for l in sub if l["fallback"])
            det = [r for r in rs if r > 1.0001]
            mean_det = sum(det) / len(det) if det else 1.0
            d = len(sub) or 1          # 分母 = 本 (fixture, leg) 的全部读数，不是过滤后的 rs
            print(f"\n{fx} {leg:<18} n={d:>6} 直达={nd/d*100:5.1f}% "
                  f"绕障={nt/d*100:5.1f}% 兜底={nf/d*100:4.1f}%"
                  + (f"  ⚠ {len(rs)} 条 ratio 非有限值被排除于分位统计" if len(rs) != d else ""))
            print(f"   ratio mean={sum(rs)/len(rs):.4f}  P50={_pct(srt,.5):.4f} "
                  f"P90={_pct(srt,.9):.4f}  P95={_pct(srt,.95):.4f}  max={max(rs):.4f}")
            print(f"   仅绕障子集(n={len(det)}) mean={mean_det:.4f} "
                  f"P90={_pct(sorted(det),.9) if det else float('nan'):.4f}")

    inv = [p for p in all_pairs if p["inverted"]]
    print("\n" + "-" * 78)
    print("★ Ranking inversion（会真正改变分配的那个量）")
    print(f"   候选组总数={len(all_pairs)}  发生翻转={len(inv)}  "
          f"比例={(len(inv)/len(all_pairs)*100) if all_pairs else float('nan'):.2f}%")
    for fx in ("C1", "C2"):
        g = [p for p in all_pairs if p["fixture"] == fx]
        gi = [p for p in g if p["inverted"]]
        print(f"   {fx}: 组数={len(g)} 翻转={len(gi)} 比例="
              f"{(len(gi)/len(g)*100) if g else float('nan'):.2f}%")
    # 哪些任务最容易当"被误选者"
    loser = {}
    for p in inv:
        loser[p["pick_euclid_best"]] = loser.get(p["pick_euclid_best"], 0) + 1
    top = sorted(loser.items(), key=lambda kv: -kv[1])[:10]
    print(f"   最常被欧氏模型误选的任务(task_id:次数)：{top}")
    sizes = {}
    for p in all_pairs:
        sizes[p["n"]] = sizes.get(p["n"], 0) + 1
    print(f"   候选集大小分布 n→组数：{dict(sorted(sizes.items()))}")
    print("\n注：候选集大小分布决定翻转可能性上限 —— 若绝大多数组 n=1，则不存在可翻转的对。")
    return 0


if __name__ == "__main__":
    raise SystemExit(report())
