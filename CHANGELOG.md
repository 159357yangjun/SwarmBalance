# 更新日志

本项目采用语义化版本号（Semantic Versioning）。

## [0.1.0] - 2026-09-08

首个对外发布的版本，覆盖项目申请书承诺的核心仿真能力与算法对比框架。

### 新增

**调度算法**

- Greedy 贪心基线（距离 / 优先级 / 紧迫度 / 电量 / 载荷 实时打分）
- PSO 粒子群批量分配 + 事件驱动双通道框架
- GA 遗传算法，支持 `permutation`（排列编码 + 贪婪分割解码）与 `assignment`（分配矩阵）双编码
- OR-Tools CP-SAT 经典求解器基线
- MARL 多智能体强化学习（IQL / VDN / QMIX 及其 `-U` 改进版）

**任务链与顺路接入**

- `backend_si/chain_codec.py`：排列编码 → 贪婪分割解码，输出每机有序任务链
- 在途无人机按绕行半径 / 载重 / 电量 / 时间窗约束顺路追加任务
- `frontend/ab_chain_test.py`：任务链机制开/关 A/B 对照脚本

**禁飞区**

- `frontend/no_fly_zone.py`：circle / polygon 禁飞区，含安全余量外扩
- 接入 `is_path_clear()` 与 A\* 可见图，实现真绕飞
- 任务取送货点自动过滤，避免生成不可达任务

**仿真环境**

- 异构机队三种机型（参数取自公开产品规格）
- 机巢有限泊位 + 动态优先级仲裁，整组换电 180 秒
- 可插拔数据源：random / CSV / GeoJSON / 企业 REST 网关

**评估与可视化**

- `frontend/metrics_schema.py`：统一指标落盘 schema（单一事实来源，自动备份不覆盖）
- 新增机队利用率、空载率、总飞行距离、顺路接入次数、禁飞区绕飞次数指标
- 原生 pygame 三维软件投影窗口（`frontend/run_visual.py`）
- Web 可视化控制台（`console/`，FastAPI + Vue3 + Three.js）

### 修复

- **送达即卸货**：此前 `current_load` 仅在整条航线跑完时清零，在途机永远「满载」，
  导致追加任务必被载重检查拒绝、任务链无法生效
- **异源航线追加**：此前只有同源任务能追加到在途航线，异源任务会覆盖整条航线导致前序任务丢失
- 统一四类算法的随机种子（`seed = 100 + episode_id`），此前 Greedy 未传 seed 导致场景不对齐
- 统一 CSV 表头口径，修复汇总脚本 `KeyError: Missing algorithm column`
- 表头不兼容时自动备份旧 CSV，不再静默覆盖历史实验结果

### 已知局限

- 任务链仅在航线尾部追加，未实现最优插入与链内局部搜索
- 禁飞区为静态配置，未实现时变管制
- `frontend/nest.py` 为未被环境引用的冗余死代码
