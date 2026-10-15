# 任务登记与依赖台账

规则：主控维护；每个任务一个 owner、branch、Draft PR、输入 SHA 与验收人。状态仅允许 BACKLOG / READY / IN_PROGRESS / REVIEW / BLOCKED / ACCEPTED / CLOSED。ACCEPTED 不等于 MERGED。

| ID | 目标 | 当前状态（2026-10-15） | PR | 依赖/门禁 |
|---|---|---|---|---|
| ARCH-01 | 世界抽象 | REVIEW | #46 | 联合接口 |
| ARCH-02 | Harness | REVIEW | #49 | 联合接口 |
| ARCH-03 | 组件契约 | REVIEW | #47 | 语义一致性 |
| ARCH-04 | Legacy 迁移 | REVIEW | #50 | ARCH-01～03 |
| ARCH-05-R2 | 独立交叉审查 | BLOCKED | #48（旧报告） | 固定所有上游 HEAD，含 EXP/VVE |
| EXP-01 | ExperimentDefinition/Runner/RunRecord | BACKLOG | 未创建 | 平台宪章裁决 |
| VVE-01 | Verification/Validation/UQ/Evidence | BACKLOG | 未创建 | 平台宪章裁决 |
| ARCH-06 | 主控统一冻结 | BLOCKED | 未创建 | ARCH-05-R2 |
| SLICE-01 | 最小无 UI 研究纵切 | BACKLOG | 未创建 | ARCH-06 |
| TASKUI-G0 | UI 审计缺口处理 | BLOCKED | #42-45 | 独立 G0 |
| L1-41 | 旧引擎生命周期修复 | REVIEW | #41 | 独立 CI/基线 |

## Task 卡必填
Task ID；目标和非目标；owner；reviewer；冻结输入（base SHA、上游 HEAD）；允许/禁止变更路径；依赖；交付物；正/负验收测试；证据链接；阻断和风险；最终裁决。

## 并发约束
- 依赖任务只在上游完成并锁定 HEAD 后启动；如上游推进则 REVIEW 过期，需要重新核对。
- 工作包不编辑别人的分支，不推送别人的 PR；主控统一改共享台账。
- 同一 PR 修复可继续原对话；新工作包新对话；独立审查新对话。
- 无充分证据只能写 UNVERIFIED / BLOCKED；禁止凭作者自述写 PASS。