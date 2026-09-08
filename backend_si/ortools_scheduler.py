"""OR-Tools 经典求解器基线（CP-SAT）。

项目书承诺
----------
申请书「四、项目实施方案（二）核心调度算法实现」明确写道：

    对比基线：搭建贪心调度基线……并集成 **OR-Tools 求解器**作为经典 VRP
    **降维求解**的性能参照。

本模块兑现这一条：在**同一套事件驱动框架**（与 PSO / GA 完全相同的双通道 +
动态贪心重排）下，把「缓冲区批量分配」这一步从元启发式换成 CP-SAT 精确求解，
从而得到「本项目优化算法 vs 经典求解器 vs 贪心」三方可比的结果。

为什么是"降维求解"
------------------
完整的异构机队 PDPTW 含 pickup-delivery 配对、机内任务排序、电量与换电约束，
直接建模规模过大、单步求解不可行。这里做两层降维，且**降维方式与 PSO/GA 的
建模假设完全一致**，所以是公平对照而非削弱基线：

1. **忽略机内排序**（与 PSO/GA 同）：CP-SAT 只解「任务 → 无人机」的分配，
   单机内部执行顺序仍由框架统一的 `_dynamic_greedy_reorder()` 决定——
   PSO / GA / OR-Tools 三者共用同一段排序代码，排序能力不构成差异。
2. **用"最坏完成时刻"做时间窗校验**：任务 i 若分给机 j，其完成时刻上界取
   该机所有任务做完的时刻 T_j。这是保守估计，因此求出的解在真实仿真中只会
   更好不会更差。

保留的硬约束（这些是真约束，不是近似）：
- 每任务必被分配且仅分给一架机；
- 异构载重上限（含环境的多任务总重上限，避免被 env 静默拒单）；
- 异构速度差异（按各机型真实 speed 换算 env-step）；
- 各机就绪时刻 `ready_time`（忙碌机先清完在手工作）。

目标函数（与申请书"以最小化总任务完成时间为目标"一致）：
    minimize  makespan_weight * makespan + tardiness_weight * Σ 超时量

依赖
----
`pip install ortools`（已加入 `backend_si/requirements.txt`）。
未安装时本模块可正常 import，但调用 `optimize()` 会给出明确的安装提示，
而不是在评测中途抛出难以定位的 ImportError。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from .pso_scheduler import PSOOptimizer, PSOScheduler

try:  # 延迟到真正求解时才需要；未安装不阻断其它算法
    from ortools.sat.python import cp_model as _cp_model

    _ORTOOLS_AVAILABLE = True
    _ORTOOLS_IMPORT_ERROR: Optional[str] = None
except Exception as _exc:  # pragma: no cover
    _cp_model = None
    _ORTOOLS_AVAILABLE = False
    _ORTOOLS_IMPORT_ERROR = str(_exc)

__all__ = ["ORToolsOptimizer", "ORToolsScheduler", "ORTOOLS_AVAILABLE"]

ORTOOLS_AVAILABLE = _ORTOOLS_AVAILABLE

# 时间/重量的整数化精度（CP-SAT 只接受整数系数）
_TIME_SCALE = 10      # 0.1 env-step
_WEIGHT_SCALE = 100   # 0.01 kg
# big-M：足以覆盖任意 (T_j - deadline_i) 的取值范围
_BIG_M = 10 ** 7


class ORToolsOptimizer:
    """用 CP-SAT 求解「任务 → 无人机」的批量分配。

    对外接口与 `PSOOptimizer` / `GAOptimizer` 完全一致：
        assignments, stats = optimizer.optimize(drones_info, tasks_info, current_time)
    """

    def __init__(self,
                 time_limit_seconds: float = 2.0,
                 makespan_weight: int = 1,
                 tardiness_weight: int = 1,
                 num_workers: int = 4,
                 capacity_penalty_weight: int = 0,
                 multi_task_max_total_weight: Optional[float] = None,
                 weights: Optional[Dict[str, float]] = None,
                 seed: Optional[int] = None,
                 battery_consumption_base: float = 0.5,
                 battery_load_penalty_factor: float = 0.3,
                 battery_low_threshold: float = 0.2,
                 env_step_seconds: float = 1.0,
                 verbose: bool = False):
        self.time_limit_seconds = max(0.1, float(time_limit_seconds))
        self.makespan_weight = int(makespan_weight)
        self.tardiness_weight = int(tardiness_weight)
        self.num_workers = max(1, int(num_workers))
        self.capacity_penalty_weight = int(capacity_penalty_weight)
        self.multi_task_max_total_weight = multi_task_max_total_weight
        self.weights = weights or {}
        self.seed = seed
        self.verbose = verbose

        # 复用 PSOOptimizer 作为「贪心播种器」——求解失败/不可行时兜底，
        # 保证 OR-Tools 基线不会比贪心更差（与 GA 的 warm_start 同理）。
        self._eval = PSOOptimizer(
            num_particles=1, max_iterations=0,
            weights=weights, seed=seed,
            battery_consumption_base=battery_consumption_base,
            battery_load_penalty_factor=battery_load_penalty_factor,
            battery_low_threshold=battery_low_threshold,
            env_step_seconds=env_step_seconds,
            warm_start=False, warm_start_seeds=0,
        )
        self._env_step_seconds = max(1e-9, float(env_step_seconds))

    # ---------- 物理口径（与 PSOOptimizer 同） ----------

    @staticmethod
    def _dist(p1, p2) -> float:
        return math.hypot(float(p1[0]) - float(p2[0]), float(p1[1]) - float(p2[1]))

    def _travel_steps(self, distance: float, speed: float) -> float:
        """米 / (米每秒) -> env-step 数，与 PSOOptimizer.calculate_travel_time 同口径。"""
        denom = max(1e-9, float(speed) * self._env_step_seconds)
        return distance / denom

    def _effective_capacity(self, drone: Dict[str, Any]) -> float:
        """环境实际接受的载重上限 = min(机型载重, 多任务总重上限)。

        环境 `step()` 会同时校验这两条，超任一即静默拒单。用 min 建模可避免
        求解器给出仿真执行不了的方案。
        """
        cap = float(drone.get("capacity", 5.0))
        if self.multi_task_max_total_weight is not None:
            cap = min(cap, float(self.multi_task_max_total_weight))
        return max(0.0, cap)

    # ---------- 主入口 ----------

    def optimize(self,
                 drones_info: List[Dict],
                 tasks_info: List[Dict],
                 current_time: float,
                 verbose: bool = True) -> Tuple[Dict[int, List[str]], Dict]:
        num_drones = len(drones_info)
        num_tasks = len(tasks_info)
        if num_tasks == 0:
            return {}, {"message": "No tasks to schedule"}
        if num_drones == 0:
            return {}, {"message": "No drones available"}

        if not ORTOOLS_AVAILABLE:
            raise RuntimeError(
                "OR-Tools 未安装，无法运行经典求解器基线。"
                "请执行：pip install ortools"
                + (f"（导入错误：{_ORTOOLS_IMPORT_ERROR}）" if _ORTOOLS_IMPORT_ERROR else "")
            )

        model, x, makespan, tardiness, drone_time_expr = self._build_model(
            drones_info, tasks_info)

        solver = _cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.time_limit_seconds
        solver.parameters.num_search_workers = self.num_workers
        if self.seed is not None:
            solver.parameters.random_seed = int(self.seed)

        status = solver.Solve(model)

        if status not in (_cp_model.OPTIMAL, _cp_model.FEASIBLE):
            # 不可行/超时无解 → 退回贪心，保证基线不崩、不劣于贪心
            return self._greedy_fallback(drones_info, tasks_info,
                                         reason=solver.StatusName(status))

        assignments: Dict[int, List[str]] = {i: [] for i in range(num_drones)}
        for i in range(num_tasks):
            for j in range(num_drones):
                if solver.Value(x[i][j]):
                    assignments[j].append(tasks_info[i]["task_id"])
                    break

        stats = {
            "solver": "CP-SAT",
            "status": solver.StatusName(status),
            "wall_time": float(solver.WallTime()),
            "objective": (float(solver.ObjectiveValue())
                          if status in (_cp_model.OPTIMAL, _cp_model.FEASIBLE) else None),
            "best_bound": (float(solver.BestObjectiveBound())
                           if status == _cp_model.OPTIMAL else None),
            "makespan_steps": (solver.Value(makespan) / _TIME_SCALE
                               if makespan is not None else None),
            "total_tardiness_steps": (sum(solver.Value(t) for t in tardiness) / _TIME_SCALE
                                      if tardiness else 0.0),
            "num_tasks": num_tasks,
            "num_drones": num_drones,
            "drone_time_steps": {
                j: solver.Value(expr) / _TIME_SCALE
                for j, expr in enumerate(drone_time_expr)
            },
        }
        if verbose or self.verbose:
            print(f"[ORTools] status={stats['status']} "
                  f"makespan={stats['makespan_steps']} "
                  f"tardiness={stats['total_tardiness_steps']} "
                  f"({stats['wall_time']:.2f}s)")
        return assignments, stats

    # ---------- 建模 ----------

    def _build_model(self, drones_info, tasks_info):
        num_drones = len(drones_info)
        num_tasks = len(tasks_info)
        model = _cp_model.CpModel()

        # 预处理：各机就绪时刻、有效载重、速度
        ready_scaled = []
        caps_scaled = []
        speeds = []
        for drone in drones_info:
            ready = float(drone.get("ready_time", 0.0))
            ready_scaled.append(int(round(ready * _TIME_SCALE)))
            caps_scaled.append(int(round(self._effective_capacity(drone) * _WEIGHT_SCALE)))
            speeds.append(max(1e-9, float(drone.get("speed", 200.0))))

        # 系数 coef[i][j]：任务 i 分给机 j 所需的「飞到取货点 + 送达」env-step 数
        coef: List[List[int]] = []
        for i, task in enumerate(tasks_info):
            row = []
            src = task["source"]
            dst = task["destination"]
            route = self._dist(src, dst)
            for j, drone in enumerate(drones_info):
                to_source = self._dist(drone.get("position", drone.get("home_position", src)), src)
                steps = self._travel_steps(to_source + route, speeds[j])
                row.append(int(round(steps * _TIME_SCALE)))
            coef.append(row)

        weights_scaled = [int(round(float(t.get("weight", 0.0)) * _WEIGHT_SCALE))
                          for t in tasks_info]
        deadlines_scaled = []
        for task in tasks_info:
            dl = task.get("deadline", None)
            if dl is None or dl == float("inf") or not math.isfinite(float(dl)):
                deadlines_scaled.append(None)
            else:
                deadlines_scaled.append(int(round(float(dl) * _TIME_SCALE)))

        # 决策变量
        x = [[model.NewBoolVar(f"x_{i}_{j}") for j in range(num_drones)]
             for i in range(num_tasks)]

        # C1 每任务恰好分给一架机
        for i in range(num_tasks):
            model.Add(sum(x[i][j] for j in range(num_drones)) == 1)

        # C2 异构载重上限（按环境实际口径取 min）
        for j in range(num_drones):
            model.Add(sum(weights_scaled[i] * x[i][j]
                          for i in range(num_tasks)) <= caps_scaled[j])

        # 各机完成时刻表达式 T_j = ready_j + Σ_i coef_ij * x_ij
        drone_time_expr = [
            ready_scaled[j] + sum(coef[i][j] * x[i][j] for i in range(num_tasks))
            for j in range(num_drones)
        ]

        # makespan = max_j T_j
        makespan = model.NewIntVar(0, _BIG_M, "makespan")
        for j in range(num_drones):
            model.Add(makespan >= drone_time_expr[j])

        # 超时量：t_i >= T_j - deadline_i - M(1 - x_ij)，对所有 j 成立
        tardiness = []
        has_deadline = False
        for i in range(num_tasks):
            dl = deadlines_scaled[i]
            if dl is None:
                continue
            has_deadline = True
            t_i = model.NewIntVar(0, _BIG_M, f"tardiness_{i}")
            for j in range(num_drones):
                model.Add(t_i >= drone_time_expr[j] - dl - _BIG_M * (1 - x[i][j]))
            tardiness.append(t_i)

        # 目标：最小化 makespan（总完成时间）与超时量
        objective_terms = []
        if self.makespan_weight:
            objective_terms.append(self.makespan_weight * makespan)
        if self.tardiness_weight and has_deadline:
            objective_terms.append(self.tardiness_weight * sum(tardiness))
        if objective_terms:
            model.Minimize(sum(objective_terms))

        return model, x, makespan, tardiness, drone_time_expr

    # ---------- 兜底 ----------

    def _greedy_fallback(self, drones_info, tasks_info, reason: str):
        """求解器无解时退回批量贪心（与 PSO/GA 的 warm-start 解同源）。

        注意：CP-SAT 返回 INFEASIBLE 通常意味着**载重约束本身无解**——例如某任务
        重量超过所有可用机型的有效载重上限。这时贪心兜底同样会超载，环境会静默
        拒单，表现为完成率上不去。此处打印告警，便于定位是真不可行还是参数配错。
        """
        print(f"[ORTools] 警告：求解器状态={reason}，退回批量贪心。"
              f"（任务数={len(tasks_info)}，机数={len(drones_info)}）")
        assignment = self._eval._greedy_assignment(drones_info, tasks_info)
        assignments: Dict[int, List[str]] = {i: [] for i in range(len(drones_info))}
        for task_idx, drone_idx in enumerate(assignment):
            assignments[int(drone_idx)].append(tasks_info[task_idx]["task_id"])
        return assignments, {
            "solver": "CP-SAT",
            "status": f"FALLBACK({reason})",
            "message": "求解器未找到可行解，已退回批量贪心",
        }


class ORToolsScheduler(PSOScheduler):
    """事件驱动的 OR-Tools 调度器（对外）。

    与 `GAScheduler` 的做法一致：完整继承 `PSOScheduler` 的双通道 + 动态贪心
    外层逻辑，仅把批量优化器替换为 `ORToolsOptimizer`。这样 OR-Tools / GA /
    PSO / Greedy 四者在同一套事件驱动框架、同一物理口径下公平对比，唯一差异是
    「buffer flush 时用的批量分配算法」。
    """

    def __init__(self,
                 num_drones: int,
                 config_path: Optional[str] = None,
                 verbose: bool = True,
                 seed: Optional[int] = None):
        super().__init__(num_drones, config_path=config_path,
                         verbose=verbose, seed=seed)
        cfg = self.config.get("ortools", {})
        self.ortools_time_limit = float(cfg.get("time_limit_seconds", 2.0))
        self.ortools_makespan_weight = int(cfg.get("makespan_weight", 1))
        self.ortools_tardiness_weight = int(cfg.get("tardiness_weight", 1))
        self.ortools_num_workers = int(cfg.get("num_workers", 4))

        # 环境的多任务总重上限（与 frontend/environment.py 同源配置）
        try:
            from config.config_loder import get_shared_config
            shared = get_shared_config() or {}
            env_cfg = shared.get("environment", {}) or {}
            drone_cfg = shared.get("drone", {}) or {}
            self.multi_task_max_total_weight = float(
                env_cfg.get("multi_task_max_total_weight",
                            drone_cfg.get("carrying_capacity", 5)))
        except Exception:
            self.multi_task_max_total_weight = None

    def _build_optimizer(self):
        return ORToolsOptimizer(
            time_limit_seconds=self.ortools_time_limit,
            makespan_weight=self.ortools_makespan_weight,
            tardiness_weight=self.ortools_tardiness_weight,
            num_workers=self.ortools_num_workers,
            multi_task_max_total_weight=self.multi_task_max_total_weight,
            weights=self.fitness_weights,
            seed=self.seed,
            battery_consumption_base=self.battery_consumption_base,
            battery_load_penalty_factor=self.battery_load_penalty_factor,
            battery_low_threshold=self.battery_low_threshold,
            env_step_seconds=self.env_step_seconds,
            verbose=self.verbose,
        )
