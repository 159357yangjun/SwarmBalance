# ARCH-03｜组件最小契约（PROPOSED v0.1）

> 仅接口与 Schema 草案，非可执行实现。基于 master@2ab60c69。ARCH-01/02 无可读取正式契约；联合冻结前仅供评审。

## 1. 跨契约核心类型（待 ARCH-01/02 共同冻结）

```python
# 伪类型定义；NOT implementation
EntityId = str
ComponentId = str
Digest = str  # sha256:<lowercase hex>
SimTimeSeconds = float
class CoordinateRef: crs_id: str; axis_order: str; unit: str
class PointRef: coordinates: tuple[float, ...]; frame: CoordinateRef
class ObservationV1:
    version: str; run_id: str; step_index: int; sim_time_seconds: float
    world_revision: int; entities: tuple; tasks: tuple; constraints: tuple
class ActionProposal:
    proposal_id: str; observed_revision: int; actions: tuple
    # each action: actor EntityId, target EntityId, kind, validity_window
class StateDeltaProposal:
    source_component_id: str; base_revision: int; changes: tuple
class EventIntent:
    event_id: str; at_seconds: float; priority_class: str
    stable_order_key: str; payload: dict; preconditions: tuple
class CommittedFrame:
    run_id: str; revision: int; step_index: int; at_seconds: float
    readonly_state: object; accepted_events: tuple; rejected_proposals: tuple
class RunContext:
    run_id: str; seed_namespace: str; clock: object
    readonly_resources: object; logger: object; scoped_rng: object
```

以上各类字段为跨组讨论提案。Observation 是可序列化的不可变只读拷贝，不暴露 Environment/Drone 可变实例或资源句柄。时间基准声明秒、step_index、dt_seconds，转换必须显式。坐标必须携带 CRS（含轴序、米/度、投影策略）。每次提议携带世界版本；提交器统一校验对象存在、资源约束、时序、单位、幂等及冲突。

## 2. 统一组件生命周期

```python
class ComponentContract:
    def describe(self) -> ComponentDescriptor: ...
    def validate_config(self, config, resources) -> ValidationReport: ...
    def initialize(self, context: RunContext, config: ReadOnlyConfig) -> InitResult: ...
    def reset(self, reset_context: ResetContext) -> ResetResult: ...
    def close(self) -> CloseReport: ...
```

禁止 import 时读取可变配置作为运行依据。initialize 前必须完成能力协商与资源预检；同一 run 中一次 initialize，多次 reset 必须复位随机流和缓冲；close 幂等，即使 initialize 部分失败也须释放。可恢复/不可恢复异常使用 `ComponentFailure(code,component_id,phase,details,retryable)`，不得返回无错误的空列表代替失败。任何组件异常由 Harness 记录并裁决，组件不能私自吞掉。运行中状态归组件内部仅限缓存和私有可复现状态，须随 checkpoint 序列化、或声明 checkpoint 不可用并拒绝该能力。

## 3. 六类专属最小接口

```python
class DataProvider(ComponentContract):
    def inspect(self, dataset_ref) -> DatasetInspection: ...
    def materialize(self, snapshot_request) -> ValidatedEntityBatch: ...
    def poll(self, time_window) -> tuple[DataRecordProposal, ...]: ...
class SpatialProvider(ComponentContract):
    def open(self, dataset_ref, requested_frame) -> SpatialSnapshot: ...
    def query(self, snapshot_id, SpatialQuery) -> SpatialQueryResult: ...
class DynamicsModel(ComponentContract):
    def propose(self, state_slice, conditions, dt_seconds) -> StateDeltaProposal: ...
class EventProvider(ComponentContract):
    def events_in_window(self, start_seconds, end_seconds, readonly_state) -> tuple[EventIntent, ...]: ...
class Scheduler(ComponentContract):
    def propose(self, observation: ObservationV1) -> ActionProposal: ...
class MetricProvider(ComponentContract):
    def observe(self, frame: CommittedFrame) -> tuple[MetricSample, ...]: ...
    def finalize(self, run_summary) -> tuple[MetricSample, ...]: ...
```

`poll` 与 `events_in_window` 不得执行世界写入；Harness 负责事件排序、判重、验证、调用状态提交。若无流能力 DataProvider 应声明 `data.streaming=false`，装配器不调用 poll。无路径搜索能力的 SpatialProvider 不得谎报 `spatial.route_query`。Scheduler 不做状态提交，只产生带版本的请求。Metrics 必须读取 committed frame，不得根据尚未接受的 intent 统计完成任务；要求有分子、分母、分母为零语义、measurement_window、unit、definition_version、source_frame_revision、missing_reason 及 provenance。

## 4. 错误、原子性和可重复性

- 所有调用返回具类型的成功值或显式错误；`VALIDATION_FAILED`、`UNSUPPORTED_CAPABILITY`、`STALE_OBSERVATION`、`NONFINITE_VALUE`、`UNTRUSTED_SOURCE`、`RESOURCE_VIOLATION`、`COMPONENT_TIMEOUT`、`INTERNAL_FAILURE` 均可定位到 component_id/record_id/field_path。
- 空批次必须与加载失败区分。未声明坐标不可被默认视为米或 WGS84；未知模型参数不可被默认视为经验证参数。
- 提案应可按 `run_id, step, phase, component_id, proposal_id` 去重。失败后的同一步重试和提交/回滚语义由 ARCH-02 冻结，未经明确规则不承诺可安全重试。
- RNG 按 `run seed + component_id + stream_name` 确定独立子流；组件不使用全局 random/numpy.random 状态，所有非确定性外部调用记录可重放输入或明确声明不可复现。
- 停止/暂停/单步的生命周期主体是 Harness。组件没有独立启动“后台仿真”的权力。
- ResourceBudget 约束内存、调用时限、批处理记录数；事件数量上限超出时返回结构化错误而非部分静默丢弃。

## 5. 对现存协议的非等价关系

`frontend/scheduling_interface.py` 是 `act(observation: dict,current_time:float)->Dict[int,List[str]]`（SCHEMA_VERSION=1.0）。`console/sim_session.py:167-185` 的 greedy 函数调用、其他算法实例 step 和 `env.step(action)` 是 legacy 执行链。新 ActionProposal 不复用 integer drone_index，也不把该接口直接命名为新标准；适配器必须显式映射稳定 EntityId、动作有效期和观察版本，重新验证语义。现有 `Drone.consume_battery` 改写自身电量，不能直接作为符合 DynamicsModel 的实现。
