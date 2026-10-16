# CONTRACT-02｜Proposal & Observation Schema（交互协议草案）

> **PROPOSED / 仅设计，非冻结 JSON Schema 或可执行 ABI。** AI-B 负责交换视图与组件提案字段；AI-A/ARCH-01/02 保有 clock、event、WorldState patch、统一提交/修订的最终字段所有权；AI-C 保有 RNG seed/stream derivation。
> Baseline: `master@2ab60c69a806a22d7ba20353dee0571752a0e8e5`。输入 HEAD：#54 `99bd0eb6b910d691d6d7776da0a5fd3f973f2997`；#47 `68382c649393057ffbf5a14508ab1ff72d575b09`；#49 `d155621aca66e3a80c388718093a452d17d71e10`；#50 `c4c0c67111ead435062650c1ed776547c477e3e3`；#46 `b5f05a70a3306f1799fcae2c3f342f3ed9ee0048`；#51 `f2df96bc609ee1e430ea6eff2456c4577347c300`。

## 1. 编码、身份和可见性

**版本**：`ObservationV1`、`ActionProposalV1`、`StateDeltaProposalV1` 是建议的 **major=1** 类型标签；字段增删遵守语义版本管理，必须经能力协商，在不支持的 major 上明确 `CONTRACT_VERSION_MISMATCH`。当前所有示例均为 `draft-1.0.0` 概念表示，**不得拿示例直接当已批准 ABI**。所有字典和 tuple 仅包含确定性可序列化的基本类型（UTF-8 字符串、有限 number、boolean、null、固定 schema 数组/对象），无 Python 对象指针/callable/模块引用；序列集合必须确定顺序并能按稳定 ID 复检；禁止在 dict/set 迭代自然顺序上决定动作。

**不变量**：`run_id`、`generation`、`committed_revision` 必须与 Harness 当前运行匹配。每个只读视图携带不透明 `view_token`：token 标识当前 boundary、**所见 stage**、revision 和生成代次，不能由组件自行构造；只有 `committed_revision` 一致而 `view_token` 不一致依然是 `STALE_OBSERVATION`。Harness 只能在验证依赖顺序后向对应组件签发 view；跨 generation/replay 使用旧 token 必须拒绝。不得由组件自行解释 token 内容/格式。

**只读**：深度不可变 value snapshot 或语义等价的独立读视图；实体/任务 payload 的嵌套对象不得指向 StateStore，组件局部修改不可能改变 B/C；`ObservationV1` 没有写权限，也不能通过 provider callback 旁路读取不同 revision。

**命名权边界**：`boundary_ref`、`clock_ref`、`model_interval_ref` 是由 ARCH-02/AI-A 签发的 opaque references；本文件不规定 `sim_time_ns`、`at_seconds`、`phase`、`priority`、`producer_seq` 等任何 envelope 字段/排序法。正式版由 AI-A 输出事件/时钟 schema 后填充；`duration_seconds` 仅表示经验证的物理时长参数，不能推定边界时间算法。

## 2. ObservationV1：Scheduler 唯一输入

```python
from dataclasses import dataclass
from typing import Literal, Mapping, Optional, Sequence

EntityId = str          # semantic ID schema owned by ARCH-01
Ref = object            # exact World/Entity ref schema owned by ARCH-01
OpaqueRef = str         # encoding unspecified; issued by Harness

@dataclass(frozen=True)
class VehicleViewV1:
    entity_id: EntityId
    definition_ref: Ref
    state_version: int
    health: str
    motion_status: str
    position: "PointWithCoordinateRef"
    battery_wh: float
    battery_capacity_wh: float
    assigned_mass_kg: float
    onboard_mass_kg: float          # physically carried, NOT synonymous with assigned
    payload_capacity_kg: float
    capabilities: tuple[str, ...]
    active_task_ids: tuple[EntityId, ...]
    # order and missing/default semantics locked by ARCH-01 / manifest

@dataclass(frozen=True)
class TaskViewV1:
    entity_id: EntityId
    definition_ref: Ref
    state_version: int
    lifecycle: str                  # canonical lifecycle owned by ARCH-01
    pickup_ref: Ref
    dropoff_ref: Ref
    mass_kg: float
    volume_m3: float | None
    assigned_vehicle_ref: Ref | None
    cargo_custody_ref: Ref | None
    deadline_ref: OpaqueRef | None   # time semantics AI-A owned
    requirements: tuple[str, ...]

@dataclass(frozen=True)
class ObservationV1:
    schema_version: Literal["observation.v1"]
    run_id: str
    generation: int
    committed_revision: int
    boundary_ref: OpaqueRef
    view_token: OpaqueRef
    clock_ref: OpaqueRef
    world_ref: Ref
    scenario_ref: Ref
    vehicles: tuple[VehicleViewV1, ...]
    tasks: tuple[TaskViewV1, ...]
    resource_ledger_view: "ReadonlyResourceLedger"
    dynamic_conditions_view: "ReadonlyFieldView"
    rules_and_constraints: tuple["TypedConstraintRef", ...]
    capability_provenance: "ManifestDigestRefs"
    # Snapshot carries data validity/unknown, not silent 0 values.
```

**Observation 构造职责**：Harness 在所有调度前的允许事件/状态候选通过校验后，按可见性规则生成独立 immutable view，并签发此 stage 的 token。任务列表必须显式区分 pending/assigned/onboard/delivered/failed 等生命周期；不得因为 legacy `unassigned_tasks` 列表中没有任务就推断所有任务已完成。约束取自 ARCH-01 ResourceLedger、机型能力与来源 manifest；充电站不是隐式单站模型。

**缺失字段**：强制字段不存在、CRS/轴序不明、能源单位非 Wh、任务质量非 kg、capacity 为负、ID 重复/悬挂、非有限数或 `assigned_mass_kg` 被冒作 `onboard_mass_kg` 均不能产生“合格 Observation”。按 `INPUT_SCHEMA_INVALID`/`UNIT_MISMATCH`/`ENTITY_REFERENCE_INVALID`/`MODEL_ASSUMPTION_CONFLICT` 在装配/构造时拒绝；可选字段须用 tagged `missing_reason` 或 null+声明语义，不得默认 0。路径长度/ETA/预测剩余续航等 **不是自动存在**：必须来自有对应单位/假设/provenance 的声明能力，缺失应 `CAPABILITY_MISSING`。

## 3. ActionProposalV1：不可变意图，不是可执行动作

```python
@dataclass(frozen=True)
class AssignTaskChain:
    kind: Literal["scheduler.assign_task_chain"]
    actor_vehicle_id: EntityId
    ordered_task_ids: tuple[EntityId, ...]
    expected_actor_state_version: int
    expected_task_state_versions: tuple[int, ...]
    # no index, no inline world patch, no direct energy deduction

@dataclass(frozen=True)
class ActionProposalV1:
    schema_version: Literal["action-proposal.v1"]
    proposal_id: str
    source_component_id: str
    run_id: str
    generation: int
    boundary_ref: OpaqueRef
    observed_revision: int
    observed_view_token: OpaqueRef
    actions: tuple[AssignTaskChain, ...]
    capability_ref: str
    provenance_ref: str              # locked manifest/model/config digest
```

**提交语义**：空 `actions=()` 是明确的“无派单建议”，不是异常或缺失。所有动作必须基于同一个被签发的视图；一个 proposal 的有序动作集合要作为该 boundary 的原子候选集合提交给 Harness（存在互相矛盾/资源冲突默认拒绝整个 boundary，不用 last-write-wins）。动作 ID 幂等键由组件在 Harness 提供的身份上下文内稳定生成，重试相同输入不得生成不可解释的新 ID。正式 `ActionOperation` discriminated union 中可以允许 cancel/requeue/route request，但每个变体必须由 ARCH-01/ARCH-03 另行会签，**不得**拿自由文本 `kind` 绕过 capability 校验。

**验证顺序（建议）**：schema/version→身份/generation/view_token→producer capability→EntityId 引用/种类→state versions→任务生命期→同任务唯一归属/货权→载重/电量/可达性/站点 lease→冲突/幂等→可执行变更暂存。`AssignTaskChain` 不能凭 `DroneIndex` 或 UI display name 选 actor；旧 `Dict[int,List[str]]` 必须先经 Legacy 映射，并由新 Committer 再验证。

## 4. StateDeltaProposalV1：Dynamics 唯一输出

```python
@dataclass(frozen=True)
class MotionEnergyChange:
    kind: Literal["dynamics.motion_energy"]
    vehicle_id: EntityId
    expected_vehicle_state_version: int
    new_position: "PointWithCoordinateRef"
    energy_consumed_wh: float      # >= 0, finite. NOT new authoritative battery
    resulting_motion_status: str
    model_ref: str                 # pinned ModelManifest identity
    quality_flags: tuple[str, ...]
    # optional energy/regeneration policy requires a separately versioned variant

@dataclass(frozen=True)
class ServiceFactCandidate:
    kind: Literal["dynamics.service_fact"]
    subject_entity_id: EntityId
    service_ref: Ref
    evidence_ref: str             # proof of service/custody; NOT UI geometric proximity
    # exact EventIntent envelope and domain lifecycle action owned by AI-A/ARCH-01

@dataclass(frozen=True)
class StateDeltaProposalV1:
    schema_version: Literal["state-delta-proposal.v1"]
    proposal_id: str
    source_component_id: str
    run_id: str
    generation: int
    boundary_ref: OpaqueRef
    base_committed_revision: int
    based_on_view_token: OpaqueRef  # after validated scheduler staging
    model_interval_ref: OpaqueRef
    changes: tuple[MotionEnergyChange, ...]
    service_facts: tuple[ServiceFactCandidate, ...]
    capability_ref: str
    model_manifest_digest: str
```

**统一能量扣减**：动力学只算 `energy_consumed_wh`，Harness 与 ARCH-01 不变量校验器按当前暂存电量统一扣减一次。禁止模型同时在自身更改 Drone.battery 再提交相同耗电。是否存在“再生能源/充电”由另一个独立、受模型声明约束的 proposal variant 表达，不允许传负 `energy_consumed_wh`。位置/速度/电量/货权/服务事实的跨对象一致性由同一 boundary Committer 验证；过低电量、超质量、NaN 或无来源字段 fail-closed。`service_facts` 只是候选领域事实；具体服务事件的规范 envelope、时间字段及 task transition kind 要 **等 AI-A 会签**。

**幂等与视图**：`base_committed_revision` 是上一次对外 commit 的 revision；`based_on_view_token` 则必须绑定接受合法派单暂存后构造的状态视图。即使 commit revision 尚未变化，Dynamics 也不得接收旧的 predecision token。

## 5. 六类组件输入/输出与副作用矩阵

| category | 规范建议入口 | 输入版本/可见性 | 输出 | 可写内容 |
|---|---|---|---|---|
| DataProvider | `inspect/materialize`，有 stream 能力才 `poll` | pinned DatasetRef、window ref | 已验证实体批次 / 数据候选 | 自身缓存，**不写 B** |
| SpatialProvider | `open/query` | frozen spatial dataset、CRS、snapshot id | 可追溯坐标/路径查询结果 | 纯缓存，**不写 B** |
| EventProvider | `events_in_window` | 只读 state、Harness 的 window/context | `EventIntentBatch`（envelope 未冻结） | 只提议；**不排序/入队/写 B** |
| Scheduler | **`propose(ObservationV1, ctx)`** | 验证过的 predecision provisional read view | `ActionProposalV1` | 只提议，不派单 |
| DynamicsModel | **`propose(StateSliceView, Conditions, ModelIntervalRef, ctx)`** | 已暂存合法动作的只读 view | `StateDeltaProposalV1` | 只提议，不推进权威时钟/扣电 |
| MetricProvider | `observe(CommittedFrame)`，`finalize` | 仅 postcommit；已提交 frame ref | `MetricSample` | 可写派生 E，不写 B/C；失败 partial |

所有六类还需通用 Lifecycle；凡持有影响计算的 D，须通过 `TransactionalComponent` 或符合等价版本能力方案。若 metric accumulator 在边界后更新失败，记录该 metric window 为 missing/partial；不得伪造 0、不可回滚已经提交的核心状态。

## 6. LegacyObservation 版本不兼容桥

**原始 `frontend/scheduling_interface.py`**：`SCHEMA_VERSION="1.0"`；旧观察含 `drone_positions`、`unassigned_tasks`、`drone_free_masks`、`drone_is_free`、`drone_batteries`、`drone_loads`、`drone_capabilities`、`charging_station(s)`；旧动作是 `Dict[int,List[str]]`。**旧 `SCHEMA_VERSION="1.0"` 不等于新 `ObservationV1` 的版本身份**；缺 `world_ref`、`generation`、`view_token` 和 EntityId 时，不得因数字 1.0 相同而直接通过。

显式双向映射草案：

```text
strict facade input ObservationV1 [verified]
  -> capability gate (legacy-required masks, fields, route/ETA semantics, units)
  -> immutable LegacyObservationV1.0 plus pinned index->EntityId table
  -> legacy routing: greedy callable OR PSO/GA/OR-Tools scheduler.step(obs, current_time)
  -> validate Dict[int,List[str]] (indexes in range, no duplicate ID, preserved order)
  -> index->EntityId, task_id cross-check, ActionProposalV1 with Harness-issued view token
  -> Harness full ActionProposal validation (not legacy auto-accept)
  -> ONLY IF all D/RNG recovery evidence is available may it enter strict boundary
```

Parity worker 则执行 **原方向**（legacy obs→legacy action→env.step 一次），不声称生成完整新 `ObservationV1` 或 `StateDeltaProposal`。旧索引表须在具体观察生成那一刻冻结，不能跨调用偷复用已重排的 drone array。

## 7. 错误响应、验收样例及待会签

诊断最小 payload：`code, severity, run_id, generation, component_id, operation, field_path, expected, actual, observed_revision, view_token_ref, retryable, remediation`，必要时关联 Harness 的 FailureRecord/trace；诊断必须避免泄露随机状态与敏感输入。下列错误码为 **本合同推荐稳定别名**，供 ARCH-02/03 统一：`CONTRACT_VERSION_MISMATCH`、`STALE_OBSERVATION`、`ENTITY_REFERENCE_INVALID`、`INVALID_ACTION`、`RESOURCE_VIOLATION`、`NONFINITE_VALUE`、`COMPONENT_EXCEPTION`、`COMPONENT_RECOVERY_UNSUPPORTED`、`CHECKPOINT_INCOMPATIBLE`、`LEGACY_OBSERVATION_UNMAPPABLE`。最终错误枚举与 fatal/reject 策略以 Harness `FAILURE_CONTRACT` 签字为准。

**正例（设计 fixture）**：run `run:fixture` / generation 2 / committed revision 4 / Harness 签发 `view:A` 的 `ObservationV1`；Scheduler 为 `vehicle:01` 派 `task:01`，两者存在、可用、payload 和电量合法，proposal/view token 匹配。Harness 在暂存分配后签发 **不同** 的 `view:B`；Dynamics 返回 `vehicle:01` 非负 Wh 的 motion_energy 候选；一次成功提交，revision 变为 5，Metric 只看到提交后 frame。具体时间/事件 envelope 不在夹具中假设。

**负例（设计 fixture）**：同 revision 4 的旧 `view:A` 被复用到 Dynamics → `STALE_OBSERVATION`；`observation.v0` 或 legacy `SCHEMA_VERSION=1.0` 不经适配直接交新 Scheduler → `CONTRACT_VERSION_MISMATCH`；`drone_index=0` 直接作为 actor EntityId → `ENTITY_REFERENCE_INVALID`；`energy_consumed_wh=NaN` → `NONFINITE_VALUE`，不产生新的已提交快照。更多覆盖与测试执行状态见 `COMPONENT_FAILURE_TEST_CASES.md`。

**待会签阻断**：
- AI-A：`BoundaryRef` / `ClockRef` / `ModelIntervalRef` / `EventIntentBatch` 的实际 shape、时间精度/排序、同刻提交/可见阶段，及服务事实与 canonical EventSpec 的映射。
- ARCH-01：`PointWithCoordinateRef`、`ReadonlyResourceLedger`、`TypedConstraintRef`、EntityRef 和 change variant、task lifecycle/custody。
- ARCH-02：Token 生存期、stage/read policy、单 commit 或其他最终批准策略、错误映射、准备/发布原子性。
- AI-C：RNG port identity、transactional cursor restore。
- ARCH-04：legacy index/table 生成、调用路由、parity/strict 能力隔离。
- 主控 ARCH-06：签署 schema major/字段、兼容转换和批准状态。**本设计不解除 #54 HOLD。**
