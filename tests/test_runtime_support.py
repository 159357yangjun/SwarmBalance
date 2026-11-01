"""Regression coverage for shared configuration and CLI dependency checks."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config.loader import config_signature, get_episode_max_steps, get_shared_config
from console.dependencies import guard_or_exit


class ConfigurationTests(unittest.TestCase):
    def test_environment_override_and_explicit_path_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            override = Path(directory) / "override.json"
            explicit = Path(directory) / "explicit.json"
            override.write_text(json.dumps({"environment": {"episode_max_steps": 41}}))
            explicit.write_text(json.dumps({"environment": {"episode_max_steps": 83}}))
            with patch.dict(os.environ, {"SWARM_BALANCE_SIM_CONFIG": str(override)}):
                self.assertEqual(get_episode_max_steps(), 41)
                self.assertEqual(get_episode_max_steps(explicit), 83)
                self.assertEqual(get_shared_config(), {"environment": {"episode_max_steps": 41}})

    def test_signature_detects_same_size_same_timestamp_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "simulation.json"
            path.write_text('{"value": 1}')
            stat = path.stat()
            before = config_signature(path)
            path.write_text('{"value": 2}')
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            after = config_signature(path)
            self.assertEqual(before[0], after[0])
            self.assertNotEqual(before[1], after[1])

    def test_missing_or_invalid_episode_limit_never_uses_default(self):
        for config in (None, {}, {"environment": {}},
                       {"environment": {"episode_max_steps": 0}},
                       {"environment": {"episode_max_steps": -1}},
                       {"environment": {"episode_max_steps": "invalid"}}):
            with self.subTest(config=config), self.assertRaises(RuntimeError):
                get_episode_max_steps(config=config)


class DependencyGuardTests(unittest.TestCase):
    def test_available_dependency_succeeds_without_output(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(guard_or_exit(("json",)), 0)
        self.assertEqual(output.getvalue(), "")

    def test_missing_dependency_returns_three_and_names_package(self):
        # Use a real missing import to exercise the diagnostic end to end.
        output = io.StringIO()
        # guard_or_exit may reconfigure stdout; StringIO intentionally has no such method.
        with contextlib.redirect_stdout(output):
            self.assertEqual(guard_or_exit(("swarmbalance_missing_test_dependency",)), 3)
        self.assertIn("swarmbalance_missing_test_dependency", output.getvalue())
        self.assertIn("缺少依赖", output.getvalue())


if __name__ == "__main__":
    unittest.main()
