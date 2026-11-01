"""Tasks HTTP routes; all routers use the same shared runtime."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from swarmbalance.web.dependencies import runtime
from swarmbalance.paths import PROJECT_ROOT as _PROJECT_ROOT, CONFIG_DIR, SCHEDULER_CONFIG, STATIC_DIR
from swarmbalance.web.schemas import TaskInjectRequest, TaskStreamRequest, TaskUpdateRequest

_SIM_JSON = CONFIG_DIR / "simulation.json"
_ALG_YAML = SCHEDULER_CONFIG
_STATIC = STATIC_DIR / "index.html"
_SPEC = STATIC_DIR / "spec.html"
_VENDOR = STATIC_DIR / "vendor"
_VENDOR_FILES = {"vue.global.prod.js": "application/javascript", "echarts.min.js": "application/javascript", "three.min.js": "application/javascript"}
APP_VERSION = (_PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip() if (_PROJECT_ROOT / "VERSION").exists() else "1.0.0"
router = APIRouter()

@router.post("/api/tasks/inject")
def inject_task(req: TaskInjectRequest):
    """运行中插入任务：不重置场景，下一步直接参与当前调度。"""
    try:
        with runtime.operation_lock:
            snap = runtime.get_session().inject_task(**req.model_dump())
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(snap)

@router.get("/api/tasks/{task_id}/candidates")
def task_candidates(task_id: str, limit: int = 5):
    """返回某个活动任务的候选无人机解释性排名，不改变仿真状态。"""
    with runtime.operation_lock:
        return JSONResponse(runtime.get_session().task_candidates(task_id, limit=limit))

@router.post("/api/task-stream")
def task_stream(req: TaskStreamRequest):
    """暂停/恢复自动任务生成，不影响当前待调度池与人工任务。"""
    with runtime.operation_lock:
        return JSONResponse(runtime.get_session().set_task_generation_paused(req.paused))

@router.patch("/api/tasks/{task_id}")
def update_task(task_id: str, req: TaskUpdateRequest):
    """修改待调度任务属性，供运行中优先级/SLA变更演示。"""
    try:
        payload = req.model_dump(exclude_none=True)
        with runtime.operation_lock:
            snap = runtime.get_session().update_pending_task(task_id, **payload)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(snap)
