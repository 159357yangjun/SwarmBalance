# L1 任务生命周期修复——完成事实单一证人

> 2026-10-12 · Draft PR #41 · **独立于 L0 取证 PR #40**。本文陈述修复设计、RED 证据与剩余边界；任何 CI 通过结论必须来自最终精确 HEAD，不从旧 SHA 借用。
>
> 基线：PR #36 HEAD `b23a8e4362260acb6a0df330fbd8665581d0e567`。冻结 `master=2ab60c69a806a22d7ba20353dee0571752a0e8e5`，E0/E1 与厂家/能耗参数不变。

## 1. 真正发现的问题

[L0 PR #40](https://github.com/159357yangjun/SwarmBalance/pull/40) 在正式 Python 3.10 与实际 `Environment.step` 下故障注入成功复现“仍有未完成 assignment 时，`is_free` 从假变真导致计数增加”的问题。L0 固定 HEAD `ff7e03b8cb7a247b2731f86e42e8541ae1deece1` 专项 2/2 是**按预期识别 RED**，不是已修复。常规 UI 是否自然产生该故障状态未证明。

L1 基线测试为**独立重新构造的真实行为门**，不是手抄 `Environment` 算法。第一次 [L1 RED CI #38210376229](https://github.com/159357yangjun/SwarmBalance/actions/runs/38210376229) 运行于 SHA `c8a71b7582685da9958a157b545ffd63620da55d`，实际 **3 tests / 3 FAIL**，均到达期望断言：
1. `[L1_PHANTOM_COMPLETION]`：无真正 dest 消费，`completed:0→1`。
2. 没有 `load_time` 的任务直接调用记录路径会虚假增计数。
3. 合法实际 source→dest 路径完成后 `Task.status` 仍为 `assigned`（`[L1_TERMINAL_STATUS]`）。

## 2. 最小修复的状态语义

| 事件或前提 | 必须发生 | 明确禁止 |
| --- | --- | --- |
| 调度器合法派单 | `pending→assigned`、写 assignment、保留容量 | 无效动作直接送达 |
| 执行器消费 `source` 服务航点 | `load_time` 与 `onboard_load_kg` 真实更新，`Task.status→in_progress` | 未取货即视为已运送 |
| 执行器消费 `dest` 服务航点 | **仅当**当前 assignment 有 `load_time` 且 Task 处于 assigned/in_progress，记账并 `Task.status→completed`、按顺序卸载 | 无取货证据、已完成订单重复记账 |
| `is_free` 转换，仍有 assignment | **保留清单、无人机置非空闲、维持/恢复未完成任务的预留载重**；等待显式故障恢复/人工核验 | 直接调用 `_record_task_completion`、凭空发放配送完成奖励、抛弃保管责任 |

修复只修改 `frontend/environment.py` 的完成记录、service waypoint 消费和旧 cleanup 兜底，不重写 `Drone.update` 或调度器适应度。为了保留旧方法的 observer 行为，`_record_task_completion` 仍由合法 `dest` 分支调用，但会在**任何计数变化前**检查取货与终态；成功返回 True，拒绝返回 False。

### 残余设计风险

- 故障注入残留清单时设置“保守冻结”是**故障安全行为**，不是自动恢复；若无外部恢复指令，该订单可能滞留至回合结束，因此下一步应增加独立“无人机悬挂任务回收/恢复”设计和超时未服务统计。**绝不**为了完成率好看而强行释放已取货物。
- `Drone.update` 末段能独立归零 `current_load`；L1 在残留清单时恢复预留容量并保持 `onboard_load_kg` 不变，但跨线程/崩溃完整一致性仍需 B5 checkpoint/restore 研究。
- `_record_task_completion` 为内部可信入口；是否全面改成独立、不可伪造的 `delivery_event_id` 和幂等事务，是 L1 后续子阶段，不应据此宣称完整身份认证或外部货物交接认证。
- `timeout_rate` 仍是“已完成订单条件超时率”，不在 L1 修改。未完成/到期未服务的总体评价属于 **L2**。
- 既有 `console/consistency_observer.py` 的调用点分类依赖 `_record_task_completion` 的源码调用环境，应在全量 CI 和固定场景上检查事件归因是否仍正确。
- E0/E1 **历史结果不可覆盖**；若逻辑修复改变相同 seed 的运行结果，应以新模型版本另存比较，并保留 `[E0_MILEAGE_SCOPE_INCOMPARABLE]` 适用警告。

## 3. 继承验证与验收

- 专项 `scripts/test_l1_task_lifecycle.py`：真实派单残留、未取货阻止完成、真实送达标完成、重复阻止、伪 dest 但未取货、已取货残留的机载质量守恒。每个测试构造不同 `Environment`，不是同一失败夹具换三个名称。
- [旧 RED #38210376229](https://github.com/159357yangjun/SwarmBalance/actions/runs/38210376229) 是不可覆盖的历史证据；[首次 GREEN #38210601811](https://github.com/159357yangjun/SwarmBalance/actions/runs/38210601811) 在原三项测试上是 3/3 PASS，但不得把它当作新六项测试/最终 HEAD 的证据。
- 新专项 CI 应实际运行 **6/6** 并继承生命周期/航点消费测试。
- PR #41 临时指向 `ci-validation`，精确 HEAD 九 Job `completed/success` 后才允许恢复原父分支 `audit/model-provenance-and-paired-plan-v1`，API 回读 HEAD、Draft、Open、未合并，并更新 PR 验收记录。
- 若老式代码范围、测试计数或冻结行为门因为**合法生产修复**而报错，保留真实失败并做最小范围调整，禁止删门或用旧 SHA 代替。
- 不修改冻结 `master`、历史 E0/E1、模型物理常数、调度算法，不未经同意合并。

## 4. 下一阶段门

L1 结束后先做 L2：从可独立核验的合法送达身份统计完成率、到期未服务与截尾订单。L3 将非法动作拒绝集中到 `Environment`；L4 引入按订单版本标记的预测与实际执行证据。当前 L1 只说明**局部配送生命周期一致性得到修复和测试**，不等于“整个仿真系统已经全面自洽”。
