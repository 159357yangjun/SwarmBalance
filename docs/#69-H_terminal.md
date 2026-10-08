# #69-H 修复终态汇报（R7：同步步弹出漏检）

基线 f1e3a5b → 本笔。修法落在 **environment.py 检测层**（按主控裁定，不碰 drone.py）。

## 改了什么
- `frontend/environment.py`：新增 `_consumed_prefix_len(prev, curr)`，把送达/取货的"航点被消费"判据从旧的 `len(prev) > len(curr)` 改为**前缀比对**：
  - (a) 正常前进：curr 是 prev 去掉前 k 个的后缀 ⇒ k 个被弹出；
  - (b) 同一 step「弹服务点 + 追加换电/仓库点」：curr 非后缀，但队首是已从 curr 消失的服务航点(source/dest) ⇒ 计为消费；
  - (c) 整体 re-route（队首非服务点、或服务点仍在 curr 中）⇒ k=0，不入送达账。
  消费块由"只看 prev[0]"改为"遍历 prev[:k] 每个被弹出的航点"，一次触发对应取货/送达。
- `console/test_h_r7_delivery_detection.py`：两面夹具（纯函数三面 + seed102 端到端真 worker）。
- `docs/数据来源与可追溯性登记表.md`：H1′ 插入使 environment.py 下游符号行号 +28，用 remap 工具重指 9 条 path:line 锚 + 手修 2 条（M9 avg_energy_per_distance→989、_is_carrying current_load→1777-1787），citation 门复绿。
- README 计数 40 文件 / 320 用例（新增夹具文件）。

## 验收四条逐条读数
| 判据 | 结果 | 一手出处 |
|---|---|---|
| (a) task_44 格 cleanup_no_svc→0 且补 DESTINATION_REACHED | ✅ seed102 reached 59→60、cleanup_no_svc 1→0；task_44 origin=destination_branch t=1458 | docs/取证输出/h_rerun_cells.json |
| (b) seed 40907 配对回放不得变 | ✅ completed/DR/cleanup=38/38/0、timeout 0.052632、delay 2.802632、first_divergence index=852 seq=853 task_11 全不变 | 本轮现测 vs c1_paired_replay…fixed.json |
| (c) 四格 rerun completion/timeout 不得变 | ⚠ **completion 全 1.0 不变；timeout/delay 7/8 格不变，唯 greedy-s102 变**（见下） | h_rerun_cells.json |
| (d) 新机制两面夹具先红后绿留档 | ✅ pre-fix RED([R7_STILL_PRESENT] task_44)、post-fix GREEN(6 tests OK) | 本轮 git checkout HEAD 对照跑 |

聚合 suite：A90+B44+C117+D25 = **276 tests, 0 failures**。C1 四面/Gate A/source/dest/Observer 零漂移全绿。

## ⚠ 判据 (c) 的内部冲突 —— 交回主控定夺，未自行放宽
(c) 要求"四格 completion/timeout 不得变"，与 (a)"task_44 从 cleanup-completion 改判为 delivered"**在受影响那一格上互斥**：
- 修前 task_44 在 t=1666 经 is_free_cleanup 计入完成（迟到，算 1 次超时）；
- 修后它在 t=1458 正确记为送达（on-time）⇒ greedy-s102 timeout 0.0667→0.05、delay 4.85→3.225。
这不是行为外溢，而是**修复生效的直接后果**——旧数把一个"从未妥投却兜底计时"的任务错记成迟到的完成，修后它按时妥投了。其余 7 格（无此碰撞）逐字不变，证明改动不外溢到干净路径。

⇒ 请你在两者间选：**(i)** 认可"被修格口的 timeout/delay 变化属预期修正"，据此更新论文口径（seed102 greedy 超时率随批次刷新）；或 **(ii)** 若坚持"任何格 timeout 都不得动"，则该修复无法达成 (a)，二者不可兼得，需重新界定 R7 是否算缺陷。执行会话倾向 (i)，但不自行替你改论文数字口径。

## 状态
未 publish、未 push。drone.py / route_planner.py / metrics_schema / runner 均未改（worker 的 --with-observer 仍是默认关、runner 不传）。停在 #69-H 修复终态汇报，等你对 (c) 冲突的裁定。

---

## 挂账表（#69-H 交付物 9b1cd15 的已知残余 —— 主控裁定①要求同时登此，不得只存 faceoff 文档）

| 编号 | 残余 | 一手证据 | 影响面 | 处置 |
|---|---|---|---|---|
| **H-R1** | 已提交规则（后缀+服务前缀）对 **9 例 mid-flight re-route 判为假阳性消费**：无人机停在离 dest/source 85~961 m 处、未经过该点却被记送达 ⇒ 这些任务的单条 completion 时刻可能偏早（后续会真送达，净 cleanup_no_svc 仍 0） | docs/#69-H_predicate_faceoff.md §1（seed102 全扫 9 例，列 t=436/479/511/983/1580/1619/1634/1745/1774 + dist_after） | 个别 completion 的 delay 计时偏早；不改 completed/DR/cleanup 计数 | **批准 #69-H2 行进线段谓词修**（见下）；在此之前引用 seed102 系 delay 时须带此注 |
| **H-R2** | 纯几何谓词（`dist(end,prev[0])≤1m`）虽修掉 H-R1，但把 seed40907 avg_delay 从 2.802632→2.776316（动冻结证人），且与旧规则在 seed40907 双向发散 11 处 ⇒ 两谓词都是错的子集 | docs/#69-H_predicate_faceoff.md §2–3 | 说明"第三个猜测直接替规则"不可行 | 转 #69-H2 纸面设计先行，禁未审落码 |

**结项判定不受影响**：#69 主链十笔仍成立；H-R1/H-R2 是 R7 修复的精度残余，非新缺陷类别。论文若引 seed102 greedy 的 delay/timeout 具体值，须待 H2 定标后刷新，或按"±1 步计时不确定"标注。

## 裁定更新（2026-10-08，D-iv）—— 覆盖上表处置栏与 faceoff §"保留"措辞
主控/ChatGPT 裁定 **不选 D-i/D-ii/D-iii**，改走第四方向 **D-iv**：
> **上位原则（冻结）**：到达不是几何观察值，而是执行器完成某服务航点的离散事件；几何只决定航点能否被执行器接受，业务只消费执行事件。

据此对本表的效力修订：
- **9b1cd15（suffix+service-prefix heuristic）降为历史中间对照，不作最终 lifecycle-correct baseline**。faceoff §当前状态里"已提交的 9b1cd15 规则**保留**"那句作废——它只是通往 D-iv 真实事件机制途中的启发式快照，其"curr 形状即弹出"的推断仍属被禁止的反推族。
- **#69-H2 行进线段谓词（本表 H-R2 拟修方案）已被否决并丢弃**：工作树那 71 行未提交改动回退至 HEAD `483fc6c`；原 diff 存档于 docs/取证输出/h2_segment_predicate_discarded.diff（防丢，非采用）。停报见 docs/#69-H2_stop_report.md。
- **H-R1 的 9 例 mid-flight re-route 假阳性由 D-iv 真实 pop 事件机制消除**（T5 夹具直接杀），不再依赖任何几何/形状推断。
- #69-H3 交付判据、六硬夹具 T1–T6、五门 G-H3-A..E 见下轮正文；(b) 参照数 avg_delay=2.802632 经溯源门 test_h_b_baseline_provenance.py 钉死，**不得 re-freeze 到 2.776316**。

## H3 复跑收口状态（2026-10-08）—— citation 已闭 / g2teeth 停裁 / 并发假象登记不修
全量 console suite（post-remap，330 tests）4 处红逐条定性：
- **citation 三门随 remap 收口 ✅**：`_citations.py --verify` 曾报 `[REWRITE_MAP_STALE]`（提交改写映射表落后 git，HEAD 上即存在、非 D-iv 引入）。执行 `--rewrite-report --write` 重生成表（旧指针18/悬空32/问题0）后 verify exit=0，`test_coverage_is_printed` standalone OK。environment.py 行号漂移的 12+1 条 path:line 已 remap，citation 门 0 breaks。
- **并发假象 ×2 登记为已知干扰、不修**：`test_g2_all_four_algorithms_get_real_fleet_speed`、`test_rewrite_map.test_batch_read_matches_per_object_read` 在聚合 discover 里红、standalone 均绿 ⇒ 是 OSM-booting 慢测并发/资源干扰所致，与被测语义无关，遵"偶发红写带分母、不当缺陷"处理，只登记不动代码。
- **g2_all_four 的聚合红已一手定性为预存 import-order 污染（非 D-iv）**：判别式实测——(a) speed_gate 单跑 `test_g2_all_four` OK；(b) `test_r2_destination_without_load` + speed_gate 两模块配对跑 ⇒ `[pso][NO_DENOMINATOR]` FAIL；(c) **同一对配在 pre-D-iv 文件（git checkout 483fc6c 版 environment/drone）上照样 FAIL**。⇒ 成因是 test_speed_fallback_gate 在 import 期 `_install_gate_config()` 冻结机型参数时，读到的 `SWARM_BALANCE_SIM_CONFIG` 被字母序在前、且 setUpClass 直接 setenv 而不还原的模块（如 test_r2）改指向了别的配置——与本会话 D-iv 改动无关，属既有测试隔离缺陷。登记为 pending-revalidation（修法应是该门自带配置注入与前置模块解耦），不在 H3 授权内动它。
- **g2teeth 停在待裁 ⛔**：一手证据见 docs/#65_rerun_delta.md §7 —— D-iv 树 gate 工况 flush_size=**0**、buffer_peak=**10**（HEAD 是 1/15）。size 触发口在修正计时后从未打开 ⇒ "重定为结构事实 flush_size>0"＝永红夹具、"optimize_calls>0"＝无牙(mutate=6≠0)。按主控裁定①"重定后仍红则停下交具名证据"停此，未删牙未降阈。论文侧：旧 buffer_peak=15/flush_size=1 作废，不得当 PSO 特性证据（裁定②）。
- **g2teeth 处置已定（主控裁定①）**：不重定义/不降级/不删——改为**显式 skip + 具名理由** `[GATE_CALIBRATION_STALE]`（test_speed_fallback_gate.py:329 前置 guard：probe 实测 flush_size==0 时打印状态并 skipTest）。skip ≠ 通过 ≠ 失败，聚合报告行印出该状态，不许默默红或绿。等独立 re-calibration 决策；不为让触发口再开而调低 `buffer_size_threshold`（改 scheduler 语义，硬边界外，裁定②）。
- **自纠入档**：上一轮我误把 unittest 缓冲的进度点读成"无 FAIL/ERROR"，本轮以一手文件读数（FAILED failures=4 + 具名清单）纠正。

## #69-H2 计划（待纸面设计审批，本轮未动码）
谓词方向：prev 前缀逐点判是否落在本步位移线段 [start,end] 可信容差内 + curr 与剩余一致。容差真源拟引用 route_planner.py:160 `euclidean(current,goal)<1`（同一 <1m "close enough" 定义）。验收三件：(a) seed102 九例判回 k=0；(b) seed40907 含 avg_delay 逐字不变；(c) t=521/t=79 双向分歧各归其位；三面先红后绿留档（旧规则在 (a)(c) 实测报红）。
