# ARCH-06｜规范接口版本候选与不兼容转换表

**状态：CANDIDATE / NOT FROZEN；不是已实现 API 或获得会签的 v1。**

| Contract | 建议唯一版本 | owner | 必须使用的接口与失败规则 |
|---|---|---|---|
| World/Scenario/State | world.v1, worldstate.v1-candidate | ARCH-01 | 静态 World、不可变 Scenario、Run-local State，全部 ID 和引用强类型 |
| Boundary | boundary-commit.v1-candidate | ARCH-02 | 每执行边界一次公开提交、revision+1，phase 不单独提交 |
| ProposalHeader | proposal-header.v1-candidate | ARCH-02/03 | run_id、generation、boundary_id、base_revision、read_view_token、proposal_id、producer_id、capability_ref、provenance_ref |
| Scheduler | scheduler-propose.v1-candidate | ARCH-03 | propose(ObservationV1, ProposalContext) -> ActionProposalV1 |
| DynamicsModel | dynamics-propose.v1-candidate | ARCH-03 | propose(StateSliceView, Conditions, ModelIntervalRef, ProposalContext) -> StateDeltaProposalV1 |
| Internal ChangeSet | normalized-changeset.v1-candidate | ARCH-02 | **仅 Harness 内部** NormalizedChangeSetV1；逐项标准化 Action/StateDelta 的 typed operation、phase、future event intents；原 change-set.v1 不是替代执行 ABI |
| Clock/Event | sim-clock.v1, event-envelope.v1-candidate | ARCH-02 | uint64 sim_time_ns，规范 phase，int32 priority，producer ID/seq；时间转换 total-or-reject |
| EventProvider window | event-window-ref.v1-candidate | ARCH-02/03 | EventIntentBatchV1.window_ref 使用 EventWindowRefV1；与 Dynamics 的 ModelIntervalRef 类型不同，错用即 WINDOW_REF_TYPE_MISMATCH |
| Logical experiment cell | C03C04-IDENTITY-v1-candidate | EXP/ARCH-02 | (plan_digest,treatment_id,replicate_key,frozen_run_spec_digest) LP4 内容键 + 三元组→spec 绑定一致性；replication_id 仅 legacy 入站 alias |
| RNG KDF | C03-HKDF-HMAC-SHA256-v1-candidate | EXP/ARCH-02 | LP4/NFC UTF-8 四字节大端长度，root seed BE64；exo 不含 treatment/full Spec，run-private 含 Spec；sampler/distribution versions 待签 |
| RunRecord | run-record.v1-candidate | ARCH-02 | 手工 Run 和实验 Run 都有完整不可变记录；attempt 单独分配并保留失败/证据缺失 |
| MetricDefinition | metric-definition.v1-candidate | ARCH-03 | 指标版本/单位/时间窗/分子分母/缺失语义、对比资格门 |
| Evidence | evidence-bundle.v1-candidate | VVE/EXP | Claim→Analysis→Batch→Attempts→Run→World/Model/Dataset/Code 的不可变引用 DAG |
| Legacy mode | legacy-direct/legacy-opaque/native-strict | ARCH-04 | legacy 默认、旧数据只读、legacy opaque 不宣称事务回滚或可移植 checkpoint |

## 规范取舍与要求修复

1. 组件 wire 只保留 ProposalHeaderV1：boundary_id 是明示 Run-local string；Harness 另拥有不可解析的 read_view_token，严格关联 generation、phase、stage_seq。来源 boundary_ref 是内部 token 或版本化导入别名，不可变成第二个身份。
2. 组件不能直接修改 WorldState，不能把 ServiceCompletionFact 作为排队中的未来 EventEnvelope。Harness 将 public Action/StateDelta → NormalizedChangeSetV1，仅允许具有 ARCH-01 版本化 reducer 的 typed operations，否则 DOMAIN_OPERATION_UNMAPPED。
3. EventSpec 和 EventIntent 在入队之前通过唯一 EventEnvelopeV1 标准化：sort=(time_ns,phase_rank,priority,producer_id,producer_seq,event_id)，不得依赖 Python set/dict 顺序；同刻已 sealed phase 的新事件拒绝。kind→phase 登记表、time=0、horizon inclusivity、EventWindowRef 的边界范围必须由 ARCH-02/03 会签。
4. EventProvider poll window Ref 与 Dynamics interval Ref 不允许通过字符串相似度无条件转换；需要显式 converter、精确纳秒和运行身份防串。
5. ExperimentPlan 必须不可变，并声明每组外生扰动 tape/seed；同一 (plan,treatment,replicate) 绑定不同 spec digest 必须拒绝而非默许第二个统计样本。Spec canonicalizer 不含 run_id、attempt_id、generation、plan_digest、执行时间等信封字段，避免循环依赖与不稳定散列。
6. 两种算法在同一 pair group/replicate 只有固定相同外生 tape digest 或可验证相同 addressable draws，才允许 common-random-numbers 推断。相同 master seed 单独不足以建立此关系。
7. RunRecord、MetricDefinition、AnalysisRecord、EvidenceBundle 属于不同 owner，禁止 postcommit 指标错误回滚已提交世界；发生 missing denominator、错误指标窗或无证据的模型应用域则返回 NOT_COMPARABLE/NOT_ASSESSED，不输出伪排名。
8. 严格模式的组件要么 PURE，要么具备可恢复的 transactional D；不能恢复私有状态、消费全局 RNG 或有未受控外部副作用时拒绝严格装配。LEGACY_OPAQUE_STEP 失败标 TAINTED，不能继续信任断点。

## 正反例必须提供实际运行证据（当前 NOT_RUN）
- 两个同刻事件、其中一项非法导致同 boundary 全部 staged B/C/D/queue/RNG 丢弃；外部无 micro-revision。
- Scheduler 错 stage_token、同 proposal_id 不同 digest → 明确拒绝。
- EventProvider 用 ModelIntervalRef 替代 EventWindowRef → 明确拒绝。
- 3.5 秒 wind、same-time station fault，以及 t=0/horizon/late phase 拒绝的精确事件轨迹。
- 同一实验槽位不同 spec → CELL_SPEC_CONFLICT；重试/崩溃恢复不重复统计样本；错误 artifact hash 不覆盖旧记录。
- 外生 CRN G01–G13 数学向量 + 独立分布采样/事件流 fixture；CRN 不含 treatment digest。
- 旧 engine 进程隔离、same-source step-parity、旧结果写前后 SHA 不变与 rollback smoke。

**只有单一接口版本完成跨组批准、AI-R 独立认可及 ARCH-06-FINAL PASS 后才能使用 FROZEN 标记。**
