# P2.4b-B4b — 自动换电目标身份与泊位资源守恒

> 仅在 `SWARM_BALANCE_AUTO_PLANNED_STATION=1` 且 `SWARM_BALANCE_CHARGE_TARGET_IDENTITY=1` 的隔离实验模式生效。默认不变，不是物理落地证明、自动外部救援或已取货货物回收。

## 父阶段与 RED/GREEN

- 父阶段 B4 不可变 HEAD `e669075e120d3e646ec7f0623346608736f26966`；全量 Windows CI [#38051651605](https://github.com/159357yangjun/SwarmBalance/actions/runs/38051651605) 9/9 通过。
- **初始 RED**：[#38064282363](https://github.com/159357yangjun/SwarmBalance/actions/runs/38064282363)，57 tests/1 FAIL：自动选择 B，A 与 B 同坐标时真实到站却登记到 A（`[B4B_AUTO_TARGET_IDENTITY_MISMATCH]`）。中途闭站及默认关闭对照通过。
- **首轮 GREEN**：[#38064735482](https://github.com/159357yangjun/SwarmBalance/actions/runs/38064735482)，57/57 PASS。限定实验模式将 B3c 的目标 ID 到站校验从人工换电扩展到自动低电改道，并在真实泊位队列注册/发放检查 ID、坐标、开放状态；换电完成清除目标与冻结标记，保留供 `Environment` 释放泊位的 `charging_station_id`。
- **第二轮严格 RED**：[#38064855047](https://github.com/159357yangjun/SwarmBalance/actions/runs/38064855047)，61 tests/1 FAIL：自动改道挂起订单时，伪造 `awaiting_berth=True` 且缺失目标 ID 仍可获取 B 泊位（`[B4B_AUTO_MISSING_TARGET_FREE_SWAP]`）。不同位置虚假到站、同坐标错误机巢与换电状态清理均已通过。
- **第二轮 GREEN**：[#38064957847](https://github.com/159357yangjun/SwarmBalance/actions/runs/38064957847)，61/61 PASS。缺失目标 ID 在**注册与最终授予**两道门都拒绝；对确实参与人工或自动充电改道的无人机启用 fail-closed；普通默认模式不改变。
- 所有测试使用真实 `Environment.step()`、`Drone.update()`、`Environment._manage_berths()`，并保留原有继承测试。失败不是被跳过或改小阈值。

## 关键安全与状态约束

1. 自动改道选择的 `charge_target_station_id` 要跟踪至实际到站和真实泊位授予，不能再用 `find_nearest_station` 重新挑同坐标 A。
2. 实验模式挂起订单的自动无人机，目标 ID 缺失、错误、站点关闭、实际坐标不符，一律不占泊位，不增加 `total_swap_sessions`，也不获得无成本的电池能量。
3. 目标机巢中途关闭仍按 B3c 既有冻结与保留任务口径处理；未经新规划与 Wh 报价不得改飞其他站。
4. 换电结束清空目标和冻结字段，原订单的 `executing_task_id`、`_suspended_route` 恢复使用既有账本机制，泊位释放仍按 `_pending_release` 真实事件。
5. 默认 `assigned` 能耗口径、Greedy/PSO、E0/E1 冻结原始资料和 `simulation.json` 未修改；两个实验开关均不自动启用。

## 验收路线

- B4 历史文件范围测试锁定在不可变 `e669075e120d3e646ec7f0623346608736f26966`，B4b 新增严格七文件白名单。源码插入行导致物理参数证据登记表有九处锚点位置漂移，逐条修正，不禁用原 `console/_citations.py` 校验。
- 必须运行 B4b + B4/B3c/B3b/B3a/B2/B1/P2.2/C4 的真实严格回归、冻结 E0 等价测试，并为本次最新 HEAD 取得完整四组 Windows CI `console/frontend/experiments/root/verification` 及全部辅助 Job 9/9 完整成功。
- **完成专项不等于全部完成。** 全量通过后再将 PR #23 暂用的 `ci-validation` base 恢复为 `p2-4b-b4-auto-planned-nest-red-v1`，API 回读；始终 Draft/open/unmerged。

## 明确未完成

此阶段没有解决实时风场变化重新规划、自动闭站后恢复/撤销任务、没有第三方实物交接的已取货货物回收，也没有对物理降落或真实机巢硬件做实测校准。
