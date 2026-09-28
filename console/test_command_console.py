"""控制台解释层的轻量单元测试。

不加载 OSM 地图：通过假的 environment 模块和最小 fake objects 验证
任务生命周期 catalog、候选无人机解释排名等纯数据逻辑。
"""
from __future__ import annotations

import importlib
import random
import sys
import types
import unittest
from collections import deque

import numpy as np


# SimSession 模块顶层只需要 environment.Environment 符号；这里替代真实 OSM 环境，
# 让该测试在未安装 osmnx 的 CI / 编辑环境也可执行。
_fake_env_module = types.ModuleType("environment")
_fake_env_module.Environment = object
_had_real_env = "environment" in sys.modules
if not _had_real_env:
    sys.modules["environment"] = _fake_env_module

sim_session = importlib.import_module("console.sim_session")
SimSession = sim_session.SimSession


def tearDownModule():
    """本模块跑完后把 environment 换回真实实现。

    上面这个桩是进程级的：sim_session 在 import 时就把 ``_env_module`` 绑到了假模块上，
    于是同一进程里**之后**运行的任何测试只要构造真实 SimSession，就会执行
    ``env_cls(...)`` 而 env_cls 是 ``object``，报 "TypeError: object() takes no arguments"。
    桩只对需要它的这些用例有意义，不该泄漏给别的测试模块。
    """
    if _had_real_env:
        return
    try:
        sys.modules.pop("environment", None)
        import environment as _real_env  # frontend/ 已由 sim_session 加入 sys.path
        sim_session._env_module = _real_env
    except Exception:  # noqa: BLE001 - 缺依赖时保留桩，本模块仍可运行
        sys.modules["environment"] = _fake_env_module


class FakeTask:
    def __init__(self, task_id="task_1", weight=2.0, source=(100.0, 0.0),
                 destination=(200.0, 0.0), deadline=120.0, priority=3,
                 volume=0.2, category="urgent", generation_time=0.0):
        self.task_id = task_id
        self.weight = weight
        self.source = source
        self.destination = destination
        self.deadline = deadline
        self.priority = priority
        self.volume = volume
        self.category = category
        self.generation_time = generation_time

    def get_weight(self): return self.weight
    def get_priority(self): return self.priority
    def get_deadline(self): return self.deadline


class FakeDrone:
    def __init__(self, drone_id, x=0.0, capacity=5.0, speed=100.0,
                 battery=3000.0, battery_capacity=3000.0, consumption=0.5,
                 drone_type="standard_cargo"):
        self.drone_id = drone_id
        self.x, self.y = x, 0.0
        self.carrying_capacity = capacity
        self.current_load = 0.0
        self.speed = speed
        self.current_battery = battery
        self.battery_capacity = battery_capacity
        self.battery_consumption_base = consumption
        self.battery_load_penalty_factor = 0.3
        self.scheduled_position = []
        self.is_charging = False
        self.awaiting_berth = False
        self.drone_type = drone_type
        self.executing_task_id = None
        self.out_of_service = False
        self.out_of_service_reason = None


class FakeGenerator:
    def __init__(self, tasks):
        self.unassigned_tasks = tasks


class FakeEnv:
    pass


def make_session(tasks=None, drones=None):
    env = FakeEnv()
    env.current_time = 0.0
    env.task_generator = FakeGenerator(tasks or [])
    env.drones = drones or []
    env.drone_assignments = {}
    env.completed_tasks = []
    s = SimSession.__new__(SimSession)
    s.env = env
    s._completed_task_owner = {}
    s.algorithm = "greedy"
    s.seed = 100
    s.num_drones = len(env.drones)
    s.step_count = 0
    s._events = deque(maxlen=300)
    s._event_seq = 0
    s._history = deque(maxlen=360)
    s._demo = {"active": False, "key": None, "name": None, "script": [], "cursor": 0}
    s._checkpoints = {}
    s.trajectories = [[] for _ in env.drones]
    s.done = False
    s.scheduler = None
    s.obs = None
    env.charging_stations = []
    env._nest_waiting = {}
    return s


class CommandConsoleTests(unittest.TestCase):
    def test_pending_task_appears_in_lifecycle_catalog(self):
        task = FakeTask()
        s = make_session([task], [FakeDrone("drone_0")])
        rows = s._task_catalog_snapshot()
        self.assertEqual(rows[0]["id"], "task_1")
        self.assertEqual(rows[0]["status"], "pending")
        self.assertIsNone(rows[0]["assigned_drone_id"])

    def test_assigned_task_overrides_pending_status(self):
        task = FakeTask()
        drone = FakeDrone("drone_0")
        drone.executing_task_id = task.task_id
        s = make_session([], [drone])
        s.env.drone_assignments = {0: [{"task": task, "assigned_time": 1.0, "load_time": 2.0}]}
        rows = s._task_catalog_snapshot()
        self.assertEqual(rows[0]["status"], "in_progress")
        self.assertEqual(rows[0]["assigned_drone_id"], "drone_0")
        self.assertEqual(rows[0]["chain_order"], 1)

    def test_candidate_ranking_filters_payload_infeasible_drone(self):
        task = FakeTask(weight=6.0, deadline=300.0)
        light = FakeDrone("light", capacity=3.0, speed=150.0, drone_type="light_express")
        heavy = FakeDrone("heavy", capacity=12.0, speed=100.0, drone_type="heavy_cargo")
        s = make_session([task], [light, heavy])
        result = s.task_candidates(task.task_id, limit=5)
        self.assertEqual(result["status"], "pending")
        by_id = {r["drone_id"]: r for r in result["candidates"]}
        self.assertFalse(by_id["light"]["feasible"])
        self.assertIn("载重不足", by_id["light"]["blockers"])
        self.assertTrue(by_id["heavy"]["payload_ok"])
        self.assertEqual(result["candidates"][0]["drone_id"], "heavy")

    def test_completed_task_keeps_owner_for_inspector(self):
        task = FakeTask(task_id="done")
        s = make_session([], [FakeDrone("drone_0")])
        s._completed_task_owner["done"] = {"drone_id": "drone_0", "drone_idx": 0}
        # 写的是 completed_task_log 而不是 completed_tasks：后者是本步的临时缓冲，
        # _compute_reward() 在每步末尾就把它 clear() 掉了，快照时刻永远是空的。
        s.env.completed_task_log = [{
            "task": task, "assigned_time": 1.0, "load_time": 2.0,
            "completion_time": 90.0, "delay": 0.0,
        }]
        row = s._task_catalog_snapshot()[0]
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["assigned_drone_id"], "drone_0")
        self.assertTrue(row["on_time"])

    def test_offline_drone_is_not_a_feasible_candidate(self):
        task = FakeTask(weight=2.0, deadline=300.0)
        drone = FakeDrone("drone_offline", capacity=8.0, speed=150.0)
        drone.out_of_service = True
        s = make_session([task], [drone])
        row = s.task_candidates(task.task_id, limit=5)["candidates"][0]
        self.assertFalse(row["feasible"])
        self.assertIn("故障停飞", row["blockers"])

    def test_drone_incident_emits_fault_and_requeue_events(self):
        drone = FakeDrone("drone_0")
        s = make_session([], [drone])
        s.env._obs = lambda: {"drone_is_free": [False]}
        s.env.set_drone_out_of_service = lambda drone_id, out_of_service=True, reason="": {
            "drone_idx": 0, "drone_id": "drone_0", "requeued_task_ids": ["task_r"], "changed": True
        }
        s.snapshot = lambda: {"events": list(s._events)}
        result = s.set_drone_out_of_service("drone_0", True, "test fault")
        kinds = [e["kind"] for e in result["events"]]
        self.assertIn("drone_fault", kinds)
        self.assertIn("task_requeued", kinds)


    def test_task_stream_control_emits_event(self):
        s = make_session([], [FakeDrone("drone_0")])
        s.env.task_generation_paused = False
        s.env.set_task_generation_paused = lambda paused=True: {"paused": bool(paused), "changed": True}
        s.env._obs = lambda: {"drone_is_free": [True]}
        s.snapshot = lambda: {"events": list(s._events)}
        result = s.set_task_generation_paused(True)
        self.assertIn("task_stream_paused", [e["kind"] for e in result["events"]])

    def test_pending_task_update_emits_event(self):
        task = FakeTask(task_id="task_edit")
        s = make_session([task], [FakeDrone("drone_0")])
        s.env._obs = lambda: {"drone_is_free": [True]}
        s.env.update_pending_task = lambda task_id, **kwargs: {"task_id": task_id, "changed": {"priority": [1, 3]}}
        s.snapshot = lambda: {"events": list(s._events)}
        result = s.update_pending_task("task_edit", priority=3)
        self.assertIn("task_updated", [e["kind"] for e in result["events"]])

    def test_manual_charge_request_emits_event(self):
        s = make_session([], [FakeDrone("drone_0")])
        s.env._obs = lambda: {"drone_is_free": [False]}
        s.env.request_drone_charge = lambda drone_id, station_id=None: {
            "drone_id": drone_id, "station_id": "1", "changed": True, "resume_tasks_after_charge": True
        }
        s.snapshot = lambda: {"events": list(s._events)}
        result = s.request_drone_charge("drone_0")
        self.assertIn("drone_charge_requested", [e["kind"] for e in result["events"]])

    def test_runtime_checkpoint_restores_dynamic_state(self):
        drone = FakeDrone("drone_0", x=12.0)
        s = make_session([], [drone])
        s.env.current_time = 25.0
        s.trajectories = [[[0.0, 0.0], [12.0, 0.0]]]
        s.snapshot = lambda: {"time": float(s.env.current_time)}
        saved = s.save_checkpoint("before_fault")
        self.assertEqual(saved["checkpoints"][0]["name"], "before_fault")

        s.env.current_time = 99.0
        s.env.drones[0].x = 888.0
        s.trajectories[0].append([888.0, 0.0])
        restored = s.load_checkpoint("before_fault")
        self.assertEqual(s.env.current_time, 25.0)
        self.assertEqual(s.env.drones[0].x, 12.0)
        self.assertEqual(restored["trajectories_restore"], [[[0.0, 0.0], [12.0, 0.0]]])

    def test_runtime_checkpoint_restores_python_and_numpy_rng(self):
        s = make_session([], [FakeDrone("drone_0")])
        s.snapshot = lambda: {"time": float(s.env.current_time)}
        random.seed(12345)
        np.random.seed(12345)
        s.save_checkpoint("rng")
        expected_py = [random.random() for _ in range(3)]
        expected_np = np.random.random(3).tolist()

        # 扰动全局 RNG 后再恢复，下一段随机序列应与保存节点完全一致。
        random.seed(999)
        np.random.seed(999)
        s.load_checkpoint("rng")
        self.assertEqual([random.random() for _ in range(3)], expected_py)
        self.assertTrue(np.allclose(np.random.random(3), expected_np))

    def test_health_snapshot_flags_urgent_and_offline(self):
        task = FakeTask(priority=3)
        drone = FakeDrone("drone_offline")
        drone.out_of_service = True
        s = make_session([task], [drone])
        health = s._health_snapshot()
        self.assertEqual(health["level"], "critical")
        self.assertEqual(health["urgent_pending"], 1)
        self.assertEqual(health["offline_drones"], 1)

    def test_demo_snapshot_exposes_next_action(self):
        s = make_session([], [FakeDrone("drone_0")])
        s._demo = {
            "active": True, "key": "demo", "name": "Demo", "cursor": 1,
            "script": [{"label": "first"}, {"label": "second", "action": "step", "count": 1}],
        }
        d = s._demo_snapshot()
        self.assertEqual(d["cursor"], 1)
        self.assertEqual(d["next"]["label"], "second")
        self.assertFalse(d["completed"])

    def test_rebuild_refreshes_episode_max_steps_from_config(self):
        from unittest.mock import patch
        s = SimSession.__new__(SimSession)
        s.osm_path = "fake.osm"
        s.episode_max_steps = 2000
        s.algorithm = "greedy"
        s.seed = 100
        s._checkpoints = {}
        created = {}

        class Env:
            def __init__(self, path, visualize=False, episode_max_steps=0):
                created["steps"] = episode_max_steps
                self.drones = [object(), object()]

        s.reset = lambda algorithm, seed: {"algorithm": algorithm, "seed": seed}
        with patch.object(sim_session, "reload_sim_modules", lambda: None), \
             patch.object(sim_session, "get_shared_config", return_value={"environment": {"episode_max_steps": 4321}}), \
             patch.object(sim_session._env_module, "Environment", Env):
            result = s.rebuild()
        self.assertEqual(s.episode_max_steps, 4321)
        self.assertEqual(created["steps"], 4321)
        self.assertEqual(s.num_drones, 2)
        self.assertEqual(result["algorithm"], "greedy")


if __name__ == "__main__":
    unittest.main()
