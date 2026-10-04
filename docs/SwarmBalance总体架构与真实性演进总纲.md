# SwarmBalance 总体架构与真实性演进总纲

> **本文档地位**：本项目最高优先级技术设计参考。任何后续开发若与本文冲突，
> **先更新本文并说明理由，再改代码**；禁止边写代码边悄悄改变总体架构。
>
> 取证基准：HEAD `f302822`（2026-10-03）。文中每个行号都是本轮亲自打开文件读到的；
> 标 **未验** 的是本轮没有复核、不应作为决策依据的推断。

---

## 1. 项目定位

| 口径 | 名称 | 约束 |
|---|---|---|
| 正式申报（历史承诺，不改写） | 《群智优衡——异构多无人机集群三维协同调度仿真平台》 | 申请书原文保持；§3 负责说明"三维"的实际达成边界 |
| 未来工程定位 | 城市低空多无人机智能调度与多层级验证平台 | 演进方向，不回溯修改历史材料 |

一句话现状判断：**当前是一个真实数据约束下的二维调度仿真器，不是飞行物理仿真器。**
这个定性由 §3 的证据支撑，不由界面观感决定。

---

## 2. 当前能力基线（四态标注，禁止用 UI 可显示冒充模型已支持）

| 能力 | 状态 | 证据 |
|---|---|---|
| 异构机队 + 多重约束调度 | **已实现** | `frontend/greedy/scheduler.py`、`frontend/matching.py` |
| Greedy / GA / PSO / OR-Tools 四种策略 | **部分实现** | 入口齐备，但默认轻载下三个批量优化器实测 `optimize_calls=0`（`docs/取证输出/speed_fallback_gate.txt`）⇒ 名义存在、实际未介入 |
| 机巢泊位 + 换电资源仲裁 | **已实现** | `frontend/environment.py:303-312, 453-854` |
| SLA / deadline | **已实现** | `frontend/task.py:369-370, 520-527` |
| 动态任务到达 | **已实现** | `frontend/environment.py:293-301` |
| OSM 建筑与路网 | **已实现（内容 A / 溯源 E）** | `frontend/data/map/part_of_yangpu.osm`，SHA-256 见 `data/provenance/osm_census.csv` |
| 风场输入 | **已实现（接口 A / 换算 C）** | Open-Meteo 1008 小时逐时，请求 URL 可重放 |
| 能耗模型 | **部分实现** | `frontend/drone.py:148-172` 距离×基础率×(1+载重惩罚)×风倍率；系数分级见 `data/provenance/parameters.csv`（heavy=A/C，light/standard=D） |
| 绕障路径规划（A* + 可见图） | **已实现** | `frontend/environment.py:1842-1945`，生产派单经 `:1072` 调用 |
| 实验系统（preset/grid/paired seeds/sensitivity/provenance） | **已实现** | `experiments/runner.py`、`console/test_*.py`、`data/provenance/` |
| FastAPI + Vue + Three.js 控制台 | **已实现** | `console/server.py:264-269`、`console/static/index.html` |
| 第三维 z / altitude 状态量 | **尚未实现** | 全仓 Python 内 `self.z`/`altitude` 零命中（子代理审计 + 我复验一致） |
| velocity 矢量 / acceleration / jerk / turn_radius | **尚未实现** | `Drone` 只有标量 `speed`（`frontend/drone.py:57,67`）；二阶动力学零命中 |
| yaw / heading / attitude | **尚未实现** | 零命中；图标朝向不来自状态量 |
| Trajectory（x(t),v(t),a(t)） | **概念存在但未进入模型** | `console/sim_session.py:126,189` 的 `trajectories` 是 UI 描点历史，不参与决策或物理 |
| 飞控闭环 / 传感器 / 定位误差 | **尚未实现** | 无 estimator 层；调度器看到的是上帝视角真值 |
| Plan vs Actual 校验 | **尚未实现** | 无 planned/actual 双轨记录 |
| 大地图流式加载（tile/quadtree/LOD） | **尚未实现** | 固定单文件 bbox |

---

## 3. 当前模型真实性边界（诚实条款，对外表述受此约束）

1. **运动学是二维一阶积分**：`max_distance = v * time_step`（`frontend/drone.py:258-259`），
   位移沿 `scheduled_position` 逐点直线推进（`frontend/drone.py:358-360`）。无加速度、无转弯半径、无朝向。
   一步之内若剩余距离 ≤ `max_distance` 则直接吸附到目标点（`frontend/drone.py:317-320`）。
2. **障碍是"二维 + 无限高棱柱"，不是"高度没参与"**：`frontend/environment.py:174` 用 `height > 20`
   筛出高楼，紧接着 `:178` 就把元素重塑成 `(geometry.bounds, geometry)` —— **height 值在此被丢弃**。
   此后相交判定只用 bbox 四轴 + `LineString × Polygon.intersects`（`:2008/2013/2015`），
   A* 启发式还同时充当 h、边权 g 增量与终止判据三职（`:1910/1918/1933/1938`，全是纯二维欧氏距离）。
   ⇒ 真实语义：**>20 m 的建筑整条垂直射线不可穿；≤20 m 无论 19 m 还是 3 m 完全透明。**
   这三处本轮已独立复验；另注意 `:176-177` 自称 bbox 剔除是"等价优化"——该论证只在二维成立，加 z 后失效。
   禁止表述为"已实现三维避障"，也禁止轻描成"只是高度没接进来"。
   运行时唯一读 height 的消费者是渲染：`console/static/index.html:2300` extrude depth、`:2301` 配色。
   完整爆炸半径（≈158 条、7 类硬阻塞、会被改红的测试名单）见 `docs/二维假设清单.md`。
3. **速度只影响运动学时间，不影响单位距离能耗**：`consumption_base` 与 speed 无关。
   这是模型的显式局限，不是缺陷——但它使"高速更费电"这类结论无法在本系统中得出。
4. **风只进能耗**（E1）：`wind_along` 参与 `_wind_factor`（`frontend/drone.py:174-195`），
   不改位移、不改速度。E2/E3（风对运动学的影响）未实现。
5. **不存在六自由度动力学、飞控闭环、传感器闭环**。本系统适用于**调度策略比较**，
   不适用于真实飞行性能预测。
6. **设备参数只有两格是真数据**：OSM 底图（内容侧 A）与 FlyCart 30 官方规格（A）+ 其派生能耗（C）。
   轻/中载档的电池与能耗系数是情景参数（D），已在 `config/simulation.json` 改名脱离厂商身份。
7. **两个假设参数的敏感性已定级**（`docs/真实性审计表.md` §10）：
   `swap_time` = 高度敏感（完成率 −11%~−17%）；SLA = 评价敏感（超时率必须绑定档位报告）。

### 3.1 本轮审计新发现的两条事实性缺陷

| # | 发现 | 证据 | 影响 |
|---|---|---|---|
| F1 | **死代码冒充主路径**：`GreedyScheduler.schedule_all_drones` 无任何调用者，其内 `route = [当前位置] + [各目的地]`（两点折线、绕过 A*）永不可达 | 严格 grep `schedule_all_drones` 仅命中定义行 `frontend/greedy/scheduler.py:191`；`schedule_route` 的生产调用者是 `frontend/environment.py:1072` | 读代码者会误判"贪心不走 A*"。Phase 1 应删除或明确隔离，不得留在主路径旁 |
| F2 | **任务状态机语义缺口**：枚举白名单是 `pending/in_progress/completed/failed`（`frontend/task.py:118-123`），**没有 created/loaded/delivered**；且送达完成时不调 `update_status("completed")`，"已完成"靠统计推断 | `frontend/environment.py:374-443` 的 `_record_task_completion` 内无状态改写；UI 侧 `in_progress/loaded` 由 `console/sim_session.py:917-921` 现算、不回写 Task | "任务生命周期"这一核心研究对象在模型里没有单一真源。Phase 1 必须先补 MissionManager 的状态机，否则后续事件总线的语义无处安放 |

> 我对本节的一条自我纠正：审计过程中我曾断言"实验与网页控制台跑的是直线口径航程"。
> 复验后**撤回**——`greedy_action_from_observation` 只返回 `{drone_idx: [task_id]}` 的**决策**
> （`scheduler.py:235-237`），路线一律由 `env.step()` 经 A* 生成。故结项数据的里程是绕障后的，不是直线。

---

## 4. 目标分层架构

```
WorldModel ─ MissionManager ─ FleetScheduler ─ RoutePlanner ─ TrajectoryPlanner
                                                                        │
                                                    Executor Interface ─┤
                                                    ├── FastExecutor     │
                                                    └── HighFidelityExecutor (ROS2→PX4 SITL→Gazebo)
                                                                        │
                              Telemetry / StateStore ←──────────────────┘
                                        │
                                     EventBus ── Scheduler / UI / Logger / Validation
                                        │
                                    Re-Scheduling（必要时）
```

职责铁律（今后禁止混在同一个 `Environment` 类里）：

| 层 | 只回答 | 现在在哪 |
|---|---|---|
| FleetScheduler | **谁**执行哪个任务 | `greedy/scheduler.py`、`frontend/matching.py`、GA/PSO/OR-Tools |
| RoutePlanner | 从**哪里**走 | `frontend/environment.py:1842-1945`（A*，内联在 God Object 里） |
| TrajectoryPlanner | **何时何地**、多大速度/加速度、什么高度与航向 | **不存在** |
| Executor | 真的执行 | `frontend/drone.py:update()`（与调度、统计、资源仲裁耦合在同一对象） |

现状根因：`Environment` 是 **2024 行 / 43 方法**的上帝对象（`frontend/environment.py:157-2024`），
同时承担世界数据、时间推进、资源仲裁、任务生命周期、指标计算、观察构造、路径规划七类职责。
A* 作为它的方法存在 ⇒ **路径规划能力无法脱离该对象被复用、替换或单独测试**。

### 4.1 各模块目标定义

- **WorldModel**：OSM/建筑/高度/地形/天气/风场/空域/禁飞区/机巢/换电站/动态障碍/临时限制。
  扩展方向 Tile→Quadtree→Streaming→LOD。
- **MissionManager**：订单生命周期、pickup/delivery、payload、priority、SLA/deadline、取消、应急、任务事件。
  **必须先解决 F2 的状态机缺口**，否则 EventBus 的事件语义无处落地。
- **FleetScheduler**：保留现有四策略。研究重点转向 rolling horizon、增量重规划、不确定性、鲁棒调度。
  禁止让它知道无人机怎么飞。
- **RoutePlanner**：把 A* 从 `Environment` 抽成独立可测模块。候选 A*/Dijkstra/可见图/RRT*/PRM/OMPL；
  第一阶段优先适配现有 OSM polygon 数据结构。
- **TrajectoryPlanner**：Route ≠ Trajectory。逐步支持 x(t)/y(t)/z(t)/velocity/acceleration/yaw/turn constraints。
  候选 Bézier / B-Spline / cubic spline / polynomial / minimum-snap。目标是消灭瞬时 90° 转弯与恒速折线。
- **DroneState**：position/velocity/acceleration/heading-yaw/attitude/battery/payload/mission/health/communication/localization_quality。
  现为 34 个 `self.*` 字段但运动学只有 4 个（`frontend/drone.py:72,73,78,86`）。
- **Executor**：统一接口 + 两个实现。
  - `FastExecutor`：20~100 架、数百任务、大量 seed 的算法比较；逐步支持 trajectory follow/accel/turn/altitude/wind/energy。
  - `HighFidelityExecutor`：ROS2 → PX4 SITL → Gazebo，**先 1 架**，以后 2~5 架。禁止一开始把几十架塞进 Gazebo。
- **Telemetry/StateStore**：所有执行器输出统一状态（位置/速度/电量/任务进度/ETA/能量/route deviation/执行状态）。
  Scheduler 不直接读 Gazebo 内部状态，只读此接口。
- **EventBus**：TaskCreated / TaskAssigned / DroneTakeoff / DroneArrived / BatteryLow / DroneOffline /
  WindChanged / RouteBlocked / StationFull / CommunicationLost / TaskCompleted。各组件订阅。

---

## 5. 调度—航路耦合（未来核心研究方向之一）

当前调度打分用的是 `route_distance = math.dist(source, destination)`
（`frontend/environment.py:1507` → 喂给 `frontend/greedy/scheduler.py:172`）——**几何直线**。
而执行阶段走的是 A* 绕障路线（`frontend/environment.py:1072`）。

⇒ 已经存在一个真实的**预测/执行口径分裂**：调度器以为的距离 ≠ 实际要飞的距离。
这不是 UI 问题，是算法模型问题，必须单独研究：

```
Scheduler → 问 RoutePlanner："D3 到任务 A 实际可飞多远？" → route distance / ETA / 预估能耗 / 可行性
例：直线 2.1 km，绕障航路 3.4 km ⇒ 可能改变分配结果
```

**代价与纪律**：一旦距离成为决策变量，`swap_time`、SLA、fleet_mix、绕障代价权重之间将两两耦合。
现有的 n=5 配对符号检验在这种维度下给不出方向一致。因此接入时必须：
(a) 保留"关闭耦合"的对照面（同一份代码，只切一个开关）；
(b) 重新做一轮 S1/S2 式敏感性，而不是沿用今天的定级结论。

### 5.1 已证实事实（本轮审计，禁止再写"当前没有 Route Planner"）

| # | 事实 | 证据 |
|---|---|---|
| E1 | 生产路径中 **A\* 是活的**：路线由 `env.step()` 生成 | `frontend/environment.py:1045, 1071, 1761` → `plan_route_around_buildings:1842` → `a_star_pathfinding:1865` |
| E2 | Greedy action **只产生任务分配，不产生飞行路线** | `frontend/greedy/scheduler.py:235-237` 返回 `{drone_idx: [task_id]}` |
| E3 | `schedule_all_drones` 是死代码（其两点折线分支不可达） | `grep schedule_all_drones` 仅命中定义行 `:191` |
| E4 | 调度**预测**仍走欧氏直线 | `frontend/environment.py:1507 route_distance = math.dist(source, destination)` → `frontend/greedy/scheduler.py:172` |
| E5 | A\* 启发式是纯二维欧氏距离；高度值在过滤后即被丢弃 | `frontend/environment.py:1947-1951`；`:174` |

⇒ **真正的缺陷不是缺能力，而是口径分裂**：调度阶段以为的距离 ≠ 执行阶段真要飞的距离。

```
调度阶段：math.dist(start, target) → 认为 Drone A 更近
执行阶段：A* 绕建筑            → Drone A 实际要绕很远
例：A 直线 1.8 km / 实飞 3.7 km；B 直线 2.2 km / 实飞 2.5 km ⇒ 现系统选 A，应选 B
```

这个缺口比"再加一个算法"更有研究价值：它给出一个可证伪命题 ——
**几何距离假设会导致错误的机队分配**。

### 5.2 Phase 1/2 接口设计（本轮只设计，不实装）

抽离的硬约束来自实测：`is_path_clear` 在 2000 步里被调 **18 万次**而真正的 A* 只有 **34 次**
（`frontend/environment.py:1983-1984` 原注释）。所以接口必须自带世界版本标识，否则抽出去就把性能炸掉。
世界指纹已有现成实现，直接复用不另造：高楼多边形 WKT + 禁飞区启用/数量/名称/margin/几何
→ md5 前 16 位（`frontend/environment.py:1961-1967`）。

```python
@dataclass(frozen=True)
class RouteRequest:
    start: tuple            # (x, y)，Phase 4 前保持二维
    goal: tuple
    world_version: str      # 复用 _path_clear_bucket() 的几何指纹，禁止新造第二套口径
    vehicle_profile: VehicleProfile   # speed / carrying_capacity / battery_capacity
                                     # / consumption_base / load_penalty_factor
    constraints: RouteConstraints     # 载重、续航可行性、margin；不含时间（ETA 是输出）

@dataclass(frozen=True)
class RouteResult:
    feasible: bool
    waypoints: tuple        # ((x, y, tag), ...)，tag ∈ {source, dest, waypoint}，与现有格式一致
    distance: float         # 折线累加长度，非欧氏
    estimated_time: float   # distance / profile.speed
    energy_estimate: float  # distance × base × (1 + load_penalty) —— 与 drone.py:163-167 同式
    metadata: dict          # {expanded_nodes, cache_hit, fallback: bool}
```

`waypoints` 的三元组格式必须与现状逐字一致（`frontend/environment.py:1805-1818`），
否则 Gate A 无法用"输出相同"来证明只是搬家。

```python
class RouteCostProvider(Protocol):
    def cost(self, req: RouteRequest) -> RouteCost: ...   # distance / eta / energy / feasible

EuclideanRouteCostProvider   # 包装现状（math.dist），默认启用 ⇒ 保证零漂移
AStarRouteCostProvider       # 委托 RoutePlanner；只在 Gate C 实验里开启
```

两面共存是关键设计：**默认仍是直线 ⇒ 架构重构可以声称没改模型；
切成 A* 才是实验变量**，二者不混在同一笔提交里。缓存键 `(start_cell, end_cell, vehicle_type, world_version)`，
仅在禁飞区/障碍/天气约束变化时失效。

### 5.3 Mission / Task 状态机（修 F2）

现状三处不一致（字段级证据待 Q2 审计补全）：枚举白名单 `pending/in_progress/completed/failed`
（`frontend/task.py:118-123`）缺 created/loaded/delivered；送达完成不回写状态（`frontend/environment.py:374-443`）；
UI 侧 `in_progress/loaded` 由会话层现算（`console/sim_session.py:917-921`）。

设计目标态（命名以能覆盖现有语义为准，不追求好看）：

```
CREATED → QUEUED → ASSIGNED → PICKUP_ENROUTE → LOADED → DELIVERY_ENROUTE → DELIVERED
                                              ↘ FAILED / CANCELLED / REASSIGNED（异常支路）
```

规则：① 状态只能由单一所有者（MissionManager）改写，其余组件只读；
② 每次转移发事件并进日志，带 `(task_id, from, to, sim_time, reason)`；
③ 会话层与 UI **不得再自行推断**状态 —— 这是 F2 的收口点；
④ 合法转移表显式声明，非法转移抛错而非静默。
本轮只定义状态与转移表，不重写调用点。

### 5.4 Phase 1 验证门（三条，缺一不可）

| 门 | 判据 | 为什么要它 |
|---|---|---|
| **Gate A** Route 抽取等价 | 同地图同起终点：旧 `Environment` A* vs 新 `RoutePlanner`，逐项比 `feasible` / `waypoint 序列` / `distance`，要求逐位一致或在写明容差内一致 | 证明"只是拆架构，没偷偷改实验模型" |
| **Gate B** 默认零漂移 | `RouteCostProvider` 仍为 Euclidean 时，正式 fixture（C-1/C-2 × paired seeds）全部核心 KPI 差异指标数 = 0 | 沿用本轮改名提交已验证过的 Δ=0 判据；防止抽离顺手改变行为 |
| **Gate C** A*-aware 调度实验 | 只有切到 `AStarRouteCostProvider` 才允许调度行为变化，且该变化必须作为**独立实验**分析（completed/timeout/mean_delay/总里程/energy/reassignment/runtime） | 架构重构与模型变更分离；否则结论归因不清 |

Gate A/B 必须在同一笔"搬家"提交里同时绿；Gate C 属于另一笔实验提交。



---

## 6. 2.5D / 3D 演进

第一阶段只做 **2.5D**：building = polygon + height，drone = x,y,z。
允许研究绕楼、飞越、爬升、下降 —— 这时建筑高度数据才真正进入模型（对应 §3.2 的解除）。
不立即追求完整城市 3D。

---

## 7. 大世界地图系统

解决固定 `part_of_yangpu.osm` 问题：City Map → Tiles/Chunks → Quadtree → Streaming → LOD。
近处高精度加载、远处低精度或不加载。
**WFC 只是未来合成测试城市生成工具，不是地图流式加载算法**，禁止混为一谈。

---

## 8. 感知与定位（后置层）

正常城市配送：GPS + IMU 优先。仅在 GPS-denied / 室内 / 城市峡谷 / 未知环境才考虑
Visual SLAM / VIO / LiDAR SLAM / LIO-SAM。
LIO-SAM 属于感知定位层，**不是核心调度算法**，禁止为技术名词的高级感强行加入。

引入这一层的真正判据：当 Scheduler 看到的不再是上帝视角真值，而是 estimated state。
在此之前加 SLAM 没有可验证的对象。

---

## 9. 局部避障

区分 Global Route 与 Local Planner。遇动态障碍优先局部绕行，**不是每次都重跑整个 GA**。
可研究对象：其他无人机、临时障碍、移动障碍、临时禁飞区。

---

## 10. 通信模型

逐步加入 latency / packet loss / disconnect / bandwidth / reconnect。
研究问题：失联后无人机 hover / return / continue / autonomous completion，以及是否触发重调度。

---

## 11. 故障与韧性

支持 battery anomaly / drone fault / station failure / station congestion / GPS degradation /
communication loss / sudden wind / task surge / route blocked，并要求系统自动
state update → reassignment → route replan → ETA recalculation。
注：当前已有 `out_of_service` 冻结与故障回收重排队（`frontend/drone.py:252-254`、`frontend/environment.py:525`），
可作为该模块的起点而非从零开始。

---

## 12. Explainable Scheduling

每次分配可解释：候选机的 ETA / Energy / Score，被拒原因（如 payload infeasible），最终选择及依据。
这将是控制台的重要组成，且能直接复用 §5 的 route-aware 估计量。

---

## 13. Plan vs Actual（未来验证系统核心页面）

每任务保存 planned route / actual route、predicted ETA / actual ETA、predicted energy / actual energy，
输出 ETA error / energy error / route deviation。
FastSim、Gazebo、真实 flight log 统一用这种比较。

⚠️ 现状提醒：今天**还没有** planned/actual 双轨记录，所以这一页不能靠现有数据拼出来。

---

## 14. 多层级验证体系

| 级 | 内容 | 当前状态 |
|---|---|---|
| L0 | 单元 / 数学测试 | **已有且强**：门 + 变异测试 + 两面夹具（`console/test_*.py`） |
| L1 | Fast Simulation | **已有** |
| L2 | 真实飞行日志回放 | **未取得**：CMU KiltHub 403；Zenodo PX4 日志已定位但未证真机 |
| L3 | PX4 SITL + Gazebo | 未实现 |
| L4 | HITL | 未实现 |
| L5 | 小规模真飞 | 未实现 |

原则：**不允许只让 Simulator 自己证明自己。**

---

## 15. 四条主研究方向

| 代号 | 方向 | 价值 | 前置依赖 |
|---|---|---|---|
| A | 动态多约束调度（新任务进入、rolling horizon、机队状态变化、能量/SLA/机巢约束） | 最高 | 现有资产即可，成本最低 |
| B | 调度—航路耦合（§5） | 最高 | RoutePlanner 抽出 + 敏感性重做 |
| C | 不确定性与鲁棒调度（风不确定、能耗预测误差、ETA 不确定、故障、通信） | 高 | 需先有误差来源 ⇒ 依赖 L2/L3 |
| D | Multi-Fidelity 校准（FastSim vs PX4/Gazebo vs 真实日志，建立快速模型误差范围） | 高 | 依赖 Phase 6-7 |

---

## 16. 非核心技术（只作扩展）

SLAM/LIO-SAM（仅在定位问题成立时）、WFC（仅合成城市）、Photorealistic rendering（够展示即可，
不是科学真实性核心）、**自研飞控（禁止作为当前路线，优先 PX4）**。

---

## 17. 阶段路线（含验收条件与风险）

### 17.0 Phase 1B 细分（2026-10-04 冻结，取代此前"一步统一成本"的写法）

原 §17 的 Phase 2 已拆成可单独归因的小步。**每步只换一种现实信息**，否则结果变化无法归因：

| 步 | 主题 | 替换内容 | 前置 | 状态 |
|---|---|---|---|---|
| **1A** | RoutePlanner 抽离 | A* 从 `Environment` 迁出，行为零漂移 | — | ✅ `c0af7c7`（Gate A 35 例等价 / Gate B 25 指标 Δ=0） |
| **1B-0** | Route discrepancy profiling | 量 Euclidean vs A*：detour 分布 + **ranking inversion** | 1A | ⚠️ `42e5838`，原公布值 **7/10676 = 0.07% 已作废**（量具缺陷 e，见下）；修正后 **7/302 = 2.32%** |
| **1B-1** | distance-aware 调度 | 仅把距离口径换成实际航路距离；ETA/energy/range 保持原逻辑 | 1B-0 | ✅ 本轮（H0 **被否**，结论见 §17.1） |

| **1B-2** | ETA-aware 调度 | `ETA = planned_route_distance / speed` 替 `euclid/speed` | 1B-1 结论 | 待做 |
| **1B-3** | energy / range feasibility | 续航可行性按实际航路判定；不可行须被检测而非静默失败 | 1B-2 | 待做 |
| **1C** | Task State / Telemetry 单一真源 | 修 F2：显式状态机 + 派生量收口 | 1B-* | 待做 |
| **2** | TrajectoryPlanner | Route → x(t),v(t),a(t),yaw；消灭瞬时转向与恒速折线 | 1C | 待做 |

**1B-1 预注册假设（先写下再看数，禁止事后编解释）**
- `H0`：distance-only 切换后 C-1/C-2 全部核心 KPI 逐值不变，或差异 < 1 单任务。
  （依据 1B-0：inversion 仅 0.07%，且最大 detour ratio ≤ 1.0833。）
- `H1`：若完成率/超时率变化 ≥ 2 单，则必须能追溯到 1B-0 记录的那 7 组翻转中的具体一次分配；
  追不到即说明存在我尚未识别的第三条路径，须先查机制再谈结论。
- 算法范围：**只用 Greedy + GA**。PSO 在 C-1/C-2 实测 `optimize_calls=0`（两次独立复现），
  不具备对照价值；OR-Tools 介入/回退率未闭合。不为凑"四算法"把未真正介入优化的结果混进来。

### 17.1 1B-1 实测结果（2026-10-04）：H0 被否，且 H0 的依据本身也是错的

**先说量具**：H0 引用 1B-0 的 `7/10676 = 0.07%`，而那个分母是伪造的 ——
`environment.py:1591-1614` 是**截断之后才补 `__pad_` 占位任务**，Greedy 却是"先剔占位、
再 `[:candidate_limit]`"（`scheduler.py:45-48 → :98`）。旧探针直接对 `obs[:60]` 取候选 ⇒
既把 `(0,0)` 坐标的假腿数进分母、又漏掉真任务。修正后同一判据重跑得 **7/302 = 2.32%**，
用 Greedy **真实评分函数**（而非"pickup 最短"代理）重放则得 **5/302 = 1.66%**。
⇒ 教训固化：**代理判据测出的"小"不能当 H0 的依据**；三档数字（0.07% / 2.32% / 1.66%）里
只有后两档可用，且它们口径不同、不可互换引用。

**实验**：C-1/C-2 × {greedy, ga} × seed 40901–40903 × {euclidean, planned_distance}，
每 seed 两面各一跑（共 24 格）。产物 `docs/取证输出/phase1b1_paired_experiment.txt`。

| 面 | 结果 |
|---|---|
| Greedy | **H0 被否**：完成任务数 Δ ∈ {−1, +4, +4}（C-1）、{+1, +2, −3}（C-2）；超时率最大 \|Δ\| = 0.074；总飞行距离最大 \|Δ\| ≈ 4095 m |
| GA | **逐位不变**（10 项 KPI × 6 seed 全 Δ=0）——但这是**阴性对照**，不是"GA 更稳健" |

**GA 为什么算阴性对照而不是空转**（这点必须写清，否则等于什么都没证）：
C-1 seed=40901 实验面上 `GAScheduler.get_stats()` 有 `flush_timeout=20`（批量优化器真进了 20 次），
同时 `route_cost_provider.stats().calls = 0` ⇒ 后端一行都不读 provider（门 G5 钉成源码断言）。
所以 GA 面的零漂移证明的是"**距离口径确实只从 Greedy 那三个点进入决策**"，即单变量成立。

**噪声底**：同配置同 seed 连跑两次 worker，4 格的 完成任务数/生成任务数/超时率/总飞行距离/总能量消耗
drift **全为 0.0** ⇒ 上面任何非零 Δ 只能由切换造成，不存在"这本来就是噪声"的退路。

**归因分两层，不许混**：
- L1 机制通道存在性（`untraceable()`）：本轮"无断链"。但它只排除"planner 一次没参与却变了"，
  `deltas` 非空是恒真前提 ⇒ **它不构成"已追溯"**。
- L2 逐事件归因（`phase1b1_attribution_trace.py`，同一初始状态 deepcopy 后分叉各自跑到结束）：
  每个 seed 都给出首分歧步与换掉的任务对，如 `C1 seed=40903 首分歧@step=133 drone1 task_13→task_16`。
  ⚠️ 该探针的重放 `max()` tie-break 与生产不同（生产按列表顺序、探针按 `(score, task_id)`）⇒
  它的**分歧步数上界与完成数差值不得当精确复算值引用**，只有"第几步、换了谁"这类定性结论可用。

**方向性观察（n=3，不做显著性宣称）**：C-2 两面符号相反（seed 40901/40902 变好、40903 变差），
C-1 以变好为主（2 正 1 负）⇒ "实际航路距离"在本世界上**没有稳定的方向性收益**，
它改变的是分配格局而非吞吐水平。

**是否继续 1B-2**：继续，但理由要换。原设想"距离口径影响很小、ETA 才是大头"已被本层证据推翻
（距离单独就能改 4 个任务）。1B-2 的必要性现在建立在两点上：① `matching.compute_match` 的
ETA 输入仍按欧氏距离算 ⇒ 与刚接上的距离口径**自相矛盾**（预测用绕障距离、时效用直线速度），
这是内部一致性缺陷，修它比论证收益更硬；② 1B-1 已证明单变量切换在这套代码里做得到、且能被门管住。

**纪律 3 的落地（变异测试）**：M1「planned 面偷偷退回欧氏」→ G3 红；
M2「provider 挂着但调度器不读」→ G2 红。两条都是先红后绿，摘除后恢复。


**反玩具感四条纪律（每个 Phase 都适用，本轮起为硬要求）**
1. 每个数字都要有可复现的测量命令（写进产物或 provenance，不接受口头"跑过了"）。
2. **先画像再优化**：不得跳过 1B-0 这类诊断直接改调度器。
3. 护栏必须有牙：变异测试证明它会红；同时区分"无效变异未被抓"与"门失灵"。
4. **贡献比例必须实测，不得从系数比推断**（本轮已因此撤回过一次："w_dist 0.01 ⇒ 只占 1/200"）。

另加一条同族教训：判据要看**运行时生效值**而非源码默认 —— 我曾据 `scheduler.py:12` 的
`candidate_limit=1` 断言"inversion 结构上不可能"，实际 `config/simulation.json:11` 覆盖为 60。


> 顺序冻结。每阶段的"行为等价门"指：同 seed 逐 run 逐指标比对，差异指标数必须为 0
> （已由 E1 的 `test_wind_injection.py` 与本轮改名提交实践验证过这套判据可用）。

| Phase | 目标 | 输入 | 输出 | 受影响文件 | 验收条件 | 风险 |
|---|---|---|---|---|---|---|
| **0** | 真实性审计与算法有效性收尾 | 现有门与读数 | 四算法介入率/flush/fallback 画像定稿 | `console/test_speed_fallback_gate.py`、新增介入率门 | 每算法 `optimize_calls` 有非零正例或明写为零；禁用清单同步 | 未完成就进 Phase 1 会让后续结论继承旧缺陷 |
| **1** | 核心接口设计（不改变行为） | §4 分层 | Mission/Route/Trajectory/Executor/Telemetry/WorldModel 接口与类型 | 新增 `frontend/core/*`（接口+空实现）；删 F1 死代码 | **行为等价门 Δ=0**；F2 状态机单一真源并有夹具；不碰数值 | 接口设计过早固化会绑死后续选择；故只做接口不做迁移 |
| **2** | 抽离现有 A* + 统一预测/执行成本口径（**不是新增 RoutePlanner**，见 §5.1） | WorldModel 几何 + 现成世界指纹 | `RoutePlanner`（A* 迁入）+ `RouteCostProvider` 两面实现 | `frontend/environment.py:1842-1945,1978-2010` 迁出；`frontend/greedy/scheduler.py:172`、`frontend/matching.py` 改查询 | Gate A 等价（feasible/waypoints/distance 逐位或容差内一致）；Gate B 默认零漂移；A* 感知调度必须作为 Gate C 独立实验 | 距离成为决策变量 ⇒ 与 swap/SLA 耦合，须重做敏感性；且 `is_path_clear` 调用量是 A* 的 5000 倍，缓存键设计不当会把性能炸掉 |
| **3** | TrajectoryPlanner | route + 动力学约束 | x(t),y(t),v(t),a(t),yaw(t) | 新增 trajectory 模块；`frontend/drone.py:update()` 改为跟随轨迹 | 消灭瞬时 90° 与恒速折线（曲率/加速度有界断言）；行为等价门需**分面**：关轨迹面 Δ=0 | 移动链改动会影响全部既有 KPI 基线 |
| **4** | 2.5D | building height | z/climb/descent 进入状态与避障 | `drone.py`、`frontend/environment.py:174,1947-2015` | 高度真正参与碰撞判定（用高楼夹具证明摘掉高度会变红）；解除 §3.2 | 与"三维"申报口径相关，须同步论文表述 |
| **5** | 重构 FastExecutor | 上述接口 | 大规模实验继续成立 | `experiments/worker.py`、`drone.py` | 100 架规模回归；性能不退化（计时面） | 计时证据易被同机其他进程污染 |
| **6** | ROS2 + PX4 SITL + Gazebo（**1 架**） | Executor 接口 | HighFidelityExecutor | 新增 executor 实现 | 单架可跑通 takeoff→cruise→land；**先证真机/仿真之别** | 引入黑箱气动模型可能侵蚀现有可复算优势 ⇒ 只能作为 L3，不得反灌绝对能耗 |
| **7** | FastSim vs PX4/Gazebo，Plan vs Actual | 两套执行结果 | ETA/energy/route deviation 误差 | 新增 validation 层 | 误差有区间且可由第三方重算 | 样本量小易过度外推 |
| **8** | 扩到 2~5 架高保真 | Phase 7 | 多机高保真 | — | 实时性与同步可接受 | 资源开销跳增 |
| **9** | 按需 Camera/AprilTag/LiDAR/SLAM/通信故障/动态障碍 | 研究需求 | — | — | 每项须先过 §18 四问 | 名词驱动而非问题驱动 |

---

## 18. 新技术准入四问（强制闸门）

任何人提出 SLAM / LIO-SAM / WFC / Isaac Sim / Unreal / 某规划算法，必须先答：

1. 它解决哪个**现实问题**？
2. 它属于系统**哪一层**？
3. 它会改变**哪条决策链**？
4. **怎么验证**它真的有效？

答不出 ⇒ 不进主线。

---

## 19. 当前禁止事项

1. 推倒现有调度系统。
2. 全量重写成 ROS2。
3. 因为 Gazebo 更真实就抛弃 FastSim（两者是不同 fidelity，互补不可替代）。
4. 继续大量美化现有直线飞行动画（等 §4 骨架定死再做视觉）。
5. 把 SLAM 等高级名词强塞进系统。
6. 把建筑高度写成"当前已影响航迹"（§3.2 明写未影响）。
7. 把场景假设参数冒充现实测量（`data/provenance/truth.jsonl` 的 8 条 disabled_claim 为准）。
8. 因 UI 显示 3D 就声称模型是完整 3D 物理仿真（`console/static/index.html:2472-2473` 的 z 是按 state 硬编码的装饰值）。

---

## 20. 保留 / 重构 / 新增 清单

**保留（不动）**：Python、FastAPI、Vue、Three.js、四算法实现、机队/机巢/换电业务规则、
实验系统（preset/grid/paired seeds/sensitivity）、`data/provenance/` 与生成器、
`console/test_*.py` 门体系、OSM 与气象数据链。
依据：provenance 链只依赖配置文件与产物 CSV，不依赖 Environment 内部结构（**未验**：需在 Phase 1 用一次实际重构验证）。

**重构**：`frontend/environment.py`（God Object 拆分）、`frontend/drone.py:update()`
（一阶积分 → 轨迹跟随）、路径规划（抽出为独立模块）、任务状态机（修 F2）。

**新增**：WorldModel、MissionManager、RoutePlanner、TrajectoryPlanner、Executor 接口、
FastExecutor、HighFidelityExecutor、StateStore、Telemetry、EventBus、Validation(L2+)。
