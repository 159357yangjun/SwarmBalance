# -*- coding: utf-8 -*-
"""#69-H R7 端到端夹具：seed 102 经生产入口，task_44 必须真送达且无 cleanup_no_svc。

历史注记（D-iv，2026-10-08）：本文件原有 `ConsumedPrefixRule` 一组纯函数面 A1–A5，
直接喂已删除的 `Environment._consumed_prefix_len(prev,curr)`（后缀启发式）。#69-H3 采纳
"执行器真正 pop 服务航点＝唯一权威证人"后，该反推函数连同其形状夹具一并退役；
对应的形状边界改由 console/test_h3_real_pop_events.py 的 T1–T6（真事件两面）覆盖。
此处只保留与谓词无关、跨机制恒成立的端到端判据。
"""
from __future__ import annotations
import os, pathlib, sys, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class Task44EndToEnd(unittest.TestCase):
    """端到端：seed 102 经生产 worker 入口，task_44 必须有 DESTINATION_REACHED 且无 cleanup_no_svc。"""

    def test_B_seed102_task44_delivered(self):
        os.environ["SWARM_BALANCE_SIM_CONFIG"] = str((ROOT / "config" / "simulation.json").resolve())
        for p in (str(ROOT), str(ROOT / "frontend")):
            if p not in sys.path:
                sys.path.insert(0, p)
        from environment import Environment
        from greedy.scheduler import greedy_action_from_observation
        import consistency_observer as co
        env = Environment(str(ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm"), episode_max_steps=3600)
        obs = env.reset(seed=102)
        ob = co.ConsistencyObserver(); co.install(env, ob)
        done = False
        while not done:
            obs, _, done, _ = env.step(greedy_action_from_observation(obs))
        comp = {e["task_id"] for e in ob.events if e["kind"] == "TASK_COMPLETION_RECORDED"}
        reach = {e["task_id"] for e in ob.events if e["kind"] == "DESTINATION_REACHED"}
        self.assertEqual(comp - reach, set(),
                         f"[R7_STILL_PRESENT] 计入完成却无送达证人的任务={sorted(comp - reach)}")
        self.assertIn("task_44", reach, "[R7_TASK44_NOT_DELIVERED]")


if __name__ == "__main__":
    unittest.main(verbosity=2)
