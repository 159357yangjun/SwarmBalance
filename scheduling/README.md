# backend_si — PSO 调度模块

群体智能（Swarm Intelligence）调度模块，为多无人机配送系统提供基于粒子群优化（PSO）的任务分配，并在外层包了一层事件驱动 + 双通道 + 动态贪心的调度逻辑。

## 模块文件

| 文件 | 作用 |
|---|---|
| [`pso_scheduler.py`](pso_scheduler.py) | 包含两个类：`PSOOptimizer`（PSO 算法核心）+ `PSOScheduler`（对外调度器） |
| [`fitness_evaluator.py`](fitness_evaluator.py) | 适应度评估器，支持多目标加权 / 帕累托前沿 |
| [`config.yaml`](config.yaml) | 所有可调超参数集中在这里 |
| [`requirements.txt`](requirements.txt) | 依赖：`numpy`、`pyyaml` |

## 架构概览

```
                    ┌─────────────────────────────────────────┐
                    │              PSOScheduler               │
                    │   （对外唯一入口，事件驱动状态机）       │
                    │                                         │
  obs, current_time │  ┌──────────────────────────────────┐  │  action
  ────────────────► │  │  step()                          │  │ ───────►
                    │  │   1. 检测新任务                  │  │
                    │  │   2. 检测刚空闲的无人机          │  │
                    │  │   3. 检查 buffer flush           │  │
                    │  │   4. 派发队头任务给空闲机        │  │
                    │  └──────────────────────────────────┘  │
                    │             │                           │
                    │     buffer flush 时调用                 │
                    │             ▼                           │
                    │  ┌──────────────────────────────────┐  │
                    │  │  PSOOptimizer.optimize()         │  │
                    │  │   纯算法：粒子群迭代 →           │  │
                    │  │   返回 {drone_idx: [task_id]}    │  │
                    │  └──────────────────────────────────┘  │
                    └─────────────────────────────────────────┘
```

`PSOScheduler` 是仿真主循环唯一需要打交道的类。`PSOOptimizer` 单独可用——如果你只想跑一次 PSO 优化（不需要事件驱动），可以直接 new 一个。

## 调度逻辑

### 外层：双通道任务分配

新任务到达时分两条路径：

1. **直通通道**：若存在"空闲且队列为空"的无人机 → 立即贪心分配给最近的那架
2. **缓冲通道**：否则进入 `pending_buffer`，等待批量 PSO

`pending_buffer` 在以下三个条件**任一**满足时触发 PSO 批量分配：

| 触发器 | 配置项 | 含义 |
|---|---|---|
| `size` | `dual_channel.buffer_size_threshold` | buffer 任务数达到阈值 |
| `emergency` | `dual_channel.emergency_ttl` | buffer 中存在剩余时间小于此值的紧急任务 |
| `timeout` | `dual_channel.buffer_timeout` | 最早任务在 buffer 中停留超过此时间步数（防止饿死） |

#### PSO 迭代优化目标

当 buffer flush 触发后，`PSOOptimizer` 对批量任务进行全局优化，目标是找到一个任务到无人机的分配方案，使得**多目标加权适应度最大化**：

```
fitness = w₁ · on_time_rate - w₂ · avg_delay - w₃ · total_energy
```

其中：

- **on_time_rate**：准时完成率，即在 `remaining_time` 内完成的任务占比
- **avg_delay**：平均延迟时间，超时任务的平均超时量（越小越好，故取负）
- **total_energy**：总能耗，所有无人机飞行距离之和的归一化值（越小越好，故取负，由于电量设计部分未完成，当前没有优化此项）

权重 `w₁`、`w₂`、`w₃` 在 `config.yaml` 的 `fitness_weights` 节配置。PSO 通过 `max_iterations` 轮迭代，每轮更新粒子速度和位置（分配方案），追踪全局最优解 `gbest` 和个体最优解 `pbest`，最终返回适应度最高的分配方案。

### 内层：动态贪心重排

无人机送完一次货时（`is_free` 由 False 变为 True），对其剩余队列做一次动态贪心重排：

```
score(task | 当前机位) = w_p · priority
                       + w_u · urgency(remaining_time)
                       - w_d · distance(机位, task.source)
```

每选出一个任务后，从该任务的目的地重新评分剩余任务，逐个挑选——**而非一次性按静态分数排序**，因为 TSP 类问题的路径成本依赖前一个访问点。

权重在 `config.yaml` 的 `dynamic_greedy` 节里调。

## 配置文件

所有超参数集中在 [`config.yaml`](config.yaml)，分 5 节：

```yaml
dual_channel:    # 双通道触发条件
  buffer_size_threshold: 8       # 攒多少个任务触发批量 PSO
  emergency_ttl: 100.0           # 紧急任务的剩余时间阈值
  buffer_timeout: 50             # buffer 老化超时

pso:             # PSO 算法核心
  num_particles: 20              # 粒子数
  max_iterations: 30             # 迭代次数
  inertia: 0.7                   # 惯性权重 w
  cognitive: 1.5                 # 个体学习因子 c1
  social: 1.5                    # 社会学习因子 c2

fitness_weights: # 适应度多目标权重
  on_time_rate: 0.4              # 准时率
  avg_delay: 0.4                 # 平均时延
  energy: 0.2                    # 能耗

dynamic_greedy:  # 内层贪心评分权重
  priority: 10.0                 # 任务优先级
  urgency: 500.0                 # 紧迫度（1 / max(1, remaining_time)）
  distance: 1.0                  # 距离惩罚

drone:           # 物理参数
  capacity: 5                    # 载重
  speed: 200.0                   # 飞行速度
```

## 使用方式

### 标准用法（仿真主循环）

```python
from backend_si.pso_scheduler import PSOScheduler

scheduler = PSOScheduler(num_drones=3, verbose=True)  # 默认读 backend_si/config.yaml

while running:
    action = scheduler.step(observation, current_time=env.current_time)
    observation, reward, running, _ = env.step(action)

# 查看事件统计
print(scheduler.get_stats())
# {'immediate_assign': 12, 'buffered': 87, 'flush_size': 11,
#  'flush_emergency': 3, 'flush_timeout': 0,
#  'reorders': 24, 'dispatches': 99}
```

### 自定义配置（对照实验）

```python
sched_a = PSOScheduler(num_drones=3, config_path='exp_configs/aggressive.yaml')
sched_b = PSOScheduler(num_drones=3, config_path='exp_configs/conservative.yaml')
```

### 只用 PSO 算法核心

```python
from backend_si.pso_scheduler import PSOOptimizer

opt = PSOOptimizer(num_particles=30, max_iterations=50)
assignments, stats = opt.optimize(drones_info, tasks_info, current_time=0)
# assignments: {drone_idx: [task_id, ...]}
# stats: {'iterations': 50, 'best_fitness': ..., 'fitness_history': [...]}
```

## 观察空间约定

`PSOScheduler.step()` 期望 `observation` 至少包含：

| 字段 | 类型 | 含义 |
|---|---|---|
| `drone_positions` | `List[List[float]]` | 各无人机的 (x, y) |
| `unassigned_tasks` | `List[Dict]` | 未分配任务，每项含 `task_id`、`source`、`destination`、`remaining_time`、`priority`、`weight` |
| `drone_is_free` | `List[bool]` | （推荐）扁平的无人机空闲状态 |
| `drone_free_masks` | `List[List[bool]]` | （兼容字段）若没有 `drone_is_free` 则从这里推断 |

## 事件统计

`scheduler.get_stats()` 返回一个 dict，便于诊断调度行为：

| 字段 | 含义 |
|---|---|
| `immediate_assign` | 走直通通道的任务数 |
| `buffered` | 进 buffer 的任务数 |
| `flush_size` / `flush_emergency` / `flush_timeout` | 三种 flush 各触发了多少次 |
| `reorders` | 内层动态贪心重排触发次数 |
| `dispatches` | 实际派发到无人机执行的任务数 |

如果 `buffered` 远大于 `immediate_assign`，说明系统大部分时间都在过载——要么调大 `buffer_size_threshold` 让 PSO 一次看到更多任务、要么加无人机数量。

## 调参速查表

| 现象 | 调整建议 |
|---|---|
| PSO 触发太频繁，调度抖动 | 调大 `buffer_size_threshold` |
| 紧急任务被忽视 | 调大 `emergency_ttl`（更多任务被视为紧急） |
| 有任务在 buffer 里饿死 | 调小 `buffer_timeout` |
| PSO 收敛不充分 | 调大 `num_particles` 或 `max_iterations` |
| PSO 太慢 | 同上调小 |
| 高优先级任务没被前置 | 加大 `dynamic_greedy.priority` 或 `dynamic_greedy.urgency` |
| 路径绕远 | 加大 `dynamic_greedy.distance`（让贪心更看重就近） |
| 多目标偏好（准时 vs 能耗） | 改 `fitness_weights.*` 的相对比例 |

## 当前局限

- **一次只带一货**：`PSOOptimizer.evaluate_fitness` 严格"取-送-取-送"地仿真无人机执行，没有"装多个包裹一次性送"的捆绑取货逻辑。`drone.capacity` 字段已经在配置里，但只在单任务超重时触发返仓，正常调度路径不利用。
- **粒子编码只覆盖分配，不覆盖顺序**：每架无人机内的任务执行顺序由内层动态贪心决定，不参与 PSO 进化。
- **PSO 起点近似**：buffer flush 时用"已有队尾任务的目的地"作为无人机的 PSO 评估起点，而非未来时刻的真实位置——一个粗略但开销低的近似。

## 依赖

```
numpy >= 1.20.0
pyyaml >= 6.0
```

`matplotlib` 仅在做适应度曲线可视化时才需要。
