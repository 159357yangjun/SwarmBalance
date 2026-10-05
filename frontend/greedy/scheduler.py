import math
import os
import random

from config.config_loder import get_shared_config
from matching import compute_match
from scheduling_interface import Scheduler


_CFG = get_shared_config()
_GREEDY_CFG = _CFG.get("environment", {}).get("greedy", {})
MAX_ASSIGNMENTS_PER_STEP = int(_GREEDY_CFG.get("max_assignments_per_step", 2))
CANDIDATE_LIMIT = int(_GREEDY_CFG.get("candidate_limit", 1))
ACCEPT_PROBABILITY = float(_GREEDY_CFG.get("accept_probability", 0.65))
MIN_BATTERY_RATIO = float(_GREEDY_CFG.get("min_battery_ratio", 0.6))
MAX_ACTIVE_DRONES_RATIO = float(_GREEDY_CFG.get("max_active_drones_ratio", 0.5))
# 匹配度权重：0 表示纯就近（同质基线行为），1 表示纯匹配度
MATCH_WEIGHT = float(_GREEDY_CFG.get("match_weight", 0.6))
DISTANCE_WEIGHT = float(_GREEDY_CFG.get("distance_weight", 0.4))
# Phase 1B-2：ETA 维度（reachability）的权重。
# **默认 0.0** ⇒ 不进 config、不改生产行为；非 0 只由实验经环境变量注入。
# 理由：默认非 0 会让"本次实现"本身改掉基线，Gate B（同 seed 零漂移）当场失效。
REACH_WEIGHT = float(os.environ.get("SWARM_BALANCE_REACH_WEIGHT", "0"))
# reachability 的归一分母：复用 matching.speed_match 里 urgency 的同一个 300（matching.py:44），
# 不另起一个数 —— 两个时效量必须同尺度，否则新分量会劫持既有平衡。
REF_SLACK_SECONDS = 300.0
# 体积折算为等效重量的系数（体积不能与重量 1:1 相加，否则轻载机型几乎无法接单）
VOLUME_TO_LOAD_FACTOR = 0.3



class GreedyScheduler(Scheduler):
    def act(self, observation, current_time=0.0):
        """稳定调度接口：贪心策略无状态、不依赖 current_time，直接复用静态就近+匹配逻辑。"""
        return self.schedule_for_drone(observation)

    @staticmethod
    def euclidean_distance(pos1, pos2):
        """计算两点之间的欧氏距离"""
        if isinstance(pos1, tuple) and isinstance(pos2, tuple):
            return math.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)
        return float('inf')

    @staticmethod
    def schedule_for_drone(observation):
        """
        贪心调度算法：为所有空闲无人机分配任务
        1. 从观察空间中获取无人机位置、空闲状态、电量信息和未分配任务信息
        2. 为每个空闲且电量充足（>=20%）的无人机分配一个离当前位置最近的任务
        返回: {drone_index: [assigned_task_id]} 字典（每个无人机最多分配一个任务）
        """
        drone_positions = observation['drone_positions']
        # 过滤掉 padding 占位任务，避免分配无效的 '__pad_X' task_id
        unassigned_tasks_info = [
            t for t in observation['unassigned_tasks']
            if not str(t.get('task_id', '')).startswith('__pad_')
        ]
        drone_free_masks = observation['drone_free_masks']

        if not unassigned_tasks_info:
            return {}

        assignments = {}
        max_assignments_per_step = max(1, MAX_ASSIGNMENTS_PER_STEP)
        candidate_limit = max(1, CANDIDATE_LIMIT)
        accept_probability = min(max(ACCEPT_PROBABILITY, 0.0), 1.0)
        min_battery_ratio = min(max(MIN_BATTERY_RATIO, 0.0), 1.0)
        max_active_drones_ratio = min(max(MAX_ACTIVE_DRONES_RATIO, 0.0), 1.0)

        drone_is_free = observation.get('drone_is_free', [])
        drone_batteries = observation.get('drone_batteries', [])
        drone_capabilities = observation.get('drone_capabilities', [])
        max_active_drones = max(1, int(math.ceil(len(drone_positions) * max_active_drones_ratio)))

        # 为每个空闲且电量充足的无人机分配任务
        for drone_idx, (drone_pos, free_mask) in enumerate(zip(drone_positions, drone_free_masks)):
            if len(assignments) >= max_assignments_per_step:
                break

            if drone_idx >= max_active_drones:
                continue

            # 优先使用 observation 中的 drone_is_free 字段（不受 padding 影响）
            if drone_is_free and len(drone_is_free) > drone_idx:
                if not drone_is_free[drone_idx]:
                    continue
            elif not all(free_mask):  # fallback: 无 drone_is_free 时降级到 free_mask 判断
                continue

            if drone_batteries and len(drone_batteries) > drone_idx:
                battery = drone_batteries[drone_idx]
                capacity = float(battery.get('capacity', 1.0))
                current = float(battery.get('current', 0.0))
                if capacity > 0 and (current / capacity) < min_battery_ratio:
                    continue

            # 随机丢弃一部分可分配机会，降低贪心吞吐
            if random.random() > accept_probability:
                continue

            # 如果没有任务可分配，跳过
            if not unassigned_tasks_info:
                break

            current_pos = tuple(drone_pos)

            candidate_tasks = unassigned_tasks_info[:candidate_limit]

            # 异构机型：用"能力-需求匹配度 + 距离"综合评分选任务，而非纯就近
            cap = drone_capabilities[drone_idx] if drone_idx < len(drone_capabilities) else {}

            # 硬过滤：载重超限的任务不可分配，避免"接单后又被 env 静默拒绝"的死循环，
            # 让重货流向真正能装的重载机型。同质机型（无 drone_type）不过滤，保持基线就近行为。
            feasible_tasks = [
                t for t in candidate_tasks
                if GreedyScheduler._is_feasible(cap, t)
            ]
            if not feasible_tasks:
                continue

            # 候选集内部对到取货点距离做归一化，使距离邻近分落在 0~1，
            # 与匹配分量纲一致（最近为 1，最远为 0）。
            provider = observation.get("route_cost_provider")
            if provider is not None:
                dists = provider.batch(current_pos, [tuple(t['source']) for t in feasible_tasks])
            else:
                dists = [
                    GreedyScheduler.euclidean_distance(current_pos, tuple(t['source']))
                    for t in feasible_tasks
                ]
            _d = {t["task_id"]: d for t, d in zip(feasible_tasks, dists)}
            min_d, max_d = min(dists), max(dists)

            def _proximity(d):
                if max_d <= min_d:
                    return 1.0
                return 1.0 - (d - min_d) / (max_d - min_d)

            best_task = max(
                feasible_tasks,
                key=lambda t: GreedyScheduler._score_task(
                    cap, current_pos, t, _proximity(_d[t["task_id"]]), provider=provider
                )
            )

            # 分配任务
            assignments[drone_idx] = [best_task['task_id']]
            # 从输入列表中移除已分配的任务
            unassigned_tasks_info.remove(best_task)

        return assignments

    @staticmethod
    def _is_feasible(cap, task):
        """硬性载重可行性判断。

        无机型信息（同质机型）时视为总是可行，保持基线"就近"行为不变；
        有异构机型信息时，任务重量不得超过该机剩余载重（与 env.step 的
        只按重量拒绝超载规则一致）。
        """
        if not cap or cap.get('drone_type') is None:
            return True
        remaining_capacity = float(cap.get('remaining_capacity', cap.get('carrying_capacity', 1.0)))
        return float(task.get('weight', 0.0)) <= remaining_capacity

    @staticmethod
    def _reachability(provider, drone_pos, task, speed_m_per_s):
        """ETA 维度：这架机多久能赶到取货点，相对任务剩余时限有多从容。

            slack = remaining_time − ETA          （还能等多久 vs 我要飞多久）
            reach = clamp(slack / REF_SLACK_SECONDS, 0, 1)   ∈[0,1]，越大越从容

        调用方按 `score += REACH_WEIGHT * (1 - reach)` 使用 ⇒ 越紧张的任务越该被抢走。

        为什么不是字面的 `ETA/remaining_time`（设计文档 §B.1 实测否掉了它）：deadline 生成式是
        `distance/14 + 420 + weight×24`（task.py:520-527），那个 420 s 常数比航段项大一到两个
        数量级 ⇒ 裸比值在真世界上中位数只有 0.107、>1 的比例 0%，测的是"SLA 常数有多宽松"，
        不是"赶不赶得上"。slack 形式减掉那个常数，组内才有信息。

        三种边界（都必须显式处理，否则分量会悄悄失效）：
          · remaining_time 为 inf（无截止时间的真实任务）⇒ 取中性 0.5，不奖不罚；
          · slack < 0（注定赶不上）⇒ clamp 到 0 = 奖惩最强，但由调用处单独计数，
            否则"已经有多少单注定超时"看不见；
          · provider 为 None（同质机型走纯就近分支）⇒ 返回 None，让调用处保持原行为。
        """
        if provider is None:
            return None
        remaining_time = task.get('remaining_time', float('inf'))
        if remaining_time == float('inf'):
            return 0.5
        eta = provider.eta(drone_pos, tuple(task['source']), speed_m_per_s)
        slack = float(remaining_time) - eta
        return max(0.0, min(1.0, slack / REF_SLACK_SECONDS))

    @staticmethod
    def _score_task(cap, drone_pos, task, proximity=0.0, provider=None, reach_weight=None):
        """综合评分 = 匹配度权重 * 能力匹配分 + 距离权重 * 距离邻近分 [+ ETA 权重 * 紧迫分]。

        匹配分由 matching.compute_match 给出（考虑载重/速度/续航与任务
        重量/体积/时效/距离的匹配）；邻近分为候选集内归一化后的距离分。

        Phase 1B-2：`reach_weight` 默认取模块常量（=环境变量注入值，缺省 0）。
        **既有两项一字未动** —— 新分量是纯加法，权重为 0 时表达式与改前代数等价（门 G11）。
        """
        if not cap or cap.get('drone_type') is None:
            # 无能力信息或同质机型时退化为就近（保持原基线行为，便于公平对比）
            return -GreedyScheduler.euclidean_distance(drone_pos, tuple(task['source']))

        remaining_capacity = float(cap.get('remaining_capacity', cap.get('carrying_capacity', 1.0)))
        # 硬性可行性：载重装不下直接判不可行（-inf），与 env.step 只按重量拒绝超载一致。
        # 避免轻载机型"抢走"重货后又因超载被静默丢弃，白白占名额并饿死重载机型。
        if float(task.get('weight', 0.0)) > remaining_capacity:
            return float('-inf')

        # Phase 1B-1：provider 存在时【只】替换这两段距离的口径；energy/range 参数一律原样
        # 传下去 —— 那是 1B-3 的范围。ETA 从 1B-2 起经 provider.eta() 取数（同源，见下）。
        if provider is not None:
            source_dist = provider.distance(drone_pos, tuple(task['source']))
            route_dist = provider.distance(tuple(task['source']), tuple(task['destination']))
        else:
            source_dist = GreedyScheduler.euclidean_distance(drone_pos, tuple(task['source']))
            route_dist = float(task.get('route_distance', 0.0))
        total_distance = source_dist + route_dist
        remaining_time = task.get('remaining_time', float('inf'))

        required_load = float(task.get('weight', 0.0)) + VOLUME_TO_LOAD_FACTOR * float(task.get('volume', 0.0))

        match_score = compute_match(
            required_load,
            remaining_capacity,
            float(cap.get('speed', 200.0)),
            remaining_time,
            float(cap.get('battery_capacity', 15000.0)),
            float(cap.get('battery_consumption_base', 0.5)),
            total_distance,
        )

        w_reach = REACH_WEIGHT if reach_weight is None else float(reach_weight)
        if w_reach:
            # speed 用该机自己的巡航速度（cap['speed']），不是全局常量：ETA 的意义就是
            # "这架机赶不赶得上"，用别人的速度算就等于没算。
            reach = GreedyScheduler._reachability(provider, drone_pos, task,
                                                  float(cap.get('speed', 200.0)))
            if reach is None:
                return MATCH_WEIGHT * match_score + DISTANCE_WEIGHT * proximity
            return (MATCH_WEIGHT * match_score + DISTANCE_WEIGHT * proximity
                    + w_reach * (1.0 - reach))
        return MATCH_WEIGHT * match_score + DISTANCE_WEIGHT * proximity


    @staticmethod
    def schedule_all_drones(drones, tasks):
        """
        为所有无人机调度任务
        返回: {drone: [assigned_tasks]} 字典
        """
        assignments = {drone: [] for drone in drones}
        unassigned_tasks = list(tasks)  # 复制列表，避免修改原列表
        
        # 创建观察空间格式的任务信息
        unassigned_tasks_info = []
        for task in unassigned_tasks:
            unassigned_tasks_info.append({
                'task_id': task.task_id,
                'source': list(task.get_source()),
                'destination': list(task.get_destination()),
                'remaining_time': float('inf'),  # 简化处理，不使用剩余时间
                'priority': task.get_priority(),
                'weight': task.get_weight()
            })
        
        # 创建观察空间字典
        observation = {
            'drone_positions': [list(d.get_position()) for d in drones],
            'drone_free_masks': [[d.is_free for _ in unassigned_tasks_info] for d in drones],
            'unassigned_tasks': unassigned_tasks_info,
        }

        task_id_map = {task.task_id: task for task in unassigned_tasks}
        id_assignments = GreedyScheduler.schedule_for_drone(observation)

        for drone_idx, task_ids in id_assignments.items():
            if drone_idx >= len(drones):
                continue
            drone = drones[drone_idx]
            assigned_tasks = [task_id_map[tid] for tid in task_ids if tid in task_id_map]
            assignments[drone] = assigned_tasks

            if assigned_tasks:
                route = [drone.get_position()] + [t.get_destination() for t in assigned_tasks]
                drone.schedule_route(route, assigned_tasks[0].task_id)
        
        return assignments


def greedy_action_from_observation(observation):
    """Callable greedy policy entry for both frontend and backend usage."""
    return GreedyScheduler.schedule_for_drone(observation)
