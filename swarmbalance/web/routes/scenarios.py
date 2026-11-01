"""Scenarios HTTP routes; all routers use the same shared runtime."""
from __future__ import annotations
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from swarmbalance.web.dependencies import runtime
from swarmbalance.application import scenario_presets, scenarios as scenario_service
from swarmbalance.application.configuration import _read_scheduler_yaml
from swarmbalance.paths import PROJECT_ROOT as _PROJECT_ROOT, CONFIG_DIR, SCHEDULER_CONFIG, STATIC_DIR
from swarmbalance.web.schemas import ScenarioApplyRequest, SceneLibraryImportRequest, SceneLibrarySaveRequest

_SIM_JSON = CONFIG_DIR / "simulation.json"
_ALG_YAML = SCHEDULER_CONFIG
_STATIC = STATIC_DIR / "index.html"
_SPEC = STATIC_DIR / "spec.html"
_VENDOR = STATIC_DIR / "vendor"
_VENDOR_FILES = {"vue.global.prod.js": "application/javascript", "echarts.min.js": "application/javascript", "three.min.js": "application/javascript"}
APP_VERSION = (_PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip() if (_PROJECT_ROOT / "VERSION").exists() else "1.0.0"
router = APIRouter()

@router.get("/api/scenarios")
def scenarios():
    return {
        "presets": scenario_presets.list_presets(),
        "has_restore_point": runtime.scenario_backup_text is not None,
    }

@router.post("/api/scenarios/apply")
def apply_scenario(req: ScenarioApplyRequest):
    '加载答辩演示场景。首次加载时保存用户原 simulation.json，便于一键恢复。'
    return JSONResponse(scenario_service.apply_scenario(req.key, runtime))

@router.post("/api/scenarios/next")
def next_scenario_action():
    """执行当前演示剧本的下一幕。动作仍调用真实 step/inject/incident 接口。"""
    try:
        with runtime.operation_lock:
            return JSONResponse(runtime.get_session().advance_demo())
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.post("/api/scenarios/restore")
def restore_scenario():
    '恢复进入演示模式前的 simulation.json 与算法/Seed。'
    return JSONResponse(scenario_service.restore_scenario(runtime))

@router.get("/api/scene-library")
def scene_library_list():
    return {"scenes": runtime.scene_library.list()}

@router.post("/api/scene-library")
def scene_library_save(req: SceneLibrarySaveRequest):
    if not _SIM_JSON.exists():
        raise HTTPException(status_code=404, detail="simulation.json 不存在")
    try:
        with runtime.operation_lock:
            session = runtime.get_session()
            doc = runtime.scene_library.save(
                name=req.name,
                description=req.description,
                simulation_config=json.loads(_SIM_JSON.read_text(encoding="utf-8")),
                scheduler_config=_read_scheduler_yaml() if req.include_scheduler else None,
                algorithm=session.algorithm,
                seed=int(session.seed),
            )
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"scene": {k: v for k, v in doc.items() if k not in {"simulation_config", "scheduler_config"}},
            "scenes": runtime.scene_library.list()}

@router.get("/api/scene-library/{scene_id}")
def scene_library_export(scene_id: str):
    try:
        return JSONResponse(runtime.scene_library.get(scene_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="场景不存在")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.post("/api/scene-library/import")
def scene_library_import(req: SceneLibraryImportRequest):
    try:
        doc = runtime.scene_library.import_document(req.document)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"scene": {k: v for k, v in doc.items() if k not in {"simulation_config", "scheduler_config"}},
            "scenes": runtime.scene_library.list()}

@router.delete("/api/scene-library/{scene_id}")
def scene_library_delete(scene_id: str):
    try:
        runtime.scene_library.delete(scene_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="场景不存在")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "scenes": runtime.scene_library.list()}

@router.post("/api/scene-library/{scene_id}/apply")
def scene_library_apply(scene_id: str):
    '事务式应用场景库配置，并按场景记录的算法/Seed 重建。\n\n    场景库负责“可复现初始配置”；运行态 checkpoint 负责“精确动态节点”。\n    为避免用户在答辩预设的临时配置上再次叠加持久场景，演示模式中禁止应用。\n    '
    return JSONResponse(scenario_service.scene_library_apply(scene_id, runtime))
