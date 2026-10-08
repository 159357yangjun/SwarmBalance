# 阶段② 终态读数（2026-10-08 本轮真跑，非推理）

复算环境：项目 `.venv310`（在仓库上一级），工作目录 = 仓库根。
基线 `b9c5331`；本文件记录的是其后一次**只改注释/docstring/文档**的修正轮的读数。

---

## ① 全量聚合 + 逐个点名 skip

```
Ran 364 tests in 1897.973s
OK (skipped=4)
EXIT=0
```
命令：`python -m unittest discover -s console -p "test_*.py"`
日志：`%TEMP%/p70_p2_final_readout.log`（本轮原始输出）

分母对账：`python console/_readme_counts.py --verify` ⇒ `[OK] console=50文件/364用例；experiments=3文件/32用例`（同一轮现算，不是抄的）。

四条 skip 逐一点名（ID 由源码站点核对，reason 为原文）：

| # | 用例 ID | reason 原文（截断） | 性质 |
|---|---|---|---|
| 1 | `console.test_c1_lifecycle_gate.C1LifecycleGate.test_1_rules_are_enforced` | `[OLD_IS_BASELINE_AUDIT_SNAPSHOT] pre-C1 基线审计见 docs/取证输出/c1_face_old.json（R1=12/R4=1/R5=12）；old 面不作通过/失败判据，牙由 mutate/forced_cleanup 注入面持有` | 默认 `C1_FACE=old`（:36）⇒ 走 old 分支 |
| 2 | `console.test_c1_lifecycle_gate.C1LifecycleGate.test_4_mutation_face_proves_teeth` | `仅 mutation 面执行` | 同上：`FACE != "mutate"` 即跳 |
| 3 | `console.test_consistency_observer_zero_drift.ObserverZeroDrift.test_h_attribution_matches_frozen_baseline` | `[H_SKIPPED_NOT_FROZEN_BASELINE] 该基准只对 580c937 有效；修复后行为请见 c1_face_r2_fixed.json` | 需 `C1_BASELINE_SHA=580c937` 才断言 |
| 4 | `console.test_phase1b1_distance_experiment.FullPairedExperiment.test_h0_h1_paired_comparison` | `正式配对实验耗时长，显式 SWARM_1B1_FULL=1 才跑（否则是未执行，不是通过）` | **@unittest.skipUnless 类级装饰器**（:205）⇒ 该类唯一用例被整类跳过 |

第 4 条对外表述必须是**「未执行」**，不得计入通过——它不在"重载场景下优化器介入"那套结论的证据链里。

**skip 名单变化证人**：本轮聚合日志里 `grep -c GATE_CALIBRATION_STALE` = **0**（命中数 0）
⇒ g2teeth 那条旧 skip 确实已从聚合中消失，不是被别的 skip 顶替。名单从 5 条降为 4 条。

聚合内 g2teeth 那一格的原文（证明 L1 证人在聚合里也真跑了）：
```
[G2TEETH_L1] 标定门实跑 OK：Ran 8 tests，含 K1–K6 与冻结三元组
[G2TEETH_L2_OBSERVED] gate(opt=1909 flush_size=0 peak=10) | noDenom(opt=0 peak=2) | mutate(opt=6 flush_size=0 peak=3) —— 此行为**信息读数**，不进退码；size 触发口在真实工况下是否打开由 L1 合成夹具裁决
[G2TEETH] 阈值 15 与被测源码全程未改 ⇒ 变红的只能是 fixture
[G2TEETH] 负面对照已实测：阈值 15→2 时 gate 面 peak 降为 5、本门退码非 0
```

---

## ② 新常驻门的先红 / 现绿原始行，与负面控制 RC=1

### 先红那一次（对生产源码施加已知变异，不是构造永红夹具）

注入：`backend_si/pso_scheduler.py:1444` 的 `>=` → `>`（唯一一处，事后逐字节还原）。
两条具名红：
```
[CAL_K2] N=15 == 阈值 15 应恰好开一次 size 口，实得 {'flush_size': 0, ...}
[CAL_FROZEN_DRIFT] 找不到 size 触发口的比较式（原 :1444）⇒ 承重语句被改名/移动，本文件的标签推导全部失效，须重开 calibration
```
⇒ **哪格因无证人而红**：`test_freeze_triple` 那一格红的原因不是"哈希不等于记录的数"，
而是"**`:1444` 的比较式这个形状在源码里找不到了**"——它才是 size 口语义的唯一证人，证人被摘走 ⇒ 整套标签推导失效。

### 现绿（清洁树，同一条命令）

```
Ran 8 tests in 0.311s
OK
RC=0
[CAL_TEETH] 变异面生效：阈值 +1（≡`>=`→`>`）使 N==15 从 flush_size=1 变 0；K1 不受影响
[CAL_FROZEN] version=threshold@backend_si/config.yaml:dual_channel.{buffer_size_threshold,emergency_ttl,buffer_timeout} fixtures=K1_below,K2_at,K3_above_once,K4_emergency_not_size,K5_timeout_not_size,K6_mutation_ge_to_gt hashes=pso_scheduler.py=0ecfb9632995;drone.py=84bd484d1836;environment.py=8a6efb782b55
[CAL_ISOLATION] AST 扫描：文件访问型违规=0，import 型违规=0；唯一外部依赖=backend_si\config.yaml
```

### 负面控制 RC=1 那一行（外包证人自己坏掉时，g2teeth 必须拦）

注入：在 `_assert_calibration_gate_is_live()` 首行强行 `raise RuntimeError('SYNTHETIC: …')`。
```
    self._assert_calibration_gate_is_live()
RuntimeError: SYNTHETIC: calibration gate witness forced to fail
----------------------------------------------------------------------
Ran 1 test in 40.883s

FAILED (errors=1)
RC=1
```
随后按 sha256 逐字节还原（两侧同为 `c37b6e125fe9`），临时备份同轮删除。

归档文件名：
- `docs/取证输出/p70_p2_g2teeth/A_red_then_green_archive.md`（先红后绿 + 半坏自检面 D + 面 D 的实测）
- `docs/取证输出/p70_p2_g2teeth/D_old_skip_verbatim.txt`（被删 skip 的原文与死因）

---

## ③ 冻结三元组写在哪一行；重开规则是否入档

**代码侧（权威来源，运行时印出）** `console/test_g2teeth_calibration.py`：
| 元素 | 行号 |
|---|---|
| `FROZEN_PRODUCTION_FILES`（版本轴：三个生产文件） | **:50** |
| `THRESHOLD_SOURCE`（阈值来源轴） | **:56** |
| `FIXTURE_SET`（夹具集合轴，K1–K6 具名） | **:58** |
| `test_freeze_triple_is_recorded_and_recomputable`（把三轴当场算出并印 `[CAL_FROZEN]`） | **:191**，print 在 **:212** |
| 承重语句在位断言（比哈希更硬的那一面） | **:205**（`:1444` 比较式）、**:206**（`:1618` 计数点） |

**文档侧**：`docs/P70_g2teeth_calibration_plan.md` §4（三元组定义）+ §7「冻结三元组 v1」（实跑读数）。

**允许重开的四种情形 / 不允许的三种理由：已入档**，位置 `docs/P70_g2teeth_calibration_plan.md` **§5**（:67 起）：
- 允许 (a) `:1444` 比较式或 `:1618` 计数点被改动；(b) `config.yaml` 那三个 dual_channel 常数任一变化；
  (c) K1–K6 在没有上述改动的前提下变红（⇒ 查事故，**禁止**就地放宽）；(d) 主控书面要求换命题。
- 不允许 ✗"正式实验里 PSO 表现不好先把门关掉"（拿实验结果调门）；✗"聚合太慢先 skip"（该分层跑不该改判据）；
  ✗"peak 从 15 掉到 10 看着像回归就把阈值降到 10"（改 scheduler 语义，越界）。

⚠ 一处诚实更正（**已改回 §5 原文，不再只记在 §7**）：§5(a) 原写"哈希对不上 §4.3"，
而实现**不锁哈希**（锁了会每次无关改动都红、逼人放宽）。执行形状是"承重语句找不到即
`[CAL_FROZEN_DRIFT]` 红"。规则文本若与代码不一致，下一个人会照规则去查哈希、查不到东西 ⇒
所以把 (a) 就地改写为实现的形状，并保留"哈希当场算出并印出供比对"这半句。

---

## ④ 残余盲区：L2 什么时候才能升为判据（结构条件，不给百分比）

写在 `docs/P70_g2teeth_calibration_plan.md` **§8**。要点：
一条断言能进退码的唯一前提是**有一个独立于"当前运行读数"的标签来源**；L2 现在没有。
它的两个候选标签都被实测驳回过："上次跑出来是 15"＝循环论证且已被 D-iv 作废一次；
"PSO 应该攒到 15 才合理"＝我的直觉、不可复算。⇒ 只能印数，这不是降级是承认没资格。

升级的三个前置条件（全满足才谈，任一不满足不许升）：
- **C-1 阈值有推导依据入库**（15 目前是无文档依据的历史常数）；
- **C-2 场景契约固定**（到达过程 + 机队构成 + episode 长度 + completion 计时定义全部冻结，
  使"积压必然越过阈值"成为由契约推出的结论而非观测）；
- **C-3 变异两面各配证人**（一个真实缺陷变异**只让 L2 红**；一个"业务语义变更但实现正确"的变异
  **不该让 L2 红**——第二个方向就是 #69-H3 那次缺的东西）。

另纠一处本轮自查发现的**假指针**：标定门 docstring 原写"（见 test_L2_*）"，而该文件里没有任何 L2 用例
（8 条全是 L1）；L2 的真实形状是另一扇常驻门里的一条 print 行。已改为具名指到文件 + 行 + §8。
教训：**注释替代码作保**会让一个不存在的用例名活到下一个人真去找。
