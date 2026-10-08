# 上位裁定第 6 条「一条常驻 order-independence 回归门」——三扇里哪一扇是它？

**一句答：P2（`console/test_p2_no_name_based_kernel_import.py`）就是那条常驻门的主体，且实测它会因新增污染变红；但按"后人重新引入全局污染时会红"这个范围量，还欠两条（见 §3），本轮不扩范围、只把判据写出来等批。**

先前那句"三扇门都报非零退码"答的是你补的**另一问**（门没跑起来时报红还是静默），不是第 6 条。两问不同，我当时把它们并列陈述容易被读成"六条判据齐了"——那是我把范围说宽了，就地更正：**三门 ≠ 第 6 条已满足**。

## 1. 判别式实测（两种形状各自注入，原始读数照抄）

### 形状 A：重新引入 P1 当初那笔污染（按名字 import 内核）
把 `console/test_r2_destination_without_load.py` 的 loader 改回 `from environment import Environment`（一行变异，跑完即还原）：

| 门 | 结果 | 读数 |
|---|---|---|
| **P2** | **FAILED (failures=1)** ✅会拦 | `[P2_NAME_IMPORT] … test_r2_destination_without_load.py:setUpClass: from environment import Environment（不在册）` |
| **P1** | **OK** ❌看不见 | `[P1_VERDICT] order_ab_rc=0 order_ba_rc=0 optimize_ab=11454 optimize_ba=11454` |
| P3 | 未单测该形状 | — |

⇒ **关键事实：P1 对这笔污染本身已经无感**——因为被污染的 G2 已子进程化，不再吃主进程常量。
所以"order-independence 回归门"**不能指望 P1**：它守的是"G2 这一条消费路径仍与顺序无关"，
而不是"没人再引入全局污染"。把它当第 6 条的主体，正是我上一轮说错的地方。

### 形状 B：只改环境变量不还原（结构上看不见的那一类）
把 r2 的 `tearDownClass` 改名使其失效（模拟"新增一个改了全局态就走人的模块"）：

| 门 | 结果 | 读数 |
|---|---|---|
| **P3** | **FAILED (failures=1)** ✅会拦 | `[P3_RESIDUE] 跑完 5 个模块后仍有未还原的全局态：[{"kind": "env", …}]` |
| **P2** | FAILED —— 但**成因不对** | 它红是因为 P3 的 setUpClass 在被污染树上跑时自己漏了 env（附带捕获），不是 P2 认得了这种形状 |

⇒ P2 是源码结构扫描，**天然看不见"只改 env 不还原"**；这一类只有 P3 那种运行时 diff 能抓。

## 2. 定性结论
- 第 6 条要的"后人重新引入全局污染 ⇒ 红"，**目前由 P2 + P3 两扇合起来覆盖两类形状**，各有实测正例。
- P1 不在这条职责上（它守具体消费路径的顺序无关性，且对原污染已无感）。
- **"三门齐 = 六条判据齐"不成立**，我上轮那句话要收回一半。

## 3. 还欠的两条（先判据、待批，本轮不动手）
**(i) 覆盖集是手写名单，新增模块不会自动进门。**
现状：`CLEAN_MODULES` 只列 5 个具名模块（r2 / c4_is_carrying / h_r7 / route_planner_equivalence / c1_dest_leg）；
新写的测试若改了 env/sys.path 而不还原，**根本不进 P3 的视野**。P2 扫全目录，但它只认一种形状。
判据（拟）：P3 的模块清单改为**从盘上现算**——凡 `console/test_*.py` 中出现
`os.environ["SWARM_BALANCE_SIM_CONFIG"] = …` 或 `sys.path.insert(…)` 的模块**必须**在普查集内；
命中而不在集内 ⇒ `[P3_COVERAGE_GAP]` 红（判据=缺口为 0，不是"名单里的都绿"）。
配套：普查集按上述谓词自动生成，另印 `modules_covered=%d / modules_matching_predicate=%d` 两个数供对账
（分母来自本轮扫描，不抄上一轮）。
代价明写：普查面变大 ⇒ 单轮耗时上升（现在 5 个模块 ≈ 8 s，全量谓词命中约 11 个模块），可接受则做。

**(ii) 没有一条门断言"套件整体与发现顺序无关"。**
现有 P1 只测一对顺序（r2↔G2）、且只盯一个读数。上位裁定第 2 条的字面是"改变测试导入顺序后结果不变"。
判据（拟）：取 discover 字母序与其**逆序**两种显式顺序，各在 fresh process 跑一遍
`console.test_*` 的一个**有界子集**（不含 OSM-booting 慢测，避免把并发假象请回来），
逐用例比对状态集合（pass/fail/skip 名单 + 关键数值读数），差集非空 ⇒ `[P1_ORDER_DEPENDENT]` 红。
判据写成 `(set_a == set_b) and all(s != 'fail' for s in set_a)`，并印两侧各自的 `Ran N tests` 分母。
代价明写：这是最贵的一条（两次子集全跑），且子集是我选的 ⇒ 它证的是"该子集顺序无关"，不外推到全仓。

**为什么不一上来就做 (ii)**：(i) 便宜且直接堵"新增模块绕过普查"这个真缺口；(ii) 的范围与成本要先由你定
（跑哪些子集、允许多久一轮）。我不替你把范围扩掉。

## 4. 复算命令
```
# 形状 A（P2 应红、P1 应绿）
python - <<'PY'   # 把 r2 的 load_kernel_environment() 换回 from environment import Environment
PY
python -m unittest console.test_p2_no_name_based_kernel_import.NoNameBasedKernelImport.test_A_no_main_process_name_import   # FAILED
python -m unittest console.test_p1_order_independence_gate                                                                   # OK ← 这就是"P1 不是那条门"的证据
# 形状 B（P3 应红）
python - <<'PY'   # 把 r2 的 tearDownClass 改名使其失效
PY
python -m unittest console.test_p3_no_cross_test_residue.NoCrossTestResidue.test_A_clean_modules_leave_no_residue             # FAILED [P3_RESIDUE]
# 两处变异均已 git checkout 还原；收尾 git status --short 为空
```

---

## 5. (ii) 已于 2026-10-08 落地为 `console/test_p4_suite_order_independence.py`（含一处**判据被实测改写**）

基线 b3f4451。主控批准实施、范围收窄为一次，并加两条：子集清单由我列主控裁、**每轮成本印在自己那行**。

### ⚠ §3(ii) 那条拟判据的形状被实测否掉了，这是本节最重要的一段

拟判据写的是："各在 fresh process 跑一遍子集（按两种顺序），逐用例比状态集合"。
第一版照做 = **一个进程内按指定顺序 `loadTestsFromNames(整批)` 再 run**。实测驳回：

```
before load: []
after load (NOTHING RUN): ['console.test_swap_time_gate', 'console.test_sla_consumption_gate']
```
⇒ `loadTestsFromNames` 在**构建 suite 阶段就把全部成员 import 完**。而 #70-P1 那笔污染冻结全局态的
时刻恰恰是 **import 期**（`frontend/environment.py:87/:100/:105`）。于是"谁先 import"在用例体内
**永远观察不到** —— 连做四次注入（抢先 setenv+按名字 import / 往 sys.modules 塞共享态 /
断言"我是第一个" / 断言"前驱是否已加载"）**全部 `STATE_DIFF={}`**，两侧 rc 相同。
⇒ 那种形状是一条**永不为红的比较**，正是"半坏自检比没有更坏"的具体样子。

定稿形状：**每个成员单独起一个进程**（`_SINGLE` 只 import 该成员），两个方向各跑一整批；
并用 `sys.modules` 反查"单加载进程里有没有把别的成员也带进来"（`[P4_BLIND]`）——
前提破了就红，不靠叙述。

### 牙（两面正例证人 + 判别式，全实测）

探针 `_p4_teeth_probe_tmp.py`（**刻意不带 `test_` 前缀**：P2 :180 与 P3 普查都按 `test_*.py` glob，
临时注入品若落在扫描范围内会被别的门扫到）读一个"前驱指纹"环境变量：
- 无前驱 ⇒ 必须绿（否则是恒红夹具）；有前驱 ⇒ 必须红（否则它对顺序效应无感）。两条都做成了断言。
- 判别式走本门真实通道：批次首 `probe_at_head=pass`、批次尾 `probe_at_tail=fail` ⇒
  `[P4_TEETH_VERDICT] exit_criterion=(head_state != tail_state)` 成立，比较分支被真实触发过。
- 探针用后 `finally` 删除并断言盘上无残留（`[P4_TEAR_DOWN]`）。

### 成本：静态估算被实测驳回一次，改成两行并排对账

| 行 | 内容 |
|---|---|
| `[P4_COST]` | 静态表 est_side_s=28.5 est_gate_s=57.0（表里的数取自**本门真实形状**的单成员进程实测，不是合跑时的模块耗时） |
| `[P4_COST_REAL]` | 本轮真跑 this_run_ab_s / this_run_ba_s / test_A_two_sides_s / **whole_gate_wall_s** / est_vs_measured / overhead_outside_two_sides_s；判据 `whole_gate_wall_s<=180` |

⚠ 第一版只印估算那一行，喊 49.8s 而实跑 103.4s ⇒ **成本行替自己撒了谎**。现在两行并排，
比值（≈1.9）与差额（≈52s，= 牙 + 自检的开销）都印出来，漂了能当场看见。

### 子集清单（8 个成员 / 40 用例，供主控裁）

c1_destination_leg_semantics(4) / c4_is_carrying_discriminator(5) / h3_real_pop_events(7) /
h_r7_delivery_detection(1) / r2_destination_without_load(4) / route_planner_equivalence(5) /
sla_consumption_gate(9) / swap_time_gate(5)。恒等式 `sum(per_module)==ran` 且任一成员不得为 0
（`[P4_EMPTY_MODULE]`——否则"两向一致"会被"两边都空"满足）。

**排除项与理由也印出来**（防下一个人以为"忘了加"）：`test_p1_order_independence_gate` ≈146.7s、
`test_speed_fallback_gate` ≈190s —— 两者内部已各自做 fresh-process A/B，套进来是平方成本。
⚠ 诚实边界：**被排除的恰是消费路径最复杂的两个，本门没覆盖它们。**

### 结果与残余盲区（明写）

本轮真跑：`Ran 3 tests ... OK`，退码 0；`ran_ab=40 ran_ba=40 state_diff=0`，两侧 8 个成员 rc 全 0。
⇒ **子集内确实顺序无关**，按主控说法这就是第一条常驻门的正例。

但必须并列写出这条正例**为什么便宜**：#70-P1 已经把 11 处主进程按名字 import 内核迁走了，
所以"抢先 import 改变后任成员读数"这一类在子集内**已无可观察对象**（我的四次注入之所以全平，
根因在此）。⇒ 本门当前守的是"新代码重新引入这类依赖时会不会被看见"，其可见性来自
**单成员进程**这个构造（新成员若依赖前驱留下的全局态，它在自己那一格里就会红），
而不是来自"两次整批跑的差异"。后者在本仓现状下是空的。这一点不要包装成"门很强"。

另：`test_p4_*` 自身不写 `SWARM_BALANCE_SIM_CONFIG`、不用 `sys.path.insert(`（只用赋值式引导永久目录），
故 P2 files=51 violations=0、P3 covered=10/matching=10 均不受本笔影响（本轮实测复跑过）。
