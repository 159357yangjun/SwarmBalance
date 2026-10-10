# P2.4b-B1 — 单一只读能耗报价函数：验证记录

> 实施边界：**只统一下一步理论能耗计算的公式来源**。不引入自动救援、不规划全程路径/返航、无机巢可达性保证，不切换 assigned 默认口径。本阶段不是飞行实测校准。

## 1. 依据与冻结版本

- P2.4a 设计基线：`7ca10647201432062fbfd366fccba48027dbdd24`；设计契约仍保留未来 A03-A16 需真实 RED 的约定。
- P2.2 生产安全基线：`97200d2786a5fc775a8e6ea4ca5f95f90b5bcefb`，全量 `console/frontend/experiments/root` CI [#38037310389](https://github.com/159357yangjun/SwarmBalance/actions/runs/38037310389) `completed/success`。
- 原 `Drone.consume_battery()` 与 `Drone._flight_step_feasible()` 内部各自计算：
  `distance * battery_consumption_base * (1 + charge_load/carrying_capacity * battery_load_penalty_factor) * _wind_factor(wind_along)`。
  公式在老版本暂时一致，但任何一侧未来改动都有漂移风险。

## 2. 严格 RED → 最小 GREEN

| 证据 | Git SHA / Actions | 真实结论 |
|---|---|---|
| RED（新增测试，旧双公式代码） | `3f0abafde7209e3cd9d6400f80d8f832cceb770e`，[#38041121887](https://github.com/159357yangjun/SwarmBalance/actions/runs/38041121887) | `Ran 31 tests`，1 失败 + 21 错误：缺报价接口，真实 gate/debit 没有共用该接口；任务 **failure** |
| 最小代码变更 | `adc074a51e1e4f0340ed0404f88593d30c3c842f` | 新增 `Drone.quote_flight_energy_wh(distance, wind_along=None)`，`consume_battery` 和 `_flight_step_feasible` 均调用它 |
| GREEN（同一严格测试 + P2.2） | `adc074a51e1e4f0340ed0404f88593d30c3c842f`，[#38041228430](https://github.com/159357yangjun/SwarmBalance/actions/runs/38041228430) | `Ran 31 tests ... OK` + `Ran 30 tests ... OK`，61/61 成功 |

不删、不跳过、不弱化断言。严格测试中给同一机体的 `quote_flight_energy_wh` 注入返回 `0.7Wh` 的确定性报价，真实 gate 与 debit 都必须各调用一次且账本记入 `0.7Wh`；故测试同时能阻挡未来有人恢复为两套计算的回归。

## 3. 预期行为完全保持

- 只读报价：不调用 `consume_battery()`，不写 `current_battery`、位置、航点、任务、账本或 `is_free`。
- 能耗公式及数值运算顺序不变：`base_consumption × (1 + load_factor) × _wind_factor`。仍使用原有实数输入、载荷范围和电池非负检查。
- 默认 `SWARM_BALANCE_ENERGY_ACCOUNTING` 未设时 `assigned`；显式 `onboard` 时才读 `onboard_load_kg`。
- `consume_battery` **直接调用**时仍允许短缺且只扣可用电，`required = debited + shortfall`。P2.2 真正飞行路径仍先调用安全门，拒绝整步的欠电运动，不形成假服务事件。
- 风沿航线方向计算方法及 E1 系数/开关完全不变；未明确启用 E1 仍按中性倍率。
- 机型参数、Greedy/PSO 调度、仿真配置、历史冻结 E0/E1 数据均未修改。

## 4. 跨阶段测试契约与全量 CI

- P2.4a 的四文件设计范围门禁现在固定在不可变设计 HEAD `7ca10647201432062fbfd366fccba48027dbdd24` 上，仍严查四文件；不能拿 B1 合法变更误判历史设计越界。
- B1 单独增加精确变更清单：能耗实现、严格测试、专项 CI、本证据文档、以及继承阶段门禁的适配文件。未允许修改 Greedy、PSO、系统配置、冻结实测/仿真输入。
- 由于仓库主 `ci.yml` 只在 PR 目标为 `master` 或 `ci-validation` 时运行，PR #15 **临时**改为 `ci-validation` 触发最新 HEAD 的完整矩阵；在确认 `console/frontend/experiments/root` 及所有必需 jobs 真正成功后恢复基准 `p2-4a-recovery-state-contract-v1` 并 API 回读。不得合并。

## 5. 尚未满足的结论与后续门

P2.4b-B1 只是实现 **A13 单步理论 Wh 的单源计算**；仅有这一接口，不能把当前最近机巢选择称为“可安全抵达”，也不能声称已解决已取货订单外部回收。P2.4b-B2 应使用此接口配合实际规划线路、任务重量与风险储备做可达机巢判断，先取得真正 RED 再修复。

本次提交请求四组全量 CI；只有全量工作流自身到达 `completed/success` 才能宣布该 HEAD 全量验收通过。保留 Draft、未合并。
