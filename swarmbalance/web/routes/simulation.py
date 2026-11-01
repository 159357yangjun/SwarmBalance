"""Simulation HTTP routes; all routers use the same shared runtime."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from swarmbalance.web.dependencies import runtime
from swarmbalance.application.session import ALGORITHMS
from swarmbalance.paths import PROJECT_ROOT as _PROJECT_ROOT, CONFIG_DIR, SCHEDULER_CONFIG, STATIC_DIR
from swarmbalance.web.schemas import ResetRequest

_SIM_JSON = CONFIG_DIR / "simulation.json"
_ALG_YAML = SCHEDULER_CONFIG
_STATIC = STATIC_DIR / "index.html"
_SPEC = STATIC_DIR / "spec.html"
_VENDOR = STATIC_DIR / "vendor"
_VENDOR_FILES = {"vue.global.prod.js": "application/javascript", "echarts.min.js": "application/javascript", "three.min.js": "application/javascript"}
APP_VERSION = (_PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip() if (_PROJECT_ROOT / "VERSION").exists() else "1.0.0"
router = APIRouter()

@router.get("/api/snapshot")
def snapshot():
    warming = runtime.warming_response()
    if warming is not None:
        return warming
    with runtime.operation_lock:
        return JSONResponse(runtime.get_session().snapshot())

@router.post("/api/reset")
def reset(req: ResetRequest):
    if req.algorithm not in ALGORITHMS:
        raise HTTPException(status_code=400, detail=f"未知算法: {req.algorithm}")
    # numpy 的随机种子只接受 0 ~ 2**32-1。此前负数或超大 Seed 会在 pso/ga/ortools
    # 路径上抛 ValueError，用户拿到的是一个没有任何说明的 500。
    if not 0 <= req.seed <= 0xFFFFFFFF:
        raise HTTPException(
            status_code=400,
            detail=f"Seed 必须是 0 ~ {0xFFFFFFFF} 之间的整数（当前为 {req.seed}）",
        )
    try:
        with runtime.operation_lock:
            snap = runtime.get_session().reset(algorithm=req.algorithm, seed=req.seed)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(snap)

@router.post("/api/step")
def step(count: int = 1):
    """推进 1~50 步。高倍速播放使用批量步进以降低 HTTP 请求压力。"""
    count = max(1, min(50, int(count)))
    session = runtime.get_session()
    snap = None
    for _ in range(count):
        # 锁按**步**取放，而不是整批一把 hold 到底。原先批量步进会独占 runtime.operation_lock
        # 直到 50 步跑完，期间 /api/snapshot 只能在锁外排队，画面直接冻结。
        # 逐步放锁后读请求最多插到两步之间，等待上界从"整批"降到"一步"。
        # 每一步本身仍是原子的，与前端在 1x 下发 50 个独立请求等价。
        with runtime.operation_lock:
            snap = session.step()
            done = session.done
        if done:
            break
    with runtime.operation_lock:
        return JSONResponse(snap if snap is not None else session.snapshot())

@router.post("/api/rebuild")
def rebuild():
    """写回 simulation.json 后调用：热重载配置并重建 Environment。"""
    with runtime.operation_lock:
        return JSONResponse(runtime.get_session().rebuild())

@router.get("/api/map")
def map_static():
    """静态地图几何：边界 + 建筑轮廓(含高度)，供 3D 视图一次性加载。"""
    warming = runtime.warming_response()
    if warming is not None:
        return warming
    with runtime.operation_lock:
        return JSONResponse(runtime.get_session().map_static())
