# 干净树全量 console 聚合终态 + skip 双向对账（2026-10-08，第四十二笔欠账闭合）

## 1. 终态（本轮真跑，非推算）

```
[LOADED] cases=374
[AGG] ran=374 failures=0 errors=0 skipped=4 expected_failures=0 unexpected_successes=0
```

命令：`python -m unittest discover -s console -p "test_*.py"`（项目 `.venv310` 解释器，工作树 `git status` 为空、HEAD=`15c8db7`）
原始日志：本目录 `F_console_aggregate_374_skips.log`（27,686 B，sha256 前 12 位 `1372599444cb`）
耗时：**未测得** —— 本轮用 `TextTestRunner` 直接取结果对象，没记挂钟；上一笔同规模是 1606.941s。
⚠ 不拿那个旧数当本轮的读数（等式数字必须本轮解析）。

分母对账（同一轮现算，不是抄的）：`python console/_readme_counts.py --verify`
⇒ `[OK] console=53文件/374用例；experiments=3文件/32用例；frontend=2文件/21用例；.=1文件/3用例`
—— 与 `[LOADED] cases=374` **两个独立来源相符**。

## 2. 四条 skip 逐个点名（reason 为原文，非转述）

| # | 用例 ID | reason 原文 | 性质 |
|---|---|---|---|
| 1 | `console.test_c1_lifecycle_gate.C1LifecycleGate.test_1_rules_are_enforced` | `[OLD_IS_BASELINE_AUDIT_SNAPSHOT] pre-C1 基线审计见 docs/取证输出/c1_face_old.json（R1=12/R4=1/R5=12）；old 面不作通过/失败判据，牙由 mutate/forced_cleanup 注入面持有` | 默认 `C1_FACE=old` ⇒ 走 old 分支 |
| 2 | `console.test_c1_lifecycle_gate.C1LifecycleGate.test_4_mutation_face_proves_teeth` | `仅 mutation 面执行` | 同上，`FACE != "mutate"` 即跳 |
| 3 | `console.test_consistency_observer_zero_drift.ObserverZeroDrift.test_h_attribution_matches_frozen_baseline` | `[H_SKIPPED_NOT_FROZEN_BASELINE] 该基准只对 580c937 有效；修复后行为请见 c1_face_r2_fixed.json` | 需 `C1_BASELINE_SHA=580c937` 才断言 |
| 4 | `console.test_phase1b1_distance_experiment.FullPairedExperiment.test_h0_h1_paired_comparison` | `正式配对实验耗时长，显式 SWARM_1B1_FULL=1 才跑（否则是未执行，不是通过）` | **类级 `@unittest.skipUnless`** ⇒ 该类唯一用例被整类跳过 |

第 4 条对外表述必须是**「未执行」**，不得计入通过。名单与第三十七笔那份 4 条**逐条同名同因**（本轮没有新增也没有消失）。

## 3. 双向对账：谓词侧 vs 实测侧（这一步是本篇的重点）

谓词侧从 `console/test_*.py` 现算 AST（不跑测试），分两类形状：

| 形状 | 站点数 | 静态可推出"会跳"的用例数 |
|---|---|---|
| `@skip / @skipIf / @skipUnless`（类级或方法级装饰器） | 1 | **1**（就是 #4，类级展开到它唯一的 test_*） |
| `self.skipTest(...)` / `raise SkipTest(...)`（运行时条件） | 35 | 0（静态只能证明"这里有跳过分支"，不能证明本轮条件成立） |
| 合计 | **36**（分布在 15 个文件） | 1 |

对账结果：`observed=4 both=1 observed_only=3 predicate_only=0`
恒等式 `both + observed_only == observed` 有断言且成立。

⇒ **读数怎么解释**：装饰器那一类是静态可判的，判到了、也对上了（1/1，无多余）；
运行时条件那一类静态只能给候选集（35 个站点），实际本轮只有另外 3 个条件成立。
所以这不是"漏了 32 个"——那 32 个站点的守卫条件本轮没触发（缺地图/缺 osmnx/依赖齐全/基线 SHA 不符等），
它们属于**未触发的跳过分支**，既不该期望出现、也不该被当成缺陷。
最保守的说法：**本轮实测 4 条，全部有名有姓有条件出处；其余 32 个站点本轮不适用。**

## 4. 一次操作失误与其规矩化（写在这里而不是只留在对话里）

为了拿"逐条 reason"，我在 22:47 停掉了一轮已跑到 ~193/374 的 `discover` 重跑带枚举的版本，作废约 14 分钟机时。
按主控定的规矩复核该次停机是否合法：**属"输出形状拿不到所需字段"这一解** ——
`discover` 的 verbosity 输出里只有末尾一行 `skipped=4`，逐条 reason 只在 `-v -v` 下出现，而那种格式无法稳定解析成结构化成员；
所以要 `res.skipped` 只能换驱动方式。
⚠ 但停机当时我**没有先把这条理由写下来**，是先停了事后才补的 —— 规矩要求的是先写后停。
下次顺序：判定 → 写下是哪一条 → 再停。

同时遵守了另一条：等终态期间不动工作树（上一笔那例红就是聚合期间改 README 造成的自造红）。
本篇与日志归档写完之前，仓内零改动。
