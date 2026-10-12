# P1-B：固定订单流的成对压力实验执行规约

## 范围和版本

- 独立分支：`p1-b-stress-grid-v1`，父提交为 P1 事件链修复 `7c5cc2745ae380278ef75c71271bb530e653d87e`。
- 这是一项**实验，不是生产合并决策**。不得修改 B 的默认关闭开关、无人机能耗公式、既有 E0/E1 原始数据或 PR #1/#2/#3 的 HEAD。
- 全程对照使用该实验分支上相同的真实 `Environment`、`Drone`、`Greedy`；仅显式切换 `SWARM_BALANCE_ENERGY_ACCOUNTING=assigned` 和 `onboard`。
- 使用隔离临时 `SWARM_BALANCE_SIM_CONFIG`，并在 CI artifact 内保存情景配置、配置 SHA-256、原始数据、订单流 tape SHA-256 及 Git 提交 SHA。

## P1.1：先校准压力

- 3600 模拟秒、10 架无人机、固定地图 `frontend/data/map/part_of_yangpu.osm`。
- `task_generation.realistic.interval_scale` 三档：normal=1.0，elevated=0.65，high=0.4。
- 所有情景采用相同任务上限 `total_tasks=500`，而非历史的 60（防止高压被相同配额截断）；其他配置直接继承默认文件。
- 固定种子 `51001..51010`，第一门只用真实 `TaskGenerator` 重放到达量：检查每档 10 次结果未达到 500 上限、三档平均到达量满足 normal→elevated→high 且相邻增幅至少 15%。**这只是到达压力校准，并不等于已验证调度队列/超时压力梯度**；后者必须读取后续真实 Greedy 运行产物判定。
- 若校准失败，停止正式网格，不人为填充缺失数据或降低门槛。

## P1.2：60 次仿真回合

- 对每个 `(profile, seed)`，用真实 realistic 任务生成器生成并冻结一份**外生订单序列**（包含任务 ID、生成时刻、起终点、重量、优先级、时限等）；订单生成时不模拟调度器移除任务，属于有意冻结的外生需求情景，与历史动态池业务数据分布并非完全相同。
- 两个能耗口径使用**完全一致**的冻结订单流，且分别在独立的 Python 子进程运行真实 `Environment.step()` 与 `greedy_action_from_observation()`。
- 每组保留 `pair-*.json`、`tape-*.json`、`scenario-*.json`；验证两组的生成总数、配置哈希和订单 tape 哈希完全相等。
- 每个 profile × 10 seeds × 2 modes = 60 episodes。CI 六个分片并行执行，每个分片 5 seed 配对。不存在对用户 E0/E1 文件的写操作。
- 指标：完成率（完成/生成）、已完成任务的超时率（不能当成全量需求超时率）、已完成任务平均延迟、空载率、总能耗 Wh、换电次数、未完成数和最大未派单队列。
- 汇总门：完整 30 unique `profile+seed` 配对、60 episode，输出 `all_runs.csv`、`summary.json`、`report.md`；逐 seed 对照差值、均值、标准差、min/max、程序 SHA、情景与任务 tape 指纹。

## 解释与禁区

- 历史 E0/E1 保持原样，不允许跨旧/新空载里程定义直接作绝对差值比较。
- 只校准三档到达量，不将任何一档提前称为“真实高压”；正式运行后还需检查未完成订单、队列长度与超时指标是否构成有效压力梯度。
- 绝对耗电量仍是**参数化情景模型**，不代表真实无人机的厂家实测能耗。
- 若任何一组未完成或违反合同，汇总门硬失败，不能宣称完成 60 回合。
