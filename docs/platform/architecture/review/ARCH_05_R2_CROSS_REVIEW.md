# ARCH-05-R2｜六方架构独立增量交叉审查（正式设计证据）

> 审查基准：2026-10-16；范围为 ARCH-01/02/03/04 + EXP-01 + VVE-01，共 6 个 Draft PR、27 份 Markdown 设计文件；辅以原 ARCH-05 PR #48 历史报告。  
> **裁决：HOLD / NO-FREEZE（禁止直接进入 ARCH-06 批准或声称代码实现）**。  
> 这是在指定 HEAD 上进行的文档级 cross-review，不是运行测试、模型现实确认、CI 或实验结论。旧设计 PR 均只读，未合并。

## 0. 来源锁定与范围

| 任务 | PR / 分支 | 固定 HEAD SHA | 文档数 |
|---|---|---|---|
| ARCH-01 World | #46 / platform/arch-01-world | b5f05a70a3306f1799fcae2c3f342f3ed9ee0048 | 5 |
| ARCH-02 Harness | #49 / platform/arch-02-harness | d155621aca66e3a80c388718093a452d17d71e10 | 6 |
| ARCH-03 Components | #47 / platform/arch-03-components | 68382c649393057ffbf5a14508ab1ff72d575b09 | 6 |
| ARCH-04 Migration | #50 / platform/arch-04-migration | c4c0c67111ead435062650c1ed776547c477e3e3 | 6 |
| EXP-01 Experiment | #52 / platform/arch-exp-01-experiments | a966567b1a2a033f477c2847073cc11777a3afd2 | 2 |
| VVE-01 Credibility | #53 / platform/arch-vve-01-credibility | 9e9d8918c1e6989568e84c3f0d020fdffb0373de | 2 |
| 前轮 ARCH-05 | #48 / platform/arch-05-review | 4f7ccc1ffb37a6101169e7e6410cc78781abb527 | 1 |

六个方案的 base 均为 master@2ab60c69a806a22d7ba20353dee0571752a0e8e5；审查时所有六个 PR 都是 Open/Draft/未合并。各 PR 的全部变更文件均位于各自 docs/platform/architecture/{world,harness,components,migration,experiments,credibility} 下。本轮共读取 27/27 全部设计正文及原 #48 审查报告；未执行可运行仿真。

**修订旧报告错误时态**：#48 的 B-00（“ARCH-01～04 PR 不存在”）现已解除，旧报告因此不再是当前交付裁决。但其历史审查时点可追溯，不能回写改变过去事实。新的阻断源自真实联合契约差异和未冻结决策，不是“缺文件”。

## 1. 结论分层

**可确认的共同方向**：WorldDefinition/Scenario 不可变、Run 独立 WorldState；Harness 为唯一权威写入者；组件只读 + proposal；Legacy 进程隔离与原有结果只读；Experiment 一次批次编排多独立 Run；VVE 区分软件 Verification、现实 Validation、UQ、实验完整性。以上是文档一致的设计意向，**不是**已实现能力。

**阻断冻结的联合契约差异（B01～B07）**：
- B01 P0：同刻 micro-commit 与单 boundary 原子提交语义不一致。
- B02 P0：Scheduler/Dynamics 目标调用方法与入参没有共同签名。
- B03 P0：事件 envelope 的 timestamp、priority/phase 和去重排序键没有统一 schema。
- B04 P0：Scenario.seed 与 Experiment replication seed plan 的最终所有权、RNG 生成和 paired-run 规则没有闭环。
- B05 P0：RunRecord/Run result 与 MetricDefinition/AnalysisRecord 的所有权及可比性门没有版本化跨组契约。
- B06 P1：组件私有状态在 boundary rollback / checkpoint 时可恢复性与拒绝策略尚需对齐。
- B07 P1：原 ARCH-04 最小纵切侧重 legacy 单步等价，而 EXP/VVE 目标强调最小研究闭环；尚无一致的分期完成门。

裁决等级说明：P0=阻止 V1 共同接口冻结；P1=允许有条件冻结部分接口，但必须在相关实施 PR 前完成明确决策；并非运行时代码缺陷，也不等同于“文件本身错误”。

## 2. 真实差异/未决裁决台账（所有条目附证据）

### B01 P0：提交原子性粒度
- 证据：[ARCH-01 WORLD_STATE.md `3/`5](https://github.com/159357yangjun/SwarmBalance/blob/b5f05a70a3306f1799fcae2c3f342f3ed9ee0048/docs/platform/architecture/world/WORLD_STATE.md) 允许同一物理时刻不同 phase 的多个显式 micro-commit，各有独立 revision；[ARCH-02 STATE_OWNERSHIP.md `3](https://github.com/159357yangjun/SwarmBalance/blob/d155621aca66e3a80c388718093a452d17d71e10/docs/platform/architecture/harness/STATE_OWNERSHIP.md) 和 [RUNTIME_SEQUENCE.md `2](https://github.com/159357yangjun/SwarmBalance/blob/d155621aca66e3a80c388718093a452d17d71e10/docs/platform/architecture/harness/RUNTIME_SEQUENCE.md) 要求每执行 boundary 只发布一次、内部 provisional view 不发布 revision。
- 影响：同刻事件、外部 snapshot、revision/compare、失败回滚与 replay 结果不等价。
- 责任：ARCH-02 主、ARCH-01 会签、ARCH-03 确认 CommittedFrame。
- 建议：V1 单 boundary 唯一对外 committed revision；phase 内部仅 staged/provisional，不对外可见；若将来支持 micro-commit 另设 mode/version。提供两个同刻事件+中途失败的负例契约测试后解除。

### B02 P0：Scheduler / Dynamics 接口签名分歧
- 证据：[ARCH-02 RUNTIME_SEQUENCE.md `2/`4](https://github.com/159357yangjun/SwarmBalance/blob/d155621aca66e3a80c388718093a452d17d71e10/docs/platform/architecture/harness/RUNTIME_SEQUENCE.md) 使用 Scheduler.decide(WorldView,ClockView)、DynamicsModel.advance；[ARCH-03 COMPONENT_CONTRACTS.md `3](https://github.com/159357yangjun/SwarmBalance/blob/68382c649393057ffbf5a14508ab1ff72d575b09/docs/platform/architecture/components/COMPONENT_CONTRACTS.md) 定义 Scheduler.propose(ObservationV1)、DynamicsModel.propose(state_slice,conditions,dt_seconds)；[ARCH-04 ADAPTER_DESIGN.md `3](https://github.com/159357yangjun/SwarmBalance/blob/c4c0c67111ead435062650c1ed776547c477e3e3/docs/platform/architecture/migration/ADAPTER_DESIGN.md) 的 LegacySchedulerAdapter.decide 与旧 act/step 另成一层。
- 影响：同名 capability 不能从一份真实接口合规测试实现端到端装配。
- 责任：ARCH-03 主、ARCH-02/04 会签。
- 建议：冻结唯一 Scheduler 提案入口及 Dynamics 输出签名；Harness 内部的 decide/advance 只能作为相位语义，不作为另一个 public protocol。明确 ObservationV1 时点/版本、ActionProposal、StateDeltaProposal、LegacyAdapter 翻译方式，给出正/负 contract fixtures。

### B03 P0：事件 envelope / 时钟 / 排序键不一致
- 证据：[ARCH-01 SCENARIO_MODEL.md `2](https://github.com/159357yangjun/SwarmBalance/blob/b5f05a70a3306f1799fcae2c3f342f3ed9ee0048/docs/platform/architecture/world/SCENARIO_MODEL.md) 使用 time_s:float、priority:int、kind/target_ref/on_failure；[ARCH-02 CLOCK_AND_EVENTS.md `1-`4](https://github.com/159357yangjun/SwarmBalance/blob/d155621aca66e3a80c388718093a452d17d71e10/docs/platform/architecture/harness/CLOCK_AND_EVENTS.md) 用整数 time_ns、phase、priority、producer_id、producer_seq，定义六类相位；[ARCH-03 COMPONENT_CONTRACTS.md `1](https://github.com/159357yangjun/SwarmBalance/blob/68382c649393057ffbf5a14508ab1ff72d575b09/docs/platform/architecture/components/COMPONENT_CONTRACTS.md) 的 EventIntent 则只有 at_seconds、priority_class、stable_order_key 和 payload/preconditions。
- 影响：非整数秒舍入、同刻不同事件优先级、重复事件判别及 mid-step 注入无法跨三方案唯一解释。
- 责任：ARCH-02 主、ARCH-01/03 会签。
- 建议：运行内核用 int nanoseconds；输入转换显式精度/舍入；统一 EventEnvelope/Intent、phase enum、priority 类型、proposer sequence 与排序键，明确与 World EventSpec 的转换。用风故障同刻与 3.5s 事件走查。

### B04 P0：Scenario seed 与 Experiment RNG 策略所有权
- 证据：[ARCH-01 SCENARIO_MODEL.md `1/`2](https://github.com/159357yangjun/SwarmBalance/blob/b5f05a70a3306f1799fcae2c3f342f3ed9ee0048/docs/platform/architecture/world/SCENARIO_MODEL.md) 场景配方含 seed；[ARCH-02 CLOCK_AND_EVENTS.md `5](https://github.com/159357yangjun/SwarmBalance/blob/d155621aca66e3a80c388718093a452d17d71e10/docs/platform/architecture/harness/CLOCK_AND_EVENTS.md) RNG key 包含 master_seed + run spec digest + component ID + stream name；[EXP-01 EXPERIMENT_SYSTEM.md 对照设计](https://github.com/159357yangjun/SwarmBalance/blob/a966567b1a2a033f477c2847073cc11777a3afd2/docs/platform/architecture/experiments/EXPERIMENT_SYSTEM.md) 定义 seed plan 并警告同 seed 不能自动视为同随机扰动；[ARCH-03 COMPONENT_CONTRACTS.md `4](https://github.com/159357yangjun/SwarmBalance/blob/68382c649393057ffbf5a14508ab1ff72d575b09/docs/platform/architecture/components/COMPONENT_CONTRACTS.md) 描述 run seed + component_id + stream_name，未与 run spec digest 协商。
- 影响：treatment 改变 run spec digest 时，原本期望配对的任务需求扰动可能被隐式重采样；Scenario.seed 与 ExperimentPlan seed 谁优先不明。
- 责任：EXP-01 主、ARCH-02/01/03 会签。
- 建议：ExperimentPlan 生成独立的 exogenous demand/weather stream seeds 并显式映射到 RunSpec；component-private seeds 可按 spec 派生；避免把整体 treatment digest 混入希望成对保持一致的扰动子流。定义 Scenario 默认 seed 被实验覆盖的显式优先级和记录字段。要求一组共享扰动配对反例。

### B05 P0：Run 结果与指标/实验归属未统一
- 证据：[EXP-01 EXPERIMENT_SYSTEM.md 资源](https://github.com/159357yangjun/SwarmBalance/blob/a966567b1a2a033f477c2847073cc11777a3afd2/docs/platform/architecture/experiments/EXPERIMENT_SYSTEM.md) 将 RunRecord 定义在 Experiment System；[VVE-01 EVIDENCE_CONTRACTS.md](https://github.com/159357yangjun/SwarmBalance/blob/9e9d8918c1e6989568e84c3f0d020fdffb0373de/docs/platform/architecture/credibility/EVIDENCE_CONTRACTS.md) 要求 ARCH-02 RunRecord 锁定 hashes；[ARCH-02 HARNESS_ARCHITECTURE.md `4](https://github.com/159357yangjun/SwarmBalance/blob/d155621aca66e3a80c388718093a452d17d71e10/docs/platform/architecture/harness/HARNESS_ARCHITECTURE.md) 返回 result(handle) 及 RunEventLog/ResultArtifact；[ARCH-03 COMPONENT_CONTRACTS.md `3](https://github.com/159357yangjun/SwarmBalance/blob/68382c649393057ffbf5a14508ab1ff72d575b09/docs/platform/architecture/components/COMPONENT_CONTRACTS.md) 只定义 MetricSample，不定义由谁冻结跨 Run 共享 MetricDefinition。
- 影响：独立手工 Run 是否有 RunRecord、实验重试 attempt 是否重写已有 run，分析如何拒绝不合格 Run，证据链对象引用不统一。
- 责任：ARCH-02 负责单 RunRecord / ARTIFACT；EXP-01 负责 ExperimentPlan/BatchRecord/AnalysisRecord；ARCH-03 负责 MetricDefinition/MetricSample；VVE-01 负责 claim/evidence 索引；四方会签。
- 建议：冻结一份 RunRecord v1（含是否属于 experiment 的可选引用）、MetricDefinition v1 和 Run→Analysis→Claim 不可变 DAG。成功/失败/缺指标/比较拒绝须保持独立可见。

### B06 P1：组件私有状态/rollback 能力不闭合
- 证据：[ARCH-02 FAILURE_CONTRACT.md `4](https://github.com/159357yangjun/SwarmBalance/blob/d155621aca66e3a80c388718093a452d17d71e10/docs/platform/architecture/harness/FAILURE_CONTRACT.md) 在异常前还原 RNG/queue 与事务 B/C/D；[ARCH-02 STATE_OWNERSHIP.md `1](https://github.com/159357yangjun/SwarmBalance/blob/d155621aca66e3a80c388718093a452d17d71e10/docs/platform/architecture/harness/STATE_OWNERSHIP.md) 区分 component-private D；[ARCH-03 COMPONENT_CONTRACTS.md `2](https://github.com/159357yangjun/SwarmBalance/blob/68382c649393057ffbf5a14508ab1ff72d575b09/docs/platform/architecture/components/COMPONENT_CONTRACTS.md) 允许不支持 checkpoint 的组件声明拒绝能力。
- 影响：无法回滚组件内部队列/缓存时，单 boundary “所有状态原子”可能只保护 WorldState 而不保护下一步计算正确性。
- 责任：ARCH-02/03；要求组件具有 precommit pure/rollbackable 之一，否则不参与 strict transaction；legacy opaque 模式单独标注 TAINTED，不能冒充 ACID。

### B07 P1：最小交付的两个不同目标未统一
- 证据：[ARCH-04 MIGRATION_SLICES.md S0–S5](https://github.com/159357yangjun/SwarmBalance/blob/c4c0c67111ead435062650c1ed776547c477e3e3/docs/platform/architecture/migration/MIGRATION_SLICES.md) 首先证明 legacy 单 worker 行为对照；[EXP-01 EXPERIMENT_SYSTEM.md MVP](https://github.com/159357yangjun/SwarmBalance/blob/a966567b1a2a033f477c2847073cc11777a3afd2/docs/platform/architecture/experiments/EXPERIMENT_SYSTEM.md) 要求有独立研究闭环；[VVE-01 CREDIBILITY_FRAMEWORK.md V0–V3](https://github.com/159357yangjun/SwarmBalance/blob/9e9d8918c1e6989568e84c3f0d020fdffb0373de/docs/platform/architecture/credibility/CREDIBILITY_FRAMEWORK.md) 区分真实模型确认门。
- 影响：团队可能把 legacy 行为等价当成新 Harness 已具备组件化、实验有效性，或者把尚无现实验证当作阻止任何工程测试的理由。
- 责任：主控/ARCH-04/EXP-01/VVE-01。建议分 M0 旧基线保全→M1 真实最小 Harness + 单 Run→M2 最小 Experiment & trace→M3 扩展性→M4 现实模型 validation/UQ；软件门和研究证据门分开声明。

## 3. 横向一致性与仍需细化的合同

- **状态归属：共同原则一致**。World 的静态数据与 RunState 区分；Harness 唯一提交；Metrics/UI 不写 Domain State。分歧是 B01 粒度而非“谁都可以写”。
- **物理量与坐标：原则一致**。Wh/m/kg/s/m/s、CRS/axis/vertical datum、显式转换在 ARCH-01/03 都出现；精度和 rounding 需列一套 converters，不可把示例 EPSG 当真实数据。
- **事件优先级：B03**，还须冻结哪些事件在 scheduler 读取前生效、哪些在动力学后产生。
- **确定性：有共同方向**，但 numeric profile、RNG 配对/独立流策略待 B04，不能承诺跨平台 bit-identical。
- **失败与异常：基本相容**，默认 fail closed；MetricProvider post-commit failure 标记 partial，实验和 VVE 应据此禁止直接 PASS。
- **依赖图：逻辑 DAG 可推导**，但具体契约包方向/模块 import cycle 尚未机器验证；设计上应坚持 domain/contracts 不依赖 UI/legacy。
- **旧引擎保护：基本一致**，legacy 环境非事务、进程全局与随机数需 worker 隔离、旧结果只读、新 sidecar；绝不将 parity 等同新平台模型可信。
- **领域范围：低空物流优先**，世界类型开放但不以通用三维物理引擎、微服务、插件市场作为 V1 强制能力。

## 4. 研究完整性额外门（EXP / VVE）

| ID | 交叉门 | 状态 | 要求 |
|---|---|---|---|
| R-EXP-01 | ExperimentDefinition→FrozenRunSpec | OPEN / B04,B05 | 因子/控制变量/seed计划与每 Run 的 digest 精确对应 |
| R-EXP-02 | 失败/取消/重试样本 | PARTIAL | attempt、failed run、缺失和排除条件不可被吞，按预注册规则处理 |
| R-EXP-03 | 指标与比较门 | OPEN / B05 | MetricDefinition、window、denominator、missing_reason 和比较资格同一标准 |
| R-VVE-01 | 模型和数据真实来源 | PARTIAL | Dataset/ModelManifest 血缘与 ValidationRecord 连接，引用可验证、不把来源当可信度 |
| R-VVE-02 | 独立验证与 UQ | DESIGN-ONLY | intended use、split、error、acceptance、域外拒绝、UQ 来源必须可追踪；不得声称已经完成 |
| R-VVE-03 | Claim→Analysis→Run DAG | OPEN / B05 | immutable digest、证据缺失显式状态、结论适用边界 |
| R-USE-01 | 原始立项双轨 | OPEN | 低空物流任务分配/机巢优化的研究交付独立于长期平台里程碑 |

## 5. 给 ARCH-06 的裁决

| Gate | 判定 | 原因 |
|---|---|---|
| G-ARCH-1 交付与 HEAD | PASS | 六个设计 PR 和 27 份文档读取核对 |
| G-ARCH-2 设计内容独立复审 | PASS-for-review | 本报告完成独立内容审查，不等于技术接口批准 |
| G-ARCH-3 25 接口一致性 | HOLD | 详见接口矩阵与 B01～B06 |
| G-ARCH-4 六扩展场景 | HOLD | 仅设计走查，阻塞/条件见矩阵 |
| G-ARCH-5 状态/时钟/RNG/语义 | HOLD | B01～B06 |
| G-ARCH-6 纵切范围 | HOLD | B07，未共同冻结 |
| G-ARCH-7 旧风险处置 | CONDITIONAL | 进程隔离/legacy_direct/只读旧证据合理，缺实际测试 |
| G-ARCH-8 独立审查输入 SHA | PASS | 本报告绑定六份精确 SHA，旧 #48 未覆写 |
| G-EXP/VVE 可信研究闭环 | HOLD | B04/B05 与 R-EXP/VVE 仍未冻结 |

**最终建议：HOLD / 不允许正式冻结 V1 跨组接口，不允许无门禁进入 S4 集成。** 这不是建议推倒六份方案：可优先冻结已一致的“静态世界、单写入者、元数据与 Legacy 保全”原则，委派 B01～B05 定向修订后按精确新 HEAD 独立增量复核，再由主控执行 ARCH-06 裁决。不能只因本报告提交就认为研究平台已工程完工或模型已获现实验证。

## 6. 变更约束、证据等级和后续复核

E0 PR/HEAD/变更文件，E1 Legacy 固定源码事实（沿用 #48/#50 溯源），E2 六份设计文档内容（本报告）、E3 contract fixtures/可运行最小纵切（未提供）、E4 独立现实参照数据验证（未提供）。任何后续 HEAD 改变，应声明受影响章节、按差异增量复核。不能把 Draft 方案视作 Accepted ADR。PR 保持 Draft，禁止合并原设计 PR。
