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
    core_sources = [
        "backend_si/ga_scheduler.py",
        "backend_si/chain_codec.py",
        "backend_si/matching.py",
        "backend_si/fitness_evaluator.py",
        "frontend/environment.py",
        "frontend/metrics_schema.py",
        "experiments/runner.py",
        "experiments/worker.py",
    ]
    source_hashes = {rel: sha256_file(project_root / rel) for rel in core_sources}

    manifest: Dict[str, Any] = {
        "schema_version": 1,
        "project": "SwarmBalance",
        "project_version": project_version,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "preset": preset_key,
        "plan_count": int(plan_count),
        "algorithms": sorted(set(algorithms)),
        "runtime": {
            "python": sys.version,
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        },
        "packages": packages,
        "git_commit": _git_commit(project_root),
        "core_source_sha256": source_hashes,
        "inputs": {
            "preset": {"path": str(preset_path) if preset_path else None, "sha256": sha256_file(preset_path) if preset_path else None},
            "simulation_config": {"path": str(base_config), "sha256": sha256_file(base_config)},
            "algorithm_config": {"path": str(algorithm_config), "sha256": sha256_file(algorithm_config)},
            "osm": {"path": str(osm_path), "sha256": sha256_file(osm_path)},
        },
        "environment_flags": {
            "SWARM_BALANCE_SIM_CONFIG": os.environ.get("SWARM_BALANCE_SIM_CONFIG"),
        },
        "notes": [
            "同一实验条件下不同算法使用相同 Seed。",
            "每个 episode 使用独立 simulation.json 副本并在独立子进程执行。",
            "该清单用于复现实验环境，不代表结果具有统计显著性。",
        ],
    }
    path = Path(output_dir) / "reproducibility.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
