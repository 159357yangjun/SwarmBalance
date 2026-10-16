# ARCH-06 主控架构冻结裁决｜2026-10-16

**Final current verdict: HOLD / NO-FREEZE.**  
**Coordinator direction: DECIDED FOR RECONCILIATION; NOT YET A SIGNED/FROZEN V1 ABI.**

本报告是架构裁决门，不是软件实现、真实模型验证或独立复审替代品。未获授权不合并其他 PR、不修改 legacy 代码或历史科研结果。

## 一、固定 GitHub 输入（各 HEAD 为审查时实际快照）

共同 base：master 2ab60c69a806a22d7ba20353dee0571752a0e8e5。

| PR | 任务 | HEAD |
|---|---|---|
| #46 | ARCH-01 | b5f05a70a3306f1799fcae2c3f342f3ed9ee0048 |
| #49 | ARCH-02 | d155621aca66e3a80c388718093a452d17d71e10 |
| #47 | ARCH-03 | 68382c649393057ffbf5a14508ab1ff72d575b09 |
| #50 | ARCH-04 | c4c0c67111ead435062650c1ed776547c477e3e3 |
| #52 | EXP-01 | a966567b1a2a033f477c2847073cc11777a3afd2 |
| #53 | VVE-01 | 9e9d8918c1e6989568e84c3f0d020fdffb0373de |
| #54 | ARCH-05-R2 | 99bd0eb6b910d691d6d7776da0a5fd3f973f2997 |
| #58 | CONTRACT-01 | bd5e47266d79d1e087ca8cfc6fe68ea28a03496b |
| #55 | CONTRACT-02 | fd7ae6a5668f2cd97174628120435281e31e1a30 |
| #56 | CONTRACT-03 | 0b038f29e7f1957bf93e4afd1e3a171d54e5b620 |
| #57 | CONTRACT-04 | 027fd78589229db3d2308ced5365b7a780703805 |
| #60 | CONTRACT-05 | abc93227b9e3160da1023d6c582e7a93ff9094b5 |
| #59 | ARCH-05-R3 review | e76eb483d5760d99673774d48dc699f6a833ad7f |

独立 R3 核查了五个 CONTRACT、17 份文档，判定 B01–B07 均 CONDITIONAL，0 项无条件 PASS。#55–#60 的 GitHub review 列表经本轮核验均无正式 review 批准；评论/请求会签不等于会签。未执行本轮 Harness、实验、崩溃恢复、legacy parity 及模型现实 Validation 的运行证明。

## 二、主控正式定向裁决（下一修订的约束，不是跨组批准）

1. **ADR-002 状态**：严格 V1 一个 boundary 对外只发布一次 WorldState revision；内部 phase 仅有 provisional/stage_seq，Harness 是唯一提交者；ARCH-01 旧同刻 micro-commit 不能继续作为 strict V1 的规范选项。
2. **ADR-003 组件**：唯一公共入口 Scheduler.propose(ObservationV1,ProposalContext) 与 DynamicsModel.propose(StateSliceView,Conditions,ModelIntervalRef,ProposalContext)。公共 ProposalHeaderV1，经 Harness 转为内部 NormalizedChangeSetV1；不能同时维护另一套可执行 ChangeSet 公共 API。
3. **ADR-004 时间与事件**：Run 内 uint64 sim_time_ns，输入秒必须精确可转换；唯一 EventEnvelopeV1 及 (time_ns,phase,priority,producer_id,producer_seq,event_id) 顺序。EventProvider 的批次 window_ref 选择 EventWindowRefV1；DynamicsModel 的 ModelIntervalRef 不得代替事件轮询窗口。初始 t=0、horizon、同刻迟到和 kind→phase 表属于必须最终会签的表。
4. **ADR-005 实验**：采纳 C03C04-IDENTITY-v1 四元组 (plan_digest,treatment_id,replicate_key,frozen_run_spec_digest) 作为哈希身份候选，附加三元组 (plan_digest,treatment_id,replicate_key) 到 spec digest 唯一绑定约束；同一槽位不同 spec 拒绝 CELL_SPEC_CONFLICT，必须新建 Plan，不能悄然多算一次 replicate。attempt ordinal/run_id 与统计 replicate 分离。
5. **ADR-006 RNG**：拟使用 LP4/HKDF-HMAC-SHA256 v1 字节规范；配对外生随机流不得含 treatment 或 full RunSpec digest；私有流可依赖完整冻结运行语义。随机分布、全对象 canonical spec digest、checkpoint 数值环境需另版固定，不能将 13/13 合成数学向量当作 CRN 集成通过。
6. **ADR-007 证据与迁移**：ARCH-02 拥有每个 RunRecord，ARCH-03 拥有 MetricDefinition，EXP 拥有 Batch/Analysis，VVE 拥有验证记录/可信声明；SW/EX/RV/UQ 各自判门。保留 legacy_direct 默认和旧结果只读，M0→M1→M2→M3→M4→M5 分期验证。

## 三、未解除的 P0 阻断（真实存在）

| P0 | 实际缺口 | 负责人 / 必需证据 |
|---|---|---|
| P0-01 | #55 的 change-set.v1/boundary_id 与 #58 的 normalized-changeset.v1/boundary_ref 尚未同版批准；原 #46 micro-commit wording 与 strict 不一致 | AI-A/AI-B + ARCH-01/02/03：唯一 schema、全字段映射、正反样例、HEAD 会签 |
| P0-02 | #58 EventIntentBatch.window_ref 在不同段落标作 ModelIntervalRef 与 EventWindowRefV1；时窗端点与 phase 规则未冻结 | AI-A/AI-B + ARCH-02/03：确定 EventWindowRefV1、错类型负例、t0/horizon/phase 表 |
| P0-03 | #57 已提议四元组+LP4/HKDF，但 #56 及 EXP/ARCH-02 尚未共同接受，完整 Spec canonicalizer、sampler 版本与 retry durability 仍待定 | AI-C/AI-D + EXP/ARCH-02/03：一致字节规范、可复核数学向量、负例及变更语义 |
| P0-04 | 跨组正式会签证据为零，独立 #59 最终仍 NO-FREEZE | 各领域责任人分别以角色、所审 HEAD、schema、无条件/有条件结论批准；AI-R 增量复核，主控最后裁决 |

## 四、ARCH-06 门禁裁决

| Gate | 结果 | 解释 |
|---|---|---|
| G06-1 输入冻结/独立 R3 | PASS（文档级） | 五组最新 HEAD 与 #59 审查存在 |
| G06-2 无 P0 接口冲突、单一规范 | FAIL | P0-01～03 |
| G06-3 ADR 正式批准与会签 | FAIL | P0-04；不伪造审批 |
| G06-4 负例契约测试实际执行 | UNVERIFIED | 只存在计划与少量数学向量 |
| G06-5 Legacy/M0 基线与回退 | UNVERIFIED | 未见本轮实际执行证据 |
| G06-6 模型现实适用性 V&V/UQ | NOT_ASSESSED | 属于 M4，不由设计冻结自动通过 |

**裁决：HOLD。尚不得把 v1-candidate 改名为 v1-frozen、不得自动将 ARCH-01～05/EXP/VVE/CONTRACT 相关 Draft PR 认作可合并、不得宣称科研结果已可信。**

设计冻结退出门：零未决 P0 字段/失败语义矛盾，跨组版本化接口与 ADR 正式签字，独立 AI-R 复审认可。随后 M0/M1 需要实测软件正反例而不是使用设计预测；现实 V&V 与 UQ 单独在 M4 评定。

## 五、马上执行的任务

- AI-A + AI-B：对同一 ProposalHeader / NormalizedChangeSet / EventWindowRef 编写单一可签署 schema，修改各自 #58/#55 分支，消除 #46 原始微提交解释冲突。
- AI-C + AI-D：对同一 C03C04-IDENTITY-v1、LP4/HKDF、full-spec digest 与 retry idempotency 出具一致文档，更新 #56/#57。
- AI-E：待 #55/#56/#57/#58 更新后再调整 #60 的 M0–M5 表。
- AI-R：以新 HEAD 更新 #59 独立复审，逐项给出 PASS/CONDITIONAL/FAIL/UNVERIFIED，书面记录签字。
- 主控：只有收到 G06-2/3 实际 PASS，才发布独立 ARCH-06-FINAL 冻结裁决。

## 六、实际检查与未执行声明

本轮调用 GitHub 最新 PR 列表，逐一核查合同变更文件清单、独立 R3 最新正文、主要冲突的最新规范段及 GitHub PR reviews。**未执行 Python pytest、仿真 Run、同随机流配对实验、Legacy 回退或模型 Validation。** 绝不使用预期执行结果替代真实证据。
