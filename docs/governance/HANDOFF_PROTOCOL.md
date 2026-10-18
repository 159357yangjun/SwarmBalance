# Agent 对话接力与证据协议 V1

## 协作拓扑
一个主控对话维护方向、裁决、任务、验收；每个执行工作包一个独立任务对话；同一 PR 修复沿用该对话；每批独立审查必须新建对话。主控可按阶段更换，但应通过 GitHub 状态恢复，而非复制聊天历史。

**GitHub 是权威工程事实源**：仓库代码、合并后 ADR、PR 和 CI；Draft 文档是提案，聊天是工作缓存。共享治理文件仅由主控任务修改。各执行方不能靠彼此聊天自动交换信息。

## 新任务启动必读顺序
1. 当前 `master` HEAD、PR 状态与 CI；检查此文档及 `PROJECT_STATUS.md` 日期。
2. `docs/platform` 中已批准的目标宪章和总体计划；未入库/未批准的目标列 PROPOSED。
3. `DECISION_LOG.md` 中 ACCEPTED ADR；`INTERFACE_REGISTRY.md` 中冻结接口。
4. 相关任务 Draft PR 的真实 HEAD 与源码或文档 blob 内容。
5. 读取任务书中的变更白名单、验收和禁止事项。

## 输入任务书最小格式
```
Task ID / Objective / Non-goals / Owner / Reviewer
Repo / base branch + full SHA / upstream PR + exact HEAD SHAs
Editable paths / forbidden paths / proposed branch
Interfaces & ADRs / dependencies / deliverables
Acceptance: positive + negative tests / evidence formats / rollback
```

## 交付格式
```
Task ID / Status
Base SHA / Head SHA / Draft PR link
Changed files + scope check
Tests actually executed + logs or workflow URLs (not planned tests)
Implementation or design evidence with precise file references
Interface changes / compatibility / risks
Blockers / questions for main coordinator
Reviewer verdict / next action
```

## 状态与冲突规则
- REVIEW 发出后冻结审查输入 HEAD；若 SHA 改变，审查失效范围必须声明并增量复核。
- 独立审核者只读核证开发工作，不能根据开发者总结直接给 PASS。
- 上游未交付时不得提前进行“已审核全部上游方案”的审查。
- CI PASS 只证明相应软件检查，不等于真实物理 Validation PASS 或科研结论可信。
- 未经用户批准不得合并、覆盖主线、修改他人分支或删历史证据。
- 任务中断由新对话从 PR、SHA、状态台账重建；发现冲突报告主控而不是自行解决跨界面协议。