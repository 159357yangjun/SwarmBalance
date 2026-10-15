# ARCH-03｜能力匹配、兼容性门禁与拒绝诊断

> 提议规则 v0.1；状态：待 ARCH-01/02 对齐。目标：fail closed，不能靠隐式默认值伪装成功。

## 装配决策树

1. descriptor/schema 是否可识别，component id/version/digest 是否完整且签名/来源符合信任策略；
2. category 与绑定槽位是否一致，所需能力的 **语义版本** 与可选的字段集是否符合；
3. 依赖 DAG 是否存在、版本范围是否可解、是否存在循环；
4. 输入字段、实体 ID、时钟基准、坐标/轴序、物理单位和作用范围是否兼容；
5. DatasetManifest 的源、license、quality、missing policy 是否满足该模型/场景；
6. ModelManifest 的参数/校准与适用域、输入假设是否适配数据；
7. 运行确定性、平台依赖、资源预算、快照能力是否满足 RunPlan；
8. 输出 DiagnosticReport `ACCEPT | ACCEPT_WITH_EXPLICIT_CONVERSION | REJECT`；任何 hard error 必须拒绝。警告不得自动修复 hard error。

## 统一诊断 Schema 草案

```json
{
  "schema_version": "0.1.0",
  "decision": "REJECT",
  "errors": [{
    "code": "CRS_MISMATCH",
    "severity": "error",
    "component_id": "example.spatial",
    "binding": "spatial",
    "field_path": "$.datasets[0].spatial.crs",
    "expected": "EPSG:32651; axis x/y; meters",
    "actual": "unknown",
    "reason": "Scheduler/DynamicsModel 依赖米制距离，但数据未声明坐标系",
    "remediation": "提供可审计的坐标系声明与显式转换计划"
  }],
  "warnings": [],
  "converter_plan": [],
  "resolved_component_graph": [],
  "config_digest": null
}
```

## 错误码与硬条件

| code | 不可直接兼容的事实 | 处理 |
|---|---|---|
| REGISTRY_UNKNOWN_COMPONENT | ID 不存在/未获准注册 | 拒绝 |
| COMPONENT_DIGEST_CONFLICT | 相同身份版本存在不同实现 digest | 拒绝 |
| CONTRACT_VERSION_MISMATCH | 主版本不兼容或所需字段不在接口中 | 拒绝 |
| CAPABILITY_MISSING | 缺少 hard capability | 拒绝 |
| DEPENDENCY_CYCLE | 依赖闭环 | 拒绝并回报具体边 |
| CRS_MISMATCH | 坐标参考/轴序/单位无法证明一致 | 拒绝或审计的显式转换 |
| UNIT_MISMATCH | Wh/J、m/km、step/s 等未经换算 | 拒绝或审计的显式转换 |
| ENTITY_REFERENCE_INVALID | 使用未知/跨 World EntityId 或 index 映射不稳定 | 拒绝 |
| CLOCK_SEMANTICS_MISMATCH | 事件时间与固定步长混淆，缺归并规则 | 拒绝 |
| MANIFEST_DIGEST_MISSING | 数据、模型或来源文件未固定字节指纹 | strict 模式拒绝 |
| UNTRUSTED_SOURCE | 原始来源未知或可信度不满足用户策略 | 拒绝/隔离 |
| DATA_QUALITY_UNMET | 缺字段/坏几何/错误字段类型/无隐式补全策略 | 拒绝/隔离并计数 |
| MODEL_OUT_OF_DOMAIN | 风、载重、速度等超模型适用域 | 拒绝，不做静默截断 |
| MODEL_ASSUMPTION_CONFLICT | 载重或风符号语义不一致 | 拒绝 |
| DETERMINISM_UNSATISFIED | 请求重放但组件调用不可重现外部数据 | 拒绝 |
| METRIC_NOT_COMPARABLE | 指标定义、denominator、样本/种子/实验族不一致 | 拒绝横向比较，允许单独报告 |
| RESOURCE_BUDGET_EXCEEDED | 预算或生命周期不允许 | 拒绝/运行中交给 Harness 故障策略 |

## 转换的边界

允许的转换必须声明 `from_unit, to_unit, exact_formula, precision, rounding, input_digest, output_digest, converter_version`。例如 km→m（乘1000）能保持语义；EPSG 经纬度→投影米制必须说明区域、轴序和投影误差；env-step→秒必须使用被冻结的 delta_seconds。**不允许**把未知经纬度当平面米、把“缺失高度”设为 0、把无来源能耗系数标成已标定、把不同分母的超时率合并。

## 运行时门禁

- Harness 检查 `ActionProposal.observed_revision` 与当前 revision 一致；否则 `STALE_OBSERVATION`。
- 所有 StateDeltaProposal 只允许提交器修改 WorldState；拒绝无效资源占用/超界/负电量/非有限数。
- EventIntent 按 ARCH-02 确定相同 timestamp 的先后顺序和去重；组件不能直接修改。
- MetricProvider 只读取 CommittedFrame，缺值表示 unknown 并携 missing_reason；不能把对未知分母的 0 当成观测结果。
- 超时、初始化失败、close 失败均进入故障账本，不静默回退到另一算法/模型。

## 源码冲突见证

- `frontend/data_source.py:228-485` CSV 缺字段默认 0、GeoJSON 行跳过：构成 `DATA_QUALITY_UNMET` 风险，Legacy Adapter 须显式报告。
- `console/sim_session.py:145-150` 未知算法回退 greedy：新契约下构成 `REGISTRY_UNKNOWN_COMPONENT`，不能默认进入可信实验。
- `frontend/metrics_schema.py:136-149` 无值转 0：新 MetricSample 需要 missing_reason；保留旧报表但不可沿用为新可信定义。
- `results/compare/manifest.json` 已证明多个历史实验族不可比较；必须继承硬门。
- `frontend/route_cost.py` ETA 单位为 env-step，不能标注为 seconds。
