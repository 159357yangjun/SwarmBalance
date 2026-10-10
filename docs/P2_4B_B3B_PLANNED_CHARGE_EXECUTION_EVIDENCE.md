# P2.4b-B3b — 人工换电规划航点真实执行（显式实验模式）

**范围：** 仅 `Environment.request_drone_charge` 中的人工换电请求；**默认关闭**，需显式设置 `SWARM_BALANCE_PLANNED_STATION_ROUTE=1`。无自动低电返航、非飞行安全认证，不改变机巢选址和其他任务调度决策。

## 真实红转绿

- 父 B3a HEAD：`b10b49e5e69a2d2b9986e20bf8b8b853460ec4f0`，已实现只读 `Environment.quote_planned_station_energy_wh`，B3a 专项 135/135 通过，但其全量 CI 须独立核对。
- **RED**：[Actions #38046366088](https://github.com/159357yangjun/SwarmBalance/actions/runs/38046366088)，HEAD `f8b5e2fbc77c81b5e8bcff5418a4fd74c28098b7`，执行 37 条、4 失败：未使用 A* 航点；明知能耗不足不拒绝；A* fallback 无解不拒绝；真实扣电 6.0 Wh 与 A* 报价 6.408260... Wh 不同。历史默认人工换电对照通过。
- **最小修复**：`c847241d961bfb25505d468b4fcbcfde114ae03e`。仅当实验开关明确为 `1` 时，人工换电使用原 `RoutePlanner` 和单源 Wh 报价，提前拒绝无可行路径/不够电；成功后将全部规划点以 `(x,y,"waypoint")` 形式交给 `Drone.update()`，挂起原任务线路；在站点原位时不要求为了换电再执行航段。默认关闭仍维持旧直连路线。
- **GREEN**：[Actions #38046471635](https://github.com/159357yangjun/SwarmBalance/actions/runs/38046471635)，相同测试 37/37 `OK`。真实 `Environment.step()` 航段消耗和位移总量与规划路径报价一致，无虚构 `source/dest` 服务，保留原 `executing_task_id` 和 `_suspended_route`。
- 不跳过/xfail 失败测试、不削弱断言、不更改 E0/E1 冻结实验与 `SWARM_BALANCE_ENERGY_ACCOUNTING` 的 `assigned` 默认值。

## 未解决的现实边界

1. 障碍场景在隔离的 Shapely 几何上用真实 A* 与真实执行器运行；B3a 的另一个专项已使用实际杨浦 OSM 加载进行只读报价。这两者**不能合并宣称**已在真实地图完整调度中连续飞行验证全部路线。
2. 本阶段只修改**人工**换电；自动低电转向、机巢关闭后的改道、时变风与重规划、泊位关闭竞争、外部故障货物回收尚未完成。
3. 计划报价发生于请求时刻。飞行途中若气流变化使下一步不足，P2.2 安全门仍停止运动；并不提供完整重新规划或迫降。
4. 5% 电池保留量来自 B3a/B2 的仿真假设，不是型号实测或厂商强制安全参数。
5. 调用 `request_drone_charge` 的默认模式仍可按旧逻辑直线飞向机巢，具有已知风险；本轮为隔离实验，没有未经批准改变生产默认值。
6. 当用户手动指定**非最近**机巢时，当前 `Drone.update` 的到站逻辑仍使用几何最近机巢判断换电。B3b 尚未将全机巢身份转移与动态关闭处置完整建模，不应宣称此情景已经安全修复。

## 下游验证门

- 保留 RED 和 GREEN 两次 GitHub Actions、确切 SHA、逐测试结果。
- 继承 B1、B2、B3a、P2.2、C4、E0 守恒与历史强制文件范围门禁。
- B3a 的白名单验证冻结在不可变 HEAD `b10b49e`，B3b 自己新增精确白名单，禁止改变 Greedy、PSO、基准数据及默认配置。
- 此外必须取得自身最新 HEAD 的完整四组 `root/frontend/experiments/console` CI 与 `verification` 真实终态成功，才能恢复 PR #18 的正确目标分支。所有 PR 保持 Draft，禁止合并。
