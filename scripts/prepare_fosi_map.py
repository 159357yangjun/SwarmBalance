#!/usr/bin/env python3
"""Download Geofabrik Liaoning OSM and crop Fosi display-only GeoJSON.

No OSM public tile bulk download. This is a way-only *subset*, NOT validated
navigation/obstacle data. Run from the repository root.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "map" / "fosi"
REGION = json.loads((BASE / "region.json").read_text(encoding="utf-8"))
BBOX = tuple(REGION["bbox_wgs84_lonlat"])
SOURCE = REGION["source_url"]
KINDS = ("buildings", "roads", "water", "landuse", "railways")


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    part.replace(path)


def get_pbf(path):
    if path.is_file() and path.stat().st_size:
        print("[cache]", path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    print("[download]", SOURCE)
    try:
        request = Request(SOURCE, headers={"User-Agent":"SwarmBalance-Fosi-Research/0.1"})
        with urlopen(request, timeout=90) as response, part.open("wb") as target:
            while True:
                buf = response.read(1024 * 1024)
                if not buf:
                    break
                target.write(buf)
        if part.stat().st_size == 0:
            raise RuntimeError("下载了空的 PBF 文件")
        part.replace(path)
    except Exception:
        part.unlink(missing_ok=True)
        raise


def crop_pbf(path):
    try:
        import osmium
        from shapely.geometry import LineString, Polygon, box, mapping
    except ImportError as exc:
        raise RuntimeError("请先安装可选依赖：python -m pip install osmium shapely") from exc

    west, south, east, north = BBOX
    crop = box(*BBOX)
    result = {k: [] for k in KINDS}
    invalid = 0

    def parts(geometry):
        if geometry.is_empty:
            return
        if geometry.geom_type in ("Polygon", "LineString"):
            yield geometry
        elif hasattr(geometry, "geoms"):
            for g in geometry.geoms:
                yield from parts(g)

    class Handler(osmium.SimpleHandler):
        def way(self, way):
            nonlocal invalid
            tags = dict(way.tags)
            kinds = []
            if tags.get("building") not in (None, "", "no"):
                kinds.append("buildings")
            if "highway" in tags:
                kinds.append("roads")
            if "waterway" in tags or tags.get("natural") == "water" or tags.get("landuse") == "reservoir":
                kinds.append("water")
            if "landuse" in tags or tags.get("natural") in ("wood","grassland","scrub","wetland"):
                kinds.append("landuse")
            if "railway" in tags:
                kinds.append("railways")
            if not kinds:
                return
            try:
                pts = [(float(n.lon),float(n.lat)) for n in way.nodes if n.location.valid()]
                if len(pts) < 2 or not all(math.isfinite(x) and math.isfinite(y) for x,y in pts):
                    return
                xs, ys = zip(*pts)
                if max(xs) < west or min(xs) > east or max(ys) < south or min(ys) > north:
                    return
                polygon = Polygon(pts) if len(pts)>=4 and pts[0]==pts[-1] else None
                if polygon is not None and not polygon.is_valid:
                    polygon = polygon.buffer(0)
                line = LineString(pts)
                properties = {"osm_id":"way:"+str(way.id),"source":"OpenStreetMap",
                              "height":tags.get("height"),"building_levels":tags.get("building:levels")}
                for kind in kinds:
                    if kind=="buildings":
                        if polygon is None or polygon.is_empty:
                            continue
                        geometry=polygon
                    elif kind in ("water","landuse") and polygon is not None:
                        geometry=polygon
                    else:
                        geometry=line
                    for geom in parts(geometry.intersection(crop)):
                        if kind=="buildings" and geom.geom_type!="Polygon":
                            continue
                        result[kind].append({"type":"Feature","properties":properties,"geometry":mapping(geom)})
            except (ValueError, TypeError, RuntimeError, OverflowError):
                invalid+=1

    Handler().apply_file(str(path), locations=True)
    output=BASE/"output"
    counts={}
    for kind in KINDS:
        save_json(output/(kind+".geojson"),{"type":"FeatureCollection","features":result[kind]})
        counts[kind]=len(result[kind])
        print("[layer]",kind,counts[kind])
    save_json(output/"data_manifest.json",{
      "region":REGION["id"],"bbox_wgs84_lonlat":BBOX,
      "source":SOURCE,"source_sha256":sha256(path),
      "generated_at":dt.datetime.now(dt.timezone.utc).isoformat(),
      "crs":"EPSG:4326","counts":counts,"invalid_ways":invalid,
      "relations_assembled":False,"simulation_safe":False,
      "warnings":["OSM multipolygon relations not assembled","Unknown building heights",
                  "GeoJSON lat/lon cannot be used as meter distances","Missing features do not imply obstacle-free airspace"]
    })
    print("[done] 只读 GIS 图层已生成；不构成可飞行空间的完整约束数据")


def main(argv=None):
    p=argparse.ArgumentParser(description="SwarmBalance 佛寺镇地图数据准备")
    p.add_argument("--dry-run",action="store_true",help="只打印下载地址和范围")
    a=p.parse_args(argv)
    print("区域:",REGION["name"],"范围:",BBOX,"源:",SOURCE)
    if not a.dry_run:
        dest=BASE/"raw"/"liaoning-latest.osm.pbf"
        get_pbf(dest)
        crop_pbf(dest)
    return 0


if __name__=="__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("[ERROR]",str(exc),file=sys.stderr)
        sys.exit(1)
