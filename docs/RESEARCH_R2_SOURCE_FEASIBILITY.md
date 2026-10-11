# Research R2 — 第一轮真实数据来源与能耗标定可行性审计

2026-10-11。**仅作来源与准入审计，不宣称实机标定。** 依据已验收的 PR #36 `b23a8e4362260acb6a0df330fbd8665581d0e567` 建独立 Draft 分支，不修改 master、冻结 E0/E1、算法、生产默认、能耗公式或既有运行结果。R1 PR #37 的完整 CI 仍独立待验收，不将此 R2 文档称作已通过 R1 的后续物理验证。

## 来源分级与真实阻塞

登记见 `data/research_r2_sources.json`。CMU [KiltHub 12683453](https://kilthub.cmu.edu/articles/dataset/Data_Collected_with_Package_Delivery_Quadcopter_Drone/12683453) 和 [Scientific Data 原论文](https://doi.org/10.1038/s41597-021-00930-x) 记载 DJI Matrice 100 的 209 次飞行；官方页面描述可下载约 242.69 MB 的数据档案，许可 CC BY 4.0。本轮**尚未下载原始 ZIP / CSV、未得到原始 SHA-256、未核对采样和字段**。早期 `data/provenance/sources.csv` 记录的是旧 KiltHub 入口的历史 HTTP 403，保留该历史观察，不把新入口访问结果倒填到过去。

[PX4 官方公开日志文档](https://docs.px4.io/main/en/dev_log/flight_log_analysis_statistical) 描述了公共日志查询和批量下载（CC-BY PX4）；本轮没有取得经甄别的 .ulg。仓内 `data/raw/px4_logs/` 当前是 ASI 实验数据包的清单和许可证：CC BY-ND 4.0，不能混同 PX4 公共日志 CC-BY PX4，亦不能据此宣称实机配送能耗已测量。

[DJI FlyCart 30](https://www.dji.com/flycart-30/specs) 双电名义能量 3968.8 Wh、30kg/16km 官方规定条件的比值 `3968.8/16 = 248.05 Wh/km` 只属规格派生量级估算，绝非独立功率积分实测。当前模拟 `light_express=38.08`、`standard_cargo=79.80`、`heavy_cargo=248.50 Wh/km` 的内部量纲一致性不能推论为真实标定。跨机型从 M100 直接迁移绝对 Wh/km **禁止**。

## 真正开始标定的强制准入门

- **D0 来源**：记录确切 URL、DOI、许可、型号、下载时刻与可用条件。当前仅达到页面/官方文档级。
- **D1 文件**：下载至少一份原始完整飞行，记录字节数、SHA-256、文件级许可证、flight_id；当前 **BLOCKED**。
- **D2 字段**：确认时间列与单位、采样间隔、电压 V、电流 A 的符号及校准，GPS 轨迹 m、载重 kg、风 m/s、飞行阶段和缺失率；当前 **BLOCKED**。
- **D3 能耗时间积分**：按有效采样间隔 `P=V*I` W 与梯形积分 `E_Wh=sum(0.5*(P_i+P_next)*Δt_seconds/3600)`；处理负时间差、传感器离群、跳采样；起降、悬停、巡航分段，不用悬停段伪造 Wh/km；当前 **BLOCKED**。
- **D4 校准与留出**：**按整次飞行**而非按行随机拆分 train/validation/test，先比较常数 Wh/km 与载重/速度/风基线，在同型号独立留出集上报告 MAE、RMSE、bias、飞行级 bootstrap 置信区间、分工况样本数及失效条件；当前 **BLOCKED**。
- **D5 外推限制**：M100 结果仅验证 M100；FlyCart 30/ARK40 需同机型实测后才能声称外部有效性，未经验证禁止宣称真实配送时延、航程或算法收益；当前 **BLOCKED**。

不得改写冻结 E0/E1，不得删除 `[E0_MILEAGE_SCOPE_INCOMPARABLE]` 的适用警告。**这份来源审计的测试只确认机器可读状态正确，不替代实飞标定。**
