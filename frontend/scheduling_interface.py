"""稳定调度接口 schema —— 算法与环境解耦。

本模块是"调度算法"与"仿真环境"之间唯一的一份契约。环境每步把当前状态打包成
观察空间（Observation）交给算法；算法读观察、返回动作空间（Action）；环境只认
这份动作，不感知算法内部实现。反过来，算法也不得持有环境引用、不直接调用环境
方法。这样算法（Greedy / PSO / GA / 未来对接的真实企业调度器）可以在同一套
schema 下自由替换、独立测试。

schema 版本号 SCHEMA_VERSION 随接口字段语义变化而递增，用于对接真实系统时的
兼容性判定。

Observation schema（环境 `environment.Environment._obs()` 产出，算法据此读取）：
    drone_positions    : List[List[float]]        每架机坐标 [x, y]
    unassigned_tasks   : List[Dict]               待分配任务，字段：
                          task_id / source / destination / remaining_time /
                          priority / weight / volume / category /
                          route_distance / source_to_warehouse
    drone_free_masks   : List[List[bool]]         每架机对各任务的"可接"掩码（含同源规则）
    drone_is_free      : List[bool]               每架机当前是否空闲
    drone_batteries    : List[Dict]               每架机 {current, capacity, is_charging}
    drone_loads        : List[Dict]               每架机 {current, capacity}
    drone_capabilities : List[Dict]               每架机机型能力
                          {drone_type, speed, battery_capacity,
                           battery_consumption_base, load_penalty_factor,
                           carrying_capacity, remaining_capacity}
    charging_station   : Dict                      单站（向后兼容）{position, charging_power}
    charging_stations  : List[Dict]                多站 {station_id, position, charging_power}

Action schema（算法返回，环境执行）：
    {drone_index:int -> [task_id:str, ...]}
    语义：本步把括号内的任务派发给对应编号的无人机。环境会做载重/同源等可行性
    校验，不可行的分配会被拒绝；算法只声明意图，不直接操作环境内部对象。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List

__all__ = ["SCHEMA_VERSION", "Action", "Scheduler"]

# 观察/动作契约版本。改动任何字段的语义时递增。
SCHEMA_VERSION = "1.0"

# 动作空间：{ drone_index -> [task_id, ...] }
Action = Dict[int, List[str]]


class Scheduler(ABC):
    """任意调度算法的统一入口。

    实现类只需实现 act()：读 observation、返回 action。继承后多 episode 复用
    同一实例时可覆盖 reset() 清空内部状态，覆盖 get_stats() 对外暴露运行统计。
    """

    @abstractmethod
    def act(self, observation: Dict[str, Any], current_time: float) -> Action:
        """根据观察输出动作。

        :param observation: 完整观察空间（见上方 Observation schema）。
        :param current_time: 当前仿真步（供 PSO/GA 等预测式算法评估时延/能耗）。
        :return: {drone_index: [task_id, ...]} 动作字典。
        """

    def reset(self) -> None:
        """重置算法内部状态。默认无操作；有状态算法应覆盖。"""

    def get_stats(self) -> Dict[str, Any]:
        """返回算法运行统计（可选）。默认空字典。"""
        return {}