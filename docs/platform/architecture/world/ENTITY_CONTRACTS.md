# ARCH-01 — 实体定义、引用与资源契约

状态：Design Draft v0.1。与 WORLD_MODEL.md、WORLD_STATE.md 一起审阅；字段为目标契约，非现有 Python 类的序列化说明。

## 1. 定义 vs 状态 vs 规则

**EntityDefinition** 在 World revision 内不可变：id、kind、capabilities、静态规格、home/location refs。
**EntityState** 在某 Run 的 WorldState 内可变：当前坐标、剩余电量、任务阶段、故障标志、占用/预留情况。
**Dynamics/Policy** 不写在 EntityDefinition/EntityState：耗电函数、运动更新、续航门、路径搜索、派单策略、资源优先级、故障恢复均由组件执行，提交者据其声明式输出校验并写入状态。

所有实体至少有 entity_id、kind、definition_revision、display_metadata（非机器判据）。ID 是 World 范围内不可重复、大小写敏感且不因排序、索引变化而变化的字符串；跨运行相同定义可复用 ID，但状态必须按 run_id 隔离。所有引用用 {world_id, entity_id} 或同一 World 内 entity_id，禁止使用旧代码中的 drone_idx 作为持久标识。

## 2. 现有类别映射与最小字段

| kind | Definition（静态） | State（可变） | 规则组件（无实体内公式） |
| --- | --- | --- | --- |
| vehicle/drone | spec_ref、capabilities、home_ref、payload_max_kg、battery_capacity_Wh、位置类型 | position、motion_mode、battery_Wh、onboard_mass_kg、current_route_ref、health_state | DynamicsModel / EnergyModel / RouteFollower |
| logistics/task | pickup、dropoff、mass_kg、volume_m3、priority、created_at_s、deadline_s 可空、required_capabilities | lifecycle、assigned_vehicle_ref、pickup_time_s、delivery_time_s、cargo_custody_ref、failure_reason | TaskLifecyclePolicy / Scheduler |
| facility/charging_station | location、berth_capacity、services、service_duration_s（或 model_ref） | open/closed、active_leases、waiting_queue_refs、reason | ResourceArbiter / ServiceModel |
| spatial/restriction | geometry_ref、restriction_kind、scope、safety_margin_m、validity_rule_ref | active、effective_geometry_revision、event_source_ref | AirspaceRule / SpatialProvider |
| 任意新 kind | namespaced schema + 可声明的能力 | schema 化 state slice | 注册组件，无需修改 World 核心 |

上表列出最低语义；不是所有 drone 必须有相同续航/动力学。硬件型号作为 manufacturer/model provenance 或 spec_ref；不允许把 DJI、ARK40、light_express 等名称变成通用字段。

### 2.1 特别不变量

- 0 ≤ battery_Wh ≤ battery_capacity_Wh；battery_capacity_Wh > 0；0 ≤ onboard_mass_kg ≤ payload_max_kg。状态变更不得出现非有限值。
- 建议同时记录 assigned_mass_kg 与 onboard_mass_kg：前者为调度归属，后者由真实取件/交接事件生效。现有 drone.consume_battery 使用 current_load，而空载统计使用另一个判定，两者并不等价；在能耗口径未裁决前不能把“已派单”静默视作“已取货”。
- task 的 lifecycle 是离散可验证转换：pending → assigned → en_route_pickup → onboard → delivered；failed/cancelled/requeued 由明确操作触发。旧代码 pending/assigned/in_progress/completed/failed 映射必须逐案说明，不能仅替换字符串。
- delivered 的权威事实来自已提交的服务完成/货权转移事件，不从几何阈值、航线长度变化或 UI 快照猜测。与现有 consumed_waypoints_this_step 的原则保持方向一致。
- 机巢 capacity 是 Definition；占用和预留是 State；服务时长由 capability 指定；charging_power 是可选属性，不意味着所有站都使用连续充电（当前旧站实际采用换电）。
- 圆形/多边形/矩形等为 SpatialProvider 可声明的 shape types；Restriction 不写死 OSM 面结构。规则可选限制实体/区域/高度/时间。

## 3. 强类型引用与完整性

建议 Ref = {entity_id, expected_kind?, expected_revision?}；resolve(ref, read_view) 必须返回明确结果：FOUND、NOT_FOUND、KIND_MISMATCH、STALE_REVISION，不得静默使用位置最近实体代替。World 版本冻结后，不可变 Definition 的引用不能指向另一个 World 版本的对象，除非提供显式外部 Ref + 转换协议（本阶段不设计跨世界派单）。

禁止删除仍被 active task、route、resource lease、cargo custody 引用的实体；运行期“移除”采用 retired 状态与补偿操作，历史事件保留原 ID。队列按 ID 序列保留次序；重复 ID 和悬空 Ref 均拒绝装配。旧 station_id 为数字/字符串混用，适配器负责一次归一化并保留 legacy_id 元数据。

## 4. 资源与货权状态

ResourceLedger 是 WorldState 内独立状态切片，不是 ChargingStation 自己的可变计数器。
- ResourceDefinition: resource_id、owner_entity_id、resource_kind、capacity、compatible_capabilities。
- Lease: lease_id、resource_id、holder_entity_id、start_s、expected_end_s 可空、status（reserved/active/released）、request_id。
- 约束：每个有效 lease 的 holder 存在；active + reserved 的资源容量须按规则校验；实际占用计算自 lease，不允许与另一个 occupied 数组分别更新而漂移。
- 排队：QueueEntry = {request_id, holder_id, requested_at_s, priority_inputs_ref}。算法仅提议选择，WorldState 单事务执行授予 lease + 去队列 + 更新车辆服务状态。
- 同一个任务的 cargo custody 只能有一个权威 holder/location；pickup、transfer、delivery 与任务状态必须事务性更新，不允许“任务完成但货物仍在另一架机上”。
- 机巢软关闭可让已持有 active lease 的服务完成，不接受新 lease；是否允许最后一个站关闭是场景策略，不应内置为 World 通用约束。
- 错误必须明确：RESOURCE_CAPACITY_EXCEEDED、CONFLICTING_LEASE、UNKNOWN_REFERENCE、INVALID_TRANSITION、CUSTODY_CONFLICT 等，不能将失败伪装为成功占用。

## 5. 与组件系统的接口示例

~~~yaml
definition:
  entity_id: vehicle:01
  kind: vehicle/drone
  spec_ref: model:generic-cargo-v2
  capabilities: [flight, payload.transport, battery.swap]
  payload_max_kg: 10.0
  battery_capacity_Wh: 1600.0
state:
  entity_id: vehicle:01
  position: {x: 0.0, y: 0.0, z: null, spatial_ref: world}
  battery_Wh: 1600.0
  assigned_mass_kg: 0.0
  onboard_mass_kg: 0.0
  health_state: ready
~~~

模型返回的 energy_delta_Wh、movement proposal、task transition proposal 是建议结果；ARCH-02 校验状态版本及不变量后一次提交。字段及组件能力名待 ARCH-03 联合定稿。

## 6. 适配与禁令

旧 Environment.drone_assignments 按无人机数组下标存储且可能是字典或列表；旧 task_generator.unassigned_tasks 作为任务队列；旧 station occupied 与 _nest_waiting 分处对象。迁移适配器必须完成身份归一化、状态投影和一致性校验，不能就地把旧列表传给新 WorldState 并宣称拥有单一状态真源。

不在实体构造器里加载地图、读取全局 config、生成随机数、调用调度算法或计算能耗公式；不在 Definition 中附带直接可执行的 Python callable 或隐式进程资源。
