# ARCH-01 — WorldState 所有权、提交与可复现状态

状态：Design Draft v0.1；对 ARCH-02 的实现提出约束，不代替其 Harness 设计。

## 1. 单一权威运行状态

WorldState = 一个 Run 的唯一可变事实集合，不等同于前端 Snapshot / 遥测表 / Metrics。任何组件获取只读 ReadView（携带 run_id、revision、sim_time_s），输出 ChangeProposal；唯有 Harness 的 StateCommitter（ARCH-02 主责）有权执行原子校验与提交。ARCH-01 负责本文件状态形状和领域不变量；ARCH-03 组件只能经公开契约参与。

| 区域 | 字段概念 | 唯一写入路径 | 派生读者 |
| --- | --- | --- | --- |
| meta | run_id、world_ref、scenario_ref、revision、sim_time_s、tick_index | Harness | 所有组件 |
| entities | entity_id → typed EntityState | StateCommitter | Scheduler、Dynamics、UI |
| logistics | task lifecycle、assignment、cargo custody refs、route refs | StateCommitter | Scheduler、Metrics |
| resources | station leases、queues、service status | StateCommitter | ResourceArbiter |
| fields | 风场激活层、天气属性、设备与空域动态覆盖 | StateCommitter | Dynamics/Spatial |
| events | 已应用 event_id、游标/时间戳、来源、错误与处理结果 | StateCommitter | Audit/Replay |
| rng | 按组件/事件命名的 RNG streams 或恢复标记 | Harness 的运行上下文（快照一同冻结） | 授权组件 |
| derived | 统计、可视化投影与索引缓存 | 非权威，随 revision 重算 | UI / Metrics |

定义性数据不复制到 mutable state：例如 payload capacity、CRS、静态建筑几何、地图来源归 World+Manifest；只允许引用固定版本。动态天气场的数值/修订号属于当前 Run 的 fields 切片。

## 2. 建议状态结构

~~~yaml
world_state:
  run_id: run:trial-73
  schema_version: worldstate.v1
  world_ref: {world_id: world:metro-A, revision: 1}
  scenario_ref: {scenario_id: scenario:weekday, revision: 1}
  revision: 204
  tick_index: 102
  sim_time_s: 102.0
  entities:
    vehicle:01:
      position: {x: 200.0, y: 300.0, z: null}
      battery_Wh: 1500.0
      motion_mode: flying
  tasks: {}
  resource_ledger: {leases: {}, queues: {}}
  dynamic_fields: {wind_field_revision: 1}
  event_cursor: {last_order_key: [102.0, 2, 10, 15, event:abc]}
  applied_event_ids: []
~~~

具体字段版本与序列化选择可调整，但不能移除 run-scoping、revision、时钟、实体 ID、事件游标、资源事务的核心语义。

## 3. 状态读写协议

1. Harness 在 t 时刻制作 ReadView(revision=r)；本批组件的读取视图不受并发写入污染。
2. 各组件输出有序提案：{proposal_id, source_component, based_on_revision:r, effect_time_s, operations, expected_refs, provenance}。
3. StateCommitter 验证 world/scenario/run IDs、时间、实体类型与存在性、资源可行性、task/custody 生命期、单位、有限值、proposal 幂等性。
4. 按 ARCH-02 统一事务和冲突政策提交，成功后 revision 增加，返回 {new_revision, applied_operation_ids, emitted_facts}；一组必须原子的操作要么全部成功，要么全部拒绝。
5. 拒绝时不部分扣电、不半分配任务、不预留半个泊位；返回 {code, detail, proposer_id, revision} 并写审计记录。不得以 last-write-wins 隐式覆盖。
6. 指标组件读取已提交事实/事件，给出派生值；不能借更新指标反过来改变模拟真相。

在一个物理时刻可以有多次显式 micro-commit（同刻不同 phase），但每次有独立 revision 且在重放中次序确定。无锁读视图必须是不可变快照或等价隔离实现。

## 4. 原子性、不变量、反例

- Drone 的位置、能耗扣减和运动状态同提交；energy proposal 是非负 Wh，输入风场状态与源模型版本要能追溯。防止模型计算的返回 Wh 与实际电量扣减漂移。
- 服务航点消费 → pickup/delivery 只有一次；实体位置恰好经过目的点不自动证明货权移交。
- assign/requeue/cancel 与任务队列、vehicle assignment、货物持有人同一事务；重复 proposal_id 不得产生重复完成。
- 机巢 grant/release 与队列/lease 同一事务；capacity 不可超限；同一个 vehicle 不可在矛盾站点同时 active。
- 运行时空域限制变化后，在后续动作提交前重新验证受影响航线，失败策略由事件与 Harness 决定，不让旧路由悄然越过动态禁飞区。
- 时间不倒退，非回滚的正常提交 effect_time_s ≥ 当前时钟；恢复 checkpoint 为新执行分叉 Run 或显式 reset/restore，不伪装成连续时间前进。
- 浮点数 NaN/Inf、负质量、越界电量、缺失必填 CRS 一律 fail-closed。

## 5. 时间与事件顺序：给 ARCH-02 的候选协议

本组推荐一个兼容固定步长与离散事件的确定性排序键：
(time_s, phase_order, event_priority, insertion_seq, event_id)。
候选 phase_order：0 外部事实/空域/天气故障、1 任务到达与调度前校验、2 scheduler 提案、3 Dynamics/服务推进、4 任务完成与资源结算、5 Metrics/观测。该顺序是 **Proposed**，特别是旧 Environment.step 中“派单→时钟加 STEP_SECONDS→生成任务→drone.update→结算”的既有顺序不能凭此文件被改变。ARCH-02 必须在联合审查中定稿，LegacyAdapter 需要声明其实际相位映射；同刻事件 priority 越小越先处理，insertion_seq 来源应可重放。

固定步长：t → t+dt 的 phase 语义要规定；离散事件：事件按 time_s 弹出，不因 wall clock 或线程调度变序。不能混用“step 数”和“秒”作为同一字段；默认 1 step=1 s 只是 legacy 当前配置。

## 6. 快照、恢复与证据

快照应至少捕获 world/scenario/组件锁版本、worldstate schema、完整可变切片、sim_time_s、tick_index、revision、未执行事件队列及已执行去重集合、每组件 RNG stream 状态、算法私有必要状态和状态 hash。恢复必须校验静态指纹、组件状态版本及 ID 引用，不兼容即显式阻止并保持原运行不变。断点续跑与从同 seed 全新重跑是两类不同证据。

旧 SimSession.save_checkpoint 用 deepcopy 存 env_dynamic、scheduler、obs、Python/NumPy 进程级 RNG，并对部分 static 属性排除；_env_generation 主要依赖配置结构字段（数量/泊位等）而非完整源数据内容。新快照不可沿用其“只靠数量”的兼容性判据，也不能把其单进程 deepcopy 当作持久可移植协议。

推荐运行证据：输入 manifests hashes、组件锁与版本、World/Scenario fingerprints、时序事件日志、状态检查点 SHA-256、结果摘要及确定性对照判据。回放必须区分完全确定性和仅统计可比性。

## 7. ARCH-02/03 对齐问题

- 提案粒度是每组件一个事务还是一事件多个事务？谁分配 insertion_seq？
- 无效 proposal 终止 Run、只跳过事件还是重试？策略必须可配置但同一实验冻结。
- Scheduler 读取更新前/更新后的事件与观测时点？Legacy 阶段不得偷换。
- 动力学模型返回能耗与位移的原子性由谁保证？建议 Committer 校验，模型单纯计算。
- checkpoint 的跨组件 schema migration 与可重放哈希由谁提供？建议 ARCH-02 实现、ARCH-03 声明可恢复能力。

本文件不是对现有 CI/运行测试已通过的声明；当前交付为静态架构设计。
