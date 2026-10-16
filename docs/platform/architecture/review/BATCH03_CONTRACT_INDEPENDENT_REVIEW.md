# SwarmBalance Batch 03｜AI-R 独立审查准入门记录（BLOCKED）

> Task ID: ARCH-05-R3 / BATCH03-AI-R-INDEPENDENT-REVIEW  
> 审查时点：2026-10-16（UTC，GitHub API 最新查询）  
> 仓库：`159357yangjun/SwarmBalance`  
> 状态：**BLOCKED / NO-FREEZE**。本文件是缺失上游的审查准入门取证报告，不是 CONTRACT-01～05 完整内容验收报告。  
> 变更政策：仅新增此文件；不编辑 CONTRACT-01～05、PR #54、Legacy、代码、测试、历史结果；不合并任何 PR。

## 1. 审查启动条件与核验结果

审查任务要求先核验 **五份**独立 Draft PR 全部交付，记录完整 HEAD、读取其**所有**变更文件，然后才可以比较和裁决 B01～B07。通过 GitHub API 查询所有近期 PR 与 `platform/contract-` 分支，并列出已存在四份 PR 的全部文件名，当前发现：

| 合同 | PR / 分支 | 当前完整 HEAD SHA | Open/Draft | 交付门 |
|---|---|---|---|---|
| CONTRACT-01（B01/B03）| [#58](https://github.com/159357yangjun/SwarmBalance/pull/58) / `platform/contract-01-state-events` | `fa894cde5b22a78f5dcac4b2fbe17b3f17fa3377` | 是/是 | PRESENT |
| CONTRACT-02（B02/B06）| [#55](https://github.com/159357yangjun/SwarmBalance/pull/55) / `platform/contract-02-component-runtime` | `b00cd337de2797b9819089b234a113e36513e003` | 是/是 | PRESENT |
| CONTRACT-03（B04）| [#56](https://github.com/159357yangjun/SwarmBalance/pull/56) / `platform/contract-03-experiment-rng` | `0b038f29e7f1957bf93e4afd1e3a171d54e5b620` | 是/是 | PRESENT |
| CONTRACT-04（B05）| [#57](https://github.com/159357yangjun/SwarmBalance/pull/57) / `platform/contract-04-results-evidence` | `1f3798ad0b4e378d6ec0d13cc6945b3a1133d118` | 是/是 | PRESENT |
| CONTRACT-05（B07）| 未发现 PR / 未发现建议 `platform/contract-05-implementation-gates` 分支 | **无** | **否** | **MISSING / BLOCKING** |

对照来源：[ARCH-05-R2 PR #54](https://github.com/159357yangjun/SwarmBalance/pull/54) 在 `99bd0eb6b910d691d6d7776da0a5fd3f973f2997`（Open/Draft），原本裁决为 HOLD/NO-FREEZE；其 B01～B07 作为后续审查问题清单，**不得**当作修复已经通过的证据。四份已存在合同 PR 的 base 均为 `master@2ab60c69a806a22d7ba20353dee0571752a0e8e5`。

**输入门判定：FAIL → 完整独立验收 BLOCKED。** CONTRACT-05 缺失造成前置条件不成立；此时不得声称五份完整变更文件已读取，也不得将某一设计原则看作共同签署的契约。

## 2. 已交付合同 PR 的文件清单（仅文件名核验）

- #58 CONTRACT-01：
  - `docs/platform/architecture/contracts/contract-01/STATE_COMMIT_CONTRACT.md`
  - `docs/platform/architecture/contracts/contract-01/STATE_EVENT_TEST_CASES.md`
  - `docs/platform/architecture/contracts/contract-01/TIME_AND_EVENT_CONTRACT.md`
- #55 CONTRACT-02：
  - `docs/platform/architecture/contracts/contract-02/COMPONENT_FAILURE_TEST_CASES.md`
  - `docs/platform/architecture/contracts/contract-02/COMPONENT_RUNTIME_CONTRACT.md`
  - `docs/platform/architecture/contracts/contract-02/PROPOSAL_AND_OBSERVATION_SCHEMA.md`
- #56 CONTRACT-03：
  - `docs/platform/architecture/contracts/contract-03/EXPERIMENT_SEED_CONTRACT.md`
  - `docs/platform/architecture/contracts/contract-03/REPRODUCIBILITY_TEST_CASES.md`
  - `docs/platform/architecture/contracts/contract-03/RNG_STREAM_OWNERSHIP.md`
- #57 CONTRACT-04：
  - `docs/platform/architecture/contracts/contract-04/EVIDENCE_TRACEABILITY_CONTRACT.md`
  - `docs/platform/architecture/contracts/contract-04/RESULT_COMPARABILITY_TEST_CASES.md`
  - `docs/platform/architecture/contracts/contract-04/RUN_AND_METRIC_CONTRACT.md`
- CONTRACT-05：无法列出文件；没有查到对应已交付 PR。

以上是通过 GitHub `list_pr_changed_filenames` 返回的 12 个文件名，**并非**声称已经读取 12 份正文，亦非通过合同测试的证据。因为规定“全部五份交付之后开始”，正文级逐条验收在此处停止。

## 3. B01～B07 的正式裁决状态

| 问题 | 预定责任人 | 状态 | 不能提前宣称的结论 |
|---|---|---|---|
| B01：WorldState 多提交与 Harness 单 boundary 原子性 | CONTRACT-01；World/Harness/Components 会签 | UNVERIFIED | 未验证单写者、同刻回滚与 revision 共同语义 |
| B02：Scheduler/Dynamics 共同签名 | CONTRACT-02；Harness/Components 会签 | UNVERIFIED | 未验证 propose/decide、advance 统一接口 |
| B03：时间、事件 envelope 与排序 | CONTRACT-01；Harness/World/Components 会签 | UNVERIFIED | 未验证 time_ns、phase、priority 与去重 |
| B04：独立/配对 RNG 实验 | CONTRACT-03；EXP/Harness/World 会签 | UNVERIFIED | 未验证 treatment 不污染 CRN 扰动流 |
| B05：Run/Metric/Analysis/Evidence 身份与引用 | CONTRACT-04；Harness/EXP/VVE/Components 会签 | UNVERIFIED | 未验证不可变 DAG、比较拒绝与 attempt |
| B06：组件 checkpoint、rollback / fail closed | CONTRACT-02；Harness/Components 会签 | UNVERIFIED | 未验证私有状态的事务/拒绝能力 |
| B07：最小研究纵切实施顺序与阶段门 | CONTRACT-05；ARCH-04/EXP/VVE/主控会签 | **BLOCKED** | **上游文件本身缺失** |

“UNVERIFIED”不是“已解决”，也不等价于设计必然失败。对尚未进行正文交叉核验的项目，不应冒称 PASS/FAIL。先满足前置材料门，再单独给出文件级证据和冲突裁决。

## 4. 用户要求的横向审查项与阶段门

| 验收项 | 当前状态 | 原因 |
|---|---|---|
| CONTRACT-01～05 输入/HEAD/全文件门 | **FAIL** | 仅四份 PR；CONTRACT-05 缺失；五份全文未齐 |
| WorldState 唯一提交者、boundary 事务 | UNVERIFIED | 待 #58 × #55 × 原设计正文核对及正反证据 |
| Clock/Event/Component 共同签名 | UNVERIFIED | 待 #58 × #55 联合 schema 与调用顺序核对 |
| RNG 独立性与 paired CRN | UNVERIFIED | 待 #56 与 EXP/Harness/Scenario 对照 |
| RunRecord/MetricDefinition/AnalysisRecord/EvidenceBundle | UNVERIFIED | 待 #57 与 EXP/VVE 逐对象验证 |
| Legacy 保护与实际回退 | UNVERIFIED | 待 #50 × 缺失的 #05，回退执行证据尚无 |
| 最小无 UI 研究纵切工程顺序 | **BLOCKED** | CONTRACT-05（B07）未交付，不能代拟其签署阶段门 |
| Verification / Validation / UQ / Experiment Integrity | UNVERIFIED | 现有 VVE 意向不等于五方合同签署 |
| M0～M5 阶段门 | **UNVERIFIED / M5-source missing** | 缺少 CONTRACT-05 的阶段输入、产物、负例与回退定义 |
| ARCH-06 冻结建议 | **FAIL / HOLD / NO-FREEZE** | 启动条件失败，禁止宣称 B01～B07 已关闭 |

## 5. 必须修复项及恢复审查程序

**阻断 P0（责任：CONTRACT-05/AI-E、主控）：** 交付独立的 `CONTRACT-05` Draft PR，包含规定的 `IMPLEMENTATION_DEPENDENCY_PLAN.md`、`VERTICAL_SLICE_ACCEPTANCE.md`、`LEGACY_MIGRATION_GATES.md`，提供完整 HEAD SHA。未经该交付，不解除当前 BLOCKED。

**复审动作（责任：AI-R）：**
1. 重新查询全部五份 PR 的 Open/Draft、base、精确 HEAD 和文件名；如任何 SHA 变化，以最新不可变 ref 重取。
2. 逐份读取**全部 15 份预期文档**（实际数量以各 PR 真实文件清单为准），对照 PR #54 的 B01～B07，形成字段/签名/事件相位/归属及失败场景的文件级差异和正反例矩阵；不可根据标题判 PASS。
3. 对 M0～M5 逐一核对输入、输出、正/负案例、阻止条件、Legacy 回退与证据独立性；重点核对 B07 对最小无 UI 研究纵切的优先级。
4. 如果设计约定不一致，则列责任人、修复 PR 和未签署决策，保持 CONDITIONAL/FAIL；如需要运行验证，必须执行并链接真实日志；未运行必须明确 UNVERIFIED。
5. 仅在五份输入齐全、冲突闭合、独立复核完成后，向主控提供建议；主控独立决定是否走 ARCH-06。

## 6. 实际执行的检查与不存在的证据

**实际执行**：GitHub REST `GET /repos/159357yangjun/SwarmBalance/pulls?state=all&sort=created&direction=desc&per_page=12`；`search_branches(query=platform/contract-)`；PR #55～#58 的 `list_pr_changed_filenames`；复核 #54 的完整 HEAD 和 HOLD 决策。已取得上表确切元信息、12 个文件路径和缺失 #05 的列表证据。

**未执行**：五份全文交叉审查、契约 fixture 运行、单 Run/Experiment 执行、CI、E0/E1 基线再计算、回退演练、模型现实数据 Validation、UQ、统计实证、运行时 ABI 兼容验证。任何“测试通过”“已解决全部 B01～B07”“ARCH-06 可冻结”都**没有证据**，因此不予声称。

## 7. 交付完整性声明

此 Draft PR 仅存储可复核的 **BLOCKED 审查准入门记录**；它**不是**完整 CONTRACT-01～05 independent acceptance，不是任何上游设计的批准，也不是合同/实现的测试报告。五份输入门恢复后应在后续增量审查提交中更新裁决，而非将本记录的 UNVERIFIED 误当作 PASS。


---
# 2026-10-16 independent five-contract full-document review addendum (AI-R)

> **This addendum supersedes the earlier missing-CONTRACT-05 intake verdict for delivery only.** Original BLOCKED history is preserved above. All five Draft PRs now exist. Independent review is **document-level conditional/HOLD**, not code/runtime Verification, CI, physical Validation or an ARCH-06 authorization. Review source is the exact immutable SHAs below. Six PRs (#55–#60) were rechecked Open/Draft; the five contracts changed only 15 Markdown files. All 15 contract document bodies were read at their fixed HEADs, including all future-test matrices. No executable test was run.

## A. Five-input ledger (document-content review scope)

| Contract | PR | Exact HEAD | Files audited |
|---|---|---|---|
| 01 | [#58](https://github.com/159357yangjun/SwarmBalance/pull/58) | `fa894cde5b22a78f5dcac4b2fbe17b3f17fa3377` | STATE_COMMIT_CONTRACT.md; TIME_AND_EVENT_CONTRACT.md; STATE_EVENT_TEST_CASES.md |
| 02 | [#55](https://github.com/159357yangjun/SwarmBalance/pull/55) | `b00cd337de2797b9819089b234a113e36513e003` | COMPONENT_RUNTIME_CONTRACT.md; PROPOSAL_AND_OBSERVATION_SCHEMA.md; COMPONENT_FAILURE_TEST_CASES.md |
| 03 | [#56](https://github.com/159357yangjun/SwarmBalance/pull/56) | `0b038f29e7f1957bf93e4afd1e3a171d54e5b620` | EXPERIMENT_SEED_CONTRACT.md; RNG_STREAM_OWNERSHIP.md; REPRODUCIBILITY_TEST_CASES.md |
| 04 | [#57](https://github.com/159357yangjun/SwarmBalance/pull/57) | `1f3798ad0b4e378d6ec0d13cc6945b3a1133d118` | RUN_AND_METRIC_CONTRACT.md; EVIDENCE_TRACEABILITY_CONTRACT.md; RESULT_COMPARABILITY_TEST_CASES.md |
| 05 | [#60](https://github.com/159357yangjun/SwarmBalance/pull/60) | `56ad6fe7b0f3a1b0b2b613d68a6e5bd5240dc955` | IMPLEMENTATION_DEPENDENCY_PLAN.md; VERTICAL_SLICE_ACCEPTANCE.md; LEGACY_MIGRATION_GATES.md |

All five use base `master@2ab60c69a806a22d7ba20353dee0571752a0e8e5`. Compare against [ARCH-05-R2 #54](https://github.com/159357yangjun/SwarmBalance/pull/54) at `99bd0eb6b910d691d6d7776da0a5fd3f973f2997`. **File-level links below are exact SHA permalinks, not floating branches.**

## B. B01–B07 closure adjudication

| Issue | Document-level grade | File-level observation and residual P0/P1 | Required owner/signatures |
|---|---|---|---|
| **B01** one writer/atomic boundary | **CONDITIONAL** | [#58 STATE_COMMIT §§2–6](https://github.com/159357yangjun/SwarmBalance/blob/fa894cde5b22a78f5dcac4b2fbe17b3f17fa3377/docs/platform/architecture/contracts/contract-01/STATE_COMMIT_CONTRACT.md) requires only Harness B/C authority, provisional staging, single externally published rev and B/C/D/RNG/queue rollback; [#55 COMPONENT_RUNTIME §§1,3–4](https://github.com/159357yangjun/SwarmBalance/blob/b00cd337de2797b9819089b234a113e36513e003/docs/platform/architecture/contracts/contract-02/COMPONENT_RUNTIME_CONTRACT.md) coheres at intent. **However #46 WORLD_STATE §3 remains visibly phase-micro-commit permissive; ADR-002 and ARCH-01/02/03 signatures absent.** New logical durability of Run artifacts not proved. ST-03/C06-03/04 NOT_RUN. | ARCH-02 + ARCH-01/03, AI-A/B; coordinator |
| **B02** Scheduler/Dynamics common API | **CONDITIONAL** | [#55 COMPONENT_RUNTIME §1–2](https://github.com/159357yangjun/SwarmBalance/blob/b00cd337de2797b9819089b234a113e36513e003/docs/platform/architecture/contracts/contract-02/COMPONENT_RUNTIME_CONTRACT.md) defines scheduler `propose(ObservationV1,ctx)`, dynamics `propose(StateSliceView,Conditions,ModelIntervalRef,ctx)`; [#55 PROPOSAL §1–4](https://github.com/159357yangjun/SwarmBalance/blob/b00cd337de2797b9819089b234a113e36513e003/docs/platform/architecture/contracts/contract-02/PROPOSAL_AND_OBSERVATION_SCHEMA.md) adds stage token and typed proposals. [#58 STATE_COMMIT §3–4](https://github.com/159357yangjun/SwarmBalance/blob/fa894cde5b22a78f5dcac4b2fbe17b3f17fa3377/docs/platform/architecture/contracts/contract-01/STATE_COMMIT_CONTRACT.md) still labels generic `ChangeSet` with emitted intents. **ActionProposal/StateDeltaProposal → ChangeSet/validator reducer mapping, ClockRef/BoundaryRef and domain typed operation variants remain unsealed.** Original #49 decide/advance vs #47 propose not formally reconciled. C02-01/02/03/05/06 NOT_RUN. | ARCH-03/ARCH-02 + ARCH-01, AI-B/A |
| **B03** event/time ordering | **CONDITIONAL** | [#58 TIME_AND_EVENT §§2–5](https://github.com/159357yangjun/SwarmBalance/blob/fa894cde5b22a78f5dcac4b2fbe17b3f17fa3377/docs/platform/architecture/contracts/contract-01/TIME_AND_EVENT_CONTRACT.md) proposes exact decimal→ns, EventSpec/Intent/Envelope, `(time_ns,phase_rank,priority,producer_id,producer_seq,event_id)`, fact vs next-boundary event. [#55 PROPOSAL §1,7](https://github.com/159357yangjun/SwarmBalance/blob/b00cd337de2797b9819089b234a113e36513e003/docs/platform/architecture/contracts/contract-02/PROPOSAL_AND_OBSERVATION_SCHEMA.md) deliberately defers envelope fields to AI-A. **Phase-kind registry, initial t=0, horizon inclusion, late same-time policy and EventProvider window admission not co-signed/frozen.** ST-06/07/09/16/17 NOT_RUN. | ARCH-02 + ARCH-01/03/AI-A, coordinator |
| **B04** independent/paired RNG | **CONDITIONAL** | [#56 EXPERIMENT_SEED §§1–7](https://github.com/159357yangjun/SwarmBalance/blob/0b038f29e7f1957bf93e4afd1e3a171d54e5b620/docs/platform/architecture/contracts/contract-03/EXPERIMENT_SEED_CONTRACT.md) assigns Plan seed over Scenario default, shares *immutable exogenous exposure* not treatment RunSpec digest, separates private RNG; [#56 RNG_STREAM §2–4](https://github.com/159357yangjun/SwarmBalance/blob/0b038f29e7f1957bf93e4afd1e3a171d54e5b620/docs/platform/architecture/contracts/contract-03/RNG_STREAM_OWNERSHIP.md) reserves stream namespaces and attempts. **KDF byte canonicalization, golden vectors, PRNG/distribution/numeric versions, event converter linkage and pairing oracle unverified.** C03-T01–T09 NOT_RUN. | EXP-01, AI-C, ARCH-01/02/03 |
| **B05** Run/Metric/Analysis/Evidence ownership | **CONDITIONAL with blocking schema delta** | [#57 RUN_AND_METRIC §§1–5](https://github.com/159357yangjun/SwarmBalance/blob/1f3798ad0b4e378d6ec0d13cc6945b3a1133d118/docs/platform/architecture/contracts/contract-04/RUN_AND_METRIC_CONTRACT.md) sets Harness single RunRecord even standalone, MetricDefinition registered by ARCH-03, EXP Batch/Analysis, VVE Claim/Bundle; [#57 EVIDENCE §§1–3](https://github.com/159357yangjun/SwarmBalance/blob/1f3798ad0b4e378d6ec0d13cc6945b3a1133d118/docs/platform/architecture/contracts/contract-04/EVIDENCE_TRACEABILITY_CONTRACT.md) content-hash DAG, separate SW/EX/RV/UQ. **New identifiable conflict:** [#56 RNG_STREAM §4](https://github.com/159357yangjun/SwarmBalance/blob/0b038f29e7f1957bf93e4afd1e3a171d54e5b620/docs/platform/architecture/contracts/contract-03/RNG_STREAM_OWNERSHIP.md) logical cell key includes `frozen_run_spec_digest`, but #57 RUN_AND_METRIC §3 `logical_run_key=(plan_digest,treatment_id,replication_id)` omits it. Also `replicate_key/replication_id` spelling and run_id/attempt_id resolution across Batch need canonical mapping. C03-T03/RCT-06 and crash finalization NOT_RUN. Ref canonical hashing and durable writer semantics still OPEN. **Do not freeze M2 identities.** | AI-C/AI-D, EXP-01 and ARCH-02/03/VVE co-sign |
| **B06** private D rollback/checkpoint | **CONDITIONAL** | [#55 COMPONENT_RUNTIME §§3–4](https://github.com/159357yangjun/SwarmBalance/blob/b00cd337de2797b9819089b234a113e36513e003/docs/platform/architecture/contracts/contract-02/COMPONENT_RUNTIME_CONTRACT.md) says PURE/TRANSACTIONAL/LEGACY_OPAQUE; prepare/abort/checkpoint, strict reject nonreversible D; [#58 STATE_COMMIT §4–6](https://github.com/159357yangjun/SwarmBalance/blob/fa894cde5b22a78f5dcac4b2fbe17b3f17fa3377/docs/platform/architecture/contracts/contract-01/STATE_COMMIT_CONTRACT.md) requires full boundary fence. **publish_prepared non-throw is a required assumption, not demonstrated; external side effects, reset/restart/cancel/timeout atomicity require tests.** C06-01…19 NOT_RUN. | ARCH-02/03 + AI-A/B, Legacy ARCH-04 |
| **B07** staged research slice and rollback | **CONDITIONAL** | [#60 IMPLEMENTATION_DEPENDENCY_PLAN §§2–4](https://github.com/159357yangjun/SwarmBalance/blob/56ad6fe7b0f3a1b0b2b613d68a6e5bd5240dc955/docs/platform/architecture/contracts/contract-05/IMPLEMENTATION_DEPENDENCY_PLAN.md) defines M0→M1→M2 no-UI research slice, M3 replacement/Legacy, M4 physical Validation/UQ, M5 UI; [#60 VERTICAL_SLICE_ACCEPTANCE](https://github.com/159357yangjun/SwarmBalance/blob/56ad6fe7b0f3a1b0b2b613d68a6e5bd5240dc955/docs/platform/architecture/contracts/contract-05/VERTICAL_SLICE_ACCEPTANCE.md) has independent positive/negative gates and [#60 LEGACY_MIGRATION_GATES](https://github.com/159357yangjun/SwarmBalance/blob/56ad6fe7b0f3a1b0b2b613d68a6e5bd5240dc955/docs/platform/architecture/contracts/contract-05/LEGACY_MIGRATION_GATES.md) S0–S6/K/G mapping. **Requires ARCH-04/EXP/VVE signatures, no implemented M0–M5 tests.** M2 depends on B04/B05 unresolved identity; implementation order is a reasonable design proposal, not validated critical path performance. | AI-E + ARCH-04/EXP/VVE, AI-R, coordinator |

**Closure count**: B01–B07 have proposed remediation text; **0 unconditional PASS closures**, **7 CONDITIONAL design cases**, **all executable/empirical outcomes UNVERIFIED**. The B05 schema identity delta is a concrete cross-contract mismatch requiring correction, not simply absence of testing. Original #54 NO-FREEZE remains prudent.

## C. Independent cross-interface and stage gate table

| Item/gate | Grade | Specific reason |
|---|---|---|
| Intake five Draft PRs, full immutable HEAD and changed-file scope | **PASS** (document intake only) | #55–#58 and #60 exist Open/Draft, 15 doc additions; 15 texts reviewed |
| G0 joint interface/schema approval | **FAIL/HOLD** | ADR/co-sign absent; B05 logical cell key conflicts; B01 original micro-commit wording not reconciled; B02 reducer mapping remains proposed |
| M0 protection design | **CONDITIONAL** | concrete hash and legacy compare gates designed; no live freeze evidence |
| M1 WorldState/Harness/Component no-UI Run | **UNVERIFIED** | ST/C02/C06/RCT fixtures not executed; same-time atomicity is proposal |
| M2 seed Plan→RunRecord→Analysis research loop | **FAIL as freeze candidate / UNVERIFIED runtime** | B04 KDF vectors/CRN missing and B05 logical cell key conflict; RCT comparator NOT_RUN |
| M3 plugin/map/Legacy parity and rollback | **UNVERIFIED** | G-M0…G-M7 execution and first divergence/rollback logs absent |
| M4 independent reality Validation/UQ | **UNVERIFIED / NOT_ASSESSED** | no independent calibration/holdout measured results; no model claim PASS |
| M5 professional UI workbench task flow | **UNVERIFIED** | no UI E2E/TaskUI G0 approvals asserted |
| Separate SW Verification / EX Integrity / RV Validation / UQ | **CONDITIONAL design** | #57 Evidence and #60 plan explicitly separate all four; not empirically demonstrated |
| ARCH-06 freeze recommendation | **FAIL / HOLD / NO-FREEZE** | above interface and evidence blockers |

## D. Must-fix priorities, negative tests and handoff

- **P0 / EXP-01 + AI-C + AI-D + ARCH-02**: canonical logical experiment cell identity and `replicate_key`/`replication_id`, `FrozenRunSpec` digest, per-attempt `run_id`/retry semantics and compare-and-set selection across #56/#57/#60; run a true crash/retry double-count fixture C03-T03/RCT-06 before M2 approval.
- **P0 / ARCH-01 + ARCH-02 + ARCH-03 + AI-A/B**: one accepted boundary revision protocol replacing #46 public phase micro-commit in strict V1; types for ActionProposal/StateDelta→ChangeSet reducers; accepted Observation token, ClockRef/EventEnvelope phase registry, failure/rollback error mappings; ADR and signatures first, then ST-03/16, C02-05/06/11, C06-04 actual negative tests.
- **P0 / AI-C + EXP-01 + ARCH-02**: freeze reproducible KDF canonical encoding/golden vectors, seed engine/distribution adapter, external tape and pair validity oracle; execute C03-T01/T02 and negative full-RunSpec-derived exo stream case.
- **P1 / ARCH-04 + AI-E + Legacy reviewers**: verify baseline hashes, actual G-M0…G-M7 parity and recovery, #41 vs master strata and compare gate refusal; preserve `legacy_direct` unmodified.
- **P1 / VVE + independent research reviewer**: require actual observed reference errors, UQ and domain scope before any REAL_WORLD claim; a software or compare PASS is insufficient.
- **P1 / UI/TaskUI owner**: TaskUI G0/G1 separate; no workbench promotion based on document-only design.

**Actually executed for this addendum**: GitHub PR metadata and changed-file queries for all five; each of 15 Markdown texts fetched from exact SHA; static side-by-side type/semantic inspection; independent report GitHub branch commit; compare changed-file scope. **Not executed**: pytest, runtime Harness/Experiment, CI, mutation/negative fixtures, model physical Validation/UQ, historical E0/E1 reproducibility or Legacy rollback. Never replace missing actual outputs with expected fixture results.

**Decision:** intake PASS, detailed documentation review complete, **ARCH-06 = HOLD / NO-FREEZE** until all P0 type/identity/semantics disagreements close under jointly signed versioned schemas and actual executable proof. Preserve old report history above rather than overwriting its original missing-input observation.
