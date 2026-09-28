"""OSM 地图加载工具。

首选 osmnx 读取本地 ``.osm`` XML；当 osmnx 不可用时，自动使用一个轻量
XML + pyproj 回退加载器。回退模式只解析本项目仿真实际需要的主干道路和
建筑轮廓，不访问网络，因此 Web 控制台/批量仿真可以在答辩机上离线运行。

桌面 pygame 渲染仍属于完整依赖栈；这里刻意不 import pygame，避免 headless
Web 服务因为一个纯可视化依赖无法启动。
"""
from __future__ import annotations

import hashlib
import math
import os
import pickle
import tempfile
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

from shapely.geometry import LineString, Polygon

try:  # 完整模式：与历史版本保持一致
    import osmnx as ox
except Exception:  # pragma: no cover - 是否安装由运行环境决定
    ox = None


def _osmnx_available() -> bool:
    """osmnx 是否**真的可用**。

    只判断 ``ox is None`` 是不够的：一个导入不完整或被替换过的模块对象同样非 None，
    走到 ``ox.graph_from_xml`` 才抛 AttributeError，控制台直接 500。这里按实际用到的
    入口判定，不可用就走内置 XML 回退——与 capabilities 的「缺依赖降级」约定一致。
    """
    return ox is not None and hasattr(ox, "graph_from_xml") and hasattr(ox, "features_from_xml")


_MAJOR_ROAD_TYPES = {
    'motorway', 'motorway_link',
    'trunk', 'trunk_link',
    'primary', 'primary_link',
    'secondary', 'secondary_link',
    'tertiary', 'tertiary_link',
}


def _height_from_tags(tags: Dict[str, str]):
    """从 OSM tags 提取建筑高度（米）；没有可靠值时返回 None。"""
    raw = tags.get('height')
    if raw not in (None, ''):
        try:
            token = str(raw).strip().lower().replace('meters', '').replace('meter', '').replace('m', '').strip()
            # 少量 OSM 数据会出现 ``12;15``，取首个可解析值，保持保守口径。
            token = token.split(';')[0].strip()
            return float(token)
        except (TypeError, ValueError):
            pass
    levels = tags.get('building:levels')
    if levels not in (None, ''):
        try:
            return float(str(levels).split(';')[0]) * 3.0
        except (TypeError, ValueError):
            pass
    return None


def _utm_epsg(lon: float, lat: float) -> int:
    """按经纬度选择 WGS84 UTM EPSG。上海/杨浦会得到 EPSG:32651。"""
    zone = max(1, min(60, int((float(lon) + 180.0) // 6.0) + 1))
    return (32600 if float(lat) >= 0 else 32700) + zone


def _load_map_data_fallback(osm_file_path):
    """无 osmnx 时的离线本地 OSM XML 加载器。

    支持本项目需要的两类几何：
    - ``way[highway]`` 中的主干道路；
    - ``way[building]`` 的建筑 Polygon（含 height / building:levels）。

    OSM multipolygon relation 不在此轻量回退器的职责范围内；完整桌面/科研环境
    安装 osmnx 后仍走原实现。仿真碰撞约束只使用有高度的建筑，回退模式足以
    支撑 Web 演示与 headless 评测，同时避免网络依赖。
    """
    try:
        from pyproj import Transformer
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "osmnx 未安装，且轻量 OSM 回退器需要 pyproj。请安装 pyproj 或按 README 安装完整依赖。"
        ) from exc

    path = Path(osm_file_path)
    if not path.exists():
        raise FileNotFoundError(f"OSM 文件不存在: {path}")

    roads_by_type = defaultdict(list)
    buildings_with_height = []
    nodes: Dict[str, Tuple[float, float]] = {}
    transformer = None

    # OSM XML 通常按 bounds -> nodes -> ways -> relations 排列；iterparse 能在处理后
    # 及时 clear 元素，读取 10MB~100MB 文件时不会把整棵 XML 树常驻内存。
    for event, elem in ET.iterparse(str(path), events=('end',)):
        tag = elem.tag.rsplit('}', 1)[-1]
        if tag == 'bounds' and transformer is None:
            try:
                lon = (float(elem.attrib['minlon']) + float(elem.attrib['maxlon'])) / 2.0
                lat = (float(elem.attrib['minlat']) + float(elem.attrib['maxlat'])) / 2.0
                transformer = Transformer.from_crs('EPSG:4326', f"EPSG:{_utm_epsg(lon, lat)}", always_xy=True)
            except Exception:
                transformer = None
            elem.clear()
            continue

        if tag == 'node':
            try:
                lon = float(elem.attrib['lon'])
                lat = float(elem.attrib['lat'])
                if transformer is None:
                    transformer = Transformer.from_crs(
                        'EPSG:4326', f"EPSG:{_utm_epsg(lon, lat)}", always_xy=True
                    )
                nodes[elem.attrib['id']] = transformer.transform(lon, lat)
            except Exception:
                pass
            elem.clear()
            continue

        if tag != 'way':
            # nd/tag 是 way 的子元素：若在它们自己的 end 事件先 clear，
            # 父 way 到达时 ref/k/v 已被清空。仅在 relation 等顶层对象结束时清理。
            if tag in {'relation'}:
                elem.clear()
            continue

        refs = []
        tags: Dict[str, str] = {}
        for child in list(elem):
            ctag = child.tag.rsplit('}', 1)[-1]
            if ctag == 'nd':
                ref = child.attrib.get('ref')
                if ref:
                    refs.append(ref)
            elif ctag == 'tag':
                k, v = child.attrib.get('k'), child.attrib.get('v')
                if k is not None and v is not None:
                    tags[k] = v
        coords = [nodes[r] for r in refs if r in nodes]

        road_type = tags.get('highway')
        if road_type in _MAJOR_ROAD_TYPES and len(coords) >= 2:
            try:
                roads_by_type[road_type].append(LineString(coords))
            except Exception:
                pass

        building_tag = tags.get('building')
        if building_tag and building_tag != 'no' and len(coords) >= 3:
            try:
                geom = Polygon(coords)
                if not geom.is_valid:
                    geom = geom.buffer(0)
                if not geom.is_empty and geom.area > 0:
                    buildings_with_height.append({
                        'geometry': geom,
                        'height': _height_from_tags(tags),
                        'id': elem.attrib.get('id'),
                        # dict 足够支持下游 ``tags.get(...)``，无需依赖 GeoPandas Row。
                        'tags': tags,
                    })
            except Exception:
                pass

        elem.clear()

    if not buildings_with_height:
        raise RuntimeError(f"未能从本地 OSM XML 解析出建筑物: {path}")
    return roads_by_type, buildings_with_height


def load_map_data(osm_file_path):
    """加载地图数据；优先 osmnx，缺失时自动离线回退。

    性能：解析本项目那份 13MB 的本地 ``.osm`` 实测约 4.3s——osmnx 会对同一个文件
    做两遍 XML 解析（``graph_from_xml`` 一遍、``features_from_xml`` 一遍），而每新建
    一个 Environment 都要重跑；批量实验里每个 worker 都付一次这笔钱。
    这里按「绝对路径 + mtime + 大小 + 解析模式 + osmnx 版本」缓存**最终返回值**，
    命中即直接反序列化。设 ``SWARM_BALANCE_OSM_CACHE=0`` 可强制重新解析。
    """
    mode = "osmnx" if _osmnx_available() else "fallback"
    cache_path = _cache_path(osm_file_path, mode)

    if _cache_enabled() and cache_path is not None:
        cached = _read_cache(cache_path)
        if cached is not None:
            return cached

    if _osmnx_available():
        data = _parse_map_data_with_osmnx(osm_file_path)
    else:
        data = _load_map_data_fallback(osm_file_path)

    if _cache_enabled() and cache_path is not None:
        _write_cache(cache_path, data)
    return data


def _parse_map_data_with_osmnx(osm_file_path):
    """真正调用 osmnx 的解析路径（冷缓存时才跑）。"""
    graph = ox.graph_from_xml(osm_file_path)
    graph = ox.project_graph(graph)
    buildings = ox.features_from_xml(osm_file_path, tags={'building': True})
    if hasattr(buildings, "to_crs") and graph.graph.get("crs") is not None:
        buildings = buildings.to_crs(graph.graph["crs"])

    roads_by_type = defaultdict(list)
    for u, v, data in graph.edges(data=True):
        road_type = data.get("highway", "residential")
        if isinstance(road_type, list):
            road_type = road_type[0] if road_type else "residential"
        if road_type not in _MAJOR_ROAD_TYPES:
            continue
        if "geometry" in data:
            geom = data["geometry"]
        else:
            node1 = graph.nodes[u]
            node2 = graph.nodes[v]
            geom = LineString([(node1["x"], node1["y"]), (node2["x"], node2["y"])])
        roads_by_type[road_type].append(geom)

    buildings_with_height = []
    for idx, building in buildings.iterrows():
        tags = building
        height_val = _height_from_tags(tags)
        buildings_with_height.append({
            "geometry": building.geometry,
            "height": height_val,
            "id": idx,
            "tags": tags,
        })
    return roads_by_type, buildings_with_height


# ---------------------------------------------------------------------------
# 解析结果磁盘缓存
# ---------------------------------------------------------------------------

_CACHE_FORMAT = 1
_CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / ".osm_cache"
_CACHE_MAX_KEEP = 6


def _cache_enabled() -> bool:
    return os.environ.get("SWARM_BALANCE_OSM_CACHE", "1").strip().lower() not in {"0", "false", "off", "no"}


def _cache_path(osm_file_path, mode: str) -> Optional[Path]:
    """按源文件指纹给出缓存文件路径；无法 stat 时返回 None（不缓存）。"""
    path = Path(osm_file_path).resolve()
    try:
        stat = path.stat()
    except OSError:
        return None
    ox_version = getattr(ox, "__version__", "none")
    raw = "|".join((
        f"fmt{_CACHE_FORMAT}", mode, ox_version, str(path),
        str(stat.st_mtime_ns), str(stat.st_size),
    ))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return _CACHE_DIR / f"osm-{digest}.pkl"


def _read_cache(cache_path: Path):
    """读缓存。任何异常都当作未命中——缓存坏了不能拖垮仿真启动。"""
    try:
        with cache_path.open("rb") as fh:
            payload = pickle.load(fh)
    except Exception:  # noqa: BLE001 - 未命中处理
        return None
    if not isinstance(payload, tuple) or len(payload) != 2:
        return None
    roads, buildings = payload
    if not isinstance(roads, dict) or not isinstance(buildings, list) or not buildings:
        return None
    return roads, buildings


def _write_cache(cache_path: Path, data) -> None:
    """原子写缓存，并只保留最近 _CACHE_MAX_KEEP 份。失败静默忽略。"""
    tmp = None
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(cache_path.parent), suffix=".tmp")
        os.close(fd)
        with open(tmp, "wb") as fh:
            pickle.dump(data, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, cache_path)
        tmp = None
        _prune_cache(cache_path.parent)
    except Exception:  # noqa: BLE001 - 缓存只影响速度，不影响正确性
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _prune_cache(directory: Path) -> None:
    try:
        files = sorted(directory.glob("osm-*.pkl"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return
    for stale in files[:-_CACHE_MAX_KEEP]:
        try:
            stale.unlink()
        except OSError:
            pass

def get_building_location_by_name(buildings_with_height, name, exact=True):
    """根据建筑名查找建筑位置。

    :param buildings_with_height: load_map_data 返回的建筑列表
    :param name: 建筑名
    :param exact: 是否完全匹配，False 则使用包含匹配
    :return: 如果找到，返回一个坐标元组 (x, y) 或坐标元组列表；未找到返回 None
    """
    if not name:
        return None

    query = name.strip().lower()
    matches = []
    for building in buildings_with_height:
        tags = building.get('tags', {})
        if tags is None:
            continue

        # 常见建筑名字段
        for field in ('name', 'building:name', 'addr:housename'):
            value = tags.get(field)
            if not value or not isinstance(value, str):
                continue

            value_norm = value.strip().lower()
            if exact:
                if value_norm == query:
                    matches.append(building)
                    break
            else:
                if query in value_norm:
                    matches.append(building)
                    break

    if not matches:
        return None

    locations = []
    for building in matches:
        geom = building.get('geometry')
        if geom is None:
            continue
        centroid = geom.centroid
        locations.append((centroid.x, centroid.y))

    if not locations:
        return None
    return locations[0] if len(locations) == 1 else locations


def get_global_bounds(buildings_with_height):
    """获取所有建筑的全局边界框。

    :param buildings_with_height: load_map_data 返回的建筑列表
    :return: 全局边界框 (min_x, min_y, max_x, max_y)，如果没有建筑则返回 None
    """
    if not buildings_with_height:
        return None

    min_x = float('inf')
    min_y = float('inf')
    max_x = float('-inf')
    max_y = float('-inf')

    for building in buildings_with_height:
        geom = building.get('geometry')
        if geom is None:
            continue
        bounds = geom.bounds  # (minx, miny, maxx, maxy)
        min_x = min(min_x, bounds[0])
        min_y = min(min_y, bounds[1])
        max_x = max(max_x, bounds[2])
        max_y = max(max_y, bounds[3])

    if min_x == float('inf'):
        return None  # 没有有效的几何体

    return (min_x, min_y, max_x, max_y)