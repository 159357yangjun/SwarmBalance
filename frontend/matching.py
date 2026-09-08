"""
异构无人机能力-任务需求匹配度模块。

把无人机机型特性（载重、速度、续航、能耗）与任务需求（重量、体积、
时效、距离）量化匹配，输出 0~1 的匹配度，作为任务分配的启发式依据。

匹配度 = w_load*载重匹配 + w_speed*速度-时效匹配 + w_range*续航-距离匹配
"""
import math

DEFAULT_WEIGHTS = {"load": 0.4, "speed": 0.3, "range": 0.3}
# 速度归一化参考上限（m/s），用于把各机型速度映射到 0~1
SPEED_MAX = 320.0
# 续航估算参考距离（米），用于把飞行距离映射到 0~1
REF_RANGE = 80000.0


def load_match(required_load, remaining_capacity):
    """载重匹配：所需运力越接近剩余载重上限（且不超载）得分越高。

    容量刚够（利用率约 0.9）最佳：既装得下，又不大材小用。

    注意：required_load 含"0.3×体积"的折算，可能略超 remaining_capacity，
    但此时重量仍装得下（真实超载由上游按重量硬过滤）。不能在此硬清零，否则
    会把"重 4kg 但体积稍大"的中型任务从长续航型(4kg)里错误剔除、挤给重载机。
    而是让利用率上限自然压低得分：util > 1.8 时公式为负，被 max(0,·) 归零。
    """
    if remaining_capacity <= 0:
        return 0.0
    utilization = required_load / remaining_capacity
    return max(0.0, min(1.0, 1.0 - abs(utilization - 0.9) / 0.9))


def speed_match(speed, remaining_time):
    """速度-时效匹配：任务越紧迫（剩余时间越短），高速机得分越高。

    不紧迫的任务速度评分保持中性（约 0.5），避免高速机无条件占据所有订单，
    导致慢速重载/长续航机型空转。
    """
    speed_norm = min(1.0, speed / SPEED_MAX)
    if remaining_time is None or remaining_time == float("inf"):
        urgency = 0.0
    else:
        urgency = max(0.0, min(1.0, 1.0 - remaining_time / 300.0))
    return (1.0 - urgency) * 0.5 + urgency * speed_norm


def range_match(battery_capacity, consumption_base, total_distance):
    """续航-距离匹配：飞行距离越大，长续航（大电池/低能耗）机型得分越高。"""
    if consumption_base <= 0:
        consumption_base = 1e-6
    est_range = battery_capacity / consumption_base
    if total_distance <= 0:
        return 0.5
    if est_range < total_distance:
        return 0.0
    ratio = total_distance / est_range
    return max(0.0, min(1.0, 1.0 - abs(ratio - 0.5) / 0.5))


def compute_match(
    required_load,
    remaining_capacity,
    speed,
    remaining_time,
    battery_capacity,
    consumption_base,
    total_distance,
    weights=None,
):
    """汇总匹配度（0~1），越高表示该机型与该任务越匹配。"""
    w = weights or DEFAULT_WEIGHTS
    return (
        w["load"] * load_match(required_load, remaining_capacity)
        + w["speed"] * speed_match(speed, remaining_time)
        + w["range"] * range_match(battery_capacity, consumption_base, total_distance)
    )