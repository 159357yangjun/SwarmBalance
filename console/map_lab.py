"""Read-only GIS map preview plus opt-in bounded background OSM import.

Never sets SimSession.osm_path; imported ways are visual-only until validated.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from console import gis_import as gis
from console import studio_project_preview as project_previews

router = APIRouter()
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "map" / "fosi"
PAGE = Path(__file__).resolve().parent / "static" / "map_lab.html"
JS = Path(__file__).resolve().parent / "static" / "map_lab.js"
LAYERS = gis.KINDS
MAX_GEOJSON_BYTES = 12 * 1024 * 1024


class CreateImport(BaseModel):
    bbox: list[float] = Field(min_length=4, max_length=4)
    force_refresh: bool = False


@router.get("/map-lab")
def map_lab_page():
    return FileResponse(PAGE, media_type="text/html; charset=utf-8")


@router.get("/map-lab/assets/map_lab.js")
def map_lab_script():
    return FileResponse(JS, media_type="application/javascript; charset=utf-8")


@router.get("/api/map-lab/status")
def map_lab_status():
    region = json.loads((DATA_DIR / "region.json").read_text(encoding="utf-8"))
    output = DATA_DIR / "output"
    layers = {}
    for name in LAYERS:
        path = output / (name + ".geojson")
        size = path.stat().st_size if path.is_file() else 0
        layers[name] = {"ready": 0 < size <= MAX_GEOJSON_BYTES, "bytes": size}
    return {"region": region, "layers": layers,
            "manifest_ready": (output / "data_manifest.json").is_file(),
            "simulation_connected": False,
            "hint": "旧佛寺镇本地图层预览；新地图包请通过创建导入任务按区域获取。"}


def send_layer(path: Path):
    if not path.is_file():
        raise HTTPException(status_code=404, detail="当前地图图层尚未准备")
    if path.stat().st_size > MAX_GEOJSON_BYTES:
        raise HTTPException(status_code=413, detail="图层过大，当前预览暂不支持；请缩小选区")
    return FileResponse(path, media_type="application/geo+json",
                        headers={"Cache-Control": "no-store"})


@router.get("/api/map-lab/layers/{layer}")
def map_lab_layer(layer: str):
    if layer not in LAYERS:
        raise HTTPException(status_code=404, detail="未知的地图图层")
    return send_layer(DATA_DIR / "output" / (layer + ".geojson"))


@router.post("/api/gis/import-jobs", status_code=202)
def create_import_job(spec: CreateImport):
    try:
        return gis.start_job(spec.bbox, force_refresh=spec.force_refresh)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except gis.ImportFailure as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/gis/import-jobs/{job_id}")
def get_import_job(job_id: str):
    try:
        return gis.read_job(job_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="找不到地图导入任务") from exc


@router.post("/api/gis/import-jobs/{job_id}/cancel")
def cancel_import_job(job_id: str):
    try:
        gis.cancel_job(job_id)
        return {"id": job_id, "cancel_requested": True}
    except gis.ImportFailure as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/api/gis/packages/{package_id}")
def get_package(package_id: str):
    try:
        return gis.manifest_for(package_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="地图包不存在") from exc


@router.get("/api/gis/packages/{package_id}/layers/{layer}")
def package_layer(package_id: str, layer: str):
    if layer not in LAYERS:
        raise HTTPException(status_code=404, detail="未知的地图图层")
    try:
        gis.manifest_for(package_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="地图包不存在") from exc
    return send_layer(gis.DATA_ROOT / "packages" / package_id / (layer + ".geojson"))


class ProjectPreviewRequest(BaseModel):
    package_id: str = Field(min_length=24, max_length=24)


def _get_mvp_project(project_id):
    # Project registry is a separate existing service; do not mutate its simulation config.
    from console.mvp_api import service
    return service.get_project(project_id)


@router.get("/api/gis/project-previews/{project_id}")
def get_project_map_preview(project_id: str):
    try:
        return project_previews.get_preview(project_id, _get_mvp_project)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=404, detail=f"无法读取项目地图预览引用：{exc}") from exc


@router.put("/api/gis/project-previews/{project_id}")
def attach_project_map_preview(project_id: str, body: ProjectPreviewRequest):
    try:
        return project_previews.attach_preview(project_id, body.package_id, _get_mvp_project)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目或地图包不存在") from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
