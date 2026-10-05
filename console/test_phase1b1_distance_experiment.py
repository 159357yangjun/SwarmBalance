# -*- coding: utf-8 -*-
"""Phase 1B-1 的门与跑法：distance-aware scheduling（Euclidean vs PlannedDistance）。

G1  provider 通道两面各测一次（缺这一条，"实验面"可能一直在偷偷跑欧氏）
G2  observation 挂载 + Greedy 真的调用了它（provider 在但没人用 = 假实验）
G3  判别式：同一 OD 上 planned > euclid 且 direct=False；对照面同输入必须恒等于欧氏
G4  未知 kind 报错、不静默兜底（兜底会让拼错的开关跑成对照组而被当成结果）
G5  GA/PSO 侧零引用 route_cost_provider ⇒ GA 面是阴性对照（漂移即机制有第二条通路）
G6  正式跑（SWARM_1B1_FULL=1）：逐 seed 配对差分 + H0/H1 判定 + 追溯证人

判据来自预注册假设（总纲 §17.0）：H0 = 核心 KPI 逐值不变或差异 < 1 单任务；
H1 = 若变化 ≥ 2 单任务，必须能追溯到该 seed 的具体一次绕障候选腿翻转。
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "frontend"))

OSM = REPO / "frontend" / "data" / "map" / "part_of_yangpu.osm"
FLIP_DOC = REPO / "docs" / "取证输出" / "phase1b1_flip_witness.txt"


def _fresh_env(provider_kind):
    """构造一个已切好 provider 的 Environment（in-process，只用于门 G1~G3）。"""
    import environment as em
    env = em.Environment(str(OSM), episode_max_steps=120)
    env.reset(seed=40901)
    got = env.set_route_cost_provider(provider_kind)
    assert got == provider_kind, "[PROVIDER_NOT_APPLIED] 请求 %r 实得 %r" % (provider_kind, got)
    return env


class FlipRateBaseline(unittest.TestCase):
    """G7：Greedy 真实评分函数下的翻转率基线 —— 把"距离口径换不得"钉成会红的断言。

    为什么这道门必须存在：1B-1 的全部理由就是"候选排序会被绕障距离改写"。若哪天
    地图/权重/候选集变了导致翻转率归零，实验面与对照面就等价了，继续做 1B-2 是浪费；
    反过来若翻转率暴涨，之前所有 KPI 解释都要重下。两种情况都得由门说出来，而不是靠记忆。

    数字来源：console/phase1b1_flip_witness.py 实测 5/302 = 1.66%（docs/取证输出/
    phase1b1_flip_witness.txt）。下限取 0.5%：留一半余量给 seed 集合变动，但仍能抓住
    "结构性归零"。上限刻意不设 —— 变高不是缺陷，是要重新解读的信号。
    """

    def test_greedy_real_scoring_flips_at_least_half_percent(self):
        from console import phase1b1_flip_witness as FW
        groups = flips = 0
        for fx in ("C1", "C2"):
            st, _ev = FW.scan(fx, 40901)          # 单 seed 足够判"有没有"这条结构性质
            groups += st["groups"]
            flips += st["flips"]
        self.assertGreater(groups, 0, "一个候选组都没数到 ⇒ 探针失效，本门不构成证据")
        rate = flips / groups
        print("[G7] flip_witness C1/C2 seed=40901：组=%d 翻转=%d 率=%.4f%%"
              % (groups, flips, rate * 100))
        self.assertGreaterEqual(rate, 0.005,
                                "真实评分下的翻转率 %.4f%% 低于基线下限 0.5%% ⇒ "
                                "distance-only 切换在此世界上几乎不改变分配，"
                                "1B-1 的结论前提已不成立，须重估 1B-2 的必要性" % (rate * 100))

    def test_documented_flip_rate_matches_probe(self):
        """产物级对账：登记的翻转率必须来自本轮真跑，不能是上一版抄下来的数。

        形状匹配而非数值相等：整批扫描耗时数十分钟，不该挂在常规回归里；
        但文档一旦被改写成与探针不同形状/不同量级的数字，这里就会红。
        """
        if not FLIP_DOC.exists():
            self.skipTest("缺少 docs/取证输出/phase1b1_flip_witness.txt ⇒ 无法对账，"
                          "这是未验证，不是通过（先跑 phase1b1_flip_witness.py 并归档）")
        text = FLIP_DOC.read_text(encoding="utf-8")
        import re
        m = re.search(r"合计：候选组=(\d+) 翻转=(\d+) 翻转率=([\d.]+)%", text)
        self.assertIsNotNone(m, "产物里没有'合计：候选组=… 翻转=… 翻转率=…%'这一行 ⇒ 对账无从进行")
        g, f, r = int(m.group(1)), int(m.group(2)), float(m.group(3))
        self.assertEqual(g, 302, "产物里的候选组分母变了（登记值 302）⇒ seed/fixture 集合被改过，"
                                "引用该数字的段落需重算")
        self.assertAlmostEqual(r, 100.0 * f / g, places=2,
                               msg="产物自相矛盾：翻转率 %s%% 与 组=%d/翻转=%d 不一致" % (r, g, f))



class ProviderChannel(unittest.TestCase):
    """G1/G2/G4：开关本身必须是活的、可证的、不会静默降级。"""

    def test_g1_env_var_channel_applies_in_fresh_import(self):
        """环境变量注入必须真的换掉 provider —— 两面各测一次。

        为什么两面都要测：只测实验面红不了"默认路径被改成 planned"这种事故；
        只测对照面则实验开关坏掉时会安静地跑成对照组（最贵的假绿灯）。
        """
        code = (
            "import os,sys,pathlib;"
            "R=pathlib.Path(sys.argv[1]);sys.path.insert(0,str(R));sys.path.insert(0,str(R/'frontend'));"
            "import environment as em;e=em.Environment(str(R/'frontend'/'data'/'map'/'part_of_yangpu.osm'),episode_max_steps=60);"
            "e.reset(seed=40901);print('KIND='+e.route_cost_kind)"
        )
        for want, expect in (("planned_distance", "planned_distance"),
                             ("", "euclidean"),
                             ("bogus_kind", "ERROR")):
            env = dict(os.environ)
            if want:
                env["SWARM_BALANCE_ROUTE_COST"] = want
            else:
                env.pop("SWARM_BALANCE_ROUTE_COST", None)
            proc = self._subprocess([sys.executable, "-X", "utf8", "-c", code, str(REPO)], env)
            out = proc.stdout + proc.stderr
            line = [l for l in out.splitlines() if l.startswith("KIND=")]
            if expect == "ERROR":
                self.assertNotEqual(proc.returncode, 0,
                                    "未知 provider kind 被静默接受了：%s ⇒ 拼错的开关会跑成对照组" % out[-200:])
                self.assertIn("UNKNOWN_COST_PROVIDER", out)
                continue
            self.assertEqual(proc.returncode, 0, out[-400:])
            self.assertTrue(line, "子进程没打印 KIND=：%s" % out[-300:])
            self.assertEqual(line[0].split("=", 1)[1], expect,
                             "SWARM_BALANCE_ROUTE_COST=%r 未生效（期望 %r）" % (want, expect))

    @staticmethod
    def _subprocess(cmd, env):
        import subprocess
        return subprocess.run(cmd, cwd=str(REPO), env=env, text=True,
                              capture_output=True, timeout=600)

    def test_g2_provider_reaches_observation_and_is_called(self):
        env = _fresh_env("planned_distance")
        obs = env._obs()
        self.assertIs(obs.get("route_cost_provider"), env.route_cost_provider,
                      "observation 没挂当前 provider ⇒ 调度器拿到的是旧口径或 None")
        from greedy.scheduler import greedy_action_from_observation
        greedy_action_from_observation(obs)
        calls = env.route_cost_provider.stats()["calls"]
        self.assertGreater(calls, 0,
                           "Greedy 一步都没调用 provider ⇒ 距离口径根本没进决策，实验是空转")

    def test_g3_discriminator_planned_differs_where_geometry_blocks(self):
        """判别式：找一个"直线被挡"的 OD，planned 必须 > euclid；对照面同输入必须 == euclid。

        没有这一条，两面可能都在返回欧氏而统计上完全看不出来（缓存命中率高时尤其危险）。
        """
        from route_planner import RouteRequest
        env = _fresh_env("planned_distance")
        prov = env.route_cost_provider
        found = None
        for b in env.high_buildings[:20]:
            (x0, y0, x1, y1) = b["geometry"].bounds
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            span = max(x1 - x0, y1 - y0, 1.0)
            a, c = (cx - span * 3, cy), (cx + span * 3, cy)
            res = env.route_planner.plan(RouteRequest(start=a, goal=c))
            if not res.direct and not res.fallback:
                found = (a, c, res)
                break
        if found is None:
            self.skipTest("本 OSM 的 20 栋样例楼都没造出'直线被挡'的 OD —— 判别式无从执行，"
                          "这是未验证，不是通过")
        a, c, res = found
        e = ((a[0] - c[0]) ** 2 + (a[1] - c[1]) ** 2) ** 0.5
        d = prov.distance(a, c)
        self.assertGreater(d, e, "planned 面在同一条被挡 OD 上没变长 ⇒ provider 没走航路长度")

        env2 = _fresh_env("euclidean")
        self.assertAlmostEqual(env2.route_cost_provider.distance(a, c), e, places=9,
                               msg="对照面必须逐字等于欧氏")

    def test_g4_unknown_kind_raises_not_silent(self):
        env = _fresh_env("euclidean")
        with self.assertRaises(Exception) as ctx:
            env.set_route_cost_provider("PlannedDistnce")   # 典型拼写错误
        self.assertIn("UNKNOWN_COST_PROVIDER", str(ctx.exception))


class GaIsNegativeControl(unittest.TestCase):
    """G5：GA/PSO 源码零引用 provider ⇒ 它是本实验的阴性对照面。"""

    def test_backend_schedulers_never_read_route_cost_provider(self):
        hits = []
        for rel in ("backend_si/pso_scheduler.py", "backend_si/ga_scheduler.py",
                    "backend_si/ortools_scheduler.py"):
            p = REPO / rel
            if not p.exists():
                continue
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                s = line.strip()
                if s.startswith("#"):
                    continue
                if "route_cost_provider" in s:
                    hits.append("%s:%d" % (rel, i))
        self.assertEqual(hits, [],
                         "后端优化器开始读 provider 了：%s ⇒ GA 不再是阴性对照，"
                         "GA 面的任何漂移都要重新归因" % ", ".join(hits))


@unittest.skipUnless(os.environ.get("SWARM_1B1_FULL") == "1",
                     "正式配对实验耗时长，显式 SWARM_1B1_FULL=1 才跑（否则是未执行，不是通过）")
class FullPairedExperiment(unittest.TestCase):
    """G6：C-1/C-2 × {greedy, ga} × seeds × {euclidean, planned_distance}。"""

    def test_h0_h1_paired_comparison(self):
        from console import phase1b1_experiment as P1
        rows, cells, _wd = P1.collect()
        diffs = P1.paired_diffs(rows)
        agg = P1.sign_summary(diffs)
        bad = P1.untraceable(diffs, cells)
        self.assertEqual(bad, [], "出现无法追溯的任务数变化：\n  " + "\n  ".join(bad))
        # H0 的量化面：把每个格子的最大 |Δ| 打出来，交回人工判读；
        # 这里只对"计数型 KPI 且 ≥1 单任务"提出硬断言（H0 允许 <1 的差异）
        violations = [d for d in diffs
                      if d["kpi"] in P1.COUNT_KPI and abs(d["diff"]) >= 1.0]
        report = ["%s/%s seed=%s %s: %.0f -> %.0f (Δ%.0f)"
                  % (v["fixture"], v["algorithm"], v["seed"], v["kpi"],
                     v["euclid"], v["planned"], v["diff"]) for v in violations]
        print("\n[H0 违反候选（计数型 KPI Δ>=1）] n=%d\n  %s"
              % (len(violations), "\n  ".join(report) or "无"))
        print("[符号汇总] %d 组" % len(agg))


class WitnessMustNotBeVacuous(unittest.TestCase):
    """G8：追溯证人必须【非平凡】—— 两面同输入时必须真的给出不同的数。

    为什么这道门是本轮最贵的一条：上一版的 flip_witness / attribution_trace 把同一个
    PlannedDistanceRouteCostProvider 实例先后喂给两面（它自带 _cache）⇒ 第二面全量命中
    第一面的缓存 ⇒ 两"面"其实是同一组数 ⇒ flips=0 是【构造出来的 0】。
    后果不是少一个证据，而是多一个假证据：C1 seed=40902 正式实验 Δ完成任务数=+4，
    旧 witness 在同一格数到 0 翻转 —— "追不到"会被读成"变化不存在"。
    恒真的证人比没有证人更坏，因为它让归因看起来已经完成。
    """

    def test_g8_planned_provider_has_real_freedom_vs_euclidean(self):
        from route_cost import EuclideanRouteCostProvider, PlannedDistanceRouteCostProvider
        env = _fresh_env("planned_distance")
        euc = EuclideanRouteCostProvider()
        plan = PlannedDistanceRouteCostProvider(env.route_planner)   # 独立实例，绝不与 euc 共享
        pairs = []
        for b in env.high_buildings[:20]:
            (x0, y0, x1, y1) = b["geometry"].bounds
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            span = max(x1 - x0, y1 - y0, 1.0)
            pairs.append(((cx - span * 3, cy), (cx + span * 3, cy)))
            pairs.append(((cx, cy - span * 3), (cx, cy + span * 3)))
        self.assertTrue(pairs, "造不出任何 OD ⇒ 本门没有分母，属未执行")
        same = diff = 0
        for a, c in pairs:
            de, dp = euc.distance(a, c), plan.distance(a, c)
            if abs(de - dp) <= 1e-9:
                same += 1
            else:
                diff += 1
        print("[G8] 判别式 OD=%d 两面相同=%d 两面不同=%d" % (len(pairs), same, diff))
        self.assertGreater(diff, 0,
                           "planned 面对所有样本都给出与欧氏相同的距离 ⇒ 它没有自由度，"
                           "任何用它测出的『翻转数=0』都是构造出来的，不得作为归因证据")
        self.assertGreater(same, 0,
                           "反过来：若没有任何一条两面相同，说明世界全是障碍，"
                           "对照面就不再是『直线口径』的基线，同样不可解释")


class CrossInstrumentConsistency(unittest.TestCase):
    """G9：三把尺子（正式实验 / witness / trace）必须能对上，对不上就点名。

    这一条是我自己撞出来的：正式实验 C1 seed=40902 Δ=+4，而 witness 说 0 翻转。
    如果只跑各自的门、不做交叉对账，两个数字会同时"通过"并各自被引用。

    ⚠ 判据必须是【本轮现算的 witness】，不能拿归档产物比 —— 归档那批是在缺陷 f/g 之下测的，
    用它当基准等于把一个已知失明的量具钉成标准答案（永红夹具）。所以这里现跑 scan()，
    并把"有绕障腿但没换冠军"单列为【合法盲点】：witness 只抓 rank inversion，
    不抓 score 幅度变化、tie-breaking、以及距离经 total_distance 进 compute_match 续航分量
    这条连续通路。⇒ 该格允许为 0，但必须印出它为什么是 0，而不是让它拦退码。
    """

    def test_g9_flip_census_agrees_with_paired_experiment(self):
        import re
        from console import phase1b1_flip_witness as FW
        paired = (REPO / "docs" / "取证输出" / "phase1b1_paired_experiment.txt")
        if not paired.exists():
            self.skipTest("缺正式实验产物 ⇒ 无法交叉对账（这是未验证，不是通过）")
        pat = re.compile(r"^(C\d) greedy seed=(\d+) 完成任务数\s+([\d.]+)\s+->\s+([\d.]+)\s+Δ=\s*(\S+)")
        changed = {}
        for line in paired.read_text(encoding="utf-8").splitlines():
            m = pat.match(line.strip())
            if m and abs(float(m.group(5))) >= 1:
                changed[(m.group(1), int(m.group(2)))] = float(m.group(5))
        self.assertTrue(changed, "正式实验里没有任何一格完成任务数变化 ⇒ G9 没有分母，属未执行")

        blind, hard_fail, seen = [], [], []
        for fx, sd in sorted(changed):
            st, _ev = FW.scan(fx, sd)          # 本轮现算，不吃归档产物
            seen.append((fx, sd, st["groups"], st["flips"], st["planned_deltas"]))
            if st["flips"] > 0:
                continue
            if st["planned_deltas"] > 0:
                blind.append("%s/%d Δ=%+.0f：witness 0 翻转，但该格有 %d 条绕障候选腿 ⇒ "
                             "走的是连续通路（score 幅度/tie-break/续航分量），属已知盲点"
                             % (fx, sd, changed[(fx, sd)], st["planned_deltas"]))
            else:
                hard_fail.append("%s/%d Δ=%+.0f：witness 0 翻转【且一条绕障腿都没有】⇒ "
                                 "要么 provider 失灵，要么存在第二条机制，必须先查"
                                 % (fx, sd, changed[(fx, sd)]))
        print("[G9] 本轮现算 witness：%s" % seen)
        for b in blind:
            print("     [BLIND] %s" % b)
        self.assertEqual(hard_fail, [], "\n".join(hard_fail))



if __name__ == "__main__":
    unittest.main(verbosity=2)

