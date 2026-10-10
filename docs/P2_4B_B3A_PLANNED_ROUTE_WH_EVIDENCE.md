# P2.4b-B3a — 真实 RoutePlanner 的机巢路径能耗只读报价

**阶段性质：** 只读、实验验证、独立 Draft PR。没有把此接口接入真实派单、改道、换电或任务恢复行为。

## 冻结基线和真实 RED/GREEN

- 父 B2 HEAD：`1601a36e7fb560b7126d13133d820a7bb4c60fe6`，仍以 `SWARM_BALANCE_STATION_ENERGY_GATE=1` 显式启用直线必要筛选；默认关闭。
- **RED**：[Actions #38045696021](https://github.com/159357yangjun/SwarmBalance/actions/runs/38045696021)。运行 28 个测试，其中 4 个新测试因为 `Environment.quote_planned_station_energy_wh` 不存在而 ERROR；已存在的 P1 能耗账本案例没有失败。RED 对应 HEAD `92b05145a176bda2095ede62f6c63052758e91f8`。
- **最小修复**：Commit `c0428575d3b668254b726b6fe06320810ff2762f`，在 `Environment` 增加只读 `quote_planned_station_energy_wh(drone, station, reserve_fraction=0.05)`。对已有 `RoutePlanner.plan(RouteRequest(...))` 的每一个实际规划航段调用 B1 `Drone.quote_flight_energy_wh`，并用每段真实方向 `_wind_along_for` 处理风；不再以单一直线距离代替 A* 绕行总耗电。
- **GREEN**：[Actions #38045796774](https://github.com/159357yangjun/SwarmBalance/actions/runs/38045796774)，28/28 PASS。新测试覆盖 Shapely 多边形阻挡、A* 绕障耗电大于直线、直线足够但绕行能耗不足、完全无可行路径时 A* fallback 必须拒绝，以及真实 `frontend/data/map/part_of_yangpu.osm` 加载后的局部通路报价。
- 绝不把 `RouteResult.fallback=True, feasible=False` 的“告警后直线兜底”误称为障碍合法航路。若 A* 末点在目标 1 米终止误差内但并未实际到站，只在末段确认清晰无障碍时追加准确机巢坐标，否则返回不可行。
- 电量检查暂采用 `required_wh + 0.05*battery_capacity <= current_battery`。**5% 是人工实验假设，不是厂商要求或实测安全余量**。

## 边界与下一阶段

1. 此时还**没有**向 `Drone.scheduled_position` 注入 A* 航点，更没有证明真实无人机始终执行规划航路；本阶段输出只是审计报价与候选路径列表。
2. 仅有单程到机巢报价，不等同完整任务航段＋返程储备、实时风场重规划、停机恢复状态机或物理迫降认证。遇临时关闭或不可达站仍应 fail-closed，不能自动补能。
3. 只读接口不改变 `drone.current_battery`、位置、任务/货物与当前路线；仅调用已存在的规划器及其几何缓存。正式仿真 `assigned` 默认，`onboard` 仅显式 opt-in。
4. 保留原 E0/E1 基线与全部 P1/P2 历史对照 SHA。此阶段不修改已有 Greedy/PSO、机巢调度或原始数据。
5. 下一阶段须分别新增真实 RED：路由安排时使用规划航点而非直接飞目标；机巢中途关闭后不可完成虚假到站；风场变化导致电量不足应停止而非跳点；多任务货物继续保持实物保管状态。
6. B3a 的完全验收仍要求继承 P2.4a/B1/B2 严格 Git 文件范围门禁及 B1/P2.2/C4 的原测试；全量四组 CI 必须真实 `completed/success`，不能以本轮 28 测试替代。

所有 PR 保持 Draft、未合并。
