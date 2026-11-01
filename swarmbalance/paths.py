"""Canonical project resource locations and legacy-path resolution."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
MAPS_DIR = DATA_DIR / "maps"
DEFAULT_MAP = MAPS_DIR / "yangpu" / "part_of_yangpu.osm"
SCHEDULER_CONFIG = CONFIG_DIR / "schedulers.yaml"
STATIC_DIR = PROJECT_ROOT / "swarmbalance" / "web" / "static"
OSM_CACHE_DIR = DATA_DIR / "cache" / "osm"
RESULTS_DIR = PROJECT_ROOT / "results"


def resolve_resource(value) -> Path:
    """Resolve project resources, including paths stored in older scene configs."""
    path = Path(value)
    if path.is_absolute():
        # Known old in-project resource locations may be embedded as absolute paths.
        try:
            name = path.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return path
        if name != "backend_si/config.yaml" and not name.startswith(("frontend/data/map/", "config/import/", "data/map/")):
            return path
    else:
        name = str(value).replace("\\", "/")
    if name in {"data/map/part_of_yangpu.osm", "frontend/data/map/part_of_yangpu.osm"}:
        return DEFAULT_MAP
    if name == "backend_si/config.yaml":
        return SCHEDULER_CONFIG
    for prefix in ("../config/import/", "config/import/", "import/"):
        if name.startswith(prefix):
            return CONFIG_DIR / "import_templates" / name[len(prefix):]
    if name.startswith("data/map/"):
        return MAPS_DIR / name[len("data/map/"):]
    if name.startswith("../config/"):
        return CONFIG_DIR / name[len("../config/"):]
    if path.is_file():
        return path.resolve()
    candidates = (PROJECT_ROOT / path, PROJECT_ROOT / "frontend" / path,
                  CONFIG_DIR / path.name)
    return next((candidate for candidate in candidates if candidate.exists()), candidates[0])
