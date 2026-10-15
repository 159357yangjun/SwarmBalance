# ARCH-03｜组件替换走查（仅设计与故障注入剧本）

## 共同规则

每次替换都产生新 AssemblyPlan 和新的 run identity；未变动的 World/Scenario、数据种子、时钟、其他组件版本保留并明确记录。不得以“只切换一个组件”暗示结果必然可比较；还要经过有效性/来源/行为等价门。历史 E0/E1 产物及 PR #41 的 L1 修复均不触动。

## Case A｜上海杨浦 OSM → 另一城市地图

**只改** `components.spatial` 的绑定、`datasets[map]` 的 ref/digest，以及必须声明的 `CoordinateConversionPlan`。若场景任务和机巢坐标是旧城市局部坐标，应明确重映射这些 Scenario 资源；无法映射就拒绝，并不能宣称零改场景。

装配检查：OSM/GeoJSON 原始许可证、字节 SHA-256、道路/建筑、CRS/轴序、投影米单位、可选建筑高度及未知比例，禁止“缺失高度=0”；空间边界，静态障碍与禁飞区解释；路径算法若依赖 A* 需具备 `spatial.route_query`，否则 `CAPABILITY_MISSING`。新地图的缓存按 digest+CRS 单独隔离。

**验收**：无地图路径硬编码进入 Dynamics/Scheduler/Metric；三个 provider 不改变接口；World/Scenario 中跨城市的实体坐标要显式通过/拒绝；地图身份记录到运行快照；初始世界与路径/能耗前后对比不宣称物理等价。

**反例**：新数据标 `coordinates:[121.5,31.2]` 但 CRS unknown，配置要求投影米：`CRS_MISMATCH`，装配 REJECT，无自动换算。

## Case B｜线性距离耗电 → 标定的分段能耗模型

**只改** `components.dynamics`、ModelManifest 的 id/version/digest、模型参数/能力绑定；若新模型额外要求温度/海拔/空速，必须补足 Event/Spatial 能力、DatasetManifest 或 **拒绝**，不可写死默认温度。

统一输入提案：`segment_distance_m, payload_mass_kg, ground_speed_mps, wind_uv_mps, dt_seconds, pre_state_energy_wh`，输出 `StateDeltaProposal` 中的能量变化与质量标志。注意这不是声称现有 `Drone.consume_battery` 符合契约。可重现校验要求：同输入同输出、0 距离边界、载重单调性适用范围、逆/顺风符号、Wh 守恒/电量非负；复杂模型的非单调特征必须在 manifest 声明，不能硬套线性 B2 断言。

**门禁**：旧模型当前 `current_load` 与空载里程定义冲突，应在证据报告注明，未解决前不得以 `Wh/km` 量化新旧模型优劣。模型输出是否改变调度 ETA/可行性，需要另行声明依赖变更；不把动力更换偷偷替换 route cost。

**反例**：模型要求 `payload_state=physically_loaded`，但旧观察仅能提供 `assigned_load`：`MODEL_ASSUMPTION_CONFLICT`，REJECT，除非 ARCH-01 提供可核验载货状态。

## Case C｜Greedy → PSO 或新算法

**只改** `components.scheduler`、参数与能力声明。输入 ObservationV1 固定；返回 ActionProposal，基于 EntityId，不向环境发送带有索引猜测的动作；Harness 统一校验任务存在、唯一归属、当前可派、载荷/电量/机巢资源和版本。

Legacy 入口事实：`frontend/scheduling_interface.py` 声明 `act(dict,time)->Dict[int,List[str]]`，但 `console/sim_session.py:167-185` 中 greedy 走函数，其余走 `scheduler.step(...)`。必须有显式 LegacySchedulerAdapter 标注具体算法 `act/step` 路由，不可把旧接口包装成新规范直接签发合格证。算法随机种子有独立命名空间，不与任务流共享全局 RNG。

**验收**：在冻结世界/数据/模型/种子与时间语义下，替换不会改变实例创建、地图、动力学、指标定义；无效动作被拒绝并给出原因；同一 seed 配对实验仅在 episode 配置、manifest、指标 denominator、对象集合一致时允许横向比较。

**反例**：新算法要求 `battery_predicted_range_m`，ObservationV1 无该已验证能力：`CAPABILITY_MISSING`，REJECT；不能以电池百分比冒名代替。

## Case D｜定时风场 + 机巢故障（组合验证）

EventProvider 在仿真窗口提供风变化、机巢状态变更的 EventIntent；Harness 按 ARCH-02 顺序提交，并把 CommittedFrame 提供 Dynamics/Metric。故障占用与派单决策必须使用一致 world revision。若 EventProvider 有外部实时随机流但无 replay snapshot，strict reproducibility REJECT。两个事件同 timestamp 的优先级由 ARCH-02 批准，ARCH-03 不自造“优先故障后派单”的规范。

## Case E｜缺字段数据与可信度

加载 CSV 机队有空 `base_x`、GeoJSON 缺坐标 CRS 和 OSM 建筑高度未知时，DataProvider 不可静默按 0/默认仓库位置/缺失楼高填充。生成 `ValidationReport`，说明缺失条数、原始字段与建议；必要字段拒绝，不参与模型的可缺字段带 missing flag 和局限。此例主要用于检查 Manifest 与诊断一致性。

## 审查记录与联合冻结事项

1. ARCH-01: EntityId, PointRef, CoordinateRef, WorldState/Scenario 资源关系。
2. ARCH-02: RunContext, CommittedFrame, event order, proposal atomicity, RNG, checkpoint。
3. ARCH-03: ObservationV1/ActionProposal 的 schema 主版本、Scheduler act/step adapter、metric definition/denominator、DatasetManifest/ModelManifest 的信任级别。
4. ARCH-04: LegacyEnvironmentAdapter/LegacySchedulerAdapter 放在哪层实现，双运行路径与旧实验不变性怎么验证。

**建议独立审查**：逐 Case 执行静态 schema 填充及拒绝原因走查；本 PR 只含文字，不声称已经运行替换测试。
