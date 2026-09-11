"""
粒子群优化算法（PSO）用于无人机任务调度
优化目标：任务准时率、平均时延

本文件包含两个类：
  - PSOOptimizer：PSO 算法核心，纯优化器（输入 drones+tasks → 输出分配）
  - PSOScheduler：对外调度器，事件驱动，双通道 + 内层动态贪心，
                  内部通过 PSOOptimizer 完成批量分配
配置参数集中在 backend_si/config.yaml。
"""
import os
import numpy as np
import math
import copy
import yaml
from typing import List, Dict, Tuple, Optional

try:
    # 首选 backend 内共享实现，保证后端可独立运行；旧 frontend 实现仅作兼容兜底。
    from .matching import compute_match as _compute_match
except Exception:
    try:
        from matching import compute_match as _compute_match
    except Exception:  # 极简独立运行环境下退化为就近贪心
        _compute_match = None

try:
    from scheduling_interface import Scheduler, SCHEMA_VERSION
except Exception:  # backend 独立运行、无 frontend 模块时退化为普通基类
    Scheduler = object  # type: ignore
    SCHEMA_VERSION = "1.0"

# 体积折算为等效重量的系数（与 frontend/greedy/scheduler.py 保持一致）
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
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   'config.yaml')


class PSOScheduler(Scheduler):
    """
    事件驱动 PSO 调度器（对外）：双通道任务分配 + 内层动态贪心排序。

    所有可调超参数集中在 backend_si/config.yaml；要换实验配置，传 config_path。

    工作流程（每个仿真步调一次 step()）：
      1. 检测新到达任务：
         - 若有"空闲且队列为空"的无人机 → 立即就近贪心分配（直通通道）
         - 否则进入 pending_buffer，等待批量 PSO（缓冲通道）
      2. 检测刚变空闲的无人机 → 对其剩余任务队列做动态贪心重排
      3. 检查 buffer 是否满足 flush 条件（size / emergency / timeout 任一）
         → 调用 PSOOptimizer 做批量分配，结果追加进各机队列
      4. 给空闲无人机派发队头任务
    """

    def __init__(self,
                 num_drones: int,
                 config_path: Optional[str] = None,
                 verbose: bool = True,
                 seed: Optional[int] = None):
        self.num_drones = num_drones
        self.verbose = verbose
        self.config = self._load_config(config_path or DEFAULT_CONFIG_PATH)

        # 解包常用配置项
        dc = self.config['dual_channel']
        self.buffer_size_threshold = dc['buffer_size_threshold']
        self.emergency_ttl = dc['emergency_ttl']
        self.buffer_timeout = dc['buffer_timeout']
        # 空闲机即时抽取 buffer：每步让"空闲+空队列"的无人机就近抓 buffer 任务，
        # 消除"空闲机干等 flush"的分配延迟；只有竞争（待分配 > 空闲机）时才留给 PSO。
        # 设 false 退回纯双通道行为（用于 A/B 对比）。
        self.eager_idle_dispatch = bool(dc.get('eager_idle_dispatch', True))
        # 空闲机抓取任务的评分权重：匹配度 vs 距离邻近（与 greedy 的 0.6/0.4 对齐）
        self.eager_match_weight = float(dc.get('eager_match_weight', 0.6))
        self.eager_distance_weight = float(dc.get('eager_distance_weight', 0.4))
        # 最小松弛紧急度：空闲机优先抢救即将超时的任务（slack 越小越紧急）
        self.eager_urgency_weight = float(dc.get('eager_urgency_weight', 0.3))
        self.eager_urgency_window = float(dc.get('eager_urgency_window', 100.0))
        # 顺路接入（任务链）：在途机链条未满时，就近把队头任务挂到它当前航线上。
        # 设 false 退回"必须先空闲再派单"的旧行为（用于 A/B 对比）。
        self.opportunistic_chain = bool(dc.get('opportunistic_chain', True))
        self.chain_detour_m = float(dc.get('chain_detour_m', 400.0))
        # 排列编码产物的链内顺序即执行序，禁止动态贪心重排覆盖（GA permutation 置真）
        self.preserve_chain_order = False

        pso_cfg = self.config['pso']
        self.pso_num_particles = pso_cfg['num_particles']
        self.pso_max_iterations = pso_cfg['max_iterations']
        self.pso_inertia = pso_cfg['inertia']
        self.pso_cognitive = pso_cfg['cognitive']
        self.pso_social = pso_cfg['social']
        # 方案 A 偏好矩阵编码新增参数（向后兼容旧 config 缺失的情况）
        self.pso_v_max = pso_cfg.get('v_max', 4.0)
        self.pso_pos_max = pso_cfg.get('pos_max', 5.0)
        # Warm-start：用贪心解播种部分粒子（默认开启；设 false 退回纯随机初始化）
        self.pso_warm_start = bool(pso_cfg.get('warm_start', True))
        self.pso_warm_start_seeds = int(pso_cfg.get('warm_start_seeds', 3))

        self.fitness_weights = dict(self.config['fitness_weights'])
        self.greedy_weights = dict(self.config['dynamic_greedy'])
        self.drone_capacity = self.config['drone']['capacity']
        # 每架机的真实载重能力（异构机队差异化）：默认用配置统一值占位，
        # 每个 step 从 observation['drone_capabilities'] 刷新为真实剩余载重。
        # 修复：原实现假设所有机同质，导致重任务被派给轻载机、被 env 静默拒单后卡死。
        self._drone_capacity = [self.drone_capacity] * num_drones
        self._drone_remaining = [self.drone_capacity] * num_drones
        # frontend Drone.update() 采用 1 step = 1 秒；fitness 中所有"时间"必须按
        # env-step 累计才能与 deadline / current_time 同口径
        self.env_step_seconds = float(self.config['drone'].get('time_step', 1.0))
        self.drone_speed = float(self.config['drone'].get('speed', 200.0))
        # 1 个 env-step 内飞行的米数，用于把距离换算成 env-step（与 fitness 同口径）
        self._meters_per_step = max(1e-9, self.drone_speed * self.env_step_seconds)

        # 电量参数（与 frontend/drone.py 中常量保持同名同义；缺省值即 drone.py 的默认值）
        battery_cfg = self.config.get('battery', {})
        self.battery_capacity = float(battery_cfg.get('capacity', 15000.0))
        self.battery_consumption_base = float(battery_cfg.get('consumption_base', 0.5))
        self.battery_load_penalty_factor = float(battery_cfg.get('load_penalty_factor', 0.3))
        self.battery_low_threshold = float(battery_cfg.get('low_threshold', 0.2))
        
        # 随机数种子（优先使用参数，其次使用配置文件，最后不设置）
        if seed is None:
            seed = self.config.get('seed')
        self.seed = seed
        if self.seed is not None:
            np.random.seed(self.seed)

        # 运行时状态
        self.drone_queues: Dict[int, List[Dict]] = {i: [] for i in range(num_drones)}
        self.pending_buffer: List[Dict] = []
        self.buffer_entry_time: Dict[str, float] = {}
        self.known_task_ids: set = set()
        self.prev_is_free: List[bool] = [True] * num_drones
        self.active_task_ids: Dict[int, str] = {}
        # 每架机当前正在执行的任务包（同源 bundle）；用于 ready_time 估计忙碌机何时空闲
        self.active_tasks: Dict[int, List[Dict]] = {}

        # 事件统计
        self.stats = {
            'immediate_assign': 0,
            'urgent_dispatch': 0,
            'buffered': 0,
            'buffer_drain': 0,
            'bundled': 0,        # 同源合并：一次 action 多送达的额外任务数
            'flush_size': 0,
            'flush_emergency': 0,
            'flush_timeout': 0,
            'reorders': 0,
            'dispatches': 0,
        }

    # ----------- 对外入口 -----------

    def _extract_capacity(self, observation: Dict) -> None:
        """从 observation['drone_capabilities'] 刷新每架机的真实载重/剩余载重。

        异构机队下每架机的 carrying_capacity 不同，必须逐机读取；observation 缺失时
        保留上次值（或配置统一值），保证外层派发/打包/抽取都按真实容量过滤，
        避免把重任务派给轻载机后被 env 静默拒绝而卡死。
        """
        cap_obs = observation.get('drone_capabilities')
        if not cap_obs or len(cap_obs) != self.num_drones:
            return
        for i, c in enumerate(cap_obs):
            if not c:
                continue
            cap = float(c.get('carrying_capacity', self.drone_capacity))
            # 剩余载重优先用 observation 给出的值，缺失时按 carrying_capacity 兜底
            remaining = float(c.get('remaining_capacity', cap))
            self._drone_capacity[i] = cap
            self._drone_remaining[i] = max(0.0, remaining)

    def act(self, observation: Dict, current_time: float) -> Dict[int, List[str]]:
        """稳定调度接口：与 step() 语义一致，作为三算法（Greedy/PSO/GA）统一入口。"""
        return self.step(observation, current_time)

    def step(self, observation: Dict, current_time: float) -> Dict[int, List[str]]:
        """
        每个仿真步调用一次。
        :param observation: 环境观察空间，需要含 'drone_positions', 'unassigned_tasks',
                            以及 'drone_is_free' 或 'drone_free_masks'
        :param current_time: 当前时间步
        :return: {drone_idx: [task_id]} 动作字典（仅向当前空闲且有队列的无人机派发）
        """
        self._extract_capacity(observation)
        is_free = self._extract_is_free(observation)

        # 1. 新任务检测与处理（跳过 environment._obs() 插入的 padding 占位任务）
        for task in observation.get('unassigned_tasks', []):
            tid = task['task_id']
            if str(tid).startswith('__pad_'):
                continue
            if tid in self.known_task_ids:
                continue
            self.known_task_ids.add(tid)
            self._on_new_task(task, observation, is_free, current_time)

        # 2. 空闲事件检测与处理（无人机刚送完货）
        for i in range(self.num_drones):
            if not self.prev_is_free[i] and is_free[i]:
                self.active_task_ids.pop(i, None)
                self.active_tasks.pop(i, None)
                self._on_drone_freed(i, observation, current_time)

        # 3. 空闲机即时抽取 buffer（消除空闲机干等 flush 的分配延迟）
        if self.eager_idle_dispatch:
            self._drain_buffer_to_idle(observation, is_free, current_time)

        # 4. buffer flush 检查（仅处理抽取后仍有竞争的剩余任务）
        self._maybe_flush_buffer(observation, current_time)

        # 5. 派发：空闲 + 无活动任务 + 有队列 → 派发队头，并同源 bundle
        action: Dict[int, List[str]] = {}
        for i in range(self.num_drones):
            if is_free[i] and i not in self.active_task_ids and self.drone_queues[i]:
                # 防御性硬过滤：队头单件若超该机真实载重，则跳过派发（送回 buffer 待重排），
                # 避免进入 env 后被静默拒单造成任务永久卡死。
                head_w = float(self.drone_queues[i][0].get('weight', 0.0))
                if head_w > self._drone_capacity[i] + 1e-9:
                    self._requeue_overload_head(i)
                    continue
                bundle = self._pop_same_source_bundle(i)
                action[i] = [t['task_id'] for t in bundle]
                # active_task_ids 仅作"该机已占用"标记（清除逻辑不看具体值）；
                # active_tasks 保存整个 bundle，供 ready_time 估计忙碌机何时空闲
                self.active_task_ids[i] = bundle[0]['task_id']
                self.active_tasks[i] = bundle
                self.stats['dispatches'] += 1
                if len(bundle) > 1:
                    self.stats['bundled'] += len(bundle) - 1

        # 6. 顺路接入：在途机链条未满时，把队头任务就近挂到它当前航线上，
        #    省掉"送完回巢/待命 → 再出发"的空驶段（申请书「任务链 / 顺路接入」）
        if self.opportunistic_chain:
            self._dispatch_chain_insertions(observation, is_free, action, current_time)

        self.prev_is_free = is_free
        return action

    # ----------- 顺路接入（任务链） -----------

    def _dispatch_chain_insertions(self, observation, is_free, action,
                                   current_time: float = 0.0) -> None:
        """给"在途且链条未满"的无人机顺路追加一单。

        这是申请书「执行完前序任务后顺路接入新任务」的调度侧实现：
        在途机不必先回巢/待命再重新出发，而是把下一单直接挂到当前航线上。

        候选来源（按优先级）：
          1. 该机自己的待派队列队头（批量优化已经替它挑好的下一单）；
          2. `pending_buffer` 中"取货点距航线末端最近"的任务（真正的顺路抓取）。

        判定条件全部基于 observation，避免直接触碰 Environment 内部对象：
          1. 该机非空闲，且 `drone_chain_info[i].can_chain` 为真（链条未满）；
          2. 任务重量 + 当前载重 ≤ 该机真实载重（与 env 拒单口径一致）；
          3. 任务取货点距"航线末端"在 `chain_detour_m` 之内（绕行可接受）。
        """
        chain_info = observation.get('drone_chain_info')
        if not chain_info:
            return
        loads = observation.get('drone_loads') or []
        taken_ids = {tid for ids in action.values() for tid in ids}

        for i in range(self.num_drones):
            if is_free[i] or i in action:
                continue
            info = chain_info[i] if i < len(chain_info) else None
            if not info or not info.get('can_chain', False):
                continue

            if i < len(loads):
                cur_load = float(loads[i].get('current', 0.0))
                cap = float(loads[i].get('capacity', self._drone_capacity[i]))
            else:
                cur_load, cap = 0.0, self._drone_capacity[i]
            room = min(cap, self._drone_capacity[i]) - cur_load
            tail = tuple(info.get('route_tail', observation['drone_positions'][i]))

            # ① 队列队头
            cand = None
            if self.drone_queues[i]:
                head = self.drone_queues[i][0]
                if float(head.get('weight', 0.0)) <= room + 1e-9:
                    cand = head

            # ② 缓冲区里最顺路、且接进来不会超时的那一单
            if cand is None:
                speed = float(info.get('speed', 0.0)) or max(1e-6, self.drone_speed)
                remaining_m = float(info.get('remaining_route_m', 0.0))
                base_eta = remaining_m / speed  # 清完在手航线还需多少 env-step
                best, best_score = None, None
                for t in self.pending_buffer:
                    if t['task_id'] in taken_ids:
                        continue
                    if float(t.get('weight', 0.0)) > room + 1e-9:
                        continue
                    d = self._dist(tail, tuple(t['source']))
                    if d > self.chain_detour_m:
                        continue
                    # 时间窗可行性：接入后的预计送达时刻不得晚于 deadline，
                    # 否则"提前分配"只是把超时风险固定下来，反而拖累平均时延
                    deadline = t.get('_abs_deadline', None)
                    if deadline is not None and float(deadline) != float('inf'):
                        leg = (d + self._dist(tuple(t['source']),
                                              tuple(t['destination']))) / speed
                        if current_time + base_eta + leg > float(deadline):
                            continue
                    # 同等条件下优先抢救更紧急的：距离为主，紧急度做小幅加权
                    score = d - 30.0 * float(t.get('priority', 1))
                    if best_score is None or score < best_score:
                        best, best_score = t, score
                cand = best

            if cand is None:
                continue

            detour = self._dist(tail, tuple(cand['source']))
            if detour > self.chain_detour_m:
                continue

            # 出队：队列队头 pop；缓冲区任务则从 buffer 移除
            if self.drone_queues[i] and self.drone_queues[i][0] is cand:
                self.drone_queues[i].pop(0)
            elif cand in self.pending_buffer:
                self.pending_buffer.remove(cand)
                self.buffer_entry_time.pop(cand['task_id'], None)

            action[i] = [cand['task_id']]
            taken_ids.add(cand['task_id'])
            self.stats['chain_insertions'] = self.stats.get('chain_insertions', 0) + 1
            self.stats['chain_detour_sum'] = \
                self.stats.get('chain_detour_sum', 0.0) + detour

    def _requeue_overload_head(self, drone_idx: int) -> None:
        """把某机队列中装不下的队头任务移回 pending_buffer，交给 flush 重新分配给重载机。"""
        head = self.drone_queues[drone_idx].pop(0)
        self.pending_buffer.append(head)
        self.buffer_entry_time[head['task_id']] = self.buffer_entry_time.get(
            head['task_id'], 0.0)

    def _pop_same_source_bundle(self, drone_idx: int) -> List[Dict]:
        """
        从 drone_idx 的队列弹出队头任务，并把队列中与队头**同源**、且累计载重不超该机
        真实载重的任务一并打包（前端只支持同源合并：一次取货、多点配送）。
        返回打包的任务列表（至少含队头一个）。
        """
        queue = self.drone_queues[drone_idx]
        head = queue.pop(0)
        bundle = [head]
        total_weight = float(head.get('weight', 0.0))
        head_source = tuple(head['source'])
        # 该机处于空闲态（current_load ≈ 0），打包上限 = 其真实 carrying_capacity
        capacity = self._drone_capacity[drone_idx]

        remaining = []
        for t in queue:
            t_weight = float(t.get('weight', 0.0))
            if (tuple(t['source']) == head_source
                    and total_weight + t_weight <= capacity + 1e-9):
                bundle.append(t)
                total_weight += t_weight
            else:
                remaining.append(t)
        self.drone_queues[drone_idx] = remaining
        return bundle

    def _estimate_ready(self, drone_idx, actual_pos, current_time):
        """
        估计无人机 drone_idx 清完"已承诺工作"后的落点(origin)与时刻(ready_time, env-step)。
        已承诺工作 = 正在执行的 bundle(active_tasks) + 队列中尚未派发的任务(drone_queues)。
        让 fitness 知道忙碌机要晚些才空闲，避免把新任务堆到其实正忙的机上。
        """
        pos = tuple(actual_pos)
        t = float(current_time)

        def travel_steps(a, b):
            return self._dist(a, b) / self._meters_per_step

        # 1) 正在执行的 bundle：近似为依次飞往各任务目的地（取货点视为已到/在途）
        for task in self.active_tasks.get(drone_idx, []):
            dest = tuple(task['destination'])
            t += travel_steps(pos, dest)
            pos = dest

        # 2) 队列中尚未派发的任务：依次 取货点 → 目的地
        for task in self.drone_queues[drone_idx]:
            src = tuple(task['source'])
            dest = tuple(task['destination'])
            t += travel_steps(pos, src) + travel_steps(src, dest)
            pos = dest

        return pos, t

    def get_stats(self) -> Dict[str, int]:
        return dict(self.stats)

    def _best_drone_for_task(self, feasible, task, observation, current_time):
        """在可行空闲机中为某任务选"最匹配"的机型（而非纯就近）。

        评分 = eager_match_weight * 载重/速度/续航匹配度 + eager_distance_weight * 距离邻近分，
        与 greedy 的 _score_task 口径一致：重货倾向重载机、急件倾向高速机、远距离倾向长续航机，
        避免慢速重载机被轻任务占用、轻载机抢重货。同质机型（无 drone_type）退化为就近贪心。
        """
        drone_positions = observation['drone_positions']
        cap_list = observation.get('drone_capabilities', [])
        source = tuple(task['source'])
        task_weight = float(task.get('weight', 0.0))
        required_load = task_weight + VOLUME_TO_LOAD_FACTOR * float(task.get('volume', 0.0))
        abs_ddl = task.get('_abs_deadline', float('inf'))
        remaining_time = (abs_ddl - current_time) if abs_ddl != float('inf') else float('inf')
        rd = float(task.get('route_distance', 0.0))

        dists = [self._dist(tuple(drone_positions[i]), source) for i in feasible]
        mn, mx = min(dists), max(dists)

        def proximity(d):
            return 1.0 if mx <= mn else 1.0 - (d - mn) / (mx - mn)

        def score(i, d):
            cap = cap_list[i] if i < len(cap_list) else {}
            if _compute_match is None or not cap or cap.get('drone_type') is None:
                return -d
            rc = float(cap.get('remaining_capacity', cap.get('carrying_capacity', 1.0)))
            if task_weight > rc + 1e-9:
                return -1e9
            ms = _compute_match(
                required_load, rc,
                float(cap.get('speed', self.drone_speed)),
                remaining_time,
                float(cap.get('battery_capacity', self.battery_capacity)),
                float(cap.get('battery_consumption_base', self.battery_consumption_base)),
                d + rd,
            )
            return (self.eager_match_weight * ms
                    + self.eager_distance_weight * proximity(d))

        return max(feasible, key=lambda i: score(i, dists[feasible.index(i)]))

    def _is_urgent(self, task, current_time):
        """任务是否需紧急直派：高优先级（urgent 类别，deadline 减半）或临近 deadline。"""
        if int(task.get('priority', 1)) >= 3:
            return True
        abs_ddl = task.get('_abs_deadline', float('inf'))
        return abs_ddl != float('inf') and (abs_ddl - current_time) < self.emergency_ttl

    def _best_drone_for_urgent(self, task, observation, current_time):
        """为紧急任务选"最早能到取货点、且装得下"的机（含仍在忙的机），
        用 _estimate_ready 估算忙碌机清完既有工作后的 ETA。紧急任务等不起 buffer，
        故直接在队尾排队，而非丢进 pending_buffer 等 flush。"""
        task_weight = float(task.get('weight', 0.0))
        drone_positions = observation.get('drone_positions', [])
        cap_list = observation.get('drone_capabilities', [])
        source = tuple(task['source'])
        best = None
        best_key = None
        for i in range(self.num_drones):
            if task_weight > self._drone_capacity[i] + 1e-9:
                continue
            origin, ready = self._estimate_ready(i, tuple(drone_positions[i]), current_time)
            eta = ready + self._dist(origin, source) / self._meters_per_step
            speed = self.drone_speed
            if i < len(cap_list) and cap_list[i]:
                speed = float(cap_list[i].get('speed', self.drone_speed))
            key = (eta, -speed)
            if best_key is None or key < best_key:
                best_key = key
                best = i
        return best

    # ----------- 事件处理 -----------

    def _on_new_task(self, task, observation, is_free, current_time):
        # 用绝对 deadline 替代陈旧的 ttl，防止任务在队列里躺久后 ttl 过期
        ttl = task.get('remaining_time', float('inf'))
        task['_abs_deadline'] = (current_time + ttl) if ttl != float('inf') else float('inf')

        task_weight = float(task.get('weight', 0.0))
        available = [i for i in range(self.num_drones)
                     if is_free[i]
                     and i not in self.active_task_ids
                     and len(self.drone_queues[i]) == 0]

        if available:
            # 载重硬过滤：只把任务派给"装得下"的空闲机，避免重任务被轻载机接走
            # 后被 env.step 静默拒绝而永久卡死（与原 greedy 的 _is_feasible 对齐）。
            feasible = [i for i in available
                        if task_weight <= self._drone_remaining[i] + 1e-9]
            if feasible:
                best = self._best_drone_for_task(feasible, task, observation, current_time)
                self.drone_queues[best].append(task)
                self.stats['immediate_assign'] += 1
                if self.verbose:
                    print(f"[PSOScheduler] 立即分配 {task['task_id']} → drone_{best}（机型匹配空闲机）")
                return

        # 紧急任务直派：无空闲机时提前预分配到"最早能空闲"的可行机，
        # 不等 buffer 的 timeout flush（对 deadline 减半的 urgent 任务太慢）
        if self._is_urgent(task, current_time):
            urgent_best = self._best_drone_for_urgent(task, observation, current_time)
            if urgent_best is not None:
                self.drone_queues[urgent_best].append(task)
                self.stats['urgent_dispatch'] += 1
                if self.verbose:
                    print(f"[PSOScheduler] 紧急直派 {task['task_id']} → drone_{urgent_best}（预排最早空闲机）")
                return

        self.pending_buffer.append(task)
        self.buffer_entry_time[task['task_id']] = current_time
        self.stats['buffered'] += 1

    def _drain_buffer_to_idle(self, observation, is_free, current_time):
        """
        每步把 buffer 里的任务就近派给当前空闲（free + 无活动任务 + 空队列）的无人机，
        当步即可被 dispatch。这样空闲机不必干等 PSO flush，分配延迟接近 greedy。

        只在"空闲机充足"时清空 buffer；当待分配任务多于空闲机（真竞争）时，多出来的
        任务仍留在 buffer 交给 PSO 批量优化（_maybe_flush_buffer）。
        """
        if not self.pending_buffer:
            return

        drone_positions = observation['drone_positions']
        cap_list = observation.get('drone_capabilities', [])
        idle = [i for i in range(self.num_drones)
                if is_free[i]
                and i not in self.active_task_ids
                and len(self.drone_queues[i]) == 0]

        # 贪心匹配：每个空闲机按"匹配度 + 距离"抓一个最优 anchor 任务，并把 buffer 中
        # 与其同源、容量内的任务一并聚拢到同一架机的队列（供派发时同源 bundle）。
        for i in idle:
            if not self.pending_buffer:
                break
            drone_pos = tuple(drone_positions[i])
            remaining = self._drone_remaining[i]
            # 载重硬过滤：只选该机当前剩余载重能装下的 anchor，避免重任务被轻载机抓走
            loadable = [t for t in self.pending_buffer
                        if float(t.get('weight', 0.0)) <= remaining + 1e-9]
            if not loadable:
                continue
            drone_cap = cap_list[i] if i < len(cap_list) else {}
            anchor = self._pick_anchor(drone_cap, drone_pos, loadable, current_time)
            grabbed = self._take_same_source_from_buffer(anchor, remaining)
            self.drone_queues[i].extend(grabbed)
            self.stats['buffer_drain'] += len(grabbed)
            self._drone_remaining[i] = remaining - sum(
                float(t.get('weight', 0.0)) for t in grabbed)
            if self.verbose:
                ids = [t['task_id'] for t in grabbed]
                print(f"[PSOScheduler] 空闲机聚拢 {ids} → drone_{i}（同源就近）")

    def _pick_anchor(self, drone_cap, drone_pos, loadable, current_time):
        """在 loadable 候选中为某空闲机挑选最优任务（评分越高越优先）。

        评分 = eager_match_weight * 匹配度 + eager_distance_weight * 距离邻近分，
        与 greedy 的 _score_task 口径一致：考虑载重利用率、速度-时效、续航-距离，
        避免纯距离贪心把任务分给不匹配机型（轻载机抢重货 / 慢机抢急件）。无
        matching 模块或同质机型时退化为就近贪心。
        """
        dists = [self._dist(drone_pos, tuple(t['source'])) for t in loadable]
        mn, mx = min(dists), max(dists)

        def proximity(d):
            return 1.0 if mx <= mn else 1.0 - (d - mn) / (mx - mn)

        def urgency_of(t, d):
            abs_ddl = t.get('_abs_deadline', float('inf'))
            if abs_ddl == float('inf'):
                return 0.0
            slack = (abs_ddl - current_time) - d / self._meters_per_step
            if slack <= 0.0:
                return 1.0
            if slack >= self.eager_urgency_window:
                return 0.0
            return 1.0 - slack / self.eager_urgency_window

        def score(t, d):
            prox = proximity(d)
            urg = urgency_of(t, d)
            if _compute_match is None or not drone_cap or drone_cap.get('drone_type') is None:
                return prox + self.eager_urgency_weight * urg
            rc = float(drone_cap.get('remaining_capacity',
                                     drone_cap.get('carrying_capacity', 1.0)))
            tw = float(t.get('weight', 0.0))
            if tw > rc + 1e-9:
                return -1e9
            required_load = tw + VOLUME_TO_LOAD_FACTOR * float(t.get('volume', 0.0))
            abs_ddl = t.get('_abs_deadline', float('inf'))
            remaining_time = (abs_ddl - current_time) if abs_ddl != float('inf') else float('inf')
            rd = float(t.get('route_distance', 0.0))
            ms = _compute_match(
                required_load, rc,
                float(drone_cap.get('speed', self.drone_speed)),
                remaining_time,
                float(drone_cap.get('battery_capacity', self.battery_capacity)),
                float(drone_cap.get('battery_consumption_base', self.battery_consumption_base)),
                d + rd,
            )
            return (self.eager_match_weight * ms
                    + self.eager_distance_weight * prox
                    + self.eager_urgency_weight * urg)

        return max(loadable, key=lambda t: score(t, self._dist(drone_pos, tuple(t['source']))))

    def _take_same_source_from_buffer(self, anchor: Dict, capacity: float) -> List[Dict]:
        """
        从 pending_buffer 取出 anchor 及其同源、累计载重不超 capacity 的任务（一并移出 buffer）。
        返回取出的任务列表（至少含 anchor）。

        capacity = 该机当前真实剩余载重，保证同源累加也不会超载（否则会被 env 静默拒单）。
        """
        anchor_source = tuple(anchor['source'])
        taken = [anchor]
        total_weight = float(anchor.get('weight', 0.0))
        self.pending_buffer.remove(anchor)
        self.buffer_entry_time.pop(anchor['task_id'], None)

        for t in list(self.pending_buffer):
            t_weight = float(t.get('weight', 0.0))
            if (tuple(t['source']) == anchor_source
                    and total_weight + t_weight <= capacity + 1e-9):
                taken.append(t)
                total_weight += t_weight
                self.pending_buffer.remove(t)
                self.buffer_entry_time.pop(t['task_id'], None)
        return taken

    def _on_drone_freed(self, drone_idx, observation, current_time):
        queue = self.drone_queues[drone_idx]
        if len(queue) <= 1:
            return
        # 排列编码：链内顺序是优化结果，不再做动态贪心重排（否则链条被打散）
        if getattr(self, 'preserve_chain_order', False):
            return
        drone_pos = tuple(observation['drone_positions'][drone_idx])
        self.drone_queues[drone_idx] = self._dynamic_greedy_reorder(
            queue, drone_pos, current_time
        )
        self.stats['reorders'] += 1
        if self.verbose:
            print(f"[PSOScheduler] drone_{drone_idx} 空闲，动态贪心重排 {len(queue)} 个队列任务")

    def _maybe_flush_buffer(self, observation, current_time):
        if not self.pending_buffer:
            return

        reason = None
        urgent_ids = set()
        if len(self.pending_buffer) >= self.buffer_size_threshold:
            reason = 'size'
        if reason is None:
            for task in self.pending_buffer:
                # 用绝对截止时间计算真实剩余 TTL；原实现用 observation 的静态
                # remaining_time 快照（不随 current_time 递减），导致紧急任务
                # 永远无法被识别，紧急 flush 形同虚设。
                abs_deadline = task.get('_abs_deadline', float('inf'))
                if abs_deadline != float('inf') and (abs_deadline - current_time) < self.emergency_ttl:
                    urgent_ids.add(task['task_id'])
            if urgent_ids:
                reason = 'emergency'
        if reason is None:
            oldest = min(self.buffer_entry_time.get(t['task_id'], current_time)
                         for t in self.pending_buffer)
            if current_time - oldest > self.buffer_timeout:
                reason = 'timeout'

        if reason is None:
            return

        if reason == 'emergency':
            # 紧急触发仅抢救"即将超时"的任务，其余任务留在 buffer 交给下步 eager_drain，
            # 避免把不紧急的任务一并预分配给尚未空闲的机 → 不必要的锁定与排队延迟。
            self._flush_buffer_with_pso(observation, current_time, reason,
                                        only_task_ids=urgent_ids)
        else:
            self._flush_buffer_with_pso(observation, current_time, reason)

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

    def _flush_buffer_with_pso(self, observation, current_time, reason, only_task_ids=None):
        # only_task_ids 非空时，仅 flush 这些任务（紧急触发抢救子集），其余留在 buffer
        flush_tasks = self.pending_buffer
        if only_task_ids is not None:
            flush_tasks = [t for t in self.pending_buffer if t['task_id'] in only_task_ids]
        if not flush_tasks:
            return

        # 充电站信息：优先用 observation 中的多站列表，缺失时回退到单站格式
        stations_info = observation.get('charging_stations', None)
        if not stations_info:
            # 向后兼容单站格式
            station_info = observation.get('charging_station', {}) or {}
            station_pos = tuple(station_info.get('position',
                                                  observation['drone_positions'][0]))
            charging_power = float(station_info.get('charging_power', 50.0))
            stations_info = [{
                'position': list(station_pos),
                'charging_power': charging_power,
            }]
        else:
            # 统一转换格式
            stations_info = [{
                'position': s['position'],
                'charging_power': float(s.get('charging_power', 50.0)),
            } for s in stations_info]

        # 电量信息（每机一份）
        battery_obs = observation.get('drone_batteries')
        # 机型能力（异构调度）：速度 + 载重，供 fitness 按机型差异化评估
        cap_obs = observation.get('drone_capabilities')

        # 每架无人机的 PSO 起点与就绪时间：
        #   origin     = 它清完"已承诺工作"（正在执行的 bundle + 队列任务）后所处的位置
        #   ready_time = 它清完这些工作、可以开始执行新 buffer 任务的时刻（env-step）
        # 修复原 bug：之前 origin 取队尾目的地、但 fitness 里 accumulated_time 从 current_time
        # 起算，等于假设所有机此刻立即可用 → PSO 把任务堆到其实正忙的机上。
        drones_info = []
        for i in range(self.num_drones):
            actual_pos = tuple(observation['drone_positions'][i])
            origin, ready_time = self._estimate_ready(i, actual_pos, current_time)

            if battery_obs is not None and i < len(battery_obs):
                bcap = float(battery_obs[i].get('capacity', self.battery_capacity))
                bcur = float(battery_obs[i].get('current', bcap))
                is_charging = bool(battery_obs[i].get('is_charging', False))
            else:
                bcap = self.battery_capacity
                bcur = bcap
                is_charging = False

            # 机型能力：默认回退到配置的单机载重/速度（同质基线）
            if cap_obs is not None and i < len(cap_obs) and cap_obs[i]:
                drone_capacity = float(cap_obs[i].get('carrying_capacity', self.drone_capacity))
                drone_speed = float(cap_obs[i].get('speed', self.drone_speed))
            else:
                drone_capacity = self.drone_capacity
                drone_speed = self.drone_speed

            # 若无人机正在充电，估算其充电站的功率（取距当前机位最近的站）
            if is_charging and stations_info:
                nearest_st = min(
                    stations_info,
                    key=lambda s: self._dist(actual_pos, tuple(s['position']))
                )
                est_charging_power = float(nearest_st.get('charging_power', 50.0))
            else:
                est_charging_power = float(stations_info[0]['charging_power']) if stations_info else 50.0

            drones_info.append({
                'index': i,
                'position': origin,
                'ready_time': ready_time,
                'capacity': drone_capacity,
                'speed': drone_speed,
                'home_position': actual_pos,
                'battery_capacity': bcap,
                'battery': bcur,
                'is_charging': is_charging,
                'est_charging_power': est_charging_power,
                'charging_stations': stations_info,
            })

        tasks_info = [{
            'task_id': t['task_id'],
            'source': t['source'],
            'destination': t['destination'],
            'deadline': t.get('_abs_deadline', float('inf')),
            'priority': t['priority'],
            'weight': t['weight'],
        } for t in flush_tasks]

        optimizer = self._build_optimizer()
        assignments, _ = optimizer.optimize(
            drones_info, tasks_info, current_time=current_time, verbose=False
        )

        # drones_info 顺序 = 全局 index，PSO 返回的 local_idx 即 global_idx
        for drone_idx, task_ids in assignments.items():
            for task_id in task_ids:
                task = next((t for t in flush_tasks
                             if t['task_id'] == task_id), None)
                if task is not None:
                    self.drone_queues[drone_idx].append(task)

        # 只移除本次 flush 处理的任务；非紧急子集保留在 buffer 待后续 eager_drain
        for task in list(flush_tasks):
            self.buffer_entry_time.pop(task['task_id'], None)
            if task in self.pending_buffer:
                self.pending_buffer.remove(task)

        # 对队列长度 > 1 的无人机做一次动态贪心重排修正顺序。
        # 例外：排列编码（任务链）产出的顺序本身就是优化结果，重排会把它覆盖掉，
        # 使"排列编码 + 贪婪分割解码"退化成纯分配 —— 此时保留链内执行序。
        if getattr(self, 'preserve_chain_order', False):
            self.stats['chain_order_preserved'] = \
                self.stats.get('chain_order_preserved', 0) + 1
        else:
            for i in range(self.num_drones):
                if len(self.drone_queues[i]) > 1:
                    start_pos = tuple(observation['drone_positions'][i])
                    self.drone_queues[i] = self._dynamic_greedy_reorder(
                        self.drone_queues[i], start_pos, current_time
                    )

        self.stats[f'flush_{reason}'] += 1
        if self.verbose:
            summary = {k: len(v) for k, v in self.drone_queues.items()}
            print(f"[PSOScheduler] PSO 批量分配（触发: {reason}），当前各机队列: {summary}")

    # ----------- 工具方法 -----------

    def _dynamic_greedy_reorder(self, tasks, start_pos, current_time):
        ordered = []
        remaining = list(tasks)
        current_pos = start_pos
        while remaining:
            best = max(remaining,
                       key=lambda t: self._score_task(t, current_pos, current_time))
            ordered.append(best)
            remaining.remove(best)
            current_pos = tuple(best['destination'])
        return ordered

    def _score_task(self, task, current_pos, current_time):
        priority = task.get('priority', 1)
        abs_deadline = task.get('_abs_deadline')
        if abs_deadline is None:
            ttl = task.get('remaining_time', float('inf'))
        else:
            ttl = (abs_deadline - current_time) if abs_deadline != float('inf') else float('inf')
        source = tuple(task['source'])
        distance = self._dist(current_pos, source)

        if ttl == float('inf'):
            urgency = 0.0
        elif ttl <= 0:
            urgency = 10.0  # 已超期 → 强制前置
        else:
            urgency = 1.0 / max(1.0, ttl)

        w = self.greedy_weights
        return (w['priority'] * priority
                + w['urgency'] * urgency
                - w['distance'] * distance)

    def _extract_is_free(self, observation):
        is_free = observation.get('drone_is_free')
        if is_free is not None and len(is_free) == self.num_drones:
            return list(is_free)
        # 兜底：从旧的 drone_free_masks 推断
        masks = observation.get('drone_free_masks', [])
        return [all(m) if m else True for m in masks]

    def _slack_to_pickup(self, drone_pos, task, current_time):
        """任务松弛时间：绝对截止 - 当前时刻 - 飞往取货点耗时。

        值越小越紧急（负值表示即使立刻飞也会迟到）。无截止时间的任务返回 inf
        （始终排在最不紧急的一端）。这是一种最小松弛优先（Least Slack First）
        调度启发，用于空闲机在 buffer 里选 anchor 时优先抢救即将超时的任务，
        对齐 greedy 通过 speed_match 间接表达的"紧迫任务优先"。
        """
        abs_deadline = task.get('_abs_deadline', float('inf'))
        if abs_deadline == float('inf'):
            return float('inf')
        travel = self._dist(drone_pos, tuple(task['source'])) / self._meters_per_step
        return (abs_deadline - current_time) - travel

    @staticmethod
    def _load_config(path: str) -> Dict:
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    @staticmethod
    def _dist(p1, p2):
        return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)
