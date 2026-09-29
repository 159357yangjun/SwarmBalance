"""Fast local preflight checks for the visual console.

The goal is to fail early with actionable messages instead of letting FastAPI import
half the simulation stack and emit a long traceback. No map/network access is used.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Dict, List

from console.config_validation import validate_simulation_config
from console.capabilities import runtime_capabilities

ROOT = Path(__file__).resolve().parents[1]


def run_checks(portable: bool = False) -> Dict[str, List[str]]:
    """Run startup checks.

    ``portable=False`` keeps the official reproducible environment strict: Python
    3.10 + the full dependency stack. ``portable=True`` is a defense/demo fallback
    that allows the Web console to run headlessly from the bundled local OSM XML
    using pyproj + the built-in parser. Optional desktop rendering and OR-Tools may
    be unavailable in that mode and are reported as warnings, never silently faked.
    """
    errors: List[str] = []
    warnings: List[str] = []
    caps = runtime_capabilities()

    if portable:
        if sys.version_info < (3, 10):
            errors.append(f"当前 Python {caps['python']}；便携模式至少需要 Python 3.10。")
        elif sys.version_info[:2] != (3, 10):
            warnings.append(
                f"当前 Python {caps['python']}；正式实验仍建议 Python 3.10.11。当前仅按便携 Web 模式运行。"
            )
        required = [
            ("numpy", "numpy"), ("shapely", "shapely"), ("pyproj", "pyproj"),
            ("yaml", "PyYAML"), ("fastapi", "fastapi"), ("uvicorn", "uvicorn"),
        ]
        missing = [hint for mod, hint in required if importlib.util.find_spec(mod) is None]
        if missing:
            errors.append("便携 Web 模式缺少依赖：" + "、".join(missing) + "。")
        if not caps["local_osm_present"]:
            errors.append("缺少内置地图 frontend/data/map/part_of_yangpu.osm。")
        if not caps["optional"]["osmnx"]:
            warnings.append("未安装 osmnx：将使用内置离线 OSM XML 回退解析器；正式实验建议完整环境。")
        if not caps["optional"]["ortools"]:
            warnings.append("未安装 OR-Tools：Greedy / GA / PSO 可用，OR-Tools 基线已在界面中标记不可用。")
    else:
        if sys.version_info[:2] != (3, 10):
            errors.append(
                f"当前 Python {caps['python']}；项目正式环境锁定 Python 3.10（推荐 3.10.11）。"
            )
        required = [
            ("numpy", "numpy==1.26.4"),
            ("osmnx", "osmnx==1.9.4"),
            ("shapely", "shapely==2.0.7"),
            ("networkx", "networkx==3.3"),
            ("yaml", "PyYAML==6.0.3"),
            ("fastapi", "fastapi"),
            ("uvicorn", "uvicorn"),
            ("ortools", "ortools"),
        ]
        missing = [hint for mod, hint in required if importlib.util.find_spec(mod) is None]
        if missing:
            errors.append("缺少依赖：" + "、".join(missing) + "。请按 README 的安装顺序执行 requirements.txt。")

    sim_path = ROOT / "config" / "simulation.json"
    if not sim_path.exists():
        errors.append("缺少 config/simulation.json。")
    else:
        try:
            cfg = json.loads(sim_path.read_text(encoding="utf-8"))
            cfg_errors, cfg_warnings = validate_simulation_config(cfg)
            errors.extend("simulation.json: " + msg for msg in cfg_errors)
            warnings.extend(cfg_warnings)
        except Exception as exc:
            errors.append(f"simulation.json 无法解析：{exc}")

    alg_path = ROOT / "backend_si" / "config.yaml"
    if not alg_path.exists():
        errors.append("缺少 backend_si/config.yaml。")
    else:
        try:
            import yaml
            parsed = yaml.safe_load(alg_path.read_text(encoding="utf-8")) or {}
            if not isinstance(parsed, dict):
                errors.append("backend_si/config.yaml 顶层必须是映射对象。")
        except Exception as exc:
            errors.append(f"backend_si/config.yaml 无法解析：{exc}")

    return {"errors": errors, "warnings": warnings}
