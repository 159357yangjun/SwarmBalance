# 四扇常驻门：各自守什么、**守不住什么**（一手源码/读数核对，2026-10-08）

纪律：每扇门只写"能守什么"就是广告。下面每条"守不住"都指向具体行号或本轮实测，不是免责声明的修辞。

| 门 | 职责一句话 | 判据形状 | 本轮实跑成本 |
|---|---|---|---|
| **P1** `console/test_p1_order_independence_gate.py` | 守"**G2 那一条消费路径**"在两种发现顺序下读数一致 | 两向各起 fresh process 跑 `TARGET`，比 `[G2/pso] optimize` | 146.7s |
| **P2** `console/test_p2_no_name_based_kernel_import.py` | 守"**源码结构**"：测试不许在主进程按名字 import 内核 | 扫 `console/test_*.py`，违规=0；豁免表基线空 | 0.28s |
| **P3** `console/test_p3_no_cross_test_residue.py` | 守"**运行时残留**"：改了全局态必须还原 + 普查集不得被人手写缩小 | 子进程真跑完成员后 diff env / sys.path；恒等式 `matching==covered` | ≈250s（含在合跑里） |
| **P4** `console/test_p4_suite_order_independence.py` | 守"**结果面**"：同一批用例换发现顺序不得改变逐用例状态 | **每成员单独起一个进程只 import 它自己**，两向各跑一整批后比状态集合 | 96–116s（整条门墙钟） |

## P1 守不住什么

1. **它对 #70-P1 原污染已经无感**。判别式实测（`docs/P70_which_gate_is_the_resident_one.md §1` 形状 A）：
   把 r2 换回按名字 import ⇒ **P2 FAILED 而 P1 仍 OK**。因为被污染的 G2 已子进程化，不再吃主进程常量。
   ⇒ 别把"P1 守顺序"读成"新增污染会被发现"。
2. 目标只有**一个具名用例**（`:29 TARGET = …test_g2_all_four_algorithms_get_real_fleet_speed`）+ 一个具名前驱
   （`:33 PRECEIDER = console.test_r2_destination_without_load`）。它是一对顺序、一个读数，不是套件级断言。
3. 注入面测的是"污染确实改变了可见状态"（`[P1_INJECT_NO_EFFECT]`），**不测**"污染会传染到别的用例"。

## P2 守不住什么

1. **只认一种形状**：`import environment` / `from environment import …` / `__import__("environment")`
   （`:44 NAME_IMPORT`）。按名字 import `drone` / `task` / `route_planner` / `config.*` **都不在它视野内**——
   它们同样在 import 期冻结常量（例如 `frontend/drone.py:13-37` 从配置读 BATTERY/WIND 常量）。
   ⇒ 这是刻意收窄的（判据必须认得自己扫的是什么），但后果是：**换个内核模块名就能绕过 P2**。
2. 普通字符串拼接后喂 `python -c` 的那类命中**只登记不判红**（本轮 `plain_string_pending=4`）⇒ 依赖人工确认宿主，机器没咬。
3. raw-string 子进程脚本整体豁免 ⇒ 若有人把该在主进程做的事塞进 raw string 里，P2 看不见。

## P3 守不住什么

1. **只测 env / sys.path 两面**（docstring `:24-28` 自述）。随机状态、注册表单例、全局单例**没测**——
   判据原文列了五类，这里只做到有实测证据的两类。补另两类要先证明"确有模块改了它且没还原"。
2. **`sys.modules` 被撤掉当判据**（`:174`）：任何真运行都会正常导入 drone/task/route_planner/config.*，
   当判据会让门永远红、只能靠放宽过活。该面由 P2 从源码结构侧守，但见上面 P2 的第 1 条限制。
3. 谓词四次收窄后有意的漏检：`sys.path[:0] = [...]` 这类**赋值式**引导不在 `PATH_INSERT` 的形状里
   ⇒ 新写的门（如 P4、标定门）不被 P3 收录。它们的残留改由 P3 test_A/test_F 的运行时 diff 兜住，
   但**结构面上看不见**。这是"宁可漏不误伤"的代价，已登记在 CHANGELOG 第三十三笔残余边界 (iv)。
4. 自我嵌套护栏使子进程跳过 P3 自己 ⇒ 本模块的残留由父进程观测（test_F），**子进程普查看不见它自己**。

## P4 守不住什么

1. **子集只有 8 个成员 / 40 用例，全仓是 51 文件 / 367 用例** ⇒ 它证的是"该子集顺序无关"，不外推。
2. **被排除的两个恰是消费路径最复杂的两个**：`test_p1_order_independence_gate`≈146.7s、
   `test_speed_fallback_gate`≈190s（各自内部已做 fresh-process A/B，套进来是平方成本）。
   这两格里若真有顺序依赖，P4 现在看不见。
3. **这条正例之所以便宜有个不舒服的原因**：#70-P1 已迁走 11 处主进程按名字 import ⇒
   子集内**已不存在"读主进程冻结常量"的可观察对象**。本轮四次注入（抢先 setenv+按名字 import／
   塞 `sys.modules` 共享态／断言"我是第一个"／断言"前驱已加载"）**全部 `STATE_DIFF={}`**。
   ⇒ P4 的可见性来自"**每个成员在自己那个干净进程里单加载**"这个构造（新成员若依赖前驱留下的全局态，
   它自己那一格就会红），**不是**来自"两次整批跑的差异"。后者在本仓现状下是空的。不要把它讲成"门很强"。
4. 关键数值读数（optimize 次数一类）只在成员自己的 stdout 里，跨成员不比对 ⇒ 若某顺序效应只改**数值**不改
   pass/fail 状态，P4 现在不会红（`readings` 字段留了口子但当前判据不吃它）。

## 四扇合起来仍然共同的盲区

- 都不看**随机状态**（`random` / numpy RNG）、全局单例、注册表的污染与不还原。
- 都不看**生产代码内部**的顺序敏感：P2/P3/P4 的作用域都是 `console/test_*.py`。
  生产侧 `console/sim_session.py:43` 的名字绑定仍在（reload 语义所需，改它属另一类授权）。
- 都不能替代聚合本身：四扇全绿只说明"这些形状没被破坏"，不等于"产品没问题"。

## 附：P4 落地后**第一次真咬**就是咬到我自己（同轮实测，非事后编）

聚合本轮 `Ran 367 / FAILED (failures=1, skipped=4)`，唯一那条红是 P4 的 `test_C`：

```
[P4_VERDICT]   cost_ab_s=22.0 cost_ba_s=22.0            ← 两侧子进程都很快
[P4_COST_REAL] whole_gate_wall_s=845.1                  ← 但整条门墙钟 845s
               overhead_outside_two_sides_s=801.1       ← 差的 801s 在 import→开跑之间
AssertionError: 845.09 not less than or equal to 180 : [P4_TOO_EXPENSIVE] 本轮整条门真跑 845s > 180s
```
单跑同一把门：`wall=88–105s`、`state_diff=0`、判据绿。⇒ **那 801s 不是本门的工作量，是同一台机器上
并发的别的常驻门（P1 146.7s / P3 ≈250s / speed_fallback ≈190s）在抢 CPU。**

⇒ 结论与处置：**墙钟秒数不得当退出码**（它会把"机器忙"报成"回归"，正是本项目纪律里"偶发红必须带分母、
负载相关读数不进退码"那一类）。改为：
- 只**印**不判：`whole_gate_wall_s` / `est_vs_measured` / `overhead_outside_two_sides_s` 全部留在读数行；
- 改吃两条**结构性**判据：成员数恒等于 8（防名单被悄悄缩）、以及 `_LAST_RUN.max_single_cost < SINGLE_TIMEOUT_S`
  （超时护栏被尊重 ⇒ 若某成员真的挂死，那是"读不到"而不是"读到一致"，必须红）。
- 单次超时上限从裸参数升为具名常量 `SINGLE_TIMEOUT_S = 900`，注释写明为什么它是护栏而不是预算。

复算：`python -m unittest console.test_p4_suite_order_independence`（单跑 wall≈88s，OK）；
聚合里那一格的红见 `%TEMP%/p70_p4_full_suite.log`（改前）与 `p70_p4_final_suite.log`（改后）。
