"""Configuration HTTP routes; all routers use the same shared runtime."""
from __future__ import annotations
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from swarmbalance.web.dependencies import runtime
from swarmbalance.application import configuration as configuration_service
from swarmbalance.paths import PROJECT_ROOT as _PROJECT_ROOT, CONFIG_DIR, SCHEDULER_CONFIG, STATIC_DIR
from swarmbalance.web.schemas import ConfigPatch, SceneLayoutRequest

_SIM_JSON = CONFIG_DIR / "simulation.json"
_ALG_YAML = SCHEDULER_CONFIG
_STATIC = STATIC_DIR / "index.html"
_SPEC = STATIC_DIR / "spec.html"
_VENDOR = STATIC_DIR / "vendor"
_VENDOR_FILES = {"vue.global.prod.js": "application/javascript", "echarts.min.js": "application/javascript", "three.min.js": "application/javascript"}
APP_VERSION = (_PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip() if (_PROJECT_ROOT / "VERSION").exists() else "1.0.0"
router = APIRouter()

@router.get("/api/config")
def get_config():
    return JSONResponse(configuration_service.get_config())

@router.post("/api/config")
def save_config(req: ConfigPatch):
    '深合并写回 simulation.json（不丢失未提及字段），不自动重建。'
    return configuration_service.save_config(req.patch)

@router.post("/api/scene-layout")
def save_scene_layout(req: SceneLayoutRequest):
    '保存机巢网络/禁飞区布局并热重建。\n\n    仅 random 数据源使用 simulation.json 中的机巢布局；CSV/GeoJSON 场景应直接\n    编辑其源文件，避免界面看似保存成功但运行时实际未生效。写入后若重建失败，\n    会回滚原配置。\n    '
    return JSONResponse(configuration_service.save_scene_layout(req.model_dump(), runtime))

@router.get("/api/scheduler-config")
def get_scheduler_config():
    return JSONResponse(configuration_service.get_scheduler_config())

@router.post("/api/scheduler-config")
def save_scheduler_config(req: ConfigPatch):
    '深合并写回 backend_si/config.yaml。调度器每 reset 重建时会读到新值。'
    return configuration_service.save_scheduler_config(req.patch)
