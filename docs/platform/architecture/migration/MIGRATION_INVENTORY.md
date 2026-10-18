# ARCH-04 / 保留-适配-重构-替换清单与 PR 影响

> 冻结基线：`master@2ab60c69a806a22d7ba20353dee0571752a0e8e5`（2026-10-15 静态读取）；“重构/替换”表示**未来建议**，不是本 PR 进行的修改。此 PR **仅六份文档**。

## 1. 决策词汇

- **保留 R**：保持既有源码与接口不变，作为受保护科学基线。
- **适配 A**：通过新边界包装旧行为；输入输出转换不引入新的物理/调度/统计语义。
- **重构 F**：在后续单独变更中拆耦合，需先有负向测试和行为对照。
- **替换 X**：仅在新实现通过独立科研认证后允许，旧实现仍可选且原始结果保留。

| 子系统 / 关键路径 | 决策 | 边界与理由 | 首个可改阶段 |
| --- | --- | --- | --- |
| `frontend/environment.py` | R→A；F 待审 | 环境唯一事件与物理执行入口；先以 `LegacyEnvironmentAdapter` 包裹 | S2 仅新增 adapter |
| `frontend/drone.py`、`task.py`、`charging_station.py`、`no_fly_zone.py` | R | 不改质量、能耗、状态机和禁飞区逻辑 | 禁止混入 ARCH-04 |
| `frontend/route_planner.py`、`route_cost.py` | R→A | 保留绕飞口径；地理模型替换需新模型 ID | S3 可引只读桥接 |
| `frontend/tools/osm.py` | R→A | 缓存/解析模式显性登记，不改高度推断 | S1–S2 |
| `frontend/data_source.py` | R→A | 保留历史路径解析兜底；新增解析清单 | S1 |
| `frontend/greedy/scheduler.py` | R→A | Greedy 走 `greedy_action_from_observation`，非直接调用实例 `step` | S2 |
| `backend_si/{ga,pso,ortools}_scheduler.py`、`matching.py`、`chain_codec.py` | R→A | 冻结算法、配置、随机数；统一能力声明而非继承重写 | S2 |
| `backend_si/config.yaml` | R | 旧格式/注释不改；新模型配置独立命名空间 | S1 |
| `config/simulation.json`、`positions.json`、`import/*` | R→A | 字段、默认值、相对路径优先级原样解释；新 Project/World schema 显式转译 | S1 |
| `config/config_loder.py` | R→A；F 有条件 | ENV 覆写+内容签名；仅旧 worker 允许模块全局 | S1–S4 |
| `config/scenes/`、`console/scene_library.py` | R→A | 场景是初始配置，schema_version 校验不可绕开 | S3 |
| `console/sim_session.py` | R→A | 原样运行 legacy 事件、轨迹、checkpoint，统一包装入口 | S2 |
| `console/server.py` | R→A；F 后续 | 当前 `_session` 和 `_op_lock` 原样存活；新 API 不覆写 `/api/*` | S4 |
| `console/scenario_presets.py` | R | 演示可逆 patch 是旧功能，绝非新 Harness 的场景协议 | S3 |
| `console/experiment_service.py` | R→A | 保留单活动子进程的旧限制；新作业服务独立目录 | S5 |
| `console/static/index.html` | R | 当前 UI 静态审查见 #43/#44/#45，ARCH-04 不重排 UI | 不在本任务 |
| `experiments/runner.py`、`worker.py`、`presets/*.yaml` | R→A | 保留每 run 子进程隔离、同 Seed 设计与 legacy result 产物 | S1–S5 |
| `experiments/reporting.py`、`reproducibility.py` | R→A | 先新增 sidecar 信息，不改主表或已有统计计算 | S5 |
| `frontend/metrics_schema.py` | R | 单一导出列真源，绝不重定义 | 永不随迁移更改 |
| `results/compare_gate.py`、`results/compare/manifest.json` | R | 研究可比性硬门，不能绕过；CSV 不自动转新格式 | 永不随迁移更改 |
| `results/experiments/*`、`results/compare/*` | R | 历史证据只读；新结果落 `results/platform_runs/<run-id>/`（**提议路径**） | S5 |
| 新增 `platform/*`（**提议**） | A→F/X（可选） | ARCH-01/02/03 联合冻结接口后再引入 Harness | S1–S6 |

## 2. PR #41–#45 逐一冲突与依赖检查

全部为 **open / Draft / unmerged**（按 2026-10-15 GitHub PR 元数据）。**既存 PR 保持原样，不合并/关闭/改 base。**

| PR | head（审计时） / base | 已查看的实际变更范围 | 对迁移的影响 / 审查行动 |
| --- | --- | --- | --- |
| [#41](https://github.com/159357yangjun/SwarmBalance/pull/41) L1 生命周期 | `logic/l1-task-lifecycle-delivery-proof-v1@f1bf21cc42f2566b2981a1a6092cbedf215db809` → `ci-validation`；87 文件 | **运行语义敏感**。修改 `frontend/environment.py`、`frontend/drone.py`、`experiments/reproducibility.py` 等及回归/CI；源码 diff 涉及“必须见证取货才能完成”、任务终态更新等。不可与 master 结果直接无注释混比；将 master 和 #41 各自定义不同 `engine_source_sha`/`model_revision`，待独立门禁 |
| [#42](https://github.com/159357yangjun/SwarmBalance/pull/42) TaskUI 规则 | `ui/taskui-01-rules@874ac7096595c3ba5b80da530373c6ef0593488c` → `master`；42 文件 | `TaskUI/*`、`console/static/AGENTS.md`、独立 workflow 与 docs；未改生产模拟和真实 UI；ARCH-04 不引入该工具链为必需依赖 |
| [#43](https://github.com/159357yangjun/SwarmBalance/pull/43) UI-00 | `ui/taskui-00-audit@a0983f62013335ad6f96ed4e88a68ea8021b7b1b` → `master`；6 文档 | 给出 Web 与 Python frontend 的真实角色；迁移兼容入口复用其审计，不把它当作已验收 UI |
| [#44](https://github.com/159357yangjun/SwarmBalance/pull/44) UI-02 | `ui/taskui-02-requirements@7636e09f8e5f2cb46cf9360a6be722ad269f8fc1` → `master`；6 文档 | 用户任务、场景/快照语义、`/api/compare` 可比性硬门为新 API 合同输入；未做运行 UI 验证 |
| [#45](https://github.com/159357yangjun/SwarmBalance/pull/45) 跨审 | `ui/taskui-b01-cross-review@298ec05be0bf114ea78e8184713231cbc066f697` → `master`；1 文档 | 报告 G0 HOLD（含两项 P0）是**审查意见**，不是新平台准入证明；ARCH-04 不声称解除 G0 |

**重叠治理**：#41 已改模型/实验溯源，ARCH-04 不追逐其代码同步以免设计基线飘移；如后续合并 #41，需新建 baseline、对照测试和重新 pin SHA。#42–45 目前与 ARCH-04 提议文档目录无直接文件重叠；若将来修改 console 或 UI 文件，必须联合复核 G0/G1 并检查对应 HEAD。PR #41 改动文件达到 87，不应视为“仅 L1 几行修复”。

## 3. 变更文件白名单

当前 ARCH-04：仅可新增 `docs/platform/architecture/migration/{LEGACY_ARCHITECTURE,COUPLING_ANALYSIS,MIGRATION_INVENTORY,ADAPTER_DESIGN,BACKWARD_COMPATIBILITY,MIGRATION_SLICES}.md`。任何 Python、配置、UI、旧结果或 CI 文件改变都算越界，必须退出本 PR 并单独走实施门禁。
