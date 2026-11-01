"""Metadata HTTP routes; all routers use the same shared runtime."""
from __future__ import annotations
import sys
from fastapi import APIRouter
from swarmbalance.application.session import ALGORITHMS
from swarmbalance.diagnostics.capabilities import runtime_capabilities
from swarmbalance.paths import PROJECT_ROOT as _PROJECT_ROOT, CONFIG_DIR, SCHEDULER_CONFIG, STATIC_DIR
from swarmbalance.simulation.entities.drone import STEP_SECONDS

_SIM_JSON = CONFIG_DIR / "simulation.json"
_ALG_YAML = SCHEDULER_CONFIG
_STATIC = STATIC_DIR / "index.html"
_SPEC = STATIC_DIR / "spec.html"
_VENDOR = STATIC_DIR / "vendor"
_VENDOR_FILES = {"vue.global.prod.js": "application/javascript", "echarts.min.js": "application/javascript", "three.min.js": "application/javascript"}
APP_VERSION = (_PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip() if (_PROJECT_ROOT / "VERSION").exists() else "1.0.0"
router = APIRouter()

@router.get("/api/algorithms")
def algorithms():
    caps = runtime_capabilities()
    return {"algorithms": caps["algorithms"], "available": caps["available_algorithms"]}

@router.get("/api/meta")
def meta():
    return {
        "name": "群智优衡——异构无人机集群三维协同调度仿真平台",
        "version": APP_VERSION,
        "algorithms": ALGORITHMS,
        "scene_library_limit": 50,
        "capabilities": runtime_capabilities(),
        # 规范 WL-1.2 要求「1 step = 1 秒」这个映射必须在代码常量与 UI 中显式声明，
        # 不能只靠配置凑出自洽；这里把它随元数据暴露，供状态栏声明。
        "step_seconds": STEP_SECONDS,
        # 侧栏「低电」的阈值口径必须与 sim_session 的计数同源，不能让界面自己猜一个百分数。
        # 走 sys.modules 取属性而不是 from-import：drone 会在改配置后被 reload，值绑定会留在旧值上。
        "battery_low_threshold": getattr(sys.modules.get("swarmbalance.simulation.entities.drone"), "BATTERY_LOW_THRESHOLD", 0.2),
    }
