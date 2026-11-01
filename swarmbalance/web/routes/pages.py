"""Pages HTTP routes; all routers use the same shared runtime."""
from __future__ import annotations
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from swarmbalance.paths import PROJECT_ROOT as _PROJECT_ROOT, CONFIG_DIR, SCHEDULER_CONFIG, STATIC_DIR

_SIM_JSON = CONFIG_DIR / "simulation.json"
_ALG_YAML = SCHEDULER_CONFIG
_STATIC = STATIC_DIR / "index.html"
_SPEC = STATIC_DIR / "spec.html"
_VENDOR = STATIC_DIR / "vendor"
_VENDOR_FILES = {"vue.global.prod.js": "application/javascript", "echarts.min.js": "application/javascript", "three.min.js": "application/javascript"}
APP_VERSION = (_PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip() if (_PROJECT_ROOT / "VERSION").exists() else "1.0.0"
router = APIRouter()

@router.get("/", response_class=HTMLResponse)
def index():
    if _STATIC.exists():
        return HTMLResponse(_STATIC.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>index.html 缺失</h1>")

@router.get("/spec", response_class=HTMLResponse)
def spec():
    """设计规范页：把世界逻辑与软件设计规范作为软件内的主要展示对象。"""
    if _SPEC.exists():
        return HTMLResponse(_SPEC.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>spec.html 缺失</h1>")

@router.get("/vendor/{name}")
def vendor(name: str):
    """本地前端依赖。

    页面原先只从 unpkg / jsdelivr 加载 Vue、ECharts、three.js，答辩现场断网或被内网
    策略拦截时整页不可用；这里提供本地副本作为首选，CDN 只作回退。
    """
    media_type = _VENDOR_FILES.get(name)
    if media_type is None:
        raise HTTPException(status_code=404, detail="未知前端依赖")
    path = _VENDOR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"本地依赖文件缺失: {name}")
    return FileResponse(str(path), media_type=media_type)
