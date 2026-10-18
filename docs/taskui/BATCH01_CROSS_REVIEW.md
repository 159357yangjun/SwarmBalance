# Batch 01 交叉复核报告：UI-00 × UI-02 × master 源码

> 交付：TASKUI-SB-B01-CROSS-REVIEW · 2026-10-15 · **仅静态交叉复核，不是 UI/E2E 运行验收**  
> 复核人：独立交叉复核 AI · 目标：G0 文档/契约一致性判定；G1 设计输入校正  
> 裁决：**G0 HOLD（不通过，待差异登记与 P0 处理方案被批准）；G1 不得以本报告充当运行验收。**

## 0. 审计边界、冻结点与读取范围

| 证据主体 | 精确 SHA | 本轮访问范围 |
|---|---|---|
| `master` 真实代码 | `2ab60c69a806a22d7ba20353dee0571752a0e8e5` | `console/static/index.html`、`console/server.py`、`console/sim_session.py`、`console/experiment_service.py` 等只读 |
| `ui/taskui-00-audit`（PR #43） | `a0983f62013335ad6f96ed4e88a68ea8021b7b1b` | `docs/taskui/audit/` 六份 Markdown，只读 |
| `ui/taskui-02-requirements`（PR #44） | `7636e09f8e5f2cb46cf9360a6be722ad269f8fc1` | `docs/taskui/requirements/` 六份 Markdown，只读 |
| `ui/taskui-b01-cross-review` | 写入前 `2ab60c69a806a22d7ba20353dee0571752a0e8e5` | **仅新增本文件**，不得纳入源分支或修改 UI / kernel |

核验：GitHub branch API 确认四个 HEAD；GitHub compare API 确认 UI-00 与 UI-02 的 merge-base 均是上述 master，均 ahead 6/behind 0，各自 diff **只包含六份 Markdown**。PR #43/#44 均为 open Draft，未合并。UI-00 六份：`BASELINE.md`、`FRONTEND_ARCHITECTURE.md`、`FUNCTION_ENTRY_MATRIX.md`、`PAGE_INVENTORY.md`、`PROTECTED_BOUNDARIES.md`、`UI_ISSUES.md`。UI-02 六份：`INFORMATION_PRIORITY.md`、`TASK_FLOWS.md`、`TASK_INVENTORY.md`、`USER_ROLES.md`、`UX_ACCEPTANCE_CRITERIA.md`、`WORKSPACE_REQUIREMENTS.md`。

方法：逐份阅读、按 T01–T24 与 F01–F09 对齐 UI-00 功能清册，然后用 master 精确 SHA 的模板、methods、路由和服务状态输出核实。`I/S` 意味着**静态存在**，不意味着点击成功；`U`=未见实现，`P`=受限；`H`=待实测假设。未启动控制台/浏览器/仿真、未修改配置或运行实验；不得引用 #41 的绿色 CI 为本 SHA 运行通过的证据。证据中的行号均指 master SHA。

## 1. 任务—入口—前端方法—API—状态—风险追踪

下表**不是**“所有能力已验收”的声明；`snap` 是 `SimSession.snapshot` 的当前世界（`console/sim_session.py:663-685`），`tab/showMap` 是浏览器本地视图，`compare` 是独立历史 CSV。表中“可用性”以源码静态路径为准，方括号里的 X ID 为本次差异。

| 任务 | 实际界面入口（UI-00 / UI-02） | 方法 → API / 服务来源 | 状态与风险 / 交叉结论 |
|---|---|---|---|
| T01 算法、Seed、重置 | 全局顶栏 | `onAlgorithmChange`（空）/ `reset` → `POST /api/reset`；`SimSession.reset` | `algorithm/seed` 待应用，`snap.algorithm/seed` 实际值；重置世界 R；静态 I |
| T02 播放、暂停、单步、倍速 | 全局顶栏 | `togglePlay/stepOnce/advance/playTick/setSpeed` → `POST /api/step` | `playing/stepping/stepSeq/snap.done`；暂停客户端循环，停止过期响应写回；I |
| T03 地图、航迹、2D/3D | 实现层 + 顶栏切换 | `draw2d/draw3d/switchView` → `GET /api/map`、`/api/snapshot` | `showMap/view/mapStatic/snap/trajectories`；I |
| T04 任务/无人机/机巢详情 | 地图命中、控制列表、事件 | `selectEntity/selectFromEvent`，`selectedTask/Drone/Nest` computed；从 `snap.task_catalog/drones/nests` 读取 | `selection` 本地；检查器只在 `v-show=showMap` 的地图内；I **但控制层不可见** [X04] |
| T05 插入任务、地图取点 | 顶栏/控制层“新任务”模态 | `openTaskModal/startMapPick/submitTask` → `POST /api/tasks/inject` | `taskForm/mapPick/snap`；运行态插单 D；非地图页取点 [X03]，提交后的视图反馈 [X06] |
| T06 编辑 pending 任务 | 地图任务检查器（非控制列表本身） | `saveTaskEdit/promoteTaskEmergency` → `PATCH /api/tasks/{id}` | `selectedTask.status=pending/taskEdit`；I，控制层选中不能直接见编辑 [X04] |
| T07 候选解释 | 地图任务检查器 | `loadTaskCandidates` → `GET /api/tasks/{id}/candidates` → `SimSession.task_candidates` | `taskCandidates` 只针对 pending；I，控制层入口不可见 [X04] |
| T08 暂停/恢复自动订单流 | 控制层实时调度状态 | `setTaskStream` → `POST /api/task-stream` | `snap.controls.task_generation_paused`；不是暂停飞行；I |
| T09 任务链、机巢队列、事件 | 控制层列表/日志、地图详情 | `snap.drones/nests/events` → `GET /api/snapshot` | `events` 服务端最近 80 条，UI 日志 30 / 坞 12；控制层任务链项不可直接选任务 [X05] |
| T10 无人机补能 | 地图无人机检查器 | `requestDroneCharge` → `POST /api/drones/{id}/charge` | `incidentBusy/incidentError/snap`；地图页失败反馈不可见 [X07] |
| T11 停飞/恢复、机巢关闭/开放 | 控制层随机注入、地图实体检查器 | `setDroneIncident/setNestIncident/random*` → 两个 `POST /api/*/incident` | `snap.drones/nests`；随机关闭至少留一个；失败展示 [X07] |
| T12 基础配置/调度超参 | 顶栏“配置”模态 | `openConfig/saveConfig` → `POST /api/config` → `POST /api/scheduler-config` → `POST /api/rebuild` | `cfg/algo` 写两类文件，再重建；非原子 R [X11] |
| T13 编辑机巢/禁飞区 | 顶栏“场景编辑”模态、2D 取点 | `startScenePointPick/saveSceneLayout` → `POST /api/scene-layout` | `sceneDraft/mapPick`；仅 random 可写，写后重建；非地图页取点 [X03] |
| T14 初始场景库 | 顶栏“场景库”模态 | `load/save/import/export/delete/applySceneLibrary` → `/api/scene-library*`；`scene_library.py` | `config/scenes` 持久初始配置，apply 重建 R；I |
| T15 演示预设、下一幕、恢复 | 数据处理展示层 | `loadScenarios/applyScenario/advanceScenario/restoreScenario` → `/api/scenarios*` | 临时备份/写主配置，重建 R；与实验隔离不同；I |
| T16 动态快照 | 数据处理展示层 | `saveCheckpoint/loadCheckpoint/deleteCheckpoint` → `/api/checkpoints*` | `SimSession._checkpoints` 进程内最多 5 个、环境代检查，替换当前世界 R；I |
| T17 实时 KPI 与趋势 | 数据处理展示层 + 实时坞 | `drawChart/drawGauge/drawFleetPie` + `snap.stats/health/history`；`GET /api/snapshot` | 世界态即时指标，能耗 UI 为 kWh，非离线算法 CSV；I |
| T18 一键实验及状态 | 算法层（`tab=compare`） | `ensureExperimentData/runExperiment/loadExperimentStatus` → `/api/experiments/{presets,start,status}` | `experimentStatus` 子进程/状态文件，轮询故障静默 [X10] |
| T19 离线算法对比 | 算法层图表/读数表 | `loadCompare/drawCompare/drawRadar/drawRank/compareBestRow` → `GET /api/compare`、`compare_gate` | `compareRows/Comparable/Refusal`；**仅部分视图守门** [X01]，空值可变 0 [X02]，来源“最新”语义 [X12] |
| T20 正式证据包 | 算法层实验区 | 下载链接 → `GET /api/experiments/package` | `conclusion_package_available` 为真时显示；与当前快照无关；I |
| T21 规范 / 使用引导 | “规范”左导航 + 顶栏“使用引导” | 规范 iframe → `GET /spec`；引导 `showGuide/closeGuide`，localStorage，无 API | UI-02 T21 只登记规范，未把引导单列/子项映射 [X13] |
| T22 任意历史两批比较 | 无可见选择器 | 无独立 batch 选择 API；当前 `/api/compare` 只按固定 CSV 列表择行 | **U**；G1 不得视为已有功能 |
| T23 动态快照跨进程落盘 | 无 | `SimSession._checkpoints` 是内存结构 | **U**；不能把 scene-library 混同 |
| T24 任意 CSV/GeoJSON 机巢几何手编 | 场景编辑可打开、提交受限 | `saveSceneLayout` → `/api/scene-layout` 对非 random 拒绝 | **P**；不创建新的 CSV/GeoJSON 编辑 API |

补充：当前浏览器 UI 真实入口是 `console/static/index.html` + Vue 3 全局构建、Canvas、Three、ECharts；`frontend/*.py` 是仿真内核，不能当成 Web 组件。UI-00 的 17 项 UI_ISSUES 基本被 UI-02 的 W/A/F 需求分组吸收，**不代表其每个故障路径已被逐项验收**。本报告以下专记交叉复核发现的新缺口、相互表述不一致和仍未闭环的验证问题。

## 2. 差异总账（15 项；P0=2，P1=9，P2=4）

“阻断 G0”表示**不能据当前交叉文档直接签署静态契约完整/安全通过**；并非授权本 PR 修改源码。静态推导的执行结果标明“条件风险/待浏览器重现”，但源码中的缺口是可直接定位的。

| ID | 严重度 | 类别 | 涉及任务 | 阻断 G0 | 差异简述 |
|---|---|---|---|---|---|
| X01 | **P0** | 安全门禁覆盖遗漏 | T19/A08/W09 | **是** | `comparable=false` 只清柱状图，不清先前雷达/排行，可能保留错误比较视觉 |
| X02 | **P0** | 缺失数据当零值 | T19/A08 | **是** | 排行、雷达和表格最优逻辑 `Number(null)===0`，与柱图缺失值断柱契约冲突 |
| X03 | P1 | 功能流程遗漏 | T05/T13/F02/F04 | **是** | 从非地图页启动地图取点，不会设 `showMap=true`，取点画布不可见 |
| X04 | P1 | 入口/实际可达性不一致 | T04/T06/T07/A03 | **是** | 控制页选择 ID 只更新 `selection`，详情/编辑/候选都在被隐藏的地图检查器 |
| X05 | P1 | 任务链对象链接过度声明 | T04/T09/F07 | **是** | 控制页链 `t.task_id` 文本没有独立任务点击处理，点击整行只选 drone |
| X06 | P1 | 提交后路径歧义 | T05/F04 | 否 | `submitTask` 设置 `tab=dispatch` 却不改变 `showMap`，不同发起页得到不同可见反馈 |
| X07 | P1 | 失败提示不可见 | T10/T11/W10 | **是** | 地图详情故障/补能失败设置 `incidentError`，报错 UI 仅在控制层渲染 |
| X08 | P1 | 非原子恢复下的快照陈旧 | T11/A04 | **是** | `restoreAllIncidents` 在异常时未 `applySnap` 已成功的部分返回，屏幕可能暂显旧状态 |
| X09 | P1 | 初始化故障缺验收闭环 | T01/T03/A01/W10 | **是** | `init()` 失败时 `finally` 消掉 loading，无统一可见启动失败及恢复路径 |
| X10 | P1 | 实验轮询故障缺契约 | T18/A08/W10 | **是** | `loadExperimentStatus` 异常仅 `console.warn`，可能继续显示旧进度 |
| X11 | P1 | 已知非原子副作用 | T12/A05 | 否（**已登记风险**） | `saveConfig` 三个独立请求，失败时真实文件/环境可能不同步；不得宣称已有事务 |
| X12 | P2 | 数据时间语义过度声明 | T19/F09 | 否 | “最近/最新”实际是固定文件顺序 + 每算法最后非空行，不等于时间戳最新批次 |
| X13 | P2 | 功能台账遗漏 | T21/A10 | **是** | 使用引导有独立顶栏入口、本地存储行为，台账却只追踪 `/spec` |
| X14 | P2 | 文档之间的依赖/优先级歧义 | UI-00/UI-02 | 否 | UI-02 仍写 UI-00 “未可访问/未收到”，P0-H 优先级易误读为 P0 已证实 bug |
| X15 | P2 | 未测证据不得冒充 G1 通过 | F01–F09/A01–A10 | 否（但阻断 **G1 运行结论**） | 无浏览器走查、同条件对照或界面截图，不能宣称任务效率改善/行为验收 |

### 2.1 每项直接证据、差异范围与修复建议

**X01 — P0 — 比较拒绝后图形残留（G0 是）。** UI-00 `PROTECTED_BOUNDARIES.md`“可比性/指标定义”和 UI-02 `WORKSPACE_REQUIREMENTS.md` W09、`UX_ACCEPTANCE_CRITERIA.md` A08 均要求不可比时无胜者/雷达/排行。源 `console/static/index.html:2701-2729`：`loadCompare` 可把 `compareComparable` 置 false；`drawCompare` 只获取并清空 `#compare` 实例，立即 return；`drawRadar:2750-2814` / `drawRank:2817-2851` 均未检查 comparable。`index.html:987-997` 的两图容器仍在。**条件风险**：先有可比绘图、再刷新为不可比时，旧雷达/排行可能留在 DOM；未做浏览器重现。**修复建议**：未来 UI PR 在 gate=false 时显式 clear 三图或全图受 gate 条件渲染；添加“可比→不可比刷新”回归，拒绝提示保留原始读数。禁止修改 compare_gate 本身来掩盖 UI 问题。

**X02 — P0 — 缺失指标被绘制/排成 0（G0 是）。** `index.html:1430-1447` `compareBestRow` 用 `Number(r[m])` 后 `isFinite` 筛选；`index.html:2765-2774` 雷达 `num=(r,k)=>Number(r[k])`；`index.html:2817-2846` 排行 `Number.isFinite(Number(r[m]))`；JS 中 `Number(null)===0`。但 `index.html:2736-2744` 柱图正确保留 `null` 并断柱。`server.py:944-978` 用 `_clean` 将 NaN/Infinity 转 null，真实数据可出现缺列/空值。**条件风险**：列集合存在但某算法读数缺失时，雷达/排行/表格高亮可能制造“已测得零”结论；是否在当前磁盘 CSV 中触发需独立复现。**修复建议**：所有图/最优行统一使用 `v===null||v===undefined||v===''` → null 的解析器，缺失项不得被排名或归一化为 0；加包含混合 schema/空字段的契约夹具。

**X03 — P1 — 从非地图页取点不可达（G0 是）。** `index.html:665-674` 地图根容器 `v-show="showMap"`；`index.html:2002-2013` `startMapPick` 仅 `showTaskModal=false;view='2d';mapPick.active=true`；`index.html:1819-1825` `startScenePointPick` 同样仅设 `view='2d'`；`goPage:2663-2687` 才改变 `showMap`。UI-02 `TASK_FLOWS.md` F02/F04 和 `TASK_INVENTORY.md` T05/T13 将地图取点当成连续可执行步骤，却未声明“须预先处于实现层”。**静态必然条件**：若从控制/数据/算法/规范页打开顶栏模态，结束模态后 `showMap` 仍是 false、横幅与 Canvas 隐藏。**建议**：未来 UI 任务在取点启动时原子保存前一工作区并跳 `goPage('impl')`，完成/取消再返回；G0 文档先纠正可达性标签，G1 脚本覆盖所有入口页。

**X04 — P1 — 控制页选中不等于看见详情（G0 是）。** `index.html:933-979` 控制页列表/事件仅 `selectEntity`；`index.html:1676-1699` `selectEntity` 更新 selection、候选；`index.html:665-783` inspector 属于 `showMap` 容器，`goPage('control')` 设 false。UI-00 `UI_ISSUES.md` UI-01 已准确警示；UI-02 虽在 T04 注释中说明，但 `TASK_INVENTORY.md` T06/T07“选任务→检查器”、`TASK_FLOWS.md` F04/F07 仍存在把“选中/可编辑/可解释”合并为单步的歧义。**建议**：T04/T06/T07 区分“选择状态已写入”和“详情/按钮当前页可见”；G1 设计独立详情宿主或显式跳地图并保留 ID；A03 专测 pending 列表→候选/编辑。

**X05 — P1 — 控制任务链不可直接选其任务（G0 是）。** `index.html:959-973` 无人机行 `@click="selectEntity('drone',d.id)"`，其内部 `v-for t in d.task_chain` 只输出 `t.task_id` 文本，无独立 click/stop。`index.html:691-700` 地图无人机 inspector 中的任务链才有 `@click="selectEntity('task',t.task_id)"`。UI-02 `TASK_FLOWS.md` F07 “也可控制层从……任务链……选中对象”暗示了不存在的链内任务链接。**建议**：将该句改为“控制层选无人机，链内任务只能进入地图 inspector 再点”；后续设计若新增控制页内链点击需单独实现/验收，不得先记为已实现。

**X06 — P1 — 插单成功后可见页取决于起点（G0 否）。** `index.html:2523-2545` `submitTask` 只 `this.tab='dispatch'`，没改 `showMap`；`index.html:2663-2687` 由导航独立控制显示。F04 仅说“tab 切至 dispatch”，读者容易以为总会看见控制页任务列表。**建议**：报告/流程区分从地图与非地图页发起；G1 决定成功后去列表还是停地图并显示任务 ID 的结果反馈，不能以只写 tab 视为导航完成。

**X07 — P1 — 实体干预错误消息隐藏（G0 是）。** `index.html:703-710,732-738` 地图详情按钮发起补能/故障/机巢关闭；`index.html:1711-1719,1737-1760` catch 仅写 `incidentError`，仅成功才写 `tab='dispatch'`；模板 `index.html:920-929` 的 `incident-note v-if="incidentError"` 位于 `tab='dispatch'` 且 `showMap=false` 的区域。地图 inspector 未找到对应的 `incidentError` 渲染。UI-00 `UI_ISSUES.md` 登记了部分故障反馈，却未单列这一**跨工作区失败不可见**路径；UI-02 W10/A04 需要覆盖。**建议**：统一带对象 ID 的操作反馈宿主或在当前 inspector 可见展示；补充地图发起失败、服务端 400 与网络断开用例。

**X08 — P1 — 恢复全部部分成功后快照可能陈旧（G0 是）。** `index.html:1778-1792` 顺序执行多个 POST、循环结束才 `this.applySnap(snap)`；中途任意请求抛错则直接进入 `catch`，此前成功的响应没有更新前端快照。UI-00 UI-09 识别“非原子”，UI-02 A04/W10 未明确验证前端“失败后重新取真实状态”。**建议**：文档要求失败后 `GET /api/snapshot` 与真实已恢复对象对齐，并列出部分完成的目标 ID；未来实现不可把“恢复全部”包装成事务。

**X09 — P1 — 首屏失败缺明确视觉状态（G0 是）。** `index.html:1851-1879` `init` 内 `/api/meta` 异常被吞，`/api/snapshot` 或 `/api/map` 异常进入 `finally{loading=false}`，没有初始化 catch/重试 UI；`index.html:665-671` loading 层由该布尔值控制。UI-00 UI-06 识别；UI-02 W10/A01 的运行控制检查不足以替代“初始化失败/部分数据不可用/可重试”的单列脚本。**建议**：将首屏状态列入 G1/A01 的失败态契约，并在未来 UI PR 做可见重试、数据不完整禁止误操作；不擅改服务端预热逻辑。

**X10 — P1 — 实验状态轮询可能显示过期状态（G0 是）。** `index.html:2943-2953` `loadExperimentStatus` 的 catch 仅 `console.warn(e)`，`startExperimentPolling` 仍按 1.5s 定时；`index.html:1011-1038` 进度会显示最后一次成功状态。UI-00 UI-07 记录了这一问题，UI-02 `UX_ACCEPTANCE_CRITERIA.md` A08 强调结果口径但未明确断网/状态接口错误时应标记“失联/读数过期”。**建议**：加入实验状态失联/数据刷新时间/再次尝试用例；结果归属、完成状态不能从旧轮询值断言。

**X11 — P1 — 分段配置变更（G0 否，已有明确保留风险）。** `index.html:2577-2609` 连续调用 `POST /api/config`、`/api/scheduler-config`、`/api/rebuild`，`server.py:667-805` 分别持久更新；中途失败缺跨文件/重建总回滚。UI-00 UI-08 与 UI-02 F02/A05/W10 已明确识别，**不应再次伪报为首次遗漏，也不能因文档承认就算已修复**。**建议**：G1 前记录部分提交情景、独立风险接受者；若要修事务需授权单独 API/回归 PR，禁止在此文档分支修服务端。

**X12 — P2 — 对比“最新”含义不可靠（G0 否）。** `server.py:848-855` 固定 `_CSV_FILES` 顺序，`server.py:897-921` 拼接后 `drop_duplicates('算法',keep='last')`；这只保证“后遍历文件/后行胜出”，不按时间戳比较多个批次。UI-00 `FUNCTION_ENTRY_MATRIX.md` 已说“历史 CSV”，UI-02 `TASK_FLOWS.md` F09、`TASK_INVENTORY.md` T19 使用“最近一次/最后有效行”易误当最新运行。**建议**：G1 统一称“固定来源顺序选取的当前登记读数”，显示每算法来源文件和批次标识；无新批次索引 API 不可宣称时间最新。

**X13 — P2 — T21 遗漏使用引导子能力（G0 是）。** `index.html:625,1289-1301,1595,1863-1868` 有“使用引导”顶栏按钮、弹窗和 `localStorage` 首次展示规则；UI-00 `PAGE_INVENTORY.md` 已记录。但 UI-02 `TASK_INVENTORY.md` T21 只列“查看世界设计规范 → /spec”，`UX_ACCEPTANCE_CRITERIA.md` A10 以 T01–T24 宣称功能覆盖。**建议**：T21 划分 T21a 规范和 T21b 本地引导，并为首次/再次打开/不影响仿真做简单静态或 G1 测试；无需新增 API。

**X14 — P2 — 交叉材料互不校验/优先级术语不齐（G0 否）。** UI-02 `TASK_INVENTORY.md` 开头和 `UX_ACCEPTANCE_CRITERIA.md` A10/G1 条件记载“未收到 UI-00”，当前 GitHub 可读 UI-00 PR #43、UI-02 PR #44，基线相同；这是**交付时点差异**，不是证明 UI-02 当日撒谎。UI-00 `UI_ISSUES.md` 的 P0/P1/P2 是故障严重度；UI-02 `TASK_FLOWS.md` “P0-H”是设计优先顺序 + 未验证假设，不能混同为源码已证实 P0 安全故障。**建议**：用本报告消除依赖，后续 G0 使用独立的“严重度/优先级/证据等级”三列。

**X15 — P2 — 缺实测，不能签 G1 行为验收（G0 否、G1 是）。** UI-00 `BASELINE.md` 明确无服务启动/截图；UI-02 `UX_ACCEPTANCE_CRITERIA.md` A01–A09 全为 NOT MEASURED，F01–F09 只是路径脚本。**建议**：至少在固定同 SHA、seed、视口、数据源下运行 F01–F09；特别执行“可比→不可比”、缺失指标、非地图页取点、控制页对象候选、恢复全部中途失败、实验轮询断线；没有证据时不能写 PASS 或声称可用性提升。

## 3. 交叉覆盖和未超出设计范围的判据

- **已对齐**：UI-00 把真实 SPA 识别为单 HTML/Vue3 内联而非 `frontend/*.py`；UI-02 没有假造新 API；T22/T23=U、T24=P；服务端快照、持久初始场景、进程内动态 checkpoint 和演示备份是三种不同语义；全局算法为待 reset 值；实验子进程不等于当前 `SimSession`；UI-00/UI-02 都要求 `compare_gate` 不能退化。
- **必须区分“功能存在”和“路径闭合”**：T01–T21 的主要源码入口/API 可以追溯，但 T04/T05/T06/T07/T09/T10/T11/T13/T18/T19 的用户上下文或异常分支并未完整证明可用；不该把 I/S 扩大解释为通过 A01–A10。
- **设计建议的合法边界**：W01–W10 的“地图主区/可关联详情/分域参数/来源门禁”可以留作 **G1 候选**；它们不是现有页面或决定好的布局。不得以“默认提供 T22 任意批次选择器”“T23 快照落盘”“非 random 随意编辑几何”“用户角色登录权限”“新增历史事件检索接口”作为已批准功能。UI-02 T21b 只补清册，不引入业务新能力。
- **禁止越界实施**：即使 X01/X02 是 P0，本交叉报告仍只建议将其指派到**单独前端修复/验证任务**，不能借复核修改 `console/static/index.html`、`console/server.py`、`console/sim_session.py`、`frontend/`、`backend_si/`、实验和研究结果；也不能替换共同 master SHA 为未授权 `ci-validation`/#41 版本。

## 4. G0 裁决、处置清单与门禁

**差异数 15 = P0 2 + P1 9 + P2 4；其中本报告判定 G0 阻断 10 项：X01/X02/X03/X04/X05/X07/X08/X09/X10/X13。** 此处“阻断”指文档口径不可直接宣告“所有功能和安全约束已完整映射”，不是宣称已通过浏览器复现 10 次故障。

**建议：G0 = HOLD。** 审阅者需先接受 X01–X15 的证据与严重度；把 X01/X02 明确设为后续 UI 实现的强制前置安全修复（提供条件夹具和拒绝示例）；要求 UI-02 的任务路径明确 X03/X04/X05/X07/X08/X09/X10/X13 的可达性/失败态，附带独立验收脚本；X06/X11/X12/X14 登记保留/待设计决定。**本 PR 不承担修复源码或批准 G1 的权限。** P0 未通过至少一次针对性运行验证并经主智能体确认前，不可将最终展示/科研判优标为可信。

若主智能体将“G0”严格限定为文档静态比对，可接受“报告提交完成”这一里程碑，但**不能**把“报告已存在”提升为“G0 PASS”。G1 的任务效率/布局验收仍须完成 F01–F09 浏览器任务记录；G2/G3 必须单独在批准的生命周期/实验基线上验收。

## 5. 证据永久链接及复核操作

- UI-00 六份：[目录（冻结 HEAD）](https://github.com/159357yangjun/SwarmBalance/tree/a0983f62013335ad6f96ed4e88a68ea8021b7b1b/docs/taskui/audit)；[PR #43](https://github.com/159357yangjun/SwarmBalance/pull/43)
- UI-02 六份：[目录（冻结 HEAD）](https://github.com/159357yangjun/SwarmBalance/tree/7636e09f8e5f2cb46cf9360a6be722ad269f8fc1/docs/taskui/requirements)；[PR #44](https://github.com/159357yangjun/SwarmBalance/pull/44)
- master 源码：[UI 模板 / JS](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/console/static/index.html)、[路由](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/console/server.py)、[单会话](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/console/sim_session.py)、[实验子进程](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/console/experiment_service.py)。
- 完成复验要求：对 `master...ui/taskui-b01-cross-review` 运行 GitHub compare，**唯一新增路径必须是 `docs/taskui/BATCH01_CROSS_REVIEW.md`**；检查 Draft PR base=master、head=`ui/taskui-b01-cross-review`、未合并；UI-00/UI-02 HEAD 必须与表中冻结 SHA 相同，不得在本任务写入这些分支。

**最终状态声明**：本报告仅核对静态代码/文档并给出可证伪的条件风险；没有任何 E2E PASS/FAIL 实验事实。最新提交 SHA 和 PR URL 以 GitHub 实际提交创建的返回值与 Draft PR 校验为准，不在报告里预填。
