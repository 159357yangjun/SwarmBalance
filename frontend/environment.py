import numpy as np
import heapq
import time
import datetime
from shapely.geometry import Point, LineString
import math
from drone import Drone, BATTERY_CONSUMPTION_BASE, BATTERY_LOAD_PENALTY_FACTOR, HETERO_ENABLED, BATTERY_LOW_THRESHOLD
from charging_station import ChargingStation, DEFAULT_CHARGING_STATIONS, find_nearest_station
from config.config_loder import get_shared_config
# from test import OptimizedMapViewer
from tools.osm import load_map_data, get_building_location_by_name, get_global_bounds
from data_source import build_data_source
from task import WAREHOUSE_POS, Task
from seed_interface import apply_seed
from no_fly_zone import get_no_fly_zones, reset_no_fly_zones


CFG = get_shared_config()
ENV_CFG = CFG.get("environment", {})
DRONE_CFG = CFG.get("drone", {})
HETERO_CFG = CFG.get("heterogeneous", {})
VIS_CFG = CFG.get("visualization", {})
FLEET_MIX = HETERO_CFG.get("fleet_mix", {})
DEFAULT_EPISODE_MAX_STEPS = int(ENV_CFG.get("episode_max_steps", 1200))
DEFAULT_NUM_DRONES = int(ENV_CFG.get("num_drones", 3))
PRINT_ROUTE_DEBUG = bool(ENV_CFG.get("print_route_debug", False))
ALLOW_MULTI_TASK = bool(ENV_CFG.get("allow_multi_task", True))
MAX_OBS_TASKS = int(ENV_CFG.get("max_obs_tasks", 20))
MAX_MULTI_TASK_TOTAL_WEIGHT = float(ENV_CFG.get("multi_task_max_total_weight", DRONE_CFG.get("carrying_capacity", 5)))

# 机巢泊位动态优先级仲裁权重（创新点2：任务紧迫度 + 电量 + 等待时长）
NEST_CFG = CFG.get("nest", {})
NEST_ARB_W_BATTERY = float(NEST_CFG.get("arbitration_weight_battery", 1.0))
NEST_ARB_W_WAIT = float(NEST_CFG.get("arbitration_weight_wait", 0.1))
NEST_ARB_W_URGENCY = float(NEST_CFG.get("arbitration_weight_urgency", 0.0))
# 泊位仲裁策略："priority" = 动态优先级（电量紧迫+等待+任务）；"fifo" = 先到先服务基线
NEST_ARB_POLICY = str(NEST_CFG.get("arbitration_policy", "priority")).strip().lower()
# 等待时长归一化基准：一次换电时长（秒）。等待项按"几个换电周期"折算，避免秒级
# 等待在数值上碾压电量临界度、导致仲裁退化为纯 FIFO。
NEST_SWAP_REF = float(NEST_CFG.get("swap_time_seconds", 180.0))
# 任务优先级范围（用于把任务紧迫度归一化到 [0,1]，与电量临界度/等待时长同量纲）
TASK_CFG = CFG.get("task", {})
TASK_PRIORITY_MIN = int(TASK_CFG.get("priority_min", 1))
TASK_PRIORITY_MAX = int(TASK_CFG.get("priority_max", 3))

# 禁飞区（申请书「可灵活配置禁飞区等障碍物布局」）
NO_FLY_ZONES = get_no_fly_zones()

# 任务链 / 顺路接入（申请书「执行完前序任务后顺路接入新任务」）
CHAIN_CFG = CFG.get("task_chain", {})
CHAIN_ENABLED = bool(CHAIN_CFG.get("enabled", True))
CHAIN_MAX_TASKS = max(1, int(CHAIN_CFG.get("max_chain_tasks", 3)))
CHAIN_MAX_DETOUR_M = float(CHAIN_CFG.get("max_detour_m", 1500.0))
# 顺路接入的电量安全余量：追加后剩余电量不得低于容量的该比例
CHAIN_BATTERY_RESERVE = float(CHAIN_CFG.get("battery_reserve_ratio", 0.15))
CHAIN_REQUIRE_SAME_SOURCE = bool(CHAIN_CFG.get("require_same_source", False))


def _dist_m(a, b) -> float:
    """两点欧氏距离（米）。抽成模块级函数供 Environment 内部各口径复用。"""
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def build_fleet_drone_types(num_drones):
    """按 fleet_mix 配比生成机型序列，长度等于 num_drones。

    配比不足 1 时用默认同质机型补齐（保持向后兼容）。
    """
    if not HETERO_ENABLED or not FLEET_MIX:
        return [None] * num_drones

    seq = []
    for dtype, count in FLEET_MIX.items():
        seq.extend([dtype] * int(count))
    if len(seq) > num_drones:
        seq = seq[:num_drones]
    while len(seq) < num_drones:
        seq.append(None)
    return seq

class Environment:
    def __init__(self, osm_file_path, visualize=False, episode_max_steps=DEFAULT_EPISODE_MAX_STEPS, data_source=None):
        roads_by_type, buildings_with_height = load_map_data(osm_file_path)
        # 全量建筑与道路：供控制台渲染"真实城市"肌理（此前只暴露高度>20 的高楼）
        self.roads_by_type = roads_by_type
        self.all_buildings = buildings_with_height

        self.global_bounds = get_global_bounds(buildings_with_height)

        self.high_buildings = [b for b in buildings_with_height if b['height'] is not None and b['height'] > 20]
        # 性能：预计算高楼包围盒。is_path_clear 会被 A* 在每条路径规划中调用数千次，
        # 先用纯 Python 的 bbox 剔除，可免掉绝大多数昂贵的 GEOS 相交调用。
        # 这是等价优化：两条线段包围盒不重叠时，几何上不可能相交。
        self._high_buildings_bbox = [(b['geometry'].bounds, b['geometry']) for b in self.high_buildings]

        # 禁飞区：与建筑物并列的飞行硬约束（参与 is_path_clear / A* / 场景生成）
        self.no_fly = get_no_fly_zones()
        self.total_no_fly_detours = 0   # 因禁飞区触发绕飞的次数

        self.unassigned_tasks = []  # 保持向后兼容，通过 task_generator 访问
        self.episode_max_steps = int(episode_max_steps)
        # 数据源适配层：统一提供 机队/机巢/任务 三类数据（随机生成 / CSV / GeoJSON）
        self.data_source = data_source if data_source is not None else build_data_source()
        self.charging_stations = self._build_charging_stations()
        self.drones = self._build_drones()
        self.task_generator = self.data_source.build_task_source()

        # 机巢泊位竞争状态（创新点2）：有限泊位 + 动态优先级仲裁排队
        self._nest_waiting = {s.station_id: [] for s in self.charging_stations}
        self.total_swap_sessions = 0          # 换电总次数（机巢周转口径）
        self._berth_occupied_sum = 0          # 逐步累计占用泊位数（泊位利用率分子）
        self._berth_wait_time_sum = 0.0       # 累计排队等待时长
        self._berth_wait_count = 0            # 排队等待事件数
        self._berth_wait_max = 0.0            # 单次最长排队等待时长（反饥饿观测）
        self._berth_wait_urgency_sum = 0.0    # 紧迫性加权的排队等待累计（电量越空权重越高）
        self._berth_wait_task_urgency_sum = 0.0  # 任务紧迫度加权的排队等待累计（带紧急任务权重越高）
        self.arbitration_policy = NEST_ARB_POLICY  # "priority" / "fifo"
        # 泊位仲裁三因素权重（实例级，便于调参扫描时逐组合覆盖）
        self.arb_weight_battery = NEST_ARB_W_BATTERY
        self.arb_weight_wait = NEST_ARB_W_WAIT
        self.arb_weight_urgency = NEST_ARB_W_URGENCY
        
        # 初始化模拟时间
        self.current_time = 0
        
        # 跟踪已完成的任务，用于奖励计算
        self.completed_tasks = []
        
        # 跟踪无人机分配的任务：{drone_idx: {'task': task, 'start_time': time}}
        self.drone_assignments = {}
        
        # 跟踪每个无人机之前的空闲状态
        self._prev_free_status = {i: True for i in range(len(self.drones))}

        # 任务链状态：{drone_idx: 当前航线串联的任务数}，航线清空时归零
        self.drone_chain_len = {i: 0 for i in range(len(self.drones))}
        self.total_chain_insertions = 0   # 顺路接入次数（异源任务链追加）

        self.reward_step = float(ENV_CFG.get("reward_step", -0.1))
        self.reward_priority_1 = float(ENV_CFG.get("reward_priority_1", 100.0))
        self.reward_priority_2 = float(ENV_CFG.get("reward_priority_2", 80.0))
        self.reward_priority_3 = float(ENV_CFG.get("reward_priority_3", 50.0))
        self.penalty_late_rate = float(ENV_CFG.get("penalty_late_rate", -0.01))
        self.overdue_initial_penalty = float(ENV_CFG.get("overdue_initial_penalty", -10.0))
        self.overdue_step_penalty = float(ENV_CFG.get("overdue_step_penalty", -0.1))
        self.priority_delay_penalty_weights = {
            1: float(ENV_CFG.get("priority_delay_penalty_weight_1", 1.0)),
            2: float(ENV_CFG.get("priority_delay_penalty_weight_2", 1.5)),
            3: float(ENV_CFG.get("priority_delay_penalty_weight_3", 2.0)),
        }
        self._overdue_task_ids = set()
        self.generated_task_times = []
        # 运行中人工注入任务编号（自由仿真控制台使用）
        self._manual_task_counter = 0
        # 交互式控制台可暂停自动订单流，便于只观察人工注入任务与重调度。
        # 仅影响 TaskGenerator.step，不影响当前待调度池，也不修改持久配置。
        self.task_generation_paused = False

        # 统计指标（按回合统计）
        self.total_generated_tasks = 0
        self.total_completed_tasks = 0
        self.total_on_time_tasks = 0
        self.total_delay = 0.0
        self.total_generation_to_assignment_wait = 0.0
        self.total_assignment_to_load_wait = 0.0
        self.total_wait_time = 0.0
        self.total_delivery_time = 0.0
        self.total_generation_to_completion_time = 0.0
        self.max_delivery_time = 0.0
        self.max_generation_to_completion_time = 0.0
        self.priority_delay_totals = {1: 0.0, 2: 0.0, 3: 0.0}
        self.priority_delay_counts = {1: 0, 2: 0, 3: 0}
        
        # 耗电量统计
        self.total_energy_consumed = 0.0  # 总耗电量 (Wh)
        self.total_charging_energy = 0.0  # 总充电量 (Wh)
        self.total_charging_sessions = 0  # 总充电次数
        self.total_flight_distance = 0.0  # 总飞行距离（米）
        # 载运效率指标：空载里程 / 载货里程 / 机队忙步数（利用率与空载率的分母与分子）
        self.total_empty_distance = 0.0   # 空载（无货）飞行里程
        self.total_loaded_distance = 0.0  # 载货飞行里程
        self.drone_busy_steps = 0.0       # 逐机累计"忙"步数（在飞/换电/等泊位）

        # 初始生成一批任务
        new_tasks = self.task_generator.generate_initial_tasks(self.current_time)
        self.total_generated_tasks = len(new_tasks)
        self.generated_task_times = [t.get_generation_time() for t in new_tasks]
        print(f"Generated {len(new_tasks)} tasks:")
        # for task in new_tasks:
        #     print(f"  {task}")

        self.viewer = None
        if visualize:
            # 桌面可视化依赖 pygame；Web/批量仿真保持 headless，不应因未安装
            # pygame 而在模块 import 阶段失败。仅真正请求桌面窗口时再加载。
            vis_mode = str(VIS_CFG.get("mode", "3d")).lower()
            if vis_mode == "2d":
                from map_drawer import OptimizedMapViewer
                self.viewer = OptimizedMapViewer(osm_file_path)
            else:
                from map_drawer_3d import MapViewer3D
                self.viewer = MapViewer3D(osm_file_path)
            self.viewer.set_on_add_drone(self.add_drone)

        self._episode_seed = None

        # print(get_building_location_by_name( self.high_buildings, "衷和楼"))
        print(f"加载了 {len(self.high_buildings)} 个具有高度信息的建筑物")

    def _build_charging_stations(self):
        """从数据源构建机巢（换电站）列表；数据源为空时退回配置默认站。"""
        specs = self.data_source.load_nests()
        stations = [
            ChargingStation(s.nest_id, s.position[0], s.position[1],
                            s.charging_power, s.swap_time_seconds, s.berths)
            for s in specs
        ]
        return stations if stations else list(DEFAULT_CHARGING_STATIONS)

    def _build_drones(self):
        """从数据源构建异构机队；数据源无机型规格时退回历史 fleet_mix 默认。"""
        specs = self.data_source.load_drones()
        if specs:
            drones = [
                Drone(s.base_position[0], s.base_position[1],
                      drone_id=s.drone_id, drone_type=s.drone_type,
                      carrying_capacity=s.carrying_capacity)
                for s in specs
            ]
            self._fleet_types = [s.drone_type for s in specs]
        else:
            num = DEFAULT_NUM_DRONES
            self._fleet_types = build_fleet_drone_types(num)
            drones = [
                Drone(WAREHOUSE_POS[0], WAREHOUSE_POS[1], drone_id=f"drone_{i}",
                      drone_type=self._fleet_types[i])
                for i in range(num)
            ]
        for d in drones:
            d.known_stations = self.charging_stations
        return drones

    def get_global_bounds(self):
        return self.global_bounds

    def get_high_buildings(self):
        return self.high_buildings

    def add_drone(self):
        """向环境中添加一架新无人机（从仓库出发）"""
        new_idx = len(self.drones)
        # 追加新机时使用默认机型（无机型偏好），若配比序列包含该下标则沿用
        dtype = self._fleet_types[new_idx] if new_idx < len(self._fleet_types) else None
        new_drone = Drone(WAREHOUSE_POS[0], WAREHOUSE_POS[1],
                          drone_id=f"drone_{new_idx}", drone_type=dtype)
        new_drone.known_stations = self.charging_stations
        self.drones.append(new_drone)
        self._prev_free_status[new_idx] = True
        print(f"[Environment] 添加无人机: drone_{new_idx} (当前共 {len(self.drones)} 架)")

    def _print_task_completion(self, drone_id, task_id, delivery_time, expected_time,
                               delay, is_on_time, priority, weight):
        """打印任务完成信息"""
        status = "✓ 准时" if is_on_time else "✗ 延迟"
        print(f"\n{'='*70}")
        print(f"📦 任务完成: {task_id}")
        print(f"{'='*70}")
        print(f"  无人机: {drone_id}")
        print(f"  优先级: {priority}/3  |  货物重量: {weight}kg")
        print(f"  配送时长: {delivery_time:.1f} 时间单位")
        print(f"  预期时长: {expected_time:.1f} 时间单位")
        if not is_on_time:
            print(f"  延迟时间: {delay:.1f} 时间单位")
        print(f"  状态: {status}")
        print(f"{'='*70}")
    
    def _record_task_completion(self, drone_idx, assignment):
        """记录单个任务完成的统计数据"""
        completed_task = assignment['task']
        assigned_time = assignment.get('assigned_time', assignment.get('start_time', self.current_time))
        load_time = assignment.get('load_time')
        if load_time is None:
            load_time = assigned_time
        completion_time = self.current_time
        generation_time = completed_task.get_generation_time()
        if generation_time is None:
            generation_time = assigned_time

        generation_to_assignment_wait = max(0, assigned_time - generation_time)
        assignment_to_load_wait = max(0, load_time - assigned_time)
        delivery_time = max(0, completion_time - load_time)
        generation_to_completion_time = max(0, completion_time - generation_time)

        deadline = completed_task.get_deadline()
        if deadline is not None:
            delay = max(0, completion_time - deadline)
        else:
            delay = 0

        is_on_time = delay <= 0
        self.total_completed_tasks += 1
        self.total_delay += float(delay)
        self.total_generation_to_assignment_wait += float(generation_to_assignment_wait)
        self.total_assignment_to_load_wait += float(assignment_to_load_wait)
        self.total_wait_time += float(assignment_to_load_wait)
        self.total_delivery_time += float(delivery_time)
        self.total_generation_to_completion_time += float(generation_to_completion_time)
        self.max_delivery_time = max(self.max_delivery_time, float(delivery_time))
        self.max_generation_to_completion_time = max(
            self.max_generation_to_completion_time,
            float(generation_to_completion_time),
        )
        priority = int(completed_task.get_priority())
        if priority in self.priority_delay_totals:
            self.priority_delay_totals[priority] += float(delay)
            self.priority_delay_counts[priority] += 1
        if is_on_time:
            self.total_on_time_tasks += 1

        self.completed_tasks.append({
            'task': completed_task,
            'generation_time': generation_time,
            'assigned_time': assigned_time,
            'load_time': load_time,
            'start_time': load_time,
            'completion_time': completion_time,
            'generation_to_assignment_wait': generation_to_assignment_wait,
            'assignment_to_load_wait': assignment_to_load_wait,
            'wait_time': assignment_to_load_wait,
            'delivery_time': delivery_time,
            'generation_to_completion_time': generation_to_completion_time,
            'delay': delay
        })

        if PRINT_ROUTE_DEBUG:
            drone_id = self.drones[drone_idx].drone_id if drone_idx < len(self.drones) else f"drone_{drone_idx}"
            expected_time = deadline - load_time if deadline else 0
            self._print_task_completion(
                drone_id, completed_task.task_id, delivery_time,
                expected_time, delay, is_on_time,
                completed_task.get_priority(), completed_task.get_weight()
            )

    def _priority_delay_weight(self, priority):
        try:
            priority = int(priority)
        except (TypeError, ValueError):
            priority = 1
        return self.priority_delay_penalty_weights.get(priority, self.priority_delay_penalty_weights[1])

    # ==================== 机巢泊位竞争（创新点2） ====================

    def _station_by_id(self, station_id):
        for s in self.charging_stations:
            if str(s.station_id) == str(station_id):
                return s
        return None

    def _drone_index_by_id(self, drone_id):
        """按运行时 drone_id 找到无人机下标；同时接受整数下标。"""
        if isinstance(drone_id, int) and 0 <= drone_id < len(self.drones):
            return int(drone_id)
        target = str(drone_id)
        for i, drone in enumerate(self.drones):
            if str(getattr(drone, 'drone_id', i)) == target:
                return i
        raise ValueError(f"未找到无人机: {drone_id}")

    def set_drone_out_of_service(self, drone_id, out_of_service=True, reason='人工故障注入'):
        """运行中将无人机置为停飞/恢复，并在停飞时回收其未完成任务。

        该接口专供交互式仿真事故注入。为了保持现有任务模型简单且可复现，
        故障机上的未完成任务会**回滚到原任务起点**并重新进入待调度池；不会
        在空中创建新的交接点。这样可以直接观察当前调度算法的重新分配过程。
        """
        idx = self._drone_index_by_id(drone_id)
        drone = self.drones[idx]
        out_of_service = bool(out_of_service)

        if not out_of_service:
            if not getattr(drone, 'out_of_service', False):
                return {'drone_idx': idx, 'drone_id': str(drone.drone_id), 'requeued_task_ids': [], 'changed': False}
            drone.out_of_service = False
            drone.out_of_service_reason = None
            drone.is_charging = False
            drone.swap_remaining_steps = 0.0
            drone.charging_station_id = None
            drone.awaiting_berth = False
            drone.berth_station_id = None
            drone.awaiting_since = None
            drone._pending_release = False
            drone._suspended_route = []
            drone._manual_charge_requested = False
            drone.scheduled_position = []
            drone.executing_task_id = None
            drone.current_load = 0.0
            drone.is_free = True
            self._prev_free_status[idx] = True
            return {'drone_idx': idx, 'drone_id': str(drone.drone_id), 'requeued_task_ids': [], 'changed': True}

        if getattr(drone, 'out_of_service', False):
            return {'drone_idx': idx, 'drone_id': str(drone.drone_id), 'requeued_task_ids': [], 'changed': False}

        # 若正在占用换电泊位，故障注入时立即释放，避免机巢资源永久泄漏。
        if getattr(drone, 'is_charging', False):
            st = self._station_by_id(getattr(drone, 'charging_station_id', None))
            if st is not None:
                st.vacate()
        # 从所有等待队列移除。
        for q in self._nest_waiting.values():
            while idx in q:
                q.remove(idx)

        requeued = []
        assignments = self.drone_assignments.pop(idx, None)
        if assignments:
            items = assignments if isinstance(assignments, list) else [assignments]
            existing = {str(t.task_id) for t in self.task_generator.unassigned_tasks}
            for a in items:
                task = a.get('task') if isinstance(a, dict) else None
                if task is None:
                    continue
                tid = str(task.task_id)
                if tid not in existing:
                    task.update_status('pending')
                    self.task_generator.unassigned_tasks.append(task)
                    existing.add(tid)
                    requeued.append(tid)

        drone.scheduled_position = []
        drone._suspended_route = []
        drone._manual_charge_requested = False
        drone.current_load = 0.0
        drone.executing_task_id = None
        drone.is_charging = False
        drone.swap_remaining_steps = 0.0
        drone.charging_station_id = None
        drone.awaiting_berth = False
        drone.berth_station_id = None
        drone.awaiting_since = None
        drone._pending_release = False
        drone.is_free = False
        drone.out_of_service = True
        drone.out_of_service_reason = str(reason or '人工故障注入')
        self.drone_chain_len[idx] = 0
        self._prev_free_status[idx] = False
        return {
            'drone_idx': idx,
            'drone_id': str(drone.drone_id),
            'requeued_task_ids': requeued,
            'changed': True,
        }

    def set_station_closed(self, station_id, closed=True, reason='人工场景事件'):
        """运行中关闭/开放机巢。

        关闭采用“软关闭”：不再接收新请求；已经在换电的无人机允许完成。
        原等待队列和正在飞往该机巢的低电无人机会改道到最近的开放机巢。
        为避免场景无任何补能点造成死锁，默认不允许关闭最后一个开放机巢。
        """
        st = self._station_by_id(station_id)
        if st is None:
            raise ValueError(f"未找到机巢: {station_id}")
        closed = bool(closed)
        if closed == bool(getattr(st, 'closed', False)):
            return {'station_id': str(st.station_id), 'changed': False, 'rerouted_drone_ids': []}

        if closed:
            open_others = [x for x in self.charging_stations if x is not st and not getattr(x, 'closed', False)]
            if not open_others:
                raise ValueError('至少保留一个开放机巢，不能关闭最后一个可用机巢')
            st.closed = True
            st.closed_reason = str(reason or '人工场景事件')
            rerouted = []
            target_pos = st.get_position()

            # 先处理已经在该站排队的无人机。
            waiting = list(self._nest_waiting.get(st.station_id, []) or [])
            self._nest_waiting[st.station_id] = []
            for idx in waiting:
                drone = self.drones[idx]
                drone.awaiting_berth = False
                drone.berth_station_id = None
                drone.awaiting_since = None
                nearest = find_nearest_station(self.charging_stations, drone.get_position())
                if nearest is not None:
                    drone.scheduled_position = [nearest.get_position()]
                    drone.is_free = False
                    rerouted.append(str(drone.drone_id))

            # 再处理尚未抵达、但正以该站为补能目的地的无人机。
            for drone in self.drones:
                if getattr(drone, 'out_of_service', False) or getattr(drone, 'is_charging', False):
                    continue
                route = list(getattr(drone, 'scheduled_position', []) or [])
                if not route:
                    continue
                last = route[-1]
                last_pos = (float(last[0]), float(last[1]))
                headed_for_closed_nest = math.dist(last_pos, target_pos) < 1e-6
                charging_detour = bool(getattr(drone, '_suspended_route', [])) or (getattr(drone, 'executing_task_id', None) is None and not drone.is_free)
                if headed_for_closed_nest and charging_detour:
                    nearest = find_nearest_station(self.charging_stations, drone.get_position())
                    if nearest is not None:
                        drone.scheduled_position = [nearest.get_position()]
                        drone.is_free = False
                        if str(drone.drone_id) not in rerouted:
                            rerouted.append(str(drone.drone_id))
            return {'station_id': str(st.station_id), 'changed': True, 'rerouted_drone_ids': rerouted}

        st.closed = False
        st.closed_reason = None
        return {'station_id': str(st.station_id), 'changed': True, 'rerouted_drone_ids': []}

    def set_task_generation_paused(self, paused=True):
        """暂停/恢复**自动**任务流；人工注入任务始终允许。"""
        paused = bool(paused)
        changed = paused != bool(getattr(self, 'task_generation_paused', False))
        self.task_generation_paused = paused
        return {'paused': paused, 'changed': changed}

    def update_pending_task(self, task_id, *, priority=None, deadline_offset=None,
                            weight=None, category=None):
        """修改仍在待调度池中的任务属性，不影响已经执行中的任务。

        该能力主要用于交互式调度演示：例如把普通订单提升为紧急任务，
        下一步直接观察当前算法是否改变候选机与分配决策。
        """
        task = None
        for item in self.task_generator.unassigned_tasks:
            if str(item.task_id) == str(task_id):
                task = item
                break
        if task is None:
            raise ValueError(f"任务 {task_id} 不在待调度池中，只有待调度任务可以修改")

        changed = {}
        if priority is not None:
            p = max(TASK_PRIORITY_MIN, min(TASK_PRIORITY_MAX, int(priority)))
            if p != int(task.priority):
                changed['priority'] = [int(task.priority), p]
                task.priority = p
        if deadline_offset is not None:
            off = float(deadline_offset)
            if off <= 0:
                raise ValueError("距截止时间必须大于 0 秒")
            old = float(task.deadline) if task.deadline is not None else None
            task.deadline = float(self.current_time) + off
            changed['deadline'] = [old, float(task.deadline)]
        if weight is not None:
            w = float(weight)
            if w <= 0:
                raise ValueError("任务重量必须大于 0")
            max_capacity = max((float(getattr(d, 'carrying_capacity', 0.0)) for d in self.drones), default=0.0)
            if max_capacity > 0 and w > max_capacity + 1e-9:
                raise ValueError(f"任务重量 {w:g}kg 超过当前机队最大载重 {max_capacity:g}kg")
            if abs(w - float(task.weight)) > 1e-9:
                changed['weight'] = [float(task.weight), w]
                task.weight = w
        if category is not None:
            c = str(category or 'normal').strip().lower()
            if c not in {'normal', 'urgent', 'emergency', 'bulk'}:
                raise ValueError(f"未知任务类别: {category}")
            if c != str(task.category):
                changed['category'] = [str(task.category), c]
                task.category = c
        return {'task_id': str(task.task_id), 'changed': changed}

    def request_drone_charge(self, drone_id, station_id=None):
        """人工请求无人机前往指定/最近开放机巢换电。

        正在执行任务时会挂起剩余航线，换电完成后恢复；空闲机则单纯前往机巢
        换电。全过程仍走有限泊位与动态优先级仲裁，不绕过资源约束。
        """
        idx = self._drone_index_by_id(drone_id)
        drone = self.drones[idx]
        if getattr(drone, 'out_of_service', False):
            raise ValueError(f"{drone.drone_id} 当前故障停飞，不能调往机巢")
        if getattr(drone, 'is_charging', False):
            return {'drone_id': str(drone.drone_id), 'station_id': str(drone.charging_station_id), 'changed': False, 'reason': 'already_charging'}
        if getattr(drone, 'awaiting_berth', False):
            return {'drone_id': str(drone.drone_id), 'station_id': str(drone.berth_station_id), 'changed': False, 'reason': 'already_waiting'}

        if station_id is None:
            st = find_nearest_station(self.charging_stations, drone.get_position())
        else:
            st = self._station_by_id(station_id)
            if st is not None and getattr(st, 'closed', False):
                raise ValueError(f"机巢 {station_id} 当前关闭")
        if st is None:
            raise ValueError("当前没有可用机巢")

        route = list(getattr(drone, 'scheduled_position', []) or [])
        if route and not getattr(drone, '_suspended_route', []):
            drone._suspended_route = route
        drone._manual_charge_requested = True
        target = st.get_position()
        if math.dist(drone.get_position(), target) < 1e-6:
            drone.scheduled_position = []
            drone.awaiting_berth = True
            drone.berth_station_id = st.station_id
            drone.awaiting_since = float(self.current_time)
            drone.is_free = False
        else:
            drone.scheduled_position = [target]
            drone.is_free = False
        self._prev_free_status[idx] = False
        return {
            'drone_id': str(drone.drone_id),
            'station_id': str(st.station_id),
            'changed': True,
            'resume_tasks_after_charge': bool(getattr(drone, '_suspended_route', [])),
        }

    def _battery_urgency(self, drone):
        """电量临界度：在低电阈值带宽内归一化（0=刚到低电阈值，1=电量耗尽）。

        相比「1 - 电量百分比」的全局紧迫度，此口径把"5% vs 19%"这类同为低电、
        但实际风险差异很大的情形拉开差距，让仲裁能真正分辨最该先换电的那一架。
        """
        level = drone.get_battery_level()
        return max(0.0, min(1.0, (BATTERY_LOW_THRESHOLD - level) / BATTERY_LOW_THRESHOLD))

    def _task_urgency(self, task):
        """任务紧迫度归一化到 [0,1]：最低优先级=0，最高优先级=1。

        与电量临界度（低电带宽内归一化）、等待时长（按换电周期折算）保持同一量纲，
        使三重因素在仲裁得分中可比、可调。
        """
        p = float(task.get_priority())
        denom = max(1, TASK_PRIORITY_MAX - TASK_PRIORITY_MIN)
        return max(0.0, min(1.0, (p - TASK_PRIORITY_MIN) / denom))

    def _drone_task_urgency(self, drone_idx):
        """该机已分配任务链中最高任务紧迫度（归一化到 [0,1]，无任务=0）。"""
        urgency = 0.0
        assigned = self.drone_assignments.get(drone_idx)
        if assigned:
            items = assigned if isinstance(assigned, list) else [assigned]
            for a in items:
                t = a.get('task') if isinstance(a, dict) else None
                if t is not None:
                    urgency = max(urgency, self._task_urgency(t))
        return urgency

    def _drone_berth_score(self, drone_idx):
        """泊位仲裁优先级（得分越高越先获得空余泊位）。

        三重因素：
          - 电量临界度：电量越空越需尽快换电恢复接单能力（低电带宽内归一化）；
          - 等待时长：等待越久越优先（按"换电周期数"折算，反饥饿但不过度压制临界度）；
          - 任务紧迫度：该机已分配任务链中最高优先级（归一化到 [0,1]）。
        带待办任务的无人机经"预判式换电"挂起航线进入泊位队列时，其任务优先级
        会被计入第三因素，使紧急任务（高 priority）在机巢竞争中获得加权。
        """
        drone = self.drones[drone_idx]
        battery_urgency = self._battery_urgency(drone)
        wait_time = 0.0
        if drone.awaiting_since is not None:
            wait_time = max(0.0, self.current_time - drone.awaiting_since)
        wait_norm = wait_time / NEST_SWAP_REF
        urgency = self._drone_task_urgency(drone_idx)
        return (self.arb_weight_battery * battery_urgency
                + self.arb_weight_wait * wait_norm
                + self.arb_weight_urgency * urgency)

    def _manage_berths(self):
        """机巢泊位生命周期管理：释放泊位 + 动态优先级仲裁移交。

        每个机巢有有限泊位，一架无人机降落-换电-起飞占用一个泊位；泊位满时，
        后续无人机在该机巢排队，由本方法按其紧迫度（电量/等待/任务）实时仲裁
        将空余泊位交给最优先的等待者。
        """
        # 1) 释放泊位：换电完成的无人机交还泊位
        for idx, drone in enumerate(self.drones):
            if getattr(drone, '_pending_release', False):
                st = self._station_by_id(getattr(drone, 'charging_station_id', None))
                if st is not None:
                    st.vacate()
                drone._pending_release = False
                drone.charging_station_id = None
            # 2) 泊位请求登记：已抵达机巢、尚未换电的无人机进入对应机巢等待队列
            if getattr(drone, 'awaiting_berth', False):
                sid = getattr(drone, 'berth_station_id', None)
                if sid is not None:
                    if drone.awaiting_since is None:
                        drone.awaiting_since = self.current_time
                    q = self._nest_waiting.setdefault(sid, [])
                    if idx not in q:
                        q.append(idx)
        # 3) 动态优先级仲裁移交：有空余泊位时，把等待队列中优先级最高者接入换电
        for st in self.charging_stations:
            q = self._nest_waiting.get(st.station_id, [])
            while st.has_berth() and q:
                if self.arbitration_policy == "fifo":
                    best = min(q, key=lambda i: (
                        self.drones[i].awaiting_since
                        if self.drones[i].awaiting_since is not None else float("inf")))
                else:
                    best = max(q, key=self._drone_berth_score)
                q.remove(best)
                drone = self.drones[best]
                wait_time = 0.0
                if drone.awaiting_since is not None:
                    wait_time = max(0.0, self.current_time - drone.awaiting_since)
                if wait_time > 0:
                    self._berth_wait_time_sum += wait_time
                    self._berth_wait_count += 1
                    self._berth_wait_max = max(self._berth_wait_max, wait_time)
                    self._berth_wait_urgency_sum += self._battery_urgency(drone) * wait_time
                    self._berth_wait_task_urgency_sum += self._drone_task_urgency(best) * wait_time
                st.occupy()
                drone.awaiting_berth = False
                drone.berth_station_id = None
                drone.awaiting_since = None
                drone.start_charging(st.station_id, swap_time_seconds=st.swap_time_seconds)
                self.total_swap_sessions += 1
        # 4) 累计占用泊位数（泊位利用率分子）
        self._berth_occupied_sum += sum(st.occupied for st in self.charging_stations)

    def _berth_metrics(self):
        """机巢泊位 / 周转指标（创新点2 + 缺口3）。

        - berth_utilization_rate : 泊位时间利用率（0~1），累计占用泊位-步 / 总可用泊位-步；
        - nest_turnover_rate     : 机巢周转率，平均每个泊位完成的换电次数（换电总次数/泊位总数）；
        - avg_berth_wait_time    : 平均泊位排队等待时长（秒）。
        """
        total_berths = sum(max(1, int(s.berths)) for s in self.charging_stations)
        elapsed = max(1, int(self.current_time))
        berth_utilization = self._berth_occupied_sum / (total_berths * elapsed)
        nest_turnover = (self.total_swap_sessions / total_berths) if total_berths else 0.0
        avg_berth_wait = (
            self._berth_wait_time_sum / self._berth_wait_count
            if self._berth_wait_count else 0.0
        )
        return {
            'total_berths': total_berths,
            'total_swap_sessions': int(self.total_swap_sessions),
            'berth_utilization_rate': berth_utilization,
            'nest_turnover_rate': nest_turnover,
            'avg_berth_wait_time': avg_berth_wait,
            'max_berth_wait_time': self._berth_wait_max,
            'avg_urgency_weighted_wait': (
                self._berth_wait_urgency_sum / self._berth_wait_count
                if self._berth_wait_count else 0.0
            ),
            'avg_task_urgency_weighted_wait': (
                self._berth_wait_task_urgency_sum / self._berth_wait_count
                if self._berth_wait_count else 0.0
            ),
            'berth_wait_count': int(self._berth_wait_count),
            'berth_queue_length': sum(len(q) for q in self._nest_waiting.values()),
        }

    def get_statistics(self):
        """获取当前统计指标"""
        completion_rate = 0.0
        if self.total_generated_tasks > 0:
            completion_rate = self.total_completed_tasks / self.total_generated_tasks

        berth = self._berth_metrics()

        avg_generation_time = 0.0
        if len(self.generated_task_times) >= 2:
            diffs = [
                b - a
                for a, b in zip(self.generated_task_times, self.generated_task_times[1:])
                if b >= a
            ]
            if diffs:
                avg_generation_time = sum(diffs) / len(diffs)

        # 机队效率指标（与完成任务数无关，两种返回分支都要有）
        denom_steps = float(max(1, self.current_time) * max(1, len(self.drones)))
        fleet = {
            'avg_drone_utilization': self.drone_busy_steps / denom_steps,
            'empty_load_ratio': (
                self.total_empty_distance / self.total_flight_distance
                if self.total_flight_distance > 0 else 0.0
            ),
            'total_flight_distance': self.total_flight_distance,
            'total_empty_distance': self.total_empty_distance,
            'total_loaded_distance': self.total_loaded_distance,
            'chain_insertions': float(self.total_chain_insertions),
            'no_fly_detours': float(self.total_no_fly_detours),
        }

        if self.total_completed_tasks == 0:
            return {
                'completion_rate': completion_rate,
                'total_completed': 0,
                'total_generated': self.total_generated_tasks,
                'on_time_rate': 0.0,
                'avg_delay': 0.0,
                'timeout_rate': 0.0,
                'avg_generation_to_assignment_wait': 0.0,
                'avg_assignment_to_load_wait': 0.0,
                'avg_wait_time_to_load': 0.0,
                'avg_load_to_delivery_time': 0.0,
                'avg_delivery_time': 0.0,
                'avg_generation_to_completion_time': 0.0,
                'avg_steps_per_order': 0.0,
                'avg_generation_time': avg_generation_time,
                'max_delivery_time': 0.0,
                'max_generation_to_completion_time': 0.0,
                'avg_delay_priority_1': 0.0,
                'avg_delay_priority_2': 0.0,
                'avg_delay_priority_3': 0.0,
                'total_wait_time': self.total_wait_time,
                'total_generation_to_completion_time': self.total_generation_to_completion_time,
                'total_energy_consumed': self.total_energy_consumed,
                'avg_energy_per_task': 0.0,
                'avg_energy_per_distance': 0.0,
                **berth,
                **fleet,
            }
        
        avg_energy_per_task = self.total_energy_consumed / self.total_completed_tasks
        
        avg_steps_per_order = self.total_delivery_time / self.total_completed_tasks
        avg_generation_to_assignment_wait = self.total_generation_to_assignment_wait / self.total_completed_tasks
        avg_assignment_to_load_wait = self.total_assignment_to_load_wait / self.total_completed_tasks
        avg_wait_time_to_load = avg_assignment_to_load_wait
        avg_generation_to_completion_time = self.total_generation_to_completion_time / self.total_completed_tasks
        priority_avg_delays = {}
        for priority in (1, 2, 3):
            count = self.priority_delay_counts.get(priority, 0)
            priority_avg_delays[priority] = (
                self.priority_delay_totals.get(priority, 0.0) / count
                if count > 0 else 0.0
            )

        return {
            'completion_rate': completion_rate,
            'total_completed': self.total_completed_tasks,
            'total_generated': self.total_generated_tasks,
            'on_time_rate': self.total_on_time_tasks / self.total_completed_tasks,
            'timeout_rate': 1.0 - (self.total_on_time_tasks / self.total_completed_tasks),
            'avg_delay': self.total_delay / self.total_completed_tasks,
            'avg_generation_to_assignment_wait': avg_generation_to_assignment_wait,
            'avg_assignment_to_load_wait': avg_assignment_to_load_wait,
            'avg_wait_time_to_load': avg_wait_time_to_load,
            'avg_load_to_delivery_time': self.total_delivery_time / self.total_completed_tasks,
            'avg_delivery_time': self.total_delivery_time / self.total_completed_tasks,
            'avg_generation_to_completion_time': avg_generation_to_completion_time,
            'avg_steps_per_order': avg_steps_per_order,
            'avg_generation_time': avg_generation_time,
            'max_delivery_time': self.max_delivery_time,
            'max_generation_to_completion_time': self.max_generation_to_completion_time,
            'avg_delay_priority_1': priority_avg_delays[1],
            'avg_delay_priority_2': priority_avg_delays[2],
            'avg_delay_priority_3': priority_avg_delays[3],
            'total_wait_time': self.total_wait_time,
            'total_generation_to_completion_time': self.total_generation_to_completion_time,
            'total_energy_consumed': self.total_energy_consumed,
            'avg_energy_per_task': avg_energy_per_task,
            **berth,
            **fleet,
        }
    
    def print_statistics(self):
        """打印累计统计信息"""
        stats = self.get_statistics()
        print(f"\n{'='*70}")
        print(f"📊 累计统计")
        print(f"{'='*70}")
        print(f"  完成率: {stats['completion_rate']:.2%}")
        print(f"  完成任务数: {stats['total_completed']}")
        print(f"  准时率: {stats['on_time_rate']:.2%}")
        print(f"  平均延迟: {stats['avg_delay']:.2f} 时间单位")
        print(f"  平均装载等待时间: {stats['avg_wait_time_to_load']:.2f} 时间单位")
        print(f"  平均配送时长: {stats['avg_delivery_time']:.2f} 时间单位")
        print(f"  平均生成到完成时长: {stats['avg_generation_to_completion_time']:.2f} 时间单位")
        print(f"  平均生成间隔: {stats['avg_generation_time']:.2f} 时间单位")
        print(f"  总耗电量: {stats['total_energy_consumed']:.2f} Wh")
        if stats['total_completed'] > 0:
            print(f"  平均每任务耗电: {stats['avg_energy_per_task']:.2f} Wh")
        print(f"  机巢泊位: 总数={stats['total_berths']} 换电次数={stats['total_swap_sessions']}")
        print(f"  泊位利用率: {stats['berth_utilization_rate']:.2%}  "
              f"机巢周转率(每泊位换电次数)={stats['nest_turnover_rate']:.2f}")
        print(f"  平均泊位排队等待: {stats['avg_berth_wait_time']:.2f} 秒 "
              f"(排队事件 {stats['berth_wait_count']} 次)")
        print(f"{'='*70}\n")

    def step(self, actions):
        # actions 格式: {drone_index: [task_id_list]}
        for drone_idx, task_ids in actions.items():
            if drone_idx < len(self.drones):
                drone = self.drones[drone_idx]
                if getattr(drone, 'out_of_service', False):
                    continue

                # 判断无人机是否正在飞往某个取货点（尚未抵达 source 航点）
                pending_source = None
                has_pending_task = False
                if not drone.is_free:
                    for wp in drone.scheduled_position:
                        if len(wp) >= 3 and wp[2] == 'source' and pending_source is None:
                            pending_source = (wp[0], wp[1])
                        if len(wp) >= 3 and wp[2] in ('source', 'dest'):
                            has_pending_task = True

                # 航线清空 → 任务链归零（新一轮从 1 开始计）
                if not drone.scheduled_position:
                    self.drone_chain_len[drone_idx] = 0

                for task_id in task_ids:
                    if task_id is not None:
                        # 找到对应的任务
                        task_to_assign = None
                        for task in self.task_generator.unassigned_tasks:
                            if task.task_id == task_id:
                                task_to_assign = task
                                break

                        if task_to_assign is not None:
                            planned_total_weight = float(drone.current_load) + float(task_to_assign.get_weight())
                            if planned_total_weight > MAX_MULTI_TASK_TOTAL_WEIGHT or planned_total_weight > float(drone.carrying_capacity):
                                continue

                            same_source = (
                                ALLOW_MULTI_TASK
                                and pending_source is not None
                                and task_to_assign.get_source() == pending_source
                            )

                            # 顺路接入：在途机在绕行阈值内追加"异源"任务，形成任务链
                            # （申请书「执行完前序任务后顺路接入新任务」）
                            chainable = (
                                CHAIN_ENABLED
                                and not same_source
                                and has_pending_task
                                and self.drone_chain_len.get(drone_idx, 0) < CHAIN_MAX_TASKS
                                and self._detour_acceptable(drone, task_to_assign)
                            )

                            if chainable:
                                self._append_task_to_chain(drone_idx, drone, task_to_assign)
                                pending_source = task_to_assign.get_source()
                                self.total_chain_insertions += 1
                            elif same_source:
                                # 同源追加：从当前路线最后一个航点规划到新目的地
                                last_wp = drone.scheduled_position[-1]
                                last_pos = (last_wp[0], last_wp[1])
                                new_route = self.plan_route_around_buildings(
                                    last_pos, task_to_assign.get_destination()
                                )
                                typed_route = []
                                for j, pt in enumerate(new_route):
                                    tag = 'dest' if j == len(new_route) - 1 else 'waypoint'
                                    typed_route.append((pt[0], pt[1], tag))
                                drone.append_route(typed_route)

                                # 追加到分配记录（兼容旧格式）
                                if drone_idx not in self.drone_assignments:
                                    self.drone_assignments[drone_idx] = []
                                elif isinstance(self.drone_assignments[drone_idx], dict):
                                    self.drone_assignments[drone_idx] = [
                                        self.drone_assignments[drone_idx]
                                    ]
                                drone.add_load(task_to_assign.get_weight())
                                self.drone_assignments[drone_idx].append({
                                    'task': task_to_assign,
                                    'assigned_time': self.current_time,
                                    'start_time': self.current_time,
                                    'load_time': None,
                                })
                                self.drone_chain_len[drone_idx] = self.drone_chain_len.get(drone_idx, 0) + 1
                            else:
                                # 新任务：完整规划路线
                                route = self.plan_route_for_tasks(drone, [task_to_assign])
                                drone.schedule_route(route, task_to_assign.task_id)
                                drone.add_load(task_to_assign.get_weight())
                                self.drone_assignments[drone_idx] = [{
                                    'task': task_to_assign,
                                    'assigned_time': self.current_time,
                                    'start_time': self.current_time,
                                    'load_time': None,
                                }]
                                self.drone_chain_len[drone_idx] = 1
                                pending_source = task_to_assign.get_source()

                            # 从未分配任务中移除
                            self.task_generator.unassigned_tasks.remove(task_to_assign)
                            # 更新任务状态
                            task_to_assign.update_status("assigned")

        # 每次调用 update 时，时间加一
        self.current_time += 1

        # 根据模式生成新任务；交互式控制台可临时暂停自动订单流。
        new_tasks = [] if getattr(self, 'task_generation_paused', False) else self.task_generator.step(self.current_time)
        if new_tasks:
            self.total_generated_tasks += len(new_tasks)
            self.generated_task_times.extend([t.get_generation_time() for t in new_tasks])

        # 记录更新前的电量状态和航点，用于统计耗电量和检测任务完成
        prev_batteries = [drone.current_battery for drone in self.drones]
        prev_scheduled = [list(drone.scheduled_position) for drone in self.drones]
        prev_positions = [(drone.x, drone.y) for drone in self.drones]

        for drone in self.drones:
            drone.update()

        # 统计耗电量和充电量
        for i, drone in enumerate(self.drones):
            battery_change = prev_batteries[i] - drone.current_battery

            if battery_change > 0:
                # 消耗了电量
                self.total_energy_consumed += battery_change

        # 里程与机队利用率：按"本步实际位移"统计，并区分空载 / 载货
        for i, drone in enumerate(self.drones):
            # 里程口径：按本步实际位移统计，并区分空载 / 载货
            moved = math.dist(prev_positions[i], (drone.x, drone.y))
            if moved > 0:
                self.total_flight_distance += moved
                if self._is_carrying(drone):
                    self.total_loaded_distance += moved
                else:
                    self.total_empty_distance += moved

            # 利用率口径："忙" = 在飞（有航线）/ 换电中 / 等泊位；与空闲相对
            if (not getattr(drone, 'out_of_service', False)) and (drone.scheduled_position or drone.is_charging or drone.awaiting_berth):
                self.drone_busy_steps += 1

        # 检测任务完成：
        # 1) 'dest' 航点被弹出 → 对应任务完成（支持一机多任务）
        # 2) is_free 转换兜底（充电自动航线等无 dest 航点的场景）
        for i, drone in enumerate(self.drones):
            # 预判式换电改道：scheduled_position 被整体挂起（非逐个航点弹出），
            # 本轮跳过航点弹出/空闲兜底检测，避免把"改道去换电"误判为任务完成。
            if getattr(drone, '_suspended_route', None):
                continue

            prev = prev_scheduled[i]
            curr = drone.scheduled_position

            # 航点弹出检测
            if len(prev) > len(curr) and len(prev) > 0:
                popped = prev[0]
                if len(popped) >= 3 and popped[2] == 'source':
                    source_pos = (popped[0], popped[1])
                    if i in self.drone_assignments:
                        assignments = self.drone_assignments[i]
                        if isinstance(assignments, dict):
                            assignments = [assignments]
                        for assignment in assignments:
                            if (
                                assignment.get('load_time') is None
                                and assignment['task'].get_source() == source_pos
                            ):
                                assignment['load_time'] = self.current_time
                if len(popped) >= 3 and popped[2] == 'dest':
                    dest_pos = (popped[0], popped[1])
                    if i in self.drone_assignments:
                        assignments = self.drone_assignments[i]
                        if isinstance(assignments, list):
                            for assignment in list(assignments):
                                if assignment['task'].get_destination() == dest_pos:
                                    self._record_task_completion(i, assignment)
                                    # 送达即卸货：此前 current_load 只在整条航线跑完时
                                    # 才清零，导致在途机永远"满载"、任务链被载重检查锁死。
                                    drone.current_load = max(
                                        0.0,
                                        float(drone.current_load)
                                        - float(assignment['task'].get_weight()))
                                    self.drone_chain_len[i] = max(
                                        0, int(self.drone_chain_len.get(i, 0)) - 1)
                                    assignments.remove(assignment)
                                    break
                        elif isinstance(assignments, dict):
                            if assignments['task'].get_destination() == dest_pos:
                                self._record_task_completion(i, assignments)
                                drone.current_load = max(
                                    0.0,
                                    float(drone.current_load)
                                    - float(assignments['task'].get_weight()))
                                self.drone_chain_len[i] = max(
                                    0, int(self.drone_chain_len.get(i, 0)) - 1)
                                del self.drone_assignments[i]

            # is_free 转换兜底：无人机变为空闲时清理剩余分配记录
            if not self._prev_free_status.get(i, True) and drone.is_free:
                if i in self.drone_assignments:
                    assignments = self.drone_assignments[i]
                    if isinstance(assignments, list):
                        for assignment in list(assignments):
                            self._record_task_completion(i, assignment)
                            assignments.remove(assignment)
                        if not assignments:
                            del self.drone_assignments[i]
                    elif isinstance(assignments, dict):
                        self._record_task_completion(i, assignments)
                        del self.drone_assignments[i]

        # 机巢泊位生命周期管理：释放泊位 + 动态优先级仲裁（创新点2）
        self._manage_berths()

        # 更新每个无人机之前的空闲状态
        self._prev_free_status = {i: drone.is_free for i, drone in enumerate(self.drones)}

        stats = self.get_statistics()

        running = True
        if self.viewer:
            running = self.viewer.render(self.drones, stats)

        done_by_horizon = self.current_time >= self.episode_max_steps
        done_by_exhaustion = (
            self.task_generator.is_exhausted
            and len(self.task_generator.unassigned_tasks) == 0
            and all(drone.is_free or getattr(drone, 'out_of_service', False) for drone in self.drones)
        )
        done = bool(done_by_horizon or done_by_exhaustion or (not running))
        info = {
            "episode_limit": bool(done_by_horizon),
            "episode_step": int(self.current_time),
            "completion_rate": float(stats["completion_rate"]),
            "total_completed": int(stats.get("total_completed", 0)),
            "total_generated": int(stats.get("total_generated", self.total_generated_tasks)),
            "on_time_rate": float(stats["on_time_rate"]),
            "timeout_rate": float(stats.get("timeout_rate", 0.0)),
            "avg_delay": float(stats["avg_delay"]),
            "avg_generation_to_assignment_wait": float(stats.get("avg_generation_to_assignment_wait", 0.0)),
            "avg_assignment_to_load_wait": float(stats.get("avg_assignment_to_load_wait", 0.0)),
            "avg_wait_time_to_load": float(stats.get("avg_wait_time_to_load", 0.0)),
            "avg_load_to_delivery_time": float(stats.get("avg_load_to_delivery_time", 0.0)),
            "avg_delivery_time": float(stats.get("avg_delivery_time", 0.0)),
            "avg_generation_to_completion_time": float(stats.get("avg_generation_to_completion_time", 0.0)),
            "avg_generation_time": float(stats.get("avg_generation_time", 0.0)),
            "avg_steps_per_order": float(stats.get("avg_steps_per_order", 0.0)),
            "max_delivery_time": float(stats.get("max_delivery_time", 0.0)),
            "max_generation_to_completion_time": float(stats.get("max_generation_to_completion_time", 0.0)),
            "avg_delay_priority_1": float(stats.get("avg_delay_priority_1", 0.0)),
            "avg_delay_priority_2": float(stats.get("avg_delay_priority_2", 0.0)),
            "avg_delay_priority_3": float(stats.get("avg_delay_priority_3", 0.0)),
            "total_energy_consumed": float(stats.get("total_energy_consumed", 0.0)),
        }

        return self._obs(), self._reward(), done, info
    
    # ==================== 运行中人工任务注入（交互式仿真） ====================

    def inject_task(self, *, source=None, destination=None, weight=1.0,
                    volume=0.0, priority=3, deadline_offset=None,
                    category="normal", task_id=None):
        """在**当前仿真时刻**向待调度池插入一条任务。

        这是 Web 控制台“运行中新增任务”的底层入口。它不会重置环境，也不会
        修改 simulation.json；下一个调度步会在当前无人机/机巢状态上处理该任务，
        因而可以直观看到滚动时域重调度与任务链插入效果。

        source / destination 为空时，从当前任务生成器的合法候选点中抽样。
        deadline_offset 使用相对当前仿真时刻的秒数；为空时沿用任务生成器 SLA 口径。
        """
        weight = float(weight)
        volume = float(volume)
        priority = int(priority)
        if weight <= 0:
            raise ValueError("任务重量必须大于 0")
        if volume < 0:
            raise ValueError("任务体积不能为负数")

        max_capacity = max(
            (float(getattr(d, 'carrying_capacity', 0.0)) for d in self.drones),
            default=0.0,
        )
        if max_capacity > 0 and weight > max_capacity + 1e-9:
            raise ValueError(
                f"任务重量 {weight:g}kg 超过当前机队最大载重 {max_capacity:g}kg，"
                "会形成不可完成任务"
            )

        # 坐标缺省时复用任务生成器的场景/热点/禁飞区规则，保证注入点可飞。
        if source is None or destination is None:
            source, destination = self.task_generator._generate_source_destination(self.current_time)
        source = (float(source[0]), float(source[1]))
        destination = (float(destination[0]), float(destination[1]))

        if math.dist(source, destination) < 1e-6:
            raise ValueError("任务起点和终点不能相同")
        if self.no_fly and (self.no_fly.contains(*source) or self.no_fly.contains(*destination)):
            raise ValueError("任务起点或终点位于禁飞区内，请重新选择")
        if self.global_bounds:
            minx, miny, maxx, maxy = self.global_bounds
            for label, pos in (("起点", source), ("终点", destination)):
                if not (minx <= pos[0] <= maxx and miny <= pos[1] <= maxy):
                    raise ValueError(f"{label}超出当前地图边界")

        priority = max(TASK_PRIORITY_MIN, min(TASK_PRIORITY_MAX, priority))
        category = str(category or "normal").strip().lower()
        if category not in {"normal", "urgent", "emergency", "bulk"}:
            category = "normal"

        distance = math.dist(source, destination)
        if deadline_offset is None:
            # 与自动任务使用同一 SLA 公式；紧急任务更紧。
            deadline_offset = self.task_generator._sla_seconds(distance, weight)
            if category in {"urgent", "emergency"} or priority >= TASK_PRIORITY_MAX:
                deadline_offset = max(1.0, float(deadline_offset) * 0.5)
        deadline_offset = float(deadline_offset)
        if deadline_offset <= 0:
            raise ValueError("截止时间必须晚于当前仿真时刻")

        self._manual_task_counter += 1
        tid = str(task_id or f"manual_{self._manual_task_counter}")
        existing = {str(t.task_id) for t in self.task_generator.unassigned_tasks}
        for assignments in self.drone_assignments.values():
            items = assignments if isinstance(assignments, list) else [assignments]
            for a in items:
                t = a.get('task') if isinstance(a, dict) else None
                if t is not None:
                    existing.add(str(t.task_id))
        if tid in existing:
            tid = f"manual_{self._manual_task_counter}_{int(self.current_time)}"

        task = Task(
            task_id=tid,
            weight=weight,
            source=source,
            destination=destination,
            deadline=float(self.current_time) + deadline_offset,
            priority=priority,
            generation_time=float(self.current_time),
            volume=volume,
            category=category,
        )
        self.task_generator.unassigned_tasks.append(task)
        self.total_generated_tasks += 1
        self.generated_task_times.append(float(self.current_time))
        return task

    def set_seed(self, seed):
        """Set the random seed for the next episode.

        Seed range: 0 <= seed <= 2**32 - 1. None disables deterministic seeding.
        """
        self._episode_seed = apply_seed(seed)
        self.task_generator.set_seed(seed)

    def reset(self, seed=None):
        if seed is not None:
            self.set_seed(seed)
        elif self._episode_seed is not None:
            apply_seed(self._episode_seed)

        self.unassigned_tasks = []
        self.charging_stations = self._build_charging_stations()
        self.drones = self._build_drones()
        self.current_time = 0
        self.completed_tasks = []
        self.drone_assignments = {}
        self._prev_free_status = {i: True for i in range(len(self.drones))}
        self._overdue_task_ids = set()
        self.generated_task_times = []
        self._manual_task_counter = 0
        # 交互式控制台可暂停自动订单流，便于只观察人工注入任务与重调度。
        # 仅影响 TaskGenerator.step，不影响当前待调度池，也不修改持久配置。
        self.task_generation_paused = False

        self.total_generated_tasks = 0
        self.total_completed_tasks = 0
        self.total_on_time_tasks = 0
        self.total_delay = 0.0
        self.total_generation_to_assignment_wait = 0.0
        self.total_assignment_to_load_wait = 0.0
        self.total_wait_time = 0.0
        self.total_delivery_time = 0.0
        self.total_generation_to_completion_time = 0.0
        self.max_delivery_time = 0.0
        self.max_generation_to_completion_time = 0.0
        self.priority_delay_totals = {1: 0.0, 2: 0.0, 3: 0.0}
        self.priority_delay_counts = {1: 0, 2: 0, 3: 0}

        # 重置耗电量统计
        self.total_energy_consumed = 0.0

        # 重置机巢泊位竞争状态与周转指标（创新点2）
        self._nest_waiting = {s.station_id: [] for s in self.charging_stations}
        self.total_swap_sessions = 0
        self._berth_occupied_sum = 0
        self._berth_wait_time_sum = 0.0
        self._berth_wait_count = 0
        self._berth_wait_max = 0.0
        self._berth_wait_urgency_sum = 0.0
        self._berth_wait_task_urgency_sum = 0.0

        # 重置任务生成器并生成初始任务
        self.task_generator.reset()
        self.task_generator.set_seed(self._episode_seed)
        initial_tasks = self.task_generator.generate_initial_tasks(self.current_time)
        self.unassigned_tasks.extend(self.task_generator.unassigned_tasks)
        self.generated_task_times = [t.get_generation_time() for t in initial_tasks]
        self.total_generated_tasks = self.task_generator.total_tasks_generated

        return self._obs()
    
    def _reward(self):
        """
        计算奖励
        1. 每步负奖励：-0.1
        2. 任务完成奖励：根据优先级给予奖励，如果超时则惩罚
        """
        reward = 0.0
        
        # 每步负奖励
        reward += self.reward_step
        
        # 计算刚刚完成的任务的奖励（送达时给奖励）
        for completed in self.completed_tasks:
            task = completed['task']
            completion_time = completed['completion_time']
            
            # 基础完成奖励
            priority = task.get_priority()
            if priority == 1:
                reward += self.reward_priority_1
            elif priority == 2:
                reward += self.reward_priority_2
            else:
                reward += self.reward_priority_3
            delay = float(completed.get('delay', 0.0))
            if delay > 0:
                reward += self.penalty_late_rate * delay * self._priority_delay_weight(priority)

        # 对未完成且已超时的任务惩罚：首次大惩罚，持续超时小惩罚
        seen_task_ids = set()
        overdue_penalty = 0.0
        current_time = self.current_time

        for task in self.task_generator.unassigned_tasks:
            if task.task_id in seen_task_ids:
                continue
            seen_task_ids.add(task.task_id)
            deadline = task.get_deadline()
            if deadline is None:
                continue
            overdue = current_time - deadline
            if overdue > 0:
                priority_weight = self._priority_delay_weight(task.get_priority())
                if task.task_id not in self._overdue_task_ids:
                    overdue_penalty += self.overdue_initial_penalty * priority_weight
                    self._overdue_task_ids.add(task.task_id)
                else:
                    overdue_penalty += self.overdue_step_penalty * priority_weight

        for assignments in self.drone_assignments.values():
            if isinstance(assignments, dict):
                assignments = [assignments]
            for assignment in assignments:
                task = assignment.get('task')
                if task is None or task.task_id in seen_task_ids:
                    continue
                seen_task_ids.add(task.task_id)
                deadline = task.get_deadline()
                if deadline is None:
                    continue
                overdue = current_time - deadline
                if overdue > 0:
                    priority_weight = self._priority_delay_weight(task.get_priority())
                    if task.task_id not in self._overdue_task_ids:
                        overdue_penalty += self.overdue_initial_penalty * priority_weight
                        self._overdue_task_ids.add(task.task_id)
                    else:
                        overdue_penalty += self.overdue_step_penalty * priority_weight

        reward += overdue_penalty
        
        # 清空已处理的完成任务
        self.completed_tasks.clear()
        
        return reward
    
    def _obs(self):
        """
        返回观察空间：
        1. list：所有无人机的：当前位置
        2. list：未分配订单的： 取位置 送位置 剩余时间：ttlj=ddlj−now 优先级
        3. list《list》：掩码：所有无人机的is_free
        """
        # 1. 所有无人机的当前位置
        drone_positions = []
        for drone in self.drones:
            pos = drone.get_position()
            drone_positions.append([pos[0], pos[1]])
        
        # 2. 未分配订单的信息
        unassigned_tasks_info = []
        current_time = self.current_time
        for task in self.task_generator.unassigned_tasks:
            source = task.get_source()
            destination = task.get_destination()
            deadline = task.get_deadline()
            priority = task.get_priority()
            task_id = task.task_id
            weight = task.get_weight()
            route_distance = math.dist(source, destination)
            source_to_warehouse = math.dist(source, WAREHOUSE_POS)
            
            # 计算剩余时间：ttlj = ddlj - now
            if deadline is not None:
                ttlj = deadline - current_time
            else:
                ttlj = float('inf')  # 如果没有截止时间，设为无穷大
            
            unassigned_tasks_info.append({
                'task_id': task_id,
                'source': [source[0], source[1]],
                'destination': [destination[0], destination[1]],
                'remaining_time': ttlj,
                'priority': priority,
                'weight': weight,
                'volume': task.get_volume(),
                'category': task.get_category(),
                'route_distance': route_distance,
                'source_to_warehouse': source_to_warehouse
            })

        # 保持任务的生成顺序（FIFO），不做额外排序，以便贪心策略按先来后到选择
        
        # 3. 所有无人机的is_free掩码
        # 当 allow_multi_task 启用时：不空闲但尚未抵达取货点的 drone 仍可接同源任务
        drone_free_masks = []
        for drone_idx, drone in enumerate(self.drones):
            if getattr(drone, 'out_of_service', False):
                free_mask = [False for _ in self.task_generator.unassigned_tasks]
            elif drone.is_free:
                free_mask = [True for _ in self.task_generator.unassigned_tasks]
            elif ALLOW_MULTI_TASK:
                pending_source = None
                for wp in drone.scheduled_position:
                    if len(wp) >= 3 and wp[2] == 'source':
                        pending_source = (wp[0], wp[1])
                        break
                if pending_source is not None:
                    chain_full = (
                        self.drone_chain_len.get(drone_idx, 0) >= CHAIN_MAX_TASKS)
                    free_mask = []
                    for task in self.task_generator.unassigned_tasks:
                        ok = task.get_source() == pending_source
                        # 顺路接入：链条未满且绕行在阈值内的异源任务同样可接
                        if not ok and CHAIN_ENABLED and not chain_full:
                            ok = self._detour_acceptable(drone, task)
                        free_mask.append(ok)
                else:
                    free_mask = [False for _ in self.task_generator.unassigned_tasks]
            else:
                free_mask = [False for _ in self.task_generator.unassigned_tasks]
            drone_free_masks.append(free_mask)

        # 固定观察长度：截断或填充到 MAX_OBS_TASKS
        current_len = len(unassigned_tasks_info)
        if current_len > MAX_OBS_TASKS:
            unassigned_tasks_info = unassigned_tasks_info[:MAX_OBS_TASKS]
            for i in range(len(drone_free_masks)):
                drone_free_masks[i] = drone_free_masks[i][:MAX_OBS_TASKS]
        elif current_len < MAX_OBS_TASKS:
            pad_count = MAX_OBS_TASKS - current_len
            pad_tasks = [
                {
                    'task_id': f'__pad_{k}',
                    'source': [0.0, 0.0],
                    'destination': [0.0, 0.0],
                    'remaining_time': -1.0,
                    'priority': 0,
                    'weight': 0.0,
                    'volume': 0.0,
                    'category': 'normal',
                    'route_distance': 0.0,
                    'source_to_warehouse': 0.0,
                }
                for k in range(pad_count)
            ]
            unassigned_tasks_info.extend(pad_tasks)
            for i in range(len(drone_free_masks)):
                drone_free_masks[i].extend([False] * pad_count)

        # 3b. 扁平的 is_free 状态（与 unassigned_tasks 是否为空解耦，事件驱动调度依赖此字段）
        drone_is_free = [bool(drone.is_free and not getattr(drone, 'out_of_service', False)) for drone in self.drones]

        # 3c. 任务链状态：调度器据此判断"在途机还能顺路接入几单"
        drone_chain_info = []
        for i, drone in enumerate(self.drones):
            tail = self._chain_tail(drone)
            chain_len = int(self.drone_chain_len.get(i, 0))
            # 剩余航线长度（米）：供调度器估算"追加该单后能否赶上 deadline"
            remaining_m = 0.0
            prev = (drone.x, drone.y)
            for wp in drone.scheduled_position:
                remaining_m += _dist_m(prev, (wp[0], wp[1]))
                prev = (wp[0], wp[1])
            speed = float(getattr(drone, 'speed', DRONE_CFG.get("speed", 17.0))) or 17.0
            drone_chain_info.append({
                'chain_len': chain_len,
                'chain_capacity': int(CHAIN_MAX_TASKS),
                'can_chain': (
                    CHAIN_ENABLED
                    and (not getattr(drone, 'out_of_service', False))
                    and (not drone.is_free)
                    and chain_len < CHAIN_MAX_TASKS
                ),
                'route_tail': [float(tail[0]), float(tail[1])],
                'remaining_route_m': float(remaining_m),
                'speed': speed,
            })

        # 4. 电量信息（PSO 等预测式调度器需要据此评估能耗与充电耗时）
        drone_batteries = [
            {
                'current': drone.current_battery,
                'capacity': drone.battery_capacity,
                'is_charging': drone.is_charging,
                'out_of_service': bool(getattr(drone, 'out_of_service', False)),
            }
            for drone in self.drones
        ]

        # 4b. 载重信息
        drone_loads = [
            {
                'current': getattr(drone, 'current_load', 0.0),
                'capacity': drone.carrying_capacity,
            }
            for drone in self.drones
        ]

        # 4c. 机型能力（异构调度：速度/能耗/续航/载重），供匹配度函数使用
        drone_capabilities = [
            {
                'drone_type': getattr(drone, 'drone_type', None),
                'speed': getattr(drone, 'speed', DRONE_CFG.get("speed", 200.0)),
                'battery_capacity': drone.battery_capacity,
                'battery_consumption_base': getattr(drone, 'battery_consumption_base', BATTERY_CONSUMPTION_BASE),
                'load_penalty_factor': getattr(drone, 'battery_load_penalty_factor', BATTERY_LOAD_PENALTY_FACTOR),
                'carrying_capacity': 0.0 if getattr(drone, 'out_of_service', False) else drone.carrying_capacity,
                'remaining_capacity': 0.0 if getattr(drone, 'out_of_service', False) else drone.carrying_capacity - getattr(drone, 'current_load', 0.0),
                'out_of_service': bool(getattr(drone, 'out_of_service', False)),
            }
            for drone in self.drones
        ]

        # 5. 充电站信息（位置 + 换电耗时），与 frontend/drone.py 实际使用的站点一致
        charging_stations_info = [
            {
                'station_id': s.station_id,
                'position': [s.x, s.y],
                'charging_power': s.charging_power,
                'swap_time_seconds': s.swap_time_seconds,
                'berths': s.berths,
                'occupied': s.occupied,
                'free_berths': s.free_berths(),
                'closed': False,
            }
            for s in self.charging_stations
            if not getattr(s, 'closed', False)
        ]
        # 向后兼容：单站字段
        charging_station_info = charging_stations_info[0] if charging_stations_info else {
            'position': [0.0, 0.0],
            'charging_power': 50.0,
            'swap_time_seconds': 180.0,
        }

        return {
            'drone_positions': drone_positions,
            'unassigned_tasks': unassigned_tasks_info,
            'drone_free_masks': drone_free_masks,
            'drone_is_free': drone_is_free,
            'drone_chain_info': drone_chain_info,
            'drone_batteries': drone_batteries,
            'drone_loads': drone_loads,
            'drone_capabilities': drone_capabilities,
            'charging_station': charging_station_info,   # 向后兼容
            'charging_stations': charging_stations_info,  # 新：多站列表
        }
    
    # ----------- 任务链 / 顺路接入 -----------

    @staticmethod
    def _is_carrying(drone) -> bool:
        """本步是否真正"带货在飞"——用于空载率统计。

        注意不能直接用 `current_load > 0`：环境在**派单时刻**就调用 add_load，
        因此"飞往取货点"的那一段也会被认为是载货，空载率会被低估到接近 0。
        正确口径是看航线上下一个任务航点：
          * 下一个任务航点是 source → 还没取货 → 空载；
          * 下一个任务航点是 dest   → 已在送货途中 → 载货；
          * 没有任务航点（如飞往机巢 / 空驶调度）→ 空载。
        """
        if float(getattr(drone, 'current_load', 0.0)) <= 1e-9:
            return False
        for wp in drone.scheduled_position:
            if len(wp) >= 3 and wp[2] == 'source':
                return False
            if len(wp) >= 3 and wp[2] == 'dest':
                return True
        return False

    def _chain_tail(self, drone):
        """当前航线的最后一个航点（任务链追加的衔接点）；航线为空时取当前位置。"""
        if drone.scheduled_position:
            wp = drone.scheduled_position[-1]
            return (wp[0], wp[1])
        return drone.get_position()

    def _detour_acceptable(self, drone, task):
        """绕行可接受性判定：距离在"顺路半径"内 **且** 电量撑得住。

        距离口径：用「新任务起点 → 航线各航点 / 当前机位」的最小距离度量绕行代价，
        阈值为 `task_chain.max_detour_m`；阈值 <= 0 表示不限制。

        电量口径：粗估追加该单所需耗电（当前位置 → 取货点 → 送达点），
        低于电量容量的 `battery_reserve_ratio` 则不放行 —— 否则任务链会把
        无人机拖到半路没电，反而拖累整体完成率。
        """
        src = task.get_source()
        sx, sy = float(src[0]), float(src[1])
        best = math.hypot(drone.x - sx, drone.y - sy)
        for wp in drone.scheduled_position:
            d = math.hypot(wp[0] - sx, wp[1] - sy)
            if d < best:
                best = d
        if CHAIN_MAX_DETOUR_M > 0 and best > CHAIN_MAX_DETOUR_M:
            return False

        # 电量可行性：粗估追加该单的耗电（不含等待/悬停）
        capacity = float(getattr(drone, 'battery_capacity', 0.0) or 0.0)
        if capacity <= 0:
            return True
        dst = task.get_destination()
        tail = self._chain_tail(drone)
        extra = _dist_m(tail, src) + _dist_m(src, dst)
        base = float(getattr(drone, 'battery_consumption_base', 0.06))
        penalty = float(getattr(drone, 'battery_load_penalty_factor', 0.33))
        load_ratio = 0.0 if not drone.carrying_capacity else min(
            1.0, float(drone.current_load) / float(drone.carrying_capacity))
        need = base * extra * (1.0 + penalty * load_ratio)
        return float(drone.current_battery) - need >= capacity * CHAIN_BATTERY_RESERVE

    def _append_task_to_chain(self, drone_idx, drone, task):
        """把新任务以「取货点 → 送达点」两段追加到既有航线尾部，形成任务链。

        与同源合并（只追加 dest 段）的区别：这里补完整的 source→dest 两段，
        因此允许异源任务串联，省掉"送完一单回巢/待命再出发"的空驶段。
        """
        src = task.get_source()
        dst = task.get_destination()

        for end_pos, tag in ((src, 'source'), (dst, 'dest')):
            last_pos = self._chain_tail(drone)
            route = self.plan_route_around_buildings(last_pos, end_pos)
            typed = []
            for j, pt in enumerate(route):
                typed.append((pt[0], pt[1], tag if j == len(route) - 1 else 'waypoint'))
            drone.append_route(typed)

        drone.add_load(task.get_weight())

        if drone_idx not in self.drone_assignments:
            self.drone_assignments[drone_idx] = []
        elif isinstance(self.drone_assignments[drone_idx], dict):
            self.drone_assignments[drone_idx] = [self.drone_assignments[drone_idx]]
        self.drone_assignments[drone_idx].append({
            'task': task,
            'assigned_time': self.current_time,
            'start_time': self.current_time,
            'load_time': None,
        })
        self.drone_chain_len[drone_idx] = self.drone_chain_len.get(drone_idx, 0) + 1

    def plan_route_for_tasks(self, drone, tasks):
        """
        为无人机规划多个任务的路线，确保绕过建筑物。
        返回完整的绕行路线，每个点格式为 (x, y, type)。
        type: 'source' = 任务起点, 'dest' = 任务终点, 'waypoint' = 绕飞航点
        """
        start_time = time.perf_counter()
        if not tasks:
            return []
        
        full_route = []  # 格式: [(x, y, type), ...]
        current_pos = drone.get_position()
        
        for task in tasks:
            # 规划从当前位置到任务起始点的路径
            source = task.get_source()
            dest = task.get_destination()
            
            # 第一步：当前位置 → 起始点（绕行）
            source_route = self.plan_route_around_buildings(current_pos, source)
            for point in source_route:
                # 最后一个点是 source，其他是 waypoint
                if len(source_route) > 1:
                    if point == source_route[-1]:
                        full_route.append((point[0], point[1], 'source'))
                    else:
                        full_route.append((point[0], point[1], 'waypoint'))
                else:
                    full_route.append((point[0], point[1], 'source'))
            
            # 第二步：起始点 → 终点（绕行）
            dest_route = self.plan_route_around_buildings(source, dest)
            for point in dest_route:
                if len(dest_route) > 1:
                    if point == dest_route[-1]:
                        full_route.append((point[0], point[1], 'dest'))
                    else:
                        full_route.append((point[0], point[1], 'waypoint'))
                else:
                    full_route.append((point[0], point[1], 'dest'))
            
            current_pos = dest
        
        if PRINT_ROUTE_DEBUG:
            print(f"Full planned route for drone {drone.drone_id}: {full_route}")
            elapsed = time.perf_counter() - start_time
            print(f"assign_task elapsed: {elapsed:.6f} seconds")
        
        # 验证整个路线是否与建筑物相交
        self.verify_route_with_types(full_route)
        
        return full_route
    
    def verify_route_with_types(self, route):
        """验证路线是否与建筑物相交"""
        for i in range(len(route) - 1):
            if not self.is_path_clear(route[i][:2], route[i+1][:2]):
                print(f"WARNING: Route segment {route[i][:2]} -> {route[i+1][:2]} intersects with building!")
                return False
        return True

    def plan_route_around_buildings(self, start_pos, end_pos):
        """
        Plans a route from start_pos to end_pos avoiding buildings using A* algorithm.
        """
        # Check if direct path is possible (stricter check)
        if self.is_path_clear(start_pos, end_pos):
            return [end_pos]

        # 直线被禁飞区拦截：记一次绕飞（用于观测禁飞区对航线的影响强度）
        if self.no_fly.path_blocked(start_pos, end_pos):
            self.total_no_fly_detours += 1

        # Try A* pathfinding
        path = self.a_star_pathfinding(start_pos, end_pos)
        
        if path and len(path) > 1:
            # Return path excluding starting position
            return path[1:]
        
        # Last resort: return direct destination with warning
        print(f"Warning: Could not find obstacle-free path from {start_pos} to {end_pos}")
        return [end_pos]

    def a_star_pathfinding(self, start, goal):
        """
        Implements A* pathfinding algorithm considering building obstacles.
        Uses visibility graph approach.
        """
        # Round positions to avoid floating point precision issues
        def round_pos(pos, decimals=2):
            return (round(pos[0], decimals), round(pos[1], decimals))
        
        start = round_pos(start)
        goal = round_pos(goal)
        
        # Get all relevant points (start, goal, and building corner points)
        all_points = [start, goal]
        
        # Add building corner points to our visibility graph
        for building in self.high_buildings:
            geom = building['geometry']
            if hasattr(geom, 'exterior'):  # Polygon
                for coord in list(geom.exterior.coords)[:-1]:
                    rounded_coord = round_pos(coord)
                    if rounded_coord != start and rounded_coord != goal:
                        all_points.append(rounded_coord)
            elif hasattr(geom, 'coords'):  # Point or LineString
                for coord in geom.coords:
                    rounded_coord = round_pos(coord)
                    if rounded_coord != start and rounded_coord != goal:
                        all_points.append(rounded_coord)

        # 禁飞区：补充外沿采样点，使 A* 能真正绕飞而不是直接穿越
        for pt in self.no_fly.corner_points():
            rounded_coord = round_pos(pt)
            if rounded_coord != start and rounded_coord != goal:
                all_points.append(rounded_coord)

        # Remove duplicates
        all_points = list(set(all_points))
        
        # Create dictionaries with rounded keys for consistent lookup
        point_to_key = {p: p for p in all_points}
        
        # Implement A* algorithm
        open_set = [(0, start)]
        came_from = {}
        g_score = {start: 0}
        f_score = {start: self.heuristic(start, goal)}
        
        open_set_set = {start}
        
        while open_set:
            _, current = heapq.heappop(open_set)
            open_set_set.remove(current)
            
            if self.heuristic(current, goal) < 1:  # Close enough to goal
                # Reconstruct path
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                path.reverse()
                return path
            
            for neighbor in all_points:
                if neighbor == current:
                    continue
                    
                # Check if path from current to neighbor intersects any buildings
                if self.is_path_clear(current, neighbor):
                    tentative_g = g_score.get(current, float('inf')) + self.heuristic(current, neighbor)
                    
                    if tentative_g < g_score.get(neighbor, float('inf')):
                        came_from[neighbor] = current
                        g_score[neighbor] = tentative_g
                        f_score[neighbor] = tentative_g + self.heuristic(neighbor, goal)
                        
                        if neighbor not in open_set_set:
                            heapq.heappush(open_set, (f_score[neighbor], neighbor))
                            open_set_set.add(neighbor)
        
        # No path found
        return None

    def heuristic(self, pos1, pos2):
        """
        Calculates Euclidean distance between two points.
        """
        return math.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)

    def is_path_clear(self, pos1, pos2):
        """
        Checks if the path between two positions is free of buildings and no-fly zones.
        禁飞区判定复用与建筑物相同的"擦角忽略"阈值，保证两类障碍口径一致。
        """
        x1, y1 = pos1
        x2, y2 = pos2
        lminx, lmaxx = (x1, x2) if x1 <= x2 else (x2, x1)
        lminy, lmaxy = (y1, y2) if y1 <= y2 else (y2, y1)

        line = LineString([pos1, pos2])

        for (bxmin, bymin, bxmax, bymax), geom in self._high_buildings_bbox:
            # bbox 快速剔除：包围盒不重叠 → 几何上必然不相交。
            # 这是纯数值比较，比 GEOS 的 intersects 便宜约两个数量级。
            if bxmax < lminx or bxmin > lmaxx or bymax < lminy or bymin > lmaxy:
                continue
            if geom.intersects(line):
                # Check if intersection is significant (not just touching corners)
                if geom.intersection(line).length > 0.1:  # Small threshold to avoid floating point errors
                    return False

        # 禁飞区：与建筑物同等对待的硬约束（含安全余量外扩）
        if self.no_fly.path_blocked(pos1, pos2):
            return False

        return True
