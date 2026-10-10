# P2.4b-B4b — 自动低电 A* 改道目标机巢身份与泊位守恒

> 实验门：仅 `SWARM_BALANCE_AUTO_PLANNED_STATION=1` 且 `SWARM_BALANCE_CHARGE_TARGET_IDENTITY=1` 时，将 B3c 已经真实验证的目标身份/地理到站/泊位授予门延伸到 **B4 自动任务**。默认模式、冻结 E0/E1、assigned 计费口径、Greedy/PSO 都未改变。

## 基线、真实红灯和绿灯

- 父 B4 不变 HEAD：`e669075e120d3e646ec7f0623346608736f26966`，完整 [CI #38051651605](https://github.com/159357yangjun/SwarmBalance/actions/runs/38051651605) 9/9 Job 成功。父 B4 能按真实 A* 路径执行自动低电改道，但 `Drone.update` 到站时仍使用 `find_nearest_station`，且 `_manage_berths` 的身份/距离校验只施加在人工换电。
- **真实 RED**：提交 `c17a5cf3509dd0fb54f019be25ec00e067de8817`，工作流 [#38063153100](https://github.com/159357yangjun/SwarmBalance/actions/runs/38063153100) `completed/failure`，60 条测试中 4 FAIL：自动规划选择目标 A，但两个机巢同坐标、旧最近搜索会误选排列在前的 Z；当目标 A 满泊位而 Z 开放时错误地在 Z 换电；伪造自动无人机远离机巢的等待状态得到泊位；同坐标时伪造错误站 ID 也得到泊位。中途目标关闭测试和身份门关闭的旧逻辑对照成功。
- **最小 GREEN**：实现提交 `ed7f5c68c1a4a94ea763750007a4fe67c1379436`，[#38063625984](https://github.com/159357yangjun/SwarmBalance/actions/runs/38063625984) `completed/success`，同一 60/60 测试全部通过；新 B4b 六条场景测试均 PASS。生产实现只改变三个 if 分支：实际到站时按预先选定的 ID 确认站点，在泊位注册和授予时对自动任务也应用 B3c 原有的 ID、坐标、开放状态验证。
- 目标 A 和 Z 同坐标是**隔离身份歧义夹具**，用于证明算法不应仅凭位置推断站点身份；不代表真实地图中两个站必须共址。可复现的目标 ID 与站点泊位计数守恒是测试结论，不能据此宣称拥有真实落地硬件的身份认证。
- 自动低电目标 A 中途关闭，保留原配送任务/飞行账本和剩余航点，停止未经重新规划的改道；当前依赖显式身份实验门，不会自动完成外部故障救援。

## 遗留风险与验收范围

1. 目前未实现自动改道时的新风场超额能耗完整重规划，也没有失效目标站的安全备选策略；门禁会保持停飞而非凭空到站。
2. 物理机型功率、真实风场、不确定性、楼宇动态障碍均未实测校准。A* 的静态路径证明不代表空域许可或实际飞行安全。
3. 已经取货的货物仍应严格区分故障机持有与外部交接，不允许从源头凭空重生；这不属于 B4b 当前完成范围。
4. 冻结 B4 父 HEAD 之前 P2.4a/B1/B2/B3a/B3b/B3c 的历史文件范围测试不改变；B4b 新增当前 HEAD 的**七文件精确集合断言**。本轮 `frontend/environment.py` 只发生两处条件插行，但由此导致源登记表 9 处引用锚点漂移，仅更新登记表，不改校验脚本。
5. 专项 60/60 成功不等于全量通过。必须跑继承 P2.2/C4/B1/B2/B3a/B3b/B3c/B4、冻结 E0 对照，并取得最新 HEAD 上 `console/frontend/root/experiments/verification` 及其余 Jobs **全部 completed/success**；只有全部通过才能恢复 PR 的原 base。

全部代码位于独立 Draft PR，不合并；仅显式实验开关生效，E0/E1 归档始终不变。

## 全量 CI 请求与继承验收

- [增强专项 #38063832465](https://github.com/159357yangjun/SwarmBalance/actions/runs/38063832465) exact HEAD `3bd28814463bdc8f23244772d03eaa7f2f2f3617` **completed/success**：B4b 60/60、B4/B3c/B3b/B3a/B2/B1/P2.2/C4 与第 16 项变更范围断言 271/271、冻结 E0 11/11，共 **342/342 PASS**；旧 B4 历史文件清单精确不变。
- 为发起全部 Windows 回归，PR #21 base 暂时调为 `ci-validation`，仅用于 `.github/workflows/ci.yml` PR 触发。此文档提交请求 **[full-suite]** 四组 + P1 校验、文档引用、浅克隆等完整 CI。
- 本次文档与登记表行号修复分别属于 B4b 精确七文件白名单；未降低源码锚点验证器、C4 扫描或测试断言。
- 必须检查**最新 HEAD** 的 `Full suite / console`、`frontend`、`experiments`、`root`、`verification` 和其余所有 Job 本身达到 `completed/success`，不得将中间 specialty 绿灯替代最终验收。只有全套通过后，恢复 PR #21 base 为 `p2-4b-b4-auto-planned-nest-red-v1` 并 API 回读；保持 Draft、未合并。
