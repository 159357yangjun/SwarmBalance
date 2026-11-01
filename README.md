# SwarmBalance · 群智优衡

异构无人机集群三维协同调度仿真平台。Greedy、PSO、GA、OR-Tools 共用仿真环境与调度接口，提供任务生成、调度、飞行仿真、指标评估和 Web 可视化。

## 安装与运行

正式环境为 Python 3.10，版本统一维护在根目录 `requirements.txt`。在项目根目录执行：

```powershell
py -3.10 -m venv .venv310
.venv310/Scripts/python.exe -m pip install -r requirements.txt

.venv310/Scripts/python.exe -m swarmbalance console
# http://127.0.0.1:8765/

.venv310/Scripts/python.exe -m swarmbalance console --portable --map-lab
# http://127.0.0.1:8765/map-lab

.venv310/Scripts/python.exe -m swarmbalance evaluate --policy ga --episodes 1 --episode-steps 100
.venv310/Scripts/python.exe -m swarmbalance selfcheck --steps 12
.venv310/Scripts/python.exe -m unittest discover -s tests -v
```

已有 `.venv310` 时直接使用，不用重新创建。便携模式允许内置离线 OSM 解析回退，缺少 OR-Tools 时会明确标记该算法不可用。浏览器页面使用本地 Vue/Three.js/ECharts，无 Node/Vite 构建步骤。

## 目录职责

```text
SwarmBalance/
├─ swarmbalance/               唯一运行时代码包
│  ├─ contracts/              调度、数据源、路由和应用异常接口
│  ├─ simulation/             仿真环境、实体、路径、事故、交接与指标
│  ├─ scheduling/             四算法、共用派发状态机与调度器注册工厂
│  ├─ application/            会话、快照、检查点、场景、配置与评测服务
│  ├─ infrastructure/         配置、地图、数据源、货物交接持久化实现
│  ├─ diagnostics/            运行能力、依赖预检与只读诊断
│  ├─ web/                    FastAPI 装配、请求结构、功能路由、static/
│  ├─ cli/                    命令行适配与旧评测参数兼容
│  └─ paths.py                资源定位与旧路径映射
├─ config/                    配置数据、import_templates/、用户 scenes/
├─ data/                      maps/、cache/、raw/、provenance/
├─ examples/enterprise_demo/  企业网关接入示例
├─ tools/                     独立离线数据工具
├─ tests/                     契约、生命周期和入口回归
├─ docs/                      架构、接口与迁移记录
├─ results/                   本地运行输出
├─ frontend/                  旧脚本/导入兼容入口
├─ backend_si/                旧算法导入兼容入口
└─ console/                   旧控制台命令/导入兼容入口
```

新代码统一使用 `swarmbalance.*` 导入。`frontend/`、`backend_si/`、`console/` 只保留兼容包装和说明，不维护另一套实现。

## 接口与数据

所有算法通过 `create_scheduler(...)` 创建，并调用 `Scheduler.act(observation, current_time)`。Web 和 CLI 共用应用服务；HTTP 路由共享一份会话与锁。详见[接口说明](docs/INTERFACES.md)和[架构说明](docs/ARCHITECTURE.md)。

仿真配置位于 `config/simulation.json`，算法配置位于 `config/schedulers.yaml`；默认地图为 `data/maps/yangpu/part_of_yangpu.osm`。资源通过 `paths.py` 定位，旧场景里的地图和导入模板路径继续映射。原始数据、第三方许可证和用户场景保持独立管理。

统一评测支持 `greedy|pso|ga|ortools`，默认写入忽略管理的 `results/adhoc/`；显式 `--record-into-evidence` 才写入 Web 对比页读取的 `results/compare/`。输出位置不代表已通过科学可比性验证。

旧的 `python -m console.run`、`python -m console.selfcheck`、`frontend/evaluate_metrics.py` 和专用算法脚本仍可运行，参数与输出兼容细节见[迁移记录](docs/MIGRATION.md)。

## 当前边界

- GIS 导入地图只用于预览，未自动接入仿真安全地图。
- 货物交接 SQLite 队列和只读 observer 为独立能力，默认不作为 Web 主链路运行。
- 仓库没有历史算法对比 CSV，也没有批量实验编排框架；缺 CSV 时对比接口返回空数据。
- 回归验证覆盖接口、入口、配置重建、检查点和真实短程运行，不能代替长期仿真或物理模型验证。
- `data/provenance/` 保留历史来源登记；部分原生成器和输入已移除，不代表当前实验结论。
- [FEATURES.md](FEATURES.md) 是目标需求清单；MARL 后端已移除，其历史指标已作废。

## 许可证

项目使用 [MIT](LICENSE) 许可证。第三方数据与浏览器库另见各目录的来源、许可证说明。
