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
