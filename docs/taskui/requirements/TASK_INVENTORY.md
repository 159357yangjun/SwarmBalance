# TASK_INVENTORY｜核心业务能力与界面/API 对照台账

> TASKUI-SB-UI-02 · `master@2ab60c69a806a22d7ba20353dee0571752a0e8e5` · 2026-10-14  
> 核验范围：`console/static/index.html`（实际 Vue3 单文件模板/方法）、`console/server.py`、`console/sim_session.py`、`console/scene_library.py`、`console/experiment_service.py`、仓库 README 与场景操作文档。**静态实现证据≠浏览器端已验收**。UI-00 审计清单在本次核对时未见可访问的对应分支/PR，待后续交叉校准。

## 分类与可信度

- **I：代码中有界面入口和可调用的 API**；不宣称运行环境已经实测通过。
- **P：部分实现**（核心动作存在，候选任务的某个子能力未形成同等 UI 入口）。
- **U：未在本次审计范围代码发现实现**；不得写成已经支持。
- 频率 H（高）/M（中）/L（低）是**工作流设计假设**，需真实任务观察修订；非使用数据。
- 风险 C（常规）/R（重建或覆盖当前会话）/D（资源/任务状态变化或删除）/E（科研可比性误判）。

## 任务映射台账

| ID | 任务/动作 | 当前用户可见路径 | 前端方法或组件 → 后端证据 | 状态 | 频率/风险 |
|---|---|---|---|---|---|
| T01 | 选择算法与 Seed、重置 | 顶栏“算法/Seed/重置” | `reset` → `POST /api/reset` | I | M/R |
| T02 | 播放/暂停、单步、倍速 | 顶栏控制组 | `togglePlay/stepOnce/setSpeed` → `POST /api/step`；暂停为前端停止调度 | I | H/C |
| T03 | 2D/3D 地图与航迹 | “实现层” + 2D/3D | `draw2d/draw3d/switchView`; `/api/snapshot`, `/api/map` | I | H/C |
| T04 | 点选 drone/task/nest 详情 | 地图、控制层列表、事件条目 | `selectEntity`、地图 hit-test，`snap.drones/nests/tasks` | I | H/C |
| T05 | 人工新任务/地图选起终点 | 顶栏“＋新任务”；弹窗转 2D 取点 | `submitTask/startMapPick` → `POST /api/tasks/inject` | I | M/D |
| T06 | 修改 pending 任务优先级/SLA/重量/类别 | 选任务→详情检查器 | `saveTaskEdit/promoteTaskEmergency` → `PATCH /api/tasks/{id}`；非 pending 不允许编辑 | I | M/D |
| T07 | 查看候选匹配解释 | 选 pending 任务→“候选无人机解释” | `loadTaskCandidates` → `GET /api/tasks/{id}/candidates` | I | H/C |
| T08 | 暂停/恢复**自动订单生成** | “控制层”实时调度状态 | `setTaskStream` → `POST /api/task-stream`；不暂停现有飞行 | I | M/D |
| T09 | 无人机任务链、机巢排队/泊位、事件 | “控制层”列表/日志、详情 | `snap.drones/nests/events` → `/api/snapshot` | I | H/C |
| T10 | 人工调无人机补能 | 地图选中无人机→详情 | `requestDroneCharge` → `POST /api/drones/{id}/charge` | I | M/D |
| T11 | 故障停飞/恢复、关闭/开放机巢 | 控制层“场景事件注入”或实体详情 | `randomDroneFault/randomNestClose/set*Incident` → `POST /api/drones/{id}/incident`、`/api/nests/{id}/incident` | I | M/D |
| T12 | 修改基础配置、算法超参并应用 | 顶栏“配置”弹窗 | `openConfig/saveConfig` → `POST /api/config` → `POST /api/scheduler-config` → `POST /api/rebuild` | I | L/R |
| T13 | 编辑机巢位置/泊位、圆形禁飞区 | 顶栏“场景编辑”，表单/2D 地图取点 | `saveSceneLayout` → `POST /api/scene-layout`；仅 random 数据源支持提交 | I | L/R |
| T14 | 保存/导入/导出/加载/删除初始场景 | 顶栏“场景库” | `/api/scene-library` GET/POST、import/export/apply/DELETE | I | M/R,D |
| T15 | 载入预设/执行下一幕/恢复演示前配置 | “数据处理展示层”指标页 | `/api/scenarios` GET、apply/next/restore POST | I | M/R,D |
| T16 | 保存/恢复/删除运行态快照 | “数据处理展示层”指标页 | `/api/checkpoints` GET/POST、load/DELETE | I | M/R,D |
| T17 | 观察态势、完成/超时、机队利用、能耗、趋势 | “数据处理展示层”指标页及控制/算法实时坞 | `snap.stats/health/history`、ECharts/实时坞 → `/api/snapshot` | I | H/C |
| T18 | 执行实验预设、查进度 | “算法层”一键实验编排 | `/api/experiments/presets|status|start`；`console/experiment_service.py` 子进程 | I | L/E |
| T19 | 读取算法对比与可比性提示 | “算法层”对比看板 | `/api/compare` 读取 `results/compare/*.csv`；`compare_gate` 阻止不可比结果宣称胜者 | I | M/E |
| T20 | 下载最新 conclusion 证据包 | “算法层”实验区 | `GET /api/experiments/package`，以正式结果存在为前提 | I | L/E |
| T21 | 查看世界设计规范 | 左导航“规范” | `/spec` 嵌入 `console/static/spec.html` | I | L/C |
| T22 | 按任意历史批次挑选两组运行结果进行专门 UI 对比 | 未见独立历史批次选择器 | 当前 `/api/compare` 选取已登记 CSV 的最后有效行，实验区显示输出目录；没有任意批次选择 API/控制件证据 | **U** | L/E |
| T23 | 保存运行态快照到可跨重启文件并重载 | 未见对应入口 | `SimSession` 快照保存在服务进程内，明确与场景库不同 | **U** | L/R |
| T24 | 手工配置任意 CSV/GeoJSON 导入场景的机巢几何 | 场景编辑器在数据源非 random 时禁保存 | `/api/scene-layout` 对非 random 返回 400；导入文件仍由配置驱动 | **P（只读/拒绝保存）** | L/R |

## 已实现能力的关键限制（必须原样带入 G1）

1. 算法选项可因依赖缺失禁用；界面不保证每个运行环境四算法均可用（`/api/meta`、`/api/algorithms`）。
2. `selectEntity` 可统一选择对象，但地图检查器只在 `showMap` 时显示，控制层是独立视图；不能把“同屏关联”记为已实现。
3. 场景编辑保存会热重建；一般配置编辑经过三次顺序请求，当前没有前端统一事务接口的证据（`index.html:2577-2608`）。
4. 演示预设会暂时改写 `simulation.json`；批量实验使用隔离配置；场景库持久化的是**初始配置**而非动态运行态。
5. 检查点限当前进程最多 5 个，环境代变化时会保留条目但拒绝不兼容恢复（`sim_session.py:395-553`）。
6. 事件日志可链接到实体，但只显示服务端返回有限事件与最近条目；不能据此声明无限历史检索/回放。
7. 批量对比必须保留 `comparable/refusal` 语义；任何更显眼的“胜者”都不可绕过门禁。
8. “任务生命周期”字段/事件是观察能力；不以 UI 显示证明真实货物状态已通过科研证据验证。

## G1 交付索引

任务操作路径见 [TASK_FLOWS](TASK_FLOWS.md)；信息频度见 [INFORMATION_PRIORITY](INFORMATION_PRIORITY.md)；工作区和行为约束见 [WORKSPACE_REQUIREMENTS](WORKSPACE_REQUIREMENTS.md)；可执行验收见 [UX_ACCEPTANCE_CRITERIA](UX_ACCEPTANCE_CRITERIA.md)。