# P2.4b-B3c — 目标机巢身份、真实到站与泊位分配 RED/GREEN

> **范围：仅独立实验模式**。B3c 必须显式设置 `SWARM_BALANCE_CHARGE_TARGET_IDENTITY=1`，人工规划路线还需 `SWARM_BALANCE_PLANNED_STATION_ROUTE=1`。不改变生产默认开关、冻结 E0/E1、任务调度器或航空物理模型。没有自动转场救援或真实安全认证。

## 冻结基础

- B3b 父 HEAD `25a77553c710c06cc105986f140d66ba5c5c6d`，9/9 Job 全量 CI [#38046927413](https://github.com/159357yangjun/SwarmBalance/actions/runs/38046927413) completed/success。
- B3b 人工换电可以 A* 报价并按真实航点执行，但 `Drone.update()` 到最后一个航点时还会 `find_nearest_station` 选最近开放站。这在两个机巢位置相同时使指定 B、最终登记 A 成为真实错误；泊位管理器还曾相信未经位置确认的 `awaiting_berth` 标志。

## 真实红灯，最小修复与绿灯

| 门 | 实际 GH Actions | 精确结论 |
|---|---|---|
| B3c 初始 RED | [#38050037131](https://github.com/159357yangjun/SwarmBalance/actions/runs/38050037131) | 46 条测试，2 FAIL + 1 ERROR：未保存指定目标 ID；同位置 A/B 身份混淆；目标 B 关闭时未经 A* 报价直飞 A。默认旧逻辑测试 PASS。 |
| 初始 GREEN | [#38050157968](https://github.com/159357yangjun/SwarmBalance/actions/runs/38050157968) | 同一 46 条测试全部 PASS。目标 ID 跟随人工任务，关闭 B 时停止未知替代路径而非免费飞行；B 满泊位只排队，到达后才计入。 |
| 伪造状态 RED | [#38050264948](https://github.com/159357yangjun/SwarmBalance/actions/runs/38050264948) | 48 条测试，2 FAIL：即使无人机实际还在 (0,0)，强行写 `awaiting_berth=True` 就可获得 B 泊位；把请求 B 伪装成 A 队列，即使共址也可从 A 获得换电。 |
| 伪造状态 GREEN | [#38050364627](https://github.com/159357yangjun/SwarmBalance/actions/runs/38050364627) | 48/48 PASS，真实 `Environment._manage_berths()` 注册及授予两道门都要求目标 ID、开放站、精确位置匹配，不满足则删除队列/停止换电并记 `arrival_not_verified`。 |

## 行为与资源不变量

- B3c 仅对显式 opt-in 的**人工换电**保存 `charge_target_station_id` 与 `charge_target_hold_reason`。绿灯同时验证了两个位置相同的 A、B：请求 B 最终登记 B，**不会**因 `find_nearest_station` 在同坐标中偏向 A。
- 实际到 B 后如所有泊位忙，应在 B 的 FIFO 队列等待，不占其他站泊位；有外部泊位释放事件后才开始本机换电。每次占用、最终释放各一次。注意外部泊位释放作为**测试输入事件**，不是无成本生成新资源。
- 人工目标 B 在途中关闭时，当前目标保持 B，`charge_target_hold_reason=target_station_closed`，原任务与货物责任保留，停止移动和扣电。不允许直接替换去 A 的路线，因为新路线尚未重新 A* 规划与报价。
- 任何凭空设定的泊位申请都不能直接换电：`_manage_berths` 必须先核验 `drone.get_position() == station.get_position()`（1e-6 容差）、实际指定 ID 与队列站 ID 一致、机巢开放、非错误的等待状态。这属于**仿真位置/身份一致性**，不代表真实物理着陆证明。
- 默认开关关闭时的最近站行为和历史 E0/E1 控制口径**按原样保留**。这种默认行为的已有缺陷不是本阶段宣布修复的内容。

## 重要限制与后续

1. **正常运行仍是默认关闭**。此轮已在独立实验分支产生真实行为验证，不应未经完整实验与审查直接替换主线策略。
2. 因闭站而冻结的人工换电请求需要显式重新请求、重新规划报价；尚未实现安全自动恢复、撤销请求时的完整状态回滚、已取货实物的第三方接收和任务重新派发。
3. 精确几何位置加机巢 ID 不是带签名的物理接入凭证，未模拟飞行姿态、落地协议和真实机巢硬件。
4. E0/E1、Greedy/PSO、`assigned` 默认载荷能源口径不变。实验开关未加入 `simulation.json`，不会自动开启。
5. 继承 P2.4a、B1、B2、B3a、B3b 的不可变历史范围检查，并新增 B3c 七文件精确白名单。源码变更后物理参数登记表内的十条 environment 行号锚点已逐条修复，保持 `console/_citations.py` 校验强度。
6. 本文只归档专项 RED/GREEN。B3c HEAD 的完整 `console/frontend/experiments/root/verification` CI 独立验收必须到 `completed/success`，否则不得恢复 PR 临时 CI base 或声明全量通过。

下一阶段可推进 B4 自动低电恢复与已取货货物外部处置，但必须逐状态独立 RED/GREEN，而不是继续复用最短距离作为安全返巢充分依据。

## 增强回归 GREEN 与完整 CI 验收请求

- [Actions #38050572275](https://github.com/159357yangjun/SwarmBalance/actions/runs/38050572275) at `287bb7f64a9708fc5a83651cfc7ea084cefcc4d9` **completed/success**：48/48 B3c 实体/继承用例、174/174 B3b/B3a/B2/B1/P2.2/C4 + 6 阶段精确 Git 白名单、11/11 冻结 E0 对照，共计 **233/233 通过**。
- 最早的 [RED #38050037131](https://github.com/159357yangjun/SwarmBalance/actions/runs/38050037131) 与 [RED #38050264948](https://github.com/159357yangjun/SwarmBalance/actions/runs/38050264948) 已永久保留。本次没有跳过、xfail 或缩小失败断言。
- Git 白名单固定父 B3b 的不可变 HEAD `25a77553c710c06cc105986f140d66ba5c5c6c6d`；只允许七个 B3c 文件变化：无人机、环境、专项与历史校验测试、工作流、证据文档及纯行号源登记表。
- 为触发仓库现有 `.github/workflows/ci.yml`，已临时将 Draft PR #19 base 设置为 `ci-validation`。**此提交请求 [full-suite] 完整矩阵**；`Full suite / console`、`frontend/root/experiments`、`verification` 与 P1 随附 Job 均需是本 HEAD 的真实 `completed/success`，否则不得宣称全量完成。
- 全量成功后应恢复 PR #19 base 为 `p2-4b-b3b-planned-charge-route-v1`，API 回读验证 HEAD/Draft/未合并；保持 `master`、默认模式、E0/E1 数据全不变。
