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
