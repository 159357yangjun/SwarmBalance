# P2.4b-B4c — 飞行中风场变化的剩余机巢路线能耗门

> **独立实验**：只有同时开启 `SWARM_BALANCE_AUTO_PLANNED_STATION=1` 与 `SWARM_BALANCE_AUTO_WIND_BUDGET_GATE=1` 才启用；默认旧调度、冻结 E0/E1 和 assigned 能耗口径均保留。假设的 5% 电池安全余量未经厂家/公开飞行日志校准，不代表真实航空安全标准。

## 目标与真正的风险

B4 能在任务低电时评估 A* 机巢路径并安排执行，但报价只发生在起飞/改道时刻。飞行途中逆风可能突然增强。原 P2.2 确保**下一秒运动**不会欠电，却不能证明剩余完整路线的能耗还付得起。这是“下一步可飞”和“全程仍可行”的严格区别。

## 实际 GitHub RED → GREEN

- B4b 父 HEAD：`8c382fbf3b5fb7991f52dc21ab764a3dcc3f365b`。B4b 专项 [#38063832465](https://github.com/159357yangjun/SwarmBalance/actions/runs/38063832465) 342/342 PASS；其全量 CI 需独立核验。
- **RED**：[Actions #38064211657](https://github.com/159357yangjun/SwarmBalance/actions/runs/38064211657) `completed/failure`：54 个测试，1 FAIL。真实 `Environment.step()` 在改道后遇到突发 `wind_u=-12`（模拟极端逆风），尽管规划路径剩余总理论 Wh+余量已超过当前电量，P2.2 仍允许单步移动 20 m，扣电 3.6 Wh。另一条风能耗关闭对照 PASS。
- **最小实现**：Commit `40e61cacb2d4651ddefcf0dac04511f4ea462e5c`，`Drone._quote_remaining_waypoints_wh()` 逐航点使用已有 `quote_flight_energy_wh()` 和方向风分量，重新合计当前实际剩余 `scheduled_position` 航路的理论 Wh；如果 `remaining_wh + 0.05 * battery_capacity > current_battery`，在下一步运动前设置 `flight_energy_blocked` 与原因 `remaining_planned_route_unaffordable`，**保留机体位置、电量、原航线、货物与订单状态**，不更换机巢、不凭空补能。
- **夹具错误/真实中间红灯**：[Actions #38064392097](https://github.com/159357yangjun/SwarmBalance/actions/runs/38064392097) 的 55 条测试中出现 1 ERROR：隔离小型 `Environment` 没创建 `total_swap_sessions`，尾部“未有虚假换电”检查因此 AttributeError；所有其他业务断言已通过。仅在夹具中显式初始化计数器为 0，保留结束后为 0 的严格断言，未修改生产逻辑。
- **GREEN**：[Actions #38064507880](https://github.com/159357yangjun/SwarmBalance/actions/runs/38064507880) 55/55 PASS，含突发逆风的全程剩余预算停飞、风能耗关闭时正常运动、预算门显式关闭时旧单步行为对照。当前实现只针对已挂起原任务、尚未到站且全部是 `waypoint` 的自动 A* 机巢航段。实际路线没在中途被重新规划，该报价是**对现有航点**做即时账面估算。

## 限制与后续验证

1. P2.2 的单步安全门仍然保留，不以 B4c 取代；B4c 无法预测未来风场变化，也没有实现天气规避、自主重新规划、紧急降落或外部救援。
2. 仅检查已选规划航点的剩余能量，没有重新计算新的障碍/空域合法性；如果环境几何也变动，必须另外设计路径再验证。
3. 若风恢复后重新变得可负担，现有代码可在后续更新时重新尝试报价并依据 P2.2 判据移动，但**尚未实测完整动态恢复轨迹**，不得宣称智能自救。
4. 一如既往保留 `assigned` 默认口径、E0/E1 固定样本及其真实对照，所有安全判断依赖当前代码的理论能源模型，不代表厂家实测余量。
5. B4b 历史精确文件范围测试固定在不可变 `8c382fbf3b5fb7991f52dc21ab764a3dcc3f365b`，新增 B4c **五文件**严格白名单（workflow、证据文档、`frontend/drone.py`、范围测试、B4c 真实测试）；不得放宽前期断言。
6. 还需继承 B4b/B4/B3c/B3b/B3a/B2/B1/P2.2/C4 测试、E0 重放与全部四组 Windows CI + verification 的最新 SHA 终态。阶段全部验证前保持 Draft、未合并；不触发默认生产启用。

## 全量验收请求

- [增强专项 #38064707093](https://github.com/159357yangjun/SwarmBalance/actions/runs/38064707093) 对完整源 HEAD `a635d21b93a7008259297c2e6ffa6e60a631a191` **completed/success**：55/55 B4c+P1、332/332 B4b/B4/B3c/B3b/B3a/B2/B1/P2.2/C4 及全部 17 项精确 Git 历史范围断言、11/11 冻结 E0，共 **398/398 PASS**。
- 本次提交触发带 **[full-suite]** 的 Windows 四组 CI；为匹配仓库 PR 触发过滤，PR #22 目标分支临时改为 `ci-validation`。全部 `console/frontend/root/experiments/verification` 加其他辅助 Job 必须在本次**新 HEAD** 上完成且 `conclusion=success` 才可宣布全量验收。
- 仅在同一 HEAD 全量 9/9 成功后，恢复 PR #22 base 为 `p2-4b-b4b-auto-station-identity-v1` 并回读 Draft/head/未合并。B4b 父 PR #21 的全量 CI 独立验收，不能以 B4c 成功取代。
- 未修改生产默认风场开关、E0/E1、调度器和物理公式，仍不代表真实飞行认证。
