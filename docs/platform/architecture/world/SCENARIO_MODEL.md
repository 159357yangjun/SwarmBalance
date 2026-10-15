# ARCH-01 — Scenario、时变事件与输入来源

状态：Design Draft v0.1。场景不等于 World，不等于某一时刻的 WorldState，更不等于 UI 演示步骤。

## 1. 场景定义

Scenario 是针对一个不可变 World revision 的“可复现实例化配方”，包括初始状态、事件流、外部数据 manifest refs、种子与参数覆盖。Scenario 定义本身不可变；每次修改得到新 scenario revision。由 Harness 将其装配成 Run + WorldState。

字段建议：scenario_id、revision、schema_version、world_ref、initial_state、event_sources、scheduled_events、environment_layers、run_parameters、seed、time_origin、provenance。初始实体覆盖仅允许合法运行态字段（初始电量/位置/服务状态等）；机型结构改变必须换 World revision 或引用另一个合法 FleetDefinition，不得在运行中静默改静态 capacity。

## 2. EventSpec 最小语义

~~~yaml
scenario_id: scenario:weather-fault
revision: 1
world_ref: {world_id: world:metro-A, revision: 1}
time_origin: {kind: simulation, start_s: 0}
seed: 101
scheduled_events:
  - event_id: event:wind-shift-001
    time_s: 300.0
    priority: 10
    kind: environment.wind.update
    target_ref: field:urban-wind
    payload: {u_ms: 6.0, v_ms: 0.0, interpretation: wind_toward}
    preconditions: {world_revision: 1}
    on_failure: abort_run
  - event_id: event:station-outage-001
    time_s: 450.0
    priority: 20
    kind: facility.set_availability
    target_ref: station:02
    payload: {available: false, reason: outage, mode: soft_close}
    on_failure: record_and_skip
  - event_id: event:task-burst-001
    time_s: 600.0
    priority: 30
    kind: demand.inject
    target_ref: null
    payload: {task_source_ref: dataset:peak-hour, batch_ref: batch:600}
    on_failure: abort_run
~~~

上面 schema 与数值仅用于契约说明。旧风场 E1 目前使用实例 wind_u/wind_v 与 Drone.set_wind 注入，且实验系数为情景假设，不宣称可直接驱动此 EventSpec。

事件至少包含全局唯一 event_id、effective time（秒）、kind（带命名空间）、target 或 source、带 schema 的 payload、priority、preconditions、failure_policy、provenance。事件 ID 跨重放去重；重复 ID 内容不一致视为输入损坏。无 event_id 的实时人工输入必须在接纳时生成并记录可回放身份和顺序号。

## 3. 支持的变化类型

| 事件 | 作用切片 | 原子效果 | 最小验收 |
| --- | --- | --- | --- |
| weather/wind 更新 | dynamic_fields | 修改字段 revision，不碰无人机静态参数 | 后续动力学读到新字段与明确时刻 |
| vehicle.fail / recover | EntityState + logistics | 更新 health，按故障策略协调任务/货权 | 任务不双归属，货物不消失 |
| facility.close / open | ResourceLedger + EntityState | 拒绝新 lease；软关闭时既有服务可结束 | 占用不超额，改道/无站失败有因由 |
| demand.inject / withdraw | TaskState + queue | 新任务 ID 校验、队列追加或撤单 | 无重复/幽灵任务 |
| airspace.activate / expire | dynamic restriction layer | 更改限制有效区间与 revision | 已规划航线重新校验；不默许穿越 |
| resource.capacity.change | 可变运营容量策略 | 检查既有 lease 是否冲突 | 缩容不静默驱逐，策略明确 |

天气既可用单一向量更新，也可引用时变网格/逐点空间场（WeatherProvider）；EventSpec 定义何时切换 field revision，具体插值/空间查询规则由 ARCH-03 模型声明。天气“from”还是“toward”必须显式转换；旧 Environment 的 u/v 注释使用风吹向的向量，而 drone._wind_along_for 的内部正号代表逆风。

## 4. 时变场域与空间限制

- DynamicField = {field_id, kind, spatial_ref, time_support, dataset/model_ref, interpolation_policy_ref, validity_window, revision}；字段数据允许 sparse tiles、样本点或常数，但调用方只依赖抽象读接口。
- RestrictionDefinition 保存持久空间约束几何与能力；RestrictionState 保存 active、effective window、运营临时覆盖。动态禁飞区可由 activate/expire 事件切换，无需修改 World 类。
- 每个事件的时间必须与 Run 同一仿真秒轴；UTC 日历事件必须经 time_origin 明确映射，日历时区和 DST 由时间适配层校验，不能盲取 OS 当地时间。
- 对缺字段的观测/数据帧须按 DatasetManifest 的 null_policy：reject、explicit_default、interpolate（有明确方法与窗口）、drop_record（有计数）；不可把缺少高度/坐标/重量默默当 0。
- 时变 provider 若依赖随机数，必须有独立命名随机流与版本固定；不得读全局随机数而不记录。

## 5. 冲突与失效策略

相同 sim_time_s 的事件顺序由 ARCH-02 唯一确定，并写入审计。冲突例：同刻关闭机巢与发放新 lease；首先完成哪个 phase 决定结果，但绝不能出现关闭后仍随机取得新 lease 的非确定态。preconditions 不满足必须返回 EVENT_PRECONDITION_FAILED；无目标返回 TARGET_NOT_FOUND；外部字段无 CRS 或时间元数据返回 INPUT_SCHEMA_INVALID；物理约束失败返回 STATE_INVARIANT_FAILED。

可选失败策略只允许经实验冻结的显式枚举（abort_run、record_and_skip、retry_with_limit），重试需要固定次数和 backoff 的仿真时间语义；禁止无限自动重试、吞异常或将失败事件视为已成功应用。

## 6. 与现有场景的关系

现有 console/scenario_presets.py 包含 config_patch、algorithm、seed 与演示脚本；config/scenes/README.md 区分“初始配置场景库”和“进程内运行态快照”；SimSession 支持人工任务、故障与站点关闭等。LegacyScenarioAdapter 可从这些格式生成输入描述和已验证动作映射，但不可把 config 热重载、现场演示按钮或 checkpoint 当作新的 Scenario/EventSpec 原生机制。

阶段验收（未来实施时）：同 seed 的事件 ID/发生顺序一致；天气变化不改变实体类型；故障不产生幽灵送达；禁飞激活阻止违规航线；缺关键字段输入明确拒绝。当前只有设计走查，没有运行执行证明。
