"""One data-source factory; concrete implementations have separate modules."""
from typing import Dict, Optional
from swarmbalance.infrastructure.config.loader import get_shared_config
from swarmbalance.contracts.data_source import DataSource, DroneSpec, NestSpec, TaskSpec
from swarmbalance.infrastructure.data_sources.common import StaticTaskSource
from swarmbalance.infrastructure.data_sources.random import RandomDataSource
from swarmbalance.infrastructure.data_sources.csv import CSVDataSource
from swarmbalance.infrastructure.data_sources.geojson import GeoJSONDataSource

def build_data_source(cfg: Optional[Dict] = None) -> DataSource:
    """根据 simulation.json 的 data_source.type 选择并构建数据源。

    未配置或无法识别时回落到 RandomDataSource，保持历史行为。
    """
    cfg = cfg or get_shared_config()
    ds_cfg = cfg.get("data_source", {}) or {}
    stype = str(ds_cfg.get("type", "random")).strip().lower()

    if stype == "csv":
        return CSVDataSource(cfg=cfg)
    if stype in ("geojson", "geo_json"):
        return GeoJSONDataSource(cfg=cfg)
    if stype == "enterprise":
        from swarmbalance.infrastructure.data_sources.enterprise import EnterpriseDataSource
        e_cfg = ds_cfg.get("enterprise", {}) or {}
        return EnterpriseDataSource(
            base_url=e_cfg.get("base_url"),
            api_token=e_cfg.get("api_token"),
            timeout=float(e_cfg.get("timeout", 10.0)),
            coord_system=e_cfg.get("coord_system", "lonlat"),
            verify=bool(e_cfg.get("verify", True)),
            live=bool(e_cfg.get("live", False)),
            cfg=cfg,
        )
    return RandomDataSource(cfg=cfg)
