# 项目架构与代码导航

本文件描述 2026-11-01 模块化重构后的实际结构。目标需求仍以 `FEATURES.md` 为准。

## 运行链路

```text
web/static/ 页面
        │ 现有 HTTP URL 与 JSON 结构
        ▼
web/app.py → web/routes/ → web/dependencies.runtime
        │                     同一 session / lock / scenario backup
        ▼
application/session.py
        ├─ snapshots / checkpoints / events / scenarios
        └─ scheduling/registry.py → Scheduler.act(observation, current_time)
                                      ├─ GreedyScheduler
                                      └─ EventDrivenScheduler
                                            ├─ PSOScheduler
                                            ├─ GAScheduler
                                            └─ ORToolsScheduler
        │ action
        ▼
simulation/environment.py
        ├─ entities/：drone / task / charging_station
        ├─ routing/：planner / cost / no_fly_zone
        ├─ incidents.py / handoff.py
        └─ infrastructure/data_sources/ → 输入规格与任务流

cli/ → application/evaluation.py → 同一 Environment + 调度器工厂
```

## 分层与职责

| 位置 | 责任 |
|---|---|
| `swarmbalance/contracts/` | Observation/Action/Scheduler、数据源规格/抽象、路由 DTO/成本协议、应用异常；不依赖 FastAPI |
| `swarmbalance/paths.py` | 项目资源根、默认文件位置、旧地图/模板/YAML 路径映射 |
| `simulation/environment.py` | 真实动态状态、reset/step 协调、任务与资源规则；公共事故/交接方法委托给独立模块 |
| `simulation/entities/` | 无人机、任务与生成器、机巢实体 |
| `simulation/routing/` | 路径规划、成本/ETA、禁飞区域 |
| `simulation/incidents.py`、`handoff.py` | 操作传入的同一 Environment，不另建业务状态 |
| `simulation/metrics.py`、`seed.py` | 统一指标定义/转换/CSV 写入与随机种子 |
| `scheduling/registry.py` | 算法描述、可用性和创建；新算法在此注册 |
| `scheduling/dispatch.py` | PSO/GA/OR-Tools 共用的事件、缓冲、任务链和派发流程 |
| `scheduling/{greedy,pso,ga,ortools}.py` | 各策略实现；GA/OR-Tools 不再继承名为 PSOScheduler 的派发基类 |
| `scheduling/chain_codec.py`、`fitness.py` | 任务链编码/解码与适应度工具 |
| `scheduling/matching.py`、`greedy_matching.py` | 保留原后端与 Greedy 不同的输入边界语义，未强行合并评分 |
| `application/session.py` | 对外会话门面，协调环境和服务 |
| `application/snapshots.py`、`checkpoints.py`、`events.py` | 只读序列化、动态状态捕获恢复、事件和历史；显式接收 session |
| `application/scenarios.py`、`scenario_presets.py`、`scene_library.py` | 演示执行、配置切换/回滚、预设与场景文件 |
| `application/configuration.py`、`comparison.py`、`evaluation.py` | 配置持久化/布局、历史 CSV 读取、episode 执行；与 HTTP 传输分离 |
| `infrastructure/config/` | 配置读取与校验 |
| `infrastructure/maps/` | OSM 解析/缓存、GIS 下载与导入任务 |
| `infrastructure/data_sources/` | random、CSV、GeoJSON、enterprise 实现和工厂；common 包含静态任务流/转换工具 |
| `infrastructure/custody/` | 独立交接日志、事务和实验性 SQLite 队列桥，当前未接入 Web |
| `diagnostics/` | 能力探测、预检、依赖诊断及可显式安装的只读 observer |
| `web/app.py`、`dependencies.py`、`schemas.py` | 应用装配、单一共享运行上下文、HTTP 请求模型 |
| `web/routes/` | pages、metadata、simulation、tasks、fleet、checkpoints、scenarios、configuration、comparison、gis |
| `web/static/` | 原 HTML/JS 页面与 vendor 文件，未引入前端构建系统 |
| `cli/` | console/evaluate/selfcheck，以及旧算法参数/CSV 的兼容适配 |

算法注册表使用延迟导入，元数据读取不直接创建调度器。每回合由工厂创建新实例，Web 在运行中故障后通过 `synchronize()` 预热执行中任务，不再直接改具体策略的内部字段。

## 配置与状态生命周期

| 位置 | 生命周期 |
|---|---|
| `config/simulation.json` | 主场景配置，JSON 中的业务参数保持原语义 |
| `config/schedulers.yaml` | 调度参数，原 YAML 内容与注释保留 |
| `config/import_templates/` | CSV / GeoJSON 输入模板 |
| `config/scenes/scene_*.json` | 用户持久场景；从初始配置重新运行，默认忽略 |
| `SimSession._checkpoints` | 当前进程的动态快照，含 Python/NumPy RNG、调度缓存、轨迹与事件；保留槽位和代际校验 |
| `data/maps/yangpu/` | 真实仿真使用的内置 OSM 文件 |
| `data/maps/fosi/`、`data/maps/gis/` | 地图区域定义、原本地图层、GIS 缓存/预览包/任务 |
| `data/cache/osm/` | 当前可再生地图缓存；`data/cache/legacy_osm/` 保留迁移前本地缓存 |
| `data/raw/`、`data/provenance/` | 原始数据、第三方许可证、历史来源登记 |
| `results/adhoc/` | 统一评测默认输出 |
| `results/compare/` | 显式生成后供对比接口读取的 CSV |
| `results/mvp/` | 原框架留下的用户本地数据，本轮未删除 |

配置内容每次读取文件，不缓存 JSON；加载来源优先级为显式路径、`SWARM_BALANCE_SIM_CONFIG`、默认主配置。热重建按规范模块名依次 reload 实体、数据源、Greedy 和 Environment，使导入期常量刷新；业务调用使用规范模块，不加载两份内核。

所有新代码使用 `swarmbalance.*` 绝对导入，未在规范包中注入 sys.path。旧目录的包装入口负责兼容旧命令和旧导入，并指向同一个规范模块对象。

## 验证入口

```powershell
.venv310/Scripts/python.exe -m unittest discover -s tests -v
.venv310/Scripts/python.exe -m swarmbalance selfcheck --steps 12
.venv310/Scripts/python.exe -m swarmbalance evaluate --policy ga --episodes 1 --episode-steps 100
.venv310/Scripts/python.exe -m pip check
```

本轮另保存了迁移前工作区及四算法/检查点/OpenAPI 基线，供逐项对照。测试只覆盖已列出的短程行为，不声明完整物理模型、长期调度性能或科研结论有效。
