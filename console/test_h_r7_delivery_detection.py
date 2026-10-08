# -*- coding: utf-8 -*-
"""#69-H R7 两面夹具：同一 env.step 内"弹 dest + 追加 nest"必须被记为送达。

判据形状（不依赖具体 seed）：直接对 Environment._consumed_prefix_len 这个纯函数喂三种转移，
钉住它"补同步步漏检、不误伤改道、不过计"三条边界。端到端那半（seed 102 task_44）由 test_B 用真 worker 入口跑。
"""
from __future__ import annotations
import os, pathlib, sys, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ConsumedPrefixRule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["SWARM_BALANCE_SIM_CONFIG"] = str((ROOT / "config" / "simulation.json").resolve())
        for p in (str(ROOT), str(ROOT / "frontend")):
            if p not in sys.path:
                sys.path.insert(0, p)
        from environment import Environment
        cls.Env = Environment   # 通过类属性访问 staticmethod，避免被重新绑定成实例方法

    def f(self, prev, curr):
        return type(self).Env._consumed_prefix_len(prev, curr)

    # ---- A. 纯函数三面：正常后缀 / pop+append服务点 / 整体改道 ----
    def test_A1_normal_suffix_pop(self):
        # ['source','dest'] -> ['dest']：弹出队首 source，curr 是 prev[1:] 后缀 ⇒ k=1（只算 source）
        self.assertEqual(self.f([('a', 1, 'source'), ('b', 2, 'dest')], [('b', 2, 'dest')]), 1)

    def test_A2_service_prefix_not_overcount(self):
        # 关键防过计：['source','dest']->['dest'] 不得返回 2（否则取货重复触发）。
        self.assertEqual(self.f([(0, 0, 'source'), (1, 1, 'dest')], [(1, 1, 'dest')]), 1)

    def test_A3_pop_and_append_same_step(self):
        # task_44 形态：prev=['dest']，同帧弹掉 dest 又追加仓库 '?' 点 ⇒ curr 非后缀，但队首是已消失的服务点 ⇒ k=1
        prev = [(9.0, 9.0, 'dest')]
        curr = [(50.0, 50.0, '?')]   # 换电/仓库单点，坐标与 dest 不同
        self.assertEqual(self.f(prev, curr), 1)

    def test_A4_reroute_not_counted(self):
        # 整体改道：队首是非服务点 '?'（如已在去机巢路上），curr 换成别的 ⇒ k=0，不入送达账
        prev = [(1.0, 1.0, '?')]
        curr = [(2.0, 2.0, '?')]
        self.assertEqual(self.f(prev, curr), 0)

    def test_A5_service_still_in_curr_is_not_consumed(self):
        # 服务点仍在 curr 里出现（没真被弹出）⇒ 不得计为消费（防把在飞误判成送达）
        prev = [(3.0, 3.0, 'dest'), (4.0, 4.0, 'source')]
        curr = [(3.0, 3.0, 'dest')]   # dest 还在原位
        self.assertEqual(self.f(prev, curr), 0)


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
