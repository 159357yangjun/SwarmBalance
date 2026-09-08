"""chain_codec 最小单测集：验证任务链解码与局部搜索的核心不变式。

运行方式（二选一，均零额外依赖）：
    python -m unittest tests.test_chain_codec -v
    python tests/test_chain_codec.py

覆盖：
  - 任务守恒（解码后 已分配 + 未分配 == 总任务数）
  - 硬约束不变式（链长 ≤ max_chain_tasks、单链载重 ≤ min(capacity, max_total_weight)）
  - 无重复分配
  - improve_chain 不改变任务集合、里程不增
  - relocate 不改变任务集合
"""

import math
import random
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scheduling.chain_codec import (  # noqa: E402
    ChainDecodeConfig,
    greedy_split_decode,
    improve_chain,
    relocate_between_chains,
)


def _make_world(seed=42, n_tasks=16, n_drones=4):
    random.seed(seed)
    cap = 30.0
    drones = [{
        'index': i,
        'position': (358000.0 + i * 150, 3462400.0),
        'ready_time': 0.0,
        'capacity': cap,
        'speed': 17.0,
        'battery_capacity': 1600.0,
        'battery': 1600.0,
        'battery_consumption_base': 0.06,
        'battery_load_penalty_factor': 0.33,
        'is_charging': False,
        'charging_stations': [{'position': [358000.0, 3462400.0],
                               'swap_time_seconds': 180}],
    } for i in range(n_drones)]
    tasks = [{
        'task_id': f'T{j}',
        'source': (357900.0 + random.uniform(0, 900),
                   3462300.0 + random.uniform(0, 800)),
        'destination': (357900.0 + random.uniform(0, 900),
                        3462300.0 + random.uniform(0, 800)),
        'deadline': 2000 + j * 30,
        'priority': random.randint(1, 3),
        'weight': random.choice([1, 2, 3, 6, 9, 14]),
    } for j in range(n_tasks)]
    return drones, tasks


class TestGreedySplitDecode(unittest.TestCase):
    def setUp(self):
        self.drones, self.tasks = _make_world()
        self.cfg = ChainDecodeConfig(max_chain_tasks=3, max_total_weight=30.0,
                                     local_search=False, relocate_between=False)

    def test_task_conservation(self):
        """解码后 已分配 + 未分配 == 任务总数，不得丢失或凭空多出。"""
        for _ in range(50):
            perm = list(range(len(self.tasks)))
            random.shuffle(perm)
            sol = greedy_split_decode(perm, self.drones, self.tasks, 0.0, self.cfg)
            assigned = sum(len(c) for c in sol.chains)
            self.assertEqual(assigned + len(sol.unassigned), len(self.tasks))

    def test_no_duplicate_assignment(self):
        for _ in range(50):
            perm = list(range(len(self.tasks)))
            random.shuffle(perm)
            sol = greedy_split_decode(perm, self.drones, self.tasks, 0.0, self.cfg)
            flat = [t for ch in sol.chains for t in ch]
            self.assertEqual(len(flat), len(set(flat)))

    def test_chain_length_and_weight_constraints(self):
        for _ in range(50):
            perm = list(range(len(self.tasks)))
            random.shuffle(perm)
            sol = greedy_split_decode(perm, self.drones, self.tasks, 0.0, self.cfg)
            for ch in sol.chains:
                self.assertLessEqual(len(ch), self.cfg.max_chain_tasks)
                w = sum(self.tasks[t]['weight'] for t in ch)
                self.assertLessEqual(w, self.cfg.max_total_weight + 1e-9)


class TestImproveChain(unittest.TestCase):
    def setUp(self):
        self.drones, self.tasks = _make_world()
        self.cfg = ChainDecodeConfig(max_chain_tasks=3, max_total_weight=30.0)

    def _chain_distance(self, seq, start):
        d, pos = 0.0, start
        for t in seq:
            s = tuple(self.tasks[t]['source'])
            dd = tuple(self.tasks[t]['destination'])
            d += math.hypot(pos[0] - s[0], pos[1] - s[1])
            d += math.hypot(s[0] - dd[0], s[1] - dd[1])
            pos = dd
        return d

    def test_preserves_tasks_and_not_worse(self):
        start = (358000.0, 3462400.0)
        for _ in range(100):
            seq = list(range(len(self.tasks)))
            random.shuffle(seq)
            seq = seq[:6]
            before = self._chain_distance(seq, start)
            improved = improve_chain(seq, self.drones[0], self.tasks, self.cfg)
            after = self._chain_distance(improved, start)
            self.assertEqual(sorted(improved), sorted(seq))
            self.assertLessEqual(after, before + 1e-6)


class TestRelocate(unittest.TestCase):
    def test_preserves_task_set(self):
        drones, tasks = _make_world()
        cfg = ChainDecodeConfig(max_chain_tasks=3, max_total_weight=30.0,
                                local_search=True, relocate_between=True)
        sol = greedy_split_decode(list(range(len(tasks))), drones, tasks, 0.0, cfg)
        orig = set(t for ch in sol.chains for t in ch)
        new_chains = relocate_between_chains(sol, drones, tasks, cfg)
        new = set(t for ch in new_chains for t in ch)
        self.assertEqual(orig, new)


if __name__ == "__main__":
    unittest.main(verbosity=2)
