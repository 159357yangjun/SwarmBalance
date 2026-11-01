"""
粒子群优化算法（PSO）用于无人机任务调度
优化目标：任务准时率、平均时延

本文件包含两个类：
  - PSOOptimizer：PSO 算法核心，纯优化器（输入 drones+tasks → 输出分配）
  - PSOScheduler：对外调度器，事件驱动，双通道 + 内层动态贪心，
                  内部通过 PSOOptimizer 完成批量分配
配置参数集中在 config/schedulers.yaml。
"""
import os
import numpy as np
import math
import copy
import yaml
from typing import List, Dict, Tuple, Optional

from swarmbalance.scheduling.matching import compute_match as _compute_match
VOLUME_TO_LOAD_FACTOR = 0.3


class Particle:
    """
    粒子类：
      position  ∈ R^(num_tasks, num_drones) 实值偏好矩阵
      assignment[i] = argmax_d position[i, d] 得到任务 i 分配的无人机
    """

    def __init__(self,
                 num_drones: int,
                 num_tasks: int,
                 v_max: float = 4.0,
                 pos_max: float = 5.0):
        """
        :param num_drones: 无人机数量
        :param num_tasks: 任务数量
        :param v_max: velocity 每个分量的绝对值上限
        :param pos_max: position 每个分量的绝对值上限（防数值发散）
        """
        self.num_drones = num_drones
        self.num_tasks = num_tasks
        self.v_max = v_max
        self.pos_max = pos_max

        # 偏好矩阵 [task, drone]，连续实值
        self.position = np.random.uniform(-1.0, 1.0, (num_tasks, num_drones))
        self.velocity = np.random.uniform(-0.5, 0.5, (num_tasks, num_drones))

        # 个体最优快照（完整偏好矩阵，不是 assignment 向量）
        self.best_position = self.position.copy()
        self.best_fitness = float('-inf')

        # 当前适应度
        self.fitness = float('-inf')

    def update_velocity(self, global_best_position, w=0.7, c1=1.5, c2=1.5):
        """
        标准连续 PSO 速度更新（在偏好矩阵上做元素级运算）
        :param global_best_position: 全局最优偏好矩阵 (num_tasks, num_drones)
        """
        r1 = np.random.random((self.num_tasks, self.num_drones))
        r2 = np.random.random((self.num_tasks, self.num_drones))

        cognitive = c1 * r1 * (self.best_position - self.position)
        social = c2 * r2 * (global_best_position - self.position)
        self.velocity = w * self.velocity + cognitive + social

        self.velocity = np.clip(self.velocity, -self.v_max, self.v_max)

    def update_position(self):
        """位置更新：偏好矩阵直接累加 velocity，clip 防发散"""
        self.position = self.position + self.velocity
        self.position = np.clip(self.position, -self.pos_max, self.pos_max)


class PSOOptimizer:
    """粒子群优化算法核心：给定无人机集合和任务集合，输出 task→drone 分配"""

    def __init__(self,
                 num_particles=30,
                 max_iterations=50,
                 w=0.7,
                 c1=1.5,
                 c2=1.5,
                 v_max: float = 4.0,
                 pos_max: float = 5.0,
                 weights: Optional[Dict[str, float]] = None,
                 seed: Optional[int] = None,
                 battery_consumption_base: float = 0.5,
                 battery_load_penalty_factor: float = 0.3,
                 battery_low_threshold: float = 0.2,
                 env_step_seconds: float = 1.0,
                 swap_time_seconds: float = 180.0,
                 warm_start: bool = True,
                 warm_start_seeds: int = 3):
        """
        初始化PSO调度器
        :param num_particles: 粒子数量
        :param max_iterations: 最大迭代次数
        :param w: 惯性权重
        :param c1: 个体学习因子
        :param c2: 社会学习因子
        :param v_max: 粒子 velocity 每个分量的绝对值上限
        :param pos_max: 粒子 position 每个分量的绝对值上限（防数值发散）
        :param weights: 适应度函数权重字典，支持扩展
                       默认: {'on_time_rate': 0.4, 'avg_delay': 0.4, 'energy': 0.2}
        :param seed: 随机数种子，用于实验可复现性
        :param battery_consumption_base: 单位距离基础耗电（与 frontend/drone.py 保持一致）
        :param battery_load_penalty_factor: 满载相对空载的耗电增量比例
        :param battery_low_threshold: 低电量阈值（占容量比例），低于则触发去充电站
        :param env_step_seconds: 1 个 env-step 对应的真实秒数（与 frontend/drone.py
                                 中 DRONE_TIME_STEP 同义；用于把 drone 的"米/秒"、
                                 充电站的"Wh/秒"换算到 env-step 量纲，使 fitness
                                 累计时间与 deadline / current_time 同口径）
        """
        self.num_particles = num_particles
        self.max_iterations = max_iterations
        self.w = w
        self.c1 = c1
        self.c2 = c2
        self.v_max = v_max
        self.pos_max = pos_max

        # 电量参数（与 frontend/drone.py 中的常量一一对应）
        self.battery_consumption_base = battery_consumption_base
        self.battery_load_penalty_factor = battery_load_penalty_factor
        self.battery_low_threshold = battery_low_threshold

        # 时间单位换算：fitness 内累计的"时间"必须与 deadline / current_time 同为
        # env-step；drone 速度以"米/秒"给出，env-step 长度 = env_step_seconds 秒
        self.env_step_seconds = env_step_seconds

        # 机巢换电耗时（秒）兜底值；observation 的 charging_stations 若给出每站
        # swap_time_seconds 则逐站覆盖，否则用此值。
        self.swap_time_seconds = float(swap_time_seconds)

        # Warm-start（启发式播种）：用批量贪心解作为部分粒子的起点 + 初始全局最优，
        # 加速收敛并保证 PSO 结果不劣于贪心。warm_start_seeds = 播种粒子数
        # （1 个精确贪心 + 其余在其邻域加噪），其余粒子保持随机以维持多样性。
        self.warm_start = warm_start
        self.warm_start_seeds = max(0, int(warm_start_seeds))

        # 设置随机数种子
        if seed is not None:
            np.random.seed(seed)

        # 适应度函数权重（可扩展）
        if weights is None:
            self.weights = {
                'on_time_rate': 0.4,    # 准时率权重
                'avg_delay': 0.4,        # 平均时延权重
                'energy': 0.2            # 能耗权重
            }
        else:
            self.weights = weights

        self.particles: List[Particle] = []
        self.global_best_position = None
        self.global_best_fitness = float('-inf')
        self.fitness_history = []

    @staticmethod
    def euclidean_distance(pos1: Tuple[float, float], pos2: Tuple[float, float]) -> float:
        """计算欧氏距离"""
        return math.sqrt((pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2)

    def calculate_travel_time(self, distance: float, speed: float = 200.0) -> float:
        """
        计算飞行 distance 所需的 env-step 数。

        说明：speed 是"米/秒"，env-step 时长 = self.env_step_seconds 秒，
        所以一个 env-step 内 drone 实际飞 speed * env_step_seconds 米。
        返回值与 environment 的 current_time / task.deadline 同口径。
        """
        denom = speed * self.env_step_seconds
        if denom <= 0:
            return 0.0
        return distance / denom

    def _battery_consumption(self, distance: float, current_load: float,
                             carrying_capacity: float,
                             base: Optional[float] = None,
                             penalty: Optional[float] = None) -> float:
        """
        计算飞行 distance 后消耗的电量（Wh），与 frontend/drone.py:consume_battery 保持一致：
            消耗 = distance * BASE * (1 + (load / capacity) * LOAD_PENALTY_FACTOR)

        base / penalty 为逐机覆盖值（异构机队每架机能耗不同）；未给出时回退到
        配置兜底 self.battery_consumption_base / self.battery_load_penalty_factor。
        """
        base = self.battery_consumption_base if base is None else base
        penalty = self.battery_load_penalty_factor if penalty is None else penalty
        if carrying_capacity <= 0:
            load_factor = 0.0
        else:
            load_factor = (current_load / carrying_capacity) * penalty
        return distance * base * (1.0 + load_factor)

    # ----------- Warm-start：贪心解播种 -----------

    def _greedy_assignment(self,
                           drones_info: List[Dict],
                           tasks_info: List[Dict]) -> np.ndarray:
        """
        批量贪心分配（与 PSO 子问题一致）：把 tasks 逐个分给"就近 origin 且不超载"
        的无人机，返回长度 num_tasks 的 assignment 向量（值为 drone 下标）。

        说明：
          - 无人机起点 = drones_info[i]['position']（外层已设为队尾任务目的地或当前机位）；
          - 任务按 priority 降序处理，与 evaluate_fitness 内部"高优先级先执行"的口径一致；
          - 选择代价 = 从该机当前模拟位置到任务取货点的欧氏距离；
          - 容量约束：优先选还装得下的机；若全部超载则退而求其次选最近的（与
            evaluate_fitness 的"超载返仓"建模一致，仍是合法分配）。
        """
        num_drones = len(drones_info)
        num_tasks = len(tasks_info)
        assignment = np.zeros(num_tasks, dtype=int)

        # 每架无人机的滚动状态：模拟当前位置 + 已装载重
        cur_pos = [tuple(d['position']) for d in drones_info]
        cur_load = [0.0 for _ in range(num_drones)]
        capacities = [float(d.get('capacity', 5)) for d in drones_info]

        order = sorted(range(num_tasks),
                       key=lambda idx: tasks_info[idx].get('priority', 1),
                       reverse=True)

        for task_idx in order:
            task = tasks_info[task_idx]
            source = tuple(task['source'])
            weight = float(task.get('weight', 0.0))

            best_fit = None      # 装得下的最近机
            best_fit_d = float('inf')
            best_any = 0         # 全局最近机（兜底）
            best_any_d = float('inf')

            for i in range(num_drones):
                dist = self.euclidean_distance(cur_pos[i], source)
                if dist < best_any_d:
                    best_any_d = dist
                    best_any = i
                if cur_load[i] + weight <= capacities[i] and dist < best_fit_d:
                    best_fit_d = dist
                    best_fit = i

            chosen = best_fit if best_fit is not None else best_any
            assignment[task_idx] = chosen

            # 更新被选中无人机的模拟状态：装货 → 飞到目的地卸货
            if best_fit is not None:
                cur_load[chosen] += weight
            else:
                # 超载场景：evaluate_fitness 会模拟返仓卸货，这里同步把载重清零再装新货
                cur_load[chosen] = weight
            cur_pos[chosen] = tuple(task['destination'])

        return assignment

    def _assignment_to_position(self,
                                assignment: np.ndarray,
                                num_tasks: int,
                                num_drones: int,
                                noise: float = 0.0) -> np.ndarray:
        """
        把离散 assignment 向量编码成偏好矩阵：被选中的 drone 列拉到 +pos_max，
        其余列设为较低的负值，使 argmax 还原出该 assignment。
        noise > 0 时在矩阵上叠加高斯噪声，生成贪心解的"邻域"粒子（保留多样性）。
        """
        position = np.full((num_tasks, num_drones), -self.pos_max, dtype=float)
        position[np.arange(num_tasks), assignment] = self.pos_max
        if noise > 0:
            position = position + np.random.normal(0.0, noise, position.shape)
        return np.clip(position, -self.pos_max, self.pos_max)

    def _pd_nearest_neighbor(self, start_pos, bundle: List[Dict]) -> List[Dict]:
        """
        带前后序约束的最近邻启发，生成 PD-TSP 初始路径。

        候选集合在每一步动态构成：尚未取货任务的取货点 ∪ 已取货但未送达任务的
        送货点；每次贪心选取距当前位置最近的候选航点。O((2k)^2)。
        """
        n = len(bundle)
        picked = [False] * n
        delivered = [False] * n
        route: List[Dict] = []
        cur = tuple(start_pos)

        for _ in range(2 * n):
            candidates = []  # (kind, task_idx, pos)
            for i in range(n):
                if not picked[i]:
                    candidates.append(('pickup', i, tuple(bundle[i]['source'])))
                elif not delivered[i]:
                    candidates.append(('delivery', i, tuple(bundle[i]['destination'])))

            kind, idx, pos = min(
                candidates, key=lambda c: self.euclidean_distance(cur, c[2]))
            route.append({
                'task_idx': idx,
                'kind': kind,
                'pos': pos,
                'task_id': bundle[idx].get('task_id'),
            })
            if kind == 'pickup':
                picked[idx] = True
            else:
                delivered[idx] = True
            cur = pos

        return route

    def _pd_route_valid(self, route: List[Dict]) -> bool:
        """检验路径是否满足前后序约束：每个任务的取货必须出现在其送货之前。"""
        seen_pickup = set()
        for wp in route:
            if wp['kind'] == 'pickup':
                seen_pickup.add(wp['task_idx'])
            else:  # delivery
                if wp['task_idx'] not in seen_pickup:
                    return False
        return True

    def _pd_route_distance(self, start_pos, route: List[Dict]) -> float:
        """从 start_pos 出发，依次访问 route 中各航点的总飞行距离。"""
        total = 0.0
        cur = tuple(start_pos)
        for wp in route:
            total += self.euclidean_distance(cur, wp['pos'])
            cur = wp['pos']
        return total

    def _pd_two_opt(self, start_pos, route: List[Dict]) -> Tuple[List[Dict], float]:
        """
        带前后序约束的 2-opt 局部搜索：反复尝试翻转子区间 [i, j]，仅接受
        "仍满足前后序约束且总距离更短"的翻转，直到无可改进为止。
        """
        best = list(route)
        best_dist = self._pd_route_distance(start_pos, best)
        improved = True
        while improved:
            improved = False
            n = len(best)
            for i in range(n - 1):
                for j in range(i + 1, n):
                    candidate = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                    if not self._pd_route_valid(candidate):
                        continue
                    d = self._pd_route_distance(start_pos, candidate)
                    if d < best_dist - 1e-9:
                        best = candidate
                        best_dist = d
                        improved = True
        return best, best_dist

    def _pd_route_arrival_times(self, start_pos, route: List[Dict],
                                ready_time: float) -> List[float]:
        """计算到达 route 中每个航点的时刻（env-step），从 ready_time 起算。"""
        times = []
        cur = tuple(start_pos)
        t = float(ready_time)
        for wp in route:
            t += self.calculate_travel_time(self.euclidean_distance(cur, wp['pos']))
            times.append(t)
            cur = wp['pos']
        return times

    def _pd_deadline_adjust(self, start_pos, route: List[Dict],
                            bundle: List[Dict], ready_time: float) -> List[Dict]:
        """
        deadline 前插调整：若某任务的送货航点预计超期，将其送货点前移到紧挨自身
        取货点之后的位置（仍满足前后序约束），以少量额外距离换取准时率。
        从最严重超期的任务开始处理。
        """
        route = list(route)
        times = self._pd_route_arrival_times(start_pos, route, ready_time)

        late = []  # (lateness, task_idx)
        for k, wp in enumerate(route):
            if wp['kind'] != 'delivery':
                continue
            ddl = bundle[wp['task_idx']].get('deadline', float('inf'))
            if ddl != float('inf') and times[k] > ddl:
                late.append((times[k] - ddl, wp['task_idx']))

        if not late:
            return route

        late.sort(reverse=True)  # 超期最严重者优先调整
        for _, task_idx in late:
            del_pos = next(i for i, wp in enumerate(route)
                           if wp['kind'] == 'delivery' and wp['task_idx'] == task_idx)
            wp = route.pop(del_pos)
            pick_pos = next(i for i, w in enumerate(route)
                            if w['kind'] == 'pickup' and w['task_idx'] == task_idx)
            route.insert(pick_pos + 1, wp)

        return route

    def plan_pickup_delivery_route(self, start_pos, bundle: List[Dict],
                                   ready_time: float = 0.0,
                                   deadline_aware: bool = True) -> List[Dict]:
        """
        :param start_pos: 无人机起点（清完已承诺工作后的落点）
        :param bundle: 任务列表，每项含 'source' / 'destination' / 'task_id' /
                       'weight' / 'deadline'（可选）
        :param ready_time: 无人机就绪时刻（env-step），用于 deadline 调整
        :param deadline_aware: 是否在 2-opt 后执行 deadline 前插调整
        :return: 航点访问序列 List[{'task_idx','kind','pos','task_id'}]，
                 取货与送货自由交错且满足前后序约束
        """
        if not bundle:
            return []
        route = self._pd_nearest_neighbor(start_pos, bundle)
        route, _ = self._pd_two_opt(start_pos, route)
        if deadline_aware:
            route = self._pd_deadline_adjust(start_pos, route, bundle, ready_time)
        return route

    def simulate_pd_route(self,
                          start_pos,
                          route: List[Dict],
                          bundle: List[Dict],
                          ready_time: float,
                          battery: float,
                          battery_capacity: float,
                          drone_capacity: float,
                          charging_stations: Optional[List[Dict]] = None
                          ) -> Dict[str, float]:
        """
        沿 PD-TSP 路径做时间/能耗仿真，给出该路径的指标，可供
        evaluate_fitness 在"多货物携带"模式下替换原单任务仿真使用。

        与 evaluate_fitness 的物理口径一致：飞行耗时按 env-step 累计，耗电按
        consume_battery 公式（载重越大单位耗电越高），电量低于阈值时绕行最近
        充电站补满。返回每任务完成时刻、延迟、准时数与总能耗。

        :return: {'on_time_count', 'total_delay', 'total_energy',
                  'completion_times'(dict: task_idx→完成时刻),
                  'makespan'(最后一个航点的时刻)}

        由于前端部分不支持不同起点取送分组，因此该部分逻辑在pso调度器中仅实现，不接入
        """
        charging_stations = charging_stations or []
        cur_pos = tuple(start_pos)
        t = float(ready_time)
        load = 0.0
        cur_battery = float(battery)

        on_time_count = 0
        total_delay = 0.0
        total_energy = 0.0
        completion_times: Dict[int, float] = {}

        for wp in route:
            target = wp['pos']

            # 电量不足 → 先绕行最近充电站补满（与 evaluate_fitness 同口径）
            if (battery_capacity > 0
                    and cur_battery / battery_capacity < self.battery_low_threshold
                    and charging_stations):
                nearest = min(charging_stations,
                              key=lambda s: self.euclidean_distance(
                                  cur_pos, tuple(s['position'])))
                station_pos = tuple(nearest['position'])
                swap_time = float(nearest.get('swap_time_seconds', self.swap_time_seconds))
                dist_to_station = self.euclidean_distance(cur_pos, station_pos)
                consumed = self._battery_consumption(
                    dist_to_station, load, drone_capacity)
                cur_battery = max(0.0, cur_battery - consumed)
                total_energy += consumed
                t += self.calculate_travel_time(dist_to_station)
                cur_pos = station_pos
                # 机巢换电：固定 swap_time 秒后满电，而非慢充
                t += swap_time
                cur_battery = battery_capacity

            # 飞往航点
            dist = self.euclidean_distance(cur_pos, target)
            consumed = self._battery_consumption(dist, load, drone_capacity)
            cur_battery = max(0.0, cur_battery - consumed)
            total_energy += consumed
            t += self.calculate_travel_time(dist)
            cur_pos = target

            # 到达：取货 → 增载；送货 → 减载并记录完成时刻
            task = bundle[wp['task_idx']]
            if wp['kind'] == 'pickup':
                load += float(task.get('weight', 0.0))
            else:
                load -= float(task.get('weight', 0.0))
                completion_times[wp['task_idx']] = t
                deadline = task.get('deadline', float('inf'))
                if deadline is not None and deadline != float('inf'):
                    delay = max(0.0, t - deadline)
                    total_delay += delay
                    if delay == 0:
                        on_time_count += 1
                else:
                    on_time_count += 1

        return {
            'on_time_count': on_time_count,
            'total_delay': total_delay,
            'total_energy': total_energy,
            'completion_times': completion_times,
            'makespan': t,
        }

    def evaluate_fitness(self,
                        position: np.ndarray,
                        drones_info: List[Dict],
                        tasks_info: List[Dict],
                        current_time: float) -> Tuple[float, Dict[str, float]]:
        """
        评估适应度函数（支持多目标优化和扩展）
        :param position: 粒子偏好矩阵 (num_tasks, num_drones)；内部 argmax 解码出分配
        :param drones_info: 无人机信息列表
        :param tasks_info: 任务信息列表
        :param current_time: 当前时间
        :return: (总适应度, 各指标详情字典)
        """
        num_tasks = len(tasks_info)
        num_drones = len(drones_info)

        # 偏好矩阵 → 任务到无人机的离散分配
        assignment = np.argmax(position, axis=1)

        # 为每个无人机分配任务
        drone_tasks = [[] for _ in range(num_drones)]
        for task_idx, drone_idx in enumerate(assignment):
            drone_tasks[int(drone_idx)].append(task_idx)

        # 计算各项指标
        on_time_count = 0
        total_delay = 0.0
        total_completion_time = 0.0
        total_energy = 0.0  # 累积每架无人机消耗的电量（Wh）

        # 用于能耗归一化：取首架无人机的电池容量为参考量级（所有无人机容量一致）
        ref_battery_capacity = drones_info[0].get('battery_capacity', 15000.0) if drones_info else 15000.0

        for drone_idx, task_indices in enumerate(drone_tasks):
            if not task_indices:
                continue

            drone_info = drones_info[drone_idx]
            drone_pos = tuple(drone_info['position'])
            drone_capacity = drone_info.get('capacity', 5)
            drone_speed = float(drone_info.get('speed', 200.0))
            battery_capacity = drone_info.get('battery_capacity', 15000.0)
            current_battery = drone_info.get('battery', battery_capacity)
            charging_stations = drone_info.get('charging_stations', [])
            warehouse_pos = tuple(drone_info.get('home_position', drone_pos))
            # 逐机能耗参数（异构机队：轻载/标准/重载的单位能耗不同），消除口径不一致
            drone_base = float(drone_info.get('battery_consumption_base', self.battery_consumption_base))
            drone_penalty = float(drone_info.get('battery_load_penalty_factor', self.battery_load_penalty_factor))

            current_pos = drone_pos
            current_load = 0
            # 从该机的"就绪时刻"起算，而非 current_time：忙碌机要先清完已承诺的工作
            # （正在执行的 bundle + 队列）才能开始新任务。修复"假设所有机立即可用"的 bug。
            accumulated_time = drone_info.get('ready_time', current_time)

            # 若无人机当前正在机巢换电（frontend drone.py 的自动换电已触发）：
            # 不需要再模拟飞往机巢的绕路，只需等待换电剩余时长结束后再计满电。
            if drone_info.get('is_charging', False):
                est_swap = float(drone_info.get('est_swap_time_seconds', self.swap_time_seconds))
                accumulated_time += est_swap
                current_battery = battery_capacity

            # 按优先级排序任务（高优先级优先执行）
            sorted_tasks = sorted(task_indices,
                                key=lambda idx: tasks_info[idx]['priority'],
                                reverse=True)

            for task_idx in sorted_tasks:
                task = tasks_info[task_idx]
                task_weight = task['weight']

                # 任务开始前：若电量低于阈值，先去最近的机巢换电。
                # 与 frontend/drone.py 一致：任务完成后 is_low_battery() → 飞往最近站换电；
                # 此处在 fitness 仿真中提前预测该行为对完成时间的影响。
                if (battery_capacity > 0
                        and current_battery / battery_capacity < self.battery_low_threshold
                        and charging_stations):
                    # 找到最近的机巢
                    nearest = min(charging_stations,
                                  key=lambda s: self.euclidean_distance(
                                      current_pos, tuple(s['position'])))
                    station_pos = tuple(nearest['position'])
                    swap_time = float(nearest.get('swap_time_seconds', self.swap_time_seconds))
                    dist_to_station = self.euclidean_distance(current_pos, station_pos)
                    consumed = self._battery_consumption(
                        dist_to_station, current_load, drone_capacity, drone_base, drone_penalty)
                    current_battery = max(0.0, current_battery - consumed)
                    total_energy += consumed
                    accumulated_time += self.calculate_travel_time(dist_to_station, drone_speed)
                    current_pos = station_pos
                    # 机巢换电：固定 swap_time 秒后满电
                    accumulated_time += swap_time
                    current_battery = battery_capacity

                # 检查载重，如果超载需要返回仓库
                if current_load + task_weight > drone_capacity:
                    return_distance = self.euclidean_distance(current_pos, warehouse_pos)
                    consumed = self._battery_consumption(
                        return_distance, current_load, drone_capacity, drone_base, drone_penalty)
                    current_battery = max(0.0, current_battery - consumed)
                    total_energy += consumed
                    accumulated_time += self.calculate_travel_time(return_distance, drone_speed)
                    current_pos = warehouse_pos
                    current_load = 0

                # 飞往取货点
                source = tuple(task['source'])
                distance_to_source = self.euclidean_distance(current_pos, source)
                consumed = self._battery_consumption(
                    distance_to_source, current_load, drone_capacity, drone_base, drone_penalty)
                current_battery = max(0.0, current_battery - consumed)
                total_energy += consumed
                accumulated_time += self.calculate_travel_time(distance_to_source, drone_speed)

                # 装货
                current_load += task_weight
                current_pos = source

                # 飞往目的地（载重提升 → 单位耗电增大）
                destination = tuple(task['destination'])
                distance_to_dest = self.euclidean_distance(source, destination)
                consumed = self._battery_consumption(
                    distance_to_dest, current_load, drone_capacity, drone_base, drone_penalty)
                current_battery = max(0.0, current_battery - consumed)
                total_energy += consumed
                accumulated_time += self.calculate_travel_time(distance_to_dest, drone_speed)

                # 卸货
                current_load -= task_weight
                current_pos = destination

                # 计算完成时间和延迟
                completion_time = accumulated_time
                total_completion_time += completion_time

                deadline = task['deadline']
                if deadline is not None and deadline != float('inf'):
                    delay = max(0, completion_time - deadline)
                    total_delay += delay
                    if delay == 0:
                        on_time_count += 1
                else:
                    # 没有截止时间的任务视为准时
                    on_time_count += 1

        # 计算各项指标
        on_time_rate = on_time_count / num_tasks if num_tasks > 0 else 0
        avg_delay = total_delay / num_tasks if num_tasks > 0 else 0
        avg_energy = total_energy / num_drones if num_drones > 0 else 0

        # 归一化处理（将指标映射到[0, 1]区间）
        # 准时率：越高越好，已在[0, 1]
        normalized_on_time = on_time_rate

        # 平均时延：越低越好，使用负指数函数归一化
        normalized_delay = math.exp(-avg_delay / 1000.0) if avg_delay > 0 else 1.0

        # 能耗：以电池容量为参考量级，平均每机消耗的电量越接近一整块电池得分越低；
        # 超过一整块电池则得 0（强惩罚密集充电场景）
        if ref_battery_capacity > 0:
            normalized_energy = max(0.0, 1.0 - avg_energy / ref_battery_capacity)
        else:
            normalized_energy = 1.0

        # 加权求和计算总适应度
        fitness = (self.weights['on_time_rate'] * normalized_on_time +
                  self.weights['avg_delay'] * normalized_delay +
                  self.weights['energy'] * normalized_energy)

        # 返回详细指标
        metrics = {
            'on_time_rate': on_time_rate,
            'avg_delay': avg_delay,
            'avg_energy': avg_energy,
            'normalized_on_time': normalized_on_time,
            'normalized_delay': normalized_delay,
            'normalized_energy': normalized_energy,
            'total_fitness': fitness
        }

        return fitness, metrics

    def optimize(self,
                drones_info: List[Dict],
                tasks_info: List[Dict],
                current_time: float,
                verbose: bool = True) -> Tuple[Dict[int, List[str]], Dict]:
        """
        执行PSO优化
        :param drones_info: 无人机信息列表
        :param tasks_info: 任务信息列表
        :param current_time: 当前时间
        :param verbose: 是否打印优化过程
        :return: (调度方案, 优化统计信息)
        """
        num_drones = len(drones_info)
        num_tasks = len(tasks_info)

        if num_tasks == 0:
            return {}, {'message': 'No tasks to schedule'}

        # 初始化粒子群（每个粒子都持有自己的 (num_tasks, num_drones) 偏好矩阵）
        self.particles = [
            Particle(num_drones, num_tasks, v_max=self.v_max, pos_max=self.pos_max)
            for _ in range(self.num_particles)
        ]
        self.global_best_position = None
        self.global_best_fitness = float('-inf')
        self.fitness_history = []

        # Warm-start：用批量贪心解播种部分粒子，并以贪心解初始化全局最优。
        # 这样 PSO 第一代起点就 ≥ 贪心，且 gbest 只会被更优解替换 → 返回解不劣于贪心。
        if self.warm_start and self.warm_start_seeds > 0:
            greedy_assignment = self._greedy_assignment(drones_info, tasks_info)
            greedy_position = self._assignment_to_position(
                greedy_assignment, num_tasks, num_drones)

            # 播种粒子：第 0 个为精确贪心解，其余在其邻域加噪（保留多样性）
            n_seed = min(self.warm_start_seeds, self.num_particles)
            for k in range(n_seed):
                noise = 0.0 if k == 0 else 0.3 * self.pos_max
                seeded = self._assignment_to_position(
                    greedy_assignment, num_tasks, num_drones, noise=noise)
                self.particles[k].position = seeded
                self.particles[k].best_position = seeded.copy()

            # 用精确贪心解初始化全局最优（拿到"≥ 贪心"的保证）
            greedy_fitness, _ = self.evaluate_fitness(
                greedy_position, drones_info, tasks_info, current_time)
            self.global_best_position = greedy_position.copy()
            self.global_best_fitness = greedy_fitness

        # 迭代优化
        for iteration in range(self.max_iterations):
            for particle in self.particles:
                # 评估当前位置的适应度
                fitness, metrics = self.evaluate_fitness(
                    particle.position, drones_info, tasks_info, current_time
                )
                particle.fitness = fitness

                # 更新个体最优
                if fitness > particle.best_fitness:
                    particle.best_fitness = fitness
                    particle.best_position = particle.position.copy()

                # 更新全局最优
                if fitness > self.global_best_fitness:
                    self.global_best_fitness = fitness
                    self.global_best_position = particle.position.copy()

            # 记录历史
            self.fitness_history.append(self.global_best_fitness)

            # 打印进度
            if verbose and (iteration % 10 == 0 or iteration == self.max_iterations - 1):
                print(f"Iteration {iteration}: Best Fitness = {self.global_best_fitness:.4f}")

            # 更新粒子速度和位置
            for particle in self.particles:
                particle.update_velocity(self.global_best_position, self.w, self.c1, self.c2)
                particle.update_position()

        # 生成最终调度方案
        assignments = self._generate_assignments(
            self.global_best_position, drones_info, tasks_info
        )

        # 计算最终指标
        _, final_metrics = self.evaluate_fitness(
            self.global_best_position, drones_info, tasks_info, current_time
        )

        stats = {
            'iterations': self.max_iterations,
            'best_fitness': self.global_best_fitness,
            'fitness_history': self.fitness_history,
            'metrics': final_metrics
        }

        return assignments, stats

    def _generate_assignments(self,
                             position: np.ndarray,
                             drones_info: List[Dict],
                             tasks_info: List[Dict]) -> Dict[int, List[str]]:
        """
        根据粒子位置（偏好矩阵）生成调度方案
        :param position: 偏好矩阵 (num_tasks, num_drones)，先 argmax 解码
        :param drones_info: 无人机信息
        :param tasks_info: 任务信息
        :return: {drone_index: [task_id_list]}
        """
        num_drones = len(drones_info)
        assignments = {i: [] for i in range(num_drones)}

        assignment = np.argmax(position, axis=1)
        for task_idx, drone_idx in enumerate(assignment):
            task_id = tasks_info[task_idx]['task_id']
            assignments[int(drone_idx)].append(task_id)

        return assignments


# 默认配置文件路径（与本模块同目录下的 config.yaml）
from swarmbalance.paths import SCHEDULER_CONFIG
DEFAULT_CONFIG_PATH = str(SCHEDULER_CONFIG)



from swarmbalance.scheduling.dispatch import EventDrivenScheduler


class PSOScheduler(EventDrivenScheduler):
    """PSO strategy using the shared event-driven dispatch state machine."""
    def _build_optimizer(self):
        """构造批量优化器实例。子类可覆写以替换为 GA 等其它算法。"""
        return PSOOptimizer(
            num_particles=self.pso_num_particles,
            max_iterations=self.pso_max_iterations,
            w=self.pso_inertia,
            c1=self.pso_cognitive,
            c2=self.pso_social,
            v_max=self.pso_v_max,
            pos_max=self.pso_pos_max,
            weights=self.fitness_weights,
            seed=self.seed,
            battery_consumption_base=self.battery_consumption_base,
            battery_load_penalty_factor=self.battery_load_penalty_factor,
            battery_low_threshold=self.battery_low_threshold,
            env_step_seconds=self.env_step_seconds,
            warm_start=self.pso_warm_start,
            warm_start_seeds=self.pso_warm_start_seeds,
        )
