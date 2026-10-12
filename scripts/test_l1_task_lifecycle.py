# -*- coding: utf-8 -*-
"""L1 lifecycle tests exercise the REAL Environment and a deliberately broken route.

RED first: on the unchanged parent, these test assertions fail.
GREEN: no completion without an actual source/destination service event;
status and counter agree after a REAL complete delivery.
"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["SWARM_BALANCE_SIM_CONFIG"] = str(ROOT / "config" / "simulation.json")
for p in (str(ROOT), str(ROOT / "frontend")):
    if p not in sys.path:
        sys.path.insert(0, p)


class L1TaskLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from environment import Environment
        from task import Task
        cls.Environment, cls.Task = Environment, Task
        cls.map_path = str(ROOT / "frontend/data/map/part_of_yangpu.osm")

    def new_world(self):
        env = self.Environment(self.map_path, episode_max_steps=3600)
        env.reset(seed=40907)
        env.task_generation_paused = True
        return env

    def select_assignable(self, env):
        for idx, drone in enumerate(env.drones):
            if not drone.is_free:
                continue
            for task in env.task_generator.unassigned_tasks:
                if float(task.get_weight()) <= min(
                    float(drone.carrying_capacity), 15.0
                ):
                    return idx, task
        self.fail("[L1_NO_ASSIGNABLE_TASK] cannot form test precondition")

    def test_01_no_phantom_completion_on_orphan_route(self):
        env = self.new_world()
        idx, task = self.select_assignable(env)
        env.step({idx: [task.task_id]})
        rows = env.drone_assignments.get(idx, [])
        if isinstance(rows, dict):
            rows = [rows]
        self.assertTrue(any(row["task"] is task for row in rows))
        self.assertEqual(task.status, "assigned")
        before = env.total_completed_tasks
        drone = env.drones[idx]
        # Simulate a broken intermediate state, NOT a public API transition.
        drone.scheduled_position = []
        drone.consumed_waypoints_this_step = []
        drone.is_free = True
        env._prev_free_status[idx] = False
        env.step({})
        print("[L1_ORPHAN_ACTUAL] before=%s after=%s status=%s" %
              (before, env.total_completed_tasks, task.status), flush=True)
        self.assertEqual(env.total_completed_tasks, before,
                         "[L1_PHANTOM_COMPLETION] a free drone is not delivery evidence")
        self.assertNotEqual(task.status, "completed")
        self.assertTrue(env.drone_assignments.get(idx),
                        "[L1_LOST_ASSIGNMENT] unfinished cargo/manifest silently discarded")
        self.assertFalse(drone.is_free,
                         "[L1_ORPHAN_REASSIGNMENT] orphaned assignment cannot be reused")

    def test_02_no_completion_before_pickup(self):
        env = self.new_world()
        idx, task = self.select_assignable(env)
        env.step({idx: [task.task_id]})
        assignment = next(row for row in env.drone_assignments[idx] if row["task"] is task)
        assignment["load_time"] = None
        before = env.total_completed_tasks
        ok = env._record_task_completion(idx, assignment)
        self.assertFalse(ok, "[L1_NO_PICKUP_WITNESS] no completion before pickup")
        self.assertEqual(env.total_completed_tasks, before)
        self.assertEqual(task.status, "assigned")

    def test_03_real_delivery_updates_terminal_status(self):
        env = self.new_world()
        idx, _ = self.select_assignable(env)
        drone = env.drones[idx]
        origin = tuple(drone.get_position())
        dest = None
        for delta in ((3.0, 0.0), (-3.0, 0.0), (0.0, 3.0), (0.0, -3.0)):
            cand = (origin[0] + delta[0], origin[1] + delta[1])
            if env.is_path_clear(origin, cand):
                dest = cand
                break
        self.assertIsNotNone(dest, "[L1_NO_CLEAR_SHORT_ROUTE] need a safe route")
        task = self.Task("l1_delivery_only", 0.5, origin, dest,
                         deadline=500.0, generation_time=0)
        env.task_generator.unassigned_tasks.append(task)
        env.total_generated_tasks += 1
        env.step({idx: [task.task_id]})
        for _ in range(15):
            if task.status == "completed" or env.total_completed_tasks >= 1:
                break
            env.step({})
        self.assertEqual(env.total_completed_tasks, 1,
                         "[L1_REAL_DELIVERY_NOT_RECORDED] real source and dest events")
        self.assertEqual(task.status, "completed",
                         "[L1_TERMINAL_STATUS] delivered task remains assigned")
        self.assertFalse(any(t is task for t in env.task_generator.unassigned_tasks))
        self.assertFalse(env.drone_assignments.get(idx),
                         "[L1_RESIDUAL_ASSIGNMENT] delivered task still assigned")
        self.assertAlmostEqual(float(drone.onboard_load_kg), 0.0, places=6)
        self.assertEqual(env.completed_task_log[-1]["task"], task)

    def test_04_duplicate_completed_task_cannot_increment_counter(self):
        env = self.new_world()
        idx, task = self.select_assignable(env)
        task.update_status("completed")
        before = env.total_completed_tasks
        accepted = env._record_task_completion(idx, {
            "task": task, "assigned_time": 0, "load_time": 1,
        })
        self.assertFalse(accepted, "[L1_DUPLICATE_COMPLETION] replay accepted")
        self.assertEqual(env.total_completed_tasks, before)

    def test_05_destination_without_pickup_is_not_delivery(self):
        env = self.new_world()
        idx, task = self.select_assignable(env)
        env.step({idx: [task.task_id]})
        drone = env.drones[idx]
        assignments = env.drone_assignments[idx]
        if isinstance(assignments, dict):
            assignments = [assignments]
        a = next(row for row in assignments if row["task"] is task)
        a["load_time"] = None
        before = env.total_completed_tasks
        # Only simulate a corrupted dest service event. No source was consumed.
        # Execute Environment.step, rather than a hand-written duplicate parser.
        drone.consumed_waypoints_this_step = []
        drone.update = lambda *args, **kwargs: (
            drone.consumed_waypoints_this_step.append(
                (task.destination[0], task.destination[1], "dest")))
        env.step({})
        self.assertEqual(env.total_completed_tasks, before)
        self.assertEqual(task.status, "assigned")
        self.assertTrue(env.drone_assignments.get(idx))
        self.assertEqual(float(drone.onboard_load_kg), 0.0)

    def test_06_orphan_with_picked_cargo_is_held(self):
        env = self.new_world()
        idx, _ = self.select_assignable(env)
        drone = env.drones[idx]
        pos = tuple(drone.get_position())
        destination = next(
            ((pos[0] + dx, pos[1] + dy)
             for dx, dy in ((3.0, 0.0), (-3.0, 0.0), (0.0, 3.0), (0.0, -3.0))
             if env.is_path_clear(pos, (pos[0] + dx, pos[1] + dy))),
            None)
        self.assertIsNotNone(destination)
        task = self.Task("l1_cargo_guard", 0.5, pos, destination, generation_time=0)
        env.task_generator.unassigned_tasks.append(task)
        env.total_generated_tasks += 1
        env.step({idx: [task.task_id]})
        self.assertEqual(task.status, "in_progress")
        onboard = float(drone.onboard_load_kg)
        self.assertAlmostEqual(onboard, 0.5, places=6)
        before = env.total_completed_tasks
        drone.scheduled_position = []
        drone.consumed_waypoints_this_step = []
        drone.is_free = True
        env._prev_free_status[idx] = False
        env.step({})
        self.assertEqual(env.total_completed_tasks, before)
        self.assertEqual(task.status, "in_progress")
        self.assertFalse(drone.is_free)
        self.assertAlmostEqual(float(drone.onboard_load_kg), onboard, places=6)
        self.assertTrue(env.drone_assignments.get(idx))
        self.assertGreaterEqual(float(drone.current_load), onboard)



if __name__ == "__main__":
    unittest.main(verbosity=2)
