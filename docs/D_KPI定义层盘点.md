# #69-D：KPI 定义层盘点与自洽审计

基线 22ab9b1。**本轮零生产改动**（见 §4）。一手证据来自提交态 `docs/取证输出/c1_face_live_fixed.json`
（seed 40907 / greedy / 1200）+ 逐行读码。硬边界 route_planner.py/drone.py/cleanup accounting/TaskState/scheduler
全程零修改，已核。

## 1. KPI 定义清单（定义位置 · 吃哪些字段 · C1 后是否自洽）
真源链：`_record_task_completion`(environment.py:422-490) 累加计数器 → `get_statistics`(:903-1007) 派生比率
→ step info(:1255-1287) 导出英文键 → `metrics_schema._STAT_KEY_MAP`(frontend/metrics_schema.py:104-129) 映射中文列
→ `experiments/reporting.py` 方向标注(HIGHER/LOWER/DIRECTION_AMBIGUOUS)。

| KPI | 定义行 | 分子 / 分母 | 吃的字段 | C1 后自洽？ |
|---|---|---|---|---|
| completed (total_completed) | env:446 +=1；聚合 :983 | — | 每次 `_record_task_completion` 调用 | ✅ 单一真源 |
| completion_rate | :907 | total_completed / **total_generated** | 两计数器 | ✅ 分母是生成数，非完成数 |
| on_time_rate | :985 | total_on_time_tasks / total_completed | :463/:446 | ✅ 分母=legal completions(现全 legal) |
| timeout_rate | :986 | 1 − on_time_rate | 同上 | ⚠ 由 on_time 反推，非直接计数（见 §3） |
| avg_delay (mean_delay) | :987 | total_delay / total_completed | :447/:446 | ✅ delay=max(0,completion−deadline)(:441) |
| unfinished | 未作独立列导出 | total_generated − total_completed | :907 同源 | ✅（replay 里我按此式算得 6） |
| energy (total_energy_consumed) | :1160 +=battery_change | 每步飞行耗电累加 | consume_battery | ✅ 与完成数无关 |
| swap (total_swap_sessions) | :865 +=1 | 换电会话计数 | 泊位仲裁 | ✅ 与完成数无关 |
| action-distance (total_flight_distance) | :1167 +=moved | 每步位移累加 | drone.move | ✅ 与完成数无关 |
| DESTINATION_REACHED / TASK_COMPLETION_RECORDED | 观察层 consistency_observer.py | 送达证人 / 完成事实 | origin==destination_branch | ✅ 见 §2(b) 对齐 |

派生但**未进 METRIC_COLUMNS**（只 print_statistics 用）：avg_energy_per_task(:966=energy/total_completed)、
avg_load_to_delivery_time、max_* 等——不进对外 CSV，故不参与算法判优。

## 2. 两条指定疑点

**(a) timeout/delay 是否只由 legal delivery completion 产生？** —— 现在成立（修复前不成立）。
C0 报的"timeout 2 例中 1 例来自非法 completion"是修复前读数；#69-C1 后所有 38 条 completion 均 origin==destination_branch。实测：

```
[A] completions with d_ontime==0 = 2; with d_delay>0 = 2
[A] timeout/delay contributed by NON-legal (no DR) completions = 0 []
[A] total_completed(d_completed sum) = 38 == len(comp) 38
```

⇒ 该断言应门化（见 §5）。

**(b) DESTINATION_REACHED ↔ TASK_COMPLETION_RECORDED 是否有第二个未对齐定义（§6-L 族）？** —— 无缺口。

```
[B] completions_without_DESTINATION_REACHED = 0
[B] DESTINATION_REACHED_without_completion (orphan) = 0
```

两集合在 seed 40907 上双向相等（各 38）。C1 已把二者统一到同一谓词 origin==destination_branch。

## 3. 发现的不自洽（具名，交回裁定，未自行改）

**不自洽 D-1｜on_time/timeout 的语义是"相对 deadline 迟到"，不是"经 dest service leg 送达"。**
定义 environment.py:441 `delay=max(0, completion_time−deadline)`、:445 `is_on_time=delay<=0`。
它把"准时"绑定到**时间窗达标**，而 C1 把"送达"绑定到**服务航点消费**。当前 seed 下二者恰好覆盖同一批 38 条（因全部 legal），所以数值一致；但这是**两个正交维度**：一条按时抵达的任务与一条经合法投递腿完成的任务不是同一件事。超时率作为 SLA 指标本身没错，但若文档/论文把它叙述成"合法送达中的超时占比"就跨了定义。**建议**：措辞钉死为"完成相对 deadline 的迟到率"，不与 delivery-leg 混述。属口径澄清，非改码。

**不自洽 D-2｜avg_energy_per_task 与 rate 指标共享被污染的旧分母，但未登记方向、也未导出。**
:966 `avg_energy_per_task = total_energy_consumed / total_completed_tasks`——与 on_time_rate/avg_delay 同分母。
C1 前该分母含 12 条非法 completion ⇒ 每任务能耗被虚低；C1 后分母干净。它不在 METRIC_COLUMNS、不在 HIGHER/LOWER_IS_BETTER ⇒ 目前无害，但若将来导出必须补方向。属前瞻登记。

**非缺陷（已排除）**：unfinished 未作为独立导出列存在（我 replay 里的 unfinished 是按 generated−completed 现算，与任何既有列不冲突）；timeout_rate=1−on_time_rate 只是冗余表达，值正确。

## 4. 自查结论：**D 轮零生产改动**

两条指定疑点均自洽；发现的两项是不自洽**表述/前瞻**（D-1 措辞、D-2 未导出量），都不是"改一个 KPI 公式能让门变绿"的生产缺陷。按指令②"若盘点结果=全部自洽、无需改码，那本身就是有效交付"——本轮**不改任何 KPI 语义**，停在待裁。

## 5. 建议的门化（待你放行才写夹具，本轮不动）

- **G-D-a**：断言"任一 d_delay>0 或 d_ontime==0 的 completion 必有 DESTINATION_REACHED 证人"，两面夹具=clean(fixed)绿 + 摘掉某 legal 完成的 DR 证人红。落点：扩展 test_c1_lifecycle_gate 或新 KPI 门。
- **G-D-b**：断言 |{DR}| == |{completion}| == counter（三集合互等），把 §2(b) 变成常驻检查而非一次性对账。

两条都是审计层，不碰生产码。等你裁定是否建门、以及 D-1 措辞要不要写进 metrics 口径文档。

> **#69-E 落地状态**：G-D-a / G-D-b 已实现为 `test_5_GD_a_timeout_only_from_legal_delivery` /
> `test_6_GD_b_dr_completion_bidirectional_align`（console/test_c1_lifecycle_gate.py）。判据用结构谓词
> （origin==destination_branch 作证；GD_b 作用在自然轨迹 c1_face_live_fixed.json，非注入后 trace），
> 期望值不写常量 2。各带合成证牙探针（注入非法 delay / 删一条 DR ⇒ 必红）。四面 fixed/mutate/forced_cleanup 绿、old 仍 [C1_NO_TEETH] 红。
>
> **D-2 互检（③，按"结论是啥写啥、不建重门"）**：`avg_energy_per_task`(environment.py:966) 分母 = total_completed_tasks，
> 与 on_time_rate/avg_delay 同分母——已核它**不在 METRIC_COLUMNS、不在 HIGHER/LOWER_IS_BETTER/DIRECTION_AMBIGUOUS**
> （grep frontend/metrics_schema.py + experiments/reporting.py 均 0 命中）⇒ 未导出、无方向 ⇒ 当前无害，符合 D 文档原结论。
> 一行互检：若将来把它导出，必须同时在 reporting 登记方向，否则会被算法对比静默当作中性列。不为此单独建门。

相关：docs/当前状态真源图.md §6-L、CHANGELOG 2026-10-07 第十五笔。

## 附（2026-10-08，#69-H3 D-iv）：取货/送达时间的权威口径句 —— 论文引用以此为准

主控裁定上位原则冻结后，`avg_delay / completion_time / on_time` 的"完成时刻"语义正式定名如下，
论文与对外口径**必须逐字采用**，不得再用"几何到达"表述：

> **取货/送达时间定义为执行层消费服务航点的离散 sim_time；`<1m` 是 planner endpoint 选择规则，不构成服务完成事件。**

对应到本表：`_record_task_completion` 的 `completion_time = self.current_time`（:467）之所以可信，
是因为它现在只在 `Drone.update()` 真正 `scheduled_position.pop(0)`（drone.py:328）并经
`consumed_waypoints_this_step` 事件缓冲被 Environment 消费时才触发——证人从"curr 形状/长度差/线段途经"
的反推，换成了执行器离散事件本身。route_planner.py:160 的 `euclidean(current,goal)<1` 仍只决定
"航点能否被执行器接受为终点"，不再兼任"服务已完成"的定义。这消除了 #69-B/C1/H 反复出现的
跨层"两套到达定义"残余（H-R1 那 9 例 re-route 假阳性即由无-pop 机制根除，见 G-H3-D）。
