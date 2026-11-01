# 2026-11-01 模块化迁移记录

本轮承接前次清理，执行已确认的目录、功能拆分和统一接口方案。整理阶段未自动提交，后续提交与推送按用户明确指令执行。迁移前实际工作区已另存基线 ZIP 和文件哈希。

## 结构变化

- 运行时代码统一为 `swarmbalance` 包，以职责命名 simulation/scheduling/application/infrastructure/web/cli/diagnostics/contracts。
- 原 PSOScheduler 的共用派发流程提取为 EventDrivenScheduler，GA/OR-Tools 继承共用基类；算法通过单一注册工厂创建并调用 act。
- SimSession 拆出 snapshots、checkpoints、events、scenarios；Environment 拆出 incidents、handoff，状态归属保持不变。
- FastAPI 集中装配，按领域拆路由、集中请求模型，一份运行上下文持有会话、锁及演示恢复点。
- CLI 统一 episode 循环，旧脚本保留参数/输出兼容适配；数据源规格、抽象、实现、工厂分开。

## 资源改名

| 旧路径 | 新路径 |
|---|---|
| `backend_si/config.yaml` | `config/schedulers.yaml` |
| `config/import/` | `config/import_templates/` |
| `frontend/data/map/part_of_yangpu.osm` | `data/maps/yangpu/part_of_yangpu.osm` |
| `data/map/fosi/`、`data/map/gis/` | `data/maps/fosi/`、`data/maps/gis/` |
| `frontend/data/.osm_cache/` | `data/cache/legacy_osm/`（保留旧缓存）；新缓存为 `data/cache/osm/` |
| `console/static/` | `swarmbalance/web/static/` |

地图、模板、调度 YAML 和浏览器 HTML/JS 的迁移不改写其有效内容；主仿真配置只更新模板路径，业务参数不变。用户场景目录和本地 results 保留。历史来源 CSV/JSONL 的旧路径属于历史登记，不批量篡改。

## 旧入口兼容

| 旧入口 | 推荐入口 |
|---|---|
| `python -m console.run` | `python -m swarmbalance console` |
| `python -m console.selfcheck` | `python -m swarmbalance selfcheck` |
| `python frontend/evaluate_metrics.py --policy ga` | `python -m swarmbalance evaluate --policy ga` |
| `python frontend/run_ga.py` 等 | 推荐统一 evaluate；原参数仍由薄适配器接收 |
| `python frontend/run_enterprise_demo.py` | `python -m examples.enterprise_demo.run` |

旧 evaluate 脚本的相对 `--output` 仍按 frontend 目录解析；新命令按项目根解析。绝对输出路径保持原样。专用算法脚本原来的 compare 输出文件名、`--no-csv` 和种子递增约定保持；旧 Greedy 专用 CSV 保留其原 15 列格式，新统一评测使用完整指标格式。

旧目录中的模块通过薄包装别名到规范模块对象，避免加载两份内核；兼容脚本可从项目外用绝对路径启动。新代码全部使用 swarmbalance 绝对导入。旧的相对地图路径，以及已知项目内旧绝对地图/模板/YAML 路径由 paths.py 映射；任意用户绝对文件路径不被改指向。

## 模块对应表

这是主要实现的归属表；会话、环境和 HTTP 的部分函数另拆到上述专门模块。

| 旧模块 | 规范实现 |
|---|---|
| `frontend/environment.py` | `swarmbalance/simulation/environment.py` |
| `frontend/drone.py` | `swarmbalance/simulation/entities/drone.py` |
| `frontend/task.py` | `swarmbalance/simulation/entities/task.py` |
| `frontend/charging_station.py` | `swarmbalance/simulation/entities/charging_station.py` |
| `frontend/route_planner.py` | `swarmbalance/simulation/routing/planner.py` |
| `frontend/route_cost.py` | `swarmbalance/simulation/routing/cost.py` |
| `frontend/no_fly_zone.py` | `swarmbalance/simulation/routing/no_fly_zone.py` |
| `frontend/matching.py` | `swarmbalance/scheduling/greedy_matching.py` |
| `frontend/greedy/scheduler.py` | `swarmbalance/scheduling/greedy.py` |
| `frontend/metrics_schema.py` | `swarmbalance/simulation/metrics.py` |
| `frontend/seed_interface.py` | `swarmbalance/simulation/seed.py` |
| `frontend/scheduling_interface.py` | `swarmbalance/contracts/scheduling.py` |
| `frontend/tools/osm.py` | `swarmbalance/infrastructure/maps/osm.py` |
| `frontend/data_source.py` | `swarmbalance/infrastructure/data_sources/factory.py` |
| `frontend/enterprise_data_source.py` | `swarmbalance/infrastructure/data_sources/enterprise.py` |
| `frontend/consistency_observer.py` | `swarmbalance/diagnostics/observer.py` |
| `backend_si/pso_scheduler.py` | `swarmbalance/scheduling/pso.py` |
| `backend_si/ga_scheduler.py` | `swarmbalance/scheduling/ga.py` |
| `backend_si/ortools_scheduler.py` | `swarmbalance/scheduling/ortools.py` |
| `backend_si/chain_codec.py` | `swarmbalance/scheduling/chain_codec.py` |
| `backend_si/matching.py` | `swarmbalance/scheduling/matching.py` |
| `backend_si/fitness_evaluator.py` | `swarmbalance/scheduling/fitness.py` |
| `config/loader.py` | `swarmbalance/infrastructure/config/loader.py` |
| `console/config_validation.py` | `swarmbalance/infrastructure/config/validation.py` |
| `console/capabilities.py` | `swarmbalance/diagnostics/capabilities.py` |
| `console/dependencies.py` | `swarmbalance/diagnostics/dependencies.py` |
| `console/preflight.py` | `swarmbalance/diagnostics/preflight.py` |
| `console/selfcheck.py` | `swarmbalance/cli/selfcheck.py` |
| `console/run.py` | `swarmbalance/cli/console.py` |
| `console/sim_session.py` | `swarmbalance/application/session.py` |
| `console/scene_library.py` | `swarmbalance/application/scene_library.py` |
| `console/scenario_presets.py` | `swarmbalance/application/scenario_presets.py` |
| `console/custody_journal.py` | `swarmbalance/infrastructure/custody/journal.py` |
| `console/custody_transaction.py` | `swarmbalance/infrastructure/custody/transaction.py` |
| `console/custody_queue_bridge.py` | `swarmbalance/infrastructure/custody/queue_bridge.py` |
| `console/gis_import.py` | `swarmbalance/infrastructure/maps/gis_import.py` |
| `console/map_lab.py` | `swarmbalance/web/routes/gis.py` |
| `console/server.py` | `swarmbalance/web/app.py` |
| `frontend/evaluate_metrics.py` | `swarmbalance/cli/evaluate.py` |
| `frontend/run_ga.py` | `swarmbalance/cli/legacy_ga.py` |
| `frontend/run_pso.py` | `swarmbalance/cli/legacy_pso.py` |
| `frontend/run_ortools.py` | `swarmbalance/cli/legacy_ortools.py` |
| `frontend/greedy/run_greedy.py` | `swarmbalance/cli/legacy_greedy.py` |
| `frontend/mock_enterprise_api.py` | `examples/enterprise_demo/mock_gateway.py` |
| `frontend/run_enterprise_demo.py` | `examples/enterprise_demo/run.py` |

## 验证与边界

新增测试覆盖注册表、状态独立、可选依赖、旧模块身份、真实旧地图加载、外部目录旧脚本启动、统一评测、完整 OpenAPI、共享 HTTP 状态、配置重建与检查点 RNG 延续。独立审查发现的旧路径定位和辅助函数依赖遗漏均增加复现测试后修正。

最终验证结果：

- 27 项回归测试全部通过，含完整 OpenAPI 契约、旧模块身份、外部目录旧脚本启动、候选解释/演示动作、检查点 RNG、配置热重建。
- 四算法使用同一真实地图、种子和固定注入任务，对照迁移前后的实体/任务/统计以及检查点恢复后继续运行，序列化数据一致；完整 OpenAPI 也一致。
- 新旧端到端 selfcheck 均通过；四种算法分别通过新的 evaluate 命令运行真实 2 步评测。
- 临时端口的真实 HTTP 服务通过页面、vendor、配置读取、任务注入/修改/解释、暂停任务流、步进和检查点保存/恢复/删除检查；验证后已停止临时服务。
- 27 个地图、模板、调度 YAML、浏览器资源及原始/来源数据文件与迁移前字节哈希一致；45 个旧模块别名与规范模块身份一致。
- CSV 模板成功读取 10 架无人机、5 个机巢、12 个任务；GeoJSON 模板成功读取 4 架无人机、2 个机巢、4 个任务。
- Python 语法与规范导入检查、pip check、git diff --check 通过；vendor 的 Git text 属性为 unset，避免行尾转换。
- 独立代码审查及修复后复核通过，本轮未留待修复的严重或重要问题。

以上短程测试不代替大规模算法性能或物理模型验证。原批量实验框架和历史科研产物仍未恢复。
