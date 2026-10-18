# ARCH-01 — 世界抽象与边界（World Model）

状态：Design Draft v0.1；仅设计，不改变旧仿真行为。
基准：SwarmBalance master @ 2ab60c69a806a22d7ba20353dee0571752a0e8e5。
负责范围：世界概念、静态定义、空间与单位约束；执行生命周期归 ARCH-02，组件运行协议归 ARCH-03。

## 1. 结论与不可变约束

**World 不是旧 Environment 的改名**。World 表示可持久化且可版本化的世界静态定义；仿真运行所产生的可变信息属于某一个 Run 的 WorldState。新核心不得 import 旧 frontend.environment、OSM、具体无人机型号、Greedy/GA/PSO 或 Web 控制台。

- 不以 OSM、某一个城市、单个仓库、二维平面或某组固定机型作为世界的内在属性。
- 以稳定 ID 和显式空间参考引用事物，不允许用数组下标作跨组件身份。
- 物理量必须具备统一规范单位，输入单位变换只能在导入边界进行，不得无提示猜测。
- 静态定义与可变状态分离；状态写入由 ARCH-02 指定的唯一提交者控制。
- 模型和规则只能产生声明式建议/结果，不能直接修改其他实体的属性。
- 相同的世界版本、场景版本、组件版本、随机流和事件顺序应支持重放；不声称现有代码已满足这一条。

## 2. 既有实现审计与迁移切割点

| 旧路径 / 类型 | 当前职责（已从 master 源码确认） | 目标边界 |
| --- | --- | --- |
| frontend/environment.py / Environment | 接收 OSM 文件路径；加载路网建筑、构造禁飞区与 RoutePlanner；创建无人机、机巢、任务源；执行派单、推进时间、更新无人机、泊位仲裁、指标累计 | LegacyEnvironmentAdapter；拆为 SpatialProvider、规则组件、状态与指标输出 |
| frontend/drone.py / Drone | 机型规格、位置、任务/航线、电池、换电、事故状态；update() 同时更新位置与电量并触发低电改道 | DroneDefinition / DroneState；运动、能耗、低电控制为外部组件 |
| frontend/task.py / Task | 重量、体积、起终点、deadline、status、生成时刻；TaskGenerator 内含动态未分配队列 | TaskDefinition / TaskState；到达流归场景/数据组件 |
| frontend/charging_station.py / ChargingStation | 机巢规格、closed、occupied；Environment._nest_waiting 承担队列与仲裁 | FacilityDefinition / FacilityState / ResourceLedger |
| frontend/no_fly_zone.py / NoFlyZoneSet | circle/polygon/bbox 几何，安全外扩、线段碰撞，模块级 _CACHE | RestrictionDefinition + 激活状态；几何由空间组件实现 |
| frontend/data_source.py / *Spec、DataSource | DroneSpec、NestSpec、TaskSpec；Random/CSV/GeoJSON 导入；部分缺失值默认回退 | ARCH-03 Provider/Manifest；转换/校验后生成世界定义 |
| console/sim_session.py / SimSession | 算法选择、循环、事件与趋势、checkpoint、reset/rebuild；单进程 RNG 快照 | ARCH-02 Harness / Run；不作为 World 的隐式单例 |
| frontend/route_planner.py / RoutePlanner | 从 Environment 抽离的寻路及障碍处理，通过回调使用碰撞缓存 | Spatial/Route capability；规划结果不直接写 WorldState |

明确已知耦合：Environment 使用模块级 CFG、FLEET_MIX、风系数和 NO_FLY_ZONES；NoFlyZoneSet 使用模块级缓存；Task 的仓库初始坐标来自共享配置；Drone 直接持有 known_stations 和能耗公式；SimSession 的默认地图路径为 part_of_yangpu.osm。文档只记录问题，不改变现状或假设它已被消除。

## 3. 核心对象关系

- **Project**：项目容器；索引 world revisions、scenario revisions、dataset/model manifests、组件锁定清单及 Run 记录；可以有多个世界，无运行时状态。
- **World**：特定 world_id + revision 的不可变定义：spatial_reference、entity_definitions、restriction_definitions、rule_bindings、resource_definitions、metadata。World 本身不含任务队列或当前风速。
- **EntityDefinition**：稳定 entity_id、kind、schema_version、静态 capability/spec、空间锚点和引用；定义与运行时状态解耦。实体种类是开放注册表，Drone/Task/Facility 是当前实例，不构成封闭枚举。
- **Scenario**：指定 world_id + revision 的可复现实例化方案，包括初始状态覆盖、事件时间表、事件源/数据源引用、种子及策略绑定；不改变 World 定义。
- **WorldState**：属于某一个 run_id，包含 sim_time_s、revision、实体状态、资源账本、动态场域、事件游标与引用索引。只允许经 Harness 协调的提交事务变更。
- **Run**（ARCH-02 拥有）：将 World 和 Scenario 与组件版本绑定；实例化 WorldState，驱动仿真，生成证据及快照；不是 World 的子类。

关系：Project 1—N World(revisions)、Project 1—N Scenario(revisions)、Run N—1 指向不可变的 World 与 Scenario，Run 1—1 当前 WorldState（另有历史快照）；EntityDefinition 由 World 拥有，EntityState 由某 Run 的 WorldState 按 entity_id 映射维护。

## 4. 最小建议接口（待 ARCH-02/03 同意后冻结）

~~~yaml
world:
  world_id: world:metro-A
  revision: 1
  schema_version: world.v1
  spatial_reference:
    crs: "EPSG:32651"     # 示例值，不代表已确认旧地图的 CRS
    axes: [east, north]
    horizontal_unit: m
    vertical_datum: null  # 二维场景不虚构高度
  entity_definitions: [ref-to-definition]
  restrictions: [ref-to-restriction]
  rule_bindings: [component-manifest-ref]
scenario:
  scenario_id: scenario:weekday
  revision: 1
  world_ref: {world_id: "world:metro-A", revision: 1}
  initial_state_ref: "sha256:..."
  event_stream_ref: "sha256:..."
  seed: 73
run:
  run_id: run:experiment-73
  world_ref: {world_id: "world:metro-A", revision: 1}
  scenario_ref: {scenario_id: "scenario:weekday", revision: 1}
  component_lock_ref: "sha256:..."
  state_revision: 0
~~~

这是语义契约，不是现在可直接运行的配置文件。真实文件格式、版本协商与实例化 API 归 ARCH-03 / ARCH-02 共同裁定。

## 5. 空间、单位与时间

- 每个 World 必须声明 CRS、轴顺序、几何维数、长度单位；不得仅以数值范围推断 CRS。旧地图当前实际 EPSG 需通过源文件和转换链另行验证，不将示例值冒充事实。
- 核心物理规范：距离 m、速度 m/s、时间 s、质量 kg、体积 m³、能量 Wh、功率 W、风速 m/s；转换要记录原单位、变换及精度。
- 局部直角坐标支持无地理位置的合成世界，如 LOCAL_CARTESIAN:cityB，必须给原点/轴/标尺；禁止将经纬度直接交给 EuclideanRouteCostProvider 当米算。
- 2D geometry 允许 z=null；若使用 3D 几何，则 vertical_datum、z_unit、障碍高度解释必须显式，不能默认建筑高度可直接比较。
- sim_time_s 是从 Run 的仿真起点计算的非负、单调秒数；日历时间采用 Scenario 显式映射（含时区）；无映射不能推导“真实 8:00”。旧系统 STEP_SECONDS 默认取配置中的 1.0，World 契约不固定 1 秒。
- 场景时变属性通过状态化场域/事件表示；不能直接覆写 World 中的静态道路、机型或坐标定义。空间数据版本变化应创建新 World revision，运行期临时限制更新其动态状态。

## 6. 边界约定（供跨组联合审查）

| 事项 | ARCH-01（本组） | ARCH-02 Harness | ARCH-03 Components |
| --- | --- | --- | --- |
| Entity/World/Scenario 语义 | 主责、提出 schema | 装配/实例化 | 提供数据与模型 manifest |
| 世界状态字段与不变量 | 主责 | 唯一提交者、事务、快照、重放 | 只读视图与变更建议 |
| 时间 | 定义单位与 sim_time 语义 | 唯一时钟、步长、同刻事件顺序 | 基于注入时钟计算 |
| 动态事件 | EventSpec 与事件结果语义 | 触发/去重/排序/回滚 | EventProvider 提供事件 |
| 空间坐标 | SpatialReference 契约 | 资源装配 | 坐标转换、地图加载、几何查询 |
| 物理模型 | 状态字段、能力和物理量 | 调度执行与状态提交 | DynamicsModel 计算提案 |

以上是待协同草案：ARCH-02/03 尚未提供最终 HEAD，任何未签字的接口均为 Proposed，不作为其团队已接受的事实。

## 7. 不包含的工作

不修改旧代码行为、算法、仪表盘、证据、配置格式与论文数据；不宣布新模型已通过实际集成。实施次序：冻结联合契约→实现适配器→对照重放/不变量验证→受控迁移，必须保留旧运行路径。

## 8. 待主控裁决

D1：世界的 CRS/垂直基准校验是否在世界装配时强制失败（本组建议：是）。
D2：航路规划结果、能耗规则属于何种组件能力（建议由 ARCH-03 定义，ARCH-01 不收编公式）。
D3：跨运行状态快照格式与兼容门归属（建议 ARCH-02 负责；ARCH-01 约束引用与单位）。
D4：同刻事件顺序以及手工注入事件何时生效（建议 ARCH-02 固定顺序，本组只提出约束）。
