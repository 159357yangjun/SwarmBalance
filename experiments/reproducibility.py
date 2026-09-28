"""Write a machine-readable reproducibility manifest for each batch experiment."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def sha256_file(path: Path) -> Optional[str]:
    path = Path(path)
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _version_of(name: str) -> Optional[str]:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


# 所有算法共用的执行路径：环境、指标口径与实验编排本身。
SHARED_SOURCES = [
    "config/config_loder.py",
    "frontend/environment.py",
    "frontend/drone.py",
    "frontend/charging_station.py",
    "frontend/task.py",
    "frontend/no_fly_zone.py",
    "frontend/data_source.py",
    "frontend/seed_interface.py",
    "frontend/metrics_schema.py",
    "frontend/scheduling_interface.py",
    "frontend/matching.py",
    "frontend/tools/osm.py",
    "experiments/runner.py",
    "experiments/worker.py",
]

# 每个算法各自的实现文件。少记一条，那一行结果就没有任何源码证据。
# greedy 用 frontend/matching.py、ga 用 backend_si/matching.py，两份同名不同体，必须分开记。
ALGORITHM_SOURCES = {
    "greedy": ["frontend/greedy/__init__.py", "frontend/greedy/scheduler.py"],
    "ga": [
        "backend_si/ga_scheduler.py",
        "backend_si/chain_codec.py",
        "backend_si/fitness_evaluator.py",
        "backend_si/matching.py",
    ],
    "pso": ["backend_si/pso_scheduler.py"],
    "ortools": ["backend_si/ortools_scheduler.py"],
}


def _hash_sources(project_root: Path, rel_paths: Iterable[str]) -> Dict[str, str]:
    hashes: Dict[str, str] = {}
    for rel in rel_paths:
        digest = sha256_file(project_root / rel)
        if digest is None:
            raise FileNotFoundError(
                f"复现清单需要 {rel} 的源码哈希，但文件不存在；"
                "源码被改名或删除时不允许静默记成 null"
            )
        hashes[rel] = digest
    return hashes


def _display_path(path: Optional[Path], root: Path) -> Optional[str]:
    """清单里的路径一律相对仓库根，绝不写绝对路径。

    绝对路径会把开发机的用户名和上层工作目录一起打进结项证据里
    （实测归档清单里就是 C:\\Users\\<user>\\AppData\\Roaming\\...\\.venv310\\...）。
    复现需要的是「相对哪个文件」，不是「在谁的盘上」。
    """
    if path is None:
        return None
    p = Path(path)
    for base in (root, root.parent):
        try:
            return p.resolve().relative_to(base).as_posix()
        except Exception:
            continue
    try:
        return "~/" + p.resolve().relative_to(Path.home()).as_posix()
    except Exception:
        return p.name


def _git_commit(root: Path) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(root), capture_output=True, text=True, timeout=3
        )
        if proc.returncode == 0:
            return proc.stdout.strip() or None
    except Exception:
        pass
    return None


def write_manifest(
    output_dir: Path,
    project_root: Path,
    preset_path: Optional[Path],
    base_config: Path,
    algorithm_config: Path,
    osm_path: Path,
    plan_count: int,
    algorithms: Iterable[str],
    preset_key: str,
) -> Path:
    version_file = project_root / "VERSION"
    project_version = version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "unknown"
    packages = {
        name: _version_of(name)
        for name in (
            "numpy", "pandas", "matplotlib", "PyYAML", "networkx", "shapely",
            "osmnx", "ortools", "fastapi", "uvicorn", "pygame",
        )
    }
    algos = sorted(set(algorithms))
    unknown = [a for a in algos if a not in ALGORITHM_SOURCES]
    if unknown:
        raise KeyError(
            f"算法 {unknown} 没有登记实现源码；在 ALGORITHM_SOURCES 里补上，"
            "否则该算法的结果行在复现清单里是空的"
        )
    algorithm_source_files = {a: ALGORITHM_SOURCES[a] for a in algos}
    listed = SHARED_SOURCES + sorted({f for a in algos for f in ALGORITHM_SOURCES[a]})
    source_hashes = _hash_sources(project_root, listed)

    manifest: Dict[str, Any] = {
        "schema_version": 2,
        "project": "SwarmBalance",
        "project_version": project_version,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "preset": preset_key,
        "plan_count": int(plan_count),
        "algorithms": algos,
        "runtime": {
            "python": sys.version,
            "python_executable": _display_path(Path(sys.executable), project_root),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "packages": packages,
        "git_commit": _git_commit(project_root),
        "core_source_sha256": source_hashes,
        "algorithm_source_files": algorithm_source_files,
        "inputs": {
            "preset": {"path": _display_path(preset_path, project_root), "sha256": sha256_file(preset_path) if preset_path else None},
            "simulation_config": {"path": _display_path(base_config, project_root), "sha256": sha256_file(base_config)},
            "algorithm_config": {"path": _display_path(algorithm_config, project_root), "sha256": sha256_file(algorithm_config)},
            "osm": {"path": _display_path(osm_path, project_root), "sha256": sha256_file(osm_path)},
        },
        "environment_flags": {
            "SWARM_BALANCE_SIM_CONFIG": os.environ.get("SWARM_BALANCE_SIM_CONFIG"),
        },
        "notes": [
            "同一实验条件下不同算法使用相同 Seed。",
            "每个 episode 使用独立 simulation.json 副本并在独立子进程执行。",
            "该清单用于复现实验环境，不代表结果具有统计显著性。",
            "schema v2 起按算法登记实现源码哈希（见 algorithm_source_files）；"
            "v1 清单只覆盖 GA 相关源码，PSO/OR-Tools/greedy 三行没有源码证据。",
        ],
    }
    path = Path(output_dir) / "reproducibility.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
