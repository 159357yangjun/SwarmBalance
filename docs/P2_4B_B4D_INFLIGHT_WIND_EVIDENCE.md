# P2.4b-B4d — 飞行途中风场变化与剩余机巢路径电量门禁

> **实验特性，不是生产默认或航空适航证明。** 只有显式同时设置 `SWARM_BALANCE_INFLIGHT_WIND_REQUOTE=1`、`SWARM_BALANCE_AUTO_PLANNED_STATION=1`、`SWARM_BALANCE_CHARGE_TARGET_IDENTITY=1` 才执行。保留冻结 E0/E1 与默认 `assigned` 能耗口径。

## 冻结父版本与真实 RED/GREEN

- B4c 父 HEAD `42cf220143caff5fe12e91c0731279ed4486272e`。创建 B4d 时父 [full-suite #38066538628](https://github.com/159357yangjun/SwarmBalance/actions/runs/38066538628) 尚未完整终态；需独立确认父全量通过，不得将子专项代替父验收。
- **RED**：[Actions #38067608381](https://github.com/159357yangjun/SwarmBalance/actions/runs/38067608381)，80 tests，1 FAIL+1 ERROR：真实 `Environment.step` 在风场突变后仍让无人机从 20m 到 40m，电池 10.8→9.6 Wh，尽管剩余到机巢航线加储备可能不够；没有保留新的停飞原因。另外两条轻风与默认关闭对照通过。
- **GREEN**：[Actions #38067751831](https://github.com/159357yangjun/SwarmBalance/actions/runs/38067751831) `completed/success`，80/80 PASS；四项测试均通过：强逆风停止、轻风继续、默认关闭同旧行为、风转弱后仍必须显式恢复。
- 仅在 `Environment.step`、真实 `Drone.update` 之前执行新实验性判据。读取 `Environment.wind_u/wind_v`，显式更新无人机的风分量；沿**当前实际排定的剩余充电航点**从真实当前位置逐段计算 `_wind_along_for`，逐段调用唯一 B1 `quote_flight_energy_wh`。不利用首段可飞偷换整条航线的可支付性。
- 若 `remaining_wh + 0.05*battery_capacity > current_battery`，设置 `charge_target_hold_reason=inflight_wind_energy_unaffordable` 与 `flight_energy_blocked`，本步直接跳过移动和扣电，不更改目标机巢身份、原订单挂起路线或货物。5% 储备是人工情景假设，不是厂商安全标准。
- 风场转弱不自动解除 HOLD；后续 B4c `resume_held_charge_route` 重新使用实际当前位置、此时环境风分量及 RoutePlanner 报价核验，才允许恢复。本阶段**没有**实现异常时自动改飞其他机巢或外部救援。

## 未证明的范围

1. 测试使用可复现的合成几何和临时 E1 风能耗系数，不是飞行日志拟合结果。**风力对速度、运动学、升阻、姿态**仍未建模，不能因此称为真实飞行安全系统。
2. 这是已在自动充电改道期间的**当前排定剩余航线**能源核验，未实现动态重新 A* 绕过新出现的障碍，也不覆盖一般业务航段的完整路线安全预算。
3. 不会自动解除因为电池耗尽、机巢闭站、货物损坏等其他问题导致的不可用状态，不会凭空增加电量。
4. 只为带原任务挂起清单、明确目标机巢和有效计划的自动充电改道提供门禁；实验开关关闭保留原样。
5. E0/E1、Greedy/PSO、`simulation.json`、`assigned` 默认能耗与 `master` 都未修改。B4c 历史范围固定在不可变父 HEAD `42cf220143caff5fe12e91c0731279ed4486272e`，B4d 当前严格六文件白名单包含引用行号修正，不禁用 `console/_citations.py`。

## 验收门

专项 80 条 GREEN 不是全部验收。还必须通过 B4c/B4b/B4/B3c/B3b/B3a/B2/B1/P2.2/C4 的独立继承回归、严格历史范围、冻结 E0 实验以及 latest HEAD 四组完整 Windows CI 与所有九个 Job。最后将临时验证 base 恢复至 `p2-4b-b4c-held-route-requote-v1` 并 API 回读 PR Draft/open/unmerged；不得自动合并。

## 扩展回归与全量 CI 请求

- 精确 HEAD `195cc651fc5fb0ac8ca132a6bdd05b08ff8e0593` 的 [Actions #38067940277](https://github.com/159357yangjun/SwarmBalance/actions/runs/38067940277) **completed/success**：本轮 B4d+继承 80/80、B4c/B4b/B4/B3c/B3b/B3a/B2/B1/P2.2/C4 与不可变阶段范围门禁 406/406、冻结 E0 风对照 11/11，**497/497 PASS**。新 `test_18_only_b4d_inflight_wind_scope_changed` 实际 PASS。
- `compare_commits` 核验 B4c 不可变父 HEAD `42cf220143caff5fe12e91c0731279ed4486272e` 到 B4d 的严格六文件集合一致，未动历史 E0/E1、调度器和默认配置。
- 本次提交请求 **[full-suite]** 九 Job Windows 完整验收，PR #25 的 base 临时指向 `ci-validation` 仅用来触发原仓库 CI 过滤器。最新提交的 `verification`、`Full suite / console`、`frontend`、`root`、`experiments`、P1 等所有 Job 必须达到真实 `completed/success` 才能恢复正确 base `p2-4b-b4c-held-route-requote-v1` 并 API 回读 Draft/open/unmerged。
- **父 B4c** 的独立 full-suite [#38066538628](https://github.com/159357yangjun/SwarmBalance/actions/runs/38066538628) 尚未完成，其接受/恢复也必须单独验收，不能用子阶段专项绿灯代替。
