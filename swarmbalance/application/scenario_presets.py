"""答辩/演示场景预设。

这些预设只负责：
1) 对 ``config/simulation.json`` 做可逆 patch；
2) 指定推荐算法、Seed、自动任务流状态；
3) 提供少量可复现的人工任务与“下一幕”演示脚本。

预设不是另一套仿真器。应用后仍使用同一个 Environment + Scheduler；因此演示、
自由仿真与批量实验共享同一套物理约束和算法实现。
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


_PRESETS: Dict[str, Dict[str, Any]] = {
    "medical_peak": {
        "name": "应急医疗高峰",
        "description": "突出异构能力匹配、紧急任务插入与任务链重规划。适合先展示候选机解释，再单步观察 GA 的真实分配。",
        "algorithm": "ga",
        "seed": 241,
        "task_generation_paused": True,
        "config_patch": {
            "data_source": {"type": "random"},
            "environment": {"num_drones": 10, "episode_max_steps": 2400},
            "heterogeneous": {"enabled": True, "fleet_mix": {"light_express": 5, "standard_cargo": 3, "heavy_cargo": 2}},
            "task_generation": {"realistic": {"total_tasks": 50, "initial_task_count": 8, "peak_probability": 0.85, "peak_steps_per_task": 16, "off_peak_steps_per_task": 38}},
            "nest": {"berths": 2, "arbitration_policy": "priority"},
            "task": {"deadline_offset_min": 600, "deadline_offset_max": 1800},
        },
        "initial_tasks": [
            {"task_id": "demo_medical_1", "category": "emergency", "priority": 3, "weight": 1.0, "volume": 0.2, "deadline_offset": 260},
            {"task_id": "demo_bulk_1", "category": "bulk", "priority": 2, "weight": 12.0, "volume": 2.4, "deadline_offset": 900},
            {"task_id": "demo_normal_1", "category": "normal", "priority": 1, "weight": 2.0, "volume": 0.5, "deadline_offset": 780},
        ],
        "script": [
            {"label": "执行首轮分配", "action": "step", "count": 1, "note": "让 GA 对当前任务池完成一次真实调度。"},
            {"label": "插入新的 P3 急救任务", "action": "inject_task", "task": {"task_id": "demo_medical_2", "category": "emergency", "priority": 3, "weight": 1.3, "volume": 0.2, "deadline_offset": 220}, "note": "运行中插入更紧急的新任务，不重置环境。"},
            {"label": "触发滚动重调度", "action": "step", "count": 1, "note": "观察新任务如何进入当前机队任务链。"},
            {"label": "推进执行过程", "action": "step", "count": 12, "note": "观察配送、换电和任务链状态变化。"},
        ],
    },
    "nest_congestion": {
        "name": "机巢拥堵与优先级仲裁",
        "description": "将泊位压缩为 1，突出有限地面资源、排队和动态优先级仲裁。",
        "algorithm": "ga",
        "seed": 352,
        "task_generation_paused": False,
        "config_patch": {
            "data_source": {"type": "random"},
            "environment": {"num_drones": 12, "episode_max_steps": 2600},
            "heterogeneous": {"enabled": True, "fleet_mix": {"light_express": 4, "standard_cargo": 5, "heavy_cargo": 3}},
            "task_generation": {"realistic": {"total_tasks": 80, "initial_task_count": 16, "peak_probability": 0.95, "peak_steps_per_task": 10, "off_peak_steps_per_task": 24}},
            "nest": {"berths": 1, "swap_time_seconds": 240, "arbitration_policy": "priority", "arbitration_weight_battery": 1.0, "arbitration_weight_wait": 0.15, "arbitration_weight_urgency": 1.2},
            "charging_stations": [
                {"station_id": 0, "x": 357600.0, "y": 3462308.0, "swap_time_seconds": 240, "berths": 1},
                {"station_id": 1, "x": 358744.0, "y": 3462283.0, "swap_time_seconds": 240, "berths": 1},
                {"station_id": 2, "x": 359190.0, "y": 3462301.0, "swap_time_seconds": 240, "berths": 1},
                {"station_id": 3, "x": 359365.0, "y": 3463070.0, "swap_time_seconds": 240, "berths": 1},
                {"station_id": 4, "x": 358639.0, "y": 3462878.0, "swap_time_seconds": 240, "berths": 1},
            ],
        },
        "initial_tasks": [],
        "script": [
            {"label": "推进至机队开始执行", "action": "step", "count": 8, "note": "先让多架无人机进入配送状态。"},
            {"label": "调两架无人机同时补能", "action": "charge_two_drones", "note": "人工触发资源竞争，但换电仍走真实泊位排队。"},
            {"label": "推进至泊位排队", "action": "step", "count": 18, "note": "观察有限泊位形成队列以及优先级分数。"},
            {"label": "继续推进仲裁", "action": "step", "count": 18, "note": "观察泊位释放后下一架无人机如何被仲裁接入。"},
        ],
    },
    "resilience": {
        "name": "故障韧性与局部重规划",
        "description": "运行中制造无人机故障和机巢关闭，演示任务回收、重新分配与补能改道。",
        "algorithm": "ga",
        "seed": 463,
        "task_generation_paused": False,
        "config_patch": {
            "data_source": {"type": "random"},
            "environment": {"num_drones": 10, "episode_max_steps": 2400},
            "heterogeneous": {"enabled": True, "fleet_mix": {"light_express": 4, "standard_cargo": 4, "heavy_cargo": 2}},
            "task_generation": {"realistic": {"total_tasks": 60, "initial_task_count": 14, "peak_probability": 0.8, "peak_steps_per_task": 16, "off_peak_steps_per_task": 34}},
            "nest": {"berths": 2, "arbitration_policy": "priority"},
        },
        "initial_tasks": [],
        "script": [
            {"label": "推进至存在忙碌无人机", "action": "step", "count": 8, "note": "先形成正在执行的任务链。"},
            {"label": "故障一架忙碌无人机", "action": "fault_busy_drone", "note": "其未完成任务回到待调度池。"},
            {"label": "执行一次重新分配", "action": "step", "count": 1, "note": "让当前算法处理被回收的任务。"},
            {"label": "关闭一个高负载机巢", "action": "close_busy_nest", "note": "新补能请求停止进入该机巢，相关无人机自动改道。"},
            {"label": "推进观察改道与恢复能力", "action": "step", "count": 12, "note": "观察故障后的系统继续运行。"},
            {"label": "恢复全部异常资源", "action": "restore_incidents", "note": "恢复停飞无人机和关闭机巢。"},
        ],
    },
    "balanced": {
        "name": "标准综合演示",
        "description": "较均衡的任务密度、异构机队和机巢配置，适合作为普通自由仿真的起点。",
        "algorithm": "ga",
        "seed": 100,
        "task_generation_paused": False,
        "config_patch": {
            "data_source": {"type": "random"},
            "environment": {"num_drones": 10, "episode_max_steps": 3600},
            "heterogeneous": {"enabled": True, "fleet_mix": {"light_express": 5, "standard_cargo": 3, "heavy_cargo": 2}},
            "task_generation": {"realistic": {"total_tasks": 60, "initial_task_count": 12, "peak_probability": 0.7, "peak_steps_per_task": 20, "off_peak_steps_per_task": 45}},
            "nest": {"berths": 2, "swap_time_seconds": 180, "arbitration_policy": "priority"},
        },
        "initial_tasks": [],
        "script": [
            {"label": "推进 10 步", "action": "step", "count": 10, "note": "观察普通订单流和异构机队分工。"},
            {"label": "插入一条紧急任务", "action": "inject_task", "task": {"task_id": "demo_urgent", "category": "urgent", "priority": 3, "weight": 1.5, "volume": 0.3, "deadline_offset": 300}, "note": "观察滚动任务插入。"},
            {"label": "执行一次重调度", "action": "step", "count": 1, "note": "让当前算法处理新增任务。"},
        ],
    },
}


def keys() -> List[str]:
    return list(_PRESETS)


def get(key: str) -> Dict[str, Any]:
    if key not in _PRESETS:
        raise KeyError(key)
    return deepcopy(_PRESETS[key])


def list_presets() -> List[Dict[str, Any]]:
    rows = []
    for key, raw in _PRESETS.items():
        rows.append({
            "key": key,
            "name": raw["name"],
            "description": raw["description"],
            "algorithm": raw["algorithm"],
            "seed": raw["seed"],
            "script_steps": len(raw.get("script", [])),
        })
    return rows
