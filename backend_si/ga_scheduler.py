"""
遗传算法（GA）用于异构无人机任务调度

支持两种编码（由 `ga.encoding` 配置切换，便于 A/B 对比）：

1. ``assignment``（旧口径，与 PSO 完全同构）
   - 染色体：长度 = 任务数，chromosome[i] = 为任务 i 服务的无人机下标
   - 适应度：复用 PSOOptimizer.evaluate_fitness（准时率/时延/能耗 三目标加权）
   - 遗传算子：锦标赛选择 + 均匀交叉 + 容量/负载感知变异 + 精英保留

2. ``permutation``（**默认**，对应申请书「排列编码 + 贪婪分割解码」）
   - 染色体：全部待排任务的一个**排列**
   - 解码：`chain_codec.greedy_split_decode()` 按排列顺序把任务挂到"增量代价
     最小"的机尾，载重 / 电量 / 时间窗任一不满足即形成分割点 → 自然产出
     **每机一条有序任务链**（任务链优化引擎）
   - 适应度：链级代价 `makespan + w_tardy * Σ超时 + w_dist * Σ里程`
     + 未分配任务重罚
   - 遗传算子：锦标赛选择 + **OX 顺序交叉** + 交换/插入/片段逆序变异 + 精英保留

两种编码都保留：温启动播种、精英保留、以及"结果不劣于贪心"的保证。

对外接口与 PSOOptimizer 完全一致：
  optimizer = GAOptimizer(...)
  assignments, stats = optimizer.optimize(drones_info, tasks_info, current_time)
"""
import numpy as np
from typing import List, Dict, Tuple, Optional

from .pso_scheduler import PSOOptimizer, PSOScheduler
from .chain_codec import (
    ChainDecodeConfig,
    chain_cost,
    greedy_split_decode,
)

#: 合法编码方式
ENCODING_ASSIGNMENT = "assignment"
ENCODING_PERMUTATION = "permutation"


class GAOptimizer:
    """遗传算法核心：给定无人机集合和任务集合，输出 task→drone 分配。

    复用 PSOOptimizer 的 evaluate_fitness / _greedy_assignment / _assignment_to_position，
    使 GA 与 PSO 共享同一套物理仿真与多目标适应度口径，可公平对比。
    """

    def __init__(self,
                 population_size: int = 60,
                 generations: int = 40,
                 crossover_rate: float = 0.85,
                 mutation_rate: float = 0.15,
                 elite_rate: float = 0.1,
                 tournament_size: int = 3,
                 capacity_penalty: float = 0.3,
                 weights: Optional[Dict[str, float]] = None,
                 seed: Optional[int] = None,
                 battery_consumption_base: float = 0.5,
                 battery_load_penalty_factor: float = 0.3,
                 battery_low_threshold: float = 0.2,
                 env_step_seconds: float = 1.0,
                 warm_start: bool = True,
                 encoding: str = ENCODING_PERMUTATION,
                 chain_config: Optional[Dict] = None):
        self.encoding = str(encoding or ENCODING_PERMUTATION).strip().lower()
        if self.encoding not in (ENCODING_ASSIGNMENT, ENCODING_PERMUTATION):
            raise ValueError(
                f"未知编码方式 {encoding!r}，可选："
                f"{ENCODING_ASSIGNMENT} / {ENCODING_PERMUTATION}")
        # 排列编码的贪婪分割解码参数
        chain_config = chain_config or {}
        self.chain_cfg = ChainDecodeConfig(
            max_chain_tasks=int(chain_config.get('max_chain_tasks', 3)),
            max_total_weight=float(chain_config.get('max_total_weight', 30.0)),
            battery_reserve=float(chain_config.get('battery_reserve', 0.1)),
            swap_time_seconds=float(chain_config.get('swap_time_seconds', 180.0)),
            w_tardy=float(chain_config.get('w_tardy', 2.0)),
            w_dist=float(chain_config.get('w_dist', 0.01)),
            w_new_chain=float(chain_config.get('w_new_chain', -30.0)),
            tardy_tolerance=float(chain_config.get('tardy_tolerance', 600.0)),
        )
        self.w_unassigned = float(chain_config.get('w_unassigned', 1e4))
        self.population_size = max(2, int(population_size))
        self.generations = max(1, int(generations))
        self.crossover_rate = min(max(crossover_rate, 0.0), 1.0)
        self.mutation_rate = min(max(mutation_rate, 0.0), 1.0)
        self.elite_rate = min(max(elite_rate, 0.0), 0.5)
        self.tournament_size = max(2, int(tournament_size))
        self.capacity_penalty = max(0.0, float(capacity_penalty))
        self.warm_start = warm_start

        # 复用 PSOOptimizer 纯粹作为"适应度评估器 + 贪心播种器"
        self._eval = PSOOptimizer(
            num_particles=1, max_iterations=0,
            weights=weights, seed=seed,
            battery_consumption_base=battery_consumption_base,
            battery_load_penalty_factor=battery_load_penalty_factor,
            battery_low_threshold=battery_low_threshold,
            env_step_seconds=env_step_seconds,
            warm_start=False, warm_start_seeds=0,
        )

        self._rng = np.random.default_rng(seed)
        self.fitness_history: List[float] = []

    # ---------- 容量违约计算 ----------

    @staticmethod
    def _loads(chromosome: np.ndarray, num_drones: int,
               weights_arr: np.ndarray) -> np.ndarray:
        loads = np.zeros(num_drones, dtype=float)
        for wi, d in zip(weights_arr, chromosome):
            loads[d] += wi
        return loads

    def _capacity_violation(self, chromosome: np.ndarray, num_drones: int,
                            weights_arr: np.ndarray, capacities: np.ndarray) -> float:
        loads = self._loads(chromosome, num_drones, weights_arr)
        return float(np.sum(np.maximum(0.0, loads - capacities)))

    # ---------- 初始化 ----------

    def _random_chromosome(self, num_tasks: int, num_drones: int) -> np.ndarray:
        if self.encoding == ENCODING_PERMUTATION:
            return self._rng.permutation(num_tasks).astype(int)
        return self._rng.integers(0, num_drones, size=num_tasks)

    def _greedy_chromosome(self, drones_info: List[Dict],
                           tasks_info: List[Dict]) -> np.ndarray:
        if self.encoding == ENCODING_PERMUTATION:
            # 播种排列：按"截止时间从紧到松"排，再用高优先级前置做二次关键字，
            # 让贪婪分割解码优先把紧急任务挂到靠前的链位。
            order = sorted(
                range(len(tasks_info)),
                key=lambda j: (
                    -float(tasks_info[j].get('priority', 1)),
                    self._deadline_key(tasks_info[j]),
                ),
            )
            return np.array(order, dtype=int)
        assignment = self._eval._greedy_assignment(drones_info, tasks_info)
        return assignment.astype(int).copy()

    @staticmethod
    def _deadline_key(task: Dict) -> float:
        dl = task.get('deadline', None)
        if dl is None:
            return float('inf')
        try:
            return float(dl)
        except (TypeError, ValueError):
            return float('inf')

    def _init_population(self, num_tasks: int, num_drones: int,
                         drones_info: List[Dict], tasks_info: List[Dict]) -> List[np.ndarray]:
        population: List[np.ndarray] = []
        if self.warm_start:
            population.append(self._greedy_chromosome(drones_info, tasks_info))
            weights_arr = np.array([float(t.get('weight', 0.0)) for t in tasks_info])
            capacities = np.array([float(d.get('capacity', 5.0)) for d in drones_info])
            while len(population) < self.population_size:
                seed_chrom = population[0].copy()
                if self._rng.random() < 0.5:
                    self._mutate(seed_chrom, num_drones, weights_arr, capacities, rate=0.3)
                    population.append(seed_chrom)
                else:
                    population.append(self._random_chromosome(num_tasks, num_drones))
        else:
            population = [self._random_chromosome(num_tasks, num_drones)
                          for _ in range(self.population_size)]

        while len(population) < self.population_size:
            population.append(self._random_chromosome(num_tasks, num_drones))
        return population[:self.population_size]

    # ---------- 适应度 ----------

    def _fitness(self, chromosome: np.ndarray,
                 drones_info: List[Dict], tasks_info: List[Dict],
                 current_time: float, weights_arr: np.ndarray,
                 capacities: np.ndarray) -> float:
        if self.encoding == ENCODING_PERMUTATION:
            sol = greedy_split_decode(chromosome, drones_info, tasks_info,
                                      current_time, self.chain_cfg)
            cost = chain_cost(sol.metrics, w_unassigned=self.w_unassigned)
            # 最大化适应度 → 取负代价
            return -cost

        num_tasks = len(tasks_info)
        num_drones = len(drones_info)
        position = self._eval._assignment_to_position(
            chromosome, num_tasks, num_drones, noise=0.0)
        fit, _ = self._eval.evaluate_fitness(
            position, drones_info, tasks_info, current_time)
        violation = self._capacity_violation(
            chromosome, num_drones, weights_arr, capacities)
        return fit - self.capacity_penalty * violation

    # ---------- 遗传算子 ----------

    def _tournament_select(self, population: List[np.ndarray],
                           fitnesses: np.ndarray) -> np.ndarray:
        idxs = self._rng.integers(0, len(population), size=self.tournament_size)
        winner = int(idxs[0])
        for i in idxs[1:]:
            if fitnesses[int(i)] > fitnesses[winner]:
                winner = int(i)
        return population[winner].copy()

    def _crossover(self, p1: np.ndarray, p2: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        child1 = p1.copy()
        child2 = p2.copy()
        if self._rng.random() >= self.crossover_rate:
            return child1, child2

        if self.encoding == ENCODING_PERMUTATION:
            return self._ox_crossover(p1, p2)
        mask = self._rng.random(len(p1)) < 0.5
        child1[mask] = p2[mask]
        child2[mask] = p1[mask]
        return child1, child2

    def _ox_crossover(self, p1: np.ndarray, p2: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """OX 顺序交叉：保留父代一段连续相对顺序，其余位置按另一父代顺序填充。

        排列编码下不能用均匀交叉（会产生重复基因），OX 是标准做法。
        """
        n = len(p1)
        if n < 2:
            return p1.copy(), p2.copy()

        def _ox(a: np.ndarray, b: np.ndarray) -> np.ndarray:
            lo, hi = 0, 0
            while hi <= lo:
                i, j = int(self._rng.integers(0, n)), int(self._rng.integers(0, n))
                lo, hi = min(i, j), max(i, j)
            child = np.full(n, -1, dtype=int)
            child[lo:hi + 1] = a[lo:hi + 1]
            taken = set(int(x) for x in child[lo:hi + 1])
            rest = [int(x) for x in b if int(x) not in taken]
            idx = 0
            for k in range(n):
                if child[k] == -1:
                    child[k] = rest[idx]
                    idx += 1
            return child

        return _ox(p1, p2), _ox(p2, p1)

    def _mutate(self, chromosome: np.ndarray, num_drones: int,
                weights_arr: np.ndarray, capacities: np.ndarray,
                rate: Optional[float] = None) -> None:
        rate = self.mutation_rate if rate is None else rate

        if self.encoding == ENCODING_PERMUTATION:
            n = len(chromosome)
            if n < 2:
                return
            for _ in range(max(1, int(round(rate * n)))):
                op = self._rng.random()
                i, j = int(self._rng.integers(0, n)), int(self._rng.integers(0, n))
                if i == j:
                    continue
                if op < 0.45:
                    # 交换
                    chromosome[i], chromosome[j] = chromosome[j], chromosome[i]
                elif op < 0.8:
                    # 插入：把 j 位置基因抽出来插到 i 前面
                    gene = int(chromosome[j])
                    others = [int(x) for k, x in enumerate(chromosome) if k != j]
                    pos = i if i < j else i
                    others.insert(pos, gene)
                    chromosome[:] = np.array(others, dtype=int)
                else:
                    # 片段逆序（2-opt 邻域）
                    lo, hi = min(i, j), max(i, j)
                    chromosome[lo:hi + 1] = chromosome[lo:hi + 1][::-1]
            return
        for j in range(len(chromosome)):
            if self._rng.random() >= rate:
                continue
            # 一半概率选"装得下该任务的机"（负载感知），一半完全随机，保持探索
            if self._rng.random() < 0.5:
                feasible = [k for k in range(num_drones)
                            if weights_arr[j] <= capacities[k] + 1e-9]
                if feasible:
                    chromosome[j] = int(self._rng.choice(feasible))
                    continue
            chromosome[j] = int(self._rng.integers(0, num_drones))

    # ---------- 容量修复 ----------

    def _repair(self, chromosome: np.ndarray, weights_arr: np.ndarray,
                capacities: np.ndarray) -> None:
        """把超载机上的任务贪心迁移到"剩余容量足够"的其它机，保证最终方案可行。

        排列编码无需修复：可行性由贪婪分割解码器在解码时保证
        （装不下的任务会自然形成分割点，挂到其它机或进入 unassigned）。
        """
        if self.encoding == ENCODING_PERMUTATION:
            return
        num_drones = len(capacities)
        for _ in range(num_drones):
            loads = self._loads(chromosome, num_drones, weights_arr)
            overloaded = [i for i in range(num_drones) if loads[i] > capacities[i] + 1e-9]
            if not overloaded:
                return

            moved = False
            for d in overloaded:
                idxs = [j for j in range(len(chromosome)) if chromosome[j] == d]
                idxs.sort(key=lambda j: weights_arr[j], reverse=True)
                for j in idxs:
                    w = weights_arr[j]
                    feasible = [k for k in range(num_drones)
                                if k != d and loads[k] + w <= capacities[k] + 1e-9]
                    if feasible:
                        # 优先迁往负载最轻的机，兼顾均衡
                        k = min(feasible, key=lambda kk: loads[kk])
                        chromosome[j] = k
                        loads[d] -= w
                        loads[k] += w
                        moved = True
                        break
            if not moved:
                return

    # ---------- 生成分配 ----------

    def _generate_assignments(self, chromosome: np.ndarray,
                              drones_info: List[Dict],
                              tasks_info: List[Dict],
                              current_time: float = 0.0) -> Dict[int, List[str]]:
        if self.encoding == ENCODING_PERMUTATION:
            # 排列 → 有序任务链；返回的任务 id 列表**保持链内顺序**，
            # 下游 drone_queues 会按此顺序逐个派发（即任务链执行序）。
            sol = greedy_split_decode(chromosome, drones_info, tasks_info,
                                      current_time, self.chain_cfg)
            self.last_chain_metrics = sol.metrics
            assignments = {i: [] for i in range(len(drones_info))}
            for drone_idx, chain in enumerate(sol.chains):
                assignments[drone_idx] = [
                    tasks_info[int(t)]['task_id'] for t in chain
                ]
            # 解码失败（无可行挂载点）的任务：退回批量贪心，避免任务被永久丢弃
            if sol.unassigned:
                fallback = self._eval._greedy_assignment(drones_info, tasks_info)
                for task_idx, drone_idx in enumerate(fallback):
                    if int(task_idx) in sol.unassigned:
                        assignments.setdefault(int(drone_idx), []).append(
                            tasks_info[int(task_idx)]['task_id'])
            return assignments

        assignments = {i: [] for i in range(len(drones_info))}
        for task_idx, drone_idx in enumerate(chromosome):
            task_id = tasks_info[task_idx]['task_id']
            assignments[int(drone_idx)].append(task_id)
        return assignments

    # ---------- 主优化入口 ----------

    def optimize(self,
                 drones_info: List[Dict],
                 tasks_info: List[Dict],
                 current_time: float,
                 verbose: bool = True) -> Tuple[Dict[int, List[str]], Dict]:
        num_drones = len(drones_info)
        num_tasks = len(tasks_info)

        if num_tasks == 0:
            return {}, {'message': 'No tasks to schedule'}

        weights_arr = np.array([float(t.get('weight', 0.0)) for t in tasks_info])
        capacities = np.array([float(d.get('capacity', 5.0)) for d in drones_info])

        population = self._init_population(
            num_tasks, num_drones, drones_info, tasks_info)
        elite_count = max(1, int(round(self.population_size * self.elite_rate)))

        best_chromosome: Optional[np.ndarray] = None
        best_fitness = float('-inf')
        self.fitness_history = []

        for gen in range(self.generations):
            fitnesses = np.array([
                self._fitness(c, drones_info, tasks_info, current_time,
                              weights_arr, capacities)
                for c in population
            ])

            best_idx = int(np.argmax(fitnesses))
            if fitnesses[best_idx] > best_fitness:
                best_fitness = float(fitnesses[best_idx])
                best_chromosome = population[best_idx].copy()
            self.fitness_history.append(float(np.max(fitnesses)))

            if verbose and (gen % 10 == 0 or gen == self.generations - 1):
                print(f"Generation {gen}: Best Fitness = {float(np.max(fitnesses)):.4f}")

            # 精英保留
            order = np.argsort(-fitnesses)
            next_pop = [population[int(i)].copy() for i in order[:elite_count]]

            # 选择 + 交叉 + 变异，补齐到种群规模
            while len(next_pop) < self.population_size:
                p1 = self._tournament_select(population, fitnesses)
                p2 = self._tournament_select(population, fitnesses)
                child1, child2 = self._crossover(p1, p2)
                self._mutate(child1, num_drones, weights_arr, capacities)
                self._mutate(child2, num_drones, weights_arr, capacities)
                next_pop.append(child1)
                if len(next_pop) < self.population_size:
                    next_pop.append(child2)

            population = next_pop[:self.population_size]

        if best_chromosome is None:
            best_chromosome = population[0].copy()
        best_chromosome = best_chromosome.copy()

        # 容量修复：保证返回方案满足异构载重约束（环境会拒掉超载分配）
        self._repair(best_chromosome, weights_arr, capacities)

        final_fitness = self._fitness(
            best_chromosome, drones_info, tasks_info, current_time,
            weights_arr, capacities)

        if self.encoding == ENCODING_PERMUTATION:
            sol = greedy_split_decode(best_chromosome, drones_info, tasks_info,
                                      current_time, self.chain_cfg)
            final_metrics = dict(sol.metrics)
            final_metrics['chain_cost'] = -float(final_fitness)
        else:
            _, final_metrics = self._eval.evaluate_fitness(
                self._eval._assignment_to_position(
                    best_chromosome, num_tasks, num_drones, noise=0.0),
                drones_info, tasks_info, current_time)
        final_metrics['total_fitness_with_penalty'] = final_fitness
        final_metrics['encoding'] = self.encoding

        assignments = self._generate_assignments(
            best_chromosome, drones_info, tasks_info, current_time)

        stats = {
            'generations': self.generations,
            'best_fitness': float(final_fitness),
            'fitness_history': self.fitness_history,
            'metrics': final_metrics,
        }

        return assignments, stats


class GAScheduler(PSOScheduler):
    """事件驱动的遗传算法调度器（对外）。

    完整复用 PSOScheduler 的双通道 + 动态贪心外层逻辑，仅把批量优化器从
    PSO 换成 GA。这样 GA / PSO / greedy 三者在同一套事件驱动框架下公平对比，
    唯一差异是"buffer flush 时用的批量分配算法"。
    """

    def __init__(self,
                 num_drones: int,
                 config_path: Optional[str] = None,
                 verbose: bool = True,
                 seed: Optional[int] = None):
        super().__init__(num_drones, config_path=config_path,
                         verbose=verbose, seed=seed)
        ga_cfg = self.config.get('ga', {})
        self.ga_population_size = int(ga_cfg.get('population_size', 60))
        self.ga_generations = int(ga_cfg.get('generations', 40))
        self.ga_crossover_rate = float(ga_cfg.get('crossover_rate', 0.85))
        self.ga_mutation_rate = float(ga_cfg.get('mutation_rate', 0.15))
        self.ga_elite_rate = float(ga_cfg.get('elite_rate', 0.1))
        self.ga_tournament_size = int(ga_cfg.get('tournament_size', 3))
        self.ga_capacity_penalty = float(ga_cfg.get('capacity_penalty', 0.3))
        self.ga_warm_start = bool(ga_cfg.get('warm_start', True))
        # 编码方式：permutation = 排列编码 + 贪婪分割解码（申请书口径，默认）
        #           assignment  = 分配矩阵编码（与 PSO 同构，用于 A/B 对比）
        self.ga_encoding = str(ga_cfg.get('encoding', ENCODING_PERMUTATION)).strip().lower()
        self.chain_config = dict(self.config.get('chain', {}))
        # 排列编码产出的链内顺序即执行序，禁止被动态贪心重排覆盖
        self.preserve_chain_order = (self.ga_encoding == ENCODING_PERMUTATION)

    def _build_optimizer(self):
        return GAOptimizer(
            population_size=self.ga_population_size,
            generations=self.ga_generations,
            crossover_rate=self.ga_crossover_rate,
            mutation_rate=self.ga_mutation_rate,
            elite_rate=self.ga_elite_rate,
            tournament_size=self.ga_tournament_size,
            capacity_penalty=self.ga_capacity_penalty,
            weights=self.fitness_weights,
            seed=self.seed,
            battery_consumption_base=self.battery_consumption_base,
            battery_load_penalty_factor=self.battery_load_penalty_factor,
            battery_low_threshold=self.battery_low_threshold,
            env_step_seconds=self.env_step_seconds,
            warm_start=self.ga_warm_start,
            encoding=self.ga_encoding,
            chain_config=self.chain_config,
        )

    @property
    def uses_chain_decoding(self) -> bool:
        """排列编码产出的链内顺序即执行序，不应再被动态贪心重排打乱。"""
        return self.ga_encoding == ENCODING_PERMUTATION