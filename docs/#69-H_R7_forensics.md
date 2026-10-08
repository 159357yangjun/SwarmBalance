# #69-H R7 取证：task_44「已装载却从未妥投、被计成完成」根因

基线 f1e35b→f1e3a5b。一手复现 seed 102 / greedy / episode 3600（生产入口 experiments.worker.run_one，非自写驱动）。本轮**只取证不改**——修法落点在 drone.py（预判式换电改道），属硬边界内文件，交回主控定夺后再动。

## 现象
`cleanup_completion_without_service` 在 seed 102 = 1（seed 101 三算法各 1）：task_44 计入 completed，但全程无 DESTINATION_REACHED ⇒ 妥投事实从未发生却被算作完成。pre-C1(f654587 worktree)同 seed 该类 = 14(s101)/27(s102)，post-C1 = 1/1 ⇒ C1 消掉了绝大多数（dest-leg 装配缺失那条根因），**残留这一条走的是另一条路径**。

## 逐航点轨迹（drone0 持 task_44，route_kinds 为 scheduled_position 的标签序列）
```
t=1306  ['waypoint','source','dest']   exec=task_44  load=2.0  charging=F
t=1339  ['source','dest']              exec=task_44  load=2.0
t=1415  ['dest']                       exec=task_44  load=2.0   ← 取货完成，只剩 dest 服务航点
t=1458  ['?']                          exec=None     load=0     ← dest 航点被单点(仓库/机巢)覆盖！
t=1486  []                             exec=None     load=0  charging=T  ← 飞往机巢换电
t=1666  (NO HOLDER，cleanup 计完成 origin=is_free_cleanup_branch has_dst_ev=False)
```
最后弹出的坐标 (357600.0, 3462308.0) ≈ config `task.warehouse_pos`(357600.57, 3462308.77)，kind='?'（无标签 2-tuple）⇒ 是"改道去机巢/仓库"的单点，不是 task_44 的目的地。

## 根因（代码级，具名行号）—— ⚠ 本节结论已在本轮后续取证中被**修正**，见文末"根因修正"
`t=1415→1458` 之间，无人机背负**尚未消费的 dest 服务航点**时，被一条低电/改道逻辑用 `schedule_route([nest_pos])`（drone.py:221-222，**整体覆盖** scheduled_position，且 task_id=None ⇒ :223 清 executing_task_id）**替换掉**了剩下的 dest 航点；随后到站 `is_charging=True`。换电结束恢复分支（drone.py:271-273 `if self._suspended_route`）因 `_suspended_route` 为空（改道没走"挂起"路径 :285，而是直接覆盖）而无货可恢复 ⇒ dest 服务航点永久丢失 ⇒ 观察层永远等不到该任务的 DESTINATION_REACHED。之后 assignment 残留在 cleanup 分支被计成完成。

对照：预判式换电的**正规**路径是 :282-285「把剩余航线存入 _suspended_route 再清空」，换满后 :271-274 恢复——这条不丢妥投。**R7 触发的是绕过挂起、直接覆盖航线的那条改道**（load 同时被清零，指向 return_to_base:239-240 或等价覆盖点）。

---

## ⚠ 根因修正（本轮二次取证推翻上节，一手证据为准）—— 批准 H1 前必须重读

上节"schedule_route 覆盖 + _suspended_route 空"是**错的**。插桩逐跳证实真实机制在 **environment.py 的航点弹出检测**，不在 drone.py：

task_44 持机 drone_0 的 scheduled_position 演变（kind 标签）：
```
t=1415  ['dest']        load=2.0 exec=task_44   ← 只剩 dest 服务航点
t=1458  ['?']           load=0   exec=None       ← 同一步内 dest 被弹出、并追加了仓库/机巢单点
```
关键一步 `[STEP-WITNESS] t=1458 prev=['dest'](len1) curr=['?'](len1)`：
- drone.update() 里 dest 航点被 :324 `pop(0)`（route 1→0），随即 :335-337 判"任务完成"置 is_free/清载/clear exec，再 :350-353 因低电 `schedule_route([nearest])` 追加一个仓库点（route 0→1）。
- 回到 environment.step 的送达检测（env.py:1190）：判据是 `len(prev) > len(curr)`。此处 prev=len1、curr=len1 ⇒ **长度未减 ⇒ 弹出检测整段跳过 ⇒ DESTINATION_REACHED 从未记录**。
- assignment 未被 :1205 消费块移除 ⇒ 残留 ⇒ 下一轮命中 is_free_cleanup 兜底(:1238)被 `_record_task_completion` 计成完成（has_dst_ev=False）。

⇒ **根因＝"送达事实靠航线长度差来推断"这一契约，在"同一仿真步内既弹出终点又追加换电航点"时失效**。这与 C1/C2b 同源（跨层用间接量猜业务事件），但落点在 environment.py 的检测谓词，不是 drone.py 的改道。

## 修正后的候选修法（原 H1 打错文件，作废；待重批）
- **H1′（推荐，落在真正机制）**：environment.py 的弹出检测不再只看 `len(prev)>len(curr)`，改为**按 prev 首元素身份判定**：若 `prev[0]` 是某 service 航点（source/dest 标签）而 `curr` 不再是同一个对象/坐标，即视为"本步消费了它"，无论长度是否变化。（仍只读 scheduled_position，不新建状态真源。）
- **H1″（更小但更脆）**：在 drone.update() 弹完 dest 触发完成的那一步，禁止同帧再 schedule_route 追加换电点（先完成、下一步再改道）。会把"完成"与"改道"拆到两步，改变时序，风险高于 H1′。
- 两者都**不碰 completion 口径定义**（区别于 H2）。倾向 H1′：修的是那条"用长度差当送达证人"的错误契约本身。

## 验收预期（批准后执行，不变）
四格 rerun `cleanup_completion_without_service` 归 0；r5_nonexact_arrival_count 允许变；**completion / timeout 不得变**；seed 40907 旧配对回放（c1_paired_replay…fixed.json）first_divergence 与九项读数不得变。任一变化即外溢，停下汇报。

---

## ✅ 主控裁定（本轮）：修在 env 检测层，不修 drone.py；H1 批文作废
理由：① schedule_route/return_to_base 钩子全部未捕获覆盖写 ⇒ drone 侧无错可修；② H1 目标点已被自证伪。

**最终修法（H1′，落在 environment.py:1190）**：弹出检测从"长度差 `len(prev)>len(curr)`"改为**逐位前缀比对**——被消费的事件＝prev 头部被移除的那个元素。判别式：仅当 `curr == prev[k:]`（curr 是 prev 去掉前 k 个的后缀，k≥1）时，认定 prev[:k] 这批航点在同步被逐个弹出 ⇒ 其中标签为 source/dest 的服务航点计入取货/送达；否则（curr 不是 prev 的任何后缀）判为 **re-route（整体换航线）**，不入送达账。这样 task_44 的"同 step 弹 dest + 追加 nest"能看见 dest 被消费（prev=['dest'] 且 curr=[]? 否——curr=['?']），需按"prev[0] 是否仍是 curr[0]"精确定位弹出数，见实现。

**两面夹具**：构造/复现"同一 env.step 内 pop dest + append 非 service 点"⇒ 修前 cleanup_no_svc=1 红、修后 DESTINATION_REACHED 补上该例且 cleanup_no_svc=0 绿；并加一条 re-route 阴性对照（整体换航线不得计送达），防误伤。

**验收四条（全须通过）**：(a) task_44 格 cleanup_no_svc→0 且补一条 DESTINATION_REACHED；(b) seed 40907 配对回放 first_divergence index=852 seq=853 task_11 与九项读数逐字不变；(c) 四格 rerun completion/timeout 逐格不变；(d) 新机制两面夹具先红后绿留档。

## 为什么这是缺陷而非"合法保险"
completion_rate 把它算作已完成、但货物从未送达、current_load 被静默清零（:240/:336）⇒ 对外"完成率 1.0"在这一格上名不副实。它满足 latent-defect 定义：有真实正例（seed 101/102），不是纯注入面。

## 候选修法（均需碰 drone.py，故停下交裁，未自行实施）
- **H1（最小、对齐既有语义）**：任何"改道去机巢/仓库"的路径在覆盖 scheduled_position 前，若背负未消费的任务航点，一律先 `_suspended_route = 剩余航点`（复用 :285 的挂起+ :271 恢复机制），不清 current_load、不清 executing_task_id。使 dest 服务航点在换电后被恢复消费。
- **H2**：cleanup 分支不再无条件 `_record_task_completion`；对"有 assignment 但无 DESTINATION_REACHED"者按未妥投处理（退回池/标 incomplete）——但这会改 completion 口径，与"不动 cleanup accounting"边界冲突，风险更高。
- **倾向 H1**：它落在"改道不该丢任务"这一既有契约上，与 C1/C2b 一脉相承（修层间契约、不新增状态真源）。

## 验收预期（待批准后执行）
四格 rerun 重跑 `cleanup_completion_without_service` 归 0（或给出 H1 下"确无残留"的证明）；r5_nonexact_arrival_count 允许变；**completion / timeout 不得变**——若变即行为外溢，停下汇报。
