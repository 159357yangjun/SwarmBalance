# 真实性数据集（data/provenance）

版本 1.0.0｜取证日期 2026-10-03｜生成器 `docs/build_truth_dataset.py`（本目录所有 CSV/JSONL 由它生成，请勿手改）。

## 为什么统计不放 MD

原先统计散在 `docs/真实性审计表.md` 的表格里：不可查询、不可 join、改一个数要人肉同步多处。现在每个数是一行带主键的记录，MD 只做人读视图。

## 文件

| 文件 | 行数 | 说明 |
|---|---|---|
| `sources.csv` | 10 | 外部来源登记：完整 URL + 本轮 HTTP 码 + 响应体大小/哈希 + 取证动作 |
| `parameters.csv` | 24 | 每个仿真参数一行：值、单位、A–E 等级、来源原文、测试条件、派生算式、复算命令 |
| `statistics.csv` | 39 | 统计量一行一个：含样本量、计算口径、本轮是否真从文件复算 |
| `wind_hourly.csv` | 1008 | Open-Meteo 杨浦逐小时风场原始数据（1008 行） |
| `osm_census.csv` | 8 | OSM 底图本轮普查计数与文件指纹 |
| `formal_baseline_run.csv` | 30 | n=10 正式基线逐 run 记录（只读复算，未重跑仿真） |
| `truth.jsonl` | 47 | 上述断言的 JSON Lines 形式，供程序逐条消费 |

## 证据等级

| 级 | 含义 |
|---|---|
| A | 厂商官方规格页/手册的直接值 |
| B | 原始公开实测数据（论文/数据集）或本地 run 记录逐行复算 |
| C | 由 A/B 可复算的派生值（附算式，**不得称『官方实测』**） |
| D | 假设值（无外部依据） |
| E | 未验证 / 存在冲突 |

当前参数等级分布：{"A": 8, "C": 3, "D": 8, "D+E": 1, "E": 3, "E->已定": 1}（共 24 个参数）

## 字段字典

### `sources.csv`

| 字段 | 类型 | 含义 |
|---|---|---|
| `source_id` | str | 主键，形如 src_*；被其余表以分号分隔引用 |
| `name` | str | 来源名称 |
| `publisher` | str | 发布主体（厂商/期刊/平台） |
| `url` | str | 完整可点击链接；禁止半段链接 |
| `source_type` | enum | vendor_spec_page|vendor_support_docs|vendor_store_product_page|vendor_product_page|journal_data_descriptor|repository_doi|api_endpoint|crowdsourced_gis|media_secondary |
| `retrieval_date` | date | 本轮亲自打开该页面的日期 |
| `http_status` | str | 本轮实测 HTTP 码；未取到写『未取得』而不是留空 |
| `response_bytes` | int | 本轮实测响应体大小 |
| `sha256` | hex | 响应体或本地文件的哈希；只锁『现在的它』，不锁『当初的它』 |
| `local_file` | relpath | 对应的仓内文件；无则空 |
| `verified_by` | str | 本轮取证动作的一手描述 |
| `notes` | str | 限制与注意事项 |

### `parameters.csv`

| 字段 | 类型 | 含义 |
|---|---|---|
| `param_id` | str | 主键 param_* |
| `drone_type` | str | 所属机型或作用域（(全局)/(地图)/(地面设施)） |
| `field` | str | 代码/配置里的字段名；未建模的以 (未建模) 前缀 |
| `value` | str | 项目当前实际使用的值 |
| `unit` | str | 单位 |
| `evidence_grade` | enum | A 官方直接值 | B 原始公开实测 | C 由 A/B 可复算的派生值 | D 假设值 | E 未验证或冲突 |
| `is_real_measurement` | enum | vendor_stated|real_flight_measurement|derived|assumed|unverified|conflict_unresolved |
| `error_band_vs_source_pct` | str | 项目值与来源值的相对差；无基准时写『不可估』 |
| `source_value` | str | 来源原文的值（逐字或注明未取得） |
| `test_condition` | str | 来源给出的测试条件；缺了就写缺 |
| `derivation` | str | 派生算式全文；C 级必填 |
| `recompute_cmd` | str | 可自行重放的命令；C 级必填 |
| `config_file` | relpath | 值所在配置文件 |
| `status` | str | 在用|在用（假设值）|未建模|仅作派生输入|未入正式表 |
| `notes` | str | 对外禁用表述等 |

### `statistics.csv`

| 字段 | 类型 | 含义 |
|---|---|---|
| `stat_id` | str | 主键 stat_* |
| `dataset` | str | 所属数据集 |
| `metric` | str | 指标名 |
| `value` | float | 数值 |
| `unit` | str | 单位 |
| `n` | int | 样本量 |
| `method` | str | 计算口径（总体标准差 ddof=0 / 分位数取法 / t 区间） |
| `computed_from_file` | relpath | 本轮真实读取并复算的文件；为空表示该值是登记的引用值 |
| `row_count_seen` | int | 本轮实际解析到的行数；-1 表示未从文件复算 |
| `evidence_grade` | enum | 同上 A–E |
| `notes` | str |  |

### `wind_hourly.csv`

| 字段 | 类型 | 含义 |
|---|---|---|
| `time_local` | datetime | Asia/Shanghai 本地时间 |
| `wind_speed_ms` | float | m/s；接口原值为 km/h，÷3.6 换算 |
| `wind_direction_deg` | float | 来向角度 |
| `temperature_c` | float | 2 m 气温 |

### `osm_census.csv`

| 字段 | 类型 | 含义 |
|---|---|---|
| `entity` | str | 统计对象 |
| `count` | int | 本轮解析得到的计数 |
| `total` | int | 分母 |
| `share` | float | 占比；分母不存在时留空 |
| `method` | str | 计数方式 |
| `computed_from_file` | relpath |  |
| `evidence_grade` | enum |  |
| `notes` | str |  |

### `formal_baseline_run.csv`

| 字段 | 类型 | 含义 |
|---|---|---|
| `fixture` | str | C1|C2|S（见 docs/CriticalFixture定义.md） |
| `seed` | int | 配对种子 40901–40910 |
| `repeat` | int | 重复序号 |
| `algorithm` | str | 本轮批次只有 greedy_immediate 有基线 |
| `completed_tasks` | int | 完成任务数 |
| `generated_tasks` | int | 生成任务数 |
| `completion_rate` | float | 完成率 |
| `timeout_rate` | float | 超时率 |
| `total_energy_wh` | float | 总能量消耗 |
| `total_distance_m` | float | 总飞行距离 |
| `avg_latency_s` | float | 平均时延 |
| `evidence_grade` | enum | B = 本地 run 记录逐行复算，非外部真值 |

## 复算

```bash
# 重新生成（会覆盖本目录）
../.venv310/Scripts/python.exe -X utf8 docs/build_truth_dataset.py

# 只校验：重算并与磁盘比对，任一字节漂移退出码 1
../.venv310/Scripts/python.exe -X utf8 docs/build_truth_dataset.py --verify

# 参数级算式核对
python -c "print(1984.4*2, 3968.8/28, 28/16)"
```

## 边界

本数据集只登记『数字→来源→条件→算式→复算命令』的证据关系。A=官方直接值 B=原始公开实测 C=可由 A/B 复算的派生值 D=假设值 E=未验证或冲突。D/E 级字段不得对外称为厂商参数。

`truth.jsonl` 中 `record_type=disabled_claim` 的 8 条为**对外禁用表述**，写论文/答辩稿前先比对这些行。

## 已知未完成项

- CMU 数据集文件本体未取得（KiltHub 403）⇒ 只能支撑定性结论，见 `sources.csv` 的 `src_cmu_kiltub`。
- OSM 下载事件溯源无凭据（时间/操作者/source_url）⇒ `osm_census.csv` 的内容计数为 A，溯源为 E。
- BS60 同时充电数量两页冲突未决 ⇒ `parameters.csv` 的 `param_bs60_charge`。
- `statistics.csv` 中 `row_count_seen=-1` 的行是**登记的引用值**，本轮未从文件复算，不要当成本轮观测。
