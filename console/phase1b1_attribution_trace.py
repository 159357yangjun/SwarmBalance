# -*- coding: utf-8 -*-
"""Phase 1B-1 归因链：把"planned 面多了/少了 N 个任务"落到【具体哪一步换了谁】。

为什么追溯门不够（本文件存在的理由）：
  phase1b1_experiment.untraceable() 只回答"该 seed 有没有改变排序的机制通道"
  （provider.deltas 非空）。它【不】证明 KPI 的变化就是这些翻转造成的 ——
  一个恒真前提能解释任何变化，那种"追溯通过"是自证。

本探针做的是逐事件归因：
  1) 同一 episode 里对每个派单机会重放两种口径的 argmax（与 flip_witness 同一判据）；
  2) 标出两面"首次选择不同"的那一步 = 唯一的原因候选；
  3) 在那一步之后用 env.step 分叉出两个世界，各自跑到回合结束，比较完成任务数；
     ⇒ 差异必须在分叉后的世界里产生，这才叫追溯到步骤。

第 4) 件事同样重要：**同 provider 复跑**（噪声底）。若同配置同 seed 两次运行本身就会差
k 个任务，那么 k 以内的 Δ 都不能归因给 provider —— 顶回结论的前提是先量出自己的尺子精度。

不改任何仿真行为：分叉只在探针进程内复制环境状态，正式实验的两面仍各跑各的。
"""
from __future__ import annotations

import copy
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


def _cfg_file(fixture, wd):
    cfg = json.loads((REPO / "config" / "simulation.json").read_text(encoding="utf-8"))
    _merge(cfg, FIXTURES[fixture])
    p = wd / ("sim_%s.json" % fixture)
    p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
    return p


def _env(provider_kind, fixture, wd):
    import environment as em
    env = em.Environment(str(OSM), episode_max_steps=3600)
    env.reset(seed=None)
    got = env.set_route_cost_provider(provider_kind)
    assert got == provider_kind, "[PROVIDER_NOT_APPLIED] %r -> %r" % (provider_kind, got)
    return env


def replay(fixture: str, seed: int, wd: pathlib.Path):
    """在同一集上并行推进 euclid/planned 两个世界，记录每次派单选择与首个分歧步。

    两个世界共用【同一个 reset 之后的状态副本】⇒ 初始条件逐字相同；此后各自 step。
    这样"首分歧步"之前的历史完全一致，分歧只能由 provider 造成。
    """
    from greedy.scheduler import GreedyScheduler as GS, greedy_action_from_observation
    from route_cost import EuclideanRouteCostProvider, PlannedDistanceRouteCostProvider
    from greedy import scheduler as gs_mod

    cf = _cfg_file(fixture, wd)
    old = os.environ.get("SWARM_BALANCE_SIM_CONFIG")
    os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(cf)
    try:
        base = _env("euclidean", fixture, wd)
        base.reset(seed=seed)
        euc_env = copy.deepcopy(base)
        plan_env = copy.deepcopy(base)
        plan_env.set_route_cost_provider("planned_distance")

        euc = euc_env.route_cost_provider
        plan = plan_env.route_cost_provider
        # 【量具缺陷 f】两面必须各用【自己那个环境里的】 provider 实例。
        # PlannedDistanceRouteCostProvider 自带 _cache：上一版把同一个实例先后喂给两面 ⇒
        # 第二面全量命中第一面的缓存 ⇒ 两"面"是同一组数 ⇒ 假证人。
        # 同理，两面的 Greedy 必须各调一次：schedule_for_drone 会就地删 unassigned_tasks_info
        # （scheduler.py:140），只跑一次再复用结果会让第二面拿到被掏空的候选集。
        # 实测代价：C1 seed=40902 旧版报的首分歧 @step=57 drone3 task_13→task_14 两头都是错的，
        # 修正后为 @step=58 drone3 task_11→task_14。
        limit = max(1, gs_mod.CANDIDATE_LIMIT)

        events, first_diff, steps = [], None, 0
        o_e, o_p = euc_env._obs(), plan_env._obs()
        d_e = d_p = False
        while not (d_e and d_p) and steps < 3600:
            # 两面各【独立】调用生产 Greedy：贪心会就地删 unassigned_tasks_info，
            # 只跑一次再复用结果会让第二面拿到被掏空的候选集（实测因此把首分歧步与任务对都报错）。
            # 【缺陷 g】Greedy 每次调用消耗一个 random.random()（scheduler.py:89 的接单概率），
            # 而两面共享全局 RNG ⇒ 第二面拿到的是【被第一面推进过】的随机流。实测：两面从同一
            # 状态分叉、逐 drone 打分完全相同，但生产 action 在 step=0 就报出 drone4 分歧
            # （对照 task_6 / 实验 task_11）—— 那是 accept_probability 抽到了不同的值，不是距离口径。
            # ⇒ 本探针给出的【首分歧步与任务对】在修复"每步重置随机流"之前不得作为归因证据引用；
            #    只有"完成数差多少"这一聚合量仍可用（它同样受此扰动，须连同本条一起引用）。
            # 【缺陷 g·未修，本探针因此不具归因资格】Greedy 每次调用消耗一个 random.random()
            # （scheduler.py:89 接单概率），而两面共享【全局】RNG ⇒ 第二面拿到的是被第一面
            # 推进过的随机流。实测：两面从同一状态分叉、逐 drone 打分完全相同（top3 一致），
            # 但生产 action 在 step=0 就报出 drone4 分歧（对照 task_6 / 实验 task_11）——
            # 那是 accept_probability 抽到了不同的值，与距离口径无关。
            # 曾试过"每步 apply_seed(seed) 重播"来对齐：那会连带重置任务生成器，
            # 让对照面退回初始机位并重发同一批任务（完成数 73 vs 正常 105）⇒ 更错，已撤回。
            # ⇒ 正确做法是给每面注入【独立 Random 实例】，但那要改生产 Greedy 的取随机方式，
            #   属行为改动，不在本轮范围。在此之前：本探针的首分歧步/任务对一律不得引用；
            #   它的完成数差也只能当"另一次运行"，不能当受控差分。
            a_e = greedy_action_from_observation(o_e)
            a_p = greedy_action_from_observation(o_p)
            pe, pp = dict(a_e), dict(a_p)   # {drone_idx: [task_id]} —— 生产的真实选择，非重放
            diff = {k: (pe.get(k), pp.get(k)) for k in set(pe) | set(pp) if pe.get(k) != pp.get(k)}
            if diff and first_diff is None:
                first_diff = (steps, diff)
            if diff and len(events) < 60:
                events.append(dict(step=steps, detail=diff))
            o_e, _, d_e, _ = euc_env.step(a_e)
            o_p, _, d_p, _ = plan_env.step(a_p)
            steps += 1
        se, sp = euc_env.get_statistics(), plan_env.get_statistics()
        return dict(fixture=fixture, seed=seed, steps=steps,
                    completed_euclid=int(se["total_completed"]),
                    completed_planned=int(sp["total_completed"]),
                    generated_euclid=int(se["total_generated"]),
                    generated_planned=int(sp["total_generated"]),
                    detours_euclid=int(se["no_fly_detours"]),
                    detours_planned=int(sp["no_fly_detours"]),
                    first_diff_step=(first_diff[0] if first_diff else None),
                    first_diff_detail=(first_diff[1] if first_diff else None),
                    n_diff_steps=len(events), events=events,
                    planned_calls=plan.calls, planned_deltas=len(plan.deltas))
    finally:
        if old is None:
            os.environ.pop("SWARM_BALANCE_SIM_CONFIG", None)
        else:
            os.environ["SWARM_BALANCE_SIM_CONFIG"] = old


def noise_floor(fixture: str, seed: int, wd: pathlib.Path, algorithm: str = "greedy"):
    """同 provider、同 seed 连跑两次 worker：量出运行间噪声底。

    这是归因的前置条件 —— 没有它，"|Δ|=1 个任务"到底是切换造成的还是噪声，无从判断。
    """
    from console.phase1b1_experiment import run_cell
    outs = []
    for i in range(2):
        res = run_cell(fixture, seed, "euclidean", algorithm, wd)
        outs.append(res["metrics"])
    drift = {k: outs[1][k] - outs[0][k] for k in ("完成任务数", "生成任务数", "超时率",
                                               "总飞行距离", "总能量消耗")}
    return dict(fixture=fixture, seed=seed, run1=outs[0]["完成任务数"],
                run2=outs[1]["完成任务数"], drift=drift,
                identical=all(abs(v) < 1e-12 for v in drift.values()))


if __name__ == "__main__":
    wd = pathlib.Path(tempfile.mkdtemp(prefix="p1b1_trace_"))
    seeds = [int(x) for x in (sys.argv[1:] or ["40901", "40902", "40903"])]
    try:
        for fx in ("C1", "C2"):
            for sd in seeds:
                r = replay(fx, sd, wd)
                print("[trace] %s seed=%d 完成 e=%d p=%d (Δ%d) 生成 e=%d p=%d "
                      "绕飞计数 e=%d p=%d 分歧步数=%d 首分歧@step=%s planner调用=%d 绕障腿=%d"
                      % (fx, sd, r["completed_euclid"], r["completed_planned"],
                         r["completed_planned"] - r["completed_euclid"],
                         r["generated_euclid"], r["generated_planned"],
                         r["detours_euclid"], r["detours_planned"], r["n_diff_steps"],
                         r["first_diff_step"], r["planned_calls"], r["planned_deltas"]), flush=True)
                if r["first_diff_detail"]:
                    print("        首分歧：%s" % json.dumps(r["first_diff_detail"], ensure_ascii=False),
                          flush=True)
    finally:
        shutil.rmtree(wd, ignore_errors=True)
