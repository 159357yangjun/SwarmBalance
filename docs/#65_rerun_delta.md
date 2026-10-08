# #65 四算法重跑轮 —— delta 表 + 旧数字作废清单

HEAD `f2bcdf5`（代码零 diff 于冻结点 bd43eaa，已 git 核）。锁 scenario/seeds/fleet/episode：seeds 101–105、algorithms [greedy,ga,pso,ortools]、fleet light5/std3/heavy2、episode 3600、config=config/simulation.json。生产入口 `experiments.worker.run_one`（非自写驱动），额外挂 opt-in observer 产 lifecycle 两读数（默认关，metrics 逐字节不变，smoke 已证）。原始 20 格：docs/取证输出/rerun65_cells.json。

## 1. NEW 均值（本轮现测）

| alg | completion | on_time | timeout | avg_delay | energy_Wh | swap | r5_nonexact | cleanup_no_svc |
|---|---|---|---|---|---|---|---|---|
| greedy | 1.000 | 0.9467 | 0.0533 | 4.302 | 13364.6 | 9.0 | 20.2 | **0.2** |
| ga | 1.000 | 0.9333 | 0.0667 | 5.437 | 13524.5 | 8.4 | 18.4 | **0.2** |
| pso | 1.000 | 0.9300 | 0.0700 | 5.697 | 13562.2 | 8.6 | 18.2 | **0.2** |
| ortools | 1.000 | 0.9333 | 0.0667 | 5.533 | 13558.4 | 8.4 | 18.4 | **0.2** |

on_time = 1 − timeout（无独立"准时率"列）。r5/cleanup 为每格 observer 计数取均值。

## 2. DELTA 表（old→new × 指标；old = results/compare/one_click_latest.csv）

| alg | completion | on_time | timeout | avg_delay | energy_Wh | swap | r5 incidence |
|---|---|---|---|---|---|---|---|
| greedy | 0.000 | 0.000 | **+0.000** | +0.085 | −620.3 | −0.6 | 新读数列 |
| ga | 0.000 | +0.010 | −0.010 | −0.795 | −275.4 | −0.2 | 新读数列 |
| pso | 0.000 | +0.000 | −0.010 | −0.622 | −177.9 | −0.2 | 新读数列 |
| ortools | 0.000 | +0.013 | −0.013 | −0.890 | −173.9 | −0.2 | 新读数列 |

（r5_nonexact / cleanup_no_service 是本轮新增列，latest 无对应旧值 ⇒ 不列 delta。）

## 3. delta 来源归因（先验确定性再谈因果）

per-seed 对账 new(f2bcdf5) vs old-raw(conclusion_20261001)：**greedy 五 seed 全部逐位相同**（s101 delay 2.583=2.583 …）⇒ 同码同 seed 确定复现，delta 不是噪声。差异只出现在 ga/pso/ortools 的 s101/s102/s104——正是批量优化器真正介入的格（其余 seed 三算法与 greedy 等价）。

- **greedy timeout Δ=0**：C1 未动贪心调度路径（符合预期，dest 契约修复对贪心的这批任务时序无影响）。
- **greedy avg_delay Δ=+0.085**：来自 latest(4.2167) 与其 raw(4.3017) 本就存在的口径差（见 §5 撤回条），非本轮引入。
- **ga/pso/ortools timeout 降 0.010–0.013**：C1 使这些格的 dest service 识别改变 → 个别任务完成时刻前移出 deadline。方向为正但幅度 ~1 task/seed，n=5 下不可称显著。

## 4. 排名变没变（一句结论）

**变了**：按超时率/平均时延，第 3–4 名从「pso < ortools」翻转为「ortools < pso」（greedy 最优、ga 次之不变）。原因是 ortools 超时降幅更大（−0.013 vs −0.010）。翻转发生在两算法本就接近、且 n=5 符号检验不可判的区间内 ⇒ 论文不得据此断言"ortools 优于 pso"，只能说"C1 后二者排序在此 seed 集上互换、差异在噪声量级"。

## 5. 旧数字作废清单（ChatGPT 三分类，逐指标登记）

**A. 直接作废（引用即错）**
- 无任何指标落入此类——completion/on_time/timeout/delay/energy/swap 新旧都指向同一实验设计，只是证据批次更新。（诚实说明：没有"算错了要删"的数，只有"证据过期要重跑"。）

**B. 旧版证据失效待重跑（本轮已重跑，须以 rerun65_cells.json 为准）**
- one_click_latest.csv 全部 4×{完成率/超时率/平均时延/总能量消耗/换电总次数}：生成于 f654587 之前的 dest 双判据代码，**不含 C1 修复** ⇒ 论文若引用须替换为本轮 new。
- 尤其 **ga/pso/ortools 的超时率/平均时延**：本轮证明它们随 C1 变化（s101/102/104），旧值不能再代表当前代码。
- 附一条我自己的更正：先前我一度写"旧 latest 不可复算"——**撤回**。实测 greedy 超时率 latest 0.053333 == 其 raw 均值 0.05333，可复算；仅 avg_delay 有 4.2167 vs 4.3017 的口径差（属 B 类"证据批次不同"，非"手抄错"）。

**C. 理论上不受影响但统一刷新**
- 完成率（四算法恒 1.0）、总飞行距离/空载率等纯里程量：本轮与旧一致或近一致，仍建议随批次一并刷新以保持同源。
- figures/*（algorithm_comparison 相关图）：数据源换成 new 后需重绘。

**跨类红线**：cleanup_no_service 本轮揭示（见 §6）说明"completion 是否合法送达"这一维度旧 latest 从未披露 ⇒ 任何引用旧 completion_rate=1.0 作"全部按时妥投"的地方，措辞须降级。

## 6. 本轮意外发现（具名，交回裁定，未修）

**latent defect 在生产 seed 上可达，非仅注入面**：cleanup_completion_without_service 在 greedy-s102、ga/pso/ortools-s101 各 =1（均值 0.2）。一手复现（seed 102）：task_44 t=1415 装载、t=1666 经 `is_free_cleanup_branch` 计成完成、has_destination_evidence=False、全程无 DESTINATION_REACHED ⇒ **计入 completed 但从未妥投**。
- pre-C1 对照（worktree @ f654587，同 seed）：该读数 = 14(s101)/27(s102)；post-C1 = 1/1 ⇒ **C1 把绝大多数 cleanup-冒充-delivery 消掉了，但残留 1 条/seed 走的是另一条路径**（不是 dest-leg 装配缺失那条已被修的根因）。
- ⚠ 更正我在 #69-C2a/F 的说法："cleanup 分支在生产 seed 不可达、R5=0"只对 seed 40907 成立，**过度外推**；结项报告里"latent defect 有牙（仅注入面）"应改为"有真实正例（seed 101/102）+ 注入面"。
- 这是新的具名缺陷候选（记为 R7），不在本轮修复范围（本轮只重跑+出表）。交主控定是否开 #69-H/R7 轮。

## 7. D-iv 改变行为面的具名读数（2026-10-08，随 #69-H3 入档）

**"修复改变行为面"条目 —— 论文不得拿旧 buffer 峰值当 PSO 特性证据。**

g2teeth 门工况（seed=40901 / tasks=240 / fleet_mix={light:3,std:2,heavy:1}=6机 / 阈值15 全程未动），
HEAD(后缀规则) vs D-iv(执行器真 pop) 一手对照：

| 读数 | HEAD 后缀规则 | D-iv 真 pop | Δ |
|---|---|---|---|
| pending_buffer **峰值** | **15** | **10** | −5 |
| flush_size（size 触发口开几次） | **1** | **0** | −1 |
| flush_emergency | 1621 | 1453 | −168 |
| flush_timeout | 461 | 456 | −5 |
| optimize_calls（有分母证人） | 2083 | 1909 | −174 |
| has_denominator | True | True | 不变 |

复算命令：`python console/phase0_speed_gate_teeth_probe.py gate`（分别在 HEAD 树与 D-iv 树各跑一次）。

**因果（已证）**：旧后缀规则那 9 例 mid-flight re-route 提前计 completion ⇒ 无人机更早回待分配池 ⇒
pending_buffer 被虚增到刚好触到 size 阈值(15)、size 触发口开了 1 次。D-iv 按裁定根除提前 completion ⇒
积压真实降到 10、size 触发口一次没开、批量优化全靠 emergency+timeout。⇒ **旧的 buffer_peak=15 / flush_size=1
是在替 R7 那个 bug 记账，不是 PSO 的真实吞吐特性**。任何引用"PSO 在 6 机工况下靠 size 触发攒批"的说法作废。

⚠ 由此得出具名结论：**g2teeth 的牙（原挂 flush_size≥1 / peak≥15）无法在不失牙的前提下迁到 D-iv 树**——
D-iv 上 flush_size=0，改判 `flush_size>0`＝永红夹具；改判 `optimize_calls>0`＝无牙（mutate 面=6≠0）。
该门整体是在旧缺陷负载下标定的。停此交主控定夺（见 #69-H_terminal.md 挂账 + H3 终态汇报），未自行放宽或删牙。

**论文口径约束（新增，主控裁定②）**：
> **PSO 的 size-flush 机制在修正后的计时模型下从未触发——这是关于 PSO 调度器行为的事实，不是实现缺陷。**
> 论文若描述 PSO 缓冲/攒批机制，必须用 D-iv 后数据重述：批量优化实际由 emergency(1453)+timeout(456) 驱动，
> size 触发口在 6 机工况开 0 次。不得沿用"靠 size 阈值攒批"这类基于旧 buffer_peak=15 的表述。

**是否为让 size 触发口再打开而重标阈值？——不要。** 为好看调低 `buffer_size_threshold` 会改变调度器语义，
属 scheduler 硬边界外（route_planner/scheduler 不动是贯穿约束）。g2teeth 现按裁定①改显式 skip
（`[GATE_CALIBRATION_STALE]`，聚合里既不默默红也不默默绿），等独立 re-calibration 决策，本轮不动它。
