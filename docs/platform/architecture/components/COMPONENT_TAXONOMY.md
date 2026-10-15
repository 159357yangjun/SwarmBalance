# ARCH-03｜组件分类与职责边界（设计草案 v0.1）

> 状态：Draft / 仅契约设计；基线 master@2ab60c69a806a22d7ba20353dee0571752a0e8e5（2026-10-15）。ARCH-01/02 的对应分支尚不可读取，跨组约定均标记 PROPOSED，不能视为已联合批准。

## 1. 源码审计：现状不是完整组件平台

| 领域 | 可核查的现有入口 | 实际耦合/约束 | 本次定义的边界 |
|---|---|---|---|
| 地图与空间 | frontend/tools/osm.py:182-247；frontend/environment.py:166-204 | Environment 构造时同步加载固定 OSM；osmnx/离线回退、解析模式和缓存对结果有影响；障碍/禁飞区混在 Environment | SpatialProvider 产带 CRS、语义与证据的不可变空间快照 |
| 机队/机巢/订单数据 | frontend/data_source.py:42-153,228-485；frontend/enterprise_data_source.py:140-238 | 现有 DataSource 只提供三类 Spec；CSV 缺列/无效值常用默认值，GeoJSON 可能默默跳过记录；企业坐标转换、机型映射存在降级 | DataProvider 管数据批次与来源，不写 WorldState |
| 动力/能耗 | frontend/drone.py:50-206；frontend/environment.py:1130-1175 | Drone.update / consume_battery 持有状态修改；wind 参数与全局配置混合；载重归属的能耗侧与空载里程侧存在未决冲突 | DynamicsModel 纯提议增量、显式物理假设与单位 |
| 路径成本 | frontend/route_cost.py:1-185；frontend/route_planner.py:38-118 | cost provider 已可在 euclidean/planned_distance 切换，但不等同于整个运动模型；ETA 以 env-step 表达 | SpatialProvider 的路径/可达能力或独立子能力；不得把距离=能耗 |
| 调度 | frontend/scheduling_interface.py:1-69；console/sim_session.py:167-185；experiments/worker.py:20-67 | 稳定接口声明 act()，现有控制台/批实验实际调用部分实例的 step()；greedy 有函数旁路；action 用 drone_index | Scheduler 消费明确版本 ObservationV1，返回 ActionProposal；由 Harness 验证并提交 |
| 事件 | console/sim_session.py:212-276；console/scenario_presets.py:1-140 | 人工故障、订单注入与演示预设绑定会话/配置；无跨会话事件契约 | EventProvider 仅产生有时间和序号的待应用 EventIntent |
| 指标 | frontend/metrics_schema.py:1-165；frontend/environment.py 统计字段；results/compare/manifest.json | 指标当前由环境统计并统一 CSV 映射；部分缺值转 0；历史文件多 schema/实验族不可比 | MetricProvider 从提交后的事件/快照产有分母、单位、口径、缺失标记的 MetricSample |
| 生命周期/配置 | console/sim_session.py:103-210；config/config_loder.py:1-140；experiments/runner.py:58-172 | 单会话、模块级配置/环境变量、实验 worker 隔离存在；配置覆盖未成为原子装配契约 | AssemblyPlan 绑定所有版本、配置、数据哈希、seed；Harness 唯一拥有运行提交权 |

**证据等级**：以上是 master 静态阅读事实，不宣称运行测试通过。L1 修复位于未合并 PR #41，不能把其行为默认为 master。

## 2. 分类与单一职责

| category | 主职责 | 生产/消费 | 禁止事项 |
|---|---|---|---|
| DataProvider | 导入、验证、规范化数据集；提供静态实体规格和可重现任务批次 | DatasetRef -> ValidatedEntityBatch | 不做派单、物理运动或直接添加世界实体 |
| SpatialProvider | 空间数据、几何/拓扑、坐标转换、地图查询及可选路径能力 | SpatialDatasetRef -> SpatialSnapshot / QueryResult | 不假定城市、绝不偷偷重定位到固定仓库坐标 |
| DynamicsModel | 给定状态和时间增量计算运动/电量等候选变化 | ReadOnlyStateSlice + Conditions -> StateDeltaProposal | 不写 Drone/WorldState，不控制仿真时钟 |
| EventProvider | 定义定时/条件事件及相应意图 | EventQuery -> EventIntent[] | 不直接触发故障/篡改任务或环境 |
| Scheduler | 给定观测和能力约束提出调度动作 | ObservationV1 -> ActionProposal | 不持有 Environment 可变引用、不发世界写操作 |
| MetricProvider | 有条件地消费已确认快照/事件及运行血缘，产可比较指标 | CommittedFrame -> MetricSample[] | 不改变运行状态、不把 unknown 当零 |
    
控制点是 **Harness 的装配器与状态提交器**，不是第七个插件。World/Entity/WorldState/Scenario 属于 ARCH-01 的概念所有权；RunContext/clock/commit transaction 属于 ARCH-02。本文件仅定义交换边界（PROPOSED）。

## 3. 能力、版本与身份

组件描述符必须声明：id（域名式稳定标识）、category、implementation_version（SemVer）、contract_version（SemVer）、artifact_digest（SHA-256）、entry_ref（静态登记的工厂标识，非任意代码路径）、capabilities、requires、config_schema_ref、determinism、resource_limits、license、provenance、supported_platforms。

- capabilities 使用命名空间和版本，如 spatial.crs_transform@1、dynamics.energy_quote@1、scheduler.assign_tasks@1、metrics.lifecycle@1；每条还要包含输入/输出契约版本与约束参数。
- requires 声明 hard/optional 依赖和语义约束；hard 不满足即拒绝。optional 缺失只能显式禁用对应能力，不能偷偷替换物理口径。
- implementation_version 不得用来推断字段兼容；由 contract_version + 能力匹配 + 数据语义共同判定。
- 同一组件版本如果 digest 不同视为供应链冲突，不做热替换。
- 组件实例生命周期和状态所有权见 COMPONENT_CONTRACTS.md；装配顺序见 REGISTRY_AND_ASSEMBLY.md。

## 4. 初始隔离规则

1. 历史源码仅是 **Legacy Adapter 候选**：例如 CSVDataSource 并不天然满足严格 DatasetManifest，必须由 adapter 把隐式默认、跳过行、坐标混用报告出来；失败则隔离，不偷补。
2. 需要物理准确性证据的指标不得自动认领 A/B 级来源；仓内 data/provenance/manifest.json 的 A/B/C/D/E 与 traceability/transformation 三轴仍应独立保留。
3. 动力结果与预测成本解耦：route distance、ETA、Wh、可行性是不同能力；引用的是同一个 scenario/time/coordinate 基准才可能联合推理。
4. 性能优化缓存不能成为未声明的全局状态；缓存 scope=dataset_digest+projection+component_version+configuration_digest+run_id（按需更窄），reset 和资源释放时由 Harness 管理失效。
5. 不支持运行中自由换插件；替换组件意味着新的 AssemblyPlan、预检与独立 run 身份，保留旧运行和 E0/E1 证据原样不动。

## 5. 交叉审查与未决接口

- ARCH-01 决定 WorldState、EntityId、CoordinateRef、ScenarioRef、EventId 的规范定义及空间单位。
- ARCH-02 决定 RunContext、SimTime（秒 vs 步）、CommittedFrame、StateDeltaProposal 事务协议与组件失败时回滚。
- ARCH-03 提案使用 EntityId 而不是 drone_index 作为新系统稳定身份；旧索引动作只能在 LegacySchedulerAdapter 中、固定映射快照下转成 ID。
- 时间提案一律传 sim_time_seconds + step_index + delta_seconds；旧 frontend/route_cost.py 的 ETA（env-step）必须显式换算并登记舍入策略。
- 类型未联合冻结以前，只提供结构草案/示例，不应据此生成正式 ABI 或宣称能够随意插拔。
