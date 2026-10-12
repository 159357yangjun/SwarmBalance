# P1.4 同轨迹双公式理论能耗影子计费

## 目的与范围

P1.3 已证实在相同外生订单流下，B 方案 30/30 场景模拟总实际扣电较少，但 A+C 与 B 的实际调度轨迹可分叉，因此之前“里程项/能耗强度项”仅为数学分解，不等于原载重公式的因果效果。本实验先取得**在相同航段、相同载重快照、相同风参数下**切换质量口径的理论需求 Wh 差异，严禁直接推断替换口径后的换电/订单完成效果。

## 仪器设计

- 保持真实 Environment、Greedy、Drone 在正常执行。仅在本独立实验入口对 `Drone.consume_battery` 安装**只读包装函数**，先记录同一航段的里程、当前位置状态、`current_load`、`onboard_load_kg`、机型 Wh/m、载重因子与风倍率，再调用原始能耗函数**恰好一次**。
- 每次被测飞行航段同时计算 `assigned_required_wh` 与 `onboard_required_wh`。实际 active mode 的 `last_energy_required_wh` 必须与对应公式逐段一致；逐段校验原始 C 能耗守恒 `required=debited+shortfall` 和电池扣减 `battery_before-battery_after=debited`。
- 两个 independent baseline 各自正常运行：真实 assigned 调度轨迹下附加另一种公式所需 Wh；真实 onboard 调度轨迹下再附加另一种公式所需 Wh。**影子结果绝不参与实际耗电、低电阈值、换电或调度决策。**
- 两组任务 tape 使用 P1.2 的统一外生订单流生成逻辑；对每个场景/seed/active mode，比较运行生成数、完成数、里程、空/载里程、真实扣电、换电、完成率、延迟、配置哈希和 tape 哈希，全部与已经提交的 P1.2 **60 行原始指标**逐项一致，才说明包装仪器没有改变被观察行为。
- 原始代码基线：`47c6e4582cd175151769ae8dd68383da805d3b3c`，仿真对照来源：`f0f70f553dba76b54b02acc835561af1b8c4a25a`；新运行时的工作流 HEAD SHA 单独记录。配置使用临时文件，不编辑 `config/simulation.json`，不覆盖 E0/E1。

## 实际执行与硬门

- 3 压力档 × 10 seeds × 2 条主动轨迹 = **60 次真实重放回合**；六个分片各 5 seeds × 2 modes。
- 分片输出全部航段的 `legs-*.csv.gz`（逐航段详细物理状态、两种理论 Wh、主动扣电与 shortfall）、`shadow-*.json`（每回合汇总）、对应 `scenario` 临时配置及 `tape` 指纹。
- 汇总门必须检查六个分片的唯一 60 回合、30 配对、原始对照指纹匹配、每条模式活动 Wh 守恒、逐航段公式一致。缺任何文件/唯一组合即硬失败。
- 最终报告分开列出：**同 assigned 真实轨迹上的理论公式差异**、**同 onboard 真实轨迹上的理论公式差异**、**两个真实调度轨迹之间的扣电差异**。不得直接用后者减去影子差异冒充精确的“路径因果效应”。

## 有意不做

- 不为影子模式维护第二套反事实电池余额与换电状态；因此影子 `required Wh` 不是“切换模型后实际能扣的 Wh”。
- 不把 B 的默认开关打开，不编辑 `frontend/drone.py`、`frontend/environment.py`，不合并 PR #1～#5，不使用新的外部飞行日志做物理校准。
- GitHub artifact 保留 30 天，重要汇总须另存长期位置后才可以作为长期基线。
