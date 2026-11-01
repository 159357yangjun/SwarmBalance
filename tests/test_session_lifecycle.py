"""Real-map regression for the extracted session and environment services."""
import contextlib
import io
import json
import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from swarmbalance.application.session import SimSession
from swarmbalance.application import checkpoints, snapshots
from swarmbalance.simulation import incidents, handoff
from swarmbalance.paths import CONFIG_DIR


class SessionLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with contextlib.redirect_stdout(io.StringIO()):
            cls.session = SimSession(episode_max_steps=50)

    def setUp(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.session.reset("ga", seed=123)
        self.session.env.task_generator.unassigned_tasks.clear()
        self.session.env.total_generated_tasks = 0
        self.session.env.generated_task_times = []
        self.session.obs = self.session.env._obs()
        self.session._checkpoints.clear()

    def test_snapshot_and_checkpoint_restore_executing_state_and_rng(self):
        session = self.session
        session.inject_task(task_id="lifecycle", weight=1, volume=0.1, deadline_offset=300)
        session.step()
        session.save_checkpoint("saved")
        random_numbers = (random.random(), float(np.random.random()))
        session.step()
        expected = session.env.get_statistics()
        session.load_checkpoint("saved")
        self.assertEqual((random.random(), float(np.random.random())), random_numbers)
        restored = session.step()
        self.assertEqual(session.env.get_statistics(), expected)
        self.assertEqual(restored["step"], 2)
        self.assertTrue(restored["drones"])
        self.assertTrue(restored["task_catalog"])

    def test_checkpoint_slot_eviction_replacement_and_missing_name(self):
        for index in range(5):
            self.session.save_checkpoint(str(index))
        replaced = self.session.save_checkpoint("2")
        self.assertEqual(replaced["覆盖"], "2")
        self.assertIsNone(replaced["淘汰"])
        evicted = self.session.save_checkpoint("5")
        self.assertEqual(evicted["淘汰"], "0")
        self.assertEqual(len(self.session.list_checkpoints()), 5)
        with self.assertRaises(ValueError):
            self.session.load_checkpoint("missing")

    def test_drone_incident_and_recovery_preserve_one_environment(self):
        session = self.session
        env = session.env
        drone_id = str(env.drones[0].drone_id)
        session.set_drone_out_of_service(drone_id, True)
        self.assertTrue(env.drones[0].out_of_service)
        session.set_drone_out_of_service(drone_id, False)
        self.assertFalse(env.drones[0].out_of_service)
        self.assertIs(session.env, env)
        self.assertEqual(len(session.snapshot()["drones"]), len(env.drones))

    def test_task_candidate_explanations_and_demo_actions_keep_working(self):
        session = self.session
        session.inject_task(task_id="candidate", weight=1, volume=0.1, deadline_offset=300)
        candidates = session.task_candidates("candidate", limit=2)
        self.assertTrue(candidates)
        session.set_demo_context("regression", "regression", [{"action": "charge_two_drones"}])
        snapshot = session.advance_demo()
        self.assertEqual(snapshot["demo"]["cursor"], 1)

    def test_rebuild_reads_override_and_rejects_incompatible_checkpoint(self):
        session = self.session
        session.save_checkpoint("old-generation")
        config = json.loads((CONFIG_DIR / "simulation.json").read_text(encoding="utf-8"))
        config["environment"]["episode_max_steps"] = 71
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "simulation.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            try:
                with patch.dict(os.environ, {"SWARM_BALANCE_SIM_CONFIG": str(path)}):
                    with contextlib.redirect_stdout(io.StringIO()):
                        session.rebuild()
                    self.assertEqual(session.episode_max_steps, 71)
                    self.assertEqual(session.env.episode_max_steps, 71)
                    with self.assertRaises(ValueError):
                        session.load_checkpoint("old-generation")
            finally:
                with contextlib.redirect_stdout(io.StringIO()):
                    session.rebuild()


if __name__ == "__main__":
    unittest.main()
