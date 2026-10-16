# ARCH-06｜ADR 主控决策登记

状态术语：COORDINATOR_DIRECTIVE = 主控决定后续规范方向但等待跨组会签；PROPOSED = 未裁决提案；ACCEPTED = 有负责方会签、独立复核并经主控最终批准；SUPERSEDED = 由后续决议取代。**本批 ADR 均未达到 ACCEPTED 条件。**

| ADR | 核心决定 | 当前状态 | 会签要求 |
|---|---|---|---|
| ADR-001 World identity | 不可变 World/Scenario，单个 Run 的独立 WorldState | COORDINATOR_DIRECTIVE | ARCH-01/02 |
| ADR-002 State boundary | 唯一 Harness writer，单 boundary 单对外 revision，内部暂存 | COORDINATOR_DIRECTIVE | ARCH-01/02/03 |
| ADR-003 Component/event ABI | public propose、internal normalized change set、精确 ns、唯一 event envelope | COORDINATOR_DIRECTIVE | ARCH-01/02/03 + AI-A/B |
| ADR-004 Experiment identity | 四元组 cell key + 三元组 spec 唯一绑定；attempt 不等于 replicate | COORDINATOR_DIRECTIVE | EXP/ARCH-02 + AI-C/D |
| ADR-005 RNG | exogenous vs run-private 随机流；LP4/HKDF candidate；明确相同 seed 不保证相同扰动 | COORDINATOR_DIRECTIVE | EXP/ARCH-01/02/03 + AI-C/D |
| ADR-006 Run/Metric/Evidence | Harness 单 Run、组件指标口径、实验分析与 VVE claim 独立分责 | COORDINATOR_DIRECTIVE | ARCH-02/03/EXP/VVE |
| ADR-007 Legacy/M0-M5 | native strict 与 legacy opaque 隔离，先保护旧基线，按科学用途评定模型 | COORDINATOR_DIRECTIVE | ARCH-04/EXP/VVE + AI-E |

## 正式批准必须具备的真实记录
- 谁批准：明确角色和审查责任人，而不是“其他 AI 应已同意”。
- 批准什么：实际 PR 完整 HEAD SHA、字段/接口版本、拒绝规则、负例以及适用的 legacy 迁移约束。
- 何种状态：APPROVED、CONDITIONAL（写条件）或 REJECTED；只发送请求不算批准。
- 独立审查：AI-R 在最新 HEAD 逐一重审，记录被替代字段、依赖与结论。
- 批准位置：使用 GitHub PR review 或有身份/角色/审查 SHA 的可复核评论；不得由主控冒用其他签字。需要时新建合并到 docs/governance/DECISION_LOG.md 的 PR，当前该治理簿仍在未合并的 #51 中。

## 冻结边界
设计冻结只代表契约可用于后续编码；不是软件执行、模型现实有效性、实验统计结果或 UI 可用性。M1/M2 契约负例、Legacy parity、现实 Validation、UQ 和工作台 E2E 应分别提交真实证据。因有未解决 P0，当前无已接受的 v1-frozen 接口。
