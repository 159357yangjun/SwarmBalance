# -*- coding: utf-8 -*-
"""Phase 1B-2 的门：ETA 维度（reachability）必须真的接上、真的有牙、默认真的不改行为。

门清单（继承 1B-1 的 G1–G5/G8/G9，本轮新增 G10–G13）：
  G10  eta() 两面各测一次 + PlannedDistance 不因 eta 多花一次 A* + 坏 speed 报错不兜底
  G11  REACH_WEIGHT=0 时与"没有这个分量"逐位等价（保护 Gate B / 生产零漂移）
  G12  ETA 的时间口径与执行侧同源：time_step 1.0→2.0 时 ETA 必须减半（防登记表 M5 同族缺陷）
  G13  **判别式**：reachability 必须有自由度 —— 至少一条候选腿 reach < 1.0；
       否则它是恒等于 1 的死项，"ETA 已接入调度"这句话就不能说。

为什么 G13 最重要：它把"实现存在"与"实现有信息"分开。实测在当前 SLA
（base=420 s、per_kg=24 s、ref_speed=14 m/s）下 drone->pickup 的 slack 中位数 453.8 s
远大于 REF_SLACK=300 ⇒ 71.6% 候选饱和到 1.0。这不是 bug，是分量的作用域限制，
必须由门说出来而不是靠记忆。
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "frontend"))

OSM = REPO / "frontend" / "data" / "map" / "part_of_yangpu.osm"


def _clean_env():
    """子进程环境：剥掉两个实验开关，保证量到的是默认态。

    REACH_WEIGHT 在 greedy/scheduler.py 的 import 期冻结 ⇒ 同进程改环境变量无效，
    必须起子进程（与 1B-1 同一套路数）。
    """
    e = dict(os.environ)
    e.pop("SWARM_BALANCE_REACH_WEIGHT", None)
    e.pop("SWARM_BALANCE_SIM_CONFIG", None)
    e["PYTHONIOENCODING"] = "utf-8"
    return e


def _run_probe(name):
    """跑 console/<name> 并返回 stdout+stderr。

    刻意用独立文件而不是 `python -c "<一长串>"`：分号拼多语句在本机引号嵌套下会被截成
    一行（本轮真撞上 SyntaxError），而 for/if 块塞不进单行。
    """
    proc = subprocess.run([sys.executable, "-X", "utf8", str(REPO / "console" / name)],
                          cwd=str(REPO), env=_clean_env(),
                          text=True, capture_output=True, timeout=900, errors="replace")
    return proc.stdout + proc.stderr


def _world(kind):
    """构造一个已切好 provider 的 Environment（G13d 与 G10 共用）。"""
    import environment as em
    env = em.Environment(str(OSM), episode_max_steps=60)
    env.reset(seed=40901)
    env.set_route_cost_provider(kind)
    return env, env.route_cost_provider


class EtaProviderContract(unittest.TestCase):
    """G10：eta() 的两面都必须活着，且实验面不多花一次搜索。"""

    # _world 用模块级函数：G13d 也要同一个世界，两处各写一份就会漂移。
    _world = staticmethod(_world)

    def test_g10a_both_faces_expose_eta_and_differ_where_geometry_blocks(self):
        from route_planner import RouteRequest
        env, plan = self._world("planned_distance")
        _, euc = self._world("euclidean")
        blocked = None
        for b in env.high_buildings[:20]:
            (x0, y0, x1, y1) = b["geometry"].bounds
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            span = max(x1 - x0, y1 - x0, 1.0)
            a, c = (cx - span * 3, cy), (cx + span * 3, cy)
            if not env.route_planner.plan(RouteRequest(start=a, goal=c)).direct:
                blocked = (a, c)
                break
        if blocked is None:
            self.skipTest("样例楼里造不出被挡 OD ⇒ G10a 无分母，属未执行")
        a, c = blocked
        sp = float(env.drones[0].speed)
        ep, ee = plan.eta(a, c, sp), euc.eta(a, c, sp)
        self.assertGreater(ep, ee, "planned 面的 ETA 没变长 ⇒ eta() 没走航路长度")
        self.assertGreater(plan.eta_calls, 0, "planned 面 eta 计数为 0 ⇒ 没走到新分支")
        self.assertGreater(euc.eta_calls, 0, "对照面 eta 计数为 0 ⇒ 两面之一根本没实现 eta")

    def test_g10b_eta_reuses_distance_cache_no_extra_astar(self):
        """eta() 必须先问 distance() ⇒ 同一 OD 只命中缓存，不再触发 A*。

        判据用 cache_hits 而不是 unique_od：_key 按 round(2) 量化，不同坐标可能落进同一个桶，
        拿桶数当"没新增工作"的证据会误报（本轮就误报过一次）。命中计数才是直接证人。
        """
        env, plan = self._world("planned_distance")
        d0 = tuple(env.drones[0].get_position())
        un = [t for t in env._obs()["unassigned_tasks"]
              if not str(t.get("task_id", "")).startswith("__pad_")]
        tgt = tuple(un[0]["source"])
        plan.distance(d0, tgt)                      # 预热这条 OD
        hits_after_warm = plan.cache_hits
        e1 = plan.eta(d0, tgt, float(env.drones[0].speed))
        e2 = plan.eta(d0, tgt, float(env.drones[0].speed))
        self.assertEqual(plan.cache_hits - hits_after_warm, 2,
                         "两次 eta 没有各自命中一次缓存 ⇒ eta 重新搜索了航路（成本翻倍）")
        self.assertAlmostEqual(e1, e2, places=12)

    def test_g10c_bad_speed_raises_not_silent(self):
        """speed<=0 必须抛错。静默兜底会让全体 ETA 相同 ⇒ 分量悄悄失效。"""
        _, euc = self._world("euclidean")
        for bad in (0.0, -5.0):
            with self.assertRaises(Exception) as ctx:
                euc.eta((0.0, 0.0), (10.0, 10.0), bad)
            self.assertIn("BAD_SPEED", str(ctx.exception))


class WeightZeroIsExactBaseline(unittest.TestCase):
    """G11：W=0 时代数等价 —— 这是"本次实现不改生产行为"承诺的执行面。"""

    def test_g11_weight_zero_equals_pre_component_score(self):
        out = _run_probe("phase1b2_equiv_probe.py")
        self.assertIn("EQUIV_BAD=0", out,
                      "W=0 的打分与手算的原式不一致：\n" + out[-800:])
        # 探针那行是 `N=96 EQUIV_BAD=0` ⇒ 必须按字段取数，不能 split("=")[1] 整段当数字
        n = [l for l in out.splitlines() if " N=" in l or l.startswith("N=")]
        self.assertTrue(n, "探针没印 N=，等价断言没有分母：\n" + out[-400:])
        count = int(n[0].split("N=")[1].split()[0])
        self.assertGreater(count, 0, "一个候选都没测到，等价断言是空转")
        print("[G11] W=0 逐位对照 %d 个候选腿 × 两面，不一致=0" % count)


    def test_g11b_default_weight_is_zero_in_clean_process(self):
        """默认态必须真的是 0：若 config 或环境把它带成非 0，Gate B 当场失效。"""
        out = _run_probe("phase1b2_equiv_probe.py")
        line = [l for l in out.splitlines() if l.startswith("DEFAULT_W=")]
        self.assertTrue(line, "探针没印 DEFAULT_W=，无法核对默认权重：" + out[-300:])
        self.assertEqual(float(line[0].split("=")[1]), 0.0,
                         "干净进程里 REACH_WEIGHT 不是 0 ⇒ 本次实现改了生产默认行为")


class UnitConsistency(unittest.TestCase):
    """G12：ETA 必须按 env-step 表达，而不是偷偷按秒。"""

    def test_g12_eta_scales_with_time_step(self):
        """time_step 1.0 → 2.0 时同一 OD 同一航速的 ETA 必须减半。

        若实现写成 `distance/speed`（漏除 STEP_SECONDS），这条会红。
        判据形状来自登记表 M5 的同族缺陷（分子按步、分母按秒，只在 step=1 凑巧一致）。
        """
        out = _run_probe("phase1b2_timestep_probe.py")
        lines = [l for l in out.splitlines() if l.startswith("TS=")]
        self.assertEqual(len(lines), 2, "没拿到两次读数：\n" + out[-500:])
        e1 = float(lines[0].split("ETA=")[1].rstrip(")'"))
        e2 = float(lines[1].split("ETA=")[1].rstrip(")'"))
        self.assertAlmostEqual(e2, e1 / 2.0, places=9,
                               msg="time_step 翻倍而 ETA 没减半（%.4f → %.4f）⇒ ETA 单位不是 env-step"
                                   % (e1, e2))


class ConfigSwitchIsLive(unittest.TestCase):
    """G14：`config.environment.greedy.reach_weight` 必须真的被读到，且默认关闭。

    为什么这道门值得常驻：本轮我先往 config 里塞了一个 `_reach_weight_note` 说明键，
    被 test_config_keys_coverage 当场判成哑键（"改了不起作用"）——那正是这道门要防的形状：
    配置里有开关、代码里没有消费者，答辩时以为调了参数其实没调。
    三态缺一不可：默认 0 / config 生效 / env 优先于 config。
    """

    # 独立文件而不是 `python -c`：分号拼 if/elif 会被本机引号嵌套截成一行（本轮实测过）。
    PROBE = "phase1b2_switch_probe.py"

    def _read(self, mode):
        proc = subprocess.run([sys.executable, "-X", "utf8", str(REPO / "console" / self.PROBE),
                               mode],
                              cwd=str(REPO), env=_clean_env(), text=True,
                              capture_output=True, timeout=600, errors="replace")
        out = proc.stdout + proc.stderr
        line = [l for l in out.splitlines() if l.startswith("W=")]
        self.assertTrue(line, "探针 %s 没有读数：%s" % (mode, out[-400:]))
        got = float(line[0].split()[0][2:].rstrip("'"))
        want = float(line[0].split()[1][5:].rstrip("'"))
        return got, want

    def test_g14a_default_off_in_shipped_config(self):
        """出厂 config 的 reach_weight 必须是 0.0 ⇒ 本次改动没换掉生产默认行为。"""
        cfg = json.loads((REPO / "config" / "simulation.json").read_text(encoding="utf-8"))
        v = cfg["environment"]["greedy"].get("reach_weight", None)
        self.assertIsNotNone(v, "config 里没有 reach_weight ⇒ 演示开关不存在")
        self.assertEqual(float(v), 0.0, "出厂值不是 0.0 ⇒ 默认行为被改了，Gate B 失效")
        got, want = self._read("off")
        self.assertEqual(got, 0.0)

    def test_g14b_config_key_is_consumed(self):
        got, want = self._read("config")
        self.assertEqual(got, want,
                         "config.reach_weight 没被读 ⇒ 它是哑键（改了不起作用）：got=%r want=%r" % (got, want))

    def test_g14c_env_overrides_config(self):
        """两面都设时环境变量赢 —— 批量实验靠它切权重，优先级反了就会整批跑成同一个值。"""
        got, want = self._read("both")
        self.assertEqual(got, want, "env 没能覆盖 config ⇒ 实验注入通道失效：got=%r want=%r" % (got, want))


class ReachabilityHasFreedom(unittest.TestCase):
    """G13：分量必须有自由度，否则它是恒等于 1 的死项。"""

    def test_g13d_eta_actually_consumes_planner_distance(self):
        """第二证人：planned 面的 ETA 必须真的来自航路长度 —— 用【合成被挡 OD】测。

        为什么不能用"真实候选腿的两面差值"当判据（我第一版就是这么写的，当场永红）：
        reachability 只吃 drone->pickup，而实测 C-1 seed=40901 的该组 48 条 pickup 腿
        planned≠euclid 的比例是 **0%**（绕障集中在 pickup->delivery，43.8% 不同、max 44.2 m）
        ⇒ 两面 ETA 必然相同 ⇒ "存在不同"是不可满足条件 = 永红夹具。
        恒真与恒假都会让门失去意义，所以这里改测【机制本身】：给一个直线必穿楼的 OD，
        planned 面的 ETA 必须比对照面长。它不依赖世界几何恰好产生绕障腿。
        """
        from route_planner import RouteRequest
        env, plan = _world("planned_distance")
        _, euc = _world("euclidean")
        blocked = None
        for b in env.high_buildings[:20]:
            (x0, y0, x1, y1) = b["geometry"].bounds
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            span = max(x1 - x0, y1 - y0, 1.0)
            a, c = (cx - span * 3, cy), (cx + span * 3, cy)
            if not env.route_planner.plan(RouteRequest(start=a, goal=c)).direct:
                blocked = (a, c)
                break
        if blocked is None:
            self.skipTest("造不出被挡 OD ⇒ 本断言无分母，属未执行")
        sp = float(env.drones[0].speed)
        self.assertGreater(plan.eta(*blocked, speed_m_per_s=sp),
                           euc.eta(*blocked, speed_m_per_s=sp),
                           "planned 面 ETA 没变长 ⇒ eta() 没消费航路长度（恒等常量或漏接）")

    def test_g13_some_candidates_are_actually_tight(self):
        import environment as em
        from greedy.scheduler import GreedyScheduler as GS
        from route_cost import PlannedDistanceRouteCostProvider
        env = em.Environment(str(OSM), episode_max_steps=60)
        o = env.reset(seed=40901)
        pp = PlannedDistanceRouteCostProvider(env.route_planner)
        un = [t for t in o["unassigned_tasks"] if not str(t.get("task_id", "")).startswith("__pad_")]
        vals = []
        for d_idx in range(len(env.drones)):
            cap = o["drone_capabilities"][d_idx]
            pos = tuple(o["drone_positions"][d_idx])
            sp = float(cap["speed"])
            for t in [x for x in un[:60] if GS._is_feasible(cap, x)]:
                rp = GS._reachability(pp, pos, t, sp)
                if rp is None:
                    continue
                vals.append(rp)
        self.assertTrue(vals, "一个 reachability 都算不出来 ⇒ 门没有分母")
        tight = sum(1 for v in vals if v < 1.0)
        print("[G13] 样本=%d 未饱和(<1.0)=%d (%.1f%%) min=%.4f max=%.4f 不同值数=%d"
              % (len(vals), tight, 100.0 * tight / len(vals), min(vals), max(vals),
                 len(set(round(v, 6) for v in vals))))
        self.assertGreater(tight, 0,
                           "所有候选的 reachability 都饱和在 1.0 ⇒ 全程余量在这个世界上恒定充裕，"
                           "时效类分量缺少区分度。此时不得宣称'ETA 已接入调度'，须先动 SLA 档位")
        # 恒等于中性值 0.5 的假实现同样满足"存在 <1.0"（本轮变异 V1 就这么溜过去过一次），
        # 所以还要它有【多个不同取值】才算真的有自由度：常量项永远只有 1 个值。
        self.assertGreater(len(set(round(v, 6) for v in vals)), 3,
                           "reachability 只有 ≤3 个不同取值 ⇒ 疑似常量/阶梯假实现，不是连续接入")



    def test_g13b_neutral_on_infinite_deadline(self):
        import environment as em
        from greedy.scheduler import GreedyScheduler as GS
        from route_cost import PlannedDistanceRouteCostProvider
        env = em.Environment(str(OSM), episode_max_steps=60)
        env.reset(seed=40901)
        prov = PlannedDistanceRouteCostProvider(env.route_planner)
        t = {"task_id": "x", "source": [1.0, 1.0], "remaining_time": float("inf")}
        self.assertEqual(GS._reachability(prov, (0.0, 0.0), t, 20.0), 0.5,
                         "无截止时间的任务不该被判最优或最差")

    def test_g13c_no_infinite_deadline_means_neutral(self):
        """无截止时间 ⇒ _slack_full_seconds 返回 None、_reachability 取中性 0.5。

        两个函数现在分工明确：`_slack_full_seconds` 是罚分项的唯一输入（None = 不加不减），
        `_reachability` 只保留 ∈[0,1] 的旧语义给对照与展示用。所以这里两条都要断言 ——
        第一版我只断言了后者，判据写的是"provider=None 应返回 None"，而实现按新分工
        返回中性 0.5 ⇒ 门红在【我自己的过期判据】上，不是代码错。判据要跟语义一起改。
        """
        from greedy.scheduler import GreedyScheduler as GS
        task = {"task_id": "x", "source": [1.0, 1.0], "destination": [2.0, 1.0],
                "remaining_time": float("inf")}
        self.assertIsNone(GS._slack_full_seconds(None, (0.0, 0.0), task, 20.0),
                          "provider 缺失时必须拿不到 slack ⇒ 调用处退回 1B-1 行为")
        self.assertIsNone(GS._slack_full_seconds(_FakeProv(), (0.0, 0.0), task, 20.0),
                          "无截止时间的真实任务也必须走中性分支，不能被判最优或最差")

    def test_g13e_penalty_is_one_sided(self):
        """约束式的定义就是【单侧】：slack≥0 贡献恒 0，slack<0 才扣分。

        这是本轮把"奖励式"换成"罚分式"的全部意义 —— 上一版的失败恰恰是它给
        "取货看着从容、送货飞不完"的单加了分（诊断产物 §1）。所以这条必须直接断言：
        存在被扣分的候选，且没有任何候选拿到正贡献。
        """
        import environment as em
        from greedy.scheduler import GreedyScheduler as GS
        from route_cost import EuclideanRouteCostProvider
        env = em.Environment(str(OSM), episode_max_steps=60)
        o = env.reset(seed=40901)
        pe = EuclideanRouteCostProvider()
        un = [t for t in o["unassigned_tasks"] if not str(t.get("task_id", "")).startswith("__pad_")]
        pos_sum = []
        for d_idx in range(len(env.drones)):
            cap = o["drone_capabilities"][d_idx]
            pos = tuple(o["drone_positions"][d_idx])
            cand = [t for t in un[:60] if GS._is_feasible(cap, t)]
            dists = pe.batch(pos, [tuple(t["source"]) for t in cand])
            mn, mx = min(dists), max(dists)
            dm = dict(zip([t["task_id"] for t in cand], dists))
            for t in cand:
                prox = 1.0 if mx <= mn else 1.0 - (dm[t["task_id"]] - mn) / (mx - mn)
                s0 = GS._score_task(cap, pos, t, prox, provider=pe, reach_weight=0.0)
                s4 = GS._score_task(cap, pos, t, prox, provider=pe, reach_weight=0.4)
                if s0 == float("-inf"):
                    continue
                pos_sum.append((s4 - s0, GS._slack_full_seconds(pe, pos, t, float(cap["speed"]))))
        self.assertTrue(pos_sum, "一个候选都测不到 ⇒ 门没有分母")
        contribs = [c for c, _ in pos_sum]
        self.assertLessEqual(max(contribs), 1e-12,
                             "出现正贡献 ⇒ 又变回奖励式，约束语义丢失（这正是 1B-2 否掉的形状）")
        neg = [c for c, sl in pos_sum if c < -1e-12]
        print("[G13e] 候选=%d 被扣分=%d 最小贡献=%.6f | 全部零贡献(slack>=0)=%d"
              % (len(pos_sum), len(neg), min(contribs), len(pos_sum) - len(neg)))
        self.assertTrue(all(sl is None or sl >= 0 for c, sl in pos_sum if abs(c) <= 1e-12),
                        "有候选 slack<0 却没被扣分 ⇒ min(0,·) 分支没接上")

    def test_g13f_penalty_uses_the_delivery_leg(self):
        """G13f：slack 必须真的含【送货腿】—— 用构造夹具逼出差异。

        为什么需要这道门（本轮变异 V6 教出来的）：把 delivery_eta 摘成 0.0 之后，
        真实世界 step=0 的 81 条候选仍然【一条都不被罚】⇒ G13e 的两面都是 0，抓不到。
        我自己在诊断产物里写过"step=0 零触发不代表整局零触发"，然后就用了一个只在
        step=0 取样的门去判语义 —— 这是同一个外推错误的第二次犯法，方向相反。
        ⇒ 单侧性由 G13e 锁，定义域由这道门锁，且必须用夹具而不是自然快照。

        夹具形状：同一 remaining_time、同一取货距离，只有送货距离不同（一近一远）。
        若实现漏掉送货腿，两条的 slack 会相等 ⇒ 罚分相同 ⇒ 门红。
        """
        from greedy.scheduler import GreedyScheduler as GS
        from route_cost import EuclideanRouteCostProvider
        pe = EuclideanRouteCostProvider()
        pos = (0.0, 0.0)
        sp = 20.0
        near = {"task_id": "near", "source": [100.0, 0.0], "destination": [120.0, 0.0],
                "remaining_time": 30.0}          # 取货 5 s + 送货 1 s ⇒ slack=+24（从容）
        far = {"task_id": "far", "source": [100.0, 0.0], "destination": [1100.0, 0.0],
               "remaining_time": 30.0}           # 取货 5 s + 送货 49 s ⇒ slack=-24（注定赶不上）
        s_near = GS._slack_full_seconds(pe, pos, near, sp)
        s_far = GS._slack_full_seconds(pe, pos, far, sp)
        print("[G13f] slack_full 近=%r 远=%r" % (s_near, s_far))
        self.assertGreater(s_near, 0.0, "夹具不成立：近单本该余量为正")
        self.assertLess(s_far, 0.0, "夹具不成立：远单本该余量为负")
        self.assertLess(s_far, s_near - 1.0,
                        "两条 slack 差不足 1 s ⇒ 送货腿没进公式（delivery 距离从 20 m 变到 1000 m "
                        "却几乎不影响结果）。这正是变异 V6 的形状")
        # 再确认它真的转成了罚分：远单被扣、近单不扣
        c_near = GS._score_task({"drone_type": "x", "remaining_capacity": 99.0, "speed": sp,
                                 "battery_capacity": 1e6, "battery_consumption_base": 1e-6},
                                pos, near, 0.5, provider=pe, reach_weight=0.4) -                  GS._score_task({"drone_type": "x", "remaining_capacity": 99.0, "speed": sp,
                                 "battery_capacity": 1e6, "battery_consumption_base": 1e-6},
                                pos, near, 0.5, provider=pe, reach_weight=0.0)
        c_far = GS._score_task({"drone_type": "x", "remaining_capacity": 99.0, "speed": sp,
                                "battery_capacity": 1e6, "battery_consumption_base": 1e-6},
                               pos, far, 0.5, provider=pe, reach_weight=0.4) -                 GS._score_task({"drone_type": "x", "remaining_capacity": 99.0, "speed": sp,
                                "battery_capacity": 1e6, "battery_consumption_base": 1e-6},
                               pos, far, 0.5, provider=pe, reach_weight=0.0)
        self.assertAlmostEqual(c_near, 0.0, places=12, msg="余量为正的单不该拿到任何贡献（约束式）")
        self.assertLess(c_far, 0.0, msg="注定赶不上的单必须被扣分")


class _FakeProv:
    """最小 provider 替身：只为让 _slack_full_seconds 走完取货+送货两段。"""
    name = "fake"

    @staticmethod
    def eta(a, b, sp):
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 / sp

    @staticmethod
    def distance(a, b):
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5



if __name__ == "__main__":
    unittest.main(verbosity=2)
