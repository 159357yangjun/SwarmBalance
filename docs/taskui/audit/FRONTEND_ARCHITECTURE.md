# 前端架构与状态/数据流（静态审计）

**代码固定点**：\`master@2ab60c69a806a22d7ba20353dee0571752a0e8e5\`。标记「验」表示直接由源码确定，「推」表示需浏览器复验。

## 真实目录、栈和页面部署

\`\`\`text
start_console*.bat / python -m console.run
  └─ console/run.py → uvicorn / console/server.py (FastAPI)
       ├─ GET / → console/static/index.html
       ├─ GET /spec → console/static/spec.html
       ├─ GET /vendor/{name} → console/static/vendor/ (白名单)
       └─ /api/* → SimSession / 配置 / 实验 / 比较文件
console/static/index.html
  ├─ 内联 CSS + Vue 3 全局构建 (createApp({...}).mount('#app'))
  ├─ 原生 Canvas 2D；Three.js 3D；ECharts 图表
  └─ 原生 fetch 封装 api()，不使用独立 SDK
console/sim_session.py
  └─ Environment / Scheduler → snapshot JSON → Vue data(snap)
frontend/*.py  ← **仿真内核及模型，不是 Web UI 源码**
backend_si/*.py ← PSO/GA/OR-Tools 等调度器
experiments/*.py / results/compare/*.csv ← 批处理指标与对比
\`\`\`

- **验**：依赖本地优先：Vue 3.5.13、ECharts 5.5.1、Three.js 0.128.0，失败时 CDN 回退；缺失库有整页报错（\`index.html:7-29,588-600\`; \`console/static/vendor/README.md\`）。没有在 Git tree 发现 React/Vue SFC、\`src/\`、\`package.json\`、node 构建配置或 Vue Router/Pinia。此处是单 HTML + 内联 JS 运行模式，而非标准 Vite SPA。
- **验**：导航不是路由文件：\`goPage(p)\` 用 \`showMap\` 与 \`tab\` 控制视图，\`mounted()\` 仅解析初次 \`location.hash\`；没有看到 \`hashchange\` 监听或导航时同步修改 URL（\`index.html:2663-2687,3018-3024\`）。
- **验**：Vue \`data()\` 在 \`index.html:1369-1400\` 集中管理全部 UI、表单、地图、实验、图表、轮询与运行中状态；\`computed\` 在 1401-1486；\`methods\` 在 1487-3017。未发现独立状态模块。
- **验**：Canvas 2D 主绘制/命中 \`draw2d\` / \`hitTest2d\` / \`handleMapClick\`（2018-2233）；3D 初始化、Raycaster 与绘制 \`init3d\` / \`draw3d\`（2249-2508）；地图源为 \`GET /api/map\` 加快照坐标，不是 Leaflet/Mapbox。
- **验**：ECharts 容器 \`#trend/#compare/#radar/#rank/#gauge/#fleetPie\`；\`chartFor\`、\`drawChart\` 等管理实例（2965-3017、2713-2912）；侧坞 mini-sparkline 是原生 SVG（1124-1136）。
- **验**：REST 客户端 \`api(path,opts)\`（1495-1523）有网络错误转换、HTTP 202 预热重试（40 秒）、422 错误格式化；不是 axios。未发现 WebSocket/SSE 实时推送；进度来自 \`POST /api/step\` 返回整份快照与实验 \`GET /api/experiments/status\` 轮询（2933-2958）。
- **验**：\`console/server.py\` 启动时后台预热单例 \`SimSession\`（61-101），操作使用 \`_op_lock\`；\`SimSession.step\` 中 greedy 直接策略、其它算法 scheduler.step，再调用 \`env.step(action)\`（\`sim_session.py:167-200\`）。

## 单向数据流与状态来源

\`\`\`text
[Vue: 用户命令 / 表单值] ─fetch──> [FastAPI endpoints]
                                       │
  ┌─ persistent config JSON/YAML  <────┤ (配置写入 / rebuild)
  ├─ in-memory SimSession  <───────────┤ (step/reset/incident/inject/checkpoint)
  └─ experiments subprocess + CSV <────┘ (实验启动/对比查询)
                                       │
[Vue: snap = response JSON] <───────────┘
  ├─ 2D / 3D 绘制（坐标、建筑、对象）
  ├─ 任务/无人机/机巢详情，事件与状态坞
  └─ KPIs、趋势与告警
\`\`\`

| 状态域 | 前端成员 / 代码 | 服务端真源 | 生命周期 |
|---|---|---|---|
| 仿真世界 | \`snap\`, \`trajectories\`, \`trend\`（1377-1379,1882-1891） | \`SimSession.snapshot()\`（663-685）；\`Environment\`（167-200） | 单一进程会话；reset/rebuild 改变 |
| 视图导航 | \`showMap\`, \`tab\`, \`view\`, \`selection\`（1373,1394） | 仅浏览器 | 页面刷新一般重置 |
| 运行命令 | \`playing\`, \`stepping\`, \`stepSeq\`, \`timer\`（1371,1921-1965） | \`POST /api/step\` / \`reset\` | 客户端调度；服务端处理实际步进 |
| 场景/算法配置 | \`cfg\`, \`algo\`, \`sceneDraft\`（1387-1393） | \`config/simulation.json\`, \`backend_si/config.yaml\`（\`server.py:667-805\`） | 持久写回并 rebuild |
| 运行态快照 | \`checkpointRows\`（1469,1597-1632） | \`SimSession._checkpoints\`（427-563） | 进程内，最多 5 个，非磁盘持久 |
| 场景库 | \`sceneLibrary\`（1375,1539-1593） | \`console/scene_library.py\`; \`config/scenes\` | 配置型持久化，非当前世界快照 |
| 演示预设 | \`scenarioPresets\`, \`scenarioHasRestore\`（1384,1633-1669） | \`console/scenario_presets.py\`; server apply/restore（440-533） | 临时 patch 配置 + 重建 |
| 实验运行 | \`experimentStatus\`, \`experimentTimer\`（1383,2913-2959） | \`console/experiment_service.py\`; \`experiments/runner.py\` | 子进程与磁盘状态文件 |
| 对比表 | \`compareRows/compareComparable\`（1380-1382,2701-2712） | \`server.py:894-1003\`; CSV + \`results/compare_gate.py\` | 独立于当前 snap，需口径门禁 |

**核心区别**：当前实时 KPI 来自 \`env.get_statistics()\` 经 \`_stats_snapshot()\` 输出（\`sim_session.py:1254-1272\`）；算法对比取历史 CSV 的有效末行并经过门禁（\`server.py:894-1003\`）；实验进度来自独立子进程。这三者**不可**合并成一种 UI 状态或互相覆盖。

## 组件职责、架构风险

- **单文件集中**：\`index.html\` 3031 行，模板、样式、API、Canvas/Three/ECharts、状态、事件处理混在一个运行单元（验）；提升改造期间跨职能回归风险（推）。
- **响应式阈值**：\`index.html:567-584\` 在 1300px 以下堆叠 grid，1150px 以下隐去实时坞并将导航变成图标（验）；小屏可发现性、布局溢出需实际测量（推）。
- **详情职责错位**：\`selectEntity()\` 只写 selection，不切页面（1676-1685）；检查器仅在 \`v-show="showMap"\` 的地图容器内（666-784）（验），造成非地图页点击列表/日志后详情不可见的风险（高可信推断）。
- **错误状态覆盖不一致**：网络/参数异常一般有 API 包装，但 \`init()\` 首屏整体失败仅 finally 取消 loading，未见统一初始化错误页；实验状态轮询 catch 后仅 console.warn（1851-1869,2943-2952）（验），用户可能看不到错误（推）。

审计不涉及拆分组件或实施重构；任何实际前端文件写入需后续单独 TaskUI PR 和 G0/G1 审查。