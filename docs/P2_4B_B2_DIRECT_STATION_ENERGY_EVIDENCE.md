# P2.4b-B2（阶段性）直线机巢能耗必要条件 — RED/GREEN 证据

> 本阶段仅检查“已知直线航段”中是否存在**明显电量不足**的候选机巢。它是可达性的必要条件，而非充分条件。未完成 OSM 障碍、禁飞区绕行、时变风、机巢降落合法性、真实机型实测校准；**不得据此声称航线安全可飞、机巢保证可达或已实现救援。**

## 基线与真实失败证据

- 父 B1：`fd8a001b09cb85b6875426d0e30532ee6e6831ac`。沿用 B1 `Drone.quote_flight_energy_wh()`，不复制新的能耗计算公式。
- **真实 RED**：B2 测试/CI 提交 `adc54819af09a603d05aa145f0a619026654fec2`，[Actions #38044171888](https://github.com/159357yangjun/SwarmBalance/actions/runs/38044171888)，28 个发现测试中 2 个明确 FAIL：
  1. `test_B2_a03_unaffordable_all_nests_does_not_overwrite_mission`：当前 0.4 Wh、最近开放机巢距 100 m，原 `Drone.update()` 无可达性报价仍把 `source/dest` 任务航线替换成到机巢的直线。
  2. `test_B2_wind_makes_farther_station_cheaper_than_nearest`：东向 100 m 为 6 m/s 逆风、西北以外的北向 150 m 为顺风，原策略仍一律选最近机巢，忽略同公式计算出的能量。
- 其他关闭机巢处理、三步真实停止/账本和既有 P1/P2 相关测试未在这次 RED 中失败。

## 最小实现及 GREEN

- 实现 `Drone._select_energy_affordable_direct_station()`（`frontend/drone.py`）：仅对**已接任务、低于阈值时的主动换电转向**，读取开放机巢位置，基于直线距离、沿航线风分量、已有 assigned/onboard 载荷计费口径和 B1 统一只读报价计算理论所需 Wh。
- 筛掉 `required_wh + reserve_wh > current_battery` 的机巢。此轮 `reserve_wh = 0.05 * battery_capacity` 是**暂定仿真余量假设**，不是厂商/飞行日志拟合值；无人机已在机巢原位时可直接登记排队，不应被储备值否决。
- 按估计理论 Wh、距离、机巢 ID 稳定排序，不再盲选距离最短的候选；若全部不满足直线能耗必要条件，**保持原先的任务航线/货物与电量不动**，`is_free=False`，记录 `flight_energy_blocked=True` 和原因 `no_energy_affordable_station`，不生成取货/交付事件。
- **真实 GREEN**：[Actions #38044278237](https://github.com/159357yangjun/SwarmBalance/actions/runs/38044278237)，28 个测试全部成功。此阶段测试按真实 `Environment.step()` → `Drone.update()`，没有禁用原能源安全门或伪造扣电。
- 保留旧 B1 HEAD 作为不可变审计锚点：P2.4a、B1 的文件范围断言对各自历史切片仍为**严格集合相等**；B2 新增独立严格范围门禁。中文路径比较保留 `git -c core.quotePath=false`，不得借编码问题移除门禁。
- 登记表因新增辅助函数导致换电说明所在行漂移，精确校正 `frontend/drone.py:300#不再使用`，保持 `console/_citations.py` 原始检查方式。

## 明确未完成事项

1. 直线理论 Wh 合格**不代表真实 OSM/no-fly 地图存在无碰撞航路**，本阶段不能授权“保证可达”；若实际路径不是直线，必须先有真实规划路径及逐航段 Wh 报价，再作完整判断。
2. 尚未覆盖已完成交付后的自动返巢分支、手动 `Environment.request_drone_charge()`、机巢临时关闭期间的重路由；它们仍保留历史策略，需要后续独立 RED/GREEN。
3. 不解决真实零电紧急着陆、无人机故障外部救援、已取货货物回收、跨机场地面接驳。
4. 无公开实测飞行日志的能耗预测误差和机型适用范围，不能对外宣称物理安全认证。
5. B1 `assigned` 生产默认不变，`onboard` 仍必须显式启用；不覆写历史 E0/E1、P1/P2 配对数据。

## 验收策略

本 PR 的 28 条专项 GREEN 只是 B2 当前必要条件绿灯。需同时检查 B1 继承测试、C4 货物真实性扫描、P2.4a/B1/B2 分支范围门禁和真实四组全量 CI；不得将部分/取消的工作流算作 full-suite 成功。所有 PR 保持 Draft/未合并。
