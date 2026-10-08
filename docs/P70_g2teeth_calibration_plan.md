# 阶段② g2teeth 重标定方案（纸面，未动一行码）

基线 b25634c。上位裁定原话约束：**不得拿当前正式实验结果"调到能过"**，要用**已知标签夹具**，
标定完冻结"阈值来源 + 夹具集合 + 版本"。本文件只交三件事：夹具清单与标签来源、阈值推导路径、
什么情况下允许重开 calibration。等批了才改码。

---

## 0. 现状（一手事实，先说清为什么它现在是 skip）
| 项 | 值 | 来源（可复算） |
|---|---|---|
| size 触发口判据 | `len(pending_buffer) >= buffer_size_threshold` | `backend_si/pso_scheduler.py:1444` |
| 阈值数值 | **15** | `backend_si/config.yaml` → `dual_channel.buffer_size_threshold`（读入点 `pso_scheduler.py:861`） |
| flush 原因计数 | `stats['flush_size' / 'flush_emergency' / 'flush_timeout']` | 累加点 `pso_scheduler.py:1618`，初值 `:940` |
| 探针三面 | gate(240 任务/6 机) / noDenom(60/10) / mutate(240/10) | `console/phase0_speed_gate_teeth_probe.py:44-50` |
| D-iv 树实测读数 | gate 面 `flush_size=0`、`buffer_peak=10`（旧校准下是 1 / 15） | `docs/#65_rerun_delta.md §7`、`docs/#69-H_terminal.md` |

⇒ 门的牙原先挂在"size 触发口会打开"上；D-iv 修好 completion 计时后那个口在**同一工况**下从未打开
⇒ 判据不可满足 = 永红夹具。按裁定①改成显式 skip `[GATE_CALIBRATION_STALE]`，不是降级也不是删。

## 1. 关键判断：这条门到底该守什么（先定命题，再谈阈值）
旧命题（已死）："PSO 的 size 触发口在门工况下会打开" —— 它是**对一次特定运行读数的断言**，
所以业务语义一变就作废，且永远无法区分"算法没积压"与"我测错了"。

拟改为两层，各自都有已知标签的证人：

- **L1 机制层（承重、必须是常驻门）**：*给定一个我们手工构造、buffer 长度已知的场景，
  size 触发口必须在 ≥15 那一格打开、在 ≤14 那一格不打开。*
  ⇒ 这一层的标签来自**我们自己写死的输入**，不来自任何正式实验，天然满足"不许拿实验结果调"。
- **L2 观测层（信息读数，不作通过/失败判据）**：真实门工况下 size/emergency/timeout 各触发几次。
  ⇒ 它是 scheduler 行为的事实，不是实现缺陷；随计时修复而漂移属预期，因此**不进退码**。
  （旧门正是把 L2 的数字当 L1 的牙用，才会一修业务语义就作废。）

⚠ 明写这条改性的代价：L1 用的是合成场景，它证的是"触发口的代码逻辑正确"，
**不证**"真实工况会积压到 15"。后者若被论文引用，只能作为 L2 读数报出并标 measured-not-guaranteed。

## 2. 夹具清单与标签来源（全部为合成输入，零依赖正式实验产物）

| ID | 夹具 | 已知标签（期望值从哪来） |
|---|---|---|
| K1 | `_maybe_flush_buffer` 直调：塞 N=14 条假任务进 `pending_buffer`，`current_time` 固定、所有 `_abs_deadline=inf` | 标签=`flush_size==0 and reason is None`。来源：**阈值定义本身**（14 < 15，`pso_scheduler.py:1444`），非实验 |
| K2 | 同 K1 但 N=15 | 标签=`flush_size==1`。来源：`>=` 边界（同上）。K1/K2 合起来钉住"边界在哪一格"，任一边漂都会红 |
| K3 | 同 K1 但 N=16、`eager_idle_dispatch` 保持默认 | 标签=`flush_size==1`（一次 flush，不是两次）——钉住"触发口每次步最多打一发" |
| K4 | N=14 但把某条任务的 `_abs_deadline - current_time` 设成 `< emergency_ttl(40)` | 标签=`flush_emergency==1 and flush_size==0` ⇒ 证明三触发口的**归因互不污染**（emergency 不会被记成 size） |
| K5 | N=14、无紧急、`buffer_entry_time` 造出 `current_time - oldest > buffer_timeout(120)` | 标签=`flush_timeout==1 and flush_size==0` ⇒ 同上，timeout 也不冒充 size |
| K6 | 变异面：把 `:1444` 的 `>=` 改成 `>`（临时副本，不改生产） | 标签=K2 **必须变红**、K1 仍绿 ⇒ 证明这套夹具真的由阈值承重；若 K2 不变红，说明夹具没有牙，标定作废 |
| K7 | 消融面：`eager_idle_dispatch=False` 跑一遍现有 G2 门工况 | 目的不是判据，是**回答"15 这个阈值在当前计时下需要多大才会被真实工况摸到"**——给 L2 一个可解释的分母，避免下次又把它当牙 |

夹具纪律（沿用本轮已验证过的三条）：
① 每条都要有"注入即红"的另一面（K6 就是整套 L1 的牙）；
② 期望值一律写成**结构事实**（阈值±1 的两侧），不写百分比、不写"这次跑出来几次的数"；
③ 断言吃被测对象自己的计数器（`stats['flush_*']`，`:1618`），不吃我在测试里复刻的计数。

## 3. 阈值的推导路径（谁定的、能不能动）
- 现值 15 的来源：`backend_si/config.yaml`（提交 `fcc7c5f` 起就在，非本轮引入）。仓内**没有**注释或文档说明它是怎么定的 ⇒ 诚实结论：**这是一个无文档依据的历史常数**，我不替它编一个理由。
- 因此本次标定**不动阈值**（改它就是改 scheduler 语义，属硬边界外，与 #69-H3 裁定②一致）。
- 标定只做一件事：把判据从"真实工况会打开 size 口"换成"size 口在阈值±1 两侧行为正确"。
- 若将来真要重定阈值：必须先补一份"为什么是这个数"的推导（例如以 K7 消融给出积压分布），并由主控签字；本轮不做。

## 4. 冻结物（标定完成时一次性入库，防"事后漂移"）
`CALIBRATION-FROZEN v1` 三元组，写进 `test_speed_fallback_gate.py` 顶部注释 + 本文件末尾：
1. **阈值来源** = `backend_si/config.yaml:dual_channel.buffer_size_threshold = 15`（读入点 `pso_scheduler.py:861`，比较点 `:1444`）；
2. **夹具集合** = K1–K7（各自标签见 §2 表）；
3. **版本** = 生产代码指纹 `git hash-object backend_si/pso_scheduler.py` + `frontend/environment.py` + `frontend/drone.py` 三个哈希，外加本文件 commit sha。
   ⇒ 任一哈希变了，skip 横幅就该摘下来重跑 K1–K6；这比"看聚合顺不顺眼"可复算。

## 5. 什么情况下允许重开 calibration（写死规则，不给临场判断留口子）
允许重开，当且仅当下列之一发生：
- (a) `pso_scheduler.py` 的 `:1444` 比较式或 `:1618` 计数点被改动（哈希对不上 §4.3）；
- (b) `config.yaml` 里那三个 dual_channel 常数（15 / 40 / 120）任一变化；
- (c) K1–K6 中任一条**在没有上述改动的前提下变红** ⇒ 这才是要查事故的时刻，此时**禁止**直接放宽判据让它变绿（沿用"当场变红的门交回主控定"）；
- (d) 主控书面要求换命题（例如决定让 L2 也进退码）。

**不允许**的重开理由（这三条就是把门做坏的形状）：
- ✗ "正式实验里 PSO 表现不好，先把门关掉" —— 那是拿实验结果调门；
- ✗ "聚合套件太慢，先 skip 掉" —— 应改为分层跑，不该改判据；
- ✗ "buffer_peak 从 15 掉到 10，看起来是回归，把阈值降到 10 让它过" —— 改 scheduler 语义，越界。

## 6. 落地范围预告（等批，本轮不做）
- 新增 `console/test_g2teeth_calibration.py`：K1–K6 常驻门（合成场景，秒级，不起 OSM 子进程 ⇒ 便宜）。
- `test_speed_fallback_gate.test_g2teeth_*`：把现在那条 `[GATE_CALIBRATION_STALE]` skip 换成
  "L1 交给新门；本用例只印 L2 读数并断言 `optimize_calls>0 or 明确标注无分母`"，同时保留具名状态行。
- `docs/#65_rerun_delta.md` 追加一行登记"15→10 的旧读数改列为 L2 观测事实"。
- README 门禁计数与 CHANGELOG 一笔；**不动 `backend_si/config.yaml`、不动 `pso_scheduler.py`**。

---

## 7. 实施轮终态（2026-10-08，基线 b8fdaee 之后）

纸面方案获批进入实施。逐条对照 §6 的预告：

| 预告 | 实际落地 | 差异 |
|---|---|---|
| 新增 `console/test_g2teeth_calibration.py`（K1–K6 常驻门） | ✅ 同名文件，**8 条用例 / 0.238s**（K1–K6 + 冻结三元组自证 + 硬约束自证） | K7 消融面**未做**：它只产 L2 解释性读数、不进判据，本轮不为它起 OSM 子进程；需要时单独放行 |
| skip 换成"L1 交新门 + 本用例只印 L2" | ✅ `[GATE_CALIBRATION_STALE]` 整块删除（原文留档 `docs/取证输出/p70_p2_g2teeth/D_old_skip_verbatim.txt`），改为真实判定：**退码 0、无 skipped** |
| README 门禁计数 + CHANGELOG 一笔 | ✅ console 49→**50 文件 / 364 用例**（由 `_readme_counts.py --fix` 写，非手抄） |
| 不动 `config.yaml` / `pso_scheduler.py` | ✅ `git diff --numstat -- backend_si/ frontend/ experiments/ config/` 为空；变异只在一次性注入后**逐字节还原** |

### 实施中比纸面多出来的两件事（都是纸面没预见的）

1. **L1 证人必须挂在 g2teeth 里面**（`_assert_calibration_gate_is_live()`）。把 size 口的判据外包给新门之后，
   如果那扇门因改名/报错/被 skip 而**根本没跑**，g2teeth 就成了"没人守着的通过"——那是最贵的假绿灯。
   ⇒ 断言四件事同时成立：`Ran N tests` 行存在、`N ≥ 7`、`returncode == 0`、输出含 `[CAL_TEETH]`；
   任一不成立 ⇒ `[CAL_BLIND]` / `[CAL_GATE_RED]` / `[CAL_NO_TEETH]` 红。**读不到读数 = 红，不是绿。**

2. **mutate 面的魔法数 `optimize_calls <= 3` 自己也是旧标定**。它是 pre-D-iv 时序留下的实测值，
   D-iv 树上同一格实测为 **6** ⇒ 照抄 3 会让本门以"我自己的过期校准值"为由红掉，正是 #69-H3 那条教训的复现，
   也正是本次重标定要消灭的形状。⇒ 换成结构关系 `m_opt * 100 < g_opt`（切机队后 optimize 必须跌破 gate 面的百分之一），
   **分母用本轮自己的 gate 读数**，不抄上一轮。

### 冻结三元组 v1（实跑读数，可复算）

```
[CAL_FROZEN] version=threshold@backend_si/config.yaml:dual_channel.{buffer_size_threshold,emergency_ttl,buffer_timeout}
            fixtures=K1_below,K2_at,K3_above_once,K4_emergency_not_size,K5_timeout_not_size,K6_mutation_ge_to_gt
            hashes=pso_scheduler.py=0ecfb9632995;drone.py=84bd484d1836;environment.py=8a6efb782b55
```
复算：`../.venv310/Scripts/python.exe -m unittest -v console.test_g2teeth_calibration`

注：`test_freeze_triple` **故意不把哈希写死成断言**（否则每次无关改动都要来改测试，门会被人关掉）。
它断言的是两件更硬的事：① 三个生产文件的哈希当场算出并印出（漂移可见）；
② 两条承重语句（`:1444` 的比较式、`:1618` 的单次计数点）仍在原位存在，找不到即 `[CAL_FROZEN_DRIFT]` 红。
⇒ §5 的重开规则 (a) 的实际执行方式是"**承重语句消失/漂移即红**"，而不是"哈希不同即红"。
(b) 那三个常数由 `setUpClass` 逐条核对"调度器读到的 == config.yaml 里解析出的"，不符即 `[CAL_LABEL_SOURCE_LEAK]`。

### 先红后绿的实测两面（§5(c) 的一次真实演练）

对生产 `:1444` 施加 `>=` → `>` 后，标定门**两条具名红**：
`[CAL_K2] N=15 == 阈值 15 应恰好开一次 size 口，实得 flush_size=0`、
`[CAL_FROZEN_DRIFT] 找不到 size 触发口的比较式（原 :1444）`；逐字节还原后复绿。
原始输出与复算命令：`docs/取证输出/p70_p2_g2teeth/A_red_then_green_archive.md`。

### 实施中自伤两次（登记，防下一个人重踩）

`test_no_experiment_artifacts_are_read` 连着误伤自己两回：第一版按全文 grep，打中了自己的 docstring
（docstring 里写着"不读 results/"）；第二版改按字符串字面量扫，仍打中 docstring。
定稿形状 = **只看真的会打开文件的调用与真的会导入模块的语句**的字面量参数。
教训与 P2 那四次同一条：**判据必须认得自己扫的是什么。**
