"""可视化控制台后端（FastAPI）。

阶段一：REST 轮询驱动的最小控制台（仿真推进 + 快照）。
阶段二：配置面板（场景 simulation.json + 算法 config.yaml 读写、热重载）、
         3D 视图静态地图、多算法对比数据。

启动：
    python -m console.run
浏览器打开 http://127.0.0.1:8765/
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_PROJECT_ROOT),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from console.sim_session import ALGORITHMS, SimSession  # noqa: E402

app = FastAPI(title="无人机调度仿真控制台")

_STATIC = Path(__file__).resolve().parent / "static" / "index.html"
_SIM_JSON = _PROJECT_ROOT / "config" / "simulation.json"
_ALG_YAML = _PROJECT_ROOT / "backend_si" / "config.yaml"

_session: Optional[SimSession] = None
_lock = threading.Lock()


def _get_session() -> SimSession:
    global _session
    if _session is None:
        with _lock:
            if _session is None:
                _session = SimSession()
                _session.reset(algorithm="greedy", seed=100)
    return _session


def _deep_merge(base: Dict, patch: Dict) -> Dict:
    """递归合并 dict，patch 覆盖 base（不丢失 base 中未提及的字段）。"""
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------

class ResetRequest(BaseModel):
    algorithm: str = "greedy"
    seed: int = 100


class ConfigPatch(BaseModel):
    patch: Dict[str, Any]


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index():
    if _STATIC.exists():
        return HTMLResponse(_STATIC.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>index.html 缺失</h1>")


# ---------------------------------------------------------------------------
# 仿真 API
# ---------------------------------------------------------------------------

@app.get("/api/algorithms")
def algorithms():
    return {"algorithms": ALGORITHMS}


@app.get("/api/snapshot")
def snapshot():
    return JSONResponse(_get_session().snapshot())


@app.post("/api/reset")
def reset(req: ResetRequest):
    if req.algorithm not in ALGORITHMS:
        raise HTTPException(status_code=400, detail=f"未知算法: {req.algorithm}")
    try:
        snap = _get_session().reset(algorithm=req.algorithm, seed=req.seed)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(snap)


@app.post("/api/step")
def step():
    return JSONResponse(_get_session().step())


@app.post("/api/rebuild")
def rebuild():
    """写回 simulation.json 后调用：热重载配置并重建 Environment。"""
    return JSONResponse(_get_session().rebuild())


@app.get("/api/map")
def map_static():
    """静态地图几何：边界 + 建筑轮廓(含高度)，供 3D 视图一次性加载。"""
    return JSONResponse(_get_session().map_static())


# ---------------------------------------------------------------------------
# 配置 API
# ---------------------------------------------------------------------------

@app.get("/api/config")
def get_config():
    if not _SIM_JSON.exists():
        raise HTTPException(status_code=404, detail="simulation.json 不存在")
    return JSONResponse(json.loads(_SIM_JSON.read_text(encoding="utf-8")))


@app.post("/api/config")
def save_config(req: ConfigPatch):
    """深合并写回 simulation.json（不丢失未提及字段），不自动重建。"""
    if not _SIM_JSON.exists():
        raise HTTPException(status_code=404, detail="simulation.json 不存在")
    cfg = json.loads(_SIM_JSON.read_text(encoding="utf-8"))
    cfg = _deep_merge(cfg, req.patch)
    _SIM_JSON.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "config": cfg}


@app.get("/api/scheduler-config")
def get_scheduler_config():
    if not _ALG_YAML.exists():
        raise HTTPException(status_code=404, detail="config.yaml 不存在")
    import yaml
    with open(_ALG_YAML, "r", encoding="utf-8") as f:
        return JSONResponse(yaml.safe_load(f) or {})


@app.post("/api/scheduler-config")
def save_scheduler_config(req: ConfigPatch):
    """深合并写回 backend_si/config.yaml。调度器每 reset 重建时会读到新值。"""
    import yaml
    if not _ALG_YAML.exists():
        raise HTTPException(status_code=404, detail="config.yaml 不存在")
    with open(_ALG_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    cfg = _deep_merge(cfg, req.patch)
    with open(_ALG_YAML, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    return {"ok": True, "config": cfg}


# ---------------------------------------------------------------------------
# 对比看板 API
# ---------------------------------------------------------------------------

_CSV_FILES = [
    "frontend_greedy_metrics.csv",
    "backend_si_metrics.csv",
    "backend_ga_metrics.csv",
    "backend_ortools_metrics.csv",
    "backend_wx_metrics.csv",
]


@app.get("/api/compare")
def compare():
    """读 results/compare/*.csv，返回各算法最后一行指标（供前端 ECharts 对比）。"""
    import math
    import pandas as pd
    compare_dir = _PROJECT_ROOT / "results" / "compare"
    frames: List[pd.DataFrame] = []
    for name in _CSV_FILES:
        path = compare_dir / name
        if not path.exists():
            continue
        df = pd.read_csv(path, encoding="utf-8-sig")
        if "算法" not in df.columns:
            continue
        frames.append(df)
    if not frames:
        return {"rows": [], "columns": []}

    data = pd.concat(frames, ignore_index=True)
    data = data.drop_duplicates("算法", keep="last").reset_index(drop=True)
    # 只保留数值列 + 算法列，去掉总步数/完成任务数等冗余
    drop_cols = {"总步数", "完成任务数", "生成任务数", "换电总次数"}
    keep_cols = [c for c in data.columns if c != "算法" and c not in drop_cols]
    rows = data[["算法"] + keep_cols].to_dict(orient="records")

    def _clean(v):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        if isinstance(v, float):
            return round(v, 4)
        return v

    for r in rows:
        for k in list(r.keys()):
            r[k] = _clean(r[k])
    return {"rows": rows, "columns": keep_cols}
