# ARCH-04 / 耦合审计与风险分级

> 基于 `master@2ab60c69a806a22d7ba20353dee0571752a0e8e5` 的静态源码审计。等级：**P0** 迁移前必须消除/隔离的研究或运行阻断；**P1** 纵切阶段必须处理；**P2** 可延期。证据状态“事实”表示源码存在，“风险”表示后果需测试证明，不暗示已经复现故障。

| ID | 等级 | 耦合点、静态证据 | 触发与风险（假设或确定性约束） | 拟定隔离/验证 |
| --- | --- | --- | --- | --- |
| C01 | P0 | `SimSession` 默认硬引用 `frontend/data/map/part_of_yangpu.osm`，`experiments/runner.py` 也有 `DEFAULT_OSM` | 不同城市可能继续引用杨浦地图；地图替换还改变障碍与距离模型 | 由显式绝对路径/文件哈希注入，保留旧默认映射；空路径 fail-closed |
| C02 | P0 | `frontend/tools/osm.py` 按 osmnx 可用性使用 osmnx / XML fallback，`_CACHE_DIR` 为磁盘 pickle | 两种解析模式和建筑/关系覆盖差异会改变绕障轨迹；跨运行缓存不是物理证据 | 数据集哈希 + 解析器身份/版本 + 缓存模式入 manifest；固定解析模式对照，不以“地图文件相同”宣称模型完全相同 |
| C03 | P0 | `frontend/environment.py:87-135`、`drone.py:7-8`、`task.py:12-16`、`greedy/scheduler.py:10-26` import 时冻结配置常量 | 同进程两个 World 不同配置会相互污染；热重载容易影响研究结果 | 首批仅进程隔离；多会话同进程设 BLOCKED，直到可证明无全局残留 |
| C04 | P0 | `console/sim_session.py:48-71` 顺序 `importlib.reload`，异常时 `continue` | 可能出现半新半旧类/常量，不能对隐式退回作研究解释 | 原样封装为“重建即影响全部 legacy worker”并限制在单会话；新 Harness 禁止此路径；异常记录 + fail-closed 策略须单独增测 |
| C05 | P0 | `console/server.py:61-76` 全局 `_session`、`_op_lock`，startup 另起预热线程 | 当前只能承诺单服务进程一个交互会话；多 worker/请求竞争及多用户隔离未验证 | LegacyServer 继续单会话；新会话 registry 另命名空间/进程，不共享可变 Environment |
| C06 | P0 | `console/sim_session.py:468-469,540-546` 保存/恢复 Python/NumPy **进程级 RNG**；`task.py:294-297` 可能调用 `random.seed` | 同进程并行会话改变抽样顺序、配对公平性 | 最小纵切对 worker 进程隔离、固定 Seed 和 run 顺序；未验证前禁止线程级并行 |
| C07 | P0 | `experiments/worker.py:39-49` 在 import 前设 `SWARM_BALANCE_SIM_CONFIG`；runner 每 run 启子进程 | 环境变量为进程级，子进程是当前可复现隔离边界 | 保留 runner→worker；新平台必须显式传配置路径并记录 sha256，不把全局 env var 变成多世界开关 |
| C08 | P0 | `frontend/environment.py:1136-1170` 更新时间、生成、运动、统计顺序；`SimSession.step` 先决策后 env.step | 改换 Harness 事件/步长顺序会改变送达、超时、能耗、空载率 | 固定一步一提交；同模型逐步对照事件/状态/指标；不同机制单独命名新模型 |
| C09 | P0 | `frontend/metrics_schema.py:51-87` 列顺序与 `results/compare_gate.py` 口径门；`/api/compare` 依赖来源文件 | 无意改列或跳过口径门会导致跨实验“虚假胜者” | 所有旧结果只读；新增 sidecar，保持旧表头、门禁及按来源拒绝机制 |
| C10 | P1 | `console/server.py` 直接读写 `config/simulation.json` 与 `backend_si/config.yaml` 并调用 rebuild | UI 多次写配置与运行态重建不构成天然事务；失败可能半写（待故障注入） | 启用冻结副本与 patch 预校验；先以兼容 façade 接旧 API，不引入跨配置自动写回 |
| C11 | P1 | `console/server.py:440-533` 演示 patch 使用进程级 `_scenario_backup_text` | 断电/进程退出丢失恢复点；不同使用者共享恢复点 | 旧路保留进程级语义；新路使用明确版本化配置快照和审计日志 |
| C12 | P1 | `console/scene_library.py:43-91` JSON 场景校验、schema_version；`SimSession` checkpoint 是对象 deepcopy | 场景库 ≠ 运行态快照；不能把历史 checkpoint 当可移植存储 | LegacySceneImporter 只读验证；checkpoint 默认 legacy-only，不做推测性反序列化 |
| C13 | P1 | `SimSession._env_generation` 以选定结构字段生成短 MD5 签名；不包括所有内部变化 | 旧检查点跨不同物理模型恢复可能被误认为安全 | 新 Harness 加模型、代码、数据、配置、坐标系的强指纹；保留旧拒绝语义 |
| C14 | P1 | `frontend/data_source.py:209-225` 相对 `frontend/` 或 `config/` 文件名兜底路径 | 同名文件可能解析到非预期输入；换 cwd 产生歧义 | 封装解析优先级；先把解析结果、原始声明、sha256 入运行清单；不暗改旧优先级 |
| C15 | P1 | `backend_si/ga_scheduler.py` 继承 `PSOScheduler`，配置来自 `backend_si/config.yaml`；`SimSession._build_scheduler` 分散导入 | 组件替换如直接按类名加载易错配算法状态/超参数 | Scheduler adapter 声明 algorithm_key/config_hash/source_hash、能力边界 |
| C16 | P1 | `experiments/reproducibility.py` 溯源含算法源码哈希、依赖和输入哈希 | 新入口漏记新 adapter/Harness 代码就无法解释迁移差异 | 扩展 sidecar manifest：adapter、harness、模型 identity；不覆写 legacy manifest |
| C17 | P1 | `console/experiment_service.py:17-24`、`:79-108` 全局 `_process`、`web_status.json`、`web_runner.log` | 同一个服务只跟踪一个批量运行，后台日志可互相覆盖 | 保留 legacy 单作业；新工作区结果路径运行 ID 化，不复用这些全局文件 |
| C18 | P1 | `frontend/tools/osm.py:250-317` pickle 缓存及 PATH_CLEAR 缓存（Environment） | 缓存无效化方式/权限/跨平台差异影响性能甚至解析观察值；具体数值待验证 | 冷/热缓存一致性测试、缓存来源记录；研究对照固定缓存政策 |
| C19 | P1 | `console/server.py:291-308` 50 步上限、逐步获取 `_op_lock` | 批量 step 与单步在插入其他请求时并非天然完全等价 | 以无并发静态夹具证明重复单步语义；并发交错另做契约 |
| C20 | P2 | `console/static/index.html` 直接消费 `/api/snapshot` 结构，含 map、history、events 等 | 替换字段名或让前端补算指标会破坏兼容 | 旧 API JSON shape 冻结并做快照 schema golden；新 API 单独命名 |
| C21 | P2 | `experiments/runner.py` 和 `results/compare/*` 历史结果混存仓库内 | 新实验可能改写 `one_click_latest.csv`、论文图或旧归档 | 输出根目录隔离，哈希核验旧文件只读；不复制“最新结果”到旧比较目录 |
| C22 | P2 | `console/server.py` 应用预设存在失败回滚分支；`scene_library.py` 存储磁盘 JSON | 新事务策略与历史场景行为差异要区分 | 失败注入测试：无效 JSON、无权限目录、scheduler 配置错误、重建异常 |

## 绝对不能“顺手修”的事项

迁移 PR 不改变：`STEP_SECONDS` 或事件顺序、`Task.status` 终态判定、距离/绕障算法、建筑高度推定、风能耗与电池参数、GA/PSO/Greedy/OR-Tools 的决策、随机数消耗序列、任务生成规模、指标定义和 CSV 比较门禁。发现疑似旧 Bug 时先登记，**以独立修复 PR + 新研究基线**处理，禁止在 adapter 内偷偷补正。

## 判定与交叉参考

C01–C09 构成迁移 P0，至少以进程隔离和新旧路径分流作为第一道硬约束。以上源码证据详见 `LEGACY_ARCHITECTURE.md` 固定 SHA 锚点；风险测试及通过/拒绝准则见 `BACKWARD_COMPATIBILITY.md`；处理切片见 `MIGRATION_SLICES.md`。
