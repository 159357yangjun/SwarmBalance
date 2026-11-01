"""One episode runner and one command dispatcher for canonical and legacy entrypoints."""
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest

from swarmbalance import __main__ as commands
from swarmbalance.application.evaluation import run_one_episode
from swarmbalance.cli import evaluate, legacy_ga, legacy_pso, legacy_ortools, legacy_greedy
from swarmbalance.paths import DEFAULT_MAP, PROJECT_ROOT


class EvaluationEntrypointTests(unittest.TestCase):
    def test_legacy_absolute_scripts_work_outside_project_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            for relative in ("frontend/evaluate_metrics.py", "frontend/run_ga.py",
                             "frontend/greedy/run_greedy.py", "console/run.py"):
                with self.subTest(script=relative):
                    process = subprocess.run([sys.executable, "-B", "-X", "utf8", str(PROJECT_ROOT / relative), "--help"],
                                             cwd=directory, capture_output=True, text=True, encoding="utf-8", timeout=30)
                    self.assertEqual(process.returncode, 0, process.stdout + process.stderr)

    def test_flat_legacy_greedy_package_import_from_frontend_directory(self):
        process = subprocess.run([sys.executable, "-B", "-c", "import greedy.scheduler; import environment"],
                                 cwd=PROJECT_ROOT / "frontend", capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)

    def test_command_help_routes_to_the_requested_entrypoint(self):
        for command in ("console", "evaluate", "selfcheck"):
            with self.subTest(command=command), contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(SystemExit) as raised:
                    commands.main([command, "--help"])
                self.assertEqual(raised.exception.code, 0)
                self.assertIn("usage:", output.getvalue())

    def test_canonical_and_legacy_episode_entrypoints_share_results(self):
        # Short real runs exercise factory construction and execution rather than mocking the loop.
        for policy, entrypoint in (("ga", legacy_ga), ("pso", legacy_pso), ("ortools", legacy_ortools), ("greedy", legacy_greedy)):
            with self.subTest(policy=policy), contextlib.redirect_stdout(io.StringIO()):
                canonical = run_one_episode(DEFAULT_MAP, 1, policy, 101)
                legacy = entrypoint.run_one_episode(DEFAULT_MAP, 1, 101)
                legacy.pop("_scheduler_stats", None)
                self.assertEqual(canonical, legacy)


if __name__ == "__main__":
    unittest.main()
