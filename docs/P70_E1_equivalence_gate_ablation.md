# E1↔E0 等价门那条红的受控消融定性（阶段⑤ 收尾，裁定 (二)①）

基线 36b64cd。**结论先说：D-iv 假设被否证；这条红不是"某次改动引起的行为漂移"，而是"E0 冻结基线早已整体过期"。**
本轮未改任何判据、未改基线、未改生产代码（消融用的临时回退已按 `git checkout HEAD --` 复原并逐字节核验）。

## 1. 消融设计与执行（单变量：只换两个生产文件）

被测：`frontend/test_wind_injection.py::WindInjectionEquivalenceTests.test_every_run_reproduces_e0_bit_for_bit`
它做两件事——(i) 用当前代码重跑 `experiments/presets/e0_baseline.yaml`，(ii) 与冻结产物
`results/experiments/e0_baseline_20261002-235335/raw_runs.csv` 逐 run 逐指标比。

| 面 | 树的状态 | 命令 |
|---|---|---|
| HEAD | 原样 | `discover -s frontend -t frontend -p "test_wind*.py"` |
| pre-D-iv | **仅** `frontend/environment.py` + `frontend/drone.py` 回退到 `3c54c37^`，其余全用 HEAD | 同一条命令 |

⇒ 刻意不用 `git worktree` / 整树 checkout：那会一次换掉几十个文件，就不是受控消融了。

## 2. 一手结果：**差异键集两侧完全相同** ⇒ 假设被否证

```
HEAD      : Ran 19 tests … FAILED (failures=1)  —— E1+静风未逐字复现 E0（12 处）
pre-D-iv  : Ran 19 tests … FAILED (failures=1)  —— E1+静风未逐字复现 E0（12 处）
$ diff <(HEAD 侧 12 个 "格/指标" 键 | sort) <(pre-D-iv 侧同样 12 个键 | sort)
IDENTICAL_KEY_SETS        ← 12 vs 12，逐项相同
```
受影响格次（两侧一致）：`C1/C2 × rep1/rep2/rep3` 的
`从分配到实际装载上机等待时间` 与 `从上机到送达平均时间`。例：
```
C1/rep1/从分配到实际装载上机等待时间: E0=46.72641509433962  E1zero=76.90566037735849
C2/rep1/从分配到实际装载上机等待时间: E0=42.71621621621622  E1zero=78.56756756756756
```
⇒ **把 D-iv 撤掉，这 12 处一格不少。** 所以"D-iv 改了 completion/assignment 时序导致等价门红"这个我上轮登记的猜测是**错的**，在此撤回。

## 3. 真因（可复算，不是叙述）：E0 冻结基线的源码指纹早已不匹配

`reproducibility.json` 里钉着 `core_source_sha256`（16 个文件的 sha256）。逐文件比对：

```
pinned=16  identical=12  DIFFERENT=4  missing=0
   experiments/worker.py          base=115953a7cbe1fff2  head=5d14ec0fcfc45417
   frontend/drone.py              base=6ab6ff3321b7921f  head=fae438dd91006d1f
   frontend/environment.py        base=ba1109906f47f3d4  head=658d818d681b342d
   frontend/greedy/scheduler.py   base=71a7d4a7e58ad46f  head=9cbb03e6bdac1388
```
关键一问：**pre-D-iv 那棵树等于基线 pin 吗？**
```
frontend/environment.py  pre-D-iv==pin? False     HEAD==pin? False
frontend/drone.py        pre-D-iv==pin? False     HEAD==pin? False
```
⇒ **不等。** 也就是说：基线生成于 `generated_at_utc=2026-10-03T03:53:35Z`（commit `1c790a0dbf9f`），
而它在**D-iv 之前**就已经被别的改动越过了。等价门比的从来不是"同一份代码 + 一个 wind 开关"，
而是"今天这份代码 vs 一份 5 天前且从未同步过的代码"。

⇒ 所以这条红的正确定性是：**[夹具失效] E0 冻结基线已过期（4/16 承重文件漂移），不是被测行为回归，也不是实现缺陷。**
它与 #69-H3 那次"buffer_peak 从 15 掉到 10"不同类——那次是业务语义变更后旧读数作废；这次是**基线本身没随仓库推进而重生成**。

## 4. 因此不能做什么（等裁，本轮一律不做）

- ✗ **不得为了让它绿而放宽判据或改基线**（主控明令）。
- ✗ 也不得直接宣布"等价性不成立"——本消融只证明了"当前无法判定"，因为参照物无效。
- ✓ 正确的下一步是**重生成 E0 基线**：在当前树上重跑 e0_baseline 预设、写入新的 `reproducibility.json` 指纹，
  然后让等价门重新成为有效证人。但这件事必须单独授权，理由两条：
  (i) 它会覆盖 `results/experiments/e0_baseline_20261002-235335/`（已入库产物）；
  (ii) 重生成之后这条门就不再是"E1 之前的基线"，其历史含义改变，属对外口径事项。

## 5. 顺带产出一条通用不变量（值得门化，但需批准）

本次能一眼看穿，全靠 `reproducibility.json` 里已经有 `core_source_sha256`——只是**没人核对它**。
建议（等裁，本轮不实现）：加一条常驻门，断言"每个被引用的冻结实验产物，其 `core_source_sha256`
与盘上当前文件一致；不一致则必须能在 CHANGELOG 里找到该产物的『已声明过期』条目"，否则红。
⇒ 这属于 `[G]` 而非 `[P]`，因为它能在下一次基线悄悄过期时报警，而不是靠人来问"为什么红"。

## 6. 复算命令

```bash
# 两面各跑一次（HEAD 面已存档 F_frontend_suite_after_wiring_still_red.log）
python -m unittest discover -s frontend -t frontend -p "test_wind*.py"

# 差异键集对照（本报告 §2 的 IDENTICAL_KEY_SETS）
#   分别从两份日志里抽 "^  C[0-9]/rep[0-9]/[^:]+:" 排序后 diff

# 基线指纹对账（§3 的 4/16）
python -c "import json,io,hashlib,pathlib;d=json.load(io.open('results/experiments/e0_baseline_20261002-235335/reproducibility.json',encoding='utf-8'));print(sum(1 for k,v in d['core_source_sha256'].items() if pathlib.Path(k).is_file() and hashlib.sha256(pathlib.Path(k).read_bytes()).hexdigest()==v),'/',len(d['core_source_sha256']),'match')"
```

---

## 7. 同日后续：本报告 §3 那句定性**不完整**（重生成后测出来的）

本报告把红判为「[夹具失效] ⇒ 参照物无效 ⇒ 不可判定」。授权重生成 E0 之后实测发现，这个说法**只说对了一半**：

| 事实 | 本轮读数 |
|---|---|
| 参照物当时确实过期 | ✓ 成立（pin 4/16 漂移，撤掉 D-iv 后差异一格不少 —— 本报告的消融仍然有效） |
| 过期是红的**唯一**成因 | ✗ **不成立**。新基线 `e0_baseline_20261008-210053`（pin 16/16 自洽）与旧 E0 在门比较的列区间上有 **12 格系统差**（`从分配到实际装载上机等待时间`、`从上机到送达平均时间` 各 6 格） |
| 新基线是否可信 | ✓ 同命令重跑第二遍，比较范围内 **0 格差**（只有 `耗时秒` 漂）⇒ 当前树自一致 |
| 旧两批之间 | 已入库的第二批 `e0_baseline_20261003-230126`（10-03，commit `a298d6d`）与旧 E0 在这两列上**完全一致** ⇒ 差异发生在 `a298d6d` 之后、`d19d647` 之前 |

⇒ 所以"不可判定"应改写为：**门的红 = 参照物过期 + 一次未归因的生产侧指标变动，两者叠加**。
指向 NEW 时 zero-wind 逐 run == E0 **成立**（门绿）；但这不等于它相对 10-02 那批没变过。

那次变动的**归因没有做**（不在"重生成基线"的授权范围内），登记为待裁 (iii)。
完整三方对照读数与复算命令：`docs/取证输出/p70_p5_e0_regen/D_three_way_comparison.md`。

⚠ 本报告 §4 那条「不得为了让它绿而放宽判据或改基线」仍然有效且已被遵守：
重生成走的是**单独授权**，且生成那一笔零生产代码改动；判据（逐 run 逐指标、`keys[10:]`）一字未动。
