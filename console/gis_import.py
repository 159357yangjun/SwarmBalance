"""Bounded, on-demand OSM way import for the GIS preview (NOT a collision dataset).

Public Overpass is a best-effort small-area source. No bulk OSM tile scraping.
Downloaded tiles, packages and import-job status stay outside Git.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DATA_ROOT = Path(__file__).resolve().parents[1] / "data" / "map" / "gis"
OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"
KINDS = ("water", "landuse", "roads", "railways", "buildings")
SCHEMA = "map-preview.v1"
MAX_AREA_KM2 = 30.0
MAX_TILES = 16
MAX_RAW_BYTES = 18 * 1024 * 1024
MAX_FEATURES = 15000
_LOCK = threading.Lock()
_ACTIVE = {"id": None, "cancel": None}


class ImportFailure(RuntimeError):
    pass


class ImportCancelled(ImportFailure):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def bbox_area(bbox):
    w, s, e, n = bbox
    mid = math.radians((s + n) / 2)
    width = (e - w) * 111.32 * math.cos(mid)
    height = (n - s) * 111.32
    return width, height, width * height


def validate_bbox(raw):
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        raise ValueError("范围应是 [west, south, east, north] 的四个坐标")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in raw):
        raise ValueError("坐标必须是有限数值")
    w, s, e, n = [round(float(v), 7) for v in raw]
    if not (-180 <= w < e <= 180 and -85 <= s < n <= 85):
        raise ValueError("经纬度范围无效；暂不支持跨越 180° 经线的区域")
    width, height, area = bbox_area((w, s, e, n))
    if width < 0.1 or height < 0.1:
        raise ValueError("选区宽高均须至少 100 米")
    if area > MAX_AREA_KM2 + 1e-7:
        raise ValueError(f"当前公开数据接口仅允许不超过 {MAX_AREA_KM2:g} 平方公里，请缩小选区")
    return [w, s, e, n]


def tile_bboxes(bbox):
    w, s, e, n = validate_bbox(bbox)
    width, height, _ = bbox_area((w, s, e, n))
    cols = max(1, math.ceil(width / 2.5))
    rows = max(1, math.ceil(height / 2.5))
    if cols * rows > MAX_TILES:
        raise ValueError("选区分块数过多，请缩小选区")
    return [
        [round(w+(e-w)*i/cols, 7), round(s+(n-s)*j/rows, 7),
         round(w+(e-w)*(i+1)/cols, 7), round(s+(n-s)*(j+1)/rows, 7)]
        for j in range(rows) for i in range(cols)
    ]


def query_for(tile):
    w, s, e, n = tile
    clause = f"({s},{w},{n},{e})"
    filters = ('"building"', '"highway"', '"waterway"', '"natural"="water"',
               '"landuse"', '"railway"')
    statements = "".join(f"way[{item}]{clause};" for item in filters)
    return f"[out:json][timeout:65];({statements});out body geom;"


def fetch_overpass(tile):
    query = query_for(tile)
    data = urlencode({"data": query}).encode("utf-8")
    request = Request(OVERPASS_ENDPOINT, data=data,
                      headers={"Content-Type": "application/x-www-form-urlencoded",
                               "Accept": "application/json",
                               "User-Agent": "SwarmBalance-research-map-preview/1.0 (small bounded OSM query)"},
                      method="POST")
    for attempt in range(3):
        try:
            with urlopen(request, timeout=85) as response:
                body = response.read(MAX_RAW_BYTES + 1)
            if len(body) > MAX_RAW_BYTES:
                raise ImportFailure("OSM 响应过大；请缩小选区")
            decoded = json.loads(body)
            if not isinstance(decoded, dict) or not isinstance(decoded.get("elements"), list):
                raise ImportFailure("远端不是预期的 OSM 数据格式")
            return decoded
        except HTTPError as exc:
            if exc.code not in (429, 502, 503, 504) or attempt == 2:
                raise ImportFailure(f"OSM 数据服务返回 HTTP {exc.code}；请稍后重试") from exc
            retry = exc.headers.get("Retry-After", "")
            wait = min(25, max(3 * (attempt + 1), int(retry) if retry.isdigit() else 0))
            time.sleep(wait)
        except (URLError, TimeoutError, OSError) as exc:
            if attempt == 2:
                raise ImportFailure(f"OSM 网络请求失败：{exc}；可稍后重试") from exc
            time.sleep(3 * (attempt + 1))
        except (ValueError, UnicodeError) as exc:
            raise ImportFailure("OSM 服务未返回有效 JSON，可能正在限流") from exc
    raise ImportFailure("OSM 查询未完成")


def load_tile(tile, force_refresh=False, fetcher=None, root=None):
    root = Path(root or DATA_ROOT)
    key = hashlib.sha256((SCHEMA + OVERPASS_ENDPOINT + query_for(tile)).encode()).hexdigest()
    path = root / "cache" / (key + ".json")
    if path.is_file() and not force_refresh:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(obj, dict) and isinstance(obj.get("elements"), list):
                return obj, True
        except (ValueError, OSError):
            pass
    result = (fetcher or fetch_overpass)(tile)
    if not isinstance(result, dict) or not isinstance(result.get("elements"), list):
        raise ImportFailure("OSM 数据格式错误")
    raw = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_RAW_BYTES:
        raise ImportFailure("原始地理数据超过缓存上限")
    write_json(path, result)
    return result, False


def convert_elements(elements, bbox):
    """Clip OSM ways, dedupe by OSM way ID, document missing multipolygon relations."""
    try:
        from shapely.geometry import LineString, Polygon, box, mapping
    except ImportError as exc:
        raise ImportFailure("GIS 导入需要 Shapely；请执行 python -m pip install shapely") from exc
    clip = box(*bbox)
    groups = {name: [] for name in KINDS}
    seen = set()
    invalid = 0
    height_missing = 0

    def simple_geoms(g):
        if g.is_empty:
            return
        if g.geom_type in ("Polygon", "LineString"):
            yield g
        elif hasattr(g, "geoms"):
            for part in g.geoms:
                yield from simple_geoms(part)

    for el in elements:
        if not isinstance(el, dict) or el.get("type") != "way":
            continue
        oid = el.get("id")
        if not isinstance(oid, int) or oid in seen:
            continue
        seen.add(oid)
        tags = el.get("tags") or {}
        geom = el.get("geometry") or []
        kinds = []
        if tags.get("building") not in (None, "", "no"):
            kinds.append("buildings")
        if "highway" in tags:
            kinds.append("roads")
        if ("waterway" in tags or tags.get("natural") == "water"
                or tags.get("landuse") == "reservoir"):
            kinds.append("water")
        if "landuse" in tags or tags.get("natural") in ("wood", "scrub", "grassland", "wetland"):
            kinds.append("landuse")
        if "railway" in tags:
            kinds.append("railways")
        if not kinds:
            continue
        try:
            pts = [(float(x["lon"]), float(x["lat"])) for x in geom]
            if len(pts) < 2 or not all(math.isfinite(x) and math.isfinite(y) for x, y in pts):
                invalid += 1
                continue
            line = LineString(pts)
            polygon = Polygon(pts) if len(pts) >= 4 and pts[0] == pts[-1] else None
            if polygon is not None and not polygon.is_valid:
                polygon = polygon.buffer(0)
            for kind in kinds:
                if kind == "buildings":
                    if polygon is None or polygon.is_empty:
                        invalid += 1
                        continue
                    g = polygon
                elif kind in ("water", "landuse") and polygon is not None:
                    g = polygon
                else:
                    g = line
                if not g.intersects(clip):
                    continue
                for part in simple_geoms(g.intersection(clip)):
                    if kind == "buildings" and part.geom_type != "Polygon":
                        continue
                    if kind == "buildings" and tags.get("height") is None:
                        height_missing += 1
                    groups[kind].append({
                        "type": "Feature", "properties": {
                            "osm_id": "way:" + str(oid),
                            "height": tags.get("height"),
                            "building_levels": tags.get("building:levels"),
                            "source": "OpenStreetMap"},
                        "geometry": mapping(part)})
        except (KeyError, TypeError, ValueError, OverflowError):
            invalid += 1
    count = sum(len(g) for g in groups.values())
    if count > MAX_FEATURES:
        raise ImportFailure(f"地理对象达到 {count} 个，超过预览上限；请缩小选区")
    return groups, {"invalid_ways": invalid, "unknown_building_heights": height_missing,
                    "relations_assembled": False, "simulation_safe": False}


def run_import(bbox, progress, cancelled, force_refresh=False, root=None, fetcher=None, pause=None):
    root = Path(root or DATA_ROOT)
    bbox = validate_bbox(bbox)
    tiles = tile_bboxes(bbox)
    all_by_id = {}
    cache_hits = 0
    stamps = []
    for index, tile in enumerate(tiles):
        if cancelled.is_set():
            raise ImportCancelled("任务已取消；已有缓存可留待下次复用")
        progress("downloading", index, len(tiles), "正在获取第 %s/%s 块" % (index+1, len(tiles)))
        obj, hit = load_tile(tile, force_refresh=force_refresh, fetcher=fetcher, root=root)
        cache_hits += int(hit)
        stamps.append(obj.get("osm3s", {}).get("timestamp_osm_base"))
        for el in obj["elements"]:
            if isinstance(el, dict) and el.get("type") == "way" and isinstance(el.get("id"), int):
                # out geom contains full way geometries; reuse once across overlapping tiles
                all_by_id.setdefault(el["id"], el)
        progress("downloading", index+1, len(tiles), "已获取 %s/%s 块" % (index+1, len(tiles)))
        if not hit and index < len(tiles)-1:
            (pause or time.sleep)(2)  # Respectful public Overpass request pacing.
    if cancelled.is_set():
        raise ImportCancelled("任务已取消")
    progress("processing", len(tiles), len(tiles), "正在裁剪并验证真实地理对象")
    groups, quality = convert_elements(list(all_by_id.values()), bbox)
    normalized = {"schema": SCHEMA, "bbox": bbox, "source": "Overpass/OSM",
                  "features": groups}
    payload = json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    package_id = hashlib.sha256(payload).hexdigest()[:24]
    destination = root / "packages" / package_id
    if destination.exists():
        return package_id, cache_hits, len(tiles)
    temp = root / "packages" / ("." + package_id + "-" + uuid.uuid4().hex)
    try:
        temp.mkdir(parents=True)
        counts = {}
        for kind, features in groups.items():
            write_json(temp / (kind + ".geojson"), {"type": "FeatureCollection", "features": features})
            counts[kind] = len(features)
        if cancelled.is_set():
            raise ImportCancelled("任务已取消")
        manifest = {"package_id": package_id, "schema": SCHEMA,
                    "bbox_wgs84_lonlat": bbox, "crs": "EPSG:4326",
                    "source": OVERPASS_ENDPOINT, "attribution": "© OpenStreetMap contributors (ODbL)",
                    "osm_timestamps": sorted(set(x for x in stamps if x)),
                    "created_utc": utc_now(), "tiles": len(tiles), "cache_hits": cache_hits,
                    "feature_counts": counts, "quality": quality,
                    "warnings": ["仅解析 OSM ways，未组装 multipolygon relations",
                                 "数据缺失不代表无障碍；未验证飞行安全性",
                                 "仅供 GIS 预览，非正式计算地图包"]}
        write_json(temp / "manifest.json", manifest)
        temp.rename(destination)
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    return package_id, cache_hits, len(tiles)


def job_path(job_id, root=None):
    if not isinstance(job_id, str) or len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        raise ValueError("无效任务 ID")
    return Path(root or DATA_ROOT) / "jobs" / (job_id + ".json")


def read_job(job_id, root=None):
    path = job_path(job_id, root)
    if not path.exists():
        raise FileNotFoundError(job_id)
    job = json.loads(path.read_text(encoding="utf-8"))
    if job["status"] in ("queued", "downloading", "processing"):
        with _LOCK:
            if _ACTIVE["id"] != job_id:
                job["status"] = "interrupted"
                job["message"] = "服务重启导致任务中断，请重新创建导入任务"
                write_json(path, job)
    return job


def start_job(bbox, force_refresh=False, root=None, fetcher=None, pause=None):
    root = Path(root or DATA_ROOT)
    box = validate_bbox(bbox)
    tile_bboxes(box)
    if not isinstance(force_refresh, bool):
        raise ValueError("force_refresh 必须是布尔值")
    with _LOCK:
        if _ACTIVE["id"] is not None:
            raise ImportFailure("已有地图准备任务正在运行，请等待完成或取消")
        job_id = uuid.uuid4().hex
        cancel = threading.Event()
        _ACTIVE.update(id=job_id, cancel=cancel)
        job = {"id": job_id, "bbox": box, "status": "queued", "message": "等待下载",
               "completed_tiles": 0, "total_tiles": len(tile_bboxes(box)),
               "package_id": None, "created_utc": utc_now(), "updated_utc": utc_now()}
        try:
            write_json(job_path(job_id, root), job)
        except Exception:
            _ACTIVE.update(id=None, cancel=None)
            raise

    def progress(status, done, total, message):
        job.update(status=status, completed_tiles=done, total_tiles=total,
                   message=message, updated_utc=utc_now())
        write_json(job_path(job_id, root), job)

    def worker():
        try:
            package_id, hits, total = run_import(box, progress, cancel, force_refresh,
                                                  root, fetcher=fetcher, pause=pause)
            job["package_id"] = package_id
            job["cache_hits"] = hits
            progress("complete", total, total, "地图图层已准备，仅限 GIS 数据预览")
        except ImportCancelled as exc:
            progress("cancelled", job["completed_tiles"], job["total_tiles"], str(exc))
        except Exception as exc:
            progress("failed", job["completed_tiles"], job["total_tiles"], str(exc))
        finally:
            with _LOCK:
                if _ACTIVE["id"] == job_id:
                    _ACTIVE.update(id=None, cancel=None)

    try:
        threading.Thread(target=worker, name="gis-import-"+job_id[:8], daemon=True).start()
    except Exception:
        with _LOCK:
            _ACTIVE.update(id=None, cancel=None)
        raise
    return job


def cancel_job(job_id):
    with _LOCK:
        if _ACTIVE["id"] != job_id or _ACTIVE["cancel"] is None:
            raise ImportFailure("该任务无法取消，可能已完成或不再运行")
        _ACTIVE["cancel"].set()


def manifest_for(package_id, root=None):
    if not isinstance(package_id, str) or len(package_id) != 24 or any(c not in "0123456789abcdef" for c in package_id):
        raise ValueError("无效地图包 ID")
    path = Path(root or DATA_ROOT) / "packages" / package_id / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(package_id)
    return json.loads(path.read_text(encoding="utf-8"))
