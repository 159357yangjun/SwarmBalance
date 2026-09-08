import math
import random
from config.config_loder import get_shared_config
from charging_station import DEFAULT_CHARGING_STATIONS, find_nearest_station


_DRONE_CFG = get_shared_config().get("drone", {})
_HETERO_CFG = get_shared_config().get("heterogeneous", {})
DRONE_TYPES = _HETERO_CFG.get("drone_types", {})
HETERO_ENABLED = bool(_HETERO_CFG.get("enabled", False))

# ==================== 电池系统常量（默认机型参数，作为实例属性的兜底） ====================
BATTERY_CAPACITY = float(_DRONE_CFG.get("battery_capacity", 15000.0))
BATTERY_CONSUMPTION_BASE = float(_DRONE_CFG.get("battery_consumption_base", 0.5))
BATTERY_LOAD_PENALTY_FACTOR = float(_DRONE_CFG.get("battery_load_penalty_factor", 0.3))
BATTERY_LOW_THRESHOLD = float(_DRONE_CFG.get("battery_low_threshold", 0.2))
DRONE_SPEED = float(_DRONE_CFG.get("speed", 200.0))
DRONE_TIME_STEP = float(_DRONE_CFG.get("time_step", 1.0))
DRONE_SWAP_TIME = float(_DRONE_CFG.get("swap_time_seconds", 180))
DEFAULT_CARRYING_CAPACITY = int(_DRONE_CFG.get("carrying_capacity", 5))


def resolve_drone_type(drone_type):
    """从配置读取机型参数，未知或禁用异构时返回 None（走默认参数）。"""
    if not HETERO_ENABLED or not drone_type:
        return None
    return DRONE_TYPES.get(drone_type)


# ==================== 无人机类 ====================
class Drone:
    def __init__(self, x, y, drone_id="drone_0", carrying_capacity=None,
                 battery_capacity=BATTERY_CAPACITY, drone_type=None):
        # 机型参数（异构无人机核心差异）：速度、基础能耗、载重惩罚系数、续航
        type_cfg = resolve_drone_type(drone_type)
        self.drone_type = drone_type
        if type_cfg:
            self.speed = float(type_cfg.get("speed", DRONE_SPEED))
            self.battery_consumption_base = float(type_cfg.get("battery_consumption_base", BATTERY_CONSUMPTION_BASE))
            self.battery_load_penalty_factor = float(type_cfg.get("battery_load_penalty_factor", BATTERY_LOAD_PENALTY_FACTOR))
            if carrying_capacity is None:
                carrying_capacity = int(type_cfg.get("carrying_capacity", DEFAULT_CARRYING_CAPACITY))
            battery_capacity = float(type_cfg.get("battery_capacity", battery_capacity))
        else:
            self.speed = DRONE_SPEED
            self.battery_consumption_base = BATTERY_CONSUMPTION_BASE
            self.battery_load_penalty_factor = BATTERY_LOAD_PENALTY_FACTOR

        # 位置信息
        self.x = x
        self.y = y
        self.drone_id = drone_id
        self.home_position = (x, y)  # 记录出发点位置（用于返回装货）
        
        # 载重信息
        self.carrying_capacity = carrying_capacity if carrying_capacity is not None else DEFAULT_CARRYING_CAPACITY
        self.current_load = 0  # 当前载重
        
        # 任务信息
        self.tasks = []
        self.scheduled_position = []
        self.executing_task_id = None  # 当前正在执行的已分配任务ID
        self.is_free = True # 表示无人机是否可以接单
        
        # ==================== 电量系统（机巢换电模式） ====================
        self.battery_capacity = battery_capacity  # 电池最大容量 (Wh)
        self.current_battery = battery_capacity  # 当前电量 (Wh)，初始满电
        self.is_charging = False  # 是否正在换电/不可接单（沿用具名，语义=换电）
        self.charging_station_id = None  # 当前所在机巢ID
        self.swap_time_seconds = DRONE_SWAP_TIME  # 换电耗时（秒）
        self.swap_remaining_steps = 0.0  # 剩余换电秒数（>0 表示换电中）
        # 可供该机选择的机巢（换电站）列表；环境按数据源覆盖，缺省用配置默认站
        self.known_stations = DEFAULT_CHARGING_STATIONS
        
        # ==================== 机巢泊位排队（起降/换电资源竞争） ====================
        self.awaiting_berth = False    # 已抵达机巢、正在等待泊位（尚未开始换电）
        self.berth_station_id = None   # 等待/占用泊位的机巢ID
        self.awaiting_since = None     # 进入等待队列的仿真时间（用于优先级仲裁）
        self._pending_release = False  # 换电完成，待环境释放泊位
        # 预判式换电：低电但仍有待飞航点（待办任务）时，挂起剩余航线先去换电，换后恢复
        self._suspended_route = []
        
    # ==================== 电量相关方法 ====================
    
    def get_battery_level(self):
        """获取电量百分比 (0.0 ~ 1.0)"""
        return self.current_battery / self.battery_capacity
    
    def is_low_battery(self, threshold=BATTERY_LOW_THRESHOLD):
        """检查是否低电量"""
        return self.get_battery_level() < threshold
    
    def consume_battery(self, distance):
        """
        消耗电量
        
        消耗公式：
            总消耗 = 基础消耗 × (1 + 载重惩罚)
            其中 载重惩罚 = (current_load / carrying_capacity) × LOAD_PENALTY_FACTOR
        """
        # 基础飞行消耗
        base_consumption = distance * self.battery_consumption_base
        
        # 载重影响
        load_factor = (self.current_load / self.carrying_capacity) * self.battery_load_penalty_factor
        total_consumption = base_consumption * (1 + load_factor)
        
        # 更新电量（不能低于0）
        self.current_battery = max(0, self.current_battery - total_consumption)
        
        return total_consumption
    
    def start_charging(self, station_id, charging_power=None, swap_time_seconds=None):
        """在机巢开始换电（降落整组更换电池，非慢充）。

        `swap_time_seconds` 指定换电耗时（秒）；未给出时沿用无人机默认换电时长。
        换电期间不可接单，`swap_time_seconds` 秒后恢复满电。`charging_power` 参数
        仅为向后兼容旧调用保留，换电模型下不再使用。
        """
        self.is_charging = True
        self.charging_station_id = station_id
        if swap_time_seconds is not None:
            self.swap_time_seconds = float(swap_time_seconds)
        self.swap_remaining_steps = self.swap_time_seconds
        self.is_free = False  # 换电中不可接单

    def stop_charging(self):
        """中止换电（当前无调用方，保留向后兼容）。"""
        self.is_charging = False
        self.charging_station_id = None
        self.swap_remaining_steps = 0.0
    
    def reset_battery(self):
        """重置电量为满电（回到仓库时调用）"""
        self.current_battery = self.battery_capacity

    def schedule_route(self, position, task_id=None):
        self.scheduled_position = position
        self.executing_task_id = task_id
        # 只有执行调度器分配的正式任务时才标记为忙碌
        # 自动飞往充电站/待机不算正式任务，is_free保持True
        if task_id is not None:
            self.is_free = False

    def append_route(self, position):
        """追加航点，不覆盖现有航点"""
        if self.scheduled_position:
            self.scheduled_position.extend(position)
        else:
            self.scheduled_position = list(position)
        self.is_free = False

    def return_to_base(self, base_position):
        """返回出发点装货"""
        self.scheduled_position = [base_position]
        self.current_load = 0
        self.is_free = False

    def add_load(self, weight):
        """装载货物"""
        self.current_load += weight

    def get_remaining_capacity(self):
        """获取剩余载重"""
        return self.carrying_capacity - self.current_load

    def update(self, time_step=None):
        if time_step is None:
            time_step = DRONE_TIME_STEP
        v = self.speed
        max_distance = v * time_step

        # 换电中：原地等待，剩余换电时长按秒递减；归零即满电并可重新接单。
        if self.is_charging:
            self.swap_remaining_steps -= time_step
            if self.swap_remaining_steps <= 0:
                self.swap_remaining_steps = 0.0
                self.current_battery = self.battery_capacity
                self.is_charging = False
                # 泊位释放交由环境仲裁处理（charging_station_id 暂留，供环境识别机巢）
                self._pending_release = True
                if self._suspended_route:
                    # 预判式换电：换满后立刻恢复被挂起的任务航线，不视为空闲（货物与任务保留）
                    self.scheduled_position = list(self._suspended_route)
                    self._suspended_route = []
                    self.is_free = False
                else:
                    self.is_free = True
            return

        # 预判式换电触发：低电但仍背负待飞航点（含待办任务）时，挂起剩余航线改飞最近机巢，
        # 让任务紧迫度伴随无人机进入泊位仲裁队列（创新点2 第三因素：任务紧迫度）。
        if (self.scheduled_position and self.executing_task_id is not None
                and self.is_low_battery() and not self.awaiting_berth
                and not self._suspended_route):
            self._suspended_route = list(self.scheduled_position)
            self.scheduled_position = []
            self.is_free = False
            nearest = find_nearest_station(self.known_stations, (self.x, self.y))
            if nearest is not None:
                nest_pos = nearest.get_position()
                if (self.x, self.y) == nest_pos:
                    self.awaiting_berth = True
                    self.berth_station_id = nearest.station_id
                else:
                    self.scheduled_position = [nest_pos]
            return

        if self.scheduled_position:
            # Get the next target position (支持新旧两种格式)
            target = self.scheduled_position[0]
            if len(target) >= 3:
                target_x, target_y, _ = target  # 新格式: (x, y, type)
            else:
                target_x, target_y = target  # 旧格式: (x, y)

            # Calculate direction vector
            dx = target_x - self.x
            dy = target_y - self.y

            # Calculate distance to target
            distance = (dx**2 + dy**2)**0.5

            if distance <= max_distance:
                # If we're close enough to target, move directly to it
                self.x = target_x
                self.y = target_y
                # 到达目标，消耗电量
                self.consume_battery(distance)
                # Remove this target from schedule as we've reached it
                self.scheduled_position.pop(0)
                if not self.scheduled_position:
                    if self._suspended_route:
                        # 预判换电改道：已抵达机巢，登记泊位请求等待环境仲裁（不卸货、不清任务）
                        self.is_free = False
                        nearest = find_nearest_station(self.known_stations, (self.x, self.y))
                        if nearest is not None and (self.x, self.y) == nearest.get_position():
                            self.awaiting_berth = True
                            self.berth_station_id = nearest.station_id
                    else:
                        self.is_free = True
                        self.current_load = 0  # 任务完成，卸货
                        self.executing_task_id = None  # 清除执行中任务ID
                        # 任务完成后：根据电量决定去向
                        if self.is_low_battery():
                            # 找到最近的充电站
                            drone_pos = (self.x, self.y)
                            nearest = find_nearest_station(self.known_stations, drone_pos)
                            if nearest is None:
                                pass
                            elif drone_pos == nearest.get_position():
                                # 已在机巢：登记泊位请求，是否立即换电交由环境仲裁（泊位可能被占）
                                self.awaiting_berth = True
                                self.berth_station_id = nearest.station_id
                                self.is_free = False
                            else:
                                # 不在机巢，飞往最近的机巢
                                self.is_free = False
                                self.schedule_route([nearest.get_position()])
                        # else: 电量充足，原地待机，等待调度器分配新任务
            else:
                # Move a step towards the target
                # Normalize the direction and multiply by time_step
                actual_distance = max_distance
                self.x += (dx / distance) * actual_distance
                self.y += (dy / distance) * actual_distance
                # 飞行消耗电量
                self.consume_battery(actual_distance)

    def get_position(self):
        return (self.x, self.y)