"""MVP-01 稳定接口；旧控制台 API 原样保留。"""
from fastapi import APIRouter, Body, HTTPException

from console.mvp_service import MVPService

router = APIRouter(prefix="/api/mvp", tags=["MVP-01"])
service = MVPService()


def _call(function, *args):
    try:
        return function(*args)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="项目、运行或结果不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/defaults")
def defaults():
    return service.defaults()


@router.get("/projects")
def list_projects():
    return {"projects": _call(service.list_projects)}


@router.post("/projects", status_code=201)
def create_project(payload: dict = Body(...)):
    return _call(service.create_project, payload)


@router.get("/projects/{project_id}")
def get_project(project_id: str):
    return _call(service.get_project, project_id)


@router.put("/projects/{project_id}")
def update_project(project_id: str, payload: dict = Body(...)):
    return _call(service.update_project, project_id, payload)


@router.post("/projects/{project_id}/runs", status_code=202)
def start_run(project_id: str):
    return _call(service.start_run, project_id)


@router.get("/projects/{project_id}/runs")
def list_runs(project_id: str):
    return {"runs": _call(service.list_runs, project_id)}


@router.get("/runs/{run_id}")
def get_run(run_id: str):
    return _call(service.get_run, run_id)


@router.get("/runs/{run_id}/result")
def get_result(run_id: str):
    return _call(service.get_result, run_id)


@router.post("/runs/{run_id}/stop", status_code=202)
def stop_run(run_id: str):
    return _call(service.stop_run, run_id)
