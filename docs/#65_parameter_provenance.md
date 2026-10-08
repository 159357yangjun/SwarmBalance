# #65 参数溯源账本（ChatGPT 五档投影）

基线 HEAD `bd43eaa`。**本轮只建账本、不改代码**；账本是对既有真源 `data/provenance/parameters.csv` + `sources.csv` + `osm_census.csv` 的**五档重投影**，不是第二份数据（冲突以 CSV 为准）。所有读数标"本轮现测"或"引自 parameters.csv"。

## 0. 五档定义与判据

| 档 | 含义 | 进入条件 |
|---|---|---|
| **Measured** | 我方/第三方对真实系统的直接测量 | 有原始记录+复算路径 |
| **Manufacturer** | 厂商公开规格页直接发布值 | 有 URL+获取日期+原文命中 |
| **Literature** | 同行评议论文/数据集结论 | 有 DOI+许可+可取证正文 |
| **Derived** | 由 Manufacturer/Measured 经明确公式派生 | 写出派生式+隐含假设 |
| **Scenario** | 情景设定值，无外部凭据 | 明写"假设"，禁挂"真实/厂商"名义 |

## 1. OSM 几何 —— Measured / Manufacturer(OSM contributors)

- 文件 `frontend/data/map/part_of_yangpu.osm`，sha256 `72c3ef9c…a65b`，11,098,582 B，elements 46,917（node 40,128 / way 6,201 / relation 588，恒等式成立）。来源 `src_osm_extract`（ODbL），下载事件时间**未取得**。
- 本轮现测：building-tagged ways = 2,876（引 osm_census.csv）；env.all_buildings = 2,889。
- **边界**：几何是真实 OSM ⇒ 支撑"空间环境真实性"；但**下载事件溯源未证**（本机 www.openstreetmap.org:443 连接失败、Overpass 406、kumi.systems 超时），故 traceability 维持 E。**不得称"实时/最新地图"**。

## 2. 建筑高度缺失声明 —— Scenario（覆盖率实测）

本轮现测（pandas tags 列逐行判定，纠正了"height 字段人人有"的假信号——那是计算字段非 OSM 标签）：

| 类别 | 栋数 | 占比 |
|---|---|---|
| 显式 `height` 标签 | 25 | 0.9% |
| 仅 `building:levels` | 374 | 12.9% |
| **两者皆无 → 套 fallback 层高** | **2,490** | **86.2%** |
| 合计 all_buildings | 2,889 | — |

- **真实高度/层数覆盖 = 399/2,889 = 13.8%**；其余 86.2% 的高度是 fallback 常数（`building_default_floors=3.0` 层，且另有 12 m 固定值并存未统一，见 param_height_fallback_floor，D+E 档）。
- 进避障碰撞集（≥HIGH_BUILDING_MIN_HEIGHT_M）仅 **18 栋**。
- **边界**：绕障行为建立在 18 栋真高楼上是有依据的；但"整座城市楼高"不能称真实——86% 是设的。不同渲染器 fallback 补法不同 ⇒ "同城两视图楼高不一致"风险在册。

## 3. ARK40（丰翼·方舟40，standard_cargo）厂家参数 —— Manufacturer

来源 `src_sf_ark40` https://piw-mr-web.inn.sf-express.com/uav/ark-40/ ，retrieval_date **2026-10-03**，HTTP 200，124,983 B，sha256 前缀 `192489504d1d934e`，顺丰自有域非转载。逐条（引 parameters.csv）：

| 参数 | 值 | 单位 | 档 | 备注 |
|---|---|---|---|---|
| carrying_capacity | 10 | kg | Manufacturer(A) | 官方页未附条件 |
| full_load_range_km | 20 | km | Manufacturer(A) | 同上 |
| speed | 14 | m/s | Manufacturer(A) | 巡航速度 |
| MTOW | 46 | kg | Manufacturer(A) | 未建模 |
| **battery_capacity** | 1600 | Wh | **Scenario(D)** | **官方页 mAh/Wh/电池容量关键词命中数=0 ⇒ 假设值，对外禁用"对标 ARK40 官方电池"** |
| **consumption_base** | 0.06 | Wh/m | **Scenario(D)** | 无电池容量即无法派生 ⇒ 假设 |

## 4. 电池额定能量 —— 分机型（有官方值才填 Manufacturer）

| 机型 | 额定能量 | 档 | 出处 |
|---|---|---|---|
| FlyCart 30 (heavy) | 单块 TB60 **1984.4 Wh**（官方直发）；双块 3968.8 Wh = 1984.4×2 | Manufacturer(单块) / **Derived(双块)** | src_flycart30, 2026-10-03, 200, 135,096 B；口径"零海拔无风" |
| ARK40 (standard) | 1600 Wh | **Scenario** | 官方无电池条目（§3） |
| 轻载 (light_express) | 380 Wh | **Scenario** | 美团从未公布电池 |

**边界**：只有 FlyCart 单块 1984.4 Wh 是厂商直接值；双块总能量是我方派生，不得称"官方发布的双块值"。ARK40/轻载电池全是设的。

## 5. 能耗函数形状 —— 可检验项（结构 vs 绝对值分离）

FlyCart 空载锚定链（引 parameters.csv，均 Derived/C，测试条件"零海拔无风、15 m/s 匀速"）：
- consumption_base 0.142 Wh/m ← 3968.8 Wh ÷ 28 km = 141.743 Wh/km ≈ 0.142（空载口径）。
- load_penalty_factor 0.75 ← 空载 28 km ÷ 满载 16 km = 1.75 = 1+0.75（航程比反推能耗比）。
- **隐含假设（未经实飞检验）**：同电池包、同无风巡航下"单位距离能耗 ∝ 1/航程"。若满载改了飞行模式/悬停占比，比值≠能耗倍率，需重推。
- 两条派生**共用同一对官方数据（28/16）**，不是两条独立证据。
- **可外部检验的是"形状"**（如 E 随载重单调升、逆风耗能不降），**绝对 Wh/km 不可**跨机型套用。CMU 机型是 Matrice 100（§7），套用绝对能耗＝冒充。

## 6. 全部 Scenario 档参数清单（对外禁挂"真实/厂商"）

引 parameters.csv evidence_grade=D 者：ARK40 battery/consumption、light battery/consumption/payload(E)、**swap_time_seconds=180**（无任何官方换电动作时长；BS60 的 60 min 是充满两块的时间非换电耗时）、**battery_low_threshold=0.2**、**sla_base_seconds=420**（直接决定超时率）、**sla_per_kg_seconds=24**、building_default_floors=3.0、以及 simulation.json 里的调度权重/reward/惩罚/task_generation 分布（greedy.match_weight 0.6、distance_weight 0.4、reward_priority_* 、hotspot.probability 0.6/radius 80 等）——均为情景设定，无外部凭据。

## 7. CMU 209 架次数据集 —— 可行性评估（本轮不拟合）

来源 `src_cmu_data_descriptor` Nature Sci Data (CC-BY 4.0) https://www.nature.com/articles/s41597-021-00930-x ，2026-10-03, 200, 319,236 B。
- **能不能拿到手**：论文正文可取（已 WebFetch 逐字摘录）；**数据本体未取得**——KiltHub 入口 `src_cmu_kiltub` https://kilthub.cmu.edu/…/14909664 两次（文章页+ndownloader 直链）均 **HTTP 403**。
- **许可**：descriptor 论文 CC-BY 4.0；数据本体许可**未取得**（拿不到文件也就没读到其 license 条款），须以 KiltHub 记录页为准，待能访问时确认。
- **格式**：论文题录为"In-flight positional and energy use data set for a delivery drone"，含位置+能耗时序；具体文件格式（CSV/列名/采样率）**未取证**。
- **适用性红线**：机型 = **DJI Matrice 100**，与本项目三机型均不同 ⇒ 只能用于**验证能耗函数的结构关系**（载重/风→能耗的方向性），**不可**拟合或背书任何机型的绝对 Wh/km。论文本身不含 Wh/km 结论或拟合系数。
- **结论**：作为"外部行为检验"的候选料，**当前通道不通（403）**；要推进需先解决取数（换网络/联系作者/镜像），且取得后仍只做形状检验不做绝对标定。

## 8. 论文措辞锚点段（供引用，②交付）

> **EN**: Platform capability envelopes are taken from manufacturer-published specifications; the spatial environment is derived from real OpenStreetMap geometry; the *functional form* of the energy model is subjected to an external behavioral check against public flight data; while the target fleet's absolute energy consumption and battery-swap parameters remain scenario settings without vendor or measurement backing.
>
> **中文**：平台能力边界来自厂家公开规格，空间环境来自真实 OSM 几何，能耗函数形式接受公开飞行数据的外部行为检验，而目标机型的绝对能耗与换电参数仍为情景设定值。

## 9. 诚实缺口（本轮未闭合，报出不开工）

- OSM 下载事件溯源未证（网络不可达）。
- CMU 数据本体 403 未取得 ⇒ §5/§7 的"外部行为检验"目前**只有设计、没有执行**。
- ARK40/轻载电池、换电 180s、SLA 420/24 全 Scenario，直接决定完成率/超时率/换电次数⇒四算法排序对这些参数敏感（下一轮敏感性扫描要量这个）。
