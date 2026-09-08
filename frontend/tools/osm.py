import osmnx as ox
import pygame
import numpy as np
from shapely.geometry import Point, LineString, Polygon, box
from shapely.strtree import STRtree
import math
from collections import defaultdict
from drone import Drone    


def _parse_buildings(buildings):
    """把投影后的建筑 GeoDataFrame 解析成含高度的列表。"""
    buildings_with_height = []
    for idx, building in buildings.iterrows():
        height = building.get('height', None)
        levels = building.get('building:levels', None)

        # 归一化：pandas 缺失值往往是 NaN，需显式剔除
        def _is_missing(v):
            if v is None:
                return True
            try:
                return math.isnan(float(v))
            except (TypeError, ValueError):
                return False

        if not _is_missing(height):
            try:
                height_val = float(str(height).split()[0]) if isinstance(height, str) else float(height)
            except (TypeError, ValueError):
                height_val = None
        elif not _is_missing(levels):
            try:
                height_val = float(levels) * 3.0  # 按每层3米估算
            except (TypeError, ValueError):
                height_val = None
        else:
            height_val = None

        buildings_with_height.append({
            'geometry': building.geometry,
            'height': height_val,
            'id': idx,
            'tags': building
        })
    return buildings_with_height


def _load_roads(graph):
    """从投影后的路网图提取主干道路几何（供可视化画路）。"""
    roads_by_type = defaultdict(list)
    major_road_types = {
        'motorway', 'motorway_link',
        'trunk', 'trunk_link',
        'primary', 'primary_link',
        'secondary', 'secondary_link',
        'tertiary', 'tertiary_link'
    }
    for u, v, data in graph.edges(data=True):
        road_type = data.get('highway', 'residential')

        if isinstance(road_type, list):  # 修复：处理可能的列表类型
            road_type = road_type[0] if road_type else 'residential'

        # 只保留主干道路，过滤掉小型道路（如 residential、service、footway 等）
        if road_type not in major_road_types:
            continue

        if 'geometry' in data:
            geom = data['geometry']
        else:
            node1 = graph.nodes[u]
            node2 = graph.nodes[v]
            geom = LineString([(node1['x'], node1['y']), (node2['x'], node2['y'])])

        roads_by_type[road_type].append(geom)
    return roads_by_type


def load_buildings(osm_file_path):
    """只加载建筑数据（仿真环境专用，跳过昂贵的路网解析+投影）。

    返回 buildings_with_height 列表（与 load_map_data 的第二返回值同构）。

    投影说明：`ox.project_gdf` 会把建筑自动投影到所在区域的 UTM 带，与
    `ox.project_graph` 对同一份地图选择的 UTM 带一致，因此坐标口径与
    `config/positions.json`、机巢坐标完全对齐。
    """
    buildings = ox.features_from_xml(osm_file_path, tags={'building': True})
    if hasattr(buildings, 'to_crs'):
        buildings = ox.project_gdf(buildings)
    return _parse_buildings(buildings)


def load_map_data(osm_file_path):
    """加载完整地图数据（路网 + 建筑）。可视化（map_drawer）使用。"""
    graph = ox.graph_from_xml(osm_file_path)
    graph = ox.project_graph(graph)
    crs = graph.graph.get('crs') if hasattr(graph, 'graph') else None
    roads_by_type = _load_roads(graph)
    buildings = ox.features_from_xml(osm_file_path, tags={'building': True})
    if hasattr(buildings, 'to_crs') and crs is not None:
        buildings = buildings.to_crs(crs)
    buildings_with_height = _parse_buildings(buildings)
    return roads_by_type, buildings_with_height


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