"""Public package, scheduler and resource contracts for the modular runtime."""
import importlib
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from swarmbalance.contracts.scheduling import Scheduler
from swarmbalance.paths import DEFAULT_MAP, CONFIG_DIR, resolve_resource
from swarmbalance.scheduling.registry import create_scheduler, list_algorithms


class SchedulerContractTests(unittest.TestCase):
    def test_all_registered_algorithms_implement_one_contract(self):
        descriptors = list_algorithms()
        self.assertEqual([item.key for item in descriptors], ["greedy", "pso", "ga", "ortools"])
        for item in descriptors:
            if not item.available:
                continue
            with self.subTest(algorithm=item.key):
                scheduler = create_scheduler(item.key, num_drones=2, seed=17)
                self.assertIsInstance(scheduler, Scheduler)
                self.assertEqual(scheduler.act({"drone_positions": [[0, 0], [0, 0]],
                                                "drone_is_free": [True, True],
                                                "drone_free_masks": [[], []],
                                                "unassigned_tasks": []}, 0), {})

    def test_each_factory_call_creates_independent_scheduler_state(self):
        for name in ("pso", "ga"):
            first = create_scheduler(name, num_drones=2, seed=17)
            first.pending_buffer.append({"task_id": "old"})
            first.known_task_ids.add("old")
            second = create_scheduler(name, num_drones=2, seed=17)
            self.assertIsNot(first, second)
            self.assertEqual(second.pending_buffer, [])
            self.assertEqual(second.known_task_ids, set())

    def test_unknown_algorithm_is_rejected(self):
        with self.assertRaises(ValueError):
            create_scheduler("unknown", num_drones=2, seed=17)

    def test_optional_algorithm_unavailable_is_reported_consistently(self):
        with patch("swarmbalance.scheduling.registry._available", return_value=False):
            descriptor = next(item for item in list_algorithms() if item.key == "ortools")
            self.assertFalse(descriptor.available)
            self.assertTrue(descriptor.reason)
            with self.assertRaises(RuntimeError):
                create_scheduler("ortools", num_drones=2, seed=17)

    def test_runtime_synchronization_does_not_dispatch_or_mutate_input(self):
        scheduler = create_scheduler("pso", num_drones=2, seed=17)
        observation = {"drone_is_free": [False, True]}
        tasks = {0: [{"task_id": "in-flight", "source": [0, 0], "destination": [1, 1]}]}
        scheduler.synchronize(observation, tasks)
        self.assertEqual(scheduler.prev_is_free, [False, True])
        self.assertEqual(scheduler.active_task_ids, {0: "in-flight"})
        self.assertEqual(scheduler.pending_buffer, [])
        scheduler.active_tasks[0][0]["task_id"] = "changed"
        self.assertEqual(tasks[0][0]["task_id"], "in-flight")


class ResourceContractTests(unittest.TestCase):
    def test_legacy_map_path_initializes_a_real_session(self):
        from swarmbalance.application.session import SimSession
        with contextlib.redirect_stdout(io.StringIO()):
            session = SimSession(osm_path="frontend/data/map/part_of_yangpu.osm", episode_max_steps=1)
        self.assertTrue(session.env.drones)

    def test_default_resources_and_legacy_paths_resolve_to_same_file(self):
        self.assertTrue(DEFAULT_MAP.is_file())
        self.assertTrue((CONFIG_DIR / "schedulers.yaml").is_file())
        for old in ("data/map/part_of_yangpu.osm", "frontend/data/map/part_of_yangpu.osm"):
            self.assertEqual(resolve_resource(old), DEFAULT_MAP)
        self.assertEqual(resolve_resource("../config/import/tasks.csv"),
                         CONFIG_DIR / "import_templates/tasks.csv")

    def test_explicit_absolute_resource_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.osm"
            self.assertEqual(resolve_resource(path), path)

    def test_legacy_module_wrappers_share_canonical_module_identity(self):
        for old, new in (("console.sim_session", "swarmbalance.application.session"),
                         ("console.server", "swarmbalance.web.app"),
                         ("frontend.drone", "swarmbalance.simulation.entities.drone"),
                         ("backend_si.pso_scheduler", "swarmbalance.scheduling.pso")):
            with self.subTest(old=old):
                self.assertIs(importlib.import_module(old), importlib.import_module(new))


if __name__ == "__main__":
    unittest.main()
