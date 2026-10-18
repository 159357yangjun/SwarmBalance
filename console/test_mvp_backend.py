"""MVP-01 项目持久化与真实子进程集成检查。"""
import importlib
import json
from pathlib import Path
import tempfile
import unittest


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        try:
            module = importlib.import_module("console.mvp_service")
        except ModuleNotFoundError:
            self.fail("MVP 项目服务尚未实现")
        self.Service = module.MVPService
        self.service = self.Service(Path(self.temp.name))

    def tearDown(self):
        if hasattr(self, "service"):
            self.service.shutdown()
        self.temp.cleanup()

    def test_create_update_and_reopen(self):
        project = self.service.create_project({"name": "真实项目"})
        self.assertEqual(project["name"], "真实项目")
        self.assertIn("charging_stations", project["simulation"])
        project["name"] = "改名"
        project["simulation"]["environment"]["episode_max_steps"] = 20
        self.service.update_project(project["project_id"], project)
        reopened = self.Service(Path(self.temp.name)).get_project(project["project_id"])
        self.assertEqual(reopened["name"], "改名")
        self.assertEqual(reopened["simulation"]["environment"]["episode_max_steps"], 20)
        self.assertEqual(len(self.service.list_projects()), 1)

    def test_reject_invalid_inputs_without_saving(self):
        for patch in ({"name": " "}, {"name": "x", "algorithm": "typo"},
                      {"name": "x", "seed": -1},
                      {"name": "x", "simulation": {"environment": {"episode_max_steps": 0}}},
                      {"name": "x", "simulation": {"environment": {"num_drones": 2}}},
                      {"name": "x", "algorithm_parameters": {"accept_probability": 3}},
                      {"name": "x", "algorithm_parameters": {"typo": 1}},
                      {"name": "x", "simulation": {"environment": []}}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.service.create_project(patch)
        self.assertEqual(self.service.list_projects(), [])

    def test_unknown_or_unsafe_id_does_not_escape_store(self):
        for identifier in ("../secret", "missing"):
            with self.assertRaises((ValueError, FileNotFoundError)):
                self.service.get_project(identifier)


class RunTests(ProjectTests):
    def short_project(self, steps=20, probability=1):
        return self.service.create_project({
            "name": "真实子进程验收", "algorithm": "greedy", "seed": 101,
            "simulation": {"environment": {"episode_max_steps": steps, "num_drones": 2},
                           "heterogeneous": {"enabled": False},
                           "task_generation": {"mode": "constant"}},
            "algorithm_parameters": {"accept_probability": probability}})

    def wait_run(self, run_id):
        import time
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            run = self.service.get_run(run_id)
            if run["status"] not in {"queued", "running", "stopping"}:
                return run
            time.sleep(0.05)
        self.service.stop_run(run_id)
        self.fail("真实仿真 90 秒未结束")

    def test_real_engine_and_result_reopen_without_baseline_writes(self):
        import hashlib
        baseline = Path(__file__).resolve().parents[1] / "config" / "simulation.json"
        before = hashlib.sha256(baseline.read_bytes()).hexdigest()
        project = self.short_project()
        run = self.service.start_run(project["project_id"])
        finished = self.wait_run(run["run_id"])
        self.assertEqual(finished["status"], "completed", finished)
        self.assertEqual(finished["step"], 20)
        self.assertEqual(finished["progress"], 1)
        service = self.Service(Path(self.temp.name))
        result = service.get_result(run["run_id"])
        self.assertEqual(result["snapshot"]["num_drones"], 2)
        self.assertEqual(result["snapshot"]["algorithm"], "greedy")
        self.assertEqual(result["snapshot"]["seed"], 101)
        self.assertGreater(result["snapshot"]["stats"]["energy"], 0)
        self.assertEqual(result["engine_input"]["greedy"]["accept_probability"], 1)
        self.assertEqual(result["engine_input"]["episode_max_steps"], 20)
        self.assertEqual(hashlib.sha256(baseline.read_bytes()).hexdigest(), before)
        self.assertEqual(service.list_runs(project["project_id"])[0]["run_id"], run["run_id"])

    def test_parameter_reaches_engine_and_disables_dispatch(self):
        project = self.short_project(probability=0)
        run = self.service.start_run(project["project_id"])
        self.assertEqual(self.wait_run(run["run_id"])["status"], "completed")
        result = self.service.get_result(run["run_id"])
        self.assertEqual(result["engine_input"]["greedy"]["accept_probability"], 0)
        self.assertEqual(result["snapshot"]["stats"]["energy"], 0)
        self.assertEqual(result["snapshot"]["stats"]["completed"], 0)

    def test_stop_and_busy_conflict(self):
        project = self.short_project(100000)
        run = self.service.start_run(project["project_id"])
        with self.assertRaises(RuntimeError):
            self.service.start_run(project["project_id"])
        self.service.stop_run(run["run_id"])
        self.assertEqual(self.wait_run(run["run_id"])["status"], "stopped")
        with self.assertRaises(RuntimeError):
            self.service.get_result(run["run_id"])

    def test_startup_reconciles_orphan_and_failure_has_details(self):
        module = importlib.import_module("console.mvp_service")
        project = self.short_project()
        run_id = "a" * 32
        folder = Path(self.temp.name) / "runs" / run_id
        module.write_json(folder / "status.json", {"run_id": run_id,
                          "project_id": project["project_id"], "status": "running"})
        self.service.recover()
        self.assertEqual(self.service.get_run(run_id)["status"], "interrupted")
        self.assertTrue((folder / "stop").exists())

    def test_launch_failure_is_persisted(self):
        # 操作系统拒绝创建进程时也必须留下明确失败记录。
        project = self.short_project()
        from unittest.mock import patch
        with patch("console.mvp_service.subprocess.Popen", side_effect=OSError("injected launch failure")):
            run = self.service.start_run(project["project_id"])
        self.assertEqual(run["status"], "failed")
        self.assertIn("injected launch failure", run["error"])

    def test_real_worker_crash_is_persisted_failure(self):
        project = self.short_project(100000)
        run = self.service.start_run(project["project_id"])
        self.service.processes[run["run_id"]].kill()
        finished = self.wait_run(run["run_id"])
        self.assertEqual(finished["status"], "failed")
        self.assertIn("仿真进程异常退出", finished["error"])

    def test_inherited_experiment_switches_do_not_override_saved_input(self):
        from unittest.mock import patch
        dump_path = Path(self.temp.name) / "outside-run.json"
        with patch.dict("os.environ", {
            "SWARM_BALANCE_ROUTE_COST": "planned_distance",
            "SWARM_BALANCE_ROUTE_COST_DUMP": str(dump_path),
            "SWARM_BALANCE_REACH_WEIGHT": "999",
        }):
            project = self.short_project()
            run = self.service.start_run(project["project_id"])
            self.assertEqual(self.wait_run(run["run_id"])["status"], "completed")
        self.service.shutdown()
        self.assertFalse(dump_path.exists(), "继承的实验开关不应写出额外文件")
        result = self.service.get_result(run["run_id"])
        self.assertEqual(result["engine_input"]["route_cost_kind"], "euclidean")
        self.assertEqual(result["engine_input"]["greedy"]["reach_weight"], 0)

    def test_concurrent_status_polling_with_stop_and_recovery(self):
        from concurrent.futures import ThreadPoolExecutor
        import threading
        import time
        project = self.short_project(100000)
        for recover in (False, True):
            run = self.service.start_run(project["project_id"])
            done = threading.Event()

            def poll():
                while not done.is_set():
                    self.service.get_run(run["run_id"])

            with ThreadPoolExecutor(max_workers=7) as executor:
                futures = [executor.submit(poll) for _ in range(4)]
                try:
                    deadline = time.monotonic() + 60
                    while self.service.get_run(run["run_id"])["step"] < 20:
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(0.005)
                    if recover:
                        self.service.recover()
                    else:
                        stops = [executor.submit(self.service.stop_run, run["run_id"]) for _ in range(3)]
                        for stop in stops:
                            stop.result()
                    self.service.shutdown()
                    expected = "interrupted" if recover else "stopped"
                    self.assertEqual(self.service.get_run(run["run_id"])["status"], expected)
                finally:
                    done.set()
                for future in futures:
                    future.result()

class ConfigurationTests(ProjectTests):
    def test_json_read_retries_transient_denial_but_preserves_permanent_error(self):
        from unittest.mock import patch
        module = importlib.import_module("console.mvp_service")
        target = Path(self.temp.name) / "read.json"
        target.write_text('{"read": true}', encoding="utf-8")
        original = Path.read_text
        calls = []

        def transient(path, **kwargs):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError("transient read denial")
            return original(path, **kwargs)

        with patch.object(Path, "read_text", transient):
            self.assertEqual(module.read_json(target), {"read": True})
        with patch.object(Path, "read_text", side_effect=PermissionError("permanent read denial")), \
                patch.object(module.time, "sleep"):
            with self.assertRaisesRegex(PermissionError, "permanent"):
                module.read_json(target)

    def test_atomic_save_retries_transient_windows_share_denial(self):
        from unittest.mock import patch
        module = importlib.import_module("console.mvp_service")
        target = Path(self.temp.name) / "atomic.json"
        original = module.os.replace
        calls = []

        def transient(source, destination):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError("simulated WinError 5")
            return original(source, destination)

        with patch.object(module.os, "replace", side_effect=transient):
            module.write_json(target, {"saved": True})
        self.assertEqual(module.read_json(target), {"saved": True})
        self.assertEqual(len(calls), 3)

    def test_time_step_must_preserve_existing_one_second_unit(self):
        for value in (0, -1, 2):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.service.create_project({"name": "invalid clock", "simulation": {"drone": {"time_step": value}}})

    def test_invalid_coordinates_drone_values_and_task_counts_are_rejected(self):
        bad = [
            {"charging_stations": [{"station_id": 0, "x": "bad", "y": 1}]},
            {"charging_stations": [{"station_id": 0, "x": 1}]},
            {"drone": {"speed": -1}},
            {"task_generation": {"realistic": {"initial_task_count": 1.5}}},
            {"no_fly_zones": {"zones": [{"type": "circle", "center": [1], "radius": 1}]}},
        ]
        for simulation in bad:
            with self.subTest(simulation=simulation), self.assertRaises(ValueError):
                self.service.create_project({"name": "bad", "simulation": simulation})

class APITests(unittest.TestCase):
    def test_router_uses_persisted_project_and_clear_errors(self):
        import inspect
        import tempfile
        from fastapi import HTTPException
        try:
            api = importlib.import_module("console.mvp_api")
        except ModuleNotFoundError:
            self.fail("MVP HTTP router 尚未实现")
        with tempfile.TemporaryDirectory() as folder:
            from console.mvp_service import MVPService
            old = api.service
            api.service = MVPService(folder)
            try:
                project = api.create_project({"name": "API 项目"})
                self.assertEqual(api.get_project(project["project_id"])["name"], "API 项目")
                self.assertEqual(len(api.list_projects()["projects"]), 1)
                with self.assertRaises(HTTPException) as invalid:
                    api.create_project({"name": "x", "algorithm": "fake"})
                self.assertEqual(invalid.exception.status_code, 400)
                with self.assertRaises(HTTPException) as missing:
                    api.get_project("b" * 32)
                self.assertEqual(missing.exception.status_code, 404)
                self.assertTrue(inspect.isfunction(api.start_run))
            finally:
                api.service = old


if __name__ == "__main__":
    unittest.main()
