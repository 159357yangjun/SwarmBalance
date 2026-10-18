# ARCH-05-R2｜25 项接口矩阵与六场景设计走查

> 附属于 [ARCH_05_R2_CROSS_REVIEW.md](ARCH_05_R2_CROSS_REVIEW.md)；检查六份设计 PR 的 27 份文档。所有“相容”仅指**文档级意向相容**，不代表接口冻结、运行态验证通过。
> 状态：COHERENT=没有观察到实质相反规定但可能仍未冻结；DELTA=跨文档已确认差异；OPEN=尚缺联合签字的最小机制/字段。

## 25 项矩阵

| ID | 交叉接口 | 证据来源（文件） | 当前设计判定 | 主责 / 后续必须输出 |
|---|---|---|---|---|
| M01 | Project/World/Scenario/WorldState 身份和寿命 | 01 WORLD_MODEL §3；02 HARNESS_ARCHITECTURE §4；EXP EXPERIMENT_SYSTEM 资源 | COHERENT | 01：冻结 ID/ref/revision；Experiment 必引用固定资源 |
| M02 | EntityDefinition/EntityState 区分 | 01 ENTITY_CONTRACTS §1-§2；02 STATE_OWNERSHIP §1 | COHERENT | 01：spec 不进 state；状态只属于 Run |
| M03 | WorldState 单写与可见 revision | 01 WORLD_STATE §3/§5；02 STATE_OWNERSHIP §3；02 RUNTIME_SEQUENCE §2 | **DELTA B01** | 02 主：统一 boundary commit 对外可见语义 |
| M04 | 事件先后、同刻处理、唯一提交 | 01 SCENARIO_MODEL §2/§5；02 CLOCK_AND_EVENTS §3-§4；03 COMPONENT_CONTRACTS §1 | **DELTA B03** | 02 主：phase/priority/event ID/producer seq |
| M05 | sim_time_s / time_ns / tick_index / revision | 01 WORLD_STATE §2/§5；02 CLOCK_AND_EVENTS §1；03 COMPONENT_CONTRACTS §1 | **DELTA B03** | 02 主：内部纳秒、外部秒及显式转换、rounding |
| M06 | CRS、坐标、距离、速度、能量单位 | 01 WORLD_MODEL §5；03 COMPATIBILITY_RULES 转换；03 MANIFESTS | COHERENT | 01/03：统一 converter 和精度，未声明拒绝 |
| M07 | 实体 ID、引用、资源独占/货权 | 01 ENTITY_CONTRACTS §3-§4；02 STATE_OWNERSHIP §4 | COHERENT | 01：resource lease/ID 同事务实现负例 |
| M08 | Observation read-only / version | 01 WORLD_STATE §3；02 HARNESS_ARCHITECTURE §4；03 COMPONENT_CONTRACTS §1 | OPEN | 03 主：具体 ObservationV1 字段与阶段时点 |
| M09 | Scheduler 输入/输出/调用入口 | 02 RUNTIME_SEQUENCE §4；03 COMPONENT_CONTRACTS §3；04 ADAPTER_DESIGN §3 | **DELTA B02** | 03 主：decide/propose 统一；legacy 单向转译 |
| M10 | Dynamics 状态推进、能耗扣减 | 01 WORLD_STATE §4；02 RUNTIME_SEQUENCE §4；03 COMPONENT_CONTRACTS §3 | **DELTA B02** | 03/02：advance/propose 统一；唯一 energy commit |
| M11 | DataProvider 加载、必填、provenance | 01 EXTENSIBILITY_CASES §5；03 COMPONENT_CONTRACTS §3；03 DATA_AND_MODEL_MANIFESTS | COHERENT | 03：missing/null 策略机器拒绝规则 |
| M12 | SpatialProvider、CRS、缓存/版本 | 01 WORLD_MODEL §5；03 REPLACEMENT_EXAMPLES Case A；04 COUPLING_ANALYSIS | COHERENT | 03/04：缓存 invalidation/OSM parser 锁定 |
| M13 | EventProvider / EventIntent / EventSpec | 01 SCENARIO_MODEL §2；02 CLOCK_AND_EVENTS §3；03 COMPONENT_CONTRACTS §1/§3 | **DELTA B03** | 02/03：结构化 event envelope 转换与权限 |
| M14 | MetricProvider、MetricDefinition、指标读写 | 03 COMPONENT_CONTRACTS §3；EXP EXPERIMENT_SYSTEM；VVE EVIDENCE_CONTRACTS | **OPEN B05** | 03/EXP：定义版本、窗口、分母、缺失、比较门 |
| M15 | 组件 initialize/reset/close/checkpoint | 02 SIMULATION_LIFECYCLE §2/§4；03 COMPONENT_CONTRACTS §2 | **OPEN B06** | 02/03：跨 generation reset、私有状态恢复 |
| M16 | Registry、capabilities、版本与依赖 | 03 REGISTRY_AND_ASSEMBLY；03 COMPATIBILITY_RULES；02 HARNESS_ARCHITECTURE §3 | COHERENT | 03：错误码统一，冻结 build-time DAG |
| M17 | Dataset/Model/Assembly manifests / 配置优先级 | 03 DATA_AND_MODEL_MANIFESTS；03 REGISTRY_AND_ASSEMBLY；VVE CREDIBILITY_FRAMEWORK | OPEN | 03/VVE：verification/validation/UQ 关联字段 |
| M18 | RNG 子流、seed、run spec digest、paired design | 01 SCENARIO_MODEL §4；02 CLOCK_AND_EVENTS §5；03 COMPONENT_CONTRACTS §4；EXP EXPERIMENT_SYSTEM | **DELTA B04** | EXP/02：seed source/stream derivation/共用扰动 |
| M19 | 失败/超时/事务回滚/不可恢复状态 | 02 FAILURE_CONTRACT；03 COMPONENT_CONTRACTS §2；04 ADAPTER_DESIGN §5 | **OPEN B06** | 02：强一致域与 legacy opaque 分离 |
| M20 | create/assemble/initialize/run/pause/stop/reset/destroy | 02 SIMULATION_LIFECYCLE；EXP EXPERIMENT_CONTRACTS | COHERENT | 02/EXP：Runner 不绕过 Harness，重试 attempts |
| M21 | Legacy Environment/Scheduler Adapter | 02 HARNESS_ARCHITECTURE §6；04 ADAPTER_DESIGN §2-§4 | COHERENT | 04：保留 greedy callable/其余 step 的映射 |
| M22 | 新旧行为对照、快照、指标等价程度 | 04 BACKWARD_COMPATIBILITY；04 MIGRATION_SLICES；02 FAILURE_CONTRACT | COHERENT | 04：不把 legacy opaque 当新原子保证 |
| M23 | domain/contracts → components → harness → UI 依赖方向 | 02 HARNESS_ARCHITECTURE §3；03 REGISTRY_AND_ASSEMBLY；04 LEGACY_ARCHITECTURE | OPEN | 02/03：冻结 import DAG，执行 cycle 检查 |
| M24 | 版本化场景、日志、会话隔离、Evidence refs | 01 WORLD_STATE §6；02 SIMULATION_LIFECYCLE §3；04 COUPLING_ANALYSIS；VVE EVIDENCE_CONTRACTS | OPEN | 02/VVE：RunRecord / log digest / immutable result |
| M25 | 最小纵切、验收退出条件及 legacy/new 关系 | 04 MIGRATION_SLICES；EXP EXPERIMENT_SYSTEM MVP；VVE CREDIBILITY_FRAMEWORK | **OPEN B07** | 主控：分别冻结 legacy parity 与真正研究最小纵切 |

**交叉实证差异**：M03、M04、M05、M09、M10、M13、M18；这些都是文档中存在的不同字段/方法/可见性约定。**未闭合**：M08、M14、M15、M17、M19、M23、M24、M25。其余 COHERENT 不意味着通过 G-ARCH-3：所有 schema 在 ARCH-06 前还须精确版本、会签和 contract cases。

## 六个扩展场景（设计推演，不是实际运行）

| 场景 | 文档证据路径 | 联合设计状态 | 通过冻结还需提交 |
|---|---|---|---|
| S01：OSM 城市甲→GeoJSON/CAD 城市乙 | 01 EXTENSIBILITY_CASES Case A；03 REPLACEMENT_EXAMPLES A；04 MIGRATION_SLICES S1/S3 | CONDITIONAL，空间/数据替换意图相容 | 精确 CRS/垂直基准/许可/版本/缓存异常策略；拒绝“经纬度即米” |
| S02：替换能耗 DynamicsModel | 01 ENTITY_CONTRACTS 电量与实际载货；03 REPLACEMENT_EXAMPLES B；VVE CREDIBILITY_FRAMEWORK | BLOCKED by B02 + VVE evidence | 统一模型提案接口、Wh 唯一扣减；模型 domain/标定与验证 status；缺温度/高度拒绝 |
| S03：新增 Scheduler，Greedy→PSO/新策略 | 02 RUNTIME_SEQUENCE；03 COMPONENT_CONTRACTS；04 ADAPTER_DESIGN | BLOCKED by B02 + B04/B05（研究比较） | 统一 Scheduler API、stable EntityId 映射、同扰动种子策略、MetricDefinition comparability |
| S04：3.5 秒风场+同刻机巢关闭+任务到达 | 01 SCENARIO_MODEL / WORLD_STATE；02 CLOCK_AND_EVENTS；03 COMPONENT_CONTRACTS | BLOCKED by B01+B03 | 同刻 phase/priority/rollback 测试、严格时间转换、重复事件幂等及任务/货权不变量 |
| S05：缺 task ID/坐标/高度的 CSV/GeoJSON | 01 EXTENSIBILITY_CASES §5；03 COMPATIBILITY_RULES；VVE CREDIBILITY_FRAMEWORK | CONDITIONAL，fail-closed 原则相容 | strict DatasetManifest + 拒绝/审计默认值策略、错误字段路径、缺失率证据 |
| S06：同场景 legacy_direct 与 legacy_harness 切换 | 04 BACKWARD_COMPATIBILITY；04 MIGRATION_SLICES S0-S5；02 HARNESS_ARCHITECTURE §6 | CONDITIONAL，严格 legacy 基线与回退一致 | worker 进程隔离，动作/状态逐步 parity，旧输出 SHA 不变，失败/非原子路径显式标识 |

### S07（新增跨平台科研闭环，非原六项计数）
ExperimentDefinition 预注册两调度策略及控制变量→FrozenRunSpec 多次运行→RunRecord 完整保存→MetricDefinition 比较门→AnalysisRecord 含失败、统计与效应估计→VVE Claim/Evidence 检验数据和模型域。**设计可表述但 B04/B05 阻断完整稳定 API；尚无运行/现实验证证据。**

## 最小可行验收门（不应合为一个 PASS）
- G0：六组接口和 schema 冻结（无 P0；有具名 P1 延期及适配范围）。
- G1：无 GUI 单 Run Harness 测试：state sole writer、atomic boundary、不可变 snapshot、失败/重放。
- G2：Experiment 最小 batch：冻结因素/种子、至少两种调度、独立 run/error records、比较门、无结果假造。
- G3：组件扩展与 legacy parity：换空间/能耗/调度不改核心，并隔离运行旧引擎。
- G4：VVE 输出明确 NOT_ASSESSED/INVALID/VALIDATED（适用域限定），真实模型验证需独立参照，不随 CI 自动通过。
- G5：工作台端到端真实操作任务，所有结果可追溯。

## 审查输入与可复核原文
- World: https://github.com/159357yangjun/SwarmBalance/tree/b5f05a70a3306f1799fcae2c3f342f3ed9ee0048/docs/platform/architecture/world
- Harness: https://github.com/159357yangjun/SwarmBalance/tree/d155621aca66e3a80c388718093a452d17d71e10/docs/platform/architecture/harness
- Components: https://github.com/159357yangjun/SwarmBalance/tree/68382c649393057ffbf5a14508ab1ff72d575b09/docs/platform/architecture/components
- Migration: https://github.com/159357yangjun/SwarmBalance/tree/c4c0c67111ead435062650c1ed776547c477e3e3/docs/platform/architecture/migration
- Experiment: https://github.com/159357yangjun/SwarmBalance/tree/a966567b1a2a033f477c2847073cc11777a3afd2/docs/platform/architecture/experiments
- VVE: https://github.com/159357yangjun/SwarmBalance/tree/9e9d8918c1e6989568e84c3f0d020fdffb0373de/docs/platform/architecture/credibility

状态：设计读取与交叉审查完成；不应在没有实际 CI / contract fixtures 时宣称运行测试 PASS。报告审查之后任何上游 HEAD 更新都需做增量 diff 复核。
