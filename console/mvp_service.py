"""MVP 项目与运行记录；独立于交互控制台的单例仿真。"""
from __future__ import annotations

import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid

from console.config_validation import assert_valid_simulation_config

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = {"queued", "running", "stopping"}
TERMINAL = {"completed", "failed", "stopped", "interrupted"}
GREEDY_KEYS = {
    "max_assignments_per_step", "candidate_limit", "accept_probability",
    "min_battery_ratio", "max_active_drones_ratio", "match_weight",
    "distance_weight", "reach_weight",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    for attempt in range(50):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except PermissionError:
            if attempt == 49:
                raise
            time.sleep(0.01)


def write_json(path, value):
    """同目录临时文件 + replace，读者不会看到半个 JSON。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(50):
            try:
                os.replace(temp, path)
                break
            except PermissionError:
                # Windows 短暂读句柄会拒绝 rename；限定重试，永久权限错误仍上报。
                if attempt == 49:
                    raise
                time.sleep(0.01)
    finally:
        temp.unlink(missing_ok=True)


@contextmanager
def status_lock(folder):
    """父进程和 worker 共享锁，序列化状态读改写，防止停止/完成互相覆盖。"""
    with (Path(folder) / "status.lock").open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        if os.name == "nt":
            import msvcrt
            deadline = time.monotonic() + 10
            while True:
                try:
                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("运行状态文件锁超时")
                    time.sleep(0.005)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def merge(base, patch):
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        else:
            base[key] = copy.deepcopy(value)
    return base


def _integer(value, label, lower, upper):
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{label} 必须是 {lower}~{upper} 之间的整数")


def _check_tree(value, template, label="simulation"):
    """拒绝拼错字段、错误结构和非有限数，避免静默无效配置。"""
    if isinstance(template, dict):
        if not isinstance(value, dict):
            raise ValueError(f"{label} 必须是对象")
        for key, item in value.items():
            if key not in template:
                raise ValueError(f"未知配置字段: {label}.{key}")
            _check_tree(item, template[key], f"{label}.{key}")
    elif isinstance(template, list):
        if not isinstance(value, list):
            raise ValueError(f"{label} 必须是数组")
        for item in value:
            if isinstance(item, (float, int)) and not math.isfinite(item):
                raise ValueError(f"{label} 不能包含非有限数")
    elif isinstance(template, bool):
        if type(value) is not bool:
            raise ValueError(f"{label} 必须是布尔值")
    elif isinstance(template, (int, float)):
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"{label} 必须是有限数值")
    elif isinstance(template, str) and not isinstance(value, str):
        raise ValueError(f"{label} 必须是字符串")


def _number(value, label, minimum=None):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{label} 必须是有限数")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} 必须至少为 {minimum}")


def _point(value, label):
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} 必须包含两个坐标")
    for coordinate in value:
        _number(coordinate, label)


def _validate_scene(config):
    if config["drone"]["time_step"] != 1.0:
        raise ValueError("MVP-01 固定物理口径 drone.time_step=1.0 秒")
    for station in config["charging_stations"]:
        if not isinstance(station, dict) or not {"station_id", "x", "y"} <= station.keys():
            raise ValueError("机巢必须包含 station_id、x、y")
        for key in ("x", "y"):
            _number(station[key], f"charging_stations.{key}")
        if "swap_time_seconds" in station:
            _number(station["swap_time_seconds"], "swap_time_seconds", 0.001)
    for key in ("speed", "battery_capacity", "carrying_capacity", "battery_consumption_base"):
        _number(config["drone"][key], f"drone.{key}", 0.001)
    for section in ("constant", "realistic"):
        for key in ("initial_task_count", "total_tasks", "max_unassigned_tasks"):
            if key in config["task_generation"][section]:
                _integer(config["task_generation"][section][key], f"{section}.{key}", 0, 1000000)
    for key, count in config["heterogeneous"]["fleet_mix"].items():
        _integer(count, f"fleet_mix.{key}", 0, 200)
    for zone in config["no_fly_zones"]["zones"]:
        if not isinstance(zone, dict):
            raise ValueError("禁飞区必须是对象")
        if zone.get("type") == "circle":
            _point(zone.get("center"), "circle.center")
            _number(zone.get("radius"), "circle.radius", 0.001)
        elif zone.get("type") == "polygon":
            points = zone.get("points")
            if not isinstance(points, list) or len(points) < 3:
                raise ValueError("polygon.points 至少需要三个点")
            for point in points:
                _point(point, "polygon.points")
        else:
            raise ValueError("禁飞区 type 必须为 circle 或 polygon")


class MVPService:
    def __init__(self, root=None):
        self.root = Path(root or os.environ.get("SWARM_BALANCE_MVP_DATA", ROOT / "results" / "mvp" )).resolve()
        self.projects = self.root / "projects"
        self.runs = self.root / "runs"
        self.lock = threading.RLock()
        self.processes = {}
        self.watchers = {}
        self.baseline = read_json(ROOT / "config" / "simulation.json")

    def defaults(self):
        return {"simulation": copy.deepcopy(self.baseline), "algorithm": "greedy",
                "algorithms": ["greedy"], "algorithm_parameters": {}, "seed": 100,
                "map": {"key": "yangpu", "label": "现有杨浦 OSM 地图"}}

    def _path(self, parent, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
            raise ValueError("无效 ID")
        return parent / identifier

    def _validate(self, payload, existing=None):
        allowed = {"name", "simulation", "algorithm", "algorithm_parameters", "seed",
                   "project_id", "created_at", "updated_at"}
        if not isinstance(payload, dict) or set(payload) - allowed:
            raise ValueError("项目必须是对象，且不能包含未知字段")
        result = copy.deepcopy(existing or self.defaults())
        result.pop("algorithms", None)
        result.pop("map", None)
        name = payload.get("name", result.get("name", ""))
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
            raise ValueError("项目名称须为 1~120 个字符")
        result["name"] = name.strip()
        result["algorithm"] = payload.get("algorithm", result["algorithm"])
        if result["algorithm"] != "greedy":
            raise ValueError("MVP-01 当前仅支持已接通的 greedy 算法")
        result["seed"] = payload.get("seed", result["seed"])
        _integer(result["seed"], "seed", 0, 0xFFFFFFFF)
        patch = payload.get("simulation", {})
        _check_tree(patch, self.baseline)
        result["simulation"] = merge(result["simulation"], patch)
        simulation = result["simulation"]
        _integer(simulation["environment"]["episode_max_steps"], "episode_max_steps", 1, 100000)
        _integer(simulation["environment"]["num_drones"], "num_drones", 1, 200)
        # 第一版只开放现有本地地图和 random 数据源，禁止配置任意本地文件读取。
        if simulation["data_source"] != self.baseline["data_source"]:
            raise ValueError("MVP-01 固定使用现有 random 数据源")
        if simulation["task"]["positions_file"] != self.baseline["task"]["positions_file"]:
            raise ValueError("MVP-01 不支持更换 positions_file")
        _validate_scene(simulation)
        try:
            assert_valid_simulation_config(simulation)
        except (AttributeError, TypeError, OverflowError) as exc:
            raise ValueError(f"场景配置结构无效: {exc}") from exc
        parameters = payload.get("algorithm_parameters", result["algorithm_parameters"])
        if not isinstance(parameters, dict) or set(parameters) - GREEDY_KEYS:
            raise ValueError("algorithm_parameters 包含未知 greedy 参数")
        effective = merge(copy.deepcopy(simulation["environment"]["greedy"]), parameters)
        for key, value in effective.items():
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(f"greedy.{key} 必须为非负有限数")
            if key in {"max_assignments_per_step", "candidate_limit"}:
                _integer(value, f"greedy.{key}", 1, 100000)
            elif key in {"accept_probability", "min_battery_ratio", "max_active_drones_ratio"} and value > 1:
                raise ValueError(f"greedy.{key} 必须在 0~1 之间")
        result["algorithm_parameters"] = copy.deepcopy(parameters)
        # 验证完整 JSON 包括数组内的 NaN，避免落盘后无法重新读取。
        try:
            json.dumps(result, allow_nan=False)
        except (ValueError, TypeError) as exc:
            raise ValueError("项目必须是有限 JSON 数据") from exc
        return result

    def create_project(self, payload):
        with self.lock:
            project = self._validate(payload)
            project.update(project_id=uuid.uuid4().hex, created_at=now(), updated_at=now())
            write_json(self._path(self.projects, project["project_id"]).with_suffix(".json"), project)
            return project

    def get_project(self, project_id):
        return read_json(self._path(self.projects, project_id).with_suffix(".json"))

    def list_projects(self):
        return sorted((read_json(p) for p in self.projects.glob("*.json")),
                      key=lambda p: p["updated_at"], reverse=True)

    def update_project(self, project_id, payload):
        with self.lock:
            old = self.get_project(project_id)
            project = self._validate(payload, old)
            project.update(project_id=project_id, created_at=old["created_at"], updated_at=now())
            write_json(self._path(self.projects, project_id).with_suffix(".json"), project)
            return project

    def start_run(self, project_id):
        with self.lock:
            project = self.get_project(project_id)
            if any(read_json(p).get("status") in ACTIVE for p in self.runs.glob("*/status.json")):
                raise RuntimeError("已有仿真运行，请等待结束或停止后再启动")
            run_id = uuid.uuid4().hex
            folder = self._path(self.runs, run_id)
            simulation = copy.deepcopy(project["simulation"])
            merge(simulation["environment"]["greedy"], project["algorithm_parameters"])
            write_json(folder / "project.json", project)
            write_json(folder / "simulation.json", simulation)
            status = {"run_id": run_id, "project_id": project_id, "project_name": project["name"],
                      "algorithm": project["algorithm"], "seed": project["seed"],
                      "status": "queued", "step": 0, "total_steps": simulation["environment"]["episode_max_steps"],
                      "progress": 0.0, "created_at": now(), "updated_at": now(), "error": None}
            write_json(folder / "status.json", status)
            env = {key: value for key, value in os.environ.items()
                   if not key.upper().startswith("SWARM_BALANCE_")}
            env["SWARM_BALANCE_SIM_CONFIG"] = str(folder / "simulation.json")
            env["PYTHONIOENCODING"] = "utf-8"
            try:
                with (folder / "worker.log").open("wb") as log:
                    process = subprocess.Popen(
                        [sys.executable, "-m", "console.mvp_worker", str(folder)],
                        cwd=str(ROOT), env=env, stdout=log, stderr=subprocess.STDOUT,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.processes[run_id] = process
                watcher = threading.Thread(target=self._watch, args=(run_id, process), daemon=True)
                self.watchers[run_id] = watcher
                watcher.start()
            except OSError as exc:
                status.update(status="failed", error=f"无法启动仿真进程: {exc}", updated_at=now())
                write_json(folder / "status.json", status)
            return self.get_run(run_id)

    def _watch(self, run_id, process):
        code = process.wait()
        with self.lock:
            folder = self._path(self.runs, run_id)
            with status_lock(folder):
                status = read_json(folder / "status.json")
                if status["status"] in ACTIVE:
                    tail = (folder / "worker.log").read_text(encoding="utf-8", errors="replace")[-4000:]
                    status.update(status="failed", error=f"仿真进程异常退出 ({code}): {tail}", updated_at=now())
                    write_json(folder / "status.json", status)
            self.processes.pop(run_id, None)
            self.watchers.pop(run_id, None)

    def get_run(self, run_id):
        folder = self._path(self.runs, run_id)
        if not (folder / "status.json").exists():
            raise FileNotFoundError(folder / "status.json")
        with status_lock(folder):
            return read_json(folder / "status.json")

    def list_runs(self, project_id):
        self.get_project(project_id)
        return sorted((s for p in self.runs.glob("*/status.json")
                       if (s := self.get_run(p.parent.name)).get("project_id") == project_id),
                      key=lambda s: s.get("created_at", ""), reverse=True)

    def get_result(self, run_id):
        status = self.get_run(run_id)
        if status["status"] != "completed":
            raise RuntimeError(f"运行尚无完成结果，当前状态: {status['status']}")
        return read_json(self._path(self.runs, run_id) / "result.json")

    def stop_run(self, run_id):
        with self.lock:
            folder = self._path(self.runs, run_id)
            self.get_run(run_id)  # 缺运行返回明确 404，不尝试创建锁文件。
            with status_lock(folder):
                status = read_json(folder / "status.json")
                if status["status"] not in ACTIVE:
                    return status
                (folder / "stop").touch()
                status.update(status="stopping", updated_at=now())
                write_json(folder / "status.json", status)
            process = self.processes.get(run_id)
            if process is not None:
                threading.Thread(target=self._stop_after_timeout, args=(run_id, process), daemon=True).start()
            return status

    def _stop_after_timeout(self, run_id, process):
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            with self.lock:
                folder = self._path(self.runs, run_id)
                with status_lock(folder):
                    status = read_json(folder / "status.json")
                    if status["status"] in ACTIVE:
                        status.update(status="stopped", error="停止超时，已终止仿真进程", updated_at=now())
                        write_json(folder / "status.json", status)
                        process.kill()

    def recover(self):
        """服务重启后明确标记旧运行中断，禁止把遗留 running 当成仍有进度。"""
        with self.lock:
            for path in self.runs.glob("*/status.json"):
                with status_lock(path.parent):
                    status = read_json(path)
                    if status.get("status") in ACTIVE:
                        (path.parent / "stop").touch()
                        status.update(status="interrupted", error="服务重启，旧运行已中断；请重新启动", updated_at=now())
                        write_json(path, status)

    def shutdown(self):
        with self.lock:
            watchers = list(self.watchers.values())
            run_ids = list(self.processes)
        for run_id in run_ids:
            self.stop_run(run_id)
        # Windows 的日志句柄要等子进程退出才释放；关闭服务也应完成回收。
        for watcher in watchers:
            watcher.join(timeout=15)
