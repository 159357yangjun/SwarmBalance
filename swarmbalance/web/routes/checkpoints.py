"""Checkpoints HTTP routes; all routers use the same shared runtime."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from swarmbalance.web.dependencies import runtime
from swarmbalance.paths import PROJECT_ROOT as _PROJECT_ROOT, CONFIG_DIR, SCHEDULER_CONFIG, STATIC_DIR
from swarmbalance.web.schemas import CheckpointRequest

_SIM_JSON = CONFIG_DIR / "simulation.json"
_ALG_YAML = SCHEDULER_CONFIG
_STATIC = STATIC_DIR / "index.html"
_SPEC = STATIC_DIR / "spec.html"
_VENDOR = STATIC_DIR / "vendor"
_VENDOR_FILES = {"vue.global.prod.js": "application/javascript", "echarts.min.js": "application/javascript", "three.min.js": "application/javascript"}
APP_VERSION = (_PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip() if (_PROJECT_ROOT / "VERSION").exists() else "1.0.0"
router = APIRouter()

@router.get("/api/checkpoints")
def checkpoints():
    with runtime.operation_lock:
        return {"checkpoints": runtime.get_session().list_checkpoints()}

@router.post("/api/checkpoints")
def save_checkpoint(req: CheckpointRequest):
    try:
        with runtime.operation_lock:
            return JSONResponse(runtime.get_session().save_checkpoint(req.name))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.post("/api/checkpoints/{name}/load")
def load_checkpoint(name: str):
    try:
        with runtime.operation_lock:
            return JSONResponse(runtime.get_session().load_checkpoint(name))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@router.delete("/api/checkpoints/{name}")
def delete_checkpoint(name: str):
    try:
        with runtime.operation_lock:
            return JSONResponse(runtime.get_session().delete_checkpoint(name))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
