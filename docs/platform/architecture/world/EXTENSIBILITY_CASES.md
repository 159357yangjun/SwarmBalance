# ARCH-01 — 世界扩展能力走查与验收案例

状态：Design Draft v0.1。所有案例为契约层设计推演，不是仓库已经运行成功的集成测试。

## 1. 验收规则

同一份 World/Entity/Scenario/WorldState **核心 schema_version=*.v1** 在不同空间数据、机队配置和事件组合下仍成立。允许更换 World 实例/Revision、实体 spec、SpatialProvider、DynamicsModel、EventProvider 和 Schema 注册项；不能因此修改 World 基类字段、偷改默认地图、增加机型专属 if 分支。重放证据需固定数据与模型 manifest/hash，不能只锁“算法名称”。

| Case | 空间 | 机队 | 动态事件 | 核心契约需变更？ |
| --- | --- | --- | --- | --- |
| A：真实城市 | 显式米制投影，OSM 导入城市甲道路/建筑 | 5 轻载 + 3 标准 + 2 重载（示例，可替换 specs） | 时刻 300 s 注入 6 m/s 水平风 | 不需要 |
| B：合成工业园 | LOCAL_CARTESIAN:plant-1，程序化栅格/多边形障碍 | 6 同质巡检机、1 个补能站 | 时刻 450 s 站点软关闭 | 不需要 |
| C：第二城市 | GeoJSON/CAD/其他 provider 导入城市乙，声明各自 CRS 并转换至世界坐标 | 4 家族 X + 4 家族 Y，各自独立模型参数 | 任务需求突增 + 时变禁飞区 | 不需要 |

案例中的数量/风速为输入示例，不代表任何设备测试事实。

## 2. Case A：城市切换而非“换 OSM 路径”

初始：World A 的 spatial_reference 含经验证 CRS；SpatialProvider A 读取道路/建筑（OSM 是来源之一）；引用地图 fingerprint；任务与站点采用 World 坐标。

替换：创建 World B，改为另一城市的 GeoJSON/CAD provider。Provider 必须输出相同语义的空间查询能力并声明源 CRS、目的 CRS、几何版本及缺失高度策略；定义的 Task/Drone/Station 引用对新世界重新校验；世界核心 schema 不增加 osm_file_path。

失败注入：输入文件仅提供经纬度却自称米制投影。预期在装配前报 SPATIAL_REFERENCE_MISMATCH；不允许在路径规划里用度当米，避免悄悄改变距离、能耗与时效。

验收证据：两个 World 有独立 fingerprints；相同 Query API 的成功/拒绝结果；World 不依赖 OSM 类型；禁飞冲突可检测。没有输入的城市地图内容不得伪造。

## 3. Case B：更换机队与能耗模型

World B 中采用 model:inspection-basic 的轻型无人机与定点服务实体；另一个 World 中加载 cargo 模型混编机队。EntityDefinition 只写 spec_ref、payload capacity、battery capacity、capabilities，速度或能耗计算由 DynamicsModel 提供。

将模型 M1：distance × base_Wh_per_m × load_factor 换成 M2：速度/海拔/时变风数据驱动的表或函数。保留位置 m、飞行时间 s、能量 Wh、加载质量 kg、模型引用的公共语义；用 ARCH-03 manifest 声明所需输入、支持 2D/3D、缺字段策略。模型缺海拔时必须拒绝、显式 default 或声明可降级，不能用旧机型常数偷偷兜底。

失败注入：M2 要求真实 onboard_mass_kg 而只有 assigned_mass_kg。预期 CAPABILITY_INPUT_MISSING；不能把“已派单”自动当“已装货”。新模型不得被挂在 Drone.update 内造成状态副作用。

验收证据：同一实体定义/状态切片可被不同 DynamicsModel 读取；模型产生可对账 energy_delta_Wh；模型换装只更新 model manifest 与 Run 锁，不修改 World 核心字段。

## 4. Case C：复杂时变事件组合

给合成园区/城市乙的 Scenario 安排：t=300 s 风场切换；t=450 s 机巢失效；t=600 s 突发任务；t=650 s 临时空域关闭；t=900 s 设施恢复。EventProvider 提交规范 EventSpec，Harness 按确定顺序对 WorldState 提交。

设计走查：
1. t=300：dynamic_fields.wind_field_revision 变化；未来 motion/energy 提案观察到新字段，之前已提交事实不改。
2. t=450：facility.state.available=false；新 lease 被阻止，已有 active lease 依软关闭策略完成；无替代机巢时产生明确失败状态而非死锁。
3. t=600：需求任务获唯一 ID，入 pending 队列；调度器对所有 capability、时间与载重约束重新评估。
4. t=650：restriction 在有效时窗内被激活；已有航线在继续执行前重验；若重规划失败，保留事实并暴露不可行原因。
5. t=900：状态恢复，排队资源重新仲裁；不恢复先前已取消的任务，不复制任务 ID。

验收证据：重复同一事件流无重复任务/额外泊位/额外货权；两个固定 seed 的重放 hash 可核对；跨场景 change 只落在 scenario、model、provider 和 World revision，非核心结构代码。

## 5. 缺失字段与极端输入

| 输入 | 必须表现 | 禁止 |
| --- | --- | --- |
| CSV 缺 task_id | 按 manifest 生成可追溯 deterministic ID，或拒绝 | 随机未登记 ID |
| 缺 source/destination 坐标 | INVALID_REQUIRED_COORDINATE 且指出文件/行 | 借默认上海仓库坐标 |
| GeoJSON 缺 CRS | 拒绝或明确声明约定并留审计记录（策略须预冻结） | 自动把坐标数当米 |
| 建筑缺 height | 按显式未知高度策略处理 | 未声明地假设为 0m |
| 能耗模型缺 wind/altitude | 按 manifest 兼容门拒绝或显式降级 | 默认采用另一模型数据 |
| 重复 station/task ID | 在装配或事件接纳时失败 | 覆盖既有实体 |
| 同时关闭全部服务站 | 按 Scenario policy 决定 reject/fail state | 世界硬编码必须至少开放一站 |

## 6. G0 设计验收清单

- [x] 静态 World、Scenario、单 Run WorldState 和 Harness 所有权有清晰语义划分（文档级）。
- [x] 同一核心契约可表达真实城市/非 OSM 合成空间（设计走查）。
- [x] 可表达异构/同质机队与独立能源模型（设计走查）。
- [x] 风、设备故障、订单激增、临时空域限制与恢复（设计走查）。
- [x] 稳定 ID、引用、资源/货权不变量和错误语义已提出（文档级）。
- [ ] ARCH-02 确认统一时钟、事件相位、提交/回滚与快照语义。
- [ ] ARCH-03 确认 Spatial/Dynamics/Event capability 与 manifest/schema 字段。
- [ ] 将上述走查转为机器可执行的 contract fixtures + 历史回归对照（不属于当前 docs-only 范围）。
- [ ] 对 legacy 地图 CRS、风/能耗口径和缺字段来源建立外部可复核的验证证据。

裁决建议：文档 G0 可进入联合设计审查，但**不得**据此宣称运行态扩展或旧仿真等价已验证。

## 7. 待主控裁决汇总

C1（高）世界空间参考校验强度及未知高度/CRS 规则；建议 fail-closed。
C2（高）ARCH-02 的 step 相位、状态提交事务以及跨组件快照复现协议；与旧链路必须显式分离。
C3（高）货权/已派单质量的能耗归属与任务转移，不以旧 current_load 代替 onboard_mass_kg。
C4（中）低电后无可用机巢、全站关闭的策略是场景规则还是全局约束；建议场景化。
C5（中）运行期改变实体静态规格是否创建新 World revision；建议不允许直接原地修改。
C6（中）地图/能源模型/事件 provider 的协商字段与兼容错误码由 ARCH-03 最终冻结。

不能在 ARCH-02/03 未提交审查结果之前，将这里的 Proposed 字段冒称三组已统一批准。
