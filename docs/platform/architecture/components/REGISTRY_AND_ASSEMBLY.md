# ARCH-03｜登记、协商与装配（设计草案）

## 静态注册表，不动态加载

本阶段仅设计 `ComponentDescriptor` 与 `AssemblyPlan` 的 schema；`entry_ref` 是受信任的构建时工厂标识，不是任意 Python import 路径/远程 URL。签名、许可证、SHA-256、允许列表校验后才可成为可选组件。registry 是版本固定的登记信息快照，不等于已运行的 Python 对象。

```yaml
registry_version: "0.1.0"
components:
  - id: "swarmbalance.spatial.osm-legacy-adapter"
    category: SpatialProvider
    implementation_version: "0.1.0"
    contract_version: "0.1.0"
    entry_ref: "builtin:spatial/osm-legacy" # 静态候选，不代表已实现
    artifact_digest: "sha256:<real digest required at implementation>"
    capabilities:
      - id: "spatial.geometry_snapshot"
        version: "1.0.0"
        attributes: {crs_required: true}
    requires: []
    determinism: {level: conditional, external_inputs_pinned: true}
```

**注意**：以上 digest 占位符说明待核验，不得传入装配器当有效值；当前无该 adapter 实现。

## 装配计划

```yaml
assembly_schema_version: "0.1.0"
project_ref: {id: demo, revision: "<immutable>"}
world_ref: {id: test-world, revision: "<immutable>"}
scenario_ref: {id: calm, revision: "<immutable>"}
run:
  seed: 100
  clock: {mode: fixed_step, delta_seconds: 1.0}
  reproducibility: strict
components:
  data: {id: "provider-id", version: "1.2.3", digest: "sha256:<required>", config: {}}
  spatial: {id: "provider-id", version: "1.2.3", digest: "sha256:<required>", config: {}}
  dynamics: {id: "model-id", version: "1.2.3", digest: "sha256:<required>", config: {}}
  events: [] # 可为空，需显式
  scheduler: {id: "scheduler-id", version: "1.2.3", digest: "sha256:<required>", config: {}}
  metrics: []
datasets: []  # 每个均引用不可变 DatasetManifest digest
models: []    # 每个均引用不可变 ModelManifest digest
```

## 装配流程

1. 收集 Project/World/Scenario + manifest refs，验证 schema、内容 hash 和信任级别。
2. 对六类绑定建立候选 DAG；锁定各自版本、能力参数、必需依赖/运行平台；拒绝不明确选择。
3. 验证单位/CRS/时间/实体类型/事件语义；对确知的合法换算生成有出处的显式 ConverterPlan；不因名称相似自动转换。
4. 检测依赖循环、冲突及资源预算；输出 deterministic topo order 与 DiagnosticReport。
5. 预检数据质量、缺失值、模型假设；隔离不可信内容；若 strict 模式数据不满足硬约束则拒绝运行。
6. 冻结 EffectiveAssemblyManifest：包含每个组件及数据/model digest、配置完整化前后的 hash、转换清单、时间基准、随机子流映射和诊断记录。
7. 交由 ARCH-02 Harness 的 create/initialize 流程。任一初始化失败，逆拓扑顺序 close；不产生“已启动”状态。

`EffectiveAssemblyManifest` 是运行身份的输入；同样 seed 但地图 digest、能耗模型/假设或调度器配置不同不得视为同一 run。显式的 `no-events` 与“未配置 events”是不同状态。

## 依赖实例

`Scheduler(requires: observation.tasks@1, observation.drone_energy@1)`；`DynamicsModel(requires: spatial.coordinate_frame@1, units.distance=m)`；`MetricProvider(requires: event.delivery_committed@1, lifecycle.definition@1)`。所有依赖声明精确字段版本和单位；环境提供能力并非自动满足统计口径。

## 配置与隔离

优先级拟定（待 ARCH-02 批准）：强类型 CLI/run override > scenario binding > project binding > descriptor **显式且有来源的** defaults。禁止不在 schema 的环境变量隐式更改装配；确需从旧 `SWARM_BALANCE_*` 导入时，Legacy Adapter 生成可追溯 `resolved_config`，逐字段记录来源；重放时不得重新读取进程环境。不能直接热替换运行中组件；新装配、新 run_id，历史结果保留。

## 交叉决策

- ARCH-01：Project/World/Scenario 的引用与覆盖权限、CoordinateRef、EntityId。
- ARCH-02：初始化失败回滚、快照/恢复、运行态服务、时间/event phase、随机流算法。
- ARCH-03：登记表身份和能力协商、Data/Model manifests、错误码与装配诊断。
