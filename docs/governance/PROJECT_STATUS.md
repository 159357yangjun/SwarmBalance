# SwarmBalance 项目状态（主控维护）

更新基准：2026-10-15；状态：INITIAL / 待主控复核。**本文件不是自动同步状态**；使用前必须重新读取 GitHub PR、分支、CI 与 HEAD SHA。

## 项目定位
低空物流可信、可扩展仿真与实验平台。核心能力：World、Components、Harness、Experiment System、Validation & Evidence、Workbench。原始异构无人机调度/机巢/任务链研究成果与长期平台建设采用双轨验收。

## 当前事实
- master 基线：`2ab60c69a806a22d7ba20353dee0571752a0e8e5`（创建本治理分支时核对）。
- ARCH-01 PR #46（世界）Draft；ARCH-02 PR #49（Harness）Draft；ARCH-03 PR #47（组件）Draft；ARCH-04 PR #50（迁移）Draft；ARCH-05 PR #48（独立审查）Draft；均未合并（2026-10-15 核对）。
- 旧 ARCH-05 报告的“设计 PR 缺失”已过时；独立内容复审尚未完成；V1 契约未冻结。
- Experiment System 和 Validation & Evidence 已提出为关键缺口，尚无获准冻结的具体契约。
- 旧引擎保留；新 Harness 不能宣称已完成。TaskUI G0 HOLD；L1 PR #41 仍需单独核实。

## 当前门禁
- G-GOV-0：治理协议 Draft PR 已创建，待审查批准。
- G-ARCH-1：ARCH-01～04 PR 提交证据齐备。
- G-ARCH-2：接口一致性 / EXP / VVE / 六场景内容级复审：HOLD。
- G-ARCH-3：ARCH-06 契约冻结：BLOCKED。
- G-ENG-1：最小无 UI Harness + 实验 + 证据纵切：NOT STARTED。
- G-VAL-1：模型现实适用性验证：NOT ESTABLISHED。

## 下一批顺序
1. 主控审阅并批准平台宪章、计划和治理规范（当前均不得假定已冻结）。
2. EXP-01、VVE-01 并行产出最小契约；ARCH-01～04 处理边界问题。
3. 上游 PR HEAD 固定后，另开独立 ARCH-05-R2 对话完成真实内容交叉审核。
4. 主控做 ARCH-06 决策；通过后才分批实现最小纵切。
5. UI 按 TaskUI 自身门禁推进；不以效果图替代验证。

## 更新协议
只有主控在核对精确 GitHub 证据后修改；每次更新附：检查时间、base/head SHA、PR、变更及门禁证据。聊天观点不得覆盖 GitHub 可核查事实。