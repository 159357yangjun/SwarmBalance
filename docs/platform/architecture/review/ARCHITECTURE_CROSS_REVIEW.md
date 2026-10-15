# ARCHITECTURE_CROSS_REVIEW — ARCH-05 独立架构交叉审查

> 审查日期：2026-10-15；仓库：159357yangjun/SwarmBalance；审查分支：platform/arch-05-review。
> 裁决状态：**HOLD / 不建议冻结 V1 契约**。此文是“来源材料尚未就绪”的可追溯阶段审查，不是四份设计方案的完成态技术背书。
> 变更约束：本 PR 只能新增本文件；不得触碰 ARCH-01～04 分支、业务代码、原 PR，不得合并。

## 0. 审查摘要、数量与判断边界

- **证据/审查门禁阻断：1 项（B-00 / P0）**：ARCH-01～04 四份设计 PR 均未出现，无法锁定 PR HEAD SHA 或读取全部设计交付，因此不能执行真实设计交叉比对。
- **已证实的跨设计技术冲突：0 项**。此数字**不代表设计通过**，而是因四份候选设计缺席，技术冲突不可判定。
- **待验证集成风险：8 项（R-01～R-08，P1×7 / P2×1）**。这些来自旧引擎的真实接口/结构证据，不等同于已确定的新设计问题。
- **可接受的有条件 V1 范围风险：2 项（A-01～A-02）**。只在约束得到书面承诺、测试门达标时可接受；不代表目前批准冻结。
- **设计裁决**：ARCH-01 FAIL（交付/证据门）、ARCH-02 FAIL（交付/证据门）、ARCH-03 FAIL（交付/证据门）、ARCH-04 FAIL（交付/证据门）。FAIL 表示**目前不可验收**，不是对尚未看到的设计内容做负面推断。
- **冻结裁决**：NO-FREEZE。**Draft PR 不得合并**。

### 来源快照与精确身份

| 来源 | PR 编号 / HEAD SHA | 观察结果 | 可复核入口 |
|---|---|---|---|
| 旧引擎共同代码基线 | master@2ab60c69a806a22d7ba20353dee0571752a0e8e5 | 已核实；仅用于审查旧实现 | [master commit](https://github.com/159357yangjun/SwarmBalance/commit/2ab60c69a806a22d7ba20353dee0571752a0e8e5) |
| ARCH-01 世界抽象 | **PR 未发现 / HEAD SHA 无法获取** | 未交付；不可比较 | [全部 PR](https://github.com/159357yangjun/SwarmBalance/pulls?q=is%3Apr) |
| ARCH-02 Harness | **PR 未发现 / HEAD SHA 无法获取** | 未交付；不可比较 | 同上 |
| ARCH-03 组件契约 | **PR 未发现 / HEAD SHA 无法获取** | 在复查时观测到 platform/arch-03-components 分支仅指向 master SHA；**不是设计 PR HEAD** | [分支](https://github.com/159357yangjun/SwarmBalance/tree/platform/arch-03-components) |
| ARCH-04 迁移 | **PR 未发现 / HEAD SHA 无法获取** | 在复查时观测到 platform/arch-04-migration 分支仅指向 master SHA；**不是设计 PR HEAD** | [分支](https://github.com/159357yangjun/SwarmBalance/tree/platform/arch-04-migration) |
| ARCH-05 审查 | platform/arch-05-review；单独由 master 创建 | 本文；独立审查，不改原作者提交 | [审查分支](https://github.com/159357yangjun/SwarmBalance/tree/platform/arch-05-review) |

以上状态来自 2026-10-15 对 GitHub 开放 PR 列表及 refs/heads/platform/arch 前缀的现场查询；已见开放 PR 合计 45 个，未含 ARCH 设计 PR。PR/branch 状态是**可变化的实时观察**，不是不可变历史事实。最终正式复审应重新拉取四个 PR 的 HEAD SHA、文件列表、具体 Blob SHA 和内容。不得把架构任务的聊天提示词、空分支或其他过往文档冒充其完整提交结果。

## 1. 审查方法与证据等级

- E0：当前 GitHub PR/ref 元数据，仅证明交付物是否可读，不能证明设计正确性。
- E1：master 固定 SHA 的旧引擎源码、签名和可直接复核的行号链接。
- E2：四个 ARCH 设计 PR 的精确 HEAD、全量新增/变更文档、接口差异（**尚无**）。
- E3：可执行纵切/回归测试、六种替换场景的日志及 manifest（**未运行，尚无**）。
- 本次覆盖 E0/E1；**未覆盖 E2/E3**。不能报告“四方案已读取/一致”“已跑通场景”“测试成功”“CI 通过”。以下矩阵为**完整待审字段矩阵**而不是冒充已测出的完整差异矩阵。

### 旧实现的直接证据锚点

| 证据 ID | 已证实事实 | 不可变源码链接 |
|---|---|---|
| E-01 | SimSession 默认地图指向 part_of_yangpu.osm，直接构建 Environment；保留 env/obs、scheduler、step_count、事件及 checkpoint | [console/sim_session.py L103–143](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/console/sim_session.py#L103-L143) |
| E-02 | 会话先选算法：greedy 直接调用 greedy_action_from_observation；其余走 scheduler.step(obs,current_time)，然后 env.step(action) | [console/sim_session.py L167–200](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/console/sim_session.py#L167-L200) |
| E-03 | 旧调度接口定义 SCHEMA_VERSION=1.0、Action=Dict[int,List[str]]、Scheduler.act(observation,current_time)；注释约定 observation/action 字段 | [frontend/scheduling_interface.py L1–69](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/frontend/scheduling_interface.py#L1-L69) |
| E-04 | Environment.step 在内部更新派单、任务、时钟、无人机、事件与统计，current_time += STEP_SECONDS，末尾判定 done | [frontend/environment.py L1033–1145](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/frontend/environment.py#L1033-L1145)、[L1245–1281](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/frontend/environment.py#L1245-L1281) |
| E-05 | STEP_SECONDS 源于配置；Drone.update 的位移为 speed × time_step；RouteCost.eta 声明返回 env-step 单位 | [frontend/drone.py L16–25](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/frontend/drone.py#L16-L25)、[L260–269](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/frontend/drone.py#L260-L269)、[frontend/route_cost.py L60–70](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/frontend/route_cost.py#L60-L70) |
| E-06 | server 使用进程级 _session / _op_lock、场景备份变量；step/reset 由 HTTP 层串行保护 | [console/server.py L56–77](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/console/server.py#L56-L77)、[L263–310](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/console/server.py#L263-L310) |
| E-07 | sim_session 显式按依赖序 importlib.reload 多模块，异常时 continue；environment/drone/task 在模块顶层读取配置 | [console/sim_session.py L42–73](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/console/sim_session.py#L42-L73)、[frontend/environment.py L85–135](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/frontend/environment.py#L85-L135)、[frontend/drone.py L7–39](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/frontend/drone.py#L7-L39) |
| E-08 | DataSource 已有 load_drones/load_nests/load_tasks/build_task_source；CSV 的许多缺失列退化为 0、空 ID、默认机巢/优先级；GeoJSON 按 role 解析 | [frontend/data_source.py L40–82](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/frontend/data_source.py#L40-L82)、[L135–161](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/frontend/data_source.py#L135-L161)、[L248–331](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/frontend/data_source.py#L248-L331)、[L337–407](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/frontend/data_source.py#L337-L407) |
| E-09 | Drone 风分量以 m/s 表示，正号约定逆风；能耗公式依据 distance、载重、wind_factor，注释明确载荷归属口径未完全统一 | [frontend/drone.py L128–205](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/frontend/drone.py#L128-L205) |
| E-10 | Environment 提供 set_station_closed；SimSession 在机巢事件后取 env._obs 并重建调度器 | [frontend/environment.py L602–662](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/frontend/environment.py#L602-L662)、[console/sim_session.py L256–295](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/console/sim_session.py#L256-L295) |
| E-11 | 禁飞区有独立进程级 _CACHE；热重载/reset 必须显式协调 | [frontend/no_fly_zone.py L180–196](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/frontend/no_fly_zone.py#L180-L196) |
| E-12 | 配置校验限定数据源 random/csv/geojson，非 random 仅警告 Web 编辑器不修改源数据 | [console/config_validation.py L79–91](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/console/config_validation.py#L79-L91) |
| E-13 | 现有算法通过 _build_scheduler 内 if/elif 显式枚举四种实现；snapshot 返回 time、step、对象、事件、统计等投影 | [console/sim_session.py L1278–1293](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/console/sim_session.py#L1278-L1293)、[L663–686](https://github.com/159357yangjun/SwarmBalance/blob/2ab60c69a806a22d7ba20353dee0571752a0e8e5/console/sim_session.py#L663-L686) |

## 2. 全量跨方案接口差异矩阵（截至本次：E2 缺失，逐行 WAIT）

**记法**：W=尚未收到正式 ARCH 文档，不等于概念冲突；旧引擎列为已观察事实；“待核对”是对 ARCH 任务负责人的严格提交要求。所有行 **差异状态均为 UNVERIFIED**，无法打勾。

| ID | 交叉契约/接口参数 | ARCH-01（世界） | ARCH-02（Harness） | ARCH-03（组件） | ARCH-04（迁移） | 旧引擎锚点 | 必需裁决 / 责任 |
|---|---|---|---|---|---|---|---|
| M-01 | Project / World / Scenario / WorldState 身份、寿命、引用关系 | W | W | W | W | E-01 | 唯一实体 ID 与版本；01 主、02/04 会签 |
| M-02 | Entity spec 与 mutable EntityState 区分 | W | W | W | W | E-04,E-08 | 定义不可变规格/可变状态边界；01 主 |
| M-03 | 世界状态唯一写入者、状态快照 | W | W | W | W | E-01,E-04,E-13 | 环境/运行器不能同时独立提交；02 主、01 会签 |
| M-04 | 事件产生/排队/同时间冲突/提交顺序 | W | W | W | W | E-04,E-10 | 确定固定步与事件序；02 主、01/03 会签 |
| M-05 | sim_time_seconds / step_index / wall_time | W | W | W | W | E-04,E-05,E-13 | 明确时间单位、换算、舍入与终止门；02 主 |
| M-06 | x/y 坐标系、距离 m、速度 m/s、坐标变换 | W | W | W | W | E-01,E-05,E-08 | 经纬度与平面坐标不可直接混用；01 主、03 会签 |
| M-07 | Entity/Resource ID、引用与占用独占 | W | W | W | W | E-08,E-10 | 缺失、悬挂引用和机巢泊位的拒绝策略；01 主 |
| M-08 | Observation schema 及只读性 | W | W | W | W | E-02,E-03 | 来源 WorldState 版本、字段/单位与兼容版本；03 主、02 会签 |
| M-09 | Scheduler 输入输出：act vs step，Action 索引语义 | W | W | W | W | E-02,E-03,E-13 | 新契约签名及 greedy/PSO/GA/OR-Tools adapter；03 主、04 会签 |
| M-10 | DynamicsModel：apply/advance/energy quote 与误差 | W | W | W | W | E-04,E-05,E-09 | 谁扣电、谁更新位移，禁止双扣/重复推进；03 主、02 会签 |
| M-11 | DataProvider：load、导入验证、缺字段与 provenance | W | W | W | W | E-08,E-12 | fail-closed / 默认值及报错码；03 主、01 会签 |
| M-12 | SpatialProvider：地图源、障碍物/禁飞区与缓存 | W | W | W | W | E-01,E-11 | CRS、加载权限、缓存归属/失效；03 主、04 会签 |
| M-13 | EventProvider：外生风场、故障、需求时间序列 | W | W | W | W | E-09,E-10 | 事件时间与作用点、重复事件幂等；03 主、02 会签 |
| M-14 | MetricProvider：状态读、累加/重算与来源 | W | W | W | W | E-04,E-09,E-13 | 不允许 KPI 随更换能耗模型悄悄改定义；03 主、04 会签 |
| M-15 | 组件 initialize / step / dispose / reset 生命周期 | W | W | W | W | E-01,E-07 | 错误回滚、释放顺序、幂等重置；03 主、02 会签 |
| M-16 | 组件能力、依赖、版本、替换前兼容性检查 | W | W | W | W | E-03,E-13 | 不兼容明确拒绝，不 silent fallback；03 主 |
| M-17 | DatasetManifest / ModelManifest / 配置优先级 | W | W | W | W | E-07,E-08,E-09 | 精确内容 Hash、单位、假设、种子、版本；03 主、04 会签 |
| M-18 | PRNG：seed、流分配、重试/并行重现 | W | W | W | W | E-01,E-07 | 独立 RNG context，记录状态，控制外部全局；02 主 |
| M-19 | 异常：无效动作、组件超时、部分写入、失败隔离 | W | W | W | W | E-04,E-06,E-07 | 错误类型、回滚边界和进入 FAILED/PAUSED 的状态机；02 主 |
| M-20 | Lifecycle：create/assemble/init/run/pause/step/stop/reset/destroy | W | W | W | W | E-01,E-06 | 禁止未初始化执行、停止后复活、隐含重建；02 主 |
| M-21 | LegacyEnvironmentAdapter / LegacySchedulerAdapter | W | W | W | W | E-02,E-03,E-04 | 只能一个方向适配，阻止循环回依赖；04 主、03 会签 |
| M-22 | 旧/新引擎切换：快照、配置、日志、指标对齐 | W | W | W | W | E-01,E-06,E-13 | 区分同一场景新 run 与运行时迁移，严禁伪等价；04 主 |
| M-23 | 依赖方向：domain/contracts → components → harness → UI | W | W | W | W | E-01,E-06,E-07 | 禁止契约 import 具体 adapter 或 UI；02/03 主 |
| M-24 | 场景版本/事件日志/并发会话隔离 | W | W | W | W | E-06,E-10,E-11 | 从单例过渡的隔离保证；01/02/04 联合 |
| M-25 | 最小纵切的可运行范围与退出标准 | W | W | W | W | E-01,E-02,E-04 | 先 1 world × 1 model × 1 scheduler × 1 task；04 主、全体会签 |

**矩阵解释**：这里列举了全部要求核对的接口面，并给出每一面的旧代码原始位置；但由于四份正式候选架构均缺席，ARCH 列不能凭任务简介填“已一致”或假想接口签名。只有拿到 HEAD SHA 和全量文档后，逐单元填写“精确拟议签名 / 冲突描述 / 修订版本 / 文档行号”，才能称为**已完成的接口差异矩阵**。

## 3. 六类变化场景走查记录（设计侧未可运行，裁决均 BLOCKED）

| S | 改变输入 | 已见旧引擎行为/潜在边界 | 新设计必须提交的最小证据 | 责任 | 当前裁决 |
|---|---|---|---|---|---|
| S-01 城市地图替换 | OSM-A → OSM-B；建筑坐标不同 | E-01 默认上海杨浦 OSM 路径；E-04 Environment.__init__ 载图；E-11 缓存存在 | World 配置地图引用，CRS 转换、图层 hash 与缓存失效；同一 harness 不改代码能载入两城 | 01/03/04 | BLOCKED |
| S-02 能耗模型替换 | 旧经验能耗 → 新模型 | E-09 计算位于 Drone.consume_battery；E-04 Environment 统计 delta | 同一航段在两模型跑，版本/单位/来源记录，唯一扣费位置，原模型回归不漂移 | 03/02/04 | BLOCKED |
| S-03 新调度算法 | 加自定义 Scheduler-X | E-02 实际调用 .step；E-03 抽象接口 .act；E-13 枚举算法硬编码 | 插件/adapter 注册可识别；输入 Observation、输出 Action、非法动作被拒，保留 Greedy 旧基线 | 03/04 | BLOCKED |
| S-04 时变风 + 机巢故障 | t=30s 风变化、t=45s 机巢关闭 | E-09 风按调用注入，E-10 支持临时关站与重启调度器 | 同时事件优先级、更新原子性，状态归属，一致日志，重复重放结果完全一致 | 01/02/03 | BLOCKED |
| S-05 缺字段数据集 | CSV 缺坐标/任务 ID/电量字段 | E-08 多处空 ID/0/default；E-12 校验仅限部分配置 | DatasetManifest 必填/可选约束；错误数据不得悄悄变成 (0,0) 实际任务；错误诊断字段级可追踪 | 03/01 | BLOCKED |
| S-06 新旧引擎切换 | legacy/new 用同一场景 seed 执行 | E-06 旧服务单例；E-07 模块 reload；E-13 snapshot | adapter 保持数据意义；same-input 双路径差异报告、不会复用同一可变对象、能回退，不冒称恢复中间状态 | 04/02 | BLOCKED |

上述是**静态设计输入走查**，不是六项演练通过；没有做运行测试、没有实际切引擎、没有制造真实故障。

## 4. 风险分级、直接证据、责任归属与建议处理

分级：P0=阻止评审/冻结；P1=纵切前必须决策并验证；P2=可在约束下延后。风险项不是已经确认四份设计相互矛盾。

| ID | 级别 / 分类 | 证据与风险原因 | 责任人（设计任务） | 处理与门禁 |
|---|---|---|---|---|
| **B-00** | **P0 / 门禁阻断** | E0：ARCH-01～04 PR 不存在/不可读取，精确 PR HEAD 和交付范围缺失 | 01～04 负责人分别补交；05 复审 | 四个 Draft PR 与 SHA、所有文档读取成功后解除；本轮 FAIL / NO-FREEZE |
| R-01 | P1 / 状态所有权 | E-01/04/13：Environment 拥有动态实体、统计；SimSession 又维护事件、history、checkpoint、step；新方案需定义唯一 authoritative state 与投影 | ARCH-01+02 | 明确单写入器及版本化 read view；强制不可变观察 |
| R-02 | P1 / 调度接口 | E-02/03：SCHEMA 的 Scheduler.act 与实际 SimSession.scheduler.step 调用不一致；已有实现可能另有各自入口 | ARCH-03+04 | 冻结一个 V1 调用签名，列全量适配器测试 |
| R-03 | P1 / 时钟与单位 | E-04/05/13：current_time 按 STEP_SECONDS 增加；step_count 是次数；路由 ETA 返回 env-step；命名有混用可能 | ARCH-01+02+03 | 二字段 time_seconds/step_index，不可拿索引当秒；更改时间步长作变形测试 |
| R-04 | P1 / 配置与缓存 | E-07/11：多个模块 import 时读配置，reload 异常 continue；全局禁飞区 cache | ARCH-02+04 | 组件上下文注入配置；明确缓存租期和失败拒绝策略；不吞 reload 错 |
| R-05 | P1 / 数据完整性 | E-08/12：CSV 缺列、空坐标/ID 可被默认值掩盖；输入契约要求明确 | ARCH-03+01 | DatasetManifest 区分 required/optional，诊断缺字段及坐标系；不可静默用 (0,0) |
| R-06 | P1 / 物理/统计口径 | E-09：已有能耗载荷归属口径争议，动态模型替换会污染结果可比性 | ARCH-03+04 | 能耗模型接口携带单位、版本、假设与归属策略；单独 compare gate |
| R-07 | P1 / 故障事件 | E-10：机巢关站直接变更 env 并 restart scheduler；新 EventProvider 还可能请求相同状态写 | ARCH-01+02+03 | 事件统一通过 Harness command→validate→commit；拒绝双写 |
| R-08 | P2 / 地图默认 | E-01：默认 Yangpu OSM 路径内嵌 SimSession | ARCH-04+01 | V1 legacy adapter 内保留旧默认，平台 World 的 map URI 必须显式配置 |
| A-01 | P2 / 有条件可接受 | E-01/07：旧引擎单会话与 import/reload 耦合无法立刻消失 | ARCH-04 | **允许 legacy 继续单实例**，前提是以进程/会话边界隔离，不声称新 Harness 多会话已支持 |
| A-02 | P2 / 有条件可接受 | E-04/05：既有 fixed-step 模拟已有可追溯执行路径 | ARCH-02 | **允许 V1 只实施固定步长 + 定点注入事件**，DES 作为未来能力，不提前做双运行时钟调度器 |

### 循环依赖、职责重复、隐藏全局和领域硬编码审查结果

- **循环依赖**：四份未来架构的真实依赖图未交付，结论 **UNKNOWN**；旧代码中 server→SimSession→Environment→Drone/DataSource 的依赖需列图，但不能据此声称新设计“存在循环”。
- **职责重复**：已观察 E-01/04 的 session/env 状态统计重叠、E-02/03 的调度入口表述不一致；是否为计划保留的 projection/adapter，必须由 ARCH-02/03/04 明文分工。
- **隐藏全局**：E-06/07/11 可定位进程级会话、配置常量、禁飞区 cache，属于迁移时必须封装的真实基线耦合。
- **领域硬编码**：E-01 默认地图、E-13 枚举算法是真实遗留特例；不能直接提升为 World/Harness 公共契约。
- **异常语义**：E-07 reload 异常继续；与新契约期望 fail-closed 的关系有待 ARCH-02/04 书面规定。
- **直接依赖证明**：未来必须提交组件/模块依赖 DAG 和构建期 cycle 检查，图中不得有 domain→legacy implementation 的反向 import。

## 5. 最小纵切复杂度评审

**当前判定：CONDITIONAL（仅为建议目标，不是审过四份纵切设计）。** 文档缺失，无法判断作者是否已经过度设计。

建议最小可执行纵切只包含：1 个离线/合成 World、1 个静态地图（或无障碍坐标）、1 架 Drone、1 个任务、1 个机巢、1 个简单 DataProvider、1 个能耗 DynamicsModel、1 个 SchedulerAdapter、一个 fixed-step Harness 和一套只读 Snapshot/RunManifest；最小四步：load → initialize(seed) → step(action) → snapshot/checksum。同一输入运行两次须逐步一致，失败时不提交半成状态。随后以受控 feature flag 与 legacy 同场景双运行对照。

首个纵切**不得强制引入** UI 改造、组件市场、动态热插拔、远程分布式 worker、数据库编排、泛化工作流 DSL 或固定步+DES 两套完整调度内核。若 ARCH-01～04 要求这些是 V1 首验前置，则判定为**潜在过度设计 P1**，需以可验证收益证明，否则剔除。

纵切验收：
1. 世界状态只有一个提交位置，组件输入是不可变/只读视图；禁止重复扣电。
2. 两次 seed+config+model version 固定的 run 产生同 checksum；快照与事件日志可溯源。
3. 切换一个地图/调度器/能耗模型无需修改 Harness 内核。
4. legacy/new 两路径对相同输入提供明确不可比项列表；失败不破坏旧路径。

## 6. 按设计任务正式门禁裁决（截至本次审查快照）

| 任务 | 交付性 | 一致性审查 | 责任 / 修复要求 | 最终判定 |
|---|---|---|---|---|
| ARCH-01 世界抽象 | PR/HEAD/全量文档缺失 | M-01～M-08、M-13/M-24 未核对 | ARCH-01：补齐 Draft PR、SHA、Entity/World/State/CRS/资源引用/动态场景定义；再交叉走查 | **FAIL（证据门，非设计内容失败）** |
| ARCH-02 Harness | PR/HEAD/全量文档缺失 | M-03～M-05、M-15/M-18～M-20 未核对 | ARCH-02：补齐生命周期、唯一写入者、事件顺序、RNG、异常 rollback | **FAIL（证据门，非设计内容失败）** |
| ARCH-03 组件 | PR/HEAD/全量文档缺失；空工作分支不足以证实交付 | M-08～M-17、M-23 未核对 | ARCH-03：补齐 6 provider 最小签名、manifest/units/compat 诊断与替换实例 | **FAIL（证据门，非设计内容失败）** |
| ARCH-04 迁移 | PR/HEAD/全量文档缺失；空工作分支不足以证实交付 | M-21～M-25 未核对 | ARCH-04：补齐依赖图、legacy adapter、旧新双路径、回退、安全验收与纵切计划 | **FAIL（证据门，非设计内容失败）** |

## 7. V1 冻结前必须满足的审查门（均尚未满足）

| 门 | 验收条件 | 当前 |
|---|---|---|
| G-ARCH-1 | 四个具体 Draft PR 的编号、full HEAD SHA、base SHA、状态锁定；变更文件清单完整 | **BLOCKED** |
| G-ARCH-2 | 逐份读取四个 PR 的**全部**设计文档、正向/反向引用；E2 逐行可追踪 | **BLOCKED** |
| G-ARCH-3 | M-01～M-25 均有四方案真实签名/语义，差异为 0 或有带责任人的接受决定 | **BLOCKED** |
| G-ARCH-4 | 六个 S-01～S-06 走查结果有配置、日志或伪代码级完整运行路径证据 | **BLOCKED** |
| G-ARCH-5 | 组件依赖 DAG、状态所有权、RNG、时间/单位、异常和非法状态拒绝机制审定 | **BLOCKED** |
| G-ARCH-6 | 纵切最小范围冻结、与 legacy E0/E1 的行为回归/对照门定义 | **BLOCKED** |
| G-ARCH-7 | 每个风险 R-01～R-08 被方案显式消除或书面接受，责任及验收负责人明确 | **BLOCKED** |
| G-ARCH-8 | ARCH-05 更新至最新 PR HEAD SHA 且唯一文件变更核验完成 | **待最终检查** |

### 对主控的建议裁决

**现在：HOLD；不建议冻结 V1 契约；不建议合并 ARCH-01～05。** 当四个设计 PR 就绪后，应重新以精确 SHA 进行独立审查，填实矩阵，复核六场景与纵切，并重新赋予四项设计 PASS/CONDITIONAL/FAIL 内容判决。ARCH-05 只能作为独立审查记录，不可倒置为设计先验批准。无效结果不是失败的项目设计，而是**本轮证据尚未具备**。

---
审查约束确认：无代码修改、无原设计分支修改、无既有 PR 修改、未合并；静态源码审查而非运行验证。