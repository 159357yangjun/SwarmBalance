# TaskUI 不可突破边界与回归验证建议

基线 master@2ab60c69a806a22d7ba20353dee0571752a0e8e5；仅依据静态源码。

## 本审计 PR 的强制边界

只新增 docs/taskui/audit/ 下六份 Markdown。禁止更改 index.html/spec.html、server.py、sim_session.py、frontend/、backend_si/、experiments/、results/、config/、测试、CI、版本文件；禁止合并 PR 或将 #41 隐式带入审计分支。无任何 UI 运行/截图证据。

## 后续 UI 改造时必须保持的契约

| 被保护系统 | 关键文件/静态定位 | 不可借布局调整修改的语义 | 检查建议 |
|---|---|---|---|
| 世界时间和单步 | console/sim_session.py:167-200；frontend/environment.py；frontend/drone.py STEP_SECONDS | 单次 step 的调度→Environment.step 序列、步长、完成条件、随机种子不变 | 相同 SHA/seed 逐步快照对比；服务端 step 计数测试 |
| 调度算法和动作结构 | console/sim_session.py:1278-1292；backend_si/pso_scheduler.py, ga_scheduler.py, ortools_scheduler.py；frontend/greedy/scheduler.py | GA/PSO/OR-Tools/Greedy 参数含义、任务分配行为、启停口径不得由 UI 改写 | 各算法固定 seed 快照比对 |
| 任务生命周期和货物状态 | console/sim_session.py:212-394,870-953；frontend/task.py、environment.py、drone.py | pending/assigned/in_progress/completed、装载归属、到达目的地才算完成；**PR #41 未合并**不等于 master 已修 | 使用被批准的生命周期基线 + 负例回归；**不得单靠 UI 完成率声称正确** |
| 能耗/风/里程/换电 | frontend/drone.py, environment.py, route_cost.py, charging_station.py；console/sim_session.py:1254-1272 | 耗电与距离、载重、风影响、换电账本、单位不可从 UI 派生“修正” | E0/E1 冻结 run 配置及指标证据复验 |
| 单一快照真源 | console/sim_session.py:663-685,768-952；console/server.py:263-396 | 图表、地图、详情均读取后端世界状态，渲染不得生成任务完成或给内核写坐标 | schema/字段契约、step 前后快照 diff |
| 配置写回与重建 | console/server.py:667-805；console/sim_session.py:643-657；config/simulation.json；backend_si/config.yaml | config 与 scheduler 配置各自持久；rebuild 是重建/代次改变，不能伪装成单纯前端刷新 | 保存失败/回滚/代次无效 checkpoint 验证 |
| 场景/检查点/演示 | console/scene_library.py；console/scenario_presets.py；console/sim_session.py:395-643；console/server.py:403-660 | 持久“初始场景”、进程内“动态快照”、演示前配置备份绝不混淆 | 保存/加载/重启/跨代场景分组测试 |
| 实验隔离 | console/experiment_service.py:17-125；experiments/runner.py；console/server.py:814-842 | 独立实验子进程、seed/配置隔离、原始结果目录不可被实时面板覆盖 | 检查原始 CSV/reproducibility、独立实验是否触碰当前 SimSession |
| 可比性/指标定义 | results/compare_gate.py；console/server.py:894-1003；experiments/reporting.py | comparable=false 禁画“优胜”，方向模糊指标不判最优；不改 CSV 原始读数与 KPI 分母 | 正/反口径案例回归、指标语义对照 |
| UI 请求并发 | console/server.py:61-64,291-309；console/static/index.html:1921-1964 | 旧响应不得覆盖 reset/restore 后新世界；不能平行发两个 step 链 | 在途 step + pause/reset/restore 故障注入 UI 集成测试 |
| 地图尺度 | console/static/index.html:665-795,2083-2508 | 2D x/y 来自真源；Three 3D 高度视觉夸张非真实物理高度；绝不可把渲染 z 写回飞行模型 | 2D/3D 同实体位置与说明复核 |

## 后续实施必须经过的门

- **G0 / 静态一致性**：功能入口矩阵全覆盖；变更不触碰保护目录/API、字段名与研究结果；指定 exact base SHA；所有用户命令和失败态可追溯。
- **G1 / 交互设计审查**：用场景创建→调度→介入→观察→保存/对比完整任务走查；验收对象详情可见、宽度断点、状态与持久性标注；不能只以页面“美观”验收。
- **G2 / 运行回归（未来单独 PR）**：真实浏览器验证空/加载/错误/无权限或不可用算法、网络断开、任务生命周期、地图取点、2D/3D、弹窗键盘焦点、场景恢复、checkpoint 代次、实验对比口径。
- **G3 / 仿真门**：仅以获得授权的内核 SHA 跑固定种子、全套 CI 和冻结参考证据；不得将 PR #41 的 9/9 检查挪为 master 的验收。

## 待主智能体裁决

当前选择 **master@2ab60c...** 为稳定的 *UI 文档审计快照*，并非宣称它在生命周期/能耗研究上最佳。PR #41 是独立正在审查的 Draft，待主智能体决定是否及何时把 lifecycle fixes 纳入集成基线。TaskUI 设计阶段不得私自合并任何内核修复。