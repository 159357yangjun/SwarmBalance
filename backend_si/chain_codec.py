"""任务链编解码器：排列编码 + 贪婪分割解码。

对应申请书原文
--------------
> 任务链优化引擎：采用启发式群体智能优化算法，结合**约束感知的任务序列构造方法**，
> 将任务分配与顺序规划统一建模为**排列编码**，经**贪婪分割解码**生成满足载重、
> 电量、时间窗约束的无人机任务链。

此前代码只优化「任务 → 无人机」的分配矩阵，单机内部顺序交给动态贪心重排，
任务链机制并未真正落地。本模块把「排列 → 有序任务链」这一步补上：

* **编码**：一条染色体 = 全部待排任务的一个排列（访问序）。
* **解码**：按排列顺序逐个把任务挂到某架无人机的链尾，挂载前检查三类硬约束
  （载重 / 电量 / 时间窗），并选择"增量代价最小"的机 —— 这就是贪婪分割：
  排列被若干"约束断点"自然切分为每机一段有序任务链。
* **评估**：解码后可按链推进时间轴，得到 makespan / 总超时量 / 总里程，
  作为群体智能算法（GA / PSO）的适应度来源。

物理口径与 `pso_scheduler.PSOOptimizer.evaluate_fitness` 保持一致：
速度用各机型真实 speed（米/秒）、时间用 env-step 秒、耗电用
`base * dist * (1 + penalty * load_ratio)`，低电量插入一次机巢往返。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

__all__ = [
    "ChainSolution",
    "ChainDecodeConfig",
    "greedy_split_decode",
    "evaluate_chains",
    "chain_cost",
]


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class ChainDecodeConfig:
    """贪婪分割解码的可调参数。"""

    # 单链最多串几个任务（对应 environment.task_chain.max_chain_tasks）
    max_chain_tasks: int = 3
    # 单链载重上限 = min(机型载重, 环境 multi_task_max_total_weight)
    max_total_weight: float = 30.0
    # 电量安全余量：链条预估耗电不得超过 当前电量 * (1 - reserve)
    battery_reserve: float = 0.1
    # 允许把任务挂到"会超时"的链上；为 False 时超时任务会被丢弃到 unassigned
    allow_tardy: bool = True
    # 时间窗违约容忍（秒）：预计送达时间超过 deadline 这么多就视为不可挂载
    tardy_tolerance: float = 600.0
    # 机巢换电耗时（秒）
    swap_time_seconds: float = 180.0
    # 增量代价权重：cost = Δ时间 + w_tardy * Δ超时 + w_dist * Δ里程
    w_tardy: float = 2.0
    w_dist: float = 0.01
    # 空闲链（该机一条任务都没有）额外奖励，鼓励把任务摊开到多机并行
    w_new_chain: float = -30.0


@dataclass
class ChainSolution:
    """解码结果。"""

    chains: List[List[int]] = field(default_factory=list)   # 每机有序任务下标
    unassigned: List[int] = field(default_factory=list)     # 无可行挂载点的任务
    finish_times: List[float] = field(default_factory=list)  # 每机链的完成时刻
    metrics: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _dist(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _battery_use(dist: float, load: float, capacity: float,
                 base: float, penalty: float) -> float:
    """与 drone.py / PSOOptimizer 同一口径的耗电估算（Wh）。"""
    load_ratio = 0.0 if capacity <= 0 else min(1.0, load / capacity)
    return float(base) * dist * (1.0 + float(penalty) * load_ratio)


class _DroneState:
    """解码过程中的单机状态（沿时间轴推进）。"""

    def __init__(self, info: Dict, cfg: ChainDecodeConfig, current_time: float):
        self.pos = tuple(info.get('position', (0.0, 0.0)))
        self.time = float(info.get('ready_time', current_time))
        self.load = 0.0
        self.capacity = float(info.get('capacity', 5.0))
        self.speed = max(1e-6, float(info.get('speed', 17.0)))
        self.battery = float(info.get('battery', info.get('battery_capacity', 1000.0)))
        self.battery_capacity = float(info.get('battery_capacity', 1000.0))
        self.base = float(info.get('battery_consumption_base', 0.06))
        self.penalty = float(info.get('battery_load_penalty_factor', 0.33))
        self.stations = info.get('charging_stations', []) or []
        self.cfg = cfg
        self.chain: List[int] = []
        self.distance = 0.0
        self.energy = 0.0

        if info.get('is_charging', False):
            # 正在换电：等换电结束再起飞，起飞时满电
            self.time += float(cfg.swap_time_seconds)
            self.battery = self.battery_capacity

    # 单链载重上限（与 environment 的拒单口径一致）
    def max_load(self) -> float:
        return min(self.capacity, self.cfg.max_total_weight)

    def can_carry(self, weight: float) -> bool:
        return self.load + weight <= self.max_load() + 1e-9

    def _swap_if_needed(self) -> None:
        """电量不足时插入一次机巢往返（与 drone.py 的自动换电行为对齐）。"""
        cfg = self.cfg
        if (self.battery_capacity > 0
                and self.battery / self.battery_capacity < 0.2
                and self.stations):
            nearest = min(self.stations,
                          key=lambda s: _dist(self.pos, tuple(s['position'])))
            st_pos = tuple(nearest['position'])
            d = _dist(self.pos, st_pos)
            self.energy += _battery_use(d, self.load, self.capacity,
                                        self.base, self.penalty)
            self.distance += d
            self.time += d / self.speed + float(cfg.swap_time_seconds)
            self.pos = st_pos
            self.battery = self.battery_capacity

    def try_append(self, task: Dict, task_idx: int, current_time: float
                   ) -> Optional[Dict[str, float]]:
        """试算把 task 挂到本机链尾的增量代价；不可行返回 None。

        返回字典含 Δ时间 / Δ超时 / Δ里程 / Δ耗电 与挂载后的完成时刻。
        """
        cfg = self.cfg
        weight = float(task.get('weight', 0.0))

        if len(self.chain) >= max(1, int(cfg.max_chain_tasks)):
            return None
        if not self.can_carry(weight):
            return None

        src = tuple(task['source'])
        dst = tuple(task['destination'])

        # 复制一份状态做"影子推演"，避免污染真实状态
        pos, t, load = self.pos, self.time, self.load
        battery = self.battery
        energy, distance = 0.0, 0.0
        deadline = task.get('deadline', None)
        if deadline is None:
            deadline = float('inf')

        # ① 电量不足 → 先去机巢换电
        if (self.battery_capacity > 0
                and battery / self.battery_capacity < 0.2
                and self.stations):
            nearest = min(self.stations,
                          key=lambda s: _dist(pos, tuple(s['position'])))
            st_pos = tuple(nearest['position'])
            d = _dist(pos, st_pos)
            energy += _battery_use(d, load, self.capacity, self.base, self.penalty)
            battery = max(0.0, battery - energy)
            distance += d
            t += d / self.speed + float(cfg.swap_time_seconds)
            pos = st_pos
            battery = self.battery_capacity

        # ② 当前位置 → 取货点 → 送达点
        d1 = _dist(pos, src)
        d2 = _dist(src, dst)
        trip = d1 + d2
        need = _battery_use(d1, load, self.capacity, self.base, self.penalty) + \
            _battery_use(d2, load + weight, self.capacity, self.base, self.penalty)
        if battery - need < self.battery_capacity * cfg.battery_reserve:
            return None

        distance += trip
        energy += need
        t += trip / self.speed
        load += weight

        # ③ 时间窗：超时量超过容忍度则视为不可行
        tardy = max(0.0, t - float(deadline))
        if (not cfg.allow_tardy or tardy > float(cfg.tardy_tolerance)) and \
                float(deadline) != float('inf'):
            return None

        d_time = t - self.time
        cost = d_time + cfg.w_tardy * tardy + cfg.w_dist * distance
        if not self.chain:
            cost += cfg.w_new_chain  # 负数权重：优先启用空闲机，摊开并行度

        return {
            'cost': cost,
            'd_time': d_time,
            'tardy': tardy,
            'distance': distance,
            'energy': energy,
            'finish': t,
            'end_pos': dst,
            'end_load': load,
            'end_battery': battery - need,
        }

    def commit(self, task_idx: int, delta: Dict[str, float]) -> None:
        self.chain.append(task_idx)
        self.time = delta['finish']
        self.pos = delta['end_pos']
        self.load = delta['end_load']
        self.battery = delta['end_battery']
        self.distance += delta['distance']
        self.energy += delta['energy']


# ---------------------------------------------------------------------------
# 贪婪分割解码
# ---------------------------------------------------------------------------

def greedy_split_decode(perm: Sequence[int],
                        drones_info: List[Dict],
                        tasks_info: List[Dict],
                        current_time: float,
                        cfg: Optional[ChainDecodeConfig] = None
                        ) -> ChainSolution:
    """把任务排列解码为「每机一条有序任务链」。

    :param perm: 任务下标的一个排列（长度可与 tasks_info 不同：允许只排部分任务）
    :param drones_info: 与 `PSOOptimizer.optimize` 同构的无人机信息列表
    :param tasks_info: 与 `PSOOptimizer.optimize` 同构的任务信息列表
    :param current_time: 当前 env-step（用作就绪时刻兜底）
    :param cfg: 解码参数，缺省用 `ChainDecodeConfig()`
    :return: `ChainSolution`
    """
    cfg = cfg or ChainDecodeConfig()
    states = [_DroneState(d, cfg, current_time) for d in drones_info]
    unassigned: List[int] = []

    for task_idx in perm:
        if not (0 <= int(task_idx) < len(tasks_info)):
            continue
        task = tasks_info[int(task_idx)]

        best_state, best_delta = None, None
        for st in states:
            delta = st.try_append(task, int(task_idx), current_time)
            if delta is None:
                continue
            if best_delta is None or delta['cost'] < best_delta['cost']:
                best_state, best_delta = st, delta

        if best_state is None:
            unassigned.append(int(task_idx))
        else:
            best_state.commit(int(task_idx), best_delta)

    sol = ChainSolution(
        chains=[st.chain for st in states],
        unassigned=unassigned,
        finish_times=[st.time for st in states],
    )
    sol.metrics = evaluate_chains(sol, drones_info, tasks_info, current_time, cfg)
    return sol


# ---------------------------------------------------------------------------
# 链级评估（供适应度与统计使用）
# ---------------------------------------------------------------------------

def evaluate_chains(sol: ChainSolution,
                    drones_info: List[Dict],
                    tasks_info: List[Dict],
                    current_time: float,
                    cfg: Optional[ChainDecodeConfig] = None) -> Dict[str, float]:
    """按链推进时间轴，统计 makespan / 超时 / 里程 / 能耗 / 链长分布。"""
    cfg = cfg or ChainDecodeConfig()
    makespan = 0.0
    total_tardy = 0.0
    total_distance = 0.0
    total_energy = 0.0
    chain_lengths: List[int] = []

    for drone_idx, chain in enumerate(sol.chains):
        if not chain:
            continue
        info = drones_info[drone_idx]
        st = _DroneState(info, cfg, current_time)
        finish_times: List[float] = []
        for task_idx in chain:
            delta = st.try_append(tasks_info[task_idx], task_idx, current_time)
            if delta is None:
                # 解码阶段已保证可行；评估阶段不再做约束松弛，直接累计已走部分
                break
            st.commit(task_idx, delta)
            finish_times.append(st.time)
        chain_lengths.append(len(chain))
        makespan = max(makespan, st.time)
        total_distance += st.distance
        total_energy += st.energy
        for task_idx, finish in zip(chain, finish_times):
            dl = tasks_info[task_idx].get('deadline', float('inf'))
            dl = float(dl) if dl is not None else float('inf')
            if dl != float('inf'):
                total_tardy += max(0.0, finish - dl)

    return {
        'makespan': float(makespan),
        'total_tardiness': float(total_tardy),
        'total_distance': float(total_distance),
        'total_energy': float(total_energy),
        'unassigned': float(len(sol.unassigned)),
        'avg_chain_len': float(np.mean(chain_lengths)) if chain_lengths else 0.0,
        'max_chain_len': float(max(chain_lengths)) if chain_lengths else 0.0,
        'used_drones': float(len(chain_lengths)),
    }


def chain_cost(metrics: Dict[str, float],
               w_makespan: float = 1.0,
               w_tardy: float = 1.0,
               w_dist: float = 0.001,
               w_unassigned: float = 1e4) -> float:
    """把链级指标压成标量代价（越小越好），用于 GA / PSO 的适应度。"""
    return (
        w_makespan * metrics.get('makespan', 0.0)
        + w_tardy * metrics.get('total_tardiness', 0.0)
        + w_dist * metrics.get('total_distance', 0.0)
        + w_unassigned * metrics.get('unassigned', 0.0)
    )
