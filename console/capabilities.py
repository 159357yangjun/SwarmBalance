"""Runtime capability detection used by preflight and the Web UI.

Keep this module dependency-light: it must be importable even when optional packages
such as osmnx / pygame / OR-Tools are absent.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]


def _has(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:
        return False


def runtime_capabilities() -> Dict[str, Any]:
    has_osmnx = _has("osmnx")
    has_pyproj = _has("pyproj")
    has_pygame = _has("pygame")
    has_ortools = _has("ortools")
    local_osm = ROOT / "frontend" / "data" / "map" / "part_of_yangpu.osm"

    algorithms: List[Dict[str, Any]] = [
        {"key": "greedy", "label": "Greedy 贪心", "available": True, "reason": ""},
        {"key": "pso", "label": "PSO 粒子群", "available": True, "reason": ""},
        {"key": "ga", "label": "GA 遗传", "available": True, "reason": ""},
        {
            "key": "ortools", "label": "OR-Tools", "available": has_ortools,
            "reason": "" if has_ortools else "未安装 ortools；其它算法仍可正常运行",
        },
    ]

    map_backend = "osmnx" if has_osmnx else ("builtin_xml" if has_pyproj else "unavailable")
    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "python_official": sys.version_info[:2] == (3, 10),
        "map_backend": map_backend,
        "map_backend_label": {
            "osmnx": "OSMnx 完整解析",
            "builtin_xml": "内置离线 OSM XML 回退解析",
            "unavailable": "不可用",
        }[map_backend],
        "local_osm_present": local_osm.exists(),
        "desktop_visualization": has_pygame and has_osmnx,
        "headless_web": has_pyproj and local_osm.exists(),
        "algorithms": algorithms,
        "available_algorithms": [x["key"] for x in algorithms if x["available"]],
        "optional": {
            "osmnx": has_osmnx,
            "pyproj": has_pyproj,
            "pygame": has_pygame,
            "ortools": has_ortools,
        },
    }
