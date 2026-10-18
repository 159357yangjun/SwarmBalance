# ARCH-04 / 后向兼容、行为对照、数据防护与回退

> **验收设计**：当前未运行测试，不报告 PASS。基线源 `master@2ab60c69a806a22d7ba20353dee0571752a0e8e5`；PR #41 引入的生命周期/货物监管变化必须另设版本基线，不能直接用其输出认定 adapter 改坏了 master。

## 1. 兼容等级（必须明确标注）

| 级别 | 目标 | 禁止误读 |
| --- | --- | --- |
| K0 静态契约 | 历史配置可解析、旧 API shape/枚举/错误语义记录、旧 CSV header 不变 | 不代表运行等价 |
| K1 相同引擎/相同输入 | 固定 exact commit、同一地图 SHA、相同 OSM 解析模式、依赖版本、配置字节、算法配置、seed、步长、缓存策略、事件注入顺序；新旧路径每步可解释对照 | 不可用换物理或换算法代替 |
| K2 历史场景 | 场景库 `schema_version` 保留并可只读导入；默认 Seed/algorithm/路径解析语义保留 | checkpoint 不自动跨运行/跨结构还原 |
| K3 结果消费 | `METRIC_COLUMNS`、原 CSV 字段/列顺序、`reproducibility.json` 已有键、`compare_gate.py` 拒绝语义均不破坏 | 新侧录指标不可参与旧图的直接比较 |
| K4 不同模型 | 不追求逐字相等；显式不同 model_revision、参数、事件时钟、解析模式与差异机制的因果说明 | 不允许称为“透明迁移” |

## 2. 准入门与最小可执行对照矩阵

| 门 | 输入/试验方式 | 必须保留的判据与失败处理 |
| --- | --- | --- |
| G-M0 / 源与产物冻结 | 锁定 `master` SHA、Python/OS/依赖版本、输入 CSV/OSM 的 sha256、`simulation.json`、`backend_si/config.yaml`、历史对比 CSV SHA | 缺任一关键来源＝BLOCK；禁止更新受保护路径 |
| G-M1 / 配置/路径 | 旧默认地图、显式自定义 OSM、相对导入 CSV/GeoJSON、`SWARM_BALANCE_SIM_CONFIG` 覆写、无效路径/缺键、scene schema 版本错误 | 解析绝对路径、字节 SHA、校验/错误类别逐项比对；静默回退不同文件＝FAIL |
| G-M2 / 决定性单步 | 选取 greedy、ga、pso，ortools 可用时加入；选 0/1/多任务、动态任务注入、静风与有风；同 seed 运行 legacy_direct 与 legacy_harness | 比对 step/time/obs/action/done，任务状态、机巢占用、载荷、电量、轨迹关键点；**同模型任何语义差异必须定位**，不得用宽松阈值吞掉；浮点只按预注册技术容差报告 |
| G-M3 / 故障和生命周期 | 无取货到达终点、重复服务、满仓/低电、禁飞绕障、泊位队列、故障注入和恢复；#41 与 master 分别执行 | 任务“完成”只以对应冻结版本的原逻辑对照；不可跨版本宣称相等 |
| G-M4 / RNG 与隔离 | 固定 seed 重跑 3 次、串行两 world、不同 seed 交错、冷/热 OSM 缓存对照；隔离 worker 运行 | 同条件应可重复；若不重复记录首次分叉 step + RNG/配置/线程上下文，不可解释时 BLOCK |
| G-M5 / 历史场景与快照 | 导入场景库合法/非法 schema、演示 patch + restore、旧 checkpoint 保存/恢复/跨代拒绝 | 场景配置不丢失；旧 checkpoint 的“当前进程、不可跨代”承诺不升级；跨代拒绝不得转为自动恢复 |
| G-M6 / 结果 | 运行固定预设 dry-run、短 run、E0 基线/静风 E1 同配置配对；验证 raw_runs/plan/reproducibility & compare gate | 历史结果 SHA 保持；主表顺序/计算相同；静风等价门按已冻结研究合同；门禁拒绝被绕过则 FAIL |
| G-M7 / 回滚 | 旧入口实际运行；feature flag 关闭；中断新 worker；模拟无权限写/OSM 缺失/adapter 拒绝 | 切回旧入口无需 schema rollback、恢复旧配置/只读结果；新路径失败不能使旧路不可启动 |

**容差规则**：每项浮点观测使用测试前声明的容差（原则上相同进程、相同依赖和执行顺序下预期一致；若使用 abs/rel 容差，需要写明量纲、原因、阈值、最大观测差及首次偏差步骤）。不得事后根据结果调阈值。统计率同时验证分子和分母，不能仅验证展示百分比。

## 3. 对照记录结构与判定

每次 paired run 输出仅到 **新建隔离目录**，建议：`results/platform_runs/<run-id>/{manifest.json,steps.jsonl,comparison.json,diagnostics.json}`（目前尚未实现）。至少保存：
- `run_id`、`mode`、`engine_commit_sha`、`adapter_commit_sha`、`algorithm_key`、`seed`、`config_sha256`、`algorithm_config_sha256`、`osm_sha256`、`osm_parser_mode/version`、`python/os/dependency versions`、`cache policy`。
- 每步输入 observation 和决定 action 的稳定规范化哈希，`env.current_time`、状态/事件、动作和由原内核给出的统计量；任何 hash 差异先输出关键实体字段 diff。
- 首个 divergent step、哪一层先分叉（输入/调度动作/模型推进/格式化/统计）、是否配置了新模型；未解释差异为 BLOCK。
- `comparison.json` 写明判定者、容差、可复现命令与源 commit。禁用“因统计显著性/平均值相近而自动放行”相同模型的逻辑不一致。

## 4. 历史数据/配置的绝对保护线

1. 旧 `config/simulation.json` 与 `backend_si/config.yaml` 保留原文件；新配置迁移**只读加载→验证→输出独立转换版本**；校验 manifest 包括解析后的绝对路径，禁止用当前目录碰运气。
2. `config/scenes/*.json`：场景导入器保留旧 schema_version/算法/Seed；未知字段显式保留或拒绝，不可默默删除；演示可逆 patch 与普通场景库分开。
3. 旧 `SimSession.save_checkpoint` 基于 deepcopy 和 Python/NumPy RNG，仅本进程使用。新平台不得承诺将旧内存快照直接序列化跨版本恢复；跨代/跨模型默认拒绝。
4. `results/compare/*.csv`、`manifest.json`、`README.md`、`results/experiments/*` 只读；不得对旧结果“补上平台字段”后回写。任何新增元数据以 sidecar 挂载；`results/compare_gate.py` 与 `frontend/metrics_schema.py` 保留。
5. PR #41 的 `Environment`/`Drone` 和模型溯源差异必须另行对照。新平台的可比性键至少包含 `engine_commit_sha` 和 `model_revision`，不允许只用 “same seed” 判断同一实验。

## 5. 科研结果改变风险登记册（全部属于变更阻断点）

| 风险 | 可能变化的科研量 | 触发动作 | 最小反证 |
| --- | --- | --- | --- |
| R01 物理参数被默认化 | 总能耗、续航、低电事件 | config 转换/模型构造 | 配置参数逐字段、单位和数值一致 |
| R02 OSM 模式/坐标/缓存改变 | 路程、绕飞次数、能耗 | SpatialProvider 替换 | 地图哈希、EPSG/单位、障碍集合、规划路线对照 |
| R03 时间/事件先后改变 | 送达/超时/排队 | Harness step/事件队列 | 首分叉 step 的 action/clock/terminal 状态 |
| R04 调度器抽象破坏 Greedy 特例 | 任务匹配、完成率 | SchedulerAdapter 转发 | 决策 action 序列一致 |
| R05 RNG 共享/重置 | 需求到达、PSO/GA 收敛、配对优势 | 多会话或 checkpoint | 隔离重跑 + RNG 状态不串扰 |
| R06 任务状态/交付守卫变更 | 合法送达数、超时率 | 合入 #41 或 adapter 自行修补 | 版本分桶并逐实体核对，不允许跨基线推论 |
| R07 任务规模隐性上限/场景默认 | 分母与完成率 | 转换 preset、调大负载 | 请求任务数、实际生成数、阈值逐项记录 |
| R08 指标列或统计口径变更 | 全部研究指标/论文图 | MetricProvider 替换 | 原 schema、分子/分母、门禁完全保留 |
| R09 自动覆盖历史结果 | 可重现性与证据链 | 新 runner 输出到旧 compare 路径 | 旧 SHA 清单写前后相同 |
| R10 失败自动降级不留痕 | 模型身份和可信度 | osmnx 回退/ortools 缺失/worker 崩溃 | 明确失败和 model identity，不允许静默换路径 |
| R11 checkpoint 跨版本恢复 | 动态状态/轨迹/后续统计 | WorldState 导入 | 结构+代码+模型强指纹，不匹配拒绝 |
| R12 并发交错 | step 序列/事件日志/历史指标 | 多请求与多运行并发 | 单 worker 串行提交、无共享可变状态 |

## 6. 回退开关与程序

- **S0–S2**：新路径不接旧 Web；回退是不开启新独立 worker，直接使用未修改的 `python -m console.run` 或现有 `experiments` 入口；验证旧源 SHA/输出路径。
- **S3–S4**：引入选择开关 `execution_mode=legacy_direct|legacy_harness`（建议默认前者）；启动失败自动阻断新路而**不重写原配置**，用户显式返回 legacy_direct。
- **S5–S6**：新结果只写到平台目录；回退为关 flag/销毁新 worker/保持历史结果只读；若新 schema 已有持久数据，不做就地逆迁移，保留版本清单和只读导出。
- 回退不允许自动偷偷变更其他模型/风参数；必须记录退回发生点、触发原因、尚未完成的 run 清单与原旧路径健康核验结果。
