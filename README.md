<div align="center">

# SwarmBalance · 群智优衡

**异构无人机集群三维协同调度仿真平台**

[![Python](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)](README.md)
[![Algorithms](https://img.shields.io/badge/algorithms-5%20families-orange.svg)](README.md)

面向城市低空物流配送场景，构建**任务生成 → 调度决策 → 飞行仿真 → 指标评估 → 可视化**的完整闭环，
在同一物理口径下横向对比五类调度方法。

</div>

---

## ✨ 核心特性

| 特性 | 说明 |
|---|---|
| **五类算法统一评测** | Greedy / PSO / GA / OR-Tools(CP-SAT) / MARL(IQL·VDN·QMIX)，共享同一仿真环境与指标口径 |
| **异构机队** | 轻载·标准·重载三种机型，参数取自美团、顺丰丰翼、大疆公开产品规格 |
| **任务链调度** | GA 采用**排列编码 + 贪婪分割解码**，输出每机一条有序任务链 |
| **顺路接入** | 在途无人机按绕行半径 / 载重 / 电量 / 时间窗约束，把下一单直接挂到当前航线 |
| **禁飞区约束** | 支持圆形与多边形禁飞区（含安全余量），接入 A\* 路径规划实现真绕飞 |
| **机巢地面资源** | 有限泊位 + 动态优先级仲裁（电量紧迫度 + 等待时长 + 任务紧迫度），整组换电 180 秒 |
| **双形态可视化** | 原生 pygame 三维软件投影窗口 + 浏览器 Web 控制台（FastAPI + Vue3 + Three.js） |
| **真实数据接入** | 随机 / CSV / GeoJSON / 企业 REST 网关四种数据源，可插拔 |

---

## 🚀 快速开始

### 环境要求

> ⚠️ **必须使用 Python 3.10**。`osmnx==1.9.4` 声明 `Requires-Python <3.13`，实测 3.11/3.12 会出现
> geopandas 组合问题，3.13 直接装不上。推荐 3.10.11。

```bash
git clone https://gitee.com/acgvgh/swarm-balance.git
cd SwarmBalance

# 1) 创建虚拟环境
python -m venv .venv310
source .venv310/bin/activate          # Windows: .venv310\Scripts\activate

# 2) pip 固定到 23.x（pip 26.2.x 在 Windows 有 safe-delete bug，会卡死甚至损坏 pip）
python -m pip install "pip==23.3.2"

# 3) 先钉 numpy，再装其余（顺序不能反！）
pip install numpy==1.26.4
pip install -r requirements.txt
```

> **为什么必须先装 numpy？** `ortools` 会把 numpy 升到 2.x，而 `osmnx==1.9.4` 要求 `numpy<1.27`，
> 升级后 osmnx 会报 `numpy._utils` 错误、甚至被连带卸载 geopandas。

### 跑一次评测

```bash
cd frontend
python evaluate_metrics.py --policy ga --episodes 1 --episode-steps 600 --seed 100
```

输出示例：

```
Episode 1 (seed=101): 完成率=0.7667, 超时率=0.0435, 平均时延=0.4565,
完成=23/30, 利用率=0.706, 空载率=0.499, 顺路接入=5, 禁飞绕飞=7
```

### 打开可视化

```bash
# 原生桌面窗口（pygame 三维视图，鼠标拖拽旋转 / 滚轮缩放）
cd frontend
python run_visual.py --algo greedy

# 或浏览器控制台
python -m console.run          # 然后打开 http://127.0.0.1:8765/
```

---

## 🧠 调度算法

| 方法 | 定位 | 编码 / 求解 | 代码位置 |
|---|---|---|---|
| **Greedy** | 基线 | 距离 + 优先级 + 紧迫度 + 电量 + 载荷 实时打分 | `frontend/greedy/` |
| **PSO** | 群体智能 | 偏好矩阵编码，粒子群批量优化 + 事件驱动 | `backend_si/pso_scheduler.py` |
| **GA** | 群体智能（主推） | **排列编码 + 贪婪分割解码** / 分配矩阵（可切换） | `backend_si/ga_scheduler.py`、`chain_codec.py` |
| **OR-Tools** | 经典求解器基线 | CP-SAT，0/1 分配，目标 `makespan + Σ超时量` | `backend_si/ortools_scheduler.py` |
| **MARL** | 强化学习扩展 | PyMARL：IQL / VDN / QMIX（含 `-U` 改进版） | `backend_wx/pymarl-master/` |

**GA 的两种编码**（`backend_si/config.yaml` 的 `ga.encoding` 切换）：

| 编码 | 染色体 | 解码 | 遗传算子 | 用途 |
|---|---|---|---|---|
| `permutation`（**默认**） | 任务排列 | 贪婪分割 → 每机有序任务链 | OX 顺序交叉 + 交换/插入/片段逆序变异 | 任务链优化引擎的落地实现 |
| `assignment` | 任务 → 无人机下标 | 直接分配 | 均匀交叉 + 负载感知变异 + 容量修复 | 与 PSO 同构，用于 A/B 对照 |

> 项目申请书规划的是「贪心 / 经典求解器 / 本项目优化算法」三种方案，PSO 与 MARL 属于实现阶段的扩展对比。
> 口径对应关系与扩展理由见 [`算法口径说明.md`](算法口径说明.md)。

### 任务链与顺路接入

1. **优化器侧**：排列经贪婪分割解码后直接产出「每机一条有序任务链」，链内顺序不再被动态贪心重排打散；
2. **调度器侧**：`PSOScheduler` 每步检查在途无人机，若链条未满、取货点在绕行半径内、载重与电量允许、且接入后不超时，就把下一单挂到当前航线尾部，省掉「送完回巢/待命 → 再出发」的空驶与等待。

配置在 `config/simulation.json`：

```json
"task_chain": {
  "enabled": true,
  "max_chain_tasks": 3,
  "max_detour_m": 1500.0,
  "battery_reserve_ratio": 0.15
}
```

机制开/关对照实验：

```bash
cd frontend
python ab_chain_test.py --policies pso ga --episodes 1 --episode-steps 1200
```

### 禁飞区

`config/simulation.json` 的 `no_fly_zones` 段，支持 `circle` / `polygon`，含安全余量外扩：

```json
"no_fly_zones": {
  "enabled": true,
  "reserve_margin_m": 15.0,
  "zones": [
    { "name": "医院应急通道", "type": "circle", "center": [358300.0, 3462500.0], "radius": 150.0 },
    { "name": "管制空域A", "type": "polygon", "points": [[358950,3462750],[359150,3462750],[359150,3462950],[358950,3462950]] }
  ]
}
```

禁飞区是**硬约束**，采用**独立于建筑 A\* 的几何绕飞**（在区外沿生成绕飞折点），
保证绝不穿越；建筑仍走 A\* 可见图绕行（软约束，失败时允许直穿并告警）；
落在禁飞区内的取送货点会被自动过滤，避免生成不可达任务污染完成率。
实现见 `frontend/no_fly_zone.py`。

---

## 🗂 项目结构

```text
SwarmBalance/
├─ config/
│  ├─ simulation.json          # 仿真环境、任务、无人机、禁飞区、任务链配置
│  ├─ positions.json           # 任务位置数据
│  └─ import/                  # CSV / GeoJSON 真实数据样例
├─ frontend/                   # 仿真环境与评估入口
│  ├─ environment.py           # 仿真环境、指标统计、A* 路径规划
│  ├─ drone.py                 # 无人机运动、电量（换电）与载重
│  ├─ task.py                  # 任务模型与任务生成器
│  ├─ charging_station.py      # 机巢（换电站）模型
│  ├─ no_fly_zone.py           # 禁飞区约束
│  ├─ data_source.py           # 数据源抽象（random/csv/geojson/enterprise）
│  ├─ metrics_schema.py        # 统一指标落盘 schema（单一事实来源）
│  ├─ map_drawer_3d.py         # 三维软件投影可视化
│  ├─ run_visual.py            # 桌面可视化入口
│  ├─ evaluate_metrics.py      # 四算法统一评测入口
│  ├─ ab_chain_test.py         # 任务链开/关 A/B 对照
│  └─ greedy/                  # 贪心调度器
├─ backend_si/                 # 群体智能调度器（PSO / GA / OR-Tools）
│  ├─ pso_scheduler.py         # PSO 优化器 + 事件驱动调度框架
│  ├─ ga_scheduler.py          # GA 优化器（排列 / 分配双编码）
│  ├─ chain_codec.py           # 排列编码 → 贪婪分割解码
│  ├─ ortools_scheduler.py     # CP-SAT 基线
│  └─ config.yaml              # 算法超参
├─ backend_wx/pymarl-master/   # 多智能体强化学习（IQL / VDN / QMIX）
├─ console/                    # Web 可视化控制台（FastAPI + Vue3 + Three.js）
├─ results/
│  ├─ compare/                 # 各算法统一指标 CSV
│  └─ plot_compare_metrics.py  # 指标汇总、归一化评分与绘图
└─ paper/                      # 课程论文、插图与 Overleaf 工程
```

---

## 🛩 仿真场景

统一 **1 步 = 1 秒** 时间口径，机巢**整组换电**（约 180 秒，换电期间不可接单）。

- 10 架异构无人机，三种机型；
- 最多 60 个配送任务，重量按「外卖/小件 → 快递包裹 → 重货」三档真实分布抽样；
- 任务含重量、体积、类别、优先级、起终点与 SLA 截止时间；
- 任务按高峰期 / 非高峰期 / 热点区域动态生成；
- 默认单回合 3600 步（1 小时）。

### 异构机型（真实产品参数）

| 机型 key | 参考产品 | 航速 (m/s) | 载重 (kg) | 电池 (Wh) | 满载续航 (km) |
|---|---|---|---|---|---|
| `light_express` | 美团第四代配送无人机 | 20 | 2.4 | 380 | 10 |
| `standard_cargo` | 顺丰丰翼方舟 ARK40 | 14 | 10 | 1600 | 20 |
| `heavy_cargo` | 大疆 FlyCart 30 双电 | 20 | 30 | 3968.8 | 16 |

> 上述为公开规格近似取值，用于仿真对比，实际以官方最新发布为准。

### 真实数据接入

`data_source.type` 支持 `random` / `csv` / `geojson` / `enterprise`。
新增一个 `DataSource` 子类（实现 `load_drones` / `load_nests` / `load_tasks` / `build_task_source`）
即可接入企业真实订单、机队与机巢数据，**无需改动环境与调度算法**。

```python
from environment import Environment
from enterprise_data_source import EnterpriseDataSource

ds = EnterpriseDataSource(base_url="https://tms.example.com", api_token="…", coord_system="lonlat")
env = Environment("data/map/part_of_yangpu.osm", data_source=ds)
```

- `coord_system="lonlat"` 时自动用 pyproj 把 WGS84 经纬度投影为 UTM 平面坐标（米）；
- `live=true` 每步轮询接口并按订单号去重，对应真实订单持续到达；
- 无网关时可运行 `frontend/mock_enterprise_api.py` + `run_enterprise_demo.py` 预览。

---

## 📊 评估指标

| 指标 | 含义 | 方向 |
|---|---|---|
| Completion Rate | 已完成任务数 / 已生成任务数 | 越高越好 |
| Timeout Rate | 超时任务占已完成任务比例 | 越低越好 |
| Average Delay | 超时任务平均超时时长 | 越低越好 |
| Generation-to-Assignment Wait | 生成 → 被分配的等待时间 | 越低越好 |
| Assignment-to-Loading Wait | 分配 → 实际装载的等待时间 | 越低越好 |
| Loading-to-Delivery Time | 装载 → 送达的平均时间 | 越低越好 |
| Avg / Max Generation-to-Completion | 全流程平均 / 最大耗时 | 越低越好 |
| Priority Average Delay | 各优先级任务平均时延 | 越低越好 |
| Total Energy Consumption | 机队累计能耗 | 越低越好 |
| **Drone Utilization** | 机队利用率（忙步数 / 总步数） | 越高越好 |
| **Empty Load Ratio** | 空载率（空载里程 / 总里程） | 越低越好 |
| **Chain Insertions** | 顺路接入次数 | 机制生效观测 |
| **No-Fly Detours** | 禁飞区绕飞次数 | 机制生效观测 |
| Berth Utilization / Nest Turnover / Avg Berth Wait | 机巢泊位利用率、周转率、排队等待 | 视运营目标 |

指标列定义集中在 `frontend/metrics_schema.py`（单一事实来源），所有评测入口共用同一份表头，
新增指标只需改这一处。表头不兼容时会自动备份旧 CSV，不会静默覆盖历史实验结果。

---

## 🧪 复现实验

```bash
cd frontend

# 五类算法（seed 统一 = 100 + episode_id，保证跑同一批场景）
python evaluate_metrics.py --policy greedy  --episodes 5 --episode-steps 2000
python evaluate_metrics.py --policy pso     --episodes 5 --episode-steps 2000
python evaluate_metrics.py --policy ga      --episodes 5 --episode-steps 2000
python evaluate_metrics.py --policy ortools --episodes 5 --episode-steps 2000

# 强化学习
cd ../backend_wx/pymarl-master/src
python main.py --config=qmix --env-config=env_drone

# 汇总指标并出图
cd ../../..
python results/plot_compare_metrics.py
```

结果写入 `results/compare/*.csv`，图表输出到 `results/compare/plots/`。

**复现建议**

- 对比实验应保持 `config/simulation.json` 中机队规模、任务数量、生成模式与截止时间一致；
- 各算法使用相同 `episodes` 与 `episode-steps`；
- 强化学习需固定模型、随机种子与测试回合数，并报告**多种子均值与方差**，不能依据单次训练下结论；
- 生成论文图表前确认 CSV 采用的是目标实验行。

---

## 📚 文档

| 文档 | 内容 |
|---|---|
| [`算法口径说明.md`](算法口径说明.md) | 申请书承诺算法与代码实现范围的对应关系、公平性保障、术语修正 |
| [`可视化操作平台完善计划书.md`](可视化操作平台完善计划书.md) | Web 控制台的架构设计与分阶段路线 |
| `backend_si/README.md` | PSO 调度器参数与双通道机制详解 |

---

## 🤝 贡献

欢迎 Issue 与 PR，流程见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。要点：

- 分支用 `ui-member`、`chain-opt` 这类**不带斜杠**的短名；
- 提交前确认 `results/compare/*.csv` 未被误改；
- 新增指标请只改 `metrics_schema.py`，不要在评测脚本里另起表头。

---

## ⚠️ 已知局限

- 任务链目前只在**航线尾部追加**，未实现 VRP 最优插入与 2-opt / Or-opt 链内局部搜索；
- 顺路接入的绕行判定用**绝对半径**（默认 1500 米，约为本地图跨度 55%），换地图需重新标定；
- 排列编码的解码是一次贪心扫描，未做链间任务交换等解码后局部改进；
- 禁飞区为静态配置，未实现时变管制，也未耦合气象与通信丢包；
- `frontend/nest.py` 的机巢仲裁类未被 `environment.py` 引用，属冗余死代码（待清理）；
- 仿真为离散时间步，未模拟天气、通信丢包等真实低空约束。

---

## 📄 许可证

本项目采用 [MIT License](LICENSE)。

## 📖 引用

若本项目对你的研究有帮助，请引用（另见 [`CITATION.cff`](CITATION.cff)）：

```bibtex
@software{swarmbalance2026,
  title  = {SwarmBalance 群智优衡: 异构无人机集群三维协同调度仿真平台},
  author = {群智优衡项目团队},
  year   = {2026},
  url    = {https://gitee.com/acgvgh/swarm-balance}
}
```

---

<div align="center">

北华大学 · 大学生创新创业训练计划项目（2026.06 — 2028.05）

</div>
