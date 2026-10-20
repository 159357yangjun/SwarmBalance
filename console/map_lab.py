"""Isolated GIS preview endpoints; never mutates SimSession or legacy Yangpu data."""
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "map" / "fosi"
PAGE = Path(__file__).resolve().parent / "static" / "map_lab.html"
LAYERS = ("water", "landuse", "buildings", "roads", "railways")
MAX_GEOJSON_BYTES = 12 * 1024 * 1024

@router.get("/map-lab")
def map_lab_page():
    return FileResponse(PAGE, media_type="text/html; charset=utf-8")

@router.get("/api/map-lab/status")
def map_lab_status():
    region = json.loads((DATA_DIR / "region.json").read_text(encoding="utf-8"))
    output = DATA_DIR / "output"
    layers = {}
    for name in LAYERS:
        path = output / (name + ".geojson")
        size = path.stat().st_size if path.is_file() else 0
        layers[name] = {"ready": 0 < size <= MAX_GEOJSON_BYTES, "bytes": size}
    return {"region": region, "layers": layers,
            "manifest_ready": (output / "data_manifest.json").is_file(),
            "simulation_connected": False,
            "hint": "只读 GIS 地图预览；没有接入当前杨浦仿真空间。"}

@router.get("/api/map-lab/layers/{layer}")
def map_lab_layer(layer: str):
    if layer not in LAYERS:
        raise HTTPException(status_code=404, detail="未知的地图图层")
    path = DATA_DIR / "output" / (layer + ".geojson")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="未下载该图层；运行 python scripts/prepare_fosi_map.py")
    if path.stat().st_size > MAX_GEOJSON_BYTES:
        raise HTTPException(status_code=413, detail="图层超过单文件预览限制；需要分块和矢量瓦片")
    return FileResponse(path, media_type="application/geo+json", headers={"Cache-Control":"no-store"})
