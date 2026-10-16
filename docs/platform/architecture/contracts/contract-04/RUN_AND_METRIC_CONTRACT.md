# CONTRACT-04 — Run 与 Metric 最低可用跨组契约

> Task: CONTRACT-04 / ARCH-05-R2 B05 | Owner: AI-D（接口整合提案） | status: **PROPOSED / NOT FROZEN** | schema: `contract-04@0.1.0` | date: 2026-10-16
>
> 只定义对象、归属、不可变引用、状态和拒绝规则；**不是实现、数据库迁移、运行验证或研究结论**。必须经 ARCH-02、ARCH-03、EXP-01、VVE-01 共同会签，再由主控 ARCH-06 裁决。本合同不覆盖 B01/B02/B03/B04/B06 决策。

## 0. 固定输入 / 与上游分歧的明确处置

| 来源 | 固定 PR HEAD SHA（不可使用移动分支名作为证据） | 与本契约关系 |
|---|---|---|
| #54 ARCH-05-R2 | `99bd0eb6b910d691d6d7776da0a5fd3f973f2997` | B05 P0、M18–M25、R-EXP-02/03、R-VVE-03 |
| #49 ARCH-02 | `d155621aca66e3a80c388718093a452d17d71e10` | 单 Run 生命周期、结果/日志/快照/故障 |
| #47 ARCH-03 | `68382c649393057ffbf5a14508ab1ff72d575b09` | MetricProvider / MetricSample、manifest |
| #52 EXP-01 | `a966567b1a2a033f477c2847073cc11777a3afd2` | ExperimentPlan/Runner/RunRecord/AnalysisRecord |
| #53 VVE-01 | `9e9d8918c1e6989568e84c3f0d020fdffb0373de` | 验证、证据、声明 |
| #50 ARCH-04 | `c4c0c67111ead435062650c1ed776547c477e3e3` | 历史比较门、sidecar、legacy opaque |
| #51 Governance | `f2df96bc609ee1e430ea6eff2456c4577347c300` | Draft/HEAD/验收与禁止越界 |

7 PR 的 base 均为 `master@2ab60c69a806a22d7ba20353dee0571752a0e8e5`，取证时均为 Open/Draft/unmerged。#52 将 RunRecord 列为 Experiment 资源，#53 要求 ARCH-02 RunRecord 锁定证据：**以“单 Run 的创建/提交归 Harness；批次的引用/分析归 Experiment”消歧**。两者均可读但不能各自产生第二份权威 RunRecord。

## 1. 资源所有权、寿命、版本及关系

| 资源 | 唯一逻辑责任方 / 创建者 | 冻结点、版本、引用和写权限 |
|---|---|---|
| `FrozenRunSpec` | ARCH-02 Harness 的预检/装配器；Experiment 可提供待冻结运行请求 | 装配验证通过 **且 initialize/首个状态提交之前** 冻结；`spec_schema_version, spec_digest`；不可变 |
| `RunRecord` | **ARCH-02 Harness**；手动/CLI/UI/Batch 均有一份 | 接受 create 分配 `run_id` 即生成 PREPARED 记录；`record_schema_version, run_id, generation, attempt_id, record_revision`；状态历史追加 |
| `RunArtifact` | Harness 的结果/trace/export 边界 | 每产物的 `artifact_id, kind, sha256, byte_size, media_type, produced_at, completeness`；内容寻址不可覆盖 |
| `MetricDefinition` | **ARCH-03 Metric contract/registry**（定义、发布与版本管理）；Experiment 挑选指标 | 配置/装配阶段解析其完整定义与 `definition_digest`；在 `FrozenRunSpec` 冻结，单 Run 内不可改变 |
| `MetricSample` | 单 Run 的 MetricProvider 产生，**Harness 在 post-commit 采集、关联和落盘** | `sample_id, metric_definition_digest, run_id, generation, frame_revision, time/window`；不可变，可带 missing_reason |
| `ExperimentDefinition` | EXP-01 | `experiment_id, revision, definition_digest`，研究假设/控制因素/排除/分析/指标预注册；旧 revision 不改 |
| `ExperimentPlan` | EXP-01 | 开始 dispatch 之前冻结 `plan_digest`、完整 treatment/cell、重复/seed 映射、每个 run spec digest、纳排准则 |
| `BatchRecord` | EXP-01 | 计划与所有原始 `run_id/attempt_id` 的追加索引、调度失败、取消及退出；不修改 RunRecord |
| `AnalysisRecord` | EXP-01 | 引用冻结批次快照、样本纳排、comparison gate、统计方法/结论/限制；新计算生成新 `analysis_id` |
| `VerificationRecord/ValidationRecord/UQRecord` | VVE-01 | 记录自身验证对象、方法、证据、有效域及单独审查状态；**不从 CI 自动升级** |
| `EvidenceBundle/CredibilityClaim` | VVE-01 | 不可变证据引用图、明确声明范围、人工/独立审阅；参见 `EVIDENCE_TRACEABILITY_CONTRACT.md` |

逻辑依赖：`ExperimentDefinition -> ExperimentPlan -> BatchRecord -> [RunRecord]`；每个 `RunRecord -> FrozenRunSpec -> pinned world/scenario/assembly/model/dataset/code`，并指向 `[RunArtifact,MetricSample]`；`AnalysisRecord -> BatchRecord + selected RunRecord/MetricDefinition + gate`。独立 Run 不需要 ExperimentDefinition/Plan/Batch（`experiment_ref=null`），但 **绝不能缺 RunRecord**。

引用形式：`{type,id,schema_version,content_digest}`。内容摘要规范预设 `sha256:<64-lowercase-hex>`，计算对象为稳定序列化的逻辑内容；具体规范化方式（JSON canonicalization/二进制产物）须在实现前一致确定并加入 `digest_algorithm`，禁止基于可变 URL、文件名、`latest` 或 branch 名保证身份。schema_version 是结构兼容版本，不代替 content_digest；内容变更另生 revision/digest。缺 hash/引用解析失败 -> `PROVENANCE_INCOMPLETE`，不能结论 PASS。

## 2. FrozenRunSpec v1 最低字段

```yaml
spec_schema_version: "0.1.0"
run_id: "<unique-run-id>"
origin: MANUAL                     # MANUAL | EXPERIMENT | API | LEGACY_IMPORTED
experiment_ref: null             # when applicable: {experiment_id, revision, plan_digest, treatment_id, replication_id}
world_ref: {id: "...", revision: "...", digest: "sha256:<real>"}
scenario_ref: {id: "...", revision: "...", digest: "sha256:<real>"}
assembly_ref: {digest: "sha256:<real>", components: ["id/version/implementation_digest/..."]}
dataset_manifest_refs: ["id/revision/digest"]
model_manifest_refs: ["id/revision/digest"]
code_ref: {git_commit_full_sha: "<40-hex>", dirty: false, execution_mode: "NATIVE_HARNESS"}
runtime_profile_ref: {digest: "sha256:<real>"} # OS/Python/libs/numeric/tolerance/clock
clock_policy: {mode: FIXED_STEP, step_ns: 1000000000, horizon_ns: 3600000000000}
rng_plan_ref: {digest: "sha256:<real>"}          # scope/streams/derivation; B04 must sign
metric_definition_refs: [{id: "timeout_rate",version: "1.0.0",digest: "sha256:<real>"}]
failure_policy_ref: {digest: "sha256:<real>"}
completeness_policy: {audit_required: true, required_artifacts: ["run_manifest","diagnostics","metrics"]}
spec_digest: "sha256:<digest-of-canonical-spec-excluding-this-field>"
```

标记为 `<real>` 的占位符 **不可用于真实运行**。生成 `spec_digest` 时排除其自身；记录所有不可省略的配置/模型、物理量/CRS 转换、随机流、终止/超时判据。外部不可重现数据必须固定快照或显式 `NON_REPRODUCIBLE`；不能绕过 strict 模式。**B04 RNG 未冻结之前，仅可标示 Proposed，不可宣称 paired-run 确定性。**

## 3. RunRecord v1 与尝试/失败规则

最低字段：`run_id, generation, attempt_id, origin, experiment_ref?, spec_digest?, created_at_utc, started_at_utc?, ended_at_utc?, lifecycle_status, terminal_reason?, error_codes[], checkpoint/snapshot_ref?, artifact_refs[], metric_sample_refs[], metric_completeness, evidence_completeness, runtime_profile_digest?, source_code_sha?, legacy_mode?, taint_flags[], status_events[], record_schema_version, record_revision`。每个 status_event 追加 `revision, timestamp_utc, from, to, actor, reason, error_ref`；导出的历史 revision 内容不可变。

- RunHandle 被创建后 PREPARED；配置/装配或初始化失败仍以 FAILED 留档（`spec_digest=null` 且 `freeze_error` 说明）。在分配 run_id **之前** 拒绝的畸形请求只生成 request rejection audit，不伪造已创建的 RunRecord。
- Harness 内部 CREATED/ASSEMBLED/READY/RUNNING/PAUSED 对外可映射 PREPARED/RUNNING，并保留 `lifecycle_detail`；COMPLETED -> SUCCEEDED；STOPPED -> CANCELLED；FAILED -> FAILED。销毁句柄不改变终态；`INVALIDATED` 是后续资格审查结果，**不覆写原 SUCCEEDED/FAILED/CANCELLED 事件**。
- `run_id` 标识一次不可替换执行尝试；`logical_run_key=(plan_digest,treatment_id,replication_id)` 对应预注册单元；每次重试创建 **新 run_id 和新 attempt_id**，以 `retry_of_run_id` 指向旧尝试，不得把旧记录改成成功或把多次尝试当独立 replicate。BatchRecord 保留所有 attempts、使用预注册 `attempt_selection_policy` 决定统计样本。
- `execution_status` 与 `evidence_completeness=COMPLETE|INCOMPLETE|UNKNOWN`、`metric_completeness=COMPLETE|PARTIAL|MISSING`、`comparison_eligibility=ELIGIBLE|NOT_COMPARABLE|UNASSESSED` **互相独立**。例如物理仿真成功、指标导出失败：SUCCEEDED + MISSING + INCOMPLETE + NOT_COMPARABLE，不能伪装“成功指标为零”。
- 预提交错误保持上次提交 revision、时钟与 RNG；post-commit MetricProvider/export 故障只标记结果缺口，不反向撤销世界提交。必须存 `last_committed_revision, failure_phase, error_code, evidence_gap`。legacy opaque 异常需 `TAINTED`，不能报称事务恢复。
- RunArtifact 至少分类 `RUN_MANIFEST, EVENT_LOG, SNAPSHOT, METRIC_SAMPLES, DIAGNOSTICS, CHECKPOINT, RAW_RESULT`。产物写入按新目录/新内容 hash append；导出失败产生显式 absent artifact 的 `missing_reason`，禁止捏造 sha/用同名文件覆盖。Run 结果记录是产物索引，不是某个 CSV 本身。

## 4. MetricDefinition 与 MetricSample 最低 Schema

定义在指标注册表（ARCH-03 合同）中、在 Run spec 冻结 **内容**，而非只在绘图或 Experiment Analyze 时按名称临时解释。

```yaml
metric_definition:
  id: timeout_rate
  version: "1.0.0"
  digest: "sha256:<real>"
  unit: "1"                          # dimensionless ratio; not percent without conversion
  value_type: ratio
  direction: lower_is_better
  source_events: [task_created, task_deadline_expired, task_completed]
  numerator: "<versioned rule for late task count>"
  denominator: "<versioned eligible generated task count>"
  population_rule: "<eligibility/censoring/actual-generated-task policy>"
  window: {time_basis: sim_time, start_ns: 0, end_rule: horizon_or_terminal}
  zero_denominator: NOT_DEFINED       # never silent 0.0
  missing_policy: EXPLICIT_REASON
  aggregation: "<per-run ratio; across-run by AnalysisRecord with prescribed weights>"
  terminal_and_cancellation_policy: "<explicit censoring rule>"
  precision_and_rounding: "<declared>"
  domain_and_legacy_mapping: "<if any>"
metric_sample:
  sample_id: "<stable-id>"
  run_id: "<run-id>"
  generation: 0
  definition_ref: {id: timeout_rate, version: "1.0.0", digest: "sha256:<real>"}
  frame_revision: 123                 # committed only, never staged proposal
  time_ns: 123000000000
  numerator: 3
  denominator: 60
  value: 0.05
  unit: "1"
  quality: OBSERVED                   # OBSERVED | ESTIMATED | MISSING | INVALID
  missing_reason: null
  provenance_ref: "artifact/event/frame digest"
```

样例仅解释结构，不是来自实际运行。样本应对分子/分母取自同一窗口、同一群体的结构化原始计数进行验证；分母零 -> `value=null, quality=MISSING, missing_reason=ZERO_DENOMINATOR`；缺字段 -> `NOT_OBSERVED`；测量失败 -> `PROVIDER_FAILED`；取消而统计未完成 -> `RUN_CENSORED`；定义无法解释 -> `DEFINITION_MISMATCH`。不得缺值补零、用 `NaN` 假装合法 JSON 数值、把不同窗口/分母/单位的值仅凭相同 id 合并。

多源采样同一 `sample_id` 与内容摘要必须一致，否则 `SAMPLE_ID_COLLISION`；记录 `frame_revision` 防止观察未提交提案；finalize 的聚合样本标出来源 sample 集及聚合规则。跨 Run 的统计检验、置信区间、排名 **仅 EXP-01 AnalysisRecord 产生**，MetricProvider 不拥有结论权。

## 5. 实验、比较门与不可变分析

`ExperimentPlan` 冻结 `definition_digest, factor_matrix, control_digest, run_spec_digests[], seed_mapping_digest, paired_stream_contract, pre_registered_metrics[], inclusion/exclusion, retry_selection, analysis_methods, estimands, comparison_key`。不同处理组只允许声明的 treatment 变更；同 seed 不自动构成公共外生扰动，须验证 B04 的 stream identity/consumption 策略。

`BatchRecord` 保存 `batch_id, plan_digest, entries[{logical_run_key, run_id, attempt_id, dispatch_state, run_record_digest?, failure_reason?}], created_at, closed_at?, completeness`；未启动、被拒、失败、取消与重试全保留，不以成功的 run 重建批次。分析引用 BatchRecord 的 **固定 revision/digest** 以防后续追加改变样本集。

`AnalysisRecord` 保存 `analysis_id, analysis_schema_version, preregistration_ref, plan_digest, batch_snapshot_digest, metric_definition_digests, comparator_gate_version, gate_input_fingerprint, gate_decision, reason_codes[], eligible_run_attempt_refs[], excluded_run_attempt_refs_with_reason[], missingness_and_censoring, statistical_method, estimates[], uncertainty_intervals[], limitations, analysis_artifact_digest, reviewer_status`。门拒绝仍创建带 `gate_decision=NOT_COMPARABLE` 的记录，`ranking=null`；允许描述单 Run 原始读数但不允许发布算法排名。

**strict research ranking 必须 gate=PASS 且至少满足**：指标定义 digest/window/denominator/缺值语义一致；可解释的固定任务暴露/horizon/时钟；固定 world/scenario/dataset/model/engine 基线（仅明示 treatment 可变）；随机配对规则通过或正确非配对分析；相同群体/重复/删失策略且所有 attempts 计账；关键 artifact/digest 验真；适用域相符。`unknown` 不等于相等、不允许支撑排名。只要硬条件失败即 `NOT_COMPARABLE`，不生成 winner/排名/显著性优劣宣称。

Legacy `results/compare_gate.py` 存在普通 descriptive 与 strict 两种检查语义；**其“未知种子可带警告描述性并列”不意味着新研究排名适格**。继续保护 `results/compare/*`、旧配置与原始 CSV；只能生成新 sidecar。不同 code commit（尤其 #41 vs master）、模型 revision 或指标 schema 应先阻断，除非预注册明确声明它是 treatment 并说明因果识别策略。

## 6. 版本/状态约束与实施范围

- 每种资源显式 `schema_version`；引用同时固定 `id+version/revision+sha256`；上游文件/PR HEAD 变化必须复核影响，不能静默沿用本合同的确认态。
- 追加记录与不可变内容寻址可先由本地 `manifest.json + jsonl + artifact` 实现；本合同**不要求数据库、对象存储、微服务或 UI**。
- 所有 `PASS` 仅限其对应门：contract lint / CI / software Verification / independent Validation / UQ / experiment comparison 分开存储，不能相互映射。
- 验收需要正反契约 fixtures（见 `RESULT_COMPARABILITY_TEST_CASES.md`）；本 PR 只含测试用例定义，**尚未执行动态测试**。

## 7. 待联合签字问题

1. ARCH-02：RunRecord 创建落盘时机、record_revision 事件格式与销毁后审计保留；RunArtifact writer 原子性及故障提交。
2. ARCH-03：MetricDefinition registry 放置位置、定义规范化哈希、MetricProvider `finalize` 跨组件聚合能力和指标口径 registry 的演进。
3. EXP-01 + AI-C CONTRACT-03：随机流配对/seed digest、`logical_run_key` 和 retry/attempt 的身份、planned analysis 的排除规则。
4. ARCH-01/02/03：B01 原子边界、B02 组件签名、B03 时间基准、B06 rollback 影响 CommittedFrame/MetricSample 的最终形态。
5. VVE-01：Validation/UQ 的审阅签名/门控、证据包发布资格；G0 不能由本 Draft 自行判 PASS。

**判定：B05 契约候选已完整提出；联合接口 G0 = HOLD / NO-FREEZE，直至上述签署与负例验证。**
