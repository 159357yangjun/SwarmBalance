import math
import random
import os
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
# ==================== 时间基准（规范 WL-1.2）====================
# 规范要求 1 step = 1 秒，且该映射「必须在代码常量与 UI 中显式声明，禁止仅靠配置
# 凑出自洽」。此前时钟写死 current_time += 1，而位移按 speed × time_step 推进，
# 两者各取各的值，只在 time_step=1.0 时碰巧一致。现在统一走这一个常量。
STEP_SECONDS = float(_DRONE_CFG.get("time_step", 1.0))
# 历史别名，与 STEP_SECONDS 同一个值；新代码请用 STEP_SECONDS。
DRONE_TIME_STEP = STEP_SECONDS
DRONE_SWAP_TIME = float(_DRONE_CFG.get("swap_time_seconds", 180))
DEFAULT_CARRYING_CAPACITY = float(_DRONE_CFG.get("carrying_capacity", 5))

# ==================== E1：风能耗修正（情景系数，非实测）====================
# 三个 K 与上下界**默认全为中性值** ⇒ 未显式开风时，E1 的 consume_battery 逐字等于 E0。
# 这是刻意的：正式默认参数不许被这轮结构扩展改动（用户约束）。风只作为实验情景输入存在。
# 依据缺口：K_HEAD / K_TAIL 无厂商公布、无实机日志可拟合 ⇒ 登记为 assumption（见 docs/数据统计总表.md §E）。
_WIND_CFG = _DRONE_CFG.get("wind_energy", {}) or {}
WIND_ENABLED = bool(_WIND_CFG.get("enabled", False))
WIND_ENERGY_HEADWIND_PER_MS = float(_WIND_CFG.get("headwind_per_ms", 0.0))
WIND_ENERGY_TAILWIND_PER_MS = float(_WIND_CFG.get("tailwind_per_ms", 0.0))
WIND_FACTOR_FLOOR = float(_WIND_CFG.get("factor_floor", 0.5))
WIND_FACTOR_CEIL = float(_WIND_CFG.get("factor_ceil", 3.0))
# 沿航线分量的求法：本步位移方向与风向单位向量的点积 ⇒ 逆风为正。
# 风场是"每步查询一次"的环境量，由 Environment 通过 set_wind() 注入；未注入即静风。


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
                # float 而不是 int：配置里 light_express 是 2.4 kg（对标美团第四代），
                # 用 int 会静默截成 2 kg —— 与配置、README 和两份文档印的 2.4 全不一致，
                # 而且直接改变「这个任务 light 机型接不接得了」的判定边界。
                carrying_capacity = float(type_cfg.get("carrying_capacity", DEFAULT_CARRYING_CAPACITY))
            battery_capacity = float(type_cfg.get("battery_capacity", battery_capacity))
        else:
            self.speed = DRONE_SPEED
            self.battery_consumption_base = BATTERY_CONSUMPTION_BASE
            self.battery_load_penalty_factor = BATTERY_LOAD_PENALTY_FACTOR

        # 位置信息
        self.x = x
        self.y = y
        self.drone_id = drone_id
        # E1 风能耗：风场由 Environment 注入（set_wind），本步沿航线分量在 update() 里现算。
        # 未注入 ⇒ _wind_uv 为 None ⇒ _wind_factor 返回 1.0 ⇒ 与 E0 逐字一致。
        self._wind_uv = None
        self.home_position = (x, y)  # 记录出发点位置（用于返回装货）
        
        # 载重信息
        self.carrying_capacity = carrying_capacity if carrying_capacity is not None else DEFAULT_CARRYING_CAPACITY
        self.current_load = 0  # 当前载重
        # B experimental channel: actual onboard kg set only after source
        # service event and removed after destination service event.
        # This does NOT replace assigned current_load for task capacity.
        self.onboard_load_kg = 0.0
        
        # 任务信息
        self.tasks = []
        self.scheduled_position = []
        self.executing_task_id = None  # 当前正在执行的已分配任务ID
        self.is_free = True # 表示无人机是否可以接单
        # #69-H3 D-iv：执行器"真正弹出服务航点"的离散事件缓冲（唯一权威证人）。
        # update() 里每次 pop(0) append 一个 (sim_time, waypoint)，保持发生顺序；
        # Environment 每步消费后清空。几何途经/长度差/前后缀一律不再反推弹出。
        self.consumed_waypoints_this_step = []
        
        # ==================== 电量系统（机巢换电模式） ====================
        self.battery_capacity = battery_capacity  # 电池最大容量 (Wh)
        self.current_battery = battery_capacity  # 当前电量 (Wh)，初始满电
        # C: distinguish modeled energy requirement, battery debit, and unmet demand.
        # These are the most recent consume_battery() leg, never inferred from
        # load state or historical aggregates.
        self.last_energy_required_wh = 0.0
        self.last_energy_debited_wh = 0.0
        self.last_energy_shortfall_wh = 0.0
        self.energy_insufficient = False
        # P2.2: an unaffordable step is a grounded hold, not simulated flight.
        self.flight_energy_blocked = False
        self.flight_energy_block_reason = None
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
        # 交互式控制：人工请求前往机巢换电。与低电自动换电共用泊位仲裁，
        # 但即使电量不低也允许用于答辩/场景调度演示。
        self._manual_charge_requested = False
        # 交互式事故注入：停飞/故障无人机不参与调度、不移动，但保留机型与电量状态。
        self.out_of_service = False
        self.out_of_service_reason = None
        
    # ==================== 电量相关方法 ====================
    
    def get_battery_level(self):
        """获取电量百分比 (0.0 ~ 1.0)"""
        return self.current_battery / self.battery_capacity
    
    def is_low_battery(self, threshold=BATTERY_LOW_THRESHOLD):
        """检查是否低电量"""
        return self.get_battery_level() < threshold
    
    def set_wind(self, wind_u=None, wind_v=None):
        """注入风场（世界坐标下的两个分量，m/s）。None ⇒ 静风 ⇒ E1 退回 E0。

        约定：风向量是"风吹往的方向"（气象惯例），因此向东吹的风 wind_u>0；
        无人机向东飞时与该向量同向 ⇒ 顺风 ⇒ `wind_along` 取负。
        """
        self._wind_uv = (None if wind_u is None or wind_v is None
                         else (float(wind_u), float(wind_v)))

    def _wind_along_for(self, dx, dy, distance):
        """本步位移方向上的风分量，**正=逆风、负=顺风**。未设风场或零位移 ⇒ None（倍率 1.0）。

        注意这里**不看 WIND_ENABLED**：分量是几何量，只要注入了风就该算得出来，
        否则"开关关着"会让符号约定无法被单测验证（第一版就因此报了三条 TypeError ——
        那是量具错，不是被测对象错）。开关只在 `_wind_factor` 里生效。
        """
        uv = getattr(self, "_wind_uv", None)
        if uv is None:
            return None
        if distance <= 0:
            return None
        # 单位位移向量 · 风速向量的相反数 = 逆风为正的分量
        return -(uv[0] * (dx / distance) + uv[1] * (dy / distance))

    def quote_flight_energy_wh(self, distance, wind_along=None):
        """Return theoretical Wh for the requested segment without any mutation.

        Single source for both direct consume_battery() ledger billing and the
        P2.2 real next-step flight feasibility gate. The original assigned
        load policy remains the default; onboard stays explicit opt-in.
        Does not promise complete-route or reachable-nest feasibility.
        """
        # Keep the original C/B invalid-input and energy-policy semantics.
        for name, value in (("distance", distance),
                            ("carrying_capacity", self.carrying_capacity),
                            ("current_load", self.current_load),
                            ("current_battery", self.current_battery),
                            ("battery_consumption_base", self.battery_consumption_base),
                            ("battery_load_penalty_factor", self.battery_load_penalty_factor)):
            if not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError("[ENERGY_INPUT_NOT_FINITE] %s=%r" % (name, value))
        if distance < 0:
            raise ValueError("[ENERGY_DISTANCE_NEGATIVE] distance=%r" % (distance,))
        if self.carrying_capacity <= 0:
            raise ValueError("[ENERGY_CAPACITY_INVALID] carrying_capacity=%r" % (self.carrying_capacity,))
        if self.current_load < 0 or self.current_load > self.carrying_capacity:
            raise ValueError("[ENERGY_LOAD_INVALID] current_load=%r carrying_capacity=%r" %
                             (self.current_load, self.carrying_capacity))
        if self.current_battery < 0:
            raise ValueError("[ENERGY_BATTERY_NEGATIVE] current_battery=%r" % (self.current_battery,))
        if self.battery_consumption_base < 0 or self.battery_load_penalty_factor < 0:
            raise ValueError("[ENERGY_COEFFICIENT_NEGATIVE] invalid energy coefficient")
        # Historical assigned charging penalizes pre-pickup flights. P1-B
        # intentionally remains opt-in and is not changed in this refactor.
        if os.environ.get("SWARM_BALANCE_ENERGY_ACCOUNTING") == "onboard":
            charge_load = float(self.onboard_load_kg)
            if not math.isfinite(charge_load) or not 0 <= charge_load <= self.carrying_capacity:
                raise ValueError("[ENERGY_ONBOARD_LOAD_INVALID] onboard_load_kg=%r" %
                                 (self.onboard_load_kg,))
        else:
            charge_load = self.current_load
        base_consumption = distance * self.battery_consumption_base
        load_factor = (charge_load / self.carrying_capacity) * self.battery_load_penalty_factor
        required = base_consumption * (1 + load_factor) * self._wind_factor(wind_along)
        if not math.isfinite(required) or required < 0:
            raise ValueError("[ENERGY_REQUIREMENT_INVALID] required_wh=%r" % required)
        return required

    def consume_battery(self, distance, wind_along=None):
        """
        消耗电量
        
        消耗公式：
            总消耗 = 基础消耗 × (1 + 载重惩罚) × 风能耗倍率
            其中 载重惩罚 = (current_load / carrying_capacity) × LOAD_PENALTY_FACTOR
                 风能耗倍率 = _wind_factor(wind_along)

        `wind_along` 是**沿航线方向的风分量（m/s）**，符号约定：**正=逆风、负=顺风**。
        它是 E1（能耗结构扩展）新增的唯一自由度：不改位移、不改速度、不改任务生成，
        因此 E0→E1 的结果差异只能归因于"同一段路更费电"这一条路径。
        默认 None ⇒ 逐字退回 E0 行为（倍率恒 1.0），这是 wind=0 必须与 E0 数值一致的前提。
        """
        # All validation and required-Wh arithmetic now use the same
        # read-only source as the flight gate. Actual debit stays here.
        total_consumption = self.quote_flight_energy_wh(distance, wind_along)

        # C: required Wh is the original model demand. The account may only
        # debit available battery; the rest is explicit energy shortfall.
        if not math.isfinite(total_consumption) or total_consumption < 0:
            raise ValueError("[ENERGY_REQUIREMENT_INVALID] required_wh=%r" % total_consumption)
        available = self.current_battery
        debited = min(available, total_consumption)
        self.current_battery = available - debited
        self.last_energy_required_wh = total_consumption
        self.last_energy_debited_wh = debited
        self.last_energy_shortfall_wh = total_consumption - debited
        self.energy_insufficient = self.last_energy_shortfall_wh > 0.0
        # Return ACTUALLY debited Wh. The original theoretical Wh remains in
        # last_energy_required_wh. Movement feasibility is a separate policy.
        return debited

    def _wind_factor(self, wind_along):
        """沿航线风分量（m/s，**正=逆风、负=顺风**）→ 能耗倍率。

        形状：`factor = 1 + K_HEAD·w`（w>0 逆风 ⇒ 更费电）；`factor = 1 − K_TAIL·|w|`（顺风 ⇒ 省电），
        再夹在 `[WIND_FACTOR_FLOOR, WIND_FACTOR_CEIL]` 内。三条纪律：
          · 下界 > 0 ⇒ 顺风不可能出现负能耗或"给电池充电"；
          · 上界有限 ⇒ 极端风输入被截断，而不是把电量一次掏空；
          · K_TAIL < K_HEAD ⇒ 顺风省的少于逆风亏的，不给调度器留"永远等顺风"的作弊面。
        不做 v_air² 二次律：那需要空速/地速分离，属 E2（运动学层），本轮禁止混入。
        K 与上下界都是**情景系数，无实测来源（assumption）**；K 取 0 ⇒ 完全退回 E0。
        """
        if wind_along is None:
            return 1.0
        if not WIND_ENABLED:
            # 开关只作用在倍率层：风场可以照常注入与计算，但不产生任何能耗影响 ⇒ 退回 E0。
            return 1.0
        w = float(wind_along)
        if not math.isfinite(w):
            raise ValueError("[WIND_INPUT_NOT_FINITE] wind_along=%r" % (wind_along,))
        if w >= 0.0:
            return min(WIND_FACTOR_CEIL, 1.0 + WIND_ENERGY_HEADWIND_PER_MS * w)
        return max(WIND_FACTOR_FLOOR, 1.0 - WIND_ENERGY_TAILWIND_PER_MS * (-w))
    
    def _select_energy_affordable_direct_station(self):
        """Necessary Wh-screen for current straight station hop; not OSM clearance.

        Only preemptive *active-mission* diversion uses this until route
        planning and no-fly verification are integrated in P2.4b-B2 follow-up.
        A successful straight-hop quote is NOT a proof of real-map reachability.
        A 5% nameplate reserve is an explicit synthetic assumption, NOT a
        calibrated manufacturer/flight-log requirement.
        """
        capacity = self.battery_capacity
        if not isinstance(capacity, (float, int)) or not math.isfinite(capacity) or capacity <= 0:
            raise ValueError("[B2_BATTERY_CAPACITY_INVALID] battery_capacity=%r" % capacity)
        reserve_wh = 0.05 * capacity
        candidates = []
        for station in (self.known_stations or []):
            if getattr(station, "closed", False):
                continue
            sx, sy = station.get_position()
            dx, dy = sx - self.x, sy - self.y
            dist = math.hypot(dx, dy)
            if not math.isfinite(dist):
                continue
            along = self._wind_along_for(dx, dy, dist)
            needed = self.quote_flight_energy_wh(dist, along)
            if dist == 0 or needed + reserve_wh <= self.current_battery:
                candidates.append((needed, dist, str(station.station_id), station))
        return min(candidates, key=lambda item: item[:3])[-1] if candidates else None

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
        self.onboard_load_kg = 0.0
        self.is_free = False

    def add_load(self, weight):
        """装载货物"""
        self.current_load += weight

    def get_remaining_capacity(self):
        """获取剩余载重"""
        return self.carrying_capacity - self.current_load

    def update(self, time_step=None, station_quote_provider=None):
        # 故障/停飞状态：冻结当前位置与电量，不推进任何飞行/换电逻辑。
        # 任务回收与泊位释放由 Environment.set_drone_out_of_service() 统一处理。
        if getattr(self, 'out_of_service', False):
            return
        # B3c explicit experimental hold: closure cannot cause a free direct
        # reroute or phantom arrival; resume requires a new quoted request.
        if (os.environ.get("SWARM_BALANCE_CHARGE_TARGET_IDENTITY") == "1"
                and getattr(self, "charge_target_hold_reason", None)):
            return
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
                self._manual_charge_requested = False
                # Target is bound to this swap, never the next task. Keep
                # charging_station_id until Environment releases its berth.
                if os.environ.get("SWARM_BALANCE_CHARGE_TARGET_IDENTITY") == "1":
                    self.charge_target_station_id = None
                    self.charge_target_hold_reason = None
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
            # Do not sacrifice the original manifest for a mathematically
            # unaffordable nearest nest. The direct-hop test is only a
            # necessary energy bound, not a no-fly/OSM route certification.
            # Explicit experimental opt-in; historical E0/E1 runs and
            # normal deployments keep the exact old nearest-station rule.
            # This is only a direct-hop necessary energy screen, not mapped
            # path certification or a production default policy change.
            auto_planned_waypoints = None
            if os.environ.get("SWARM_BALANCE_AUTO_PLANNED_STATION") == "1":
                # Only an explicitly injected Environment RoutePlanner can
                # certify the geometry. Missing provider => HOLD, not a
                # straight-line fallback or a free station teleport.
                offers = []
                if callable(station_quote_provider):
                    for station in (self.known_stations or []):
                        if getattr(station, "closed", False):
                            continue
                        quote = station_quote_provider(station)
                        if (quote.get("feasible") and not quote.get("fallback")
                                and quote.get("affordable")):
                            offers.append((quote["total_wh"], quote["distance_m"],
                                           str(station.station_id), station, quote))
                if not offers:
                    self.flight_energy_blocked = True
                    self.flight_energy_block_reason = "no_affordable_planned_station"
                    self.is_free = False
                    return
                *_, nearest, chosen = min(offers, key=lambda item: item[:3])
                auto_planned_waypoints = [
                    (float(x), float(y), "waypoint")
                    for x, y in chosen["waypoints"]]
                self.charge_target_station_id = nearest.station_id
                self.flight_energy_blocked = False
                self.flight_energy_block_reason = None
            elif os.environ.get("SWARM_BALANCE_STATION_ENERGY_GATE") == "1":
                nearest = self._select_energy_affordable_direct_station()
                if nearest is None:
                    self.flight_energy_blocked = True
                    self.flight_energy_block_reason = "no_energy_affordable_station"
                    self.is_free = False
                    return
                self.flight_energy_blocked = False
                self.flight_energy_block_reason = None
            else:
                nearest = find_nearest_station(self.known_stations, (self.x, self.y))
            self._suspended_route = list(self.scheduled_position)
            self.scheduled_position = []
            self.is_free = False
            nest_pos = nearest.get_position()
            if (self.x, self.y) == nest_pos:
                self.awaiting_berth = True
                self.berth_station_id = nearest.station_id
            else:
                self.scheduled_position = (auto_planned_waypoints
                                           if auto_planned_waypoints is not None
                                           else [nest_pos])
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

            # E1：本步的沿航线风分量（正=逆风）。方向用"本步实际位移方向"，
            # 顺风/逆风因此随航段自动变号 —— 这是 wind_along 必须是分量而非幅值的原因。
            wind_along = self._wind_along_for(dx, dy, distance)

            # P2.2: evaluate the *actual next movement* before mutating
            # position, battery, task state or waypoint/event buffers.
            # Do not partially debit an impossible leg and still fly it.
            next_meters = min(distance, max_distance)
            if not self._flight_step_feasible(next_meters, wind_along):
                return

            if distance <= max_distance:
                # If we're close enough to target, move directly to it
                self.x = target_x
                self.y = target_y
                # 到达目标，消耗电量
                self.consume_battery(distance, wind_along)
                # Remove this target from schedule as we've reached it
                _popped = self.scheduled_position.pop(0)
                # #69-H3 D-iv：这是执行器真正消费航点的唯一离散事件点——append 进有序缓冲。
                # 只有这里（抵达并 pop）算消费；侧向飞过、整体改道、追加 nest 都不产生此事件。
                self.consumed_waypoints_this_step.append(_popped)
                if not self.scheduled_position:
                    if self._suspended_route or self._manual_charge_requested:
                        # 预判/人工换电改道：已抵达机巢，登记泊位请求等待环境仲裁。
                        # 人工换电可以发生在空闲机；若有挂起任务则换电后恢复任务航线。
                        self.is_free = False
                        if (os.environ.get("SWARM_BALANCE_CHARGE_TARGET_IDENTITY") == "1"
                                and getattr(self, "charge_target_station_id", None) is not None
                                and (self._manual_charge_requested
                                     or (os.environ.get("SWARM_BALANCE_AUTO_PLANNED_STATION") == "1"
                                         and bool(self._suspended_route)))):
                            # Exact requested ID, not a distance tie at
                            # co-located stations. Never silently swap elsewhere.
                            wanted_id = str(self.charge_target_station_id)
                            target_station = next(
                                (st for st in (self.known_stations or [])
                                 if str(st.station_id) == wanted_id), None)
                            if (target_station is not None
                                    and not getattr(target_station, "closed", False)
                                    and (self.x, self.y) == target_station.get_position()):
                                self.awaiting_berth = True
                                self.berth_station_id = target_station.station_id
                            else:
                                self.charge_target_hold_reason = "target_station_not_available"
                        else:
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
                self.consume_battery(actual_distance, wind_along)

    def _flight_step_feasible(self, distance, wind_along):
        """Fail-closed real-movement gate. No shadow battery or formula switch.

        This calls the single read-only Wh quote shared by consume_battery(),
        without calling or mutating the actual debit routine.
        A blocked proposed step records unmet REQUIRED Wh and debits zero,
        so required == debited + shortfall remains true.
        """
        # The exact same pure Wh source as consume_battery().
        required = self.quote_flight_energy_wh(distance, wind_along)
        if required > self.current_battery:
            self.flight_energy_blocked = True
            self.flight_energy_block_reason = "insufficient_step_energy"
            self.energy_insufficient = True
            self.last_energy_required_wh = required
            self.last_energy_debited_wh = 0.0
            self.last_energy_shortfall_wh = required
            self.is_free = False  # keep reserved; no free/unassigned phantom dispatch
            return False
        self.flight_energy_blocked = False
        self.flight_energy_block_reason = None
        return True

    def get_position(self):
        return (self.x, self.y)