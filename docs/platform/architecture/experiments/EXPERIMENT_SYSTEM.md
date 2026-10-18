# EXP-01｜实验系统一等资源（PROPOSED v0.1）

状态：设计草案；非运行代码、非实验已验证。共同基线 master@2ab60c69a806a22d7ba20353dee0571752a0e8e5。

## 使命与边界
Experiment System 对科研问题、对照设计、批次调度、统计分析与结果证据负责；Harness 仅执行一个 FrozenRunSpec 并返回 RunRecord；World/Scenario 定义对象和情境；Component Registry 装配模型；VVE-01 定义证据与现实适用性。不能让批处理逻辑写 WorldState，也不能让指标图表代替科研结论。

## 资源
- ExperimentDefinition：experiment_id、revision、question、hypothesis、world/scenario refs、treatment_factors、controlled_factors、baseline、metrics、replication_plan、exclusion_rules、analysis_plan、claim_scope。
- ExperimentPlan：锁定输入内容摘要、完整处理组组合、每组随机流配置、run_manifest 哈希、执行顺序。
- ExperimentRunner：在资源预算和并发上限内提交独立 Run，不改变单次 Harness 时钟或事务。
- RunRecord：run_id、experiment_id、treatment_id、seed_plan_ref、frozen_run_spec_hash、status、error、artifact refs、metric definition versions。
- AnalysisRecord：统计方法、样本纳入与剔除、缺失、估计值、区间、不确定性、不可比较原因。
- EvidenceBundle：由 VVE-01 定义，实验只引用可核对证据，不能直接赋予模型 Validation PASS。

## 对照设计
处理因子、受控因子和潜在混杂项分别声明。相同 seed 只有在随机流定义与消费策略一致时才能支持配对比较；更换组件可能改变 RNG 消费顺序，禁止自动断言同 seed 等于同扰动。重复次数由预注册精度/功效与预算选择，禁止固定数字冒充统计充分性。失败和中断要保留原始记录，不得只统计成功 run。对比门检查输入、指标、单位、时间窗、模型含义与删失规则；可不完全等价但必须标注差异和可解释条件。

## 运行流程
validate definition -> resolve dataset/world/scenario/model locks -> prepare immutable ExperimentPlan -> submit FrozenRunSpec to Harness -> retain run artifacts -> compare gate -> analysis -> claim review with VVE。批次失败允许部分完成但不能静默填补缺失；重试创建 attempt_id，防止同一 Run 双计。

## MVP
一个低空物流 World、两种 Scheduler、相同任务需求条件、明确种子策略、至少两次独立 Run、同一 MetricDefinition，输出 run manifest、对比门结果和未验证范围。该 MVP 仅验证实验软件链，不直接证明现实调度优越性。

## 冻结前问题
E1 ExperimentDefinition 的不可变 revision 与一次运行关系；E2 common random numbers 可用条件；E3 MetricProvider 是否只处理单次运行、跨 Run 统计由 Analysis 担当；E4 错误重试/剔除不得产生选择偏差；E5 与 legacy experiment_service 的导入/并列策略。
