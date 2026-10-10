# P2.4b-B4c — 显式恢复前重新规划与当前风场报价（实验模式）

**阶段边界**：针对自动低电改道已经因目标机巢关闭而进入 `charge_target_hold_reason` 的无人机，提供**显式**恢复操作。需同时开启 `SWARM_BALANCE_HELD_ROUTE_REQUOTE=1`、`SWARM_BALANCE_AUTO_PLANNED_STATION=1` 和 `SWARM_BALANCE_CHARGE_TARGET_IDENTITY=1`。三个开关默认均未启用；不修改 Greedy/PSO、`assigned`、冻结 E0/E1 或默认工作流。

## 真正的 RED / GREEN 证据

- B4b 父分支冻结 HEAD `69ea639f12a89141adc881ae614e511a72ede7d4`；B4b 全量工作流 [#38065340479](https://github.com/159357yangjun/SwarmBalance/actions/runs/38065340479) 在本阶段切出时**尚未到达 9/9 终态**。B4c 测试通过不能替代父阶段验收。
- **RED**：[Actions #38066028083](https://github.com/159357yangjun/SwarmBalance/actions/runs/38066028083)，72 个测试中四个 B4c `ERROR`，均因为真实 `Environment` 不存在 `resume_held_charge_route` 接口；旧有继承测试无失败。
- **GREEN**：[Actions #38066144677](https://github.com/159357yangjun/SwarmBalance/actions/runs/38066144677) `completed/success`，72/72 通过，包含四项新的可执行约束：B 机巢重新开放后不自动起飞、显式恢复重新报价且不提前扣电；仍关闭必须拒绝；新逆风导致能耗报价不可支付必须拒绝且原任务及电量守恒；实验开关关闭必须拒绝。
- 最小实现：`Environment.resume_held_charge_route(drone_id)` 首先确认实验开关、运行状态、挂起订单和合法目标机巢，然后调用已存在的 `quote_planned_station_energy_wh`。这使用无人机**当前位置**、真实 `RoutePlanner` 和 B1 理论 Wh，拒绝 A* fallback、不可行线路与没有保留量的线路；所有失败发生在改写航线之前。
- 只有核验成功才用 `(x,y,"waypoint")` 取代旧充电航线，清除 `charge_target_hold_reason`，保留原 `_suspended_route`、`executing_task_id` 和货物责任；不凭空移动、扣电、换电或交付。后续正常 `Environment.step` 才执行移动。

## 工程范围和未验证事项

- 测试使用真实 `Drone.update()` / `Environment.step()` / A* 报价、合成几何路径与固定场景系数，测试中临时注入逆风。不等于真实机型风功率校准。
- 这是**显式恢复受阻航线**，不是自动监测飞行中时变风并在每一步实时重规划；也没有允许关闭最后一个机巢或自动救援。
- 仍未实现重新选择另一个机巢、任务中的物理货物交接、外部救援、对起降硬件的真实性测量。
- 用户可观察的风场变化在测试中通过 `d.set_wind()` 明确注入，只有下一次重新报价才用当前风场。正常运行的风更新调度不由本阶段承诺。
- 原 B4b 严格文件范围检查固定在不可变父 HEAD；当前 B4c 独立检查新增六文件严格白名单，引用登记表仅修复因加入新接口造成的代码行号漂移，没有放宽 `console/_citations.py`。
- 只有最新 B4c HEAD 的专项、继承 B4b/B4/B3c/B3b/B3a/B2/B1/P2.2/C4、冻结 E0 及完整 Windows CI 的 `console/frontend/root/experiments/verification` 和所有辅助 Job 全部真正 `completed/success` 后，才能完成阶段验收。所有 PR 保持 Draft/unmerged；B4b 必须自行完整成功后才可对其收尾。
