# 主控架构决策记录（ADR Ledger）

本文件登记**已批准**决定与候选提案；未签字提案不能当作冻结契约。每个 ADR 必有日期、责任人、影响范围、替代方案、理由、反对意见、基线 SHA、涉及 PR、验证门和替代/废止关系。

| ADR | 议题 | 状态 | 当前约束 |
|---|---|---|---|
| ADR-000 | 多智能体协作：固定主控+任务对话+独立审核+GitHub 权威状态 | PROPOSED | 本 PR 待批准 |
| ADR-001 | Project/World/Scenario/Run/WorldState 身份关系 | OPEN | ARCH-01/02/03 会签 |
| ADR-002 | 单写入者、提交事务、事件顺序与时钟 | OPEN | ARCH-01/02/03 会签 |
| ADR-003 | 组件语义兼容、单位、CRS、时间分辨率 | OPEN | ARCH-03 主责 |
| ADR-004 | Experiment 一等资源与独立 Runner | OPEN | EXP-01 |
| ADR-005 | Validation & Evidence，分清 Verification/Validation/UQ | OPEN | VVE-01 |
| ADR-006 | Legacy 隔离、回退和结果比较 | OPEN | ARCH-04 |
| ADR-007 | 首期低空物流领域边界与首个研究纵切 | OPEN | 主控 |
| ADR-008 | UI 任务驱动布局与可操作性门禁 | OPEN | TaskUI |

### 决策模板
`ADR-ID | Status(PROPOSED/ACCEPTED/REJECTED/SUPERSEDED) | Context | Decision | Alternatives | Consequences | Evidence | Approvers | Date | Supersedes`

**任何跨团队冲突**：执行方提交带文件行号的差异→主控指定 owner 修订→独立复核→统一 ADR；不得默认为最新聊天版本优先。