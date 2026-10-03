# -*- coding: utf-8 -*-
"""S2 前置：SLA/deadline 的消费链门 —— 把"SLA 是评价参数还是行为参数"钉成可红断言。

本轮只读追踪的结论（每条都有具名行号，改动会当场转红）：

  生成   frontend/task.py:369-370 读 sla_base_seconds / sla_per_kg_seconds（实例级，非模块级）
        frontend/task.py:520-527 _sla_seconds() = distance/ref_speed + base + weight*per_kg
        frontend/environment.py:1297 / task.py:549 两处调用 ⇒ 写入 task.deadline

  统计   frontend/environment.py:391-393 delay = max(0, completion_time - deadline) → on_time/超时率
        frontend/environment.py:437 expected_time 仅在 PRINT_ROUTE_DEBUG 分支里，纯打印

  决策   frontend/environment.py:1503-1512 _obs() 把 ttlj = deadline - now 放进观察空间
        frontend/greedy/scheduler.py:174 读出 remaining_time
        frontend/greedy/scheduler.py:180-186 喂给 compute_match(...)
        frontend/matching.py:34-46 speed_match(): urgency = 1 - remaining_time/300 ⇒ 进打分

  不进决策的路径（同样要断言，否则"没有"无法被证明）
        matching.py            —— 无 SLA 系数引用（只用观察空间传来的 remaining_time）
        scheduling_interface.py/run_ga.py/run_pso.py/run_ortools.py —— deadline 引用数 0
        environment.py:1438-1477 overdue_penalty 只进 _reward()（RL 奖励，MARL 已撤除）

所以判据不是"SLA 会不会改超时率"（必然改），而是：**它同时进了贪心打分**。
本门的意义：若哪天有人把 deadline 从调度器摘掉（或接进 GA/PSO/OR-Tools），
S2 的定性结论就要重下——届时门会红，而不是靠我记忆。
"""
from __future__ import annotations

import pathlib
import sys
import unittest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "frontend"))


def _src(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


class SlaIsGeneratedFromConfig(unittest.TestCase):
    def test_deadline_formula_reads_both_coefficients(self):
        body = _src("frontend/task.py")
        self.assertIn('task_cfg.get("sla_base_seconds"', body)
        self.assertIn('task_cfg.get("sla_per_kg_seconds"', body)
        # 公式形状必须在源码里可见
        self.assertRegex(body.replace(" ", ""), r"flight\+self\._sla_base_seconds.*weight\*self\._sla_per_kg_seconds")

    def test_deadline_actually_moves_with_sla(self):
        """判别式：同一 (distance, weight) 在 Loose/Current/Strict 下必须给出不同 deadline。"""
        import json
        import tempfile
        import os

        cfg_path = REPO / "config" / "simulation.json"
        base_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        tmp = tempfile.mkdtemp(prefix="slagate_")
        old = os.environ.get("SWARM_BALANCE_SIM_CONFIG")
        try:
            out = {}
            for label, b, k in (("Loose", 540, 30), ("Current", 420, 24), ("Strict", 300, 18)):
                cfg = json.loads(json.dumps(base_cfg))
                cfg["task"]["sla_base_seconds"] = b
                cfg["task"]["sla_per_kg_seconds"] = k
                p = pathlib.Path(tmp) / f"{label}.json"
                p.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
                os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(p)
                for name in list(sys.modules):
                    if name.startswith(("frontend", "config")):
                        del sys.modules[name]
                tk = __import__("frontend.task", fromlist=["TaskGenerator"])
                gen = tk.TaskGenerator.__new__(tk.TaskGenerator)
                gen._sla_base_seconds = float(b)
                gen._sla_per_kg_seconds = float(k)
                gen._sla_reference_speed = 14.0
                out[label] = int(gen._sla_seconds(2000.0, 8.0))
            self.assertEqual(out["Loose"], int(2000 / 14 + 540 + 8 * 30), f"Loose 算式不符: {out}")
            self.assertGreater(out["Loose"], out["Current"])
            self.assertGreater(out["Current"], out["Strict"])
            # 三档必须两两不同，否则扫描等于没扫
            self.assertEqual(len(set(out.values())), 3, f"三档出现相同 deadline: {out}")
        finally:
            if old is None:
                os.environ.pop("SWARM_BALANCE_SIM_CONFIG", None)
            else:
                os.environ["SWARM_BALANCE_SIM_CONFIG"] = old
            for f in pathlib.Path(tmp).glob("*"):
                f.unlink(missing_ok=True)
            os.rmdir(tmp)


class DeadlineReachesGreedyScoring(unittest.TestCase):
    """核心断言：SLA 不只是及格线，它经观察空间进入贪心打分。"""

    def test_observation_exposes_ttlj(self):
        body = _src("frontend/environment.py")
        flat = body.replace(" ", "")
        self.assertIn("ttlj=deadline-current_time", flat)
        self.assertIn("'remaining_time':ttlj", flat)

    def test_greedy_scheduler_reads_remaining_time_into_compute_match(self):
        g = _src("frontend/greedy/scheduler.py")
        self.assertIn("task.get('remaining_time'", g)
        self.assertIn("remaining_time,", g)          # 作为实参传给 compute_match
        self.assertIn("compute_match(", g)

    def test_matching_turns_remaining_time_into_urgency(self):
        m = _src("frontend/matching.py")
        self.assertIn("def speed_match(speed, remaining_time)", m)
        self.assertRegex(m.replace(" ", ""), r"urgency=max\(0\.0,min\(1\.0,1\.0-remaining_time/300\.0\)\)")
        self.assertIn('w["speed"] * speed_match(speed, remaining_time)', m)

    def test_speed_match_monotone_in_urgency(self):
        """数值面：紧任务（小 remaining_time）更偏好高速机；松任务退化为中性 0.5。"""
        mp = __import__("matching", fromlist=["speed_match"])
        fast, slow = 20.0, 14.0
        tight_a = mp.speed_match(fast, 30.0)
        tight_b = mp.speed_match(slow, 30.0)
        self.assertGreater(tight_a, tight_b, "紧迫任务下高速机应更匹配")
        inf_a = mp.speed_match(fast, float("inf"))
        inf_b = mp.speed_match(slow, float("inf"))
        self.assertAlmostEqual(inf_a, inf_b, places=9, msg="无 deadline 时两者都应为中性 0.5")
        self.assertAlmostEqual(inf_a, 0.5, places=9)


class DeadlineNotUsedForFeasibility(unittest.TestCase):
    """反面对照：不许存在"deadline 太紧 ⇒ 拒单/不分配"这类硬约束路径。"""

    OPTIMIZER_FILES = ("frontend/scheduling_interface.py", "frontend/run_ga.py",
                       "frontend/run_pso.py", "frontend/run_ortools.py")

    def test_optimizers_never_reference_deadline(self):
        hits = {f: _src(f).count("deadline") for f in self.OPTIMIZER_FILES}
        bad = {f: c for f, c in hits.items() if c}
        self.assertFalse(bad, f"优化器出现了 deadline 引用（S2 定性需重下）: {bad}")

    def test_greedy_hard_rejects_are_capacity_only(self):
        """贪心里返回 -inf 的拒因只能是容量，不能是时限。"""
        g = _src("frontend/greedy/scheduler.py")
        lines = [ln.strip() for ln in g.splitlines() if "float('-inf')" in ln or 'float("-inf")' in ln]
        self.assertTrue(lines, "未找到 -inf 分支，说明贪心的拒单形状已变，请复核本断言前提")
        for ln in lines:
            self.assertNotIn("remaining_time", ln, f"出现按时限拒单的分支: {ln}")
        self.assertIn("remaining_capacity", g)

    def test_overdue_penalty_only_feeds_reward(self):
        env = _src("frontend/environment.py")
        start = env.index("def _reward(")
        end = env.index("\n    def ", start + 1)
        block = env[start:end]
        self.assertIn("overdue_penalty", block, "overdue_penalty 不再位于 _reward 内 ⇒ 去向变了，须重查")
        outside = env[:start] + env[end:]
        self.assertNotIn("overdue_penalty", outside.replace("overdue_initial_penalty", "")
                         .replace("overdue_step_penalty", ""),
                         "overdue_penalty 出现在 _reward 之外 ⇒ SLA 已进入别的通路")


if __name__ == "__main__":
    unittest.main(verbosity=2)
