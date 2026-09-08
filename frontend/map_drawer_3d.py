"""
三维视图绘制器：将原来的 2D 俯视地图升级为可旋转/缩放/平移的三维轴测视图。

核心思路（软件 3D 投影，零额外依赖，仅用 pygame）：
  - 世界坐标 (x, y) 为已投影的米制平面坐标，z 为海拔高度（米），向上为正。
  - 通过「方位角 azimuth 围绕 Z 轴旋转 + 俯仰角 elevation 抬高视角」得到屏幕投影：
        Xr = (x-cx)*cosA - (y-cy)*sinA
        Yr = (x-cx)*sinA + (y-cy)*cosA
        vy = sin(E)*Yr + cos(E)*z          # 屏幕“向上”轴（E 越高越接近纯俯视）
        sx = px + scale * Xr
        sy = py - scale * vy
        depth = cos(E)*Yr - sin(E)*z       # 用于画家算法（远处先画）
  - 建筑按 footprints 拉伸成棱柱（底面 → 顶面为纯竖直平移），用 3 次多边形填充
    完成（阴影 + 墙体 + 屋顶），并用高度/景深着色增强立体感。
  - 无人机按其飞行状态赋予可视高度，绘制“竖直投影线 + 机体标记”表达空中位置。
  - 保留原 2D 版的右侧 Dashboard 信息面板与图例（这些只依赖屏幕坐标，不受 3D 影响）。

对外接口与 OptimizedMapViewer 保持一致：render(drones, stats)、set_on_add_drone()。
"""

import os
import math
import numpy as np
import pygame
from shapely.geometry import Point
from shapely.strtree import STRtree
from collections import defaultdict

from tools.osm import load_map_data
from charging_station import DEFAULT_CHARGING_STATIONS
from config.config_loder import get_shared_config

_CFG = get_shared_config().get("visualization", {})
_MODE = str(_CFG.get("mode", "3d")).lower()

# 默认视角参数（simulation.json 的 visualization 段可覆盖）
DEFAULT_AZIMUTH = float(_CFG.get("azimuth", 35.0))
DEFAULT_ELEVATION = float(_CFG.get("elevation", 55.0))
DEFAULT_ZOOM = float(_CFG.get("zoom", 1.0))
DEFAULT_HEIGHT_SCALE = float(_CFG.get("height_scale", 6.0))
DEFAULT_DRONE_ALT = float(_CFG.get("drone_altitude", 45.0))

# 机型 → 专属颜色，便于从三维视角区分异构机队
DRONE_TYPE_COLORS = {
    "light_express": (96, 200, 150),    # 轻载快递型（美团参考）- 绿色
    "standard_cargo": (215, 175, 100),  # 标准货运型（顺丰ARK40参考）- 橙色
    "heavy_cargo": (190, 120, 120),     # 重载运输型（大疆FlyCart30参考）- 红棕
}
DRONE_TYPE_LABELS = {
    "light_express": "Light-Express",
    "standard_cargo": "Standard-Cargo",
    "heavy_cargo": "Heavy-Cargo",
}


class MapViewer3D:
    """三维仿真的可视化查看器（软件投影，pygame 渲染）。"""

    def __init__(self, osm_file_path, screen_size=(1200, 800)):
        pygame.init()
        self.clock = pygame.time.Clock()
        self.screen_size = screen_size
        self.screen = pygame.display.set_mode(screen_size)
        pygame.display.set_caption("群智优衡 - 异构多无人机集群三维协同调度仿真")

        # ==== 配色（清新极简风） ====
        self.COLORS = {
            'BACKGROUND': (235, 240, 245),      # 天空/背景
            'GROUND': (222, 226, 230),          # 地面底色
            'ROAD': (255, 255, 255),            # 道路主体
            'ROAD_STROKE': (206, 212, 218),     # 道路描边
            'TEXT': (33, 37, 41),
            'TEXT_SECONDARY': (108, 117, 125),
            'PANEL_BG': (255, 255, 255),
            'PANEL_BORDER': (222, 226, 230),
        }
        self.DRONE_COLORS = [
            (190, 120, 120), (120, 150, 170), (120, 165, 155),
            (215, 175, 140), (170, 140, 195), (210, 150, 180),
            (220, 210, 140), (120, 180, 210),
        ]

        # ==== 视角参数 ====
        self.azimuth = DEFAULT_AZIMUTH          # 方位角（度）
        self.elevation = DEFAULT_ELEVATION      # 俯仰角（度，0~90，越大越接近俯视）
        self.zoom = DEFAULT_ZOOM
        self.height_scale = DEFAULT_HEIGHT_SCALE
        self.drone_altitude = DEFAULT_DRONE_ALT
        self.pan_x = 0
        self.pan_y = 0
        self.topdown = False                    # 是否临时切到俯视模式

        # ==== 交互状态 ====
        self.dragging = False
        self.drag_start = (0, 0)
        self.drag_mode = None                   # 'orbit' | 'pan'
        self.fps_counter = 0
        self.fps_time = 0
        self.current_fps = 0

        # 面板交互组件（与 2D 版一致）
        self.selected_algorithm = "Greedy"
        self.algorithm_options = ["Greedy", "PSO", "QMIX", "VDN", "IQL"]
        self.algo_dropdown_open = False
        self._add_drone_rect = None
        self._algo_selector_rect = None
        self._algo_dropdown_rects = []
        self.on_add_drone = None
        self.selected_building = None

        # ==== 加载并预处理地图数据 ====
        self.roads_by_type, self.buildings_with_height = load_map_data(osm_file_path)
        self.building_geoms = [b['geometry'] for b in self.buildings_with_height]
        if self.building_geoms:
            self.building_index = STRtree(self.building_geoms)

        self._precompute_buildings()
        self.calculate_bounds()

        # 初始缩放：让整个地图适配屏幕
        self.base_scale = min(
            self.screen_size[0] / self.map_width,
            self.screen_size[1] / self.map_height,
        )
        self.scale = self.base_scale

        self._init_fonts()

    # ------------------------------------------------------------------ #
    # 数据预处理
    # ------------------------------------------------------------------ #
    def _precompute_buildings(self):
        """把建筑脚印、高度、质心一次性缓存，避免每帧重复计算几何。"""
        self._bldg_rings = []       # 每个建筑一个 (N,2) numpy 数组（世界坐标）
        self._bldg_h = []           # 高度（米）
        self._bldg_c = []           # 质心 (cx, cy)
        for b in self.buildings_with_height:
            geom = b['geometry']
            if geom is None or not hasattr(geom, 'exterior'):
                continue
            ring = np.array(list(geom.exterior.coords), dtype=float)
            if ring.shape[0] < 3:
                continue
            h = b.get('height')
            if h is None or (isinstance(h, float) and math.isnan(h)) or h <= 0:
                # 缺失高度（OSM 中大部分建筑无 height/levels 标签）：
                # 依据占地面积为建筑合成一个确定性的合理高度，使城市呈现立体感。
                area = float(geom.area)
                h = min(45.0, max(4.0, math.sqrt(max(area, 1.0)) * 0.6))
            self._bldg_rings.append(ring[:, :2])
            self._bldg_h.append(float(h))
            c = geom.centroid
            self._bldg_c.append((float(c.x), float(c.y)))

        self._bldg_h = np.array(self._bldg_h, dtype=float)

        # 依据高度预计算墙体/屋顶颜色（只随 height_scale 变化，故放在这里按高度分档）
        self._bldg_wall_colors = [self._wall_color(h) for h in self._bldg_h]
        self._bldg_roof_colors = [self._roof_color(h) for h in self._bldg_h]

    @staticmethod
    def _wall_color(h):
        """建筑墙体颜色：越高越深。"""
        t = min(1.0, h / 50.0)
        base = 216
        r = int(base - 40 * t)
        g = int(base - 30 * t)
        b = int(base - 15 * t)
        return (r, g, b)

    @staticmethod
    def _roof_color(h):
        """建筑屋顶颜色：比墙体更亮一档。"""
        w = MapViewer3D._wall_color(h)
        return (min(255, w[0] + 26), min(255, w[1] + 24), min(255, w[2] + 18))

    def calculate_bounds(self):
        all_geoms = []
        for roads in self.roads_by_type.values():
            all_geoms.extend(roads)
        all_geoms.extend(self.building_geoms)
        if all_geoms:
            min_x = min_y = float('inf')
            max_x = max_y = float('-inf')
            for g in all_geoms:
                b = g.bounds
                min_x = min(min_x, b[0]); min_y = min(min_y, b[1])
                max_x = max(max_x, b[2]); max_y = max(max_y, b[3])
            self.min_x, self.min_y, self.max_x, self.max_y = min_x, min_y, max_x, max_y
        else:
            self.min_x, self.min_y, self.max_x, self.max_y = -180, -90, 180, 90
        self.map_width = max(self.max_x - self.min_x, 1e-6)
        self.map_height = max(self.max_y - self.min_y, 1e-6)
        self.cx = (self.min_x + self.max_x) / 2
        self.cy = (self.min_y + self.max_y) / 2

    # ------------------------------------------------------------------ #
    # 投影变换
    # ------------------------------------------------------------------ #
    def _refresh_transform(self):
        """根据当前视角参数刷新投影像素比例与旋转因子。"""
        A = math.radians(self.azimuth)
        E = math.radians(self.elevation if not self.topdown else 89.0)
        self._cosA = math.cos(A)
        self._sinA = math.sin(A)
        self._sinE = math.sin(E)
        self._cosE = math.cos(E)
        hs = 0.0 if self.topdown else self.height_scale
        self._hs = hs
        self._px = self.screen_size[0] / 2 + self.pan_x
        self._py = self.screen_size[1] / 2 + self.pan_y + self.screen_size[1] * 0.04

    def project(self, x, y, z=0.0):
        """世界坐标 → 屏幕坐标 + 深度。返回 (sx, sy, depth)。"""
        dx = x - self.cx
        dy = y - self.cy
        Xr = dx * self._cosA - dy * self._sinA
        Yr = dx * self._sinA + dy * self._cosA
        vy = self._sinE * Yr + self._cosE * z
        sx = self._px + self.scale * Xr
        sy = self._py - self.scale * vy
        depth = self._cosE * Yr - self._sinE * z
        return sx, sy, depth

    def screen_to_ground(self, sx, sy):
        """屏幕坐标反解回地面 (x, y)（z=0），用于建筑拾取。"""
        Xr = (sx - self._px) / self.scale
        if abs(self._cosE) < 1e-6 or abs(self._sinE) < 1e-6:
            Yr = 0.0
        else:
            Yr = (self._py - sy) / self.scale / self._sinE
        dx = self._cosA * Xr + self._sinA * Yr
        dy = -self._sinA * Xr + self._cosA * Yr
        return dx + self.cx, dy + self.cy

    # ------------------------------------------------------------------ #
    # 绘制：地面 / 道路 / 建筑 / 站点 / 无人机
    # ------------------------------------------------------------------ #
    def draw(self, drones=None, stats=None):
        drones = drones or []
        self._refresh_transform()
        self.screen.fill(self.COLORS['BACKGROUND'])

        self._draw_ground()
        self._draw_roads()
        self._draw_buildings()
        self._draw_charging_stations()
        self._draw_routes(drones)
        self._draw_drones(drones)
        self._draw_legend()
        self.draw_info_panel(drones, stats)

        pygame.display.flip()

    def _draw_ground(self):
        """绘制地图范围的地面底块。"""
        corners = [(self.min_x, self.min_y), (self.max_x, self.min_y),
                   (self.max_x, self.max_y), (self.min_x, self.max_y)]
        pts = [self.project(x, y, 0.0)[:2] for x, y in corners]
        pygame.draw.polygon(self.screen, self.COLORS['GROUND'], pts)

    def _draw_roads(self):
        for road_type, roads in self.roads_by_type.items():
            for road in roads:
                if len(road.coords) < 2:
                    continue
                pts = [self.project(c[0], c[1], 0.0)[:2] for c in road.coords]
                if len(pts) < 2:
                    continue
                is_major = any(k in road_type for k in ('motorway', 'primary', 'trunk', 'secondary'))
                width = 3 if is_major else 2
                pygame.draw.lines(self.screen, self.COLORS['ROAD_STROKE'], False, pts, width + 2)
                pygame.draw.lines(self.screen, self.COLORS['ROAD'], False, pts, width)

    def _draw_buildings(self):
        """按景深从远到近绘制建筑棱柱（画家算法）。"""
        scale = self.scale
        # 每栋建筑的单向竖直上移量（屋顶 = 底面 + up_offset）
        up_per_meter = scale * self._cosE * self._hs

        # 1) 计算每栋建筑的底面投影点与深度
        proj = []          # (roof_up_offset_px, depth, ring_projected_points, wall_color, roof_color)
        for i, ring in enumerate(self._bldg_rings):
            # 质心深度作为排序键
            cx, cy = self._bldg_c[i][0], self._bldg_c[i][1]
            _, _, depth = self.project(cx, cy, 0.0)
            pts = []
            for (px, py) in ring:
                sx, sy, _ = self.project(px, py, 0.0)
                pts.append((int(sx), int(sy)))
            h = self._bldg_h[i]
            off = up_per_meter * h
            proj.append((off, depth, pts,
                         self._bldg_wall_colors[i], self._bldg_roof_colors[i]))

        # 2) 远→近排序（depth 大者远，先画）
        proj.sort(key=lambda t: t[1], reverse=True)

        # 3) 逐个绘制
        for off, _depth, base_pts, wall_c, roof_c in proj:
            if off <= 0.5:
                # 高度几乎不可见时直接画平面脚印
                pygame.draw.polygon(self.screen, roof_c, base_pts)
                continue
            roof_pts = [(x, y - off) for (x, y) in base_pts]

            # 阴影（底面略下移，增强立体感）
            pygame.draw.polygon(self.screen, (205, 209, 214),
                                [(x, y + 3) for (x, y) in base_pts])

            # 墙体：屋顶环 + 底面环（反向）围成的整体轮廓
            wall_poly = roof_pts + base_pts[::-1]
            pygame.draw.polygon(self.screen, wall_c, wall_poly)
            # 屋顶
            pygame.draw.polygon(self.screen, roof_c, roof_pts)

    def _draw_charging_stations(self):
        """充电站：竖直杆 + 顶部圆盘。"""
        for st in DEFAULT_CHARGING_STATIONS:
            bx, by, _ = self.project(st.x, st.y, 0.0)
            tx, ty, _ = self.project(st.x, st.y, 18.0)
            pygame.draw.line(self.screen, (120, 130, 140), (bx, by), (tx, ty), 2)
            pygame.draw.circle(self.screen, (42, 157, 143), (int(tx), int(ty)), 5)
            pygame.draw.circle(self.screen, (255, 255, 255), (int(tx), int(ty)), 2)
            label = self.small_font.render(str(st.station_id), True, self.COLORS['TEXT'])
            self.screen.blit(label, (int(tx) + 8, int(ty) - 7))

    def _drone_color(self, drone):
        """优先按机型取色，未识别则按编号取色。"""
        dt = getattr(drone, 'drone_type', None)
        if dt in DRONE_TYPE_COLORS:
            return DRONE_TYPE_COLORS[dt]
        idx = int(drone.drone_id.split('_')[1]) if '_' in drone.drone_id else 0
        return self.DRONE_COLORS[idx % len(self.DRONE_COLORS)]

    def _drone_altitude(self, drone):
        """无人机可视高度：充电/待机落地，任务中升至巡航高度。"""
        if getattr(drone, 'is_charging', False):
            return 0.0
        if getattr(drone, 'is_free', True):
            return 0.0
        return self.drone_altitude

    def _draw_routes(self, drones):
        for drone in drones:
            route = drone.scheduled_position
            if not route:
                continue
            color = self._drone_color(drone)
            alt = self._drone_altitude(drone)
            pts = []
            for p in route:
                x, y = p[0], p[1]
                sx, sy, _ = self.project(x, y, alt)
                pts.append((int(sx), int(sy)))
            if len(pts) >= 2:
                self._draw_dashed_polyline(pts, color)
            # 航点标记（源/终点/绕飞点）
            for p in route:
                x, y = p[0], p[1]
                sx, sy, _ = self.project(x, y, alt)
                if len(p) >= 3 and p[2] == 'source':
                    self._marker_pole(sx, sy, alt, (220, 210, 140), 'square')
                elif len(p) >= 3 and p[2] == 'dest':
                    self._marker_pole(sx, sy, alt, (210, 150, 180), 'diamond')
                else:
                    self._marker_pole(sx, sy, alt, (120, 180, 210), 'triangle')

    def _draw_dashed_polyline(self, pts, color, dash=8, gap=6):
        for i in range(len(pts) - 1):
            self._draw_dashed_line(pts[i], pts[i + 1], color, dash_len=dash, gap_len=gap)

    def _draw_dashed_line(self, start, end, color, width=2, dash_len=8, gap_len=6):
        x1, y1 = start
        x2, y2 = end
        dx, dy = x2 - x1, y2 - y1
        length = (dx * dx + dy * dy) ** 0.5
        if length < 2:
            return
        ux, uy = dx / length, dy / length
        pos = 0.0
        drawing = True
        while pos < length:
            s = pos
            e = min(pos + (dash_len if drawing else gap_len), length)
            if drawing:
                pygame.draw.line(self.screen, color,
                                 (int(x1 + ux * s), int(y1 + uy * s)),
                                 (int(x1 + ux * e), int(y1 + uy * e)), max(1, width))
            pos += dash_len if drawing else gap_len
            drawing = not drawing

    def _marker_pole(self, sx, sy, alt, color, shape):
        """航点三维标记：地面立杆 + 顶点形状。"""
        # 竖直方向：sy 随高度 z 线性上移，地面对应点 = 顶点向下回退 offset
        ground_sy = sy + self.scale * self._cosE * alt
        pygame.draw.line(self.screen, (180, 184, 190),
                         (int(sx), int(sy)), (int(sx), int(ground_sy)), 1)
        size = 5
        if shape == 'square':
            pygame.draw.rect(self.screen, color, (sx - size, sy - size, size * 2, size * 2))
        elif shape == 'diamond':
            pygame.draw.polygon(self.screen, color,
                                [(sx, sy - size), (sx + size, sy), (sx, sy + size), (sx - size, sy)])
        else:
            pygame.draw.polygon(self.screen, color,
                                [(sx, sy - size), (sx - size, sy + size), (sx + size, sy + size)])

    def _draw_drones(self, drones):
        for drone in drones:
            x, y = drone.get_position()
            alt = self._drone_altitude(drone)
            color = self._drone_color(drone)
            sx, sy, _ = self.project(x, y, alt)
            sx, sy = int(sx), int(sy)

            # 竖直投影线（表达高度）
            if alt > 0:
                gx, gy, _ = self.project(x, y, 0.0)
                self._draw_dashed_line((sx, sy), (int(gx), int(gy)),
                                       (150, 155, 160), width=1, dash_len=4, gap_len=4)

            # 机体标记
            size = 7
            if drone.is_free and not getattr(drone, 'is_charging', False):
                # 落地待机
                pygame.draw.circle(self.screen, (42, 157, 143), (sx, sy), size + 2)
                pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), size)
                pygame.draw.circle(self.screen, (42, 157, 143), (sx, sy), size - 2)
            else:
                pygame.draw.circle(self.screen, color, (sx, sy), size + 3)
                pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), size + 1)
                pygame.draw.circle(self.screen, color, (sx, sy), size)
                pygame.draw.circle(self.screen, (255, 255, 255), (sx, sy), max(2, size // 3))

            # 编号标签
            label = self.small_font.render(drone.drone_id, True, (255, 255, 255))
            self.screen.blit(label, (sx + 10, sy - 8))
            label = self.small_font.render(drone.drone_id, True, self.COLORS['TEXT'])
            self.screen.blit(label, (sx + 9, sy - 9))

    # ------------------------------------------------------------------ #
    # 图例 / 面板（复用 2D 版逻辑）
    # ------------------------------------------------------------------ #
    def _draw_legend(self):
        items = [
            ("Drone (IDLE)", (42, 157, 143), 'circle_filled'),
            ("Drone (BUSY)", (230, 57, 70), 'circle_hollow'),
            ("Task Source", (220, 210, 140), 'square'),
            ("Task Dest", (210, 150, 180), 'diamond'),
            ("Waypoint", (120, 180, 210), 'triangle'),
            ("Charging", (42, 157, 143), 'circle_small'),
        ]
        lx, ly = 15, self.screen_size[1] - 180
        lw, ih = 160, 22
        bh = len(items) * ih + 16
        shadow = pygame.Rect(lx + 2, ly + 2, lw, bh)
        pygame.draw.rect(self.screen, (200, 200, 205), shadow, border_radius=6)
        card = pygame.Rect(lx, ly, lw, bh)
        pygame.draw.rect(self.screen, (255, 255, 255), card, border_radius=6)
        pygame.draw.rect(self.screen, self.COLORS['PANEL_BORDER'], card, 1, border_radius=6)
        for i, (text, color, shape) in enumerate(items):
            y = ly + 8 + i * ih
            cx, cy = lx + 10, y + 7
            if shape == 'circle_filled':
                pygame.draw.circle(self.screen, color, (cx, cy), 6)
            elif shape == 'circle_hollow':
                pygame.draw.circle(self.screen, color, (cx, cy), 8)
                pygame.draw.circle(self.screen, (255, 255, 255), (cx, cy), 4)
                pygame.draw.circle(self.screen, color, (cx, cy), 2)
            elif shape == 'circle_small':
                pygame.draw.circle(self.screen, color, (cx, cy), 4)
            elif shape == 'square':
                pygame.draw.rect(self.screen, color, (cx - 5, cy - 5, 10, 10))
            elif shape == 'diamond':
                pygame.draw.polygon(self.screen, color,
                                    [(cx, cy - 5), (cx + 5, cy), (cx, cy + 5), (cx - 5, cy)])
            elif shape == 'triangle':
                pygame.draw.polygon(self.screen, color,
                                    [(cx, cy - 5), (cx - 5, cy + 5), (cx + 5, cy + 5)])
            self.screen.blit(self.small_font.render(text, True, self.COLORS['TEXT']), (cx + 14, y))

        # 视角操作提示
        tip = self.small_font.render("LMB: orbit   RMB/Shift: pan   Wheel: zoom   T: top-down   R: reset",
                                     True, self.COLORS['TEXT_SECONDARY'])
        self.screen.blit(tip, (15, 12))

    def _draw_nested_card(self, x, y, w, h):
        pygame.draw.rect(self.screen, (245, 246, 248), (x, y, w, h), border_radius=5)
        pygame.draw.rect(self.screen, (233, 236, 239), (x, y, w, h), 1, border_radius=5)

    def _draw_metric_card(self, panel_x, content_w, y, label, value, value_color=None):
        card_h = 32
        self._draw_nested_card(panel_x, y, content_w, card_h)
        self.screen.blit(self.small_font.render(label, True, self.COLORS['TEXT_SECONDARY']),
                         (panel_x + 8, y + 7))
        vc = value_color or self.COLORS['TEXT']
        val = self.bold_font.render(str(value), True, vc)
        self.screen.blit(val, (panel_x + content_w - 8 - val.get_width(), y + 7))
        return card_h + 3

    def draw_info_panel(self, drones=None, stats=None):
        drones = drones or []
        PANEL_WIDTH = 230
        PADDING = 10
        CARD_PAD = 8
        panel_x = self.screen_size[0] - PANEL_WIDTH - 10
        panel_y = 10
        panel_h = self.screen_size[1] - 20
        content_w = PANEL_WIDTH - CARD_PAD * 2

        pygame.draw.rect(self.screen, (200, 200, 205),
                         (panel_x + 3, panel_y + 3, PANEL_WIDTH, panel_h), border_radius=10)
        card = pygame.Rect(panel_x, panel_y, PANEL_WIDTH, panel_h)
        pygame.draw.rect(self.screen, (255, 255, 255), card, border_radius=10)
        pygame.draw.rect(self.screen, self.COLORS['PANEL_BORDER'], card, 1, border_radius=10)

        y = panel_y + PADDING
        self.screen.blit(self.font.render("Dashboard", True, self.COLORS['TEXT']),
                         (panel_x + CARD_PAD + 2, y))
        y += 26
        self.screen.blit(self.small_font.render(f"FPS: {self.current_fps}", True, self.COLORS['TEXT_SECONDARY']),
                         (panel_x + CARD_PAD + 2, y))
        y += 20

        self._draw_controls(panel_x, CARD_PAD, content_w, y)
        btn_h, gap, sel_h = 30, 6, 30
        ctrl_total = btn_h + gap + sel_h
        if self.algo_dropdown_open:
            ctrl_total += (len(self.algorithm_options) - 1) * 26
        y += ctrl_total + 10

        if stats is not None:
            metrics = [
                ("Completed", str(stats.get('total_completed', 0))),
                ("Completion", f"{stats.get('completion_rate', 0):.1%}"),
                ("On-time Rate", f"{stats.get('on_time_rate', 0):.1%}"),
                ("Avg Delay", f"{stats.get('avg_delay', 0):.1f}"),
                ("Avg Wait", f"{stats.get('avg_wait_time_to_load', 0):.1f}"),
                ("Energy", f"{stats.get('total_energy_consumed', 0):.0f} Wh"),
            ]
            for label, value in metrics:
                y += self._draw_metric_card(panel_x + CARD_PAD, content_w, y, label, value)

        y += 6
        self.screen.blit(self.font.render("Drones", True, self.COLORS['TEXT']),
                         (panel_x + CARD_PAD + 2, y))
        y += 24

        DRONE_CARD_H = 24
        for drone in drones:
            color = self._drone_color(drone)
            status = "IDLE" if drone.is_free else "BUSY"
            battery_pct = drone.get_battery_level()
            dt = getattr(drone, 'drone_type', None)
            type_label = DRONE_TYPE_LABELS.get(dt, "") if dt else ""
            card_x = panel_x + CARD_PAD
            self._draw_nested_card(card_x, y, content_w, DRONE_CARD_H)
            pygame.draw.circle(self.screen, color, (card_x + 10, y + 12), 4)
            text = f"{drone.drone_id} {status} {battery_pct*100:.0f}%"
            if type_label:
                text += f" {type_label}"
            self.screen.blit(self.small_font.render(text, True, self.COLORS['TEXT']),
                             (card_x + 20, y + 7))
            y += DRONE_CARD_H + 3

    def _draw_controls(self, panel_x, card_pad, content_w, y):
        cx = panel_x + card_pad
        btn_w, btn_h = content_w, 30
        self._add_drone_rect = pygame.Rect(cx, y, btn_w, btn_h)
        btn_color = (100, 170, 150)
        hover = self._add_drone_rect.collidepoint(pygame.mouse.get_pos())
        if hover:
            btn_color = (80, 150, 130)
        pygame.draw.rect(self.screen, btn_color, self._add_drone_rect, border_radius=6)
        label = self.small_font.render("+ Add Drone", True, (255, 255, 255))
        self.screen.blit(label, (cx + (btn_w - label.get_width()) // 2, y + 7))
        y += btn_h + 6

        sel_h = 30
        self._algo_selector_rect = pygame.Rect(cx, y, content_w, sel_h)
        pygame.draw.rect(self.screen, (230, 233, 238), self._algo_selector_rect, border_radius=6)
        pygame.draw.rect(self.screen, self.COLORS['PANEL_BORDER'], self._algo_selector_rect, 1, border_radius=6)
        self.screen.blit(self.small_font.render(f"Algo: {self.selected_algorithm}", True, self.COLORS['TEXT']),
                         (cx + 8, y + 7))
        self.screen.blit(self.small_font.render("▾", True, self.COLORS['TEXT_SECONDARY']),
                         (cx + content_w - 20, y + 7))

        if self.algo_dropdown_open:
            opts = [a for a in self.algorithm_options if a != self.selected_algorithm]
            self._algo_dropdown_rects.clear()
            for i, opt in enumerate(opts):
                opt_y = y + sel_h + i * 26
                rect = pygame.Rect(cx, opt_y, content_w, 26)
                self._algo_dropdown_rects.append((opt, rect))
                bg = (210, 215, 220) if rect.collidepoint(pygame.mouse.get_pos()) else (240, 243, 246)
                pygame.draw.rect(self.screen, bg, rect, border_radius=4)
                pygame.draw.rect(self.screen, (222, 226, 230), rect, 1, border_radius=4)
                self.screen.blit(self.small_font.render(opt, True, self.COLORS['TEXT']),
                                 (cx + 8, opt_y + 4))

    # ------------------------------------------------------------------ #
    # 字体 / 交互 / 主循环
    # ------------------------------------------------------------------ #
    def _init_fonts(self):
        candidates = [
            '/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/System/Library/Fonts/Helvetica.ttc',
            'C:\\Windows\\Fonts\\segoeui.ttf',
            'C:\\Windows\\Fonts\\arial.ttf',
        ]
        font_loaded = next((p for p in candidates if os.path.exists(p)), None)
        if font_loaded:
            self.font = pygame.font.Font(font_loaded, 18)
            self.small_font = pygame.font.Font(font_loaded, 14)
            self.title_font = pygame.font.Font(font_loaded, 22)
            self.bold_font = pygame.font.Font(font_loaded, 14)
        else:
            self.font = pygame.font.Font(None, 20)
            self.small_font = pygame.font.Font(None, 16)
            self.title_font = pygame.font.Font(None, 24)
            self.bold_font = pygame.font.Font(None, 16)
        self.bold_font.set_bold(True)

    def set_on_add_drone(self, callback):
        self.on_add_drone = callback

    def _find_building_at(self, screen_pos):
        try:
            wx, wy = self.screen_to_ground(screen_pos[0], screen_pos[1])
        except Exception:
            return None
        point = Point(wx, wy)
        if not self.building_geoms:
            return None
        for idx in self.building_index.query(point):
            if self.building_geoms[idx].contains(point):
                return idx
        return None

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # 左键
                    ui_handled = False
                    if self.algo_dropdown_open:
                        for opt, rect in self._algo_dropdown_rects:
                            if rect.collidepoint(event.pos):
                                self.selected_algorithm = opt
                                self.algo_dropdown_open = False
                                ui_handled = True
                                break
                    if not ui_handled and self._algo_selector_rect and self._algo_selector_rect.collidepoint(event.pos):
                        self.algo_dropdown_open = not self.algo_dropdown_open
                        ui_handled = True
                    if not ui_handled and self._add_drone_rect and self._add_drone_rect.collidepoint(event.pos):
                        if self.on_add_drone:
                            self.on_add_drone()
                        self.algo_dropdown_open = False
                        ui_handled = True
                    if not ui_handled:
                        # Shift 键 + 左键 = 平移；否则旋转
                        if pygame.key.get_mods() & pygame.KMOD_SHIFT:
                            self.drag_mode = 'pan'
                        else:
                            self.drag_mode = 'orbit'
                        self.dragging = True
                        self.drag_start = event.pos
                        self.algo_dropdown_open = False
                elif event.button == 3:  # 右键平移
                    self.drag_mode = 'pan'
                    self.dragging = True
                    self.drag_start = event.pos
                elif event.button == 4:  # 滚轮放大
                    self.zoom = min(self.zoom * 1.1, 8.0)
                    self._apply_zoom()
                elif event.button == 5:  # 滚轮缩小
                    self.zoom = max(self.zoom / 1.1, 0.2)
                    self._apply_zoom()

            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button in (1, 3):
                    self.dragging = False
                    self.drag_mode = None

            elif event.type == pygame.MOUSEMOTION:
                if self.dragging:
                    dx = event.pos[0] - self.drag_start[0]
                    dy = event.pos[1] - self.drag_start[1]
                    if self.drag_mode == 'orbit':
                        self.azimuth = (self.azimuth + dx * 0.4) % 360.0
                        self.elevation = max(5.0, min(89.0, self.elevation - dy * 0.3))
                    else:
                        self.pan_x += dx
                        self.pan_y += dy
                    self.drag_start = event.pos

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    self.azimuth = DEFAULT_AZIMUTH
                    self.elevation = DEFAULT_ELEVATION
                    self.zoom = DEFAULT_ZOOM
                    self.pan_x = 0
                    self.pan_y = 0
                    self.topdown = False
                    self._apply_zoom()
                elif event.key == pygame.K_t:
                    self.topdown = not self.topdown
                elif event.key == pygame.K_EQUALS or event.key == pygame.K_PLUS:
                    self.height_scale = min(8.0, self.height_scale + 0.5)
                elif event.key == pygame.K_MINUS:
                    self.height_scale = max(0.5, self.height_scale - 0.5)

        return True

    def _apply_zoom(self):
        self.scale = self.base_scale * self.zoom

    def render(self, drones, stats=None):
        running = self.handle_events()
        self.draw(drones, stats)

        current = pygame.time.get_ticks()
        self.fps_counter += 1
        if current - self.fps_time > 1000:
            self.current_fps = self.fps_counter
            self.fps_counter = 0
            self.fps_time = current
        self.clock.tick(60)
        return running

    def run(self):
        running = True
        drones = []
        while running:
            running = self.handle_events()
            self.draw(drones, None)
            self.clock.tick(60)
        pygame.quit()


if __name__ == "__main__":
    import sys
    osm = "data/map/part_of_yangpu.osm"
    viewer = MapViewer3D(osm)
    viewer.run()