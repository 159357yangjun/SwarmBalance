# ARCH-03｜数据和模型血缘声明（草案）

## 1. 职责关系

`ProjectConfig` 表示用户“选用哪份数据/模型/组件及其显式参数”，`DatasetManifest` 说明外部/生成数据从何而来、是什么格式、质量如何、怎样转换，`ModelManifest` 说明公式/状态变量/适用条件/标定与未验证假设。运行装配冻结 `EffectiveAssemblyManifest`，将以上 **内容 digest** 锁定；配置本身不得替代来源证据，来源 manifest 不得从结果文件反推可信度。

## 2. DatasetManifest JSON 示例（非现有 OSM 的真实元数据）

```json
{
  "schema_version": "0.1.0",
  "dataset_id": "example.map.test",
  "revision": "1.0.0",
  "content": [{"uri":"project://datasets/map.osm", "media_type":"application/xml","sha256":"REQUIRED_REAL_DIGEST"}],
  "origin": {"organization": "REQUIRED", "url": null, "retrieved_at_utc": null, "license": "REQUIRED"},
  "evidence": {"grade":"E", "traceability":"None", "transformation":"As-published", "claim_scope":"unverified"},
  "spatial": {"crs":"REQUIRED_EPSG_OR_WKT", "axis_order":["x","y"], "coordinate_unit":"m", "vertical_datum":null, "coordinate_transform_record":null},
  "time": {"time_basis":"not_applicable","timezone":null,"sampling_interval_seconds":null},
  "fields": [{"path":"buildings.height","type":"number","unit":"m","nullable":true,
              "missing_policy":"propagate_missing","quality_flag":"unverified"}],
  "quality": {"total_records":null,"invalid_records":null,"missingness":{}, "validation_report_uri":null},
  "assumptions": [], "known_limitations": ["example only, not executable"]
}
```

缺少 CRS/许可证/真实 digest 的示例不得通过 strict 验证。真实 GeoJSON 经纬度一般要进行明确 CRS 转换，不能把 `[lon,lat]` 数值直接作为米制 `x,y`。OSM 高度的 `height`、`building:levels` 与未知高度必须保持三态区分；不能没有根据就假定 0 或固定层高。任务坐标、飞行高度和三维避障必须分别确认投影与垂直基准。

## 3. ModelManifest JSON 示例（仅待审议概念）

```json
{
  "schema_version": "0.1.0", "model_id":"example.energy.scenario",
  "revision":"0.1.0", "implementation_digest":"REQUIRED_REAL_DIGEST",
  "component_contract":"DynamicsModel@0.1.0", "intended_use":"simulated flight energy",
  "state_variables":[{"name":"battery_energy","unit":"Wh"}],
  "inputs":[{"name":"segment_distance","unit":"m"}, {"name":"payload_mass","unit":"kg"},
            {"name":"wind_along","unit":"m/s","sign":"positive means headwind"}],
  "outputs":[{"name":"energy_delta","unit":"Wh"}],
  "equations":[{"id":"scenario-linear", "expression":"distance * base * load_factor * wind_factor", "status":"assumed"}],
  "parameters":[{"name":"base", "unit":"Wh/m", "value":null,"source_ref":null, "evidence_grade":"E"}],
  "assumptions":["scenario coefficient, not calibrated physics"],
  "calibration":{"dataset_refs":[],"method":"none","status":"not_calibrated"},
  "validation":{"checks":[],"limits":["no physical-accuracy claim"]},
  "domain":{"speed_range_mps":null,"wind_range_mps":null,"payload_range_kg":null},
  "uncertainty":{"type":"not_quantified"}, "randomness":{"deterministic_given_seed":true}
}
```

历史 `frontend/drone.py:152-205` 使用 `current_load` 参与耗电，`frontend/environment.py` 的载货里程通过航段归属判断；两者口径尚存争议。ModelManifest 必须把“派单载重”与“实际载货”定义不同输入；未统一不得声称 Wh/km 的实证结果，不能让默认能耗模型冒充物理真值。风场 `u,v`、风速单位与符号约定不可省略。

## 4. 数据校验/缺失策略

- 字段级区分 `missing`、`invalid`、`not_applicable`、`estimated`；不得用零代替未知，也不得因空值自动使用车队默认值。
- 可选策略：`reject`（strict 硬字段）、`quarantine`（不参与可信运行）、`propagate_missing`（可下游处理），或 `impute_explicitly`（附方法、来源、责任人、质量降级和衍生 digest）。没有“silent fallback”策略。
- 提供校验报告：总行数、跳过与隔离行、每字段缺失率、样本/主键唯一性、空间边界/几何有效性、单位/范围、转换流水线版本和生成前后 digest。
- 任何数据源外部采集必须存取时间、授权与可用性、原始哈希；回放需固定快照，不在运行中不记录地重新拉企业接口。

## 5. 与仓内现有证据的关系

`data/provenance/manifest.json` 已区分 evidence_grade (A/B/C/D/E)、traceability (Complete/Partial/None)、transformation (As-published/Derived/Local-extraction/Assumption)。新 manifest 应保留其三轴信息，而非把“完整溯源”误当“物理准确”。`results/compare/manifest.json` 记录不同指标 schema、实验族、seed_set 和不可比关系；MetricSample/结果 manifest 必须依照来源与实验协议进行 comparability gate。现有 `frontend/data_source.py:228-485` 的 CSV 数值自动兜底、GeoJSON 跳过记录只列为 Legacy Adapter 风险，绝不认定该路径自然达标。

## 6. 冲突/强制拒绝

没有 dataset digest `MANIFEST_DIGEST_MISSING`；坐标不匹配且无显式转换 `CRS_MISMATCH`；来源未知且请求 trusted-only `UNTRUSTED_SOURCE`；模型输入质量不达标 `MODEL_INPUT_QUALITY`；参数超出 model domain `MODEL_OUT_OF_DOMAIN`；混用不可比指标 `METRIC_NOT_COMPARABLE`。错误报告须含受影响 run/组件/字段和修复建议。
