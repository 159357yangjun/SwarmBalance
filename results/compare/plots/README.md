# 本目录已作废（VOID）—— 不要用于答辩、不要用于论文配图

**结论先说**：下面 12 张图与 3 份派生表里仍含 **6 个已被撤除的 MARL 算法**
（`iql` / `iql_u` / `vdn` / `vdn_u` / `qmix` / `qmix_u`）。这些行的数字在
`docs/数据来源与可追溯性登记表.md` 第五节 R2 已被逐格证伪（54 个性能格里 23 个优于该算法
历史上最好的一局、38 个与任何 train/test 行都不相等），并于 6b8c4c8 从数据源与对比页撤除。
**撤除没到达本目录**，所以这里的图与表现在仍然是一批"结论已被否掉"的产物。

## 凭什么说它没被撤除覆盖（一手证据）

| 事实 | 实测方式 |
|---|---|
| 三份派生表各 10 行算法：greedy / pso / ga / ortools + 上面那 6 个 | `csv.reader` 读第一列，断言写在 `console/test_plots_archive_void.py` |
| 整个目录最后一次入库改动停在 `fcc7c5f`（2026-09-11） | `git log -1 -- results/compare/plots` |
| `fcc7c5f` 是 `6b8c4c8`（2026-09-29 撤除 MARL）的**祖先** —— 即那次撤除从未碰过这里 | `git merge-base --is-ancestor fcc7c5f 6b8c4c8` |
| 当前出图脚本在这批数据上**拒绝**出图（混口径），所以也不可能"顺手刷新"过这里 | `python results/plot_compare_metrics.py` → 退出码 1，原文以 `[REFUSED]` 开头 |

另有一处口径不一致值得记下：本目录 `combined_compare_metrics.csv` 里 `ga` 记的是
**2000 步 / 60 任务**，而现已入库的 `results/compare/backend_ga_metrics.csv` 是
**400/600 步、22/30 任务** —— 同目录并存两份不同口径的 GA，谁也不知道图上那根 GA 柱是哪来的。

### 已实测 vs 尚未实测（别把推断当成核过）

- **实测**：三份派生表的算法列确实是上面 10 个（含 6 个已撤除）；12 张 PNG 的最后一次入库
  改动逐张查过，全部是 `fcc7c5f`（与那三份表同一次提交、同批产物）。
- **未实测**：PNG 的**像素里**是否真画着 6 根 MARL 柱，没有单独核验 —— 位图无法像 CSV 那样
  读列核对，只能靠"同批、同一脚本、同一输入表"推断。要坐实这件事，只能按下面的顺序重跑
  生成器再逐张比对。作废判断不依赖这一条：只要派生表还带着那六行，这批产物就不能当证据用。

## 为什么默认不就地重生

出图入口默认只写 `results/adhoc/plots/`（已 gitignore）。要把结果刷进这里需要
`--record-into-evidence`，而它今天会先被口径门禁拒绝：GA 与三个 2000 步基线不同口径。
**补齐顺序**（不是改判据，是把数据补齐）：

1. 按结项口径重跑 GA：`episode_max_steps=3600`、`episodes=5`、`seed 101–105`
   （与 `one_click_latest.csv` 同口径，见 `results/compare/README.md` 的 manifest）；
2. 确认 `python results/compare_gate.py --check-all` 通过；
3. 再跑 `python results/plot_compare_metrics.py --record-into-evidence`。

## 本文件由谁保证不失效

`console/test_plots_archive_void.py`：
① 断言这三份表的算法列就是上面那 10 个（含 6 个已撤除的）——若有人清了 MARL 行却忘了撤销本通知，
测试会红并提示改这里（双向指纹，避免"作废声明"反过来过期）；
② 断言本文件确实写着"作废"并逐个点名那 6 个算法；
③ 断言 `fcc7c5f` 是 `6b8c4c8` 的祖先（撤除未到达本目录这件事不能只靠人记）；
④ 判别式：喂一份"去掉 MARL 行"的表，判据必须不认它。
