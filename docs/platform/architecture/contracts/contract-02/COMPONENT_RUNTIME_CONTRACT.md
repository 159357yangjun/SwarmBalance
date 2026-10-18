# CONTRACT-02｜Component Runtime Contract（B02 / B06）

> **状态：PROPOSED / DESIGN-ONLY / 待 ARCH-02、ARCH-04、ARCH-01、AI-A、AI-C 与主控会签；不得当作 Frozen ABI 或已运行代码。**
> Owner: Batch 03 AI-B；Task: CONTRACT-02；目标分支：`platform/contract-02-component-runtime`；base: `master@2ab60c69a806a22d7ba20353dee0571752a0e8e5`。
> 允许修改范围仅 `docs/platform/architecture/contracts/contract-02/*`。不改变 Legacy 引擎、旧 PR、历史数据或主线。

## 0. 可复核输入与优先级

| 输入 | 固定 HEAD（全文） | 本文使用的依据 |
|---|---|---|
| #54 ARCH-05-R2 | `99bd0eb6b910d691d6d7776da0a5fd3f973f2997` | CROSS_REVIEW B02/B06；INTERFACE_AND_SCENARIO_MATRIX M08–M10/M15/M19/M21 |
| #47 ARCH-03 | `68382c649393057ffbf5a14508ab1ff72d575b09` | COMPONENT_CONTRACTS §1–4，COMPATIBILITY_RULES，REGISTRY_AND_ASSEMBLY，MANIFESTS，TAXONOMY，REPLACEMENT_EXAMPLES |
| #49 ARCH-02 | `d155621aca66e3a80c388718093a452d17d71e10` | RUNTIME_SEQUENCE §1–4，STATE_OWNERSHIP §1–5，FAILURE_CONTRACT，SIMULATION_LIFECYCLE，CLOCK_AND_EVENTS，HARNESS_ARCHITECTURE |
| #50 ARCH-04 | `c4c0c67111ead435062650c1ed776547c477e3e3` | ADAPTER_DESIGN §1–5，BACKWARD_COMPATIBILITY，COUPLING_ANALYSIS，MIGRATION_INVENTORY，LEGACY_ARCHITECTURE，MIGRATION_SLICES |
| #46 ARCH-01 | `b5f05a70a3306f1799fcae2c3f342f3ed9ee0048` | ENTITY_CONTRACTS §1–5，WORLD_STATE §1–6，SCENARIO_MODEL，WORLD_MODEL，EXTENSIBILITY_CASES |
| #51 Governance | `f2df96bc609ee1e430ea6eff2456c4577347c300` | HANDOFF_PROTOCOL，INTERFACE_REGISTRY，DECISION_LOG，TASK_REGISTRY |

所有源仍为 Draft。#51 的 ADR-002/003/006 为 OPEN、INTERFACE_REGISTRY 尚无正式冻结接口；若上述任一上游 HEAD 更新，必须在本稿复审中列出变更差异，不能默认沿用。本设计只处理 B02/B06；B01、B03、B04、B05、B07 仍由相应负责人或主控裁决。

> **跨组增量约束**：统一的 `ProposalHeaderV1`、`Action/StateDelta→ChangeSetV1`、`EventSpec/Intent→EnvelopeV1`、Error/rollback map 见 [TRANSACTION_EVENT_PROPOSAL_CONVERGENCE.md](TRANSACTION_EVENT_PROPOSAL_CONVERGENCE.md)，其中所有 clock/event 字段严格取自 **AI-A PR #58 提案**，不是 AI-B 单方冻结。新增文档同时列明 #56/#57/#59/#60 精确 HEAD 与签字矩阵，原有字段名只是待签字的 ingress aliases。

## 1. B02 统一裁决提案：对外只允许 `propose`

**唯一规范候选 API**：
- `Scheduler.propose(observation: ObservationV1, ctx: ProposalContext) -> ActionProposal`。
- `DynamicsModel.propose(state: StateSliceView, conditions: DynamicsConditions, interval: ModelIntervalRef, ctx: ProposalContext) -> StateDeltaProposal`。

ARCH-03 原来的 `propose(ObservationV1)` 与 `propose(state_slice, conditions, dt_seconds)` 通过只读上下文显式补入版本、能力、RNG、运行指纹；不增加由 Harness 决策产生的第二套业务接口。ARCH-02 的 `scheduler.decide(WorldView,ClockView)` 和 `dynamics.advance(...)` 只可作为 **Harness 阶段名称/内部适配调用点**，其实际调用必须经过本段 `propose`，不可把 `decide/advance` 作为组件可选的另一规范签名；Legacy `decide` 仅保留于独立 adapter/worker 边界。

**读视图语义**：Scheduler 看到已验证并暂存于本 boundary 的 pre-decision 输入和领域状态，**不是**上一已提交状态的裸引用；该视图的公开 `committed_revision` 仍是上一次提交的版本，另以 Harness 签发的不透明 `view_token` 绑定 provisional stage；不能让两个阶段仅靠 revision 相等误判为同一个视图。Dynamics 看见调度意图已验证暂存后的只读视图；派单已暂存不等于对外已提交。任何组件输出都不执行 commit；只有 Harness 验证全部候选变化后才能发布新权威状态。MetricProvider 仅观测 post-commit frame。

**单一事实写入者**：Harness/StateCommitter 才能写 WorldState、时钟、队列与 RNG 提交状态；调度、动力、事件及数据提供者不得持有可变 Environment、StateStore 或 Drone 引用。Dynamics 生成位移/能量/服务事实的原子提案，不在本地扣减电量；`energy_delta_wh` 定义为**非负消耗量**，能量归一化由 Domain commit 验证；不把 assigned_mass 当作 physically_onboard_mass。运单完成须由可验证服务/货权事实驱动，不能靠坐标接近判定。

## 2. Protocol 草案（交换形状，非运行时实现）

以下引用含义在 `PROPOSAL_AND_OBSERVATION_SCHEMA.md` 详述。名字和返回值属于 **AI-B 的组件交互提案**；`ClockRef`、`EventIntentRef`、`BoundaryRef` 的内部字段严格保留 AI-A/ARCH-02 的所有权；实体 patch schema 归 ARCH-01。伪 Python 类型不是可直接 import 的文件。

```python
from typing import Protocol, Generic, TypeVar, Literal, Mapping, Sequence
T = TypeVar("T")

class ReadOnlyView(Protocol):
    @property
    def view_token(self) -> str: ...
    @property
    def committed_revision(self) -> int: ...
    # domain fields via ARCH-01 typed view, no mutable state references

class ProposalContext(Protocol):
    @property
    def run_id(self) -> str: ...
    @property
    def generation(self) -> int: ...
    @property
    def boundary_id(self) -> str: ...  # explicit public Run-local ID, minted by Harness
    @property
    def base_revision(self) -> int: ...  # committed revision
    @property
    def read_view_token(self) -> "OpaqueViewToken": ...  # stage_seq binding
    @property
    def scoped_rng(self) -> "TransactionalRNGPort": ...
    @property
    def readonly_resources(self) -> "FrozenResourcePort": ...
    # no writable StateStore, raw clock, writable queue or global RNG

class ComponentDescriptor(Protocol):
    # id, category, contract_version, implementation_version, digest,
    # capabilities, private_state_policy, checkpoint_format, determinism, ...
    ...

class Lifecycle(Protocol):
    def describe(self) -> ComponentDescriptor: ...
    def validate_config(self, config: "FrozenConfig", resources: "ResourceCatalog") -> "ValidationReport": ...
    def initialize(self, ctx: "InitContext", config: "FrozenConfig") -> "InitReceipt": ...
    def reset(self, ctx: "NewGenerationContext") -> "ResetReceipt": ...
    def close(self) -> "CloseReport": ...

class TransactionalComponent(Lifecycle, Protocol):
    def begin_boundary(self, tx: "BoundaryTxnRef") -> None: ...
    def prepare_commit(self, tx: "BoundaryTxnRef") -> "PreparedPrivateState": ...
    def abort_boundary(self, tx: "BoundaryTxnRef") -> None: ...
    def publish_prepared(self, prepared: "PreparedPrivateState") -> None: ...
    # publish_prepared MUST be prevalidated and guaranteed non-throwing
    def checkpoint(self) -> "VersionedPrivateCheckpoint": ...
    def restore(self, cp: "VersionedPrivateCheckpoint") -> None: ...

class Scheduler(Lifecycle, Protocol):
    def propose(self, observation: "ObservationV1", ctx: ProposalContext) -> "ActionProposalV1": ...

class DynamicsModel(Lifecycle, Protocol):
    def propose(self, state: "StateSliceView", conditions: "DynamicsConditions",
                interval: "ModelIntervalRef", ctx: ProposalContext) -> "StateDeltaProposalV1": ...

class DataProvider(Lifecycle, Protocol):
    def inspect(self, dataset_ref: "DatasetRef") -> "DatasetInspection": ...
    def materialize(self, request: "SnapshotRequest") -> "ValidatedEntityBatch": ...
    def poll(self, window: "ModelIntervalRef", ctx: ProposalContext) -> "DataRecordProposalBatch": ...

class SpatialProvider(Lifecycle, Protocol):
    def open(self, dataset_ref: "DatasetRef", requested_frame: "CoordinateRef") -> "SpatialSnapshot": ...
    def query(self, snapshot_id: str, query: "SpatialQuery") -> "SpatialQueryResult": ...

class EventProvider(Lifecycle, Protocol):
    def events_in_window(self, window: "EventWindowRefV1", state: ReadOnlyView,
                         ctx: ProposalContext) -> "EventIntentBatchV1": ...

class MetricProvider(Lifecycle, Protocol):
    def observe(self, frame: "CommittedFrame") -> "Sequence[MetricSample]": ...
    def finalize(self, summary: "ReadOnlyRunSummary") -> "Sequence[MetricSample]": ...
```

**签名处理规则**：`dt_seconds` 的确切数值可以由 `ModelIntervalRef` 暴露一个由 Harness 校验过的派生只读 `duration_seconds`，但区间端点、时间轴/精度与事件排序字段不由本任务冻结。`Scheduler.propose` 中 `ctx` 仅可用于授权服务，**不得**由 scheduler 使用第二条可变查询偷看之后的时刻。若 `DataProvider.poll` 未声明 streaming、SpatialProvider 未声明 route_query，装配器不得调用该能力。

## 3. 生命周期及状态机责任

| 阶段 | Harness | 组件 | 失败后规则 |
|---|---|---|---|
| describe / validate_config | 静态解析 descriptor、锁 digest/能力/DAG | 无运行时副作用，不读取 OS RNG 或隐式全局配置 | hard mismatch 在 assemble 前 REJECT |
| initialize | 新 run/generation scoped resources + 顺序初始化，未发布 revision 0 | 接收不可变配置、申请局部资源、建立未对外暴露的私有状态；返回版本化收据 | 任一失败，Harness 逆拓扑 close，禁止发布 READY |
| begin_boundary | 获取旧 B/C/D fence 与后续 provisional views | PURE 不修改影响结果的私有状态；TRANSACTIONAL 把改动保持在私有 staging | fence 无法可靠建立即禁止执行 |
| propose/prepare | 生成只读请求并验证所有操作 | 不发布用户可见副作用；把 RNG 消耗视为事务的暂存变更 | 任何硬错误：丢弃 boundary B/C/queue/RNG/D，记录诊断 |
| atomic publish | 单一不可分割发布权威 B/C/RNG/D prepared + revision | `publish_prepared` 必须预先证明 non-throwing；不允许回调外部系统 | 若不能提供保证，strict run 装配期拒绝 |
| postcommit | 持续 Trace/Result 和 MetricProvider.observe | 指标可更新派生状态 E；失败仅标 metric/evidence partial | **绝不**回滚已提交 B/C/D |
| reset | 确保 quiescent，increment generation，重建 WorldState/streams/queues | 清空或重建私有缓存/统计/RNG handles，验证与 clean initialize 等价 | 不能证明 clean reset 则 close + fresh instance；仍不行 REJECT |
| close | 逆拓扑调用，收集诊断并销毁引用 | 幂等释放 IO/内存资源；不修改已提交事实 | cleanup 失败单独记录，不改先前 terminal reason |

`reset` 是新 generation、不是 `restore`；一次 generation 的初始化只执行一次。序列化 checkpoint 只准在静止 commit barrier，读取私有状态不得自发推进 RNG。多组件的 `prepare_commit` 必须在单次发布前全部成功。准备对象不可泄漏可变引用；提交后不得再次复用。

## 4. B06：私有状态、事务及准入分级

描述符必须显式声明如下能力（一个 component 的多能力也须一致协调）：

```yaml
private_state_policy: PURE | TRANSACTIONAL | LEGACY_OPAQUE
transaction_capability:
  precommit_side_effect_free: true|false
  begin_prepare_abort: true|false
  publish_prepared_nothrow: true|false
  checkpoint_supported: true|false
  restore_supported: true|false
  checkpoint_format: "<versioned identifier or null>"
  resources_replayable: true|false
rng_capability:
  scoped_rng_only: true|false
  cursor_restorable: true|false
```

- **PURE**：输出仅依赖 pinned 输入与授权的受控 RNG；内部临时缓存只可重建，不能改变算法下次输出、迭代顺序或随机抽样。无持久 D，则空 checkpoint 是合法的规范值；不允许把隐蔽 warm-start 状态标为 PURE。
- **TRANSACTIONAL**：调度优化器的温启动种群、缓存、内部事件游标、独立 metric accumulator 等一切影响下一次输出的可变信息属于 D。严格模式要求本地 staged copy/undo journal 或等价机制，能可靠 `abort_boundary`、`restore`，并固定 checkpoint schema/version/content digest；重试所需的 RNG 位置属于 Harness 事务。私有并发线程、文件追加、网络请求或全局状态若未被纳入隔离，不可声称事务化。
- **LEGACY_OPAQUE**：旧 env.step、旧 numpy/global random、import-time 配置与热重载可能直接产生不可撤销副作用；只允许显式隔离 worker 的 `LEGACY_OPAQUE_STEP` 配置，**绝不**满足 strict atomic/replay/portable checkpoint 标志。异常/timeout 后 worker TAINTED/FAILED，不继续 step；通过销毁 worker + pinned inputs 清洁重建（新 run/generation）恢复，不在同一步偷重试。

**准入矩阵**：

| Run 要求 | PURE | TRANSACTIONAL | LEGACY_OPAQUE |
|---|---|---|---|
| strict atomic boundary + deterministic retry | 接受（需要受控 RNG 且无可变副作用） | 仅在 begin/prepare/abort、no-throw publish、RNG restore 被证明时接受 | REJECT |
| strict checkpoint/restart | 接受（空 D checkpoint；缓存可重建） | 仅在兼容格式的 checkpoint+restore 测试通过时接受 | REJECT |
| 不需 rewind 的最小单步开发试验 | 允许并标注证据级别 | 缺 restore 的组件不得自动享受原子性保证；需显式降级并不参加 strict run | 可单独进入显式 worker 兼容试验，标 TAINTED 风险 |
| 同进程多 Run / paired research | 只许 run-scoped 对象/流 | 同左且隔离内部状态和缓存键 | 默认 REJECT；worker-per-run 与预注册比较门另评 |

**拒绝时点**：若请求 `strict_transactions=true`、`required_checkpoint=true` 或 `retry_enabled=true`，任何组件有未知 D、不可恢复 RNG、不可校验 checkpoint、可失败的 publish hook 或外部副作用，必须在 assemble/initialize **REJECT: COMPONENT_RECOVERY_UNSUPPORTED**（对外可映射 `CAPABILITY_MISSING` / `DETERMINISM_UNSATISFIED`）；不得等模型抛异常后才发现不能回滚。无法于初始化结束证明干净恢复，也不能转 READY。一个事务组件测试失败可触发运行前拒绝而非自动 downgrade。

**重试要求**：Harness 显式配置 finite attempt budget；只允许在恢复完整 B/C/D/RNG/event queue、generation/revision/view token 严格匹配后，使用相同请求上下文重试；初始异常若有未知外部副作用，一律 FAILED 而不重试。硬非法 action 不是“重采样直到合法”；无授权不能跳过/替换 scheduler 或 model。

## 5. RNG 与跨组所有权边界

组件只能请求 `ctx.scoped_rng` 命名流，不得使用共享 `random.seed`、`numpy.random.seed`、`np.random.*` 全局状态、`hash()` 衍生流、OS entropy 或系统时间生成决策。每次调用前 Harness 保留 **本 boundary 消耗游标**，成功一次性发布，失败恢复；连续失败不前移任何流。组件私有 D 中如果包含独立 PRNG，须纳入私有 checkpoint 或重构为 Harness 管辖子流。禁止共享 scheduler 随机子流与任务到达/天气子流。

**不在 CONTRACT-02 决定** Scenario.seed 与 ExperimentPlan/master_seed 的优先级、Key Derivation Formula、跨 treatment 共享外生扰动流，及具体 PRNG 算法；这些属于 AI-C CONTRACT-03/EXP-01/ARCH-02。需要其返回：`RNGPort v1` 方法、子流 namespace 授权、游标保存/恢复的稳定标识、strict replay 的范围，才可锁定本稿 Protocol ABI。

## 6. LegacySchedulerAdapter：二层合同（不能混同）

**旧事实（基线 master 固定 SHA）**：`console/sim_session.py:167-185` 对 greedy 调用 `greedy_action_from_observation(self.obs)`；对 PSO/GA/OR-Tools 对象调用 `scheduler.step(self.obs, current_time=self.env.current_time)`；`frontend/scheduling_interface.py` 虽声明 `act(obs,current_time)` 的抽象，真实 SimSession 并不统一调用它。`env.step(action)` 接受 `Dict[int, List[str]]`，并在旧引擎中校验/可能拒绝动作。

1. **parity / legacy_direct 或 legacy_harness 的 worker 内部**：仅保留上述分支、旧原始 observation、step time、action 顺序；Greedy **不能被擅自改成** `step` 或 `act`。GA/PSO/OR-Tools 必须使用原有 factory 构造及 `step`，不能直接用 Optimizer.optimize 替代。所有种子、模型、OSM parser、配置、依赖、缓存策略与 engine SHA 固定。worker 内单步只调用 `env.step(action)` 一次，默认拒绝未知 algorithm key，禁止静默退回 Greedy。无法装载 OR-Tools 时明确失败而非偷偷换启发式。该模式只能声称 Legacy K1 单步 parity 目标，不能声称 B/C/D 原子回滚。
2. **future strict Scheduler facade（仅设计，不属于 Legacy parity）**：显式只读 `ObservationV1` 转 `LegacyObservationV1.0`（逐字段认证单位/顺序、可行掩码、task ID），保留一次冻结的 `index_to_entity_id` / `entity_id_to_index` 映射，将旧 `{drone_index:[task_id]}` 转为新的 `ActionProposal`，补 Harness 的 `observed_revision`、`view_token` 与合法 `proposal_id`，再由 Harness 重验载重/电量/机巢/货权。翻译若缺字段、任务索引失配、时间基准无法证明、不同 mask/物理语义、需要 process-global RNG，则 **REJECT**，不能自动补零或虚构新能力。此 facade 不保证算法与新 World 在同 seed 下 parity，且如未证明完整 D/RNG 事务恢复，不得进入 strict mode。

`LegacyEnvironmentAdapter` 才是旧域状态写入的唯一 opaque owner，`LegacySchedulerAdapter` 不能直接写 `WorldState` 或反向补算旧任务完成/指标。旧 checkpoint 是单进程 deepcopy 与全局 RNG 快照；禁止当作 portable cross-run component checkpoint。历史 CSV、compare_gate 和 E0/E1 源不变；新证据只允许 sidecar。

## 7. 未决接口及具体会签请求（**不自行冻结 AI-A**）

| ID | 接口/准确要求 | Owner/会签 | 本文状态 |
|---|---|---|---|
| DEP-A-01 | AI-A 给出 authoritative `BoundaryRef` / committed revision / provisional `ViewToken` 生命周期、事件进入 Scheduler 前是否可见、同刻两次事件/commit 的可观察边界；本稿只要求唯一只读授权上下文和不会误用旧观察 | AI-A（ARCH-01/02）+ 主控 | OPEN B01/B03 |
| DEP-A-02 | AI-A 返回 `EventIntent`→event envelope 的映射、去重/排序键、阶段权限、injection effective time、服务事实 canonical representation，不能在此文假定具体 time_ns/phase enum/priority 排序 | AI-A + ARCH-02 + 主控 | OPEN B03 |
| DEP-C-01 | `TransactionalRNGPort` 的 seed/子流所有权、rollback snapshot/counter、paired exogenous stream 授权和 key derivation 版本 | AI-C + EXP-01/ARCH-02 | OPEN B04 |
| DEP-02-01 | 让 ARCH-02 对 `propose` 唯一 public entry、基于 provisional view 的 `view_token`、B/C/D 原子 publish 与 rollback 规则、各错误默认 fatal/reject 口径逐项签字；并与 B01 一次/多次 revision 决议相容 | ARCH-02 + AI-A + 主控 | OPEN B01/B02/B06 |
| DEP-01-01 | EntityId/Ref、payload_mass、onboard_mass、resource leases、energy delta 和 service-completion 领域 patch 具体 variant/schema | ARCH-01 + AI-A | OPEN |
| DEP-04-01 | Legacy Greedy callable vs PSO/GA/OR-Tools step map、固定索引转换要求、worker 隔离和 opaque TAINTED 状态；不得声称旧进程内 checkpoint 具有 portability | ARCH-04 + 主控 | OPEN B06 |
| DEP-05-01 | postcommit MetricProvider 私有累加器 checkpoint / fail-partial 与 RunRecord metric completeness gate 的映射 | CONTRACT-04/EXP-01 + ARCH-03 | OPEN B05 |

## 8. 验收门（设计 ≠ 实测）

G-DOC：本目录三文件，正文明确 Protocol/schema + 正负 fixture；仅 docs-only 白名单；锁六 PR 完整 HEAD；标出所有会签接口。G-CONTRACT（**待未来实现**）：签名/能力协商、stale view/revision、原子 rejection、RNG 恢复、nonthrow publish、reset 隔代、checkpoint incompatibility、legacy parity + TAINTED 全部成为可执行测试，且保留错误和日志。G-ARCH：由主控在接受跨组签字、独立复审和 ADR 后判定；本文提交不解除 #54 HOLD。参见 `COMPONENT_FAILURE_TEST_CASES.md` 的每条测试期待和实际执行状态。
## 9. 增量对齐：事务入口、事件输出与失败语义

- **One header, one commit authority**：`ActionProposal`、`StateDeltaProposal` 与可发事件的 provider 使用统一 `ProposalHeaderV1`，通过版本化、可拒绝的 converter 归一为 #58 的**仅 Harness 内部** `NormalizedChangeSetV1`。Harness 是唯一 phase/operation 编排和状态提交者，组件不能通过原 `decide/advance` 绕过 converter；公共 `ProposalContext.boundary_id` 与 `ProposalHeaderV1.boundary_id` 必须一致，旧 `boundary_ref` 仅允许通过版本化 Harness 导入映射，`stage_seq` 与 token 绑定，绝不靠名称相似判断。
- **Queue vs committed fact**：`EventIntentV1` 仅为未接纳的未来事件请求；AI-A `EventEnvelopeV1` 才能进入权威 queue；`ServiceFactCandidate` 转成 domain operation/CommittedDomainFact，而非 retroactive same-time queue entry。AI-A 的时间单位/事件顺序、t=0、horizon、phase map 依然 PENDING 主控会签。
- **Failure normalization**：本合同 `STALE_OBSERVATION` 到 #58 `STALE_PROVISIONAL_VIEW`；`COMPONENT_RECOVERY_UNSUPPORTED` 到拒绝装配的 recovery/checkpoint 能力诊断；`NONFINITE_VALUE` 在已开始 boundary 时落入 `INVALID_STATE_CHANGE` 家族；事件 precondition skip 必须有版本化政策并在成功发布后才正式消费，其他 precommit fatal 恢复 B/C/D/queue/RNG，postcommit observer failure 仅污染证据，Legacy 失败标 `TAINTED`。同一错误不要同时标 REJECT_COMMAND + FAIL_RUN，按发生窗口与 FrozenRunSpec policy 给一个决策。详见新增文件 §5。
- **No premature guarantees**：`prepare_commit` 成功、`publish_prepared` non-throwing、组件 D/RNG checkpoint/restore 均是拟定 **准入条件**，非经实测的 guarantee；任何实现证据不足则 strict-mode assemble REJECT。涉及 #58 的单 boundary 规范必须由 ARCH-01/02/03 会签及 ADR-002 批准，不能由 CONTRACT-02 单独裁决原 #46 micro-commit 口径。

## 10. Strict V1 public ABI 与 CONTRACT-01 精确同步（主控方向，待签字）

- **Public**：Scheduler 提交 `ActionProposalV1{schema_version,header:ProposalHeaderV1,actions,emitted_event_intents}`；Dynamics 提交 `StateDeltaProposalV1{schema_version,header:ProposalHeaderV1,model_interval_ref:ModelIntervalRef,changes,service_facts,emitted_event_intents}`。两者的公共 Header **九个语义字段完全相同**：`run_id,generation,boundary_id,base_revision,read_view_token,proposal_id,producer_id,capability_ref,provenance_ref`（加独立 header schema version）。Harness **唯一**创建 `NormalizedChangeSetV1`，旧 `change-set.v1` 无公共提交权限。本文旧节中提到的 `ChangeSet` 均按 [TRANSACTION_EVENT_PROPOSAL_CONVERGENCE.md §0–3](TRANSACTION_EVENT_PROPOSAL_CONVERGENCE.md) 的内部转换语义理解。
- **EventProducer**：`EventIntentBatchV1.window_ref:EventWindowRefV1`；模型 `ModelIntervalRef` 只用于 Dynamics 积分。错传引用类型拒绝 `WINDOW_REF_TYPE_MISMATCH`；不允许无条件结构转换。调用方必须使用由 Harness 签发并验证的窗口，不能凭相同起止时间认定同一令牌。
- **Strict commit**：一个 boundary 最多发布一次 revision（成功恰好 +1；无 work 的 NO_BOUNDARY 不递增）；pre-input / scheduler / dynamics / post-model 全部只见内部不可变 provisional overlay。原 ARCH-01 文档公开 micro-commit 的许可，在 strict V1 的正式 ADR-002 ACCEPTED 后被取代；本合同不冒充已经批准了 ADR。
- **精确事件边界候选**：t=0 初始入队、首次 boundary 同刻输入先于调度可见；horizon INCLUDE_ONCE、禁止越界积分，真实末刻事件可形成有界零时长事件 boundary，但不允许纯 metrics 空 tick；同刻迟到 targeting sealed phase 一律 `INVALID_EVENT_ORDER`，不自动延迟；类型到 phase 必须有被冻结的 registry，缺映射拒绝。详细 candidate/mapping 见收敛文件 §0.3，必须 AI-A/ARCH-01/02/03 明确会签。
- **Runtime gate**：失败阶段区分 preadmission REJECT_REQUEST、装配 REJECT_ASSEMBLY、提交前 ROLLBACK_BOUNDARY、合法记录失败 SKIP_EVENT、提交后 POSTCOMMIT_PARTIAL、Legacy TAINT_LEGACY；strict 缺完整 B/C/D/RNG/queue/seq rollback 能力即装配拒绝。全部为待实现要求，未运行合同测试。参照 #58 `bd5e47266d79d1e087ca8cfc6fe68ea28a03496b` 和 #61 `6e7b69dc70c56a8e13f5cf7de750ad3c59068dcc`。
