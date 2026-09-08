import math
from config.config_loder import get_shared_config


class ChargingStation:
    """机巢（换电站）模型：有限泊位 + 换电（降落整组更换电池，非慢充）。

    真实交付机巢（美团/大疆 Dock/顺丰丰翼）为自动换电机巢：每个机巢有有限个
    「泊位」(berths)，同一时刻每个泊位只能服务一架无人机的「降落-换电-起飞」
    全流程；泊位被占满时，后续无人机进入排队，由环境按其紧迫度动态仲裁
    （见 environment.py 的 _manage_berths）。charging_power 字段仅作向后兼容保留。
    """

    def __init__(self, station_id, x, y, charging_power=50, swap_time_seconds=180, berths=2):
        self.station_id = station_id
        self.x = x
        self.y = y
        self.charging_power = charging_power
        self.swap_time_seconds = float(swap_time_seconds)
        self.berths = max(1, int(berths))  # 泊位数量（>=1）
        self.occupied = 0                  # 当前占用泊位数（运行时状态）

    def get_position(self):
        return (self.x, self.y)

    def has_berth(self):
        """是否还有空余泊位。"""
        return self.occupied < self.berths

    def free_berths(self):
        """当前空余泊位数。"""
        return self.berths - self.occupied

    def occupy(self):
        """占用一个泊位（调用前应先 has_berth 判断）。"""
        self.occupied = min(self.berths, self.occupied + 1)

    def vacate(self):
        """释放一个泊位。"""
        self.occupied = max(0, self.occupied - 1)


def _distance(pos1, pos2):
    return math.sqrt((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2)


def build_default_charging_stations():
    """从配置文件构建充电站列表，支持新旧两种配置格式"""
    cfg = get_shared_config()
    berths_default = int(cfg.get("nest", {}).get("berths", 2))

    # 新格式: "charging_stations" 数组
    stations_array = cfg.get("charging_stations", None)
    if stations_array:
        stations = []
        for s in stations_array:
            stations.append(ChargingStation(
                station_id=int(s.get("station_id", 0)),
                x=float(s.get("x", 356000.0)),
                y=float(s.get("y", 3463000.0)),
                charging_power=float(s.get("charging_power", 50)),
                swap_time_seconds=float(s.get("swap_time_seconds", 180)),
                berths=int(s.get("berths", berths_default)),
            ))
        return stations

    # 旧格式兼容: "charging_station" 单站
    old_cfg = cfg.get("charging_station", {})
    if old_cfg:
        return [ChargingStation(
            station_id=int(old_cfg.get("station_id", 0)),
            x=float(old_cfg.get("x", 356000.0)),
            y=float(old_cfg.get("y", 3463000.0)),
            charging_power=float(old_cfg.get("charging_power", 50)),
            swap_time_seconds=float(old_cfg.get("swap_time_seconds", 180)),
            berths=int(old_cfg.get("berths", berths_default)),
        )]

    # 兜底默认
    return [ChargingStation(station_id=0, x=356000.0, y=3463000.0,
                            charging_power=50, swap_time_seconds=180,
                            berths=berths_default)]


def find_nearest_station(stations, position):
    """给定位置，找到最近的充电站"""
    if not stations:
        return None
    return min(stations, key=lambda s: _distance(position, s.get_position()))


DEFAULT_CHARGING_STATIONS = build_default_charging_stations()
# 向后兼容：DEFAULT_CHARGING_STATION 始终指向第一个充电站
DEFAULT_CHARGING_STATION = DEFAULT_CHARGING_STATIONS[0] if DEFAULT_CHARGING_STATIONS else None
