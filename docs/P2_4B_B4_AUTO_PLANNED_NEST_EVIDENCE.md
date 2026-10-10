# P2.4b-B4 — 自动低电转向 A* 规划机巢的实验性能源门

> 当前只在环境变量 `SWARM_BALANCE_AUTO_PLANNED_STATION=1` **显式启用**。默认关闭、E0/E1 和 `assigned` 能耗口径不变。本阶段并不等于真实物理返航保证，尤其没有处理飞行中途闭站、时变风场或外部故障救援。

## 基线与 RED → GREEN

- B3c 父阶段冻结 HEAD：`fca9ebfeb2413d8b396f20c10c98ddd50d2fcd47`，对应原有真实机巢身份/泊位守恒。B4 独立 Draft PR，不在 B3c 的 CI 运行中修改其 HEAD。
- **RED**：[Actions #38051168420](https://github.com/159357yangjun/SwarmBalance/actions/runs/38051168420)：47 条测试，4 FAIL，默认控制用例 PASS。具体：自动低电仍排 `[(100,0)]` 的直线机巢；直线理论能耗能支付而 A* 绕行不足仍提前覆盖原任务；A* 无解 fallback 仍被当作可飞路线；真实移动耗电 6 Wh 而真实路线报价 6.408260... Wh。
- **GREEN**：[Actions #38051322550](https://github.com/159357yangjun/SwarmBalance/actions/runs/38051322550)：相同 47 条测试 `completed/success`，B4 新增 5 条均通过，覆盖 A* 规划航点、不可负担绕行拒绝、A* fallback 拒绝、真实 `Environment.step()` 距离和 Wh 守恒、默认旧逻辑对照。
- 实现采用 B3a `Environment.quote_planned_station_energy_wh()`，并在显式实验模式的 `Environment.step()` 中向 `Drone.update(station_quote_provider=...)` 注入**真实 RoutePlanner 只读报价**，不创建第二套 Wh 公式，不硬编码最近距离代表真实路程。
- 只从**开放**机巢中筛选 `feasible=True, fallback=False, affordable=True` 的候选；按 `total_wh`、`distance_m`、稳定机巢 ID 排序。若全部不可行、超出 Wh 预算，或没有实际规划提供方，则停止自动改道，保留原任务与货物、位置、电量及执行中的任务身份，不发出免费移动或交付。
- 成功时挂起旧任务航线，全部 A* 路径航点标记 `waypoint`（非 `source/dest`），交给真实执行器逐步移动与扣电。飞完才请求真实泊位；未做隐式换电。
- 正式模式仍运行原 `Drone.update()` 距离选择逻辑，不通过新增必填参数改变其签名兼容性；新增报价 provider 是可选入参。

## 验收边界与后续

1. 隔离合成的 Shapely 多边形用于真实 A* 绕行 RED/GREEN；不能宣称已测量真实风场、障碍物高度的不确定性或厂家电池极限。
2. 自动航线报价只反映**请求当时**已知机巢和风场，不能保证未来风场变化或目的机巢中途关闭后能继续安全飞行。后续应增加中途闭站和变风导致不足时的明确冻结/重新规划 RED。
3. B3c 当前目标 ID 与泊位严查主要面向显式人工换电；B4 自动改道的非最近机巢和共享坐标 ID 与到站严格绑定，仍需独立 B4b RED，不能把 `charge_target_station_id` 存在误称为该门已全部覆盖。
4. 已取货实物归属、外部接驳和补能后任务恢复未获真实性实测，不允许“自动补能成功率”中存在无成本货物传送。
5. 遵循 P2.4a～B3c 不可变历史范围检查，并给 B4 本身新增严格**六文件**白名单。新增的实验开关只来自环境变量，未改写冻结输入与 `simulation.json`。
6. 本阶段 47 条专项 GREEN **不构成全部通过**；必须继续执行继承 B3c/B3b/B3a/B2/B1/P2.2/C4、冻结 E0，以及独立四组全量 CI，且同 HEAD 的 `console/frontend/root/experiments/verification` 等 Job 全为 `completed/success`，才可恢复正确 PR base。所有 PR 保持 Draft/unmerged。
