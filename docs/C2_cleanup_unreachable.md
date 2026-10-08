# #69-C2：latent cleanup 不可达性论证（本轮零代码改动）

基线 `c5ea8b0`（D-iv 已落地）。主控窄敕三件之一：先答"一个 dest 尚未 pop 的机子能否进入 cleanup"，
答案必须有证人（代码或夹具），不许从断言倒推。实测结论：**当前提交态下该路径结构上开不了火** ⇒ 走裁定③，
**不改代码**，出本论证 + 解释与上一轮 seed101/102 R7 非零读数的矛盾。

## 1. 入口条件表（真实行号 + 判据原文，现读自 frontend/environment.py @ c5ea8b0）

| # | 位置 | 判据原文 | 语义 |
|---|---|---|---|
| E1 | environment.py:1233 | `if not self._prev_free_status.get(i, True) and drone.is_free:` | cleanup 分支唯一入口：该机上一帧非空闲、本帧变空闲 |
| E2 | environment.py:1234 | `if i in self.drone_assignments:` | 且仍挂着未送达 assignment |
| E3 | environment.py:1238 | `self._record_task_completion(i, assignment)` | 满足 E1∧E2 即计一次完成（＝兜底账） |

⇒ "dest 未弹出却走 cleanup" 要求 **同一机同时满足 E1 ∧ E2**。

## 2. is_free=True 的全部来源（枚举 frontend/drone.py + environment.py，共 4 处）

| 来源 | 位置 | 到达时 assignment 是否已被移除 |
|---|---|---|
| F1 构造初值 | drone.py:88 `self.is_free = True` | 新机无 assignment ⇒ E2 假 |
| F2 换电完成 | drone.py:281（仅 `_suspended_route` 为空时） | 挂起航线恢复走 drone.py:279 `is_free=False`；置真的那条要求无挂起任务 ⇒ E2 假 |
| F3 航线跑空后 | drone.py:342（`pop(0)` 使 scheduled_position 清空且无改道请求） | 该 pop 正是 dest 弹出本身；dest-pop 在 environment.py:1221/1230 已 remove/del assignment ⇒ E2 假 |
| F4 故障注入复位 | environment.py:545（`set_drone_out_of_service`，人工事故路径） | 同函数 :563 `assignments.pop(idx,None)` 先摘走并回队任务 ⇒ E2 假 |

⇒ 四条里没有任何一条能造出"is_free=True 且 assignment 仍在"。F3 是唯一"由飞行推进触发"的入口，
而它变空闲的前提恰是最后一个航点被 pop——dest 服务航点在 pop 的同一帧就被 :1212 记账并 :1221 移除。

## 3. 运行时证人（不是静态推断）

### 3.1 不变量探针：全 episode 逐步检查 E1∧E2 的必要前提
判据＝每步末统计"挂着 drone_assignments 却 is_free"的机数。
```
python <probe>: Environment.step 包装，逐 step 计 len([i for i,d if i in drone_assignments and d.is_free])
SEED=102   steps=2064  free_with_assignment_count=0
SEED=101   steps=2049  free_with_assignment_count=0
SEED=40907 steps=2018  free_with_assignment_count=0
```
合计 **~6131 步、0 次** 出现 E1∧E2 的前提状态。

### 3.2 cleanup 实际开火数（经生产入口 `experiments.worker.run_one(with_observer=True)`）
| 工况 | seeds | cleanup_no_svc | completions | destination_reached | legal_unique | unattributed_completions |
|---|---|---|---|---|---|---|
| 默认 config / 3600 | 101,102,40907 | **0** | 60 | 60 | 60 | 0 |
| 锁定 fleet 5/3/2（10 机）/3600 | 101,102 | **0** | 60 | 60 | 60 | 0 |

**正例对照（防"量具瞎了"）**：同两格 `completions_recorded == destination_reached == counter == legal_unique == 60`
且 `unattributed_completions=0` ⇒ observer 确实在分类每一次完成、且全部归到 `destination_branch`；
读数 0 属"现场没有"，不是"工具到不了"。

### 3.3 负面对照（我曾试图硬造 E1∧E2）
注入器扫描"assignment 存在 ∧ is_free"以强制 `_prev_free_status[i]=False` 造转换：
`NEGCHECK injected=False` ⇒ **连注入器都找不到可注入的时刻**，与 §2 枚举一致。
（注：该注入器写法偏保守，只作旁证；承重证据是 §3.1 的逐步计数。）

## 4. 与上一轮 R7 非零读数（task_44）的矛盾消解 —— 两边不是各自成立，是不同代码态

历史读数出处：`docs/取证输出/rerun65_cells.json`，locked = seeds 101–105 / greedy·ga·pso·ortools /
**episode 3600 / fleet_mix {light:5,std:3,heavy:2} / head=f2bcdf5**。其中 greedy-102：cleanup_no_svc=**1**、dr=59。

本轮把变量逐个对齐后复算：

| 代码态 | 含 C1? | 含 H1′(9b1cd15)? | 含 D-iv? | greedy-102 cleanup_no_svc | dr | legal_unique |
|---|---|---|---|---|---|---|
| `f2bcdf5`（rerun65 原态） | ✅ | ❌ | ❌ | **1**（一手复现） | 59 | 59 |
| `9b1cd15`（H1′ 前缀比对） | ✅ | ✅ | ❌ | **0** | 60 | 60 |
| `483fc6c`（HEAD 去 D-iv） | ✅ | ✅ | ❌ | **0** | 60 | 60 |
| `c5ea8b0`（D-iv） | ✅ | ✅ | ✅ | **0** | 60 | 60 |

⇒ 差异**不由 fleet/episode 造成**（我用 rerun65 的 5/3/2 十机 fleet 在 3600 步重跑，post-H1′ 各态仍是 0），
**由代码态造成**：关闭这条兜底火口的是 **H1′（9b1cd15）把弹出检测从长度差改为前缀比对**，
使 task_44 那类"同帧弹 dest + 追加 nest"能被正确记为送达、assignment 被 remove，从而不再残留到 is_free 转换。
C1 修的是 dest-leg 装配缺失（另一条根因），不足以关掉这一条。

**所以两个结论并不冲突**：R7 非零是 f2bcdf5 的真实读数；本轮"不可达"是 ≥9b1cd15 之后的真实读数。
我此前把"seed101/102 R7 非零"当作现状引用是**过期口径**——它已被 H1′ 闭合，此处更正。

## 5. 处置：按裁定③不改代码

- cleanup 分支保留原样（environment.py:1233-1244）：它的存在是为"充电自动航线等无 dest 航点的场景"兜底，
  在当前生命周期模型下 E1∧E2 不可满足 ⇒ 结构性不开火，无需 fail-closed 改造。
- **不新增变异两面**：裁定②的两面夹具只在"可达→改 fail-closed"时才需要；强行给一条开不了火的分支造红面，
  只会得到"期望值为 0 的夹具给不了牙"那种永真/永假的坏门。
- 已有牙维持：C1 门 `cleanup_completion_without_service` 断言 + G-H3-B（seed102 cleanup=0 且 task_44 送达）
  持续监这条火口；若将来有人改动 is_free 赋值点使其重新可达，这两扇会当场红。
- 挂账移交：`current_load` / `is_free` 状态语义审计仍归后续 **#69-C3**（§2 的 F2/F4 两处涉及载重与泊位状态转移，
  本轮不展开）。

## 6. 硬边界遵守
未 push、未打 tag、paper/ 未碰、未用绝对坐标回退；drone.py 三段（pop 点 :328-331 / is_free+current_load :342-343 /
单段直线位移 :362-366）本轮零修改；工作树净于 `c5ea8b0`（porcelain=0）。
