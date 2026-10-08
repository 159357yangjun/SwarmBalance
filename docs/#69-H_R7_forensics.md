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

## 根因（代码级，具名行号）
`t=1415→1458` 之间，无人机背负**尚未消费的 dest 服务航点**时，被一条低电/改道逻辑用 `schedule_route([nest_pos])`（drone.py:221-222，**整体覆盖** scheduled_position，且 task_id=None ⇒ :223 清 executing_task_id）**替换掉**了剩下的 dest 航点；随后到站 `is_charging=True`。换电结束恢复分支（drone.py:271-273 `if self._suspended_route`）因 `_suspended_route` 为空（改道没走"挂起"路径 :285，而是直接覆盖）而无货可恢复 ⇒ dest 服务航点永久丢失 ⇒ 观察层永远等不到该任务的 DESTINATION_REACHED。之后 assignment 残留在 cleanup 分支被计成完成。

对照：预判式换电的**正规**路径是 :282-285「把剩余航线存入 _suspended_route 再清空」，换满后 :271-274 恢复——这条不丢妥投。**R7 触发的是绕过挂起、直接覆盖航线的那条改道**（load 同时被清零，指向 return_to_base:239-240 或等价覆盖点）。

## 为什么这是缺陷而非"合法保险"
completion_rate 把它算作已完成、但货物从未送达、current_load 被静默清零（:240/:336）⇒ 对外"完成率 1.0"在这一格上名不副实。它满足 latent-defect 定义：有真实正例（seed 101/102），不是纯注入面。

## 候选修法（均需碰 drone.py，故停下交裁，未自行实施）
- **H1（最小、对齐既有语义）**：任何"改道去机巢/仓库"的路径在覆盖 scheduled_position 前，若背负未消费的任务航点，一律先 `_suspended_route = 剩余航点`（复用 :285 的挂起+ :271 恢复机制），不清 current_load、不清 executing_task_id。使 dest 服务航点在换电后被恢复消费。
- **H2**：cleanup 分支不再无条件 `_record_task_completion`；对"有 assignment 但无 DESTINATION_REACHED"者按未妥投处理（退回池/标 incomplete）——但这会改 completion 口径，与"不动 cleanup accounting"边界冲突，风险更高。
- **倾向 H1**：它落在"改道不该丢任务"这一既有契约上，与 C1/C2b 一脉相承（修层间契约、不新增状态真源）。

## 验收预期（待批准后执行）
四格 rerun 重跑 `cleanup_completion_without_service` 归 0（或给出 H1 下"确无残留"的证明）；r5_nonexact_arrival_count 允许变；**completion / timeout 不得变**——若变即行为外溢，停下汇报。
