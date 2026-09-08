import os
import osmnx as ox
import pygame
import numpy as np
from shapely.geometry import Point, LineString, Polygon, box
from shapely.strtree import STRtree
import math
from collections import defaultdict
from drone import Drone
from frontend.charging_station import ChargingStation
from tools.osm import load_map_data
from drone import DEFAULT_CHARGING_STATIONS

class OptimizedMapViewer:
    """优化的地图查看器，使用空间索引提高性能"""
    
    def __init__(self, osm_file_path, screen_size=(1200, 800)):
        pygame.init()
        self.clock = pygame.time.Clock()
        self.screen_size = screen_size
        self.screen = pygame.display.set_mode(screen_size)
        pygame.display.set_caption("OSM Map Viewer - Optimized")
        
        # 颜色方案 — 清新极简风
        self.COLORS = {
            'BACKGROUND': (248, 249, 250),     # #f8f9fa 浅灰背景
            'ROAD_HIGHWAY': (233, 236, 239),   # 次要道路 - 浅灰
            'ROAD_RESIDENTIAL': (255, 255, 255), # #ffffff 居民区道路 - 白色
            'ROAD_PRIMARY': (255, 255, 255),    # #ffffff 主干道 - 白色
            'ROAD_STROKE': (222, 226, 230),     # 道路边框 - 浅灰
            'BUILDING': (233, 236, 239),        # #e9ecef 建筑填充
            'BUILDING_STROKE': (173, 181, 189), # #adb5bd 建筑描边
            'BUILDING_HIGH': (206, 212, 218),   # 高层建筑 - 稍深
            'BUILDING_HOVER': (173, 181, 189),  # 悬停高亮
            'BUILDING_SELECTED': (100, 180, 140), # 选中建筑
            'WATER': (180, 210, 230),           # 水域浅蓝
            'GREEN': (160, 210, 160),           # 绿地
            'TEXT': (33, 37, 41),               # #212529 深灰文字
            'TEXT_SECONDARY': (108, 117, 125),  # 次要文字
            'SELECTION': (100, 150, 200, 128),
            'PANEL_BG': (255, 255, 255, 240),   # 白色面板背景
            'PANEL_BORDER': (222, 226, 230),    # 面板边框
            'SHADOW': (0, 0, 0, 30),            # 阴影色
        }

        # 无人机颜色配置 — 低饱和度
        self.DRONE_COLORS = [
            (190, 120, 120),   # 红色
            (120, 150, 170),   # 蓝色
            (120, 165, 155),   # 青色
            (215, 175, 140),   # 橙色
            (170, 140, 195),   # 紫色
            (210, 150, 180),   # 粉色
            (220, 210, 140),   # 黄色
            (120, 180, 210),   # 天蓝
        ]

        # 特殊点颜色 — 低饱和度
        self.TASK_SOURCE_COLOR = (220, 210, 140)   # 任务起点 - 明黄方块
        self.TASK_DEST_COLOR = (210, 150, 180)     # 任务终点 - 粉色菱形
        self.WAYPOINT_COLOR = (120, 180, 210)      # 绕飞转弯点 - 天蓝三角
        self.NEXT_TARGET_COLOR = (190, 120, 120)   # 下一个目标 - 红色大圆
        
        # 视图控制
        self.zoom = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.dragging = False
        self.drag_start = (0, 0)

        self.fps_counter = 0
        self.fps_time = 0
        self.current_fps = 0
        
        # 加载数据
        # self.load_map_data(osm_file_path)
        self.roads_by_type, self.buildings_with_height = load_map_data(osm_file_path)
        
        # print(f"buildings_with_height: {self.buildings_with_height[0]}")
        
        # 构建空间索引
        self.build_spatial_index()
        
        # 计算边界
        self.calculate_bounds()

        self.scale = min(self.screen_size[0] / self.map_width, self.screen_size[1] / self.map_height)
        
        # 交互状态
        self.hovered_building = None
        self.selected_building = None

        # 右侧面板交互组件
        self.selected_algorithm = "Greedy"
        self.algorithm_options = ["Greedy", "PSO", "QMIX", "VDN", "IQL"]
        self.algo_dropdown_open = False
        self._add_drone_rect = None
        self._algo_selector_rect = None
        self._algo_dropdown_rects: list = []
        self.on_add_drone = None  # callback, 由外部设置


        # 尝试加载系统字体，回退到默认
        self._init_fonts()

    def set_on_add_drone(self, callback):
        """设置"添加无人机"按钮的回调函数"""
        self.on_add_drone = callback
        
        # 尝试加载系统字体，回退到默认
        self._init_fonts()

    def _init_fonts(self):
        """初始化字体，优先使用系统字体"""
        font_candidates = [
            # Linux
            '/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf',
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            # macOS
            '/System/Library/Fonts/Helvetica.ttc',
            '/System/Library/Fonts/SFNSDisplay.ttf',
            # Windows
            'C:\\Windows\\Fonts\\segoeui.ttf',
            'C:\\Windows\\Fonts\\arial.ttf',
        ]
        font_loaded = None
        for path in font_candidates:
            if os.path.exists(path):
                font_loaded = path
                break
        if font_loaded:
            self.font = pygame.font.Font(font_loaded, 18)
            self.small_font = pygame.font.Font(font_loaded, 14)
            self.title_font = pygame.font.Font(font_loaded, 22)
            self.bold_font = pygame.font.Font(font_loaded, 14)
            self.bold_font.set_bold(True)
        else:
            self.font = pygame.font.Font(None, 20)
            self.small_font = pygame.font.Font(None, 16)
            self.title_font = pygame.font.Font(None, 24)
            self.bold_font = pygame.font.Font(None, 16)
            self.bold_font.set_bold(True)
        
        # 加载图片资源
        try:
            self.charger_image = pygame.image.load('assets/charging_4.png').convert_alpha()
        except pygame.error as e:
            print(f"Failed to load charger image: {e}")
            self.charger_image = None
       
    def build_spatial_index(self):
        """构建空间索引以加速查询"""
        self.building_geoms = [b['geometry'] for b in self.buildings_with_height]
        if self.building_geoms:
            self.building_index = STRtree(self.building_geoms)
    
    def calculate_bounds(self):
        """计算边界"""
        all_geoms = []
        
        for roads in self.roads_by_type.values():
            all_geoms.extend(roads)
        
        all_geoms.extend(self.building_geoms)
        
        if all_geoms:
            bounds = all_geoms[0].bounds
            min_x, min_y, max_x, max_y = bounds
            
            for geom in all_geoms[1:]:
                b = geom.bounds
                min_x = min(min_x, b[0])
                min_y = min(min_y, b[1])
                max_x = max(max_x, b[2])
                max_y = max(max_y, b[3])
            
            self.min_x, self.min_y, self.max_x, self.max_y = min_x, min_y, max_x, max_y
        else:
            self.min_x, self.min_y, self.max_x, self.max_y = -180, -90, 180, 90
        
        self.map_width = self.max_x - self.min_x
        self.map_height = self.max_y - self.min_y

        # print(f"Map bounds: ({self.min_x}, {self.min_y}) to ({self.max_x}, {self.max_y}), size: ({self.map_width}, {self.map_height})")
    
    def world_to_screen(self, x, y):
        """坐标转换"""
        # 使用统一的缩放比例
        screen_x = (x - self.min_x) * self.scale * self.zoom
        screen_y = (self.max_y - y) * self.scale * self.zoom
        screen_x += self.pan_x
        screen_y += self.pan_y
        return int(screen_x), int(screen_y)

    def get_visible_bounds(self):
        """获取当前可见区域的边界"""
        top_left = self.screen_to_world(0, 0)
        bottom_right = self.screen_to_world(self.screen_size[0], self.screen_size[1])
        return (top_left[0], bottom_right[1], bottom_right[0], top_left[1])

    def screen_to_world(self, screen_x, screen_y):
        """屏幕坐标转世界坐标"""
        # 使用统一的缩放比例
        unified_scale = min(self.screen_size[0], self.screen_size[1])
        world_x = (screen_x - self.pan_x) / self.zoom / self.scale  + self.min_x
        world_y = self.max_y - (screen_y - self.pan_y) / self.zoom / self.scale 
        return world_x, world_y
    
    def draw_road(self, road, road_type):
        """绘制道路"""
        if len(road.coords) < 2:
            return

        screen_points = []
        for coord in road.coords:
            screen_point = self.world_to_screen(coord[0], coord[1])
            screen_points.append(screen_point)

        # 根据道路类型设置样式 — 白色道路 + 浅灰边框
        if 'motorway' in road_type or 'primary' in road_type or 'trunk' in road_type:
            color = self.COLORS['ROAD_PRIMARY']
            stroke_color = self.COLORS['ROAD_STROKE']
            width = max(2, int(4 * self.zoom))
            stroke_width = width + 2
        elif 'secondary' in road_type:
            color = self.COLORS['ROAD_PRIMARY']
            stroke_color = self.COLORS['ROAD_STROKE']
            width = max(2, int(3 * self.zoom))
            stroke_width = width + 2
        elif 'residential' in road_type or 'living' in road_type:
            color = self.COLORS['ROAD_RESIDENTIAL']
            width = max(1, int(2 * self.zoom))
            stroke_color = None
            stroke_width = 0
        else:
            color = self.COLORS['ROAD_HIGHWAY']
            width = max(1, int(1.5 * self.zoom))
            stroke_color = None
            stroke_width = 0

        if len(screen_points) > 1:
            # 先画边框（仅主干道）
            if stroke_color:
                pygame.draw.lines(self.screen, stroke_color, False, screen_points, stroke_width)
            pygame.draw.lines(self.screen, color, False, screen_points, width)
    
    def draw_building(self, building_data, is_hovered=False, is_selected=False):
        """绘制建筑 — 高度分级着色 + 描边"""
        geom = building_data['geometry']

        if hasattr(geom, 'exterior'):
            screen_points = []
            for coord in geom.exterior.coords:
                screen_point = self.world_to_screen(coord[0], coord[1])
                screen_points.append(screen_point)

            if len(screen_points) > 2:
                height = building_data.get('height')
                # 根据状态和高度选择颜色
                if is_selected:
                    fill_color = self.COLORS['BUILDING_SELECTED']
                    stroke_color = (70, 150, 110)
                    stroke_width = 2
                elif is_hovered:
                    fill_color = self.COLORS['BUILDING_HOVER']
                    stroke_color = (140, 150, 160)
                    stroke_width = 2
                elif height and height > 30:
                    # 超高层建筑 - 稍深
                    fill_color = (180, 185, 195)
                    stroke_color = self.COLORS['BUILDING_STROKE']
                    stroke_width = 1
                elif height and height > 15:
                    # 中层建筑
                    fill_color = (215, 220, 225)
                    stroke_color = self.COLORS['BUILDING_STROKE']
                    stroke_width = 1
                elif height and height > 0:
                    # 低层建筑
                    fill_color = (233, 236, 239)  # #e9ecef
                    stroke_color = self.COLORS['BUILDING_STROKE']
                    stroke_width = 1
                else:
                    # 未知高度
                    fill_color = self.COLORS['BUILDING']
                    stroke_color = self.COLORS['BUILDING_STROKE']
                    stroke_width = 1

                # 先画阴影偏移
                shadow_offset = 1
                shadow_points = [(p[0] + shadow_offset, p[1] + shadow_offset) for p in screen_points]
                pygame.draw.polygon(self.screen, (220, 220, 225), shadow_points)
                # 填充
                pygame.draw.polygon(self.screen, fill_color, screen_points)
                # 描边
                pygame.draw.polygon(self.screen, stroke_color, screen_points, stroke_width)

    def draw_charging_station(self, station: ChargingStation):
        """绘制充电站 — 清新简洁风格"""
        screen_pos = self.world_to_screen(station.x, station.y)

        if self.charger_image:
            # 使用图片绘制充电站
            base_size = 32
            scaled_size = max(base_size, int(base_size * self.zoom))
            scaled_image = pygame.transform.scale(self.charger_image, (scaled_size, scaled_size))
            image_rect = scaled_image.get_rect(center=screen_pos)
            self.screen.blit(scaled_image, image_rect)
        else:
            # 回退到圆形绘制 — 绿色充电图标风格
            station_size = max(10, int(8 * self.zoom))

            # 外圈 — 浅灰
            pygame.draw.circle(self.screen, (222, 226, 230), screen_pos, station_size)
            # 主体 — 白色
            pygame.draw.circle(self.screen, (255, 255, 255), screen_pos, station_size - 2)
            # 内圈 — 绿色充电色
            charge_color = (42, 157, 143)
            pygame.draw.circle(self.screen, charge_color, screen_pos, station_size - 4)
            # 闪电符号（白色小圆）
            pygame.draw.circle(self.screen, (255, 255, 255), screen_pos, max(2, station_size // 3))

            # 绘制充电站ID
            id_text = self.small_font.render(str(station.station_id), True, self.COLORS['TEXT'])
            self.screen.blit(id_text, (screen_pos[0] + station_size + 4, screen_pos[1] - 6))

                
    
    def find_hovered_building(self, mouse_pos):
        """查找鼠标悬停的建筑"""
        world_x, world_y = self.screen_to_world(mouse_pos[0], mouse_pos[1])
        point = Point(world_x, world_y)
        
        if self.building_geoms:
            # 使用空间索引查找
            indices = self.building_index.query(point)
            for idx in indices:
                if self.building_geoms[idx].contains(point):
                    return idx
        return None
    
    def _draw_nested_card(self, x, y, w, h):
        """绘制嵌套小卡片的背景"""
        pygame.draw.rect(self.screen, (245, 246, 248), (x, y, w, h), border_radius=5)
        pygame.draw.rect(self.screen, (233, 236, 239), (x, y, w, h), 1, border_radius=5)

    def _draw_metric_card(self, panel_x, content_w, y, label, value, value_color=None):
        """在指定 y 位置绘制单个指标小卡片，返回卡片高度"""
        card_h = 32
        self._draw_nested_card(panel_x, y, content_w, card_h)
        # label 在左侧
        label_surf = self.small_font.render(label, True, self.COLORS['TEXT_SECONDARY'])
        self.screen.blit(label_surf, (panel_x + 8, y + 7))
        # value 在右侧 — 加粗
        vc = value_color or self.COLORS['TEXT']
        val_surf = self.bold_font.render(str(value), True, vc)
        self.screen.blit(val_surf, (panel_x + content_w - 8 - val_surf.get_width(), y + 7))
        return card_h + 3

    def draw_info_panel(self, drones=[], stats=None):
        """绘制右侧信息面板 — 全高度白色背景
          指标若干小卡片 + 无人机独立卡片"""
        PANEL_WIDTH = 230
        PADDING = 10
        CARD_PAD = 8
        panel_x = self.screen_size[0] - PANEL_WIDTH - 10
        panel_y = 10
        panel_h = self.screen_size[1] - 20
        content_w = PANEL_WIDTH - CARD_PAD * 2  # 内容区域宽度

        # === 满高度主面板 ===
        shadow_rect = pygame.Rect(panel_x + 3, panel_y + 3, PANEL_WIDTH, panel_h)
        pygame.draw.rect(self.screen, (200, 200, 205), shadow_rect, border_radius=10)
        card_rect = pygame.Rect(panel_x, panel_y, PANEL_WIDTH, panel_h)
        pygame.draw.rect(self.screen, (255, 255, 255), card_rect, border_radius=10)
        pygame.draw.rect(self.screen, self.COLORS['PANEL_BORDER'], card_rect, 1, border_radius=10)

        y = panel_y + PADDING

        # ===== 标题 =====
        title = self.font.render("Dashboard", True, self.COLORS['TEXT'])
        self.screen.blit(title, (panel_x + CARD_PAD + 2, y))
        y += 26

        # ===== FPS =====
        fps = self.small_font.render(f"FPS: {self.current_fps}", True, self.COLORS['TEXT_SECONDARY'])
        self.screen.blit(fps, (panel_x + CARD_PAD + 2, y))
        y += 20

        # ===== 交互控件 =====
        self._draw_controls(panel_x, CARD_PAD, content_w, y)
        # _draw_controls 的内部 y 递增不可控，手动估算偏移后继续
        btn_h = 30; gap = 6; sel_h = 30
        ctrl_total = btn_h + gap + sel_h
        if self.algo_dropdown_open:
            opts_count = len(self.algorithm_options) - 1
            ctrl_total += opts_count * 26
        y += ctrl_total + 10

        # ===== 指标小卡片 =====
        if stats is not None:
            metrics = [
                ("Completed",    str(stats.get('total_completed', 0))),
                ("Completion",   f"{stats.get('completion_rate', 0):.1%}"),
                ("On-time Rate", f"{stats.get('on_time_rate', 0):.1%}"),
                ("Avg Delay",    f"{stats.get('avg_delay', 0):.1f}"),
                ("Avg Wait",     f"{stats.get('avg_wait_time_to_load', 0):.1f}"),
                ("Energy",       f"{stats.get('total_energy_consumed', 0):.0f} Wh"),
            ]
            for label, value in metrics:
                y += self._draw_metric_card(panel_x + CARD_PAD, content_w, y, label, value)

        # ===== 分隔间距 =====
        y += 6

        # ===== 无人机小卡片 =====
        drone_label = self.font.render("Drones", True, self.COLORS['TEXT'])
        self.screen.blit(drone_label, (panel_x + CARD_PAD + 2, y))
        y += 24

        DRONE_CARD_H = 24  # 每个无人机卡片高度
        for drone in drones:
            drone_idx = int(drone.drone_id.split('_')[1]) if '_' in drone.drone_id else 0
            drone_color = self.DRONE_COLORS[drone_idx % len(self.DRONE_COLORS)]
            status = "IDLE" if drone.is_free else "BUSY"
            battery_pct = drone.get_battery_level()

            # 单独卡片背景
            card_x = panel_x + CARD_PAD
            self._draw_nested_card(card_x, y, content_w, DRONE_CARD_H)

            # 状态圆点
            dot_color = self.COLORS['TEXT']
            pygame.draw.circle(self.screen, dot_color, (card_x + 10, y + 12), 4)

            # 名称 + 状态 + 电量百分比
            label = self.small_font.render(
                f"{drone.drone_id}  {status}  {battery_pct*100:.0f}%",
                True, self.COLORS['TEXT'])
            self.screen.blit(label, (card_x + 20, y + 7))

            y += DRONE_CARD_H + 3

        y += 4

        # ===== 选中建筑卡片（如有） =====
        if self.selected_building is not None:
            building = self.buildings_with_height[self.selected_building]
            y += 6
            bldg_label = self.font.render("Building", True, self.COLORS['TEXT'])
            self.screen.blit(bldg_label, (panel_x + CARD_PAD + 2, y))
            y += 22

            lines = []
            h = building.get('height')
            lines.append(f"Height: {h or 'Unknown'}m")
            if building.get('id') is not None:
                lines.append(f"ID: {building['id']}")
            name = building.get('tags', {}).get('name')
            if name:
                lines.append(str(name))

            bldg_card_h = len(lines) * 18 + 10
            self._draw_nested_card(panel_x + CARD_PAD, y, content_w, bldg_card_h)
            y += 5
            for line in lines:
                s = self.small_font.render(line, True, self.COLORS['TEXT_SECONDARY'])
                self.screen.blit(s, (panel_x + CARD_PAD + 10, y))
                y += 18
            y += 5

    def _draw_controls(self, panel_x, card_pad, content_w, y):
        """绘制顶部交互控件：添加无人机按钮 + 算法切换下拉"""
        cx = panel_x + card_pad  # 控件左边界

        # ---- 添加无人机按钮 ----
        btn_w = content_w
        btn_h = 30
        self._add_drone_rect = pygame.Rect(cx, y, btn_w, btn_h)

        btn_color = (100, 170, 150)
        hover = self._add_drone_rect.collidepoint(pygame.mouse.get_pos())
        if hover:
            btn_color = (80, 150, 130)

        pygame.draw.rect(self.screen, btn_color, self._add_drone_rect, border_radius=6)
        btn_label = self.small_font.render("+ Add Drone", True, (255, 255, 255))
        self.screen.blit(btn_label, (cx + (btn_w - btn_label.get_width()) // 2, y + 7))
        y += btn_h + 6

        # ---- 算法切换下拉 ----
        sel_h = 30
        self._algo_selector_rect = pygame.Rect(cx, y, content_w, sel_h)

        # 下拉按钮
        sel_color = (230, 233, 238)
        pygame.draw.rect(self.screen, sel_color, self._algo_selector_rect, border_radius=6)
        pygame.draw.rect(self.screen, self.COLORS['PANEL_BORDER'], self._algo_selector_rect, 1, border_radius=6)

        algo_text = self.small_font.render(f"Algo: {self.selected_algorithm}", True, self.COLORS['TEXT'])
        self.screen.blit(algo_text, (cx + 8, y + 7))
        # 下拉箭头
        arrow = self.small_font.render("▾", True, self.COLORS['TEXT_SECONDARY'])
        self.screen.blit(arrow, (cx + content_w - 20, y + 7))

        # 下拉列表
        if self.algo_dropdown_open:
            opts = [a for a in self.algorithm_options if a != self.selected_algorithm]
            self._algo_dropdown_rects.clear()
            for i, opt in enumerate(opts):
                opt_y = y + sel_h + i * 26
                opt_rect = pygame.Rect(cx, opt_y, content_w, 26)
                self._algo_dropdown_rects.append((opt, opt_rect))

                opt_hover = opt_rect.collidepoint(pygame.mouse.get_pos())
                bg = (210, 215, 220) if opt_hover else (240, 243, 246)
                pygame.draw.rect(self.screen, bg, opt_rect, border_radius=4)
                pygame.draw.rect(self.screen, (222, 226, 230), opt_rect, 1, border_radius=4)
                opt_label = self.small_font.render(opt, True, self.COLORS['TEXT'])
                self.screen.blit(opt_label, (cx + 8, opt_y + 4))

    def handle_events(self):
        """处理事件"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # 左键
                    ui_handled = False

                    # 1) 下拉列表项点击
                    if self.algo_dropdown_open:
                        for opt_name, opt_rect in self._algo_dropdown_rects:
                            if opt_rect.collidepoint(event.pos):
                                self.selected_algorithm = opt_name
                                self.algo_dropdown_open = False
                                ui_handled = True
                                break

                    # 2) 算法选择器点击（切换下拉）
                    if not ui_handled and self._algo_selector_rect is not None:
                        if self._algo_selector_rect.collidepoint(event.pos):
                            self.algo_dropdown_open = not self.algo_dropdown_open
                            ui_handled = True

                    # 3) 添加无人机按钮点击
                    if not ui_handled and self._add_drone_rect is not None:
                        if self._add_drone_rect.collidepoint(event.pos):
                            if self.on_add_drone is not None:
                                self.on_add_drone()
                            self.algo_dropdown_open = False
                            ui_handled = True

                    if ui_handled:
                        pass  # UI 事件已处理
                    else:
                        # 检查是否点击了建筑
                        hover_idx = self.find_hovered_building(event.pos)
                        if hover_idx is not None:
                            self.selected_building = hover_idx
                        else:
                            # 开始拖动
                            self.dragging = True
                            self.drag_start = event.pos
                            self.algo_dropdown_open = False  # 点击地图关闭下拉
                elif event.button == 4:  # 放大
                    # 以鼠标位置为中心缩放
                    mouse_world = self.screen_to_world(event.pos[0], event.pos[1])
                    self.zoom *= 1.1
                    self.zoom = min(self.zoom, 10.0)
                    # 调整平移使鼠标位置保持不变
                    new_mouse_screen = self.world_to_screen(mouse_world[0], mouse_world[1])
                    self.pan_x += event.pos[0] - new_mouse_screen[0]
                    self.pan_y += event.pos[1] - new_mouse_screen[1]
                elif event.button == 5:  # 缩小
                    mouse_world = self.screen_to_world(event.pos[0], event.pos[1])
                    self.zoom /= 1.1
                    self.zoom = max(self.zoom, 0.05)
                    new_mouse_screen = self.world_to_screen(mouse_world[0], mouse_world[1])
                    self.pan_x += event.pos[0] - new_mouse_screen[0]
                    self.pan_y += event.pos[1] - new_mouse_screen[1]
            
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    self.dragging = False
            
            elif event.type == pygame.MOUSEMOTION:
                if self.dragging:
                    dx = event.pos[0] - self.drag_start[0]
                    dy = event.pos[1] - self.drag_start[1]
                    self.pan_x += dx
                    self.pan_y += dy
                    self.drag_start = event.pos
                else:
                    # 更新悬停的建筑
                    hover_idx = self.find_hovered_building(event.pos)
                    self.hovered_building = hover_idx
            
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    self.zoom = 1.0
                    self.pan_x = 0
                    self.pan_y = 0
                    self.selected_building = None
        
        return True


    def draw(self, drones=[], stats=None):
        """主绘制函数"""
        self.screen.fill(self.COLORS['BACKGROUND'])

        # 获取可见区域
        visible_bounds = self.get_visible_bounds()
        
        # 绘制道路
        for road_type, roads in self.roads_by_type.items():
            for road in roads:
                if road.bounds[2] >= visible_bounds[0] and road.bounds[0] <= visible_bounds[2] and \
                   road.bounds[3] >= visible_bounds[1] and road.bounds[1] <= visible_bounds[3]:
                    self.draw_road(road, road_type)
        
        # 绘制建筑
        for idx, building in enumerate(self.buildings_with_height):
            geom = building['geometry']
            if geom.bounds[2] >= visible_bounds[0] and geom.bounds[0] <= visible_bounds[2] and \
               geom.bounds[3] >= visible_bounds[1] and geom.bounds[1] <= visible_bounds[3]:
                is_hovered = (self.hovered_building == idx)
                is_selected = (self.selected_building == idx)
                self.draw_building(building, is_hovered, is_selected)
        
        # 绘制所有充电站
        for station in DEFAULT_CHARGING_STATIONS:
            self.draw_charging_station(station)

        # 绘制所有无人机的路线（先画路线，再画无人机）
        for drone in drones:
            drone_idx = int(drone.drone_id.split('_')[1]) if '_' in drone.drone_id else 0
            drone_color = self.DRONE_COLORS[drone_idx % len(self.DRONE_COLORS)]
            
            if drone.scheduled_position:
                self.draw_drone_route(drone, drone_color)
        
        # 绘制无人机到下一个目标的航向虚线
        for drone in drones:
            drone_idx = int(drone.drone_id.split('_')[1]) if '_' in drone.drone_id else 0
            drone_color = self.DRONE_COLORS[drone_idx % len(self.DRONE_COLORS)]
            if drone.scheduled_position:
                next_target = drone.scheduled_position[0]
                tx = next_target[0]
                ty = next_target[1]
                drone_pos = self.world_to_screen(drone.x, drone.y)
                target_pos = self.world_to_screen(tx, ty)
                self.draw_dashed_line(target_pos, drone_pos, drone_color, width=2, dash_len=6, gap_len=4)

        # 绘制无人机和任务点
        for drone in drones:
            drone_idx = int(drone.drone_id.split('_')[1]) if '_' in drone.drone_id else 0
            drone_color = self.DRONE_COLORS[drone_idx % len(self.DRONE_COLORS)]
            self.draw_drone(drone, drone_color)
        

        # 绘制图例
        self.draw_legend()
        
        # 绘制UI
        self.draw_info_panel(drones, stats)
        
        pygame.display.flip()
    
    def draw_drone_route(self, drone, drone_color):
        """绘制无人机的路线，区分不同类型的航点"""
        route = drone.scheduled_position
        
        # 检查路线格式：是否包含类型信息 (x, y, type)
        has_types = len(route) > 0 and len(route[0]) >= 3
        
        # 绘制路线线段（半透明）
        for i in range(len(route) - 1):
            if has_types:
                start_screen = self.world_to_screen(route[i][0], route[i][1])
                end_screen = self.world_to_screen(route[i+1][0], route[i+1][1])
            else:
                start_screen = self.world_to_screen(route[i][0], route[i][1])
                end_screen = self.world_to_screen(route[i+1][0], route[i+1][1])
            
            # 绘制虚线线段
            self.draw_dashed_line(start_screen, end_screen, drone_color, width=2, dash_len=8, gap_len=6)
        
        # 根据类型绘制航点标记
        for i, point in enumerate(route):
            if has_types:
                x, y, point_type = point
                screen_pos = self.world_to_screen(x, y)
                
                if point_type == 'source':
                    # 任务起点 - 黄色方块
                    square_size = max(5, int(4 * self.zoom))
                    rect = pygame.Rect(screen_pos[0] - square_size, screen_pos[1] - square_size, 
                                       square_size * 2, square_size * 2)
                    pygame.draw.rect(self.screen, self.TASK_SOURCE_COLOR, rect)
                    pygame.draw.rect(self.screen, self.COLORS['BUILDING_STROKE'], rect, 1)
                elif point_type == 'dest':
                    # 任务终点 - 粉色菱形
                    self.draw_diamond(screen_pos, self.TASK_DEST_COLOR, max(6, int(5 * self.zoom)))
                elif point_type == 'waypoint':
                    # 绕飞航点 - 天蓝色三角形
                    self.draw_triangle(screen_pos, self.WAYPOINT_COLOR, size=max(4, int(3 * self.zoom)))
            else:
                # 旧格式（无类型信息）：第一个是 source，最后一个是 dest，中间是 waypoint
                screen_pos = self.world_to_screen(point[0], point[1])
                if i == 0:
                    square_size = max(5, int(4 * self.zoom))
                    rect = pygame.Rect(screen_pos[0] - square_size, screen_pos[1] - square_size, 
                                       square_size * 2, square_size * 2)
                    pygame.draw.rect(self.screen, self.TASK_SOURCE_COLOR, rect)
                    pygame.draw.rect(self.screen, self.COLORS['BUILDING_STROKE'], rect, 1)
                elif i == len(route) - 1:
                    self.draw_diamond(screen_pos, self.TASK_DEST_COLOR, max(6, int(5 * self.zoom)))
                elif len(route) > 2:
                    self.draw_triangle(screen_pos, self.WAYPOINT_COLOR, size=max(4, int(3 * self.zoom)))
    
    def draw_dashed_line(self, start, end, color, width=2, dash_len=8, gap_len=6):
        """绘制虚线"""
        x1, y1 = start
        x2, y2 = end
        dx = x2 - x1
        dy = y2 - y1
        length = (dx*dx + dy*dy) ** 0.5
        if length < 2:
            return

        # 单位方向向量
        ux = dx / length
        uy = dy / length

        pos = 0.0
        drawing = True
        while pos < length:
            seg_start = max(pos, 0)
            seg_end = min(pos + (dash_len if drawing else gap_len), length)
            if drawing:
                sx = int(x1 + ux * seg_start)
                sy = int(y1 + uy * seg_start)
                ex = int(x1 + ux * seg_end)
                ey = int(y1 + uy * seg_end)
                pygame.draw.line(self.screen, color, (sx, sy), (ex, ey), max(1, width))
            pos += dash_len if drawing else gap_len
            drawing = not drawing
    
    def draw_triangle(self, center, color, size=5):
        """绘制三角形（绕飞点标记）"""
        points = [
            (center[0], center[1] - size),
            (center[0] - size * 0.866, center[1] + size * 0.5),
            (center[0] + size * 0.866, center[1] + size * 0.5)
        ]
        pygame.draw.polygon(self.screen, color, points)
        pygame.draw.polygon(self.screen, self.COLORS['BUILDING_STROKE'], points, 1)

    def draw_diamond(self, center, color, size=6):
        """绘制菱形（终点标记）"""
        points = [
            (center[0], center[1] - size),
            (center[0] + size, center[1]),
            (center[0], center[1] + size),
            (center[0] - size, center[1])
        ]
        pygame.draw.polygon(self.screen, color, points)
        pygame.draw.polygon(self.screen, self.COLORS['BUILDING_STROKE'], points, 1)
    
    def draw_drone(self, drone, drone_color):
        """绘制无人机 — 带外环和拖尾效果"""
        x, y = drone.get_position()
        screen_pos = self.world_to_screen(x, y)

        # 绘制无人机
        drone_size = max(8, int(6 * self.zoom))

        # 外发光环
        glow_size = drone_size + 4
        glow_surf = pygame.Surface((glow_size * 2, glow_size * 2), pygame.SRCALPHA)
        for r in range(glow_size, 0, -1):
            alpha = max(0, 40 - r * 5)
            pygame.draw.circle(glow_surf, (*drone_color, alpha), (glow_size, glow_size), r)
        self.screen.blit(glow_surf, (screen_pos[0] - glow_size, screen_pos[1] - glow_size))

        if drone.is_free:
            # 空闲状态：青色圆形带白色内圈
            idle_color = (42, 157, 143)
            pygame.draw.circle(self.screen, idle_color, screen_pos, drone_size + 2)
            pygame.draw.circle(self.screen, (255, 255, 255), screen_pos, drone_size)
            pygame.draw.circle(self.screen, idle_color, screen_pos, drone_size - 2)
        else:
            # 执行任务：对应颜色的圆形，带白色边框和内圈
            pygame.draw.circle(self.screen, drone_color, screen_pos, drone_size + 3)
            pygame.draw.circle(self.screen, (255, 255, 255), screen_pos, drone_size + 1)
            pygame.draw.circle(self.screen, drone_color, screen_pos, drone_size)
            # 内亮点
            pygame.draw.circle(self.screen, (255, 255, 255), screen_pos, max(2, drone_size // 3))

        # 绘制无人机ID（白色阴影 + 深色文字）
        id_text = self.small_font.render(drone.drone_id, True, (255, 255, 255))
        self.screen.blit(id_text, (screen_pos[0] + 11, screen_pos[1] - 7))
        id_text = self.small_font.render(drone.drone_id, True, self.COLORS['TEXT'])
        self.screen.blit(id_text, (screen_pos[0] + 10, screen_pos[1] - 8))
    
    def draw_legend(self):
        """绘制图例 — 白色卡片 + 阴影，左下角"""
        legend_items = [
            ("Drone (IDLE)", (42, 157, 143), 'circle_filled'),   # 实心圆
            ("Drone (BUSY)", (230, 57, 70), 'circle_hollow'),    # 空心圆
            ("Task Source", self.TASK_SOURCE_COLOR, 'square'),
            ("Task Dest", self.TASK_DEST_COLOR, 'diamond'),
            ("Waypoint", self.WAYPOINT_COLOR, 'triangle'),
        ]

        legend_x = 15
        legend_y = self.screen_size[1] - 160
        legend_w = 155
        item_height = 24
        bg_height = len(legend_items) * item_height + 16

        # 阴影
        shadow_rect = pygame.Rect(legend_x + 2, legend_y + 2, legend_w, bg_height)
        pygame.draw.rect(self.screen, (200, 200, 205), shadow_rect, border_radius=6)

        # 白色卡片
        card_rect = pygame.Rect(legend_x, legend_y, legend_w, bg_height)
        pygame.draw.rect(self.screen, (255, 255, 255), card_rect, border_radius=6)
        pygame.draw.rect(self.screen, self.COLORS['PANEL_BORDER'], card_rect, 1, border_radius=6)

        for i, (text, color, shape) in enumerate(legend_items):
            y = legend_y + 8 + i * item_height
            cx, cy = legend_x + 10, y + 7
            if shape == 'circle_filled':
                pygame.draw.circle(self.screen, color, (cx, cy), 6)
            elif shape == 'circle_hollow':
                pygame.draw.circle(self.screen, color, (cx, cy), 8)
                pygame.draw.circle(self.screen, (255, 255, 255), (cx, cy), 4)
                pygame.draw.circle(self.screen, color, (cx, cy), 2)
            elif shape == 'square':
                pygame.draw.rect(self.screen, color, (cx - 5, cy - 5, 10, 10))
                pygame.draw.rect(self.screen, (173, 181, 189), (cx - 5, cy - 5, 10, 10), 1)
            elif shape == 'diamond':
                self.draw_diamond((cx, cy), color, 5)
            elif shape == 'triangle':
                self.draw_triangle((cx, cy), color, 5)

            label = self.small_font.render(text, True, self.COLORS['TEXT'])
            self.screen.blit(label, (cx + 14, y))
    
    def render(self, drones, stats=None):
        running = self.handle_events()
        self.draw(drones, stats)

        # FPS calculation
        current_time = pygame.time.get_ticks()
        self.fps_counter += 1
        
        if current_time - self.fps_time > 1000:  # Update every second
            self.current_fps = self.fps_counter
            self.fps_counter = 0
            self.fps_time = current_time
            print(f"FPS: {self.current_fps}")
        
        self.clock.tick(60)
        
        return running


    def run(self):
        """主循环"""
        # clock = pygame.time.Clock()
        running = True
        
        while running:
            running = self.handle_events()
            self.draw()
            self.clock.tick(60)
        
        pygame.quit()

# 使用示例
if __name__ == "__main__":
    osm_file_path = "data/map/map.osm"
    
    try:
        pygame.init()
        viewer = OptimizedMapViewer(osm_file_path)
        viewer.run()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()