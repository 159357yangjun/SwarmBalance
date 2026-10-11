# Research R1 — 能耗量纲、计费策略与执行账本准入审计

> 本轮是 **Verification + scenario sanity check**，不是实机 Calibration/Validation。
> 起点：实验复现来源审计 PR #36，固定 HEAD `b23a8e4362260acb6a0df330fbd8665581d0e567`，九 Job [#38132539818](https://github.com/159357yangjun/SwarmBalance/actions/runs/38132539818) 9/9 success。此 R1 阶段保持独立 Draft、禁止自动合并。

## 1. 原始问题和真实 RED

同一 `seed`、同一机型参数和路线，`SWARM_BALANCE_ENERGY_ACCOUNTING=onboard` 与默认/assigned 的能耗不同：前者使用实际上机载重，后者使用已分配载重。历史 `experiments/reproducibility.py` 的 schema v2 已有 `SWARM_BALANCE_SIM_CONFIG` 及 11 个实验开关，却**没有记录这个模式**。这意味着两批看似相同来源的结果可能拥有不同的 Wh 账本。

真实首次 Windows CI：[#38140710083](https://github.com/159357yangjun/SwarmBalance/actions/runs/38140710083)，**18 项（继承 P1 基础测试也执行），4 ERROR**，错误是缺少 `energy_accounting_policy`；1000 m、真实 `Environment.step()`、风倍率、区间内部一致性的正向对照全部通过。

最小修复：只给复现清单新增
`energy_accounting_policy = {requested, effective, fallback_to_assigned}`。
代码中的真实语义：**恰好** `onboard` ⇒ 物理载重；其他输入（含不设）⇒ `assigned`；未知值要留下 requested 和 fallback 标记，不能把实际 fallback 模糊成用户请求。保留 schema v2；不改变飞行公式或任务调度。

## 2. 三类参数的静风、满载内部量纲

数据来源：版本锁定的 `config/simulation.json`，公式 `Wh(1000m) = 1000 × battery_consumption_base(Wh/m) × (1 + battery_load_penalty_factor)`。必须由真实 `Drone.quote_flight_energy_wh()` 和实际 `consume_battery()` 对账验证。

| 情景机型 | 满载 kg | Battery Wh | 模型静风满载 Wh/km | 声明航程 km | 借航程估算的总 Wh | 证据等级 |
|---|---:|---:|---:|---:|---:|---|
| light_express | 2.4 | 380 | 38.08 | 10 | 380.8 | 未绑定具体制造商的模拟情景参数 |
| standard_cargo | 10 | 1600 | 79.80 | 20 | 1596.0 | 未绑定具体制造商的模拟情景参数 |
| heavy_cargo | 30 | 3968.8 | 248.50 | 16 | 3976.0 | 机型名称参照 DJI FlyCart 30；系数按电池和航程派生，**不是飞行日志拟合** |

满载航程/电池量级的约 1% 内一致，只表示数据表由同一场景假设构造，不是独立验证。尤其不能用 `3968.8 Wh / 16 km` 与用它反推的 `248.5 Wh/km` 相互“验证”真实模型。

## 3. 符号约定与执行账本

- 距离用 **m**；`battery_consumption_base` 单位 **Wh/m**；乘 1000 得 **Wh/km**。
- 满载与空载按 **kg** 比例计算；`assigned` 允许取货前就计入待配送载重，`onboard` 按真实已取货质量计。标准载重机型 1 km 静风：assigned(10kg)=79.8 Wh，onboard(0kg)=60.0 Wh，差 19.8 Wh。
- `wind_along` 正数为逆风，负数为顺风；只在显式启用 E1 情景时生效。标准空载机型、演示系数 `K_HEAD=0.05, K_TAIL=0.03`：1 km 静风 60.0 Wh、+6 m/s 逆风 78.0 Wh、−6 m/s 顺风 49.2 Wh。这三个数是**公式演示**，不是气象飞行测量。
- 真实 `Environment.step()` 20m、空载演示：`total_flight_distance=20m`，`total_energy_consumed=1.2Wh`，与电池扣量一致。相同变量由既有 P1、P2.4b-B1 继承测试多重验证。
- 电池短缺时不得移动、不得新增实飞里程；飞行报价 `required Wh` 与扣除 `debited Wh`、欠额 `shortfall Wh` 分列。

## 4. 能不能发表调度算法收益？

**R1 内部单位/账本通过 ≠ 数据驱动能耗模型通过。** 下一项 R2 必须验证能耗的外部来源、特定机型和飞行工况。项目早期文档曾记录旧版场景 Wh/km 异常，不能拿旧版本数值证明当前 HEAD 的误差或准确度。

进入 R3/R4 前还需：
1. 用原始可追溯飞行数据核对功率、电压×电流时间积分、里程、飞行阶段、风、载荷和起降；
2. 按整次飞行留出训练/验证样本，不把同一次飞行的连续帧同时分到训练和验证；
3. 给出每机型/各载荷与风档的误差、分布、样本量、可信区间，而不止单一均值；
4. 在相同原始订单流、地图、机队和能耗模型下，做 Greedy、GA、PSO、OR-Tools 多 seed 配对对照，记录未完成/超时/时延/Wh/换电等，不把“完成率全 1.0”称为最优。

**保护边界**：不改 `frontend/drone.py`、`frontend/environment.py`、Greedy/PSO、`config/simulation.json`、`experiments/presets/e0_baseline.yaml`、`experiments/presets/e1_wind_clash.yaml`、或冻结 E0/E1、历史结果。旧 E0 空载里程定义不相容的告警照旧保留。
