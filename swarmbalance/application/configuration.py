"""Configuration persistence and layout operations shared by transport adapters."""
from __future__ import annotations
import copy
import json
from typing import Any, Dict, List, Optional, Tuple
from swarmbalance.contracts.errors import ApplicationError
from swarmbalance.infrastructure.config.validation import assert_valid_simulation_config
from swarmbalance.paths import CONFIG_DIR, SCHEDULER_CONFIG
_SIM_JSON = CONFIG_DIR / "simulation.json"
_ALG_YAML = SCHEDULER_CONFIG

def _deep_merge(base: Dict, patch: Dict) -> Dict:
    """递归合并 dict，patch 覆盖 base（不丢失 base 中未提及的字段）。"""
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base

def _read_scheduler_yaml() -> Dict[str, Any]:
    import yaml
    if not _ALG_YAML.exists():
        return {}
    with open(_ALG_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _write_scheduler_yaml(cfg: Dict[str, Any]) -> None:
    import yaml
    # 内容没变就**一个字节都不要写**。safe_load + safe_dump 是破坏性往返：
    # config/schedulers.yaml 实测 180 行里有 111 行注释（文件头写着"谁消费这个配置"、
    # seed 为何固定以保证可复现、各段分隔线），往返一次只剩 67 行、注释全灭。
    # 而界面上「保存并应用」即使什么都没改也会走到这里，等于一次空操作静默删掉
    # 整个配置文件的文档。真正要保留注释需要 round-trip 解析器（ruamel.yaml），
    # 那是新增依赖，得先征询；这里先堵住"没改也写"这条最坏路径。
    if cfg == _read_scheduler_yaml():
        return
    with open(_ALG_YAML, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg or {}, f, allow_unicode=True, sort_keys=False)

def get_config():
    if not _SIM_JSON.exists():
        raise ApplicationError(status_code=404, detail="simulation.json 不存在")
    return json.loads(_SIM_JSON.read_text(encoding="utf-8"))

def save_config(patch: Dict[str, Any]):
    """深合并写回 simulation.json（不丢失未提及字段），不自动重建。"""
    if not _SIM_JSON.exists():
        raise ApplicationError(status_code=404, detail="simulation.json 不存在")
    cfg = json.loads(_SIM_JSON.read_text(encoding="utf-8"))
    cfg = _deep_merge(cfg, patch)
    try:
        assert_valid_simulation_config(cfg)
    except ValueError as exc:
        raise ApplicationError(status_code=400, detail=f"配置校验失败：{exc}")
    _SIM_JSON.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "config": cfg}

def save_scene_layout(payload: Dict[str, Any], context):
    """保存机巢网络/禁飞区布局并热重建。

    仅 random 数据源使用 simulation.json 中的机巢布局；CSV/GeoJSON 场景应直接
    编辑其源文件，避免界面看似保存成功但运行时实际未生效。写入后若重建失败，
    会回滚原配置。
    """
    if not _SIM_JSON.exists():
        raise ApplicationError(status_code=404, detail="simulation.json 不存在")
    cfg = json.loads(_SIM_JSON.read_text(encoding="utf-8"))
    if str(cfg.get("data_source", {}).get("type", "random")).lower() != "random":
        raise ApplicationError(status_code=400, detail="场景布局编辑器当前仅支持 random 数据源；CSV/GeoJSON 请编辑对应导入文件")

    bounds = context.get_session().map_static().get("bounds", [0, 0, 0, 0])
    minx, miny, maxx, maxy = [float(v) for v in bounds]
    stations = []
    ids = set()
    for i, raw in enumerate(payload["charging_stations"]):
        try:
            sid = int(raw.get("station_id", i))
            x = float(raw.get("x"))
            y = float(raw.get("y"))
            berths = max(1, int(raw.get("berths", cfg.get("nest", {}).get("berths", 2))))
            swap = float(raw.get("swap_time_seconds", cfg.get("nest", {}).get("swap_time_seconds", 180)))
        except (TypeError, ValueError):
            raise ApplicationError(status_code=400, detail=f"第 {i+1} 个机巢参数格式无效")
        if sid in ids:
            raise ApplicationError(status_code=400, detail=f"机巢 ID 重复: {sid}")
        if not (minx <= x <= maxx and miny <= y <= maxy):
            raise ApplicationError(status_code=400, detail=f"机巢 {sid} 超出当前地图边界")
        if swap <= 0:
            raise ApplicationError(status_code=400, detail=f"机巢 {sid} 换电时间必须大于 0")
        ids.add(sid)
        stations.append({
            "station_id": sid, "x": x, "y": y, "berths": berths,
            "swap_time_seconds": swap,
            "charging_power": float(raw.get("charging_power", 50.0)),
        })
    if not stations:
        raise ApplicationError(status_code=400, detail="至少保留一个机巢")

    nfz = dict(payload["no_fly_zones"] or {})
    nfz.setdefault("enabled", True)
    nfz.setdefault("reserve_margin_m", 0.0)
    nfz.setdefault("zones", [])
    try:
        from swarmbalance.simulation.routing.no_fly_zone import load_no_fly_zones
        zone_set = load_no_fly_zones(nfz)
    except Exception as exc:
        raise ApplicationError(status_code=400, detail=f"禁飞区配置无效: {exc}")
    if zone_set:
        for st in stations:
            if zone_set.contains(st["x"], st["y"]):
                raise ApplicationError(status_code=400, detail=f"机巢 {st['station_id']} 位于禁飞区（含安全余量）内，请调整布局")

    # 机巢落在建筑物内部会造成路径终点天然不可达，保存前直接拦截。
    try:
        from shapely.geometry import Point
        buildings = getattr(context.get_session().env, "high_buildings", []) or []
        for st in stations:
            pt = Point(st["x"], st["y"])
            if any((b.get("geometry") is not None and b["geometry"].buffer(1.0).contains(pt)) for b in buildings):
                raise ApplicationError(status_code=400, detail=f"机巢 {st['station_id']} 位于建筑物内部，请重新取点")
    except ApplicationError:
        raise
    except Exception:
        # 建筑几何校验是增强项，异常时不阻断其它已完成的边界/禁飞区校验。
        pass

    old_text = _SIM_JSON.read_text(encoding="utf-8")
    cfg["charging_stations"] = stations
    cfg["no_fly_zones"] = nfz
    _SIM_JSON.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        with context.operation_lock:
            snap = context.get_session().rebuild()
    except Exception as exc:
        _SIM_JSON.write_text(old_text, encoding="utf-8")
        try:
            with context.operation_lock:
                context.get_session().rebuild()
        except Exception:
            pass
        raise ApplicationError(status_code=400, detail=f"场景重建失败，已回滚配置: {exc}")
    return snap

def get_scheduler_config():
    if not _ALG_YAML.exists():
        raise ApplicationError(status_code=404, detail="config.yaml 不存在")
    import yaml
    with open(_ALG_YAML, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def save_scheduler_config(patch: Dict[str, Any]):
    """深合并写回 config/schedulers.yaml。调度器每 reset 重建时会读到新值。"""
    import yaml
    if not _ALG_YAML.exists():
        raise ApplicationError(status_code=404, detail="config.yaml 不存在")
    with open(_ALG_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    # 见 _write_scheduler_yaml 的注释：safe_load + safe_dump 是破坏性往返，会把
    # config/schedulers.yaml 的 111 行注释全部抹掉。内容没变就一个字节都不写。
    # 注意必须先留快照再合并：_deep_merge 是**原地改写 base 并返回同一个对象**，
    # 直接写 `if _deep_merge(cfg, patch) != cfg` 等于自己和自己比，恒为假，
    # 会把所有保存请求静默吞掉（我第一版就犯了这个错，靠"真改一个值"那侧的
    # 测试才抓出来 —— 只测"空 patch 不该写"会给出假绿灯）。
    before = copy.deepcopy(cfg)
    merged = _deep_merge(cfg, patch)
    if merged != before:
        with open(_ALG_YAML, "w", encoding="utf-8") as f:
            yaml.safe_dump(merged, f, allow_unicode=True, sort_keys=False)
    return {"ok": True, "config": merged}
