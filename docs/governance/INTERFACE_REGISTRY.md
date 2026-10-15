# 跨模块接口登记簿

状态：DRAFT REGISTRY；尚无 V1 冻结条目。源代码和 Draft PR 仅代表提案，不得当作已批准接口。

| Contract | 主责 | 会签 | 最小协商项 | 状态 |
|---|---|---|---|---|
| Project/World/Scenario/WorldState | ARCH-01 | ARCH-02/03 | stable ID、revision、静态/可变、CRS/单位 | PROPOSED |
| Harness/Run/StateStore | ARCH-02 | ARCH-01/03 | 生命周期、单一状态提交、快照、event barrier、RNG | PROPOSED |
| Data/Spatial/Dynamics/Event/Scheduler/Metric | ARCH-03 | ARCH-01/02/04 | 输入输出语义、版本、能力、依赖、单位、时钟 | PROPOSED |
| Legacy Adapter | ARCH-04 | ARCH-02/03 | old/new 语义映射、单例隔离、回退、基线 | PROPOSED |
| Experiment Definition/Runner/Record | EXP-01 | ARCH-02/03/VVE-01 | 控制变量、重复、seed plan、比较资格、失败 | NOT DESIGNED |
| Validation Record/Evidence Bundle | VVE-01 | EXP-01/ARCH-03 | 模型假设、验证数据、UQ、声明范围、溯源 | NOT DESIGNED |

## 接口冻结必要字段
Contract ID/version；owner/reviewers；schema 和示例；输入输出与失败语义；时间/单位/坐标；不可变/可变归属；幂等/顺序；能力/兼容规则；负例；调用方清单；迁移策略；对应 ADR 和完整 PR HEAD SHA。

禁止：独立实现方把自创接口当 V1；默许两个组件同时写 WorldState；把真实数据来源等同 Validation PASS；仅凭接口签名判断模型可安全替换。