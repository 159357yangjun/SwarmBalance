"""Persistent scene library for the local SwarmBalance console.

A scene bundle captures the pieces needed to reproduce a *configuration*:
- ``config/simulation.json``;
- ``backend_si/config.yaml`` (optional but enabled by default);
- preferred algorithm + seed.

It intentionally does not serialize the live Environment object. Runtime checkpoints
remain an in-memory mechanism for restoring an exact dynamic node; scene bundles are
portable JSON files intended for sharing, import/export and repeatable demonstrations.
"""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from uuid import uuid4

from console.config_validation import assert_valid_simulation_config

SCHEMA_VERSION = 1
MAX_SCENES = 50
_MAX_DOC_BYTES = 2 * 1024 * 1024
_ID_RE = re.compile(r"^scene_[0-9a-f]{12}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean_text(value: Any, *, field: str, max_len: int, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field} 不能为空")
    if len(text) > max_len:
        raise ValueError(f"{field} 不能超过 {max_len} 个字符")
    return text


def validate_document(raw: Dict[str, Any], *, for_import: bool = False) -> Dict[str, Any]:
    """Validate and normalize a scene document without mutating the caller's dict."""
    if not isinstance(raw, dict):
        raise ValueError("场景文件必须是 JSON 对象")
    doc = copy.deepcopy(raw)
    version = int(doc.get("schema_version", SCHEMA_VERSION))
    if version != SCHEMA_VERSION:
        raise ValueError(f"不支持的场景格式版本: {version}（当前支持 {SCHEMA_VERSION}）")

    name = _clean_text(doc.get("name"), field="场景名称", max_len=80, required=True)
    description = _clean_text(doc.get("description"), field="场景说明", max_len=500)
    simulation = doc.get("simulation_config")
    if not isinstance(simulation, dict) or not simulation:
        raise ValueError("场景文件缺少 simulation_config")
    assert_valid_simulation_config(simulation)
    stations = simulation.get("charging_stations") or []
    if len(stations) > 100:
        raise ValueError("机巢数量超过场景库安全上限（100）")

    scheduler = doc.get("scheduler_config")
    if scheduler is not None and not isinstance(scheduler, dict):
        raise ValueError("scheduler_config 必须是 JSON 对象或 null")

    algorithm = str(doc.get("algorithm") or "ga").strip().lower()
    if algorithm not in {"greedy", "ga", "pso", "ortools"}:
        raise ValueError(f"不支持的算法: {algorithm}")
    try:
        seed = int(doc.get("seed", 100))
    except (TypeError, ValueError):
        raise ValueError("seed 必须是整数")
    if abs(seed) > 2_147_483_647:
        raise ValueError("seed 超出支持范围")

    normalized = {
        "schema_version": SCHEMA_VERSION,
        "scene_id": str(doc.get("scene_id") or ""),
        "name": name,
        "description": description,
        "created_at": str(doc.get("created_at") or _utc_now()),
        "updated_at": str(doc.get("updated_at") or _utc_now()),
        "algorithm": algorithm,
        "seed": seed,
        "simulation_config": simulation,
        "scheduler_config": scheduler,
        "source": str(doc.get("source") or ("import" if for_import else "local")),
    }
    payload = json.dumps(normalized, ensure_ascii=False).encode("utf-8")
    if len(payload) > _MAX_DOC_BYTES:
        raise ValueError("场景文件过大（上限 2 MiB）")
    return normalized


class SceneLibrary:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, scene_id: str) -> Path:
        if not _ID_RE.match(str(scene_id or "")):
            raise ValueError("非法场景 ID")
        return self.root / f"{scene_id}.json"

    def _read_path(self, path: Path) -> Dict[str, Any]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        doc = validate_document(raw)
        if not doc.get("scene_id"):
            doc["scene_id"] = path.stem
        return doc

    def list(self) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for path in self.root.glob("scene_*.json"):
            try:
                d = self._read_path(path)
            except Exception:
                # A hand-edited/corrupt file should not make the whole console unusable.
                continue
            sim = d.get("simulation_config") or {}
            mix = ((sim.get("heterogeneous") or {}).get("fleet_mix") or {})
            rows.append({
                "scene_id": d["scene_id"],
                "name": d["name"],
                "description": d.get("description", ""),
                "updated_at": d.get("updated_at", ""),
                "algorithm": d.get("algorithm", "ga"),
                "seed": d.get("seed", 100),
                "num_drones": int((sim.get("environment") or {}).get("num_drones", 0) or 0),
                "nest_count": len(sim.get("charging_stations") or []),
                "fleet_mix": mix,
            })
        rows.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
        return rows

    def get(self, scene_id: str) -> Dict[str, Any]:
        path = self._path(scene_id)
        if not path.exists():
            raise KeyError(scene_id)
        return self._read_path(path)

    def save(self, *, name: str, description: str, simulation_config: Dict[str, Any],
             scheduler_config: Optional[Dict[str, Any]], algorithm: str, seed: int,
             source: str = "local") -> Dict[str, Any]:
        if len(self.list()) >= MAX_SCENES:
            raise ValueError(f"场景库最多保存 {MAX_SCENES} 个场景，请先删除不需要的场景")
        scene_id = f"scene_{uuid4().hex[:12]}"
        now = _utc_now()
        doc = validate_document({
            "schema_version": SCHEMA_VERSION,
            "scene_id": scene_id,
            "name": name,
            "description": description,
            "created_at": now,
            "updated_at": now,
            "algorithm": algorithm,
            "seed": seed,
            "simulation_config": simulation_config,
            "scheduler_config": scheduler_config,
            "source": source,
        })
        self._path(scene_id).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        return doc

    def import_document(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        doc = validate_document(raw, for_import=True)
        return self.save(
            name=doc["name"],
            description=doc.get("description", ""),
            simulation_config=doc["simulation_config"],
            scheduler_config=doc.get("scheduler_config"),
            algorithm=doc["algorithm"],
            seed=doc["seed"],
            source="import",
        )

    def delete(self, scene_id: str) -> None:
        path = self._path(scene_id)
        if not path.exists():
            raise KeyError(scene_id)
        path.unlink()
