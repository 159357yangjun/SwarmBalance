"""运行时事故注入的轻量 smoke tests。

通过 stub 掉 osmnx，直接构造 Environment.__new__，不加载真实 OSM。
验证故障停飞回收任务、机巢关闭触发改道两条核心链路。
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
for p in (str(ROOT), str(FRONTEND)):
    if p not in sys.path:
        sys.path.insert(0, p)

from console import _preflight

_preflight.require("numpy", "shapely", gated_in="console/test_environment_incidents.py")

sys.modules.setdefault("osmnx", types.ModuleType("osmnx"))
# #70-P1 判据②：内核改走按路径加载器，不在模块顶层 `import environment`。
# 原先这里还会"发现 sys.modules['environment'] 是假桩就把它删掉再按名字重导"——
# 那是**替全进程**决定"environment 这个名字指向哪份代码"，正是要消除的顺序耦合源。
# 按路径加载得到的模块不进 sys.modules，本模块自造一份真内核即可，与别人的桩互不干扰。
_env_kernel = _preflight.load_kernel_environment()[0]
Environment = _env_kernel.Environment
from charging_station import ChargingStation  # noqa: E402
from drone import Drone  # noqa: E402
from task import Task  # noqa: E402


class _Generator:
    def __init__(self):
        self.unassigned_tasks = []


def make_env():
    env = Environment.__new__(Environment)
    env.charging_stations = [
        ChargingStation(0, 0.0, 0.0, berths=1),
        ChargingStation(1, 1000.0, 0.0, berths=1),
    ]
    drone = Drone(10.0, 0.0, drone_id="D0", carrying_capacity=5)
    drone.known_stations = env.charging_stations
    env.drones = [drone]
    env._nest_waiting = {0: [], 1: []}
    env.drone_assignments = {}
    env.task_generator = _Generator()
    env.drone_chain_len = {0: 0}
    env._prev_free_status = {0: True}
    env.current_time = 10.0
    env.task_generation_paused = False
    return env, drone


class EnvironmentIncidentTests(unittest.TestCase):
    def test_drone_fault_requeues_incomplete_task(self):
        env, drone = make_env()
        task = Task(
            task_id="T1", weight=2.0, source=(0.0, 0.0), destination=(100.0, 0.0),
            deadline=100.0, priority=3, generation_time=0.0,
        )
        drone.schedule_route([(0.0, 0.0, "source"), (100.0, 0.0, "dest")], "T1")
        drone.add_load(2.0)
        env.drone_assignments = {0: [{"task": task, "assigned_time": 0.0, "start_time": 0.0, "load_time": None}]}

        result = env.set_drone_out_of_service("D0", True, "test")
        self.assertEqual(result["requeued_task_ids"], ["T1"])
        self.assertTrue(drone.out_of_service)
        self.assertFalse(drone.scheduled_position)
        self.assertEqual(env.task_generator.unassigned_tasks, [task])
        self.assertNotIn(0, env.drone_assignments)

    def test_nest_close_reroutes_waiting_drone(self):
        env, drone = make_env()
        drone.awaiting_berth = True
        drone.berth_station_id = 0
        drone.awaiting_since = 5.0
        drone.is_free = False
        env._nest_waiting = {0: [0], 1: []}

        result = env.set_station_closed(0, True, "maintenance")
        self.assertTrue(env.charging_stations[0].closed)
        self.assertEqual(result["rerouted_drone_ids"], ["D0"])
        self.assertEqual(drone.scheduled_position, [(1000.0, 0.0)])
        self.assertFalse(drone.awaiting_berth)

    def test_last_open_nest_cannot_be_closed(self):
        env, _ = make_env()
        env.charging_stations[1].closed = True
        with self.assertRaises(ValueError):
            env.set_station_closed(0, True, "maintenance")

    def test_manual_charge_request_preserves_active_route(self):
        env, drone = make_env()
        drone.scheduled_position = [(200.0, 0.0, "source"), (400.0, 0.0, "dest")]
        drone.executing_task_id = "T-active"
        drone.is_free = False
        result = env.request_drone_charge("D0", station_id=1)
        self.assertTrue(result["changed"])
        self.assertTrue(result["resume_tasks_after_charge"])
        self.assertEqual(drone._suspended_route[0][:2], (200.0, 0.0))
        self.assertEqual(drone.scheduled_position, [(1000.0, 0.0)])
        self.assertTrue(drone._manual_charge_requested)

    def test_task_stream_can_pause_and_resume(self):
        env, _ = make_env()
        self.assertFalse(env.task_generation_paused)
        self.assertTrue(env.set_task_generation_paused(True)["changed"])
        self.assertTrue(env.task_generation_paused)
        self.assertTrue(env.set_task_generation_paused(False)["changed"])
        self.assertFalse(env.task_generation_paused)

    def test_pending_task_can_be_promoted_to_emergency(self):
        env, _ = make_env()
        task = Task(
            task_id="T-edit", weight=1.0, source=(0.0, 0.0), destination=(100.0, 0.0),
            deadline=100.0, priority=1, generation_time=0.0, category="normal",
        )
        env.task_generator.unassigned_tasks.append(task)
        result = env.update_pending_task("T-edit", priority=3, deadline_offset=30, category="urgent")
        self.assertEqual(task.priority, 3)
        self.assertEqual(task.deadline, 40.0)
        self.assertEqual(task.category, "urgent")
        self.assertIn("priority", result["changed"])


if __name__ == "__main__":
    unittest.main()
