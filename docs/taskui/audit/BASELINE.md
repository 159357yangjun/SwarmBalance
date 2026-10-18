# TASKUI-SB-UI-00 — 仓库与 UI 静态审计基线

- 审计时间：2026-10-14；方法：通过 GitHub API 读取分支、PR、递归 Git tree、源代码和检查记录；**未启动浏览器、服务或仿真**。
- 冻结 UI / 文档基线：\`master\` = **\`2ab60c69a806a22d7ba20353dee0571752a0e8e5\`**。
- 目标分支：\`ui/taskui-00-audit\`，从上述 master SHA 创建；本 PR 只能新增本目录六份文档。
- \`ci-validation\` HEAD = \`34cf506ea9b0871fba395e47df6dc96b3a2a21b0\`；与 master 比较：ahead 33、behind 0。改动覆盖 \`frontend/drone.py\`、\`frontend/environment.py\`、CI/测试/文档；**不是** master 同义别名。
- PR [#41](https://github.com/159357yangjun/SwarmBalance/pull/41) 当前 open、Draft、未合并，base = \`ci-validation\`（\`34cf506...\`），head 分支 \`logic/l1-task-lifecycle-delivery-proof-v1\`，head = **\`f1bf21cc42f2566b2981a1a6092cbedf215db809\`**。CI 读取到 head 的 Full suite/root、console、frontend、experiments、verification 和 lifecycle-green 为 success；部分按条件跳过。**绿色检查不等于 PR 被接受/合并**。
- \`ci-validation...PR#41\`：ahead 195、behind 0；变化包括 \`frontend/drone.py\` 和 \`frontend/environment.py\`，未见 \`console/static/index.html\` / \`console/server.py\` / \`console/sim_session.py\` 在该比较的变更清单中。不能据此保证后端与新生命周期行为完全兼容。

## 冻结选择与适用范围

**选择 master 精确 SHA 作为 TaskUI 静态结构基线**：它是仓库默认公开分支、审计文件实际取样的代码版本；对 master 新增文档的 PR 不会隐式携带 \`ci-validation\` 的 33 个提交或 #41 的 195 个提交。它不代表 master 的任务生命周期已有 #41 修复。UI 未来对内核进行集成验证时须单独指定批准的生命周期基线，不得擅自 cherry-pick、rebase 或合并 #41。

准确措辞：**静态源码基线确定；运行行为未验证；生产质量与实验可复现性未据本轮重新认证**。本次没有启动 UI、截屏、测量布局或执行测试。仓库已有 \`deliverables/界面展示/\` 图片是历史素材，非当前 SHA 的现场截图，不用于判定本轮实际渲染。

## 来源索引与校验规则

| 项 | 证据路径 / 行段 | 结论类型 |
|---|---|---|
| UI 入口与依赖 | \`console/static/index.html:1-29,600-665,1342-1369\` | 源码已验证 |
| 启动与静态资源服务 | \`console/run.py:1-78\`; \`console/server.py:45-58,194-227\` | 源码已验证 |
| 单一会话、命令与快照 | \`console/server.py:61-76,263-396\`; \`console/sim_session.py:103-212,663-685\` | 源码已验证 |
| 视图/导航/详情 | \`console/static/index.html:633-1154,1667-1692,2663-2687\` | 源码已验证，用户体验仅推断 |
| 仿真与指标保护 | \`console/sim_session.py:180-200,1254-1292\`; \`frontend/environment.py\`; \`results/compare_gate.py\` | 调用链已验证，实验结果未复验 |
| 分支与 SHA | GitHub branch API、PR #41 metadata、compare API | API 已验证 |
| Head checks | GitHub commit check-runs API（PR #41 HEAD）| API 已验证；结果会随新提交改变 |

**复验方式**：先检查上述 SHA 是否仍为分支 HEAD；按文件+行号定位代码；后续 UI 设计审查需 G0/G1 决策后再进入组件/交互改动。本轮文档行号均指 \`2ab60c...\`，其它分支行号不能直接套用。

## 审计不做的事

不宣称 Vue Router、Pinia、Vite/npm 工程存在；不把 \`frontend/\` 当作 Web 前端；不把演示指标当成已通过独立实测的真实世界指标。不修改 \`config/simulation.json\`、\`backend_si/config.yaml\`、仿真、调度、API、测试或任何既有 PR。