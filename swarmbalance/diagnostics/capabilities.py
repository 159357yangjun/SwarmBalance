"""Runtime capability detection used by preflight and the Web UI.

Keep this module dependency-light: it must be importable even when optional packages
such as osmnx / OR-Tools are absent.
"""
from __future__ import annotations

from swarmbalance.paths import DEFAULT_MAP, SCHEDULER_CONFIG

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List

from swarmbalance.paths import PROJECT_ROOT as ROOT


def _has(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:
        return False


def runtime_capabilities() -> Dict[str, Any]:
    has_osmnx = _has("osmnx")
    has_pyproj = _has("pyproj")
    has_ortools = _has("ortools")
    local_osm = DEFAULT_MAP

    from swarmbalance.scheduling.registry import list_algorithms
    algorithms = [item.as_dict() for item in list_algorithms()]

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
        "headless_web": has_pyproj and local_osm.exists(),
        "algorithms": algorithms,
        "available_algorithms": [x["key"] for x in algorithms if x["available"]],
        "optional": {
            "osmnx": has_osmnx,
            "pyproj": has_pyproj,
            "ortools": has_ortools,
        },
    }
