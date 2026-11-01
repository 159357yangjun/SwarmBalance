"""Fleet HTTP routes; all routers use the same shared runtime."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from swarmbalance.web.dependencies import runtime
from swarmbalance.paths import PROJECT_ROOT as _PROJECT_ROOT, CONFIG_DIR, SCHEDULER_CONFIG, STATIC_DIR
from swarmbalance.web.schemas import DroneChargeRequest, DroneIncidentRequest, NestIncidentRequest

_SIM_JSON = CONFIG_DIR / "simulation.json"
_ALG_YAML = SCHEDULER_CONFIG
_STATIC = STATIC_DIR / "index.html"
_SPEC = STATIC_DIR / "spec.html"
_VENDOR = STATIC_DIR / "vendor"
_VENDOR_FILES = {"vue.global.prod.js": "application/javascript", "echarts.min.js": "application/javascript", "three.min.js": "application/javascript"}
APP_VERSION = (_PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip() if (_PROJECT_ROOT / "VERSION").exists() else "1.0.0"
router = APIRouter()

@router.post("/api/drones/{drone_id}/charge")
def request_drone_charge(drone_id: str, req: DroneChargeRequest):
    """人工调无人机前往指定/最近开放机巢补能。"""
    try:
        with runtime.operation_lock:
            snap = runtime.get_session().request_drone_charge(drone_id, station_id=req.station_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(snap)

@router.post("/api/drones/{drone_id}/incident")
def drone_incident(drone_id: str, req: DroneIncidentRequest):
    """运行中故障/恢复无人机；故障机未完成任务自动回收并等待重调度。"""
    try:
        with runtime.operation_lock:
            snap = runtime.get_session().set_drone_out_of_service(
                drone_id, out_of_service=req.out_of_service, reason=req.reason)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(snap)

@router.post("/api/nests/{station_id}/incident")
def nest_incident(station_id: str, req: NestIncidentRequest):
    """运行中临时关闭/重新开放机巢。"""
    try:
        with runtime.operation_lock:
            snap = runtime.get_session().set_nest_closed(
                station_id, closed=req.closed, reason=req.reason)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(snap)
