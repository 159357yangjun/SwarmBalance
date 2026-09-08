# 更新日志

本项目采用语义化版本号（Semantic Versioning）。

## [0.2.0] - 2026-09-08

> 大版本：任务链局部搜索与链间迁移落地、禁飞区独立绕飞修复、控制台成为唯一入口
> （一键启动 + 内置评测/出图/自检）、退役 pygame 桌面可视化、补齐单元测试与开源文档。

### 新增

- **2-opt 链内局部搜索**（`chain_codec.improve_chain`）：解码后对每条任务链做
  swap + Or-opt 移位 + 2-opt 反转三种邻域的局部改进，缩短总里程；补齐申请书
  「链内局部搜索」缺口，`chain.local_search` 可开关（用于 A/B 对照）
- **链间任务迁移**（`chain_codec.relocate_between_chains`）：单链局部搜索之后，
  把任务从一条链移到另一条链的更优位置（受载重/链长约束），纠正贪婪分割的
  次优挂载，`chain.relocate_between` 可开关
- **一键启动**：`启动控制台.bat` 双击即启动控制台并自动打开浏览器
  （`console.run` 新增 `--open` 参数）
- **控制台内置评测**：新增「评测」页，在界面上选算法/回合数/步数点「开始评测」，
  后台线程运行并实时返回指标（替代命令行 `evaluate_metrics.py`），
  后端 `/api/evaluate` + `/api/evaluate/status` 接口
- **控制台内置出图与自检**：「对比」页新增「生成对比图」按钮（替代
  `plot_compare_metrics.py`），「评测」页新增「运行自检」按钮（替代
  `python -m unittest`），后端 `/api/plot` + `/api/selftest` 接口（子进程隔离执行）

### 性能优化

- **距离查表缓存**（`PSOOptimizer.euclidean_distance`）：适应度评估中反复计算的
  任务/机巢/仓库距离改为查表，坐标取 2 位小数做 key，上限 20 万条自动清空
- **仿真环境跳过路网解析**：`load_map_data` 拆分为 `load_buildings`（环境专用，
  不再解析+投影整张路网图）与 `load_map_data`（可视化专用）；此前每个
  `Environment` 实例都白付路网解析代价，而环境根本不用路网

### 测试

- 新增 `tests/test_chain_codec.py` 与 `tests/test_no_fly.py`（unittest，零额外依赖）：
  覆盖任务链解码的任务守恒 / 无重复 / 链长载重约束、局部搜索的任务集合不变与
  里程不增、禁飞区的包含 / 安全余量 / 线段相交 / 开关

### 修复

- **解码缩进 bug（严重）**：`greedy_split_decode` 的 `if best_state is None` 缩进
  错误跑到了 for 循环外，导致整个循环只提交最后一个任务、其余全部丢弃（GA 排列
  模式只派 1 单）。由运行验证发现，已修复
- **建筑加载解包 bug**：`environment.py` 按 `load_map_data` 双返回值解包
  `load_buildings`（只返回单值），运行时 `ValueError`，已修复
- **控制台并发竞态（后端）**：`SimSession` 全局单例只锁了创建、没锁读写，
  `step`/`reset`/`snapshot`/`rebuild`/`map` 及两个配置写接口全部加 `RLock` 保护，
  避免双标签页或"边步进边重置"时仿真状态互相干扰
- **控制台步进竞态（前端）**：高倍速下 `setInterval` 会在上一次 step 请求
  未返回时就发下一次，请求堆积乱序。加 `_stepping` 防重入标志，并为
  `stepOnce` 补 try-catch（失败时停播并提示，不再让异常打断定时器）
- **贪心分配载重只增不减**：`_greedy_assignment` 装货后从不卸货，导致滚动载重
  状态越来越"满"，后续任务被误判超载，污染 GA/PSO warm-start 起点质量
- 删除 `environment.py` 顶层无用的 `import osmnx as ox`
- 清理 `tools/osm.py` 拼写错误的死变量 `ubidings_with_height`

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

- **禁飞区绕飞失效**：此前把禁飞区采样点混进建筑 A\* 可见图，一旦起降点被楼宇包围
  （任务点常位于楼旁），A\* 会整体失败并 fallback 直穿禁飞区，硬约束形同虚设。
  改为**独立的禁飞区几何绕飞**（区外沿四边中点 + 四角生成折点，单/双折点择优），
  不再依赖建筑可见图的连通性
- **任务链计数残留**：`is_free` 兜底完成路径未重置 `drone_chain_len`，
  极端情况下会把后续顺路接入永久挡在门外
- **GA 插入变异位置偏移**：移除基因后索引左移未补偿，`i > j` 时插入点偏后一位

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
