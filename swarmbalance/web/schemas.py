"""HTTP request models; preserve existing payload contracts."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class ResetRequest(BaseModel):
    algorithm: str = "greedy"
    seed: int = 100

class ConfigPatch(BaseModel):
    patch: Dict[str, Any]

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
