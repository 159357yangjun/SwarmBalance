# L0 核心逻辑闭环——只读审计与真实反例

> 2026-10-12 · 审计阶段：L0（**不修改生产行为**）。依据既有 `docs/仿真软件设计规范.md`、`docs/端到端一致性门设计.md` 和 [方法/路线说明 PR #39](https://github.com/159357yangjun/SwarmBalance/pull/39)。  
> 取证代码锚点：`b23a8e4362260acb6a0df330fbd8665581d0e567`（研究审计 PR #36）；审计工具仅解释此版本，不代表各 Draft 分支已经合并到 `master`。  
> **证据级别**：A=源码已直接证实；B=实际执行轨迹与负面对照证实；C=既有审计/历史观察；D=待测试假设。不可将 D 写成 A/B。

## 一、研究问题与审计范围

目标不是让代码“变绿”，也不是重跑 R2 飞行数据；而是先检查：
1. 一个订单从创建、分配、取货、送达、故障释放，是否始终有唯一权威状态与所有者？
2. `Drone.current_load`（已承诺容量）与 `onboard_load_kg`（真实机载量）能否按任务身份守恒？
3. 每段实际飞行的电量扣减及换电事件能否重算？
4. `Environment.step` 对非法调度、航线中断以及设备故障是否有可验证的去向？
5. `get_statistics` 是否按真实执行事实和正确分母描述配送表现？

L0 不决定新状态枚举、不改历史 `timeout_rate` 定义、不修改 `Environment`/`Drone`/`Task`。所有修复必须在 L1/L2 单独 RED→GREEN。

## 二、状态写入点/读取点审计

| 事实 | 生产写入证据 | 主要消费端 | 目前缺失的独立证人 |
| --- | --- | --- | --- |
| `Task.status` | `frontend/task.py:83,118-124`（默认 pending、无前态守卫的 update_status）；`environment.py:1308`（分配时写 assigned）；`:621,2546`（部分释放写 pending） | 任务对象自身及待分配任务源；当前 `_record_task_completion` 未同步写 completed | 可独立枚举的终态、完整任务注册表及身份审计 |
| `drone_assignments` | `environment.py:1277-1300`、`:2069-2073` 追加；`:1459-1486` 服务/cleanup 移除；`:611`、`:2548` 故障/交接回收 | `step`、`_obs`、机队紧迫度、既有 observer | 分配版本号、货物所有者和每次释放原因 |
| `total_completed_tasks`、`completed_tasks` | `environment.py:422-481` 的 `_record_task_completion` 增计数和记录；`:1447,1461` 送达分支调用；`:1480,1485` **空闲兜底调用** | `get_statistics`、奖励、UI 观察者、实验输出 | 不依赖此同一函数/计数器的独立 `DELIVERY_COMPLETED(task_id)` 身份事件 |
| `Drone.current_load` / `onboard_load_kg` | `drone.py:83,87,338-343`；`environment.py:1435,1449-1469,548-549,629-630,2549` | `quote_flight_energy_wh`、任务容量判断、服务处理 | 按 `task_id` 核对每笔货物保管与实际载重质量 |
| `Drone.current_battery` | `drone.py:101` 初始化；`:235` 消耗；`:317,370` 换电/重置；`_flight_step_feasible` 预检查 | `Environment.step` 由前后电量差累加总能耗（`environment.py:1375-1382`） | 每次变化的独立原因码/换电事件、电池身份，跨故障对账 |
| `ChargingStation.occupied` | `charging_station.py:21,40-46` 增减占用并限制至边界 | `Environment._manage_berths`/状态和指标 | 逐换电会话ID、机巢库存与跨恢复一致性 |
| `timeout_rate` | `environment.py:1110-1130` 没有完成时置 0；`:1160` 仅完成单分母 | `metrics_schema.py:114`、实验对比 | “到期未服务/尚未到期截尾”的独立分母 |

上表为**指定核心模块的写入/消费链**，不是宣称已扫描仓库每一个文件。以后新增桥接、插件或事件接入必须补充调用方，不能把本表当全仓穷尽证明。

## 三、L0 风险矩阵（按违反业务事实的后果排序）

| ID | 等级 | 已查到的事实 | 边界与下一证据 |
| --- | --- | --- | --- |
| **L0-C1** | P0 · A | `environment.py:1475-1486`：`is_free` 转换后只要剩余 assignment 就会执行 `_record_task_completion`，没有 `dest` 证人检查。 | 代码路径真实存在；**自然订单轨迹是否可达未证明**。本 PR `scripts/l0_logic_probe.py --cleanup-red` 用有效派单后的路线丢失做故障注入；只在 GitHub CI 捕获硬断言失败后升级为 B。 |
| **L0-C2** | P0 · A | `_record_task_completion` 增加计数，但不将对应 `Task.status` 置 completed；`Task.update_status` 只检查枚举，不检查状态转移合法性。 | 没有自动成为一致状态机；L1 应先梳理所有读者，再用合法送达事件统一写入。 |
| **L0-M1** | P0 · A | `timeout_rate = 1 - on_time/completed`，且 `completed=0` 时返回 0。100 单仅准时完成 40 单，条件超时率仍为 0%，实际未完成 60%。 | 该字段本身算的是**已完成条件超时**，不能称全任务违约率。L2 必须新增“到期未服务”和“截尾”；不得直接篡改冻结字段。 |
| **L0-A1** | P1 · A | `step(actions)` 派单路径首先以载重为硬检查；完整路程/能源/状态可行性由其它模块分散处理，而不是一个统一动作准入结果。 | 不直接声称所有非法动作都可被执行；L3 要构造非法订单/故障/超载/低电真值矩阵。 |
| **L0-P1** | P1 · A | PSO fitness 用直线距离、简化换电与电池截零后继续估算；真实环境用 RoutePlanner、逐步电池门和泊位仲裁。GA/OR-Tools 代理目标也不完全相同。 | 这是模型间隙，**不必强制相同内部算法目标**；L4 必须分别留痕预测与执行结果。 |
| **L0-E1** | P1 · A | 能耗引用 `quote_flight_energy_wh`、电池通过 `consume_battery` 更新、环境按前后差统计；已有 R1 内部量纲验证。 | 需按运动/换电等事件独立重算，当前还不能仅凭同一对象写入点宣称完整账本。 |
| **L0-F1** | P1 · C | B5 安全研究证明独立组件的软件性质，但完整 `Environment` 恢复/跨 SQLite–内存原子性尚无保证。 | 这是已登记的适用边界，不在 L0 擅改为已完成能力。 |
| **L0-S1** | P2 · D | `experiments/runner.py` 使用算法间配对 seed；尚未验证外生订单流与算法内 RNG 全链路隔离。 | L5 需要对**预生成订单 ID/时间/位置**做逐单序列比对，不能只比较 seed 值。 |

## 四、真正的反例与预注册判断（避免“假 RED”）

### 4.1 真实代码路径的 cleanup 负面夹具

`scripts/l0_logic_probe.py --cleanup-red` 严格分两段：
1. `Environment.reset(seed=40907)` 后，选一架可承担实际初始任务的无人机，调用**真实** `Environment.step({idx: [task_id]})` 完成分配；核对它仍有任务、状态 assigned、尚未完成。
2. **故障注入**：清空其剩余航线/服务事件缓冲，并设 `is_free=True`、上一帧为忙（模拟外部提前撤销航线却遗留分配记录）。再次调用真实 `Environment.step({})`。
3. 预注册硬断言：在**没有本步送达事件**时，`total_completed_tasks` 不能增加。若增加，测试退出非零并包含 `[L0_CLEANUP_WITHOUT_DELIVERY]`；CI 必须检查这是真断言失败，不是安装失败/跳过/超时。
4. **重要边界**：这是一种故障注入**非受控状态**，并不能证明正常业务 API 可以自然到达同一状态；其意义是暴露防御性恢复/cleanup 的缺口。修复时不可用“测试不能自然发生”直接抹掉异常路径，应当定义合法回收策略。

若后续代码修复导致此测试变绿（退出码 0），诊断工作流的“预期当前 RED”会报错，提示需要更新阶段证据；**不得凭旧版本说新版本仍有缺陷**。

### 4.2 纯源码与统计口径哨兵

`--source` 用 AST 确认指定版本确实存在对应函数/完成写入与兜底路径，输出真实源码行号；同时计算 **100 单生成/40 单准时完成 → 条件超时率 0、未完成率 0.6** 的说明性算例。该算例不是新仿真实验、不是修复建议的实证绩效。

## 五、L1 / L2 的测试先于修复清单

- **L1-RED-1** 正常单 `pending → assigned → picked → delivered`；每步核对 Task.status、有效订单归属、货物 kg、完成事件与计数。
- **L1-RED-2** 同一机同源 2 单、异源任务链；必须按任务身份逐笔取送，不许“一条 dest 误结算另一单”。
- **L1-RED-3** 故障、取消、非法恢复、换电等待、低电无法航行、提前自由态，任一情景都不能当作合法送达。
- **L1-RED-4** 反复接收同一 order ID、同单多机抢单、送达事件重复/乱序，必须被环境拒绝且不增加完成数。
- **L1-RED-5** 货物拥有者从无人机移至合法交接方，需要事务凭证和可核对的身份日志，B5 opt-in 边界仍生效。
- **L2-RED-1** 全零完成、部分完成、全部完成、已过 SLA 尚未送达、尚未到期未完成、截止时刻恰好送达六种口径，全部有精确分母和独立事件重算。
- **L3-RED-1** 在不改算法的情况下送入非法动作；环境必须返回明确拒绝事件与原因，订单仍有去向。
- **L4-RED-1** 把 `planned_distance` / `actual_distance`、`predicted_energy_wh` / `actual_energy_wh` 绑定到相同任务 ID，支持重计划后的版本关联。

这些测试**尚未实施**，不能把表当已通过门。实现优先顺序 L1 → L2 → L3 → L4；外部 R2 标定继续暂停。

## 六、复现、验收及安全

- 冻结 `master=2ab60c69a806a22d7ba20353dee0571752a0e8e5`、E0/E1，所有改动在独立 Draft PR。
- L0 只新增：`scripts/l0_logic_probe.py`、本审计文档及专用 GitHub Workflow；源码、参数、冻结数据 0 修改。
- 两类证据分开：**静态观察** ≠ **实际运行负面对照**；负面对照只有在目标断言真正失败且失败标记匹配时才被视为有效。
- 本轮如仅 1 个专用审计 Job 成功，**不得称“九 Job 全量验收完成”**；真正的 L1 生产改动必须遵循 RED→GREEN→继承回归→精确 HEAD 9/9。
- 允许在此 PR 文档/正文更新**审计证据**，不允许顺带修复生产代码或主动合并。
- 若 CLI 工具发生环境错误，必须标为 **BLOCKED**，不能把报错当业务 RED。

## 七、关联资料

项目内部：`docs/仿真软件设计规范.md`、`docs/端到端一致性门设计.md`、`docs/世界逻辑规格书.md`、`docs/P2_4B_B5_SECURITY_AND_RESEARCH_GATES.md`、[方法综述 PR #39](https://github.com/159357yangjun/SwarmBalance/pull/39)。

外部框架：NASA-STD-7009B（Verification/Validation 与使用范围）、ODD（概念模型）、SimPy 文档（事件同刻确定顺序、资源容量）。详见 PR #39 的文献链接。

**当前裁决（代码审计）：最优先隔离并修复 L0-C1/C2，其次重新定义 L0-M1 的公开指标口径；在这些门通过前，不用仿真完成率得出“某调度算法更接近真实”的结论。**


## 八、L0 实际执行证据（完成后补录；不得混成自然轨迹）

- **首轮代码 HEAD**：`8f4220ae4e52958a3bcee548d79456fbf26005d5`。GitHub Actions [#38209357798](https://github.com/159357yangjun/SwarmBalance/actions/runs/38209357798) 实际为 **2/2 Job completed/success**，但第二个 Job 的“成功”是**正确地抓到内部真实断言失败**，绝不意味着系统已修好。
- 源码/范围门：`[L0_SCOPE_PASS]` 精确三个非生产文件；`[L0_SOURCE_AUDIT_CONFIRMED]` 给出源码行号：`assignment_status:1308`、`completion_counter:446`、`cleanup_guard:1475`、`timeout_conditional:1160`。
- **动态现场**：`[L0_REAL_KERNEL_READY] 3.10.11`；先通过真实 `Environment.step({idx:[task_id]})` 合法接单，再人为撤销剩余航线/转为空闲，保留已接受分配。真实 `Environment.step({})` 后日志：`task_id="task_4"`、`drone_idx=0`、`before_completed=0`、`after_completed=1`、`task_status="assigned"`、`real_delivery_event_in_second_step=false`。
- 硬断言在原环境真实执行后以 `AssertionError: [L0_CLEANUP_WITHOUT_DELIVERY]` 失败（CLI 退出码 1）；GitHub Job 只有在错误标记精准匹配且确认跑到故障注入现场时才打印 `[L0_TRUE_RED_CONFIRMED]`。**这是真 RED，不是缺依赖、超时、空执行或预先伪造的日志事件。**
- **证据等级**：L0-C1 从“静态确认 A”升级为“故障注入执行确认 B”。仅证明代码面对该人为破坏的中间状态**可能虚假完成**，不证明常规 UI/故障 API 会自然产生该状态。L0-C2 的完成后仍 assigned 在同一运行例中直接被观察；其正常送达情况下的全链互证仍待 L1 建门。
- L1 最先修复的不是篡改数字，而是明确**派单保留/取消/回收/送达**的统一状态转移：`is_free` **不能**作为 `DELIVERY_COMPLETED` 的充分条件。下一阶段须先写会真正失败的业务断言、修复后 GREEN，并在精确新 HEAD 完成继承回归与完整九 Job 验收。

> 注：这段记录引用首轮实际运行 SHA；补录文档会产生新的 SHA。新 HEAD 的同一测试要重新验证，不能默认沿用旧运行结果。
