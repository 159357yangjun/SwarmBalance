<div align="center">

# SwarmBalance · 群智优衡

**异构无人机集群三维协同调度仿真平台**（重构基线）

[![Python](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

面向城市低空物流配送场景，构建**任务生成 → 调度决策 → 飞行仿真 → 指标评估 → 可视化**的完整闭环，
在同一物理口径下横向对比四类调度方法（Greedy / PSO / GA / OR-Tools CP-SAT）。

> **项目主索引：[FEATURES.md](FEATURES.md)** —— 20 个功能模块的完整目标需求清单，
> 重构以其为目标范围；文末附当前基线的实现状态对照。

> **本分支为 2026-10-25 重构后的最小运行基线**：论文制品、历史实验证据链、研究脚本、
> 门禁测试、结项工具与批量实验框架（experiments/）已全部移除（可从 git 历史找回）。
> 多智能体强化学习（MARL）后端因其指标无法归因已于 v1.0.1 移除，
> **勿在任何文档中重新引用 MARL 数字**。

</div>

---

## 🚀 快速开始

**环境要求**：Python 3.10（正式环境锁定 3.10，勿用系统新版 Python）

```bash
python -m pip install -r requirements.txt
```

### 启动 Web 控制台

当前仓库根目录暂无启动脚本（原 `start_console*.bat` 已在重构清理中删除，可在 git 历史找回）。
等价的直接启动方式：

```bash
python -m console.run --portable        # 或安装依赖后去掉 --portable
# 浏览器打开 http://127.0.0.1:8765/
```

浏览器端提供 2D/3D 指挥台（FastAPI + Vue3 + Three.js，依赖已本地化）、运行中交互调度、
场景编辑、一键演示剧本与实时态势趋势。

### 单算法评测

```bash
python frontend/evaluate_metrics.py --policy ga ...
# 默认写 results/adhoc/<算法>.csv（运行时自动创建，已在 .gitignore），不碰入库数据
```

批量实验编排（原 `run_conclusion.py` + `experiments/`）已随重构移除；重建需求见
[FEATURES.md §十七 科研实验与算法比较](FEATURES.md)。

## 🗂 项目结构

```
SwarmBalance/
├─ FEATURES.md          # ★ 项目主索引：完整功能需求清单（20 模块）+ 实现状态对照
├─ frontend/            # 仿真内核：drone/environment/route_planner/GA、地图、Web 静态资源
│  ├─ greedy/           # 贪心调度器
│  └─ data/map/         # 杨浦 OSM 地图
├─ backend_si/          # 算法后端：GA（排列编码+贪婪分割解码）、PSO、OR-Tools CP-SAT
├─ console/             # FastAPI Web 控制台（server/run/sim_session/地图实验室/场景库）
├─ config/              # 配置加载与场景（simulation.json、GIS import 代码与模板）
├─ data/                # 地图、风场实测数据与来源登记
└─ requirements.txt     # Python 依赖
```

## 🧠 调度算法

| 算法 | 位置 | 说明 |
|---|---|---|
| Greedy | `frontend/greedy/` | 最近任务贪心，含顺路接入约束（绕行半径/载重/电量/时间窗） |
| GA | `backend_si/ga_scheduler.py` | 排列编码 + 贪婪分割解码，输出每机有序任务链 |
| PSO | `backend_si/pso_scheduler.py` | 粒子群 |
| OR-Tools | `backend_si/ortools_scheduler.py` | CP-SAT 求解器基线 |

四种策略共享同一仿真环境与指标口径（`frontend/metrics_schema.py`）。
自定义算法经 `frontend/scheduling_interface.py` 标准接口接入（对应 FEATURES.md §十一.16）。

## ⚠️ 已知局限

- 历史实验结论（compare CSV、冻结产物）与批量实验框架已随重构移除，性能对比需重新生成后方可声明。
- 回归测试体系已移除；恢复开发时第一步应是重建核心行为测试。
- `/api/compare` 页面对比数据源缺失时返回空表；口径门禁（原 `results/compare_gate.py`）未恢复。
- 启动脚本缺失，暂以 `python -m console.run` 直启（见上）。

## 📄 许可证

MIT，见 [LICENSE](LICENSE)。
