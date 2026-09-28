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
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(_PROJECT_ROOT),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from console.sim_session import ALGORITHMS, SimSession  # noqa: E402
from console import experiment_service  # noqa: E402
from console import scenario_presets  # noqa: E402
from console.scene_library import SceneLibrary  # noqa: E402
from console.config_validation import assert_valid_simulation_config  # noqa: E402
from console.capabilities import runtime_capabilities  # noqa: E402

try:  # sim_session 已把 frontend/ 加入 sys.path；取规范要求的步长常量作为唯一来源
    from drone import STEP_SECONDS  # noqa: E402
except Exception:  # pragma: no cover - 缺依赖时仍要能让 /api/meta 起来
    STEP_SECONDS = 1.0

app = FastAPI(title="无人机调度仿真控制台")

_STATIC = Path(__file__).resolve().parent / "static" / "index.html"
_SPEC = Path(__file__).resolve().parent / "static" / "spec.html"
_VENDOR = Path(__file__).resolve().parent / "static" / "vendor"
# 白名单而非目录挂载：既避免路径穿越，也让「本地依赖是否齐全」可被预检明确判定。
_VENDOR_FILES = {
    "vue.global.prod.js": "application/javascript",
    "echarts.min.js": "application/javascript",
    "three.min.js": "application/javascript",
}
_SIM_JSON = _PROJECT_ROOT / "config" / "simulation.json"
_ALG_YAML = _PROJECT_ROOT / "backend_si" / "config.yaml"
_SCENE_LIBRARY = SceneLibrary(_PROJECT_ROOT / "config" / "scenes")
APP_VERSION = (_PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip() if (_PROJECT_ROOT / "VERSION").exists() else "1.0.0"

_session: Optional[SimSession] = None
_lock = threading.Lock()
_op_lock = threading.RLock()  # 串行化 step/reset/rebuild/inject，避免浏览器高倍速下并发推进
_warm_done = threading.Event()  # 后台预热线程结束（成功或失败）后置位，用于 /api/snapshot 快速返回
_scenario_backup_text: Optional[str] = None
_scenario_backup_runtime: Optional[Dict[str, Any]] = None


def _get_session() -> SimSession:
    global _session
    if _session is None:
        with _lock:
            if _session is None:
                _session = SimSession()
                _session.reset(algorithm="greedy", seed=100)
    return _session


@app.on_event("startup")
def _warmup_session() -> None:
    """启动即后台预热仿真会话，同时让端口照常早开。

    两个约束互相冲突，必须同时满足：
    1. SimSession 首次构造要解析本地 OSM 地图，实测约 4.3s。若等首个请求才初始化，
       用户会看到一个阻塞 4.3s 的 /api/snapshot。
    2. 若把预热挪到绑定端口之前（实测首个请求可降到 0.12s），浏览器就要等 8.5s 才能
       开始加载 CDN 与地图数据，总可用时间从 5.8s 退化到 8.5s。
    所以端口早开、预热跑在后台，未就绪期间 /api/snapshot 用 202 快速回绝，
    由前端 api() 等待重试（见 static/index.html 的 warming 分支）。
    """

    def _warm() -> None:
        try:
            _get_session()
        except Exception as exc:  # noqa: BLE001 - 预热失败降级为首次请求时初始化
            print(f"[预热] 会话初始化失败，将在首次请求时重试：{exc}", file=sys.stderr)
        finally:
            # 失败也要置位：否则 /api/snapshot 会一直 202，前端永远卡在加载态。
            _warm_done.set()

    threading.Thread(target=_warm, name="session-warmup", daemon=True).start()


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


class ExperimentStartRequest(BaseModel):
    preset: str = "quick"


class TaskInjectRequest(BaseModel):
    # source / destination 为空时由当前场景合法候选点随机抽样。
    source: Optional[List[float]] = None
    destination: Optional[List[float]] = None
    weight: float = 1.0
    volume: float = 0.0
    priority: int = 3
    deadline_offset: Optional[float] = None
    category: str = "normal"
    task_id: Optional[str] = None

class DroneIncidentRequest(BaseModel):
    out_of_service: bool = True
    reason: str = "人工故障注入"


class NestIncidentRequest(BaseModel):
    closed: bool = True
    reason: str = "人工场景事件"


class TaskStreamRequest(BaseModel):
    paused: bool = True


class TaskUpdateRequest(BaseModel):
    priority: Optional[int] = None
    deadline_offset: Optional[float] = None
    weight: Optional[float] = None
    category: Optional[str] = None


class DroneChargeRequest(BaseModel):
    station_id: Optional[str] = None


class SceneLayoutRequest(BaseModel):
    charging_stations: List[Dict[str, Any]]
    no_fly_zones: Dict[str, Any]


class ScenarioApplyRequest(BaseModel):
    key: str = "balanced"


class CheckpointRequest(BaseModel):
    name: str = "答辩节点"


class SceneLibrarySaveRequest(BaseModel):
    name: str
    description: str = ""
    include_scheduler: bool = True


class SceneLibraryImportRequest(BaseModel):
    document: Dict[str, Any]


# ---------------------------------------------------------------------------
# 页面
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index():
    if _STATIC.exists():
        return HTMLResponse(_STATIC.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>index.html 缺失</h1>")


@app.get("/spec", response_class=HTMLResponse)
def spec():
    """设计规范页：把世界逻辑与软件设计规范作为软件内的主要展示对象。"""
    if _SPEC.exists():
        return HTMLResponse(_SPEC.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>spec.html 缺失</h1>")


@app.get("/vendor/{name}")
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


# ---------------------------------------------------------------------------
# 仿真 API
# ---------------------------------------------------------------------------

@app.get("/api/algorithms")
def algorithms():
    caps = runtime_capabilities()
    return {"algorithms": caps["algorithms"], "available": caps["available_algorithms"]}


@app.get("/api/meta")
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
        "battery_low_threshold": getattr(sys.modules.get("drone"), "BATTERY_LOW_THRESHOLD", 0.2),
    }


def _warming_response() -> Optional[JSONResponse]:
    """后台预热尚未结束（且会话还没建好）时返回 202，否则返回 None。

    首屏的 /api/snapshot 与 /api/map 会在预热线程持有 _lock 期间到达，
    不加这道快速回绝的话，请求会一直阻塞到地图解析完成（实测 4.3s）。
    """
    if _warm_done.is_set() or _session is not None:
        return None
    return JSONResponse({"warming": True, "detail": "仿真会话正在后台预热，请稍候"}, status_code=202)


@app.get("/api/snapshot")
def snapshot():
    warming = _warming_response()
    if warming is not None:
        return warming
    with _op_lock:
        return JSONResponse(_get_session().snapshot())


@app.post("/api/reset")
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
        with _op_lock:
            snap = _get_session().reset(algorithm=req.algorithm, seed=req.seed)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(snap)


@app.post("/api/step")
def step(count: int = 1):
    """推进 1~50 步。高倍速播放使用批量步进以降低 HTTP 请求压力。"""
    count = max(1, min(50, int(count)))
    with _op_lock:
        return JSONResponse(_get_session().step_many(count))


@app.post("/api/tasks/inject")
def inject_task(req: TaskInjectRequest):
    """运行中插入任务：不重置场景，下一步直接参与当前调度。"""
    try:
        with _op_lock:
            snap = _get_session().inject_task(**req.model_dump())
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(snap)


@app.get("/api/tasks/{task_id}/candidates")
def task_candidates(task_id: str, limit: int = 5):
    """返回某个活动任务的候选无人机解释性排名，不改变仿真状态。"""
    with _op_lock:
        return JSONResponse(_get_session().task_candidates(task_id, limit=limit))

@app.post("/api/task-stream")
def task_stream(req: TaskStreamRequest):
    """暂停/恢复自动任务生成，不影响当前待调度池与人工任务。"""
    with _op_lock:
        return JSONResponse(_get_session().set_task_generation_paused(req.paused))


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: str, req: TaskUpdateRequest):
    """修改待调度任务属性，供运行中优先级/SLA变更演示。"""
    try:
        payload = req.model_dump(exclude_none=True)
        with _op_lock:
            snap = _get_session().update_pending_task(task_id, **payload)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(snap)


@app.post("/api/drones/{drone_id}/charge")
def request_drone_charge(drone_id: str, req: DroneChargeRequest):
    """人工调无人机前往指定/最近开放机巢补能。"""
    try:
        with _op_lock:
            snap = _get_session().request_drone_charge(drone_id, station_id=req.station_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(snap)


@app.post("/api/drones/{drone_id}/incident")
def drone_incident(drone_id: str, req: DroneIncidentRequest):
    """运行中故障/恢复无人机；故障机未完成任务自动回收并等待重调度。"""
    try:
        with _op_lock:
            snap = _get_session().set_drone_out_of_service(
                drone_id, out_of_service=req.out_of_service, reason=req.reason)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(snap)


@app.post("/api/nests/{station_id}/incident")
def nest_incident(station_id: str, req: NestIncidentRequest):
    """运行中临时关闭/重新开放机巢。"""
    try:
        with _op_lock:
            snap = _get_session().set_nest_closed(
                station_id, closed=req.closed, reason=req.reason)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(snap)


@app.post("/api/rebuild")
def rebuild():
    """写回 simulation.json 后调用：热重载配置并重建 Environment。"""
    with _op_lock:
        return JSONResponse(_get_session().rebuild())


@app.get("/api/map")
def map_static():
    """静态地图几何：边界 + 建筑轮廓(含高度)，供 3D 视图一次性加载。"""
    warming = _warming_response()
    if warming is not None:
        return warming
    with _op_lock:
        return JSONResponse(_get_session().map_static())


# ---------------------------------------------------------------------------
# 运行态快照（内存检查点，不改 simulation.json）
# ---------------------------------------------------------------------------

@app.get("/api/checkpoints")
def checkpoints():
    with _op_lock:
        return {"checkpoints": _get_session().list_checkpoints()}


@app.post("/api/checkpoints")
def save_checkpoint(req: CheckpointRequest):
    try:
        with _op_lock:
            return JSONResponse(_get_session().save_checkpoint(req.name))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/checkpoints/{name}/load")
def load_checkpoint(name: str):
    try:
        with _op_lock:
            return JSONResponse(_get_session().load_checkpoint(name))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.delete("/api/checkpoints/{name}")
def delete_checkpoint(name: str):
    try:
        with _op_lock:
            return JSONResponse(_get_session().delete_checkpoint(name))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ---------------------------------------------------------------------------
# 一键演示场景（可逆配置 patch + 真实调度剧本）
# ---------------------------------------------------------------------------

@app.get("/api/scenarios")
def scenarios():
    return {
        "presets": scenario_presets.list_presets(),
        "has_restore_point": _scenario_backup_text is not None,
    }


@app.post("/api/scenarios/apply")
def apply_scenario(req: ScenarioApplyRequest):
    """加载答辩演示场景。首次加载时保存用户原 simulation.json，便于一键恢复。"""
    global _scenario_backup_text, _scenario_backup_runtime
    if not _SIM_JSON.exists():
        raise HTTPException(status_code=404, detail="simulation.json 不存在")
    try:
        preset = scenario_presets.get(req.key)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"未知演示场景: {req.key}")

    current_text = _SIM_JSON.read_text(encoding="utf-8")
    created_backup = False
    with _op_lock:
        session = _get_session()
        previous_runtime = {"algorithm": session.algorithm, "seed": session.seed}
        if _scenario_backup_text is None:
            # 第一次进入演示模式时保存用户真实配置；之后在多个预设之间切换，
            # 每次都从这份基线重新打 patch，避免上一个预设的泊位数/任务密度等
            # 悄悄泄漏到下一个预设。
            _scenario_backup_text = current_text
            _scenario_backup_runtime = dict(previous_runtime)
            created_backup = True
        base_text = _scenario_backup_text or current_text
        cfg = json.loads(base_text)
        cfg = _deep_merge(cfg, preset.get("config_patch") or {})
        _SIM_JSON.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            # rebuild 让模块级配置常量生效，再按预设算法/Seed 重置一次。
            session.rebuild()
            snap = session.reset(preset.get("algorithm", "ga"), int(preset.get("seed", 100)))
            if bool(preset.get("task_generation_paused", False)):
                snap = session.set_task_generation_paused(True)
            # 初始人工任务沿用 Environment.inject_task，位置为空时继续使用当前随机源合法点规则。
            for task in preset.get("initial_tasks") or []:
                snap = session.inject_task(**dict(task))
            snap = session.set_demo_context(req.key, preset["name"], preset.get("script") or [])
        except Exception as exc:
            # 加载失败时回到“点击加载前”的配置，而不是把用户卡在半套预设里。
            _SIM_JSON.write_text(current_text, encoding="utf-8")
            try:
                session.rebuild()
                session.reset(previous_runtime["algorithm"], int(previous_runtime["seed"]))
            except Exception:
                pass
            if created_backup:
                _scenario_backup_text = None
                _scenario_backup_runtime = None
            raise HTTPException(status_code=400, detail=f"演示场景加载失败，配置已回滚: {exc}")
    return JSONResponse(snap)


@app.post("/api/scenarios/next")
def next_scenario_action():
    """执行当前演示剧本的下一幕。动作仍调用真实 step/inject/incident 接口。"""
    try:
        with _op_lock:
            return JSONResponse(_get_session().advance_demo())
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/scenarios/restore")
def restore_scenario():
    """恢复进入演示模式前的 simulation.json 与算法/Seed。"""
    global _scenario_backup_text, _scenario_backup_runtime
    if _scenario_backup_text is None:
        raise HTTPException(status_code=409, detail="当前没有可恢复的演示前配置")
    restore_text = _scenario_backup_text
    runtime = dict(_scenario_backup_runtime or {})
    current_text = _SIM_JSON.read_text(encoding="utf-8") if _SIM_JSON.exists() else ""
    _SIM_JSON.write_text(restore_text, encoding="utf-8")
    try:
        with _op_lock:
            session = _get_session()
            session.rebuild()
            snap = session.reset(runtime.get("algorithm", "greedy"), int(runtime.get("seed", 100)))
            session.clear_demo_context()
            snap = session.snapshot()
    except Exception as exc:
        if current_text:
            _SIM_JSON.write_text(current_text, encoding="utf-8")
        raise HTTPException(status_code=400, detail=f"恢复演示前配置失败: {exc}")
    _scenario_backup_text = None
    _scenario_backup_runtime = None
    return JSONResponse(snap)


# ---------------------------------------------------------------------------
# 场景库（可持久化、可导入导出；与运行态 checkpoint 分工明确）
# ---------------------------------------------------------------------------

def _read_scheduler_yaml() -> Dict[str, Any]:
    import yaml
    if not _ALG_YAML.exists():
        return {}
    with open(_ALG_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _write_scheduler_yaml(cfg: Dict[str, Any]) -> None:
    import yaml
    with open(_ALG_YAML, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg or {}, f, allow_unicode=True, sort_keys=False)


@app.get("/api/scene-library")
def scene_library_list():
    return {"scenes": _SCENE_LIBRARY.list()}


@app.post("/api/scene-library")
def scene_library_save(req: SceneLibrarySaveRequest):
    if not _SIM_JSON.exists():
        raise HTTPException(status_code=404, detail="simulation.json 不存在")
    try:
        with _op_lock:
            session = _get_session()
            doc = _SCENE_LIBRARY.save(
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
            "scenes": _SCENE_LIBRARY.list()}


@app.get("/api/scene-library/{scene_id}")
def scene_library_export(scene_id: str):
    try:
        return JSONResponse(_SCENE_LIBRARY.get(scene_id))
    except KeyError:
        raise HTTPException(status_code=404, detail="场景不存在")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/scene-library/import")
def scene_library_import(req: SceneLibraryImportRequest):
    try:
        doc = _SCENE_LIBRARY.import_document(req.document)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"scene": {k: v for k, v in doc.items() if k not in {"simulation_config", "scheduler_config"}},
            "scenes": _SCENE_LIBRARY.list()}


@app.delete("/api/scene-library/{scene_id}")
def scene_library_delete(scene_id: str):
    try:
        _SCENE_LIBRARY.delete(scene_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="场景不存在")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "scenes": _SCENE_LIBRARY.list()}


@app.post("/api/scene-library/{scene_id}/apply")
def scene_library_apply(scene_id: str):
    """事务式应用场景库配置，并按场景记录的算法/Seed 重建。

    场景库负责“可复现初始配置”；运行态 checkpoint 负责“精确动态节点”。
    为避免用户在答辩预设的临时配置上再次叠加持久场景，演示模式中禁止应用。
    """
    global _scenario_backup_text, _scenario_backup_runtime
    if _scenario_backup_text is not None:
        raise HTTPException(status_code=409, detail="当前处于答辩演示场景，请先点击“恢复演示前配置”再应用场景库")
    try:
        doc = _SCENE_LIBRARY.get(scene_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="场景不存在")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    old_sim = _SIM_JSON.read_text(encoding="utf-8") if _SIM_JSON.exists() else ""
    old_alg = _ALG_YAML.read_text(encoding="utf-8") if _ALG_YAML.exists() else ""
    _SIM_JSON.write_text(json.dumps(doc["simulation_config"], ensure_ascii=False, indent=2), encoding="utf-8")
    if doc.get("scheduler_config") is not None:
        _write_scheduler_yaml(doc["scheduler_config"])
    try:
        with _op_lock:
            session = _get_session()
            session.rebuild()
            snap = session.reset(doc.get("algorithm", "ga"), int(doc.get("seed", 100)))
            session.clear_demo_context()
            snap = session.snapshot()
    except Exception as exc:
        if old_sim:
            _SIM_JSON.write_text(old_sim, encoding="utf-8")
        if old_alg:
            _ALG_YAML.write_text(old_alg, encoding="utf-8")
        try:
            with _op_lock:
                session = _get_session()
                session.rebuild()
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=f"场景应用失败，配置已回滚: {exc}")
    return JSONResponse(snap)


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
    try:
        assert_valid_simulation_config(cfg)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"配置校验失败：{exc}")
    _SIM_JSON.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "config": cfg}


@app.post("/api/scene-layout")
def save_scene_layout(req: SceneLayoutRequest):
    """保存机巢网络/禁飞区布局并热重建。

    仅 random 数据源使用 simulation.json 中的机巢布局；CSV/GeoJSON 场景应直接
    编辑其源文件，避免界面看似保存成功但运行时实际未生效。写入后若重建失败，
    会回滚原配置。
    """
    if not _SIM_JSON.exists():
        raise HTTPException(status_code=404, detail="simulation.json 不存在")
    cfg = json.loads(_SIM_JSON.read_text(encoding="utf-8"))
    if str(cfg.get("data_source", {}).get("type", "random")).lower() != "random":
        raise HTTPException(status_code=400, detail="场景布局编辑器当前仅支持 random 数据源；CSV/GeoJSON 请编辑对应导入文件")

    bounds = _get_session().map_static().get("bounds", [0, 0, 0, 0])
    minx, miny, maxx, maxy = [float(v) for v in bounds]
    stations = []
    ids = set()
    for i, raw in enumerate(req.charging_stations):
        try:
            sid = int(raw.get("station_id", i))
            x = float(raw.get("x"))
            y = float(raw.get("y"))
            berths = max(1, int(raw.get("berths", cfg.get("nest", {}).get("berths", 2))))
            swap = float(raw.get("swap_time_seconds", cfg.get("nest", {}).get("swap_time_seconds", 180)))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"第 {i+1} 个机巢参数格式无效")
        if sid in ids:
            raise HTTPException(status_code=400, detail=f"机巢 ID 重复: {sid}")
        if not (minx <= x <= maxx and miny <= y <= maxy):
            raise HTTPException(status_code=400, detail=f"机巢 {sid} 超出当前地图边界")
        if swap <= 0:
            raise HTTPException(status_code=400, detail=f"机巢 {sid} 换电时间必须大于 0")
        ids.add(sid)
        stations.append({
            "station_id": sid, "x": x, "y": y, "berths": berths,
            "swap_time_seconds": swap,
            "charging_power": float(raw.get("charging_power", 50.0)),
        })
    if not stations:
        raise HTTPException(status_code=400, detail="至少保留一个机巢")

    nfz = dict(req.no_fly_zones or {})
    nfz.setdefault("enabled", True)
    nfz.setdefault("reserve_margin_m", 0.0)
    nfz.setdefault("zones", [])
    try:
        from no_fly_zone import load_no_fly_zones
        zone_set = load_no_fly_zones(nfz)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"禁飞区配置无效: {exc}")
    if zone_set:
        for st in stations:
            if zone_set.contains(st["x"], st["y"]):
                raise HTTPException(status_code=400, detail=f"机巢 {st['station_id']} 位于禁飞区（含安全余量）内，请调整布局")

    # 机巢落在建筑物内部会造成路径终点天然不可达，保存前直接拦截。
    try:
        from shapely.geometry import Point
        buildings = getattr(_get_session().env, "high_buildings", []) or []
        for st in stations:
            pt = Point(st["x"], st["y"])
            if any((b.get("geometry") is not None and b["geometry"].buffer(1.0).contains(pt)) for b in buildings):
                raise HTTPException(status_code=400, detail=f"机巢 {st['station_id']} 位于建筑物内部，请重新取点")
    except HTTPException:
        raise
    except Exception:
        # 建筑几何校验是增强项，异常时不阻断其它已完成的边界/禁飞区校验。
        pass

    old_text = _SIM_JSON.read_text(encoding="utf-8")
    cfg["charging_stations"] = stations
    cfg["no_fly_zones"] = nfz
    _SIM_JSON.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        with _op_lock:
            snap = _get_session().rebuild()
    except Exception as exc:
        _SIM_JSON.write_text(old_text, encoding="utf-8")
        try:
            with _op_lock:
                _get_session().rebuild()
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=f"场景重建失败，已回滚配置: {exc}")
    return JSONResponse(snap)


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
# 一键实验 API（独立子进程，不影响当前自由仿真会话）
# ---------------------------------------------------------------------------

@app.get("/api/experiments/presets")
def experiment_presets():
    return {"presets": experiment_service.presets()}


@app.get("/api/experiments/status")
def experiment_status():
    return experiment_service.status()


@app.post("/api/experiments/start")
def experiment_start(req: ExperimentStartRequest):
    try:
        return experiment_service.start(req.preset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.get("/api/experiments/package")
def experiment_package():
    """构建并下载最近一次正式 conclusion 实验的结项证据包。"""
    try:
        from build_conclusion_package import build
        path = build(None, None, allow_missing=False)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return FileResponse(str(path), media_type="application/zip", filename=path.name)


# ---------------------------------------------------------------------------
# 对比看板 API
# ---------------------------------------------------------------------------

_CSV_FILES = [
    "frontend_greedy_metrics.csv",
    "backend_si_metrics.csv",
    "backend_ga_metrics.csv",
    "backend_ortools_metrics.csv",
    "backend_wx_metrics.csv",
    "one_click_latest.csv",
]


def _resolve_basis(meta_rows: List[Dict[str, Any]]) -> Tuple[Optional[int], List[Dict[str, Any]]]:
    """按「生成任务数」的众数确定共同口径，返回 (基准任务数, 偏离行列表)。

    为什么不用总步数：总步数是 episode 提前跑完时的**运行结果**，同一设定下各算法
    天然互不相等，拿它当基准会把正常的性能差异误报成口径不一致（曾实测 10 行步数
    全不相等 → 众数退化成无意义的 858 → 9/10 行被误标）。完成率等指标的分母是
    生成任务数，所以只有它不一致才是真正不可比。

    众数只出现一次时返回 (None, [])：宁可不给基准，也不硬选一个误导人的。
    """
    counts: Dict[int, int] = {}
    for row in meta_rows:
        try:
            n = int(float(row.get("生成任务数", 0)))
        except (TypeError, ValueError):
            continue
        if n > 0:
            counts[n] = counts.get(n, 0) + 1
    if not counts:
        return None, []
    top = max(counts.items(), key=lambda kv: (kv[1], -kv[0]))
    if top[1] < 2:
        return None, []
    basis = top[0]
    off: List[Dict[str, Any]] = []
    for row in meta_rows:
        try:
            n = int(float(row.get("生成任务数", 0)))
            steps = int(float(row.get("总步数", 0)))
        except (TypeError, ValueError):
            continue
        if n > 0 and n != basis:
            off.append({"算法": row.get("算法"), "生成任务数": n, "总步数": steps})
    return basis, off


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
        df["_来源"] = path.name          # 记录每行来自哪个文件，供下面标注来源
        frames.append(df)
    if not frames:
        return {"rows": [], "columns": [], "basis": None, "inconsistent": []}

    data = pd.concat(frames, ignore_index=True)
    # 先去掉"空跑"行：全零 / 全 NaN 的一行没有任何评测意义。
    # 否则 one_click_latest.csv 这类全零记录会在下面 keep="last" 时
    # 覆盖掉同一个算法在其它 CSV 里的真实结果（实测 greedy/ga/pso/ortools 被清零）。
    num_cols_all = [c for c in data.columns if c not in ("算法", "_来源")]
    numeric = data[num_cols_all].apply(pd.to_numeric, errors="coerce")
    valid_mask = numeric.abs().sum(axis=1) > 0
    data = data.loc[valid_mask].reset_index(drop=True)
    if data.empty:
        return {"rows": [], "columns": []}

    # 同一算法取最后一条（保留最近一次评测），但只从有效行里取
    data = data.drop_duplicates("算法", keep="last").reset_index(drop=True)

    # 口径守卫：只有分母（生成任务数）不一致才算不可比。历史上的真实反例是 ga 以
    # 30 任务进图、其余算法 60 任务。这里只标注、不改数值、不剔除行。
    # 只保留数值列 + 算法列，去掉总步数/完成任务数等冗余
    drop_cols = {"总步数", "完成任务数", "生成任务数", "换电总次数"}
    keep_cols = [c for c in data.columns if c not in ("算法", "_来源") and c not in drop_cols]
    rows = data[["算法"] + keep_cols].to_dict(orient="records")
    scale_rows = data[["算法", "总步数", "生成任务数", "_来源"]].to_dict(orient="records")
    basis_tasks, inconsistent = _resolve_basis(scale_rows)
    flagged = {i["算法"] for i in inconsistent}

    def _clean(v):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        if isinstance(v, float):
            return round(v, 4)
        return v

    def _as_int(v):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None

    for row, scale in zip(rows, scale_rows):
        for k in list(row.keys()):
            row[k] = _clean(row[k])
        row["口径"] = {
            "生成任务数": _as_int(scale.get("生成任务数")),
            "总步数": _as_int(scale.get("总步数")),
            "偏离": row.get("算法") in flagged,
            # keep="last" 会让后读到的文件顶掉先读到的；标出来源，避免答辩时
            # 说不清这一行到底是手工评测还是一次一键实验的结果。
            "来源": scale.get("_来源"),
        }

    return {
        "rows": rows,
        "columns": keep_cols,
        "basis": {"生成任务数": basis_tasks} if basis_tasks is not None else None,
        "inconsistent": inconsistent,
    }
