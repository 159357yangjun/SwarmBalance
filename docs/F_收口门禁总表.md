# #69-F：收口确认轮（全量门禁一次性总表）

HEAD = 7d36b99，工作树净。本轮所有读数**均为 F 轮现测**（跑于 20:xx），除明确标注"未重跑"外不引上一轮存档数字充数。

## ① 全量门禁总表（F 轮实测）

| 门禁 | 判据 | F 轮读数 | 状态 | 是否本轮重跑 |
|---|---|---|---|---|
| C1 fixed | R1/R2/R3/R4=0, cleanup门=0, GD_a=0, GD_b对齐 | Ran 8 OK (skip=1 test_4) | ✅ | 是 |
| C1 mutate | R3=1（注入重复被抓）+ GD 绿 | Ran 8 OK | ✅RED(预期) | 是 |
| C1 forced_cleanup | cleanup门=1, R1=1, R4=1 + GD 绿 | Ran 8 OK (skip=1) | ✅RED(预期) | 是 |
| C1 old(live) | [C1_NO_TEETH]（当前代码不再自带违规） | Ran 8 FAILED(failures=1) | ⚠ 刻意红·待裁项① | 是 |
| Gate A 路由等价 | 35 例逐点 direct/astar/fallback/detour | Ran 5 OK | ✅ | 是 |
| source A/B/C/D | dest 契约前 source-leg 语义 | Ran 4 OK | ✅ | 是 |
| destination A/B/C/D | dest-leg direct/detour/fallback/mutation | Ran 4 OK | ✅ | 是 |
| Observer 零漂移 | a–h 主判据零漂移 | Ran 8 OK (skip=1 test_h 基线门控) | ✅ | 是 |
| compare_gate | 混口径拒绝 | Ran 27 OK | ✅ | 是 |
| height_binary_gate | 高度二值化 | Ran 4 OK | ✅ | 是 |
| loader_baseline_gate | OSM 加载基线 | Ran 9 OK | ✅ | 是 |
| README counts | console=39文件/314用例 | Ran 5 OK | ✅ | 是 |
| 聚合 suite batch A | 12 个快门文件 | Ran 90 OK | ✅ | 是 |
| 聚合 suite batch B | lifecycle/fixtures/env | Ran 38 OK (skip=1) | ✅ | 是 |
| 聚合 suite batch C | 12 个 env-heavy 文件 | Ran 117 OK | ✅ | 是 |
| 聚合 suite batch D | phase1b1+phase1b2 | Ran 25 OK (skip=1) | ✅ | 是 |
| **聚合合计** | A+B+C+D | **270 tests, 0 failures** | ✅ | 是 |

注：聚合 270 不含 `test_c1_lifecycle_gate`（默认 face=old→[C1_NO_TEETH] 会红，故单独按四面计；见待裁项①）。

## ② paired replay f654587→HEAD 终态比对

与 C1 提交产物 `c1_paired_replay_f654587_fixed.json` 逐字段对账，AFTER 侧从本轮重生成的
`c1_face_live_fixed.json`（mtime 20:25，本轮现测）现算：

| 字段 | committed(C1) | F 轮现算 | 一致 |
|---|---|---|---|
| completed | 38 | 38 | ✅ |
| DESTINATION_REACHED | 38 | 38 | ✅ |
| cleanup_completion | 0 | 0 | ✅ |

first_divergence：committed index=852 / seq=853 / task_11 / after-kind=DESTINATION_REACHED ——
该事件在本轮事件流中仍存在且同 seq/kind/task ⇒ **E 后读数逐字不变**（纯审计层，无行为外溢）。

## ③ #69 剩余开项清单（只列不修）

- **[待裁①] teeth 极性 / old 面红**：default/old 面在干净代码上 `[C1_NO_TEETH]` 红（真牙只在注入面）。
  这是当前唯一让"跑默认 face 的聚合 runner"不绿的来源。选项 (a) teeth 只对 mutate/forced_cleanup 要求红、old 并入 fixed（执行会话倾向）/(b) 保持现状当代价。**须主控定，否则 #69 不能对外称"suite 全绿"。**
- **[待裁②] drone.py:336 处置**：C2b 结论"语义重叠/冗余双写（非幽灵清零）"已给证据，但**保留+双向注释锚 vs 合并单点真源**未落码——属"结论已定、动作待批"，不算关闭。
- **[待裁③] D-1 措辞**：on_time/timeout="相对 deadline 迟到"≠"经 dest service leg 送达"，是否写进 metrics 口径文档未定。
- **[预存干扰条数]**：本轮聚合 A/B/C/D=270 全绿、0 failures ⇒ **当前无预存顺序干扰复现**（历史登记的 `test_g2_all_four_algorithms_get_real_fleet_speed` 聚合红，本轮 batch D 单独跑 25 OK 未触发）。诚实标注：这是"本轮批次切法下未见"，不等于"聚合并发时序下永不再现"；若日后改回单次 discover 需重验。
- **#69 结项判断**：三个待裁项都是**判据极性/措辞/前瞻动作**，不是未闭合的缺陷。生命周期一致性主线（C1 契约修复 + C2a/C2b/D/E 审计与门化）技术面已闭合。**建议：三项裁定落定即可结 #69，无需 F 之后另开 G**；其中只有待裁①会影响"suite 全绿"这一对外表述，优先级最高。

相关：docs/D_KPI定义层盘点.md、docs/C2b_drone载重归零审计.md、CHANGELOG 2026-10-07 第十六笔。
