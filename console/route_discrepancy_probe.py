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
    degenerate = [0]   # source==destination 的退化 OD 计数（ratio 无定义，不进分位数）
    seen_od = set()    # pickup->delivery 是任务的静态属性，只测一次；逐步重复测量会把
                       # 同一个 task 计几十次，既虚增样本又把零长度 OD 放大成假 NaN 潮
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
            if e <= 1e-9:
                # 退化对（机位==取货点，或 source==destination）：ratio 无定义。
                # 单独计数并从 ratio 分位统计里排除 —— 第一版把它们写成 NaN 混进列表，
                # 于是 drone->pickup 那一行会显示"48.8 万条非有限值"，看着像量具崩了，
                # 其实是无人机起飞即在该任务取货点上这类正常情形。
                degenerate[0] += 1
                rec0 = dict(fixture=fixture, seed=seed, leg=leg, euclid=e, route=e,
                            direct=True, fallback=False, detour=False, ratio=float("nan"),
                            degenerate=True)
                legs.append(rec0)
                return rec0
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
            # 必须先剔 __pad_ 再截断，顺序与 Greedy 一致（scheduler.py:45-48 先过滤 padding、
            # :98 才 [:candidate_limit]）。environment.py:1591-1614 是【截断之后】才补 padding，
            # 所以 obs[:60] 的尾部恒为占位任务；直接对 un[:limit] 取候选会让探针看到的集合
            # 比真实参与排序的多出占位、又少掉真任务 —— 实测本探针因此把候选集截到约 42 个
            # 真任务之外还数进了 (0,0) 坐标的假腿，翻转率被系统性低估。
            un = [t for t in obs["unassigned_tasks"]
                  if not str(t.get("task_id", "")).startswith("__pad_")]
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
                    # 排序判据只依赖 drone->pickup（Greedy 真正用的那一段），
                    # 所以先把候选填进来，再决定要不要测静态 OD —— 否则去重会把 scored 掏空。
                    scored.append(dict(task_id=t["task_id"], e_pickup=l1["euclid"],
                                       r_pickup=l1["route"], e_leg=None, r_leg=None))
                    key = (fixture, seed, t["task_id"])
                    if key in seen_od:
                        continue
                    if tuple(src) == tuple(dst):
                        degenerate[0] += 1        # ratio 无定义，不进分位数统计
                        continue
                    seen_od.add(key)
                    l2 = measure_leg(src, dst, "pickup->delivery")
                    scored[-1]["e_leg"] = l2["euclid"]
                    scored[-1]["r_leg"] = l2["route"]
                if len(scored) < 2:
                    continue
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
    return legs, pairs, steps, degenerate[0], len(seen_od)


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
            legs, pairs, steps, degen, n_od = collect(fx, sd)
            print(f"      steps={steps} 排序腿={len([l for l in legs if l['leg']=='drone->pickup'])} "
                  f"唯一OD={n_od} 候选组={len(pairs)} 退化OD(source==dest)={degen}")
            all_legs += legs
            all_pairs += pairs

    print("\n" + "=" * 78)
    print("Phase 1B-0  Route discrepancy profiling（诊断，不改行为）")
    print("=" * 78)
    for fx in ("C1", "C2"):
        for leg in ("drone->pickup", "pickup->delivery"):
            rs = [l["ratio"] for l in all_legs
                  if l["fixture"] == fx and l["leg"] == leg and l["ratio"] == l["ratio"]]
            ndeg = sum(1 for l in all_legs
                       if l["fixture"] == fx and l["leg"] == leg and l.get("degenerate"))
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
                  + (f"   退化对(e=0)={ndeg} 条，ratio 无定义 ⇒ 不进分位统计" if ndeg else ""))
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
    # 量具声明由脚本自己打印，不手写进产物：产物每次运行被整体覆盖，手写的适用边界
    # 会在下一次重跑时静默消失 —— 那等于让读数失去它的条件，比没有读数更危险。
    print("""
================================================================================
量具状态与适用边界（本轮实测后如实登记）
================================================================================
已修四类缺陷：
 a) 候选集取错来源：曾把 action（只含已选中的 1 个任务）当候选集 ⇒ groups=0。
    现复现 Greedy 真实枚举：unassigned[:candidate_limit] + _is_feasible（scheduler.py:96-107）。
    candidate_limit 的【生效值】是 60（config/simulation.json:11），不是代码默认 1 ——
    我曾据默认值误判"inversion 结构上不可能"，判据要看运行时生效值。
 b) 静态 OD 逐步重复测量：pickup->delivery 只取决于任务本身，去重后样本从虚增的 48.8 万
    降到 180 条唯一 OD；否则各类占比全被重复计数稀释。
 c) 百分比分母误用全体 legs ⇒ 曾输出"直达=71128%"。现分母 = 本 (fixture, leg) 子集。
 d) 退化对（机位恰在取货点 / source==destination）ratio 无定义：曾以 NaN 混入列表并显示成
    "48.8 万条非有限值"，看着像量具崩了；现单独计数且不进分位统计。
 e) 【本轮新发现】候选集截断与 padding 的先后顺序：Greedy 是"先剔 __pad_、再 [:candidate_limit]"
    （scheduler.py:45-48 → :98），而 environment.py:1591-1614 是【截断之后】才补 padding ⇒
    obs[:60] 尾部恒为占位任务。旧版直接对 un[:limit] 取候选，于是探针的候选集合既混进了
    (0,0) 坐标的假腿、又少掉了真任务 ⇒ 参与排序的组被系统性改变。修复后必须重跑本探针，
    旧的 ranking inversion 数字不得继续引用（Phase 1B-1 的 H0 依据因此作废，见下）。

仍存在的边界（引用本数据须知）：
 · drone->pickup 的 n 是"派单机会数"量级（数十万），同一 (drone, task) 对在多个 step 上被
   重复计入 ⇒ 它是【决策机会加权】的分布，不是独立样本分布。因此 mean/P50≈1.0 主要由大量
   直达机会贡献，只能读作"该世界几何下多数派单机会无需绕障"，不能读作"绕障不重要"。
 · ranking inversion 只量"换冠军"这一种翻转（组内 e_pickup 最小者 vs r_pickup 最小者），
   未量整条排序的 Kendall tau 或 top-k 变化。
 · 【判据强度】上面那条"只看 pickup 最短"只是 Greedy 决策的**近似代理**。真实 argmax 是
   MATCH_WEIGHT*match + DISTANCE_WEIGHT*proximity，其中 proximity 在候选集内归一化 ⇒ 依赖
   整组距离，且 match 还吃 total_distance = source_dist + route_dist。因此本探针的翻转率是
   对真实翻转率的**下界估计**；精确证人见 console/phase1b1_flip_witness.py（重放真评分函数）。
 · 仅覆盖 greedy 一条链；GA/PSO/OR-Tools 的距离口径不在本探针范围内（后端零引用 provider，
   已在 console/test_phase1b1_distance_experiment.py::G5 钉成断言）。

结论适用性：本产物此前公布的 "★ Ranking inversion = 7/10676 = 0.07%" 是在缺陷 e 之下测得，
修复后数字会变 ⇒ 该值**不再作为 Phase 1B-1 H0 的依据**，须以本轮重跑值与 flip_witness
同时为准。""")
    return 0


if __name__ == "__main__":
    raise SystemExit(report())
