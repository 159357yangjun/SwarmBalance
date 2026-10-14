# 功能—界面入口—组件—API—状态追踪矩阵

基线：master@2ab60c69a806a22d7ba20353dee0571752a0e8e5。**证据级别 S：静态链路确实存在；未测试端到端行为。** UI 列行号均为 console/static/index.html；服务列行号均为 console/server.py；SimSession 指 console/sim_session.py。没有独立 Vue 组件文件，所谓「组件」是同一 HTML 内的区块/方法。

| 功能 | 用户入口/区块 + JS | 后端 API（server 行号） | 后端真源 / 前端状态 |
|---|---|---|---|
| 首屏及依赖检测 | 23-29,588-600；init 1851-1880 | GET / 194-200；GET /api/meta 235-249；GET /api/snapshot 263-270；GET /api/map 389-396 | SimSession.snapshot 663-685、map_static 688；appMeta/snap/mapStatic/loading |
| 分层导航 | 636-655；goPage 2663-2687 | 无 | showMap/tab，完全浏览器本地 |
| 2D/3D 切换绘制 | 619-620,665-795；draw2d 2083；init3d 2249；draw3d 2467 | GET /api/map 389-396；GET /api/snapshot 263-270 | mapStatic/snap/view/selection/threeState |
| 算法及 Seed 选择 | 603-609；onAlgorithmChange 1966；reset 1899-1920 | POST /api/reset 272-288；GET /api/meta 235 | SimSession.reset 145-165 / _build_scheduler 1278-1292；algorithm/seed/snap.algorithm |
| 开始/暂停/单步/倍率 | 611-617；advance 1921-1941、playTick 1948-1963 | POST /api/step 291-309 | SimSession.step 167-200 → Environment.step；playing/stepping/stepSeq/snap |
| 订单流暂停/恢复 | 913-915；setTaskStream 1702-1710 | POST /api/task-stream 328-333 | SimSession.set_task_generation_paused 325；snap.controls |
| 新增任务 | 626,915,1303-1339；submitTask 2523-2545 | POST /api/tasks/inject 311-319 | SimSession.inject_task 212；taskForm/snap/taskError |
| 任务属性调整/紧急升级 | 753-765；saveTaskEdit 1720-1729、promote 1731-1735 | PATCH /api/tasks/{task_id} 335-345 | SimSession.update_pending_task 337；taskEdit/snap |
| 候选无人机解释 | 767-778；loadTaskCandidates 1686-1693 | GET /api/tasks/{task_id}/candidates 322-326 | SimSession.task_candidates 967；taskCandidates |
| 无人机补能 | 703-708；requestDroneCharge 1711-1719 | POST /api/drones/{id}/charge 347-355 | SimSession.request_drone_charge 363；incidentBusy/snap |
| 无人机故障/恢复 | 706-710,924；setDroneIncident 1737-1748/randomDroneFault 1761-1769 | POST /api/drones/{id}/incident 358-368 | SimSession.set_drone_out_of_service 226；incidentBusy/snap |
| 机巢关闭/开放 | 732-738,925；setNestIncident 1749-1760/randomNestClose 1770-1777 | POST /api/nests/{id}/incident 370-379 | SimSession.set_nest_closed 256；incidentBusy/snap |
| 一键恢复事故 | 926；restoreAllIncidents 1778-1792 | **多次** POST /api/drones/{id}/incident 与 /api/nests/{id}/incident | 多步修改，非原子批量；incidentError/snap |
| 对象选择/详情 | 675-783,937-979；selectEntity 1676-1685、selectFromEvent 1695-1700、hitTest2d 2018 | GET candidates 322-326；其余快照数据来自 GET snapshot | snap.drones/nests/task_catalog/events；selection；**详情只在 showMap 为真时渲染** |
| 实时健康、任务链与图表 | 852-897,900-984,1089-1171；drawChart/drawGauge/drawFleetPie | GET snapshot 263-270；step/reset 的返回 snap | SimSession._drones_snapshot 768、_nests_snapshot 807、_task_catalog_snapshot 889、_stats_snapshot 1254 |
| 仿真配置 | 622,1173-1210；openConfig 2546、saveConfig 2577 | GET/POST /api/config 667-686；GET/POST /api/scheduler-config 777-805；POST /api/rebuild 382-387 | config/simulation.json + backend_si/config.yaml；SimSession.rebuild 643；cfg/algo |
| 场景布局（机巢/禁飞） | 623,1212-1258；openSceneEditor 1794、saveSceneLayout 1831 | GET /api/config 667；POST /api/scene-layout 689-774 | simulation.json 持久配置 + rebuild；sceneDraft/mapPick/snap |
| 场景库保存/加载/导入导出/删除 | 624,1260-1287；1539-1593 | GET/POST /api/scene-library 562-586；GET /{id} 588；POST /import 598；DELETE /{id} 608；POST /{id}/apply 619 | console/scene_library.py → config/scenes；sceneLibrary/snap |
| 答辩演示场景 | 813-832；loadScenarios/apply/advance/restore 1633-1669 | GET /api/scenarios 440-445；POST /apply 448-497、/next 500-508、/restore 510-533 | scenario_presets.py + SimSession.advance_demo 579；scenarioPresets/snap.demo |
| 动态运行态快照 | 834-850；save/load/deleteCheckpoint 1597-1632 | GET /api/checkpoints 403-407；POST / 409-417、/{name}/load 418、DELETE /{name} 427 | SimSession._checkpoints 427-563；snap.checkpoints，**不持久化** |
| 算法对比与排名 | 987-1010,1042-1077；loadCompare 2701、drawCompare 2713、drawRadar/drawRank | GET /api/compare 894-1003 | results/compare/*.csv + results/compare_gate.py；compareRows/compareComparable/compareMetric |
| 一键实验/状态 | 1011-1038；ensureExperimentData 2913、runExperiment 2933、loadExperimentStatus 2943 | GET /api/experiments/presets 814；POST /start 824；GET /status 819 | console/experiment_service.py → experiments/runner.py 子进程；experimentStatus |
| 下载正式证据包 | 1034 超链接 | GET /api/experiments/package 834-842 | build_conclusion_package.py → ZIP；不属于实时快照 |
| 规范正文 | 652,1080-1086 | GET /spec 201-207 | console/static/spec.html；只读 iframe |
| 使用引导 | 625,1289-1301；closeGuide 1595 | 无 | showGuide + localStorage |

## 数据语义约束

1. **实时会话**：\`snap\` 每次 step/reset 等响应替换；服务端是 \`Environment\` 真源，Vue 不能直接计算虚构能耗或完成事件。快照字段由 SimSession.snapshot()（663-685）和 _stats_snapshot()（1254-1272）定义。
2. **可编辑运行态**与**持久初始场景**不同：checkpoint 是 SimSession 内存对象，scene library 是文件配置，演示预设 patch simulation.json；相互替换会破坏复现语义。
3. **图表对比**来自磁盘历史 CSV 而非 snap，\`comparable=false\` 时必须维持拒绝“最优”结论。
4. **选择器不是 API**：goPage、switchView、openGuide 是浏览器内部状态；不要为不存在的 UI 功能臆造 endpoint。
5. **调用链存在 ≠ 运行成功**：所有行为验收状态目前为“未执行 UI/E2E”。