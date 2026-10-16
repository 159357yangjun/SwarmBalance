# CONTRACT-04 — 结果可比性与证据链契约验收用例

> B05 / AI-D | status PROPOSED; **这些是将来必须执行的 fixtures，不是本 PR 已运行的测试结果。** 架构跨组 G0 仍 HOLD / NO-FREEZE。
>
> Source lock: #54 `99bd0eb6b910d691d6d7776da0a5fd3f973f2997`；#49 `d155621aca66e3a80c388718093a452d17d71e10`；#47 `68382c649393057ffbf5a14508ab1ff72d575b09`；#52 `a966567b1a2a033f477c2847073cc11777a3afd2`；#53 `9e9d8918c1e6989568e84c3f0d020fdffb0373de`；#50 `c4c0c67111ead435062650c1ed776547c477e3e3`；#51 `f2df96bc609ee1e430ea6eff2456c4577347c300`；共同 base `2ab60c69a806a22d7ba20353dee0571752a0e8e5`。

## 1. 判定接口（供合同测试实现使用）

输入：`comparison_request{analysis_plan_digest,plan_digest,batch_snapshot_digest,required_metric_definition_refs[],run_attempt_refs[],claim_scope}`。Resolver 应先验证完整 ref/hash 与 plan，调用 `check_comparability` 产生不可变：
```yaml
decision: PASS | NOT_COMPARABLE | INSUFFICIENT_EVIDENCE
gate_version: "contract-04@0.1.0"
input_fingerprint: "sha256:<real>"
reason_codes: []
per_run: [{run_id: "...", attempt_id: "...", included: true, reason: null}]
ranking_allowed: false  # true only for actually-PASS strict research gate & valid preregistered ranking method
ranking: null            # forced null on any refusal
```
仅 `PASS` 代表通过**设计可比性门**；不是统计显著性、建模真实有效性、Validation PASS 或“某算法获胜”。`NOT_COMPARABLE` 表示已证明不可比；`INSUFFICIENT_EVIDENCE` 表示必要证据缺失/不确定；两者对排名一律 fail closed。决策记录需要 `reason_codes + compared_values + affected_refs + remediation`。具体 schema/序列化由会签确定。

## 2. 必备 fixtures（正例及负例）

| ID | 给定输入 / 触发 | 预期判定、必须保存的记录 |
|---|---|---|
| RCT-01 正例：独立手动 Run | 手动 UI/CLI 创建并正常完成，无 experiment_ref | Harness 创建唯一 RunRecord、FrozenRunSpec/Artifact/MetricSample refs，`origin=MANUAL, experiment_ref=null`；不要求 BatchRecord |
| RCT-02 正例：受控两组比较 | 同一确定模型、world/scenario/dataset、时窗和指标 digest；预注册 treatment 唯一 Scheduler、两组尝试完整，所有必需原始证据可核对；B04 配对语义已证明 | `comparison_gate=PASS`，AnalysisRecord 记录纳排/方法/估计量；仅当满足预注册排名/统计要求才允许非空 ranking；物理 Validation 仍独立 NOT_ASSESSED |
| RCT-03 运行前失败 | run_id 已分配但 assembly 缺数据 digest，FrozenRunSpec 无法最终冻结 | `RunRecord.status=FAILED`，`spec_digest=null`，存 freeze_error、时间与错误；不可捏造 artifacts；Batch 可引用失败 |
| RCT-04 取消保全 | 完成若干 boundary 后 STOP/CANCEL | 原 RunRecord `CANCELLED`，last_committed_snapshot 与 stop_reason 有据，指标样本部分/删失注明；不能按成功并入完整样本 |
| RCT-05 指标故障 | World commit 成功但 post-commit MetricProvider 抛异常 | Run 主状态按 Harness terminal reason 保持；metric=PARTIAL/MISSING, evidence=INCOMPLETE, `PROVIDER_FAILED`；不撤销已提交 world revision、不以0替代 |
| RCT-06 重试去重 | 一个 plan replication 的 attempt-1 FAILED、attempt-2 SUCCEEDED | 两个独立 run_id/attempt_id、`retry_of` 链；Batch 全部保留；Analysis 根据预注册策略只选一个合法统计样本，禁止把二者当独立重复 |
| RCT-07 分母为零 | 指标定义请求 timeout_rate；本 Run eligible generated tasks=0 | `MetricSample.value=null, quality=MISSING, missing_reason=ZERO_DENOMINATOR`；不得写 `0.0` 或比较该点 |
| RCT-08 缺失列 | Legacy 20 列 schema 缺少 `空载率`，对手有 25 列 schema | `MISSING_METRIC` + `NOT_COMPARABLE`；原始空值保留 NaN/null，不补零、不出排名 |
| RCT-09 定义冲突 | 两 Run 都叫 timeout_rate，但 denominator = generated tasks vs due tasks，或 window 不同 | `METRIC_DEFINITION_MISMATCH` / `WINDOW_MISMATCH`，拒排名；单位比例/百分比未经版本化换算也拒绝 |
| RCT-10 运行协议混淆 | 一个 horizon 600 steps/30 generated tasks，另一个 2000 steps/60 tasks | `EXPOSURE_MISMATCH`，`NOT_COMPARABLE`；无 winner |
| RCT-11 不完整 seed | 两组仅称 `seed=101`，实际 Scheduler 改动 RNG 消费序，未有共享外生流的可验证计划 | `RNG_PAIRING_UNPROVEN`；不得做 paired significance 或排位；需 AI-C 确认有效配对，或预注册合适独立样本设计 |
| RCT-12 版本漂移 | 一个 Run 使用 master commit，另一个使用 PR #41 改变任务完成语义的 commit，但宣称同模型对照 | `ENGINE_MODEL_REVISION_MISMATCH`；除非它就是预注册 treatment 且分析明确因果问题，否则拒绝 |
| RCT-13 工件被替换 | RunArtifact 的内容变化，原记录 sha256 不变 | `ARTIFACT_HASH_MISMATCH`，EvidenceBundle `REJECTED/INCOMPLETE`；严禁根据路径直接补 hash |
| RCT-14 悬挂引用 | Claim -> Analysis -> Batch 中缺少一条 RunRecord 或 DatasetManifest | `PROVENANCE_INCOMPLETE`，列出断边；Claim `INSUFFICIENT`，原 bundle 仍可审计 |
| RCT-15 假阳性 CI | PR 工作流 CI SUCCESS，Validation 无独立现实数据、误差和预声明门槛 | `CI_CHECK=PASS`、`ValidationRecord=NOT_ASSESSED`；现实准确性/可部署声明拒绝 `REAL_WORLD_CLAIM_NOT_SUPPORTED` |
| RCT-16 域外外推 | 已验证模型域 wind<=6m/s，研究声明风 10m/s 真实可用 | `MODEL_OUT_OF_DOMAIN` / `VALIDATION_SCOPE_MISMATCH`，Claim 不可标现实 SUPPORTED |
| RCT-17 Legacy opaque 故障 | env.step 写入状态后崩溃，不能原子回滚 | Run `FAILED+TAINTED`，保留首次失效 boundary / partial evidence；不输出合法后续 replay 或排名 |
| RCT-18 pre/post commit | 预提交拒绝提案 + postcommit exporter 故障分别注入 | 前者原 state/revision/RNG 不变；后者不得回滚，独立标 Evidence INCOMPLETE；引用最后完整 revision |
| RCT-19 历史 unknown | 旧 ad-hoc baseline 种子集/episode_count=unknown，普通 legacy compare gate 可警告显示描述性并列 | 新 strict research ranking `INSUFFICIENT_EVIDENCE`；不得把 `unknown==unknown` 判为可复现实验 |
| RCT-20 旧数据不可覆写 | 导入 `results/compare` CSV 后生成 sidecar，导入前后源 sha256 相同 | PASS only if original unchanged；允许追加新存储/manifest，不得“补全”旧 CSV 后写回 |
| RCT-21 bundle完整≠现实验证 | all hashes links resolve，Bundle `COMPLETE`；Validation NOT_ASSESSED | 仅证据链接完整；Claim 不可宣布现实验证 PASS |
| RCT-22 缺席 batch attempt | 计划四个 replication，仅三个被启动，另一个调度失败 | Batch 仍包含第四个 `NOT_DISPATCHED` entry + reason；Analysis 不可自动将 3 描述为“完整4” |

## 3. 真实仓库可证明的**必须拒绝排名**反例

此反例来自 `master@2ab60c69a806a22d7ba20353dee0571752a0e8e5` 中**已存在的历史 manifest 声明**，不是本轮新执行的对比测试：

- `results/compare/manifest.json`：`backend_ga_metrics.csv` 标记 `quarantined=true`；内部 5 行为 400 steps / 22 generated tasks，1 行为 600 steps / 30 tasks；`metrics_schema_version=n25-e5c7244bc840`。
- `backend_ortools_metrics.csv`：2000 steps / 60 tasks，`metrics_schema_version=n20-75f2e8bdb73e`；Greedy/PSO ad-hoc 基线亦为 2000/60/20列。
- `results/compare_gate.py` 已有按来源声明 + 磁盘签名 + quarantine 拒绝混组逻辑；`frontend/metrics_schema.py` 的 legacy 缺字段补 `0.0` 是新 MetricSample 必须消除的风险（**不能修改历史结果**）。

强制预期：
```yaml
comparison:
  members: ["backend_ga_metrics.csv", "backend_ortools_metrics.csv"]
  purpose: "rank algorithms by completion/timeout rate"
result:
  decision: NOT_COMPARABLE
  reason_codes: [EXPOSURE_MISMATCH, METRIC_SCHEMA_MISMATCH, LEGACY_QUARANTINED, REPLICATION_SEED_UNKNOWN]
  ranking_allowed: false
  ranking: null
  preserve_original_csv: true
```

**理由**：运行长度 600 vs 2000、任务分母 30 vs 60、25 vs 20 列及未知完整 seed/episode，任何 0.7667 vs 0.9667 的并排“谁更优”都混入暴露量、定义和选择偏差；GA 隔离状态是硬拒绝。不得为了凑柱状图替换其 horizon、删除失败行或把缺失的机队指标补 0。即便历史 `one_click_latest.csv`（同 3600 horizon、5 repeats、seeds 101–105、60 tasks）四算法内部可在已声明范围对照，也需补齐本合同的 manifest/digest/质量证据后才能对新的严格研究排名声称 PASS；不能迁移自动升级旧声明。

## 4. 可执行验收流程（未来实施 PR）

1. 构造隔离的 fixture 输入（所有 hash 用测试时实际内容 sha256；本文件中的 `<real>`、说明字符串不得提交给 runtime 充真实 digest）。
2. 逐个运行 `freeze_spec`、Harness `create/run/export`（涉及生命周期者）、metric validation、`check_comparability`、`verify_links`、`assess_scope`。
3. 持久化 `fixture_id, implementation_commit_sha, test_case_digest, runner_version, timestamp, input/output_artifact_digest, actual_decision, expected_decision, diff, reviewer`；只有**真运行日志**存在时才允许记测试 PASS。
4. 读取 legacy `results/compare_gate.py` 的 `--check-all`、`--selftest` 和隔离运行的 `--check-group` 输出作回归证据；任何写历史结果目录的操作立即 FAIL。
5. 对所有拒绝用例断言 `ranking=null`、证据链保留、reason_codes 非空；对所有成功用例断言冻结内容真实可解析；检测错误不应吞异常或改成零。
6. 允许引擎实施在最低 slice 使用 JSON/JSONL 本地 store；测试不要求 DB、分布式调度、云服务。

**本 Draft 中真正执行的验证：只核验 GitHub PR 固定 HEAD、阅读相关设计/legacy 文档与写入范围；没有运行上述 RCT-01～22、CI、统计对照或现实模型 Validation。** ARCH-06 必须再次检查实际 HEAD/差异和会签，不能将测试计划当测试通过。

## 5. 单一逻辑单元与 RNG identity 扩展验收（C03/C04 对齐）

**唯一规范**：`logical_cell_tuple=(plan_digest,treatment_id,replicate_key,frozen_run_spec_digest)`；旧 `replication_id` 仅作为受控导入别名。精确 canonical LP4 / attempt identity / HKDF / 独立可复算 G01–G13 golden vectors 和 ID-N01–N16 的预期拒绝，见 [LOGICAL_RUN_IDENTITY_AND_RNG_CONVERGENCE.md](LOGICAL_RUN_IDENTITY_AND_RNG_CONVERGENCE.md)。本节扩展原 RCT-06、RCT-11、RCT-19、RCT-22；**还不是实现测试运行结果**。

| Extension | Input/fixture | Expected oracle (not executed) |
|---|---|---|
| RCT-ID-01 | 重试 attempt-1/attempt-2，输入 cell 相同 | cell_key/spec_digest/exogenous key/private key 一致；ordinal/attempt_id/run_id 不同；两条原记录保留 |
| RCT-ID-02 | 模拟成功结果落盘但 ack 丢失，按相同 ordinal 重发 | 返回同一 attempt_id/run_id，禁止启动新 Run，Batch 计数不增加 |
| RCT-ID-03 | 改 frozen model/metric/code/seed digests 还请求原 cell retry | `SPEC_CHANGED_NOT_RETRY`，不得以旧 plan 掩盖新的运行定义 |
| RCT-ID-04 | 同 plan paired A/B 用不同 Scheduler、同 p02/r02 外生源 | G09 外生键相同；G11/G12 private 键不同；保留 event tape/因果应用差异；若同样 seed 但实际 tape 不同则 `CRN_EXPOSURE_MISMATCH` |
| RCT-ID-05 | 改 replicate r02→r03，或更换外生数据、时间/分布定义 | G09/G10 不同；已存在配对身份被重新评估，不自动升级为 CRN |
| RCT-ID-06 | 伪造非 NFC 文本、重叠导入 alias、错误长度前缀、错误 UINT64 浮点化 | `IDENTITY_ENCODING_INVALID` 或 `REPLICATE_ALIAS_CONFLICT`；不能悄悄转换出另一个键 |
| RCT-ID-07 | `run_id` 被放入 FrozenRunSpec hash，或者相互包含 plan_digest/spec_digest | `ATTEMPT_FIELDS_IN_SPEC` / `CYCLIC_SPEC_PLAN_DIGEST`；冻结前拒绝 |
| RCT-ID-08 | 未决 attempt-1 与 attempt-2 均被算为独立成功 replicate | `ATTEMPT_OUTCOME_UNRESOLVED` / strict `INSUFFICIENT_EVIDENCE`；`ranking=null` |
| RCT-ID-09 | CRN exo key 混入 algorithm id/attempt/worker 或共享可变 Scheduler RNG | `CRN_NAMESPACE_CONTAMINATION` / `PRIVATE_STREAM_OWNER_CONFLICT`，拒 paired claim |
| RCT-ID-10 | 向审查报告提交 G01–G13 KDF 数学一致性而没有 Run/CI log 或分布 sampler 版本 | 仅能报告 vector math check；**不得标注 simulator replay PASS 或 model Validation PASS** |

执行门：实施方至少在两个独立语言/代码路径重算并记录完整 G01–G13 的实际输出；测试 `ID-N01..N16` 逐项使用结构化拒绝码，且任何 NOT_COMPARABLE / INSUFFICIENT_EVIDENCE 必须 `ranking=null`。**本轮只进行了局部纯数学向量计算（Python/Node.js 代表性核对），没有执行上述 RCT-ID 测试或仓库 CI。**

## 5. 待决问题 / 责任接口

- ARCH-02：失败前创建 RunRecord 以及错误/导出状态如何写盘，Run Artifact 的原子元数据索引。
- ARCH-03：MetricDefinition 固定字段与 hash 规范、MetricProvider post-commit 与 zero-denominator。
- EXP-01/AI-C：attempt selection、共享随机流、预注册排序/统计门的具体算法。
- VVE-01：Validation 的独立数据和 reviewer 标准，Claim 状态的语义版本。
- ARCH-04：legacy descriptive vs strict research gate 的映射，sidecar 存储。
- AI-A/B 与主控：B01/B02/B03/B06 改动可能影响 frame 语义；未经联合 G0 不允许冠以 FROZEN。
