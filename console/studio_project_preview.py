"""Project-scoped GIS preview associations, separate from simulation input.

An attachment is a resource bookmark ONLY: it neither edits MVP simulation.json
nor changes the Yangpu map loaded by the legacy simulator.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from console import gis_import as gis

PROJECT_ID = re.compile(r"^[0-9a-f]{32}$")
LOCK = threading.RLock()
BASE = gis.DATA_ROOT / "project_previews"


def _valid_project(project_id, get_project):
    if not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
        raise ValueError("项目 ID 格式无效")
    project = get_project(project_id)
    if project.get("project_id") != project_id:
        raise ValueError("项目 ID 不匹配")
    return project


def _path(project_id, root=None):
    if not isinstance(project_id, str) or not PROJECT_ID.fullmatch(project_id):
        raise ValueError("项目 ID 格式无效")
    return Path(root or BASE) / (project_id + ".json")


def get_preview(project_id, get_project, root=None, manifest_loader=None):
    project = _valid_project(project_id, get_project)
    path = _path(project_id, root)
    if not path.exists():
        return {"project_id": project_id, "project_name": project["name"],
                "map_preview": None, "simulation_connected": False}
    with LOCK:
        data = json.loads(path.read_text(encoding="utf-8"))
    stored = data.get("map_preview")
    if not isinstance(stored, dict) or stored.get("package_id") is None:
        raise ValueError("已保存的项目地图引用损坏")
    loader = manifest_loader or gis.manifest_for
    manifest = loader(stored["package_id"])
    return {"project_id": project_id, "project_name": project["name"],
            "map_preview": {**stored, "bbox_wgs84_lonlat": manifest["bbox_wgs84_lonlat"],
                            "quality": manifest.get("quality")},
            "simulation_connected": False}


def attach_preview(project_id, package_id, get_project, root=None, manifest_loader=None):
    project = _valid_project(project_id, get_project)
    loader = manifest_loader or gis.manifest_for
    manifest = loader(package_id)  # validates identity; rejects missing packages
    if manifest.get("quality", {}).get("simulation_safe") is not False:
        raise ValueError("只能关联标记为 GIS 预览的地图包，不得将计算地图混入预览资源")
    if manifest.get("package_id") != package_id:
        raise ValueError("地图包 ID 与实际数据不一致")
    stored = {"package_id": package_id, "attached_utc": gis.utc_now()}
    value = {"project_id": project_id, "map_preview": stored,
             "simulation_connected": False}
    with LOCK:
        gis.write_json(_path(project_id, root), value)
    return {"project_id": project_id, "project_name": project["name"],
            "map_preview": {**stored, "bbox_wgs84_lonlat": manifest["bbox_wgs84_lonlat"],
                            "quality": manifest.get("quality")},
            "simulation_connected": False}
